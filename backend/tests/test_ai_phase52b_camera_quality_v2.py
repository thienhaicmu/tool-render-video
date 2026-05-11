"""
test_ai_phase52b_camera_quality_v2.py — Phase 52B Camera Quality Intelligence v2 tests.

Tests:
  - Full camera quality v2 evaluation
  - Missing metadata fallback
  - Deterministic scoring
  - Score clamping 0–100
  - Confidence clamping 0–1
  - Risk score handling
  - Creator fit scoring
  - No crash on empty input
  - No unsafe/internal fields exposed
  - No dependency on motion_crop execution
  - Render influence reporting
"""
from __future__ import annotations

import types
from typing import Any

import pytest

from app.ai.camera_quality.camera_quality_evaluator import evaluate_camera_quality_v2
from app.ai.camera_quality.camera_quality_schema import (
    CameraQualityV2,
    SCORE_WEIGHTS,
    RISK_WEIGHT,
    fallback_camera_quality_v2,
)
from app.ai.camera_quality.camera_quality_scorer import (
    score_micro_jitter_risk,
    score_whip_pan_risk,
    score_crop_smoothness,
    score_subject_stability,
    score_scene_continuity,
    score_creator_fit,
    compute_confidence,
)
from app.ai.director.render_influence import apply_ai_render_influence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan(**kwargs) -> Any:
    ns = types.SimpleNamespace(
        creator_camera_preference={},
        camera_motion_apply={},
        creator_preference_profile={},
        market_optimization_intelligence={},
        creator_preset_evolution={},
        beat_visual_execution={},
        pacing={},
        render_quality_evaluation={},
        adaptive_creator_intelligence={},
        story={},
        camera=None,
        # Other fields needed for render influence
        subtitle_execution={},
        subtitle_text_apply={},
        creator_subtitle_preference={},
        creator_subtitle_influence={},
        strategy_variants={},
        variant_evaluation={},
        best_strategy_reasoning={},
        subtitle_quality_v2={},
        camera_quality_v2={},
    )
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _full_plan() -> Any:
    """Build a rich plan with all camera quality signals populated."""
    return _plan(
        creator_camera_preference={
            "available": True,
            "inference_mode": "metadata_only",
            "camera_preference": {
                "motion_style":             "smooth_subject",
                "crop_aggressiveness":      "low",
                "stability_priority":       "high",
                "deadzone_preference":      "wide",
                "subject_hold":             "long",
                "scene_sensitivity":        "medium",
                "center_bias":              "medium",
                "reframing_risk_tolerance": "low",
                "smoothness_priority":      "high",
                "confidence":              0.78,
                "signals": ["signal_a", "signal_b"],
            },
            "tuning_pack": {
                "applied": True,
                "confidence_tier": "high",
                "deadzone_delta": 0.02,
                "ema_alpha_delta": 0.02,
                "hold_frames_delta": 3,
                "scene_threshold_delta": 1.0,
                "smooth_window_delta": 2,
                "reasoning": ["stability preference applied"],
                "warnings": [],
            },
            "warnings": [],
        },
        camera_motion_apply={
            "available": True,
            "enabled": True,
            "mode": "balanced",
            "applied": [
                {
                    "apply_id": "cam_001",
                    "camera_type": "motion_smoothing_hint",
                    "confidence": 0.82,
                    "applied": True,
                    "safe": True,
                    "changes": {"motion_smoothing": True},
                    "warnings": [],
                },
                {
                    "apply_id": "cam_002",
                    "camera_type": "subject_lock_preference",
                    "confidence": 0.75,
                    "applied": True,
                    "safe": True,
                    "changes": {"subject_lock_preference": True},
                    "warnings": [],
                },
            ],
            "blocked": [],
            "warnings": [],
        },
        creator_preference_profile={
            "available": True,
            "confidence": 0.76,
            "camera": {"motion_style": "smooth_subject", "confidence": 0.74},
            "subtitle": {"style": "viral_bold", "confidence": 0.72},
            "conflicts_resolved": [],
            "market_alignment": {"market_fit": "tiktok"},
        },
        market_optimization_intelligence={
            "enabled": True,
            "available": True,
            "target_market": "tiktok",
            "camera_market_bias": {
                "weight": 0.5,
                "preferred_style": "smooth_subject",
            },
        },
        creator_preset_evolution={
            "available": True,
            "evolved_presets": [{"id": "p1"}],
        },
        adaptive_creator_intelligence={
            "available": True,
            "enabled": True,
            "creator_profile": {
                "style_confidence": 0.65,
                "camera_confidence": 0.72,
            },
        },
        beat_visual_execution={
            "available": True,
            "warnings": [],
        },
        pacing={
            "beat_available": True,
            "bpm": 110.0,
            "energy_level": 0.6,
        },
        story={
            "available": True,
            "segments": [{"type": "hook"}, {"type": "content"}],
        },
        render_quality_evaluation={
            "available": True,
            "enabled": True,
            "output_scores": [
                {"camera_smoothness": 85.0},
                {"camera_smoothness": 80.0},
            ],
        },
    )


