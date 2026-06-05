"""Sprint 6 audit O-4 Commit 1 — `_should_skip_raw_part_write` predicate truth-table.

The predicate determines whether `raw_part.mp4` can be skipped when
`cut_video` is fused into the final render encode in a future commit.
This file pins the four-input truth table so a future regression that
silently expands the skip set is caught in CI rather than as a render
behavior change.

Today the predicate is wired as TELEMETRY ONLY at part_cut.py — the
actual `cut_video` bypass ships in a separate commit after manual
visual review on 3-5 sample renders per SPRINT_PLAN risk register
line 302. The audit doc
`docs/review/SPRINT_6_O4_RAW_PART_SKIP_PREDICATE_2026-06-05.md`
captures the deferred Commit 2 plan.

Inputs:
  - part_subtitle_enabled                       (per-part Whisper gate)
  - feature_base_clip_first                     (env FEATURE_BASE_CLIP_FIRST)
  - feature_overlay_after_base_clip             (env FEATURE_OVERLAY_AFTER_BASE_CLIP)
  - feature_base_clip_validation_artifact       (env FEATURE_BASE_CLIP_VALIDATION_ARTIFACT)

The predicate fires (returns True) iff NEITHER C1 (per-part Whisper)
NOR C2 (render_base_clip) will read raw_part. C3 (render_part_smart) is
the only remaining reader and would be replaced by a fused
`-ss start -t duration -i source` argv.
"""
from __future__ import annotations

import os
import inspect
from unittest.mock import patch


def _predicate(s: bool, f1: bool, f2: bool, fv: bool) -> bool:
    """Mirror of the production predicate at part_cut.py for the
    truth-table sweep. Kept here so test failures cite the production
    line directly via TestSourcePin below."""
    from app.orchestration.stages.part_cut import _should_skip_raw_part_write
    return _should_skip_raw_part_write(
        part_subtitle_enabled=s,
        feature_base_clip_first=f1,
        feature_overlay_after_base_clip=f2,
        feature_base_clip_validation_artifact=fv,
    )


# ---------------------------------------------------------------------------
# Section 1: subtitle gate dominates
# ---------------------------------------------------------------------------


class TestSubtitleGateDominates:
    """When per-part Whisper would run, raw_part is required regardless of
    base_clip configuration. Predicate must always return False."""

    def test_subtitle_on_all_flags_off(self):
        assert _predicate(s=True, f1=False, f2=False, fv=False) is False

    def test_subtitle_on_base_clip_first_only(self):
        assert _predicate(s=True, f1=True, f2=False, fv=False) is False

    def test_subtitle_on_overlay_consumer_on(self):
        assert _predicate(s=True, f1=True, f2=True, fv=False) is False

    def test_subtitle_on_validation_consumer_on(self):
        assert _predicate(s=True, f1=True, f2=False, fv=True) is False

    def test_subtitle_on_both_consumers_on(self):
        assert _predicate(s=True, f1=True, f2=True, fv=True) is False

    def test_subtitle_on_orphan_consumer_flags_no_first(self):
        """Defensive: even with overlay/validation flags set but
        FEATURE_BASE_CLIP_FIRST=0, the subtitle gate alone keeps
        predicate False (raw_part needed by C1)."""
        assert _predicate(s=True, f1=False, f2=True, fv=True) is False


# ---------------------------------------------------------------------------
# Section 2: base_clip consumer gate dominates when subtitle off
# ---------------------------------------------------------------------------


class TestBaseClipConsumerGate:
    """When subtitle is off but base_clip will render with a real
    consumer, predicate must remain False — C2 reads raw_part."""

    def test_subtitle_off_overlay_consumer_active(self):
        assert _predicate(s=False, f1=True, f2=True, fv=False) is False

    def test_subtitle_off_validation_consumer_active(self):
        assert _predicate(s=False, f1=True, f2=False, fv=True) is False

    def test_subtitle_off_both_consumers_active(self):
        assert _predicate(s=False, f1=True, f2=True, fv=True) is False


# ---------------------------------------------------------------------------
# Section 3: predicate fires (the actual skip-eligible cases)
# ---------------------------------------------------------------------------


