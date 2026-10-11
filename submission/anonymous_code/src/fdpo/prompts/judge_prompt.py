"""Judge instruction templates: verdict + critique + section attribution."""

from __future__ import annotations

from fdpo.core.prompt import SECTION_TITLES, render_system

_JUDGE_SYSTEM = """You are a rigorous evaluator of LLM outputs. You are given:
1. the sectioned prompt that was used,
2. the input question,
3. the model's output,
4. the reference (gold) answer.

Return ONLY a JSON object with exactly these keys:
{schema_desc}

Rules:
- "critique": one or two sentences on WHY the output is wrong.
- "error_type": "MISSING" if required guidance/content was absent, "WRONG" if
  guidance was present but incorrect or misapplied, "CONFLICT" if two parts of
  the prompt or output contradict each other.
{attribution_rules}"""

_ATTRIBUTION_5 = """- "section": the ONE prompt section most responsible for the failure, as one of
  {section_names}, or "multiple" if several share responsibility, or "none" if
  the prompt is fine and the model simply erred.
- If "section" is "multiple", also include "sections": a JSON array of the
  responsible section names."""

_ATTRIBUTION_MONO = """- "section": always "full_prompt" (this prompt has a single section)."""


def build_judge_messages(sections: dict[str, str], question: str, output: str,
                         reference: str, schema: tuple[str, ...]) -> list[dict]:
    monolithic = len(schema) == 1
    if monolithic:
        schema_desc = '{"verdict": "correct"|"incorrect", "critique": "...", "section": "full_prompt", "error_type": "MISSING"|"WRONG"|"CONFLICT"}'
        attribution = _ATTRIBUTION_MONO
    else:
        names = ", ".join(f'"{name}"' for name in schema)
        schema_desc = '{"verdict": "correct"|"incorrect", "critique": "...", "section": "<name>"|"multiple"|"none", "error_type": "MISSING"|"WRONG"|"CONFLICT"}'
        attribution = _ATTRIBUTION_5.format(section_names=names)

    system = _JUDGE_SYSTEM.format(schema_desc=schema_desc,
                                  attribution_rules=attribution)
    titles = " / ".join(SECTION_TITLES.get(s, s) for s in schema)
    user = (
        f"PROMPT SECTIONS ({titles}):\n{render_system(sections)}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"MODEL OUTPUT:\n{output}\n\n"
        f"REFERENCE ANSWER:\n{reference}\n\n"
        "The output has been verified as INCORRECT. Diagnose it and return the JSON."
    )
    return [{"role": "system", "content": system},
            {"role": "user", "content": user}]
