"""Complete per-subject MMLU report (neutral baseline, all 6 subjects).

Reads results/mmluneutral_<subject>/ for all six subjects, prints per-seed and
per-subject-mean baseline vs final TEST, the macro-average across subjects, and
the old letter-only mixed-run per-subject numbers for context.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("results")

SUBJECTS = (
    "college_mathematics", "econometrics", "high_school_biology",
    "philosophy", "professional_law", "computer_security",
)

# Old LETTER-ONLY mixed 6-subject run (n=50), per-subject decomposition — context
# only (different setup). (baseline, final, delta) in %.
OLD_MIXED = {
    "college_mathematics": (75.3, 70.0),
    "econometrics": (62.0, 58.0),
    "high_school_biology": (82.0, 88.0),
    "philosophy": (74.0, 75.3),
    "professional_law": (52.7, 62.0),
    "computer_security": (92.0, 94.0),
}


def runs_for(subject: str) -> list[Path]:
    d = ROOT / f"mmluneutral_{subject}"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir()):
        if p.is_dir() and (p / "metrics.json").exists():
            m = json.loads((p / "metrics.json").read_text(encoding="utf-8"))
            if m.get("status") == "completed":
                out.append(p)
    return out


def main() -> None:
    print("=" * 90)
    print("COMPLETE MMLU PER-SUBJECT REPORT — neutral one-liner baseline, FDPO discovers CoT")
    print("  (50 train / 66 test per subject, tau 3, 3 seeds, gpt-4o-mini)")
    print("=" * 90)
    print(f"{'subject':22s} {'base':>6s} {'final':>6s} {'delta':>7s}   "
          f"{'per-seed deltas':22s} {'old(mixed)':>11s}")
    print("-" * 90)

    subj_means = []
    for subj in SUBJECTS:
        runs = runs_for(subj)
        if not runs:
            print(f"{subj:22s} (no completed runs)")
            continue
        bases, finals, shipped = [], [], []
        for rd in runs:
            m = json.loads((rd / "metrics.json").read_text(encoding="utf-8"))
            bases.append(m["seed_test"]["accuracy"] * 100)
            finals.append(m["final_test"]["accuracy"] * 100)
            shipped.append(m["optimization"].get("shipped_structured"))
        mb = sum(bases) / len(bases)
        mf = sum(finals) / len(finals)
        subj_means.append((subj, mb, mf))
        seed_deltas = " ".join(f"{f-b:+.1f}" for b, f in zip(bases, finals))
        ob, of = OLD_MIXED.get(subj, (0, 0))
        print(f"{subj:22s} {mb:6.1f} {mf:6.1f} {mf-mb:+7.1f}   "
              f"{seed_deltas:22s} {ob:.0f}->{of:.0f}")

    print("-" * 90)
    if subj_means:
        macro_b = sum(mb for _, mb, _ in subj_means) / len(subj_means)
        macro_f = sum(mf for _, _, mf in subj_means) / len(subj_means)
        print(f"{'MACRO-AVERAGE':22s} {macro_b:6.1f} {macro_f:6.1f} "
              f"{macro_f-macro_b:+7.1f}   (mean of {len(subj_means)} subjects)")
    print("=" * 90)


if __name__ == "__main__":
    main()
