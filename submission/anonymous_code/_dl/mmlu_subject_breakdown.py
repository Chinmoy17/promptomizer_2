"""Ad-hoc: per-subject breakdown for one MMLU simple_fdpo run.

eval_log.csv columns: phase, example_id, correct, pred, gold
example_id format: mmlu_<subject>_test_<n> or mmlu_<subject>_train_<n>
"""
import csv
import re
import sys
from collections import defaultdict

run = sys.argv[1]
rows = list(csv.DictReader(open(f"{run}/eval_log.csv", encoding="utf-8")))

phases = sorted({r["phase"] for r in rows})
print(f"phases in eval_log: {phases}")

def bucket(ex_id):
    m = re.match(r"mmlu_(.+?)_(train|test|validation|dev)_\d+", ex_id)
    return m.group(1) if m else "?"

by = defaultdict(lambda: defaultdict(lambda: {"correct": 0, "n": 0}))
for r in rows:
    subj = bucket(r["example_id"])
    b = by[r["phase"]][subj]
    b["n"] += 1
    if r["correct"] == "True":
        b["correct"] += 1

def show(title, phase_a, phase_b):
    if phase_a not in by or phase_b not in by:
        print(f"\n(skip {title}: need phases {phase_a} and {phase_b})")
        return
    print(f"\n=== {title}: {phase_a} -> {phase_b} ===")
    print(f'{"subject":<25} {"n":>4} {"base":>7} {"final":>7} {"delta":>8}')
    print("-" * 55)
    subjects = sorted(by[phase_a].keys(), key=lambda s: -by[phase_a][s]["n"])
    for subj in subjects:
        a = by[phase_a][subj]
        b = by[phase_b].get(subj, {"correct": 0, "n": 0})
        if not a["n"] or not b["n"]:
            continue
        pa, pb = a["correct"] / a["n"], b["correct"] / b["n"]
        print(f'{subj:<25} {a["n"]:>4} {pa:>7.1%} {pb:>7.1%} {pb-pa:>+8.1%}')

show("TEST",  "seed",     "final")
show("TRAIN", "baseline", "final_train")
