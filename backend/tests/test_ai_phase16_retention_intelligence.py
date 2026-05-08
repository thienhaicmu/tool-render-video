"""
test_ai_phase16_retention_intelligence.py — Phase 16: Retention Intelligence Foundation.

Tests covering:
  - RetentionSchema (RetentionRiskRegion, RetentionAnalysis, RetentionRecommendation)
  - Dropoff detector heuristics (weak_hook, long_setup, pacing_decay, silence_gap,
    subtitle_overload, story_drop, unclear_payoff)
  - Retention analyzer (score computation, strengths, never raises)
  - Retention recommender (advisory only, safe_to_auto_apply locked False)
  - AIEditPlan retention field
  - AI Director integration
  - No external dependencies
"""
from __future__ import annotations

import pytest

from app.ai.retention.retention_schema import (
    RetentionRiskRegion,
    RetentionAnalysis,
    RetentionRecommendation,
    VALID_CATEGORIES,
    VALID_SEVERITIES,
)
from app.ai.retention.dropoff_detector import detect_retention_risks
from app.ai.retention.retention_analyzer import analyze_retention
from app.ai.retention.retention_recommender import build_retention_recommendations
from app.ai.director.edit_plan_schema import (
    AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan,
)
from app.ai.director.ai_director import (
    _attach_retention_intelligence,
    _append_retention_explainability,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_plan() -> AIEditPlan:
    return AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )


def _make_chunks(n: int = 5, duration: float = 30.0) -> list[dict]:
    step = duration / n
    return [
        {"text": f"word{i} content here", "start": round(i * step, 2), "end": round((i + 1) * step, 2)}
        for i in range(n)
    ]


def _make_hook_chunks() -> list[dict]:
    return [
        {"text": "Why is this the secret you never knew? Stop and watch!", "start": 0.0, "end": 3.0},
        {"text": "The truth will shock you — don't miss this reveal.", "start": 3.0, "end": 6.0},
        {"text": "Here's what nobody tells you about this topic.", "start": 6.0, "end": 9.0},
    ]


def _make_story_context_with_hook() -> dict:
    return {
        "available": True,
        "narrative_flow": "hook_to_climax",
        "segments": [
            {"segment_type": "hook", "start": 0.0, "end": 5.0, "confidence": 0.85, "emotion": "curiosity"},
            {"segment_type": "build_up", "start": 5.0, "end": 18.0, "confidence": 0.70, "emotion": "neutral"},
            {"segment_type": "climax", "start": 18.0, "end": 28.0, "confidence": 0.80, "emotion": "excitement"},
            {"segment_type": "payoff", "start": 28.0, "end": 33.0, "confidence": 0.75, "emotion": "satisfaction"},
        ],
        "dominant_arc": "hook_to_climax",
        "retention_score": 75.0,
        "warnings": [],
    }


def _make_story_context_no_hook_no_payoff() -> dict:
    return {
        "available": True,
        "narrative_flow": "front_loaded",
        "segments": [
            {"segment_type": "setup", "start": 0.0, "end": 15.0, "confidence": 0.60, "emotion": "neutral"},
            {"segment_type": "build_up", "start": 15.0, "end": 28.0, "confidence": 0.55, "emotion": "calm"},
        ],
        "dominant_arc": "front_loaded",
        "retention_score": 40.0,
        "warnings": [],
    }


def _make_pacing_high_energy() -> dict:
    return {
        "pacing_style": "fast",
        "energy_level": 0.80,
        "emotion": "excitement",
        "emotion_score": 0.75,
        "beat_available": True,
        "bpm": 135.0,
    }


def _make_pacing_low_energy() -> dict:
    return {
        "pacing_style": "slow",
        "energy_level": 0.25,
        "emotion": "calm",
        "emotion_score": 0.60,
        "beat_available": False,
        "bpm": None,
    }


