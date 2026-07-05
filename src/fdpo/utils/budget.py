"""Token/cost accounting and the hard budget guard.

Every ModelClient.complete() reports (role, model, tokens) to a TokenLedger;
the BudgetGuard is checked after every call and raises BudgetExceededError
when cumulative spend reaches the cap. Callers catch the error, persist
partial results, and exit cleanly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fdpo.utils.io import CsvAppender

# model-name substring -> ($ per M input tokens, $ per M output tokens)
# Matched longest-key-first so "gpt-4o-mini" wins over "gpt-4o".
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "deepseek": (0.27, 1.10),
    "llama": (0.10, 0.10),
    "qwen": (0.10, 0.10),
    "mistral": (0.10, 0.10),
}


class BudgetExceededError(Exception):
    def __init__(self, spent: float, cap: float):
        self.spent = spent
        self.cap = cap
        super().__init__(f"budget exceeded: spent ${spent:.4f} >= cap ${cap:.2f}")


def price_for(model: str, fallback: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    name = model.lower()
    for key in sorted(PRICE_TABLE, key=len, reverse=True):
        if key in name:
            return PRICE_TABLE[key]
    return fallback


@dataclass
class LedgerEntry:
    role: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
    purpose: str


@dataclass
class TokenLedger:
    """In-memory + CSV record of every API call's tokens and cost."""

    fallback_price: tuple[float, float] = (0.0, 0.0)
    csv_path: Path | None = None
    entries: list[LedgerEntry] = field(default_factory=list)
    _csv: CsvAppender | None = field(default=None, repr=False)

    _FIELDS = ["role", "model", "prompt_tokens", "completion_tokens", "cost_usd", "purpose"]

    def record(self, role: str, model: str, prompt_tokens: int,
               completion_tokens: int, purpose: str = "") -> float:
        p_in, p_out = price_for(model, self.fallback_price)
        cost = (prompt_tokens * p_in + completion_tokens * p_out) / 1_000_000
        entry = LedgerEntry(role, model, prompt_tokens, completion_tokens, cost, purpose)
        self.entries.append(entry)
        if self.csv_path is not None:
            if self._csv is None:
                self._csv = CsvAppender(self.csv_path, self._FIELDS)
            self._csv.append(vars(entry))
        return cost

    @property
    def spent_usd(self) -> float:
        return sum(e.cost_usd for e in self.entries)

    @property
    def n_calls(self) -> int:
        return len(self.entries)

    def by_role(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for e in self.entries:
            r = out.setdefault(e.role, {"calls": 0, "prompt_tokens": 0,
                                        "completion_tokens": 0, "cost_usd": 0.0})
            r["calls"] += 1
            r["prompt_tokens"] += e.prompt_tokens
            r["completion_tokens"] += e.completion_tokens
            r["cost_usd"] += e.cost_usd
        return out

    def summary(self) -> dict:
        return {
            "total_calls": self.n_calls,
            "total_cost_usd": round(self.spent_usd, 6),
            "by_role": {r: {**v, "cost_usd": round(v["cost_usd"], 6)}
                        for r, v in self.by_role().items()},
        }


@dataclass
class BudgetGuard:
    """Raises when ledger spend reaches the cap. cap <= 0 disables the guard."""

    cap_usd: float
    ledger: TokenLedger

    def check(self) -> None:
        if self.cap_usd > 0 and self.ledger.spent_usd >= self.cap_usd:
            raise BudgetExceededError(self.ledger.spent_usd, self.cap_usd)
