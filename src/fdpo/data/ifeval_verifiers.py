"""Programmatic verifiers for IFEval/IFBench verifiable-instruction prompts.

Every example's `meta` carries `instruction_id_list` (which checks apply) and
`kwargs` (one parameter dict per instruction, same length/order). Correctness
for this task family is NOT "extracted answer == gold" -- there is no single
gold answer -- it is "every listed instruction's checker function passes
against the raw response text".

Real data across both downloaded files (`Dataset/ifeval`, `Dataset/ifbench`)
spans 83 distinct instruction types. This module implements a REAL SUBSET --
the ~18 highest-frequency, mechanically unambiguous types (see CHECKERS) --
not the full taxonomy (some types need genuine NLP, e.g. `language:
response_language` needs language detection, `words:odd_even_syllables`
needs a syllable counter; these are deliberately not implemented rather than
faked).

`is_fully_covered()` filters the loaded pool (see loaders.py) to only
examples where EVERY listed instruction has an implemented checker, so every
example that actually gets run is scored by logic we are confident is
correct -- nothing is silently guessed at or defaulted to "wrong".
"""

from __future__ import annotations

import json
import re
from typing import Callable

Checker = Callable[[str, dict], tuple[bool, str]]  # (response, kwargs) -> (passed, reason_if_failed)

# Unlike every other dataset in this project (which extracts one final answer
# line and ignores everything before it), IFEval/IFBench check the ENTIRE raw
# response against the constraints -- there is no built-in extraction step.
# That means a solver that reasons out loud before answering corrupts its own
# word count / forbidden-word / format checks with its own reasoning text.
# This marker gives the solver an explicit, optional way to separate planning
# from the graded content, mirroring the "Answer: X" convention used
# elsewhere: text before the LAST standalone "FINAL RESPONSE:" line is
# ignored; only the text after it is checked. If the marker never appears,
# the entire response is checked, unchanged from before this existed.
_FINAL_RESPONSE_MARKER = re.compile(r"(?im)^[ \t]*final response[ \t]*:[ \t]*$")


def extract_scored_text(raw: str) -> str:
    matches = list(_FINAL_RESPONSE_MARKER.finditer(raw))
    if not matches:
        return raw
    return raw[matches[-1].end():].lstrip("\n")


def _words(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s]


def _paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _cmp(n: int, relation: str | None, target: int) -> bool:
    relation = (relation or "at least").lower()
    if relation in ("at least", ">="):
        return n >= target
    if relation in ("at most", "<="):
        return n <= target
    if relation in ("exactly", "=="):
        return n == target
    if relation == "around":
        return abs(n - target) <= max(1, round(target * 0.1))
    return n >= target  # conservative default for an unrecognized relation


def _no_comma(r: str, kw: dict) -> tuple[bool, str]:
    ok = "," not in r
    return ok, "" if ok else "response contains a comma"


def _number_words(r: str, kw: dict) -> tuple[bool, str]:
    n = len(_words(r))
    target = int(kw.get("num_words") or 0)
    ok = _cmp(n, kw.get("relation"), target)
    return ok, "" if ok else (f"produced {n} words, need "
                              f"{kw.get('relation', 'at least')} {target}")


def _number_sentences(r: str, kw: dict) -> tuple[bool, str]:
    n = len(_sentences(r))
    target = int(kw.get("num_sentences") or 0)
    ok = _cmp(n, kw.get("relation"), target)
    return ok, "" if ok else (f"produced {n} sentences, need "
                              f"{kw.get('relation', 'at least')} {target}")


def _forbidden_words(r: str, kw: dict) -> tuple[bool, str]:
    words = [w.lower() for w in (kw.get("forbidden_words") or [])]
    low = r.lower()
    hit = [w for w in words if re.search(rf"\b{re.escape(w)}\b", low)]
    ok = not hit
    return ok, "" if ok else f"used forbidden word(s): {', '.join(hit)}"


def _number_highlighted_sections(r: str, kw: dict) -> tuple[bool, str]:
    n = len(re.findall(r"\*[^*\n]+\*", r))
    target = int(kw.get("num_highlights") or 0)
    ok = n >= target
    return ok, "" if ok else f"found {n} *highlighted* sections, need at least {target}"


