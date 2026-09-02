"""Unit tests for the IFEval/IFBench programmatic verifiers."""

from fdpo.data.ifeval_verifiers import (CHECKERS, describe_requirements,
                                        extract_scored_text, is_fully_covered,
                                        verify)


def test_is_fully_covered_true_when_all_known():
    assert is_fully_covered(["punctuation:no_comma", "startend:quotation"])


def test_is_fully_covered_false_when_unknown_present():
    assert not is_fully_covered(["punctuation:no_comma", "language:response_language"])


def test_no_comma_pass_and_fail():
    ok, why = CHECKERS["punctuation:no_comma"]("no commas here.", {})
    assert ok and why == ""
    ok, why = CHECKERS["punctuation:no_comma"]("oops, a comma.", {})
    assert not ok and "comma" in why


def test_number_words_at_least():
    ok, _ = CHECKERS["length_constraints:number_words"](
        "one two three", {"num_words": 3, "relation": "at least"})
    assert ok
    ok, why = CHECKERS["length_constraints:number_words"](
        "one two", {"num_words": 3, "relation": "at least"})
    assert not ok and "2 words" in why


def test_number_sentences_exactly():
    ok, _ = CHECKERS["length_constraints:number_sentences"](
        "One. Two. Three.", {"num_sentences": 3, "relation": "exactly"})
    assert ok
    ok, _ = CHECKERS["length_constraints:number_sentences"](
        "One. Two.", {"num_sentences": 3, "relation": "exactly"})
    assert not ok


def test_forbidden_words():
    ok, _ = CHECKERS["keywords:forbidden_words"](
        "a clean response", {"forbidden_words": ["banned"]})
    assert ok
    ok, why = CHECKERS["keywords:forbidden_words"](
        "this is banned content", {"forbidden_words": ["banned"]})
    assert not ok and "banned" in why


def test_keywords_existence_missing():
    ok, why = CHECKERS["keywords:existence"](
        "only apple here", {"keywords": ["apple", "banana"]})
    assert not ok and "banana" in why


def test_title_format():
    ok, _ = CHECKERS["detectable_format:title"]("<<My Title>>\nBody text.", {})
    assert ok
    ok, _ = CHECKERS["detectable_format:title"]("No title here.", {})
    assert not ok


def test_quotation():
    ok, _ = CHECKERS["startend:quotation"]('"wrapped in quotes"', {})
    assert ok
    ok, _ = CHECKERS["startend:quotation"]("not wrapped", {})
    assert not ok


def test_english_lowercase_and_capital():
    ok, _ = CHECKERS["change_case:english_lowercase"]("all lower case text", {})
    assert ok
    ok, _ = CHECKERS["change_case:english_lowercase"]("Has Capitals", {})
    assert not ok
    ok, _ = CHECKERS["change_case:english_capital"]("ALL CAPS TEXT", {})
    assert ok


def test_json_format():
    ok, _ = CHECKERS["detectable_format:json_format"]('{"a": 1}', {})
    assert ok
    ok, _ = CHECKERS["detectable_format:json_format"]("not json", {})
    assert not ok


def test_number_bullet_lists_exact():
    ok, _ = CHECKERS["detectable_format:number_bullet_lists"](
        "* one\n* two\n* three", {"num_bullets": 3})
    assert ok
    ok, _ = CHECKERS["detectable_format:number_bullet_lists"](
        "* one\n* two", {"num_bullets": 3})
    assert not ok


def test_verify_all_pass():
    passed, detail = verify(
        ["punctuation:no_comma", "change_case:english_lowercase"],
        [{}, {}],
        "no commas and all lowercase")
    assert passed and detail == ""


def test_verify_reports_each_failure():
    passed, detail = verify(
        ["punctuation:no_comma", "startend:quotation"],
        [{}, {}],
        "has a comma, and is not quoted")
    assert not passed
    assert "punctuation:no_comma" in detail
    assert "startend:quotation" in detail


def test_verify_unimplemented_checker_fails_closed():
    passed, detail = verify(["language:response_language"], [{}], "anything")
    assert not passed
    assert "no verifier implemented" in detail


def test_no_consecutive_repeats():
    ok, _ = CHECKERS["words:no_consecutive"]("the quick brown fox", {})
    assert ok
    ok, why = CHECKERS["words:no_consecutive"]("the the quick fox", {})
    assert not ok and "the" in why


def test_one_word_per_line():
    ok, _ = CHECKERS["format:newline"]("one\ntwo\nthree", {})
    assert ok
    ok, _ = CHECKERS["format:newline"]("one two\nthree", {})
    assert not ok


def test_options():
    ok, _ = CHECKERS["format:options"]("yes", {"options": "yes/no/maybe"})
    assert ok
    ok, _ = CHECKERS["format:options"]("maybe not", {"options": "yes/no/maybe"})
    assert not ok


