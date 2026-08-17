"""End-to-end runs on the mock client (--dry-run path): every method writes a
complete, internally-consistent results tree; budget abort saves partial state."""

import json

import pytest

from fdpo.config import ExperimentConfig
from fdpo.utils.io import read_json
from scripts.run_experiment import run


def make_cfg(tmp_path, method, **overrides) -> ExperimentConfig:
    cfg = ExperimentConfig(
        method=method, dataset="arc", seed=0,
        n_train=8, n_test=6, n_shots=2, max_rounds=2,
        val_size=4, budget_usd=0.0,  # guard disabled
        dry_run=True, results_root=str(tmp_path / "results"),
        phase="test_phase",
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


EXPECTED_FILES = ["config.json", "metrics.json", "registry.json",
                  "eval_log.csv", "ledger.csv"]


@pytest.mark.parametrize("method", ["zeroshot_cot", "fewshot_cot"])
def test_baseline_methods_write_results(tmp_path, method):
    run_dir = run(make_cfg(tmp_path, method))
    for name in EXPECTED_FILES:
        assert (run_dir / name).exists(), name
    metrics = read_json(run_dir / "metrics.json")
    assert metrics["status"] == "completed"
    assert metrics["method"] == method
    assert metrics["optimization"] is None
    # mock solver answers A; synthetic golds alternate A/B -> accuracy 0.5
    assert metrics["seed_test"]["accuracy"] == pytest.approx(0.5)


@pytest.mark.parametrize("method", ["fdpo", "monolithic"])
def test_optimization_methods_full_tree(tmp_path, method):
    run_dir = run(make_cfg(tmp_path, method))
    for name in EXPECTED_FILES + ["train_log.csv", "rounds_log.csv", "events.jsonl"]:
        assert (run_dir / name).exists(), name

    metrics = read_json(run_dir / "metrics.json")
    assert metrics["status"] == "completed"
    assert metrics["optimization"]["rounds_run"] == 2
    fm = metrics["fdpo_metrics"]
    # mock judge attributes every failure -> rewrites happen and gate passes
    # (mock solver is unchanged by the rewrite, so nothing regresses)
    assert fm["n_commits"] >= 1
    assert fm["regression_rate"] == 0.0
    assert metrics["cost"]["total_calls"] > 0

    registry = read_json(run_dir / "registry.json")
    expected_sections = 1 if method == "monolithic" else 5
    assert len(registry["sections"]) == expected_sections
    active_sections = [
        s for s in registry["sections"].values()
        if s["versions"][s["active_version"]]["status"] == "active"
    ]
    assert len(active_sections) == expected_sections


def test_config_json_never_contains_keys(tmp_path):
    run_dir = run(make_cfg(tmp_path, "zeroshot_cot"))
    raw = (run_dir / "config.json").read_text()
    assert "api_key" not in raw and "sk-" not in raw


def test_budget_abort_saves_partial_results(tmp_path):
    cfg = make_cfg(tmp_path, "fdpo",
                   budget_usd=0.0001, price_in=1000.0, price_out=1000.0)
    run_dir = run(cfg)
    metrics = read_json(run_dir / "metrics.json")
    assert metrics["status"] == "budget_aborted"
    assert (run_dir / "registry.json").exists()
    assert (run_dir / "ledger.csv").exists()
    # spend recorded despite the abort
    assert metrics["cost"]["total_cost_usd"] > 0


def test_fdpo_registry_records_gate_history(tmp_path):
    run_dir = run(make_cfg(tmp_path, "fdpo"))
    registry = read_json(run_dir / "registry.json")
    all_versions = [v for s in registry["sections"].values() for v in s["versions"]]
    gated = [v for v in all_versions if v["gate"] is not None]
    assert gated, "at least one gated rewrite should be recorded"
    for v in gated:
        assert {"acc_old", "acc_new", "passed", "broke"} <= set(v["gate"])


def test_events_jsonl_is_valid(tmp_path):
    run_dir = run(make_cfg(tmp_path, "fdpo"))
    lines = (run_dir / "events.jsonl").read_text().strip().splitlines()
    assert lines
    valid_events = {"bundle", "edits"}
    events = [json.loads(line) for line in lines]
    for event in events:
        assert event["event"] in valid_events, f"unexpected event type: {event['event']}"
    # every round that produced a bundle must have logged its edits first
    assert any(e["event"] == "bundle" for e in events)
    assert any(e["event"] == "edits" for e in events), \
        "edits events must be persisted for post-hoc analysis"
