"""P2 smoke — pipeline_setup.setup_render_pipeline + PipelineSetupResult.

Per Track D D2 audit (followup_7), orchestration/pipeline_setup.py has
zero direct test consumers. setup_render_pipeline is the FIRST call
in run_render_pipeline; its output dataclass field names are aliased
back to local variables that flow through the entire orchestrator.
A field rename silently strands the rest of the pipeline.

See docs/review/AUDIT_2026-06-02_followup_10.md for closure record.
"""
from __future__ import annotations

import dataclasses
import inspect
from unittest.mock import MagicMock


SETUP_RESULT_FIELDS = {
    "output_mode", "effective_channel", "started_at",
    "mv_cfg", "mv_market",
    "hook_apply_enabled", "hook_applied_text", "hook_score",
    "hook_overlay_enabled",
    "output_dir",
}


class TestPipelineSetupSurface:
    """setup_render_pipeline + dataclass conformance."""

    def test_setup_render_pipeline_signature(self):
        from app.orchestration.pipeline_setup import setup_render_pipeline
        sig = inspect.signature(setup_render_pipeline)
        params = list(sig.parameters.keys())
        assert params == ["payload"], (
            f"setup_render_pipeline must take a single `payload` arg, "
            f"got {params!r}."
        )

    def test_pipeline_setup_result_fields(self):
        from app.orchestration.pipeline_setup import PipelineSetupResult
        assert dataclasses.is_dataclass(PipelineSetupResult)
        actual = {f.name for f in dataclasses.fields(PipelineSetupResult)}
        missing = SETUP_RESULT_FIELDS - actual
        assert not missing, (
            f"PipelineSetupResult missing fields: {missing}."
        )

    def test_prepare_output_dir_signature(self):
        from app.orchestration.pipeline_setup import prepare_output_dir
        sig = inspect.signature(prepare_output_dir)
        params = list(sig.parameters.keys())
        assert params == ["job_id", "effective_channel", "output_dir"], (
            f"prepare_output_dir signature drift: {params!r}."
        )

    def test_setup_normalizes_market_to_us_when_unknown(self, monkeypatch):
        """Behavioral smoke: unknown market codes default to US.
        Guards against the normalization branch being removed."""
        from app.orchestration import pipeline_setup
        from app.orchestration.pipeline_setup import setup_render_pipeline

        # Avoid touching real channels directory.
        monkeypatch.setattr(pipeline_setup, "ensure_channel", lambda c: None)
        monkeypatch.setattr(
            pipeline_setup, "_resolve_output_dir",
            lambda c, o, s: __import__("pathlib").Path("/tmp/out"),
        )

        payload = MagicMock()
        payload.output_mode = "channel"
        payload.channel_code = "manual"
        payload.market_viral = None
        payload.ai_target_market = "XX"  # unknown — must normalize to US
        payload.viral_market = None
        payload.hook_apply_enabled = False
        payload.hook_applied_text = ""
        payload.hook_score = 0
        payload.hook_overlay_enabled = False
        payload.render_output_subdir = "test"
        payload.output_dir = "/tmp/out"

        result = setup_render_pipeline(payload)
        assert result.mv_market == "US", (
            f"Unknown market 'XX' should normalize to US, got {result.mv_market!r}."
        )
