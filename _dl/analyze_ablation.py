"""Summarize the effect-report ablation (results/ablation_<benchmark>_<solver>_<arm>/).

    python _dl/analyze_ablation.py
"""
from __future__ import annotations

import glob
import itertools
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARMS = ("report", "noreport")
SETS = (("hearsay", "4omini"), ("mmlu", "4omini"), ("hearsay", "41mini"), ("mmlu", "41mini"))


def load(bench: str, tag: str, arm: str) -> list[dict]:
    runs = []
    for path in sorted(glob.glob(str(ROOT / f"results/ablation_{bench}_{tag}_{arm}/*/metrics.json"))):
        metrics = json.loads(Path(path).read_text(encoding="utf-8"))
        if metrics["status"] != "completed":
            continue
        config = json.loads(Path(path).with_name("config.json").read_text(encoding="utf-8"))
        metrics["_subject"] = config["subjects"][0] if config.get("subjects") else None
        runs.append(metrics)
    return runs


def committed(run: dict) -> dict[int, dict]:
    return {r["round"]: r for r in run["optimization"]["rounds_log"] if r["status"] == "committed"}


def later_rounds(run: dict, rounds: tuple[int, ...]) -> list[dict]:
    return [r for n, r in sorted(committed(run).items()) if n in rounds]


def perm_p(a: list[float], b: list[float]) -> float | None:
    """Exact two-sided permutation test on the difference of means."""
    if len(a) < 2 or len(b) < 2:
        return None
    pooled, n = a + b, len(a)
    observed = abs(statistics.mean(a) - statistics.mean(b))
    hits = total = 0
    for idx in itertools.combinations(range(len(pooled)), n):
        left = [pooled[i] for i in idx]
        right = [pooled[i] for i in range(len(pooled)) if i not in idx]
        total += 1
        hits += abs(statistics.mean(left) - statistics.mean(right)) >= observed - 1e-12
    return hits / total


def signflip_p(diffs: list[float]) -> float | None:
    """Exact two-sided sign-flip test on paired differences."""
    if len(diffs) < 2:
        return None
    observed = abs(sum(diffs))
    hits = sum(abs(sum(s * d for s, d in zip(signs, diffs))) >= observed - 1e-12
               for signs in itertools.product((1, -1), repeat=len(diffs)))
    return hits / 2 ** len(diffs)


def summarize(runs: list[dict], rounds: tuple[int, ...]) -> dict:
    rs = [r for run in runs for r in later_rounds(run, rounds)]
    sec = [len(r["sections_changed"]) for r in rs]
    nan = float("nan")
    return {
        "rounds": len(rs),
        "sections": statistics.mean(sec) if sec else nan,
        "single": sum(s == 1 for s in sec),
        "m_rec": sum(len(r["recovered_this_round"]) for r in rs),
        "m_reg": sum(len(r["regressed_this_round"]) for r in rs),
        "v_rec": sum(r["val_recovered_this_round"] for r in rs),
        "v_reg": sum(r["val_regressed_this_round"] for r in rs),
        "m_acc": statistics.mean(r["train_acc_after"] for r in rs) if rs else nan,
        "v_acc": statistics.mean(r["val_acc_after"] for r in rs) if rs else nan,
    }


def per_run(runs: list[dict], rounds: tuple[int, ...], key) -> list[tuple[str | None, float]]:
    out = []
    for run in runs:
        rs = later_rounds(run, rounds)
        if rs:
            out.append((run["_subject"], statistics.mean(key(r) for r in rs)))
    return out


def compare(data: dict, rounds: tuple[int, ...], key) -> float | None:
    a, b = (per_run(data[arm], rounds, key) for arm in ARMS)
    if any(s is not None for s, _ in a + b):
        by_subject = {arm: {} for arm in ARMS}
        for arm, values in zip(ARMS, (a, b)):
            for subject, value in values:
                by_subject[arm].setdefault(subject, []).append(value)
        shared = sorted(set(by_subject["report"]) & set(by_subject["noreport"]))
        return signflip_p([statistics.mean(by_subject["report"][s]) - statistics.mean(by_subject["noreport"][s])
                           for s in shared])
    return perm_p([v for _, v in a], [v for _, v in b])


def fmt(p: float | None) -> str:
    return "n/a" if p is None else f"{p:.3f}"


