"""P1 Contract #8 — `qa_pipeline` validation never bypassed.

Per CLAUDE.md Sacred Contract #8, `_validate_render_output` is the
SOLE output validation gate. It must:
  - Be invoked on every render success path.
  - Raise (via the caller) on `ok=False` so the failure surfaces.
  - NEVER be wrapped in a try/except that swallows a validation
    failure and returns success.
  - NEVER have its hard-fail thresholds (file size, duration, video
    stream presence, audio stream presence) lowered to make a
    specific broken render pass.

These tests fix the gap identified in the Track D D2 audit
(docs/review/AUDIT_2026-06-02_followup_7.md Finding 4 row #8).

Two layers of guard:
  1. Source-text scan asserts the validation surface in
     `stages/part_render_finalize.py` does NOT have an enclosing
     `try/except` around `_validate_render_output` that returns
     success on failure.
  2. Behavioral test: when `_validate_render_output` returns
     `ok=False`, `run_part_finalize` MUST raise RuntimeError
     (it must NOT swallow the failure).

See docs/review/AUDIT_2026-06-02_followup_9.md for the closure record.
"""
from __future__ import annotations

import inspect
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestQaPipelineSurfaceUnbypassed:
    """Contract #8: structural integrity of the validation surface."""

    def test_validate_render_output_exists_in_qa_pipeline(self):
        """The validation entry point lives at the documented address.
        Renaming or relocating it would silently strand all callers."""
        from app.orchestration.qa_pipeline import _validate_render_output

        sig = inspect.signature(_validate_render_output)
        params = list(sig.parameters.keys())
        # Documented signature: output_path, expected_duration, expect_audio.
        assert params[0] == "output_path"
        assert "expected_duration" in params
        assert "expect_audio" in params

    def test_assess_output_quality_exists_in_qa_pipeline(self):
        """The quality-assessment entry point also lives where docs say."""
        from app.orchestration.qa_pipeline import _assess_output_quality

        sig = inspect.signature(_assess_output_quality)
        params = list(sig.parameters.keys())
        assert params[0] == "output_path"
        assert "expect_subtitle" in params
        assert "subtitle_file" in params
        assert "expect_hook" in params
        assert "hook_applied" in params

    def test_finalize_imports_validate_render_output(self):
        """Static guard: the finalize module imports the validation
        gate. If a refactor removes the import, the call site goes
        silent (NameError swallowed by a wider try/except, like Track
        C C2's `_mv_score_part` was)."""
        from app.orchestration.stages import part_render_finalize as finalize_mod

        # Module must have _validate_render_output bound at module level.
        assert hasattr(finalize_mod, "_validate_render_output"), (
            "Contract #8: stages/part_render_finalize.py must import "
            "_validate_render_output. Without the import, the "
            "validation gate at line 485 raises NameError silently."
        )
        assert hasattr(finalize_mod, "_assess_output_quality"), (
            "Contract #8: stages/part_render_finalize.py must import "
            "_assess_output_quality."
        )

    def test_validate_render_output_call_site_not_wrapped_in_try(self):
        """The `_validate_render_output(...)` call at finalize line
        ~485 MUST NOT be inside a try/except block that would catch
        the subsequent RuntimeError. Lower-bound source-text guard."""
        from app.orchestration.stages import part_render_finalize as finalize_mod

        source = inspect.getsource(finalize_mod.run_part_finalize)

        # Locate the validation call.
        call_match = re.search(r"_qa\s*=\s*_validate_render_output\(", source)
        assert call_match is not None, (
            "Contract #8: _validate_render_output call site missing "
            "from run_part_finalize body."
        )

        # Walk backward from the call to find the nearest enclosing
        # control-flow keyword. It must NOT be `try`.
        prefix = source[: call_match.start()]
        # Find the last indentation-leading keyword. We only care about
        # the *immediately enclosing* try, not any ancestor try.
        # Naive scan: check the 200 chars before the call.
        window = prefix[-400:]
        # Look for `try:` at the same indent level as the call.
        # The call lives at indent 4 (one tab inside the function body).
        # A wrapping `try:` would also be at the same indent level.
        same_indent_try = re.search(r"\n    try:\n", window)
        assert same_indent_try is None, (
            "Contract #8 violation: _validate_render_output appears to "
            "be wrapped in a try block at the same indent level. This "
            "would allow swallowing the RuntimeError on ok=False, "
            "violating the unbypassable-gate contract. Window: "
            f"{window!r}"
        )

    def test_finalize_raises_runtime_error_on_validate_failure(self, tmp_path):
        """Behavioral guard: when `_validate_render_output` returns
        ok=False, run_part_finalize MUST raise RuntimeError. Pre-fix
        (or future regression) where the raise is removed or wrapped
        would let corrupt videos surface as success."""
        from app.orchestration.stages.part_render_finalize import run_part_finalize

        srt_part = tmp_path / "p.srt"
        srt_part.write_text("s", encoding="utf-8")
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("a", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)

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

        seg = {"start": 0.0, "end": 5.0, "duration": 5.0,
               "viral_score": 50, "motion_score": 50, "hook_score": 50,
               "priority_rank": 1, "content_type_hint": "vlog"}
        preflight = MagicMock(
            vf_ct="vlog", vf_crf_delta=0, part_video_crf=20,
            vf_bitrate_profile="standard", vf_subtitle_bump=False,
            t_encode=0.0, motion_crop_fallback=[],
        )
        encode = MagicMock(render_ms=1000)
        timeline = MagicMock(source_duration=5.0, output_duration=5.0)

        with patch(
            "app.orchestration.stages.part_render_finalize._validate_render_output",
            return_value={
                "ok": False,
                "error": "simulated_corruption",
                "code": "RN007",
                "warnings": [],
                "metadata": {"size_bytes": 100, "duration": 0.0,
                             "has_video": False, "has_audio": False},
            },
        ) as mock_validate, patch(
            "app.orchestration.stages.part_render_finalize._assess_output_quality",
            return_value={"passed": True, "warnings": [], "hard_failures": [],
                          "checks": {}, "score_penalty": 0},
        ), patch(
            "app.orchestration.stages.part_render_finalize._mv_score_part",
            return_value={"viral_score": 0, "viral_tier": "weak",
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
        ):
            # Contract #8 behavioral assertion: ok=False must propagate.
            with pytest.raises(RuntimeError, match=r"output_validation_failed"):
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

        # The validation gate was invoked — confirms we reached it
        # (not stopped earlier by some other exception path).
        assert mock_validate.called

    def test_finalize_invokes_validate_on_happy_path(self, tmp_path):
        """Positive case: when validation returns ok=True, the call
        was still invoked. Guards against future "skip validation if
        flag X" branches that would bypass the gate."""
        from app.orchestration.stages.part_render_finalize import run_part_finalize

        srt_part = tmp_path / "p.srt"
        srt_part.write_text("s", encoding="utf-8")
        ass_part = tmp_path / "p.ass"
        ass_part.write_text("a", encoding="utf-8")
        final_part = tmp_path / "p.mp4"
        final_part.write_bytes(b"v" * 100)

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

        seg = {"start": 0.0, "end": 5.0, "duration": 5.0,
               "viral_score": 50, "motion_score": 50, "hook_score": 50,
               "priority_rank": 1, "content_type_hint": "vlog"}
        preflight = MagicMock(
            vf_ct="vlog", vf_crf_delta=0, part_video_crf=20,
            vf_bitrate_profile="standard", vf_subtitle_bump=False,
            t_encode=0.0, motion_crop_fallback=[],
        )
        encode = MagicMock(render_ms=1000)
        timeline = MagicMock(source_duration=5.0, output_duration=5.0)

        with patch(
            "app.orchestration.stages.part_render_finalize._validate_render_output",
            return_value={
                "ok": True, "error": None, "warnings": [],
                "metadata": {"duration": 5.0, "size_bytes": 100,
                             "has_video": True, "has_audio": True},
            },
        ) as mock_validate, patch(
            "app.orchestration.stages.part_render_finalize._assess_output_quality",
            return_value={"passed": True, "warnings": [], "hard_failures": [],
                          "checks": {}, "score_penalty": 0},
        ) as mock_assess, patch(
            "app.orchestration.stages.part_render_finalize._mv_score_part",
            return_value={"viral_score": 0, "viral_tier": "weak",
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

        # Contract #8: validation runs on every success path.
        assert mock_validate.called, (
            "Contract #8: _validate_render_output was not invoked on "
            "the happy path of run_part_finalize. The validation gate "
            "must run unconditionally."
        )
        # And quality assessment runs (separately — non-blocking).
        assert mock_assess.called, (
            "Contract #8: _assess_output_quality was not invoked. "
            "Quality assessment runs after validation passes."
        )
