# test_subtitle_text_transforms.py — Unit tests for subtitles/text_transforms.py (Phase 4G.5).
#
# Coverage:
# - Module imports cleanly; subtitle_engine still importable
# - Same-object identity for all moved symbols
# - text_transforms.py does NOT import subtitle_engine
# - resolve_hook_overlay_text: explicit hook text returned and cleaned
# - resolve_hook_overlay_text: falls back to first SRT block when no explicit text
# - resolve_hook_overlay_text: returns empty when SRT is missing/empty
# - resolve_hook_overlay_text: truncates to max_words
# - resolve_hook_overlay_text: converts all-caps (>3 words) to title-case
# - format_hook_subtitle: short text returned unchanged
# - format_hook_subtitle: short segment uppercases emphasis words
# - format_hook_subtitle: long segment splits into two lines
# - format_hook_subtitle: emphasis word anchors split point on line 1
# - apply_market_hook_text_to_srt: replaces first block text; preserves timestamps
# - apply_market_hook_text_to_srt: blank hook_text returns applied=False
# - apply_market_hook_text_to_srt: missing file returns applied=False
# - apply_hook_subtitle_format: formats first max_hook_blocks blocks
# - apply_hook_subtitle_format: empty file returns 0
# - apply_hook_subtitle_format: safe no-op on missing file
# - apply_subtitle_execution_hints: None input returns fallback dict
# - apply_subtitle_execution_hints: invalid type returns fallback dict
# - apply_subtitle_execution_hints: available=False returns applied=False with warnings
# - apply_subtitle_execution_hints: valid input returns applied=True with parsed fields
# - apply_subtitle_execution_hints: emphasis_strength clamped to [0.0, 1.0]
# - apply_subtitle_execution_hints: unknown emotion_style falls back to neutral
# - apply_subtitle_execution_hints: never raises
# - apply_market_line_break_to_srt: empty payload is safe no-op (returns path unchanged)
from __future__ import annotations

import inspect
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# SRT fixtures
# ---------------------------------------------------------------------------

_SRT_TWO_BLOCKS = """\
1
00:00:01,000 --> 00:00:03,000
Hello world this is test

2
00:00:04,000 --> 00:00:06,000
Second subtitle block

"""

_SRT_CAPS_BLOCK = """\
1
00:00:01,000 --> 00:00:03,000
THIS IS ALL CAPS TEXT HERE

"""

_SRT_EMPTY = ""


