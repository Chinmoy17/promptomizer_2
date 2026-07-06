"""Paper-faithful single-pass FDPO (`--method simple_fdpo`).

This is the algorithm from the original figure, ported to the benchmark setting
with one addition: a per-example confusion-matrix breakdown of what the
optimization actually changed on the training batch.

    if |F| >= tau:
        E_fail  <- sample failures
        E_gold  <- sample correctly-solved cases
        p_new   <- LLMOptimize(p_old, E_fail, E_gold)   # ONE call, whole markdown
        activate p_new
    return

No rounds. No regression gate (accepts every rewrite). No val slice. No judge.
No per-section attribution. No history window. No bundle find/replace.

The confusion-matrix reporting is the non-paper part: we track which train
examples were RECOVERED (was wrong -> now right) vs REGRESSED (was right ->
now wrong), which is the honest signal for a real-world before/after comparison.
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
    """Single-pass paper-faithful FDPO. See module docstring for the algorithm.

    Returns a summary dict with the train-batch confusion matrix and
    optimization outcome. Test evaluation is done by the caller
    (`run_experiment.run`) before and after this function.
    """
    rng = random.Random(cfg.seed)
    train_by_id = {ex.id: ex for ex in train}

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

    # 2. Prepare the failure and gold pools for the optimizer.
    failures = [
        {
            "question": train_by_id[r.example_id].question,
            "output": r.output,
            "gold": r.gold,
            "example_id": r.example_id,
        }
        for r in baseline.rows if not r.correct
    ]
    corrects = [train_by_id[r.example_id] for r in baseline.rows if r.correct]

    triggered = len(failures) >= cfg.tau
    optimizer_calls = 0
    edit_status = "not_triggered"

    if not triggered:
        logger.info("simple: |F|=%d < tau=%d -- optimization NOT triggered",
                    len(failures), cfg.tau)
        current = baseline
    else:
        # 3. Sample E_fail and E_gold.
        e_fail = rng.sample(failures, min(cfg.n_fail, len(failures)))
        e_gold = rng.sample(corrects, min(cfg.n_gold, len(corrects))) if corrects else []
        logger.info("simple: triggered (|F|=%d >= tau=%d), sampled %d failures + %d golds",
                    len(failures), cfg.tau, len(e_fail), len(e_gold))

        # 4. One LLM call: rewrites the whole markdown from scratch.
        current_md = to_markdown(registry.active_prompt(), schema=registry.schema)
        messages = build_simple_optimizer_messages(current_md, e_fail, e_gold)
        result = optimizer.complete(messages, temperature=cfg.optimizer_temperature,
                                     max_tokens=2000, purpose="simple:rewrite")
        optimizer_calls = 1

        # 5. Parse the returned markdown. Any parse failure -> keep old prompt.
        new_sections = None
        try:
            new_sections = parse_markdown(result.text)
            missing = set(registry.schema) - set(new_sections)
            if missing:
                # LLM dropped some sections -- backfill from current; note it.
                logger.warning("simple: optimizer omitted sections %s; backfilling",
                               sorted(missing))
                for k in missing:
                    new_sections[k] = registry.active_prompt()[k]
                edit_status = "partial_parse"
            else:
                edit_status = "committed"
        except ValueError as e:
            logger.warning("simple: optimizer markdown parse failed (%s); keeping old prompt", e)
            edit_status = "parse_failed"
            new_sections = None

        # 6. Activate new sections (only sections that actually changed).
        if new_sections is not None:
            changed = {name: new_sections[name] for name in registry.schema
                       if new_sections.get(name, "") != registry.active_prompt()[name]}
            if not changed:
                logger.info("simple: optimizer proposed no changes (p_new == p_old)")
                edit_status = "no_change"
                current = baseline
            else:
                # 7. Re-eval on train to compute confusion matrix + build a
                # semantically-honest GateResult (this is the paper's
                # `CompareBaselineVsCurrent` + `EvaluateAccuracyGain`).
                candidate_prompt = registry.prompt_with_edits(changed)
                logger.info("simple: re-evaluating train batch with new prompt (%d sections changed)",
                            len(changed))
                current = evaluate(solver, candidate_prompt, train, dataset,
                                    temperature=cfg.solver_temperature,
                                    max_tokens=cfg.solver_max_tokens,
                                    purpose="simple:current",
                                    max_workers=cfg.max_workers)
                current_correct = {r.example_id for r in current.rows if r.correct}
                current_wrong = {r.example_id for r in current.rows if not r.correct}
                gate = GateResult(
                    acc_old=baseline.accuracy,
                    acc_new=current.accuracy,
                    rho=0.0,             # simple mode does not gate
                    passed=True,          # simple mode always activates
                    batch_size=len(train),
                    n_failures=len(failures),
                    recovered_failures=len(baseline_wrong & current_correct),
                    broke=len(baseline_correct & current_wrong),
                )
                registry.commit_bundle(changed, round_num=1, gate=gate)
                registry.record_round(passed=True, acc=current.accuracy)
        else:
            current = baseline

    # Save current markdown snapshot to run_dir.
    save_markdown_prompt(registry.active_prompt(), run_dir / "prompt_current.md",
                         schema=registry.schema)

    # 8. Confusion matrix on the train batch (independent of whether we
    # actually optimized -- degenerate case is baseline vs itself).
    current_correct = {r.example_id for r in current.rows if r.correct}
    current_wrong = {r.example_id for r in current.rows if not r.correct}
    recoveries = sorted(baseline_wrong & current_correct)
    regressions = sorted(baseline_correct & current_wrong)
    still_wrong = sorted(baseline_wrong & current_wrong)
    still_right = len(baseline_correct & current_correct)
    net_gain = len(recoveries) - len(regressions)

    logger.info(
        "simple: TRAIN confusion matrix -- recovered %d, regressed %d, "
        "still wrong %d, still right %d, net_gain %+d",
        len(recoveries), len(regressions), len(still_wrong), still_right, net_gain,
    )
    logger.info("simple: TRAIN accuracy %.3f -> %.3f (delta %+.3f)",
                baseline.accuracy, current.accuracy, current.accuracy - baseline.accuracy)

    return {
        "mode": "simple",
        "edit_status": edit_status,
        "triggered": triggered,
        "tau": cfg.tau,
        "n_failures_triggering": len(failures),
        "optimizer_calls": optimizer_calls,
        "baseline_train": {
            "accuracy": baseline.accuracy,
            "n_correct": len(baseline_correct),
            "n_wrong": len(baseline_wrong),
        },
        "current_train": {
            "accuracy": current.accuracy,
            "n_correct": len(current_correct),
            "n_wrong": len(current_wrong),
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
        "rounds_run": 1 if triggered else 0,
        "train_acc_per_round": [current.accuracy] if triggered else [baseline.accuracy],
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
