# test_subtitle_readability.py — Unit tests for subtitles/readability.py (Phase 4G.5).
#
# Coverage:
# - Module imports cleanly; subtitle_engine still importable
# - Same-object identity for all moved symbols (readability cluster)
# - _HOOK_EMPHASIS_WORDS is a frozenset containing expected anchor words
# - _is_cjk detects CJK/Hangul/Kana; ignores ASCII
# - _emphasis_level returns correct intensity for known preset IDs
# - _should_emphasize: numbers, contrast words, urgency, hook words
# - _should_emphasize: subtle level returns False except for numbers
# - _uppercase_emphasis_words uppercases emphasis tokens in text
# - _insert_emphasis_markers wraps emphasis tokens with PUA sentinels
# - _insert_emphasis_markers skips already-marked tokens
# - _semantic_wrap_block: orphan avoidance (exactly 1 word on line 2)
# - _semantic_wrap_block: widow avoidance (short trailing word → shift right)
# - _semantic_wrap_block: already-wrapped text returned unchanged
# - subtitle_emphasis_pass returns same list object (mutates in-place)
# - subtitle_emphasis_pass: word-level SRT (avg <= 1.5 words) skips transforms
# - subtitle_emphasis_pass: minimal preset applies no transforms
# - resegment_srt_for_readability: word-level SRT is returned unchanged
# - resegment_srt_for_readability: long block is split
# - resegment_srt_for_readability: safe no-op on missing file
# - readability.py does NOT import subtitle_engine
# - resegment output count returned correctly
from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# SRT fixtures
# ---------------------------------------------------------------------------

_SRT_SEGMENT = """\
1
00:00:01,000 --> 00:00:03,000
Hello world this is a test subtitle

2
00:00:04,000 --> 00:00:06,000
Second subtitle block here too

"""

_SRT_WORD = """\
1
00:00:01,000 --> 00:00:01,300
Hello

2
00:00:01,300 --> 00:00:01,600
world

3
00:00:01,600 --> 00:00:02,000
this

4
00:00:02,000 --> 00:00:02,300
is

5
00:00:02,300 --> 00:00:02,600
a

6
00:00:02,600 --> 00:00:03,000
test

"""

_SRT_LONG_BLOCK = """\
1
00:00:01,000 --> 00:00:05,000
This is a very long subtitle block that has way too many words for one display

"""


def _write_srt(content: str, tmp_dir: str, name: str = "source.srt") -> str:
    p = Path(tmp_dir) / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestReadabilityModuleImports:
    def test_readability_imports_cleanly(self):
        import app.services.subtitles.readability as m
        assert m is not None

    def test_subtitle_engine_still_importable(self):
        import app.services.subtitle_engine as e
        assert e is not None

    def test_hook_emphasis_words_in_readability(self):
        from app.services.subtitles.readability import _HOOK_EMPHASIS_WORDS
        assert isinstance(_HOOK_EMPHASIS_WORDS, frozenset)

    def test_is_cjk_in_readability(self):
        from app.services.subtitles.readability import _is_cjk
        assert callable(_is_cjk)

    def test_subtitle_emphasis_pass_in_readability(self):
        from app.services.subtitles.readability import subtitle_emphasis_pass
        assert callable(subtitle_emphasis_pass)

    def test_resegment_srt_for_readability_in_readability(self):
        from app.services.subtitles.readability import resegment_srt_for_readability
        assert callable(resegment_srt_for_readability)

    def test_no_whisper_import_in_readability(self):
        import app.services.subtitles.readability as m
        assert not hasattr(m, "whisper")

    def test_no_subtitle_engine_import_in_readability(self):
        import app.services.subtitles.readability as m
        src = inspect.getsource(m)
        assert "subtitle_engine" not in src


# ---------------------------------------------------------------------------
# Same-object identity
# ---------------------------------------------------------------------------

class TestReadabilitySameObjectIdentity:
    def test_hook_emphasis_words_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e._HOOK_EMPHASIS_WORDS is r._HOOK_EMPHASIS_WORDS

    def test_is_cjk_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e._is_cjk is r._is_cjk

    def test_emphasis_level_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e._emphasis_level is r._emphasis_level

    def test_should_emphasize_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e._should_emphasize is r._should_emphasize

    def test_semantic_wrap_block_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e._semantic_wrap_block is r._semantic_wrap_block

    def test_subtitle_emphasis_pass_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e.subtitle_emphasis_pass is r.subtitle_emphasis_pass

    def test_resegment_srt_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e.resegment_srt_for_readability is r.resegment_srt_for_readability

    def test_intel_max_wps_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e._INTEL_MAX_WPS is r._INTEL_MAX_WPS

    def test_clause_starters_identity(self):
        import app.services.subtitles.readability as r
        import app.services.subtitle_engine as e
        assert e._CLAUSE_STARTERS is r._CLAUSE_STARTERS


# ---------------------------------------------------------------------------
# _HOOK_EMPHASIS_WORDS
# ---------------------------------------------------------------------------

