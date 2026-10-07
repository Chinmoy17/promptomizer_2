"""Which selection rule shipped each canonical run, and did it ship the best-validation round?"""
import json
from pathlib import Path

RES = Path(__file__).resolve().parent.parent / "results"
RUNS = [
    ("AIME 4o", "reflect_aime_v1"), ("AIME 4.1", "reflect_aime_gpt41mini_v3"),
    ("PUPA 4o", "pupa_pilot_v1"), ("PUPA 4.1", "pupa_pilot_gpt41mini_v2"),
    ("IFB 4o", "reflect_ifbench_v1"), ("IFB 4.1", "reflect_ifbench_gpt41mini_v2"),
    ("Hear 4o", "reflect_hearsay_gpt4omini_v1"), ("Hear 4.1", "reflect_hearsay_gpt41mini_v1"),
]
for s in ["college_mathematics", "computer_security", "econometrics",
          "high_school_biology", "philosophy", "professional_law"]:
    RUNS.append((f"MMLU-{s[:8]} 4o", f"mmlu_reflect_{s}"))
    RUNS.append((f"MMLU-{s[:8]} 4.1", f"mmlu_reflect_gpt41mini_{s}"))

print(f"{'run':20s} {'selection':14s} shipped_rd  val_by_round            argmax_val_rd  ships_best?")
for k, sub in RUNS:
    d = sorted(p for p in (RES / sub).iterdir() if (p / "metrics.json").exists())[-1]
    o = json.loads((d / "metrics.json").read_text(encoding="utf-8"))["optimization"]
    log = [r for r in o.get("rounds_log", []) if "val_acc_after" in r]
    vals = {r["round"]: round(r["val_acc_after"], 3) for r in log}
    best = max(vals.values()) if vals else None
    best_rounds = [t for t, v in vals.items() if v == best]
    sr = o.get("shipped_round")
    ok = (sr in best_rounds) if (sr is not None and best is not None) else None
    print(f"{k:20s} {str(o.get('selection')):14s} {str(sr):10s}  {str(vals):28s} {str(best_rounds):13s} {ok}")
