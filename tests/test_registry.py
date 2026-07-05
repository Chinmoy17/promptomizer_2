"""Registry state machine (v2): bundle commit/reject, whole-run stagnation
fix (a tie counts as progress, not stagnation), best-snapshot restore, and
JSON round-trip."""

import pytest

from fdpo.core.prompt import SCHEMA_5, render_messages, render_system
from fdpo.core.registry import GateResult, PromptRegistry
from fdpo.prompts.seeds import seed_sections


def make_registry(tmp_path=None):
    path = (tmp_path / "registry.json") if tmp_path else None
    return PromptRegistry(SCHEMA_5, seed_sections("gsm8k", SCHEMA_5), path=path)


def gate(passed: bool, acc_old=0.7, acc_new=0.75) -> GateResult:
    return GateResult(acc_old=acc_old, acc_new=acc_new, rho=0.02, passed=passed,
                      batch_size=20, n_failures=5, recovered_failures=3, broke=0)


def test_seed_state():
    reg = make_registry()
    prompt = reg.active_prompt()
    assert list(prompt) == list(SCHEMA_5)
    assert "####" in prompt["output_format"]
    assert reg.counts() == {"commits": 0, "rejects": 0}


def test_commit_bundle_activates_versions():
    reg = make_registry()
    versions = reg.commit_bundle({"constraints": "new constraint text"},
                                 round_num=1, gate=gate(True))
    assert versions == {"constraints": 1}
    assert reg.active_prompt()["constraints"] == "new constraint text"
    state = reg.sections["constraints"]
    assert state.versions[0].status == "archived"
    assert state.versions[1].status == "active"
    assert reg.counts()["commits"] == 1


def test_commit_bundle_activates_multiple_sections_together():
    reg = make_registry()
    versions = reg.commit_bundle(
        {"context": "new context", "constraints": "new constraints"},
        round_num=1, gate=gate(True))
    assert versions == {"context": 1, "constraints": 1}
    active = reg.active_prompt()
    assert active["context"] == "new context"
    assert active["constraints"] == "new constraints"
    # untouched sections stay at the seed
    assert active["system_role"] == seed_sections("gsm8k", SCHEMA_5)["system_role"]
    assert reg.counts()["commits"] == 2


def test_reject_bundle_keeps_active_unchanged():
    reg = make_registry()
    old = reg.active_prompt()["task_details"]
    reg.reject_bundle({"task_details": "bad candidate"}, round_num=1, gate=gate(False))
    assert reg.active_prompt()["task_details"] == old
    assert reg.sections["task_details"].versions[1].status == "rejected"
    assert reg.counts()["rejects"] == 1


def test_prompt_with_edits_swaps_only_given_sections():
    reg = make_registry()
    candidate = reg.prompt_with_edits({"context": "candidate context"})
    assert candidate["context"] == "candidate context"
    assert candidate["system_role"] == reg.active_prompt()["system_role"]
    # original untouched
    assert reg.active_prompt()["context"] != "candidate context"


def test_tie_counts_as_progress_not_stagnation():
    """The v2 stagnation fix: a commit that merely TIES the historical best
    (zero regression, no strict improvement) must reset stagnant_rounds and
    update the best snapshot -- not be treated as a non-improving round."""
    reg = make_registry()
    reg.commit_bundle({"output_format": "v1 good"}, 1, gate(True, acc_new=0.80))
    reg.record_round(passed=True, acc=0.80)
    assert reg.run_stagnant_rounds == 0
    assert reg.run_best_acc == pytest.approx(0.80)
    assert reg.run_best_versions["output_format"] == 1

    # a second commit that TIES 0.80 exactly (not a strict improvement)
    reg.commit_bundle({"output_format": "v2 also good"}, 2, gate(True, acc_old=0.80, acc_new=0.80))
    reg.record_round(passed=True, acc=0.80)
    assert reg.run_stagnant_rounds == 0, "a tie must not count as stagnation"
    assert reg.run_best_versions["output_format"] == 2, "best must track the latest commit"


def test_best_snapshot_restore_after_real_stagnation():
    reg = make_registry()
    reg.commit_bundle({"output_format": "v1 good"}, 1, gate(True, acc_new=0.80))
    reg.record_round(passed=True, acc=0.80)

    # three genuinely REJECTED rounds in a row -> real stagnation
    for round_num in (2, 3, 4):
        reg.reject_bundle({"output_format": f"bad attempt {round_num}"}, round_num,
                          gate(False, acc_old=0.80, acc_new=0.70))
        reg.record_round(passed=False, acc=0.70)

    assert reg.run_stagnant_rounds == 3
    restored = reg.restore_best_snapshot()
    assert restored["output_format"] == "v1 good"
    assert reg.run_stagnant_rounds == 0


def test_json_round_trip(tmp_path):
    reg = make_registry(tmp_path)
    reg.commit_bundle({"constraints": "committed text"}, 1, gate(True))
    reg.record_round(passed=True, acc=0.75)
    reg.reject_bundle({"context": "rejected text"}, 2, gate(False))
    reg.record_round(passed=False, acc=0.75)

    loaded = PromptRegistry.load(tmp_path / "registry.json")
    assert loaded.active_prompt() == reg.active_prompt()
    assert loaded.counts() == reg.counts()
    assert loaded.run_best_acc == pytest.approx(0.75)
    assert loaded.run_stagnant_rounds == 1
    assert loaded.sections["context"].versions[1].gate["passed"] is False


def test_render():
    reg = make_registry()
    system = render_system(reg.active_prompt())
    assert "## System Role" in system and "## Output Format" in system
    msgs = render_messages(reg.active_prompt(), "What is 2+2?",
                           shots=[("Q1", "A1")])
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[-1]["content"] == "What is 2+2?"
