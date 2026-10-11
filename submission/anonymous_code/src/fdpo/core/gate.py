"""Per-section regression gate with a rolling correct-pool.

The pool holds train examples the solver previously answered correctly
(global, FIFO-capped; per-section clustering is a documented later extension —
key the pool by section if gate batches ever need to be cluster-specific).

A gate evaluation runs the OLD and NEW prompts on:
  - a seeded sample of the pool  -> the gate decision + regression measurement
  - the triggering failures      -> recovery measurement (non-gating)
"""

from __future__ import annotations

import random

from fdpo.clients.base import ModelClient
from fdpo.core.registry import GateResult
from fdpo.data.loaders import Example
from fdpo.eval.evaluator import evaluate


class CorrectPool:
    def __init__(self, cap: int = 200):
        self.cap = cap
        self._examples: dict[str, Example] = {}  # id -> Example, insertion-ordered

    def add(self, ex: Example) -> None:
        if ex.id in self._examples:
            return
        self._examples[ex.id] = ex
        while len(self._examples) > self.cap:
            oldest = next(iter(self._examples))
            del self._examples[oldest]

    def __len__(self) -> int:
        return len(self._examples)

    def sample(self, n: int, rng: random.Random) -> list[Example]:
        pool = list(self._examples.values())
        if len(pool) <= n:
            return pool
        return rng.sample(pool, n)


def evaluate_candidate(solver: ModelClient, dataset: str,
                       old_sections: dict[str, str],
                       new_sections: dict[str, str],
                       gate_batch: list[Example],
                       failures: list[Example], *,
                       rho: float, min_pool: int = 5,
                       solver_temperature: float = 0.0,
                       solver_max_tokens: int = 1024,
                       max_workers: int = 1) -> GateResult:
    """Compare old vs new prompt. Gate decision uses only the correct-pool
    batch; failure recovery is measured but never blocks a commit.

    Cold start: with fewer than min_pool previously-correct examples the gate
    auto-passes (there is nothing meaningful to regress against).
    """
    recovered = 0
    if failures:
        rec = evaluate(solver, new_sections, failures, dataset,
                       temperature=solver_temperature,
                       max_tokens=solver_max_tokens, purpose="gate:recovery",
                       max_workers=max_workers)
        recovered = sum(r.correct for r in rec.rows)

    if len(gate_batch) < min_pool:
        return GateResult(acc_old=1.0, acc_new=1.0, rho=rho, passed=True,
                          batch_size=len(gate_batch), n_failures=len(failures),
                          recovered_failures=recovered, broke=0)

    old = evaluate(solver, old_sections, gate_batch, dataset,
                   temperature=solver_temperature,
                   max_tokens=solver_max_tokens, purpose="gate:old",
                   max_workers=max_workers)
    new = evaluate(solver, new_sections, gate_batch, dataset,
                   temperature=solver_temperature,
                   max_tokens=solver_max_tokens, purpose="gate:new",
                   max_workers=max_workers)

    old_correct = old.correct_ids()
    new_correct = new.correct_ids()
    broke = len(old_correct - new_correct)

    return GateResult(
        acc_old=old.accuracy, acc_new=new.accuracy, rho=rho,
        passed=new.accuracy >= old.accuracy - rho,
        batch_size=len(gate_batch), n_failures=len(failures),
        recovered_failures=recovered, broke=broke,
    )