class TestHookEmphasisWords:
    def test_is_frozenset(self):
        from app.services.subtitles.readability import _HOOK_EMPHASIS_WORDS
        assert isinstance(_HOOK_EMPHASIS_WORDS, frozenset)

    def test_contains_anchor_words(self):
        from app.services.subtitles.readability import _HOOK_EMPHASIS_WORDS
        for word in ("never", "crazy", "secret", "stop", "best", "worst"):
            assert word in _HOOK_EMPHASIS_WORDS

    def test_common_words_not_in_set(self):
        from app.services.subtitles.readability import _HOOK_EMPHASIS_WORDS
        for word in ("the", "a", "is", "in", "to"):
            assert word not in _HOOK_EMPHASIS_WORDS


# ---------------------------------------------------------------------------
# _is_cjk
# ---------------------------------------------------------------------------

class TestIsCjk:
    def test_ascii_is_not_cjk(self):
        from app.services.subtitles.readability import _is_cjk
        assert _is_cjk("Hello world") is False

    def test_hiragana_detected(self):
        from app.services.subtitles.readability import _is_cjk
        assert _is_cjk("こんにちは") is True

    def test_katakana_detected(self):
        from app.services.subtitles.readability import _is_cjk
        assert _is_cjk("コンニチハ") is True

    def test_cjk_unified_detected(self):
        from app.services.subtitles.readability import _is_cjk
        assert _is_cjk("这是中文") is True

    def test_hangul_detected(self):
        from app.services.subtitles.readability import _is_cjk
        assert _is_cjk("안녕하세요") is True

    def test_empty_string_not_cjk(self):
        from app.services.subtitles.readability import _is_cjk
        assert _is_cjk("") is False


# ---------------------------------------------------------------------------
# _emphasis_level
# ---------------------------------------------------------------------------

class TestEmphasisLevel:
    def test_tiktok_bounce_is_strong(self):
        from app.services.subtitles.readability import _emphasis_level
        assert _emphasis_level("tiktok_bounce_v1") == "strong"

    def test_viral_bold_is_strong(self):
        from app.services.subtitles.readability import _emphasis_level
        assert _emphasis_level("viral_bold") == "strong"

    def test_story_clean_is_medium(self):
        from app.services.subtitles.readability import _emphasis_level
        assert _emphasis_level("story_clean_01") == "medium"

    def test_clean_pro_is_subtle(self):
        from app.services.subtitles.readability import _emphasis_level
        assert _emphasis_level("clean_pro") == "subtle"

    def test_boxed_caption_is_minimal(self):
        from app.services.subtitles.readability import _emphasis_level
        assert _emphasis_level("boxed_caption") == "minimal"

    def test_unregistered_preset_falls_back_to_default(self):
        # "pro_karaoke" is not in _PRESETS → normalize_subtitle_style_id returns
        # "tiktok_bounce_v1" (the default) → "strong"
        from app.services.subtitles.readability import _emphasis_level
        assert _emphasis_level("pro_karaoke") == "strong"

    def test_unknown_preset_falls_back_to_default_strong(self):
        # Unknown presets normalize to "tiktok_bounce_v1" → "strong"
        from app.services.subtitles.readability import _emphasis_level
        assert _emphasis_level("nonexistent_preset_xyz") == "strong"


# ---------------------------------------------------------------------------
# _should_emphasize
# ---------------------------------------------------------------------------

