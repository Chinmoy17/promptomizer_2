"""Section optimizer: one LLM call that rewrites the implicated section."""

from __future__ import annotations

import re

from fdpo.clients.base import ModelClient
from fdpo.data.loaders import Example
from fdpo.prompts.optimizer_prompt import build_optimizer_messages

_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")


def rewrite_section(client: ModelClient, section_name: str, section_text: str,
                    other_sections: dict[str, str], failures: list[dict],
                    golds: list[Example], temperature: float = 1.0) -> str:
    messages = build_optimizer_messages(section_name, section_text,
                                        other_sections, failures, golds)
    result = client.complete(messages, temperature=temperature,
                             max_tokens=600, purpose=f"rewrite:{section_name}")
    text = result.text.strip()
    text = _FENCE.sub("", text).strip()
    return text or section_text  # never commit an empty section
