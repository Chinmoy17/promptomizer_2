"""Per-dataset answer extraction and programmatic verdicts.

Every extractor returns the predicted answer or None; None counts as
incorrect and is tallied as an extraction failure in metrics.
"""

from __future__ import annotations

import re

_GSM8K_FINAL = re.compile(r"####\s*\$?([-+]?[\d,]*\.?\d+)")
_ANY_NUMBER = re.compile(r"[-+]?\$?[\d,]*\.?\d+")
_MC_ANSWER = re.compile(r"[Aa]nswer\s*(?:is)?\s*:?\s*\**\(?([A-E])\)?\b")
_MC_STANDALONE = re.compile(r"\b([A-E])\b")
_YESNO_ANSWER = re.compile(r"[Aa]nswer\s*(?:is)?\s*:?\s*\**(Yes|No)\b", re.IGNORECASE)
_YESNO_STANDALONE = re.compile(r"\b(Yes|No)\b", re.IGNORECASE)


def normalize_number(s: str) -> float | None:
    s = s.strip().replace(",", "").replace("$", "")
    if not s or s in "+-.":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def extract_gsm8k(text: str) -> str | None:
    """Prefer the '#### <number>' final line; fall back to the last number."""
    m = _GSM8K_FINAL.search(text)
    if m:
        return m.group(1)
    numbers = [n for n in _ANY_NUMBER.findall(text) if normalize_number(n) is not None]
    return numbers[-1] if numbers else None


def gsm8k_gold(reference: str) -> str:
    """GSM8K references end with '#### <answer>'."""
    m = _GSM8K_FINAL.search(reference)
    if m:
        return m.group(1)
    return reference.strip()


def extract_mc_letter(text: str) -> str | None:
    m = _MC_ANSWER.search(text)
    if m:
        return m.group(1).upper()
    standalone = _MC_STANDALONE.findall(text)
    return standalone[-1].upper() if standalone else None


def extract_yes_no(text: str) -> str | None:
    m = _YESNO_ANSWER.search(text)
    if m:
        return m.group(1).capitalize()
    standalone = _YESNO_STANDALONE.findall(text)
    return standalone[0].capitalize() if standalone else None


def extract_pred(dataset: str, text: str) -> str | None:
    if dataset == "gsm8k":
        return extract_gsm8k(text)
    if dataset in ("arc", "mmlu"):
        return extract_mc_letter(text)
    if dataset == "legalbench_hearsay":
        return extract_yes_no(text)
    raise ValueError(f"unknown dataset: {dataset}")


def is_correct(dataset: str, pred: str | None, gold: str) -> bool:
    if pred is None:
        return False
    if dataset == "gsm8k":
        p, g = normalize_number(pred), normalize_number(gold)
        return p is not None and g is not None and abs(p - g) < 1e-6
    return pred.strip().lower() == gold.strip().lower()
