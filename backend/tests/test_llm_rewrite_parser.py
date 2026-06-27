"""Tests for parse_rewrite_response — defensive parser for rewrite output."""
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response


def test_happy_path_plain_text():
    raw = "Đây là narration đã được rewrite cho TTS."
    out = parse_rewrite_response(raw, target_duration_sec=10.0, word_budget=20)
    assert out == "Đây là narration đã được rewrite cho TTS."


def test_strip_code_fences_triple_backtick():
    raw = "```\nHello narration here.\n```"
    assert parse_rewrite_response(raw, 5.0, 10) == "Hello narration here."


def test_strip_code_fences_with_lang_marker():
    raw = "```text\nHello narration.\n```"
    assert parse_rewrite_response(raw, 5.0, 10) == "Hello narration."


def test_strip_prose_prefix_narration_colon():
    # Single-pass regex strips one matched prefix; the parser is intentionally
    # conservative — Sacred #3 spirit: prefer keeping text over over-stripping.
    raw = "Narration: This is the actual content."
    out = parse_rewrite_response(raw, 5.0, 20)
    assert out == "This is the actual content."


def test_strip_prose_prefix_here_is_keeps_inner_text():
    # "Here is X" — first regex match strips "Here is ", leaving the rest.
    raw = "Here is the actual narration content."
    out = parse_rewrite_response(raw, 5.0, 20)
    assert out == "the actual narration content."


def test_reject_empty_string():
    assert parse_rewrite_response("", 5.0, 10) is None
    assert parse_rewrite_response("   \n  ", 5.0, 10) is None


def test_reject_whitespace_only_after_strip():
    raw = "```\n   \n```"
    assert parse_rewrite_response(raw, 5.0, 10) is None


def test_reject_over_2x_budget():
    raw = " ".join(["word"] * 50)
    assert parse_rewrite_response(raw, 5.0, word_budget=10) is None


def test_none_input_returns_none():
    assert parse_rewrite_response(None, 5.0, 10) is None  # type: ignore[arg-type]


def test_internal_whitespace_collapsed():
    raw = "Hello    world\n\n\nfoo"
    assert parse_rewrite_response(raw, 5.0, 20) == "Hello world foo"


def test_minimum_budget_floor():
    # word_budget=3, 2x cap=20 (max(20, ...) floor), so 15 words still accepted.
    raw = " ".join(["w"] * 15)
    out = parse_rewrite_response(raw, 1.0, word_budget=3)
    assert out == " ".join(["w"] * 15)
