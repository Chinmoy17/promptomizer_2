"""Optimizer instruction template (v2): one call proposes targeted find/replace
edits across every implicated section at once -- see Docs/fdpo_mechanism.md.
"""

from __future__ import annotations

from fdpo.core.prompt import SECTION_TITLES, render_system
from fdpo.data.loaders import Example

_OPTIMIZER_SYSTEM = """You are an expert prompt engineer improving a sectioned prompt.

You are shown the complete current prompt, its recent performance history, and
evidence about which sections are causing failures right now. Propose a small
set of TARGETED EDITS -- not full rewrites -- that fix the failure patterns
while preserving everything that already works.

Rules:
- You may edit ONLY the sections listed under "SECTIONS TO FIX". Never touch
  any other section, even if you think it could also be improved.
- Each edit is a (find, replace) pair. "find" must be an EXACT, VERBATIM
  substring of that section's CURRENT text -- copy it character-for-character,
  including punctuation and capitalization. "replace" is the new text for
  that exact span.
- Prefer several small, surgical edits over one edit that replaces the whole
  section. If only one phrase is wrong, edit only that phrase.
- Address the failure patterns in the evidence below. Do not undo anything
  the "PREVIOUS BEST FULL PROMPT" was already getting right.
- Return ONLY a JSON object of this exact shape, no markdown fences, no
  commentary outside the JSON:
  {"edits": [{"section": "<name>", "find": "<exact substring>", "replace": "<new text>"}, ...]}
- If a section listed under "SECTIONS TO FIX" genuinely needs no change,
  omit it from "edits" entirely."""


def _render_full_prompt(sections: dict[str, str]) -> str:
    return render_system(sections)


def _render_aggregate(agg: dict) -> str:
    lines = []
    if agg.get("error_type_counts"):
        counts = ", ".join(f"{k}: {v}" for k, v in agg["error_type_counts"].items() if v)
        lines.append(f"Error type distribution: {counts}")
    if agg.get("common_keywords"):
        lines.append(f"Common keywords across failing questions: {', '.join(agg['common_keywords'])}")
    return "\n".join(lines) if lines else "(no aggregate pattern detected)"


def build_optimizer_messages(
    implicated: dict[str, dict],       # section -> {"failures": [...], "aggregate": {...}}
    current_prompt: dict[str, str],
    current_acc: float | None,
    best_prompt: dict[str, str],
    best_acc: float | None,
    golds: list[Example],
    history: list[dict],               # past round outcomes, most recent last
    schema: tuple[str, ...],
) -> list[dict]:
    sections_to_fix = ", ".join(f'"{name}"' for name in implicated)

    fix_blocks = []
    for name, data in implicated.items():
        title = SECTION_TITLES.get(name, name)
        fail_blocks = []
        for i, f in enumerate(data["failures"], 1):
            fail_blocks.append(
                f"  [Failure {i}] ({f['error_type']})\n"
                f"  Question: {f['question']}\n"
                f"  Model output: {f['output']}\n"
                f"  Judge critique: {f['critique']}"
            )
        fix_blocks.append(
            f"### {title} (\"{name}\")\n"
            f"Current text: {current_prompt[name]}\n"
            f"{_render_aggregate(data['aggregate'])}\n"
            + "\n".join(fail_blocks)
        )

    gold_blocks = [
        f"[Gold {i}]\nQuestion: {g.question}\nReference answer: {g.reference}"
        for i, g in enumerate(golds, 1)
    ]

    history_blocks = []
    for h in history[-1:] if not history else history:
        history_blocks.append(
            f"- Round {h['round']}: edited {h['sections']}, "
            f"{'COMMITTED' if h['passed'] else 'REJECTED'} "
            f"(acc {h['acc_old']:.3f} -> {h['acc_new']:.3f})"
        )
    history_text = "\n".join(history_blocks) if history_blocks else "(no prior rounds yet)"

    current_acc_text = f"{current_acc:.3f}" if current_acc is not None else "(not yet measured)"
    best_acc_text = f"{best_acc:.3f}" if best_acc is not None else "(not yet measured)"

    user = (
        f"CURRENT FULL PROMPT (validation accuracy: {current_acc_text}):\n"
        f"{_render_full_prompt(current_prompt)}\n\n"
        f"PREVIOUS BEST FULL PROMPT (validation accuracy: {best_acc_text}):\n"
        f"{_render_full_prompt(best_prompt)}\n\n"
        f"THIS RUN'S RECENT HISTORY:\n{history_text}\n\n"
        f"SECTIONS TO FIX (edit ONLY these: {sections_to_fix}):\n"
        + "\n\n".join(fix_blocks)
        + "\n\nGOLD EXAMPLES (solved correctly / reference answers):\n"
        + "\n\n".join(gold_blocks)
        + "\n\nPropose your edits now. Return only the JSON object."
    )
    return [{"role": "system", "content": _OPTIMIZER_SYSTEM},
            {"role": "user", "content": user}]
