"""The FDPO offline batch optimization loop.

Per round: evaluate the active prompt on the train subsample; failures are
judge-attributed to sections; each implicated section is rewritten and must
pass the regression gate before commit. No online/tau trigger — the round
structure IS the trigger policy, kept as this single function so an online
variant can replace it later (ablation A10).

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
from fdpo.core.optimizer import rewrite_section
from fdpo.core.registry import PromptRegistry
from fdpo.data.loaders import Example
from fdpo.eval.evaluator import evaluate
from fdpo.utils.io import CsvAppender, JsonlAppender

logger = logging.getLogger("fdpo")

TRAIN_LOG_FIELDS = ["round", "example_id", "correct", "pred", "gold", "section"]
ROUNDS_LOG_FIELDS = ["round", "section", "n_failures", "acc_old", "acc_new",
                     "passed", "broke", "recovered", "batch_size"]


def run_optimization(cfg: ExperimentConfig, registry: PromptRegistry,
                     train: list[Example], dataset: str,
                     solver: ModelClient, judge: ModelClient,
                     optimizer: ModelClient, run_dir: Path) -> dict:
    """Returns a summary dict; per-rewrite records also land in rounds_log.csv."""
    rng = random.Random(cfg.seed)
    pool = CorrectPool(cap=cfg.pool_cap)
    train_by_id = {ex.id: ex for ex in train}
    train_log = CsvAppender(run_dir / "train_log.csv", TRAIN_LOG_FIELDS)
    rounds_log = CsvAppender(run_dir / "rounds_log.csv", ROUNDS_LOG_FIELDS)
    events = JsonlAppender(run_dir / "events.jsonl")

    rewrites: list[dict] = []
    round_accs: list[float] = []
    stabilized_at: int | None = None
    judge_parse_failures = 0

    for round_num in range(1, cfg.max_rounds + 1):
        # 1. evaluate active prompt on the train stream
        active = registry.active_prompt()
        result = evaluate(solver, active, train, dataset,
                          temperature=cfg.solver_temperature,
                          max_tokens=cfg.solver_max_tokens, purpose="train")
        round_accs.append(result.accuracy)
        logger.info("round %d: train accuracy %.3f", round_num, result.accuracy)

        # 2. verdicts -> pool / judge attribution
        failures_by_section: dict[str, list[dict]] = {s: [] for s in registry.schema}
        correct_examples: list[Example] = []
        for row in result.rows:
            ex = train_by_id[row.example_id]
            section_label = ""
            if row.correct:
                pool.add(ex)
                correct_examples.append(ex)
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

        # 3. rewrite + gate each implicated section, most failures first
        implicated = sorted(
            (s for s in registry.schema if failures_by_section[s]),
            key=lambda s: len(failures_by_section[s]), reverse=True)
        for section in implicated:
            failures = failures_by_section[section]
            sampled_failures = failures[: cfg.n_fail]
            golds = (rng.sample(correct_examples, min(cfg.n_gold, len(correct_examples)))
                     if correct_examples else train[: cfg.n_gold])

            active = registry.active_prompt()
            other = {n: t for n, t in active.items() if n != section}
            candidate = rewrite_section(optimizer, section, active[section],
                                        other, sampled_failures, golds,
                                        temperature=cfg.optimizer_temperature)

            gate_batch = pool.sample(cfg.gate_batch_size, rng)
            gate = evaluate_candidate(
                solver, dataset, active, registry.prompt_with(section, candidate),
                gate_batch, [f["example"] for f in sampled_failures],
                rho=cfg.rho, solver_temperature=cfg.solver_temperature,
                solver_max_tokens=cfg.solver_max_tokens)

            if gate.passed:
                registry.commit(section, candidate, round_num, gate)
            else:
                registry.reject(section, candidate, round_num, gate)
            registry.record_round_acc(section,
                                      gate.acc_new if gate.passed else gate.acc_old)
            if registry.sections[section].stagnant_rounds >= cfg.stagnation_limit:
                logger.info("section %s stagnant %d rounds -> restoring best snapshot",
                            section, registry.sections[section].stagnant_rounds)
                registry.restore_best_snapshot(section)

            record = {"round": round_num, "section": section,
                      "n_failures": len(sampled_failures),
                      "acc_old": gate.acc_old, "acc_new": gate.acc_new,
                      "passed": gate.passed, "broke": gate.broke,
                      "recovered": gate.recovered_failures,
                      "batch_size": gate.batch_size}
            rounds_log.append(record)
            events.append({"event": "rewrite", **record})
            rewrites.append({"committed": gate.passed, "broke": gate.broke,
                             "batch_size": gate.batch_size,
                             "n_failures": gate.n_failures,
                             "recovered_failures": gate.recovered_failures})
            logger.info("round %d [%s]: %s (old %.3f -> new %.3f, broke %d, recovered %d/%d)",
                        round_num, section,
                        "COMMIT" if gate.passed else "REJECT",
                        gate.acc_old, gate.acc_new, gate.broke,
                        gate.recovered_failures, gate.n_failures)

        # 4. stabilization check on train accuracy
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
        "rewrites": rewrites,
        "registry_counts": registry.counts(),
    }
