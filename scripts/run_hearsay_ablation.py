"""Hearsay ablation: rounds 2-3 of reflect_fdpo with vs. without the effect report.

Both arms replay the same round-1 prompt (taken from the main Hearsay run's registry),
so they differ only in what the optimizer is shown for rounds 2 and 3.

    python -m scripts.run_hearsay_ablation --solver gpt-4o-mini --repeats 5
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from fdpo.core.registry import PromptRegistry
from fdpo.data.md_prompt import to_markdown

ROOT = Path(__file__).resolve().parent.parent
SOURCES = {
    "gpt-4o-mini": ("4omini", "results/reflect_hearsay_gpt4omini_v1"),
    "gpt-4.1-mini": ("41mini", "results/reflect_hearsay_gpt41mini_v1"),
}
ARMS = (("report", []), ("noreport", ["--no-effect-report"]))


def extract_round1(solver: str) -> Path:
    """Write the main run's round-1 prompt to prompts/ablation/ (read-only on results)."""
    tag, group = SOURCES[solver]
    run_dir = sorted(p for p in (ROOT / group).iterdir() if (p / "metrics.json").exists())[-1]
    registry = PromptRegistry.load(run_dir / "registry.json")
    prompt = {name: registry.sections[name].versions[registry.version_as_of_round(name, 1)].text
              for name in registry.schema}
    out = ROOT / "prompts" / "ablation" / f"hearsay_round1_{tag}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_markdown(prompt, schema=registry.schema), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solver", choices=sorted(SOURCES), required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0,
                        help="index of the first repeat (keeps arm-order alternation across batches)")
    parser.add_argument("--budget-usd", type=float, default=2.0)
    parser.add_argument("--extract-only", action="store_true")
    args = parser.parse_args()

    round1 = extract_round1(args.solver)
    print(f"round-1 prompt: {round1.relative_to(ROOT)}", flush=True)
    if args.extract_only:
        return

    tag = SOURCES[args.solver][0]
    for repeat in range(args.offset, args.offset + args.repeats):
        # Alternate which arm goes first so API drift does not favor one arm.
        order = ARMS if repeat % 2 == 0 else ARMS[::-1]
        for arm, extra in order:
            command = [
                sys.executable, "-m", "scripts.run_experiment",
                "--method", "reflect_fdpo", "--dataset", "legalbench_hearsay",
                "--seed", "0", "--n-train", "50", "--n-test", "49",
                "--simple-max-rounds", "3", "--simple-val-frac", "0.5",
                "--tau", "1", "--skip-above-acc", "0.95",
                "--split-mode", "stratified",
                "--solver-temperature", "0.0", "--optimizer-temperature", "0.7",
                "--budget-usd", str(args.budget_usd),
                "--phase", f"ablation_hearsay_{tag}_{arm}",
                "--round1-prompt-file", str(round1), *extra,
            ]
            started = time.time()
            done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            print(f"repeat {repeat + 1} arm={arm} rc={done.returncode} "
                  f"{time.time() - started:.0f}s", flush=True)
            if done.returncode != 0:
                print(done.stderr[-600:], flush=True)


if __name__ == "__main__":
    main()
