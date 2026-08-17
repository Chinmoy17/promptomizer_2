"""Analyze the per-subject CoT pilot (math + biology) and compare to the old
letter-only balanced run.

Reads results/mmlucot_<subject>/ runs, prints per-seed baseline vs final TEST,
the validation-gate decision, and extraction failures. The old letter-only
numbers are printed inline for contrast.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("results")

# Old letter-only balanced run (per-subject mean, from _dl/analyze_mmlu_runs.py):
OLD = {
    "college_mathematics": (75.3, 70.0, -5.3),
    "high_school_biology": (82.0, 88.0, +6.0),
}


def runs_for(phase: str) -> list[Path]:
    d = ROOT / phase
    if not d.exists():
        return []
    return sorted(
        (p for p in d.iterdir() if p.is_dir() and (p / "metrics.json").exists()),
        key=lambda p: p.name,
    )


def main() -> None:
    print("=" * 84)
    print("PER-SUBJECT CoT PILOT (pinned CoT output, tau 3, 50 train / 66 test)")
    print("=" * 84)
    for subject in ("college_mathematics", "high_school_biology"):
        phase = f"mmluneutral_{subject}"
        runs = runs_for(phase)
        print(f"\n### {subject}  ({len(runs)} seeds)")
        ob, of, od = OLD[subject]
        print(f"  OLD (letter-only): {ob:.1f}% -> {of:.1f}%  ({od:+.1f}pp)")
        base_list, final_list = [], []
        for rd in runs:
            m = json.loads((rd / "metrics.json").read_text(encoding="utf-8"))
            opt = m["optimization"]
            b = m["seed_test"]["accuracy"] * 100
            f = m["final_test"]["accuracy"] * 100
            base_list.append(b)
            final_list.append(f)
            xf = (m["seed_test"].get("extraction_failures", 0),
                  m["final_test"].get("extraction_failures", 0))
            shipped = opt.get("shipped_structured")
            bv = opt.get("baseline_val_acc", 0) * 100
            sv = (opt.get("best_structured_val_acc") or 0) * 100
            print(f"  seed {m['seed']}: {b:.1f}% -> {f:.1f}%  ({f-b:+.1f}pp)  "
                  f"[shipped={shipped}, val {bv:.1f}->{sv:.1f}, xfail={xf}]")
        if base_list:
            mb = sum(base_list) / len(base_list)
            mf = sum(final_list) / len(final_list)
            print(f"  NEW (CoT) MEAN:  {mb:.1f}% -> {mf:.1f}%  ({mf-mb:+.1f}pp)")
            print(f"  >> vs old baseline: CoT baseline {mb-ob:+.1f}pp; "
                  f"final {mf-of:+.1f}pp")
    print("\n" + "=" * 84)


if __name__ == "__main__":
    main()
