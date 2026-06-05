"""Sprint 6 P0 HIGH gate (post Sprint 7.2 simplification) — tests for the
base_clip gate in part_render_encode.py.

Sprint 6 P0 HIGH introduced a consumer-aware gate that replaced the
unconditional `if _FEATURE_BASE_CLIP_FIRST:` with a check on whether a
downstream consumer would actually read base_clip.mp4. Sprint 7.2
removed the `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` opt-in escape hatch
(zero usage observed during the 30-day settling period from 2026-06-05).

Post-Sprint-7.2 gate:

    if _FEATURE_BASE_CLIP_FIRST and _FEATURE_OVERLAY_AFTER_BASE_CLIP:

Cases pinned here mirror the simulate-the-pipeline-block style used in
``tests/test_render_base_clip.py:248-316`` — they exercise the boolean
gate, not the full ``run_render_encode`` call graph.

Cases:
  1. Both flags off — gate False, render_base_clip NOT called (default).
  2. FIRST=1, OVERLAY=0 — gate False, render_base_clip NOT called
     (Sprint 6 P0 HIGH win).
  3. FIRST=1, OVERLAY=1 — gate True, render_base_clip IS called
     (the overlay-composite consumer is active).
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock


def _gate(first: bool, overlay: bool) -> bool:
    """Mirror of the production gate in part_render_encode.py post Sprint 7.2."""
    return first and overlay


# ---------------------------------------------------------------------------
# Section 1: gate truth-table — direct boolean exercise
# ---------------------------------------------------------------------------


class TestGateTruthTable:
    def test_all_flags_off_gate_false(self):
        assert _gate(first=False, overlay=False) is False

    def test_first_off_overrides_overlay(self):
        # FIRST is the master switch — if it's off, overlay alone cannot
        # turn the gate on.
        assert _gate(first=False, overlay=True) is False

    def test_first_on_no_overlay_gate_false(self):
        # The Sprint 6 P0 HIGH win: FIRST=1 alone no longer activates the
        # base_clip render. Before that sprint, the gate would have been
        # True here and produced a 50-150 MB throwaway artifact.
        assert _gate(first=True, overlay=False) is False

    def test_first_plus_overlay_gate_true(self):
        # composite_overlays_on_base_clip is the only consumer — gate True.
        assert _gate(first=True, overlay=True) is True


# ---------------------------------------------------------------------------
# Section 2: simulate the pipeline block (matches test_render_base_clip.py
# TestFeatureBaseClipFlag pattern)
# ---------------------------------------------------------------------------


class TestPipelineBlockGate:
    def test_block_skips_base_clip_when_first_off(self):
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        first, overlay = False, False
        if _gate(first, overlay):
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4")
        mock_render_base.assert_not_called()

    def test_block_skips_base_clip_when_first_on_but_no_overlay(self):
        """Sprint 6 P0 HIGH default for FEATURE_BASE_CLIP_FIRST=1 users."""
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        first, overlay = True, False
        if _gate(first, overlay):
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4")
        mock_render_base.assert_not_called()

    def test_block_calls_base_clip_when_overlay_active(self):
        mock_render_base = MagicMock(return_value={"path": "/fake/base.mp4"})
        first, overlay = True, True
        if _gate(first, overlay):
            mock_render_base("/fake/cut.mp4", "/fake/base.mp4")
        mock_render_base.assert_called_once()


# ---------------------------------------------------------------------------
# Section 3: post-Sprint-7.2 cleanup pins — the VALIDATION_ARTIFACT flag
# is GONE everywhere
# ---------------------------------------------------------------------------


class TestValidationArtifactFlagRemoved:
    """Sprint 7.2 (2026-06-05) deleted _FEATURE_BASE_CLIP_VALIDATION_ARTIFACT
    from all 5 module-level read sites (render_pipeline.py + 4 stages).
    These pins surface any future reintroduction in CI rather than as a
    silent regression in flag-read coverage."""

    def test_render_pipeline_does_not_read_validation_artifact_flag(self):
        from app.orchestration import render_pipeline
        assert not hasattr(render_pipeline, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_renderer_does_not_read_validation_artifact_flag(self):
        from app.orchestration.stages import part_renderer
        assert not hasattr(part_renderer, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_render_setup_does_not_read_validation_artifact_flag(self):
        from app.orchestration.stages import part_render_setup
        assert not hasattr(part_render_setup, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_render_encode_does_not_read_validation_artifact_flag(self):
        from app.orchestration.stages import part_render_encode
        assert not hasattr(part_render_encode, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_cut_does_not_read_validation_artifact_flag(self):
        from app.orchestration.stages import part_cut
        assert not hasattr(part_cut, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_part_render_encode_gate_uses_simple_and(self):
        """Post Sprint 7.2 the gate at part_render_encode.py reads
        `if _FEATURE_BASE_CLIP_FIRST and _FEATURE_OVERLAY_AFTER_BASE_CLIP:`.
        Pin the source so a future reintroduction of the VALIDATION flag
        surfaces here rather than as a silent regression."""
        from app.orchestration.stages import part_render_encode
        src = inspect.getsource(part_render_encode)
        assert "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT" not in src, (
            "Sprint 7.2 removed FEATURE_BASE_CLIP_VALIDATION_ARTIFACT from "
            "part_render_encode.py — a future commit has reintroduced it. "
            "Either the reintroduction is intentional (re-scope the flag in "
            "a new audit doc) or this is a regression."
        )