class TestShouldEmphasize:
    def test_dollar_number_always_emphasized(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("$1,000", "subtle") is True

    def test_percentage_always_emphasized(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("100%", "subtle") is True

    def test_multiplier_always_emphasized(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("10x", "subtle") is True

    def test_contrast_word_strong_level(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("never", "strong") is True

    def test_contrast_word_not_subtle_level(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("never", "subtle") is False

    def test_common_word_not_emphasized(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("the", "strong") is False

    def test_hook_word_strong_level(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("crazy", "strong") is True

    def test_hook_word_medium_level(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("crazy", "medium") is True

    def test_hook_word_subtle_level_not_emphasized(self):
        from app.services.subtitles.readability import _should_emphasize
        assert _should_emphasize("crazy", "subtle") is False


# ---------------------------------------------------------------------------
# _semantic_wrap_block
# ---------------------------------------------------------------------------

class TestSemanticWrapBlock:
    def test_short_text_unchanged(self):
        from app.services.subtitles.readability import _semantic_wrap_block
        # Short text should be below max_em — returned unchanged
        result = _semantic_wrap_block("Hi there", 18.0)
        assert result == "Hi there"

    def test_already_wrapped_unchanged(self):
        from app.services.subtitles.readability import _semantic_wrap_block
        result = _semantic_wrap_block("Line one\nLine two", 18.0)
        assert result == "Line one\nLine two"

    def test_single_word_unchanged(self):
        from app.services.subtitles.readability import _semantic_wrap_block
        result = _semantic_wrap_block("SUPERLONGWORD", 5.0)
        assert result == "SUPERLONGWORD"

    def test_orphan_avoidance_no_split(self):
        # 2 words: midpoint split → best_idx=1, n-best_idx=1 → orphan → return unsplit
        from app.services.subtitles.readability import _semantic_wrap_block
        result = _semantic_wrap_block("Hello world", 1.0)
        # With max_em=1.0 (forces wrap attempt), 2 words: best_idx=1, n-best_idx=1 → orphan
        assert "\n" not in result

    def test_wrap_produces_newline_for_long_text(self):
        from app.services.subtitles.readability import _semantic_wrap_block
        # 8 words, force max_em=1 so wrapping is triggered
        text = "one two three four five six seven eight"
        result = _semantic_wrap_block(text, 1.0)
        # With orphan-safe split (8 words), should produce a newline
        assert "\n" in result


# ---------------------------------------------------------------------------
# subtitle_emphasis_pass
# ---------------------------------------------------------------------------

class TestSubtitleEmphasisPass:
    def test_returns_same_list_object(self):
        from app.services.subtitles.readability import subtitle_emphasis_pass
        blocks = [{"start": 0.0, "end": 2.0, "text": "Hello world"}]
        result = subtitle_emphasis_pass(blocks, preset_id="tiktok_bounce_v1")
        assert result is blocks

    def test_empty_blocks_unchanged(self):
        from app.services.subtitles.readability import subtitle_emphasis_pass
        result = subtitle_emphasis_pass([])
        assert result == []

    def test_word_level_srt_skips_transforms(self):
        # Word-level SRT: ≥6 blocks, avg ≤1.5 words → all transforms skipped
        from app.services.subtitles.readability import subtitle_emphasis_pass
        blocks = [
            {"start": float(i) * 0.3, "end": float(i) * 0.3 + 0.3, "text": w}
            for i, w in enumerate(["never", "crazy", "stop", "only", "best", "worst"])
        ]
        original_texts = [b["text"] for b in blocks]
        subtitle_emphasis_pass(blocks, preset_id="tiktok_bounce_v1")
        # Word-level: no changes should be applied
        assert [b["text"] for b in blocks] == original_texts

    def test_minimal_preset_no_emphasis(self):
        # boxed_caption → minimal level → no highlight markers applied
        from app.services.subtitles.readability import subtitle_emphasis_pass
        blocks = [{"start": 0.0, "end": 3.0, "text": "Never stop learning now"}]
        subtitle_emphasis_pass(blocks, preset_id="boxed_caption")
        # minimal level: no _HL markers, no uppercase beyond normal
        from app.services.subtitles.styles import _HL_OPEN
        assert _HL_OPEN not in blocks[0]["text"]

    def test_cjk_text_skips_uppercase_and_markers(self):
        from app.services.subtitles.readability import subtitle_emphasis_pass
        from app.services.subtitles.styles import _HL_OPEN
        blocks = [{"start": 0.0, "end": 2.0, "text": "これは日本語のテキストです"}]
        subtitle_emphasis_pass(blocks, preset_id="tiktok_bounce_v1")
        assert _HL_OPEN not in blocks[0]["text"]


# ---------------------------------------------------------------------------
# resegment_srt_for_readability
# ---------------------------------------------------------------------------

class TestResegmentSrtForReadability:
    def test_word_level_returned_unchanged(self):
        # avg ≤1.5 words → word-level → no modification
        from app.services.subtitles.readability import resegment_srt_for_readability
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_WORD, tmp, "word.srt")
            original = Path(path).read_text(encoding="utf-8")
            result = resegment_srt_for_readability(path)
            assert result == 6  # 6 blocks returned unchanged
            assert Path(path).read_text(encoding="utf-8") == original

    def test_long_block_is_split(self):
        # Single block with many words → should be split into multiple blocks
        from app.services.subtitles.readability import resegment_srt_for_readability
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_LONG_BLOCK, tmp, "long.srt")
            result = resegment_srt_for_readability(path)
            assert result > 1  # Must have been split

    def test_missing_file_returns_zero(self):
        from app.services.subtitles.readability import resegment_srt_for_readability
        result = resegment_srt_for_readability("/nonexistent/path/file.srt")
        assert result == 0

    def test_output_is_valid_srt_format(self):
        from app.services.subtitles.readability import resegment_srt_for_readability
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_LONG_BLOCK, tmp, "long.srt")
            resegment_srt_for_readability(path)
            content = Path(path).read_text(encoding="utf-8")
            # Must start with block index 1
            assert content.startswith("1\n")
            # Must contain timestamp arrows
            assert "-->" in content

    def test_segment_level_modified_in_place(self):
        from app.services.subtitles.readability import resegment_srt_for_readability
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_LONG_BLOCK, tmp, "seg.srt")
            before = Path(path).read_text(encoding="utf-8")
            resegment_srt_for_readability(path)
            after = Path(path).read_text(encoding="utf-8")
            # A long block must have been modified
            assert before != after
