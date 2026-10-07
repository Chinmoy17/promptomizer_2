"""Evidence for the paper's design-decision appendix, computed from saved runs.

Prints (and writes Paper_COLING/Artifacts/design_evidence.json):
  1. which round had the best validation accuracy vs. the round that shipped / the last round
  2. how many sections the optimizer edits in round 1 vs later rounds
  3. optimizer parse failures / no-change rounds from run.log
  4. optimizer prompt size per call (cost of showing every item)
  5. selection inflation: expected best-of-N validation gain under NO true improvement
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"

RUNS = [
    ("AIME 4o", "reflect_aime_v1"), ("AIME 4.1", "reflect_aime_gpt41mini_v3"),
    ("PUPA 4o", "pupa_pilot_v1"), ("PUPA 4.1", "pupa_pilot_gpt41mini_v2"),
    ("IFB 4o", "reflect_ifbench_v1"), ("IFB 4.1", "reflect_ifbench_gpt41mini_v2"),
    ("Hear 4o", "reflect_hearsay_gpt4omini_v1"), ("Hear 4.1", "reflect_hearsay_gpt41mini_v1"),
]
for s in ["college_mathematics", "computer_security", "econometrics",
          "high_school_biology", "philosophy", "professional_law"]:
    RUNS.append((f"MMLU-{s[:6]} 4o", f"mmlu_reflect_{s}"))
    RUNS.append((f"MMLU-{s[:6]} 4.1", f"mmlu_reflect_gpt41mini_{s}"))


def run_dir(sub: str) -> Path:
    return sorted(p for p in (RES / sub).iterdir() if (p / "metrics.json").exists())[-1]


out: dict = {}
data = {}
for label, sub in RUNS:
    d = run_dir(sub)
    data[label] = (d, json.loads((d / "metrics.json").read_text(encoding="utf-8")))

# ---- 1. selection ----------------------------------------------------------
print("=== 1. best-validation round vs shipped / last round ===")
hist = {1: 0, 2: 0, 3: 0}
n_unique = n_last_best = 0
last_rule_deficits, best_rule_adv = [], []
for label, (d, m) in data.items():
    o = m["optimization"]
    log = [r for r in o.get("rounds_log", []) if "val_acc_after" in r]
    if not log:
        continue
    vals = {r["round"]: r["val_acc_after"] for r in log}
    best = max(vals.values())
    best_rounds = [t for t, v in vals.items() if abs(v - best) < 1e-9]
    last_round = max(vals)
    if len(best_rounds) == 1:
        n_unique += 1
        hist[best_rounds[0]] += 1
        if best_rounds[0] == last_round:
            n_last_best += 1
    sel = o.get("selection")
    gap_last = 100 * (best - vals[last_round])
    if sel == "last_round":
        last_rule_deficits.append((label, round(gap_last, 1)))
    elif sel == "best_of_rounds":
        sr = o.get("shipped_round")
        if sr is not None:
            best_rule_adv.append((label, round(100 * (vals[sr] - vals[last_round]), 1)))
print(f"runs with a unique best-validation round: {n_unique}; by round: {hist}; "
      f"last round was the unique best in {n_last_best}")
print("final-round rule: best-minus-shipped(last) validation (pp):", last_rule_deficits)
print("best-of-rounds rule: shipped-minus-last validation (pp):", best_rule_adv)
out["selection"] = {"unique_best_by_round": hist, "n_unique": n_unique,
                    "last_was_unique_best": n_last_best,
                    "last_rule_deficit_pp": last_rule_deficits,
                    "best_rule_advantage_pp": best_rule_adv}

# ---- 2. sections edited ----------------------------------------------------
print("\n=== 2. sections edited per committed round ===")
w1, w2 = [], []
sec_counts: dict[str, int] = {}
for label, (d, m) in data.items():
    for r in m["optimization"].get("rounds_log", []):
        if "sections_changed" not in r:
            continue
        w = len(r["sections_changed"])
        (w1 if r["round"] == 1 else w2).append(w)
        for s in r["sections_changed"]:
            sec_counts[s] = sec_counts.get(s, 0) + 1
print(f"round 1: n={len(w1)} mean sections edited={np.mean(w1):.2f}")
print(f"rounds 2-3: n={len(w2)} mean sections edited={np.mean(w2):.2f}; single-section rounds={sum(1 for x in w2 if x == 1)}")
print("times each section was edited (all committed rounds):", sec_counts)
out["sections"] = {"round1_mean": float(np.mean(w1)), "round1_n": len(w1),
                   "later_mean": float(np.mean(w2)), "later_n": len(w2),
                   "later_single": sum(1 for x in w2 if x == 1), "counts": sec_counts}

# ---- 3. parse failures ------------------------------------------------------
print("\n=== 3. optimizer parse failures / omitted sections / no-change rounds ===")
tot = {"parse failed": 0, "omitted sections": 0, "proposed no changes": 0}
for label, (d, m) in data.items():
    p = d / "run.log"
    if not p.exists():
        continue
    t = p.read_text(encoding="utf-8", errors="ignore")
    for k in tot:
        tot[k] += len(re.findall(k, t))
print(tot, "over", len(data), "runs (run.log present for some)")
n_logs = sum(1 for _, (d, _) in data.items() if (d / "run.log").exists())
print("runs with run.log:", n_logs)
out["parse"] = {**tot, "runs_with_log": n_logs}

# ---- 4. optimizer prompt size ----------------------------------------------
print("\n=== 4. optimizer prompt tokens per call (cost of showing every item) ===")
per_bench: dict[str, list] = {}
for label, (d, m) in data.items():
    opt = m.get("cost", {}).get("by_role", {}).get("optimizer")
    if not opt or not opt["calls"]:
        continue
    bench = label.split(" ")[0].split("-")[0]
    per_bench.setdefault(bench, []).append(opt["prompt_tokens"] / opt["calls"])
for b, v in per_bench.items():
    print(f"{b:8s} n_runs={len(v):2d} mean={np.mean(v):9.0f}  min={min(v):9.0f}  max={max(v):9.0f}")
out["optimizer_prompt_tokens_per_call"] = {b: [float(min(v)), float(np.mean(v)), float(max(v))]
                                           for b, v in per_bench.items()}

# ---- 5. selection inflation -------------------------------------------------
print("\n=== 5. selection inflation under NO true improvement ===")
churn = []
for label, (d, m) in data.items():
    nv = m["optimization"]["val_split"]["n_validation"]
    for r in m["optimization"].get("rounds_log", []):
        if "val_recovered_this_round" in r and nv:
            churn.append((r["val_recovered_this_round"] + r["val_regressed_this_round"]) / nv)
mean_churn = float(np.mean(churn))
print(f"observed mean per-round validation churn: {100*mean_churn:.1f}% of items (n_rounds={len(churn)})")
rng = np.random.default_rng(0)


def sim(n: int, p: float, rounds: int, f: float, reps: int = 40000) -> float:
    """Mean of (max over rounds of val acc) - (baseline val acc) when no prompt is truly better.
    Each round re-draws a fraction f of items; f=1 means independent evaluations."""
    base = rng.random((reps, n)) < p
    cur = base.copy()
    best = np.full(reps, -1.0)
    for _ in range(rounds):
        redraw = rng.random((reps, n)) < f
        fresh = rng.random((reps, n)) < p
        cur = np.where(redraw, fresh, cur)
        best = np.maximum(best, cur.mean(axis=1))
    return float(100 * np.mean(best - base.mean(axis=1)))


rows = []
for n in (20, 25, 32):
    p = 0.7
    f_obs = min(1.0, mean_churn / (2 * p * (1 - p)))
    se = 100 * np.sqrt(p * (1 - p) / n)
    r = {"n": n, "p": p, "se_pp": round(float(se), 1), "f_matched": round(float(f_obs), 2),
         "inflation_matched_pp": round(sim(n, p, 3, f_obs), 1),
         "inflation_independent_pp": round(sim(n, p, 3, 1.0), 1)}
    rows.append(r)
    print(r)
out["inflation"] = {"mean_val_churn": mean_churn, "rows": rows}

(ROOT / "Paper_COLING" / "Artifacts" / "design_evidence.json").write_text(
    json.dumps(out, indent=2, default=str), encoding="utf-8")
print("\nwrote Paper_COLING/Artifacts/design_evidence.json")
