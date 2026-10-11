"""Test the theory: CoT helps computational subjects, hurts recall subjects.

Two signals per subject:
  1. The CoT effect on MATCHED test items: baseline (terse/direct seed) vs final
     (optimizer's CoT prompt) — same 66 test items within each run.
  2. How much the optimizer lengthened the solver's reasoning (mean completion
     tokens: baseline mining = direct, vs round evals = CoT). Ties the accuracy
     change to actual reasoning length.
"""

from __future__ import annotations

import csv
import glob
import json
import os
import statistics

SUBJECTS = [
    "college_mathematics", "econometrics", "philosophy",
    "high_school_biology", "professional_law", "computer_security",
]

print("=" * 92)
print("CoT-vs-direct on matched test items, + reasoning length (baseline direct -> optimized CoT)")
print("=" * 92)
print(f"{'subject':22s} {'base%':>6s} {'final%':>7s} {'delta':>7s}   "
      f"{'base_tok':>9s} {'cot_tok':>8s} {'x_longer':>9s}")
print("-" * 92)

for s in SUBJECTS:
    bases, finals = [], []
    base_tok, cot_tok = [], []
    for d in sorted(glob.glob(f"results/mmluneutral_{s}/*/")):
        m = json.loads(open(os.path.join(d, "metrics.json"), encoding="utf-8").read())
        bases.append(m["seed_test"]["accuracy"] * 100)
        finals.append(m["final_test"]["accuracy"] * 100)
        with open(os.path.join(d, "ledger.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["role"] != "solver":
                    continue
                ct = int(r["completion_tokens"])
                if ct == 0:  # skip content-filter blocks
                    continue
                if r["purpose"] == "simple:baseline":
                    base_tok.append(ct)
                elif r["purpose"].startswith("simple:round") and not r["purpose"].endswith("-val"):
                    cot_tok.append(ct)
    mb = statistics.mean(bases)
    mf = statistics.mean(finals)
    bt = statistics.mean(base_tok) if base_tok else 0
    ctk = statistics.mean(cot_tok) if cot_tok else 0
    x = ctk / bt if bt else 0
    print(f"{s:22s} {mb:6.1f} {mf:7.1f} {mf-mb:+7.1f}   "
          f"{bt:9.1f} {ctk:8.1f} {x:8.1f}x")
print("=" * 92)
