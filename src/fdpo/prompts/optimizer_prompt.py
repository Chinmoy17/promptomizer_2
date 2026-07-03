"""Optimizer instruction template: rewrite exactly one prompt section."""

from __future__ import annotations

from fdpo.core.prompt import SECTION_TITLES
from fdpo.data.loaders import Example

_OPTIMIZER_SYSTEM = """You are an expert prompt engineer. You will improve exactly ONE section of a
sectioned prompt, using evidence from failed examples and correctly-solved gold
examples.

Rules:
- Rewrite ONLY the target section. Do not mention or restate other sections.
- Address the failure patterns in the critiques; keep what already works.
- Be concise and imperative. No meta-commentary.
- Return ONLY the new text of the section — no JSON, no markdown fences, no
  preamble like "Here is the new section"."""


def build_optimizer_messages(section_name: str, section_text: str,
                             other_sections: dict[str, str],
                             failures: list[dict],
                             golds: list[Example]) -> list[dict]:
    title = SECTION_TITLES.get(section_name, section_name)

    fail_blocks = []
    for i, f in enumerate(failures, 1):
        fail_blocks.append(
            f"[Failure {i}] ({f['error_type']})\n"
            f"Question: {f['question']}\n"
            f"Model output: {f['output']}\n"
            f"Judge critique: {f['critique']}"
        )
    gold_blocks = [
        f"[Gold {i}]\nQuestion: {g.question}\nReference answer: {g.reference}"
        for i, g in enumerate(golds, 1)
    ]
    context = "\n".join(
        f"- {SECTION_TITLES.get(n, n)}: {t}" for n, t in other_sections.items()
    ) or "(none — this is a single-section prompt)"

    user = (
        f"TARGET SECTION: {title}\n\n"
        f"CURRENT TEXT OF TARGET SECTION:\n{section_text}\n\n"
        f"OTHER SECTIONS (context only — do NOT rewrite these):\n{context}\n\n"
        f"FAILED EXAMPLES ATTRIBUTED TO THIS SECTION:\n" + "\n\n".join(fail_blocks)
        + "\n\nGOLD EXAMPLES (solved correctly / reference answers):\n"
        + "\n\n".join(gold_blocks)
        + f"\n\nRewrite the '{title}' section now. Return only its new text."
    )
    return [{"role": "system", "content": _OPTIMIZER_SYSTEM},
            {"role": "user", "content": user}]
