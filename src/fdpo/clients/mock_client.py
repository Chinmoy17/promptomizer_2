"""Deterministic mock client for pytest and --dry-run pipeline checks."""

from __future__ import annotations

import json
from collections.abc import Callable


from fdpo.clients.base import ChatResult, ModelClient
from fdpo.utils.budget import BudgetGuard, TokenLedger

Responder = Callable[[list[dict]], str]


class MockModelClient(ModelClient):
    """Returns canned responses from a queue, or computes them via a callable.

    - responses: list of strings popped in order (raises when exhausted), OR
    - responder: callable(messages) -> str for scripted behavior.
    Token counts are faked as len(text) // 4.
    """

    def __init__(self, role: str = "mock", model: str = "mock-model",
                 responses: list[str] | None = None,
                 responder: Responder | None = None,
                 ledger: TokenLedger | None = None,
                 guard: BudgetGuard | None = None):
        super().__init__(role, model, ledger, guard)
        if (responses is None) == (responder is None):
            raise ValueError("provide exactly one of responses / responder")
        self._queue = list(responses) if responses is not None else None
        self._responder = responder
        self.calls: list[list[dict]] = []

    def _complete(self, messages: list[dict], *, json_mode: bool,
                  temperature: float, max_tokens: int) -> ChatResult:
        self.calls.append(messages)
        if self._queue is not None:
            if not self._queue:
                raise RuntimeError(f"mock client ({self.role}) ran out of responses")
            text = self._queue.pop(0)
        else:
            text = self._responder(messages)
        n = max(1, len(text) // 4)
        prompt_n = max(1, sum(len(m.get("content", "")) for m in messages) // 4)
        return ChatResult(text=text, prompt_tokens=prompt_n,
                          completion_tokens=n, model=self.model)


def dry_run_client(role: str, ledger: TokenLedger | None = None,
                   guard: BudgetGuard | None = None) -> MockModelClient:
    """Plausible generic behavior per role so --dry-run exercises the full
    pipeline without APIs: solver answers 'A'/42, judge emits valid JSON,
    optimizer echoes a rewritten section."""

    def respond(messages: list[dict]) -> str:
        text_all = " ".join(m.get("content", "") for m in messages)
        if role == "judge":
            section = "full_prompt" if "full_prompt" in text_all else "output_format"
            return json.dumps({
                "verdict": "incorrect",
                "critique": "The output format instruction was ignored.",
                "section": section,
                "error_type": "WRONG",
            })
        if role == "optimizer":
            return "Respond concisely. End with the exact required answer format."
        text = " ".join(m.get("content", "") for m in messages)
        if "####" in text:
            return "Let's think step by step. The total is 42.\n#### 42"
        if "Yes or No" in text or "Yes|No" in text:
            return "Reasoning: this is an out-of-court statement.\nAnswer: Yes"
        return "Let's think step by step. The best option is A.\nAnswer: A"

    return MockModelClient(role=role, model=f"mock-{role}",
                           responder=respond, ledger=ledger, guard=guard)
