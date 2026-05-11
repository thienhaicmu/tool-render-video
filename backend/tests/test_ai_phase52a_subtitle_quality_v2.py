"""
test_ai_phase52a_subtitle_quality_v2.py — Phase 52A Subtitle Quality Intelligence v2 tests.

Tests:
  - Full subtitle quality v2 evaluation
  - Missing metadata fallback
  - Deterministic scoring
  - Score clamping 0–100
  - Confidence clamping 0–1
  - Risk score handling
  - Creator fit scoring
  - No crash on empty input
  - No unsafe/internal fields exposed
  - Render influence reporting
"""
from __future__ import annotations

import types
from typing import Any

import pytest

from app.ai.subtitle_quality.subtitle_quality_evaluator import evaluate_subtitle_quality_v2
from app.ai.subtitle_quality.subtitle_quality_schema import (
    SubtitleQualityV2,
    SCORE_WEIGHTS,
    fallback_subtitle_quality_v2,
)
from app.ai.subtitle_quality.subtitle_quality_scorer import (
    score_mobile_readability,
    score_subtitle_balance,
    score_keyword_emphasis_quality,
    score_safe_zone_fit,
    score_creator_fit,
    score_overload_risk,
    score_fatigue_risk,
    compute_confidence,
)
from app.ai.director.render_influence import apply_ai_render_influence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan(**kwargs) -> Any:
    """Build a minimal fake AIEditPlan namespace for testing."""
    ns = types.SimpleNamespace(
        subtitle_execution={},
        subtitle_text_apply={},
        creator_subtitle_preference={},
        creator_subtitle_influence={},
        creator_preference_profile={},
        market_optimization_intelligence={},
        creator_preset_evolution={},
        pacing={},
        subtitle=None,
        # Phase 51 fields (not consumed by 52A, but needed to avoid AttributeError)
        strategy_variants={},
        variant_evaluation={},
        best_strategy_reasoning={},
        subtitle_quality_v2={},
    )
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _full_plan() -> Any:
    """Build a rich plan with all subtitle quality signals populated."""
    return _plan(
        subtitle_execution={
            "available": True,
            "global_hint": {
                "emphasis_strength": 0.45,
                "density_mode": "compact",
                "beat_sync_strength": 0.3,
                "keyword_focus": ["epic", "win", "moment", "live"],
                "warnings": [],
            },
            "regions": [{"start": 0, "end": 5}] * 8,
            "warnings": [],
        },
        subtitle_text_apply={"available": True, "enabled": True, "warnings": []},
        creator_subtitle_preference={
            "available": True,
            "subtitle_preference": {
                "style": "viral_bold",
                "density": "medium",
                "keyword_emphasis": "moderate",
                "confidence": 0.78,
                "signals": ["signal_a", "signal_b"],
            },
        },
        creator_subtitle_influence={
            "available": True,
            "confidence_tier": "high",
            "preset_bias": "viral_bold",
            "preset_bias_strength": 0.35,
            "density_nudge": "none",
            "emphasis_delta": 0.05,
            "motion_style_bias": "static",
            "mobile_readability_nudge": 0.3,
        },
        creator_preference_profile={
            "available": True,
            "confidence": 0.75,
            "subtitle": {"style": "viral_bold", "confidence": 0.72},
            "camera": {"motion_style": "static_center"},
            "conflicts_resolved": [],
            "market_alignment": {"market_fit": "tiktok"},
        },
        market_optimization_intelligence={
            "enabled": True,
            "available": True,
            "target_market": "tiktok",
            "subtitle_market_bias": {
                "weight": 0.6,
                "preferred_style": "viral_bold",
            },
        },
        creator_preset_evolution={
            "available": True,
            "evolved_presets": [{"id": "p1"}],
        },
        pacing={
            "beat_available": True,
            "bpm": 120.0,
            "energy_level": 0.65,
            "emotion": "hype",
        },
    )


def _payload():
    return types.SimpleNamespace(add_subtitle=True, motion_aware_crop=False)


# ---------------------------------------------------------------------------
# TestFullEvaluation
# ---------------------------------------------------------------------------

