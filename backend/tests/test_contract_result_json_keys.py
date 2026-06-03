"""P1 Contract #1 — result_json backward-compat aliases conformance.

Per CLAUDE.md Sacred Contract #1, every dict returned by
`_compute_output_ranking_entry` (and thus every entry in
`result_json["render_outputs"]` / `result_json["market_viral_parts"]`)
MUST contain these three keys, forever:

    output_rank_score
    is_best_output
    is_best_clip

These names are hardcoded as string literals in multiple consumers
(history UI, output viewer, AI Director training pipeline,
ai_visibility_summary.py, routes/jobs.py). Removing any of them does
not throw an exception — the consuming code silently reads None /
undefined, and data disappears from the UI without a visible failure.

This conformance test fixes a gap identified in the Track D D2 audit
(docs/review/AUDIT_2026-06-02_followup_7.md Finding 4 row #1).
Previously _compute_output_ranking_entry was tested in isolation via
its component-helper tests, but no test asserted the three frozen
backward-compat aliases survive on every code path.

See docs/review/AUDIT_2026-06-02_followup_9.md for the closure record.
"""
from __future__ import annotations

import pytest


SACRED_KEYS = ("output_rank_score", "is_best_output", "is_best_clip")


class TestResultJsonContractKeys:
    """Sacred Contract #1: result_json backward-compat aliases.

    Each test calls _compute_output_ranking_entry with a different
    realistic seg shape and asserts all 3 frozen keys are present
    AND have type-correct values.
    """

    def test_keys_present_on_minimal_seg(self):
        """A bare-minimum seg with only `start`/`end`/`duration` still
        produces an entry with all 3 sacred keys."""
        from app.orchestration.pipeline_ranking import _compute_output_ranking_entry

        seg = {"start": 0.0, "end": 5.0, "duration": 5.0}
        entry = _compute_output_ranking_entry(
            part_no=1, seg=seg, output_file="/tmp/part_001.mp4",
        )

        for key in SACRED_KEYS:
            assert key in entry, (
                f"Contract #1 violation: '{key}' missing from "
                f"_compute_output_ranking_entry output for minimal seg. "
                f"This breaks history UI / output viewer / AI Director."
            )

    def test_keys_present_on_full_seg(self):
        """A fully-populated seg (every score present) still produces
        an entry with all 3 sacred keys."""
        from app.orchestration.pipeline_ranking import _compute_output_ranking_entry

        seg = {
            "start": 0.0, "end": 30.0, "duration": 30.0,
            "viral_score": 80, "motion_score": 60,
            "hook_score": 70, "hook_text_score": 75,
            "retention_score": 65, "speech_density_score": 55,
            "mv_viral_score": 78, "duration_fit_score": 90,
            "continuity_score": 85,
            "content_type_hint": "vlog",
            "selection_reason": "test",
        }
        entry = _compute_output_ranking_entry(
            part_no=2, seg=seg, output_file="/tmp/part_002.mp4",
        )

        for key in SACRED_KEYS:
            assert key in entry

    def test_keys_present_when_all_scores_missing(self):
        """Even with an empty-ish seg (no scores), the entry includes
        all 3 sacred keys. Score-defaulting to 50.0 must not strip them."""
        from app.orchestration.pipeline_ranking import _compute_output_ranking_entry

        seg = {}
        entry = _compute_output_ranking_entry(
            part_no=99, seg=seg, output_file="/tmp/x.mp4",
        )

        for key in SACRED_KEYS:
            assert key in entry

    def test_output_rank_score_is_numeric(self):
        """output_rank_score must be a number (int or float).
        The history UI rounds it for display — None would crash."""
        from app.orchestration.pipeline_ranking import _compute_output_ranking_entry

        entry = _compute_output_ranking_entry(
            part_no=1,
            seg={"viral_score": 80, "duration": 10.0},
            output_file="/tmp/x.mp4",
        )

        rank = entry["output_rank_score"]
        assert isinstance(rank, (int, float)), (
            f"Contract #1 violation: output_rank_score must be numeric, "
            f"got {type(rank).__name__} ({rank!r})."
        )
        assert 0.0 <= rank <= 100.0, (
            f"Contract #1 violation: output_rank_score out of [0,100] range: {rank}"
        )

    def test_is_best_flags_are_boolean(self):
        """is_best_output and is_best_clip must be booleans.
        The default state is False (set later by the ranking sort)."""
        from app.orchestration.pipeline_ranking import _compute_output_ranking_entry

        entry = _compute_output_ranking_entry(
            part_no=1, seg={"viral_score": 50}, output_file="/tmp/x.mp4",
        )

        assert isinstance(entry["is_best_output"], bool), (
            f"Contract #1: is_best_output must be bool, "
            f"got {type(entry['is_best_output']).__name__}"
        )
        assert isinstance(entry["is_best_clip"], bool), (
            f"Contract #1: is_best_clip must be bool, "
            f"got {type(entry['is_best_clip']).__name__}"
        )
        # Default state: both False before ranking sort flips the winner.
        assert entry["is_best_output"] is False
        assert entry["is_best_clip"] is False

    def test_output_rank_score_matches_output_score(self):
        """The backward-compat alias output_rank_score must equal the
        new-name output_score on every entry. They are required to
        track each other exactly — divergence would corrupt the UI."""
        from app.orchestration.pipeline_ranking import _compute_output_ranking_entry

        for vs in [0, 30, 50, 75, 100]:
            entry = _compute_output_ranking_entry(
                part_no=1, seg={"viral_score": vs, "duration": 10.0},
                output_file="/tmp/x.mp4",
            )
            assert entry["output_rank_score"] == entry["output_score"], (
                f"Contract #1: output_rank_score ({entry['output_rank_score']}) "
                f"must match output_score ({entry['output_score']}) for "
                f"viral_score={vs}. The alias must not diverge."
            )

    def test_keys_present_with_payload_hook_score_override(self):
        """When payload_hook_score is supplied (the per-job hook score
        override), the 3 sacred keys are still present."""
        from app.orchestration.pipeline_ranking import _compute_output_ranking_entry

        entry = _compute_output_ranking_entry(
            part_no=1, seg={"viral_score": 60},
            output_file="/tmp/x.mp4",
            payload_hook_score=85,
        )

        for key in SACRED_KEYS:
            assert key in entry
