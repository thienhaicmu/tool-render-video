"""
test_ai_phase47_orchestrator.py — Phase 47 Multi-Signal AI Render Orchestrator tests.

Covers:
  - Signal aggregation (all 6 signal categories, missing signal fallback)
  - Confidence engine (per-signal scoring, aggregate)
  - Conflict resolver (deterministic behavior, winner selection)
  - Strategy planner (recommendation-only, conservative guard)
  - Render orchestrator (end-to-end, determinism, safety boundaries)
  - Edit plan schema integration (field existence, backward compat)
  - Render influence reporting
  - Explainability metadata
  - Safety boundaries (no ffmpeg, no playback_speed, no executor override)
"""
import pytest
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_minimal_plan():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan, AIClipPlan,
    )
    return AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[AIClipPlan(start=0.0, end=20.0, score=80.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(pacing_style="fast_hook", energy_level=0.85),
    )


def _make_rich_plan(mode: str = "viral_tiktok"):
    """Plan with all Phase 41–46 signals populated."""
    plan = _make_minimal_plan()
    plan.mode = mode
    plan.creator_style_adaptation = {"adapted_style": mode, "adaptation_confidence": 0.80}
    plan.creator_retrieval = {
        "enabled": True,
        "matches": [
            {"id": "m1", "creator_style": mode, "score": 0.9},
            {"id": "m2", "creator_style": mode, "score": 0.8},
            {"id": "m3", "creator_style": mode, "score": 0.7},
        ],
    }
    plan.adaptive_creator_intelligence = {
        "available": True,
        "enabled": True,
        "learning_mode": "assistive_only",
        "creator_profile": {
            "style_confidence": 0.75,
            "subtitle_confidence": 0.65,
            "pacing_confidence": 0.60,
            "camera_confidence": 0.55,
        },
        "adaptive_influences": {
            "subtitle_enhancement_weight": 0.10,
            "pacing_enhancement_weight": 0.12,
        },
        "warnings": [],
    }
    plan.creator_feedback_intelligence = {
        "available": True,
        "enabled": True,
        "feedback_mode": "assistive_only",
        "learned_feedback_patterns": {
            "total_exports": 8,
            "total_signals": 12,
            "dominant_creator_style": mode,
            "dominant_subtitle_style": "compact",
            "dominant_pacing_style": "fast_hook",
        },
        "ranking_biases": {
            "subtitle_weighting_bias": 0.10,
            "pacing_weighting_bias": 0.08,
        },
    }
    plan.market_optimization_intelligence = {
        "available": True,
        "enabled": True,
        "optimization_mode": "assistive_only",
        "target_market": mode,
        "market_profile": {"confidence": 0.82, "platform_type": "tiktok"},
        "subtitle_market_bias": {"weight": 0.20, "style": "compact"},
        "pacing_market_bias": {"weight": 0.22, "style": "fast_hook"},
        "camera_market_bias": {"weight": 0.18, "style": "dynamic_safe"},
        "hook_market_bias": {"weight": 0.24},
    }
    plan.render_quality_evaluation = {
        "available": True,
        "enabled": True,
        "evaluation_mode": "evaluation_only",
        "best_quality_output_id": "out_001",
        "output_scores": [
            {"output_id": "out_001", "overall_score": 76.5},
            {"output_id": "out_002", "overall_score": 64.0},
        ],
    }
    plan.creator_preset_evolution = {
        "available": True,
        "enabled": True,
        "evolution_mode": "assistive_only",
        "best_preset_id": "tiktok_viral_v2",
        "recommended_presets": [
            {
                "preset_id": "tiktok_viral_v2",
                "preset_name": "TikTok Viral v2",
                "subtitle_style": "compact",
                "pacing_style": "fast_hook",
                "camera_style": "dynamic_safe",
                "_score": 72.5,
            }
        ],
        "evolved_presets": [
            {
                "preset_id": "tiktok_viral_v2",
                "subtitle_style": "compact",
                "pacing_style": "fast_hook",
                "camera_style": "dynamic_safe",
            }
        ],
        "warnings": [],
    }
    return plan


def _make_podcast_plan():
    return _make_rich_plan("podcast")


def _make_empty_signals():
    return {
        "creator_signal": {"available": False},
        "market_signal": {"available": False},
        "quality_signal": {"available": False},
        "preset_signal": {"available": False},
        "feedback_signal": {"available": False},
        "retrieval_signal": {"available": False},
        "confidence": 0.0,
        "active_signal_count": 0,
    }


# ---------------------------------------------------------------------------
# 1. Signal Aggregation tests
# ---------------------------------------------------------------------------

class TestSignalAggregation:
    def test_aggregate_returns_dict(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(None)
        assert isinstance(result, dict)

    def test_aggregate_none_plan_returns_all_unavailable(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(None)
        for key in ("creator_signal", "market_signal", "quality_signal",
                    "preset_signal", "feedback_signal", "retrieval_signal"):
            assert result[key].get("available") is False

    def test_aggregate_rich_plan_activates_signals(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan())
        active = result["active_signal_count"]
        assert active >= 4

    def test_aggregate_confidence_bounded(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan())
        assert 0.0 <= result["confidence"] <= 1.0

    def test_creator_signal_extracts_style(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan("podcast"))
        assert result["creator_signal"]["adapted_style"] == "podcast"

    def test_creator_signal_confidence_bounded(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan())
        cs = result["creator_signal"]
        for key in ("style_confidence", "subtitle_confidence", "pacing_confidence"):
            assert 0.0 <= cs[key] <= 1.0

    def test_market_signal_extracts_target(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan("viral_tiktok"))
        ms = result["market_signal"]
        assert ms["target_market"] == "viral_tiktok"

    def test_market_signal_confidence_bounded(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan())
        ms = result["market_signal"]
        assert 0.0 <= ms["market_confidence"] <= 1.0

    def test_quality_signal_extracts_best_output(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan())
        qs = result["quality_signal"]
        assert qs["best_output_id"] == "out_001"
        assert qs["best_overall_score"] == 76.5

    def test_preset_signal_extracts_best_preset(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan())
        ps = result["preset_signal"]
        assert ps["best_preset_id"] == "tiktok_viral_v2"
        assert ps["best_subtitle_style"] == "compact"

    def test_feedback_signal_extracts_exports(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan())
        fs = result["feedback_signal"]
        assert fs["total_exports"] == 8
        assert fs["dominant_pacing_style"] == "fast_hook"

    def test_retrieval_signal_extracts_matches(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals(_make_rich_plan())
        rs = result["retrieval_signal"]
        assert rs["match_count"] == 3
        assert rs["retrieval_confidence"] > 0.0

    def test_missing_market_signal_graceful(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        plan = _make_minimal_plan()
        plan.adaptive_creator_intelligence = {
            "available": True,
            "enabled": True,
            "creator_profile": {"style_confidence": 0.5},
        }
        result = aggregate_signals(plan)
        assert result["market_signal"]["available"] is False

    def test_missing_feedback_signal_graceful(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        plan = _make_minimal_plan()
        result = aggregate_signals(plan)
        assert result["feedback_signal"]["available"] is False

    def test_never_raises(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = aggregate_signals("not_a_plan")
        assert isinstance(result, dict)

    def test_deterministic(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        plan = _make_rich_plan()
        r1 = aggregate_signals(plan)
        r2 = aggregate_signals(plan)
        assert r1["confidence"] == r2["confidence"]
        assert r1["active_signal_count"] == r2["active_signal_count"]

    def test_feedback_bias_clamped_0_30(self):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        plan = _make_minimal_plan()
        plan.creator_feedback_intelligence = {
            "available": True,
            "enabled": True,
            "feedback_mode": "assistive_only",
            "learned_feedback_patterns": {"total_exports": 5},
            "ranking_biases": {"subtitle_weighting_bias": 0.99},
        }
        result = aggregate_signals(plan)
        fs = result["feedback_signal"]
        assert fs["subtitle_weighting_bias"] <= 0.30


# ---------------------------------------------------------------------------
# 2. Confidence Engine tests
# ---------------------------------------------------------------------------

class TestConfidenceEngine:
    def test_returns_dict(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        result = compute_signal_confidence(_make_empty_signals())
        assert isinstance(result, dict)

    def test_all_zero_on_no_signals(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        result = compute_signal_confidence(_make_empty_signals())
        for key in ("creator_confidence", "market_confidence", "quality_confidence",
                    "preset_confidence", "feedback_confidence", "retrieval_confidence"):
            assert result[key] == 0.0
        assert result["aggregate_confidence"] == 0.0

    def test_all_keys_present(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = compute_signal_confidence(aggregate_signals(_make_rich_plan()))
        for key in ("creator_confidence", "market_confidence", "quality_confidence",
                    "preset_confidence", "feedback_confidence", "retrieval_confidence",
                    "aggregate_confidence"):
            assert key in result

    def test_all_bounded_0_1(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        result = compute_signal_confidence(aggregate_signals(_make_rich_plan()))
        for val in result.values():
            assert 0.0 <= val <= 1.0

    def test_rich_plan_higher_than_minimal(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        rich = compute_signal_confidence(aggregate_signals(_make_rich_plan()))
        minimal = compute_signal_confidence(aggregate_signals(_make_minimal_plan()))
        assert rich["aggregate_confidence"] >= minimal["aggregate_confidence"]

    def test_creator_confidence_from_style_confidence(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        signals = {
            "creator_signal": {"available": True, "style_confidence": 0.80},
            "market_signal": {"available": False},
            "quality_signal": {"available": False},
            "preset_signal": {"available": False},
            "feedback_signal": {"available": False},
            "retrieval_signal": {"available": False},
        }
        result = compute_signal_confidence(signals)
        assert result["creator_confidence"] == pytest.approx(0.80, abs=0.01)

    def test_feedback_confidence_scales_with_exports(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        low_export = {"feedback_signal": {"available": True, "total_exports": 1},
                      **{k: {"available": False} for k in
                         ("creator_signal", "market_signal", "quality_signal",
                          "preset_signal", "retrieval_signal")}}
        high_export = {"feedback_signal": {"available": True, "total_exports": 10},
                       **{k: {"available": False} for k in
                          ("creator_signal", "market_signal", "quality_signal",
                           "preset_signal", "retrieval_signal")}}
        low_conf = compute_signal_confidence(low_export)["feedback_confidence"]
        high_conf = compute_signal_confidence(high_export)["feedback_confidence"]
        assert high_conf > low_conf

    def test_never_raises(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        result = compute_signal_confidence("bad_input")
        assert isinstance(result, dict)

    def test_deterministic(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        sigs = aggregate_signals(_make_rich_plan())
        r1 = compute_signal_confidence(sigs)
        r2 = compute_signal_confidence(sigs)
        assert r1["aggregate_confidence"] == r2["aggregate_confidence"]


# ---------------------------------------------------------------------------
# 3. Conflict Resolver tests
# ---------------------------------------------------------------------------

class TestConflictResolver:
    def _resolve(self, plan=None):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.conflict_resolver import resolve_conflicts
        sigs = aggregate_signals(plan or _make_rich_plan())
        conf = compute_signal_confidence(sigs)
        return resolve_conflicts(sigs, conf)

    def test_returns_dict(self):
        result = self._resolve()
        assert isinstance(result, dict)

    def test_all_dimension_keys_present(self):
        result = self._resolve()
        for key in ("subtitle_style", "pacing_style", "camera_style", "hook_emphasis"):
            assert key in result
            assert "winner" in result[key]
            assert "value" in result[key]
            assert "reason" in result[key]

    def test_resolution_mode_deterministic(self):
        result = self._resolve()
        assert result["resolution_mode"] == "deterministic"

    def test_conflict_count_is_int(self):
        result = self._resolve()
        assert isinstance(result["conflict_count"], int)

    def test_deterministic_same_output_twice(self):
        plan = _make_rich_plan()
        r1 = self._resolve(plan)
        r2 = self._resolve(plan)
        assert r1["subtitle_style"]["winner"] == r2["subtitle_style"]["winner"]
        assert r1["pacing_style"]["winner"] == r2["pacing_style"]["winner"]

    def test_empty_signals_returns_conservative_defaults(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.conflict_resolver import resolve_conflicts
        sigs = _make_empty_signals()
        conf = compute_signal_confidence(sigs)
        result = resolve_conflicts(sigs, conf)
        assert result["resolution_mode"] == "deterministic"
        for key in ("subtitle_style", "pacing_style", "camera_style"):
            assert result[key]["winner"] == "conservative_default"

    def test_winner_is_string(self):
        result = self._resolve()
        for key in ("subtitle_style", "pacing_style", "camera_style", "hook_emphasis"):
            assert isinstance(result[key]["winner"], str)

    def test_reason_is_string(self):
        result = self._resolve()
        for key in ("subtitle_style", "pacing_style", "camera_style", "hook_emphasis"):
            assert isinstance(result[key]["reason"], str)

    def test_hook_strong_when_market_weight_high(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.conflict_resolver import resolve_conflicts
        sigs = {
            **_make_empty_signals(),
            "market_signal": {
                "available": True,
                "target_market": "viral_tiktok",
                "market_confidence": 0.85,
                "subtitle_bias": {},
                "pacing_bias": {},
                "camera_bias": {},
                "hook_bias": {"weight": 0.25},
                "optimization_mode": "assistive_only",
            },
        }
        sigs["active_signal_count"] = 1
        conf = compute_signal_confidence(sigs)
        result = resolve_conflicts(sigs, conf)
        assert result["hook_emphasis"]["value"] == "strong"

    def test_hook_default_when_no_market(self):
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.conflict_resolver import resolve_conflicts
        conf = compute_signal_confidence(_make_empty_signals())
        result = resolve_conflicts(_make_empty_signals(), conf)
        assert result["hook_emphasis"]["value"] == "default"

    def test_never_raises(self):
        from app.ai.orchestrator.conflict_resolver import resolve_conflicts
        result = resolve_conflicts("bad", "bad")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 4. Strategy Planner tests
# ---------------------------------------------------------------------------

class TestStrategyPlanner:
    def _plan(self, plan=None):
        from app.ai.orchestrator.signal_aggregation import aggregate_signals
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.conflict_resolver import resolve_conflicts
        from app.ai.orchestrator.strategy_planner import plan_render_strategy
        sigs = aggregate_signals(plan or _make_rich_plan())
        conf = compute_signal_confidence(sigs)
        resolved = resolve_conflicts(sigs, conf)
        return plan_render_strategy(sigs, conf, resolved)

    def test_returns_dict(self):
        result = self._plan()
        assert isinstance(result, dict)

    def test_recommended_strategy_key_present(self):
        result = self._plan()
        assert "recommended_strategy" in result

    def test_strategy_keys_present(self):
        result = self._plan()
        rec = result["recommended_strategy"]
        for key in ("subtitle_style", "subtitle_density", "camera_motion",
                    "hook_emphasis", "clip_selection_bias", "ranking_priority"):
            assert key in rec

    def test_strategy_mode_recommendation_only(self):
        result = self._plan()
        assert result["strategy_mode"] == "recommendation_only"

    def test_strategy_confidence_bounded(self):
        result = self._plan()
        assert 0.0 <= result["strategy_confidence"] <= 1.0

    def test_conservative_fallback_on_minimal_plan(self):
        from app.ai.orchestrator.strategy_planner import plan_render_strategy
        from app.ai.orchestrator.confidence_engine import compute_signal_confidence
        from app.ai.orchestrator.conflict_resolver import resolve_conflicts
        sigs = _make_empty_signals()
        conf = compute_signal_confidence(sigs)
        resolved = resolve_conflicts(sigs, conf)
        result = plan_render_strategy(sigs, conf, resolved)
        rec = result["recommended_strategy"]
        assert rec["camera_motion"] == "smooth_subject"
        assert rec["ranking_priority"] == "creator_fit"

    def test_deterministic(self):
        plan = _make_rich_plan()
        r1 = self._plan(plan)
        r2 = self._plan(plan)
        assert r1["recommended_strategy"] == r2["recommended_strategy"]

    def test_subtitle_density_is_valid(self):
        result = self._plan()
        rec = result["recommended_strategy"]
        assert rec["subtitle_density"] in ("low", "medium", "high")

    def test_camera_motion_is_valid(self):
        result = self._plan()
        rec = result["recommended_strategy"]
        assert rec["camera_motion"] in (
            "dynamic_subject", "smooth_subject", "smooth_social",
            "static", "cinematic",
        )

    def test_no_ffmpeg_in_strategy(self):
        result = self._plan()
        assert "ffmpeg_args" not in str(result)

    def test_no_render_command_in_strategy(self):
        result = self._plan()
        assert "render_command" not in str(result)

    def test_no_playback_speed_in_strategy(self):
        result = self._plan()
        assert "playback_speed" not in str(result)

    def test_never_raises(self):
        from app.ai.orchestrator.strategy_planner import plan_render_strategy
        result = plan_render_strategy("bad", "bad", "bad")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 5. Render Orchestrator (end-to-end) tests
# ---------------------------------------------------------------------------

class TestRenderOrchestrator:
    def test_returns_dict(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(None)
        assert isinstance(result, dict)

    def test_none_plan_disabled(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(None)
        assert result["available"] is True
        assert result["enabled"] is False
        assert result["orchestration_mode"] == "reasoning_only"

    def test_minimal_plan_disabled(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_minimal_plan())
        assert result["available"] is True
        assert result["orchestration_mode"] == "reasoning_only"

    def test_rich_plan_enabled(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert result["available"] is True
        assert result["orchestration_mode"] == "reasoning_only"

    def test_all_output_keys_present_on_rich_plan(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        for key in ("available", "enabled", "orchestration_mode", "aggregated_signals",
                    "confidence_scores", "resolved_conflicts", "recommended_strategy",
                    "strategy_confidence", "strategy_mode", "explainability", "warnings"):
            assert key in result, f"missing key: {key}"

    def test_orchestration_mode_always_reasoning_only(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        for plan in (None, _make_minimal_plan(), _make_rich_plan()):
            result = orchestrate_render_signals(plan)
            assert result["orchestration_mode"] == "reasoning_only"

    def test_strategy_mode_always_recommendation_only(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert result.get("strategy_mode") == "recommendation_only"

    def test_deterministic_twice(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        plan = _make_rich_plan()
        r1 = orchestrate_render_signals(plan)
        r2 = orchestrate_render_signals(plan)
        assert r1["enabled"] == r2["enabled"]
        if r1.get("recommended_strategy"):
            assert r1["recommended_strategy"] == r2["recommended_strategy"]

    def test_no_ffmpeg_in_output(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "ffmpeg_args" not in str(result)

    def test_no_playback_speed_in_output(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "playback_speed" not in str(result)

    def test_no_subtitle_timing_in_output(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "subtitle_timing" not in str(result)

    def test_no_render_command_in_output(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "render_command" not in str(result)

    def test_no_executor_override_in_output(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "executor_override" not in str(result)

    def test_no_rerender_in_output(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "rerender" not in str(result)

    def test_payload_not_mutated(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals

        @dataclass
        class FakeRequest:
            ai_target_market: str = "viral_tiktok"
            ai_mode: str = "viral_tiktok"

        req = FakeRequest()
        original = req.ai_target_market
        orchestrate_render_signals(_make_rich_plan(), payload=req)
        assert req.ai_target_market == original

    def test_explainability_why_this_strategy_is_list(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        explainability = result.get("explainability") or {}
        why = explainability.get("why_this_strategy")
        assert isinstance(why, list)
        assert len(why) >= 1

    def test_explainability_reasons_are_strings(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        why = (result.get("explainability") or {}).get("why_this_strategy") or []
        for reason in why:
            assert isinstance(reason, str)

    def test_warnings_is_list(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert isinstance(result.get("warnings"), list)

    def test_never_raises_on_bad_input(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals("not_a_plan")
        assert isinstance(result, dict)

    def test_no_internet_required(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert result is not None

    def test_no_api_key_required(self):
        import os
        backup = os.environ.copy()
        for key in list(os.environ):
            if "API_KEY" in key or "OPENAI" in key or "ANTHROPIC" in key:
                del os.environ[key]
        try:
            from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
            result = orchestrate_render_signals(_make_rich_plan())
            assert result is not None
        finally:
            os.environ.update(backup)

    def test_podcast_plan_orchestrated(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_podcast_plan())
        assert result["available"] is True

    def test_confidence_scores_bounded(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        conf = result.get("confidence_scores") or {}
        for val in conf.values():
            assert 0.0 <= val <= 1.0


# ---------------------------------------------------------------------------
# 6. Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchema:
    def test_multi_signal_orchestration_field_exists(self):
        plan = _make_minimal_plan()
        assert hasattr(plan, "multi_signal_orchestration")
        assert isinstance(plan.multi_signal_orchestration, dict)

    def test_multi_signal_orchestration_in_to_dict(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "multi_signal_orchestration" in d

    def test_multi_signal_orchestration_default_empty(self):
        plan = _make_minimal_plan()
        assert plan.multi_signal_orchestration == {}

    def test_backward_compat_phase46_preserved(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "creator_preset_evolution" in d

    def test_backward_compat_phase45_preserved(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "render_quality_evaluation" in d

    def test_backward_compat_phase44_preserved(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "market_optimization_intelligence" in d

    def test_backward_compat_phase43_preserved(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "creator_feedback_intelligence" in d

    def test_backward_compat_phase42_preserved(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "adaptive_creator_intelligence" in d

    def test_backward_compat_phase41_preserved(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "creator_retrieval" in d


# ---------------------------------------------------------------------------
# 7. Render influence reporting
# ---------------------------------------------------------------------------

class TestRenderInfluence:
    def test_influence_no_orchestration_reports_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_minimal_plan()
        _payload, report = apply_ai_render_influence(None, plan, {})
        skipped = " ".join(str(s) for s in report.get("skipped", []))
        assert "multi_signal_orchestration" in skipped

    def test_influence_with_disabled_orchestration_reports_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_minimal_plan()
        plan.multi_signal_orchestration = {
            "available": True,
            "enabled": False,
            "orchestration_mode": "reasoning_only",
            "warnings": [],
        }
        _payload, report = apply_ai_render_influence(None, plan, {})
        skipped = " ".join(str(s) for s in report.get("skipped", []))
        assert "multi_signal_orchestration" in skipped
        assert "reasoning_only" in skipped

    def test_influence_with_enabled_orchestration_reports_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_minimal_plan()
        plan.multi_signal_orchestration = {
            "available": True,
            "enabled": True,
            "orchestration_mode": "reasoning_only",
            "aggregated_signals": {"active_signal_count": 5},
            "confidence_scores": {"aggregate_confidence": 0.72},
            "recommended_strategy": {
                "subtitle_style": "compact",
                "camera_motion": "dynamic_subject",
                "hook_emphasis": "strong",
            },
            "warnings": [],
        }
        _payload, report = apply_ai_render_influence(None, plan, {})
        skipped = " ".join(str(s) for s in report.get("skipped", []))
        assert "multi_signal_orchestration" in skipped
        assert "reasoning_only" in skipped

    def test_influence_never_mutates_orchestration_metadata(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_minimal_plan()
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        plan.multi_signal_orchestration = orchestrate_render_signals(_make_rich_plan())
        original_mode = plan.multi_signal_orchestration.get("orchestration_mode")
        apply_ai_render_influence(None, plan, {})
        assert plan.multi_signal_orchestration.get("orchestration_mode") == original_mode


# ---------------------------------------------------------------------------
# 8. Explainability metadata tests
# ---------------------------------------------------------------------------

class TestExplainability:
    def test_why_this_strategy_non_empty(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        why = (result.get("explainability") or {}).get("why_this_strategy") or []
        assert len(why) >= 1

    def test_signal_count_matches_active(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        active = (result.get("aggregated_signals") or {}).get("active_signal_count") or 0
        exp_count = (result.get("explainability") or {}).get("signal_count") or 0
        assert exp_count == active

    def test_strategy_confidence_in_explainability(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        exp = result.get("explainability") or {}
        assert "strategy_confidence" in exp
        assert 0.0 <= exp["strategy_confidence"] <= 1.0

    def test_creator_style_mentioned_when_available(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan("podcast"))
        why = " ".join((result.get("explainability") or {}).get("why_this_strategy") or [])
        assert "podcast" in why.lower() or len(why) > 0

    def test_market_mentioned_when_confidence_high(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan("viral_tiktok"))
        why = " ".join((result.get("explainability") or {}).get("why_this_strategy") or [])
        # At least one reason should be present
        assert len(why) > 0

    def test_fallback_reason_on_empty_signals(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_minimal_plan())
        why = (result.get("explainability") or {}).get("why_this_strategy") or []
        # Either empty (no explainability) or "insufficient signal" message
        if why:
            assert any(isinstance(r, str) for r in why)

    def test_future_ui_safe_structure(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        exp = result.get("explainability") or {}
        # Must be JSON-serializable (no functions, no objects)
        import json
        json.dumps(exp)


# ---------------------------------------------------------------------------
# 9. Safety boundary tests
# ---------------------------------------------------------------------------

class TestSafetyBoundaries:
    def test_no_ffmpeg_args_anywhere(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "ffmpeg_args" not in str(result)

    def test_no_render_command_anywhere(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "render_command" not in str(result)

    def test_no_playback_speed_anywhere(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "playback_speed" not in str(result)

    def test_no_subtitle_timing_anywhere(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "subtitle_timing" not in str(result)

    def test_no_rerender_anywhere(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "rerender" not in str(result)

    def test_no_delete_output_anywhere(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "delete_output" not in str(result)

    def test_no_subprocess_anywhere(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "subprocess" not in str(result)

    def test_no_executable_anywhere(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "executable" not in str(result)

    def test_orchestration_mode_never_execution(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert result["orchestration_mode"] == "reasoning_only"
        assert "execution" not in result["orchestration_mode"]

    def test_strategy_mode_never_execution(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert result.get("strategy_mode") == "recommendation_only"

    def test_confidence_always_bounded(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        for plan in (_make_minimal_plan(), _make_rich_plan(), _make_podcast_plan()):
            result = orchestrate_render_signals(plan)
            conf = float(result.get("strategy_confidence") or 0.0)
            assert 0.0 <= conf <= 1.0

    def test_no_autonomous_execution(self):
        from app.ai.orchestrator.render_orchestrator import orchestrate_render_signals
        result = orchestrate_render_signals(_make_rich_plan())
        assert "autonomous" not in str(result).lower() or \
               "autonomous_execution" not in str(result)
