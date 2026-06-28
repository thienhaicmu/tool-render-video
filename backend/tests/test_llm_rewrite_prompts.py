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
    # Scaffolding is ~7KB now (added 11-tone multi-language table for en/vi/ja/ko).
    assert len(usr) < MAX_REWRITE_INPUT_CHARS + 8000


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


def test_prompt_includes_human_like_delivery_section():
    # Pins the HUMAN-LIKE DELIVERY block (Step A 2026-06-27): the LLM must
    # be instructed about breath cues, sentence variety, tone interpretation.
    _, usr = build_rewrite_prompt("Hello.", 10.0, "vi-VN", tone="gây cấn")
    assert "HUMAN-LIKE DELIVERY" in usr
    assert "BREATH CUES" in usr
    assert "SENTENCE VARIETY" in usr
    assert "TONE INTERPRETATION" in usr
    # Tone substitution still works at the bottom of the new section.
    assert "gây cấn" in usr


def test_system_prompt_mentions_human_like_speech():
    sys, _ = build_rewrite_prompt("Hi.", 5.0, "en-US")
    assert "SPEAK" in sys.upper() or "speaking" in sys.lower()
    assert "rhythm" in sys.lower() or "emphasis" in sys.lower()


# A2.1 + A2.2 (2026-06-28) — clip context wiring pins.

def test_clip_context_section_suppressed_when_all_empty():
    _, usr = build_rewrite_prompt("Hi.", 5.0, "en-US")
    assert "CLIP CONTEXT" not in usr


def test_clip_context_section_renders_when_fields_provided():
    _, usr = build_rewrite_prompt(
        "Hi.", 5.0, "vi-VN",
        content_type="vlog",
        hook_type="reveal",
        clip_title="Khoảnh khắc bất ngờ",
        target_platform="tiktok",
        part_idx=1,
        total_parts=3,
    )
    assert "CLIP CONTEXT" in usr
    assert "vlog" in usr.lower()
    assert "reveal" in usr.lower()
    assert "Khoảnh khắc bất ngờ" in usr
    assert "tiktok" in usr.lower()
    assert "FIRST clip" in usr


def test_clip_context_section_partial_fields():
    # Only content_type provided — only that line shows, no other CLIP CONTEXT noise.
    _, usr = build_rewrite_prompt(
        "Hi.", 5.0, "en-US",
        content_type="commentary",
    )
    assert "CLIP CONTEXT" in usr
    assert "commentary" in usr.lower()
    assert "HOOK ARCHETYPE" not in usr
    assert "PART POSITION" not in usr


def test_clip_context_position_last_clip_message():
    _, usr = build_rewrite_prompt(
        "Hi.", 5.0, "en-US",
        content_type="vlog",
        part_idx=3, total_parts=3,
    )
    assert "LAST clip" in usr


def test_clip_context_position_middle_clip_message():
    _, usr = build_rewrite_prompt(
        "Hi.", 5.0, "en-US",
        content_type="vlog",
        part_idx=2, total_parts=4,
    )
    assert "middle clip" in usr or "2/4" in usr


def test_select_prompt_video_meta_suppressed_when_zero():
    from app.features.render.ai.llm.prompts import build_render_plan_prompt
    _, usr = build_render_plan_prompt(
        srt_content="1\n00:00:00,000 --> 00:00:05,000\nhi\n",
        output_count=2, min_sec=15, max_sec=60,
    )
    assert "SOURCE META" not in usr


def test_select_prompt_video_meta_renders_when_provided():
    from app.features.render.ai.llm.prompts import build_render_plan_prompt
    _, usr = build_render_plan_prompt(
        srt_content="1\n00:00:00,000 --> 00:00:05,000\nhi\n",
        output_count=2, min_sec=15, max_sec=60,
        video_duration_sec=600.0,
    )
    assert "SOURCE META" in usr
    assert "10.0 minutes" in usr or "600s" in usr


def test_prompt_no_format_keyerror():
    # Format-safety regression guard — calling .format with the canonical
    # placeholder set must not raise. Any literal brace inside the template
    # would surface as a KeyError here.
    try:
        build_rewrite_prompt("Hello.", 10.0, "vi-VN", tone="x")
    except KeyError as exc:
        raise AssertionError(f"Template has literal brace: {exc}")