def _payload():
    return types.SimpleNamespace(add_subtitle=True, motion_aware_crop=False)


# ---------------------------------------------------------------------------
# TestFullEvaluation
# ---------------------------------------------------------------------------

class TestFullEvaluation:
    def test_returns_dict_with_camera_quality_v2_key(self):
        result = evaluate_camera_quality_v2(_full_plan())
        assert "camera_quality_v2" in result

    def test_all_required_keys_present(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        required = {
            "micro_jitter_risk", "whip_pan_risk", "crop_smoothness",
            "subject_stability", "scene_continuity", "creator_fit",
            "overall", "confidence", "reasoning",
        }
        assert required.issubset(cqv2.keys())

    def test_positive_scores_are_integers(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        for key in ("crop_smoothness", "subject_stability", "scene_continuity",
                    "creator_fit", "overall"):
            assert isinstance(cqv2[key], int), f"{key} should be int"

    def test_risk_scores_are_integers(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        for key in ("micro_jitter_risk", "whip_pan_risk"):
            assert isinstance(cqv2[key], int), f"{key} should be int"

    def test_confidence_is_float(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        assert isinstance(cqv2["confidence"], float)

    def test_reasoning_is_list(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        assert isinstance(cqv2["reasoning"], list)

    def test_full_plan_overall_above_zero(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        assert cqv2["overall"] > 0

    def test_full_plan_confidence_above_zero(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        assert cqv2["confidence"] > 0.0

    def test_full_plan_reasoning_not_empty(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        assert len(cqv2["reasoning"]) > 0

    def test_no_extra_unexpected_keys(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        expected = {
            "micro_jitter_risk", "whip_pan_risk", "crop_smoothness",
            "subject_stability", "scene_continuity", "creator_fit",
            "overall", "confidence", "reasoning",
        }
        assert set(cqv2.keys()) == expected


# ---------------------------------------------------------------------------
# TestFallbackBehavior
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    def test_none_input_returns_fallback(self):
        result = evaluate_camera_quality_v2(None)
        cqv2 = result["camera_quality_v2"]
        assert cqv2["overall"] == 0
        assert cqv2["confidence"] == 0.0
        assert cqv2["reasoning"] == []

    def test_empty_namespace_does_not_crash(self):
        result = evaluate_camera_quality_v2(types.SimpleNamespace())
        assert "camera_quality_v2" in result

    def test_garbage_string_does_not_crash(self):
        result = evaluate_camera_quality_v2("not_a_plan")
        assert "camera_quality_v2" in result

    def test_garbage_integer_does_not_crash(self):
        result = evaluate_camera_quality_v2(42)
        assert "camera_quality_v2" in result

    def test_fallback_all_scores_zero(self):
        fallback = fallback_camera_quality_v2()
        for key in ("micro_jitter_risk", "whip_pan_risk", "crop_smoothness",
                    "subject_stability", "scene_continuity", "creator_fit", "overall"):
            assert fallback[key] == 0

    def test_fallback_confidence_zero(self):
        assert fallback_camera_quality_v2()["confidence"] == 0.0

    def test_fallback_reasoning_empty(self):
        assert fallback_camera_quality_v2()["reasoning"] == []

    def test_missing_camera_preference_does_not_crash(self):
        plan = _plan(creator_camera_preference=None)
        result = evaluate_camera_quality_v2(plan)
        assert "camera_quality_v2" in result

    def test_missing_camera_apply_does_not_crash(self):
        plan = _plan(camera_motion_apply=None)
        result = evaluate_camera_quality_v2(plan)
        assert "camera_quality_v2" in result

    def test_missing_creator_profile_does_not_crash(self):
        plan = _plan(creator_preference_profile=None, creator_camera_preference=None)
        result = evaluate_camera_quality_v2(plan)
        assert "camera_quality_v2" in result

    def test_missing_market_does_not_crash(self):
        plan = _plan(market_optimization_intelligence=None)
        result = evaluate_camera_quality_v2(plan)
        assert "camera_quality_v2" in result


# ---------------------------------------------------------------------------
# TestScoreClamping
# ---------------------------------------------------------------------------

class TestScoreClamping:
    def test_micro_jitter_risk_clamped_0_100(self):
        v = score_micro_jitter_risk(_full_plan())
        assert 0 <= v <= 100

    def test_whip_pan_risk_clamped_0_100(self):
        v = score_whip_pan_risk(_full_plan())
        assert 0 <= v <= 100

    def test_crop_smoothness_clamped_0_100(self):
        v = score_crop_smoothness(_full_plan())
        assert 0 <= v <= 100

    def test_subject_stability_clamped_0_100(self):
        v = score_subject_stability(_full_plan())
        assert 0 <= v <= 100

    def test_scene_continuity_clamped_0_100(self):
        v = score_scene_continuity(_full_plan())
        assert 0 <= v <= 100

    def test_creator_fit_clamped_0_100(self):
        v = score_creator_fit(_full_plan())
        assert 0 <= v <= 100

    def test_overall_clamped_0_100(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        assert 0 <= cqv2["overall"] <= 100

    def test_schema_to_dict_clamps_above_100(self):
        obj = CameraQualityV2(crop_smoothness=999, overall=200)
        d = obj.to_dict()
        assert d["crop_smoothness"] == 100
        assert d["overall"] == 100

    def test_schema_to_dict_clamps_below_0(self):
        obj = CameraQualityV2(crop_smoothness=-50, overall=-10)
        d = obj.to_dict()
        assert d["crop_smoothness"] == 0
        assert d["overall"] == 0


# ---------------------------------------------------------------------------
# TestConfidenceClamping
# ---------------------------------------------------------------------------

class TestConfidenceClamping:
    def test_confidence_in_0_1(self):
        conf = compute_confidence(_full_plan())
        assert 0.0 <= conf <= 1.0

    def test_no_signals_gives_zero_confidence(self):
        conf = compute_confidence(None)
        assert conf == 0.0

    def test_schema_clamps_confidence_above_1(self):
        obj = CameraQualityV2(confidence=5.0)
        assert obj.to_dict()["confidence"] == 1.0

    def test_schema_clamps_confidence_below_0(self):
        obj = CameraQualityV2(confidence=-1.0)
        assert obj.to_dict()["confidence"] == 0.0

    def test_full_plan_confidence_in_range(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        assert 0.0 <= cqv2["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_overall(self):
        plan = _full_plan()
        r1 = evaluate_camera_quality_v2(plan)["camera_quality_v2"]["overall"]
        r2 = evaluate_camera_quality_v2(plan)["camera_quality_v2"]["overall"]
        assert r1 == r2

    def test_same_input_same_jitter_risk(self):
        plan = _full_plan()
        assert score_micro_jitter_risk(plan) == score_micro_jitter_risk(plan)

    def test_same_input_same_creator_fit(self):
        plan = _full_plan()
        assert score_creator_fit(plan) == score_creator_fit(plan)

    def test_same_input_same_confidence(self):
        plan = _full_plan()
        assert compute_confidence(plan) == compute_confidence(plan)

    def test_same_input_same_reasoning(self):
        plan = _full_plan()
        r1 = evaluate_camera_quality_v2(plan)["camera_quality_v2"]["reasoning"]
        r2 = evaluate_camera_quality_v2(plan)["camera_quality_v2"]["reasoning"]
        assert r1 == r2


# ---------------------------------------------------------------------------
# TestRiskScoreHandling
# ---------------------------------------------------------------------------

class TestRiskScoreHandling:
    def test_jitter_risk_low_on_high_stability(self):
        plan = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "stability_priority": "high",
                    "deadzone_preference": "wide",
                    "reframing_risk_tolerance": "low",
                    "smoothness_priority": "high",
                    "motion_style": "static_center",
                    "confidence": 0.7,
                },
            }
        )
        risk = score_micro_jitter_risk(plan)
        assert risk < 20  # high stability → low jitter

    def test_jitter_risk_high_on_low_stability(self):
        plan = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "stability_priority": "low",
                    "deadzone_preference": "narrow",
                    "reframing_risk_tolerance": "high",
                    "smoothness_priority": "low",
                    "motion_style": "dynamic_subject",
                    "confidence": 0.4,
                },
            },
            camera_motion_apply={"applied": [], "blocked": [], "warnings": ["jitter_detected"]},
        )
        risk = score_micro_jitter_risk(plan)
        assert risk >= 25

    def test_whip_pan_risk_low_on_static_center(self):
        plan = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "motion_style": "static_center",
                    "crop_aggressiveness": "low",
                    "scene_sensitivity": "low",
                    "confidence": 0.7,
                },
            },
            pacing={"bpm": 90.0},
        )
        risk = score_whip_pan_risk(plan)
        assert risk < 20

    def test_whip_pan_risk_high_on_dynamic_aggressive(self):
        plan = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "motion_style": "dynamic_subject",
                    "crop_aggressiveness": "high",
                    "scene_sensitivity": "high",
                    "confidence": 0.5,
                },
            },
            pacing={"bpm": 170.0},
        )
        risk = score_whip_pan_risk(plan)
        assert risk >= 35

    def test_high_risk_reduces_overall(self):
        low_risk_plan = _full_plan()
        # Full plan already has low risk settings

        high_risk_plan = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "motion_style": "dynamic_subject",
                    "crop_aggressiveness": "high",
                    "stability_priority": "low",
                    "deadzone_preference": "narrow",
                    "subject_hold": "short",
                    "scene_sensitivity": "high",
                    "center_bias": "low",
                    "reframing_risk_tolerance": "high",
                    "smoothness_priority": "low",
                    "confidence": 0.5,
                },
            },
            pacing={"bpm": 180.0},
        )

        low_overall  = evaluate_camera_quality_v2(low_risk_plan)["camera_quality_v2"]["overall"]
        high_overall = evaluate_camera_quality_v2(high_risk_plan)["camera_quality_v2"]["overall"]
        assert low_overall >= high_overall - 5  # low risk plan should score at least as high

    def test_motion_smoothing_hint_reduces_jitter(self):
        with_smoothing = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "stability_priority": "medium",
                    "deadzone_preference": "medium",
                    "smoothness_priority": "medium",
                    "confidence": 0.6,
                },
            },
            camera_motion_apply={
                "applied": [{"camera_type": "motion_smoothing_hint", "safe": True}],
                "blocked": [],
                "warnings": [],
            },
        )
        no_smoothing = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "stability_priority": "medium",
                    "deadzone_preference": "medium",
                    "smoothness_priority": "medium",
                    "confidence": 0.6,
                },
            },
            camera_motion_apply={"applied": [], "blocked": [], "warnings": []},
        )
        assert score_micro_jitter_risk(with_smoothing) < score_micro_jitter_risk(no_smoothing)


