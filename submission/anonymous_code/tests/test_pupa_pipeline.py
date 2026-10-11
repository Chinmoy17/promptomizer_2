"""Offline unit tests for PUPA's mechanical pieces (no API calls):
leakage fraction computation and quality-score parsing. The 3-call
pipeline itself (run_pupa_pipeline) is exercised end-to-end via the
dry-run smoke path in test_reflect_loop.py-style tests elsewhere.
"""

from fdpo.data.pupa_pipeline import compute_leakage, parse_quality_score


def test_compute_leakage_no_units():
    fraction, detail = compute_leakage("", "any redacted text")
    assert fraction == 0.0
    assert "no PII units" in detail


def test_compute_leakage_none_leaked():
    fraction, detail = compute_leakage("alice||acme corp", "a generic request")
    assert fraction == 0.0
    assert "no PII leaked" in detail


def test_compute_leakage_partial():
    fraction, detail = compute_leakage(
        "alice||acme corp||90210", "Alice works somewhere, no zip given")
    assert fraction == 1 / 3
    assert "1/3" in detail
    assert "alice" in detail.lower()


def test_compute_leakage_all_leaked_case_insensitive():
    fraction, _ = compute_leakage("Alice||ACME Corp", "alice works at acme corp")
    assert fraction == 1.0


def test_parse_quality_score_valid():
    assert parse_quality_score("Reasoning...\nScore: 0.8") == 0.8


def test_parse_quality_score_clamped_above_one():
    assert parse_quality_score("Score: 1.5") == 1.0


def test_parse_quality_score_missing_defaults_zero():
    assert parse_quality_score("The candidate response is fine.") == 0.0
