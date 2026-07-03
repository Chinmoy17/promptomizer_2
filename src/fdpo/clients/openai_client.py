"""OpenAI-compatible client: OpenAI API, vLLM, Ollama, TGI, Together, DeepSeek.

Sequential with exponential backoff — deliberate: basic API tiers, and
sequential calls keep the budget ledger and registry persistence trivially
correct. Parallelize test-set evaluation later only if wall-clock demands it.
"""

from __future__ import annotations

import logging
import random
import time

from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from fdpo.clients.base import ChatResult, ModelClient
from fdpo.config import RoleConfig
from fdpo.utils.budget import BudgetGuard, TokenLedger

logger = logging.getLogger("fdpo")

RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)
MAX_ATTEMPTS = 5


class OpenAICompatClient(ModelClient):
    def __init__(self, role_cfg: RoleConfig,
                 ledger: TokenLedger | None = None,
                 guard: BudgetGuard | None = None):
        super().__init__(role_cfg.role, role_cfg.model, ledger, guard)
        self._client = OpenAI(base_url=role_cfg.base_url, api_key=role_cfg.api_key)

    def _complete(self, messages: list[dict], *, json_mode: bool,
                  temperature: float, max_tokens: int) -> ChatResult:
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                usage = resp.usage
                return ChatResult(
                    text=resp.choices[0].message.content or "",
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    model=resp.model or self.model,
                )
            except RETRYABLE as e:
                if attempt == MAX_ATTEMPTS - 1:
                    raise
                delay = min(2 ** attempt * 2, 60) + random.uniform(0, 1)
                logger.warning("%s call failed (%s: %s); retry %d/%d in %.1fs",
                               self.role, type(e).__name__, e, attempt + 1,
                               MAX_ATTEMPTS - 1, delay)
                time.sleep(delay)
        raise RuntimeError("unreachable")
