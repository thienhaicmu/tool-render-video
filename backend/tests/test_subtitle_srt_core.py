"""Tests for Phase 4G.2 — SRT core extraction.

Verifies:
- app.services.subtitles.srt_core imports cleanly
- app.services.subtitle_engine still exposes all moved SRT symbols
- Same-object identity for all moved functions
- format_srt_timestamp / parse_srt_timestamp round-trip
- _parse_srt_blocks / parse_srt_blocks parsing behavior unchanged
- write_srt_blocks round-trip
- slice_srt_by_time: rebase, filter, speed-scale behavior unchanged
- slice_srt_to_text behavior unchanged
- _run_with_retry retry behavior (mocked subprocess)
- slice_srt_to_output_timeline still works via subtitle_engine (not moved)
- Old import paths work end-to-end
"""
import os
import tempfile
import subprocess
import pytest


# ---------------------------------------------------------------------------
# Import tests
# ---------------------------------------------------------------------------

class TestSrtCoreModuleImports:
    def test_srt_core_imports_cleanly(self):
        import app.services.subtitles.srt_core

    def test_subtitle_engine_imports_cleanly(self):
        import app.services.subtitle_engine

    def test_srt_core_has_no_styles_dep(self):
        # srt_core must not expose symbols from subtitle_engine, styles, or TimelineMap
        import app.services.subtitles.srt_core as m
        assert not hasattr(m, "TimelineMap"), "srt_core must not expose TimelineMap"
        assert not hasattr(m, "ASSPreset"), "srt_core must not expose ASSPreset (styles dep)"
        assert not hasattr(m, "_PRESETS"), "srt_core must not expose _PRESETS (styles dep)"
        assert not hasattr(m, "whisper"), "srt_core must not expose whisper"

    def test_srt_core_has_no_whisper_dep(self):
        import app.services.subtitles.srt_core as m
        import inspect
        src = inspect.getsource(m)
        assert "whisper" not in src


# ---------------------------------------------------------------------------
# Same-object identity tests
# ---------------------------------------------------------------------------

class TestSrtCoreSameObjectIdentity:
    def test_format_srt_timestamp_identity(self):
        import app.services.subtitles.srt_core as c
        import app.services.subtitle_engine as e
        assert c.format_srt_timestamp is e.format_srt_timestamp

    def test_parse_srt_timestamp_identity(self):
        import app.services.subtitles.srt_core as c
        import app.services.subtitle_engine as e
        assert c.parse_srt_timestamp is e.parse_srt_timestamp

    def test_parse_srt_blocks_identity(self):
        import app.services.subtitles.srt_core as c
        import app.services.subtitle_engine as e
        assert c.parse_srt_blocks is e.parse_srt_blocks

    def test_write_srt_blocks_identity(self):
        import app.services.subtitles.srt_core as c
        import app.services.subtitle_engine as e
        assert c.write_srt_blocks is e.write_srt_blocks

    def test_slice_srt_by_time_identity(self):
        import app.services.subtitles.srt_core as c
        import app.services.subtitle_engine as e
        assert c.slice_srt_by_time is e.slice_srt_by_time

    def test_slice_srt_to_text_identity(self):
        import app.services.subtitles.srt_core as c
        import app.services.subtitle_engine as e
        assert c.slice_srt_to_text is e.slice_srt_to_text

    def test_run_with_retry_identity(self):
        import app.services.subtitles.srt_core as c
        import app.services.subtitle_engine as e
        assert c._run_with_retry is e._run_with_retry

    def test_slice_srt_to_output_timeline_only_in_engine(self):
        import app.services.subtitles.srt_core as c
        import app.services.subtitle_engine as e
        assert hasattr(e, "slice_srt_to_output_timeline")
        assert not hasattr(c, "slice_srt_to_output_timeline")


# ---------------------------------------------------------------------------
# Timestamp format/parse tests
# ---------------------------------------------------------------------------

