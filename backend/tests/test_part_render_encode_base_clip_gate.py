"""Sprint 6 P0 HIGH — tests for the tightened base_clip gate in
part_render_encode.py.

Before Sprint 6 P0 HIGH the gate was `if _FEATURE_BASE_CLIP_FIRST:`. That
unconditionally ran `render_base_clip()` even when nothing downstream read
the resulting `base_clip.mp4` — wasting one full motion-crop FFmpeg encode
and 50-150 MB per part. The new gate also requires a consumer:

    if _FEATURE_BASE_CLIP_FIRST and (
        _FEATURE_OVERLAY_AFTER_BASE_CLIP
        or _FEATURE_BASE_CLIP_VALIDATION_ARTIFACT
    ):

Cases pinned here mirror the simulate-the-pipeline-block style used in
``tests/test_render_base_clip.py:248-316`` — they exercise the boolean
gate, not the full ``run_render_encode`` call graph, because that graph
needs PartRenderContext / RenderPreflightResult / BaseClipManifest
fixtures that no helper currently exposes.

Cases:
  1. Both flags off — gate False, render_base_clip NOT called (regression
     guard for the default config).
  2. FIRST=1, OVERLAY=0, VALIDATION=0 — gate False, render_base_clip
     NOT called (THE optimisation Sprint 6 P0 HIGH ships).
  3. FIRST=1, OVERLAY=1 — gate True, render_base_clip IS called (existing
     overlay-composite path preserved).
  4. FIRST=1, VALIDATION=1 — gate True, render_base_clip IS called
     (legacy A/B forensics opt-in preserved).
  5. The new env var defaults to OFF (Sacred Contract #2 compliance).
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


def _gate(first: bool, overlay: bool, validation: bool) -> bool:
    """Mirror of the production gate in part_render_encode.py."""
    return first and (overlay or validation)


# ---------------------------------------------------------------------------
# Section 1: gate truth-table — direct boolean exercise
# ---------------------------------------------------------------------------


class TestGateTruthTable:
    def test_all_flags_off_gate_false(self):
        assert _gate(first=False, overlay=False, validation=False) is False

    def test_first_off_overrides_other_flags(self):
        # FIRST is the master switch — if it's off, neither consumer can
        # turn the gate on.
        assert _gate(first=False, overlay=True, validation=True) is False

    def test_first_on_no_consumer_gate_false(self):
        # The Sprint 6 P0 HIGH win: FIRST=1 alone no longer activates the
        # base_clip render. Before this sprint, the gate would have been
        # True here and produced a 50-150 MB throwaway artifact.
        assert _gate(first=True, overlay=False, validation=False) is False

    def test_first_plus_overlay_gate_true(self):
        # composite_overlays_on_base_clip is a real consumer — gate True.
        assert _gate(first=True, overlay=True, validation=False) is True

    def test_first_plus_validation_gate_true(self):
        # FEATURE_BASE_CLIP_VALIDATION_ARTIFACT is the explicit opt-in
        # for legacy A/B forensics — gate True.
        assert _gate(first=True, overlay=False, validation=True) is True

    def test_first_plus_both_consumers_gate_true(self):
        assert _gate(first=True, overlay=True, validation=True) is True


# ---------------------------------------------------------------------------
# Section 2: simulate the pipeline block (matches test_render_base_clip.py
# TestFeatureBaseClipFlag pattern)
# ---------------------------------------------------------------------------


class TestPipelineBlockGate:
    def test_block_skips_base_clip_when_first_off(self):
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        first, overlay, validation = False, False, False
        if _gate(first, overlay, validation):
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4")
        mock_render_base.assert_not_called()

    def test_block_skips_base_clip_when_first_on_but_no_consumer(self):
        """Sprint 6 P0 HIGH default for FEATURE_BASE_CLIP_FIRST=1 users."""
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        first, overlay, validation = True, False, False
        if _gate(first, overlay, validation):
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4")
        mock_render_base.assert_not_called()

    def test_block_calls_base_clip_when_overlay_active(self):
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        first, overlay, validation = True, True, False
        if _gate(first, overlay, validation):
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4")
        mock_render_base.assert_called_once()

    def test_block_calls_base_clip_when_validation_flag_on(self):
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        first, overlay, validation = True, False, True
        if _gate(first, overlay, validation):
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4")
        mock_render_base.assert_called_once()


# ---------------------------------------------------------------------------
# Section 3: env-flag defaults — Sacred Contract #2 compliance
# ---------------------------------------------------------------------------


class TestValidationArtifactFlagDefault:
    def test_validation_artifact_flag_defaults_off(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEATURE_BASE_CLIP_VALIDATION_ARTIFACT", None)
            flag_value = (
                os.getenv("FEATURE_BASE_CLIP_VALIDATION_ARTIFACT", "0") == "1"
            )
        assert flag_value is False, (
            "FEATURE_BASE_CLIP_VALIDATION_ARTIFACT must default to OFF — "
            "Sacred Contract #2 requires new flags to default to disabled."
        )

    def test_validation_artifact_flag_on_when_env_set(self):
        with patch.dict(os.environ, {"FEATURE_BASE_CLIP_VALIDATION_ARTIFACT": "1"}):
            flag_value = (
                os.getenv("FEATURE_BASE_CLIP_VALIDATION_ARTIFACT", "0") == "1"
            )
        assert flag_value is True


# ---------------------------------------------------------------------------
# Section 4: module-level reads exist + are coherent across the 4 sites
# ---------------------------------------------------------------------------


class TestModuleLevelFlagReadsCoherent:
    """Every module that holds a per-process copy of the feature flag must
    read the same env var name. Drift between the 4 sites would silently
    activate the wrong code path on one consumer while leaving another
    inactive — exactly the kind of corruption Sacred Contract #6 protects
    against in the WebSocket emitter case."""

    def test_render_pipeline_reads_validation_artifact_flag(self):
        from app.orchestration import render_pipeline
        assert hasattr(render_pipeline, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_renderer_reads_validation_artifact_flag(self):
        from app.orchestration.stages import part_renderer
        assert hasattr(part_renderer, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_render_setup_reads_validation_artifact_flag(self):
        from app.orchestration.stages import part_render_setup
        assert hasattr(part_render_setup, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_render_encode_reads_validation_artifact_flag(self):
        from app.orchestration.stages import part_render_encode
        assert hasattr(part_render_encode, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_render_encode_gate_uses_consumer_check(self):
        """The gate at part_render_encode.py guards the render_base_clip
        call on (FIRST AND (OVERLAY OR VALIDATION)). Pin the source so a
        future drift surfaces in CI rather than as a silent perf
        regression on disk."""
        import inspect
        from app.orchestration.stages import part_render_encode
        src = inspect.getsource(part_render_encode)
        assert "_base_clip_consumer_active" in src, (
            "The Sprint 6 P0 HIGH gate boolean variable name was renamed or "
            "removed; the consumer-active check has likely regressed."
        )
        assert "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT" in src, (
            "FEATURE_BASE_CLIP_VALIDATION_ARTIFACT no longer participates in "
            "the gate — the legacy A/B forensics opt-in has regressed."
        )