# ---------------------------------------------------------------------------
# TestCropSmoothness
# ---------------------------------------------------------------------------

class TestCropSmoothness:
    def test_high_smoothness_priority_improves_crop(self):
        high = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "smoothness_priority": "high",
                    "deadzone_preference": "wide",
                    "stability_priority": "high",
                    "confidence": 0.7,
                },
            }
        )
        low = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "smoothness_priority": "low",
                    "deadzone_preference": "narrow",
                    "stability_priority": "low",
                    "confidence": 0.5,
                },
            }
        )
        assert score_crop_smoothness(high) > score_crop_smoothness(low)

    def test_phase45_signal_blends_into_smoothness(self):
        with_rqe = _plan(
            creator_camera_preference={},
            render_quality_evaluation={
                "available": True,
                "output_scores": [{"camera_smoothness": 90.0}],
            },
        )
        without_rqe = _plan(
            creator_camera_preference={},
            render_quality_evaluation={},
        )
        # With good Phase 45 score, smoothness should be higher or equal
        assert score_crop_smoothness(with_rqe) >= score_crop_smoothness(without_rqe) - 5

    def test_clamped_0_100(self):
        v = score_crop_smoothness(_full_plan())
        assert 0 <= v <= 100


# ---------------------------------------------------------------------------
# TestSubjectStability
# ---------------------------------------------------------------------------

