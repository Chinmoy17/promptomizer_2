"""End-to-end and unit tests for the reflective `reflect_fdpo` method.

Uses --dry-run (mock clients) so no API calls, no cost. The blind control
(`simple_fdpo`) has its own tests in test_simple_loop.py and is untouched.
"""

from fdpo.config import ExperimentConfig, build_arg_parser
from fdpo.data.md_prompt import parse_markdown
from fdpo.prompts.reflect_optimizer_prompt import (_MAX_OUTPUT_CHARS,
                                                   build_reflect_optimizer_messages)
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
    "val_recovered": [
        {"question": "V-recovered?", "gold": "No"},
    ],
    "val_regressed": [
        {"question": "V-regressed-1?", "output": "Answer: Yes", "gold": "No"},
        {"question": "V-regressed-2?", "output": "Answer: Yes", "gold": "No"},
    ],
    "val_before": 0.72,
    "val_after": 0.68,
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
    assert "CRITICAL RULE ABOUT EXAMPLES" in messages[0]["content"]
    assert "not paraphrased with different names" in messages[0]["content"]


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
    # Mining per-item detail present, full (not capped).
    assert "Old constraint text." in effect
    assert "Q-regressed?" in effect
    assert "Model's new wrong answer: Answer: No" in effect
    assert "Q-recovered?" in effect
    # Validation is now FULL detail too, not aggregate-only.
    assert "0.720 -> 0.680" in effect
    assert "V-recovered?" in effect
    assert "V-regressed-1?" in effect
    assert "V-regressed-2?" in effect
    assert effect.count("Model's new wrong answer: Answer: Yes") == 2


def test_cli_accepts_ablation_flags():
    args = build_arg_parser().parse_args(
        ["--method", "reflect_fdpo", "--no-effect-report",
         "--round1-prompt-file", "x.md"])
    assert args.no_effect_report is True
    assert args.round1_prompt_file == "x.md"
    defaults = build_arg_parser().parse_args(["--method", "reflect_fdpo"])
    assert defaults.no_effect_report is False and defaults.round1_prompt_file == ""


def test_builder_no_effect_report_drops_every_report_instruction():
    messages = build_reflect_optimizer_messages(
        "## System Role\nSolve the task.", [], [], dataset="legalbench_hearsay",
        round_num=2, max_rounds=3, reflection=REFLECTION, effect_report=False)
    system, user = messages[0]["content"], messages[1]["content"]
    assert "EFFECT OF YOUR PREVIOUS REWRITE" not in user
    assert "V-regressed-1?" not in user
    assert "next round" not in user
    for phrase in ("EFFECT", "RECOVERED", "REGRESSED", "validation item",
                   "VALIDATION item", "From round 2 on"):
        assert phrase not in system, phrase
    # Everything not about the report is carried over unchanged.
    for phrase in ("HOW THIS PROCESS WORKS", "CRITICAL RULE ABOUT EXAMPLES",
                   "CRITICAL FACT ABOUT THE SOLVER", "A good rewrite",
                   "RESPONSE FORMAT"):
        assert phrase in system, phrase
    assert "{task_description}" not in system and "{max_rounds}" not in system


def test_builder_default_keeps_report_instructions():
    messages = build_reflect_optimizer_messages(
        "## System Role\nSolve.", [], [], dataset="legalbench_hearsay",
        round_num=1, max_rounds=3)
    assert "EFFECT REPORT of your previous rewrite" in messages[0]["content"]
    assert "next round" in messages[1]["content"]


