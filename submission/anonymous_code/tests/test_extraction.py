"""Answer extraction and verdict edge cases (table-driven, no network)."""

import pytest

from fdpo.data.extraction import (
    extract_gsm8k,
    extract_mc_letter,
    extract_yes_no,
    gsm8k_gold,
    is_correct,
    normalize_number,
)


@pytest.mark.parametrize("text,expected", [
    ("Step 1... Step 2...\n#### 42", "42"),
    ("#### 1,234", "1,234"),
    ("The answer is #### -3.5", "-3.5"),
    ("#### $72", "72"),
    ("So she has 18 eggs left. The total is 18.", "18"),  # fallback: last number
    ("No numbers here at all.", None),
])
def test_extract_gsm8k(text, expected):
    assert extract_gsm8k(text) == expected


def test_gsm8k_gold():
    ref = "She sells 16 - 3 - 4 = <<16-3-4=9>>9 eggs.\n#### 18"
    assert gsm8k_gold(ref) == "18"


@pytest.mark.parametrize("text,expected", [
    ("Answer: B", "B"),
    ("The answer is C.", "C"),
    ("answer: (D)", "D"),
    ("**Answer: A**", "A"),
    ("I believe the best option is B", "B"),  # fallback: standalone letter
    ("no letters here", None),
])
def test_extract_mc(text, expected):
    assert extract_mc_letter(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Answer: Yes", "Yes"),
    ("answer is no", "No"),
    ("Reasoning...\nAnswer: **No**", "No"),
    ("Yes, this is hearsay because...", "Yes"),  # fallback
    ("unclear", None),
])
def test_extract_yes_no(text, expected):
    assert extract_yes_no(text) == expected


def test_normalize_number():
    assert normalize_number("1,234") == 1234.0
    assert normalize_number("$72") == 72.0
    assert normalize_number("-3.5") == -3.5
    assert normalize_number("abc") is None
    assert normalize_number("") is None


@pytest.mark.parametrize("dataset,pred,gold,expected", [
    ("gsm8k", "42", "42", True),
    ("gsm8k", "42.0", "42", True),
    ("gsm8k", "1,234", "1234", True),
    ("gsm8k", "41", "42", False),
    ("gsm8k", None, "42", False),
    ("arc", "b", "B", True),
    ("mmlu", "A", "B", False),
    ("legalbench_hearsay", "yes", "Yes", True),
])
def test_is_correct(dataset, pred, gold, expected):
    assert is_correct(dataset, pred, gold) is expected


def test_subsample_deterministic():
    from fdpo.data.loaders import Example, subsample
    pool = [Example(id=str(i), question=f"q{i}", gold="A") for i in range(100)]
    a = subsample(pool, 10, seed=7)
    b = subsample(pool, 10, seed=7)
    c = subsample(pool, 10, seed=8)
    assert [e.id for e in a] == [e.id for e in b]
    assert [e.id for e in a] != [e.id for e in c]
    assert len(a) == 10
