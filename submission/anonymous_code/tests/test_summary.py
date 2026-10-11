"""build_results_summary rolls run metrics into one summary.json."""

from fdpo.config import ExperimentConfig
from fdpo.utils.io import read_json
from scripts.build_results_summary import main as summary_main
from scripts.run_experiment import run


def test_summary_rollup(tmp_path):
    results_root = tmp_path / "results"
    for method in ("zeroshot_cot", "fdpo"):
        cfg = ExperimentConfig(method=method, dataset="arc", n_train=6, n_test=4,
                               max_rounds=1, budget_usd=0.0, dry_run=True,
                               results_root=str(results_root), phase="00_test")
        run(cfg)

    assert summary_main(["--results-root", str(results_root)]) == 0
    summary = read_json(results_root / "summary.json")
    assert summary["n_runs"] == 2
    methods = {r["method"] for r in summary["runs"]}
    assert methods == {"zeroshot_cot", "fdpo"}
    fdpo_row = next(r for r in summary["runs"] if r["method"] == "fdpo")
    assert fdpo_row["status"] == "completed"
    assert fdpo_row["n_commits"] is not None
