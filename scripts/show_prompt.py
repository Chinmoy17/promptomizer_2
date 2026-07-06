"""Print a fully-rendered prompt -- exactly as it's sent to the solver -- for
inspection, no API calls involved.

Usage:
    uv run python -m scripts.show_prompt --dataset legalbench_hearsay
        # the SEED prompt (version 0 of every section)

    uv run python -m scripts.show_prompt --registry results/<phase>/<run_id>/registry.json
        # the ACTIVE (final, or current-mid-run) prompt from a completed/in-progress run

    uv run python -m scripts.show_prompt --registry <path> --best
        # that run's whole-run BEST-KNOWN snapshot instead of its current active prompt
        # (differs from --active only if the run stagnated and never restored)

    uv run python -m scripts.show_prompt --registry <path> --history
        # every version of every section, in order, with gate results
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fdpo.core.prompt import SCHEMA_5, SCHEMA_MONOLITHIC, render_system
from fdpo.prompts.seeds import seed_sections


def _load_registry(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dataset", choices=("gsm8k", "arc", "mmlu", "legalbench_hearsay"),
                   help="show the SEED prompt for this dataset")
    p.add_argument("--registry", type=Path,
                   help="path to a run's registry.json; shows that run's prompt instead of a seed")
    p.add_argument("--monolithic", action="store_true",
                   help="use the 1-section schema instead of the 5-section one (--dataset mode only)")
    p.add_argument("--best", action="store_true",
                   help="with --registry: show the whole-run best-known snapshot, not the current active prompt")
    p.add_argument("--history", action="store_true",
                   help="with --registry: print every version of every section with its gate result")
    args = p.parse_args(argv)

    if not args.dataset and not args.registry:
        p.error("provide --dataset (seed prompt) or --registry (a run's prompt)")

    if args.registry:
        reg = _load_registry(args.registry)
        if args.history:
            for name, s in reg["sections"].items():
                print(f"\n{'=' * 60}\n{name}\n{'=' * 60}")
                for v in s["versions"]:
                    marker = " <- ACTIVE" if v["version"] == s["active_version"] else ""
                    print(f"\n--- v{v['version']} (round {v['created_round']}, {v['status']}){marker} ---")
                    print(v["text"])
                    if v["gate"]:
                        g = v["gate"]
                        print(f"    gate: acc {g['acc_old']:.3f} -> {g['acc_new']:.3f}, "
                             f"broke {g['broke']}, recovered {g['recovered_failures']}/{g['n_failures']}")
            return 0

        if args.best:
            sections = {name: s["versions"][reg["run_best_versions"][name]]["text"]
                       for name, s in reg["sections"].items()}
            label = f"BEST-KNOWN snapshot (validation acc {reg['run_best_acc']:.3f})"
        else:
            sections = {name: s["versions"][s["active_version"]]["text"]
                       for name, s in reg["sections"].items()}
            label = "ACTIVE prompt (current end state of this run)"
        print(f"=== {label} ===\n")
        print(render_system(sections))
        return 0

    schema = SCHEMA_MONOLITHIC if args.monolithic else SCHEMA_5
    sections = seed_sections(args.dataset, schema)
    print(f"=== SEED prompt for {args.dataset} (as sent to the solver) ===\n")
    print(render_system(sections))
    return 0


if __name__ == "__main__":
    sys.exit(main())
