"""LLM judge: parse + validate the attribution JSON, retrying on bad output."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from fdpo.clients.base import ModelClient
from fdpo.prompts.judge_prompt import build_judge_messages

logger = logging.getLogger("fdpo")

ERROR_TYPES = ("MISSING", "WRONG", "CONFLICT")
MAX_PARSE_RETRIES = 2


@dataclass
class JudgeResult:
    verdict: str                 # "correct" | "incorrect"
    critique: str
    section: str                 # section name | "multiple" | "none"
    error_type: str              # MISSING | WRONG | CONFLICT
    sections: list[str] = field(default_factory=list)  # named when "multiple"
    parse_failed: bool = False


def _validate(raw: dict, schema: tuple[str, ...]) -> JudgeResult:
    verdict = str(raw.get("verdict", "incorrect")).lower()
    if verdict not in ("correct", "incorrect"):
        raise ValueError(f"bad verdict: {verdict!r}")

    section = raw.get("section", "none")
    if isinstance(section, int) or (isinstance(section, str) and section.isdigit()):
        idx = int(section) - 1
        if not 0 <= idx < len(schema):
            raise ValueError(f"section index out of range: {section!r}")
        section = schema[idx]
    section = str(section).strip().lower()
    if section not in (*schema, "multiple", "none"):
        raise ValueError(f"unknown section: {section!r}")

    error_type = str(raw.get("error_type", "WRONG")).upper()
    if error_type not in ERROR_TYPES:
        raise ValueError(f"bad error_type: {error_type!r}")

    named = []
    if section == "multiple":
        named = [str(s).strip().lower() for s in raw.get("sections", [])]
        named = [s for s in named if s in schema]

    return JudgeResult(verdict=verdict, critique=str(raw.get("critique", "")),
                       section=section, error_type=error_type, sections=named)


def judge_failure(client: ModelClient, sections: dict[str, str], question: str,
                  output: str, reference: str,
                  schema: tuple[str, ...]) -> JudgeResult:
    """Diagnose one incorrect output. Falls back to section='none' if the judge
    can't produce valid JSON after retries (logged, counted, never crashes)."""
    messages = build_judge_messages(sections, question, output, reference, schema)

    for attempt in range(MAX_PARSE_RETRIES + 1):
        result = client.complete(messages, json_mode=True, temperature=0.0,
                                 max_tokens=400, purpose="judge")
        try:
            return _validate(json.loads(result.text), schema)
        except (json.JSONDecodeError, ValueError) as e:
            if attempt == MAX_PARSE_RETRIES:
                break
            logger.warning("judge JSON invalid (%s); retry %d", e, attempt + 1)
            messages = messages + [
                {"role": "assistant", "content": result.text},
                {"role": "user", "content":
                    f"Your previous reply was invalid ({e}). Return ONLY a valid "
                    "JSON object matching the schema in the system message."},
            ]

    logger.warning("judge parse failed after retries; treating as section='none'")
    return JudgeResult(verdict="incorrect", critique="", section="none",
                       error_type="WRONG", parse_failed=True)
