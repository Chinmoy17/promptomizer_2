"""Compare content-filter blocks on professional_law between the earlier MIXED
run (results/smoke, where law got +9.3) and the per-subject run.

Key question: are the blocks BALANCED between the baseline (seed) and final test
evals? If yes, they cancel in the delta and don't bias the +9.3 / -1.0 results.

A blocked call -> empty completion -> pred not in A-E (extraction failure).
"""

from __future__ import annotations

import csv
import glob
import os


def law_fail_by_phase(run_dir: str):
    s_tot = s_fail = f_tot = f_fail = 0
    p = os.path.join(run_dir, "eval_log.csv")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if "professional_law" not in r["example_id"]:
                continue
            blocked = r["pred"].strip() not in ("A", "B", "C", "D", "E")
            if r["phase"] == "seed":
                s_tot += 1
                s_fail += blocked
            elif r["phase"] == "final":
                f_tot += 1
                f_fail += blocked
    return s_tot, s_fail, f_tot, f_fail


def ledger_blocks(run_dir: str):
    tot = blk = 0
    with open(os.path.join(run_dir, "ledger.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["role"] != "solver":
                continue
            tot += 1
            if int(r["prompt_tokens"]) == 0 and int(r["completion_tokens"]) == 0:
                blk += 1
    return blk, tot


def report(title: str, dirs: list[str]) -> None:
    print(title)
    for d in dirs:
        res = law_fail_by_phase(d)
        if not res or res[0] == 0:
            continue
        s_tot, s_fail, f_tot, f_fail = res
        blk, tot = ledger_blocks(d)
        name = os.path.basename(os.path.normpath(d))
        print(f"  {name[-15:]}: law baseline blocked={s_fail}/{s_tot}  "
              f"final blocked={f_fail}/{f_tot}   | ledger total blocks={blk}/{tot}")
    print()


report("MIXED run (results/smoke) — law decomposed, +9.3 came from here:",
       sorted(glob.glob("results/smoke/mmlu_simple_fdpo_gpt-4o-mini_s*/")))
report("PER-SUBJECT run (results/mmluneutral_professional_law) — -1.0:",
       sorted(glob.glob("results/mmluneutral_professional_law/*/")))
