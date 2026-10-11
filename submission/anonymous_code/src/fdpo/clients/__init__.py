"""Client factory: resolve a role to a live or mock client."""

from __future__ import annotations

from fdpo.clients.base import ChatResult, ModelClient
from fdpo.clients.mock_client import MockModelClient, dry_run_client
from fdpo.config import ExperimentConfig
from fdpo.utils.budget import BudgetGuard, TokenLedger

__all__ = ["ChatResult", "ModelClient", "MockModelClient", "make_client"]


def make_client(role: str, cfg: ExperimentConfig,
                ledger: TokenLedger | None = None,
                guard: BudgetGuard | None = None) -> ModelClient:
    if cfg.dry_run:
        return dry_run_client(role, ledger=ledger, guard=guard)
    from fdpo.clients.openai_client import OpenAICompatClient
    return OpenAICompatClient(cfg.roles[role], ledger=ledger, guard=guard)