def _make_risk_region(category="long_setup", severity="high", risk=0.70) -> RetentionRiskRegion:
    return RetentionRiskRegion(
        start=5.0,
        end=20.0,
        risk=risk,
        reason="Test risk region",
        category=category,
        severity=severity,
        suggestions=["Fix this"],
    )


# ---------------------------------------------------------------------------
# 1. Retention Schema
# ---------------------------------------------------------------------------

class TestRetentionSchema:
    def test_risk_region_required_fields(self):
        r = RetentionRiskRegion(start=0.0, end=10.0, risk=0.5)
        assert r.start == 0.0
        assert r.end == 10.0
        assert r.risk == 0.5

    def test_risk_region_defaults(self):
        r = RetentionRiskRegion(start=0.0, end=5.0, risk=0.3)
        assert r.reason == ""
        assert r.category == "unknown"
        assert r.severity == "medium"
        assert r.suggestions == []

    def test_risk_region_to_dict_has_required_keys(self):
        r = _make_risk_region()
        d = r.to_dict()
        for key in ("start", "end", "risk", "reason", "category", "severity", "suggestions"):
            assert key in d

    def test_risk_region_to_dict_caps_suggestions_at_3(self):
        r = RetentionRiskRegion(start=0.0, end=5.0, risk=0.5, suggestions=["a", "b", "c", "d", "e"])
        d = r.to_dict()
        assert len(d["suggestions"]) <= 3

    def test_retention_analysis_defaults(self):
        a = RetentionAnalysis()
        assert a.available is True
        assert a.overall_retention_score == 0.0
        assert a.risk_regions == []
        assert a.strengths == []
        assert a.warnings == []

    def test_retention_analysis_to_dict_has_required_keys(self):
        a = RetentionAnalysis()
        d = a.to_dict()
        for key in ("available", "overall_retention_score", "risk_regions", "strengths", "warnings"):
            assert key in d

    def test_retention_analysis_to_dict_caps_risk_regions_at_10(self):
        a = RetentionAnalysis(
            risk_regions=[RetentionRiskRegion(start=i, end=i+1, risk=0.5) for i in range(15)]
        )
        d = a.to_dict()
        assert len(d["risk_regions"]) <= 10

    def test_retention_analysis_to_dict_caps_strengths_at_6(self):
        a = RetentionAnalysis(strengths=["s1", "s2", "s3", "s4", "s5", "s6", "s7", "s8"])
        d = a.to_dict()
        assert len(d["strengths"]) <= 6

    def test_retention_recommendation_defaults(self):
        rec = RetentionRecommendation()
        assert rec.priority == "medium"
        assert rec.recommended_action == ""
        assert rec.reason == ""
        assert rec.safe_to_auto_apply is False
        assert rec.metadata == {}

    def test_retention_recommendation_to_dict_safe_to_auto_apply_always_false(self):
        rec = RetentionRecommendation(safe_to_auto_apply=True)  # attempt to set True
        d = rec.to_dict()
        assert d["safe_to_auto_apply"] is False  # structurally locked

    def test_retention_recommendation_to_dict_has_required_keys(self):
        rec = RetentionRecommendation(priority="high", recommended_action="Do something")
        d = rec.to_dict()
        for key in ("priority", "recommended_action", "reason", "safe_to_auto_apply", "metadata"):
            assert key in d

    def test_valid_categories_contains_required(self):
        required = {
            "weak_hook", "long_setup", "low_energy", "silence_gap",
            "subtitle_overload", "story_drop", "unclear_payoff", "pacing_decay", "unknown",
        }
        assert required.issubset(VALID_CATEGORIES)

    def test_valid_severities_contains_required(self):
        assert {"low", "medium", "high"}.issubset(VALID_SEVERITIES)


# ---------------------------------------------------------------------------
# 2. Dropoff Detector
# ---------------------------------------------------------------------------

