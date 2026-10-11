"""Produce matched tuning/test and resource records from the paper's saved runs.

The reported-results manifest controls exclusions. No accuracy overrides are
used; optimizer and whole-run token totals are checked against per-call ledgers.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"

# (label, results subdir) ; latest timestamped run under the subdir is used.
RUNS = [
    ("AIME / 4o-mini", "reflect_aime_v1"),
    ("AIME / 4.1-mini", "reflect_aime_gpt41mini_v3"),
    ("PUPA / 4o-mini", "pupa_pilot_v1"),
    ("PUPA / 4.1-mini", "pupa_pilot_gpt41mini_v2"),
    ("IFBench / 4o-mini", "reflect_ifbench_v1"),
    ("IFBench / 4.1-mini", "reflect_ifbench_gpt41mini_v2"),
    ("Hearsay / 4o-mini", "reflect_hearsay_gpt4omini_v1"),
    ("Hearsay / 4.1-mini", "reflect_hearsay_gpt41mini_v1"),
]
SUBJECTS = ["college_mathematics", "computer_security", "econometrics",
            "high_school_biology", "philosophy", "professional_law"]
for s in SUBJECTS:
    RUNS.append((f"MMLU-{s} / 4o-mini", f"mmlu_reflect_{s}"))
for s in SUBJECTS:
    RUNS.append((f"MMLU-{s} / 4.1-mini", f"mmlu_reflect_gpt41mini_{s}"))

ARTIFACTS = ROOT / "Paper_COLING" / "Artifacts"
manifest = json.loads((ARTIFACTS / "reported_results.json").read_text(encoding="utf-8"))
excluded = tuple(manifest["validation_excluded_prefixes"])
rows = []
resources = []
for label, subdir in RUNS:
    if label.startswith(excluded):
        continue
    paths = sorted(path for path in (RES / subdir).iterdir()
                   if (path / "metrics.json").exists())
    run_path = paths[-1]
    metrics = json.loads((run_path / "metrics.json").read_text(encoding="utf-8"))
    optimization = metrics["optimization"]
    returned_edit = bool(optimization.get("shipped_structured"))
    val_base = optimization.get("baseline_val_acc")
    val_returned = optimization.get("best_structured_val_acc") if returned_edit else val_base
    test_base = metrics["seed_test"]["accuracy"]
    test_final = metrics["final_test"]["accuracy"]
    rows.append({
        "run": label,
        "run_id": metrics["run_id"],
        "metrics_path": (run_path / "metrics.json").relative_to(ROOT).as_posix(),
        "shipped": returned_edit,
        "selection": optimization.get("selection"),
        "shipped_round": optimization.get("shipped_round"),
        "val_base": val_base,
        "val_best": val_returned,
        "val_measured": not optimization.get("skipped_high_baseline", False),
        "val_gain_pp": None if val_base is None else 100 * (val_returned - val_base),
        "test_base": test_base,
        "test_final": test_final,
        "test_delta_pp": 100 * (test_final - test_base),
        "rounds_run": optimization.get("rounds_run"),
        "optimizer_calls": optimization.get("optimizer_calls"),
        "rounds": [{
            "round": record["round"],
            "mining_accuracy": record["train_acc_after"],
            "validation_accuracy": record["val_acc_after"],
            "mining_recovered": len(record.get("recovered_this_round", [])),
            "mining_regressed": len(record.get("regressed_this_round", [])),
            "validation_recovered": record.get("val_recovered_this_round", 0),
            "validation_regressed": record.get("val_regressed_this_round", 0),
            "sections_changed": record["sections_changed"],
        } for record in optimization.get("rounds_log", []) if record["status"] == "committed"],
    })
    with (run_path / "ledger.csv").open(encoding="utf-8", newline="") as handle:
        ledger = list(csv.DictReader(handle))
    role_totals = metrics["cost"]["by_role"]
    for role, totals in role_totals.items():
        entries = [entry for entry in ledger if entry["role"] == role]
        observed = (len(entries), sum(int(entry["prompt_tokens"]) for entry in entries),
                    sum(int(entry["completion_tokens"]) for entry in entries))
        expected = (totals["calls"], totals["prompt_tokens"], totals["completion_tokens"])
        if observed != expected:
            raise ValueError(f"Token ledger mismatch: {label}, {role}")
        ledger_cost = sum(float(entry["cost_usd"]) for entry in entries)
        if not math.isclose(ledger_cost, totals["cost_usd"], rel_tol=0, abs_tol=1e-6):
            raise ValueError(f"Cost ledger mismatch: {label}, {role}")
    if {entry["role"] for entry in ledger} != set(role_totals):
        raise ValueError(f"Unaccounted ledger role: {label}")
    if not math.isclose(sum(float(entry["cost_usd"]) for entry in ledger),
                        metrics["cost"]["total_cost_usd"], rel_tol=0, abs_tol=1e-6):
        raise ValueError(f"Whole-run cost mismatch: {label}")
    optimizer = role_totals.get("optimizer", {})
    resources.append({
        "run": label,
        "run_id": metrics["run_id"],
        "metrics_path": (run_path / "metrics.json").relative_to(ROOT).as_posix(),
        "optimizer_calls": optimizer.get("calls", 0),
        "optimizer_input_tokens": optimizer.get("prompt_tokens", 0),
        "optimizer_output_tokens": optimizer.get("completion_tokens", 0),
        "total_tokens": sum(totals["prompt_tokens"] + totals["completion_tokens"]
                            for totals in role_totals.values()),
        "total_cost_usd": metrics["cost"]["total_cost_usd"],
        "by_role": role_totals,
        "model_identifiers": sorted({entry["model"] for entry in ledger}),
    })

print("Matched records: seed-to-returned accuracy; PUPA uses thresholded accuracy.")
for row in rows:
    print(f"{row['run']:38s} edited={str(row['shipped']):5s} "
          f"val={row['val_gain_pp']:+.1f}pp test={row['test_delta_pp']:+.1f}pp")

core = [row for row in rows if not row["run"].startswith("MMLU")]
mmlu = [row for row in rows if row["run"].startswith("MMLU")]


def summarize(name: str, rs: list[dict]) -> None:
    shipped = [r for r in rs if r["shipped"] and r["val_gain_pp"] is not None]
    vgain = [r for r in shipped if r["val_gain_pp"] > 0]
    gap = [r for r in vgain if r["test_delta_pp"] <= 0]
    both = [r for r in vgain if r["test_delta_pp"] > 0]
    mean_v = sum(r["val_gain_pp"] for r in shipped) / max(len(shipped), 1)
    mean_t = sum(r["test_delta_pp"] for r in shipped) / max(len(shipped), 1)
    print(f"\n[{name}] n={len(rs)} shipped={len(shipped)} "
          f"val_gain>0: {len(vgain)}  of which test<=0: {len(gap)}  test>0: {len(both)}  "
          f"mean dVal={mean_v:+.1f}pp  mean dTest={mean_t:+.1f}pp")


summarize("matched non-MMLU", core)
summarize("MMLU 12 subject-runs", mmlu)
summarize("all matched", rows)
summarize("selection=last_round (older rule)", [r for r in rows if r["selection"] == "last_round"])
summarize("selection=best_of_rounds", [r for r in rows if r["selection"] == "best_of_rounds"])
summarize("non-MMLU, last_round", [r for r in core if r["selection"] == "last_round"])
summarize("non-MMLU, best_of_rounds", [r for r in core if r["selection"] == "best_of_rounds"])
core_rounds = [record for row in core for record in row["rounds"]]
print(f"\nMatched non-MMLU committed rounds: {len(core_rounds)}; "
    f"mining regressions exceed recoveries: "
    f"{sum(record['mining_regressed'] > record['mining_recovered'] for record in core_rounds)}; "
    f"validation regressions exceed recoveries: "
    f"{sum(record['validation_regressed'] > record['validation_recovered'] for record in core_rounds)}")
print("AIME GPT-4.1 Mini rounds:", rows[0]["rounds"])

(ARTIFACTS / "val_test_gap.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
aggregates = []
for benchmark, solver in [(row["benchmark"], row["solver"]) for row in manifest["results"]
                         if row["provenance"] == "saved"]:
    suffix = " / 4o-mini" if solver == "GPT-4o-mini" else " / 4.1-mini"
    matching = [record for record in resources if record["run"].endswith(suffix)
                and (record["run"].startswith("MMLU-") if benchmark == "MMLU"
                     else record["run"] == benchmark + suffix)]
    if not matching:
        raise ValueError(f"No resource records: {benchmark}, {solver}")
    aggregates.append({
        "benchmark": benchmark,
        "solver": solver,
        "runs": len(matching),
        **{key: sum(record[key] for record in matching) for key in
           ("optimizer_calls", "optimizer_input_tokens", "optimizer_output_tokens",
            "total_tokens", "total_cost_usd")},
        "run_ids": [record["run_id"] for record in matching],
    })
(ARTIFACTS / "resource_usage.json").write_text(json.dumps({
    "scope": "matched saved runs; all logged roles; development and rechecks excluded",
    "ledger_verified": True,
    "cost_tolerance_usd": 0.000001,
    "runs": resources,
    "aggregates": aggregates,
}, indent=2), encoding="utf-8")
print("\nPASS: resource tokens/calls/costs match each per-call ledger.")
for row in aggregates:
    print(f"{row['benchmark']} / {row['solver']}: {row['runs']} run(s), "
          f"{row['optimizer_calls']} optimizer calls, input={row['optimizer_input_tokens']}, "
          f"output={row['optimizer_output_tokens']}, total={row['total_tokens']}, "
          f"cost=${row['total_cost_usd']:.2f}")
print("wrote val_test_gap.json and resource_usage.json")