class TestTimestampFormatParse:
    def test_format_zero(self):
        from app.services.subtitles.srt_core import format_srt_timestamp
        assert format_srt_timestamp(0.0) == "00:00:00,000"

    def test_format_one_hour(self):
        from app.services.subtitles.srt_core import format_srt_timestamp
        assert format_srt_timestamp(3600.0) == "01:00:00,000"

    def test_format_milliseconds(self):
        from app.services.subtitles.srt_core import format_srt_timestamp
        assert format_srt_timestamp(1.234) == "00:00:01,234"

    def test_format_rounds_to_ms(self):
        from app.services.subtitles.srt_core import format_srt_timestamp
        # int(round(1.2345 * 1000)) = int(round(1234.5)) = 1234 (banker's rounding)
        result = format_srt_timestamp(1.2345)
        assert result == "00:00:01,234"

    def test_parse_basic(self):
        from app.services.subtitles.srt_core import parse_srt_timestamp
        assert parse_srt_timestamp("00:00:01,234") == pytest.approx(1.234, abs=1e-9)

    def test_parse_dot_separator(self):
        from app.services.subtitles.srt_core import parse_srt_timestamp
        assert parse_srt_timestamp("00:00:01.234") == pytest.approx(1.234, abs=1e-9)

    def test_parse_one_hour(self):
        from app.services.subtitles.srt_core import parse_srt_timestamp
        assert parse_srt_timestamp("01:00:00,000") == pytest.approx(3600.0, abs=1e-9)

    def test_parse_malformed_returns_zero(self):
        from app.services.subtitles.srt_core import parse_srt_timestamp
        assert parse_srt_timestamp("badformat") == 0.0

    def test_roundtrip(self):
        from app.services.subtitles.srt_core import format_srt_timestamp, parse_srt_timestamp
        for sec in [0.0, 1.0, 59.999, 3600.0, 7261.123]:
            formatted = format_srt_timestamp(sec)
            parsed = parse_srt_timestamp(formatted)
            assert abs(parsed - sec) < 0.001, f"roundtrip failed for {sec}: got {parsed}"


# ---------------------------------------------------------------------------
# SRT parsing tests
# ---------------------------------------------------------------------------

SRT_SIMPLE = """\
1
00:00:01,000 --> 00:00:02,500
Hello world

2
00:00:03,000 --> 00:00:04,000
Second block

"""

SRT_MULTILINE = """\
1
00:00:01,000 --> 00:00:02,000
Line one
Line two

"""


def _write_srt(content: str, suffix: str = ".srt"):
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestParseSrtBlocks:
    def test_basic_two_blocks(self):
        from app.services.subtitles.srt_core import _parse_srt_blocks
        path = _write_srt(SRT_SIMPLE)
        try:
            blocks = _parse_srt_blocks(path)
            assert len(blocks) == 2
            assert blocks[0]["start"] == pytest.approx(1.0)
            assert blocks[0]["end"] == pytest.approx(2.5)
            assert blocks[0]["text"] == "Hello world"
            assert blocks[1]["start"] == pytest.approx(3.0)
        finally:
            os.unlink(path)

    def test_multiline_text_joined_with_space(self):
        from app.services.subtitles.srt_core import _parse_srt_blocks
        path = _write_srt(SRT_MULTILINE)
        try:
            blocks = _parse_srt_blocks(path)
            assert len(blocks) == 1
            # _parse_srt_blocks joins with space
            assert blocks[0]["text"] == "Line one Line two"
        finally:
            os.unlink(path)

    def test_empty_file(self):
        from app.services.subtitles.srt_core import _parse_srt_blocks
        path = _write_srt("\n\n")
        try:
            assert _parse_srt_blocks(path) == []
        finally:
            os.unlink(path)

    def test_blocks_with_zero_duration_filtered(self):
        srt = "1\n00:00:01,000 --> 00:00:01,000\ntext\n\n"
        from app.services.subtitles.srt_core import _parse_srt_blocks
        path = _write_srt(srt)
        try:
            assert _parse_srt_blocks(path) == []
        finally:
            os.unlink(path)


class TestPublicParseSrtBlocks:
    def test_multiline_text_joined_with_newline(self):
        from app.services.subtitles.srt_core import parse_srt_blocks
        path = _write_srt(SRT_MULTILINE)
        try:
            blocks = parse_srt_blocks(path)
            assert len(blocks) == 1
            # parse_srt_blocks preserves newlines
            assert blocks[0]["text"] == "Line one\nLine two"
        finally:
            os.unlink(path)

    def test_single_line_text(self):
        from app.services.subtitles.srt_core import parse_srt_blocks
        path = _write_srt(SRT_SIMPLE)
        try:
            blocks = parse_srt_blocks(path)
            assert len(blocks) == 2
            assert blocks[0]["text"] == "Hello world"
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# write_srt_blocks round-trip test
# ---------------------------------------------------------------------------