class TestDropoffDetector:
    def test_never_raises_on_none_args(self):
        result = detect_retention_risks(None, None, None, None, None)
        assert isinstance(result, list)

    def test_never_raises_on_empty_args(self):
        result = detect_retention_risks([], {}, {}, {}, {})
        assert isinstance(result, list)

    def test_never_raises_on_garbage_input(self):
        result = detect_retention_risks("string", 42, False, [], None)
        assert isinstance(result, list)

    def test_returns_list_of_risk_regions(self):
        result = detect_retention_risks(
            transcript_chunks=_make_chunks(),
            story_context=_make_story_context_no_hook_no_payoff(),
        )
        for r in result:
            assert isinstance(r, RetentionRiskRegion)

    def test_weak_hook_detected_when_no_hook_segment_and_no_keywords(self):
        boring_chunks = [
            {"text": "welcome to today content for everyone", "start": 0.0, "end": 3.0},
            {"text": "let us discuss some information here", "start": 3.0, "end": 6.0},
        ]
        result = detect_retention_risks(
            transcript_chunks=boring_chunks,
            story_context={"segments": [], "narrative_flow": "front_loaded"},
        )
        categories = {r.category for r in result}
        assert "weak_hook" in categories

    def test_weak_hook_not_detected_when_hook_segment_present(self):
        result = detect_retention_risks(
            transcript_chunks=_make_hook_chunks(),
            story_context=_make_story_context_with_hook(),
        )
        categories = {r.category for r in result}
        assert "weak_hook" not in categories

    def test_long_setup_detected_from_story_segments(self):
        long_setup_story = {
            "segments": [
                {"segment_type": "setup", "start": 0.0, "end": 15.0, "confidence": 0.6},
                {"segment_type": "build_up", "start": 15.0, "end": 28.0, "confidence": 0.6},
                {"segment_type": "outro", "start": 28.0, "end": 33.0, "confidence": 0.6},
            ],
            "narrative_flow": "front_loaded",
        }
        chunks = _make_chunks(duration=33.0)
        result = detect_retention_risks(transcript_chunks=chunks, story_context=long_setup_story)
        categories = {r.category for r in result}
        assert "long_setup" in categories

    def test_long_setup_not_detected_when_setup_is_short(self):
        short_setup_story = {
            "segments": [
                {"segment_type": "setup", "start": 0.0, "end": 3.0, "confidence": 0.7},
                {"segment_type": "climax", "start": 3.0, "end": 25.0, "confidence": 0.8},
                {"segment_type": "payoff", "start": 25.0, "end": 30.0, "confidence": 0.7},
            ],
            "narrative_flow": "hook_to_climax",
        }
        chunks = _make_chunks(duration=30.0)
        result = detect_retention_risks(transcript_chunks=chunks, story_context=short_setup_story)
        categories = {r.category for r in result}
        assert "long_setup" not in categories

    def test_pacing_decay_detected_on_low_energy_slow_pacing(self):
        chunks = _make_chunks(duration=40.0)
        story = {
            "segments": [
                {"segment_type": "climax", "start": 5.0, "end": 20.0, "confidence": 0.8},
                {"segment_type": "outro", "start": 28.0, "end": 40.0, "confidence": 0.6},
            ],
            "narrative_flow": "front_loaded",
        }
        result = detect_retention_risks(
            transcript_chunks=chunks,
            pacing_context=_make_pacing_low_energy(),
            story_context=story,
        )
        categories = {r.category for r in result}
        assert "pacing_decay" in categories

    def test_pacing_decay_not_detected_on_high_energy(self):
        chunks = _make_chunks(duration=30.0)
        result = detect_retention_risks(
            transcript_chunks=chunks,
            pacing_context=_make_pacing_high_energy(),
            story_context=_make_story_context_with_hook(),
        )
        categories = {r.category for r in result}
        assert "pacing_decay" not in categories

    def test_silence_gap_detected_from_chunk_timing(self):
        gap_chunks = [
            {"text": "first segment", "start": 0.0, "end": 5.0},
            {"text": "after long silence", "start": 9.0, "end": 14.0},  # 4.0s gap
        ]
        result = detect_retention_risks(transcript_chunks=gap_chunks)
        categories = {r.category for r in result}
        assert "silence_gap" in categories

    def test_silence_gap_not_detected_for_short_gaps(self):
        tight_chunks = [
            {"text": "first part", "start": 0.0, "end": 3.0},
            {"text": "second part", "start": 3.2, "end": 6.0},  # 0.2s gap — fine
        ]
        result = detect_retention_risks(transcript_chunks=tight_chunks)
        categories = {r.category for r in result}
        assert "silence_gap" not in categories

    def test_subtitle_overload_detected_from_high_density(self):
        chunks = _make_chunks()
        subtitle_ctx = {"density": "dense", "max_words_per_line": 10}
        result = detect_retention_risks(
            transcript_chunks=chunks,
            subtitle_context=subtitle_ctx,
        )
        categories = {r.category for r in result}
        assert "subtitle_overload" in categories

    def test_subtitle_overload_not_detected_on_normal_density(self):
        chunks = _make_chunks()
        subtitle_ctx = {"density": "normal", "max_words_per_line": 6}
        result = detect_retention_risks(
            transcript_chunks=chunks,
            subtitle_context=subtitle_ctx,
        )
        categories = {r.category for r in result}
        assert "subtitle_overload" not in categories

    def test_story_drop_detected_on_unclear_narrative(self):
        unclear_story = {
            "segments": [],
            "narrative_flow": "unclear",
        }
        result = detect_retention_risks(
            transcript_chunks=_make_chunks(duration=30.0),
            story_context=unclear_story,
        )
        categories = {r.category for r in result}
        assert "story_drop" in categories

    def test_story_drop_detected_on_unknown_middle_segment(self):
        unknown_mid_story = {
            "segments": [
                {"segment_type": "hook", "start": 0.0, "end": 5.0, "confidence": 0.8},
                {"segment_type": "unknown", "start": 12.0, "end": 22.0, "confidence": 0.4},
            ],
            "narrative_flow": "hook_to_climax",
        }
        result = detect_retention_risks(
            transcript_chunks=_make_chunks(duration=30.0),
            story_context=unknown_mid_story,
        )
        categories = {r.category for r in result}
        assert "story_drop" in categories

    def test_unclear_payoff_detected_when_no_payoff_in_long_video(self):
        no_payoff_story = {
            "segments": [
                {"segment_type": "hook", "start": 0.0, "end": 5.0, "confidence": 0.8},
                {"segment_type": "build_up", "start": 5.0, "end": 25.0, "confidence": 0.6},
            ],
            "narrative_flow": "front_loaded",
        }
        result = detect_retention_risks(
            transcript_chunks=_make_chunks(duration=30.0),
            story_context=no_payoff_story,
        )
        categories = {r.category for r in result}
        assert "unclear_payoff" in categories

    def test_unclear_payoff_not_detected_for_short_clips(self):
        no_payoff_story = {
            "segments": [{"segment_type": "setup", "start": 0.0, "end": 8.0, "confidence": 0.6}],
            "narrative_flow": "front_loaded",
        }
        result = detect_retention_risks(
            transcript_chunks=_make_chunks(n=3, duration=10.0),
            story_context=no_payoff_story,
        )
        categories = {r.category for r in result}
        assert "unclear_payoff" not in categories

    def test_risk_region_has_valid_severity(self):
        result = detect_retention_risks(
            transcript_chunks=[{"text": "hello", "start": 0.0, "end": 3.0}],
            story_context={"segments": [], "narrative_flow": "unclear"},
        )
        for r in result:
            assert r.severity in VALID_SEVERITIES

    def test_risk_region_has_valid_category(self):
        result = detect_retention_risks(
            transcript_chunks=[{"text": "hello", "start": 0.0, "end": 3.0}],
            story_context={"segments": [], "narrative_flow": "unclear"},
        )
        for r in result:
            assert r.category in VALID_CATEGORIES


