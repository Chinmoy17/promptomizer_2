"""Reflective multi-round FDPO (`--method reflect_fdpo`).

Derived from `simple_loop.run_simple_optimization` (which stays byte-identical
as the blind control arm — diff the two files to see the mechanism delta).
Two changes from the blind mechanism:

  1. ALL current mining failures AND all currently-correct mining items are
     shown every round (no `n_fail`/`n_gold` sampling cap) — the optimizer
     never sees a subset of what is currently wrong or currently working.
  2. From round 2 on, the optimizer is shown the MEASURED EFFECT of its own
     previous rewrite in full, on BOTH sets: every mining item it recovered
     and regressed (regressions include the solver's new wrong answer), the
     previous text of every section it changed, AND every validation item it
     recovered/regressed (same detail). Validation is intentionally no longer
     blind to the optimizer.

Consequence of (2): once validation's items are visible to the optimizer, its
accuracy is no longer a fully independent signal of generalization — the
optimizer can specifically target what it will be scored on next round. That
motivated an earlier version of this mechanism to ship whichever round was
simply LAST, ignoring validation for the selection itself. In practice that
threw away real signal: a real run's round 2 beat round 3 on BOTH mining
(0.862 vs 0.828) AND validation (0.633 vs 0.533) by a wide margin, yet
"last round" shipped round 3 anyway. So the mechanism now ships whichever
COMMITTED round has the best validation accuracy (mining accuracy if the val
split is disabled) — using validation as the best signal available, however
imperfect, rather than discarding it. Every round still commits
unconditionally (so a bad round doesn't block a later good one from being
found), but the FINAL choice of which round to ship is a comparison across
all of them. There is still no accept-margin gate against baseline (removed
earlier after this project's own reruns showed a round's val accuracy vs.
the untouched baseline is noisy enough that gating on it discarded as much
signal as it protected) and the run never reverts to the untouched seed
UNLESS no round ever committed at all (never triggered, or skipped for an
already-high baseline) — in that case there is nothing to choose among, and
the seed was never touched anyway.

Test is handled entirely by the caller and is never touched here, in either
mechanism.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from fdpo.clients.base import ModelClient
from fdpo.config import ExperimentConfig
from fdpo.core.registry import GateResult, PromptRegistry
from fdpo.data.loaders import Example, _stratified_take
from fdpo.data.md_prompt import parse_markdown, save_markdown_prompt, to_markdown
from fdpo.eval.evaluator import evaluate
from fdpo.prompts.reflect_optimizer_prompt import build_reflect_optimizer_messages

logger = logging.getLogger("fdpo")


def run_reflect_optimization(cfg: ExperimentConfig, registry: PromptRegistry,
                             train: list[Example], dataset: str,
                             solver: ModelClient, optimizer: ModelClient,
                             run_dir: Path, *,
                             judge: ModelClient | None = None,
                             external: ModelClient | None = None) -> dict:
    """Multi-round FDPO where the optimizer sees the full per-item effect of
    its own previous rewrite on both mining and validation. Every round
    commits unconditionally; ships whichever committed round has the BEST
    validation accuracy (see module docstring for why, and for why this
    never falls back to the untouched seed once at least one round has
    committed). Test evaluation is done by the caller.
    """
    rng = random.Random(cfg.seed)
    train_by_id = {ex.id: ex for ex in train}
    max_rounds = max(1, int(cfg.simple_max_rounds))

    # 0. Mining / validation split (identical to simple_fdpo).
    val_frac = float(cfg.simple_val_frac)
    if 0.0 < val_frac < 1.0 and len(train) >= 4:
        n_mining = max(1, round(len(train) * (1.0 - val_frac)))
        n_mining = min(n_mining, len(train) - 1)   # guarantee >= 1 validation
        mining, validation = _stratified_take(train, n_mining, rng)
        has_val_split = True
        logger.info("reflect: train split -> mining=%d, validation=%d "
                    "(val_frac=%.2f, stratified)", len(mining), len(validation),
                    val_frac)
    else:
        mining = list(train)
        validation = list(train)
        has_val_split = False
        logger.warning("reflect: validation split disabled (val_frac=%.2f, "
                       "n_train=%d) -- scoring candidates in-sample on the "
                       "mining set", val_frac, len(train))

    # 1. Baseline eval on the MINING set.
    logger.info("reflect: baseline eval on %d mining examples", len(mining))
    baseline = evaluate(solver, registry.active_prompt(), mining, dataset,
                        temperature=cfg.solver_temperature,
                        max_tokens=cfg.solver_max_tokens, purpose="reflect:baseline",
                        max_workers=cfg.max_workers, judge=judge, external=external)
    baseline_correct = baseline.correct_ids()
    baseline_wrong = baseline.wrong_ids()
    logger.info("reflect: baseline mining accuracy %.3f (%d correct, %d wrong)",
                baseline.accuracy, len(baseline_correct), len(baseline_wrong))

    # Near-ceiling guard (identical to simple_fdpo).
    skip_high = cfg.skip_above_acc > 0.0 and baseline.accuracy >= cfg.skip_above_acc
    if skip_high:
        logger.info("reflect: baseline mining accuracy %.3f >= skip_above_acc %.3f "
                    "-- skipping optimization (near-ceiling); keeping seed prompt",
                    baseline.accuracy, cfg.skip_above_acc)

    # Baseline eval on the (now non-blind) VALIDATION set. Keep the full
    # EvalResult -- the reflection report needs per-item validation churn
    # with real question/output/gold detail, not just counts.
    prev_val_wrong: set[str] | None = None
    if has_val_split and not skip_high:
        baseline_val = evaluate(solver, registry.active_prompt(), validation, dataset,
                                temperature=cfg.solver_temperature,
                                max_tokens=cfg.solver_max_tokens,
                                purpose="reflect:baseline-val",
                                max_workers=cfg.max_workers, judge=judge,
                                external=external)
        baseline_val_acc = baseline_val.accuracy
        prev_val_wrong = baseline_val.wrong_ids()
    else:
        baseline_val_acc = baseline.accuracy
    logger.info("reflect: baseline validation accuracy %.3f", baseline_val_acc)

    save_markdown_prompt(registry.active_prompt(), run_dir / "prompt_baseline.md",
                         schema=registry.schema)

    # 2. Cache baseline outputs so failures always show the CURRENT prompt's
    #    actual wrong answer. baseline_details carries verifier-dataset
    #    constraint-violation text (empty "" for every other dataset).
    baseline_outputs = {r.example_id: r.output for r in baseline.rows}
    baseline_details = {r.example_id: r.detail for r in baseline.rows}

    # 3. Multi-round loop. Every round is committed and becomes the parent of
    #    the next (so a bad round doesn't block a later good one). `best_*`
    #    tracks whichever COMMITTED round has scored highest so far on the
    #    comparison metric (validation accuracy, or mining accuracy if the
    #    val split is disabled) -- `best_round_num` starts at 0 (the seed) but
    #    `best_val_acc` starts below any real score, so the FIRST committed
    #    round always displaces it; the untouched seed can only ever "win" by
    #    never being displaced, i.e. if no round ever commits at all.
    best_round_num = 0
    best_val_acc = float("-inf")
    best_wrong = baseline_wrong
    best_correct = baseline_correct
    best_result = baseline
    current_wrong = baseline_wrong
    current_correct = baseline_correct
    optimizer_calls = 0
    rounds_log: list[dict] = []
    triggered = False
    any_committed = False
    final_edit_status = "skipped_high_baseline" if skip_high else "not_triggered"

    current_outputs = baseline_outputs
    current_details = baseline_details
    prev_val_acc = baseline_val_acc      # validation accuracy of the CURRENT prompt
    reflection: dict | None = None       # effect report of the last committed round

    effective_rounds = 0 if skip_high else max_rounds
    for round_num in range(1, effective_rounds + 1):
        # ALL current failures are shown -- no sampling cap. n_fail no longer
        # applies to reflect_fdpo (it still governs simple_fdpo unchanged).
        # "gold" here means "why this counts as wrong": for verifier datasets
        # (ifeval/ifbench) current_details carries the DYNAMIC constraint
        # violations of the CURRENT output (which constraint, why); for every
        # other dataset current_details is empty and this falls back to the
        # example's static reference/gold text, unchanged from before.
        failures = [
            {
                "question": train_by_id[eid].question,
                "output": current_outputs.get(eid, "(wrong)"),
                "gold": current_details.get(eid) or train_by_id[eid].reference,
                "example_id": eid,
            }
            for eid in current_wrong
        ]
        if len(failures) < cfg.tau:
            logger.info("reflect: round %d skipped — |F|=%d < tau=%d (converged)",
                        round_num, len(failures), cfg.tau)
            rounds_log.append({
                "round": round_num,
                "status": "below_tau",
                "n_failures_before": len(failures),
            })
            if round_num == 1:
                final_edit_status = "not_triggered"
            break

        triggered = True
        corrects = [train_by_id[eid] for eid in current_correct]
        e_fail = list(failures)   # ALL failures, not a sample
        e_gold = list(corrects)   # ALL currently-correct mining items, not a sample
        logger.info("reflect: round %d — |F|=%d, showing ALL %d failures + "
                    "ALL %d golds%s", round_num, len(failures), len(e_fail),
                    len(e_gold), " (with effect report)" if reflection else "")

        current_md = to_markdown(registry.active_prompt(), schema=registry.schema)
        messages = build_reflect_optimizer_messages(
            current_md, e_fail, e_gold, dataset=dataset,
            round_num=round_num, max_rounds=effective_rounds,
            reflection=reflection)
        result = optimizer.complete(messages, temperature=cfg.optimizer_temperature,
                                    max_tokens=8000,
                                    purpose=f"reflect:rewrite-r{round_num}")
        optimizer_calls += 1

        try:
            new_sections = parse_markdown(result.text)
        except ValueError as e:
            logger.warning("reflect: round %d parse failed (%s); continuing to next round",
                           round_num, e)
            rounds_log.append({
                "round": round_num,
                "status": "parse_failed",
                "n_failures_before": len(failures),
            })
            continue

        missing = set(registry.schema) - set(new_sections)
        if missing:
            logger.warning("reflect: round %d optimizer omitted sections %s; backfilling",
                           round_num, sorted(missing))
            for k in missing:
                new_sections[k] = registry.active_prompt()[k]

        for k in cfg.pin_sections:
            if k in registry.schema:
                new_sections[k] = registry.active_prompt()[k]

        changed = {name: new_sections[name] for name in registry.schema
                   if new_sections.get(name, "") != registry.active_prompt()[name]}
        if not changed:
            logger.info("reflect: round %d — optimizer proposed no changes; continuing",
                        round_num)
            rounds_log.append({
                "round": round_num,
                "status": "no_change",
                "n_failures_before": len(failures),
            })
            continue

        # Capture the OLD text of each edited section BEFORE committing — the
        # next round's effect report shows the optimizer what it changed FROM.
        old_texts = {k: registry.active_prompt()[k] for k in changed}

        candidate_prompt = registry.prompt_with_edits(changed)
        logger.info("reflect: round %d -- re-evaluating mining+validation with new "
                    "prompt (%d sections changed)", round_num, len(changed))
        new_eval = evaluate(solver, candidate_prompt, mining, dataset,
                            temperature=cfg.solver_temperature,
                            max_tokens=cfg.solver_max_tokens,
                            purpose=f"reflect:round{round_num}",
                            max_workers=cfg.max_workers, judge=judge,
                            external=external)
        new_wrong = new_eval.wrong_ids()
        new_correct = new_eval.correct_ids()
        if has_val_split:
            val_eval = evaluate(solver, candidate_prompt, validation, dataset,
                                temperature=cfg.solver_temperature,
                                max_tokens=cfg.solver_max_tokens,
                                purpose=f"reflect:round{round_num}-val",
                                judge=judge, external=external,
                                max_workers=cfg.max_workers)
            cand_val_acc = val_eval.accuracy
            val_wrong = val_eval.wrong_ids()
            val_new_outputs = {r.example_id: r.output for r in val_eval.rows}
            val_new_details = {r.example_id: r.detail for r in val_eval.rows}
        else:
            cand_val_acc = new_eval.accuracy
            val_wrong = None
            val_new_outputs = {}
            val_new_details = {}

        # Full per-item churn of THIS rewrite, on BOTH sets.
        recovered_ids = sorted(current_wrong - new_wrong)
        regressed_ids = sorted(new_wrong - current_wrong)
        new_outputs = {r.example_id: r.output for r in new_eval.rows}
        new_details = {r.example_id: r.detail for r in new_eval.rows}
        if val_wrong is not None and prev_val_wrong is not None:
            val_recovered_ids = sorted(prev_val_wrong - val_wrong)
            val_regressed_ids = sorted(val_wrong - prev_val_wrong)
        else:
            val_recovered_ids = []
            val_regressed_ids = []

        gate = GateResult(
            acc_old=1.0 - len(current_wrong) / max(len(current_wrong) + len(current_correct), 1),
            acc_new=new_eval.accuracy,
            rho=0.0,
            passed=True,
            batch_size=len(train),
            n_failures=len(failures),
            recovered_failures=len(recovered_ids),
            broke=len(regressed_ids),
        )
        registry.commit_bundle(changed, round_num=round_num, gate=gate)
        any_committed = True
        final_edit_status = "committed"

        # Every round commits (so a bad round doesn't block a later good
        # one), but only the best-by-validation (or best-by-mining, if no
        # val split) round is tracked as the one to actually ship -- see
        # module docstring. `registry.restore_round()` reconstructs this
        # round's exact prompt at the end regardless of what committed after
        # it.
        if cand_val_acc > best_val_acc:
            best_round_num = round_num
            best_val_acc = cand_val_acc
            best_wrong = new_wrong
            best_correct = new_correct
            best_result = new_eval

        rounds_log.append({
            "round": round_num,
            "status": "committed",
            "n_failures_before": len(failures),
            "n_failures_after": len(new_wrong),
            "train_acc_after": new_eval.accuracy,
            "val_acc_after": cand_val_acc,
            "sections_changed": sorted(changed.keys()),
            "failing_ids_before": sorted(current_wrong),
            "failing_ids_after": sorted(new_wrong),
            "recovered_this_round": recovered_ids,
            "regressed_this_round": regressed_ids,
            "val_recovered_this_round": len(val_recovered_ids),
            "val_regressed_this_round": len(val_regressed_ids),
            "reflection_shown": reflection is not None,
        })
        logger.info(
            "reflect: round %d COMMITTED -- |F| %d -> %d, mining acc %.3f -> %.3f, "
            "val acc %.3f -> %.3f (val churn +%d/-%d)",
            round_num, len(failures), len(new_wrong),
            gate.acc_old, new_eval.accuracy, prev_val_acc, cand_val_acc,
            len(val_recovered_ids), len(val_regressed_ids),
        )

        # Build the EFFECT REPORT the next round's optimizer will see: what
        # this rewrite changed, and everything it recovered/regressed on BOTH
        # mining and validation (full detail, no caps) -- regressions include
        # the solver's new wrong answer.
        reflection = {
            "prev_round": round_num,
            "changed_sections": [
                {"section": k, "previous_text": old_texts[k]}
                for k in sorted(changed)
            ],
            "mining_recovered": [
                {"question": train_by_id[eid].question,
                 "gold": train_by_id[eid].reference}
                for eid in recovered_ids
            ],
            "mining_regressed": [
                {"question": train_by_id[eid].question,
                 "output": new_outputs.get(eid, "(wrong)"),
                 "gold": new_details.get(eid) or train_by_id[eid].reference}
                for eid in regressed_ids
            ],
            "val_recovered": [
                {"question": train_by_id[eid].question,
                 "gold": train_by_id[eid].reference}
                for eid in val_recovered_ids
            ],
            "val_regressed": [
                {"question": train_by_id[eid].question,
                 "output": val_new_outputs.get(eid, "(wrong)"),
                 "gold": val_new_details.get(eid) or train_by_id[eid].reference}
                for eid in val_regressed_ids
            ],
            "val_before": prev_val_acc if has_val_split else None,
            "val_after": cand_val_acc if has_val_split else None,
        }

        current_outputs = new_outputs
        current_details = new_details
        prev_val_acc = cand_val_acc
        if val_wrong is not None:
            prev_val_wrong = val_wrong

        # ALWAYS continue — the next round starts from this round's output.
        current_wrong = new_wrong
        current_correct = new_correct

    # No accept gate against baseline, and no fallback to the untouched seed
    # once anything has committed: ship whichever COMMITTED round scored
    # best (validation, or mining if no val split) -- see module docstring.
    # restore_round() reconstructs that round's exact prompt from full
    # version history, regardless of what a LATER round subsequently did.
    ship_structured = any_committed
    if ship_structured:
        registry.restore_round(best_round_num)
        logger.info(
            "reflect: SHIP round %d (best val acc %.3f, baseline val %.3f) "
            "-- best-of-committed-rounds, never falls back to baseline",
            best_round_num, best_val_acc, baseline_val_acc,
        )
    else:
        reason = ("baseline at/above skip_above_acc; optimization skipped"
                  if skip_high else "no round was committed (never triggered)")
        logger.info("reflect: nothing to ship (%s) -- active prompt is "
                    "already the untouched seed", reason)

    save_markdown_prompt(registry.active_prompt(), run_dir / "prompt_current.md",
                         schema=registry.schema)

    # 4. Confusion matrix on the mining batch (baseline vs. the shipped round).
    recoveries = sorted(baseline_wrong & best_correct)
    regressions = sorted(baseline_correct & best_wrong)
    still_wrong = sorted(baseline_wrong & best_wrong)
    still_right = len(baseline_correct & best_correct)
    net_gain = len(recoveries) - len(regressions)

    logger.info(
        "reflect: MINING confusion matrix -- recovered %d, regressed %d, "
        "still wrong %d, still right %d, net_gain %+d",
        len(recoveries), len(regressions), len(still_wrong), still_right, net_gain,
    )
    logger.info("reflect: MINING accuracy %.3f -> %.3f (delta %+.3f)",
                baseline.accuracy, best_result.accuracy,
                best_result.accuracy - baseline.accuracy)

    return {
        "mode": "reflect",
        "edit_status": final_edit_status,
        "triggered": triggered,
        "tau": cfg.tau,
        "skip_above_acc": cfg.skip_above_acc,
        "skipped_high_baseline": skip_high,
        "simple_max_rounds": max_rounds,
        "accept_margin": cfg.accept_margin,
        "shipped_structured": ship_structured,
        "selection": "best_of_rounds",  # ships whichever committed round
                                        # scored best on validation (mining
                                        # if no val split); never baseline
                                        # unless nothing ever committed.
        "shipped_round": best_round_num if any_committed else None,
        "val_split": {
            "enabled": has_val_split,
            "val_frac": val_frac,
            "n_mining": len(mining),
            "n_validation": len(validation) if has_val_split else 0,
        },
        "baseline_val_acc": baseline_val_acc,
        # The genuine best validation accuracy among all committed rounds
        # (this is the round that actually ships). None if nothing committed.
        "best_structured_val_acc": best_val_acc if any_committed else None,
        "n_failures_triggering": len(baseline_wrong),
        "optimizer_calls": optimizer_calls,
        "rounds_log": rounds_log,
        "baseline_failing_ids": sorted(baseline_wrong),
        "solver_temperature": cfg.solver_temperature,
        "optimizer_temperature": cfg.optimizer_temperature,
        "baseline_train": {
            "accuracy": baseline.accuracy,
            "n_correct": len(baseline_correct),
            "n_wrong": len(baseline_wrong),
        },
        "current_train": {
            "accuracy": best_result.accuracy,
            "n_correct": len(best_correct),
            "n_wrong": len(best_wrong),
        },
        "train_confusion": {
            "recoveries": recoveries,
            "regressions": regressions,
            "still_wrong": still_wrong,
            "still_right_count": still_right,
            "net_gain": net_gain,
        },
        # Compatibility with the run_experiment metrics pipeline.
        "rewrites": [],
        "registry_counts": registry.counts(),
        "rounds_run": len([r for r in rounds_log
                            if r["status"] == "committed"]),
        "train_acc_per_round": [
            r.get("train_acc_after", best_result.accuracy) for r in rounds_log
        ] if rounds_log else [best_result.accuracy],
        "time_to_stabilization": None,
        "judge_parse_failures": 0,
    }