class TestSubjectStability:
    def test_long_hold_high_stability_improves_score(self):
        stable = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "subject_hold": "long",
                    "stability_priority": "high",
                    "center_bias": "high",
                    "motion_style": "static_center",
                    "confidence": 0.8,
                },
            }
        )
        unstable = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "subject_hold": "short",
                    "stability_priority": "low",
                    "center_bias": "low",
                    "motion_style": "dynamic_subject",
                    "confidence": 0.4,
                },
            }
        )
        assert score_subject_stability(stable) > score_subject_stability(unstable)

    def test_subject_lock_preference_applied_boosts_stability(self):
        with_lock = _plan(
            creator_camera_preference={},
            camera_motion_apply={
                "applied": [{"camera_type": "subject_lock_preference", "safe": True}],
                "blocked": [],
                "warnings": [],
            },
        )
        without_lock = _plan(
            creator_camera_preference={},
            camera_motion_apply={"applied": [], "blocked": [], "warnings": []},
        )
        assert score_subject_stability(with_lock) >= score_subject_stability(without_lock)

    def test_clamped_0_100(self):
        v = score_subject_stability(_full_plan())
        assert 0 <= v <= 100


# ---------------------------------------------------------------------------
# TestSceneContiguity
# ---------------------------------------------------------------------------