def _keyword_frequency(r: str, kw: dict) -> tuple[bool, str]:
    keyword = (kw.get("keyword") or "").lower()
    n = len(re.findall(rf"\b{re.escape(keyword)}\b", r.lower())) if keyword else 0
    target = int(kw.get("frequency") or 0)
    ok = _cmp(n, kw.get("relation"), target)
    return ok, "" if ok else (f"keyword '{keyword}' appeared {n} times, need "
                              f"{kw.get('relation', 'at least')} {target}")


def _repeat_prompt(r: str, kw: dict) -> tuple[bool, str]:
    prompt = (kw.get("prompt_to_repeat") or "").strip()
    ok = bool(prompt) and prompt in r
    return ok, "" if ok else "did not repeat the original prompt verbatim"


def _quotation(r: str, kw: dict) -> tuple[bool, str]:
    t = r.strip()
    ok = len(t) >= 2 and t[0] == '"' and t[-1] == '"'
    return ok, "" if ok else "response is not wrapped in double quotes"


def _english_lowercase(r: str, kw: dict) -> tuple[bool, str]:
    letters = re.findall(r"[A-Za-z]", r)
    ok = bool(letters) and all(c.islower() for c in letters)
    return ok, "" if ok else "response contains uppercase letters"


def _english_capital(r: str, kw: dict) -> tuple[bool, str]:
    letters = re.findall(r"[A-Za-z]", r)
    ok = bool(letters) and all(c.isupper() for c in letters)
    return ok, "" if ok else "response contains lowercase letters"


def _keywords_existence(r: str, kw: dict) -> tuple[bool, str]:
    keywords = [k.lower() for k in (kw.get("keywords") or [])]
    low = r.lower()
    missing = [k for k in keywords if not re.search(rf"\b{re.escape(k)}\b", low)]
    ok = not missing
    return ok, "" if ok else f"missing required keyword(s): {', '.join(missing)}"


def _title(r: str, kw: dict) -> tuple[bool, str]:
    ok = bool(re.search(r"<<[^<>\n]+>>", r))
    return ok, "" if ok else "missing a title wrapped in << >>"


def _postscript(r: str, kw: dict) -> tuple[bool, str]:
    marker = kw.get("postscript_marker") or "P.S."
    ok = marker in r
    return ok, "" if ok else f"missing a postscript starting with '{marker}'"


def _end_checker(r: str, kw: dict) -> tuple[bool, str]:
    phrase = (kw.get("end_phrase") or "").strip()
    ok = bool(phrase) and r.strip().endswith(phrase)
    return ok, "" if ok else f"response does not end with the exact phrase '{phrase}'"


def _number_placeholders(r: str, kw: dict) -> tuple[bool, str]:
    n = len(re.findall(r"\[[^\[\]\n]+\]", r))
    target = int(kw.get("num_placeholders") or 0)
    ok = n >= target
    return ok, "" if ok else f"found {n} [placeholder] spans, need at least {target}"


def _number_paragraphs(r: str, kw: dict) -> tuple[bool, str]:
    n = len(_paragraphs(r))
    target = int(kw.get("num_paragraphs") or 0)
    ok = n == target
    return ok, "" if ok else f"produced {n} paragraphs, need exactly {target}"


def _two_responses(r: str, kw: dict) -> tuple[bool, str]:
    ok = "******" in r
    return ok, "" if ok else "missing the required 6-asterisk (******) separator between two responses"


