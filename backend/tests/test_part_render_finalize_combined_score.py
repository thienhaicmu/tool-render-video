"""P0 T2 — Combined score block regression guard (Track D follow-up).

The combined score block at stages/part_render_finalize.py:396-461 is
wrapped in `try / except: pass`. Per Track D audit finding H4
(docs/review/AUDIT_2026-06-02_followup_7.md), if any of
`resolve_combined_score_weights`, the weight arithmetic, or either of
the two `_emit_render_event` calls silently raises, then:

  - seg["combined_weights"] never lands
  - seg["combined_score"] never lands
  - the `adaptive_score_weights_resolved` event is never emitted
  - the `combined_score_computed` event is never emitted
  - downstream best-clip ranking falls back to default weighting

This test file is the regression guard. It asserts that the combined
score side effects actually happen when the block runs normally.

If a future refactor breaks the block (e.g., loses the
`resolve_combined_score_weights` import or rewires `ctx.mv_market` away
from the expected attribute), at least one of these tests will fail
loudly instead of degrading silently.

See docs/review/AUDIT_2026-06-02_followup_8.md for the closure record.
"""
from __future__ import annotations

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
    ctx.payload.combined_scoring_enabled = True
    ctx.payload.adaptive_scoring_enabled = False
    ctx.payload.motion_aware_crop = False
    ctx.payload.aspect_ratio = "9:16"
    ctx.normalized_text_layers = []
    ctx.cancel_registry.is_cancelled.return_value = False
    return ctx


def _make_preflight():
    return MagicMock(
        vf_ct="vlog", vf_crf_delta=0, part_video_crf=20,
        vf_bitrate_profile="standard", vf_subtitle_bump=False,
        t_encode=0.0, motion_crop_fallback=[],
    )


def _make_encode():
    return MagicMock(render_ms=1000)


def _make_timeline():
    return MagicMock(source_duration=5.0, output_duration=5.0)


