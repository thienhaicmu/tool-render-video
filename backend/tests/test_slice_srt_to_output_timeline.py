"""
test_slice_srt_to_output_timeline.py — Unit tests for slice_srt_to_output_timeline().

Coverage:
- Source timestamp 10 s at speed 1.15 converts to output ≈ 8.70 s
- Output SRT is rebased to zero (first entry starts at 0)
- timeline.effective_speed is used (not a raw float from the caller)
- Output SRT file contains valid SRT content
- Empty source SRT does not crash
- Speed clamp [0.5, 1.5] is respected via TimelineMap
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.domain.timeline import TimelineMap
from app.services.subtitle_engine import slice_srt_to_output_timeline, parse_srt_blocks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_srt(content: str, tmp_dir: str) -> str:
    p = Path(tmp_dir) / "source.srt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _make_timeline(speed: float = 1.15, source_start: float = 0.0, source_end: float = 40.0) -> TimelineMap:
    return TimelineMap(
        source_start=source_start,
        source_end=source_end,
        effective_speed=speed,
        trim_offset=0.0,
    )


# Single block at t=10 s (in full-source time, no offset)
_SRT_ONE_BLOCK = """\
1
00:00:10,000 --> 00:00:12,000
Hello world

"""

# Two blocks: source t=5 s and t=15 s
_SRT_TWO_BLOCKS = """\
1
00:00:05,000 --> 00:00:07,000
First block

2
00:00:15,000 --> 00:00:17,000
Second block

"""

_SRT_EMPTY = ""


# ---------------------------------------------------------------------------
# Timing conversion
# ---------------------------------------------------------------------------

class TestOutputTimelineConversion:
    def test_single_block_speed_1_15(self):
        """Source 10 s at 1.15× → output ≈ 8.70 s."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15, source_start=0.0, source_end=30.0)
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)

        assert result["subtitle_count"] == 1
        assert result["first_start"] == pytest.approx(10.0 / 1.15, rel=1e-3)

    def test_single_block_speed_1_0(self):
        """At 1.0× speed, output time equals source time."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.0, source_start=0.0, source_end=30.0)
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)

        assert result["first_start"] == pytest.approx(10.0, rel=1e-3)

    def test_output_rebased_to_zero(self):
        """Output timestamps are rebased to zero relative to source_start."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            # source_start=0: block at 10 s → rebased to 10 s / speed (already at 0 base)
            tl = _make_timeline(speed=1.15, source_start=0.0, source_end=30.0)
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)

        # Rebased from source_start=0, so first_start = (10-0)/1.15
        assert result["first_start"] == pytest.approx(10.0 / 1.15, rel=1e-3)

    def test_rebase_with_nonzero_source_start(self):
        """With source_start=5, a block at 15 s → (15-5)/speed output time."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_TWO_BLOCKS, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.0, source_start=5.0, source_end=30.0)
            result = slice_srt_to_output_timeline(src, out, 5.0, 30.0, tl)

        # Block at 5 s → (5-5)/1.0 = 0.0; Block at 15 s → (15-5)/1.0 = 10.0
        assert result["first_start"] == pytest.approx(0.0, abs=0.001)
        assert result["last_start"] == pytest.approx(10.0, abs=0.001)

    def test_two_blocks_both_converted(self):
        """Both blocks in the window are converted to output timeline."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_TWO_BLOCKS, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15, source_start=0.0, source_end=30.0)
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)

        assert result["subtitle_count"] == 2
        assert result["first_start"] == pytest.approx(5.0 / 1.15, rel=1e-3)
        assert result["last_start"] == pytest.approx(15.0 / 1.15, rel=1e-3)


# ---------------------------------------------------------------------------
# Uses timeline.effective_speed
# ---------------------------------------------------------------------------

class TestUsesTimelineEffectiveSpeed:
    def test_clamped_speed_used(self):
        """TimelineMap clamps speed to [0.5, 1.5]; output uses clamped value."""
        # 2.5 is above _SPEED_MAX=1.5 → clamped to 1.5 by TimelineMap
        tl = TimelineMap(
            source_start=0.0,
            source_end=30.0,
            effective_speed=2.5,
            trim_offset=0.0,
        )
        assert tl.effective_speed == pytest.approx(1.5)
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)

        # Uses clamped 1.5, not the raw 2.5
        assert result["first_start"] == pytest.approx(10.0 / 1.5, rel=1e-3)

    def test_slow_speed_clamped_to_min(self):
        """Speed below 0.5 is clamped to 0.5 by TimelineMap."""
        tl = TimelineMap(
            source_start=0.0,
            source_end=30.0,
            effective_speed=0.1,
            trim_offset=0.0,
        )
        assert tl.effective_speed == pytest.approx(0.5)
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)

        assert result["first_start"] == pytest.approx(10.0 / 0.5, rel=1e-3)


# ---------------------------------------------------------------------------
# Output SRT validity
# ---------------------------------------------------------------------------

class TestOutputSrtValidity:
    def test_output_file_is_valid_srt(self):
        """Output file can be parsed back as valid SRT blocks."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_TWO_BLOCKS, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15)
            slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            blocks = parse_srt_blocks(out)

        assert len(blocks) == 2
        for b in blocks:
            assert b["start"] >= 0.0
            assert b["end"] > b["start"]
            assert b["text"].strip() != ""

    def test_output_blocks_have_reduced_timestamps(self):
        """At speed > 1, output timestamps are strictly less than source timestamps."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15)
            slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            blocks = parse_srt_blocks(out)

        assert blocks[0]["start"] < 10.0   # source was 10 s; output is 10/1.15 ≈ 8.7 s
        assert blocks[0]["end"] < 12.0


# ---------------------------------------------------------------------------
# Empty source SRT
# ---------------------------------------------------------------------------

class TestEmptySourceSrt:
    def test_empty_srt_does_not_crash(self):
        """Empty source SRT returns subtitle_count=0 and writes the output file."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_EMPTY, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15)
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            # Assertions must run inside the with block before the temp dir is removed.
            assert result["subtitle_count"] == 0
            assert result["first_start"] is None
            # Output file exists (written with zero entries)
            assert Path(out).exists()

    def test_empty_srt_output_has_no_blocks(self):
        """Empty source → output SRT parses as zero blocks."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_EMPTY, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15)
            slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            blocks = parse_srt_blocks(out)

        assert blocks == []

    def test_blocks_outside_window_excluded(self):
        """Blocks entirely outside [source_start, source_end] are excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)  # block at t=10s
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15, source_start=0.0, source_end=9.0)
            # Window ends at 9 s — block at 10 s is outside
            result = slice_srt_to_output_timeline(src, out, 0.0, 9.0, tl)

        assert result["subtitle_count"] == 0
