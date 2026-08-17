"""Optimizer instruction template (v2): one call proposes targeted find/replace
edits across ANY section of the whole prompt. The optimizer sees every
section's verbatim current text; judge-flagged sections are shown with failure
evidence as *advisory* priorities, not as an edit restriction -- see
Docs/fdpo_mechanism.md.
"""

from __future__ import annotations

from fdpo.core.prompt import SECTION_TITLES, render_system
from fdpo.data.loaders import Example

_OPTIMIZER_SYSTEM = """You are an expert prompt engineer improving a sectioned prompt.

You are shown the complete current prompt, its recent performance history, and
evidence about which sections the judge attributed the current failures to.
Your task is to rewrite the prompt so it fixes the failing examples on this
dataset while preserving the ones that already work.

You have full-prompt flexibility: read the entire prompt as one artifact and
propose edits to ANY section (system_role, context, task_details, constraints,
output_format) if changing that section will help. The judge-flagged sections
under "PRIORITY EVIDENCE" are where failures were attributed, so start there,
but do not feel constrained -- if a fix genuinely belongs in a different
section (e.g. tightening the output_format, adding a clarification to the
context, or reframing the system_role), edit it.

Rules:
- Edit as few or as many sections as needed. Prefer the smallest set of
  changes that fixes the observed failures without regressing the working
  examples.
- Each edit is a (find, replace) pair. "find" must be an EXACT, VERBATIM
  substring of that section's CURRENT text -- copy it character-for-character,
  including punctuation and capitalization. "replace" is the new text for
  that exact span.
- Prefer several small, surgical edits over one edit that replaces the whole
  section. If only one phrase is wrong, edit only that phrase.
- Address the failure patterns in the evidence below. Do not undo anything
  the "PREVIOUS BEST FULL PROMPT" was already getting right.
- **Prefer scoped, narrow rules over broad single-keyword triggers.** A rule
  like "if the statement mentions X, it is not Y" tends to over-apply to
  unrelated cases that share the keyword X. Tie the rule to the underlying
  structural condition instead (e.g. "if the argument works even when the
  statement's content is false, it is not Y"). If you cannot phrase the
  condition narrowly, add a concrete clarifying example (both a positive and
  a negative case) rather than a broad rule.
- Return ONLY a JSON object of this exact shape, no markdown fences, no
  commentary outside the JSON:
  {"edits": [{"section": "<name>", "find": "<exact substring>", "replace": "<new text>"}, ...]}
  "section" must be one of the schema sections in the current prompt.
- If no change is genuinely warranted this round, return {"edits": []}."""


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
    schema_list = ", ".join(f'"{name}"' for name in schema)
    priority_sections = ", ".join(f'"{name}"' for name in implicated) or "(none this round)"

    fix_blocks = []
    for name in schema:
        title = SECTION_TITLES.get(name, name)
        header = f'### {title} ("{name}")\nCurrent text: {current_prompt[name]}'
        data = implicated.get(name)
        if not data:
            # Not flagged this round, but still fully editable -- show its
            # verbatim text so the optimizer can craft an exact find/replace.
            fix_blocks.append(header + "\n(no failures attributed to this section)")
            continue
        fail_blocks = []
        for i, f in enumerate(data["failures"], 1):
            fail_blocks.append(
                f"  [Failure {i}] ({f['error_type']})\n"
                f"  Question: {f['question']}\n"
                f"  Model output: {f['output']}\n"
                f"  Judge critique: {f['critique']}"
            )
        fix_blocks.append(
            header + "\n"
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
        f"EDITABLE SECTIONS (you may edit ANY of these): {schema_list}\n"
        f"Sections the judge attributed this round's failures to (advisory -- "
        f"start here, but edit wherever the real fix belongs): {priority_sections}\n\n"
        f"ALL PROMPT SECTIONS (verbatim current text; flagged sections also "
        f"include failure evidence):\n"
        + "\n\n".join(fix_blocks)
        + "\n\nGOLD EXAMPLES (solved correctly / reference answers):\n"
        + "\n\n".join(gold_blocks)
        + "\n\nPropose your edits now. Return only the JSON object."
    )
    return [{"role": "system", "content": _OPTIMIZER_SYSTEM},
            {"role": "user", "content": user}]
