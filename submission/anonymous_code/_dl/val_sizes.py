"""Validation-set sizes per run (the paper quotes a 'smallest validation set')."""
import json
from pathlib import Path

RES = Path(__file__).resolve().parent.parent / "results"
RUNS = [("AIME 4o", "reflect_aime_v1"), ("AIME 4.1", "reflect_aime_gpt41mini_v3"),
        ("PUPA 4o", "pupa_pilot_v1"), ("PUPA 4.1", "pupa_pilot_gpt41mini_v2"),
        ("IFB 4o", "reflect_ifbench_v1"), ("IFB 4.1", "reflect_ifbench_gpt41mini_v2"),
        ("Hear 4o", "reflect_hearsay_gpt4omini_v1"), ("Hear 4.1", "reflect_hearsay_gpt41mini_v1"),
        ("MMLU-phil 4o", "mmlu_reflect_philosophy"), ("MMLU-law 4.1", "mmlu_reflect_gpt41mini_professional_law")]
for k, sub in RUNS:
    d = sorted(p for p in (RES / sub).iterdir() if (p / "metrics.json").exists())[-1]
    o = json.loads((d / "metrics.json").read_text(encoding="utf-8"))["optimization"]
    print(f"{k:14s} val_split={o['val_split']}")
