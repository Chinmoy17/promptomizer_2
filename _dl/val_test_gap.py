"""Validation-vs-test comparison for the 10 canonical (benchmark x model) runs
plus the 12 MMLU per-subject runs, read directly from each run's metrics.json.

Prints a table and writes Paper_COLING/Artifacts/val_test_gap.json.
AIME / GPT-4.1 Mini uses the corrected 14/30 baseline per RESULTS.md.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"

# (label, results subdir) ; latest timestamped run under the subdir is used.
RUNS = [
    ("AIME / 4o-mini", "reflect_aime_v1"),
    ("AIME / 4.1-mini", "reflect_aime_gpt41mini_v3"),
    ("PUPA / 4o-mini", "pupa_pilot_v1"),
    ("PUPA / 4.1-mini", "pupa_pilot_gpt41mini_v2"),
    ("IFBench / 4o-mini", "reflect_ifbench_v1"),
    ("IFBench / 4.1-mini", "reflect_ifbench_gpt41mini_v2"),
    ("Hearsay / 4o-mini", "reflect_hearsay_gpt4omini_v1"),
    ("Hearsay / 4.1-mini", "reflect_hearsay_gpt41mini_v1"),
]
SUBJECTS = ["college_mathematics", "computer_security", "econometrics",
            "high_school_biology", "philosophy", "professional_law"]
for s in SUBJECTS:
    RUNS.append((f"MMLU-{s} / 4o-mini", f"mmlu_reflect_{s}"))
for s in SUBJECTS:
    RUNS.append((f"MMLU-{s} / 4.1-mini", f"mmlu_reflect_gpt41mini_{s}"))

# No overrides: every number is the saved artifact. (The 14/30 "corrected" AIME
# baseline is not backed by a saved seed-prompt evaluation; see paper Sec. 5.)
OVERRIDE_SEED_TEST: dict[str, float] = {}


def latest_metrics(subdir: str) -> dict:
    runs = sorted(p for p in (RES / subdir).iterdir() if (p / "metrics.json").exists())
    return json.loads((runs[-1] / "metrics.json").read_text(encoding="utf-8"))


rows = []
for label, subdir in RUNS:
    m = latest_metrics(subdir)
    o = m["optimization"]
    shipped = bool(o.get("shipped_structured"))
    val0 = o.get("baseline_val_acc")
    val1 = o.get("best_structured_val_acc") if shipped else val0
    t0 = OVERRIDE_SEED_TEST.get(label, m["seed_test"]["accuracy"])
    t1 = m["final_test"]["accuracy"]
    rows.append({
        "run": label,
        "shipped": shipped,
        "selection": o.get("selection"),
        "shipped_round": o.get("shipped_round"),
        "val_base": val0, "val_best": val1,
        "val_gain_pp": None if val0 is None else round(100 * (val1 - val0), 1),
        "test_base": t0, "test_final": t1,
        "test_delta_pp": round(100 * (t1 - t0), 1),
        "rounds_run": o.get("rounds_run"),
    })

hdr = f"{'run':38s} ship  val_base val_best  dVal(pp)  t_base t_final dTest(pp)"
print(hdr)
for r in rows:
    vb = "  n/a " if r["val_base"] is None else f"{r['val_base']:.3f}"
    vv = "  n/a " if r["val_best"] is None else f"{r['val_best']:.3f}"
    dv = "  n/a" if r["val_gain_pp"] is None else f"{r['val_gain_pp']:+.1f}"
    print(f"{r['run']:38s} {str(r['shipped'])[0]:4s} {vb:>8s} {vv:>8s} {dv:>8s}  "
          f"{r['test_base']:.3f}  {r['test_final']:.3f}  {r['test_delta_pp']:+.1f}")

core = rows[:8]
mmlu = rows[8:]


def summarize(name: str, rs: list[dict]) -> None:
    shipped = [r for r in rs if r["shipped"] and r["val_gain_pp"] is not None]
    vgain = [r for r in shipped if r["val_gain_pp"] > 0]
    gap = [r for r in vgain if r["test_delta_pp"] <= 0]
    both = [r for r in vgain if r["test_delta_pp"] > 0]
    mean_v = sum(r["val_gain_pp"] for r in shipped) / max(len(shipped), 1)
    mean_t = sum(r["test_delta_pp"] for r in shipped) / max(len(shipped), 1)
    print(f"\n[{name}] n={len(rs)} shipped={len(shipped)} "
          f"val_gain>0: {len(vgain)}  of which test<=0: {len(gap)}  test>0: {len(both)}  "
          f"mean dVal={mean_v:+.1f}pp  mean dTest={mean_t:+.1f}pp")


summarize("core 8 (non-MMLU)", core)
summarize("MMLU 12 subject-runs", mmlu)
summarize("all 20", rows)
summarize("selection=last_round (older rule)", [r for r in rows if r["selection"] == "last_round"])
summarize("selection=best_of_rounds", [r for r in rows if r["selection"] == "best_of_rounds"])
summarize("core-8, last_round", [r for r in core if r["selection"] == "last_round"])
summarize("core-8, best_of_rounds", [r for r in core if r["selection"] == "best_of_rounds"])

(ROOT / "Paper_COLING" / "Artifacts" / "val_test_gap.json").write_text(
    json.dumps(rows, indent=2), encoding="utf-8")
print("\nwrote Paper_COLING/Artifacts/val_test_gap.json")
