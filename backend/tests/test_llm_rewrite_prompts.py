"""Tests for build_rewrite_prompt — word-budget math + format safety."""
from app.features.render.ai.llm.rewrite_prompts import (
    build_rewrite_prompt,
    _compute_word_budget,
    MAX_REWRITE_INPUT_CHARS,
)


def test_word_budget_vietnamese_30sec():
    # vi-VN @ 140 wpm × 30/60 = 70
    assert _compute_word_budget(30.0, "vi-VN") == 70


def test_word_budget_english_30sec():
    # en-US @ 150 wpm × 30/60 = 75
    assert _compute_word_budget(30.0, "en-US") == 75


def test_word_budget_japanese_60sec():
    # ja-JP @ 200 wpm × 1 = 200
    assert _compute_word_budget(60.0, "ja-JP") == 200


def test_word_budget_korean_15sec():
    # ko-KR @ 180 × 0.25 = 45
    assert _compute_word_budget(15.0, "ko-KR") == 45


def test_word_budget_english_gb_45sec():
    # en-GB @ 145 × 0.75 = 108.75 → 108
    assert _compute_word_budget(45.0, "en-GB") == 108


def test_word_budget_unknown_lang_default():
    # default = 150 wpm
    assert _compute_word_budget(60.0, "xx-XX") == 150


def test_word_budget_minimum_floor():
    assert _compute_word_budget(0.0, "en-US") >= 3


def test_word_budget_ceiling():
    assert _compute_word_budget(99999.0, "en-US") <= 800


def test_prompt_returns_tuple_str_str():
    sys, usr = build_rewrite_prompt("Hello world.", 10.0, "en-US")
    assert isinstance(sys, str) and isinstance(usr, str)
    assert len(sys) > 0 and len(usr) > 0


def test_prompt_contains_target_duration():
    _, usr = build_rewrite_prompt("Hello.", 42.0, "en-US")
    assert "42.0" in usr


def test_prompt_truncates_long_input():
    big = "x" * (MAX_REWRITE_INPUT_CHARS + 500)
    _, usr = build_rewrite_prompt(big, 10.0, "en-US")
    assert "[truncated]" in usr
    # User prompt body bounded by MAX_REWRITE_INPUT_CHARS + truncation marker + template scaffolding
    # Scaffolding is ~2KB (4 sections, 7 rules, language-name table, language style note).
    assert len(usr) < MAX_REWRITE_INPUT_CHARS + 3000


def test_prompt_default_tone_substituted():
    _, usr = build_rewrite_prompt("Hi.", 5.0, "en-US", tone="")
    assert "natural / informative" in usr


def test_prompt_custom_tone_substituted():
    _, usr = build_rewrite_prompt("Hi.", 5.0, "en-US", tone="dramatic")
    assert "dramatic" in usr


def test_prompt_includes_vietnamese_full_name_and_native_script():
    # Cross-language quality pin: prompt must name Vietnamese explicitly +
    # show native script so LLM doesn't write VN in romanised English.
    _, usr = build_rewrite_prompt("Hello world.", 10.0, "vi-VN")
    assert "Vietnamese" in usr
    assert "Tiếng Việt" in usr


def test_prompt_includes_japanese_full_name_and_native_script():
    _, usr = build_rewrite_prompt("Hello world.", 10.0, "ja-JP")
    assert "Japanese" in usr
    assert "日本語" in usr


def test_prompt_includes_translate_or_rewrite_decision_block():
    # Pins the STEP 2 decision tree exists (the explicit translate-or-rewrite
    # logic the LLM must follow when source != target language).
    _, usr = build_rewrite_prompt("Bonjour le monde.", 10.0, "vi-VN")
    assert "IF source language ==" in usr
    assert "IF source language !=" in usr
    assert "TRANSLATE + REWRITE" in usr


def test_prompt_no_format_keyerror():
    # Format-safety regression guard — calling .format with the canonical
    # placeholder set must not raise. Any literal brace inside the template
    # would surface as a KeyError here.
    try:
        build_rewrite_prompt("Hello.", 10.0, "vi-VN", tone="x")
    except KeyError as exc:
        raise AssertionError(f"Template has literal brace: {exc}")
