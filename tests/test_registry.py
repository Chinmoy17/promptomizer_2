"""Registry state machine: commit/reject/rollback/best-snapshot + JSON round-trip."""

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


def test_commit_activates_new_version():
    reg = make_registry()
    v = reg.commit("constraints", "new constraint text", round_num=1, gate=gate(True))
    assert v == 1
    assert reg.active_prompt()["constraints"] == "new constraint text"
    state = reg.sections["constraints"]
    assert state.versions[0].status == "archived"
    assert state.versions[1].status == "active"
    assert reg.counts()["commits"] == 1


def test_reject_keeps_active_unchanged():
    reg = make_registry()
    old = reg.active_prompt()["task_details"]
    reg.reject("task_details", "bad candidate", round_num=1, gate=gate(False))
    assert reg.active_prompt()["task_details"] == old
    assert reg.sections["task_details"].versions[1].status == "rejected"
    assert reg.counts()["rejects"] == 1


def test_prompt_with_swaps_only_one_section():
    reg = make_registry()
    candidate = reg.prompt_with("context", "candidate context")
    assert candidate["context"] == "candidate context"
    assert candidate["system_role"] == reg.active_prompt()["system_role"]
    # original untouched
    assert reg.active_prompt()["context"] != "candidate context"


def test_best_snapshot_restore_after_stagnation():
    reg = make_registry()
    reg.commit("output_format", "v1 good", 1, gate(True, acc_new=0.80))
    reg.record_round_acc("output_format", 0.80)   # best
    reg.commit("output_format", "v2 worse", 2, gate(True, acc_old=0.80, acc_new=0.79))
    for acc in (0.79, 0.78, 0.79):
        reg.record_round_acc("output_format", acc)
    state = reg.sections["output_format"]
    assert state.stagnant_rounds == 3
    restored = reg.restore_best_snapshot("output_format")
    assert restored == state.best_version
    assert reg.active_prompt()["output_format"] == "v1 good"
    assert state.stagnant_rounds == 0


def test_json_round_trip(tmp_path):
    reg = make_registry(tmp_path)
    reg.commit("constraints", "committed text", 1, gate(True))
    reg.reject("context", "rejected text", 2, gate(False))
    reg.record_round_acc("constraints", 0.9)

    loaded = PromptRegistry.load(tmp_path / "registry.json")
    assert loaded.active_prompt() == reg.active_prompt()
    assert loaded.counts() == reg.counts()
    assert loaded.sections["constraints"].best_acc == pytest.approx(0.9)
    assert loaded.sections["context"].versions[1].gate["passed"] is False


def test_render():
    reg = make_registry()
    system = render_system(reg.active_prompt())
    assert "## System Role" in system and "## Output Format" in system
    msgs = render_messages(reg.active_prompt(), "What is 2+2?",
                           shots=[("Q1", "A1")])
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[-1]["content"] == "What is 2+2?"