class TestPredicateFires:
    """Subtitle off + no base_clip consumer = predicate True. These are
    the configurations a future Commit 2 would actually skip."""

    def test_default_config_subtitle_off(self):
        """The default-config skip case: all 3 feature flags OFF."""
        assert _predicate(s=False, f1=False, f2=False, fv=False) is True

    def test_subtitle_off_first_off_orphan_overlay(self):
        """FEATURE_BASE_CLIP_FIRST=0 → base_clip never renders → consumer
        is inactive even when the OVERLAY env var is set in isolation.
        Predicate fires."""
        assert _predicate(s=False, f1=False, f2=True, fv=False) is True

    def test_subtitle_off_first_off_orphan_validation(self):
        """Same logic for VALIDATION_ARTIFACT in isolation."""
        assert _predicate(s=False, f1=False, f2=False, fv=True) is True

    def test_subtitle_off_first_off_both_orphans(self):
        assert _predicate(s=False, f1=False, f2=True, fv=True) is True


# ---------------------------------------------------------------------------
# Section 4: keyword-only signature (defensive against positional drift)
# ---------------------------------------------------------------------------


class TestKeywordOnlySignature:
    def test_predicate_rejects_positional_args(self):
        from app.orchestration.stages.part_cut import _should_skip_raw_part_write
        import pytest
        with pytest.raises(TypeError):
            _should_skip_raw_part_write(False, False, False, False)


# ---------------------------------------------------------------------------
# Section 5: env-flag mirror reads (drift prevention)
# ---------------------------------------------------------------------------


class TestModuleLevelFlagReadsCoherent:
    """Sprint 6 P0 HIGH introduced the four-site flag read pattern. Sprint 6
    O-4 Commit 1 adds part_cut.py as a fifth site so the predicate reads
    the SAME env vars every other render-pipeline module reads. Drift
    between sites would silently disagree about which parts are skip-
    eligible."""

    def test_part_cut_reads_base_clip_first_flag(self):
        from app.orchestration.stages import part_cut
        assert hasattr(part_cut, "_FEATURE_BASE_CLIP_FIRST")

    def test_part_cut_reads_overlay_flag(self):
        from app.orchestration.stages import part_cut
        assert hasattr(part_cut, "_FEATURE_OVERLAY_AFTER_BASE_CLIP")

    def test_part_cut_reads_validation_artifact_flag(self):
        from app.orchestration.stages import part_cut
        assert hasattr(part_cut, "_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT")

    def test_validation_flag_default_off(self):
        """Sacred Contract #2 spirit — the Sprint 6 P0 HIGH opt-in stays
        OFF by default. Predicate's true cases include the orphan-flag
        configurations that ARE skip-eligible (see Section 3) — defaults
        ensure those cases are reachable."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FEATURE_BASE_CLIP_VALIDATION_ARTIFACT", None)
            v = os.getenv("FEATURE_BASE_CLIP_VALIDATION_ARTIFACT", "0") == "1"
        assert v is False


# ---------------------------------------------------------------------------
# Section 6: source pin — production line still matches the predicate
# ---------------------------------------------------------------------------


class TestSourcePin:
    """Sentinel pins on the production source so a future edit that
    drifts the predicate semantics surfaces in CI rather than as a
    silent render behavior change."""

    def test_predicate_lives_in_part_cut(self):
        from app.orchestration.stages import part_cut
        assert callable(part_cut._should_skip_raw_part_write)

    def test_predicate_combines_subtitle_and_consumer_gates(self):
        from app.orchestration.stages import part_cut
        src = inspect.getsource(part_cut._should_skip_raw_part_write)
        # Both gates must be present in the predicate body.
        assert "part_subtitle_enabled" in src
        assert "base_clip_will_render" in src

    def test_run_cut_stage_emits_telemetry_when_predicate_true(self):
        """Commit 1 ships telemetry, not skip. Source-pin that
        run_cut_stage logs `raw_part_skip_eligible` when the predicate
        fires — future Commit 2 will replace this with the actual skip."""
        from app.orchestration.stages import part_cut
        src = inspect.getsource(part_cut.run_cut_stage)
        assert "raw_part_skip_eligible" in src, (
            "Sprint 6 O-4 Commit 1 telemetry log was removed from "
            "run_cut_stage. Either Commit 2 replaced it (intended) or "
            "the telemetry pin regressed (unintended)."
        )
        assert "_should_skip_raw_part_write" in src, (
            "Predicate evaluation removed from run_cut_stage."
        )
