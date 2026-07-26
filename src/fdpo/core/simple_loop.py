"""Paper-faithful single-pass FDPO (`--method simple_fdpo`).

This is the algorithm from the original figure, ported to the benchmark setting
with three additions:
  1. A per-example confusion-matrix breakdown of what optimization changed.
  2. Optional multi-round with best-snapshot rescue (opt in via
     `cfg.simple_max_rounds > 1`). Default is 1 (paper-faithful single pass).
  3. Dataset-specific task description injected into the optimizer's system
     prompt (see `simple_optimizer_prompt._TASK_DESCRIPTIONS`).

Single-round pseudocode (cfg.simple_max_rounds == 1, backward compatible):

    if |F| >= tau:
        E_fail  <- sample failures
        E_gold  <- sample correctly-solved cases
        p_new   <- LLMOptimize(p_old, E_fail, E_gold)   # ONE call, whole markdown
        activate p_new
    return

Multi-round pseudocode (cfg.simple_max_rounds > 1, "N rounds, keep-best"):

    M, V = stratified_split(train, 1 - val_frac)        # mining / validation
    baseline_val = acc(seed, V)
    best_val     = -1
    current      = seed
    for r in 1..cfg.simple_max_rounds:
        F = failures of current on M
        if |F| < tau:  break                            # converged
        p_new    = LLMOptimize(current, F, gold_from_M)
        v_new    = acc(p_new, V)                         # held-out score
        commit p_new (unconditionally -- active becomes p_new for next round)
        if v_new > best_val:                            # keep-best on VALIDATION
            best_prompt = p_new; best_val = v_new
        current = p_new                                 # NEXT round starts here
    # LENIENT accept gate:
    if best_val >= baseline_val - accept_margin:        # default margin ships it
        activate best_prompt                            # structured prompt -> test
    else:
        activate seed                                   # revert (rare, strict only)

Rationale: gating strictly on "must reduce train failures" stops the loop
after one bad round AND overfits the accept decision to the exact examples
the optimizer saw. Under "N rounds, keep-best" a bad round does not stop the
loop, and candidates are now scored on a HELD-OUT validation slice V so the
kept prompt is chosen on data the optimizer did not optimize against. The
final accept is LENIENT (see --accept-margin): by default the best-validation
structured prompt is shipped so its true test behavior is observed, rather
than silently reverting to the bare seed. This matches OPRO/APE-style
iteration with a standard train/val/test split.

The keep-best selection gates on held-out VALIDATION accuracy, never on test.
Test evaluation is done by the caller (`run_experiment.run`) before and
after this function; the test set is never touched here.

No judge, no per-section attribution, no rho, no history window.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from fdpo.clients.base import ModelClient
from fdpo.config import ExperimentConfig
from fdpo.core.registry import GateResult, PromptRegistry
from fdpo.data.loaders import Example, _stratified_take
from fdpo.data.md_prompt import (load_markdown_prompt, parse_markdown,
                                  save_markdown_prompt, to_markdown)
from fdpo.eval.evaluator import evaluate
from fdpo.prompts.simple_optimizer_prompt import build_simple_optimizer_messages

logger = logging.getLogger("fdpo")


def run_simple_optimization(cfg: ExperimentConfig, registry: PromptRegistry,
                            train: list[Example], dataset: str,
                            solver: ModelClient, optimizer: ModelClient,
                            run_dir: Path) -> dict:
    """Single-pass or multi-round paper-faithful FDPO with best-snapshot
    rescue. See module docstring for the algorithm.

    Returns a summary dict with per-round history, train confusion matrix,
    and optimization outcome. Test evaluation is done by the caller.
    """
    rng = random.Random(cfg.seed)
    train_by_id = {ex.id: ex for ex in train}
    max_rounds = max(1, int(cfg.simple_max_rounds))

    # 0. Split the train pool into a MINING set (where the optimizer sees
    #    failures) and a held-out VALIDATION set (where candidate prompts are
    #    scored and the accept gate decides). This keeps the accept decision
    #    off the exact examples the optimizer optimized against. The sealed
    #    TEST set (evaluated by the caller) is never touched here. Stratified
    #    so both sets keep the dataset's label/slice balance.
    val_frac = float(cfg.simple_val_frac)
    if 0.0 < val_frac < 1.0 and len(train) >= 4:
        n_mining = max(1, round(len(train) * (1.0 - val_frac)))
        n_mining = min(n_mining, len(train) - 1)   # guarantee >= 1 validation
        mining, validation = _stratified_take(train, n_mining, rng)
        has_val_split = True
        logger.info("simple: train split -> mining=%d, validation=%d "
                    "(val_frac=%.2f, stratified)", len(mining), len(validation),
                    val_frac)
    else:
        mining = list(train)
        validation = list(train)
        has_val_split = False
        logger.warning("simple: validation split disabled (val_frac=%.2f, "
                       "n_train=%d) -- scoring candidates in-sample on the "
                       "mining set", val_frac, len(train))

    # 1. Baseline eval on the MINING set (this is the paper's `B`; the source
    #    of the failures the optimizer rewrites against).
    logger.info("simple: baseline eval on %d mining examples", len(mining))
    baseline = evaluate(solver, registry.active_prompt(), mining, dataset,
                        temperature=cfg.solver_temperature,
                        max_tokens=cfg.solver_max_tokens, purpose="simple:baseline",
                        max_workers=cfg.max_workers)
    baseline_correct = {r.example_id for r in baseline.rows if r.correct}
    baseline_wrong = {r.example_id for r in baseline.rows if not r.correct}
    logger.info("simple: baseline mining accuracy %.3f (%d correct, %d wrong)",
                baseline.accuracy, len(baseline_correct), len(baseline_wrong))

    # Baseline eval on the held-out VALIDATION set -- the reference the accept
    # gate compares candidate prompts against.
    if has_val_split:
        baseline_val = evaluate(solver, registry.active_prompt(), validation, dataset,
                                temperature=cfg.solver_temperature,
                                max_tokens=cfg.solver_max_tokens,
                                purpose="simple:baseline-val",
                                max_workers=cfg.max_workers)
        baseline_val_acc = baseline_val.accuracy
    else:
        baseline_val_acc = baseline.accuracy
    logger.info("simple: baseline validation accuracy %.3f", baseline_val_acc)

    # Save baseline markdown to the run directory (audit trail).
    save_markdown_prompt(registry.active_prompt(), run_dir / "prompt_baseline.md",
                         schema=registry.schema)

    # Seed the registry best-snapshot with the baseline (version 0) so a later
    # restore_best_snapshot() always has a valid target. This does NOT force
    # the baseline to win: the lenient accept gate (after the loop) prefers a
    # structured round and only reverts to version 0 when no acceptable
    # structured prompt was produced.
    registry.record_round(passed=True, acc=baseline.accuracy)

    # 2. Cache the baseline output text per-example so we can show the
    #    optimizer the model's *specific* wrong answer even in later rounds.
    baseline_outputs = {r.example_id: r.output for r in baseline.rows}

    # 3. Multi-round loop with a LENIENT, VALIDATION-gated accept.
    #    best_val_acc tracks the highest held-out VALIDATION accuracy achieved
    #    by any STRUCTURED round so far (-1.0 => no structured round yet).
    #    Whenever a round beats it we record that round as the registry
    #    best-snapshot; the final ship/revert decision compares it against the
    #    baseline validation accuracy using cfg.accept_margin.
    best_val_acc = -1.0
    best_wrong = baseline_wrong
    best_correct = baseline_correct
    best_result = baseline
    current_wrong = baseline_wrong
    current_correct = baseline_correct
    optimizer_calls = 0
    rounds_log: list[dict] = []
    triggered = False
    final_edit_status = "not_triggered"

    for round_num in range(1, max_rounds + 1):
        # Failure evidence for THIS round: for each currently-wrong example
        # we show the *baseline* model output (proxy — accepting some
        # staleness in later rounds rather than caching per-round outputs).
        failures = [
            {
                "question": train_by_id[eid].question,
                "output": baseline_outputs.get(eid, "(wrong)"),
                "gold": train_by_id[eid].reference,
                "example_id": eid,
            }
            for eid in current_wrong
        ]
        if len(failures) < cfg.tau:
            logger.info("simple: round %d skipped — |F|=%d < tau=%d (converged)",
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
        logger.info("simple: round %d — |F|=%d, sampled %d failures + %d golds",
                    round_num, len(failures), len(e_fail), len(e_gold))

        current_md = to_markdown(registry.active_prompt(), schema=registry.schema)
        messages = build_simple_optimizer_messages(current_md, e_fail, e_gold,
                                                    dataset=dataset)
        result = optimizer.complete(messages, temperature=cfg.optimizer_temperature,
                                    max_tokens=2000,
                                    purpose=f"simple:rewrite-r{round_num}")
        optimizer_calls += 1

        # Parse the returned markdown. On parse failure or no-change, skip
        # THIS round but continue the loop — a fresh optimizer call in the
        # next round may succeed (rng advanced, temp>0 gives variety).
        try:
            new_sections = parse_markdown(result.text)
        except ValueError as e:
            logger.warning("simple: round %d parse failed (%s); continuing to next round",
                           round_num, e)
            rounds_log.append({
                "round": round_num,
                "status": "parse_failed",
                "n_failures_before": len(failures),
            })
            continue

        # Backfill missing sections from current active prompt.
        missing = set(registry.schema) - set(new_sections)
        if missing:
            logger.warning("simple: round %d optimizer omitted sections %s; backfilling",
                           round_num, sorted(missing))
            for k in missing:
                new_sections[k] = registry.active_prompt()[k]

        changed = {name: new_sections[name] for name in registry.schema
                   if new_sections.get(name, "") != registry.active_prompt()[name]}
        if not changed:
            logger.info("simple: round %d — optimizer proposed no changes; continuing",
                        round_num)
            rounds_log.append({
                "round": round_num,
                "status": "no_change",
                "n_failures_before": len(failures),
            })
            continue

        # Evaluate the candidate: on the MINING set (drives the NEXT round's
        # failures + the working-set confusion matrix) and on the held-out
        # VALIDATION set (drives the accept gate). mining + validation sums to
        # the original train size, so this costs no more than the old
        # whole-train re-eval.
        candidate_prompt = registry.prompt_with_edits(changed)
        logger.info("simple: round %d -- re-evaluating mining+validation with new "
                    "prompt (%d sections changed)", round_num, len(changed))
        new_eval = evaluate(solver, candidate_prompt, mining, dataset,
                            temperature=cfg.solver_temperature,
                            max_tokens=cfg.solver_max_tokens,
                            purpose=f"simple:round{round_num}",
                            max_workers=cfg.max_workers)
        new_wrong = {r.example_id for r in new_eval.rows if not r.correct}
        new_correct = {r.example_id for r in new_eval.rows if r.correct}
        if has_val_split:
            val_eval = evaluate(solver, candidate_prompt, validation, dataset,
                                temperature=cfg.solver_temperature,
                                max_tokens=cfg.solver_max_tokens,
                                purpose=f"simple:round{round_num}-val",
                                max_workers=cfg.max_workers)
            cand_val_acc = val_eval.accuracy
        else:
            cand_val_acc = new_eval.accuracy

        gate = GateResult(
            acc_old=1.0 - len(current_wrong) / max(len(current_wrong) + len(current_correct), 1),
            acc_new=new_eval.accuracy,
            rho=0.0,
            passed=True,
            batch_size=len(train),
            n_failures=len(failures),
            recovered_failures=len(current_wrong - new_wrong),
            broke=len(current_correct - new_correct),
        )
        # Always commit — this becomes the starting point for the NEXT round.
        registry.commit_bundle(changed, round_num=round_num, gate=gate)

        # LENIENT, VALIDATION-gated best-tracking: prefer the STRUCTURED round
        # with the highest held-out VALIDATION accuracy. A structured round is
        # recorded as the best snapshot even when it is below baseline -- so the
        # optimizer's enriched prompt is shipped and seen on the test set
        # instead of reverting to the bare seed. The baseline-vs-structured
        # decision (with --accept-margin) happens once, after the loop.
        is_new_best = cand_val_acc > best_val_acc
        if is_new_best:
            registry.record_round(passed=True, acc=cand_val_acc)
            best_val_acc = cand_val_acc
            best_wrong = new_wrong
            best_correct = new_correct
            best_result = new_eval
            final_edit_status = "committed"
        elif final_edit_status == "not_triggered":
            # First round produced a change but wasn't the best -- still an
            # attempt; the caller can see the full trajectory.
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
            "recovered_this_round": sorted(current_wrong - new_wrong),
            "regressed_this_round": sorted(new_wrong - current_wrong),
        })
        logger.info(
            "simple: round %d COMMITTED -- |F| %d -> %d, mining acc %.3f -> %.3f, "
            "val acc %.3f -> %.3f%s",
            round_num, len(failures), len(new_wrong),
            gate.acc_old, new_eval.accuracy, baseline_val_acc, cand_val_acc,
            " (new best)" if is_new_best else " (not best, continuing)",
        )

        # ALWAYS continue — the next round starts from this round's output.
        current_wrong = new_wrong
        current_correct = new_correct

    # LENIENT accept gate (once, after the loop):
    #   * If at least one structured round exists AND its train accuracy is
    #     within --accept-margin of baseline, SHIP that structured prompt
    #     (run_best_versions already points at it). With the default margin
    #     (1.0) this always ships the optimizer's best structured prompt, so we
    #     observe its true test-set performance instead of reverting to a bare
    #     seed with empty sections.
    #   * Otherwise revert to the baseline seed (version 0).
    structured_exists = best_val_acc >= 0.0
    ship_structured = structured_exists and (
        best_val_acc >= baseline_val_acc - cfg.accept_margin
    )
    if ship_structured:
        logger.info(
            "simple: ACCEPT structured prompt (best val acc %.3f, baseline val "
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
            reason = "no structured round was produced"
        logger.info("simple: REVERT to baseline seed (%s)", reason)
        registry.run_best_versions = {name: 0 for name in registry.schema}
        registry.restore_best_snapshot()
        best_wrong, best_correct, best_result = (
            baseline_wrong, baseline_correct, baseline)

    # Save the final active markdown snapshot to run_dir.
    save_markdown_prompt(registry.active_prompt(), run_dir / "prompt_current.md",
                         schema=registry.schema)

    # 4. Confusion matrix on the train batch (baseline vs. best across rounds).
    recoveries = sorted(baseline_wrong & best_correct)
    regressions = sorted(baseline_correct & best_wrong)
    still_wrong = sorted(baseline_wrong & best_wrong)
    still_right = len(baseline_correct & best_correct)
    net_gain = len(recoveries) - len(regressions)

    logger.info(
        "simple: MINING confusion matrix -- recovered %d, regressed %d, "
        "still wrong %d, still right %d, net_gain %+d",
        len(recoveries), len(regressions), len(still_wrong), still_right, net_gain,
    )
    logger.info("simple: MINING accuracy %.3f -> %.3f (delta %+.3f)",
                baseline.accuracy, best_result.accuracy,
                best_result.accuracy - baseline.accuracy)

    return {
        "mode": "simple",
        "edit_status": final_edit_status,
        "triggered": triggered,
        "tau": cfg.tau,
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
        # Fields below are for compatibility with the run_experiment metrics
        # pipeline (which was built for the multi-round `fdpo` method).
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


def bootstrap_registry_from_markdown(dataset: str, run_dir: Path,
                                     registry: PromptRegistry,
                                     prompt_file: str | None = None) -> str:
    """Replace the registry's seed sections with what's loaded from
    `prompts/<dataset>.md` (or `prompt_file` if given, or the Python seed
    fallback). Returns the source path or 'seed'.

    Called from `run_experiment.run` for `--method simple_fdpo` BEFORE the
    seed_test eval, so the baseline uses the markdown-file prompt.
    """
    sections, _, md_source = load_markdown_prompt(
        dataset, schema=registry.schema, override_path=prompt_file)
    # When an override prompt is used, warn about any schema section it omits:
    # those would silently keep the (good) Python-seed text and contaminate a
    # deliberately-vague-prompt experiment.
    if prompt_file:
        missing = [s for s in registry.schema if s not in sections]
        if missing:
            logger.warning("--prompt-file %s omits sections %s; they keep the "
                           "default seed text (possible experiment contamination)",
                           prompt_file, missing)
    # Swap the version-0 text in place -- registry was init'd from Python seeds
    # and no rounds have run yet, so this is safe.
    for name in registry.schema:
        if name in sections:
            registry.sections[name].versions[0].text = sections[name]
    registry._save()
    return str(md_source) if md_source else "seed-fallback"
