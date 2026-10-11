"""Extract grounded numbers from the 3 validation-gated hearsay runs (today).

Prints, per seed: baseline vs final TEST accuracy, the accept-gate decision,
and the full per-round mining/validation trajectory. Used to ground the
report — no hand-typed numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path("results/smoke")


def newest_runs(prefix: str, n: int) -> list[Path]:
    runs = sorted(
        (p for p in ROOT.iterdir()
         if p.is_dir() and p.name.startswith(prefix) and "mock" not in p.name),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return runs[:n]


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def main() -> None:
    prefix = "legalbench_hearsay_simple_fdpo_gpt-4o-mini_s"
    # Pick the 3 newest (one per seed) from today.
    runs = newest_runs(prefix, 3)
    by_seed: dict[int, Path] = {}
    for r in runs:
        m = json.loads((r / "metrics.json").read_text(encoding="utf-8"))
        by_seed[m["seed"]] = r

    print("=" * 78)
    print("VALIDATION-GATED LENIENT MECHANISM — hearsay one-liner, 3 seeds")
    print("=" * 78)

    deltas = []
    for seed in sorted(by_seed):
        m = json.loads((by_seed[seed] / "metrics.json").read_text(encoding="utf-8"))
        opt = m["optimization"]
        base = m["seed_test"]["accuracy"]
        final = m["final_test"]["accuracy"]
        delta = final - base
        deltas.append(delta)
        vs = opt["val_split"]
        print(f"\n--- SEED {seed}  ({by_seed[seed].name}) ---")
        print(f"  TEST:  baseline {pct(base)}  ->  final {pct(final)}   "
              f"delta {100*delta:+.1f}pp   macro_f1 {m['final_test']['macro_f1']:.3f}")
        print(f"  split: mining={vs['n_mining']}  validation={vs['n_validation']}  "
              f"(val_frac={vs['val_frac']})")
        print(f"  gate:  shipped_structured={opt['shipped_structured']}  "
              f"baseline_val={pct(opt['baseline_val_acc'])}  "
              f"best_val={pct(opt['best_structured_val_acc']) if opt['best_structured_val_acc'] is not None else 'n/a'}  "
              f"accept_margin={opt['accept_margin']}")
        print("  rounds:")
        for rd in opt["rounds_log"]:
            st = rd["status"]
            if st.startswith("committed"):
                print(f"    r{rd['round']}: {st:16s} "
                      f"mining_acc={pct(rd['train_acc_after'])}  "
                      f"val_acc={pct(rd['val_acc_after'])}  "
                      f"(|F| {rd['n_failures_before']}->{rd['n_failures_after']})")
            else:
                print(f"    r{rd['round']}: {st}")

    print("\n" + "=" * 78)
    mean = sum(deltas) / len(deltas)
    spread = max(deltas) - min(deltas)
    print(f"TEST delta: mean {100*mean:+.1f}pp   "
          f"min {100*min(deltas):+.1f}pp   max {100*max(deltas):+.1f}pp   "
          f"spread {100*spread:.1f}pp")
    print("=" * 78)


if __name__ == "__main__":
    main()
