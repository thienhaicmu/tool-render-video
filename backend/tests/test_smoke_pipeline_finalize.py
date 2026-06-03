"""P2 smoke — pipeline_finalize.run_render_finalize + FinalizeContext.

Per Track D D2 audit (followup_7), orchestration/pipeline_finalize.py
has zero direct test consumers. FinalizeContext is the largest
inter-stage handoff dataclass — 18+ fields collected by the
orchestrator at the finalize point. A field rename here silently
strands the entire result_json + outputs ranking surface.

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import dataclasses
import inspect


FINALIZE_CONTEXT_FIELDS = {
    "job_id", "effective_channel", "payload",
    "started_at", "output_dir", "output_stem",
    "outputs", "failed_parts", "total_parts",
    "scored", "recovery_notes",
    "rank_entries", "rank_entries_ordered",
    "best_rank_entry", "partial_warning",
    "preset_name", "preset_id", "preset_label",
    "mv_parts",
    "voice_summary", "subtitle_translate_summary",
    "ai_influence_report", "ai_beat_report",
}


class TestPipelineFinalizeSurface:
    """run_render_finalize signature + FinalizeContext conformance."""

    def test_run_render_finalize_signature(self):
        from app.orchestration.pipeline_finalize import run_render_finalize
        sig = inspect.signature(run_render_finalize)
        params = list(sig.parameters.keys())
        assert params == ["ctx"], (
            f"run_render_finalize must take single `ctx` arg, got {params!r}."
        )

    def test_run_render_finalize_returns_str(self):
        """Returns the final status string ('completed' or
        'completed_with_errors'). The caller's finally block uses
        this to decide whether to clean up the preview session.
        With `from __future__ import annotations`, the return annotation
        is the string 'str'."""
        from app.orchestration.pipeline_finalize import run_render_finalize
        sig = inspect.signature(run_render_finalize)
        assert sig.return_annotation == "str"

    def test_finalize_context_is_dataclass(self):
        from app.orchestration.pipeline_finalize import FinalizeContext
        assert dataclasses.is_dataclass(FinalizeContext)

    def test_finalize_context_fields(self):
        from app.orchestration.pipeline_finalize import FinalizeContext
        actual = {f.name for f in dataclasses.fields(FinalizeContext)}
        missing = FINALIZE_CONTEXT_FIELDS - actual
        assert not missing, (
            f"FinalizeContext missing fields: {missing}. "
            f"The orchestrator binds each field explicitly when "
            f"constructing the context — a rename leaves the field "
            f"unbound."
        )

    def test_ctx_param_typed_as_finalize_context(self):
        """The single param's annotation must reference FinalizeContext.
        Catches accidental annotation drift during refactors."""
        from app.orchestration.pipeline_finalize import run_render_finalize
        sig = inspect.signature(run_render_finalize)
        assert sig.parameters["ctx"].annotation == "FinalizeContext"
