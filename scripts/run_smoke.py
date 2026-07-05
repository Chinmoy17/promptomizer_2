"""Phase-0 smoke matrix: {gsm8k, arc} x {zeroshot_cot, fewshot_cot, monolithic, fdpo}
under one cumulative budget cap.

Usage:
    uv run python -m scripts.run_smoke --budget-usd 25
    uv run python -m scripts.run_smoke --dry-run          # no APIs, pipeline check
"""

from __future__ import annotations

import argparse
import sys

from fdpo.config import ExperimentConfig, ROLES, load_role
from fdpo.utils.budget import TokenLedger
from fdpo.utils.io import read_json
from fdpo.utils.log import setup_logging
from scripts.run_experiment import run

SMOKE_DATASETS = ("gsm8k", "arc")
SMOKE_METHODS = ("zeroshot_cot", "fewshot_cot", "monolithic", "fdpo")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the Phase-0 smoke matrix.")
    p.add_argument("--budget-usd", type=float, default=25.0,
                   help="cumulative cap across ALL smoke runs")
    p.add_argument("--per-run-budget-usd", type=float, default=4.0)
    p.add_argument("--n-train", type=int, default=150)
    p.add_argument("--n-test", type=int, default=200)
    p.add_argument("--max-rounds", type=int, default=5)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--phase", default="00_smoke")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    logger = setup_logging()
    from dotenv import load_dotenv
    load_dotenv()

    spent_total = 0.0
    completed, aborted, skipped = [], [], []

    for dataset in SMOKE_DATASETS:
        for method in SMOKE_METHODS:
            remaining = args.budget_usd - spent_total
            if not args.dry_run and remaining < 0.50:
                skipped.append(f"{dataset}/{method}")
                logger.warning("skipping %s/%s: only $%.2f of the smoke budget left",
                               dataset, method, remaining)
                continue

            cfg = ExperimentConfig(
                method=method, dataset=dataset, seed=args.seed,
                n_train=args.n_train, n_test=args.n_test,
                max_rounds=args.max_rounds,
                budget_usd=min(args.per_run_budget_usd, remaining),
                phase=args.phase, dry_run=args.dry_run,
            )
            if not args.dry_run:
                cfg.roles = {role: load_role(role) for role in ROLES}

            logger.info("=== smoke run: %s / %s (per-run cap $%.2f, total spent $%.2f) ===",
                        dataset, method, cfg.budget_usd, spent_total)
            run_dir = run(cfg)
            metrics = read_json(run_dir / "metrics.json")
            spent_total += metrics["cost"]["total_cost_usd"]
            (completed if metrics["status"] == "completed" else aborted).append(
                f"{dataset}/{method}")

    logger.info("SMOKE DONE: %d completed %s | %d aborted %s | %d skipped %s | total $%.2f",
                len(completed), completed, len(aborted), aborted,
                len(skipped), skipped, spent_total)
    return 0 if not aborted and not skipped else 1


if __name__ == "__main__":
    sys.exit(main())
