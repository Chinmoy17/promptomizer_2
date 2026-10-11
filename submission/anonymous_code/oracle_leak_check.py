"""ORACLE / LEAKAGE DIAGNOSTIC -- NOT a valid held-out result.

Answers a specific curiosity question: if our LLM optimizer gets to see the
SEALED 64-item test set's OWN failures directly (the same information leak
Trace2Policy's human curator had when authoring Round 1 -- see their Appendix
H: "Round 1 added two refinements diagnosed from v1's iter-30 errors PLUS
Opus v1's heldout errors"), how much accuracy gain is achievable via an LLM
rewrite instead of a human writing rules?

This deliberately violates the project's core discipline (sealed test set,
touched only for measurement). The resulting "final" number is an OPTIMISTIC
CEILING under test-set exposure, not a generalization estimate. Do not report
this number as a legitimate FDPO result -- it exists only to quantify how
much of Trace2Policy's reported lift plausibly came from their leak, vs a
genuine mechanism improvement.

Usage:
    uv run python oracle_leak_check.py
"""
from __future__ import annotations

from dotenv import load_dotenv

from fdpo.clients import make_client
from fdpo.config import ExperimentConfig, load_role
from fdpo.core.prompt import SCHEMA_5
from fdpo.core.registry import PromptRegistry
from fdpo.core.simple_loop import bootstrap_registry_from_markdown, run_simple_optimization
from fdpo.data.loaders import load_splits
from fdpo.eval.evaluator import evaluate
from fdpo.prompts.seeds import seed_sections
from fdpo.utils.budget import BudgetGuard, TokenLedger
from fdpo.utils.io import atomic_write_json, ensure_run_dir, make_run_id
from fdpo.utils.log import setup_logging

cfg = ExperimentConfig(
    method="simple_fdpo", dataset="legalbench_hearsay", seed=42,
    n_train=30, n_test=64, split_mode="stratified",
    simple_max_rounds=2, simple_val_frac=0.0, accept_margin=0.0, tau=3,
    solver_temperature=0.0, optimizer_temperature=0.7,
    max_workers=3, budget_usd=2.0, phase="hearsay_ORACLE_LEAK_diagnostic",
    prompt_file="prompts/hearsay_oneliner.md",
)
load_dotenv()
cfg.roles = {role: load_role(role) for role in ("solver", "judge", "optimizer")}

# Same fixed (rng=0) stratified carve as the real run -- identical 64 items.
_, test = load_splits(cfg.dataset, cfg.n_train, cfg.n_test, cfg.seed,
                      split_mode=cfg.split_mode)

run_id = make_run_id(cfg.dataset, cfg.method, cfg.roles["solver"].model, cfg.seed)
run_dir = ensure_run_dir(cfg.results_root, cfg.phase, run_id)
logger = setup_logging(run_dir)
logger.warning("ORACLE/LEAKAGE DIAGNOSTIC RUN -- optimizer sees the sealed "
               "test set's own failures. NOT a valid held-out result.")

ledger = TokenLedger(csv_path=run_dir / "ledger.csv")
guard = BudgetGuard(cap_usd=cfg.budget_usd, ledger=ledger)
clients = {role: make_client(role, cfg, ledger=ledger, guard=guard)
           for role in ("solver", "judge", "optimizer")}

registry = PromptRegistry(SCHEMA_5, seed_sections(cfg.dataset, SCHEMA_5),
                          path=run_dir / "registry.json")
bootstrap_registry_from_markdown(cfg.dataset, run_dir, registry,
                                 prompt_file=cfg.prompt_file)

baseline = evaluate(clients["solver"], registry.active_prompt(), test, cfg.dataset,
                    temperature=cfg.solver_temperature,
                    max_tokens=cfg.solver_max_tokens, max_workers=cfg.max_workers)
logger.info("baseline accuracy on the 64 sealed items: %.4f (%d/%d)",
           baseline.accuracy, sum(r.correct for r in baseline.rows), len(baseline.rows))

# THE LEAK: pass the sealed 64 test items in as `train`, so the optimizer's
# failure evidence is drawn directly from the set we then re-score on.
summary = run_simple_optimization(cfg, registry, test, cfg.dataset,
                                  clients["solver"], clients["optimizer"], run_dir)

final = evaluate(clients["solver"], registry.active_prompt(), test, cfg.dataset,
                 temperature=cfg.solver_temperature,
                 max_tokens=cfg.solver_max_tokens, max_workers=cfg.max_workers)
logger.info("final (oracle) accuracy on the SAME 64 sealed items: %.4f (%d/%d)",
           final.accuracy, sum(r.correct for r in final.rows), len(final.rows))

atomic_write_json(run_dir / "oracle_summary.json", {
    "warning": "ORACLE/LEAKAGE DIAGNOSTIC -- not a valid held-out result",
    "baseline_accuracy": baseline.accuracy,
    "final_accuracy": final.accuracy,
    "delta_pp": (final.accuracy - baseline.accuracy) * 100,
    "n_items": len(test),
    "optimizer_calls": summary.get("optimizer_calls"),
    "rounds_log": summary.get("rounds_log"),
})
print(f"baseline: {baseline.accuracy:.4f}  final(oracle): {final.accuracy:.4f}  "
     f"delta: {(final.accuracy - baseline.accuracy) * 100:+.1f}pp  "
     f"spent ${ledger.spent_usd:.4f}")
