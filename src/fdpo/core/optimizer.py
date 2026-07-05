"""Whole-prompt bundle optimizer (v2, see Docs/fdpo_mechanism.md):

1. aggregate_failures() -- programmatic (non-LLM) evidence per section.
2. rewrite_prompt_bundle() -- ONE optimizer call proposing find/replace edits
   across every implicated section at once.
3. apply_edits() -- apply those edits to section text; an edit whose `find`
   doesn't match verbatim is skipped and logged, never crashes the run.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from dataclasses import dataclass, field

from fdpo.clients.base import ModelClient
from fdpo.data.loaders import Example
from fdpo.prompts.optimizer_prompt import build_optimizer_messages

logger = logging.getLogger("fdpo")

MAX_PARSE_RETRIES = 2
_FENCE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")
_WORD = re.compile(r"[a-zA-Z]{4,}")
_STOPWORDS = frozenset({
    "that", "this", "with", "from", "have", "which", "were", "what", "when",
    "does", "would", "could", "should", "there", "their", "about", "into",
    "than", "then", "them", "these", "those", "will", "your", "answer",
    "question", "following", "given",
})


def aggregate_failures(failures: list[dict]) -> dict:
    """Programmatic (non-LLM) evidence: error_type histogram + common keywords
    across the failing questions, so the optimizer sees the aggregate pattern,
    not just a handful of anecdotes."""
    error_type_counts = Counter(f["error_type"] for f in failures)
    words = Counter()
    for f in failures:
        for w in _WORD.findall(f["question"].lower()):
            if w not in _STOPWORDS:
                words[w] += 1
    common_keywords = [w for w, _ in words.most_common(5)]
    return {"error_type_counts": dict(error_type_counts),
           "common_keywords": common_keywords}


@dataclass
class EditResult:
    edits_applied: dict[str, str] = field(default_factory=dict)  # section -> new full text
    edit_log: list[dict] = field(default_factory=list)           # per-edit apply/skip record
    parse_failed: bool = False


def apply_edits(sections: dict[str, str], edits: list[dict]) -> EditResult:
    """Apply each {section, find, replace} edit via exact substring match.
    An edit whose `find` isn't a verbatim substring of that section's CURRENT
    (already-possibly-edited-this-bundle) text is skipped and logged, not
    treated as an error -- one bad edit never blocks the rest of the bundle.
    """
    working = dict(sections)
    touched: set[str] = set()
    log: list[dict] = []
    for e in edits:
        section, find, replace = e.get("section"), e.get("find", ""), e.get("replace", "")
        if section not in working:
            log.append({**e, "applied": False, "reason": "unknown or unflagged section"})
            continue
        if find not in working[section]:
            log.append({**e, "applied": False, "reason": "find not an exact substring"})
            continue
        working[section] = working[section].replace(find, replace, 1)
        touched.add(section)
        log.append({**e, "applied": True})
    return EditResult(edits_applied={s: working[s] for s in touched}, edit_log=log)


def rewrite_prompt_bundle(client: ModelClient,
                          implicated: dict[str, dict],
                          current_prompt: dict[str, str],
                          current_acc: float | None,
                          best_prompt: dict[str, str],
                          best_acc: float | None,
                          golds: list[Example],
                          history: list[dict],
                          schema: tuple[str, ...],
                          temperature: float = 0.3) -> EditResult:
    """One optimizer call -> parsed, validated edit list -> applied edits.
    Falls back to an empty EditResult (no-op this round) if the optimizer
    can't produce valid JSON after retries -- never crashes the run."""
    messages = build_optimizer_messages(implicated, current_prompt, current_acc,
                                        best_prompt, best_acc, golds, history, schema)

    for attempt in range(MAX_PARSE_RETRIES + 1):
        result = client.complete(messages, json_mode=True, temperature=temperature,
                                 max_tokens=1200, purpose="rewrite:bundle")
        text = _FENCE.sub("", result.text.strip()).strip()
        try:
            raw = json.loads(text)
            edits = raw.get("edits", [])
            if not isinstance(edits, list):
                raise ValueError("'edits' must be a list")
            for e in edits:
                if not isinstance(e, dict) or not {"section", "find", "replace"} <= set(e):
                    raise ValueError(f"malformed edit entry: {e!r}")
                if e["section"] not in implicated:
                    raise ValueError(f"edit targets unflagged section: {e['section']!r}")
            return apply_edits(current_prompt, edits)
        except (json.JSONDecodeError, ValueError) as exc:
            if attempt == MAX_PARSE_RETRIES:
                break
            logger.warning("optimizer JSON invalid (%s); retry %d", exc, attempt + 1)
            messages = messages + [
                {"role": "assistant", "content": result.text},
                {"role": "user", "content":
                    f"Your previous reply was invalid ({exc}). Return ONLY the JSON "
                    "object matching the schema in the system message."},
            ]

    logger.warning("optimizer parse failed after retries; no edits applied this round")
    return EditResult(parse_failed=True)
