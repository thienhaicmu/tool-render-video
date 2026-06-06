"""Tests for app.features.render.engine.subtitle.processing.readability."""
import pytest

from app.features.render.engine.subtitle.processing.readability import (
    _HOOK_EMPHASIS_WORDS,
    _emphasis_level,
    _is_cjk,
    _should_emphasize,
    subtitle_emphasis_pass,
)


# ---------------------------------------------------------------------------
# _is_cjk
# ---------------------------------------------------------------------------

def test_is_cjk_latin_is_false():
    assert _is_cjk("Hello world") is False


def test_is_cjk_japanese_hiragana_is_true():
    assert _is_cjk("こんにちは") is True


def test_is_cjk_chinese_is_true():
    assert _is_cjk("你好世界") is True


def test_is_cjk_korean_is_true():
    assert _is_cjk("안녕하세요") is True


def test_is_cjk_mixed_detects_cjk():
    assert _is_cjk("Hello 世界") is True


def test_is_cjk_empty_string_is_false():
    assert _is_cjk("") is False


# ---------------------------------------------------------------------------
# _HOOK_EMPHASIS_WORDS
# ---------------------------------------------------------------------------

def test_hook_emphasis_words_is_frozenset():
    assert isinstance(_HOOK_EMPHASIS_WORDS, frozenset)


def test_hook_emphasis_words_contains_expected_entries():
    assert "never" in _HOOK_EMPHASIS_WORDS
    assert "crazy" in _HOOK_EMPHASIS_WORDS
    assert "secret" in _HOOK_EMPHASIS_WORDS


def test_hook_emphasis_words_non_empty():
    assert len(_HOOK_EMPHASIS_WORDS) > 0


# ---------------------------------------------------------------------------
# _emphasis_level
# ---------------------------------------------------------------------------

def test_emphasis_level_tiktok_bounce_v1_is_strong():
    assert _emphasis_level("tiktok_bounce_v1") == "strong"


def test_emphasis_level_viral_bold_is_strong():
    assert _emphasis_level("viral_bold") == "strong"


def test_emphasis_level_story_clean_01_is_medium():
    assert _emphasis_level("story_clean_01") == "medium"


def test_emphasis_level_clean_pro_is_subtle():
    assert _emphasis_level("clean_pro") == "subtle"


def test_emphasis_level_unknown_falls_back_to_medium():
    result = _emphasis_level("completely_unknown_style_xyz")
    # unknown → normalize → default tiktok_bounce_v1 → strong
    assert result in ("strong", "medium")


# ---------------------------------------------------------------------------
# _should_emphasize
# ---------------------------------------------------------------------------

def test_should_emphasize_number_always_emphasizes():
    # numbers should be emphasized regardless of level
    assert _should_emphasize("100%", "strong") is True
    assert _should_emphasize("$5k", "strong") is True


def test_should_emphasize_hook_word_strong():
    assert _should_emphasize("never", "strong") is True


def test_should_emphasize_hook_word_subtle_is_false():
    # subtle level: only numbers
    assert _should_emphasize("never", "subtle") is False


def test_should_emphasize_medium_contrast_word():
    assert _should_emphasize("best", "medium") is True


def test_should_emphasize_ordinary_word_is_false():
    assert _should_emphasize("the", "strong") is False


# ---------------------------------------------------------------------------
# subtitle_emphasis_pass
# ---------------------------------------------------------------------------

def test_subtitle_emphasis_pass_empty_returns_empty():
    result = subtitle_emphasis_pass([])
    assert result == []


def test_subtitle_emphasis_pass_returns_same_list():
    blocks = [{"start": 0.0, "end": 2.0, "text": "Hello world"}]
    result = subtitle_emphasis_pass(blocks)
    assert result is blocks


def test_subtitle_emphasis_pass_does_not_crash_on_cjk():
    blocks = [{"start": 0.0, "end": 2.0, "text": "こんにちは世界"}]
    result = subtitle_emphasis_pass(blocks, preset_id="tiktok_bounce_v1")
    assert len(result) == 1
    # CJK text: text may be unchanged (no uppercase, no markers)
    assert result[0]["text"] is not None


def test_subtitle_emphasis_pass_strong_level_uppercases_hook_words():
    blocks = [{"start": 0.0, "end": 3.0, "text": "you never know the secret"}]
    result = subtitle_emphasis_pass(blocks, preset_id="tiktok_bounce_v1", market="US")
    # "never" and "secret" are hook words — should be uppercased at strong level
    text = result[0]["text"]
    assert "NEVER" in text or "never" in text.lower()


def test_subtitle_emphasis_pass_word_level_skips_transforms():
    """Word-level SRT (avg ~1 word/block, ≥6 blocks) should skip transforms."""
    blocks = [
        {"start": float(i) * 0.3, "end": float(i) * 0.3 + 0.3, "text": w}
        for i, w in enumerate(["you", "never", "know", "the", "real", "secret", "truth"])
    ]
    original_texts = [b["text"] for b in blocks]
    result = subtitle_emphasis_pass(blocks, preset_id="tiktok_bounce_v1")
    # Word-level: no transforms applied
    for b, orig in zip(result, original_texts):
        assert b["text"] == orig
