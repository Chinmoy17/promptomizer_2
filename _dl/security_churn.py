"""Why did computer_security regress? Per-item churn (baseline vs final).

At a 92% baseline there are ~61/66 already-correct items to BREAK and only ~5
wrong items to FIX. If added reasoning makes the model second-guess, it breaks
more than it fixes. This quantifies recovered vs regressed per seed.
"""

from __future__ import annotations

import csv
import glob
import os

for d in sorted(glob.glob("results/mmluneutral_computer_security/*/")):
    base, final = {}, {}
    with open(os.path.join(d, "eval_log.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            ok = r["correct"].strip().lower() == "true"
            if r["phase"] == "seed":
                base[r["example_id"]] = ok
            elif r["phase"] == "final":
                final[r["example_id"]] = ok
    ids = [k for k in base if k in final]
    recovered = [k for k in ids if not base[k] and final[k]]      # wrong -> right
    regressed = [k for k in ids if base[k] and not final[k]]      # right -> wrong
    still_right = sum(1 for k in ids if base[k] and final[k])
    still_wrong = sum(1 for k in ids if not base[k] and not final[k])
    seed = os.path.basename(os.path.normpath(d)).split("_")[-2]
    print(f"{seed}: baseline_right={sum(base[k] for k in ids)}/{len(ids)}  "
          f"recovered(wrong->right)={len(recovered)}  "
          f"regressed(right->wrong)={len(regressed)}  "
          f"still_right={still_right}  still_wrong={still_wrong}  "
          f"net={len(recovered)-len(regressed):+d}")