def test_no_whitespace():
    ok, _ = CHECKERS["format:no_whitespace"]("nowhitespacehere", {})
    assert ok
    ok, _ = CHECKERS["format:no_whitespace"]("has whitespace", {})
    assert not ok


def test_paragraph_last_first_word():
    ok, _ = CHECKERS["words:paragraph_last_first"]("Start middle Start", {})
    assert ok
    ok, _ = CHECKERS["words:paragraph_last_first"]("Start middle End", {})
    assert not ok


def test_count_numbers_exact():
    ok, _ = CHECKERS["count:numbers"]("I have 3 apples and 5 oranges", {"N": 2})
    assert ok
    ok, why = CHECKERS["count:numbers"]("just one 1 number", {"N": 2})
    assert not ok and "found 1" in why


def test_unique_word_count():
    ok, _ = CHECKERS["count:unique_word_count"]("a b c d", {"N": 4})
    assert ok
    ok, _ = CHECKERS["count:unique_word_count"]("a a a a", {"N": 4})
    assert not ok


def test_pronoun_count():
    ok, _ = CHECKERS["count:pronouns"]("he told her that it was his", {"N": 3})
    assert ok
    ok, _ = CHECKERS["count:pronouns"]("no pronouns present anywhere", {"N": 1})
    assert not ok


def test_conjunction_count():
    ok, _ = CHECKERS["count:conjunctions"]("cats and dogs but not birds", {"small_n": 2})
    assert ok
    ok, _ = CHECKERS["count:conjunctions"]("cats dogs birds", {"small_n": 1})
    assert not ok


def test_word_count_range():
    ok, _ = CHECKERS["count:word_count_range"](
        "one two three four", {"min_words": 3, "max_words": 5})
    assert ok
    ok, _ = CHECKERS["count:word_count_range"](
        "one two", {"min_words": 3, "max_words": 5})
    assert not ok


def test_stop_word_ratio():
    ok, _ = CHECKERS["ratio:stop_words"]("Elephants trumpet loudly", {"percentage": 50})
    assert ok
    ok, _ = CHECKERS["ratio:stop_words"](
        "the a an of to in on the a an", {"percentage": 10})
    assert not ok


def test_sub_bullets():
    ok, _ = CHECKERS["format:sub-bullets"]("* point one\n- sub point\n* point two", {})
    assert ok
    ok, _ = CHECKERS["format:sub-bullets"]("* point one\n* point two", {})
    assert not ok


def test_consonant_clusters():
    ok, _ = CHECKERS["words:consonants"]("strong bright clock", {})
    assert ok
    ok, why = CHECKERS["words:consonants"]("a o i", {})
    assert not ok


def test_ifbench_coverage_is_nonzero():
    """Regression guard: this used to be 0/300 before the additional
    IFBench-specific checkers were added -- catches an accidental removal."""
    import json
    from pathlib import Path
    path = Path(__file__).parent.parent / "Dataset" / "ifbench" / "test.jsonl"
    if not path.exists():
        return  # dataset not downloaded in this environment; skip silently
    covered = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            if is_fully_covered(row["meta"]["instruction_id_list"]):
                covered += 1
    assert covered >= 50


def test_extract_scored_text_no_marker_returns_whole_text():
    text = "no commas here, just an answer"
    assert extract_scored_text(text) == text


def test_extract_scored_text_strips_reasoning_before_marker():
    text = ("Let me count words first: one two three.\n"
            "FINAL RESPONSE:\n"
            "one two three")
    assert extract_scored_text(text) == "one two three"


def test_extract_scored_text_is_case_insensitive_and_whitespace_tolerant():
    text = "thinking...\n  final response:  \nthe actual answer"
    assert extract_scored_text(text) == "the actual answer"


def test_extract_scored_text_uses_last_marker_if_repeated():
    text = "final response: not this one\nmore reasoning\nFINAL RESPONSE:\nreal answer"
    assert extract_scored_text(text) == "real answer"


def test_extract_scored_text_ignores_marker_phrase_inline_not_standalone():
    text = "I will now write my final response: here it is, with a comma"
    # "final response:" is not on its own line here, so nothing is stripped.
    assert extract_scored_text(text) == text


def test_verify_only_checks_text_after_marker():
    # Reasoning before the marker contains a comma; only the text after the
    # marker is checked, so this must PASS the no-comma constraint.
    response = "Let's see, I need to avoid commas.\nFINAL RESPONSE:\nno commas here"
    passed, detail = verify(["punctuation:no_comma"], [{}], response)
    assert passed and detail == ""


def test_verify_still_fails_when_violation_is_after_marker():
    response = "planning\nFINAL RESPONSE:\noops, a comma"
    passed, detail = verify(["punctuation:no_comma"], [{}], response)
    assert not passed and "comma" in detail


def test_describe_requirements_is_static_and_readable():
    text = describe_requirements(
        ["length_constraints:number_words"], [{"num_words": 300, "relation": "at least"}])
    assert text.startswith("Must satisfy:")
    assert "length_constraints:number_words" in text
    assert "300" in text
