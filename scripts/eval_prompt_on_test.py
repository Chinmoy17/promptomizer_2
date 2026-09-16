"""Evaluate one fixed prompt file against a dataset's TEST split only --
no mining/validation split, no optimization rounds, no duplicate seed+final
eval. For re-checking an already-optimized prompt (e.g. after raising
--solver-max-tokens to remove truncation) without the full reflect_fdpo
pipeline's overhead.

Accepts the same CLI flags as scripts.run_experiment (reuses the identical
arg parser / config / client-construction / eval logic, so results are
directly comparable), but only ever calls `evaluate()` once, on `test`.

Usage:
    uv run python -m scripts.eval_prompt_on_test --dataset aime \
        --prompt-file results/reflect_aime_gpt41mini_v3/.../prompt_current.md \
        --n-train 90 --n-test 30 --seed 0 --solver-max-tokens 24000 \
        --budget-usd 5.0 --phase reflect_aime_gpt41mini_v3_recheck
"""

from __future__ import annotations

import sys

from fdpo.clients import make_client
from fdpo.config import build_arg_parser, config_from_args
from fdpo.core.prompt import SCHEMA_5
from fdpo.data.loaders import load_splits
from fdpo.data.md_prompt import load_markdown_prompt
from fdpo.eval.evaluator import evaluate
from fdpo.utils.budget import BudgetGuard, TokenLedger
from fdpo.utils.io import CsvAppender, atomic_write_json, ensure_run_dir, make_run_id

EVAL_LOG_FIELDS = ["example_id", "correct", "pred", "gold", "blocked"]


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    cfg = config_from_args(args)

    run_id = make_run_id(cfg.dataset, "eval_only", cfg.roles["solver"].model, cfg.seed)
    run_dir = ensure_run_dir(cfg.results_root, cfg.phase, run_id)

    ledger = TokenLedger(fallback_price=(cfg.price_in, cfg.price_out),
                         csv_path=run_dir / "ledger.csv")
    guard = BudgetGuard(cap_usd=cfg.budget_usd, ledger=ledger)
    solver = make_client("solver", cfg, ledger=ledger, guard=guard)

    _, test = load_splits(cfg.dataset, cfg.n_train, cfg.n_test, cfg.seed,
                          dataset_root=cfg.dataset_root,
                          split_mode=cfg.split_mode, subjects=cfg.subjects)
    print(f"loaded {len(test)} test examples (dataset={cfg.dataset}, seed={cfg.seed}, "
         f"split_mode={cfg.split_mode})")

    sections, _, source = load_markdown_prompt(
        cfg.dataset, schema=SCHEMA_5, override_path=cfg.prompt_file)
    print(f"prompt source: {source}")

    result = evaluate(solver, sections, test, cfg.dataset,
                      temperature=cfg.solver_temperature,
                      max_tokens=cfg.solver_max_tokens,
                      purpose="eval_only", max_workers=cfg.max_workers)

    eval_log = CsvAppender(run_dir / "eval_log.csv", EVAL_LOG_FIELDS)
    for row in result.rows:
        eval_log.append({"example_id": row.example_id, "correct": row.correct,
                         "pred": row.pred, "gold": row.gold, "blocked": row.blocked})

    n_correct = sum(r.correct for r in result.rows)
    print(f"accuracy: {result.accuracy:.3f} ({n_correct}/{result.n_evaluated} correct, "
         f"{result.n_blocked} blocked, {result.extraction_failures} extraction failures)")
    print(f"spend: ${ledger.spent_usd:.4f}")

    atomic_write_json(run_dir / "metrics.json", {
        "dataset": cfg.dataset, "prompt_file": cfg.prompt_file, "prompt_source": str(source),
        "n_train": cfg.n_train, "n_test": cfg.n_test, "seed": cfg.seed,
        "split_mode": cfg.split_mode, "solver_max_tokens": cfg.solver_max_tokens,
        "solver_temperature": cfg.solver_temperature,
        "accuracy": result.accuracy, "n_correct": n_correct,
        "n_evaluated": result.n_evaluated, "n_blocked": result.n_blocked,
        "extraction_failures": result.extraction_failures,
        "spent_usd": ledger.spent_usd,
    })
    print(f"wrote {run_dir}")


if __name__ == "__main__":
    main(sys.argv[1:])
