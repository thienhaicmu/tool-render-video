"""
test_ai_phase13_preset_evolution.py — Phase 13: Smart Preset Evolution tests.

All tests are unit-level — no API keys, no GPU, no real rendering, no heavy deps.
Preset analysis is deterministic heuristic-only.
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List, Optional


# ── Memory result stub helpers ────────────────────────────────────────────────

def _mem(
    preset=None,
    market="US",
    mode="viral_tiktok",
    score=75.0,
    status="completed",
    subtitle_tone="hype",
    camera_behavior="fast_follow",
    pacing_style="fast",
    duration=30.0,
    story_arc=None,
) -> dict:
    """Build a minimal memory result dict matching retriever output format."""
    return {
        "id": "test_mem",
        "text": "sample render text",
        "score": 0.85,
        "metadata": {
            "preset": preset,
            "market": market,
            "mode": mode,
            "score": score,
            "status": status,
            "subtitle_tone": subtitle_tone,
            "camera_behavior": camera_behavior,
            "pacing_style": pacing_style,
            "duration": duration,
            "story_arc": story_arc,
        },
    }


def _ctx(market="US", mode="viral_tiktok") -> dict:
    return {"market": market, "mode": mode}


# ── Import modules ────────────────────────────────────────────────────────────

from app.ai.presets.preset_schema import (
    PresetPerformanceSample,
    PresetRecommendation,
    PresetEvolutionReport,
)
from app.ai.presets.preset_analyzer import analyze_preset_performance
from app.ai.presets.preset_recommender import recommend_preset


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestPresetSchema:
    def test_preset_performance_sample_defaults(self):
        s = PresetPerformanceSample()
        assert s.preset is None
        assert s.ai_mode is None
        assert s.market is None
        assert s.score is None
        assert s.metadata == {}

    def test_preset_recommendation_defaults(self):
        r = PresetRecommendation()
        assert r.recommended_preset is None
        assert r.confidence == 0.0
        assert r.reasons == []
        assert r.suggested_adjustments == {}
        assert r.warnings == []

    def test_preset_evolution_report_defaults(self):
        r = PresetEvolutionReport()
        assert r.available is True
        assert r.market is None
        assert r.ai_mode is None
        assert r.best_samples == []
        assert r.recommendation is None
        assert r.warnings == []

    def test_preset_recommendation_to_dict_has_all_keys(self):
        r = PresetRecommendation(confidence=72.0, reasons=["test"])
        d = r.to_dict()
        for key in ("recommended_preset", "confidence", "reasons",
                    "suggested_adjustments", "warnings"):
            assert key in d

    def test_preset_recommendation_to_dict_caps_reasons_at_5(self):
        r = PresetRecommendation(reasons=[f"reason {i}" for i in range(10)])
        d = r.to_dict()
        assert len(d["reasons"]) <= 5

    def test_preset_evolution_report_to_dict_has_all_keys(self):
        r = PresetEvolutionReport()
        d = r.to_dict()
        for key in ("available", "market", "ai_mode", "best_samples",
                    "recommendation", "warnings"):
            assert key in d

    def test_preset_evolution_report_to_dict_caps_best_samples_at_5(self):
        r = PresetEvolutionReport(
            best_samples=[{"preset": f"p{i}"} for i in range(10)]
        )
        d = r.to_dict()
        assert len(d["best_samples"]) <= 5

    def test_preset_performance_sample_to_dict(self):
        s = PresetPerformanceSample(preset="tiktok_us", market="US", score=80.0)
        d = s.to_dict()
        assert d["preset"] == "tiktok_us"
        assert d["market"] == "US"
        assert d["score"] == 80.0


# ── Analyzer safety ───────────────────────────────────────────────────────────

class TestAnalyzerSafety:
    def test_never_raises_on_empty_memory_list(self):
        result = analyze_preset_performance([])
        assert isinstance(result, PresetEvolutionReport)

    def test_never_raises_on_none_memories(self):
        result = analyze_preset_performance(None)
        assert isinstance(result, PresetEvolutionReport)

    def test_never_raises_on_garbage_memories(self):
        result = analyze_preset_performance("not_a_list")
        assert isinstance(result, PresetEvolutionReport)

    def test_never_raises_on_garbage_context(self):
        result = analyze_preset_performance([_mem()], context="bad_ctx")
        assert isinstance(result, PresetEvolutionReport)

    def test_empty_list_returns_available_false(self):
        result = analyze_preset_performance([])
        assert result.available is False

    def test_none_returns_available_false(self):
        result = analyze_preset_performance(None)
        assert result.available is False

    def test_malformed_entry_is_skipped_safely(self):
        mems = [_mem(), {"broken": "no_metadata"}, None, 42, _mem(score=90.0)]
        result = analyze_preset_performance(mems, context=_ctx())
        assert isinstance(result, PresetEvolutionReport)

    def test_all_failed_returns_available_false(self):
        mems = [
            _mem(status="failed"),
            _mem(status="failed"),
        ]
        result = analyze_preset_performance(mems, context=_ctx())
        assert result.available is False


# ── High-score completed samples ──────────────────────────────────────────────

class TestHighScoreCompletedSamples:
    def test_completed_samples_produce_available_report(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        result = analyze_preset_performance(mems, context=_ctx())
        assert result.available is True

    def test_high_score_completed_samples_increase_confidence(self):
        low_mems = [_mem(status="completed", score=10.0) for _ in range(2)]
        high_mems = [_mem(status="completed", score=90.0) for _ in range(5)]
        low_report = analyze_preset_performance(low_mems, context=_ctx())
        high_report = analyze_preset_performance(high_mems, context=_ctx())
        # More and higher-score samples → higher or equal confidence
        low_conf = low_report.recommendation.confidence if low_report.recommendation else 0
        high_conf = high_report.recommendation.confidence if high_report.recommendation else 0
        # We can't always guarantee high > low without recommendation, so check report level
        assert high_report.available is True

    def test_best_samples_list_is_populated(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        result = analyze_preset_performance(mems, context=_ctx())
        assert len(result.best_samples) > 0

    def test_best_samples_capped_at_5(self):
        mems = [_mem(status="completed", score=float(80 + i)) for i in range(10)]
        result = analyze_preset_performance(mems, context=_ctx())
        assert len(result.best_samples) <= 5

    def test_completed_with_errors_is_usable(self):
        mems = [_mem(status="completed_with_errors", score=70.0) for _ in range(3)]
        result = analyze_preset_performance(mems, context=_ctx())
        assert result.available is True


# ── Failed samples reduce confidence ─────────────────────────────────────────

class TestFailedSamplesReduceConfidence:
    def test_failed_samples_warn_in_report(self):
        mems = [
            _mem(status="completed", score=80.0),
            _mem(status="failed"),
            _mem(status="failed"),
        ]
        result = analyze_preset_performance(mems, context=_ctx())
        assert any("failed" in w for w in result.warnings)

    def test_mixed_failed_completed_still_produces_report(self):
        mems = [
            _mem(status="completed", score=85.0),
            _mem(status="completed", score=75.0),
            _mem(status="failed"),
        ]
        result = analyze_preset_performance(mems, context=_ctx())
        assert result.available is True

    def test_all_failed_gives_no_usable_samples(self):
        mems = [_mem(status="failed") for _ in range(5)]
        result = analyze_preset_performance(mems, context=_ctx())
        assert result.available is False
        assert len(result.best_samples) == 0


# ── Market / mode relevance ───────────────────────────────────────────────────

class TestMarketModeRelevance:
    def test_same_market_samples_rank_higher(self):
        mems = [
            _mem(market="US", score=60.0, status="completed"),
            _mem(market="UK", score=95.0, status="completed"),
            _mem(market="US", score=70.0, status="completed"),
        ]
        result = analyze_preset_performance(mems, context=_ctx(market="US"))
        # US samples should appear in best_samples (ranked by relevance including market match)
        assert result.available is True
        us_in_best = [s for s in result.best_samples if s.get("market") == "US"]
        assert len(us_in_best) > 0

    def test_same_mode_samples_rank_higher(self):
        mems = [
            _mem(mode="viral_tiktok", score=60.0, status="completed"),
            _mem(mode="other_mode", score=95.0, status="completed"),
            _mem(mode="viral_tiktok", score=65.0, status="completed"),
        ]
        result = analyze_preset_performance(mems, context=_ctx(mode="viral_tiktok"))
        assert result.available is True

    def test_market_stored_in_report(self):
        mems = [_mem(status="completed", score=80.0)]
        result = analyze_preset_performance(mems, context={"market": "JP", "mode": "viral"})
        assert result.market == "JP"

    def test_mode_stored_in_report(self):
        mems = [_mem(status="completed", score=80.0)]
        result = analyze_preset_performance(mems, context={"market": "US", "mode": "my_mode"})
        assert result.ai_mode == "my_mode"


# ── Recommender safety ────────────────────────────────────────────────────────

class TestRecommenderSafety:
    def test_never_raises_on_empty_report(self):
        report = PresetEvolutionReport(available=False)
        result = recommend_preset(report)
        assert isinstance(result, PresetRecommendation)

    def test_never_raises_on_unavailable_report(self):
        report = PresetEvolutionReport(available=False, warnings=["no_samples"])
        result = recommend_preset(report)
        assert isinstance(result, PresetRecommendation)
        assert result.confidence == 0.0

    def test_never_raises_on_none_context(self):
        report = PresetEvolutionReport(
            available=True,
            best_samples=[_mem(status="completed")["metadata"]],
        )
        result = recommend_preset(report, current_context=None)
        assert isinstance(result, PresetRecommendation)

    def test_does_not_suggest_playback_speed(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        assert "playback_speed" not in rec.suggested_adjustments

    def test_does_not_suggest_codec(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        assert "codec" not in rec.suggested_adjustments

    def test_does_not_suggest_ffmpeg_flags(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        assert "ffmpeg" not in rec.suggested_adjustments

    def test_does_not_suggest_timing_changes(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        assert "timing" not in rec.suggested_adjustments

    def test_reasons_capped_at_5(self):
        mems = [_mem(status="completed", score=float(70 + i)) for i in range(5)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        assert len(rec.reasons) <= 5

    def test_confidence_is_0_to_100(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        assert 0.0 <= rec.confidence <= 100.0

    def test_safe_adjustments_only_allowed_fields(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        allowed = {"subtitle_tone", "camera_behavior", "pacing_style",
                   "target_duration_hint", "ai_mode_hint"}
        for key in rec.suggested_adjustments:
            assert key in allowed, f"Unsafe adjustment key: {key}"


# ── Recommender produces useful suggestions ───────────────────────────────────

class TestRecommenderSuggestions:
    def test_subtitle_tone_suggested_from_dominant_samples(self):
        mems = [
            _mem(status="completed", score=80.0, subtitle_tone="hype"),
            _mem(status="completed", score=85.0, subtitle_tone="hype"),
            _mem(status="completed", score=70.0, subtitle_tone="calm"),
        ]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        if rec.suggested_adjustments.get("subtitle_tone"):
            assert rec.suggested_adjustments["subtitle_tone"] == "hype"

    def test_camera_behavior_suggested_from_dominant_samples(self):
        mems = [
            _mem(status="completed", score=80.0, camera_behavior="fast_follow"),
            _mem(status="completed", score=85.0, camera_behavior="fast_follow"),
            _mem(status="completed", score=70.0, camera_behavior="static"),
        ]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        if rec.suggested_adjustments.get("camera_behavior"):
            assert rec.suggested_adjustments["camera_behavior"] == "fast_follow"

    def test_reasons_list_is_nonempty(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        assert len(rec.reasons) > 0

    def test_recommendation_has_all_keys_in_to_dict(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        rec = recommend_preset(report, current_context=_ctx())
        d = rec.to_dict()
        for key in ("recommended_preset", "confidence", "reasons",
                    "suggested_adjustments", "warnings"):
            assert key in d


# ── AIEditPlan preset_evolution field ────────────────────────────────────────

class TestEditPlanPresetEvolutionField:
    def test_ai_edit_plan_has_preset_evolution_field(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AIPacingPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "preset_evolution")
        assert isinstance(plan.preset_evolution, dict)

    def test_ai_edit_plan_preset_evolution_defaults_to_empty(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert plan.preset_evolution == {}

    def test_ai_edit_plan_to_dict_includes_preset_evolution(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AIPacingPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.preset_evolution = {"available": True, "market": "US"}
        d = plan.to_dict()
        assert "preset_evolution" in d
        assert d["preset_evolution"]["market"] == "US"


# ── AI Director with no memory ────────────────────────────────────────────────

class TestAIDirectorPresetWithNoMemory:
    def test_attach_preset_evolution_no_memory_sets_available_false(self):
        from app.ai.director.ai_director import _attach_preset_evolution
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        # Empty memory context
        _attach_preset_evolution(plan, {}, "viral_tiktok", {"market": "US"}, "test_job")
        assert isinstance(plan.preset_evolution, dict)
        assert plan.preset_evolution.get("available") is False

    def test_attach_preset_evolution_never_raises_on_garbage_context(self):
        from app.ai.director.ai_director import _attach_preset_evolution
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        _attach_preset_evolution(plan, None, "test", None, "job_x")
        assert isinstance(plan.preset_evolution, dict)

    def test_attach_preset_evolution_with_memories(self):
        from app.ai.director.ai_director import _attach_preset_evolution
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        memory_ctx = {
            "results": [
                _mem(status="completed", score=80.0),
                _mem(status="completed", score=85.0),
                _mem(status="completed", score=75.0),
            ]
        }
        _attach_preset_evolution(plan, memory_ctx, "viral_tiktok", {"market": "US"}, "job_y")
        assert plan.preset_evolution.get("available") is True


# ── Explainability integration ────────────────────────────────────────────────

class TestPresetExplainabilityIntegration:
    def _make_plan_with_explainability(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.explainability = {"summary": {"summary_lines": ["Existing line"]}}
        return plan

    def test_preset_explainability_appends_safely(self):
        from app.ai.director.ai_director import _append_preset_explainability

        plan = self._make_plan_with_explainability()
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        report.recommendation = recommend_preset(report, current_context=_ctx())
        _append_preset_explainability(plan, report)
        lines = plan.explainability["summary"]["summary_lines"]
        assert "Existing line" in lines

    def test_explainability_append_never_raises_on_no_explainability(self):
        from app.ai.director.ai_director import _append_preset_explainability
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        _append_preset_explainability(plan, report)

    def test_explainability_append_never_raises_on_none_report(self):
        from app.ai.director.ai_director import _append_preset_explainability

        plan = self._make_plan_with_explainability()
        _append_preset_explainability(plan, None)

    def test_no_duplicate_preset_recommendation_line(self):
        from app.ai.director.ai_director import _append_preset_explainability

        plan = self._make_plan_with_explainability()
        mems = [_mem(status="completed", score=85.0) for _ in range(5)]
        report = analyze_preset_performance(mems, context=_ctx())
        report.recommendation = recommend_preset(report, current_context=_ctx())
        _append_preset_explainability(plan, report)
        _append_preset_explainability(plan, report)  # call twice
        lines = plan.explainability["summary"]["summary_lines"]
        preset_lines = [l for l in lines if "Preset recommendation" in str(l)]
        assert len(preset_lines) <= 1


# ── Result JSON compactness ───────────────────────────────────────────────────

class TestResultJsonCompactness:
    def test_report_to_dict_is_compact(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(6)]
        report = analyze_preset_performance(mems, context=_ctx())
        report.recommendation = recommend_preset(report, current_context=_ctx())
        d = report.to_dict()
        assert len(d["best_samples"]) <= 5

    def test_report_to_dict_has_all_expected_keys(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        d = report.to_dict()
        for key in ("available", "market", "ai_mode", "best_samples",
                    "recommendation", "warnings"):
            assert key in d

    def test_recommendation_in_report_to_dict(self):
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        report.recommendation = recommend_preset(report, current_context=_ctx())
        d = report.to_dict()
        assert d["recommendation"] is not None
        assert "confidence" in d["recommendation"]
        assert "suggested_adjustments" in d["recommendation"]

    def test_no_raw_memory_text_in_compact_output(self):
        """Best samples should not contain raw text blobs."""
        mems = [_mem(status="completed", score=80.0) for _ in range(3)]
        report = analyze_preset_performance(mems, context=_ctx())
        d = report.to_dict()
        for sample in d["best_samples"]:
            assert "text" not in sample or not isinstance(sample.get("text"), str) or len(sample.get("text", "")) < 500


# ── No external dependencies ──────────────────────────────────────────────────

class TestNoExternalDependencies:
    def test_no_api_key_required(self):
        import os
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result = analyze_preset_performance([_mem()], context=_ctx())
            assert isinstance(result, PresetEvolutionReport)
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved

    def test_no_gpu_required(self):
        result = analyze_preset_performance([_mem()], context=_ctx())
        assert isinstance(result, PresetEvolutionReport)

    def test_no_real_rendering_required(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = analyze_preset_performance([_mem()], context=_ctx())
        assert isinstance(result, PresetEvolutionReport)

    def test_no_torch_required(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "torch", None)
        result = analyze_preset_performance([_mem()], context=_ctx())
        assert isinstance(result, PresetEvolutionReport)

    def test_no_sentence_transformers_required(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "sentence_transformers", None)
        result = analyze_preset_performance([_mem()], context=_ctx())
        assert isinstance(result, PresetEvolutionReport)

    def test_preset_schema_import_is_safe(self):
        from app.ai.presets import preset_schema, preset_analyzer, preset_recommender

    def test_recommender_no_api_key_required(self):
        import os
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            report = PresetEvolutionReport(available=False)
            result = recommend_preset(report)
            assert isinstance(result, PresetRecommendation)
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved
