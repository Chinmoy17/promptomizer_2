"""Analyze the MMLU balanced validation-gated runs (3 seeds).

For each seed: baseline vs final TEST accuracy (macro == micro because the test
set is balanced 50/subject), the validation-gate decision, and a per-subject
decomposition read from eval_log.csv (phase 'seed' vs 'final'). No hand-typed
numbers.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

ROOT = Path("results/smoke")
# Balanced test set mixes original _test_N, _validation_N and _dev_N ids (dev +
# val + test were pooled and re-carved), so match any suffix and keep the subject.
_ID = re.compile(r"^mmlu_(.+)_(?:test|validation|dev)_\d+$")


def newest_completed(seed: int) -> Path | None:
    prefix = f"mmlu_simple_fdpo_gpt-4o-mini_s{seed}_"
    cands = []
    for p in ROOT.iterdir():
        if not (p.is_dir() and p.name.startswith(prefix)):
            continue
        mj = p / "metrics.json"
        if not mj.exists():
            continue
        try:
            m = json.loads(mj.read_text(encoding="utf-8"))
        except Exception:
            continue
        if m.get("status") == "completed":
            cands.append((p.stat().st_mtime, p))
    if not cands:
        return None
    return max(cands, key=lambda t: t[0])[1]


def subject_of(example_id: str) -> str | None:
    m = _ID.match(example_id)
    return m.group(1) if m else None


def per_subject(run_dir: Path) -> dict[str, dict[str, tuple[int, int]]]:
    """Return {subject: {'seed': (correct,total), 'final': (correct,total)}}."""
    out: dict[str, dict[str, list[int]]] = {}
    with (run_dir / "eval_log.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            phase = row["phase"]
            if phase not in ("seed", "final"):
                continue
            subj = subject_of(row["example_id"])
            if subj is None:
                continue
            d = out.setdefault(subj, {"seed": [0, 0], "final": [0, 0]})
            d[phase][1] += 1
            if row["correct"].strip().lower() == "true":
                d[phase][0] += 1
    return {s: {k: (v[0], v[1]) for k, v in d.items()} for s, d in out.items()}


def pct(c: int, t: int) -> float:
    return 100.0 * c / t if t else 0.0


def main() -> None:
    seeds = {}
    for s in (0, 1, 2):
        rd = newest_completed(s)
        if rd is not None:
            seeds[s] = rd

    print("=" * 82)
    print("MMLU BALANCED (50/50 per subject x6) — validation-gated one-liner FDPO")
    print("=" * 82)

    test_deltas = []
    # subject -> list of (base_pct, final_pct) across seeds
    subj_acc: dict[str, list[tuple[float, float]]] = {}
    for s in sorted(seeds):
        rd = seeds[s]
        m = json.loads((rd / "metrics.json").read_text(encoding="utf-8"))
        opt = m["optimization"]
        base = m["seed_test"]["accuracy"] * 100
        final = m["final_test"]["accuracy"] * 100
        test_deltas.append(final - base)
        print(f"\n--- SEED {s}  ({rd.name}) ---")
        print(f"  TEST (300, balanced): baseline {base:.1f}%  ->  final {final:.1f}%  "
              f"delta {final - base:+.1f}pp")
        print(f"  gate: shipped_structured={opt['shipped_structured']}  "
              f"baseline_val={opt['baseline_val_acc']*100:.1f}%  "
              f"best_structured_val={opt['best_structured_val_acc']*100:.1f}%  "
              f"(margin {opt['accept_margin']})")
        note = ("  NOTE: best structured val < baseline val -> shipped ONLY by leniency"
                if opt["best_structured_val_acc"] < opt["baseline_val_acc"] else "")
        if note:
            print(note)
        ps = per_subject(rd)
        print("  per-subject (baseline -> final):")
        for subj in sorted(ps):
            b = ps[subj]["seed"]
            fi = ps[subj]["final"]
            bp, fp = pct(*b), pct(*fi)
            subj_acc.setdefault(subj, []).append((bp, fp))
            print(f"    {subj:22s} {bp:5.1f}% -> {fp:5.1f}%  ({fp - bp:+.1f}pp)  "
                  f"[n={fi[1]}]")

    print("\n" + "=" * 82)
    print("PER-SUBJECT MEAN across seeds (baseline -> final, mean delta):")
    for subj in sorted(subj_acc):
        rows = subj_acc[subj]
        mb = sum(r[0] for r in rows) / len(rows)
        mf = sum(r[1] for r in rows) / len(rows)
        print(f"  {subj:22s} {mb:5.1f}% -> {mf:5.1f}%  ({mf - mb:+.1f}pp)")
    if test_deltas:
        mean = sum(test_deltas) / len(test_deltas)
        print(f"\nAGGREGATE TEST delta (macro): mean {mean:+.1f}pp   "
              f"min {min(test_deltas):+.1f}pp   max {max(test_deltas):+.1f}pp   "
              f"(n={len(test_deltas)} seeds)")
    print("=" * 82)


if __name__ == "__main__":
    main()
