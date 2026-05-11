"""
test_ai_phase48_safe_influence.py — Phase 48 Safe Controlled Influence Engine tests.

Covers:
- Safety gate behavior (blocked / soft / strong tiers)
- Subtitle bias (style + density)
- Camera bias (smoothing / stability / deadzone)
- Ranking bias (priority + secondary sort)
- Market weighting (per-platform profiles)
- Influence engine end-to-end
- Determinism
- Fallback / never-raises behavior
- Safety boundaries (no render mutation, no executor override)
- Edit plan schema field
- Render influence reporting
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_edit_plan(**kwargs):
    """Return a minimal AIEditPlan-like mock."""
    plan = MagicMock()
    plan.multi_signal_orchestration = kwargs.get("multi_signal_orchestration", {})
    plan.safe_influence_pack = kwargs.get("safe_influence_pack", {})
    return plan


def _make_mso(agg_confidence: float, strategy: dict | None = None, market: str = "") -> dict:
    """Build a realistic multi_signal_orchestration dict for Phase 47."""
    return {
        "available": True,
        "enabled": True,
        "orchestration_mode": "reasoning_only",
        "confidence_scores": {"aggregate_confidence": agg_confidence},
        "recommended_strategy": strategy or {
            "subtitle_style": "readable",
            "pacing_style": "balanced",
            "camera_motion": "smooth_subject",
            "hook_emphasis": "moderate",
            "clip_selection_bias": "retention",
            "ranking_priority": "retention",
        },
        "aggregated_signals": {
            "active_signal_count": 3,
            "market_signal": {"available": True, "target_market": market} if market else {},
        },
    }


# ---------------------------------------------------------------------------
# 1. Safety Gate
# ---------------------------------------------------------------------------

class TestSafetyGate:
    def test_blocked_below_threshold(self):
        from app.ai.influence.safety_gate import evaluate_gate, TIER_BLOCKED
        result = evaluate_gate(0.60)
        assert result["passed"] is False
        assert result["tier"] == TIER_BLOCKED
        assert "confidence_too_low" in result["reason"]

    def test_soft_tier_at_boundary(self):
        from app.ai.influence.safety_gate import evaluate_gate, TIER_SOFT
        result = evaluate_gate(0.70)
        assert result["passed"] is True
        assert result["tier"] == TIER_SOFT

    def test_soft_tier_midrange(self):
        from app.ai.influence.safety_gate import evaluate_gate, TIER_SOFT
        result = evaluate_gate(0.78)
        assert result["passed"] is True
        assert result["tier"] == TIER_SOFT

    def test_strong_tier_at_boundary(self):
        from app.ai.influence.safety_gate import evaluate_gate, TIER_STRONG
        result = evaluate_gate(0.86)
        assert result["passed"] is True
        assert result["tier"] == TIER_STRONG

    def test_strong_tier_high_confidence(self):
        from app.ai.influence.safety_gate import evaluate_gate, TIER_STRONG
        result = evaluate_gate(0.99)
        assert result["passed"] is True
        assert result["tier"] == TIER_STRONG

    def test_exactly_block_threshold(self):
        from app.ai.influence.safety_gate import evaluate_gate, TIER_BLOCKED
        result = evaluate_gate(0.699)
        assert result["passed"] is False
        assert result["tier"] == TIER_BLOCKED

    def test_exactly_strong_threshold(self):
        from app.ai.influence.safety_gate import evaluate_gate, TIER_STRONG
        result = evaluate_gate(0.851)
        assert result["passed"] is True
        assert result["tier"] == TIER_STRONG

    def test_confidence_preserved_in_result(self):
        from app.ai.influence.safety_gate import evaluate_gate
        result = evaluate_gate(0.75)
        assert abs(result["confidence"] - 0.75) < 1e-6

    def test_is_soft_or_strong_blocked(self):
        from app.ai.influence.safety_gate import evaluate_gate, is_soft_or_strong
        gate = evaluate_gate(0.50)
        assert is_soft_or_strong(gate) is False

    def test_is_soft_or_strong_soft(self):
        from app.ai.influence.safety_gate import evaluate_gate, is_soft_or_strong
        gate = evaluate_gate(0.75)
        assert is_soft_or_strong(gate) is True

    def test_is_strong_soft_returns_false(self):
        from app.ai.influence.safety_gate import evaluate_gate, is_strong
        gate = evaluate_gate(0.75)
        assert is_strong(gate) is False

    def test_is_strong_strong_returns_true(self):
        from app.ai.influence.safety_gate import evaluate_gate, is_strong
        gate = evaluate_gate(0.90)
        assert is_strong(gate) is True

    def test_zero_confidence_blocked(self):
        from app.ai.influence.safety_gate import evaluate_gate, TIER_BLOCKED
        result = evaluate_gate(0.0)
        assert result["passed"] is False
        assert result["tier"] == TIER_BLOCKED

    def test_result_always_has_required_keys(self):
        from app.ai.influence.safety_gate import evaluate_gate
        for conf in (0.0, 0.60, 0.70, 0.85, 0.90, 1.0):
            result = evaluate_gate(conf)
            assert "passed" in result
            assert "tier" in result
            assert "confidence" in result
            assert "reason" in result


# ---------------------------------------------------------------------------
# 2. Subtitle Bias
# ---------------------------------------------------------------------------

class TestSubtitleBias:
    def _soft_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.75)

    def _strong_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.90)

    def _blocked_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.50)

    def test_blocked_gate_returns_unavailable(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        result = compute_subtitle_bias({"subtitle_style": "readable"}, self._blocked_gate())
        assert result["available"] is False

    def test_soft_tier_no_style_bias(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        # Soft tier: style bias blocked, but density="high" triggers density bias → available=True
        result = compute_subtitle_bias({"subtitle_style": "readable", "subtitle_density": "high"}, self._soft_gate())
        assert result["available"] is True
        assert result["subtitle_style_bias"] == ""
        assert result["subtitle_density_bias"] == "lighter"

    def test_strong_tier_style_bias_readable(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        result = compute_subtitle_bias({"subtitle_style": "readable"}, self._strong_gate())
        assert result["subtitle_style_bias"] == "clean_pro"

    def test_strong_tier_style_bias_compact(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        result = compute_subtitle_bias({"subtitle_style": "compact"}, self._strong_gate())
        assert result["subtitle_style_bias"] == "viral_bold"

    def test_density_bias_soft_high_density(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        strategy = {"subtitle_style": "readable", "subtitle_density": "high"}
        result = compute_subtitle_bias(strategy, self._soft_gate())
        assert result["subtitle_density_bias"] == "lighter"

    def test_density_bias_low_density_unchanged(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        strategy = {"subtitle_style": "readable", "subtitle_density": "low"}
        result = compute_subtitle_bias(strategy, self._soft_gate())
        assert result["subtitle_density_bias"] == "unchanged"

    def test_style_bias_only_allowed_values(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        allowed = {"viral_bold", "clean_pro", "boxed_caption", ""}
        for style in ("compact", "readable", "clean_readable", "medium_density", "unknown"):
            result = compute_subtitle_bias({"subtitle_style": style}, self._strong_gate())
            assert result["subtitle_style_bias"] in allowed

    def test_never_raises_on_bad_input(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        from app.ai.influence.safety_gate import evaluate_gate
        result = compute_subtitle_bias(None, evaluate_gate(0.90))
        assert "available" in result

    def test_deterministic_same_inputs(self):
        from app.ai.influence.subtitle_bias import compute_subtitle_bias
        strategy = {"subtitle_style": "readable", "subtitle_density": "high"}
        gate = self._strong_gate()
        r1 = compute_subtitle_bias(strategy, gate)
        r2 = compute_subtitle_bias(strategy, gate)
        assert r1 == r2


# ---------------------------------------------------------------------------
# 3. Camera Bias
# ---------------------------------------------------------------------------

class TestCameraBias:
    def _soft_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.75)

    def _strong_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.90)

    def _blocked_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.50)

    def test_blocked_gate_returns_unavailable(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        result = compute_camera_bias({"camera_motion": "smooth_subject"}, self._blocked_gate())
        assert result["available"] is False

    def test_soft_tier_smoothing_available(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        result = compute_camera_bias({"camera_motion": "smooth_subject"}, self._soft_gate())
        assert result["available"] is True
        assert result["smoothing_preference"] == "prefer_smooth"

    def test_soft_tier_no_stability(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        result = compute_camera_bias({"camera_motion": "smooth_subject"}, self._soft_gate())
        assert result["motion_stability_bias"] == ""

    def test_strong_tier_stability_available(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        result = compute_camera_bias({"camera_motion": "smooth_subject"}, self._strong_gate())
        assert result["motion_stability_bias"] == "stable"

    def test_strong_tier_deadzone_for_stable(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        result = compute_camera_bias({"camera_motion": "smooth_subject"}, self._strong_gate())
        assert result["deadzone_preference"] == "moderate"

    def test_static_motion_locked_deadzone(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        result = compute_camera_bias({"camera_motion": "static"}, self._strong_gate())
        assert result["motion_stability_bias"] == "locked"
        assert result["deadzone_preference"] == "wide"

    def test_camera_motion_bias_passthrough(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        result = compute_camera_bias({"camera_motion": "cinematic"}, self._soft_gate())
        assert result["camera_motion_bias"] == "cinematic"

    def test_unknown_motion_passthrough_hint_only(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        # Unknown motion: no smoothing map entry, but raw value passes through as a hint
        result = compute_camera_bias({"camera_motion": "flying_pan"}, self._strong_gate())
        assert result["available"] is True
        assert result["camera_motion_bias"] == "flying_pan"
        assert result["smoothing_preference"] == ""

    def test_never_raises_on_bad_input(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        from app.ai.influence.safety_gate import evaluate_gate
        result = compute_camera_bias(None, evaluate_gate(0.90))
        assert "available" in result

    def test_deterministic(self):
        from app.ai.influence.camera_bias import compute_camera_bias
        strategy = {"camera_motion": "smooth_social"}
        gate = self._strong_gate()
        r1 = compute_camera_bias(strategy, gate)
        r2 = compute_camera_bias(strategy, gate)
        assert r1 == r2


# ---------------------------------------------------------------------------
# 4. Ranking Bias
# ---------------------------------------------------------------------------

class TestRankingBias:
    def _soft_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.75)

    def _strong_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.90)

    def _blocked_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.50)

    def test_blocked_returns_unavailable(self):
        from app.ai.influence.ranking_bias import compute_ranking_bias
        result = compute_ranking_bias({"ranking_priority": "retention"}, self._blocked_gate())
        assert result["available"] is False

    def test_allowed_priority_passes_through(self):
        from app.ai.influence.ranking_bias import compute_ranking_bias
        for priority in ("retention", "creator_fit", "market_fit", "preset_fit", "quality"):
            result = compute_ranking_bias({"ranking_priority": priority}, self._soft_gate())
            assert result["available"] is True
            assert result["ranking_priority_bias"] == priority

    def test_unknown_priority_not_surfaced(self):
        from app.ai.influence.ranking_bias import compute_ranking_bias
        result = compute_ranking_bias({"ranking_priority": "viral_score"}, self._strong_gate())
        assert result["available"] is False

    def test_secondary_sort_soft_tier_empty(self):
        from app.ai.influence.ranking_bias import compute_ranking_bias
        result = compute_ranking_bias({"ranking_priority": "retention"}, self._soft_gate())
        assert result["secondary_sort_bias"] == ""

    def test_secondary_sort_strong_tier(self):
        from app.ai.influence.ranking_bias import compute_ranking_bias
        result = compute_ranking_bias({"ranking_priority": "retention"}, self._strong_gate())
        assert result["secondary_sort_bias"] == "hook_score"

    def test_secondary_sort_creator_fit(self):
        from app.ai.influence.ranking_bias import compute_ranking_bias
        result = compute_ranking_bias({"ranking_priority": "creator_fit"}, self._strong_gate())
        assert result["secondary_sort_bias"] == "style_match"

    def test_deterministic(self):
        from app.ai.influence.ranking_bias import compute_ranking_bias
        strategy = {"ranking_priority": "quality"}
        gate = self._strong_gate()
        r1 = compute_ranking_bias(strategy, gate)
        r2 = compute_ranking_bias(strategy, gate)
        assert r1 == r2

    def test_never_raises_on_bad_input(self):
        from app.ai.influence.ranking_bias import compute_ranking_bias
        from app.ai.influence.safety_gate import evaluate_gate
        result = compute_ranking_bias(None, evaluate_gate(0.90))
        assert "available" in result


# ---------------------------------------------------------------------------
# 5. Market Weighting
# ---------------------------------------------------------------------------

class TestMarketWeighting:
    def _soft_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.75)

    def _strong_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.90)

    def _blocked_gate(self):
        from app.ai.influence.safety_gate import evaluate_gate
        return evaluate_gate(0.50)

    def _signals(self, market: str) -> dict:
        return {"market_signal": {"target_market": market}}

    def test_blocked_returns_unavailable(self):
        from app.ai.influence.market_weighting import compute_market_weights
        result = compute_market_weights(self._signals("tiktok"), self._blocked_gate())
        assert result["available"] is False

    def test_no_market_returns_unavailable(self):
        from app.ai.influence.market_weighting import compute_market_weights
        result = compute_market_weights({}, self._soft_gate())
        assert result["available"] is False

    def test_tiktok_hook_bias_positive(self):
        from app.ai.influence.market_weighting import compute_market_weights
        result = compute_market_weights(self._signals("tiktok"), self._strong_gate())
        assert result["available"] is True
        assert result["hook_weight_bias"] > 0.0

    def test_podcast_readability_high(self):
        from app.ai.influence.market_weighting import compute_market_weights
        result = compute_market_weights(self._signals("podcast"), self._strong_gate())
        assert result["available"] is True
        assert result["readability_bias"] > result.get("hook_weight_bias", 0.0)

    def test_educational_readability_high(self):
        from app.ai.influence.market_weighting import compute_market_weights
        result = compute_market_weights(self._signals("educational"), self._strong_gate())
        assert result["available"] is True
        assert result["readability_bias"] >= result.get("energy_weight_bias", 0.0)

    def test_bias_bounded_by_max(self):
        from app.ai.influence.market_weighting import compute_market_weights, _MAX_BIAS
        result = compute_market_weights(self._signals("viral_tiktok"), self._strong_gate())
        for key, val in result.items():
            if isinstance(val, float):
                assert val <= _MAX_BIAS + 1e-9, f"{key}={val} exceeds MAX_BIAS={_MAX_BIAS}"

    def test_soft_tier_mult_produces_lower_biases(self):
        from app.ai.influence.market_weighting import compute_market_weights
        soft = compute_market_weights(self._signals("tiktok"), self._soft_gate())
        strong = compute_market_weights(self._signals("tiktok"), self._strong_gate())
        # Soft bias should be smaller (0.6 multiplier vs 1.0)
        assert soft.get("hook_weight_bias", 0) < strong.get("hook_weight_bias", 0)

    def test_target_market_preserved(self):
        from app.ai.influence.market_weighting import compute_market_weights
        result = compute_market_weights(self._signals("youtube_shorts"), self._strong_gate())
        assert result["target_market"] == "youtube_shorts"

    def test_unknown_market_uses_default_profile(self):
        from app.ai.influence.market_weighting import compute_market_weights
        result = compute_market_weights(self._signals("snapchat"), self._strong_gate())
        assert result["available"] is True

    def test_deterministic(self):
        from app.ai.influence.market_weighting import compute_market_weights
        signals = self._signals("tiktok")
        gate = self._strong_gate()
        r1 = compute_market_weights(signals, gate)
        r2 = compute_market_weights(signals, gate)
        assert r1 == r2

    def test_never_raises_on_bad_input(self):
        from app.ai.influence.market_weighting import compute_market_weights
        from app.ai.influence.safety_gate import evaluate_gate
        result = compute_market_weights(None, evaluate_gate(0.90))
        assert "available" in result


# ---------------------------------------------------------------------------
# 6. Influence Engine — End-to-End
# ---------------------------------------------------------------------------

class TestInfluenceEngine:
    def _plan_with_mso(self, agg_confidence: float, market: str = "") -> MagicMock:
        plan = MagicMock()
        plan.multi_signal_orchestration = _make_mso(agg_confidence, market=market)
        return plan

    def _plan_no_mso(self) -> MagicMock:
        plan = MagicMock()
        plan.multi_signal_orchestration = {}
        return plan

    def test_no_mso_returns_disabled(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_no_mso())
        assert result["enabled"] is False
        assert "no_orchestration_available_phase47" in result["warnings"]

    def test_blocked_confidence_returns_disabled(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.50))
        assert result["enabled"] is False
        assert any("gate_blocked" in w for w in result["warnings"])

    def test_soft_confidence_can_enable(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.75))
        assert result["available"] is True

    def test_strong_confidence_enables(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.92))
        assert result["enabled"] is True

    def test_output_has_safe_influence_surface(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.92))
        si = result.get("safe_influence", {})
        assert "subtitle_style_bias" in si
        assert "subtitle_density_bias" in si
        assert "camera_motion_bias" in si
        assert "ranking_priority_bias" in si

    def test_influence_mode_always_safe_controlled(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        for conf in (0.0, 0.50, 0.75, 0.92):
            result = compute_safe_influence(self._plan_with_mso(conf))
            assert result.get("influence_mode") == "safe_controlled"

    def test_gate_info_present_when_passed(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.92))
        assert "gate" in result
        assert result["gate"]["passed"] is True

    def test_domain_bias_dicts_present(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.92))
        for key in ("subtitle_bias", "camera_bias", "ranking_bias", "market_weights"):
            assert key in result

    def test_confidence_in_output(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.92))
        assert isinstance(result.get("confidence"), float)

    def test_explainability_present_when_enabled(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.92))
        if result.get("enabled"):
            exp = result.get("explainability", [])
            assert isinstance(exp, list)
            assert len(exp) > 0

    def test_none_edit_plan_returns_fallback(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(None)
        assert result["available"] is True
        assert result["enabled"] is False

    def test_market_signal_flows_to_weights(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        result = compute_safe_influence(self._plan_with_mso(0.92, market="tiktok"))
        mw = result.get("market_weights", {})
        if mw.get("available"):
            assert mw["target_market"] == "tiktok"

    def test_deterministic_same_inputs(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        plan = self._plan_with_mso(0.92, market="tiktok")
        r1 = compute_safe_influence(plan)
        r2 = compute_safe_influence(plan)
        assert r1 == r2

    def test_never_raises_on_corrupt_mso(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        plan = MagicMock()
        plan.multi_signal_orchestration = {"available": True, "enabled": True}
        result = compute_safe_influence(plan)
        assert "available" in result


# ---------------------------------------------------------------------------
# 7. Edit Plan Schema
# ---------------------------------------------------------------------------

class TestEditPlanSchema:
    def _make_plan(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan,
        )
        return AIEditPlan(
            enabled=True,
            mode="auto",
            selected_segments=[AIClipPlan(start=0.0, end=5.0, score=0.9)],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )

    def test_safe_influence_pack_field_exists(self):
        plan = self._make_plan()
        assert hasattr(plan, "safe_influence_pack")

    def test_safe_influence_pack_default_empty_dict(self):
        plan = self._make_plan()
        assert plan.safe_influence_pack == {}

    def test_to_dict_includes_safe_influence_pack(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "safe_influence_pack" in d

    def test_to_dict_safe_influence_pack_empty_by_default(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert d["safe_influence_pack"] == {}

    def test_to_dict_safe_influence_pack_populated(self):
        plan = self._make_plan()
        plan.safe_influence_pack = {"available": True, "enabled": True, "influence_mode": "safe_controlled"}
        d = plan.to_dict()
        assert d["safe_influence_pack"]["available"] is True

    def test_to_dict_multi_signal_orchestration_present(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "multi_signal_orchestration" in d

    def test_independent_instances_do_not_share_dicts(self):
        plan1 = self._make_plan()
        plan2 = self._make_plan()
        plan1.safe_influence_pack["x"] = 1
        assert "x" not in plan2.safe_influence_pack


# ---------------------------------------------------------------------------
# 8. Render Influence Reporting
# ---------------------------------------------------------------------------

class TestRenderInfluenceReporting:
    def _make_report(self):
        return {"applied": [], "skipped": [], "warnings": []}

    def _make_plan_with_influence(self, enabled: bool = True, conf: float = 0.92, tier: str = "strong") -> MagicMock:
        plan = MagicMock()
        plan.safe_influence_pack = {
            "available": True,
            "enabled": enabled,
            "influence_mode": "safe_controlled",
            "confidence": conf,
            "gate": {"passed": True, "tier": tier, "confidence": conf, "reason": "ok"},
            "safe_influence": {
                "subtitle_style_bias": "clean_pro",
                "subtitle_density_bias": "lighter",
                "camera_motion_bias": "smooth_subject",
                "ranking_priority_bias": "retention",
            },
            "market_weights": {"available": True, "target_market": "tiktok"},
        }
        return plan

    def test_no_safe_influence_pack_reports_skipped(self):
        from app.ai.director.render_influence import _report_safe_influence_pack
        plan = MagicMock()
        plan.safe_influence_pack = {}
        report = self._make_report()
        _report_safe_influence_pack(None, plan, report)
        assert any("safe_influence_pack:no_result" in s for s in report["skipped"])

    def test_unavailable_reports_skipped(self):
        from app.ai.director.render_influence import _report_safe_influence_pack
        plan = MagicMock()
        plan.safe_influence_pack = {"available": False}
        report = self._make_report()
        _report_safe_influence_pack(None, plan, report)
        assert any("unavailable_phase48" in s for s in report["skipped"])

    def test_enabled_reports_to_skipped_not_applied(self):
        from app.ai.director.render_influence import _report_safe_influence_pack
        plan = self._make_plan_with_influence(enabled=True)
        report = self._make_report()
        _report_safe_influence_pack(None, plan, report)
        assert len(report["applied"]) == 0
        assert any("safe_influence_pack" in s for s in report["skipped"])

    def test_disabled_reports_to_skipped(self):
        from app.ai.director.render_influence import _report_safe_influence_pack
        plan = self._make_plan_with_influence(enabled=False)
        report = self._make_report()
        _report_safe_influence_pack(None, plan, report)
        assert any("enabled=False" in s for s in report["skipped"])


# ---------------------------------------------------------------------------
# 9. Safety Boundaries
# ---------------------------------------------------------------------------

class TestSafetyBoundaries:
    """Verify Phase 48 never crosses safety boundaries."""

    def _run_full_influence(self, confidence: float = 0.92) -> dict:
        from app.ai.influence.influence_engine import compute_safe_influence
        plan = MagicMock()
        plan.multi_signal_orchestration = _make_mso(confidence, market="tiktok")
        return compute_safe_influence(plan)

    def test_no_ffmpeg_key_in_output(self):
        result = self._run_full_influence()
        result_str = str(result)
        assert "ffmpeg" not in result_str.lower()

    def test_no_playback_speed_in_output(self):
        result = self._run_full_influence()
        result_str = str(result)
        assert "playback_speed" not in result_str.lower()

    def test_no_subtitle_timing_rewrite(self):
        result = self._run_full_influence()
        result_str = str(result)
        assert "subtitle_timing" not in result_str.lower()

    def test_no_rerender_key(self):
        result = self._run_full_influence()
        result_str = str(result)
        assert "rerender" not in result_str.lower()

    def test_no_executor_override_key(self):
        result = self._run_full_influence()
        result_str = str(result)
        assert "executor_override" not in result_str.lower()

    def test_influence_mode_is_safe_controlled(self):
        result = self._run_full_influence()
        assert result.get("influence_mode") == "safe_controlled"

    def test_safe_influence_surface_only_soft_keys(self):
        result = self._run_full_influence()
        si = result.get("safe_influence", {})
        allowed = {"subtitle_style_bias", "subtitle_density_bias", "camera_motion_bias", "ranking_priority_bias"}
        for key in si:
            assert key in allowed, f"Unexpected key in safe_influence: {key}"

    def test_subtitle_style_bias_only_allowed_presets(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        from app.ai.influence.subtitle_bias import _ALLOWED_STYLE_PRESETS
        plan = MagicMock()
        plan.multi_signal_orchestration = _make_mso(0.92)
        result = compute_safe_influence(plan)
        bias = (result.get("safe_influence") or {}).get("subtitle_style_bias", "")
        assert bias == "" or bias in _ALLOWED_STYLE_PRESETS

    def test_market_weights_bounded(self):
        from app.ai.influence.market_weighting import compute_market_weights, _MAX_BIAS
        from app.ai.influence.safety_gate import evaluate_gate
        signals = {"market_signal": {"target_market": "tiktok"}}
        gate = evaluate_gate(0.92)
        result = compute_market_weights(signals, gate)
        for key, val in result.items():
            if isinstance(val, float):
                assert val <= _MAX_BIAS + 1e-9

    def test_never_raises_on_any_garbage_input(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        for bad_plan in (None, 42, "hello", [], {}, object()):
            result = compute_safe_influence(bad_plan)
            assert "available" in result

    def test_deterministic_across_calls(self):
        from app.ai.influence.influence_engine import compute_safe_influence
        plan = MagicMock()
        plan.multi_signal_orchestration = _make_mso(0.88, market="youtube_shorts")
        results = [compute_safe_influence(plan) for _ in range(5)]
        for r in results[1:]:
            assert r == results[0]

    def test_report_never_writes_to_applied(self):
        from app.ai.director.render_influence import _report_safe_influence_pack
        plan = MagicMock()
        plan.safe_influence_pack = {
            "available": True,
            "enabled": True,
            "influence_mode": "safe_controlled",
            "confidence": 0.92,
            "gate": {"passed": True, "tier": "strong", "confidence": 0.92, "reason": "ok"},
            "safe_influence": {
                "subtitle_style_bias": "viral_bold",
                "subtitle_density_bias": "lighter",
                "camera_motion_bias": "smooth_subject",
                "ranking_priority_bias": "retention",
            },
            "market_weights": {"available": False, "target_market": ""},
        }
        report = {"applied": [], "skipped": [], "warnings": []}
        _report_safe_influence_pack(None, plan, report)
        assert report["applied"] == []
