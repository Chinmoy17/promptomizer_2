"""Tests for md_prompt: parse/serialize and load-with-fallback."""

from pathlib import Path

import pytest

from fdpo.core.prompt import SCHEMA_5
from fdpo.data.md_prompt import (load_markdown_prompt, parse_markdown,
                                  save_markdown_prompt, to_markdown)


def test_parse_valid_markdown_returns_snake_case_keys():
    md = """## System Role
You are an expert.

## Context
Some context.

## Task Details
Do the thing.

## Constraints
Only do X, not Y.

## Output Format
Answer: Yes or No
"""
    sections = parse_markdown(md)
    assert set(sections) == set(SCHEMA_5)
    assert sections["system_role"] == "You are an expert."
    assert sections["context"] == "Some context."
    assert sections["task_details"] == "Do the thing."
    assert sections["constraints"] == "Only do X, not Y."
    assert sections["output_format"] == "Answer: Yes or No"


def test_parse_case_insensitive_header_matching():
    md = "## SYSTEM ROLE\nExpert\n\n## output format\nAnswer: X"
    sections = parse_markdown(md)
    assert sections["system_role"] == "Expert"
    assert sections["output_format"] == "Answer: X"


def test_parse_unknown_headers_are_skipped_silently():
    md = ("## System Role\nExpert\n\n"
          "## Random Made-Up Header\nnoise\n\n"
          "## Task Details\nSolve it")
    sections = parse_markdown(md)
    assert "system_role" in sections
    assert "task_details" in sections
    assert "random_made_up_header" not in sections


def test_parse_no_headers_raises():
    with pytest.raises(ValueError, match="no `## Section` headers"):
        parse_markdown("Just some plain text with no headers.")


def test_parse_only_unknown_headers_raises():
    with pytest.raises(ValueError, match="no known section headers matched"):
        parse_markdown("## Foo\ntext\n\n## Bar\ntext")


def test_to_markdown_roundtrip():
    original = {
        "system_role": "Expert.",
        "context": "Some context.",
        "task_details": "Do it.",
        "constraints": "No Y.",
        "output_format": "Answer: X",
    }
    md = to_markdown(original)
    reparsed = parse_markdown(md)
    assert reparsed == original


def test_load_from_file_when_it_exists(tmp_path: Path):
    md_dir = tmp_path / "prompts"
    md_dir.mkdir()
    (md_dir / "legalbench_hearsay.md").write_text(
        "## System Role\nFrom file\n\n## Context\nctx\n\n"
        "## Task Details\ntask\n\n## Constraints\ncon\n\n"
        "## Output Format\nAnswer: Yes",
        encoding="utf-8",
    )
    sections, md, src = load_markdown_prompt("legalbench_hearsay", prompts_root=str(md_dir))
    assert src is not None
    assert sections["system_role"] == "From file"


def test_load_falls_back_to_python_seeds_when_no_file(tmp_path: Path):
    empty_dir = tmp_path / "prompts"
    empty_dir.mkdir()
    sections, md, src = load_markdown_prompt("gsm8k", prompts_root=str(empty_dir))
    assert src is None
    assert "system_role" in sections
    assert "output_format" in sections
    # Fallback still produces valid markdown
    reparsed = parse_markdown(md)
    assert set(reparsed) == set(SCHEMA_5)


def test_save_markdown_writes_correctly(tmp_path: Path):
    sections = {
        "system_role": "R", "context": "C", "task_details": "T",
        "constraints": "K", "output_format": "F",
    }
    out = tmp_path / "sub" / "out.md"
    save_markdown_prompt(sections, out)
    assert out.exists()
    reparsed = parse_markdown(out.read_text(encoding="utf-8"))
    assert reparsed == sections
