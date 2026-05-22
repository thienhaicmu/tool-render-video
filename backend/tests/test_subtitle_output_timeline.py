"""
test_subtitle_output_timeline.py — Unit tests for subtitles/output_timeline.py (Phase 4G.3).

Coverage:
- Module imports cleanly
- Same-object identity between output_timeline and subtitle_engine
- Speed 1.0 conversion leaves timestamps unchanged
- Speed 1.15 divides timestamps by 1.15
- TimelineMap clamped speed is used (not raw caller value)
- Empty source SRT does not crash
- Output file is valid SRT
- Old import path (subtitle_engine) still works end-to-end
- Function calls srt_core.slice_srt_by_time (not duplicate logic)
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.domain.timeline import TimelineMap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_srt(content: str, tmp_dir: str) -> str:
    p = Path(tmp_dir) / "source.srt"
    p.write_text(content, encoding="utf-8")
    return str(p)


def _make_timeline(speed: float = 1.15, source_start: float = 0.0, source_end: float = 30.0) -> TimelineMap:
    return TimelineMap(
        source_start=source_start,
        source_end=source_end,
        effective_speed=speed,
        trim_offset=0.0,
    )


_SRT_ONE_BLOCK = """\
1
00:00:10,000 --> 00:00:12,000
Hello world

"""

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
# Import tests
# ---------------------------------------------------------------------------

class TestOutputTimelineModuleImports:
    def test_module_imports_cleanly(self):
        import app.services.subtitles.output_timeline as m
        assert m is not None

    def test_slice_srt_to_output_timeline_importable_from_module(self):
        from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
        assert callable(slice_srt_to_output_timeline)

    def test_subtitle_engine_still_importable(self):
        import app.services.subtitle_engine as e
        assert hasattr(e, "slice_srt_to_output_timeline")

    def test_old_import_path_callable(self):
        from app.services.subtitle_engine import slice_srt_to_output_timeline
        assert callable(slice_srt_to_output_timeline)


# ---------------------------------------------------------------------------
# Same-object identity
# ---------------------------------------------------------------------------

class TestOutputTimelineSameObjectIdentity:
    def test_same_object_identity(self):
        import app.services.subtitles.output_timeline as ot
        import app.services.subtitle_engine as e
        assert e.slice_srt_to_output_timeline is ot.slice_srt_to_output_timeline

    def test_no_wrapper_same_function(self):
        from app.services.subtitles.output_timeline import slice_srt_to_output_timeline as fn_new
        from app.services.subtitle_engine import slice_srt_to_output_timeline as fn_old
        assert fn_new is fn_old


# ---------------------------------------------------------------------------
# Output timeline conversion — speed 1.0
# ---------------------------------------------------------------------------

class TestOutputTimelineSpeedOne:
    def test_speed_1_0_timestamps_unchanged(self):
        """At 1.0× speed, output timestamp equals source timestamp (rebased)."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.0, source_start=0.0)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
        assert result["first_start"] == pytest.approx(10.0, rel=1e-3)

    def test_speed_1_0_two_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_TWO_BLOCKS, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.0, source_start=0.0)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
        assert result["subtitle_count"] == 2
        assert result["first_start"] == pytest.approx(5.0, rel=1e-3)
        assert result["last_start"] == pytest.approx(15.0, rel=1e-3)


# ---------------------------------------------------------------------------
# Output timeline conversion — speed 1.15
# ---------------------------------------------------------------------------

class TestOutputTimelineSpeedOneFifteen:
    def test_speed_1_15_divides_timestamp(self):
        """Source 10 s at 1.15× → output ≈ 8.696 s."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15, source_start=0.0)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
        assert result["first_start"] == pytest.approx(10.0 / 1.15, rel=1e-3)

    def test_speed_1_15_output_less_than_source(self):
        """At speed > 1, output timestamps are strictly less than source timestamps."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15, source_start=0.0)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            from app.services.subtitles.srt_core import parse_srt_blocks
            blocks = parse_srt_blocks(out)
        assert blocks[0]["start"] < 10.0
        assert blocks[0]["end"] < 12.0


# ---------------------------------------------------------------------------
# Clamped speed behavior via TimelineMap
# ---------------------------------------------------------------------------