def _json_format(r: str, kw: dict) -> tuple[bool, str]:
    t = r.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n|\n```$", "", t)
    try:
        json.loads(t)
        return True, ""
    except (ValueError, TypeError):
        return False, "response is not valid JSON"


def _number_bullet_lists(r: str, kw: dict) -> tuple[bool, str]:
    n = len(re.findall(r"^\s*[*\-]\s+", r, re.MULTILINE))
    target = int(kw.get("num_bullets") or 0)
    ok = n == target
    return ok, "" if ok else f"found {n} bullet points, need exactly {target}"


_PRONOUNS = frozenset("""i me my mine myself you your yours yourself yourselves he him his
himself she her hers herself it its itself we us our ours ourselves they
them their theirs themselves who whom whose this that these those""".split())

_CONJUNCTIONS = frozenset("""and but or nor for yet so although because since unless while
whereas though if until after before when whenever wherever whether""".split())

# Standard English stop words (Van Rijsbergen-style short list) -- used only
# for ratio:stop_words; a fixed, defensible list, not a claim of matching any
# specific upstream implementation exactly.
_STOP_WORDS = frozenset("""a an the and or but if then else when at by for with about
against between into through during before after above below to from up down
in out on off over under again further once here there all any both each
few more most other some such no nor not only own same so than too very is
are was were be been being have has had do does did will would should can
could may might must shall of as it its this that these those i you he she
we they""".split())


def _consonant_clusters_ok(r: str, kw: dict) -> tuple[bool, str]:
    """Best-effort interpretation of "each word must contain at least one
    consonant cluster (two or more consecutive consonants)" -- observed
    verbatim in the IFBench prompt text for this instruction id."""
    words = [w for w in _words(r) if w.isalpha()]
    bad = [w for w in words if not re.search(r"[bcdfghjklmnpqrstvwxyz]{2,}", w.lower())]
    ok = bool(words) and not bad
    return ok, "" if ok else f"word(s) without a 2+ consonant cluster: {', '.join(bad[:5])}"


def _no_consecutive_repeats(r: str, kw: dict) -> tuple[bool, str]:
    words = [w.lower() for w in _words(r)]
    for a, b in zip(words, words[1:]):
        if a == b:
            return False, f"word '{a}' repeated consecutively"
    return True, ""


def _one_word_per_line(r: str, kw: dict) -> tuple[bool, str]:
    lines = [ln.strip() for ln in r.strip().splitlines() if ln.strip()]
    bad = [ln for ln in lines if len(ln.split()) != 1]
    ok = bool(lines) and not bad
    return ok, "" if ok else "found a line with more/fewer than one word"


def _options(r: str, kw: dict) -> tuple[bool, str]:
    opts = [o.strip().lower() for o in (kw.get("options") or "").split("/") if o.strip()]
    ok = bool(opts) and r.strip().lower() in opts
    return ok, "" if ok else f"response must be exactly one of: {kw.get('options')}"


def _no_whitespace(r: str, kw: dict) -> tuple[bool, str]:
    ok = not any(c.isspace() for c in r)
    return ok, "" if ok else "response contains whitespace"


def _paragraph_last_first_word(r: str, kw: dict) -> tuple[bool, str]:
    bad = []
    for p in _paragraphs(r):
        w = _words(p)
        if not w or w[0].lower() != w[-1].lower():
            bad.append(p[:40])
    ok = not bad
    return ok, "" if ok else "a paragraph's first and last word do not match"


def _count_numbers(r: str, kw: dict) -> tuple[bool, str]:
    n = len(re.findall(r"\b\d+\b", r))
    target = int(kw.get("N") or 0)
    ok = _cmp(n, kw.get("relation") or "exactly", target)
    return ok, "" if ok else f"found {n} numbers, need exactly {target}"


def _unique_word_count(r: str, kw: dict) -> tuple[bool, str]:
    n = len({w.lower() for w in _words(r)})
    target = int(kw.get("N") or 0)
    ok = n >= target
    return ok, "" if ok else f"found {n} unique words, need at least {target}"


def _pronoun_count(r: str, kw: dict) -> tuple[bool, str]:
    n = sum(1 for w in _words(r) if w.lower() in _PRONOUNS)
    target = int(kw.get("N") or 0)
    ok = n >= target
    return ok, "" if ok else f"found {n} pronouns, need at least {target}"


def _conjunction_count(r: str, kw: dict) -> tuple[bool, str]:
    n = sum(1 for w in _words(r) if w.lower() in _CONJUNCTIONS)
    target = int(kw.get("small_n") or 0)
    ok = n >= target
    return ok, "" if ok else f"found {n} conjunctions, need at least {target}"


def _word_count_range(r: str, kw: dict) -> tuple[bool, str]:
    n = len(_words(r))
    lo, hi = kw.get("min_words"), kw.get("max_words")
    ok = (lo is None or n >= lo) and (hi is None or n <= hi)
    return ok, "" if ok else f"found {n} words, need between {lo} and {hi}"


def _stop_word_ratio(r: str, kw: dict) -> tuple[bool, str]:
    words = _words(r)
    if not words:
        return False, "empty response"
    pct = 100.0 * sum(1 for w in words if w.lower() in _STOP_WORDS) / len(words)
    target = float(kw.get("percentage") or 100.0)
    ok = pct <= target
    return ok, "" if ok else f"stop words are {pct:.0f}% of response, need at most {target:.0f}%"


def _sub_bullets(r: str, kw: dict) -> tuple[bool, str]:
    lines = r.splitlines()
    n_bullets = sum(1 for ln in lines if re.match(r"^\s*\*\s+", ln))
    has_sub = any(re.match(r"^\s*-\s+", ln) for ln in lines)
    ok = n_bullets > 0 and has_sub
    return ok, "" if ok else "missing '*' bullet points and/or a '-' sub-bullet under each"


CHECKERS: dict[str, Checker] = {
    "punctuation:no_comma": _no_comma,
    "length_constraints:number_words": _number_words,
    "length_constraints:number_sentences": _number_sentences,
    "keywords:forbidden_words": _forbidden_words,
    "detectable_format:number_highlighted_sections": _number_highlighted_sections,
    "keywords:frequency": _keyword_frequency,
    "combination:repeat_prompt": _repeat_prompt,
    "startend:quotation": _quotation,
    "change_case:english_lowercase": _english_lowercase,
    "change_case:english_capital": _english_capital,
    "keywords:existence": _keywords_existence,
    "detectable_format:title": _title,
    "detectable_content:postscript": _postscript,
    "startend:end_checker": _end_checker,
    "detectable_content:number_placeholders": _number_placeholders,
    "length_constraints:number_paragraphs": _number_paragraphs,
    "combination:two_responses": _two_responses,
    "detectable_format:json_format": _json_format,
    "detectable_format:number_bullet_lists": _number_bullet_lists,
    # -- IFBench-specific additions (grounded in observed prompt phrasing;
    # see the coverage-scoping conversation for confidence notes on each) --
    "words:consonants": _consonant_clusters_ok,
    "words:no_consecutive": _no_consecutive_repeats,
    "format:newline": _one_word_per_line,
    "format:options": _options,
    "format:no_whitespace": _no_whitespace,
    "words:paragraph_last_first": _paragraph_last_first_word,
    "count:numbers": _count_numbers,
    "count:unique_word_count": _unique_word_count,
    "count:pronouns": _pronoun_count,
    "count:conjunctions": _conjunction_count,
    "count:word_count_range": _word_count_range,
    "ratio:stop_words": _stop_word_ratio,
    "format:sub-bullets": _sub_bullets,
}


def is_fully_covered(instruction_id_list: list[str]) -> bool:
    return all(iid in CHECKERS for iid in instruction_id_list)


def describe_requirements(instruction_id_list: list[str], kwargs_list: list[dict]) -> str:
    """Static, human-readable summary of what a response must satisfy --
    used as the example's `reference` field (shown for correctly-solved
    gold examples). Does not depend on any particular solver output."""
    parts = []
    for iid, kw in zip(instruction_id_list, kwargs_list):
        set_params = {k: v for k, v in (kw or {}).items() if v is not None}
        parts.append(iid + (f" ({set_params})" if set_params else ""))
    return "Must satisfy: " + "; ".join(parts)


def verify(instruction_id_list: list[str], kwargs_list: list[dict],
          response: str) -> tuple[bool, str]:
    """Run every listed checker against `response`. Returns (all_passed,
    detail) -- detail is a "; "-joined list of which instructions failed and
    why, empty string if everything passed.

    Only the text after the last standalone "FINAL RESPONSE:" line (if any)
    is checked -- see extract_scored_text()."""
    response = extract_scored_text(response)
    reasons = []
    for iid, kw in zip(instruction_id_list, kwargs_list):
        checker = CHECKERS.get(iid)
        if checker is None:
            # Should not occur if the pool was filtered by is_fully_covered()
            # -- fail closed (never silently pass) if it ever does.
            reasons.append(f"{iid}: no verifier implemented")
            continue
        ok, why = checker(response, kw or {})
        if not ok:
            reasons.append(f"{iid}: {why}")
    return (len(reasons) == 0), "; ".join(reasons)