class TestCombinedScoreBlockActivation:
    """P0 T2 regression guard — H4 silent-fail surface.

    The combined score block must call resolve_combined_score_weights,
    populate seg["combined_weights"] + seg["combined_score"], and emit
    both `adaptive_score_weights_resolved` + `combined_score_computed`
    WS events. A silent NameError in the block would degrade ranking
    quietly with no visible signal.
    """

    def test_combined_score_populated_when_block_runs_clean(self, tmp_path):
        """Happy path: resolve_combined_score_weights returns a weights
        dict, the weighted sum lands in seg, both WS events emit."""
        from app.orchestration.stages.part_render_finalize import run_part_finalize

        srt_part = tmp_path / "p.srt"
        srt_part.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nhello world\n",
            encoding="utf-8",
        )
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("ass", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path)
        seg = {
            "start": 0.0, "end": 5.0, "duration": 5.0,
            "viral_score": 80, "motion_score": 50, "hook_score": 60,
            "priority_rank": 1, "content_type_hint": "vlog",
        }

        fake_weights = {
            "viral_weight":  0.50,
            "market_weight": 0.30,
            "hook_weight":   0.20,
            "reason":        "fixed",
        }

        with patch(
            "app.orchestration.stages.part_render_finalize.resolve_combined_score_weights",
            return_value=fake_weights,
        ) as mock_resolve, patch(
            "app.orchestration.stages.part_render_finalize._emit_render_event",
        ) as mock_emit, patch(
            "app.orchestration.stages.part_render_finalize._mv_score_part",
            return_value={
                "viral_score": 70,
                "viral_tier": "warm",
                "viral_market": "US",
                "reasons": [],
            },
        ), patch(
            "app.orchestration.stages.part_render_finalize.apply_micro_pacing",
            return_value={"applied": False, "segments_trimmed": 0,
                          "total_trim_ms": 0, "method": "none"},
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
                part_timeline=_make_timeline(),
                t_part_start=0.0, cut_ms=100,
                first_frame_scan_ms=10, subtitle_ass_ms=10,
                preflight=_make_preflight(), encode=_make_encode(),
            )

        # H4 regression guard: resolve_combined_score_weights was invoked.
        assert mock_resolve.called, (
            "T2 regression: resolve_combined_score_weights was not invoked. "
            "The combined score block at stages/part_render_finalize.py:396+ "
            "fell into its surrounding except:pass silently."
        )

        # Kwargs match the block's call signature exactly.
        resolve_kwargs = mock_resolve.call_args.kwargs
        assert resolve_kwargs["target_market"] == "US"
        assert resolve_kwargs["has_market_score"] is True  # mv_viral_score=70 was set
        assert resolve_kwargs["has_hook_score"] is True   # hook_score=60 > 0
        assert resolve_kwargs["duration"] == 5.0
        assert resolve_kwargs["adaptive_enabled"] is False

        # seg["combined_weights"] is the resolved dict.
        assert seg.get("combined_weights") == fake_weights, (
            "T2 regression: seg['combined_weights'] not set. "
            "The block ran resolve_combined_score_weights but the assignment "
            "raised silently before reaching the seg dict."
        )

        # seg["combined_score"] equals weighted-sum, clamped to [0,100], rounded to 0.1.
        # viral_score=80 * 0.50  = 40.0
        # mv_viral=70    * 0.30  = 21.0
        # hook=60        * 0.20  = 12.0
        # total = 73.0
        assert seg.get("combined_score") == 73.0, (
            f"T2 regression: combined_score arithmetic broken. "
            f"Expected 73.0 (80*0.5 + 70*0.3 + 60*0.2), got {seg.get('combined_score')!r}."
        )

        # Both WS events emitted.
        weights_emits = [
            c for c in mock_emit.call_args_list
            if c.kwargs.get("event") == "adaptive_score_weights_resolved"
        ]
        score_emits = [
            c for c in mock_emit.call_args_list
            if c.kwargs.get("event") == "combined_score_computed"
        ]
        assert len(weights_emits) == 1, (
            f"T2 regression: adaptive_score_weights_resolved event not emitted "
            f"(saw {len(weights_emits)} emits)."
        )
        assert len(score_emits) == 1, (
            f"T2 regression: combined_score_computed event not emitted "
            f"(saw {len(score_emits)} emits)."
        )

        # The combined_score_computed context carries the computed score.
        score_ctx = score_emits[0].kwargs.get("context", {})
        assert score_ctx.get("combined_score") == 73.0
        assert score_ctx.get("viral_score") == 80.0
        assert score_ctx.get("market_viral_score") == 70.0
        assert score_ctx.get("hook_score_component") == 60.0

    def test_combined_score_clamped_to_100_when_weights_overshoot(self, tmp_path):
        """When raw weighted sum would exceed 100 (e.g., weights summing >1
        or scores stacked high), the result clamps to 100.0."""
        from app.orchestration.stages.part_render_finalize import run_part_finalize

        srt_part = tmp_path / "p.srt"
        srt_part.write_text(
            "1\n00:00:00,000 --> 00:00:02,000\nhi\n",
            encoding="utf-8",
        )
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("ass", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path)
        seg = {
            "start": 0.0, "end": 5.0, "duration": 5.0,
            "viral_score": 100, "motion_score": 100, "hook_score": 100,
            "priority_rank": 1, "content_type_hint": "vlog",
        }

        # Weights summing to 1.5 — raw weighted sum would be 150, clamped to 100.
        overweight = {
            "viral_weight":  0.75,
            "market_weight": 0.45,
            "hook_weight":   0.30,
            "reason":        "test_clamp",
        }

        with patch(
            "app.orchestration.stages.part_render_finalize.resolve_combined_score_weights",
            return_value=overweight,
        ), patch(
            "app.orchestration.stages.part_render_finalize._emit_render_event"
        ), patch(
            "app.orchestration.stages.part_render_finalize._mv_score_part",
            return_value={"viral_score": 100, "viral_tier": "hot",
                          "viral_market": "US", "reasons": []},
        ), patch(
            "app.orchestration.stages.part_render_finalize.apply_micro_pacing",
            return_value={"applied": False, "segments_trimmed": 0,
                          "total_trim_ms": 0, "method": "none"},
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
                ctx=ctx, idx=2, seg=seg,
                srt_part=srt_part, ass_part=ass_part, final_part=final_part,
                part_subtitle_enabled=True,
                hook_overlay_applied_for_part=False,
                hook_subtitle_formatted=False,
                srt_count=1,
                trim_offset=0.0, effective_start=0.0,
                part_timeline=_make_timeline(),
                t_part_start=0.0, cut_ms=100,
                first_frame_scan_ms=10, subtitle_ass_ms=10,
                preflight=_make_preflight(), encode=_make_encode(),
            )

        # Clamp upper bound: 100*0.75 + 100*0.45 + 100*0.30 = 150 → 100.0
        assert seg.get("combined_score") == 100.0, (
            f"T2 regression: combined_score upper clamp broken. "
            f"Expected 100.0, got {seg.get('combined_score')!r}."
        )

    def test_combined_score_uses_viral_when_market_score_missing(self, tmp_path):
        """When seg lacks mv_viral_score, the block falls back to using
        viral_score in its place (per the _cs_mv assignment logic)."""
        from app.orchestration.stages.part_render_finalize import run_part_finalize

        srt_part = tmp_path / "p.srt"
        srt_part.write_text("s", encoding="utf-8")
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("a", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)

        ctx = _make_ctx(tmp_path)
        seg = {
            "start": 0.0, "end": 5.0, "duration": 5.0,
            "viral_score": 50, "motion_score": 50, "hook_score": 50,
            "priority_rank": 1, "content_type_hint": "vlog",
        }

        fake_weights = {
            "viral_weight":  0.50,
            "market_weight": 0.30,
            "hook_weight":   0.20,
            "reason":        "fixed",
        }

        with patch(
            "app.orchestration.stages.part_render_finalize.resolve_combined_score_weights",
            return_value=fake_weights,
        ) as mock_resolve, patch(
            "app.orchestration.stages.part_render_finalize._emit_render_event"
        ), patch(
            # _mv_score_part returns None-equivalent → seg["mv_viral_score"]
            # never gets set, so the combined block must fall back to viral.
            "app.orchestration.stages.part_render_finalize._mv_score_part",
            side_effect=Exception("simulated mv failure"),
        ), patch(
            "app.orchestration.stages.part_render_finalize.apply_micro_pacing",
            return_value={"applied": False, "segments_trimmed": 0,
                          "total_trim_ms": 0, "method": "none"},
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
                part_timeline=_make_timeline(),
                t_part_start=0.0, cut_ms=100,
                first_frame_scan_ms=10, subtitle_ass_ms=10,
                preflight=_make_preflight(), encode=_make_encode(),
            )

        # When mv_viral_score is missing, has_market_score must be False.
        # This proves the block's fallback path is wired correctly — pre-fix
        # code (or future refactor breakage) would never reach this assertion
        # because resolve_combined_score_weights wouldn't be called at all.
        assert mock_resolve.called
        assert mock_resolve.call_args.kwargs["has_market_score"] is False, (
            "T2 regression: has_market_score should be False when "
            "seg['mv_viral_score'] is unset (mv block raised silently)."
        )

        # Combined uses viral_score (50) in both the viral and market slots:
        # 50*0.5 + 50*0.3 + 50*0.2 = 50.0
        assert seg.get("combined_score") == 50.0
