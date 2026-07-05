"""Shared evaluation: run the solver over examples, verdict programmatically.

Used for test-set evaluation AND the regression gate's old-vs-new comparison,
so both are measured identically.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from fdpo.clients.base import ModelClient
from fdpo.core.prompt import render_messages
from fdpo.data.extraction import extract_pred, is_correct
from fdpo.data.loaders import Example

DEFAULT_MAX_WORKERS = 1  # safe default: sequential unless a caller opts in.
# Callers with scripted/order-dependent mock responses (tests) must stay
# sequential; real runs pass cfg.max_workers explicitly (config.py default 8).


@dataclass
class EvalRow:
    example_id: str
    pred: str | None
    gold: str
    correct: bool
    output: str


@dataclass
class EvalResult:
    rows: list[EvalRow]

    @property
    def accuracy(self) -> float:
        return sum(r.correct for r in self.rows) / len(self.rows) if self.rows else 0.0

    @property
    def extraction_failures(self) -> int:
        return sum(1 for r in self.rows if r.pred is None)

    def correct_ids(self) -> set[str]:
        return {r.example_id for r in self.rows if r.correct}


def evaluate(solver: ModelClient, sections: dict[str, str],
             examples: list[Example], dataset: str, *,
             shots: list[tuple[str, str]] | None = None,
             temperature: float = 0.0, max_tokens: int = 1024,
             purpose: str = "eval",
             max_workers: int = DEFAULT_MAX_WORKERS) -> EvalResult:
    """Runs the solver over every example. Calls are independent (same fixed
    `sections` prompt, no shared mutable state between examples) so they're
    dispatched across a bounded thread pool; ThreadPoolExecutor.map preserves
    input order in its output regardless of completion order, so rows line
    up with `examples` the same as the old sequential loop did.
    """
    def _run_one(ex: Example) -> EvalRow:
        result = solver.complete(
            render_messages(sections, ex.question, shots=shots),
            temperature=temperature, max_tokens=max_tokens, purpose=purpose)
        pred = extract_pred(dataset, result.text)
        return EvalRow(example_id=ex.id, pred=pred, gold=ex.gold,
                       correct=is_correct(dataset, pred, ex.gold), output=result.text)

    workers = max(1, min(max_workers, len(examples))) if examples else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_run_one, examples))
    return EvalResult(rows=rows)
