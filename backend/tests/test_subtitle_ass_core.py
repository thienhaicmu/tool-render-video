# test_subtitle_ass_core.py — Unit tests for subtitles/ass_core.py (Phase 4G.4).
#
# Coverage:
# - Module imports cleanly; subtitle_engine still importable
# - Same-object identity for all moved public and private functions
# - _ass_time precision (centisecond, H:MM:SS.cc)
# - _ass_escape_text braces/backslash escaping
# - _ass_escape_text PUA sentinel stripping when no market match
# - _ass_highlight_tags market-specific output
# - _hex_to_ass #RRGGBB to ASS &HAABBGGRR conversion
# - _safe_filter_path escaping
# - srt_to_ass_bounce output contains [Script Info], [V4+ Styles], [Events]
# - srt_to_ass_bounce produces Dialogue lines
# - srt_to_ass_bounce style line uses given preset
# - srt_to_ass_karaoke falls back to srt_to_ass_bounce for segment-level SRT
# - srt_to_ass_karaoke produces karaoke k-tags for word-level SRT
# - Old import path works end-to-end
# - No Whisper/FFmpeg dependency (subprocess not called in pure unit tests)
# - ass_core imports srt_core.parse_srt_timestamp (not a duplicate)
# - readability._break_by_visual_width used (not a duplicate in ass_core)
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# SRT fixtures
# ---------------------------------------------------------------------------

_SRT_SEGMENT = """\
1
00:00:01,000 --> 00:00:03,000
Hello world this is a test

2
00:00:04,000 --> 00:00:06,000
Second subtitle block here

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

"""

_SRT_EMPTY = ""


def _write_srt(content: str, tmp_dir: str, name: str = "source.srt") -> str:
    p = Path(tmp_dir) / name
    p.write_text(content, encoding="utf-8")
    return str(p)


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestAssCorModuleImports:
    def test_ass_core_imports_cleanly(self):
        import app.services.subtitles.ass_core as m
        assert m is not None

    def test_subtitle_engine_still_importable(self):
        import app.services.subtitle_engine as e
        assert e is not None

    def test_srt_to_ass_bounce_in_ass_core(self):
        from app.services.subtitles.ass_core import srt_to_ass_bounce
        assert callable(srt_to_ass_bounce)

    def test_srt_to_ass_karaoke_in_ass_core(self):
        from app.services.subtitles.ass_core import srt_to_ass_karaoke
        assert callable(srt_to_ass_karaoke)

    def test_render_subtitle_preview_in_ass_core(self):
        from app.services.subtitles.ass_core import render_subtitle_preview
        assert callable(render_subtitle_preview)

    def test_hex_to_ass_in_ass_core(self):
        from app.services.subtitles.ass_core import _hex_to_ass
        assert callable(_hex_to_ass)

    def test_no_whisper_import_in_ass_core(self):
        import app.services.subtitles.ass_core as m
        assert not hasattr(m, "whisper")

    def test_no_subtitle_engine_import_in_ass_core(self):
        import inspect
        import app.services.subtitles.ass_core as m
        src = inspect.getsource(m)
        assert "subtitle_engine" not in src


# ---------------------------------------------------------------------------
# Same-object identity
# ---------------------------------------------------------------------------

class TestAssCoreSameObjectIdentity:
    def test_srt_to_ass_bounce_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e.srt_to_ass_bounce is ac.srt_to_ass_bounce

    def test_srt_to_ass_karaoke_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e.srt_to_ass_karaoke is ac.srt_to_ass_karaoke

    def test_render_subtitle_preview_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e.render_subtitle_preview is ac.render_subtitle_preview

    def test_hex_to_ass_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e._hex_to_ass is ac._hex_to_ass

    def test_ass_time_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e._ass_time is ac._ass_time

    def test_ass_escape_text_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e._ass_escape_text is ac._ass_escape_text

    def test_burn_subtitle_onto_video_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e.burn_subtitle_onto_video is ac.burn_subtitle_onto_video

    def test_safe_filter_path_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e._safe_filter_path is ac._safe_filter_path

    def test_preview_aspect_res_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e._PREVIEW_ASPECT_RES is ac._PREVIEW_ASPECT_RES

    def test_preview_fonts_dir_identity(self):
        import app.services.subtitles.ass_core as ac
        import app.services.subtitle_engine as e
        assert e._PREVIEW_FONTS_DIR is ac._PREVIEW_FONTS_DIR


# ---------------------------------------------------------------------------
# _ass_time precision
# ---------------------------------------------------------------------------

