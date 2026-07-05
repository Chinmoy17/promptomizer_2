"""Experiment configuration: argparse for parameters, .env for model roles."""

from __future__ import annotations

import argparse
import os
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv

METHODS = ("zeroshot_cot", "fewshot_cot", "monolithic", "fdpo")
DATASETS = ("gsm8k", "arc", "mmlu", "legalbench_hearsay")
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
    n_fail: int = 5            # failure examples fed to the optimizer per rewrite
    n_gold: int = 3            # gold exemplars fed to the optimizer per rewrite
    gate_batch_size: int = 20  # previously-correct examples per gate evaluation
    pool_cap: int = 200        # FIFO cap on the gate's correct pool
    stagnation_limit: int = 3  # stagnant rounds before best-snapshot restore
    early_stop: bool = True

    # verdicts: "programmatic" = extracted answer vs gold; "llm" = trust the judge
    verdict_mode: str = "programmatic"

    # generation
    solver_max_tokens: int = 1024
    solver_temperature: float = 0.0
    optimizer_temperature: float = 1.0

    # budget
    budget_usd: float = 4.0    # per-run cap; <= 0 disables the guard
    price_in: float = 0.0      # $/M input-token fallback for unknown models
    price_out: float = 0.0     # $/M output-token fallback for unknown models

    # output
    phase: str = "00_smoke"
    results_root: str = "results"
    dataset_root: str = "Dataset"

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
    p.add_argument("--gate-batch-size", type=int, default=d.gate_batch_size)
    p.add_argument("--pool-cap", type=int, default=d.pool_cap)
    p.add_argument("--stagnation-limit", type=int, default=d.stagnation_limit)
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
    p.add_argument("--results-root", default=d.results_root)
    p.add_argument("--dataset-root", default=d.dataset_root,
                   help="folder holding committed Dataset/<name>/{train,test}.jsonl")
    p.add_argument("--dry-run", action="store_true",
                   help="use the mock client (no API calls, no cost)")
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
        gate_batch_size=args.gate_batch_size,
        pool_cap=args.pool_cap,
        stagnation_limit=args.stagnation_limit,
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
        dry_run=args.dry_run,
    )
    if not cfg.dry_run:
        cfg.roles = {role: load_role(role) for role in ROLES}
    return cfg
