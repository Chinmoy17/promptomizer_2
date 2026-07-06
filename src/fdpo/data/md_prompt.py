"""Markdown-native prompt storage: parse/serialize `## Section` files.

For the `simple_fdpo` method, prompts are stored as human-editable markdown
files under `prompts/<dataset>.md`. The LLM optimizer sees and edits the full
markdown as one document (not per-section find/replace).

Falls back to `seed_sections()` (Python dicts) if the markdown file doesn't
exist, so other datasets keep working without needing markdown files upfront.
"""

from __future__ import annotations

import re
from pathlib import Path

from fdpo.core.prompt import SCHEMA_5, SECTION_TITLES, render_system
from fdpo.prompts.seeds import seed_sections

DEFAULT_PROMPTS_ROOT = "prompts"

# Reverse map "System Role" -> "system_role" for parsing markdown headers.
_TITLE_TO_KEY = {v.lower(): k for k, v in SECTION_TITLES.items()}

_HEADER = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def parse_markdown(md: str) -> dict[str, str]:
    """Parse `## Section Title\\ntext...\\n## Next Section\\n...` into a
    section dict keyed by snake_case names. Ignores unrecognized headers."""
    result: dict[str, str] = {}
    matches = list(_HEADER.finditer(md))
    if not matches:
        raise ValueError("no `## Section` headers found in markdown")
    for i, m in enumerate(matches):
        title = m.group(1).strip().lower()
        key = _TITLE_TO_KEY.get(title)
        if key is None:
            # Unknown header — skip, but leave text pass-through-friendly
            continue
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        result[key] = md[start:end].strip()
    if not result:
        raise ValueError(
            "markdown parsed but no known section headers matched. "
            f"Expected any of: {sorted(_TITLE_TO_KEY)}"
        )
    return result


def to_markdown(sections: dict[str, str], schema: tuple[str, ...] = SCHEMA_5) -> str:
    """Serialize a sections dict back to markdown, ordered by `schema`."""
    ordered = {k: sections[k] for k in schema if k in sections}
    return render_system(ordered) + "\n"


def load_markdown_prompt(dataset: str,
                         prompts_root: str = DEFAULT_PROMPTS_ROOT,
                         schema: tuple[str, ...] = SCHEMA_5,
                         ) -> tuple[dict[str, str], str, Path | None]:
    """Return (sections_dict, raw_markdown, source_path).

    Priority:
      1. `prompts/<dataset>.md` if it exists (source_path set).
      2. Fallback: serialize `seed_sections(dataset, schema)` to markdown
         (source_path is None — no file was loaded).
    """
    md_path = Path(prompts_root) / f"{dataset}.md"
    if md_path.exists():
        md = md_path.read_text(encoding="utf-8")
        return parse_markdown(md), md, md_path
    seed = seed_sections(dataset, schema)
    md = to_markdown(seed, schema)
    return seed, md, None


def save_markdown_prompt(sections: dict[str, str], path: Path,
                         schema: tuple[str, ...] = SCHEMA_5) -> None:
    """Write sections to a markdown file (used by simple_loop for archive/active
    snapshots inside a run directory)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_markdown(sections, schema), encoding="utf-8")