class TestAssTime:
    def test_zero(self):
        from app.services.subtitles.ass_core import _ass_time
        assert _ass_time(0.0) == "0:00:00.00"

    def test_one_second(self):
        from app.services.subtitles.ass_core import _ass_time
        assert _ass_time(1.0) == "0:00:01.00"

    def test_centiseconds(self):
        from app.services.subtitles.ass_core import _ass_time
        assert _ass_time(1.15) == "0:00:01.15"

    def test_minutes_and_seconds(self):
        from app.services.subtitles.ass_core import _ass_time
        assert _ass_time(65.5) == "0:01:05.50"

    def test_hours(self):
        from app.services.subtitles.ass_core import _ass_time
        assert _ass_time(3661.0) == "1:01:01.00"

    def test_cs_rounding(self):
        from app.services.subtitles.ass_core import _ass_time
        # 10.005 s → 1000.5 cs → rounds to 1001 → 10:00.01 (ss=10, cs=01)
        result = _ass_time(10.005)
        assert result == "0:00:10.01"


# ---------------------------------------------------------------------------
# _ass_escape_text
# ---------------------------------------------------------------------------

class TestAssEscapeText:
    def test_plain_text_unchanged(self):
        from app.services.subtitles.ass_core import _ass_escape_text
        assert _ass_escape_text("hello world") == "hello world"

    def test_braces_replaced_with_parens(self):
        from app.services.subtitles.ass_core import _ass_escape_text
        assert _ass_escape_text("test {value}") == "test (value)"

    def test_backslash_escaped(self):
        from app.services.subtitles.ass_core import _ass_escape_text
        result = _ass_escape_text("path\\to\\file")
        assert "\\\\" in result

    def test_newline_to_ass_hardnewline(self):
        from app.services.subtitles.ass_core import _ass_escape_text
        result = _ass_escape_text("line1\nline2")
        assert r"\N" in result
        assert "\n" not in result

    def test_pua_sentinels_stripped_when_unresolved(self):
        from app.services.subtitles.ass_core import _ass_escape_text
        from app.services.subtitles.styles import _HL_OPEN, _HL_CLOSE
        text = f"{_HL_OPEN}word{_HL_CLOSE}"
        result = _ass_escape_text(text)
        assert _HL_OPEN not in result
        assert _HL_CLOSE not in result


# ---------------------------------------------------------------------------
# _ass_highlight_tags
# ---------------------------------------------------------------------------

class TestAssHighlightTags:
    def test_us_default(self):
        from app.services.subtitles.ass_core import _ass_highlight_tags
        open_tag, close_tag = _ass_highlight_tags("US")
        assert r"\b1" in open_tag
        assert r"\b0" in close_tag

    def test_eu_market(self):
        from app.services.subtitles.ass_core import _ass_highlight_tags
        open_tag, close_tag = _ass_highlight_tags("EU")
        assert "00FFFF" in open_tag  # cyan in ASS BGR

    def test_jp_market(self):
        from app.services.subtitles.ass_core import _ass_highlight_tags
        open_tag, close_tag = _ass_highlight_tags("JP")
        assert "66FFCC" in open_tag

    def test_none_market_uses_default(self):
        from app.services.subtitles.ass_core import _ass_highlight_tags
        result = _ass_highlight_tags(None)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _hex_to_ass
# ---------------------------------------------------------------------------

class TestHexToAss:
    def test_white(self):
        from app.services.subtitles.ass_core import _hex_to_ass
        assert _hex_to_ass("#FFFFFF") == "&H00FFFFFF"

    def test_black(self):
        from app.services.subtitles.ass_core import _hex_to_ass
        assert _hex_to_ass("#000000") == "&H00000000"

    def test_red_swapped_to_bgr(self):
        from app.services.subtitles.ass_core import _hex_to_ass
        # CSS red = #FF0000 → ASS BGR = 0000FF
        assert _hex_to_ass("#FF0000") == "&H000000FF"

    def test_blue_swapped(self):
        from app.services.subtitles.ass_core import _hex_to_ass
        # CSS blue = #0000FF → ASS BGR = FF0000
        assert _hex_to_ass("#0000FF") == "&H00FF0000"

    def test_alpha(self):
        from app.services.subtitles.ass_core import _hex_to_ass
        result = _hex_to_ass("#FFFFFF", alpha=128)
        assert result.startswith("&H80")

    def test_invalid_fallback_to_white(self):
        from app.services.subtitles.ass_core import _hex_to_ass
        result = _hex_to_ass("not_a_color")
        assert result == "&H00FFFFFF"


# ---------------------------------------------------------------------------
# _safe_filter_path
# ---------------------------------------------------------------------------

class TestSafeFilterPath:
    def test_backslashes_to_forward(self):
        from app.services.subtitles.ass_core import _safe_filter_path
        result = _safe_filter_path(r"C:\path\to\file.ass")
        # Path separators (backslashes) become forward slashes; colon gets \: escape
        assert "/path/to/file.ass" in result

    def test_colon_escaped(self):
        from app.services.subtitles.ass_core import _safe_filter_path
        result = _safe_filter_path("C:/path/file.ass")
        assert r"\:" in result

    def test_apostrophe_escaped(self):
        from app.services.subtitles.ass_core import _safe_filter_path
        result = _safe_filter_path("/path/o'clock.ass")
        assert r"\'" in result


