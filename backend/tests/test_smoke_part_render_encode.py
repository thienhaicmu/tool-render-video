"""P2 smoke — part_render_encode.run_render_encode + RenderEncodeResult.

Per Track D D2 audit (followup_7), stages/part_render_encode.py has
zero direct test consumers. run_render_encode is where the FFmpeg
subprocess fires; a signature drift would silently strand all callers.

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import dataclasses
import inspect


ENCODE_PARAMS = {
    "ctx", "idx", "seg", "raw_part", "ass_part", "final_part",
    "part_subtitle_enabled", "overlay_title",
    "part_manifest", "part_timeline",
    "part_text_layers", "part_text_layers_overlay",
    "effective_subtitle_style", "preflight",
}


class TestPartRenderEncodeSurface:
    """Signature + dataclass conformance for the encode stage."""

    def test_run_render_encode_signature(self):
        from app.orchestration.stages.part_render_encode import run_render_encode
        sig = inspect.signature(run_render_encode)
        params = set(sig.parameters.keys())
        missing = ENCODE_PARAMS - params
        assert not missing, (
            f"run_render_encode missing expected params: {missing}."
        )

    def test_render_encode_result_dataclass(self):
        from app.orchestration.stages.part_render_encode import RenderEncodeResult
        assert dataclasses.is_dataclass(RenderEncodeResult)
        fields = {f.name for f in dataclasses.fields(RenderEncodeResult)}
        # Currently single-field but dataclass form was chosen for
        # consistency + future extensibility.
        assert "render_ms" in fields, (
            "RenderEncodeResult missing render_ms field — "
            "the caller reads encode.render_ms in the total_part log."
        )

    def test_render_encode_returns_render_encode_result(self):
        from app.orchestration.stages.part_render_encode import run_render_encode
        sig = inspect.signature(run_render_encode)
        # `from __future__ import annotations` makes annotations strings.
        assert sig.return_annotation == "RenderEncodeResult"

    def test_preflight_param_typed_as_preflight_result(self):
        """The `preflight` kwarg consumes the dataclass returned by
        run_render_preflight. Annotation drift here would silently
        break the inter-stage handoff."""
        from app.orchestration.stages.part_render_encode import run_render_encode
        sig = inspect.signature(run_render_encode)
        assert sig.parameters["preflight"].annotation == "RenderPreflightResult"
