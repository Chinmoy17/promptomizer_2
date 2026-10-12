"""Test scoring of the IFBench / GPT-4o-mini seed and returned prompts.

Both prompts are scored together on the same 42 test items; this writes
Artifacts/ifbench_test_scores.json, which val_test_gap.py reads.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUN = ROOT / "results/reflect_ifbench_v1/ifbench_reflect_fdpo_gpt-4o-mini_s0_20260829-134611"
SCORES = ROOT / "results/reflect_ifbench_v1_test_scores"
SEED_DIR = SCORES / "ifbench_eval_only_gpt-4o-mini_s0_20261013-012648"
FINAL_DIR = SCORES / "ifbench_eval_only_gpt-4o-mini_s0_20261013-012721"
OUT = ROOT / "Paper_COLING" / "Artifacts" / "ifbench_test_scores.json"


def outcomes(path: Path, phase: str | None = None) -> dict[str, bool]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if phase is None or row["phase"] == phase]
    if any(row["blocked"] == "True" for row in rows):
        raise ValueError(f"Provider-blocked items in {path.name}")
    return {row["example_id"]: row["correct"] == "True" for row in rows}


test_ids = list(outcomes(RUN / "eval_log.csv", "seed"))
seed, final = outcomes(SEED_DIR / "eval_log.csv"), outcomes(FINAL_DIR / "eval_log.csv")
if set(seed) != set(test_ids) or set(final) != set(test_ids):
    raise ValueError("Scored items differ from the run's 42-item test split")
recovered = [item for item in test_ids if not seed[item] and final[item]]
regressed = [item for item in test_ids if seed[item] and not final[item]]

OUT.write_text(json.dumps({
    "run": "IFBench / 4o-mini",
    "n_evaluated": len(test_ids),
    "seed_correct": sum(seed.values()),
    "final_correct": sum(final.values()),
    "recovered": len(recovered),
    "regressed": len(regressed),
    "recovered_ids": recovered,
    "regressed_ids": regressed,
    "run_dirs": {"seed": SEED_DIR.relative_to(ROOT).as_posix(),
                 "final": FINAL_DIR.relative_to(ROOT).as_posix()},
}, indent=2), encoding="utf-8")
print(f"seed {sum(seed.values())}/{len(test_ids)} -> final {sum(final.values())}/{len(test_ids)}; "
      f"recovered {len(recovered)}, regressed {len(regressed)}")
print("wrote", OUT.relative_to(ROOT).as_posix())
