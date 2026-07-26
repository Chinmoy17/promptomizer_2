"""Experiment configuration: argparse for parameters, .env for model roles."""

from __future__ import annotations

import argparse
import os
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv

METHODS = ("zeroshot_cot", "fewshot_cot", "monolithic", "fdpo", "simple_fdpo")
DATASETS = ("gsm8k", "arc", "mmlu", "legalbench_hearsay", "legalbench_contract_nli")
ROLES = ("solver", "judge", "optimizer")


@dataclass(frozen=True)
class RoleConfig:
    """One LLM role (solver / judge / optimizer) resolved from .env."""

    role: str
    model: str
    base_url: str
    api_key: str
    api_version: str = ""  # set (non-empty) => Azure OpenAI, else plain OpenAI-compatible


def load_role(role: str) -> RoleConfig:
    """Resolve one role from .env.

    Per-role `{ROLE}_*` vars take priority; any left unset fall back to the
    shared `AZURE_OPENAI_*` vars, so one Azure deployment can back all three
    roles (solver/judge/optimizer) without repeating the same endpoint/key
    three times. `api_version` is the Azure marker: non-empty => use the
    `AzureOpenAI` client instead of plain `OpenAI` (see openai_client.py).
    """
    prefix = role.upper()
    model = (os.environ.get(f"{prefix}_MODEL")
             or os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", ""))
    base_url = (os.environ.get(f"{prefix}_BASE_URL")
                or os.environ.get("AZURE_OPENAI_ENDPOINT")
                or "https://api.openai.com/v1")
    api_key = (os.environ.get(f"{prefix}_API_KEY")
               or os.environ.get("AZURE_OPENAI_API_KEY", ""))
    api_version = (os.environ.get(f"{prefix}_API_VERSION")
                   or os.environ.get("AZURE_OPENAI_API_VERSION", ""))
    if not model:
        raise ValueError(
            f"{prefix}_MODEL (or AZURE_OPENAI_DEPLOYMENT_NAME) is not set. Copy "
            f".env.example to .env and fill in the {role} role (see README)."
        )
    return RoleConfig(role=role, model=model, base_url=base_url, api_key=api_key,
                       api_version=api_version)


@dataclass
class ExperimentConfig:
    method: str = "fdpo"
    dataset: str = "gsm8k"
    seed: int = 0

    # data
    n_train: int = 150
    n_test: int = 200
    n_shots: int = 4  # few-shot CoT exemplars

    # optimization (offline batch rounds; no online/tau mode yet)
    max_rounds: int = 5
    rho: float = 0.02          # regression gate: reject if acc_new < acc_old - rho
    eps: float = 0.01          # stabilization: |delta pool acc| < eps for 3 rounds
    n_fail: int = 100          # max failures shown to the optimizer per rewrite. Set high
                                # (100) so on our benchmark sizes (<=120 train) essentially
                                # ALL failures are shown — the optimizer needs to see the
                                # pattern of what the solver is actually getting wrong, not
                                # a small random subset. Kept as a soft cap so prompt size
                                # stays bounded for very large train batches.
    n_gold: int = 10           # correctly-solved exemplars shown alongside failures. 10 gives
                                # the optimizer a real sample of "what already works" to
                                # protect against; 3 (the paper default) is too few for the
                                # optimizer to reliably avoid breaking existing successes.
    tau: int = 5               # simple_fdpo: min failures on baseline batch to trigger
                                # one-shot optimization (paper's `|F_f| >= tau`).
    simple_max_rounds: int = 1 # simple_fdpo: max optimizer rounds. 1 = paper-faithful
                                # single-pass (backward compatible default). >1 wraps the
                                # loop with best-snapshot rescue: a round is committed only
                                # if it reduces the train failure count; a regressing round
                                # stops the loop and reverts to the best snapshot seen.
    accept_margin: float = 1.0 # simple_fdpo: leniency of the accept gate. After the rounds,
                                # ship the best STRUCTURED round if its train accuracy is
                                # >= baseline_acc - accept_margin, else revert to the seed.
                                # Default 1.0 = always ship the optimizer's best structured
                                # prompt (so you see it on the test set) rather than reverting
                                # to a bare seed. Set 0.0 for strict no-regression (ship only
                                # if the structured prompt beats/ties baseline on train).
    simple_val_frac: float = 0.35 # simple_fdpo: fraction of the train pool held out as a
                                # VALIDATION set. The optimizer mines failures from the mining
                                # set (1-frac); each candidate prompt is scored on the held-out
                                # validation set and the accept gate uses that validation
                                # accuracy. 0 disables the split (score in-sample on the mining
                                # set). The sealed TEST set is never touched here.
    val_size: int = 20         # size of the FIXED held-out validation slice, carved once
                                # from train at run start; used for every gate check and
                                # for full-prompt accuracy tracking (v2 mechanism -- replaces
                                # the old per-call resampled gate_batch_size)
    pool_cap: int = 200        # FIFO cap on the gold-example correct pool
    stagnation_limit: int = 3  # rounds with no committed bundle before best-snapshot restore
    history_window: int = 3    # how many past round outcomes the optimizer sees in context
    prompt_file: str = ""      # simple_fdpo: override the seed prompt path. Empty = use
                                # prompts/<dataset>.md. Set to run one dataset with an
                                # alternative seed (e.g. a deliberately vague prompt, to
                                # test whether the optimizer can bootstrap structure).

    # bookkeeping
    phase: str = "smoke"       # results/<phase>/<run_id>/. Default `smoke` is for
                                # exploratory/dev runs; use `main` for real, publishable
                                # experiments (see results/README.md for the scheme).
    early_stop: bool = True
    split_mode: str = "seeded"  # "seeded" (default, backward-compat) | "stratified".
                                 # Stratified: test set FIXED across seeds, stratified
                                 # by meta['slice'] (or gold as fallback). Strongly
                                 # recommended for legalbench_hearsay (5 semantic slices).

    # verdicts: "programmatic" = extracted answer vs gold; "llm" = trust the judge
    verdict_mode: str = "programmatic"

    # generation
    solver_max_tokens: int = 2048   # was 1024; raised because reasoning-heavy MMLU
                                     # subjects (professional_law, philosophy) truncate
                                     # before emitting the 'Answer: X' sentinel, causing
                                     # silent extraction failures counted as wrong.
    solver_temperature: float = 0.0
    optimizer_temperature: float = 0.7  # was 0.3 (v2 constraint for find/replace exact
                                         # substring reproduction). simple_fdpo returns
                                         # full markdown so that constraint is gone;
                                         # 0.7 matches ProTeGi / mid of literature norm
                                         # (OPRO/APE use 1.0). Higher temp is important
                                         # for multi-round: rounds 2/3 need to explore
                                         # genuinely different rewrites, not paraphrase
                                         # round 1's output.

    # budget
    budget_usd: float = 4.0    # per-run cap; <= 0 disables the guard
    price_in: float = 0.0      # $/M input-token fallback for unknown models
    price_out: float = 0.0     # $/M output-token fallback for unknown models

    # output

    results_root: str = "results"
    dataset_root: str = "Dataset"

    # concurrency
    max_workers: int = 8       # concurrent solver calls per eval batch (conservative default;
                                # bounded by the deployment's RPM, not just TPM)

    # testing / offline
    dry_run: bool = False      # use the mock client instead of real APIs

    roles: dict = field(default_factory=dict)  # role name -> RoleConfig (resolved)

    def to_dict(self) -> dict:
        d = asdict(self)
        # never persist API keys into config.json
        d["roles"] = {
            r: {"model": rc.model, "base_url": rc.base_url}
            for r, rc in self.roles.items()
        }
        return d


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Run one FDPO / baseline experiment (one method x dataset x seed)."
    )
    d = ExperimentConfig()
    p.add_argument("--method", choices=METHODS, default=d.method)
    p.add_argument("--dataset", choices=DATASETS, default=d.dataset)
    p.add_argument("--seed", type=int, default=d.seed)
    p.add_argument("--n-train", type=int, default=d.n_train)
    p.add_argument("--n-test", type=int, default=d.n_test)
    p.add_argument("--n-shots", type=int, default=d.n_shots)
    p.add_argument("--max-rounds", type=int, default=d.max_rounds)
    p.add_argument("--rho", type=float, default=d.rho)
    p.add_argument("--eps", type=float, default=d.eps)
    p.add_argument("--n-fail", type=int, default=d.n_fail)
    p.add_argument("--n-gold", type=int, default=d.n_gold)
    p.add_argument("--tau", type=int, default=d.tau,
                   help="simple_fdpo: min failures on the baseline batch "
                        "required to trigger a single-pass rewrite")
    p.add_argument("--simple-max-rounds", type=int, default=d.simple_max_rounds,
                   help="simple_fdpo: max optimizer rounds. 1 = paper-faithful "
                        "single-pass (default). >1 enables best-snapshot rescue: "
                        "a round is committed only if it reduces the train failure "
                        "count; a regressing round reverts to the best snapshot.")
    p.add_argument("--accept-margin", type=float, default=d.accept_margin,
                   help="simple_fdpo: gate leniency. Ship the best structured round "
                        "if its train acc >= baseline - margin. Default 1.0 = always "
                        "ship the optimizer's structured prompt; 0.0 = strict "
                        "no-regression (revert to seed unless structured beats baseline).")
    p.add_argument("--simple-val-frac", type=float, default=d.simple_val_frac,
                   help="simple_fdpo: fraction of train held out as a stratified "
                        "validation set for scoring candidate prompts and driving "
                        "the accept gate. Default 0.35. 0 disables the split (score "
                        "in-sample on the mining set).")
    p.add_argument("--val-size", type=int, default=d.val_size,
                   help="fixed held-out validation slice size (carved once from train)")
    p.add_argument("--pool-cap", type=int, default=d.pool_cap)
    p.add_argument("--stagnation-limit", type=int, default=d.stagnation_limit)
    p.add_argument("--history-window", type=int, default=d.history_window,
                   help="past round outcomes shown to the optimizer")
    p.add_argument("--prompt-file", default=d.prompt_file,
                   help="simple_fdpo: override seed prompt path (default "
                        "prompts/<dataset>.md). Use to run a dataset with an "
                        "alternative seed, e.g. a deliberately vague prompt.")
    p.add_argument("--no-early-stop", action="store_true")
    p.add_argument("--verdict-mode", choices=("programmatic", "llm"),
                   default=d.verdict_mode)
    p.add_argument("--solver-max-tokens", type=int, default=d.solver_max_tokens)
    p.add_argument("--solver-temperature", type=float, default=d.solver_temperature)
    p.add_argument("--optimizer-temperature", type=float,
                   default=d.optimizer_temperature)
    p.add_argument("--budget-usd", type=float, default=d.budget_usd,
                   help="per-run spend cap in USD; <= 0 disables the guard")
    p.add_argument("--price-in", type=float, default=d.price_in,
                   help="$/M input tokens for models missing from the price table")
    p.add_argument("--price-out", type=float, default=d.price_out,
                   help="$/M output tokens for models missing from the price table")
    p.add_argument("--phase", default=d.phase)
    p.add_argument("--split-mode", choices=("seeded", "stratified"),
                   default=d.split_mode,
                   help="'seeded' (default): random per-seed splits. "
                        "'stratified': test set FIXED across seeds, stratified "
                        "by meta['slice'] (or gold). Recommended for legalbench.")
    p.add_argument("--results-root", default=d.results_root)
    p.add_argument("--dataset-root", default=d.dataset_root,
                   help="folder holding committed Dataset/<name>/{train,test}.jsonl")
    p.add_argument("--dry-run", action="store_true",
                   help="use the mock client (no API calls, no cost)")
    p.add_argument("--max-workers", type=int, default=d.max_workers,
                   help="concurrent solver calls per eval batch")
    return p


