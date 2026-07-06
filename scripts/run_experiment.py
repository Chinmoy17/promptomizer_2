"""Run one experiment: (method x dataset x solver x seed) -> results/<phase>/<run_id>/.

Usage:
    uv run python -m scripts.run_experiment --method fdpo --dataset gsm8k --seed 0
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from fdpo.baselines.cot import build_shots
from fdpo.clients import make_client
from fdpo.config import ExperimentConfig, build_arg_parser, config_from_args
from fdpo.core.loop import run_optimization
from fdpo.core.prompt import SCHEMA_5, SCHEMA_MONOLITHIC
from fdpo.core.registry import PromptRegistry
from fdpo.data.loaders import load_splits, synthetic_splits
from fdpo.eval.evaluator import evaluate
from fdpo.eval.metrics import novel_metrics, standard_metrics
from fdpo.prompts.seeds import seed_sections
from fdpo.utils.budget import BudgetExceededError, BudgetGuard, TokenLedger
from fdpo.utils.io import CsvAppender, atomic_write_json, ensure_run_dir, make_run_id
from fdpo.utils.log import setup_logging

EVAL_LOG_FIELDS = ["phase", "example_id", "correct", "pred", "gold"]


def run(cfg: ExperimentConfig, clients: dict | None = None) -> Path:
    solver_model = "mock" if cfg.dry_run else cfg.roles["solver"].model
    run_id = make_run_id(cfg.dataset, cfg.method, solver_model, cfg.seed)
    run_dir = ensure_run_dir(cfg.results_root, cfg.phase, run_id)
    logger = setup_logging(run_dir)
    atomic_write_json(run_dir / "config.json", {**cfg.to_dict(), "run_id": run_id})
    logger.info("run %s -> %s", run_id, run_dir)

    ledger = TokenLedger(fallback_price=(cfg.price_in, cfg.price_out),
                         csv_path=run_dir / "ledger.csv")
    guard = BudgetGuard(cap_usd=cfg.budget_usd, ledger=ledger)
    if clients is None:
        clients = {role: make_client(role, cfg, ledger=ledger, guard=guard)
                   for role in ("solver", "judge", "optimizer")}
    else:  # injected (tests): wire accounting in
        for c in clients.values():
            c.ledger, c.guard = ledger, guard

    if cfg.dry_run:
        train, test = synthetic_splits(cfg.dataset, cfg.n_train, cfg.n_test)
    else:
        train, test = load_splits(cfg.dataset, cfg.n_train, cfg.n_test, cfg.seed,
                                  dataset_root=cfg.dataset_root,
                                  split_mode=cfg.split_mode)
    logger.info("data: %d train / %d test", len(train), len(test))

    schema = SCHEMA_MONOLITHIC if cfg.method == "monolithic" else SCHEMA_5
    registry = PromptRegistry(schema, seed_sections(cfg.dataset, schema),
                              path=run_dir / "registry.json")
    eval_log = CsvAppender(run_dir / "eval_log.csv", EVAL_LOG_FIELDS)

    shots = None
    if cfg.method == "fewshot_cot":
        exemplars = train[: cfg.n_shots]
        train = train[cfg.n_shots:]  # exemplars never appear in optimization/eval
        shots = build_shots(cfg.dataset, exemplars)

    status = "completed"
    seed_result = final_result = None
    opt_summary: dict = {}
    started = time.time()
    try:
        seed_result = evaluate(clients["solver"], registry.active_prompt(), test,
                               cfg.dataset, shots=shots,
                               temperature=cfg.solver_temperature,
                               max_tokens=cfg.solver_max_tokens, purpose="eval",
                               max_workers=cfg.max_workers)
        for row in seed_result.rows:
            eval_log.append({"phase": "seed", "example_id": row.example_id,
                             "correct": row.correct, "pred": row.pred,
                             "gold": row.gold})
        logger.info("seed test accuracy: %.3f", seed_result.accuracy)

        if cfg.method in ("fdpo", "monolithic"):
            opt_summary = run_optimization(cfg, registry, train, cfg.dataset,
                                           clients["solver"], clients["judge"],
                                           clients["optimizer"], run_dir)
            final_result = evaluate(clients["solver"], registry.active_prompt(),
                                    test, cfg.dataset,
                                    temperature=cfg.solver_temperature,
                                    max_tokens=cfg.solver_max_tokens,
                                    purpose="eval", max_workers=cfg.max_workers)
            for row in final_result.rows:
                eval_log.append({"phase": "final", "example_id": row.example_id,
                                 "correct": row.correct, "pred": row.pred,
                                 "gold": row.gold})
            logger.info("final test accuracy: %.3f", final_result.accuracy)
    except BudgetExceededError as e:
        status = "budget_aborted"
        logger.error("BUDGET ABORT: %s — partial results saved", e)

    seed_acc = seed_result.accuracy if seed_result else 0.0
    final_acc = final_result.accuracy if final_result else seed_acc
    metrics = {
        "run_id": run_id,
        "status": status,
        "method": cfg.method,
        "dataset": cfg.dataset,
        "solver_model": solver_model,
        "seed": cfg.seed,
        "seed_test": standard_metrics(cfg.dataset, seed_result) if seed_result else None,
        "final_test": standard_metrics(cfg.dataset, final_result) if final_result
                      else (standard_metrics(cfg.dataset, seed_result) if seed_result else None),
        "optimization": opt_summary or None,
        "wall_clock_s": round(time.time() - started, 1),
        "cost": ledger.summary(),
    }
    if cfg.method in ("fdpo", "monolithic") and opt_summary:
        metrics["fdpo_metrics"] = {
            **novel_metrics(opt_summary.pop("rewrites"), seed_acc, final_acc, ledger),
            "time_to_stabilization": opt_summary["time_to_stabilization"],
        }
    atomic_write_json(run_dir / "metrics.json", metrics)
    logger.info("metrics written: %s (status=%s, spent $%.4f)",
                run_dir / "metrics.json", status, ledger.spent_usd)
    return run_dir


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    cfg = config_from_args(args)
    run(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