# ---------------------------------------------------------------------------
# srt_to_ass_bounce output structure
# ---------------------------------------------------------------------------

class TestSrtToAssBounce:
    def test_output_has_script_info(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "[Script Info]" in content

    def test_output_has_v4_styles(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "[V4+ Styles]" in content

    def test_output_has_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "[Events]" in content

    def test_output_has_dialogue_lines(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "Dialogue:" in content

    def test_dialogue_count_matches_srt(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        lines = [l for l in content.splitlines() if l.startswith("Dialogue:")]
        assert len(lines) == 2

    def test_style_line_contains_fontname(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass, font_name="Montserrat")
            content = Path(ass).read_text(encoding="utf-8")
        assert "Montserrat" in content

    def test_empty_srt_produces_valid_ass_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_EMPTY, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "Dialogue:" not in content

    def test_returns_ass_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            result = srt_to_ass_bounce(src, ass)
        assert result == ass

    def test_play_res_y_embedded(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass, play_res_y=1920)
            content = Path(ass).read_text(encoding="utf-8")
        assert "PlayResY: 1920" in content

    def test_old_import_path_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitle_engine import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "[Script Info]" in content


# ---------------------------------------------------------------------------
# srt_to_ass_karaoke
# ---------------------------------------------------------------------------

class TestSrtToAssKaraoke:
    def test_karaoke_fallback_for_segment_level_srt(self):
        """Segment-level SRT → karaoke detects avg_words > 1.5 and falls back to bounce."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_SEGMENT, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_karaoke
            srt_to_ass_karaoke(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        # Bounce fallback still produces valid ASS
        assert "[Script Info]" in content
        assert "Dialogue:" in content

    def test_karaoke_word_level_produces_k_tags(self):
        """Word-level SRT produces \\k timing tags."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_WORD, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_karaoke
            srt_to_ass_karaoke(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert r"\k" in content

    def test_karaoke_output_has_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_WORD, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_karaoke
            srt_to_ass_karaoke(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "[Script Info]" in content
        assert "[V4+ Styles]" in content
        assert "[Events]" in content

    def test_karaoke_empty_srt_fallback(self):
        """Empty SRT → karaoke falls back to bounce (no crash)."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_EMPTY, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_karaoke
            srt_to_ass_karaoke(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "[Script Info]" in content

    def test_old_karaoke_import_path_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_WORD, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitle_engine import srt_to_ass_karaoke
            srt_to_ass_karaoke(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        assert "[Script Info]" in content


# ---------------------------------------------------------------------------
# Delegates to srt_core and readability (no duplicate logic)
# ---------------------------------------------------------------------------

class TestAssCoreDelegates:
    def test_parse_srt_timestamp_from_srt_core(self):
        import app.services.subtitles.ass_core as ac
        from app.services.subtitles.srt_core import parse_srt_timestamp
        assert ac.parse_srt_timestamp is parse_srt_timestamp

    def test_break_by_visual_width_from_readability(self):
        import app.services.subtitles.ass_core as ac
        from app.services.subtitles.readability import _break_by_visual_width
        assert ac._break_by_visual_width is _break_by_visual_width

    def test_run_with_retry_from_srt_core(self):
        import app.services.subtitles.ass_core as ac
        from app.services.subtitles.srt_core import _run_with_retry
        assert ac._run_with_retry is _run_with_retry


# ---------------------------------------------------------------------------
# Timestamp conversion unchanged end-to-end
# ---------------------------------------------------------------------------

class TestAssTimestampConversion:
    def test_srt_timestamp_converts_to_ass_correctly(self):
        """SRT timestamp parses and converts to ASS centisecond format correctly."""
        from app.services.subtitles.ass_core import _ass_time
        from app.services.subtitles.srt_core import parse_srt_timestamp
        # SRT "00:00:10,500" → 10.5 s → ASS "0:00:10.50"
        t = parse_srt_timestamp("00:00:10,500")
        assert _ass_time(t) == "0:00:10.50"

    def test_ass_timestamp_in_bounce_output(self):
        """Dialogue lines in bounce output use ASS H:MM:SS.cc format."""
        with tempfile.TemporaryDirectory() as tmp:
            srt_content = "1\n00:00:01,000 --> 00:00:03,000\nHello\n\n"
            src = _write_srt(srt_content, tmp)
            ass = str(Path(tmp) / "out.ass")
            from app.services.subtitles.ass_core import srt_to_ass_bounce
            srt_to_ass_bounce(src, ass)
            content = Path(ass).read_text(encoding="utf-8")
        # "0:00:01.00" and "0:00:03.00" should appear in a Dialogue line
        assert "0:00:01.00" in content
        assert "0:00:03.00" in content
