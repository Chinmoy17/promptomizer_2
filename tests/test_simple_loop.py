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
    """Default cfg (simple_max_rounds=1): at most one committed round.
    The invariant simple_fdpo preserves is that no version is ever REJECTED
    at the registry level — either committed (active or archived) or, on a
    multi-round regression, the round's version stays active but the
    best-snapshot is restored (which may re-archive versions but never marks
    them rejected)."""
    run_dir = run(make_cfg(tmp_path, tau=1))
    reg = read_json(run_dir / "registry.json")
    for section in reg["sections"].values():
        for v in section["versions"][1:]:
            assert v["status"] != "rejected", \
                f"simple mode should never reject: found {v['status']}"


def test_simple_fdpo_multi_round_config_accepted(tmp_path):
    """simple_max_rounds=3 with mock client runs without crashing and
    produces a rounds_log with at least one entry."""
    run_dir = run(make_cfg(tmp_path, tau=1, simple_max_rounds=3))
    m = read_json(run_dir / "metrics.json")
    opt = m["optimization"]
    assert opt["simple_max_rounds"] == 3
    assert "rounds_log" in opt
    assert isinstance(opt["rounds_log"], list)
    # Mock client's optimizer output is deterministic — the loop will make
    # at least one round (committed, no_change, or parse_failed) or bail on
    # below_tau. Any non-empty log is acceptable here.
    assert len(opt["rounds_log"]) >= 1


def test_simple_fdpo_registry_no_rejects_multi_round(tmp_path):
    """Even with 3 rounds and best-snapshot rescue in play, no registry
    version should ever be marked 'rejected' — simple_fdpo either commits
    (may later re-archive on rescue) or leaves the registry unchanged."""
    run_dir = run(make_cfg(tmp_path, tau=1, simple_max_rounds=3))
    reg = read_json(run_dir / "registry.json")
    for section in reg["sections"].values():
        for v in section["versions"][1:]:
            assert v["status"] != "rejected", \
                f"simple_fdpo (multi-round) should never reject: found {v['status']}"
