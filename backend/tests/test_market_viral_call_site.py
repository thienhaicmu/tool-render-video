"""Track C bug fix C2 regression guard — market viral scoring call site.

Before 2026-06-03, the call to _mv_score_part inside run_part_finalize
raised a silent NameError (caught by surrounding try/except) because
the Phase A refactor on 2026-05-28 (commit 765616d) extracted the
caller from render_pipeline.py to stages/part_renderer.py without
copying the `score_part_for_market as _mv_score_part` import.

The fix restores the import. These tests prove the call now actually
fires and the resulting mv_viral_* fields land in `seg`. If the import
is ever lost again (e.g., during a future refactor), at least one of
these tests will fail.

See docs/review/AUDIT_2026-06-02_followup_6.md for the timeline.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_ctx(tmp_path):
    """Minimal PartRenderContext stand-in for finalize testing."""
    ctx = MagicMock()
    ctx.job_id = "test_job"
    ctx.effective_channel = "manual"
    ctx.work_dir = tmp_path
    ctx.output_dir = tmp_path
    ctx.output_stem = "t"
    ctx.target_platform = "tiktok"
    ctx.mv_market = "US"
    ctx.hook_overlay_enabled = False
    ctx.hook_applied_text = ""
    ctx.source = {"title": "T", "slug": "t"}
    ctx.payload.voice_enabled = False
    ctx.payload.reup_bgm_enable = False
    ctx.payload.video_codec = "libx264"
    ctx.payload.playback_speed = 1.0
    ctx.payload.cleanup_temp_files = False
    ctx.payload.combined_scoring_enabled = False
    ctx.payload.adaptive_scoring_enabled = False
    ctx.payload.motion_aware_crop = False
    ctx.payload.aspect_ratio = "9:16"
    ctx.normalized_text_layers = []
    ctx.cancel_registry.is_cancelled.return_value = False
    return ctx


def _make_seg():
    return {
        "start": 0.0, "end": 5.0, "duration": 5.0,
        "viral_score": 50, "motion_score": 50, "hook_score": 50,
        "priority_rank": 1, "content_type_hint": "vlog",
    }


class TestMarketViralCallSiteActivation:
    """C2 fix regression guard.

    The market viral scoring block in run_part_finalize is wrapped in
    try/except: pass. Before C2, the NameError on _mv_score_part fell
    into that except and silently swallowed the entire scoring step.
    After C2, the call fires and the seg fields get populated.
    """

    def test_mv_score_part_is_invoked_when_srt_exists(self, tmp_path):
        """Calling run_part_finalize with an SRT triggers _mv_score_part.
        Before C2 fix, the NameError prevented invocation entirely."""
        from app.orchestration.stages.part_render_finalize import run_part_finalize

        srt_part = tmp_path / "p.srt"
        srt_part.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nhello world this is viral\n",
            encoding="utf-8",
        )
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("ass", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path)
        seg = _make_seg()
        preflight = MagicMock(
            vf_ct="vlog", vf_crf_delta=0, part_video_crf=20,
            vf_bitrate_profile="standard", vf_subtitle_bump=False,
            t_encode=0.0, motion_crop_fallback=[],
        )
        encode = MagicMock(render_ms=1000)
        timeline = MagicMock(source_duration=5.0, output_duration=5.0)

        with patch(
            "app.orchestration.stages.part_render_finalize._mv_score_part",
            return_value={
                "viral_score": 73,
                "viral_tier": "warm",
                "viral_market": "US",
                "reasons": ["strong hook", "good keywords"],
            },
        ) as mock_score, patch(
            "app.orchestration.stages.part_render_finalize.apply_micro_pacing",
            return_value={"applied": False, "segments_trimmed": 0, "total_trim_ms": 0, "method": "none"},
        ), patch(
            "app.orchestration.stages.part_render_finalize._maybe_prepend_remotion_hook_intro",
            return_value=0.0,
        ), patch(
            "app.orchestration.stages.part_render_finalize._maybe_prepend_asset_intro"
        ), patch(
            "app.orchestration.stages.part_render_finalize._maybe_append_asset_outro"
        ), patch(
            "app.orchestration.stages.part_render_finalize._maybe_apply_asset_logo"
        ), patch(
            "app.orchestration.stages.part_render_finalize._validate_render_output",
            return_value={
                "ok": True, "error": None, "warnings": [],
                "metadata": {"duration": 5.0, "size_bytes": 100,
                             "has_video": True, "has_audio": True},
            },
        ), patch(
            "app.orchestration.stages.part_render_finalize._assess_output_quality",
            return_value={"passed": True, "warnings": [], "hard_failures": [],
                          "checks": {}, "score_penalty": 0},
        ):
            run_part_finalize(
                ctx=ctx, idx=1, seg=seg,
                srt_part=srt_part, ass_part=ass_part, final_part=final_part,
                part_subtitle_enabled=True,
                hook_overlay_applied_for_part=False,
                hook_subtitle_formatted=False,
                srt_count=1,
                trim_offset=0.0, effective_start=0.0,
                part_timeline=timeline,
                t_part_start=0.0, cut_ms=100,
                first_frame_scan_ms=10, subtitle_ass_ms=10,
                preflight=preflight, encode=encode,
            )

        # C2 fix asserts: _mv_score_part WAS invoked (pre-fix this never
        # happened because NameError fell into except).
        assert mock_score.called, (
            "Track C C2 fix regression: _mv_score_part was not invoked. "
            "Check that `from app.services.viral_scoring import "
            "score_part_for_market as _mv_score_part` is still present "
            "in part_render_finalize.py."
        )

        # The scoring result should land in seg fields. Pre-C2-fix these
        # stayed unset (silent no-op).
        assert seg.get("mv_viral_score") == 73
        assert seg.get("mv_viral_tier") == "warm"
        assert seg.get("mv_viral_market") == "US"
        assert seg.get("mv_viral_reasons") == ["strong hook", "good keywords"]

    def test_mv_score_part_skipped_when_srt_missing_keeps_no_op(self, tmp_path):
        """When srt_part is missing, _mv_text stays empty but _mv_score_part
        is still called with empty text. Behavior preserved either way."""
        from app.orchestration.stages.part_render_finalize import run_part_finalize

        srt_part = tmp_path / "p.srt"  # NOT created
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("ass", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path)
        seg = _make_seg()
        preflight = MagicMock(
            vf_ct="vlog", vf_crf_delta=0, part_video_crf=20,
            vf_bitrate_profile="standard", vf_subtitle_bump=False,
            t_encode=0.0, motion_crop_fallback=[],
        )
        encode = MagicMock(render_ms=1000)
        timeline = MagicMock(source_duration=5.0, output_duration=5.0)

        with patch(
            "app.orchestration.stages.part_render_finalize._mv_score_part",
            return_value={"viral_score": 0, "viral_tier": "weak",
                          "viral_market": "US", "reasons": []},
        ) as mock_score, patch(
            "app.orchestration.stages.part_render_finalize.apply_micro_pacing",
            return_value={"applied": False, "segments_trimmed": 0, "total_trim_ms": 0, "method": "none"},
        ), patch(
            "app.orchestration.stages.part_render_finalize._maybe_prepend_remotion_hook_intro",
            return_value=0.0,
        ), patch(
            "app.orchestration.stages.part_render_finalize._maybe_prepend_asset_intro"
        ), patch(
            "app.orchestration.stages.part_render_finalize._maybe_append_asset_outro"
        ), patch(
            "app.orchestration.stages.part_render_finalize._maybe_apply_asset_logo"
        ), patch(
            "app.orchestration.stages.part_render_finalize._validate_render_output",
            return_value={
                "ok": True, "error": None, "warnings": [],
                "metadata": {"duration": 5.0, "size_bytes": 100,
                             "has_video": True, "has_audio": True},
            },
        ), patch(
            "app.orchestration.stages.part_render_finalize._assess_output_quality",
            return_value={"passed": True, "warnings": [], "hard_failures": [],
                          "checks": {}, "score_penalty": 0},
        ):
            run_part_finalize(
                ctx=ctx, idx=1, seg=seg,
                srt_part=srt_part, ass_part=ass_part, final_part=final_part,
                part_subtitle_enabled=True,
                hook_overlay_applied_for_part=False,
                hook_subtitle_formatted=False,
                srt_count=1,
                trim_offset=0.0, effective_start=0.0,
                part_timeline=timeline,
                t_part_start=0.0, cut_ms=100,
                first_frame_scan_ms=10, subtitle_ass_ms=10,
                preflight=preflight, encode=encode,
            )

        # Even with no SRT file on disk, _mv_score_part should still be
        # invoked (with empty text). This proves the import resolution
        # path works regardless of SRT presence.
        assert mock_score.called
        # The call uses empty text when SRT is missing.
        text_arg = mock_score.call_args.args[0]
        assert text_arg == "", f"Expected empty text when SRT missing, got {text_arg!r}"
