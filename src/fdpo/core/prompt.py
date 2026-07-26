"""Prompt schemas and rendering.

A prompt is an ordered dict of named sections. FDPO uses the MPO-aligned
5-section schema; monolithic-FDPO (ablation A1) uses a single section —
the same loop, registry, and gate operate on both.
"""

from __future__ import annotations

SCHEMA_5 = ("system_role", "context", "task_details", "constraints", "output_format")
SCHEMA_MONOLITHIC = ("full_prompt",)

SECTION_TITLES = {
    "system_role": "System Role",
    "context": "Context",
    "task_details": "Task Details",
    "constraints": "Constraints",
    "output_format": "Output Format",
    "full_prompt": "Instructions",
}


def render_system(sections: dict[str, str]) -> str:
    """Join active section texts into one system message, headed per section.

    Empty sections are skipped. A prompt with a single non-empty section (a
    vague one-liner baseline, before FDPO enriches it) renders as RAW TEXT with
    no `## header` scaffolding, so the baseline is a true headerless one-liner.
    Multi-section prompts -- the enriched FDPO output and full seed prompts --
    keep their `## Section` headers unchanged.
    """
    nonempty = [(name, text.strip()) for name, text in sections.items()
                if text.strip()]
    if len(nonempty) == 1:
        return nonempty[0][1]
    parts = []
    for name, body in nonempty:
        title = SECTION_TITLES.get(name, name.replace("_", " ").title())
        parts.append(f"## {title}\n{body}")
    return "\n\n".join(parts)


def render_messages(sections: dict[str, str], question: str,
                    shots: list[tuple[str, str]] | None = None) -> list[dict]:
    """Build chat messages: sectioned system prompt, optional few-shot pairs,
    then the user question."""
    messages: list[dict] = [{"role": "system", "content": render_system(sections)}]
    for shot_q, shot_a in shots or []:
        messages.append({"role": "user", "content": shot_q})
        messages.append({"role": "assistant", "content": shot_a})
    messages.append({"role": "user", "content": question})
    return messages


def monolithic_text(sections: dict[str, str]) -> str:
    """Concatenate a sectioned prompt into a single block (seed for A1)."""
    return "\n\n".join(text.strip() for text in sections.values())
