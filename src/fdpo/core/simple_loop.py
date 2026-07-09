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

    best_prompt = seed
    best_wrong  = failures on seed
    current     = seed
    for r in 1..cfg.simple_max_rounds:
        F = failures on current
        if |F| < tau:  break                           # converged
        p_new  = LLMOptimize(current, F, gold)
        F_new  = failures on p_new
        commit p_new (unconditionally — active becomes p_new for next round)
        if |F_new| < |best_wrong|:                     # trajectory-best update
            best_prompt = p_new; best_wrong = F_new
        current = p_new                                # NEXT round starts here
    activate best_prompt                                # revert if last != best

Rationale: gating strictly on "must reduce train failures" stops the loop
after one bad round. Under the "N rounds, keep-best" design, a bad round
does not stop the loop — rounds 2/3 get another chance from that round's
output. The final active prompt is whichever version had the fewest train
failures across the trajectory. This matches OPRO/APE-style iteration and
is what the user asked for when they said "run the loop 2/3 times".

The keep-best selection gates ONLY on train failure count, never on test.
Test evaluation is done by the caller (`run_experiment.run`) before and
after this function.

No judge, no per-section attribution, no rho, no history window.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from fdpo.clients.base import ModelClient
from fdpo.config import ExperimentConfig
from fdpo.core.registry import GateResult, PromptRegistry
from fdpo.data.loaders import Example
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

    # 1. Baseline eval on the whole train batch (this is the paper's `B`).
    logger.info("simple: baseline eval on %d train examples", len(train))
    baseline = evaluate(solver, registry.active_prompt(), train, dataset,
                        temperature=cfg.solver_temperature,
                        max_tokens=cfg.solver_max_tokens, purpose="simple:baseline",
                        max_workers=cfg.max_workers)
    baseline_correct = {r.example_id for r in baseline.rows if r.correct}
    baseline_wrong = {r.example_id for r in baseline.rows if not r.correct}
    logger.info("simple: baseline train accuracy %.3f (%d correct, %d wrong)",
                baseline.accuracy, len(baseline_correct), len(baseline_wrong))

    # Save baseline markdown to the run directory (audit trail).
    save_markdown_prompt(registry.active_prompt(), run_dir / "prompt_baseline.md",
                         schema=registry.schema)

    # Establish the baseline as the initial best-snapshot in the registry so
    # a later restore_best_snapshot() reverts cleanly to this seed prompt if
    # every round regresses.
    registry.record_round(passed=True, acc=baseline.accuracy)

    # 2. Cache the baseline output text per-example so we can show the
    #    optimizer the model's *specific* wrong answer even in later rounds.
    baseline_outputs = {r.example_id: r.output for r in baseline.rows}

    # 3. Multi-round loop with best-snapshot rescue.
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

        # Evaluate the candidate on the whole train batch.
        candidate_prompt = registry.prompt_with_edits(changed)
        logger.info("simple: round %d — re-evaluating train batch with new prompt "
                    "(%d sections changed)", round_num, len(changed))
        new_eval = evaluate(solver, candidate_prompt, train, dataset,
                            temperature=cfg.solver_temperature,
                            max_tokens=cfg.solver_max_tokens,
                            purpose=f"simple:round{round_num}",
                            max_workers=cfg.max_workers)
        new_wrong = {r.example_id for r in new_eval.rows if not r.correct}
        new_correct = {r.example_id for r in new_eval.rows if r.correct}

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

        # Trajectory-best update: if this round's train failure count is
        # strictly better than any past round's best, update the best snapshot
        # (registry tracks this via record_round(passed=True, ...)).
        improved_best = len(new_wrong) < len(best_wrong)
        if improved_best:
            registry.record_round(passed=True, acc=new_eval.accuracy)
            best_wrong = new_wrong
            best_correct = new_correct
            best_result = new_eval
            best_committed = True
            final_edit_status = "committed"
        else:
            # Committed to the trajectory but did not improve on the
            # trajectory-best. Do NOT call record_round — that would move the
            # best snapshot to this (worse-or-equal) round.
            if final_edit_status == "not_triggered":
                # First round produced a change but didn't beat baseline —
                # still counts as an attempt; caller can see the trajectory.
                final_edit_status = "committed"

        rounds_log.append({
            "round": round_num,
            "status": "committed" if improved_best else "committed_no_best_update",
            "n_failures_before": len(failures),
            "n_failures_after": len(new_wrong),
            "train_acc_after": new_eval.accuracy,
            "sections_changed": sorted(changed.keys()),
        })
        logger.info(
            "simple: round %d COMMITTED — |F| %d -> %d, train acc %.3f -> %.3f%s",
            round_num, len(failures), len(new_wrong),
            gate.acc_old, new_eval.accuracy,
            " (new best)" if improved_best else " (not best, continuing)",
        )

        # ALWAYS continue — the next round starts from this round's output.
        current_wrong = new_wrong
        current_correct = new_correct

    # After the loop: if the trajectory's final active prompt is not the
    # trajectory-best, revert to the best snapshot. On single-round mode
    # this is a no-op (best == active).
    active_matches_best = all(
        registry.sections[name].active_version == best_v
        for name, best_v in registry.run_best_versions.items()
    )
    if not active_matches_best:
        logger.info("simple: reverting active prompt to trajectory-best snapshot")
        registry.restore_best_snapshot()

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
        "simple: TRAIN confusion matrix -- recovered %d, regressed %d, "
        "still wrong %d, still right %d, net_gain %+d",
        len(recoveries), len(regressions), len(still_wrong), still_right, net_gain,
    )
    logger.info("simple: TRAIN accuracy %.3f -> %.3f (delta %+.3f)",
                baseline.accuracy, best_result.accuracy,
                best_result.accuracy - baseline.accuracy)

    return {
        "mode": "simple",
        "edit_status": final_edit_status,
        "triggered": triggered,
        "tau": cfg.tau,
        "simple_max_rounds": max_rounds,
        "n_failures_triggering": len(baseline_wrong),
        "optimizer_calls": optimizer_calls,
        "rounds_log": rounds_log,
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
        "rounds_run": len([r for r in rounds_log if r["status"] == "committed"]),
        "train_acc_per_round": [
            r.get("train_acc_after", best_result.accuracy) for r in rounds_log
        ] if rounds_log else [best_result.accuracy],
        "time_to_stabilization": None,
        "judge_parse_failures": 0,
    }


def bootstrap_registry_from_markdown(dataset: str, run_dir: Path,
                                      registry: PromptRegistry) -> str:
    """Replace the registry's seed sections with what's loaded from
    `prompts/<dataset>.md` (or fallback). Returns the source path or 'seed'.

    Called from `run_experiment.run` for `--method simple_fdpo` BEFORE the
    seed_test eval, so the baseline uses the markdown-file prompt.
    """
    sections, _, md_source = load_markdown_prompt(dataset, schema=registry.schema)
    # Swap the version-0 text in place -- registry was init'd from Python seeds
    # and no rounds have run yet, so this is safe.
    for name in registry.schema:
        if name in sections:
            registry.sections[name].versions[0].text = sections[name]
    registry._save()
    return str(md_source) if md_source else "seed-fallback"