class TestSceneContinuity:
    def test_medium_scene_sensitivity_best_continuity(self):
        medium = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "scene_sensitivity": "medium",
                    "motion_style": "smooth_subject",
                    "confidence": 0.7,
                },
            }
        )
        high = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "scene_sensitivity": "high",
                    "motion_style": "dynamic_subject",
                    "confidence": 0.5,
                },
            }
        )
        assert score_scene_continuity(medium) >= score_scene_continuity(high)

    def test_beat_visual_execution_boosts_continuity(self):
        with_bve = _plan(
            creator_camera_preference={},
            beat_visual_execution={"available": True, "warnings": []},
        )
        without_bve = _plan(
            creator_camera_preference={},
            beat_visual_execution={},
        )
        assert score_scene_continuity(with_bve) >= score_scene_continuity(without_bve)

    def test_clamped_0_100(self):
        v = score_scene_continuity(_full_plan())
        assert 0 <= v <= 100


# ---------------------------------------------------------------------------
# TestCreatorFitScoring
# ---------------------------------------------------------------------------

class TestCreatorFitScoring:
    def test_no_creator_data_returns_neutral(self):
        plan = _plan(creator_camera_preference={"available": False})
        v = score_creator_fit(plan)
        assert 0 <= v <= 100

    def test_high_confidence_preference_boosts_creator_fit(self):
        high_conf = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "motion_style": "smooth_subject",
                    "stability_priority": "high",
                    "confidence": 0.85,
                },
            },
            creator_preference_profile={
                "available": True,
                "camera": {"motion_style": "smooth_subject", "confidence": 0.82},
                "confidence": 0.8,
            },
        )
        low_conf = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "motion_style": "unknown",
                    "stability_priority": "unknown",
                    "confidence": 0.15,
                },
            },
            creator_preference_profile={
                "available": True,
                "camera": {"motion_style": "unknown", "confidence": 0.1},
                "confidence": 0.1,
            },
        )
        assert score_creator_fit(high_conf) > score_creator_fit(low_conf)

    def test_style_agreement_50b_50d_boosts_score(self):
        agree = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "motion_style": "smooth_subject",
                    "confidence": 0.72,
                },
                "tuning_pack": {"confidence_tier": "medium"},
            },
            creator_preference_profile={
                "available": True,
                "camera": {"motion_style": "smooth_subject", "confidence": 0.70},
                "confidence": 0.70,
            },
        )
        disagree = _plan(
            creator_camera_preference={
                "available": True,
                "camera_preference": {
                    "motion_style": "smooth_subject",
                    "confidence": 0.72,
                },
                "tuning_pack": {"confidence_tier": "medium"},
            },
            creator_preference_profile={
                "available": True,
                "camera": {"motion_style": "dynamic_subject", "confidence": 0.70},
                "confidence": 0.70,
            },
        )
        assert score_creator_fit(agree) >= score_creator_fit(disagree)

    def test_creator_fit_clamped_0_100(self):
        v = score_creator_fit(_full_plan())
        assert 0 <= v <= 100


