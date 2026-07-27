"""Break down professional_law content-filter blocks by eval phase (purpose).

If the CoT/final eval trips the filter more than the terse baseline eval, the
law delta is partly a content-filter artifact rather than a model effect.
"""

from __future__ import annotations

import csv
import glob
import os
from collections import Counter

blocked = Counter()
total = Counter()
for d in sorted(glob.glob("results/mmluneutral_professional_law/*/")):
    with open(os.path.join(d, "ledger.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["role"] != "solver":
                continue
            p = r["purpose"]
            total[p] += 1
            if int(r["prompt_tokens"]) == 0 and int(r["completion_tokens"]) == 0:
                blocked[p] += 1

print("professional_law content-filter blocks by purpose (3 seeds pooled):")
print(f"{'purpose':26s} {'blocked':>8s} {'total':>7s} {'rate':>7s}")
for p in sorted(total):
    print(f"{p:26s} {blocked[p]:8d} {total[p]:7d} {100*blocked[p]/max(total[p],1):6.1f}%")
