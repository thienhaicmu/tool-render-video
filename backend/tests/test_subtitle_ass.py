"""Tests for app.features.render.engine.subtitle.generator.ass."""
import pytest

from app.features.render.engine.subtitle.generator.ass import (
    _ass_escape_text,
    _ass_highlight_tags,
    _ass_time,
    _hex_to_ass,
    _safe_filter_path,
)


# ---------------------------------------------------------------------------
# _ass_time
# ---------------------------------------------------------------------------

def test_ass_time_zero():
    assert _ass_time(0.0) == "0:00:00.00"


def test_ass_time_one_second():
    assert _ass_time(1.0) == "0:00:01.00"


def test_ass_time_90_seconds():
    assert _ass_time(90.0) == "0:01:30.00"


def test_ass_time_with_centiseconds():
    # 1.25s → 1s + 25 centiseconds
    result = _ass_time(1.25)
    assert result == "0:00:01.25"


def test_ass_time_over_one_hour():
    assert _ass_time(3661.0) == "1:01:01.00"


def test_ass_time_returns_string():
    assert isinstance(_ass_time(5.0), str)


# ---------------------------------------------------------------------------
# _ass_escape_text
# ---------------------------------------------------------------------------

def test_ass_escape_text_plain_text_unchanged():
    result = _ass_escape_text("Hello world")
    assert result == "Hello world"


def test_ass_escape_text_braces_become_parens():
    result = _ass_escape_text("text{override}")
    assert "{" not in result
    assert "}" not in result


def test_ass_escape_text_python_newline_to_ass_newline():
    result = _ass_escape_text("line one\nline two")
    assert r"\N" in result
    assert "\n" not in result


def test_ass_escape_text_backslash_escaped():
    result = _ass_escape_text("C:\\path")
    # backslash should be escaped (doubled)
    assert "\\\\" in result


# ---------------------------------------------------------------------------
# _ass_highlight_tags
# ---------------------------------------------------------------------------

def test_ass_highlight_tags_us_market():
    open_tag, close_tag = _ass_highlight_tags("US")
    assert r"\b1" in open_tag
    assert r"\b0" in close_tag


def test_ass_highlight_tags_eu_market():
    open_tag, close_tag = _ass_highlight_tags("EU")
    assert "FFFF" in open_tag  # cyan for EU


def test_ass_highlight_tags_jp_market():
    open_tag, close_tag = _ass_highlight_tags("JP")
    assert "fscx104" in open_tag


def test_ass_highlight_tags_default_us_for_unknown():
    open_tag_us, _ = _ass_highlight_tags("US")
    open_tag_unknown, _ = _ass_highlight_tags("ZZ")
    assert open_tag_us == open_tag_unknown


def test_ass_highlight_tags_returns_tuple_of_two():
    result = _ass_highlight_tags("US")
    assert isinstance(result, tuple)
    assert len(result) == 2


# ---------------------------------------------------------------------------
# _hex_to_ass
# ---------------------------------------------------------------------------

def test_hex_to_ass_white():
    # #FFFFFF → &H00FFFFFF
    result = _hex_to_ass("#FFFFFF")
    assert result == "&H00FFFFFF"


def test_hex_to_ass_black():
    result = _hex_to_ass("#000000")
    assert result == "&H00000000"


def test_hex_to_ass_with_alpha():
    result = _hex_to_ass("#FFFFFF", alpha=0x80)
    assert result.startswith("&H80")


def test_hex_to_ass_rgb_order():
    # #FF0000 (red) → ASS is BBGGRR so should be 0000FF
    result = _hex_to_ass("#FF0000")
    assert result == "&H000000FF"


def test_hex_to_ass_invalid_falls_back_to_white():
    result = _hex_to_ass("notacolor")
    assert "FF" in result  # white fallback


# ---------------------------------------------------------------------------
# _safe_filter_path
# ---------------------------------------------------------------------------

def test_safe_filter_path_backslash_to_slash():
    # The function replaces \ with / first, then escapes colons.
    # C:\path\to\file.ass → C:/path/to/file.ass → C\:/path/to/file.ass
    result = _safe_filter_path("C:\\path\\to\\file.ass")
    # forward slashes should be present after conversion
    assert "/" in result


def test_safe_filter_path_colon_escaped():
    result = _safe_filter_path("C:/path/file.ass")
    assert r"\:" in result


def test_safe_filter_path_plain_unix_path():
    result = _safe_filter_path("/tmp/subtitle.ass")
    # No backslash, no colon in /tmp/subtitle.ass — unchanged
    assert result == "/tmp/subtitle.ass"


def test_safe_filter_path_apostrophe_escaped():
    result = _safe_filter_path("/tmp/it's.ass")
    assert r"\'" in result
