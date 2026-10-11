"""Effect-report ablation: rounds 2-3 of reflect_fdpo with vs. without the report.

Both arms replay the same round-1 prompt (taken from the benchmark's main-run registry),
so they differ only in what the optimizer is shown for rounds 2 and 3.

    python -m scripts.run_ablation --benchmark hearsay --solver gpt-4o-mini --repeats 5
    python -m scripts.run_ablation --benchmark mmlu --solver gpt-4o-mini --repeats 1
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
TAGS = {"gpt-4o-mini": "4omini", "gpt-4.1-mini": "41mini"}
SUBJECTS = ("college_mathematics", "computer_security", "econometrics",
            "high_school_biology", "philosophy", "professional_law")
HEARSAY_GROUPS = {"gpt-4o-mini": "reflect_hearsay_gpt4omini_v1",
                  "gpt-4.1-mini": "reflect_hearsay_gpt41mini_v1"}
ARMS = (("report", []), ("noreport", ["--no-effect-report"]))


def units(benchmark: str) -> tuple[str | None, ...]:
    return (None,) if benchmark == "hearsay" else SUBJECTS


def main_group(benchmark: str, solver: str, unit: str | None) -> str:
    if benchmark == "hearsay":
        return HEARSAY_GROUPS[solver]
    prefix = "mmlu_reflect_" if solver == "gpt-4o-mini" else "mmlu_reflect_gpt41mini_"
    return prefix + unit


def benchmark_args(benchmark: str, unit: str | None) -> list[str]:
    if benchmark == "hearsay":
        return ["--dataset", "legalbench_hearsay", "--n-test", "49", "--split-mode", "stratified"]
    return ["--dataset", "mmlu", "--subjects", unit, "--n-test", "66", "--split-mode", "balanced"]


def extract_round1(benchmark: str, solver: str, unit: str | None) -> Path:
    """Write the main run's round-1 prompt to prompts/ablation/ (read-only on results)."""
    group = ROOT / "results" / main_group(benchmark, solver, unit)
    run_dir = sorted(p for p in group.iterdir() if (p / "metrics.json").exists())[-1]
    registry = PromptRegistry.load(run_dir / "registry.json")
    prompt = {name: registry.sections[name].versions[registry.version_as_of_round(name, 1)].text
              for name in registry.schema}
    stem = f"{benchmark}_round1_{TAGS[solver]}" + (f"_{unit}" if unit else "")
    out = ROOT / "prompts" / "ablation" / f"{stem}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(to_markdown(prompt, schema=registry.schema), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", choices=("hearsay", "mmlu"), default="hearsay")
    parser.add_argument("--solver", choices=sorted(TAGS), required=True)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--offset", type=int, default=0,
                        help="index of the first repeat (keeps arm-order alternation across batches)")
    parser.add_argument("--budget-usd", type=float, default=2.0)
    parser.add_argument("--extract-only", action="store_true")
    args = parser.parse_args()

    round1 = {unit: extract_round1(args.benchmark, args.solver, unit)
              for unit in units(args.benchmark)}
    for path in round1.values():
        print(f"round-1 prompt: {path.relative_to(ROOT)}", flush=True)
    if args.extract_only:
        return

    tag = TAGS[args.solver]
    for repeat in range(args.offset, args.offset + args.repeats):
        for index, unit in enumerate(units(args.benchmark)):
            # Alternate which arm goes first so API drift does not favor one arm.
            order = ARMS if (repeat + index) % 2 == 0 else ARMS[::-1]
            for arm, extra in order:
                command = [
                    sys.executable, "-m", "scripts.run_experiment",
                    "--method", "reflect_fdpo", "--seed", "0", "--n-train", "50",
                    *benchmark_args(args.benchmark, unit),
                    "--simple-max-rounds", "3", "--simple-val-frac", "0.5",
                    "--tau", "1", "--skip-above-acc", "0.95",
                    "--solver-temperature", "0.0", "--optimizer-temperature", "0.7",
                    "--budget-usd", str(args.budget_usd),
                    "--phase", f"ablation_{args.benchmark}_{tag}_{arm}",
                    "--round1-prompt-file", str(round1[unit]), *extra,
                ]
                started = time.time()
                done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
                print(f"repeat {repeat + 1} {unit or args.benchmark} arm={arm} "
                      f"rc={done.returncode} {time.time() - started:.0f}s", flush=True)
                if done.returncode != 0:
                    print(done.stderr[-600:], flush=True)


if __name__ == "__main__":
    main()
