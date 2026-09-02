"""One-off diagnostic: re-evaluate a SPECIFIC past round's exact prompt
(reconstructed from a completed run's registry.json, via
PromptRegistry.restore_round()) against that run's sealed test set, using
the same split/config/roles the original run used.

Existing runs already ship the best-by-validation round automatically (see
reflect_loop.py's `selection: "best_of_rounds"`) -- this script is for
inspecting a run that predates that mechanism, or for curiosity about a
round that wasn't shipped.

Costs real API money (one fresh test-set pass). Writes
round{N}_test_eval.json into the run directory; does not touch the run's
own metrics.json, eval_log.csv, or registry.json (a SEPARATE ledger file is
used so the run's original cost accounting is untouched).

Usage:
    uv run python -m scripts.eval_round_on_test --run-dir <path> --round N
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from fdpo.clients import make_client
from fdpo.config import ExperimentConfig, load_role
from fdpo.core.registry import PromptRegistry
from fdpo.data.loaders import load_splits
from fdpo.eval.evaluator import evaluate
from fdpo.eval.metrics import standard_metrics
from fdpo.utils.budget import BudgetGuard, TokenLedger
from fdpo.utils.io import atomic_write_json, read_json
from fdpo.utils.log import setup_logging


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-dir", required=True,
                   help="a completed run's results/<phase>/<run_id> directory")
    p.add_argument("--round", type=int, required=True,
                   help="round number to reconstruct and evaluate (0 = seed)")
    args = p.parse_args(argv)

    run_dir = Path(args.run_dir)
    cfg_raw = read_json(run_dir / "config.json")
    logger = setup_logging()

    load_dotenv()
    cfg = ExperimentConfig(
        method=cfg_raw["method"], dataset=cfg_raw["dataset"], seed=cfg_raw["seed"],
        n_train=cfg_raw["n_train"], n_test=cfg_raw["n_test"],
        split_mode=cfg_raw["split_mode"], subjects=tuple(cfg_raw["subjects"]),
        solver_max_tokens=cfg_raw["solver_max_tokens"],
        solver_temperature=cfg_raw["solver_temperature"],
        max_workers=cfg_raw["max_workers"], dataset_root=cfg_raw["dataset_root"],
    )
    cfg.roles["solver"] = load_role("solver")
    cfg.roles["judge"] = load_role("judge")
    if cfg.dataset == "pupa":
        cfg.roles["external"] = load_role("external")

    _, test = load_splits(cfg.dataset, cfg.n_train, cfg.n_test, cfg.seed,
                          dataset_root=cfg.dataset_root, split_mode=cfg.split_mode,
                          subjects=cfg.subjects)

    registry = PromptRegistry.load(run_dir / "registry.json")
    # restore_round() saves to registry.path as a side effect of its normal
    # use inside reflect_loop.py -- clear it FIRST so this diagnostic never
    # overwrites the run's own committed registry.json on disk.
    registry.path = None
    sections = registry.restore_round(args.round)

    logger.info("reconstructed round %d's prompt from %s; evaluating on "
               "%d sealed test examples", args.round, run_dir, len(test))

    ledger = TokenLedger(csv_path=run_dir / f"round{args.round}_ledger.csv")
    guard = BudgetGuard(cap_usd=0.0, ledger=ledger)  # 0 = no cap
    solver = make_client("solver", cfg, ledger=ledger, guard=guard)
    judge = make_client("judge", cfg, ledger=ledger, guard=guard)
    external = (make_client("external", cfg, ledger=ledger, guard=guard)
                if cfg.dataset == "pupa" else None)

    result = evaluate(solver, sections, test, cfg.dataset,
                      temperature=cfg.solver_temperature,
                      max_tokens=cfg.solver_max_tokens, purpose="round-eval",
                      max_workers=cfg.max_workers, judge=judge, external=external)

    metrics = standard_metrics(cfg.dataset, result)
    logger.info("round %d on sealed test: accuracy=%.3f%s", args.round,
               result.accuracy,
               f", mean_score={metrics.get('mean_score', 0):.3f}"
               if cfg.dataset == "pupa" else "")

    out_path = run_dir / f"round{args.round}_test_eval.json"
    atomic_write_json(out_path, {"round": args.round, "n_test": len(test),
                                 **metrics, "cost": ledger.summary()})
    logger.info("wrote %s (spent $%.4f)", out_path, ledger.spent_usd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
