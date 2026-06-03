"""P2 smoke — pipeline_source_prep.prepare_render_source + SourcePrepResult.

Per Track D D2 audit (followup_7), orchestration/pipeline_source_prep.py
has zero direct test consumers. prepare_render_source produces the
source_path that the entire render pipeline depends on — a field
rename in SourcePrepResult silently strands the rest of the orchestrator.

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import dataclasses
import inspect


SOURCE_PREP_PARAMS = {
    "job_id", "effective_channel", "payload",
    "work_dir", "output_dir", "hook_applied_text",
    "set_stage", "load_session_fn",
}

SOURCE_PREP_RESULT_FIELDS = {
    "source", "source_path", "edit_session_id",
    "detected_source_mode", "output_stem",
}


class TestPipelineSourcePrepSurface:
    """prepare_render_source signature + SourcePrepResult conformance."""

    def test_prepare_render_source_signature(self):
        from app.orchestration.pipeline_source_prep import prepare_render_source
        sig = inspect.signature(prepare_render_source)
        params = set(sig.parameters.keys())
        missing = SOURCE_PREP_PARAMS - params
        assert not missing, (
            f"prepare_render_source missing expected params: {missing}."
        )

    def test_prepare_render_source_is_keyword_only(self):
        """The function uses `*` to enforce keyword-only args. This
        keeps additive changes safe."""
        from app.orchestration.pipeline_source_prep import prepare_render_source
        sig = inspect.signature(prepare_render_source)
        for name, param in sig.parameters.items():
            assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
                f"prepare_render_source.{name} must be keyword-only, "
                f"got kind={param.kind}."
            )

    def test_source_prep_result_fields(self):
        from app.orchestration.pipeline_source_prep import SourcePrepResult
        assert dataclasses.is_dataclass(SourcePrepResult)
        actual = {f.name for f in dataclasses.fields(SourcePrepResult)}
        missing = SOURCE_PREP_RESULT_FIELDS - actual
        assert not missing, (
            f"SourcePrepResult missing fields: {missing}."
        )
