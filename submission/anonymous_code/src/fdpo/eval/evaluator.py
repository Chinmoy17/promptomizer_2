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
from fdpo.data.ifeval_verifiers import verify
from fdpo.data.loaders import VERIFIER_DATASETS, Example
from fdpo.data.pupa_pipeline import run_pupa_pipeline

DEFAULT_MAX_WORKERS = 1  # safe default: sequential unless a caller opts in.
# Callers with scripted/order-dependent mock responses (tests) must stay
# sequential; real runs pass cfg.max_workers explicitly (config.py default 8).

# PUPA's "correct" is a threshold on a CONTINUOUS composite score (see
# EvalRow.score / pupa_pipeline.py), not a natural boolean -- 0.7 is a
# pragmatic bar chosen so reflect_fdpo's existing boolean recovered/
# regressed bookkeeping keeps working unmodified. The real, reportable
# metric for PUPA is EvalResult.mean_score, not .accuracy.
PUPA_PASS_THRESHOLD = 0.7


@dataclass
class EvalRow:
    example_id: str
    pred: str | None
    gold: str
    correct: bool
    output: str
    blocked: bool = False   # provider refused (content filter) -> not evaluable
    detail: str = ""        # verifier datasets only: which instruction(s)
                             # failed and why (see fdpo.data.ifeval_verifiers);
                             # empty for every other dataset
    score: float = 1.0      # PUPA only: continuous composite (quality +
                             # (1-leakage))/2, so the real metric isn't lost
                             # to the boolean `correct` threshold. 1.0/0.0
                             # (mirroring `correct`) for every other dataset.


@dataclass
class EvalResult:
    rows: list[EvalRow]

    @property
    def n_blocked(self) -> int:
        return sum(1 for r in self.rows if r.blocked)

    @property
    def n_evaluated(self) -> int:
        """Rows that actually produced a scorable answer (total minus blocked)."""
        return len(self.rows) - self.n_blocked

    @property
    def accuracy(self) -> float:
        # Content-filter-blocked calls are NOT counted as wrong -- they are
        # excluded from the denominator (they were never evaluable).
        denom = self.n_evaluated
        return sum(r.correct for r in self.rows) / denom if denom else 0.0

    @property
    def mean_score(self) -> float:
        # The real, reportable metric for PUPA (continuous composite score);
        # identical to .accuracy for every other dataset (score mirrors
        # correct there), so this is always safe to read regardless of
        # dataset.
        denom = self.n_evaluated
        return (sum(r.score for r in self.rows if not r.blocked) / denom
                if denom else 0.0)

    @property
    def extraction_failures(self) -> int:
        # Genuine unparseable outputs only; a blocked call is not a parse failure.
        return sum(1 for r in self.rows if r.pred is None and not r.blocked)

    def correct_ids(self) -> set[str]:
        return {r.example_id for r in self.rows if r.correct}

    def wrong_ids(self) -> set[str]:
        # Excludes blocked calls -- they are not failures the optimizer can fix.
        return {r.example_id for r in self.rows if not r.correct and not r.blocked}

    def blocked_ids(self) -> set[str]:
        # Example IDs whose solver call the provider's content filter refused,
        # surfaced so the same rejected items can be tracked across the
        # baseline and final evaluations.
        return {r.example_id for r in self.rows if r.blocked}


def evaluate(solver: ModelClient, sections: dict[str, str],
             examples: list[Example], dataset: str, *,
             shots: list[tuple[str, str]] | None = None,
             temperature: float = 0.0, max_tokens: int = 1024,
             purpose: str = "eval",
             max_workers: int = DEFAULT_MAX_WORKERS,
             judge: ModelClient | None = None,
             external: ModelClient | None = None) -> EvalResult:
    """Runs the solver over every example. Calls are independent (same fixed
    `sections` prompt, no shared mutable state between examples) so they're
    dispatched across a bounded thread pool; ThreadPoolExecutor.map preserves
    input order in its output regardless of completion order, so rows line
    up with `examples` the same as the old sequential loop did.

    `judge`/`external` are only used for dataset == "pupa" (its 3-call
    pipeline; see pupa_pipeline.py) and are ignored otherwise -- every other
    dataset's single-call path is unchanged.
    """
    def _run_one(ex: Example) -> EvalRow:
        if dataset == "pupa":
            if judge is None or external is None:
                raise ValueError(
                    "dataset='pupa' requires both judge= and external= "
                    "clients to be passed to evaluate()")
            result = run_pupa_pipeline(
                solver, external, judge, sections, ex,
                temperature=temperature, max_tokens=max_tokens, purpose=purpose)
            return EvalRow(
                example_id=ex.id, pred=f"{result.score:.2f}", gold=ex.gold,
                correct=result.score >= PUPA_PASS_THRESHOLD,
                output=result.redacted_request, blocked=result.blocked,
                detail=result.detail, score=result.score)

        result = solver.complete(
            render_messages(sections, ex.question, shots=shots),
            temperature=temperature, max_tokens=max_tokens, purpose=purpose)
        if dataset in VERIFIER_DATASETS:
            # No extracted-answer-vs-gold match for this task family --
            # correctness is "every listed instruction's checker passes
            # against the raw response text" (see ifeval_verifiers.verify).
            passed, detail = verify(ex.meta.get("instruction_id_list", []),
                                    ex.meta.get("kwargs", []), result.text)
            return EvalRow(example_id=ex.id, pred=("PASS" if passed else "FAIL"),
                          gold=ex.gold, correct=passed, output=result.text,
                          blocked=result.blocked, detail=detail,
                          score=1.0 if passed else 0.0)
        pred = extract_pred(dataset, result.text)
        correct = is_correct(dataset, pred, ex.gold)
        return EvalRow(example_id=ex.id, pred=pred, gold=ex.gold,
                       correct=correct, output=result.text,
                       blocked=result.blocked, score=1.0 if correct else 0.0)

    workers = max(1, min(max_workers, len(examples))) if examples else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(_run_one, examples))
    return EvalResult(rows=rows)
