"""P0 T1 — Cover frame extraction regression guard (Track D follow-up).

The cover frame block at stages/part_done.py:142-208 is wrapped in
`try / except: pass`. Per Track D audit finding H2
(docs/review/AUDIT_2026-06-02_followup_7.md), if any of
`_select_cover_frame_time`, `extract_thumbnail_frame`,
`_cover_path.write_bytes(...)`, or the `cover_frame_selected` emit
silently raises, the cover frame goes missing for the part with no
visible failure signal.

This test file is the regression guard. It asserts the cover frame
side effects actually happen when the block runs normally:
  - extract_thumbnail_frame is invoked
  - cover JPG file is written to disk
  - seg["cover_file"] + seg["cover_frame_offset"] are set
  - cover_frame_selected WS event is emitted

If a future refactor breaks any of these (e.g., loses an import that
makes the block raise NameError silently), at least one of these
tests will fail loudly.

See docs/review/AUDIT_2026-06-02_followup_8.md for the closure record.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _make_ctx(tmp_path):
    """Minimal PartRenderContext stand-in for cover-frame testing."""
    ctx = MagicMock()
    ctx.job_id = "test_job"
    ctx.effective_channel = "manual"
    ctx.output_dir = tmp_path
    ctx.output_stem = "stem"
    ctx.target_platform = "tiktok"
    ctx.payload.cleanup_temp_files = False
    ctx.ai_edit_plan = None
    ctx.source = {"title": "T"}
    return ctx


class TestCoverFrameExtractionActivation:
    """P0 T1 regression guard — H2 silent-fail surface.

    The cover frame extraction block must produce a JPG file and
    populate seg["cover_file"] + seg["cover_frame_offset"]. Pre-fix
    code (or a future regression) would silently swallow exceptions
    in this block, leaving the cover missing without notice.
    """

    def test_cover_jpg_written_and_seg_fields_set(self, tmp_path):
        """Cover frame happy path: extract_thumbnail_frame returns bytes,
        JPG gets written, seg fields get populated, WS event emitted."""
        from app.orchestration.stages.part_done import run_part_done

        srt_part = tmp_path / "p.srt"
        srt_part.write_text("subtitle", encoding="utf-8")
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("ass", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)
        raw_part = tmp_path / "p_raw.mp4"
        raw_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path)
        seg = {"start": 0.0, "end": 10.0, "duration": 10.0,
               "viral_score": 50, "motion_score": 50, "hook_score": 75,
               "priority_rank": 1}
        srt_meta = {"first_start": 0.0, "first_end": 2.0,
                    "last_start": 8.0, "last_end": 10.0}

        fake_jpg_bytes = b"\xff\xd8\xff\xe0" + b"jpgcontent" * 10

        with patch(
            "app.orchestration.stages.part_done._select_cover_frame_time",
            return_value=(3.5, "hook_aligned"),
        ) as mock_select, patch(
            "app.orchestration.stages.part_done.extract_thumbnail_frame",
            return_value=fake_jpg_bytes,
        ) as mock_extract, patch(
            "app.orchestration.stages.part_done._emit_render_event"
        ) as mock_emit, patch(
            "app.orchestration.stages.part_done.upsert_job_part"
        ), patch(
            # _assess_render_quality_intelligence — covered by C1 test, mock here to isolate
            "app.orchestration.stages.part_done._assess_render_quality_intelligence",
            return_value=None,
        ):
            run_part_done(
                ctx=ctx, idx=1, seg=seg,
                raw_part=raw_part, srt_part=srt_part, ass_part=ass_part,
                final_part=final_part, part_name="p.mp4",
                srt_meta=srt_meta, variant_type="",
                part_subtitle_enabled=True,
            )

        # H2 regression guard: _select_cover_frame_time was called
        assert mock_select.called, (
            "T1 regression: _select_cover_frame_time was not invoked. "
            "Check that the cover frame block at stages/part_done.py:142+ "
            "still runs without silent failure."
        )

        # H2 regression guard: extract_thumbnail_frame was called with final_part path
        assert mock_extract.called, (
            "T1 regression: extract_thumbnail_frame was not invoked. "
            "An exception likely fell into the surrounding except:pass."
        )
        # First positional arg is the video path string
        extract_args = mock_extract.call_args.args
        assert extract_args[0] == str(final_part)

        # The JPG file was written to disk
        expected_jpg = tmp_path / "stem_part_001_cover.jpg"
        assert expected_jpg.exists(), (
            f"T1 regression: cover JPG not written. Expected at {expected_jpg}. "
            "_cover_path.write_bytes(...) may have raised silently."
        )
        assert expected_jpg.read_bytes() == fake_jpg_bytes

        # seg dict mutations
        assert seg.get("cover_file") == str(expected_jpg)
        assert seg.get("cover_frame_offset") == 3.5

        # cover_frame_selected WS event emitted
        cover_emits = [
            c for c in mock_emit.call_args_list
            if c.kwargs.get("event") == "cover_frame_selected"
        ]
        assert len(cover_emits) == 1, (
            f"T1 regression: cover_frame_selected event not emitted "
            f"(saw {len(cover_emits)} emits). Check the _emit_render_event "
            f"call inside the cover frame block."
        )
        # Event context carries the cover_file
        ctx_kwarg = cover_emits[0].kwargs.get("context", {})
        assert ctx_kwarg.get("cover_file") == str(expected_jpg)
        assert ctx_kwarg.get("frame_offset") == 3.5
        assert ctx_kwarg.get("cover_reason") == "hook_aligned"

    def test_variant_type_uses_variant_naming(self, tmp_path):
        """When variant_type is set, the cover file uses the variant
        naming pattern (no part_NNN suffix)."""
        from app.orchestration.stages.part_done import run_part_done

        srt_part = tmp_path / "p.srt"
        srt_part.write_text("s", encoding="utf-8")
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("a", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)
        raw_part = tmp_path / "p_raw.mp4"
        raw_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path)
        seg = {"start": 0.0, "end": 5.0, "duration": 5.0,
               "viral_score": 60, "motion_score": 60, "hook_score": 60,
               "priority_rank": 1}

        with patch(
            "app.orchestration.stages.part_done._select_cover_frame_time",
            return_value=(1.0, "default"),
        ), patch(
            "app.orchestration.stages.part_done.extract_thumbnail_frame",
            return_value=b"jpg",
        ), patch(
            "app.orchestration.stages.part_done._emit_render_event"
        ), patch(
            "app.orchestration.stages.part_done.upsert_job_part"
        ), patch(
            "app.orchestration.stages.part_done._assess_render_quality_intelligence",
            return_value=None,
        ):
            run_part_done(
                ctx=ctx, idx=2, seg=seg,
                raw_part=raw_part, srt_part=srt_part, ass_part=ass_part,
                final_part=final_part, part_name="p.mp4",
                srt_meta={}, variant_type="aggressive",
                part_subtitle_enabled=False,
            )

        # When variant_type is "aggressive", the file is stem_aggressive_cover.jpg
        # (NOT stem_part_002_cover.jpg).
        expected = tmp_path / "stem_aggressive_cover.jpg"
        assert expected.exists()
        assert seg.get("cover_file") == str(expected)

    def test_extract_thumbnail_returns_none_skips_file_write(self, tmp_path):
        """If extract_thumbnail_frame returns None (e.g., video corrupt),
        the JPG write is skipped. seg fields stay unset.
        This is intended behavior — exception NOT raised."""
        from app.orchestration.stages.part_done import run_part_done

        srt_part = tmp_path / "p.srt"
        srt_part.write_text("s", encoding="utf-8")
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("a", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)
        raw_part = tmp_path / "p_raw.mp4"
        raw_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path)
        seg = {"start": 0.0, "end": 5.0, "duration": 5.0,
               "viral_score": 50, "motion_score": 50, "hook_score": 50,
               "priority_rank": 1}

        with patch(
            "app.orchestration.stages.part_done._select_cover_frame_time",
            return_value=(2.0, "default"),
        ), patch(
            "app.orchestration.stages.part_done.extract_thumbnail_frame",
            return_value=None,  # video corrupt or no readable frame
        ), patch(
            "app.orchestration.stages.part_done._emit_render_event"
        ) as mock_emit, patch(
            "app.orchestration.stages.part_done.upsert_job_part"
        ), patch(
            "app.orchestration.stages.part_done._assess_render_quality_intelligence",
            return_value=None,
        ):
            run_part_done(
                ctx=ctx, idx=1, seg=seg,
                raw_part=raw_part, srt_part=srt_part, ass_part=ass_part,
                final_part=final_part, part_name="p.mp4",
                srt_meta={}, variant_type="",
                part_subtitle_enabled=False,
            )

        # No JPG file should exist
        expected_jpg = tmp_path / "stem_part_001_cover.jpg"
        assert not expected_jpg.exists()
        # seg fields should NOT be set
        assert "cover_file" not in seg
        assert "cover_frame_offset" not in seg
        # cover_frame_selected should NOT be emitted
        cover_emits = [
            c for c in mock_emit.call_args_list
            if c.kwargs.get("event") == "cover_frame_selected"
        ]
        assert len(cover_emits) == 0
