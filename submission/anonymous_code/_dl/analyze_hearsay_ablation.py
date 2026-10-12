"""Summarize the Hearsay effect-report ablation and write Paper_COLING/Artifacts/ablation_hearsay.json.

    python _dl/analyze_hearsay_ablation.py
"""
from __future__ import annotations

import glob
import itertools
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Paper_COLING" / "Artifacts" / "ablation_hearsay.json"
ARMS = ("report", "noreport")
TAG = "4omini"
ROUND1_PROMPT = "prompts/ablation/hearsay_round1_4omini.md"
ROUND_GROUPS = (("2", (2,)), ("3", (3,)), ("2-3", (2, 3)))


def load(arm: str) -> list[dict]:
    runs = []
    for path in sorted(glob.glob(str(ROOT / f"results/ablation_hearsay_{TAG}_{arm}/*/metrics.json"))):
        metrics = json.loads(Path(path).read_text(encoding="utf-8"))
        if metrics["status"] == "completed":
            runs.append(metrics)
    return runs


def committed(run: dict) -> dict[int, dict]:
    return {r["round"]: r for r in run["optimization"]["rounds_log"] if r["status"] == "committed"}


def later_rounds(run: dict, rounds: tuple[int, ...]) -> list[dict]:
    return [r for n, r in sorted(committed(run).items()) if n in rounds]


def perm_p(a: list[float], b: list[float]) -> float:
    """Exact two-sided permutation test on the difference of means."""
    pooled, n = a + b, len(a)
    observed = abs(statistics.mean(a) - statistics.mean(b))
    hits = total = 0
    for idx in itertools.combinations(range(len(pooled)), n):
        left = [pooled[i] for i in idx]
        right = [pooled[i] for i in range(len(pooled)) if i not in idx]
        total += 1
        hits += abs(statistics.mean(left) - statistics.mean(right)) >= observed - 1e-12
    return hits / total


def round_summary(runs: list[dict], rounds: tuple[int, ...]) -> dict:
    rs = [r for run in runs for r in later_rounds(run, rounds)]
    sec = [len(r["sections_changed"]) for r in rs]
    return {
        "rounds": len(rs),
        "sections_mean": statistics.mean(sec),
        "single_section": sum(s == 1 for s in sec),
        "mining_recovered": sum(len(r["recovered_this_round"]) for r in rs),
        "mining_regressed": sum(len(r["regressed_this_round"]) for r in rs),
        "validation_recovered": sum(r["val_recovered_this_round"] for r in rs),
        "validation_regressed": sum(r["val_regressed_this_round"] for r in rs),
    }


def per_round_metric(runs: list[dict], rounds: tuple[int, ...], key) -> list[float]:
    return [statistics.mean(key(r) for r in later_rounds(run, rounds)) for run in runs]


def test_conf(run: dict) -> dict:
    return run["optimization"]["test_confusion"]


def run_level(data: dict) -> list[dict]:
    mining_churn = lambda r: len(r["recovered_this_round"]) + len(r["regressed_this_round"])
    mining_net = lambda r: len(r["recovered_this_round"]) - len(r["regressed_this_round"])
    val_churn = lambda r: r["val_recovered_this_round"] + r["val_regressed_this_round"]
    per_run = lambda fn: {arm: [fn(run) for run in data[arm]] for arm in ARMS}
    per_round = lambda fn: {arm: per_round_metric(data[arm], (2, 3), fn) for arm in ARMS}
    specs = [
        ("mining_churn_per_round", per_round(mining_churn)),
        ("mining_net_gain_per_round", per_round(mining_net)),
        ("mining_regressions_per_round", per_round(lambda r: len(r["regressed_this_round"]))),
        ("validation_churn_per_round", per_round(val_churn)),
        ("validation_gain_points", per_run(lambda run: 100 * (
            run["optimization"]["best_structured_val_acc"] - run["optimization"]["baseline_val_acc"]))),
        ("test_churn_per_run", per_run(lambda run: len(test_conf(run)["recoveries"])
                                       + len(test_conf(run)["regressions"]))),
        ("test_regressions_per_run", per_run(lambda run: len(test_conf(run)["regressions"]))),
        ("test_change_points", per_run(lambda run: 100 * (
            run["final_test"]["accuracy"] - run["seed_test"]["accuracy"]))),
    ]
    rows = []
    for name, values in specs:
        rows.append({"metric": name, "report": statistics.mean(values["report"]),
                     "noreport": statistics.mean(values["noreport"]),
                     "p": perm_p(values["report"], values["noreport"]),
                     "report_runs": values["report"], "noreport_runs": values["noreport"]})
    return rows


def section_p(data: dict, rounds: tuple[int, ...]) -> float:
    key = lambda r: len(r["sections_changed"])
    return perm_p(*(per_round_metric(data[arm], rounds, key) for arm in ARMS))


def build(data: dict) -> dict:
    return {
        "benchmark": "LegalBench-Hearsay", "solver": "gpt-4o-mini", "optimizer": "gpt-5", "seed": 0,
        "round1_prompt": ROUND1_PROMPT,
        "runs_per_arm": {arm: len(data[arm]) for arm in ARMS},
        "test": "exact two-sided permutation test on run-level means; uncorrected",
        "rounds": {label: {arm: round_summary(data[arm], rounds) for arm in ARMS}
                   for label, rounds in ROUND_GROUPS},
        "sections_p": {label: section_p(data, rounds) for label, rounds in ROUND_GROUPS},
        "run_level": run_level(data),
        "runs": [{
            "arm": arm, "run_id": run["run_id"], "shipped_round": run["optimization"]["shipped_round"],
            "best_validation_accuracy": run["optimization"]["best_structured_val_acc"],
            "test_seed_accuracy": run["seed_test"]["accuracy"],
            "test_final_accuracy": run["final_test"]["accuracy"],
            "test_recovered": len(test_conf(run)["recoveries"]),
            "test_regressed": len(test_conf(run)["regressions"]),
        } for arm in ARMS for run in data[arm]],
    }


def main() -> None:
    data = {arm: load(arm) for arm in ARMS}
    summary = build(data)
    OUT.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}  runs: {summary['runs_per_arm']}")
    for label, _ in ROUND_GROUPS:
        for arm in ARMS:
            s = summary["rounds"][label][arm]
            print(f"  rounds {label:3s} {arm:9s} sections {s['sections_mean']:.2f} single {s['single_section']}/{s['rounds']} "
                  f"mining {s['mining_recovered']}/{s['mining_regressed']} val {s['validation_recovered']}/{s['validation_regressed']}")
        print(f"    sections p = {summary['sections_p'][label]:.3f}")
    for row in summary["run_level"]:
        print(f"  {row['metric']:30s} report {row['report']:7.2f}  no report {row['noreport']:7.2f}  p = {row['p']:.3f}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
