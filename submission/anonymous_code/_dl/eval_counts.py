"""Test-set denominators for the 10 canonical runs (blocked = provider content filter)."""
import json
from pathlib import Path

RES = Path(__file__).resolve().parent.parent / "results"
RUNS = {
    "AIME 4o": "reflect_aime_v1", "AIME 4.1": "reflect_aime_gpt41mini_v3",
    "PUPA 4o": "pupa_pilot_v1", "PUPA 4.1": "pupa_pilot_gpt41mini_v2",
    "IFB 4o": "reflect_ifbench_v1", "IFB 4.1": "reflect_ifbench_gpt41mini_v2",
    "Hear 4o": "reflect_hearsay_gpt4omini_v1", "Hear 4.1": "reflect_hearsay_gpt41mini_v1",
}
for s in ["college_mathematics", "computer_security", "econometrics",
          "high_school_biology", "philosophy", "professional_law"]:
    RUNS[f"MMLU-{s[:8]} 4o"] = f"mmlu_reflect_{s}"
    RUNS[f"MMLU-{s[:8]} 4.1"] = f"mmlu_reflect_gpt41mini_{s}"
for k, sub in RUNS.items():
    d = sorted(p for p in (RES / sub).iterdir() if (p / "metrics.json").exists())[-1]
    m = json.loads((d / "metrics.json").read_text(encoding="utf-8"))
    b, f = m["seed_test"], m["final_test"]
    print(f"{k:22s} n={b['n_examples']:3d} eval_seed={b['n_evaluated']:3d} blocked_seed={b['n_blocked']} "
          f"eval_final={f['n_evaluated']:3d} blocked_final={f['n_blocked']}")
