"""P2 smoke — part_render_setup.run_render_preflight + RenderPreflightResult.

Per Track D D2 audit (followup_7), stages/part_render_setup.py has
zero direct test consumers. The preflight stage starts a thread
(encode_timer) whose lifecycle is managed by the caller — a signature
or field rename breaks the join() in the caller's finally block.

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import dataclasses
import inspect
import threading


PREFLIGHT_PARAMS = {
    "ctx", "idx", "seg", "part_name", "final_part_path",
    "_effective_start", "_trim_offset", "_visual_trim",
    "_force_accurate_cut", "part_subtitle_enabled",
}

PREFLIGHT_RESULT_FIELDS = {
    # Encoding params
    "vf_ct", "vf_crf_delta", "part_video_crf",
    "vf_bitrate_profile", "vf_subtitle_bump",
    # Threading
    "encode_stop", "encode_timer",
    # Timers
    "t_encode", "t_render",
    # Motion-crop state
    "motion_ck", "motion_crop_fallback",
    # Plan + camera
    "part_plan", "camera_strategy",
}


class TestPartRenderSetupSurface:
    """Signature + dataclass conformance for the preflight stage."""

    def test_run_render_preflight_signature(self):
        from app.orchestration.stages.part_render_setup import run_render_preflight
        sig = inspect.signature(run_render_preflight)
        params = set(sig.parameters.keys())
        missing = PREFLIGHT_PARAMS - params
        assert not missing, (
            f"run_render_preflight missing expected params: {missing}."
        )

    def test_render_preflight_result_fields(self):
        from app.orchestration.stages.part_render_setup import RenderPreflightResult
        assert dataclasses.is_dataclass(RenderPreflightResult)
        actual = {f.name for f in dataclasses.fields(RenderPreflightResult)}
        missing = PREFLIGHT_RESULT_FIELDS - actual
        assert not missing, (
            f"RenderPreflightResult missing fields: {missing}. "
            f"Caller in process_one_part aliases each back to its "
            f"original local name."
        )

    def test_threading_lifecycle_field_types_documented(self):
        """encode_stop / encode_timer must be typed as Event / Thread —
        the caller's finally block calls .set() and .join() on them.
        With `from __future__ import annotations`, the .type attr is the
        annotation string."""
        from app.orchestration.stages.part_render_setup import RenderPreflightResult
        fields_by_name = {f.name: f for f in dataclasses.fields(RenderPreflightResult)}
        assert fields_by_name["encode_stop"].type == "threading.Event"
        assert fields_by_name["encode_timer"].type == "threading.Thread"

    def test_motion_crop_fallback_is_list_typed(self):
        """motion_crop_fallback is a mutable list passed by reference and
        appended to downstream. Must NOT be a tuple — composite_overlays_*
        uses .append()."""
        from app.orchestration.stages.part_render_setup import RenderPreflightResult
        fields_by_name = {f.name: f for f in dataclasses.fields(RenderPreflightResult)}
        assert fields_by_name["motion_crop_fallback"].type == "list"