# ---------------------------------------------------------------------------
# 3. Retention Analyzer
# ---------------------------------------------------------------------------

class TestRetentionAnalyzer:
    def test_never_raises_on_empty_input(self):
        result = analyze_retention()
        assert isinstance(result, RetentionAnalysis)

    def test_never_raises_on_none_input(self):
        result = analyze_retention(None, None, None, None, None, None)
        assert isinstance(result, RetentionAnalysis)

    def test_never_raises_on_garbage_input(self):
        result = analyze_retention("string", 42, False, [], "x", None)
        assert isinstance(result, RetentionAnalysis)

    def test_returns_retention_analysis(self):
        result = analyze_retention(transcript_chunks=_make_chunks())
        assert isinstance(result, RetentionAnalysis)

    def test_available_true_on_success(self):
        result = analyze_retention(transcript_chunks=_make_chunks())
        assert result.available is True

    def test_score_is_in_valid_range(self):
        result = analyze_retention(
            transcript_chunks=_make_chunks(duration=30.0),
            story_context=_make_story_context_no_hook_no_payoff(),
            pacing_context=_make_pacing_low_energy(),
        )
        assert 0.0 <= result.overall_retention_score <= 100.0

    def test_high_severity_risks_reduce_score(self):
        # Scenario with multiple high-severity risks
        boring_chunks = [
            {"text": "welcome to this video content today", "start": 0.0, "end": 30.0},
        ]
        bad_story = {
            "segments": [
                {"segment_type": "setup", "start": 0.0, "end": 25.0, "confidence": 0.5},
            ],
            "narrative_flow": "unclear",
        }
        result = analyze_retention(
            transcript_chunks=boring_chunks,
            pacing_context=_make_pacing_low_energy(),
            story_context=bad_story,
        )
        assert result.overall_retention_score < 70.0

    def test_strong_signals_increase_score(self):
        result = analyze_retention(
            transcript_chunks=_make_hook_chunks(),
            pacing_context=_make_pacing_high_energy(),
            story_context=_make_story_context_with_hook(),
            memory_context={"results": [{"id": "m1", "text": "prior render"}]},
        )
        assert result.overall_retention_score > 50.0

    def test_score_not_below_zero(self):
        # Worst-case scenario shouldn't go below 0
        bad_chunks = [{"text": "boring content here now", "start": 0.0, "end": 60.0}]
        bad_story = {
            "segments": [
                {"segment_type": "setup", "start": 0.0, "end": 40.0, "confidence": 0.3},
                {"segment_type": "outro", "start": 40.0, "end": 60.0, "confidence": 0.3},
            ],
            "narrative_flow": "unclear",
        }
        result = analyze_retention(
            transcript_chunks=bad_chunks,
            pacing_context=_make_pacing_low_energy(),
            story_context=bad_story,
            subtitle_context={"density": "dense", "max_words_per_line": 12},
        )
        assert result.overall_retention_score >= 0.0

    def test_score_not_above_100(self):
        result = analyze_retention(
            transcript_chunks=_make_hook_chunks(),
            pacing_context=_make_pacing_high_energy(),
            story_context=_make_story_context_with_hook(),
            memory_context={"results": [{"id": "m1"}, {"id": "m2"}, {"id": "m3"}]},
        )
        assert result.overall_retention_score <= 100.0

    def test_strong_hook_detected_as_strength(self):
        result = analyze_retention(
            transcript_chunks=_make_hook_chunks(),
            story_context=_make_story_context_with_hook(),
        )
        assert any("hook" in s for s in result.strengths)

    def test_high_energy_detected_as_strength(self):
        result = analyze_retention(
            transcript_chunks=_make_chunks(),
            pacing_context=_make_pacing_high_energy(),
            story_context=_make_story_context_with_hook(),
        )
        assert any("energy" in s for s in result.strengths)

    def test_memory_support_detected_as_strength(self):
        result = analyze_retention(
            transcript_chunks=_make_chunks(),
            memory_context={"results": [{"id": "m1", "text": "prior render success"}]},
        )
        assert any("memory" in s for s in result.strengths)

    def test_risk_regions_list_returned(self):
        result = analyze_retention(
            transcript_chunks=_make_chunks(duration=30.0),
            story_context=_make_story_context_no_hook_no_payoff(),
        )
        assert isinstance(result.risk_regions, list)

    def test_warnings_list_returned(self):
        result = analyze_retention()
        assert isinstance(result.warnings, list)