class TestWriteSrtBlocks:
    def test_roundtrip_parse_write(self):
        from app.services.subtitles.srt_core import parse_srt_blocks, write_srt_blocks
        src_path = _write_srt(SRT_SIMPLE)
        out_fd, out_path = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            blocks = parse_srt_blocks(src_path)
            write_srt_blocks(blocks, out_path)
            blocks2 = parse_srt_blocks(out_path)
            assert len(blocks) == len(blocks2)
            for b1, b2 in zip(blocks, blocks2):
                assert abs(b1["start"] - b2["start"]) < 0.001
                assert abs(b1["end"] - b2["end"]) < 0.001
                assert b1["text"] == b2["text"]
        finally:
            os.unlink(src_path)
            os.unlink(out_path)

    def test_multiline_text_preserved(self):
        from app.services.subtitles.srt_core import parse_srt_blocks, write_srt_blocks
        src_path = _write_srt(SRT_MULTILINE)
        out_fd, out_path = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            blocks = parse_srt_blocks(src_path)
            write_srt_blocks(blocks, out_path)
            content = open(out_path, encoding="utf-8").read()
            assert "Line one\nLine two" in content
        finally:
            os.unlink(src_path)
            os.unlink(out_path)


# ---------------------------------------------------------------------------
# slice_srt_by_time tests
# ---------------------------------------------------------------------------

SRT_FOR_SLICE = """\
1
00:00:05,000 --> 00:00:07,000
Alpha

2
00:00:10,000 --> 00:00:12,000
Beta

3
00:00:20,000 --> 00:00:22,000
Gamma

"""


class TestSliceSrtByTime:
    def _make_srt(self):
        return _write_srt(SRT_FOR_SLICE)

    def test_rebase_to_zero(self):
        from app.services.subtitles.srt_core import slice_srt_by_time, _parse_srt_blocks
        src = self._make_srt()
        out_fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            meta = slice_srt_by_time(src, out, 5.0, 15.0)
            blocks = _parse_srt_blocks(out)
            assert len(blocks) == 2
            # Alpha starts at 5.0 in source → rebased to 0.0
            assert blocks[0]["start"] == pytest.approx(0.0, abs=0.001)
            # Beta starts at 10.0 → rebased to 5.0
            assert blocks[1]["start"] == pytest.approx(5.0, abs=0.001)
            assert meta["subtitle_count"] == 2
        finally:
            os.unlink(src)
            os.unlink(out)

    def test_blocks_outside_range_excluded(self):
        from app.services.subtitles.srt_core import slice_srt_by_time, _parse_srt_blocks
        src = self._make_srt()
        out_fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            meta = slice_srt_by_time(src, out, 5.0, 8.0)
            blocks = _parse_srt_blocks(out)
            # Only Alpha overlaps 5–8
            assert len(blocks) == 1
            assert blocks[0]["text"] == "Alpha"
        finally:
            os.unlink(src)
            os.unlink(out)

    def test_apply_playback_speed_true(self):
        from app.services.subtitles.srt_core import slice_srt_by_time, _parse_srt_blocks
        src = self._make_srt()
        out_fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            # Use speed=1.5 (within clamp range [0.5, 1.5])
            meta = slice_srt_by_time(src, out, 5.0, 15.0, playback_speed=1.5, apply_playback_speed=True)
            blocks = _parse_srt_blocks(out)
            # Alpha: (5.0 - 5.0) / 1.5 = 0.0
            assert blocks[0]["start"] == pytest.approx(0.0, abs=0.001)
            # Beta: (10.0 - 5.0) / 1.5 ≈ 3.333
            assert blocks[1]["start"] == pytest.approx(10.0 / 3.0, abs=0.001)
        finally:
            os.unlink(src)
            os.unlink(out)

    def test_apply_playback_speed_false(self):
        from app.services.subtitles.srt_core import slice_srt_by_time, _parse_srt_blocks
        src = self._make_srt()
        out_fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            slice_srt_by_time(src, out, 5.0, 15.0, playback_speed=2.0, apply_playback_speed=False)
            blocks = _parse_srt_blocks(out)
            # speed not applied: (10.0 - 5.0) / 1.0 = 5.0
            assert blocks[1]["start"] == pytest.approx(5.0, abs=0.001)
        finally:
            os.unlink(src)
            os.unlink(out)

    def test_empty_result_metadata(self):
        from app.services.subtitles.srt_core import slice_srt_by_time
        src = self._make_srt()
        out_fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            meta = slice_srt_by_time(src, out, 50.0, 60.0)
            assert meta["subtitle_count"] == 0
            assert meta["first_start"] is None
            assert meta["last_end"] is None
        finally:
            os.unlink(src)
            os.unlink(out)

    def test_speed_clamped_to_0_5_min(self):
        from app.services.subtitles.srt_core import slice_srt_by_time
        src = self._make_srt()
        out_fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            meta = slice_srt_by_time(src, out, 5.0, 15.0, playback_speed=0.1)
            assert meta["playback_speed"] == pytest.approx(0.5)
        finally:
            os.unlink(src)
            os.unlink(out)

    def test_speed_clamped_to_1_5_max(self):
        from app.services.subtitles.srt_core import slice_srt_by_time
        src = self._make_srt()
        out_fd, out = tempfile.mkstemp(suffix=".srt")
        os.close(out_fd)
        try:
            meta = slice_srt_by_time(src, out, 5.0, 15.0, playback_speed=9.9)
            assert meta["playback_speed"] == pytest.approx(1.5)
        finally:
            os.unlink(src)
            os.unlink(out)