def report(bench: str, tag: str) -> None:
    data = {arm: load(bench, tag, arm) for arm in ARMS}
    if not any(data.values()):
        return
    paired = any(r["_subject"] for arm in ARMS for r in data[arm])
    print(f"\n{'=' * 78}\n{bench} / solver {tag}   runs: "
          + ", ".join(f"{a}={len(data[a])}" for a in ARMS)
          + ("   (tests paired by subject)" if paired else "   (unpaired tests)"))

    print("\nParent state after replaying round 1 (same prompt per subject; differences are evaluation noise)")
    for arm in ARMS:
        r1 = [committed(r)[1] for r in data[arm] if 1 in committed(r)]
        print(f"  {arm:9s} mean mining acc {statistics.mean(r['train_acc_after'] for r in r1):.3f}  "
              f"mean val acc {statistics.mean(r['val_acc_after'] for r in r1):.3f}  (n={len(r1)})")

    for label, rounds in (("Round 2 only (identical parent prompt)", (2,)),
                          ("Round 3 only (parents diverge)", (3,)),
                          ("Rounds 2-3 pooled", (2, 3))):
        print(f"\n{label}")
        print(f"  {'arm':9s} {'rounds':>6s} {'sections':>8s} {'single':>9s} {'mining rec/reg':>15s} "
              f"{'val rec/reg':>12s} {'mining acc':>10s} {'val acc':>8s}")
        for arm in ARMS:
            s = summarize(data[arm], rounds)
            print(f"  {arm:9s} {s['rounds']:6d} {s['sections']:8.2f} {s['single']:4d}/{s['rounds']:<4d} "
                  f"{s['m_rec']:7d}/{s['m_reg']:<7d} {s['v_rec']:5d}/{s['v_reg']:<6d} "
                  f"{s['m_acc']:10.3f} {s['v_acc']:8.3f}")
        print("  p (run-level): sections changed = "
              + fmt(compare(data, rounds, lambda r: len(r["sections_changed"])))
              + ", mining regressions = "
              + fmt(compare(data, rounds, lambda r: len(r["regressed_this_round"]))))

    print("\nReturned prompt and test outcome per run")
    print(f"  {'arm':9s} {'run':24s} {'ship':>4s} {'best val':>8s} {'test seed':>9s} {'test final':>10s} "
          f"{'T rec':>5s} {'T reg':>5s} {'churn':>5s}")
    for arm in ARMS:
        for i, run in enumerate(data[arm], 1):
            opt, tc = run["optimization"], run["optimization"]["test_confusion"]
            rec, reg = len(tc["recoveries"]), len(tc["regressions"])
            best = opt["best_structured_val_acc"]
            print(f"  {arm:9s} {(run['_subject'] or str(i)):24s} {str(opt['shipped_round']):>4s} "
                  f"{'-' if best is None else format(best, '.2f'):>8s} "
                  f"{run['seed_test']['accuracy']:9.3f} {run['final_test']['accuracy']:10.3f} "
                  f"{rec:5d} {reg:5d} {rec + reg:5d}")
    for arm in ARMS:
        runs = data[arm]
        if not runs:
            continue
        d_t = [100 * (r["final_test"]["accuracy"] - r["seed_test"]["accuracy"]) for r in runs]
        churn = [len(r["optimization"]["test_confusion"]["recoveries"])
                 + len(r["optimization"]["test_confusion"]["regressions"]) for r in runs]
        regs = [len(r["optimization"]["test_confusion"]["regressions"]) for r in runs]
        d_v = [100 * (r["optimization"]["best_structured_val_acc"] - r["optimization"]["baseline_val_acc"])
               for r in runs if r["optimization"]["best_structured_val_acc"] is not None]
        print(f"  {arm:9s} mean dV {statistics.mean(d_v):+.1f}  mean dT {statistics.mean(d_t):+.1f}  "
              f"mean test churn {statistics.mean(churn):.1f}  total test regressions {sum(regs)}")
    if paired:
        print("\n  paired test dT (report - no report), per subject: "
              + ", ".join(f"{s}={100 * (a['final_test']['accuracy'] - a['seed_test']['accuracy']) - 100 * (b['final_test']['accuracy'] - b['seed_test']['accuracy']):+.1f}"
                          for a in data["report"] for b in data["noreport"] if a["_subject"] == b["_subject"]
                          for s in [a["_subject"][:10]]))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for benchmark, solver_tag in SETS:
        report(benchmark, solver_tag)