# ---------------------------------------------------------------------------
# 4. Retention Recommender
# ---------------------------------------------------------------------------

class TestRetentionRecommender:
    def test_never_raises_on_empty_analysis(self):
        result = build_retention_recommendations(RetentionAnalysis())
        assert isinstance(result, list)

    def test_never_raises_on_unavailable_analysis(self):
        analysis = RetentionAnalysis(available=False)
        result = build_retention_recommendations(analysis)
        assert isinstance(result, list)

    def test_returns_list_of_recommendations(self):
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[_make_risk_region("weak_hook", "high", 0.72)],
        )
        result = build_retention_recommendations(analysis)
        for r in result:
            assert isinstance(r, RetentionRecommendation)

    def test_safe_to_auto_apply_always_false(self):
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[
                _make_risk_region("weak_hook", "high", 0.72),
                _make_risk_region("long_setup", "high", 0.70),
                _make_risk_region("unclear_payoff", "high", 0.65),
            ],
        )
        recs = build_retention_recommendations(analysis)
        for rec in recs:
            assert rec.safe_to_auto_apply is False

    def test_safe_to_auto_apply_false_in_to_dict(self):
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[_make_risk_region("weak_hook", "high")],
        )
        recs = build_retention_recommendations(analysis)
        for rec in recs:
            assert rec.to_dict()["safe_to_auto_apply"] is False

    def test_max_6_recommendations(self):
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[
                _make_risk_region("weak_hook", "high", 0.72),
                _make_risk_region("long_setup", "high", 0.70),
                _make_risk_region("unclear_payoff", "high", 0.65),
                _make_risk_region("pacing_decay", "medium", 0.60),
                _make_risk_region("silence_gap", "medium", 0.52),
                _make_risk_region("subtitle_overload", "low", 0.38),
                _make_risk_region("story_drop", "medium", 0.55),
                _make_risk_region("unknown", "low", 0.30),
            ],
        )
        recs = build_retention_recommendations(analysis)
        assert len(recs) <= 6

    def test_weak_hook_gets_high_priority_recommendation(self):
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[_make_risk_region("weak_hook", "high", 0.72)],
        )
        recs = build_retention_recommendations(analysis)
        assert recs, "Expected at least one recommendation"
        assert recs[0].priority == "high"

    def test_no_duplicate_category_recommendations(self):
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[
                _make_risk_region("weak_hook", "high", 0.72),
                _make_risk_region("weak_hook", "medium", 0.45),  # duplicate category
            ],
        )
        recs = build_retention_recommendations(analysis)
        actions = [r.recommended_action for r in recs]
        # Only one recommendation per unique category
        assert len(set(actions)) == len(actions)

    def test_recommendations_are_advisory_text_only(self):
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[_make_risk_region("long_setup", "high", 0.70)],
        )
        recs = build_retention_recommendations(analysis)
        for rec in recs:
            assert isinstance(rec.recommended_action, str)
            assert rec.recommended_action  # not empty
            assert isinstance(rec.reason, str)

    def test_no_recs_when_no_risk_regions(self):
        analysis = RetentionAnalysis(available=True, risk_regions=[])
        recs = build_retention_recommendations(analysis)
        assert recs == []

    def test_priority_values_are_valid(self):
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[
                _make_risk_region("weak_hook", "high"),
                _make_risk_region("pacing_decay", "medium"),
                _make_risk_region("subtitle_overload", "low"),
            ],
        )
        recs = build_retention_recommendations(analysis)
        valid_priorities = {"high", "medium", "low"}
        for rec in recs:
            assert rec.priority in valid_priorities


