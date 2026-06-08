"""Tests for app.features.render.engine.subtitle.generator.srt."""
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.features.render.engine.subtitle.generator.srt import (
    _parse_srt_blocks,
    _run_with_retry,
    format_srt_timestamp,
    parse_srt_blocks,
    parse_srt_timestamp,
    slice_srt_to_text,
    write_srt_blocks,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,000
Hello world

2
00:00:04,500 --> 00:00:06,000
This is a test

"""

def _write_srt(content: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".srt", delete=False, mode="w", encoding="utf-8")
    tmp.write(content)
    tmp.flush()
    tmp.close()
    return Path(tmp.name)


# ---------------------------------------------------------------------------
# format_srt_timestamp
# ---------------------------------------------------------------------------

def test_format_srt_timestamp_zero():
    assert format_srt_timestamp(0.0) == "00:00:00,000"


def test_format_srt_timestamp_one_second():
    assert format_srt_timestamp(1.0) == "00:00:01,000"


def test_format_srt_timestamp_with_ms():
    assert format_srt_timestamp(1.5) == "00:00:01,500"


def test_format_srt_timestamp_over_one_minute():
    assert format_srt_timestamp(90.0) == "00:01:30,000"


def test_format_srt_timestamp_over_one_hour():
    assert format_srt_timestamp(3661.0) == "01:01:01,000"


# ---------------------------------------------------------------------------
# parse_srt_timestamp
# ---------------------------------------------------------------------------

def test_parse_srt_timestamp_zero():
    assert parse_srt_timestamp("00:00:00,000") == pytest.approx(0.0)


def test_parse_srt_timestamp_one_second():
    assert parse_srt_timestamp("00:00:01,000") == pytest.approx(1.0)


def test_parse_srt_timestamp_with_ms():
    assert parse_srt_timestamp("00:00:01,500") == pytest.approx(1.5)


def test_parse_srt_timestamp_roundtrip():
    original = 3661.25
    ts = format_srt_timestamp(original)
    recovered = parse_srt_timestamp(ts)
    assert recovered == pytest.approx(original, abs=0.001)


def test_parse_srt_timestamp_invalid_returns_zero():
    assert parse_srt_timestamp("invalid") == 0.0


# ---------------------------------------------------------------------------
# _parse_srt_blocks
# ---------------------------------------------------------------------------

def test_parse_srt_blocks_returns_list_of_dicts():
    p = _write_srt(_SAMPLE_SRT)
    try:
        blocks = _parse_srt_blocks(str(p))
        assert isinstance(blocks, list)
        assert len(blocks) == 2
        assert blocks[0]["start"] == pytest.approx(1.0)
        assert blocks[0]["end"] == pytest.approx(3.0)
        assert blocks[0]["text"] == "Hello world"
    finally:
        p.unlink(missing_ok=True)


def test_parse_srt_blocks_skips_empty():
    srt = "\n\n\n"
    p = _write_srt(srt)
    try:
        blocks = _parse_srt_blocks(str(p))
        assert blocks == []
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# parse_srt_blocks
# ---------------------------------------------------------------------------

def test_parse_srt_blocks_public_preserves_multiline():
    srt = "1\n00:00:01,000 --> 00:00:03,000\nLine one\nLine two\n\n"
    p = _write_srt(srt)
    try:
        blocks = parse_srt_blocks(str(p))
        assert "\n" in blocks[0]["text"]
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# write_srt_blocks
# ---------------------------------------------------------------------------

def test_write_srt_blocks_round_trip():
    p = _write_srt(_SAMPLE_SRT)
    try:
        blocks = parse_srt_blocks(str(p))
        out = Path(str(p) + ".out.srt")
        write_srt_blocks(blocks, str(out))
        try:
            recovered = parse_srt_blocks(str(out))
            assert len(recovered) == len(blocks)
            assert recovered[0]["text"] == blocks[0]["text"]
        finally:
            out.unlink(missing_ok=True)
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# slice_srt_to_text
# ---------------------------------------------------------------------------

def test_slice_srt_to_text_returns_text_in_range():
    p = _write_srt(_SAMPLE_SRT)
    try:
        text = slice_srt_to_text(str(p), 0.0, 4.0)
        assert "Hello world" in text
    finally:
        p.unlink(missing_ok=True)


def test_slice_srt_to_text_excludes_out_of_range():
    p = _write_srt(_SAMPLE_SRT)
    try:
        text = slice_srt_to_text(str(p), 4.0, 7.0)
        assert "Hello world" not in text
        assert "This is a test" in text
    finally:
        p.unlink(missing_ok=True)


def test_slice_srt_to_text_empty_range():
    p = _write_srt(_SAMPLE_SRT)
    try:
        text = slice_srt_to_text(str(p), 100.0, 200.0)
        assert text == ""
    finally:
        p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# _run_with_retry
# ---------------------------------------------------------------------------

def test_run_with_retry_succeeds_on_first_attempt():
    mock_result = MagicMock()
    with patch("subprocess.run", return_value=mock_result) as mock_run:
        result = _run_with_retry(["echo", "hello"], retries=2)
    assert mock_run.call_count == 1


def test_run_with_retry_raises_after_max_retries():
    with patch(
        "subprocess.run",
        side_effect=subprocess.CalledProcessError(1, ["cmd"], stderr="error"),
    ), patch("time.sleep"):
        with pytest.raises(RuntimeError, match="FFmpeg failed"):
            _run_with_retry(["cmd"], retries=2)
