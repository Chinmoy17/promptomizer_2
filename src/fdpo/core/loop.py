"""The FDPO offline batch optimization loop (v2 -- see Docs/fdpo_mechanism.md).

Per round: evaluate the active prompt on the train-for-failures pool; failures
are judge-attributed to sections (unchanged mechanism); every implicated
section's evidence is aggregated programmatically and handed, together with
the full current/best prompt and this run's history, to ONE optimizer call
that proposes find/replace edits across all implicated sections at once.
The resulting whole prompt is gated as a single candidate against a FIXED
held-out validation slice (carved once, never resampled) and committed or
rejected atomically -- no per-section bisection (Option A).

Monolithic-FDPO (ablation A1) is this same loop over a 1-section schema.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

from fdpo.clients.base import ModelClient
from fdpo.config import ExperimentConfig
from fdpo.core.gate import CorrectPool, evaluate_candidate
from fdpo.core.judge import judge_failure
from fdpo.core.optimizer import aggregate_failures, rewrite_prompt_bundle
from fdpo.core.registry import PromptRegistry
from fdpo.data.loaders import Example
from fdpo.eval.evaluator import evaluate
from fdpo.utils.io import CsvAppender, JsonlAppender

logger = logging.getLogger("fdpo")

TRAIN_LOG_FIELDS = ["round", "example_id", "correct", "pred", "gold", "section"]
ROUNDS_LOG_FIELDS = ["round", "sections", "n_failures", "acc_old", "acc_new",
                     "passed", "broke", "recovered", "batch_size"]


def run_optimization(cfg: ExperimentConfig, registry: PromptRegistry,
                     train: list[Example], dataset: str,
                     solver: ModelClient, judge: ModelClient,
                     optimizer: ModelClient, run_dir: Path) -> dict:
    """Returns a summary dict; per-bundle records also land in rounds_log.csv."""
    rng = random.Random(cfg.seed)

    # Carve the FIXED validation slice ONCE -- never resampled again this run.
    # It is disjoint from the pool used to find failures / sample golds, and
    # is separate from (never overlaps with) the true held-out test set.
    shuffled = train.copy()
    rng.shuffle(shuffled)
    val_size = min(cfg.val_size, max(0, len(shuffled) - 1))
    val_slice = shuffled[:val_size]
    train_pool = shuffled[val_size:]
    train_by_id = {ex.id: ex for ex in train_pool}

    pool = CorrectPool(cap=cfg.pool_cap)  # gold-example sampling only (v2)
    train_log = CsvAppender(run_dir / "train_log.csv", TRAIN_LOG_FIELDS)
    rounds_log = CsvAppender(run_dir / "rounds_log.csv", ROUNDS_LOG_FIELDS)
    events = JsonlAppender(run_dir / "events.jsonl")

    bundles: list[dict] = []
    round_accs: list[float] = []
    history: list[dict] = []
    stabilized_at: int | None = None
    judge_parse_failures = 0
    current_val_acc: float | None = None

    for round_num in range(1, cfg.max_rounds + 1):
        # 1. evaluate active prompt on the train-for-failures pool
        active = registry.active_prompt()
        result = evaluate(solver, active, train_pool, dataset,
                          temperature=cfg.solver_temperature,
                          max_tokens=cfg.solver_max_tokens, purpose="train",
                          max_workers=cfg.max_workers)
        round_accs.append(result.accuracy)
        logger.info("round %d: train accuracy %.3f", round_num, result.accuracy)

        # 2. verdicts -> gold pool / judge attribution (unchanged mechanism)
        failures_by_section: dict[str, list[dict]] = {s: [] for s in registry.schema}
        for row in result.rows:
            ex = train_by_id[row.example_id]
            section_label = ""
            if row.correct:
                pool.add(ex)
            else:
                jr = judge_failure(judge, active, ex.question, row.output,
                                   ex.reference, registry.schema)
                judge_parse_failures += jr.parse_failed
                targets: list[str] = []
                if jr.section == "multiple":
                    targets = jr.sections or list(registry.schema)
                elif jr.section != "none":
                    targets = [jr.section]
                section_label = "+".join(targets) if targets else "none"
                for t in targets:
                    failures_by_section[t].append({
                        "question": ex.question, "output": row.output,
                        "critique": jr.critique, "error_type": jr.error_type,
                        "example": ex,
                    })
            train_log.append({"round": round_num, "example_id": row.example_id,
                              "correct": row.correct, "pred": row.pred,
                              "gold": row.gold, "section": section_label})

        implicated_names = [s for s in registry.schema if failures_by_section[s]]

        if implicated_names:
            # 3. programmatic aggregation + ONE optimizer call for the whole bundle
            implicated = {
                name: {"failures": failures_by_section[name][: cfg.n_fail],
                      "aggregate": aggregate_failures(failures_by_section[name])}
                for name in implicated_names
            }
            correct_pool_sample = pool.sample(cfg.n_gold, rng)
            golds = correct_pool_sample if correct_pool_sample else train_pool[: cfg.n_gold]

            if current_val_acc is None:
                current_val_acc = evaluate(
                    solver, active, val_slice, dataset,
                    temperature=cfg.solver_temperature,
                    max_tokens=cfg.solver_max_tokens, purpose="val",
                    max_workers=cfg.max_workers).accuracy

            best_acc = registry.run_best_acc if registry.run_best_acc >= 0 else current_val_acc

            edit_result = rewrite_prompt_bundle(
                optimizer, implicated, active, current_val_acc,
                registry.best_prompt(), best_acc, golds,
                history[-cfg.history_window:], registry.schema,
                temperature=cfg.optimizer_temperature)

            # Log every proposed edit's fate (applied / skipped-with-reason /
            # parse-failed). Fires even for no-edit rounds so we can inspect
            # what the optimizer tried but the find-string never matched.
            events.append({"event": "edits", "round": round_num,
                           "parse_failed": edit_result.parse_failed,
                           "edits": edit_result.edit_log})

            all_failures_flat = [f["example"] for name in implicated_names
                                 for f in implicated[name]["failures"]]

            if not edit_result.edits_applied:
                logger.info("round %d: no edits applied (parse_failed=%s)",
                           round_num, edit_result.parse_failed)
                registry.record_round(passed=False, acc=current_val_acc)
            else:
                candidate_prompt = registry.prompt_with_edits(edit_result.edits_applied)
                gate = evaluate_candidate(
                    solver, dataset, active, candidate_prompt,
                    val_slice, all_failures_flat,
                    rho=cfg.rho, solver_temperature=cfg.solver_temperature,
                    solver_max_tokens=cfg.solver_max_tokens,
                    max_workers=cfg.max_workers)

                if gate.passed:
                    registry.commit_bundle(edit_result.edits_applied, round_num, gate)
                    current_val_acc = gate.acc_new
                else:
                    registry.reject_bundle(edit_result.edits_applied, round_num, gate)
                registry.record_round(passed=gate.passed,
                                      acc=gate.acc_new if gate.passed else gate.acc_old)

                if registry.run_stagnant_rounds >= cfg.stagnation_limit:
                    logger.info("stagnant %d rounds -> restoring best snapshot",
                               registry.run_stagnant_rounds)
                    registry.restore_best_snapshot()
                    current_val_acc = registry.run_best_acc

                sections_str = "+".join(edit_result.edits_applied)
                record = {"round": round_num, "sections": sections_str,
                          "n_failures": len(all_failures_flat),
                          "acc_old": gate.acc_old, "acc_new": gate.acc_new,
                          "passed": gate.passed, "broke": gate.broke,
                          "recovered": gate.recovered_failures,
                          "batch_size": gate.batch_size}
                rounds_log.append(record)
                events.append({"event": "bundle", **record})
                bundles.append({"committed": gate.passed, "broke": gate.broke,
                                "batch_size": gate.batch_size,
                                "n_failures": gate.n_failures,
                                "recovered_failures": gate.recovered_failures})
                history.append({"round": round_num, "sections": sections_str,
                                "passed": gate.passed,
                                "acc_old": gate.acc_old, "acc_new": gate.acc_new})
                logger.info("round %d [%s]: %s (old %.3f -> new %.3f, broke %d, recovered %d/%d)",
                           round_num, sections_str,
                           "COMMIT" if gate.passed else "REJECT",
                           gate.acc_old, gate.acc_new,
                           gate.broke, gate.recovered_failures, gate.n_failures)

        # 4. stabilization check on train accuracy (unchanged)
        if stabilized_at is None and len(round_accs) >= 4:
            recent = round_accs[-4:]
            deltas = [abs(recent[i + 1] - recent[i]) for i in range(3)]
            if all(d < cfg.eps for d in deltas):
                stabilized_at = round_num
                logger.info("stabilized at round %d", round_num)
                if cfg.early_stop:
                    break

    return {
        "rounds_run": len(round_accs),
        "train_acc_per_round": round_accs,
        "time_to_stabilization": stabilized_at,
        "judge_parse_failures": judge_parse_failures,
        "rewrites": bundles,
        "registry_counts": registry.counts(),
    }
