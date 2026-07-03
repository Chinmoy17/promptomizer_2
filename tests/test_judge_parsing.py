"""Judge JSON parsing: valid, numeric sections, retry-then-recover, fallback."""

import json

from fdpo.clients.mock_client import MockModelClient
from fdpo.core.judge import judge_failure
from fdpo.core.prompt import SCHEMA_5, SCHEMA_MONOLITHIC

SECTIONS = {name: f"text of {name}" for name in SCHEMA_5}


def call(responses, schema=SCHEMA_5):
    client = MockModelClient(role="judge", responses=responses)
    return judge_failure(client, dict(list(SECTIONS.items())[: len(schema)]),
                         "q?", "wrong output", "gold", schema), client


def test_valid_json():
    r, _ = call([json.dumps({
        "verdict": "incorrect", "critique": "bad format",
        "section": "output_format", "error_type": "WRONG"})])
    assert r.section == "output_format"
    assert r.error_type == "WRONG"
    assert not r.parse_failed


def test_numeric_section_mapped_to_name():
    r, _ = call([json.dumps({
        "verdict": "incorrect", "critique": "x",
        "section": 4, "error_type": "MISSING"})])
    assert r.section == "constraints"  # 4th of SCHEMA_5


def test_multiple_with_named_sections():
    r, _ = call([json.dumps({
        "verdict": "incorrect", "critique": "x", "section": "multiple",
        "sections": ["context", "constraints", "not_a_section"],
        "error_type": "CONFLICT"})])
    assert r.section == "multiple"
    assert r.sections == ["context", "constraints"]


def test_malformed_then_recovered():
    good = json.dumps({"verdict": "incorrect", "critique": "x",
                       "section": "context", "error_type": "WRONG"})
    r, client = call(["this is not json {", good])
    assert r.section == "context"
    assert not r.parse_failed
    assert len(client.calls) == 2
    # the retry message includes the corrective instruction
    assert "valid" in client.calls[1][-1]["content"].lower()


def test_fallback_after_exhausted_retries():
    r, client = call(["not json", "still not json", "{bad}"])
    assert r.parse_failed
    assert r.section == "none"
    assert len(client.calls) == 3


def test_monolithic_schema():
    r, _ = call([json.dumps({
        "verdict": "incorrect", "critique": "x",
        "section": "full_prompt", "error_type": "WRONG"})],
        schema=SCHEMA_MONOLITHIC)
    assert r.section == "full_prompt"