class TestFullEvaluation:
    def test_returns_dict_with_subtitle_quality_v2_key(self):
        result = evaluate_subtitle_quality_v2(_full_plan())
        assert "subtitle_quality_v2" in result

    def test_all_required_keys_present(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        required = {
            "mobile_readability", "subtitle_balance", "keyword_emphasis_quality",
            "safe_zone_fit", "creator_fit", "overload_risk", "fatigue_risk",
            "overall", "confidence", "reasoning",
        }
        assert required.issubset(sqv2.keys())

    def test_positive_scores_are_integers(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        for key in ("mobile_readability", "subtitle_balance", "keyword_emphasis_quality",
                    "safe_zone_fit", "creator_fit", "overall"):
            assert isinstance(sqv2[key], int), f"{key} should be int"

    def test_risk_scores_are_integers(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        for key in ("overload_risk", "fatigue_risk"):
            assert isinstance(sqv2[key], int), f"{key} should be int"

    def test_confidence_is_float(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        assert isinstance(sqv2["confidence"], float)

    def test_reasoning_is_list(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        assert isinstance(sqv2["reasoning"], list)

    def test_full_plan_overall_above_zero(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        assert sqv2["overall"] > 0

    def test_full_plan_confidence_above_zero(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        assert sqv2["confidence"] > 0.0

    def test_full_plan_reasoning_not_empty(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        assert len(sqv2["reasoning"]) > 0

    def test_no_extra_unexpected_keys(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        expected = {
            "mobile_readability", "subtitle_balance", "keyword_emphasis_quality",
            "safe_zone_fit", "creator_fit", "overload_risk", "fatigue_risk",
            "overall", "confidence", "reasoning",
        }
        assert set(sqv2.keys()) == expected


# ---------------------------------------------------------------------------
# TestFallbackBehavior
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    def test_none_input_returns_fallback(self):
        result = evaluate_subtitle_quality_v2(None)
        sqv2 = result["subtitle_quality_v2"]
        assert sqv2["overall"] == 0
        assert sqv2["confidence"] == 0.0
        assert sqv2["reasoning"] == []

    def test_empty_namespace_does_not_crash(self):
        result = evaluate_subtitle_quality_v2(types.SimpleNamespace())
        assert "subtitle_quality_v2" in result

    def test_garbage_string_does_not_crash(self):
        result = evaluate_subtitle_quality_v2("not_a_plan")
        assert "subtitle_quality_v2" in result

    def test_garbage_integer_does_not_crash(self):
        result = evaluate_subtitle_quality_v2(42)
        assert "subtitle_quality_v2" in result

    def test_fallback_all_scores_zero(self):
        fallback = fallback_subtitle_quality_v2()
        for key in ("mobile_readability", "subtitle_balance", "keyword_emphasis_quality",
                    "safe_zone_fit", "creator_fit", "overload_risk", "fatigue_risk", "overall"):
            assert fallback[key] == 0

    def test_fallback_confidence_zero(self):
        assert fallback_subtitle_quality_v2()["confidence"] == 0.0

    def test_fallback_reasoning_empty(self):
        assert fallback_subtitle_quality_v2()["reasoning"] == []

    def test_missing_subtitle_execution_does_not_crash(self):
        plan = _plan(subtitle_execution=None)
        result = evaluate_subtitle_quality_v2(plan)
        assert "subtitle_quality_v2" in result

    def test_missing_creator_profile_does_not_crash(self):
        plan = _plan(creator_preference_profile=None, creator_subtitle_preference=None)
        result = evaluate_subtitle_quality_v2(plan)
        assert "subtitle_quality_v2" in result

    def test_missing_market_does_not_crash(self):
        plan = _plan(market_optimization_intelligence=None)
        result = evaluate_subtitle_quality_v2(plan)
        assert "subtitle_quality_v2" in result


# ---------------------------------------------------------------------------
# TestScoreClamping
# ---------------------------------------------------------------------------

class TestScoreClamping:
    def test_mobile_readability_clamped_0_100(self):
        for _ in range(3):
            v = score_mobile_readability(_full_plan())
            assert 0 <= v <= 100

    def test_subtitle_balance_clamped_0_100(self):
        v = score_subtitle_balance(_full_plan())
        assert 0 <= v <= 100

    def test_keyword_emphasis_quality_clamped_0_100(self):
        v = score_keyword_emphasis_quality(_full_plan())
        assert 0 <= v <= 100

    def test_safe_zone_fit_clamped_0_100(self):
        v = score_safe_zone_fit(_full_plan())
        assert 0 <= v <= 100

    def test_creator_fit_clamped_0_100(self):
        v = score_creator_fit(_full_plan())
        assert 0 <= v <= 100

    def test_overload_risk_clamped_0_100(self):
        v = score_overload_risk(_full_plan())
        assert 0 <= v <= 100

    def test_fatigue_risk_clamped_0_100(self):
        v = score_fatigue_risk(_full_plan())
        assert 0 <= v <= 100

    def test_overall_clamped_0_100(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        assert 0 <= sqv2["overall"] <= 100

    def test_schema_to_dict_clamps_above_100(self):
        obj = SubtitleQualityV2(mobile_readability=999, overall=200)
        d = obj.to_dict()
        assert d["mobile_readability"] == 100
        assert d["overall"] == 100

    def test_schema_to_dict_clamps_below_0(self):
        obj = SubtitleQualityV2(mobile_readability=-50, overall=-10)
        d = obj.to_dict()
        assert d["mobile_readability"] == 0
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
        obj = SubtitleQualityV2(confidence=5.0)
        assert obj.to_dict()["confidence"] == 1.0

    def test_schema_clamps_confidence_below_0(self):
        obj = SubtitleQualityV2(confidence=-1.0)
        assert obj.to_dict()["confidence"] == 0.0

    def test_full_plan_confidence_in_range(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        assert 0.0 <= sqv2["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_overall(self):
        plan = _full_plan()
        r1 = evaluate_subtitle_quality_v2(plan)["subtitle_quality_v2"]["overall"]
        r2 = evaluate_subtitle_quality_v2(plan)["subtitle_quality_v2"]["overall"]
        assert r1 == r2

    def test_same_input_same_mobile_readability(self):
        plan = _full_plan()
        assert score_mobile_readability(plan) == score_mobile_readability(plan)

    def test_same_input_same_creator_fit(self):
        plan = _full_plan()
        assert score_creator_fit(plan) == score_creator_fit(plan)

    def test_same_input_same_confidence(self):
        plan = _full_plan()
        assert compute_confidence(plan) == compute_confidence(plan)

    def test_same_input_same_reasoning(self):
        plan = _full_plan()
        r1 = evaluate_subtitle_quality_v2(plan)["subtitle_quality_v2"]["reasoning"]
        r2 = evaluate_subtitle_quality_v2(plan)["subtitle_quality_v2"]["reasoning"]
        assert r1 == r2


# ---------------------------------------------------------------------------
# TestRiskScoreHandling
# ---------------------------------------------------------------------------

class TestRiskScoreHandling:
    def test_overload_risk_zero_on_compact_light(self):
        plan = _plan(
            subtitle_execution={
                "global_hint": {
                    "density_mode": "compact",
                    "emphasis_strength": 0.1,
                    "keyword_focus": ["one"],
                },
                "regions": [{"s": 0}] * 3,
                "warnings": [],
            }
        )
        risk = score_overload_risk(plan)
        assert risk < 20  # compact + low emphasis → low overload

    def test_overload_risk_high_on_expressive_high_emphasis(self):
        plan = _plan(
            subtitle_execution={
                "global_hint": {
                    "density_mode": "expressive",
                    "emphasis_strength": 0.9,
                    "keyword_focus": ["a"] * 10,
                },
                "regions": [{"s": 0}] * 20,
                "warnings": [],
                "execution_metadata": {},
            }
        )
        risk = score_overload_risk(plan)
        assert risk >= 40  # expressive + high emphasis + many keywords

    def test_fatigue_risk_high_on_fast_bpm(self):
        plan = _plan(
            pacing={"bpm": 200.0, "energy_level": 0.9},
            subtitle_execution={
                "global_hint": {
                    "density_mode": "expressive",
                    "emphasis_strength": 0.8,
                    "beat_sync_strength": 0.8,
                    "keyword_focus": [],
                },
                "regions": [{"s": 0}] * 20,
                "warnings": [],
            },
        )
        risk = score_fatigue_risk(plan)
        assert risk >= 30

    def test_fatigue_risk_low_on_slow_bpm(self):
        plan = _plan(
            pacing={"bpm": 90.0, "energy_level": 0.3},
            subtitle_execution={
                "global_hint": {
                    "density_mode": "compact",
                    "emphasis_strength": 0.2,
                    "beat_sync_strength": 0.1,
                    "keyword_focus": [],
                },
                "regions": [{"s": 0}] * 5,
                "warnings": [],
            },
        )
        risk = score_fatigue_risk(plan)
        assert risk < 20

    def test_high_risk_reduces_overall(self):
        low_risk_plan = _full_plan()
        low_risk_plan.subtitle_execution["global_hint"]["density_mode"] = "compact"
        low_risk_plan.subtitle_execution["global_hint"]["emphasis_strength"] = 0.2

        high_risk_plan = _full_plan()
        high_risk_plan.subtitle_execution["global_hint"]["density_mode"] = "expressive"
        high_risk_plan.subtitle_execution["global_hint"]["emphasis_strength"] = 0.9

        low_overall  = evaluate_subtitle_quality_v2(low_risk_plan)["subtitle_quality_v2"]["overall"]
        high_overall = evaluate_subtitle_quality_v2(high_risk_plan)["subtitle_quality_v2"]["overall"]
        # High risk should not be higher than low risk
        assert high_overall <= low_overall + 5  # small tolerance for other signal effects

    def test_overload_flag_in_execution_increases_risk(self):
        plan_with_overload = _plan(
            subtitle_execution={
                "global_hint": {"density_mode": "normal", "emphasis_strength": 0.3, "keyword_focus": []},
                "regions": [],
                "warnings": ["subtitle_overload"],
                "execution_metadata": {},
            }
        )
        plan_no_overload = _plan(
            subtitle_execution={
                "global_hint": {"density_mode": "normal", "emphasis_strength": 0.3, "keyword_focus": []},
                "regions": [],
                "warnings": [],
                "execution_metadata": {},
            }
        )
        assert score_overload_risk(plan_with_overload) > score_overload_risk(plan_no_overload)


# ---------------------------------------------------------------------------
# TestMobileReadability
# ---------------------------------------------------------------------------

class TestMobileReadability:
    def test_compact_density_better_than_expressive(self):
        compact = _plan(subtitle_execution={
            "global_hint": {"density_mode": "compact", "emphasis_strength": 0.3, "keyword_focus": []},
            "regions": [], "warnings": [],
        })
        expressive = _plan(subtitle_execution={
            "global_hint": {"density_mode": "expressive", "emphasis_strength": 0.3, "keyword_focus": []},
            "regions": [], "warnings": [],
        })
        assert score_mobile_readability(compact) >= score_mobile_readability(expressive)

    def test_subtitle_text_apply_boosts_mobile(self):
        no_sta = _plan(
            subtitle_execution={"global_hint": {"density_mode": "normal", "emphasis_strength": 0.0, "keyword_focus": []}, "regions": [], "warnings": []},
            subtitle_text_apply={},
        )
        with_sta = _plan(
            subtitle_execution={"global_hint": {"density_mode": "normal", "emphasis_strength": 0.0, "keyword_focus": []}, "regions": [], "warnings": []},
            subtitle_text_apply={"available": True, "enabled": True, "warnings": []},
        )
        assert score_mobile_readability(with_sta) >= score_mobile_readability(no_sta)

    def test_positive_mobile_nudge_improves_score(self):
        no_nudge = _plan(
            subtitle_execution={"global_hint": {"density_mode": "normal", "emphasis_strength": 0.0, "keyword_focus": []}, "regions": [], "warnings": []},
            creator_subtitle_influence={},
        )
        with_nudge = _plan(
            subtitle_execution={"global_hint": {"density_mode": "normal", "emphasis_strength": 0.0, "keyword_focus": []}, "regions": [], "warnings": []},
            creator_subtitle_influence={"mobile_readability_nudge": 0.5},
        )
        assert score_mobile_readability(with_nudge) > score_mobile_readability(no_nudge)

    def test_none_plan_returns_baseline(self):
        v = score_mobile_readability(None)
        assert 0 <= v <= 100


# ---------------------------------------------------------------------------
# TestCreatorFitScoring
# ---------------------------------------------------------------------------

class TestCreatorFitScoring:
    def test_no_creator_data_returns_neutral(self):
        plan = _plan(creator_subtitle_preference={"available": False})
        v = score_creator_fit(plan)
        assert 0 <= v <= 100

    def test_high_confidence_preference_boosts_creator_fit(self):
        high_conf = _plan(
            creator_subtitle_preference={
                "available": True,
                "subtitle_preference": {"style": "viral_bold", "confidence": 0.85, "signals": []},
            },
            creator_subtitle_influence={"confidence_tier": "high", "preset_bias_strength": 0.3},
            creator_preference_profile={"available": True, "subtitle": {"style": "viral_bold", "confidence": 0.8}, "confidence": 0.8},
        )
        low_conf = _plan(
            creator_subtitle_preference={
                "available": True,
                "subtitle_preference": {"style": "viral_bold", "confidence": 0.2, "signals": []},
            },
            creator_subtitle_influence={"confidence_tier": "low", "preset_bias_strength": 0.1},
            creator_preference_profile={"available": True, "subtitle": {"style": "unknown", "confidence": 0.1}, "confidence": 0.1},
        )
        assert score_creator_fit(high_conf) > score_creator_fit(low_conf)

    def test_style_agreement_50a_50d_boosts_score(self):
        agree = _plan(
            creator_subtitle_preference={
                "available": True,
                "subtitle_preference": {"style": "viral_bold", "confidence": 0.7, "signals": []},
            },
            creator_preference_profile={
                "available": True,
                "subtitle": {"style": "viral_bold", "confidence": 0.7},
                "confidence": 0.7,
            },
            creator_subtitle_influence={},
        )
        disagree = _plan(
            creator_subtitle_preference={
                "available": True,
                "subtitle_preference": {"style": "viral_bold", "confidence": 0.7, "signals": []},
            },
            creator_preference_profile={
                "available": True,
                "subtitle": {"style": "clean_pro", "confidence": 0.7},
                "confidence": 0.7,
            },
            creator_subtitle_influence={},
        )
        assert score_creator_fit(agree) >= score_creator_fit(disagree)

    def test_creator_fit_clamped_0_100(self):
        v = score_creator_fit(_full_plan())
        assert 0 <= v <= 100


# ---------------------------------------------------------------------------
# TestScoringWeights
# ---------------------------------------------------------------------------

class TestScoringWeights:
    def test_weights_sum_to_one(self):
        total = sum(SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_all_dimensions_have_weights(self):
        for dim in ("mobile_readability", "subtitle_balance", "keyword_emphasis_quality",
                    "safe_zone_fit", "creator_fit"):
            assert dim in SCORE_WEIGHTS

    def test_mobile_readability_highest_weight(self):
        assert SCORE_WEIGHTS["mobile_readability"] >= max(
            SCORE_WEIGHTS["subtitle_balance"],
            SCORE_WEIGHTS["keyword_emphasis_quality"],
        )


# ---------------------------------------------------------------------------
# TestNoUnsafeFields
# ---------------------------------------------------------------------------

class TestNoUnsafeFields:
    _FORBIDDEN = {"Traceback", "Exception", "Error", "__class__", "__dict__",
                  "stack", "exec", "eval", "compile"}

    def _check_no_forbidden(self, text: str) -> None:
        text_lower = text.lower()
        for f in self._FORBIDDEN:
            assert f.lower() not in text_lower, f"Forbidden text found: {f!r}"

    def test_no_debug_text_in_reasoning(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        for line in sqv2["reasoning"]:
            self._check_no_forbidden(line)

    def test_no_forbidden_keys_in_result(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        forbidden_keys = {"traceback", "exception", "class", "__dict__", "exec"}
        for k in sqv2.keys():
            assert k not in forbidden_keys

    def test_no_forbidden_keys_in_fallback(self):
        fallback = fallback_subtitle_quality_v2()
        forbidden_keys = {"traceback", "exception", "class", "__dict__"}
        for k in fallback.keys():
            assert k not in forbidden_keys

    def test_no_render_pipeline_fields_in_result(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        render_fields = {"ffmpeg", "playback_speed", "subtitle_timing", "ass_style",
                         "executor", "rerender", "segment_start", "segment_end"}
        for k in sqv2.keys():
            assert k not in render_fields

    def test_reasoning_max_six_items(self):
        sqv2 = evaluate_subtitle_quality_v2(_full_plan())["subtitle_quality_v2"]
        assert len(sqv2["reasoning"]) <= 6


# ---------------------------------------------------------------------------
# TestSchemaDataclass
# ---------------------------------------------------------------------------

class TestSchemaDataclass:
    def test_default_scores_are_zero(self):
        obj = SubtitleQualityV2()
        assert obj.overall == 0
        assert obj.mobile_readability == 0

    def test_default_confidence_is_zero(self):
        assert SubtitleQualityV2().confidence == 0.0

    def test_default_reasoning_is_empty(self):
        assert SubtitleQualityV2().reasoning == []

    def test_to_dict_has_all_keys(self):
        d = SubtitleQualityV2().to_dict()
        expected = {
            "mobile_readability", "subtitle_balance", "keyword_emphasis_quality",
            "safe_zone_fit", "creator_fit", "overload_risk", "fatigue_risk",
            "overall", "confidence", "reasoning",
        }
        assert expected.issubset(d.keys())

    def test_to_dict_reasoning_capped_at_six(self):
        obj = SubtitleQualityV2(reasoning=["r"] * 20)
        assert len(obj.to_dict()["reasoning"]) <= 6

    def test_fallback_dict_matches_spec(self):
        fallback = fallback_subtitle_quality_v2()
        assert "subtitle_quality_v2" not in fallback  # raw inner dict, not wrapped
        assert all(fallback[k] == 0 for k in (
            "mobile_readability", "subtitle_balance", "keyword_emphasis_quality",
            "safe_zone_fit", "creator_fit", "overload_risk", "fatigue_risk", "overall"
        ))


# ---------------------------------------------------------------------------
# TestRenderInfluenceReporting
# ---------------------------------------------------------------------------

class TestRenderInfluenceReporting:
    def _apply(self, plan_kwargs: dict) -> dict:
        plan = types.SimpleNamespace(
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
        )
        for k, v in plan_kwargs.items():
            setattr(plan, k, v)
        payload = _payload()
        _, report = apply_ai_render_influence(payload, plan)
        return report

    def test_no_result_reports_no_result(self):
        report = self._apply({"subtitle_quality_v2": None})
        skipped_str = " ".join(report["skipped"])
        assert "subtitle_quality_v2:no_result_phase52a" in skipped_str

    def test_empty_dict_reports_no_result(self):
        report = self._apply({"subtitle_quality_v2": {}})
        skipped_str = " ".join(report["skipped"])
        assert "subtitle_quality_v2:no_result_phase52a" in skipped_str

    def test_all_zero_reports_no_signal(self):
        report = self._apply({"subtitle_quality_v2": {
            "overall": 0, "confidence": 0.0,
            "mobile_readability": 0, "subtitle_balance": 0,
            "keyword_emphasis_quality": 0, "safe_zone_fit": 0,
            "creator_fit": 0, "overload_risk": 0, "fatigue_risk": 0,
            "reasoning": [],
        }})
        skipped_str = " ".join(report["skipped"])
        assert "subtitle_quality_v2:no_signal_phase52a" in skipped_str

    def test_available_result_reports_evaluated(self):
        report = self._apply({"subtitle_quality_v2": {
            "overall": 82, "confidence": 0.78,
            "mobile_readability": 85, "subtitle_balance": 78,
            "keyword_emphasis_quality": 80, "safe_zone_fit": 88,
            "creator_fit": 82, "overload_risk": 10, "fatigue_risk": 15,
            "reasoning": ["Good mobile readability"],
        }})
        skipped_str = " ".join(report["skipped"])
        assert "subtitle_quality_v2:evaluated_phase52a" in skipped_str

    def test_report_contains_overall(self):
        report = self._apply({"subtitle_quality_v2": {
            "overall": 75, "confidence": 0.7,
            "mobile_readability": 70, "subtitle_balance": 72,
            "keyword_emphasis_quality": 65, "safe_zone_fit": 80,
            "creator_fit": 75, "overload_risk": 20, "fatigue_risk": 18,
            "reasoning": [],
        }})
        skipped_str = " ".join(report["skipped"])
        assert "overall=75" in skipped_str

    def test_report_contains_confidence(self):
        report = self._apply({"subtitle_quality_v2": {
            "overall": 75, "confidence": 0.68,
            "mobile_readability": 70, "subtitle_balance": 72,
            "keyword_emphasis_quality": 65, "safe_zone_fit": 80,
            "creator_fit": 75, "overload_risk": 15, "fatigue_risk": 12,
            "reasoning": [],
        }})
        skipped_str = " ".join(report["skipped"])
        assert "confidence=0.68" in skipped_str

    def test_never_reports_to_applied(self):
        report = self._apply({"subtitle_quality_v2": {
            "overall": 90, "confidence": 0.9,
            "mobile_readability": 92, "subtitle_balance": 88,
            "keyword_emphasis_quality": 85, "safe_zone_fit": 93,
            "creator_fit": 90, "overload_risk": 5, "fatigue_risk": 8,
            "reasoning": ["Excellent"],
        }})
        applied_str = " ".join(report["applied"])
        assert "subtitle_quality_v2" not in applied_str

    def test_missing_attribute_reports_no_result(self):
        plan = types.SimpleNamespace(
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
            # NO subtitle_quality_v2 attribute
        )
        payload = _payload()
        _, report = apply_ai_render_influence(payload, plan)
        skipped_str = " ".join(report["skipped"])
        assert "subtitle_quality_v2:no_result_phase52a" in skipped_str