def test_builder_truncates_long_solver_output():
    """A verbose completion (e.g. GPT-4.1 on AIME writing thousands of tokens
    of working) must not be pasted into the optimizer request in full -- only
    a bounded tail survives, which is what previously blew the gpt-5
    deployment's per-minute token quota on a single optimizer call."""
    long_output = ("scratch work " * 200) + "#### 42"
    assert len(long_output) > _MAX_OUTPUT_CHARS

    failures = [{"question": "Q1?", "output": long_output, "gold": "42"}]
    messages = build_reflect_optimizer_messages(
        "## System Role\nSolve.", failures, [], dataset="aime",
        round_num=1, max_rounds=3, reflection=None)
    user = messages[1]["content"]
    assert "#### 42" in user
    assert long_output not in user
    assert user.count("scratch work") < 200

    reflection = {
        **REFLECTION,
        "mining_regressed": [
            {"question": "Q2?", "output": long_output, "gold": "7"},
        ],
    }
    messages2 = build_reflect_optimizer_messages(
        "## System Role\nSolve.", [], [], dataset="aime",
        round_num=2, max_rounds=3, reflection=reflection)
    user2 = messages2[1]["content"]
    assert "#### 42" in user2
    assert long_output not in user2
    assert "```" not in user2[user2.index("EFFECT OF YOUR"):user2.index("FAILURES (")]


def test_builder_leaves_short_solver_output_unchanged():
    """No-op for existing short-completion datasets (hearsay/MMLU/etc)."""
    short_output = "Answer: Yes"
    failures = [{"question": "Q?", "output": short_output, "gold": "No"}]
    messages = build_reflect_optimizer_messages(
        "## System Role\nSolve.", failures, [], dataset="legalbench_hearsay",
        round_num=1, max_rounds=3, reflection=None)
    assert f"Model's wrong answer: {short_output}" in messages[1]["content"]


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
    assert opt["selection"] == "best_of_rounds"
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
        # Best-of-rounds selection: the shipped val accuracy must be the
        # MAXIMUM val_acc_after among all committed rounds, and the shipped
        # round number must actually be the round that achieved it.
        if opt["shipped_structured"]:
            best = max(committed, key=lambda r: r["val_acc_after"])
            assert opt["best_structured_val_acc"] == best["val_acc_after"]
            assert opt["shipped_round"] == best["round"]
            assert opt["current_train"]["accuracy"] == best["train_acc_after"]


ROUND1_MD = """## System Role
You are a careful evidence-law analyst.

## Context
Replayed round-one context.

## Task Details
Replayed round-one task details.

## Constraints
Replayed round-one constraints.

## Output Format
Answer: Yes or No
"""


def _committed(opt):
    return [r for r in opt["rounds_log"] if r["status"] == "committed"]


def test_no_effect_report_never_shows_reflection(tmp_path):
    run_dir = run(make_cfg(tmp_path, effect_report=False, tau=1))
    opt = read_json(run_dir / "metrics.json")["optimization"]
    assert opt["effect_report"] is False
    committed = _committed(opt)
    assert committed
    assert all(r["reflection_shown"] is False for r in committed)


def test_round1_replay_fixes_the_parent_and_skips_the_optimizer_call(tmp_path):
    md = tmp_path / "round1.md"
    md.write_text(ROUND1_MD, encoding="utf-8")
    run_dir = run(make_cfg(tmp_path, round1_prompt_file=str(md), tau=1))
    opt = read_json(run_dir / "metrics.json")["optimization"]
    committed = _committed(opt)
    first = committed[0]
    assert first["round"] == 1 and first["replayed"] is True
    assert first["reflection_shown"] is False
    assert first["sections_changed"]
    assert all(r["replayed"] is False for r in committed[1:])
    assert opt["optimizer_calls"] <= 2          # rounds 2 and 3 only
    assert opt["round1_prompt_file"] == str(md)
    # Round 2 is the first round that can show the report of the replayed edit.
    second = [r for r in committed if r["round"] == 2]
    assert not second or second[0]["reflection_shown"] is True


def test_round1_replay_without_effect_report_matches_the_ablation_arm(tmp_path):
    md = tmp_path / "round1.md"
    md.write_text(ROUND1_MD, encoding="utf-8")
    run_dir = run(make_cfg(tmp_path, round1_prompt_file=str(md), tau=1,
                           effect_report=False))
    opt = read_json(run_dir / "metrics.json")["optimization"]
    committed = _committed(opt)
    assert committed[0]["replayed"] is True
    assert all(r["reflection_shown"] is False for r in committed)