def _write_srt(content: str, tmp_dir: str, name: str = "source.srt") -> str:
    p = Path(tmp_dir) / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestTextTransformsModuleImports:
    def test_text_transforms_imports_cleanly(self):
        import app.services.subtitles.text_transforms as m
        assert m is not None

    def test_subtitle_engine_still_importable(self):
        import app.services.subtitle_engine as e
        assert e is not None

    def test_resolve_hook_overlay_text_in_module(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        assert callable(resolve_hook_overlay_text)

    def test_format_hook_subtitle_in_module(self):
        from app.services.subtitles.text_transforms import format_hook_subtitle
        assert callable(format_hook_subtitle)

    def test_apply_subtitle_execution_hints_in_module(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        assert callable(apply_subtitle_execution_hints)

    def test_no_whisper_import_in_text_transforms(self):
        import app.services.subtitles.text_transforms as m
        assert not hasattr(m, "whisper")

    def test_no_subtitle_engine_import_in_text_transforms(self):
        import app.services.subtitles.text_transforms as m
        src = inspect.getsource(m)
        assert "subtitle_engine" not in src


# ---------------------------------------------------------------------------
# Same-object identity
# ---------------------------------------------------------------------------

class TestTextTransformsSameObjectIdentity:
    def test_resolve_hook_overlay_text_identity(self):
        import app.services.subtitles.text_transforms as tt
        import app.services.subtitle_engine as e
        assert e.resolve_hook_overlay_text is tt.resolve_hook_overlay_text

    def test_apply_market_line_break_to_srt_identity(self):
        import app.services.subtitles.text_transforms as tt
        import app.services.subtitle_engine as e
        assert e.apply_market_line_break_to_srt is tt.apply_market_line_break_to_srt

    def test_apply_market_hook_text_to_srt_identity(self):
        import app.services.subtitles.text_transforms as tt
        import app.services.subtitle_engine as e
        assert e.apply_market_hook_text_to_srt is tt.apply_market_hook_text_to_srt

    def test_format_hook_subtitle_identity(self):
        import app.services.subtitles.text_transforms as tt
        import app.services.subtitle_engine as e
        assert e.format_hook_subtitle is tt.format_hook_subtitle

    def test_apply_hook_subtitle_format_identity(self):
        import app.services.subtitles.text_transforms as tt
        import app.services.subtitle_engine as e
        assert e.apply_hook_subtitle_format is tt.apply_hook_subtitle_format

    def test_apply_subtitle_execution_hints_identity(self):
        import app.services.subtitles.text_transforms as tt
        import app.services.subtitle_engine as e
        assert e.apply_subtitle_execution_hints is tt.apply_subtitle_execution_hints


# ---------------------------------------------------------------------------
# resolve_hook_overlay_text
# ---------------------------------------------------------------------------

class TestResolveHookOverlayText:
    def test_explicit_text_returned(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        text, reason = resolve_hook_overlay_text("My hook text", None)
        assert text == "My hook text"
        assert reason == "explicit"

    def test_explicit_text_strips_ass_tags(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        text, reason = resolve_hook_overlay_text("{\\b1}Bold text{\\b0}", None)
        assert "{" not in text
        assert "Bold text" in text

    def test_explicit_text_collapses_whitespace(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        text, _ = resolve_hook_overlay_text("  hello   world  ", None)
        assert text == "hello world"

    def test_explicit_text_truncated_to_max_words(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        words = " ".join([f"word{i}" for i in range(20)])
        text, _ = resolve_hook_overlay_text(words, None, max_words=5)
        assert len(text.split()) == 5

    def test_all_caps_more_than_3_words_converted_to_title(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        text, _ = resolve_hook_overlay_text("THIS IS ALL CAPS TEXT", None)
        assert text == text.title() or text[0].isupper()
        assert text != "THIS IS ALL CAPS TEXT"

    def test_falls_back_to_srt_first_block(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            text, reason = resolve_hook_overlay_text(None, path)
            assert reason == "subtitle_first_block"
            assert "Hello" in text or len(text) > 0

    def test_falls_back_to_empty_when_no_srt(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        text, reason = resolve_hook_overlay_text(None, None)
        assert text == ""
        assert reason == "no_suitable_text"

    def test_falls_back_to_empty_when_srt_missing(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        text, reason = resolve_hook_overlay_text(None, "/nonexistent/path.srt")
        assert text == ""
        assert reason == "no_suitable_text"

    def test_explicit_empty_string_falls_through(self):
        from app.services.subtitles.text_transforms import resolve_hook_overlay_text
        text, reason = resolve_hook_overlay_text("", None)
        assert text == ""
        assert reason == "no_suitable_text"


# ---------------------------------------------------------------------------
# format_hook_subtitle
# ---------------------------------------------------------------------------

class TestFormatHookSubtitle:
    def test_short_text_unchanged(self):
        from app.services.subtitles.text_transforms import format_hook_subtitle
        result = format_hook_subtitle("Hi")
        assert result == "Hi"

    def test_text_under_20_chars_unchanged(self):
        from app.services.subtitles.text_transforms import format_hook_subtitle
        result = format_hook_subtitle("Short text here")
        # 15 chars < 20 → returned as-is
        assert result == "Short text here"

    def test_short_segment_uppercases_emphasis_word(self):
        from app.services.subtitles.text_transforms import format_hook_subtitle
        result = format_hook_subtitle("You never believe this")
        # 4 words → short path: emphasis words uppercased
        assert "NEVER" in result

    def test_long_segment_splits_to_two_lines(self):
        from app.services.subtitles.text_transforms import format_hook_subtitle
        result = format_hook_subtitle("This is the secret they never want you to know")
        assert "\n" in result

    def test_long_segment_line1_is_uppercased(self):
        from app.services.subtitles.text_transforms import format_hook_subtitle
        result = format_hook_subtitle("You will never believe what happened next")
        lines = result.split("\n")
        assert lines[0] == lines[0].upper()

    def test_emphasis_word_anchors_split_point(self):
        from app.services.subtitles.text_transforms import format_hook_subtitle
        # "stop" at position 2 should be included in line 1 (split_at = 3)
        result = format_hook_subtitle("you must stop doing this right now okay")
        lines = result.split("\n")
        # "STOP" should be in line 1
        assert "STOP" in lines[0]


# ---------------------------------------------------------------------------
# apply_market_hook_text_to_srt
# ---------------------------------------------------------------------------

class TestApplyMarketHookTextToSrt:
    def test_replaces_first_block_text(self):
        from app.services.subtitles.text_transforms import apply_market_hook_text_to_srt
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            result = apply_market_hook_text_to_srt(path, "My hook line")
            assert result["applied"] is True
            assert result["affected_count"] >= 1
            content = Path(path).read_text(encoding="utf-8")
            assert "My hook line" in content

    def test_preserves_second_block(self):
        from app.services.subtitles.text_transforms import apply_market_hook_text_to_srt
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            apply_market_hook_text_to_srt(path, "Hook text")
            content = Path(path).read_text(encoding="utf-8")
            assert "Second subtitle block" in content

    def test_blank_hook_text_not_applied(self):
        from app.services.subtitles.text_transforms import apply_market_hook_text_to_srt
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            result = apply_market_hook_text_to_srt(path, "")
            assert result["applied"] is False

    def test_missing_file_returns_not_applied(self):
        from app.services.subtitles.text_transforms import apply_market_hook_text_to_srt
        result = apply_market_hook_text_to_srt("/nonexistent/path.srt", "hook")
        assert result["applied"] is False

    def test_original_hook_text_recorded(self):
        from app.services.subtitles.text_transforms import apply_market_hook_text_to_srt
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            result = apply_market_hook_text_to_srt(path, "Replacement hook")
            assert "Hello" in result["original_hook_text"] or len(result["original_hook_text"]) > 0


# ---------------------------------------------------------------------------
# apply_hook_subtitle_format
# ---------------------------------------------------------------------------

class TestApplyHookSubtitleFormat:
    def test_formats_first_two_blocks(self):
        from app.services.subtitles.text_transforms import apply_hook_subtitle_format
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            count = apply_hook_subtitle_format(path, max_hook_blocks=2)
            assert count == 2

    def test_only_formats_up_to_max_hook_blocks(self):
        from app.services.subtitles.text_transforms import apply_hook_subtitle_format
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            count = apply_hook_subtitle_format(path, max_hook_blocks=1)
            assert count == 1

    def test_empty_file_returns_zero(self):
        from app.services.subtitles.text_transforms import apply_hook_subtitle_format
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_EMPTY, tmp)
            count = apply_hook_subtitle_format(path)
            assert count == 0

    def test_missing_file_returns_zero(self):
        from app.services.subtitles.text_transforms import apply_hook_subtitle_format
        count = apply_hook_subtitle_format("/nonexistent/path.srt")
        assert count == 0


# ---------------------------------------------------------------------------
# apply_subtitle_execution_hints
# ---------------------------------------------------------------------------

class TestApplySubtitleExecutionHints:
    def test_none_input_returns_fallback(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        result = apply_subtitle_execution_hints([], None)
        assert result["applied"] is False
        assert result["emphasis_strength"] == 0.0
        assert result["emotion_style"] == "neutral"

    def test_non_dict_input_returns_fallback(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        result = apply_subtitle_execution_hints([], "not a dict")
        assert result["applied"] is False

    def test_available_false_returns_applied_false_with_warnings(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        execution = {"available": False, "warnings": ["no_data"]}
        result = apply_subtitle_execution_hints([], execution)
        assert result["applied"] is False
        assert "no_data" in result["warnings"]

    def test_valid_input_returns_applied_true(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {
                "emphasis_strength": 0.8,
                "emotion_style": "hype",
                "density_mode": "expressive",
                "keyword_focus": ["viral", "crazy"],
            },
        }
        result = apply_subtitle_execution_hints([], execution)
        assert result["applied"] is True
        assert abs(result["emphasis_strength"] - 0.8) < 1e-6
        assert result["emotion_style"] == "hype"
        assert result["density_mode"] == "expressive"
        assert "viral" in result["keyword_focus"]

    def test_emphasis_strength_clamped_above_1(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {"emphasis_strength": 5.0},
        }
        result = apply_subtitle_execution_hints([], execution)
        assert result["emphasis_strength"] == 1.0

    def test_emphasis_strength_clamped_below_0(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {"emphasis_strength": -2.0},
        }
        result = apply_subtitle_execution_hints([], execution)
        assert result["emphasis_strength"] == 0.0

    def test_unknown_emotion_style_falls_back_to_neutral(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {"emotion_style": "unknown_style_xyz"},
        }
        result = apply_subtitle_execution_hints([], execution)
        assert result["emotion_style"] == "neutral"

    def test_keyword_focus_capped_at_10(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {
                "keyword_focus": [f"word{i}" for i in range(20)],
            },
        }
        result = apply_subtitle_execution_hints([], execution)
        assert len(result["keyword_focus"]) == 10

    def test_never_raises(self):
        from app.services.subtitles.text_transforms import apply_subtitle_execution_hints
        # Should not raise even with malformed data
        for bad_input in [None, 42, [], {}, {"available": True}, {"available": True, "global_hint": "bad"}]:
            result = apply_subtitle_execution_hints([], bad_input)
            assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# apply_market_line_break_to_srt
# ---------------------------------------------------------------------------

class TestApplyMarketLineBreakToSrt:
    def test_empty_payload_is_noop(self):
        from app.services.subtitles.text_transforms import apply_market_line_break_to_srt
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            before = Path(path).read_text(encoding="utf-8")
            result = apply_market_line_break_to_srt(path, {})
            assert result == path
            assert Path(path).read_text(encoding="utf-8") == before

    def test_none_payload_is_noop(self):
        from app.services.subtitles.text_transforms import apply_market_line_break_to_srt
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            result = apply_market_line_break_to_srt(path, None)
            assert result == path

    def test_returns_path_on_exception(self):
        # market_subtitle_policy may not be available — exception should be swallowed
        from app.services.subtitles.text_transforms import apply_market_line_break_to_srt
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_srt(_SRT_TWO_BLOCKS, tmp)
            # Pass a truthy payload to trigger the import attempt
            result = apply_market_line_break_to_srt(path, {"target_market": "TEST_FAKE_MARKET"})
            # Should return path unchanged regardless of whether market_subtitle_policy exists
            assert result == path