# ---------------------------------------------------------------------------
# slice_srt_to_text tests
# ---------------------------------------------------------------------------

class TestSliceSrtToText:
    def test_returns_overlapping_text(self):
        from app.services.subtitles.srt_core import slice_srt_to_text
        src = _write_srt(SRT_FOR_SLICE)
        try:
            text = slice_srt_to_text(src, 5.0, 15.0)
            assert "Alpha" in text
            assert "Beta" in text
            assert "Gamma" not in text
        finally:
            os.unlink(src)

    def test_no_file_written(self, tmp_path):
        from app.services.subtitles.srt_core import slice_srt_to_text
        src = _write_srt(SRT_FOR_SLICE)
        before = list(tmp_path.iterdir())
        try:
            slice_srt_to_text(src, 5.0, 15.0)
            after = list(tmp_path.iterdir())
            assert before == after
        finally:
            os.unlink(src)

    def test_empty_range_returns_empty_string(self):
        from app.services.subtitles.srt_core import slice_srt_to_text
        src = _write_srt(SRT_FOR_SLICE)
        try:
            assert slice_srt_to_text(src, 50.0, 60.0) == ""
        finally:
            os.unlink(src)


# ---------------------------------------------------------------------------
# _run_with_retry tests
# ---------------------------------------------------------------------------

class TestRunWithRetry:
    def test_success_on_first_try(self, monkeypatch):
        from app.services.subtitles.srt_core import _run_with_retry
        import unittest.mock as mock

        fake_result = mock.MagicMock()
        fake_result.returncode = 0

        with mock.patch("app.services.subtitles.srt_core.subprocess.run", return_value=fake_result) as m:
            result = _run_with_retry(["echo", "hi"], retries=2)
            assert m.call_count == 1

    def test_retries_on_subprocess_error(self, monkeypatch):
        from app.services.subtitles.srt_core import _run_with_retry
        import unittest.mock as mock

        err = subprocess.CalledProcessError(1, ["cmd"], stderr="err")
        with mock.patch("app.services.subtitles.srt_core.subprocess.run", side_effect=err):
            with mock.patch("app.services.subtitles.srt_core.time.sleep"):
                with pytest.raises(RuntimeError, match="FFmpeg failed"):
                    _run_with_retry(["cmd"], retries=2, wait_sec=0.0)

    def test_retry_count_exact(self, monkeypatch):
        from app.services.subtitles.srt_core import _run_with_retry
        import unittest.mock as mock

        call_count = {"n": 0}
        def fake_run(*args, **kwargs):
            call_count["n"] += 1
            raise subprocess.CalledProcessError(1, ["cmd"], stderr="")
        with mock.patch("app.services.subtitles.srt_core.subprocess.run", side_effect=fake_run):
            with mock.patch("app.services.subtitles.srt_core.time.sleep"):
                with pytest.raises(RuntimeError):
                    _run_with_retry(["cmd"], retries=2, wait_sec=0.0)
        # retries=2 means attempt up to 3 times (1 + 2 retries)
        assert call_count["n"] == 3


# ---------------------------------------------------------------------------
# slice_srt_to_output_timeline still works via subtitle_engine
# ---------------------------------------------------------------------------

class TestSliceSrtToOutputTimelineEngineCompat:
    def test_engine_still_has_output_timeline_fn(self):
        from app.services.subtitle_engine import slice_srt_to_output_timeline
        assert callable(slice_srt_to_output_timeline)

    def test_output_timeline_calls_slice_srt_by_time(self, monkeypatch):
        import app.services.subtitle_engine as e
        import unittest.mock as mock

        dummy_meta = {"subtitle_count": 0, "first_start": None, "first_end": None,
                      "last_start": None, "last_end": None, "playback_speed": 1.0,
                      "apply_playback_speed": True}

        timeline_mock = mock.MagicMock()
        timeline_mock.effective_speed = 1.15

        with mock.patch.object(e, "slice_srt_by_time", return_value=dummy_meta) as m:
            result = e.slice_srt_to_output_timeline("in.srt", "out.srt", 10.0, 70.0, timeline_mock)
            m.assert_called_once_with(
                "in.srt", "out.srt", 10.0, 70.0,
                rebase_to_zero=True,
                playback_speed=1.15,
                apply_playback_speed=True,
            )
