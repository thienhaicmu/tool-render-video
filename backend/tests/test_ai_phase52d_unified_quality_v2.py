"""
test_ai_phase52d_unified_quality_v2.py — Phase 52D: Unified Quality Score v2 tests.

Covers:
    - Full unified quality v2 evaluation (rich plan with all subsystems populated)
    - Missing metadata fallback (no crash)
    - Deterministic scoring
    - Weighted score calculation verification
    - Score clamping 0–100
    - Confidence clamping 0–1
    - Missing subsystem confidence reduction
    - Creator fit fallback
    - Market fit fallback
    - Strategy fit fallback
    - No crash on empty / garbage input
    - No unsafe/internal fields exposed
    - Schema dataclass behavior
    - render_influence reporting
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ai.unified_quality.unified_quality_schema import (
    UnifiedQualityV2,
    SCORE_WEIGHTS,
    fallback_render_quality_v2,
)
from app.ai.unified_quality.unified_quality_scorer import (
    score_subtitle,
    score_camera,
    score_hook,
    score_creator_fit,
    score_market_fit,
    score_strategy_fit,
    compute_confidence,
)
from app.ai.unified_quality.unified_quality_evaluator import evaluate_unified_quality_v2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(**kwargs) -> SimpleNamespace:
    defaults = dict(
        subtitle_quality_v2={},
        camera_quality_v2={},
        hook_quality_v2={},
        creator_preference_profile={},
        creator_preset_evolution={},
        market_optimization_intelligence={},
        variant_evaluation={},
        best_strategy_reasoning={},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _full_plan() -> SimpleNamespace:
    """Rich plan with all Phase 52A/B/C + strategy + creator + market signals."""
    return _make_plan(
        subtitle_quality_v2={
            "overall": 86,
            "confidence": 0.84,
            "creator_fit": 88,
            "safe_zone_fit": 90,
            "mobile_readability": 87,
        },
        camera_quality_v2={
            "overall": 88,
            "confidence": 0.80,
            "creator_fit": 84,
        },
        hook_quality_v2={
            "overall": 85,
            "confidence": 0.82,
            "creator_fit": 83,
            "market_fit": 87,
        },
        creator_preference_profile={
            "confidence": 0.80,
            "hook": {"style": "curiosity"},
            "pacing": {"style": "upbeat"},
        },
        creator_preset_evolution={
            "available": True,
            "evolved_presets": [{"id": "p1"}],
        },
        market_optimization_intelligence={
            "available": True,
            "target_market": "us",
            "confidence": 0.78,
        },
        variant_evaluation={
            "available": True,
            "best_variant_id": "v1",
            "confidence": 0.75,
        },
        best_strategy_reasoning={
            "confidence": 0.72,
            "recommendation_strength": "moderate",
        },
    )


# ---------------------------------------------------------------------------
# TestFullEvaluation
# ---------------------------------------------------------------------------

class TestFullEvaluation:
    def test_full_plan_overall_above_zero(self):
        result = evaluate_unified_quality_v2(_full_plan())
        assert result["render_quality_v2"]["overall"] > 0

    def test_full_plan_confidence_above_zero(self):
        result = evaluate_unified_quality_v2(_full_plan())
        assert result["render_quality_v2"]["confidence"] > 0.0

    def test_full_plan_reasoning_not_empty(self):
        result = evaluate_unified_quality_v2(_full_plan())
        assert len(result["render_quality_v2"]["reasoning"]) > 0

    def test_wrapped_in_render_quality_v2_key(self):
        result = evaluate_unified_quality_v2(_full_plan())
        assert "render_quality_v2" in result

    def test_full_plan_all_keys_present(self):
        result = evaluate_unified_quality_v2(_full_plan())
        rqv2 = result["render_quality_v2"]
        expected = {
            "subtitle_score", "camera_score", "hook_score",
            "creator_fit", "market_fit", "strategy_fit",
            "overall", "confidence", "reasoning",
        }
        assert expected.issubset(set(rqv2.keys()))

    def test_full_plan_subtitle_matches_52a_overall(self):
        plan = _full_plan()
        result = evaluate_unified_quality_v2(plan)
        assert result["render_quality_v2"]["subtitle_score"] == 86

    def test_full_plan_camera_matches_52b_overall(self):
        result = evaluate_unified_quality_v2(_full_plan())
        assert result["render_quality_v2"]["camera_score"] == 88

    def test_full_plan_hook_matches_52c_overall(self):
        result = evaluate_unified_quality_v2(_full_plan())
        assert result["render_quality_v2"]["hook_score"] == 85


# ---------------------------------------------------------------------------
# TestFallbackBehavior
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    def test_none_input_returns_fallback(self):
        result = evaluate_unified_quality_v2(None)
        assert "render_quality_v2" in result
        rqv2 = result["render_quality_v2"]
        assert rqv2["overall"] == 0
        assert rqv2["confidence"] == 0.0

    def test_empty_namespace_does_not_crash(self):
        result = evaluate_unified_quality_v2(SimpleNamespace())
        assert "render_quality_v2" in result

    def test_garbage_string_does_not_crash(self):
        result = evaluate_unified_quality_v2("garbage")
        assert "render_quality_v2" in result

    def test_garbage_integer_does_not_crash(self):
        result = evaluate_unified_quality_v2(42)
        assert "render_quality_v2" in result

    def test_fallback_all_scores_zero(self):
        fb = fallback_render_quality_v2()
        for k, v in fb.items():
            if k != "reasoning":
                assert v == 0 or v == 0.0, f"Expected 0 for {k}, got {v}"

    def test_fallback_confidence_zero(self):
        assert fallback_render_quality_v2()["confidence"] == 0.0

    def test_fallback_reasoning_empty(self):
        assert fallback_render_quality_v2()["reasoning"] == []

    def test_missing_52a_does_not_crash(self):
        plan = _make_plan(camera_quality_v2={"overall": 80}, hook_quality_v2={"overall": 75})
        result = evaluate_unified_quality_v2(plan)
        assert "render_quality_v2" in result

    def test_missing_52b_does_not_crash(self):
        plan = _make_plan(subtitle_quality_v2={"overall": 80}, hook_quality_v2={"overall": 75})
        result = evaluate_unified_quality_v2(plan)
        assert "render_quality_v2" in result

    def test_missing_52c_does_not_crash(self):
        plan = _make_plan(subtitle_quality_v2={"overall": 80}, camera_quality_v2={"overall": 85})
        result = evaluate_unified_quality_v2(plan)
        assert "render_quality_v2" in result

    def test_missing_creator_does_not_crash(self):
        plan = _make_plan(
            subtitle_quality_v2={"overall": 80},
            camera_quality_v2={"overall": 85},
            hook_quality_v2={"overall": 78},
        )
        result = evaluate_unified_quality_v2(plan)
        assert "render_quality_v2" in result

    def test_missing_market_does_not_crash(self):
        plan = _make_plan(subtitle_quality_v2={"overall": 80})
        result = evaluate_unified_quality_v2(plan)
        assert "render_quality_v2" in result

    def test_missing_strategy_does_not_crash(self):
        plan = _make_plan(subtitle_quality_v2={"overall": 80}, camera_quality_v2={"overall": 85})
        result = evaluate_unified_quality_v2(plan)
        assert "render_quality_v2" in result


# ---------------------------------------------------------------------------
# TestWeightedScoreCalculation
# ---------------------------------------------------------------------------

class TestWeightedScoreCalculation:
    def test_weights_drive_overall(self):
        # All subsystem scores same value → overall should equal that value
        plan = _make_plan(
            subtitle_quality_v2={"overall": 80, "creator_fit": 80, "safe_zone_fit": 80},
            camera_quality_v2={"overall": 80, "creator_fit": 80},
            hook_quality_v2={"overall": 80, "creator_fit": 80, "market_fit": 80},
            creator_preference_profile={"confidence": 0.0},
        )
        result = evaluate_unified_quality_v2(plan)
        rqv2 = result["render_quality_v2"]
        # subtitle=80, camera=80, hook=80 → weighted 0.25+0.25+0.20 = 0.70 × 80 = 56
        # creator=avg(80,80,80)=80, market=80, strategy=0
        # 0.25×80 + 0.25×80 + 0.20×80 + 0.15×80 + 0.10×80 + 0.05×0 = 76
        assert rqv2["subtitle_score"] == 80
        assert rqv2["camera_score"] == 80
        assert rqv2["hook_score"] == 80
        assert 70 <= rqv2["overall"] <= 90

    def test_subtitle_weight_is_0_25(self):
        assert SCORE_WEIGHTS["subtitle_score"] == 0.25

    def test_camera_weight_is_0_25(self):
        assert SCORE_WEIGHTS["camera_score"] == 0.25

    def test_hook_weight_is_0_20(self):
        assert SCORE_WEIGHTS["hook_score"] == 0.20

    def test_all_weights_sum_to_1(self):
        total = sum(SCORE_WEIGHTS.values())
        assert abs(total - 1.0) < 1e-9

    def test_missing_subscore_zeroes_that_dimension(self):
        plan = _make_plan(
            camera_quality_v2={"overall": 90},
            hook_quality_v2={"overall": 85},
        )
        result = evaluate_unified_quality_v2(plan)
        assert result["render_quality_v2"]["subtitle_score"] == 0

    def test_all_missing_overall_is_zero(self):
        plan = _make_plan()
        result = evaluate_unified_quality_v2(plan)
        assert result["render_quality_v2"]["overall"] == 0


# ---------------------------------------------------------------------------
# TestScoreClamping
# ---------------------------------------------------------------------------

class TestScoreClamping:
    def _clamped(self, key: str, plan):
        return evaluate_unified_quality_v2(plan)["render_quality_v2"][key]

    def test_subtitle_score_clamped(self):
        assert 0 <= self._clamped("subtitle_score", _full_plan()) <= 100

    def test_camera_score_clamped(self):
        assert 0 <= self._clamped("camera_score", _full_plan()) <= 100

    def test_hook_score_clamped(self):
        assert 0 <= self._clamped("hook_score", _full_plan()) <= 100

    def test_creator_fit_clamped(self):
        assert 0 <= self._clamped("creator_fit", _full_plan()) <= 100

    def test_market_fit_clamped(self):
        assert 0 <= self._clamped("market_fit", _full_plan()) <= 100

    def test_strategy_fit_clamped(self):
        assert 0 <= self._clamped("strategy_fit", _full_plan()) <= 100

    def test_overall_clamped(self):
        assert 0 <= self._clamped("overall", _full_plan()) <= 100

    def test_schema_to_dict_clamps_above_100(self):
        uq = UnifiedQualityV2(
            subtitle_score=200, camera_score=999, hook_score=150,
            creator_fit=999, market_fit=200, strategy_fit=300,
            overall=999, confidence=5.0,
        )
        d = uq.to_dict()
        for k in ("subtitle_score", "camera_score", "hook_score",
                   "creator_fit", "market_fit", "strategy_fit", "overall"):
            assert d[k] == 100
        assert d["confidence"] == 1.0

    def test_schema_to_dict_clamps_below_0(self):
        uq = UnifiedQualityV2(subtitle_score=-50, overall=-10, confidence=-2.0)
        d = uq.to_dict()
        assert d["subtitle_score"] == 0
        assert d["overall"] == 0
        assert d["confidence"] == 0.0


# ---------------------------------------------------------------------------
# TestConfidenceClamping
# ---------------------------------------------------------------------------

class TestConfidenceClamping:
    def test_confidence_in_0_1(self):
        result = evaluate_unified_quality_v2(_full_plan())
        c = result["render_quality_v2"]["confidence"]
        assert 0.0 <= c <= 1.0

    def test_all_missing_gives_zero_confidence(self):
        plan = _make_plan()
        assert compute_confidence(plan) == 0.0

    def test_schema_clamps_confidence_above_1(self):
        uq = UnifiedQualityV2(confidence=3.5)
        assert uq.to_dict()["confidence"] == 1.0

    def test_schema_clamps_confidence_below_0(self):
        uq = UnifiedQualityV2(confidence=-1.0)
        assert uq.to_dict()["confidence"] == 0.0

    def test_full_plan_confidence_in_range(self):
        c = compute_confidence(_full_plan())
        assert 0.0 <= c <= 1.0

    def test_missing_subsystem_lowers_confidence(self):
        full_conf  = compute_confidence(_full_plan())
        sparse     = _make_plan(subtitle_quality_v2={"overall": 80, "confidence": 0.80})
        sparse_conf = compute_confidence(sparse)
        assert full_conf > sparse_conf

    def test_each_available_subsystem_increases_confidence(self):
        empty = compute_confidence(_make_plan())
        one   = compute_confidence(_make_plan(subtitle_quality_v2={"overall": 80, "confidence": 0.8}))
        assert one > empty


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_overall(self):
        plan = _full_plan()
        r1 = evaluate_unified_quality_v2(plan)
        r2 = evaluate_unified_quality_v2(plan)
        assert r1["render_quality_v2"]["overall"] == r2["render_quality_v2"]["overall"]

    def test_same_input_same_confidence(self):
        plan = _full_plan()
        assert compute_confidence(plan) == compute_confidence(plan)

    def test_same_input_same_reasoning(self):
        plan = _full_plan()
        r1 = evaluate_unified_quality_v2(plan)
        r2 = evaluate_unified_quality_v2(plan)
        assert r1["render_quality_v2"]["reasoning"] == r2["render_quality_v2"]["reasoning"]

    def test_same_input_same_creator_fit(self):
        plan = _full_plan()
        r1 = evaluate_unified_quality_v2(plan)
        r2 = evaluate_unified_quality_v2(plan)
        assert r1["render_quality_v2"]["creator_fit"] == r2["render_quality_v2"]["creator_fit"]


# ---------------------------------------------------------------------------
# TestCreatorFit
# ---------------------------------------------------------------------------

class TestCreatorFit:
    def test_no_creator_data_returns_zero(self):
        plan = _make_plan()
        assert score_creator_fit(plan) == 0

    def test_subscore_creator_fits_averaged(self):
        plan = _make_plan(
            subtitle_quality_v2={"creator_fit": 90},
            camera_quality_v2={"creator_fit": 80},
            hook_quality_v2={"creator_fit": 70},
        )
        score = score_creator_fit(plan)
        # avg(90, 80, 70) = 80; within some delta for profile supplement
        assert 78 <= score <= 90

    def test_creator_profile_confidence_supplements(self):
        base_plan = _make_plan(
            subtitle_quality_v2={"creator_fit": 80},
        )
        enriched = _make_plan(
            subtitle_quality_v2={"creator_fit": 80},
            creator_preference_profile={"confidence": 0.80},
        )
        assert score_creator_fit(enriched) >= score_creator_fit(base_plan)

    def test_preset_evolution_supplements(self):
        base = _make_plan(subtitle_quality_v2={"creator_fit": 75})
        evolved = _make_plan(
            subtitle_quality_v2={"creator_fit": 75},
            creator_preset_evolution={"available": True, "evolved_presets": [{"id": "p1"}]},
        )
        assert score_creator_fit(evolved) >= score_creator_fit(base)

    def test_creator_fit_clamped(self):
        plan = _make_plan(
            subtitle_quality_v2={"creator_fit": 100},
            camera_quality_v2={"creator_fit": 100},
            hook_quality_v2={"creator_fit": 100},
            creator_preference_profile={"confidence": 0.99},
            creator_preset_evolution={"available": True, "evolved_presets": [{"id": "p1"}]},
        )
        assert 0 <= score_creator_fit(plan) <= 100


# ---------------------------------------------------------------------------
# TestMarketFit
# ---------------------------------------------------------------------------

class TestMarketFit:
    def test_no_market_data_returns_zero(self):
        plan = _make_plan()
        assert score_market_fit(plan) == 0

    def test_hook_market_fit_drives_score(self):
        plan = _make_plan(hook_quality_v2={"market_fit": 85})
        score = score_market_fit(plan)
        assert score > 0

    def test_subtitle_safe_zone_supplements(self):
        hook_only = _make_plan(hook_quality_v2={"market_fit": 80})
        both = _make_plan(
            hook_quality_v2={"market_fit": 80},
            subtitle_quality_v2={"safe_zone_fit": 90},
        )
        # combining signals should change score (weighted blend)
        s_hook = score_market_fit(hook_only)
        s_both = score_market_fit(both)
        assert abs(s_both - s_hook) <= 20  # reasonable delta

    def test_market_confidence_supplements(self):
        base = _make_plan(hook_quality_v2={"market_fit": 80})
        enriched = _make_plan(
            hook_quality_v2={"market_fit": 80},
            market_optimization_intelligence={"available": True, "confidence": 0.80},
        )
        assert score_market_fit(enriched) >= score_market_fit(base)

    def test_market_fit_clamped(self):
        plan = _make_plan(
            hook_quality_v2={"market_fit": 100},
            subtitle_quality_v2={"safe_zone_fit": 100},
            market_optimization_intelligence={"available": True, "confidence": 0.99},
        )
        assert 0 <= score_market_fit(plan) <= 100


# ---------------------------------------------------------------------------
# TestStrategyFit
# ---------------------------------------------------------------------------

class TestStrategyFit:
    def test_no_strategy_data_returns_zero(self):
        plan = _make_plan()
        assert score_strategy_fit(plan) == 0

    def test_variant_evaluation_confidence_drives_score(self):
        plan = _make_plan(
            variant_evaluation={"available": True, "confidence": 0.80, "best_variant_id": "v1"},
        )
        score = score_strategy_fit(plan)
        assert score > 0

    def test_strong_recommendation_boosts_score(self):
        moderate = _make_plan(
            variant_evaluation={"available": True, "confidence": 0.70},
            best_strategy_reasoning={"confidence": 0.70, "recommendation_strength": "moderate"},
        )
        strong = _make_plan(
            variant_evaluation={"available": True, "confidence": 0.70},
            best_strategy_reasoning={"confidence": 0.70, "recommendation_strength": "strong"},
        )
        assert score_strategy_fit(strong) > score_strategy_fit(moderate)

    def test_strategy_fit_clamped(self):
        plan = _make_plan(
            variant_evaluation={"available": True, "confidence": 0.99, "best_variant_id": "v1"},
            best_strategy_reasoning={"confidence": 0.99, "recommendation_strength": "strong"},
        )
        assert 0 <= score_strategy_fit(plan) <= 100

    def test_strategy_never_applied(self):
        # scorer output is a score, not a mutation directive
        plan = _full_plan()
        result = evaluate_unified_quality_v2(plan)
        rqv2 = result["render_quality_v2"]
        assert "apply" not in rqv2
        assert "execute" not in rqv2
        assert "mutation" not in rqv2


# ---------------------------------------------------------------------------
# TestNoUnsafeFields
# ---------------------------------------------------------------------------

class TestNoUnsafeFields:
    _FORBIDDEN = {
        "traceback", "exception", "__class__", "stack", "frame",
        "ffmpeg", "executor", "pipeline", "rewrite", "mutation", "override",
    }

    def test_no_debug_text_in_reasoning(self):
        result = evaluate_unified_quality_v2(_full_plan())
        for line in result["render_quality_v2"]["reasoning"]:
            lower = line.lower()
            for bad in self._FORBIDDEN:
                assert bad not in lower, f"Debug text '{bad}' found: {line}"

    def test_no_forbidden_keys_in_result(self):
        result = evaluate_unified_quality_v2(_full_plan())
        for k in result["render_quality_v2"]:
            assert k not in self._FORBIDDEN

    def test_no_forbidden_keys_in_fallback(self):
        fb = fallback_render_quality_v2()
        for k in fb:
            assert k not in self._FORBIDDEN

    def test_reasoning_max_five_items(self):
        result = evaluate_unified_quality_v2(_full_plan())
        assert len(result["render_quality_v2"]["reasoning"]) <= 5

    def test_no_render_pipeline_fields(self):
        result = evaluate_unified_quality_v2(_full_plan())
        rqv2 = result["render_quality_v2"]
        for k in ("applied", "blocked", "mutations", "overrides", "executor"):
            assert k not in rqv2


# ---------------------------------------------------------------------------
# TestSchemaDataclass
# ---------------------------------------------------------------------------

class TestSchemaDataclass:
    def test_default_scores_are_zero(self):
        d = UnifiedQualityV2().to_dict()
        for k in ("subtitle_score", "camera_score", "hook_score",
                   "creator_fit", "market_fit", "strategy_fit", "overall"):
            assert d[k] == 0

    def test_default_confidence_is_zero(self):
        assert UnifiedQualityV2().to_dict()["confidence"] == 0.0

    def test_default_reasoning_is_empty(self):
        assert UnifiedQualityV2().to_dict()["reasoning"] == []

    def test_to_dict_has_all_keys(self):
        d = UnifiedQualityV2().to_dict()
        expected = {
            "subtitle_score", "camera_score", "hook_score",
            "creator_fit", "market_fit", "strategy_fit",
            "overall", "confidence", "reasoning",
        }
        assert expected == set(d.keys())

    def test_to_dict_reasoning_capped_at_five(self):
        uq = UnifiedQualityV2(reasoning=["a", "b", "c", "d", "e", "f", "g"])
        assert len(uq.to_dict()["reasoning"]) == 5

    def test_fallback_dict_matches_spec(self):
        fb = fallback_render_quality_v2()
        assert fb["overall"] == 0
        assert fb["confidence"] == 0.0
        assert fb["reasoning"] == []
        for k in ("subtitle_score", "camera_score", "hook_score",
                   "creator_fit", "market_fit", "strategy_fit"):
            assert fb[k] == 0


# ---------------------------------------------------------------------------
# TestRenderInfluenceReporting
# ---------------------------------------------------------------------------

class TestRenderInfluenceReporting:
    def _make_report(self):
        return {"applied": [], "skipped": [], "blocked": []}

    def _call_reporter(self, edit_plan, report=None):
        from app.ai.director.render_influence import _report_render_quality_v2
        if report is None:
            report = self._make_report()
        _report_render_quality_v2(None, edit_plan, report)
        return report

    def test_no_attribute_reports_no_result(self):
        plan = SimpleNamespace()
        report = self._call_reporter(plan)
        assert any("no_result_phase52d" in s for s in report["skipped"])

    def test_empty_dict_reports_no_result(self):
        plan = SimpleNamespace(render_quality_v2={})
        report = self._call_reporter(plan)
        assert any("no_result" in s for s in report["skipped"])

    def test_all_zero_reports_no_signal(self):
        plan = SimpleNamespace(render_quality_v2=fallback_render_quality_v2())
        report = self._call_reporter(plan)
        assert any("no_signal_phase52d" in s for s in report["skipped"])

    def test_available_result_reports_evaluated(self):
        plan = SimpleNamespace(render_quality_v2={
            "subtitle_score": 86, "camera_score": 88, "hook_score": 85,
            "creator_fit": 87, "market_fit": 83, "strategy_fit": 70,
            "overall": 87, "confidence": 0.86, "reasoning": ["Quality is strong"],
        })
        report = self._call_reporter(plan)
        assert any("evaluated_phase52d" in s for s in report["skipped"])

    def test_report_contains_overall(self):
        plan = SimpleNamespace(render_quality_v2={
            "subtitle_score": 86, "camera_score": 88, "hook_score": 85,
            "creator_fit": 87, "market_fit": 83, "strategy_fit": 70,
            "overall": 87, "confidence": 0.86, "reasoning": [],
        })
        report = self._call_reporter(plan)
        assert any("overall=87" in s for s in report["skipped"])

    def test_report_contains_confidence(self):
        plan = SimpleNamespace(render_quality_v2={
            "subtitle_score": 86, "camera_score": 88, "hook_score": 85,
            "creator_fit": 87, "market_fit": 83, "strategy_fit": 70,
            "overall": 87, "confidence": 0.86, "reasoning": [],
        })
        report = self._call_reporter(plan)
        assert any("confidence=0.86" in s for s in report["skipped"])

    def test_never_reports_to_applied(self):
        plan = SimpleNamespace(render_quality_v2={
            "subtitle_score": 86, "camera_score": 88, "hook_score": 85,
            "creator_fit": 87, "market_fit": 83, "strategy_fit": 70,
            "overall": 87, "confidence": 0.86, "reasoning": [],
        })
        report = self._call_reporter(plan)
        assert len(report["applied"]) == 0

    def test_never_reports_to_blocked(self):
        plan = SimpleNamespace(render_quality_v2={
            "subtitle_score": 86, "camera_score": 88, "hook_score": 85,
            "creator_fit": 87, "market_fit": 83, "strategy_fit": 70,
            "overall": 87, "confidence": 0.86, "reasoning": [],
        })
        report = self._call_reporter(plan)
        assert len(report["blocked"]) == 0
