"""End-to-end and unit tests for the reflective `reflect_fdpo` method.

Uses --dry-run (mock clients) so no API calls, no cost. The blind control
(`simple_fdpo`) has its own tests in test_simple_loop.py and is untouched.
"""

from fdpo.config import ExperimentConfig, build_arg_parser
from fdpo.data.md_prompt import parse_markdown
from fdpo.prompts.reflect_optimizer_prompt import build_reflect_optimizer_messages
from fdpo.utils.io import read_json
from scripts.run_experiment import run


def make_cfg(tmp_path, **overrides) -> ExperimentConfig:
    cfg = ExperimentConfig(
        method="reflect_fdpo",
        dataset="legalbench_hearsay",
        seed=0,
        n_train=8, n_test=6,
        val_size=4,        # ignored by reflect_fdpo but must be valid
        max_rounds=2,      # ignored by reflect_fdpo
        tau=3,
        n_fail=5, n_gold=2,
        simple_max_rounds=3,
        budget_usd=0.0,
        dry_run=True,
        results_root=str(tmp_path / "results"),
        phase="test_phase",
    )
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


REFLECTION = {
    "prev_round": 1,
    "changed_sections": [
        {"section": "constraints", "previous_text": "Old constraint text."},
    ],
    "mining_recovered": [
        {"question": "Q-recovered?", "gold": "Yes"},
    ],
    "mining_regressed": [
        {"question": "Q-regressed?", "output": "Answer: No", "gold": "Yes"},
    ],
    "n_mining_recovered": 1,
    "n_mining_regressed": 1,
    "val_before": 0.72,
    "val_after": 0.68,
    "val_recovered": 1,
    "val_regressed": 2,
}


def test_cli_accepts_reflect_fdpo_method():
    args = build_arg_parser().parse_args(["--method", "reflect_fdpo"])
    assert args.method == "reflect_fdpo"


def test_builder_round1_has_no_reflection_block():
    messages = build_reflect_optimizer_messages(
        "## System Role\nSolve the task.", [], [], dataset="legalbench_hearsay",
        round_num=1, max_rounds=3, reflection=None)
    assert "EFFECT OF YOUR PREVIOUS REWRITE" not in messages[1]["content"]
    # The protocol is still explained up front in the system message.
    assert "HOW THIS PROCESS WORKS" in messages[0]["content"]
    assert "## Analysis" in messages[0]["content"]


def test_builder_reflection_block_content_and_placement():
    messages = build_reflect_optimizer_messages(
        "## System Role\nSolve the task.", [], [], dataset="legalbench_hearsay",
        round_num=2, max_rounds=3, reflection=REFLECTION)
    user = messages[1]["content"]
    assert "EFFECT OF YOUR PREVIOUS REWRITE (round 1)" in user
    # Placement: after the current-prompt fence, before FAILURES.
    assert user.index("FULL CURRENT PROMPT") < user.index("EFFECT OF YOUR")
    assert user.index("EFFECT OF YOUR") < user.index("FAILURES (")
    # The reflection block must be fence-free (mock client extracts the FIRST
    # fenced block as the current prompt).
    effect = user[user.index("EFFECT OF YOUR"):user.index("FAILURES (")]
    assert "```" not in effect
    # Per-item detail present.
    assert "Old constraint text." in effect
    assert "Q-regressed?" in effect
    assert "Model's new wrong answer: Answer: No" in effect
    assert "Q-recovered?" in effect
    # Validation is aggregate-only.
    assert "0.720 -> 0.680" in effect
    assert "recovered 1 and regressed 2 held-out item(s)" in effect


def test_builder_task_description_injected():
    messages = build_reflect_optimizer_messages(
        "## System Role\nSolve.", [], [], dataset="arc")
    assert "ARC-Challenge science multiple-choice question" in messages[0]["content"]


def test_parse_markdown_drops_analysis_header():
    md = ("## Analysis\nMy previous constraint edit caused the regression.\n"
          "## System Role\nYou are an expert.\n"
          "## Output Format\nAnswer: Yes or No")
    sections = parse_markdown(md)
    assert "analysis" not in sections
    assert sections["system_role"] == "You are an expert."
    assert "regression" not in " ".join(sections.values())


def test_reflect_fdpo_end_to_end_dry_run(tmp_path):
    run_dir = run(make_cfg(tmp_path))
    for name in ("config.json", "metrics.json", "registry.json",
                 "eval_log.csv", "prompt_baseline.md", "prompt_current.md"):
        assert (run_dir / name).exists(), f"missing artifact: {name}"
    m = read_json(run_dir / "metrics.json")
    assert m["method"] == "reflect_fdpo"
    assert m["status"] == "completed"
    opt = m["optimization"]
    assert opt["mode"] == "reflect"
    assert opt["simple_max_rounds"] == 3
    # Confusion matrices present with the standard keys.
    for key in ("recoveries", "regressions", "still_wrong",
                "still_right_count", "net_gain"):
        assert key in opt["train_confusion"]
        assert key in opt["test_confusion"]
    # Round log: committed rounds carry the val churn + reflection markers,
    # and round 1 never sees a reflection while later rounds do.
    committed = [r for r in opt["rounds_log"]
                 if r["status"].startswith("committed")]
    if committed:
        first = committed[0]
        assert first["reflection_shown"] is False
        assert "val_recovered_this_round" in first
        assert "val_regressed_this_round" in first
        for later in committed[1:]:
            assert later["reflection_shown"] is True