# ---------------------------------------------------------------------------
# 5. AIEditPlan retention field
# ---------------------------------------------------------------------------

class TestEditPlanRetention:
    def test_ai_edit_plan_has_retention_field(self):
        plan = _make_plan()
        assert hasattr(plan, "retention")

    def test_retention_defaults_to_empty_dict(self):
        plan = _make_plan()
        assert plan.retention == {}

    def test_ai_edit_plan_to_dict_includes_retention(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "retention" in d

    def test_retention_value_propagated_to_to_dict(self):
        plan = _make_plan()
        plan.retention = {"available": True, "overall_retention_score": 74}
        d = plan.to_dict()
        assert d["retention"]["overall_retention_score"] == 74


# ---------------------------------------------------------------------------
# 6. AI Director Integration
# ---------------------------------------------------------------------------

class TestAIDirectorRetentionIntegration:
    def test_attach_sets_retention_dict(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        assert isinstance(plan.retention, dict)

    def test_attach_never_raises_on_empty_chunks(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, [], {}, "job1")
        assert isinstance(plan.retention, dict)

    def test_attach_never_raises_on_none_pacing(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        assert isinstance(plan.retention, dict)

    def test_retention_has_available_key(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        assert "available" in plan.retention

    def test_retention_has_overall_score_key(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        assert "overall_retention_score" in plan.retention

    def test_retention_has_risk_regions_key(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        assert "risk_regions" in plan.retention

    def test_retention_has_strengths_key(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        assert "strengths" in plan.retention

    def test_retention_has_recommendations_key(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        assert "recommendations" in plan.retention

    def test_risk_regions_capped_at_10(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(duration=30.0), {}, "job1")
        assert len(plan.retention.get("risk_regions", [])) <= 10

    def test_recommendations_capped_at_6(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(duration=30.0), {}, "job1")
        assert len(plan.retention.get("recommendations", [])) <= 6

    def test_all_recommendations_safe_to_auto_apply_false(self):
        plan = _make_plan()
        plan.story = _make_story_context_no_hook_no_payoff()
        _attach_retention_intelligence(plan, _make_chunks(duration=30.0), _make_pacing_low_energy(), "job1")
        for rec in plan.retention.get("recommendations", []):
            assert rec.get("safe_to_auto_apply") is False

    def test_explainability_append_never_raises_no_explainability(self):
        plan = _make_plan()
        analysis = RetentionAnalysis(available=True, risk_regions=[_make_risk_region()])
        _append_retention_explainability(plan, analysis)  # no explainability dict

    def test_explainability_line_added_for_risk(self):
        plan = _make_plan()
        plan.explainability = {"summary": {"summary_lines": []}}
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[_make_risk_region("long_setup", "high", 0.70)],
        )
        _append_retention_explainability(plan, analysis)
        lines = plan.explainability["summary"]["summary_lines"]
        assert any("setup" in l.lower() or "retention" in l.lower() for l in lines)

    def test_explainability_strength_line_added(self):
        plan = _make_plan()
        plan.explainability = {"summary": {"summary_lines": []}}
        analysis = RetentionAnalysis(
            available=True,
            strengths=["strong opening hook"],
            risk_regions=[],
        )
        _append_retention_explainability(plan, analysis)
        lines = plan.explainability["summary"]["summary_lines"]
        assert any("hook" in l.lower() for l in lines)

    def test_no_duplicate_explainability_lines(self):
        plan = _make_plan()
        plan.explainability = {"summary": {"summary_lines": []}}
        analysis = RetentionAnalysis(
            available=True,
            risk_regions=[_make_risk_region("long_setup", "high")],
        )
        _append_retention_explainability(plan, analysis)
        _append_retention_explainability(plan, analysis)
        lines = plan.explainability["summary"]["summary_lines"]
        setup_lines = [l for l in lines if "setup" in l.lower() or "retention" in l.lower()]
        assert len(setup_lines) == len(set(setup_lines))

    def test_attach_uses_plan_story_context(self):
        plan = _make_plan()
        plan.story = _make_story_context_with_hook()
        _attach_retention_intelligence(plan, _make_hook_chunks(), _make_pacing_high_energy(), "job1")
        assert plan.retention.get("available") is True

    def test_overall_score_is_integer_in_result(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        score = plan.retention.get("overall_retention_score")
        assert isinstance(score, int)

    def test_attach_never_raises_on_garbage_plan_attributes(self):
        plan = _make_plan()
        plan.story = "not a dict"
        plan.memory_context = None
        _attach_retention_intelligence(plan, [], {}, "job1")
        assert isinstance(plan.retention, dict)


# ---------------------------------------------------------------------------
# 7. Result JSON Compactness
# ---------------------------------------------------------------------------

class TestResultJsonCompactness:
    def test_retention_to_dict_is_compact(self):
        analysis = RetentionAnalysis(
            available=True,
            overall_retention_score=74.0,
            risk_regions=[_make_risk_region()],
            strengths=["strong opening hook"],
            warnings=[],
        )
        d = analysis.to_dict()
        import json
        serialized = json.dumps(d)
        assert len(serialized) < 5000  # should not be huge

    def test_risk_region_to_dict_is_compact(self):
        r = _make_risk_region()
        d = r.to_dict()
        import json
        serialized = json.dumps(d)
        assert len(serialized) < 1000

    def test_recommendation_to_dict_no_auto_apply(self):
        rec = RetentionRecommendation(priority="high", recommended_action="Strengthen hook")
        d = rec.to_dict()
        assert d["safe_to_auto_apply"] is False


# ---------------------------------------------------------------------------
# 8. No External Dependencies
# ---------------------------------------------------------------------------

class TestNoExternalDependencies:
    def test_no_api_key_required(self):
        import os
        env_backup = os.environ.copy()
        for key in list(os.environ.keys()):
            if "API_KEY" in key or "OPENAI" in key or "ANTHROPIC" in key:
                os.environ.pop(key, None)
        try:
            result = analyze_retention(transcript_chunks=_make_chunks())
            assert isinstance(result, RetentionAnalysis)
        finally:
            os.environ.update(env_backup)

    def test_no_gpu_required(self):
        result = detect_retention_risks(transcript_chunks=_make_chunks())
        assert isinstance(result, list)

    def test_no_internet_required(self):
        result = analyze_retention(
            transcript_chunks=_make_chunks(duration=30.0),
            story_context=_make_story_context_with_hook(),
        )
        assert isinstance(result, RetentionAnalysis)

    def test_no_real_rendering_required(self):
        plan = _make_plan()
        _attach_retention_intelligence(plan, _make_chunks(), {}, "job1")
        assert isinstance(plan.retention, dict)

    def test_retention_modules_import_safely(self):
        import importlib
        for mod in [
            "app.ai.retention.retention_schema",
            "app.ai.retention.dropoff_detector",
            "app.ai.retention.retention_analyzer",
            "app.ai.retention.retention_recommender",
        ]:
            importlib.import_module(mod)

    def test_no_ffmpeg_command_in_modules(self):
        import inspect
        import app.ai.retention.retention_schema as m1
        import app.ai.retention.dropoff_detector as m2
        import app.ai.retention.retention_analyzer as m3
        import app.ai.retention.retention_recommender as m4
        for mod in (m1, m2, m3, m4):
            src = inspect.getsource(mod)
            assert "ffmpeg" not in src.lower(), f"ffmpeg found in {mod.__name__}"
            assert "subprocess" not in src, f"subprocess found in {mod.__name__}"

    def test_no_timing_mutation_in_modules(self):
        import inspect
        import app.ai.retention.dropoff_detector as m
        src = inspect.getsource(m)
        # Must not alter start/end timing
        assert "segment_start" not in src
        assert "segment_end" not in src
        assert "playback_speed" not in src
