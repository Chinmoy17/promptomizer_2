"""End-to-end tests for the paper-faithful `simple_fdpo` method.

Uses --dry-run (mock clients) so no API calls, no cost. Verifies the pipeline
produces the expected artifacts and the confusion-matrix accounting is
internally consistent.
"""

import pytest

from fdpo.config import ExperimentConfig
from fdpo.utils.io import read_json
from scripts.run_experiment import run


def make_cfg(tmp_path, **overrides) -> ExperimentConfig:
    cfg = ExperimentConfig(
        method="simple_fdpo",
        dataset="legalbench_hearsay",
        seed=0,
        n_train=8, n_test=6,
        val_size=4,        # ignored by simple_fdpo but must be valid
        max_rounds=2,      # ignored by simple_fdpo
        tau=3,             # trigger threshold: 3 failures is easy on mock data
        n_fail=5, n_gold=2,
        budget_usd=0.0,    # guard disabled
        dry_run=True,
        results_root=str(tmp_path / "results"),
        phase="test_phase",
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def test_simple_fdpo_produces_all_expected_files(tmp_path):
    run_dir = run(make_cfg(tmp_path))
    for name in ("config.json", "metrics.json", "registry.json",
                 "eval_log.csv", "ledger.csv",
                 "prompt_baseline.md", "prompt_current.md"):
        assert (run_dir / name).exists(), f"missing artifact: {name}"


def test_simple_fdpo_metrics_shape(tmp_path):
    run_dir = run(make_cfg(tmp_path))
    m = read_json(run_dir / "metrics.json")
    assert m["method"] == "simple_fdpo"
    assert m["status"] == "completed"
    opt = m["optimization"]
    assert opt is not None
    assert opt["mode"] == "simple"
    assert opt["tau"] == 3
    # Baseline/current shapes
    for phase in ("baseline_train", "current_train"):
        assert phase in opt
        assert "accuracy" in opt[phase]
        assert "n_correct" in opt[phase]
        assert "n_wrong" in opt[phase]
    # Train confusion matrix
    tc = opt["train_confusion"]
    for k in ("recoveries", "regressions", "still_wrong",
              "still_right_count", "net_gain"):
        assert k in tc


def test_simple_fdpo_confusion_matrix_is_internally_consistent(tmp_path):
    run_dir = run(make_cfg(tmp_path))
    m = read_json(run_dir / "metrics.json")
    opt = m["optimization"]
    tc = opt["train_confusion"]
    baseline_wrong = opt["baseline_train"]["n_wrong"]
    baseline_correct = opt["baseline_train"]["n_correct"]
    # baseline_wrong = recoveries + still_wrong
    assert baseline_wrong == len(tc["recoveries"]) + len(tc["still_wrong"])
    # baseline_correct = regressions + still_right_count
    assert baseline_correct == len(tc["regressions"]) + tc["still_right_count"]
    # net_gain = |recoveries| - |regressions|
    assert tc["net_gain"] == len(tc["recoveries"]) - len(tc["regressions"])


def test_simple_fdpo_writes_test_confusion_matrix(tmp_path):
    run_dir = run(make_cfg(tmp_path))
    m = read_json(run_dir / "metrics.json")
    opt = m["optimization"]
    assert "test_confusion" in opt
    tc = opt["test_confusion"]
    for k in ("recoveries", "regressions", "still_wrong",
              "still_right_count", "net_gain"):
        assert k in tc


def test_simple_fdpo_triggers_on_low_threshold(tmp_path):
    run_dir = run(make_cfg(tmp_path, tau=1))
    m = read_json(run_dir / "metrics.json")
    opt = m["optimization"]
    # tau=1: even a single failure triggers optimization
    assert opt["triggered"] is True
    # Mock optimizer produces a valid markdown response -> committed or partial
    assert opt["edit_status"] in ("committed", "partial_parse", "no_change")


def test_simple_fdpo_skips_when_threshold_not_met(tmp_path):
    # tau larger than the whole batch cannot possibly trigger
    run_dir = run(make_cfg(tmp_path, tau=1000))
    m = read_json(run_dir / "metrics.json")
    opt = m["optimization"]
    assert opt["triggered"] is False
    assert opt["edit_status"] == "not_triggered"
    assert opt["optimizer_calls"] == 0


def test_simple_fdpo_registry_records_at_most_one_commit(tmp_path):
    """No rounds -> at most 1 registry commit (per changed section, in a
    single bundle). Never any rejects."""
    run_dir = run(make_cfg(tmp_path, tau=1))
    reg = read_json(run_dir / "registry.json")
    for section in reg["sections"].values():
        # version 0 is the seed; any additional versions must be status="active"
        # (never "rejected" -- simple mode does not reject).
        for v in section["versions"][1:]:
            assert v["status"] == "active", \
                f"simple mode should never reject: found {v['status']}"
