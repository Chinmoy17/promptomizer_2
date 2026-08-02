"""Aggregate metrics: standard (accuracy / EM / macro-F1) + novel FDPO metrics."""

from __future__ import annotations

from fdpo.eval.evaluator import EvalResult
from fdpo.utils.budget import TokenLedger


def macro_f1(preds: list[str | None], golds: list[str]) -> float:
    labels = sorted(set(golds))
    f1s = []
    for label in labels:
        tp = sum(1 for p, g in zip(preds, golds)
                 if g == label and p is not None and p.lower() == label.lower())
        fp = sum(1 for p, g in zip(preds, golds)
                 if g != label and p is not None and p.lower() == label.lower())
        fn = sum(1 for p, g in zip(preds, golds)
                 if g == label and (p is None or p.lower() != label.lower()))
        denom = 2 * tp + fp + fn
        f1s.append(2 * tp / denom if denom else 0.0)
    return sum(f1s) / len(f1s) if f1s else 0.0


def standard_metrics(dataset: str, result: EvalResult) -> dict:
    out = {
        "accuracy": result.accuracy,
        "n_examples": len(result.rows),
        "n_evaluated": result.n_evaluated,
        "n_blocked": result.n_blocked,
        "extraction_failures": result.extraction_failures,
    }
    if dataset == "gsm8k":
        out["exact_match"] = result.accuracy  # EM == accuracy for numeric EM
    if dataset == "legalbench_hearsay":
        out["macro_f1"] = macro_f1([r.pred for r in result.rows],
                                   [r.gold for r in result.rows])
    return out


def novel_metrics(rounds: list[dict], seed_acc: float, final_acc: float,
                  ledger: TokenLedger) -> dict:
    """The four FDPO-specific metrics, computed from per-rewrite gate records.

    rounds: one dict per attempted rewrite, with keys
        committed(bool), broke(int), batch_size(int),
        n_failures(int), recovered_failures(int)
    """
    committed = [r for r in rounds if r["committed"]]

    gated = [r for r in committed if r["batch_size"] > 0]
    regression_rate = (
        sum(r["broke"] / r["batch_size"] for r in gated) / len(gated)
        if gated else 0.0
    )

    total_failures = sum(r["n_failures"] for r in committed)
    attribution_acc = (
        sum(r["recovered_failures"] for r in committed) / total_failures
        if total_failures else None
    )

    # optimization overhead = judge + optimizer roles + gate-eval solver calls
    opt_cost = sum(
        e.cost_usd for e in ledger.entries
        if e.role in ("judge", "optimizer") or e.purpose.startswith("gate")
    )
    gain_pp = (final_acc - seed_acc) * 100
    cost_per_pp = opt_cost / gain_pp if gain_pp > 0 else None

    return {
        "regression_rate": regression_rate,
        "section_attribution_accuracy": attribution_acc,
        "cost_per_accuracy_point_usd": cost_per_pp,
        "optimization_cost_usd": round(opt_cost, 6),
        "n_rewrites_attempted": len(rounds),
        "n_commits": len(committed),
        "n_rollbacks": len(rounds) - len(committed),
    }
