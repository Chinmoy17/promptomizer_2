"""Summarize the earlier-protocol AIME runs and prompt re-evaluations described in the appendix.

Reads saved run folders under results/ and writes Paper_COLING/Artifacts/aime_additional_runs.json.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
OUT = ROOT / "Paper_COLING" / "Artifacts" / "aime_additional_runs.json"


def latest(group: str) -> Path:
    runs = sorted(p for p in (RES / group).iterdir() if (p / "metrics.json").exists())
    return runs[-1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def outcomes(path: Path, phase: str | None = None) -> dict[str, bool]:
    out = {}
    with (path / "eval_log.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if phase is None or row.get("phase") == phase:
                out[row["example_id"]] = row["correct"] == "True"
    return out


def transitions(before: dict[str, bool], after: dict[str, bool]) -> tuple[int, int]:
    ids = set(before) & set(after)
    return (sum(1 for i in ids if not before[i] and after[i]),
            sum(1 for i in ids if before[i] and not after[i]))


def pct(value: float) -> float:
    return round(100 * value, 1)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def optimization_run(group: str, label: str) -> dict:
    path = latest(group)
    config, metrics = load_json(path / "config.json"), load_json(path / "metrics.json")
    optimization = metrics["optimization"]
    committed = [r for r in optimization["rounds_log"] if r["status"] == "committed"]
    seed, final = outcomes(path, "seed"), outcomes(path, "final")
    recovered, regressed = transitions(seed, final)
    returned_edit = bool(optimization.get("shipped_structured"))
    val_base = optimization["baseline_val_acc"]
    return {
        "label": label,
        "solver": metrics["solver_model"],
        "metrics_path": (path / "metrics.json").relative_to(ROOT).as_posix(),
        "solver_max_tokens": config["solver_max_tokens"],
        "selection": optimization["selection"],
        "committed_rounds": len(committed),
        "returned_edited_prompt": returned_edit,
        "returned_round": committed[-1]["round"] if returned_edit else None,
        "val_base_pct": pct(val_base),
        "val_round_pct": [pct(r["val_acc_after"]) for r in committed],
        "val_returned_pct": pct(optimization["best_structured_val_acc"]) if returned_edit else pct(val_base),
        "n_test": len(seed),
        "seed_correct": sum(seed.values()),
        "returned_correct": sum(final.values()),
        "recovered": recovered,
        "regressed": regressed,
        "seed_prompt_equals_returned": (path / "prompt_baseline.md").read_text(encoding="utf-8")
        == (path / "prompt_current.md").read_text(encoding="utf-8"),
    }


def reevaluation(group: str, label: str, prompt_source: str, baseline_group: str | None = None) -> dict:
    path = latest(group)
    metrics = load_json(path / "metrics.json")
    result = outcomes(path)
    record = {
        "label": label,
        "solver": "gpt-4o-mini",
        "metrics_path": (path / "metrics.json").relative_to(ROOT).as_posix(),
        "prompt_source": prompt_source,
        "prompt_sha256": digest(ROOT / metrics["prompt_file"]),
        "solver_max_tokens": metrics["solver_max_tokens"],
        "n_test": metrics["n_evaluated"],
        "correct": metrics["n_correct"],
    }
    if baseline_group:
        recovered, regressed = transitions(outcomes(latest(baseline_group)), result)
        record["against"] = baseline_group
        record["recovered"], record["regressed"] = recovered, regressed
    return record


haiku = optimization_run("reflect_aime_haiku_v1", "Claude Haiku 4.5, earlier protocol")
gpt4o = optimization_run("reflect_aime_v1", "GPT-4o-mini, earlier protocol")
seed_path = latest("reflect_aime_v1") / "prompt_baseline.md"
transfer_source = latest("reflect_aime_gpt41mini_v3") / "prompt_current.md"
reevaluations = [
    reevaluation("aime_4o_shipped_rerun_2k", "GPT-4o-mini seed prompt, re-evaluated", "seed"),
    reevaluation("aime_4o_shipped_rerun_16k", "GPT-4o-mini seed prompt, re-evaluated", "seed"),
    reevaluation("aime_gpt41r1_prompt_on_4omini", "GPT-4o-mini with the GPT-4.1 Mini round-1 prompt",
                 "gpt-4.1-mini returned prompt (round 1)", baseline_group="aime_4o_shipped_rerun_16k"),
]
assert reevaluations[0]["prompt_sha256"] == reevaluations[1]["prompt_sha256"] == digest(seed_path)
assert reevaluations[2]["prompt_sha256"] == digest(transfer_source) != digest(seed_path)
assert gpt4o["seed_prompt_equals_returned"] and not haiku["seed_prompt_equals_returned"]

OUT.write_text(json.dumps({
    "source": "Saved AIME runs and prompt re-evaluations on the 30 test problems; none enters the matched analyses",
    "n_test": gpt4o["n_test"],
    "optimization_runs": [haiku, gpt4o],
    "reevaluations": reevaluations,
}, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT)}")
for run in (haiku, gpt4o):
    print(run["label"], "| val", run["val_base_pct"], "->", run["val_returned_pct"], run["val_round_pct"],
          "| test", run["seed_correct"], "->", run["returned_correct"],
          f"(rec {run['recovered']}, reg {run['regressed']})", "| edited:", run["returned_edited_prompt"])
for item in reevaluations:
    print(item["label"], item["solver_max_tokens"], item["correct"], item.get("recovered"), item.get("regressed"))
