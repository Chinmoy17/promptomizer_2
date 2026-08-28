"""Reflective multi-round FDPO (`--method reflect_fdpo`).

Derived from `simple_loop.run_simple_optimization` (which stays byte-identical
as the blind control arm — diff the two files to see the mechanism delta).
One change: from round 2 on, the optimizer is shown the MEASURED EFFECT of its
own previous rewrite instead of a counts-only hint:

  - the previous text of every section it changed,
  - the specific mining items its edit recovered / regressed (regressions
    include the solver's NEW wrong answer),
  - the aggregate held-out validation movement (counts only — raw validation
    items are never shown to the optimizer, so the accept gate stays fair).

Everything else — mining/validation split, per-round evals, keep-best on
validation, lenient accept gate, sealed test handled by the caller — is
unchanged from `simple_fdpo`.

Round-by-round data flow (mining M, validation V; test never touched here):

    v0 (seed): eval on M (failures for round 1) + V (gate reference)
    round r:   optimizer sees current failures on M
               + (r >= 2) effect report of round r-1's rewrite
               -> v_r; eval v_r on M (next failures + effect detail)
                        and on V (keep-best score, aggregate effect counts)
    ship: best-of-rounds by V accuracy, if >= baseline V - accept_margin
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
                             run_dir: Path) -> dict:
    """Multi-round FDPO where the optimizer sees the per-item effect of its
    own previous rewrite. See module docstring. Test evaluation is done by
    the caller.
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
                        max_workers=cfg.max_workers)
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

    # Baseline eval on the held-out VALIDATION set. Unlike simple_fdpo we keep
    # the full EvalResult (not just the accuracy): the reflection report needs
    # per-item validation churn COUNTS (never the items themselves).
    prev_val_wrong: set[str] | None = None
    if has_val_split and not skip_high:
        baseline_val = evaluate(solver, registry.active_prompt(), validation, dataset,
                                temperature=cfg.solver_temperature,
                                max_tokens=cfg.solver_max_tokens,
                                purpose="reflect:baseline-val",
                                max_workers=cfg.max_workers)
        baseline_val_acc = baseline_val.accuracy
        prev_val_wrong = baseline_val.wrong_ids()
    else:
        baseline_val_acc = baseline.accuracy
    logger.info("reflect: baseline validation accuracy %.3f", baseline_val_acc)

    save_markdown_prompt(registry.active_prompt(), run_dir / "prompt_baseline.md",
                         schema=registry.schema)

    registry.record_round(passed=True, acc=baseline.accuracy)

    # 2. Cache baseline outputs so failures always show the CURRENT prompt's
    #    actual wrong answer.
    baseline_outputs = {r.example_id: r.output for r in baseline.rows}

    # 3. Multi-round loop, keep-best on validation (identical skeleton to
    #    simple_fdpo). `reflection` carries the effect report of the last
    #    COMMITTED rewrite into the next optimizer call.
    best_val_acc = -1.0
    best_wrong = baseline_wrong
    best_correct = baseline_correct
    best_result = baseline
    current_wrong = baseline_wrong
    current_correct = baseline_correct
    optimizer_calls = 0
    rounds_log: list[dict] = []
    triggered = False
    final_edit_status = "skipped_high_baseline" if skip_high else "not_triggered"

    current_outputs = baseline_outputs
    prev_val_acc = baseline_val_acc      # validation accuracy of the CURRENT prompt
    reflection: dict | None = None       # effect report of the last committed round

    effective_rounds = 0 if skip_high else max_rounds
    for round_num in range(1, effective_rounds + 1):
        failures = [
            {
                "question": train_by_id[eid].question,
                "output": current_outputs.get(eid, "(wrong)"),
                "gold": train_by_id[eid].reference,
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
        e_fail = rng.sample(failures, min(cfg.n_fail, len(failures)))
        e_gold = rng.sample(corrects, min(cfg.n_gold, len(corrects))) if corrects else []
        logger.info("reflect: round %d — |F|=%d, sampled %d failures + %d golds%s",
                    round_num, len(failures), len(e_fail), len(e_gold),
                    " (with effect report)" if reflection else "")

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
                            max_workers=cfg.max_workers)
        new_wrong = new_eval.wrong_ids()
        new_correct = new_eval.correct_ids()
        if has_val_split:
            val_eval = evaluate(solver, candidate_prompt, validation, dataset,
                                temperature=cfg.solver_temperature,
                                max_tokens=cfg.solver_max_tokens,
                                purpose=f"reflect:round{round_num}-val",
                                max_workers=cfg.max_workers)
            cand_val_acc = val_eval.accuracy
            val_wrong = val_eval.wrong_ids()
        else:
            cand_val_acc = new_eval.accuracy
            val_wrong = None

        # Per-item churn of THIS rewrite on the mining set, and aggregate
        # churn on the validation set (counts only).
        recovered_ids = sorted(current_wrong - new_wrong)
        regressed_ids = sorted(new_wrong - current_wrong)
        new_outputs = {r.example_id: r.output for r in new_eval.rows}
        if val_wrong is not None and prev_val_wrong is not None:
            val_recovered = len(prev_val_wrong - val_wrong)
            val_regressed = len(val_wrong - prev_val_wrong)
        else:
            val_recovered = val_regressed = 0

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

        is_new_best = cand_val_acc > best_val_acc
        if is_new_best:
            registry.record_round(passed=True, acc=cand_val_acc)
            best_val_acc = cand_val_acc
            best_wrong = new_wrong
            best_correct = new_correct
            best_result = new_eval
            final_edit_status = "committed"
        elif final_edit_status == "not_triggered":
            final_edit_status = "committed"

        rounds_log.append({
            "round": round_num,
            "status": "committed_best" if is_new_best else "committed",
            "n_failures_before": len(failures),
            "n_failures_after": len(new_wrong),
            "train_acc_after": new_eval.accuracy,
            "val_acc_after": cand_val_acc,
            "sections_changed": sorted(changed.keys()),
            "failing_ids_before": sorted(current_wrong),
            "failing_ids_after": sorted(new_wrong),
            "recovered_this_round": recovered_ids,
            "regressed_this_round": regressed_ids,
            "val_recovered_this_round": val_recovered,
            "val_regressed_this_round": val_regressed,
            "reflection_shown": reflection is not None,
        })
        logger.info(
            "reflect: round %d COMMITTED -- |F| %d -> %d, mining acc %.3f -> %.3f, "
            "val acc %.3f -> %.3f (val churn +%d/-%d)%s",
            round_num, len(failures), len(new_wrong),
            gate.acc_old, new_eval.accuracy, prev_val_acc, cand_val_acc,
            val_recovered, val_regressed,
            " (new best)" if is_new_best else " (not best, continuing)",
        )

        # Build the EFFECT REPORT the next round's optimizer will see: what
        # this rewrite changed, what it recovered/regressed on mining (per
        # item, regressions with the solver's new wrong answer), and how the
        # held-out validation moved (aggregate counts only).
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
                 "gold": train_by_id[eid].reference}
                for eid in regressed_ids
            ],
            "n_mining_recovered": len(recovered_ids),
            "n_mining_regressed": len(regressed_ids),
            "val_before": prev_val_acc if has_val_split else None,
            "val_after": cand_val_acc if has_val_split else None,
            "val_recovered": val_recovered,
            "val_regressed": val_regressed,
        }

        current_outputs = new_outputs
        prev_val_acc = cand_val_acc
        if val_wrong is not None:
            prev_val_wrong = val_wrong

        # ALWAYS continue — the next round starts from this round's output.
        current_wrong = new_wrong
        current_correct = new_correct

    # LENIENT accept gate (identical to simple_fdpo).
    structured_exists = best_val_acc >= 0.0
    ship_structured = structured_exists and (
        best_val_acc >= baseline_val_acc - cfg.accept_margin
    )
    if ship_structured:
        logger.info(
            "reflect: ACCEPT structured prompt (best val acc %.3f, baseline val "
            "%.3f, margin %.2f) -- shipping to test",
            best_val_acc, baseline_val_acc, cfg.accept_margin,
        )
        registry.restore_best_snapshot()
    else:
        if structured_exists:
            reason = (f"best structured val acc {best_val_acc:.3f} < "
                      f"baseline val {baseline_val_acc:.3f} - margin "
                      f"{cfg.accept_margin:.2f}")
        else:
            reason = ("baseline at/above skip_above_acc; optimization skipped"
                      if skip_high else "no structured round was produced")
        logger.info("reflect: REVERT to baseline seed (%s)", reason)
        registry.run_best_versions = {name: 0 for name in registry.schema}
        registry.restore_best_snapshot()
        best_wrong, best_correct, best_result = (
            baseline_wrong, baseline_correct, baseline)

    save_markdown_prompt(registry.active_prompt(), run_dir / "prompt_current.md",
                         schema=registry.schema)

    # 4. Confusion matrix on the mining batch (baseline vs. best across rounds).
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
        "val_split": {
            "enabled": has_val_split,
            "val_frac": val_frac,
            "n_mining": len(mining),
            "n_validation": len(validation) if has_val_split else 0,
        },
        "baseline_val_acc": baseline_val_acc,
        "best_structured_val_acc": best_val_acc if structured_exists else None,
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
                            if r["status"].startswith("committed")]),
        "train_acc_per_round": [
            r.get("train_acc_after", best_result.accuracy) for r in rounds_log
        ] if rounds_log else [best_result.accuracy],
        "time_to_stabilization": None,
        "judge_parse_failures": 0,
    }
