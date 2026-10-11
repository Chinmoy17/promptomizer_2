"""Count Azure content-filter blocks per subject/run.

A content-filtered solver call returns an empty completion with prompt_tokens=0
and completion_tokens=0 (see clients/openai_client.py). Every other call has
prompt_tokens > 0. So 0/0-token solver rows in ledger.csv are exactly the
content-filter blocks. This quantifies how much each subject was affected.
"""

from __future__ import annotations

import csv
import glob
import os

SUBJECTS = [
    "professional_law", "computer_security", "econometrics",
    "philosophy", "high_school_biology", "college_mathematics",
]


def main() -> None:
    print("=" * 72)
    print("Azure content-filter blocks per subject (neutral-baseline MMLU runs)")
    print("  a block = solver ledger row with 0 prompt AND 0 completion tokens")
    print("=" * 72)
    grand_b = grand_s = 0
    for s in SUBJECTS:
        runs = sorted(glob.glob(f"results/mmluneutral_{s}/*/"))
        tot_b = tot_s = 0
        per_run = []
        for d in runs:
            led = os.path.join(d, "ledger.csv")
            if not os.path.exists(led):
                continue
            with open(led, encoding="utf-8") as f:
                rows = [r for r in csv.DictReader(f) if r["role"] == "solver"]
            blocked = sum(1 for r in rows
                          if int(r["prompt_tokens"]) == 0
                          and int(r["completion_tokens"]) == 0)
            tot_b += blocked
            tot_s += len(rows)
            seed = os.path.basename(os.path.normpath(d)).split("_")[-2]
            per_run.append(f"{seed}:{blocked}/{len(rows)}")
        grand_b += tot_b
        grand_s += tot_s
        pct = 100 * tot_b / max(tot_s, 1)
        print(f"{s:22s} {tot_b:4d} / {tot_s:5d} solver calls  ({pct:4.1f}%)   "
              f"[{'  '.join(per_run)}]")
    print("-" * 72)
    print(f"{'ALL SUBJECTS':22s} {grand_b:4d} / {grand_s:5d}  "
          f"({100*grand_b/max(grand_s,1):.1f}%)")
    print("=" * 72)


if __name__ == "__main__":
    main()
