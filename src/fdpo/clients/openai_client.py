"""OpenAI-compatible client: OpenAI API, Azure OpenAI, vLLM, Ollama, TGI, Together, DeepSeek.

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
    AzureOpenAI,
    BadRequestError,
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


# Reasoning models (OpenAI o-series and gpt-5) reject `temperature` (only the
# default is allowed) and require `max_completion_tokens` in place of the now
# unsupported `max_tokens`. Detect them by model/deployment name so ordinary
# models (e.g. gpt-4o-mini) keep the classic parameters unchanged.
def _is_reasoning_model(model: str) -> bool:
    name = model.lower()
    return "gpt-5" in name or name.startswith(("o1", "o3", "o4"))


class OpenAICompatClient(ModelClient):
    def __init__(self, role_cfg: RoleConfig,
                 ledger: TokenLedger | None = None,
                 guard: BudgetGuard | None = None):
        super().__init__(role_cfg.role, role_cfg.model, ledger, guard)
        if role_cfg.api_version:
            # Azure OpenAI: needs api-version + azure_endpoint, and `model` below
            # is actually the deployment name, not the underlying model name.
            self._client = AzureOpenAI(
                azure_endpoint=role_cfg.base_url,
                api_key=role_cfg.api_key,
                api_version=role_cfg.api_version,
            )
        else:
            self._client = OpenAI(base_url=role_cfg.base_url, api_key=role_cfg.api_key)

    def _complete(self, messages: list[dict], *, json_mode: bool,
                  temperature: float, max_tokens: int) -> ChatResult:
        kwargs: dict = {"model": self.model, "messages": messages}
        if _is_reasoning_model(self.model):
            # o-series / gpt-5: temperature must stay default (omit it), and the
            # token cap moves to max_completion_tokens (shared with hidden
            # reasoning tokens).
            kwargs["max_completion_tokens"] = max_tokens
        else:
            kwargs["temperature"] = temperature
            kwargs["max_tokens"] = max_tokens
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
            except BadRequestError as e:
                # Azure content filter: return empty completion, treat as wrong.
                # Realistic behavior — we don't want one flagged prompt to abort
                # a whole eval on datasets like MMLU-professional_law.
                if getattr(e, "code", None) == "content_filter" or \
                   "content_filter" in str(e) or \
                   "content management policy" in str(e):
                    logger.warning("%s call blocked by content filter; "
                                   "returning empty completion", self.role)
                    return ChatResult(text="", prompt_tokens=0,
                                      completion_tokens=0, model=self.model,
                                      blocked=True)
                raise
            except RETRYABLE as e:
                if attempt == MAX_ATTEMPTS - 1:
                    raise
                delay = min(2 ** attempt * 2, 60) + random.uniform(0, 1)
                logger.warning("%s call failed (%s: %s); retry %d/%d in %.1fs",
                               self.role, type(e).__name__, e, attempt + 1,
                               MAX_ATTEMPTS - 1, delay)
                time.sleep(delay)
        raise RuntimeError("unreachable")
