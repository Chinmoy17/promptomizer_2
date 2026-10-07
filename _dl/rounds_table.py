"""Round-by-round trajectories for the 8 non-MMLU runs, printed as LaTeX rows,
plus summary statistics used in the paper's appendix. Reads saved metrics.json.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
RUNS = [
    ("AIME", "4o-mini", "reflect_aime_v1"),
    ("AIME", "4.1 Mini", "reflect_aime_gpt41mini_v3"),
    ("PUPA", "4o-mini", "pupa_pilot_v1"),
    ("PUPA", "4.1 Mini", "pupa_pilot_gpt41mini_v2"),
    ("IFBench", "4o-mini", "reflect_ifbench_v1"),
    ("IFBench", "4.1 Mini", "reflect_ifbench_gpt41mini_v2"),
    ("Hearsay", "4o-mini", "reflect_hearsay_gpt4omini_v1"),
    ("Hearsay", "4.1 Mini", "reflect_hearsay_gpt41mini_v1"),
]
ABBR = {"system_role": "SR", "context": "Ctx", "task_details": "TD",
        "constraints": "Con", "output_format": "OF"}


def latest(sub: str) -> dict:
    d = sorted(p for p in (RES / sub).iterdir() if (p / "metrics.json").exists())[-1]
    return json.loads((d / "metrics.json").read_text(encoding="utf-8"))


n_rounds = n_val_drop = n_mine_net_neg = n_val_net_neg = 0
n_later = 0
for bench, model, sub in RUNS:
    m = latest(sub)
    o = m["optimization"]
    log = o.get("rounds_log", [])
    shipped = o.get("shipped_round") if o.get("shipped_structured") else None
    base_m = o.get("baseline_train", {}).get("accuracy")
    base_v = o.get("baseline_val_acc")
    print(f"{bench} & {model} & 0 & {100*base_m:.1f} & {100*base_v:.1f} & -- & -- & -- \\\\")
    prev_v = base_v
    for r in log:
        t = r["round"]
        if "recovered_this_round" not in r:
            print(f" & & {t} & \\multicolumn{{5}}{{c}}{{{r.get('status', 'skipped')}}} \\\\")
            continue
        mr, mg = len(r["recovered_this_round"]), len(r["regressed_this_round"])
        vr, vg = r["val_recovered_this_round"], r["val_regressed_this_round"]
        secs = ",".join(ABBR.get(s, s) for s in r["sections_changed"])
        star = "$^*$" if shipped == t else ""
        print(f" & & {t}{star} & {100*r['train_acc_after']:.1f} & {100*r['val_acc_after']:.1f} "
              f"& {mr}/{mg} & {vr}/{vg} & {secs} \\\\")
        n_rounds += 1
        if r["val_acc_after"] < prev_v:
            n_val_drop += 1
        if mg > mr:
            n_mine_net_neg += 1
        if vg > vr:
            n_val_net_neg += 1
        if t >= 2:
            n_later += 1
        prev_v = r["val_acc_after"]
    print("\\midrule")

print(f"\n% rounds={n_rounds} (rounds>=2: {n_later})  val acc below previous round: {n_val_drop}  "
      f"mining regressed>recovered: {n_mine_net_neg}  val regressed>recovered: {n_val_net_neg}")
