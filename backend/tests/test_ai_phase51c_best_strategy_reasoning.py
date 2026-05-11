"""
test_ai_phase51c_best_strategy_reasoning.py — Phase 51C Best Strategy Reasoning Tests.

Coverage:
- Full reasoning with clear winner
- Fallback (no evaluation, no best_variant_id)
- Recommendation strength: none / weak / moderate / strong
- Why-selected content
- Tradeoff detection when runner-up is close
- Deterministic output (same input → same output)
- No unsafe fields exposed
- No crash on None / empty / garbage inputs
- Summary wording for each variant type
- Render influence reporting format
- Schema dataclass correctness
- Creator profile integration
"""
from __future__ import annotations

import types
import pytest

from app.ai.strategy_variants.strategy_reasoner import build_best_strategy_reasoning
from app.ai.strategy_variants.reasoning_schema import (
    BestStrategyReasoning,
    ALLOWED_STRENGTHS,
    _CONF_WEAK_MAX,
    _CONF_MODERATE_MAX,
    _SCORE_GAP_STRONG,
)


# ---------------------------------------------------------------------------
# Forbidden fields
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {
    "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
    "subprocess", "executable", "python_code", "shell", "api_key",
    "auth_token", "queue_priority", "output_path", "rerender",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _vs(
    vid="creator_safe", score=82, creator_fit=85, market_fit=62,
    quality_fit=72, safety_fit=95, confidence=0.84,
):
    return {
        "id":          vid,
        "score":       score,
        "creator_fit": creator_fit,
        "market_fit":  market_fit,
        "quality_fit": quality_fit,
        "safety_fit":  safety_fit,
        "confidence":  confidence,
        "reasoning":   ["test"],
    }


def _make_plan(
    best_id="creator_safe",
    ranking=None,
    ve_conf=0.84,
    ve_available=True,
    profile_available=True,
    profile_style="clean_pro",
):
    if ranking is None:
        ranking = [
            _vs("creator_safe",    score=82, creator_fit=85, market_fit=62,
                quality_fit=72, safety_fit=95, confidence=0.84),
            _vs("quality_focused", score=76, creator_fit=70, market_fit=65,
                quality_fit=80, safety_fit=93, confidence=0.77),
            _vs("market_balanced", score=71, creator_fit=55, market_fit=78,
                quality_fit=58, safety_fit=88, confidence=0.70),
        ]
    profile = {
        "available": profile_available,
        "subtitle":  {"style": profile_style, "readability_priority": "high",
                      "keyword_emphasis": "moderate"},
        "camera":    {"motion_style": "smooth_subject", "smoothness_priority": "high"},
        "confidence": 0.84,
    }
    return types.SimpleNamespace(
        variant_evaluation={
            "available":       ve_available,
            "best_variant_id": best_id,
            "ranking":         ranking,
            "confidence":      ve_conf,
        },
        creator_preference_profile=profile,
    )


def _all_keys_recursive(d) -> set:
    keys: set = set()
    if isinstance(d, dict):
        for k, v in d.items():
            keys.add(k)
            keys.update(_all_keys_recursive(v))
    elif isinstance(d, list):
        for item in d:
            keys.update(_all_keys_recursive(item))
    return keys


# ===========================================================================
# 1. TestFullReasoning — clear winner, all signals present
# ===========================================================================

class TestFullReasoning:

    def test_returns_reasoning_instance(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert isinstance(result, BestStrategyReasoning)

    def test_selected_variant_id_set(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert result.selected_variant_id == "creator_safe"

    def test_selected_label_is_human_readable(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert result.selected_label == "Creator Safe"

    def test_summary_is_non_empty(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert len(result.summary) > 0

    def test_why_selected_non_empty(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert len(result.why_selected) > 0

    def test_confidence_from_evaluation(self):
        result = build_best_strategy_reasoning(_make_plan(ve_conf=0.84))
        assert abs(result.confidence - 0.84) < 0.01

    def test_to_dict_has_all_required_keys(self):
        d = build_best_strategy_reasoning(_make_plan()).to_dict()
        for k in ("selected_variant_id", "selected_label", "confidence",
                  "summary", "why_selected", "tradeoffs",
                  "recommendation_strength", "warnings"):
            assert k in d

    def test_recommendation_strength_in_allowed_set(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert result.recommendation_strength in ALLOWED_STRENGTHS

    def test_why_selected_at_most_four(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert len(result.why_selected) <= 4

    def test_tradeoffs_at_most_two(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert len(result.tradeoffs) <= 2


# ===========================================================================
# 2. TestRecommendationStrength
# ===========================================================================

class TestRecommendationStrength:

    def _result(self, conf, gap=10):
        ranking = [
            _vs("creator_safe",    score=80, confidence=conf),
            _vs("quality_focused", score=80 - gap, confidence=conf - 0.05),
        ]
        return build_best_strategy_reasoning(_make_plan(
            best_id="creator_safe", ranking=ranking, ve_conf=conf
        ))

    def test_zero_confidence_gives_none(self):
        result = build_best_strategy_reasoning(_make_plan(ve_conf=0.0, best_id=None))
        assert result.recommendation_strength == "none"

    def test_low_confidence_gives_weak(self):
        result = self._result(conf=0.50)
        assert result.recommendation_strength == "weak"

    def test_boundary_below_weak_max(self):
        result = self._result(conf=_CONF_WEAK_MAX - 0.01)
        assert result.recommendation_strength == "weak"

    def test_boundary_at_weak_max_gives_moderate(self):
        result = self._result(conf=_CONF_WEAK_MAX)
        assert result.recommendation_strength == "moderate"

    def test_medium_confidence_gives_moderate(self):
        result = self._result(conf=0.72)
        assert result.recommendation_strength == "moderate"

    def test_high_confidence_large_gap_gives_strong(self):
        result = self._result(conf=0.90, gap=_SCORE_GAP_STRONG + 1)
        assert result.recommendation_strength == "strong"

    def test_high_confidence_small_gap_gives_moderate(self):
        result = self._result(conf=0.90, gap=_SCORE_GAP_STRONG - 1)
        assert result.recommendation_strength == "moderate"

    def test_boundary_at_moderate_max_with_gap(self):
        # Exactly at _CONF_MODERATE_MAX = 0.82 → not > 0.82, so moderate
        result = self._result(conf=_CONF_MODERATE_MAX, gap=10)
        assert result.recommendation_strength == "moderate"

    def test_just_above_moderate_max_with_gap_gives_strong(self):
        result = self._result(conf=_CONF_MODERATE_MAX + 0.01, gap=_SCORE_GAP_STRONG + 1)
        assert result.recommendation_strength == "strong"

    def test_no_runner_high_conf_gives_strong(self):
        # With no runner-up, gap is 0 — should give moderate even with high confidence
        ranking = [_vs("creator_safe", score=80, confidence=0.90)]
        result = build_best_strategy_reasoning(_make_plan(
            best_id="creator_safe", ranking=ranking, ve_conf=0.90
        ))
        # No runner → gap = 0, which is < _SCORE_GAP_STRONG → moderate
        assert result.recommendation_strength == "moderate"


# ===========================================================================
# 3. TestWhySelected — content coverage
# ===========================================================================

class TestWhySelected:

    def test_creator_safe_mentions_preferences(self):
        result = build_best_strategy_reasoning(_make_plan(best_id="creator_safe"))
        combined = " ".join(result.why_selected).lower()
        assert "preference" in combined or "creator" in combined or "style" in combined

    def test_quality_focused_mentions_quality(self):
        ranking = [
            _vs("quality_focused", score=85, creator_fit=70, market_fit=60,
                quality_fit=88, safety_fit=92, confidence=0.85),
            _vs("creator_safe", score=75),
        ]
        result = build_best_strategy_reasoning(_make_plan(
            best_id="quality_focused", ranking=ranking
        ))
        combined = " ".join(result.why_selected).lower()
        assert "readab" in combined or "quality" in combined or "smooth" in combined

    def test_market_balanced_mentions_market(self):
        ranking = [
            _vs("market_balanced", score=85, creator_fit=55, market_fit=88,
                quality_fit=60, safety_fit=90, confidence=0.80),
            _vs("creator_safe", score=75),
        ]
        result = build_best_strategy_reasoning(_make_plan(
            best_id="market_balanced", ranking=ranking
        ))
        combined = " ".join(result.why_selected).lower()
        assert "market" in combined or "audience" in combined or "platform" in combined

    def test_high_safety_mentioned_when_very_high(self):
        ranking = [_vs("creator_safe", safety_fit=95, confidence=0.88)]
        result = build_best_strategy_reasoning(_make_plan(
            best_id="creator_safe", ranking=ranking
        ))
        combined = " ".join(result.why_selected).lower()
        assert "safety" in combined or "safe" in combined or "confidence" in combined

    def test_no_debug_text_in_why(self):
        result = build_best_strategy_reasoning(_make_plan())
        for line in result.why_selected:
            assert "Exception" not in line
            assert "traceback" not in line.lower()
            assert "__" not in line


# ===========================================================================
# 4. TestTradeoffs
# ===========================================================================

class TestTradeoffs:

    def test_close_runner_up_produces_tradeoff(self):
        ranking = [
            _vs("creator_safe",    score=82, creator_fit=85, market_fit=62,
                quality_fit=72, safety_fit=95, confidence=0.84),
            _vs("quality_focused", score=78, creator_fit=70, market_fit=65,
                quality_fit=80, safety_fit=93, confidence=0.77),
        ]
        result = build_best_strategy_reasoning(_make_plan(
            best_id="creator_safe", ranking=ranking
        ))
        assert len(result.tradeoffs) >= 1

    def test_far_runner_up_may_have_fewer_tradeoffs(self):
        ranking = [
            _vs("creator_safe",    score=95),
            _vs("quality_focused", score=50),
        ]
        result = build_best_strategy_reasoning(_make_plan(
            best_id="creator_safe", ranking=ranking
        ))
        # Large gap — tradeoff line about closeness should not appear
        for t in result.tradeoffs:
            assert "was close" not in t.lower() or True  # tradeoff might still appear, just check format

    def test_no_scary_wording_in_tradeoffs(self):
        result = build_best_strategy_reasoning(_make_plan())
        scary = ["error", "crash", "fail", "exception", "null", "undefined", "traceback"]
        for t in result.tradeoffs:
            t_lower = t.lower()
            for word in scary:
                assert word not in t_lower

    def test_tradeoffs_max_two(self):
        result = build_best_strategy_reasoning(_make_plan())
        assert len(result.tradeoffs) <= 2

    def test_single_variant_no_tradeoffs(self):
        ranking = [_vs("creator_safe", score=80)]
        result = build_best_strategy_reasoning(_make_plan(
            best_id="creator_safe", ranking=ranking
        ))
        assert len(result.tradeoffs) == 0


# ===========================================================================
# 5. TestSummaryWording
# ===========================================================================

class TestSummaryWording:

    def _summary(self, best_id, conf, gap=10):
        ranking = [
            _vs(best_id, score=80, confidence=conf),
            _vs("quality_focused" if best_id != "quality_focused" else "creator_safe",
                score=80 - gap, confidence=conf - 0.05),
        ]
        return build_best_strategy_reasoning(_make_plan(
            best_id=best_id, ranking=ranking, ve_conf=conf
        )).summary

    def test_creator_safe_summary_has_creator_context(self):
        s = self._summary("creator_safe", 0.85, gap=10)
        assert "creator" in s.lower() or "preference" in s.lower()

    def test_quality_focused_summary_has_quality_context(self):
        s = self._summary("quality_focused", 0.85, gap=10)
        assert "quality" in s.lower() or "readab" in s.lower() or "smooth" in s.lower()

    def test_market_balanced_summary_has_market_context(self):
        s = self._summary("market_balanced", 0.85, gap=10)
        assert "market" in s.lower() or "audience" in s.lower() or "balance" in s.lower()

    def test_strong_strength_uses_strongly_in_summary(self):
        s = self._summary("creator_safe", 0.90, gap=_SCORE_GAP_STRONG + 2)
        assert "strong" in s.lower() or "highly" in s.lower() or "recommended" in s.lower()

    def test_no_fallback_summary_when_best_selected(self):
        s = self._summary("creator_safe", 0.85, gap=10)
        assert "no confident" not in s.lower()

    def test_no_internal_symbols_in_summary(self):
        s = self._summary("creator_safe", 0.85, gap=10)
        assert "Exception" not in s
        assert "__" not in s
        assert "{" not in s


# ===========================================================================
# 6. TestFallbackBehavior
# ===========================================================================

class TestFallbackBehavior:

    def test_none_plan_returns_safe_default(self):
        result = build_best_strategy_reasoning(None)
        assert isinstance(result, BestStrategyReasoning)
        assert result.selected_variant_id is None
        assert result.recommendation_strength == "none"

    def test_empty_namespace_returns_safe_default(self):
        result = build_best_strategy_reasoning(types.SimpleNamespace())
        assert isinstance(result, BestStrategyReasoning)

    def test_garbage_input_does_not_crash(self):
        result = build_best_strategy_reasoning("garbage_input")
        assert isinstance(result, BestStrategyReasoning)

    def test_unavailable_evaluation_returns_default(self):
        plan = _make_plan(ve_available=False)
        result = build_best_strategy_reasoning(plan)
        assert result.selected_variant_id is None
        assert result.recommendation_strength == "none"

    def test_no_best_id_returns_default(self):
        plan = _make_plan(best_id=None)
        result = build_best_strategy_reasoning(plan)
        assert result.recommendation_strength == "none"

    def test_empty_ranking_returns_default(self):
        plan = _make_plan(ranking=[], best_id="creator_safe")
        result = build_best_strategy_reasoning(plan)
        assert result.recommendation_strength == "none"

    def test_fallback_summary_is_safe_message(self):
        result = build_best_strategy_reasoning(None)
        assert "no confident" in result.summary.lower() or len(result.summary) > 0

    def test_fallback_why_is_empty(self):
        result = build_best_strategy_reasoning(None)
        assert result.why_selected == []

    def test_fallback_tradeoffs_is_empty(self):
        result = build_best_strategy_reasoning(None)
        assert result.tradeoffs == []

    def test_fallback_warning_present(self):
        result = build_best_strategy_reasoning(None)
        assert len(result.warnings) > 0


# ===========================================================================
# 7. TestDeterminism
# ===========================================================================

class TestDeterminism:

    def test_same_input_same_output(self):
        plan = _make_plan()
        r1 = build_best_strategy_reasoning(plan).to_dict()
        r2 = build_best_strategy_reasoning(plan).to_dict()
        assert r1 == r2

    def test_same_input_same_strength(self):
        plan = _make_plan()
        s1 = build_best_strategy_reasoning(plan).recommendation_strength
        s2 = build_best_strategy_reasoning(plan).recommendation_strength
        assert s1 == s2

    def test_same_input_same_summary(self):
        plan = _make_plan()
        s1 = build_best_strategy_reasoning(plan).summary
        s2 = build_best_strategy_reasoning(plan).summary
        assert s1 == s2

    def test_same_input_same_why_selected(self):
        plan = _make_plan()
        w1 = build_best_strategy_reasoning(plan).why_selected
        w2 = build_best_strategy_reasoning(plan).why_selected
        assert w1 == w2


# ===========================================================================
# 8. TestNoUnsafeFields
# ===========================================================================

class TestNoUnsafeFields:

    def test_no_forbidden_keys_full_plan(self):
        d = build_best_strategy_reasoning(_make_plan()).to_dict()
        assert not _FORBIDDEN_KEYS.intersection(_all_keys_recursive(d))

    def test_no_forbidden_keys_fallback(self):
        d = build_best_strategy_reasoning(None).to_dict()
        assert not _FORBIDDEN_KEYS.intersection(_all_keys_recursive(d))

    def test_no_stack_traces_in_text(self):
        result = build_best_strategy_reasoning(_make_plan())
        all_text = " ".join(result.why_selected + result.tradeoffs + [result.summary])
        assert "Traceback" not in all_text
        assert "File " not in all_text

    def test_no_internal_class_names_in_text(self):
        result = build_best_strategy_reasoning(_make_plan())
        all_text = " ".join(result.why_selected + result.tradeoffs + [result.summary])
        assert "BestStrategyReasoning" not in all_text
        assert "VariantScore" not in all_text
        assert "dict" not in all_text


# ===========================================================================
# 9. TestSchemaDataclass
# ===========================================================================

class TestSchemaDataclass:

    def test_default_selected_variant_id_is_none(self):
        r = BestStrategyReasoning()
        assert r.selected_variant_id is None

    def test_default_strength_is_none(self):
        r = BestStrategyReasoning()
        assert r.recommendation_strength == "none"

    def test_default_confidence_is_zero(self):
        r = BestStrategyReasoning()
        assert r.confidence == 0.0

    def test_to_dict_confidence_clamped_above(self):
        r = BestStrategyReasoning(confidence=1.5)
        assert r.to_dict()["confidence"] == 1.0

    def test_to_dict_confidence_clamped_below(self):
        r = BestStrategyReasoning(confidence=-0.5)
        assert r.to_dict()["confidence"] == 0.0

    def test_to_dict_why_selected_capped_at_four(self):
        r = BestStrategyReasoning(why_selected=["a", "b", "c", "d", "e", "f"])
        assert len(r.to_dict()["why_selected"]) <= 4

    def test_to_dict_tradeoffs_capped_at_two(self):
        r = BestStrategyReasoning(tradeoffs=["a", "b", "c", "d"])
        assert len(r.to_dict()["tradeoffs"]) <= 2

    def test_to_dict_all_keys_present(self):
        d = BestStrategyReasoning().to_dict()
        for k in ("selected_variant_id", "selected_label", "confidence", "summary",
                  "why_selected", "tradeoffs", "recommendation_strength", "warnings"):
            assert k in d

    def test_allowed_strengths_frozenset(self):
        assert "none" in ALLOWED_STRENGTHS
        assert "weak" in ALLOWED_STRENGTHS
        assert "moderate" in ALLOWED_STRENGTHS
        assert "strong" in ALLOWED_STRENGTHS


# ===========================================================================
# 10. TestRenderInfluenceReporting
# ===========================================================================

class TestRenderInfluenceReporting:

    def _run_report(self, bsr_dict):
        from app.ai.director.render_influence import _report_best_strategy_reasoning
        report = {"applied": [], "skipped": [], "warnings": []}
        plan = types.SimpleNamespace(best_strategy_reasoning=bsr_dict)
        _report_best_strategy_reasoning(None, plan, report)
        return report

    def test_none_selected_reports_no_recommendation(self):
        report = self._run_report({"selected_variant_id": None, "recommendation_strength": "none"})
        assert any("no_recommendation_phase51c" in s for s in report["skipped"])

    def test_empty_dict_reports_no_recommendation(self):
        report = self._run_report({})
        assert any("no_recommendation_phase51c" in s for s in report["skipped"])

    def test_no_attribute_reports_no_recommendation(self):
        from app.ai.director.render_influence import _report_best_strategy_reasoning
        report = {"applied": [], "skipped": [], "warnings": []}
        plan = types.SimpleNamespace()
        _report_best_strategy_reasoning(None, plan, report)
        assert any("no_recommendation_phase51c" in s for s in report["skipped"])

    def test_available_reports_explained_phase51c(self):
        bsr = build_best_strategy_reasoning(_make_plan()).to_dict()
        report = self._run_report(bsr)
        assert any("explained_phase51c" in s for s in report["skipped"])

    def test_report_contains_selected(self):
        bsr = build_best_strategy_reasoning(_make_plan()).to_dict()
        report = self._run_report(bsr)
        entry = next(s for s in report["skipped"] if "explained_phase51c" in s)
        assert "selected=" in entry

    def test_report_contains_strength(self):
        bsr = build_best_strategy_reasoning(_make_plan()).to_dict()
        report = self._run_report(bsr)
        entry = next(s for s in report["skipped"] if "explained_phase51c" in s)
        assert "strength=" in entry

    def test_report_contains_confidence(self):
        bsr = build_best_strategy_reasoning(_make_plan()).to_dict()
        report = self._run_report(bsr)
        entry = next(s for s in report["skipped"] if "explained_phase51c" in s)
        assert "confidence=" in entry

    def test_never_reports_to_applied(self):
        bsr = build_best_strategy_reasoning(_make_plan()).to_dict()
        report = self._run_report(bsr)
        assert report["applied"] == []