def config_from_args(args: argparse.Namespace) -> ExperimentConfig:
    load_dotenv()
    cfg = ExperimentConfig(
        method=args.method,
        dataset=args.dataset,
        seed=args.seed,
        n_train=args.n_train,
        n_test=args.n_test,
        n_shots=args.n_shots,
        max_rounds=args.max_rounds,
        rho=args.rho,
        eps=args.eps,
        n_fail=args.n_fail,
        n_gold=args.n_gold,
        tau=args.tau,
        simple_max_rounds=args.simple_max_rounds,
        accept_margin=args.accept_margin,
        simple_val_frac=args.simple_val_frac,
        val_size=args.val_size,
        pool_cap=args.pool_cap,
        stagnation_limit=args.stagnation_limit,
        history_window=args.history_window,
        prompt_file=args.prompt_file,
        early_stop=not args.no_early_stop,
        verdict_mode=args.verdict_mode,
        solver_max_tokens=args.solver_max_tokens,
        solver_temperature=args.solver_temperature,
        optimizer_temperature=args.optimizer_temperature,
        budget_usd=args.budget_usd,
        price_in=args.price_in,
        price_out=args.price_out,
        phase=args.phase,
        results_root=args.results_root,
        dataset_root=args.dataset_root,
        split_mode=args.split_mode,
        dry_run=args.dry_run,
        max_workers=args.max_workers,
    )
    if not cfg.dry_run:
        cfg.roles = {role: load_role(role) for role in ROLES}
    return cfg
