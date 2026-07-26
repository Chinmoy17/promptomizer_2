"""Recovered-vs-regressed churn per subject for the MMLU balanced runs.

For each subject (pooled across the 3 seeds): how many test items the shipped
prompt RECOVERED (baseline wrong -> final right) vs REGRESSED (baseline right ->
final wrong). Net = recovered - regressed. This exposes the churn hidden behind
the small per-subject net deltas.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path("results/smoke")
_ID = re.compile(r"^mmlu_(.+)_(?:test|validation|dev)_\d+$")


def newest_completed(seed: int) -> Path | None:
    prefix = f"mmlu_simple_fdpo_gpt-4o-mini_s{seed}_"
    cands = []
    for p in ROOT.iterdir():
        if p.is_dir() and p.name.startswith(prefix) and (p / "metrics.json").exists():
            try:
                if json.loads((p / "metrics.json").read_text(encoding="utf-8")).get("status") == "completed":
                    cands.append((p.stat().st_mtime, p))
            except Exception:
                pass
    return max(cands, key=lambda t: t[0])[1] if cands else None


def load(run_dir: Path):
    base, final = {}, {}
    with (run_dir / "eval_log.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            eid = row["example_id"]
            ok = row["correct"].strip().lower() == "true"
            if row["phase"] == "seed":
                base[eid] = ok
            elif row["phase"] == "final":
                final[eid] = ok
    return base, final


def subj(eid: str) -> str | None:
    m = _ID.match(eid)
    return m.group(1) if m else None


def main() -> None:
    # subject -> [recovered, regressed, still_wrong, still_right]
    agg: dict[str, list[int]] = {}
    reg_examples: dict[str, list[str]] = {}
    for s in (0, 1, 2):
        rd = newest_completed(s)
        if rd is None:
            continue
        base, final = load(rd)
        for eid, b in base.items():
            if eid not in final:
                continue
            fi = final[eid]
            k = subj(eid)
            if k is None:
                continue
            a = agg.setdefault(k, [0, 0, 0, 0])
            if not b and fi:
                a[0] += 1
            elif b and not fi:
                a[1] += 1
                reg_examples.setdefault(k, []).append(f"s{s}:{eid}")
            elif not b and not fi:
                a[2] += 1
            else:
                a[3] += 1

    print("=" * 78)
    print("MMLU CHURN per subject (pooled across 3 seeds, 150 test items each)")
    print("=" * 78)
    print(f"{'subject':22s} {'recov':>6s} {'regr':>6s} {'net':>5s}  "
          f"{'stillW':>7s} {'stillR':>7s}")
    tot = [0, 0, 0, 0]
    for k in sorted(agg):
        r, rg, sw, sr = agg[k]
        for i, v in enumerate((r, rg, sw, sr)):
            tot[i] += v
        print(f"{k:22s} {r:6d} {rg:6d} {r-rg:+5d}  {sw:7d} {sr:7d}")
    print("-" * 78)
    print(f"{'TOTAL':22s} {tot[0]:6d} {tot[1]:6d} {tot[0]-tot[1]:+5d}  "
          f"{tot[2]:7d} {tot[3]:7d}")
    print("=" * 78)
    print("\nRegressed items (baseline RIGHT -> final WRONG), worst subjects:")
    for k in ("college_mathematics", "econometrics"):
        ex = reg_examples.get(k, [])
        print(f"  {k} ({len(ex)} regressions): {ex}")


if __name__ == "__main__":
    main()
