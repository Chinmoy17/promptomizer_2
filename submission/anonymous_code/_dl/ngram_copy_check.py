"""Verbatim-copy check: does any shipped prompt contain word 8-grams that also
occur in dataset items (train or test)? Used to support the paper's claim that
validation/test divergence is not explained by the optimizer pasting items.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES, DS = ROOT / "results", ROOT / "Dataset"
N = 8

RUNS = [
    ("AIME / 4o-mini", "reflect_aime_v1", "aime"),
    ("AIME / 4.1-mini", "reflect_aime_gpt41mini_v3", "aime"),
    ("PUPA / 4o-mini", "pupa_pilot_v1", "pupa"),
    ("PUPA / 4.1-mini", "pupa_pilot_gpt41mini_v2", "pupa"),
    ("IFBench / 4o-mini", "reflect_ifbench_v1", "ifbench"),
    ("IFBench / 4.1-mini", "reflect_ifbench_gpt41mini_v2", "ifbench"),
    ("Hearsay / 4o-mini", "reflect_hearsay_gpt4omini_v1", "legalbench_hearsay"),
    ("Hearsay / 4.1-mini", "reflect_hearsay_gpt41mini_v1", "legalbench_hearsay"),
]
for s in ["college_mathematics", "computer_security", "econometrics",
          "high_school_biology", "philosophy", "professional_law"]:
    RUNS.append((f"MMLU-{s} / 4o-mini", f"mmlu_reflect_{s}", "mmlu"))
    RUNS.append((f"MMLU-{s} / 4.1-mini", f"mmlu_reflect_gpt41mini_{s}", "mmlu"))


def toks(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def grams(words: list[str]) -> set[tuple]:
    return {tuple(words[i:i + N]) for i in range(len(words) - N + 1)}


def flat(o) -> str:
    if isinstance(o, str):
        return o
    if isinstance(o, dict):
        return " ".join(flat(v) for v in o.values())
    if isinstance(o, list):
        return " ".join(flat(v) for v in o)
    return ""


cache: dict[str, set] = {}


def item_grams(name: str) -> set:
    if name not in cache:
        g: set = set()
        for split in ("train", "test"):
            p = DS / name / f"{split}.jsonl"
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        g |= grams(toks(flat(json.loads(line))))
        cache[name] = g
    return cache[name]


print(f"{'run':38s} shipped  prompt_8grams  shared_with_items")
out = []
for label, sub, ds in RUNS:
    run = sorted(p for p in (RES / sub).iterdir() if (p / "metrics.json").exists())[-1]
    m = json.loads((run / "metrics.json").read_text(encoding="utf-8"))
    shipped = bool(m["optimization"].get("shipped_structured"))
    pg = grams(toks((run / "prompt_current.md").read_text(encoding="utf-8")))
    shared = pg & item_grams(ds)
    out.append({"run": label, "shipped": shipped, "prompt_8grams": len(pg),
                "shared": len(shared), "examples": [" ".join(x) for x in list(shared)[:2]]})
    print(f"{label:38s} {str(shipped)[0]:7s} {len(pg):13d} {len(shared):18d}")
    for e in out[-1]["examples"]:
        print(f"      e.g. '{e}'")

(ROOT / "Paper_COLING" / "Artifacts" / "ngram_copy_check.json").write_text(
    json.dumps(out, indent=2), encoding="utf-8")
