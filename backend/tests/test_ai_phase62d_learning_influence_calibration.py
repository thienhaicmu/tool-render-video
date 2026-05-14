"""
test_ai_phase62d_learning_influence_calibration.py

Phase 62D — Learning-Aware Influence Calibration
Tests cover: required execution contracts, fallback shape, gate conditions,
positive calibration (subtitle/camera/segment), negative calibration (conflicting
pattern, CPR signals), execution mode behaviour (off/safe/balanced/aggressive),
user override exclusion, confidence delta bounds, total delta cap, determinism,
empty/garbage input safety, and integration scenarios.

REQUIRED EXECUTION TESTS (first 4):
  1. build_learning_influence_calibration returns a dict
  2. Returns "learning_influence_calibration" top-level key
  3. Never raises on None input
  4. Never raises on garbage input
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from app.ai.outcome_tracking.learning_influence_calibration_engine import (
    _apply_total_cap,
    _compute_confidence,
    _neg_action_for_domain,
    _subtitle_action,
    _camera_action,
    build_learning_influence_calibration,
)

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_MAX_POSITIVE_DELTA = 0.04
_MAX_NEGATIVE_DELTA = 0.04
_MAX_TOTAL_DELTA    = 0.10


def _make_plan(
    rot_available: bool = True,
    creator_type: str = "podcast",
    platform: str = "tiktok",
    overall_result: str = "improved",
    ai_effectiveness: str = "strong",
    rot_confidence: float = 0.85,
    quality: dict | None = None,
    ai_execution: dict | None = None,
    ab_available: bool = True,
    ab_winner: str = "ai_on",
    ab_overall_delta: int = 6,
    creator_fit: str = "high",
    bench_status: str = "best_fit",
    # pattern inputs
    classification: str = "strong_pattern",
    pattern_confidence: float = 0.80,
    signals: dict | None = None,
    # reinforcement inputs
    cpr_available: bool = True,
    cpr_confidence: float = 0.75,
    cpr_reinforced: dict | None = None,
    cpr_negative: list | None = None,
    # execution mode
    execution_mode: str = "balanced",
    # user override
    subtitle_override: bool = False,
    camera_override: bool = False,
) -> SimpleNamespace:
    if quality is None:
        quality = {"subtitle": 82, "camera": 80, "hook": 76, "overall": 81}
    if ai_execution is None:
        ai_execution = {"subtitle_applied": True, "camera_applied": True}
    if signals is None:
        signals = {
            "subtitle_style":   "clean_pro",
            "subtitle_density": "balanced",
            "camera_style":     "stable",
            "camera_stability": "high",
            "motion_energy":    "low",
            "ranking_priority": "retention_creator_fit",
        }
    if cpr_reinforced is None:
        cpr_reinforced = {
            "subtitle": {"confidence_delta": 0.04},
            "camera":   {"confidence_delta": 0.04},
        }
    if cpr_negative is None:
        cpr_negative = []

    return SimpleNamespace(
        render_outcome_tracking={
            "available":      rot_available,
            "creator_type":   creator_type,
            "overall_result": overall_result,
            "ai_effectiveness": ai_effectiveness,
            "confidence":     rot_confidence,
            "quality":        quality,
            "ai_execution":   ai_execution,
            "ab_result":      {"winner": ab_winner, "overall_delta": ab_overall_delta},
            "benchmark_result": {"creator_fit": creator_fit},
        },
        creator_preference_reinforcement={
            "available":             cpr_available,
            "confidence":            cpr_confidence,
            "reinforced_preferences": cpr_reinforced,
            "negative_signals":      cpr_negative,
        },
        render_success_patterns={
            "available": True,
            "confidence": pattern_confidence,
            "patterns": [{
                "classification": classification,
                "confidence":     pattern_confidence,
                "signals":        signals,
                "creator_type":   creator_type,
                "platform":       platform,
            }],
        },
        creator_render_strategy={"available": True},
        creator_preference_profile={"platform": platform},
        ai_execution_mode={"mode": execution_mode},
        ai_execution_metrics={"available": True},
        ai_ab_evaluation={"available": ab_available},
        creator_benchmark_summary={"benchmark_status": bench_status},
        subtitle_execution_promotion={"reason": "user_override" if subtitle_override else "ai_strategy"},
        camera_execution_promotion={"reason": "user_override" if camera_override else "ai_strategy"},
        render_quality_v2={},
        platform_quality_feedback={},
        quality_gated_influence={},
    )


def _lic(plan) -> dict:
    return build_learning_influence_calibration(plan).get("learning_influence_calibration", {})


# ---------------------------------------------------------------------------
# REQUIRED EXECUTION TESTS (4)
# ---------------------------------------------------------------------------

class TestRequiredExecution:
    def test_returns_dict(self):
        result = build_learning_influence_calibration(_make_plan())
        assert isinstance(result, dict)

    def test_returns_top_level_key(self):
        result = build_learning_influence_calibration(_make_plan())
        assert "learning_influence_calibration" in result

    def test_never_raises_on_none(self):
        result = build_learning_influence_calibration(None)
        assert isinstance(result, dict)
        assert result["learning_influence_calibration"]["available"] is False

    def test_never_raises_on_garbage(self):
        for bad in ("string", 42, [], object(), True, b"bytes"):
            result = build_learning_influence_calibration(bad)
            assert isinstance(result, dict)
            assert "learning_influence_calibration" in result


# ---------------------------------------------------------------------------
# REQUIRED INTEGRATION TESTS
# ---------------------------------------------------------------------------

class TestRequiredIntegration:
    def test_strong_balanced_produces_all_domains(self):
        """Strong pattern + balanced mode → subtitle, camera, segment all calibrated."""
        lic = _lic(_make_plan(classification="strong_pattern", execution_mode="balanced"))
        assert lic["available"] is True
        cal = lic["calibration"]
        assert "subtitle" in cal
        assert "camera" in cal
        assert "segment" in cal

    def test_strong_balanced_deltas_within_bounds(self):
        lic = _lic(_make_plan(classification="strong_pattern", execution_mode="balanced"))
        for domain, entry in lic["calibration"].items():
            delta = entry["confidence_delta"]
            assert 0.0 < delta <= _MAX_POSITIVE_DELTA, f"{domain} delta {delta} out of bounds"

    def test_strong_balanced_total_within_cap(self):
        lic = _lic(_make_plan(classification="strong_pattern", execution_mode="balanced"))
        pos_total = sum(e["confidence_delta"] for e in lic["calibration"].values())
        neg_total = sum(abs(e["confidence_delta"]) for e in lic["negative_calibration"])
        assert pos_total + neg_total <= _MAX_TOTAL_DELTA + 1e-9

    def test_mode_off_no_execution_calibration(self):
        """Mode off → calibration dict is empty, reasoning mentions mode off."""
        lic = _lic(_make_plan(execution_mode="off"))
        assert lic["available"] is True
        assert lic["calibration"] == {}
        assert lic["negative_calibration"] == []
        assert any("off" in r.lower() for r in lic["reasoning"])

    def test_mode_off_has_confidence(self):
        """Mode off still computes a conservative confidence."""
        lic = _lic(_make_plan(execution_mode="off", pattern_confidence=0.80))
        assert lic["confidence"] == round(0.80 * 0.5, 4)


# ---------------------------------------------------------------------------
# Fallback shape
# ---------------------------------------------------------------------------

class TestFallbackShape:
    def _fb(self, plan) -> dict:
        return _lic(plan)

    def test_fallback_on_none(self):
        fb = self._fb(None)
        assert fb["available"] is False
        assert fb["calibration"] == {}
        assert fb["negative_calibration"] == []
        assert fb["confidence"] == 0.0
        assert fb["reasoning"] == []

    def test_fallback_when_rot_unavailable(self):
        assert self._fb(_make_plan(rot_available=False))["available"] is False

    def test_fallback_when_creator_type_unknown(self):
        assert self._fb(_make_plan(creator_type="unknown"))["available"] is False

    def test_fallback_when_all_quality_zero(self):
        assert self._fb(
            _make_plan(quality={"subtitle": 0, "camera": 0, "hook": 0, "overall": 0})
        )["available"] is False

    def test_fallback_when_rsp_unavailable(self):
        plan = _make_plan()
        plan.render_success_patterns = {"available": False, "patterns": [], "confidence": 0.0}
        assert self._fb(plan)["available"] is False

    def test_fallback_when_rsp_empty_patterns(self):
        plan = _make_plan()
        plan.render_success_patterns = {"available": True, "patterns": [], "confidence": 0.8}
        assert self._fb(plan)["available"] is False


# ---------------------------------------------------------------------------
# Available output shape
# ---------------------------------------------------------------------------

class TestAvailableShape:
    def setup_method(self):
        self.lic = _lic(_make_plan())

    def test_available_true(self):
        assert self.lic["available"] is True

    def test_has_calibration_dict(self):
        assert isinstance(self.lic["calibration"], dict)

    def test_has_negative_calibration_list(self):
        assert isinstance(self.lic["negative_calibration"], list)

    def test_has_user_override_excluded_list(self):
        assert isinstance(self.lic["user_override_excluded"], list)

    def test_confidence_bounded(self):
        assert 0.0 <= self.lic["confidence"] <= 1.0

    def test_reasoning_is_list(self):
        assert isinstance(self.lic["reasoning"], list)

    def test_creator_type_correct(self):
        assert self.lic["creator_type"] == "podcast"

    def test_platform_correct(self):
        assert self.lic["platform"] == "tiktok"

    def test_execution_mode_present(self):
        assert self.lic["execution_mode"] == "balanced"


# ---------------------------------------------------------------------------
# Positive calibration
# ---------------------------------------------------------------------------

class TestPositiveCalibration:
    def test_strong_pattern_subtitle_positive(self):
        cal = _lic(_make_plan(classification="strong_pattern"))["calibration"]
        assert "subtitle" in cal
        assert cal["subtitle"]["confidence_delta"] > 0.0

    def test_strong_pattern_camera_positive(self):
        cal = _lic(_make_plan(classification="strong_pattern"))["calibration"]
        assert "camera" in cal
        assert cal["camera"]["confidence_delta"] > 0.0

    def test_strong_pattern_segment_positive(self):
        cal = _lic(_make_plan(classification="strong_pattern"))["calibration"]
        assert "segment" in cal
        assert cal["segment"]["confidence_delta"] > 0.0

    def test_moderate_pattern_smaller_deltas_than_strong(self):
        strong_cal  = _lic(_make_plan(classification="strong_pattern"))["calibration"]
        moderate_cal = _lic(_make_plan(classification="moderate_pattern"))["calibration"]
        assert moderate_cal["subtitle"]["confidence_delta"] < strong_cal["subtitle"]["confidence_delta"]
        assert moderate_cal["camera"]["confidence_delta"]   < strong_cal["camera"]["confidence_delta"]

    def test_weak_pattern_no_positive_calibration(self):
        cal = _lic(_make_plan(classification="weak_pattern"))["calibration"]
        assert cal == {}

    def test_conflicting_pattern_no_positive_calibration(self):
        cal = _lic(_make_plan(classification="conflicting_pattern"))["calibration"]
        assert cal == {}

    def test_strong_subtitle_action_clean(self):
        plan = _make_plan(signals={"subtitle_style": "clean_pro", "camera_style": "stable", "camera_stability": "high"})
        cal = _lic(plan)["calibration"]
        assert cal["subtitle"]["action"] == "support_clean_compact_subtitles"

    def test_strong_camera_action_stable(self):
        plan = _make_plan(signals={"subtitle_style": "clean_pro", "camera_style": "stable", "camera_stability": "high"})
        cal = _lic(plan)["calibration"]
        assert cal["camera"]["action"] == "support_stable_camera"

    def test_segment_action_retention(self):
        cal = _lic(_make_plan(classification="strong_pattern"))["calibration"]
        assert cal["segment"]["action"] == "support_retention_creator_fit_ranking"

    def test_positive_delta_never_exceeds_max(self):
        """Even with mode=aggressive, no single positive delta exceeds 0.04."""
        cal = _lic(_make_plan(classification="strong_pattern", execution_mode="aggressive"))["calibration"]
        for domain, entry in cal.items():
            assert entry["confidence_delta"] <= _MAX_POSITIVE_DELTA, (
                f"{domain} delta {entry['confidence_delta']} exceeds max"
            )


# ---------------------------------------------------------------------------
# Negative calibration
# ---------------------------------------------------------------------------

class TestNegativeCalibration:
    def test_conflicting_pattern_produces_negative(self):
        neg = _lic(_make_plan(classification="conflicting_pattern"))["negative_calibration"]
        assert len(neg) > 0

    def test_conflicting_camera_negative_entry(self):
        neg = _lic(_make_plan(classification="conflicting_pattern"))["negative_calibration"]
        domains = [e["domain"] for e in neg]
        assert "camera" in domains

    def test_conflicting_subtitle_negative_entry(self):
        neg = _lic(_make_plan(classification="conflicting_pattern"))["negative_calibration"]
        domains = [e["domain"] for e in neg]
        assert "subtitle" in domains

    def test_negative_delta_is_negative(self):
        neg = _lic(_make_plan(classification="conflicting_pattern"))["negative_calibration"]
        for entry in neg:
            assert entry["confidence_delta"] < 0.0, (
                f"{entry['domain']} delta {entry['confidence_delta']} should be negative"
            )

    def test_negative_delta_bounded(self):
        neg = _lic(_make_plan(classification="conflicting_pattern"))["negative_calibration"]
        for entry in neg:
            assert abs(entry["confidence_delta"]) <= _MAX_NEGATIVE_DELTA

    def test_cpr_negative_signal_propagates(self):
        cpr_neg = [{"domain": "camera", "signal": "aggressive motion underperformed", "confidence_delta": 0.03}]
        neg = _lic(_make_plan(
            classification="strong_pattern",   # no pattern-level negative
            cpr_negative=cpr_neg,
        ))["negative_calibration"]
        domains = [e["domain"] for e in neg]
        assert "camera" in domains

    def test_no_duplicate_negative_domain(self):
        """Each domain appears at most once in negative_calibration."""
        neg = _lic(_make_plan(classification="conflicting_pattern"))["negative_calibration"]
        domains = [e["domain"] for e in neg]
        assert len(domains) == len(set(domains))

    def test_strong_pattern_no_negative_calibration(self):
        neg = _lic(_make_plan(classification="strong_pattern", cpr_negative=[]))["negative_calibration"]
        assert neg == []


# ---------------------------------------------------------------------------
# Execution mode behaviour
# ---------------------------------------------------------------------------

class TestExecutionMode:
    def test_mode_off_empty_calibration(self):
        assert _lic(_make_plan(execution_mode="off"))["calibration"] == {}

    def test_mode_off_empty_negative(self):
        assert _lic(_make_plan(execution_mode="off"))["negative_calibration"] == []

    def test_mode_off_available_true(self):
        assert _lic(_make_plan(execution_mode="off"))["available"] is True

    def test_mode_safe_smaller_positive_than_balanced(self):
        safe_cal     = _lic(_make_plan(execution_mode="safe",     classification="strong_pattern"))["calibration"]
        balanced_cal = _lic(_make_plan(execution_mode="balanced", classification="strong_pattern"))["calibration"]
        assert safe_cal["subtitle"]["confidence_delta"] < balanced_cal["subtitle"]["confidence_delta"]

    def test_mode_safe_negative_applies_fully(self):
        """Safe mode applies negative calibration at full scale."""
        safe_neg     = _lic(_make_plan(execution_mode="safe",     classification="conflicting_pattern"))["negative_calibration"]
        balanced_neg = _lic(_make_plan(execution_mode="balanced", classification="conflicting_pattern"))["negative_calibration"]
        safe_cam     = next(e for e in safe_neg     if e["domain"] == "camera")
        balanced_cam = next(e for e in balanced_neg if e["domain"] == "camera")
        assert abs(safe_cam["confidence_delta"]) == abs(balanced_cam["confidence_delta"])

    def test_mode_aggressive_larger_than_balanced(self):
        agg_cal  = _lic(_make_plan(execution_mode="aggressive", classification="strong_pattern"))["calibration"]
        bal_cal  = _lic(_make_plan(execution_mode="balanced",   classification="strong_pattern"))["calibration"]
        assert agg_cal["subtitle"]["confidence_delta"] >= bal_cal["subtitle"]["confidence_delta"]

    def test_mode_aggressive_still_capped(self):
        agg_cal = _lic(_make_plan(execution_mode="aggressive", classification="strong_pattern"))["calibration"]
        for domain, entry in agg_cal.items():
            assert entry["confidence_delta"] <= _MAX_POSITIVE_DELTA

    def test_unknown_mode_treated_as_balanced(self):
        plan = _make_plan()
        plan.ai_execution_mode = {"mode": "unknown_mode"}
        lic = _lic(plan)
        assert lic["execution_mode"] == "balanced"
        assert lic["available"] is True


# ---------------------------------------------------------------------------
# User override exclusion
# ---------------------------------------------------------------------------

class TestUserOverrideExclusion:
    def test_subtitle_override_excluded_from_calibration(self):
        lic = _lic(_make_plan(subtitle_override=True, classification="strong_pattern"))
        assert "subtitle" not in lic["calibration"]

    def test_subtitle_override_in_excluded_list(self):
        lic = _lic(_make_plan(subtitle_override=True, classification="strong_pattern"))
        assert "subtitle" in lic["user_override_excluded"]

    def test_camera_override_excluded_from_calibration(self):
        lic = _lic(_make_plan(camera_override=True, classification="strong_pattern"))
        assert "camera" not in lic["calibration"]

    def test_camera_override_in_excluded_list(self):
        lic = _lic(_make_plan(camera_override=True, classification="strong_pattern"))
        assert "camera" in lic["user_override_excluded"]

    def test_segment_not_affected_by_subtitle_override(self):
        lic = _lic(_make_plan(subtitle_override=True, classification="strong_pattern"))
        assert "segment" in lic["calibration"]

    def test_no_override_excluded_list_empty(self):
        lic = _lic(_make_plan(subtitle_override=False, camera_override=False))
        assert lic["user_override_excluded"] == []

    def test_override_mode_off_also_recorded(self):
        lic = _lic(_make_plan(execution_mode="off", subtitle_override=True))
        assert "subtitle" in lic["user_override_excluded"]


# ---------------------------------------------------------------------------
# Confidence delta bounds
# ---------------------------------------------------------------------------

class TestConfidenceDeltaBounds:
    def test_all_positive_deltas_bounded(self):
        for mode in ("safe", "balanced", "aggressive"):
            cal = _lic(_make_plan(execution_mode=mode, classification="strong_pattern"))["calibration"]
            for domain, entry in cal.items():
                assert entry["confidence_delta"] <= _MAX_POSITIVE_DELTA

    def test_all_negative_deltas_bounded(self):
        for mode in ("safe", "balanced", "aggressive"):
            neg = _lic(_make_plan(
                execution_mode=mode, classification="conflicting_pattern"
            ))["negative_calibration"]
            for entry in neg:
                assert abs(entry["confidence_delta"]) <= _MAX_NEGATIVE_DELTA


# ---------------------------------------------------------------------------
# Total delta cap
# ---------------------------------------------------------------------------

class TestTotalDeltaCap:
    def test_total_absolute_within_cap(self):
        for cls in ("strong_pattern", "moderate_pattern", "conflicting_pattern"):
            lic = _lic(_make_plan(classification=cls))
            pos  = sum(e["confidence_delta"] for e in lic["calibration"].values())
            neg  = sum(abs(e["confidence_delta"]) for e in lic["negative_calibration"])
            assert pos + neg <= _MAX_TOTAL_DELTA + 1e-9, (
                f"Total {pos + neg} exceeded cap for {cls}"
            )

    def test_apply_total_cap_scales_proportionally(self):
        cal = {
            "subtitle": {"confidence_delta": 0.06},
            "camera":   {"confidence_delta": 0.06},
        }
        neg: list = []
        scaled_cal, _ = _apply_total_cap(cal, neg)
        total = sum(v["confidence_delta"] for v in scaled_cal.values())
        assert abs(total - _MAX_TOTAL_DELTA) < 1e-6

    def test_apply_total_cap_preserves_proportion(self):
        cal = {
            "subtitle": {"confidence_delta": 0.06},
            "camera":   {"confidence_delta": 0.04},
        }
        scaled_cal, _ = _apply_total_cap(cal, [])
        ratio = scaled_cal["subtitle"]["confidence_delta"] / scaled_cal["camera"]["confidence_delta"]
        assert abs(ratio - 1.5) < 1e-6

    def test_apply_total_cap_no_change_when_within(self):
        cal = {
            "subtitle": {"confidence_delta": 0.02},
            "camera":   {"confidence_delta": 0.03},
        }
        scaled, _ = _apply_total_cap(cal, [])
        assert scaled["subtitle"]["confidence_delta"] == 0.02
        assert scaled["camera"]["confidence_delta"] == 0.03


# ---------------------------------------------------------------------------
# Compute confidence
# ---------------------------------------------------------------------------

class TestComputeConfidence:
    def test_strong_pattern_full_scale(self):
        conf = _compute_confidence(0.80, 0.70, "balanced", "strong_pattern")
        expected = round((0.80 * 0.6 + 0.70 * 0.4) * 1.0 * 1.0, 4)
        assert conf == expected

    def test_moderate_pattern_scaled(self):
        conf = _compute_confidence(0.80, 0.70, "balanced", "moderate_pattern")
        expected = round((0.80 * 0.6 + 0.70 * 0.4) * 0.8, 4)
        assert conf == expected

    def test_weak_pattern_zero(self):
        assert _compute_confidence(0.90, 0.90, "balanced", "weak_pattern") == 0.0

    def test_conflicting_pattern_halved(self):
        conf = _compute_confidence(0.80, 0.80, "balanced", "conflicting_pattern")
        expected = round((0.80 * 0.6 + 0.80 * 0.4) * 0.5, 4)
        assert conf == expected

    def test_safe_mode_slightly_lower(self):
        safe_conf    = _compute_confidence(0.80, 0.70, "safe",    "strong_pattern")
        balanced_conf = _compute_confidence(0.80, 0.70, "balanced","strong_pattern")
        assert safe_conf < balanced_conf

    def test_confidence_clamped(self):
        conf = _compute_confidence(1.0, 1.0, "aggressive", "strong_pattern")
        assert 0.0 <= conf <= 1.0


# ---------------------------------------------------------------------------
# Action helpers
# ---------------------------------------------------------------------------

class TestActionHelpers:
    def test_subtitle_action_clean(self):
        assert _subtitle_action({"subtitle_style": "clean_pro"}) == "support_clean_compact_subtitles"

    def test_subtitle_action_bold(self):
        assert _subtitle_action({"subtitle_style": "bold_impact"}) == "support_emphasis_subtitles"

    def test_subtitle_action_default(self):
        assert _subtitle_action({}) == "support_subtitle_influence"

    def test_camera_action_stable(self):
        assert _camera_action({"camera_style": "stable"}) == "support_stable_camera"

    def test_camera_action_dynamic(self):
        assert _camera_action({"camera_style": "dynamic"}) == "support_dynamic_camera"

    def test_camera_action_high_stability(self):
        assert _camera_action({"camera_stability": "high"}) == "support_stable_camera"

    def test_neg_action_camera(self):
        assert _neg_action_for_domain("camera") == "soften_aggressive_camera"

    def test_neg_action_subtitle(self):
        assert _neg_action_for_domain("subtitle") == "soften_subtitle_emphasis"

    def test_neg_action_ranking(self):
        assert _neg_action_for_domain("ranking") == "reduce_segment_ranking_confidence"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        plan = _make_plan()
        r1 = build_learning_influence_calibration(plan)
        r2 = build_learning_influence_calibration(plan)
        assert r1 == r2

    def test_different_classifications_different_deltas(self):
        strong   = _lic(_make_plan(classification="strong_pattern"))
        moderate = _lic(_make_plan(classification="moderate_pattern"))
        assert strong["calibration"]["subtitle"]["confidence_delta"] != moderate["calibration"]["subtitle"]["confidence_delta"]


# ---------------------------------------------------------------------------
# Edge cases / safety
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_no_crash_confidence_not_nan(self):
        plan = _make_plan()
        lic  = _lic(plan)
        assert not math.isnan(lic["confidence"])

    def test_dict_edit_plan_accepted(self):
        plan = _make_plan()
        plan_dict = {
            "render_outcome_tracking":          plan.render_outcome_tracking,
            "creator_preference_reinforcement": plan.creator_preference_reinforcement,
            "render_success_patterns":          plan.render_success_patterns,
            "creator_preference_profile":       plan.creator_preference_profile,
            "ai_execution_mode":                plan.ai_execution_mode,
            "subtitle_execution_promotion":     plan.subtitle_execution_promotion,
            "camera_execution_promotion":       plan.camera_execution_promotion,
        }
        result = build_learning_influence_calibration(plan_dict)
        assert isinstance(result, dict)
        assert "learning_influence_calibration" in result

    def test_no_unsafe_fields_in_output(self):
        """Output must not expose internal or unsafe keys."""
        lic = _lic(_make_plan())
        for bad_key in ("db", "cloud", "retrain", "finetune", "render_command", "ffmpeg"):
            assert bad_key not in lic
            assert all(bad_key not in str(v) for v in lic.values())

    def test_reasoning_length_bounded(self):
        lic = _lic(_make_plan())
        assert len(lic["reasoning"]) <= 5

    def test_calibration_entry_has_reason(self):
        lic = _lic(_make_plan(classification="strong_pattern"))
        for domain, entry in lic["calibration"].items():
            assert "reason" in entry, f"{domain} entry missing 'reason'"

    def test_partial_quality_still_available(self):
        plan = _make_plan(quality={"overall": 70})
        assert _lic(plan)["available"] is True