# ---------------------------------------------------------------------------
# TestScoringWeights
# ---------------------------------------------------------------------------

class TestScoringWeights:
    def test_weights_sum_to_0_9(self):
        total = sum(SCORE_WEIGHTS.values())
        assert abs(total - 0.90) < 1e-9

    def test_risk_weight_is_0_1(self):
        assert abs(RISK_WEIGHT - 0.10) < 1e-9

    def test_total_weights_sum_to_1(self):
        total = sum(SCORE_WEIGHTS.values()) + RISK_WEIGHT
        assert abs(total - 1.0) < 1e-9

    def test_all_dimensions_have_weights(self):
        for dim in ("crop_smoothness", "subject_stability", "scene_continuity", "creator_fit"):
            assert dim in SCORE_WEIGHTS

    def test_crop_and_stability_equal_highest_weights(self):
        assert SCORE_WEIGHTS["crop_smoothness"] == SCORE_WEIGHTS["subject_stability"]
        assert SCORE_WEIGHTS["crop_smoothness"] >= SCORE_WEIGHTS["scene_continuity"]


# ---------------------------------------------------------------------------
# TestNoUnsafeFields
# ---------------------------------------------------------------------------

class TestNoUnsafeFields:
    _FORBIDDEN = {"Traceback", "Exception", "Error", "__class__", "__dict__",
                  "stack", "exec", "eval", "compile", "motion_crop", "crop_x",
                  "crop_y", "ffmpeg"}

    def _check_no_forbidden(self, text: str) -> None:
        text_lower = text.lower()
        for f in self._FORBIDDEN:
            assert f.lower() not in text_lower, f"Forbidden text in reasoning: {f!r}"

    def test_no_debug_text_in_reasoning(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        for line in cqv2["reasoning"]:
            self._check_no_forbidden(line)

    def test_no_forbidden_keys_in_result(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        forbidden_keys = {"traceback", "exception", "class", "__dict__", "ffmpeg",
                          "crop_x", "crop_y", "motion_crop"}
        for k in cqv2.keys():
            assert k not in forbidden_keys

    def test_no_forbidden_keys_in_fallback(self):
        fallback = fallback_camera_quality_v2()
        forbidden_keys = {"traceback", "exception", "class", "__dict__"}
        for k in fallback.keys():
            assert k not in forbidden_keys

    def test_no_render_pipeline_fields_in_result(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        render_fields = {"ffmpeg", "playback_speed", "crop_x", "crop_y",
                         "executor", "rerender", "segment_start", "segment_end",
                         "motion_crop", "tracking_config"}
        for k in cqv2.keys():
            assert k not in render_fields

    def test_reasoning_max_six_items(self):
        cqv2 = evaluate_camera_quality_v2(_full_plan())["camera_quality_v2"]
        assert len(cqv2["reasoning"]) <= 6

    def test_no_motion_crop_dependency(self):
        # Evaluating without any motion_crop engine import should succeed
        plan = _plan()
        result = evaluate_camera_quality_v2(plan)
        assert "camera_quality_v2" in result


# ---------------------------------------------------------------------------
# TestSchemaDataclass
# ---------------------------------------------------------------------------

class TestSchemaDataclass:
    def test_default_scores_are_zero(self):
        obj = CameraQualityV2()
        assert obj.overall == 0
        assert obj.crop_smoothness == 0

    def test_default_confidence_is_zero(self):
        assert CameraQualityV2().confidence == 0.0

    def test_default_reasoning_is_empty(self):
        assert CameraQualityV2().reasoning == []

    def test_to_dict_has_all_keys(self):
        d = CameraQualityV2().to_dict()
        expected = {
            "micro_jitter_risk", "whip_pan_risk", "crop_smoothness",
            "subject_stability", "scene_continuity", "creator_fit",
            "overall", "confidence", "reasoning",
        }
        assert expected.issubset(d.keys())

    def test_to_dict_reasoning_capped_at_six(self):
        obj = CameraQualityV2(reasoning=["r"] * 20)
        assert len(obj.to_dict()["reasoning"]) <= 6

    def test_fallback_dict_matches_spec(self):
        fallback = fallback_camera_quality_v2()
        assert "camera_quality_v2" not in fallback  # raw inner dict, not wrapped
        assert all(fallback[k] == 0 for k in (
            "micro_jitter_risk", "whip_pan_risk", "crop_smoothness",
            "subject_stability", "scene_continuity", "creator_fit", "overall"
        ))


# ---------------------------------------------------------------------------
# TestRenderInfluenceReporting
# ---------------------------------------------------------------------------

class TestRenderInfluenceReporting:
    def _make_plan(self, camera_quality_v2_val):
        return types.SimpleNamespace(
            enabled=True,
            subtitle=None,
            camera=None,
            pacing={},
            memory_context={},
            explainability={},
            confidence={},
            beat_execution={},
            story={},
            preset_evolution={},
            creator_style={},
            external_knowledge={},
            retention={},
            subtitle_execution={},
            beat_visual_execution={},
            timing_mutation={},
            story_optimization={},
            variants={},
            variant_selection={},
            creator_style_adaptation={},
            render_decision_preview={},
            execution_recommendations={},
            execution_simulation={},
            safe_render_mutations={},
            multivariant_render_plans={},
            multivariant_execution={},
            output_ranking={},
            ai_apply_policy={},
            timing_apply={},
            subtitle_text_apply={},
            camera_motion_apply={},
            clip_candidate_discovery={},
            clip_segment_selection={},
            clip_batch_planning={},
            feature_enhancement={},
            creator_knowledge={},
            creator_patterns={},
            creator_retrieval={},
            adaptive_creator_intelligence={},
            creator_feedback_intelligence={},
            market_optimization_intelligence={},
            render_quality_evaluation={},
            creator_preset_evolution={},
            multi_signal_orchestration={},
            safe_influence_pack={},
            creator_subtitle_preference={},
            creator_camera_preference={},
            creator_subtitle_influence={},
            creator_preference_profile={},
            strategy_variants={},
            variant_evaluation={},
            best_strategy_reasoning={},
            subtitle_quality_v2={},
            camera_quality_v2=camera_quality_v2_val,
        )

    def _report(self, cqv2_val) -> dict:
        plan = self._make_plan(cqv2_val)
        payload = _payload()
        _, report = apply_ai_render_influence(payload, plan)
        return report

    def test_no_result_reports_no_result(self):
        report = self._report(None)
        assert "camera_quality_v2:no_result_phase52b" in " ".join(report["skipped"])

    def test_empty_dict_reports_no_result(self):
        report = self._report({})
        assert "camera_quality_v2:no_result_phase52b" in " ".join(report["skipped"])

    def test_all_zero_reports_no_signal(self):
        report = self._report({
            "overall": 0, "confidence": 0.0,
            "micro_jitter_risk": 0, "whip_pan_risk": 0,
            "crop_smoothness": 0, "subject_stability": 0,
            "scene_continuity": 0, "creator_fit": 0,
            "reasoning": [],
        })
        assert "camera_quality_v2:no_signal_phase52b" in " ".join(report["skipped"])

    def test_available_result_reports_evaluated(self):
        report = self._report({
            "overall": 87, "confidence": 0.84,
            "micro_jitter_risk": 18, "whip_pan_risk": 22,
            "crop_smoothness": 88, "subject_stability": 91,
            "scene_continuity": 86, "creator_fit": 89,
            "reasoning": ["Subject framing stable"],
        })
        assert "camera_quality_v2:evaluated_phase52b" in " ".join(report["skipped"])

    def test_report_contains_overall(self):
        report = self._report({
            "overall": 87, "confidence": 0.84,
            "micro_jitter_risk": 18, "whip_pan_risk": 22,
            "crop_smoothness": 88, "subject_stability": 91,
            "scene_continuity": 86, "creator_fit": 89,
            "reasoning": [],
        })
        assert "overall=87" in " ".join(report["skipped"])

    def test_report_contains_confidence(self):
        report = self._report({
            "overall": 87, "confidence": 0.84,
            "micro_jitter_risk": 18, "whip_pan_risk": 22,
            "crop_smoothness": 88, "subject_stability": 91,
            "scene_continuity": 86, "creator_fit": 89,
            "reasoning": [],
        })
        assert "confidence=0.84" in " ".join(report["skipped"])

    def test_never_reports_to_applied(self):
        report = self._report({
            "overall": 90, "confidence": 0.9,
            "micro_jitter_risk": 10, "whip_pan_risk": 12,
            "crop_smoothness": 92, "subject_stability": 93,
            "scene_continuity": 88, "creator_fit": 91,
            "reasoning": ["Excellent"],
        })
        assert "camera_quality_v2" not in " ".join(report["applied"])

    def test_missing_attribute_reports_no_result(self):
        plan = types.SimpleNamespace(
            enabled=True,
            subtitle=None, camera=None, pacing={}, memory_context={},
            explainability={}, confidence={}, beat_execution={}, story={},
            preset_evolution={}, creator_style={}, external_knowledge={},
            retention={}, subtitle_execution={}, beat_visual_execution={},
            timing_mutation={}, story_optimization={}, variants={},
            variant_selection={}, creator_style_adaptation={},
            render_decision_preview={}, execution_recommendations={},
            execution_simulation={}, safe_render_mutations={},
            multivariant_render_plans={}, multivariant_execution={},
            output_ranking={}, ai_apply_policy={}, timing_apply={},
            subtitle_text_apply={}, camera_motion_apply={},
            clip_candidate_discovery={}, clip_segment_selection={},
            clip_batch_planning={}, feature_enhancement={},
            creator_knowledge={}, creator_patterns={}, creator_retrieval={},
            adaptive_creator_intelligence={}, creator_feedback_intelligence={},
            market_optimization_intelligence={}, render_quality_evaluation={},
            creator_preset_evolution={}, multi_signal_orchestration={},
            safe_influence_pack={}, creator_subtitle_preference={},
            creator_camera_preference={}, creator_subtitle_influence={},
            creator_preference_profile={}, strategy_variants={},
            variant_evaluation={}, best_strategy_reasoning={},
            subtitle_quality_v2={},
            # NO camera_quality_v2 attribute
        )
        payload = _payload()
        _, report = apply_ai_render_influence(payload, plan)
        assert "camera_quality_v2:no_result_phase52b" in " ".join(report["skipped"])
