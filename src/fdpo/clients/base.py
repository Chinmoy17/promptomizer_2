"""ModelClient ABC: one interface for every model at every site."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from fdpo.utils.budget import BudgetGuard, TokenLedger


@dataclass
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str


class ModelClient(ABC):
    """A chat-completion client bound to one role (solver / judge / optimizer).

    Subclasses implement _complete(); this base handles ledger reporting and
    the budget-guard check so no call can escape accounting.
    """

    def __init__(self, role: str, model: str,
                 ledger: TokenLedger | None = None,
                 guard: BudgetGuard | None = None):
        self.role = role
        self.model = model
        self.ledger = ledger
        self.guard = guard

    def complete(self, messages: list[dict], *, json_mode: bool = False,
                 temperature: float = 0.0, max_tokens: int = 1024,
                 purpose: str = "") -> ChatResult:
        result = self._complete(messages, json_mode=json_mode,
                                temperature=temperature, max_tokens=max_tokens)
        if self.ledger is not None:
            self.ledger.record(self.role, result.model, result.prompt_tokens,
                               result.completion_tokens, purpose)
        if self.guard is not None:
            self.guard.check()
        return result

    @abstractmethod
    def _complete(self, messages: list[dict], *, json_mode: bool,
                  temperature: float, max_tokens: int) -> ChatResult:
        ...