class TestOutputTimelineClampedSpeed:
    def test_clamped_speed_2_5_becomes_1_5(self):
        """TimelineMap clamps 2.5 → 1.5; output uses 1.5."""
        tl = TimelineMap(source_start=0.0, source_end=30.0, effective_speed=2.5, trim_offset=0.0)
        assert tl.effective_speed == pytest.approx(1.5)
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
        assert result["first_start"] == pytest.approx(10.0 / 1.5, rel=1e-3)

    def test_clamped_speed_0_1_becomes_0_5(self):
        """TimelineMap clamps 0.1 → 0.5; output uses 0.5."""
        tl = TimelineMap(source_start=0.0, source_end=30.0, effective_speed=0.1, trim_offset=0.0)
        assert tl.effective_speed == pytest.approx(0.5)
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
        assert result["first_start"] == pytest.approx(10.0 / 0.5, rel=1e-3)


# ---------------------------------------------------------------------------
# Empty source SRT
# ---------------------------------------------------------------------------

class TestOutputTimelineEmptySrt:
    def test_empty_srt_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_EMPTY, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            assert result["subtitle_count"] == 0
            assert result["first_start"] is None
            assert Path(out).exists()

    def test_empty_srt_output_has_no_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_EMPTY, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            from app.services.subtitles.srt_core import parse_srt_blocks
            blocks = parse_srt_blocks(out)
        assert blocks == []


# ---------------------------------------------------------------------------
# Output file validity
# ---------------------------------------------------------------------------

class TestOutputTimelineOutputValidity:
    def test_output_file_is_valid_srt(self):
        """Output file can be parsed back as valid SRT blocks."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_TWO_BLOCKS, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            from app.services.subtitles.srt_core import parse_srt_blocks
            blocks = parse_srt_blocks(out)
        assert len(blocks) == 2
        for b in blocks:
            assert b["start"] >= 0.0
            assert b["end"] > b["start"]
            assert b["text"].strip() != ""

    def test_output_subtitle_count_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_TWO_BLOCKS, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.0)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
        assert result["subtitle_count"] == 2


# ---------------------------------------------------------------------------
# Old import path end-to-end
# ---------------------------------------------------------------------------

class TestOutputTimelineOldImportPath:
    def test_old_path_end_to_end(self):
        """Import from subtitle_engine and run the function — must work identically."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.15, source_start=0.0)
            from app.services.subtitle_engine import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
        assert result["subtitle_count"] == 1
        assert result["first_start"] == pytest.approx(10.0 / 1.15, rel=1e-3)

    def test_old_path_empty_srt(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_EMPTY, tmp)
            out = str(Path(tmp) / "overlay.srt")
            tl = _make_timeline(speed=1.0)
            from app.services.subtitle_engine import slice_srt_to_output_timeline
            result = slice_srt_to_output_timeline(src, out, 0.0, 30.0, tl)
            assert result["subtitle_count"] == 0
            assert Path(out).exists()


# ---------------------------------------------------------------------------
# Delegates to srt_core.slice_srt_by_time (no duplicate logic)
# ---------------------------------------------------------------------------

class TestOutputTimelineDelegatesToSrtCore:
    def test_uses_srt_core_slice_srt_by_time(self):
        """output_timeline.py must import slice_srt_by_time from srt_core (no copy)."""
        import app.services.subtitles.output_timeline as ot
        from app.services.subtitles.srt_core import slice_srt_by_time
        assert ot.slice_srt_by_time is slice_srt_by_time

    def test_no_timeline_map_defined_in_module(self):
        """output_timeline.py imports TimelineMap — does not define its own."""
        import app.services.subtitles.output_timeline as ot
        import inspect
        src = inspect.getsource(ot)
        # Should import TimelineMap, not define it
        assert "class TimelineMap" not in src
        assert "TimelineMap" in src

    def test_apply_playback_speed_true_used(self):
        """Verify timestamps are divided by speed (apply_playback_speed=True behavior)."""
        with tempfile.TemporaryDirectory() as tmp:
            src = _write_srt(_SRT_ONE_BLOCK, tmp)
            out_applied = str(Path(tmp) / "applied.srt")
            out_not_applied = str(Path(tmp) / "not_applied.srt")
            tl = _make_timeline(speed=1.15, source_start=0.0)
            from app.services.subtitles.output_timeline import slice_srt_to_output_timeline
            from app.services.subtitles.srt_core import slice_srt_by_time, parse_srt_blocks
            slice_srt_to_output_timeline(src, out_applied, 0.0, 30.0, tl)
            # Comparison: same slice but without speed division
            slice_srt_by_time(src, out_not_applied, 0.0, 30.0, rebase_to_zero=True, playback_speed=1.15, apply_playback_speed=False)
            blocks_applied = parse_srt_blocks(out_applied)
            blocks_not_applied = parse_srt_blocks(out_not_applied)
        # Speed-applied timestamps are smaller (divided by 1.15)
        assert blocks_applied[0]["start"] < blocks_not_applied[0]["start"]
