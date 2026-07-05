"""Roll every results/**/metrics.json into results/summary.json.

Usage:
    uv run python -m scripts.build_results_summary [--results-root results]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from fdpo.utils.io import atomic_write_json, read_json


def build_summary(results_root: Path) -> dict:
    runs = []
    for metrics_path in sorted(results_root.glob("*/*/metrics.json")):
        m = read_json(metrics_path)
        fdpo_m = m.get("fdpo_metrics") or {}
        runs.append({
            "phase": metrics_path.parent.parent.name,
            "run_id": m.get("run_id", metrics_path.parent.name),
            "status": m.get("status"),
            "dataset": m.get("dataset"),
            "method": m.get("method"),
            "solver_model": m.get("solver_model"),
            "seed": m.get("seed"),
            "seed_accuracy": (m.get("seed_test") or {}).get("accuracy"),
            "final_accuracy": (m.get("final_test") or {}).get("accuracy"),
            "macro_f1": (m.get("final_test") or {}).get("macro_f1"),
            "regression_rate": fdpo_m.get("regression_rate"),
            "section_attribution_accuracy": fdpo_m.get("section_attribution_accuracy"),
            "time_to_stabilization": fdpo_m.get("time_to_stabilization"),
            "n_commits": fdpo_m.get("n_commits"),
            "n_rollbacks": fdpo_m.get("n_rollbacks"),
            "cost_usd": (m.get("cost") or {}).get("total_cost_usd"),
            "wall_clock_s": m.get("wall_clock_s"),
        })
    return {"n_runs": len(runs), "runs": runs}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--results-root", default="results")
    args = p.parse_args(argv)

    root = Path(args.results_root)
    summary = build_summary(root)
    root.mkdir(parents=True, exist_ok=True)
    atomic_write_json(root / "summary.json", summary)
    print(f"wrote {root / 'summary.json'} ({summary['n_runs']} runs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
