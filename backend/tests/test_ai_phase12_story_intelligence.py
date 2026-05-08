"""
test_ai_phase12_story_intelligence.py — Phase 12: Story Intelligence Foundation.

All tests are unit-level — no audio models, no API keys, no GPU, no rendering.
Story analysis is deterministic heuristic-only.
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List, Optional


# ── Minimal stubs ─────────────────────────────────────────────────────────────

def _chunk(text: str, start: float, end: float) -> dict:
    return {"text": text, "start": start, "end": end}


def _pacing_ctx(
    energy: float = 0.6,
    style: str = "dynamic",
    emotion: str = "excited",
) -> dict:
    return {
        "energy_level": energy,
        "pacing_style": style,
        "emotion": emotion,
        "emotion_score": 0.7,
        "beat_available": False,
        "bpm": None,
    }


# Strong hook transcript (early + hook keywords)
_HOOK_CHUNKS = [
    _chunk("Why does nobody tell you this secret?", 0.0, 4.0),
    _chunk("Stop what you are doing right now.", 4.0, 8.0),
    _chunk("Here is what you need to know before it is too late.", 8.0, 15.0),
    _chunk("The truth nobody talks about will shock you.", 15.0, 22.0),
    _chunk("It gets even more intense from here.", 22.0, 30.0),
    _chunk("This is the climax of everything we discussed.", 50.0, 60.0),
    _chunk("Now here is the payoff you have been waiting for.", 70.0, 80.0),
    _chunk("That is all for today, thank you for watching.", 85.0, 95.0),
]

# Rising energy transcript (mid portion has high-energy words)
_BUILD_UP_CHUNKS = [
    _chunk("Let me introduce what we will talk about today.", 0.0, 5.0),
    _chunk("Getting started with the basics.", 5.0, 12.0),
    _chunk("Now things are getting amazing and incredible fast.", 20.0, 28.0),
    _chunk("This is absolutely insane and completely massive.", 28.0, 36.0),
    _chunk("The energy is at its ultimate peak right now.", 40.0, 50.0),
    _chunk("Everything is coming together perfectly.", 55.0, 65.0),
    _chunk("Final thoughts and wrap-up.", 70.0, 80.0),
]

# High intensity (peak energy)
_HIGH_INTENSITY_CHUNKS = [
    _chunk("Welcome everyone.", 0.0, 5.0),
    _chunk("So here we are, building up slowly.", 15.0, 25.0),
    _chunk("The absolutely insane powerful massive climax is here now.", 45.0, 55.0),
    _chunk("Incredible ultimate powerful extreme moment happening.", 55.0, 65.0),
    _chunk("Goodbye and thanks.", 75.0, 85.0),
]


# ── Import modules ────────────────────────────────────────────────────────────

from app.ai.story.story_schema import StorySegment, StoryAnalysis, VALID_SEGMENT_TYPES
from app.ai.story.story_analyzer import analyze_story_structure
from app.ai.story.retention import estimate_retention


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestStorySchema:
    def test_story_segment_defaults(self):
        seg = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.8)
        assert seg.emotion is None
        assert seg.retention_risk is None
        assert seg.notes == []

    def test_story_segment_to_dict_has_all_keys(self):
        seg = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.8)
        d = seg.to_dict()
        for key in ("type", "start", "end", "confidence", "emotion", "retention_risk"):
            assert key in d

    def test_story_analysis_defaults(self):
        sa = StoryAnalysis()
        assert sa.available is True
        assert sa.narrative_flow == "unknown"
        assert sa.dominant_arc == "unknown"
        assert sa.retention_score == 0.0
        assert sa.segments == []
        assert sa.warnings == []

    def test_story_analysis_to_dict_has_all_keys(self):
        sa = StoryAnalysis()
        d = sa.to_dict()
        for key in ("available", "narrative_flow", "dominant_arc",
                    "retention_score", "segments", "warnings"):
            assert key in d

    def test_to_dict_segments_capped_at_12(self):
        segs = [
            StorySegment(start=float(i), end=float(i+1), segment_type="setup", confidence=0.5)
            for i in range(20)
        ]
        sa = StoryAnalysis(segments=segs)
        d = sa.to_dict()
        assert len(d["segments"]) <= 12

    def test_valid_segment_types_defined(self):
        for t in ("hook", "setup", "build_up", "tension", "climax", "payoff", "outro", "unknown"):
            assert t in VALID_SEGMENT_TYPES


# ── Analyzer safety tests ─────────────────────────────────────────────────────

class TestAnalyzerSafety:
    def test_never_raises_on_empty_transcript(self):
        result = analyze_story_structure([])
        assert isinstance(result, StoryAnalysis)

    def test_never_raises_on_none_transcript(self):
        result = analyze_story_structure(None)
        assert isinstance(result, StoryAnalysis)

    def test_never_raises_on_garbage_transcript(self):
        result = analyze_story_structure("not_a_list")
        assert isinstance(result, StoryAnalysis)

    def test_never_raises_on_garbage_pacing(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context="bad")
        assert isinstance(result, StoryAnalysis)

    def test_never_raises_on_none_pacing(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=None)
        assert isinstance(result, StoryAnalysis)

    def test_empty_transcript_available_false(self):
        result = analyze_story_structure([])
        assert result.available is False

    def test_none_transcript_available_false(self):
        result = analyze_story_structure(None)
        assert result.available is False

    def test_valid_transcript_available_true(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert result.available is True

    def test_result_has_no_invalid_segment_types(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        for seg in result.segments:
            assert seg.segment_type in VALID_SEGMENT_TYPES


# ── Hook detection ────────────────────────────────────────────────────────────

class TestHookDetection:
    def test_hook_text_in_early_position_creates_hook_segment(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        early_segs = [s for s in result.segments if s.start < 20.0]
        assert any(s.segment_type == "hook" for s in early_segs), (
            f"Expected 'hook' in early segments, got: {[(s.start, s.segment_type) for s in early_segs]}"
        )

    def test_hook_segment_has_positive_confidence(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        hook_segs = [s for s in result.segments if s.segment_type == "hook"]
        assert all(s.confidence > 0 for s in hook_segs)

    def test_hook_segment_confidence_above_threshold(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        hook_segs = [s for s in result.segments if s.segment_type == "hook"]
        assert any(s.confidence >= 0.30 for s in hook_segs)

    def test_neutral_early_text_no_hook(self):
        chunks = [
            _chunk("Hello everyone welcome to today.", 0.0, 5.0),
            _chunk("We will discuss some things here.", 5.0, 10.0),
            _chunk("More content in the middle of the video.", 25.0, 40.0),
        ]
        result = analyze_story_structure(chunks, pacing_context=_pacing_ctx(energy=0.3))
        early_segs = [s for s in result.segments if s.start < 15.0]
        assert all(s.segment_type != "hook" for s in early_segs)


# ── Build-up detection ────────────────────────────────────────────────────────

class TestBuildUpDetection:
    def test_rising_energy_creates_build_up(self):
        result = analyze_story_structure(
            _BUILD_UP_CHUNKS, pacing_context=_pacing_ctx(energy=0.65)
        )
        types = {s.segment_type for s in result.segments}
        assert "build_up" in types, f"Expected build_up, got: {types}"

    def test_low_energy_no_build_up(self):
        chunks = [
            _chunk("Plain content here, nothing special.", 0.0, 10.0),
            _chunk("Some more plain content in the middle.", 20.0, 35.0),
            _chunk("Still plain content at the peak.", 50.0, 65.0),
            _chunk("Ending with plain content.", 75.0, 85.0),
        ]
        result = analyze_story_structure(chunks, pacing_context=_pacing_ctx(energy=0.1, style="slow"))
        types = {s.segment_type for s in result.segments}
        assert "build_up" not in types or "hook" not in types


# ── Climax / tension detection ────────────────────────────────────────────────

class TestClimaxDetection:
    def test_high_intensity_creates_tension_or_climax(self):
        result = analyze_story_structure(
            _HIGH_INTENSITY_CHUNKS, pacing_context=_pacing_ctx(energy=0.85)
        )
        types = {s.segment_type for s in result.segments}
        assert "tension" in types or "climax" in types, (
            f"Expected tension or climax, got: {types}"
        )

    def test_high_energy_pacing_context_contributes_to_climax(self):
        result = analyze_story_structure(
            _HIGH_INTENSITY_CHUNKS,
            pacing_context=_pacing_ctx(energy=0.95, style="fast")
        )
        types = {s.segment_type for s in result.segments}
        assert "tension" in types or "climax" in types


# ── Retention risk tests ──────────────────────────────────────────────────────

class TestRetentionRisk:
    def test_estimate_retention_returns_dict(self):
        seg = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.8)
        result = estimate_retention(seg)
        assert isinstance(result, dict)

    def test_estimate_retention_has_required_keys(self):
        seg = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.8)
        result = estimate_retention(seg)
        for key in ("score", "risk", "reasons", "warnings"):
            assert key in result

    def test_hook_has_higher_score_than_outro(self):
        hook_seg = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.8)
        outro_seg = StorySegment(start=80.0, end=90.0, segment_type="outro", confidence=0.8)
        hook_result = estimate_retention(hook_seg)
        outro_result = estimate_retention(outro_seg)
        assert hook_result["score"] > outro_result["score"]

    def test_outro_has_higher_risk_than_hook(self):
        hook_seg = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.8)
        outro_seg = StorySegment(start=80.0, end=90.0, segment_type="outro", confidence=0.8)
        hook_result = estimate_retention(hook_seg)
        outro_result = estimate_retention(outro_seg)
        assert outro_result["risk"] > hook_result["risk"]

    def test_weak_pacing_low_confidence_increases_risk(self):
        seg_high = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.85)
        seg_low = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.10)
        result_high = estimate_retention(seg_high)
        result_low = estimate_retention(seg_low)
        assert result_low["risk"] >= result_high["risk"]
        assert result_low["score"] <= result_high["score"]

    def test_score_is_clamped_0_100(self):
        for seg_type in ("hook", "setup", "build_up", "climax", "outro", "unknown"):
            seg = StorySegment(start=0.0, end=5.0, segment_type=seg_type, confidence=0.8)
            result = estimate_retention(seg)
            assert 0 <= result["score"] <= 100, f"score out of range for {seg_type}"

    def test_risk_is_clamped_0_1(self):
        for seg_type in ("hook", "setup", "build_up", "climax", "outro", "unknown"):
            seg = StorySegment(start=0.0, end=5.0, segment_type=seg_type, confidence=0.8)
            result = estimate_retention(seg)
            assert 0.0 <= result["risk"] <= 1.0, f"risk out of range for {seg_type}"

    def test_estimate_retention_never_raises_on_garbage(self):
        result = estimate_retention(None)
        assert isinstance(result, dict)

    def test_estimate_retention_never_raises_on_string(self):
        result = estimate_retention("not_a_segment")
        assert isinstance(result, dict)

    def test_curiosity_emotion_reduces_risk(self):
        seg_neutral = StorySegment(start=0.0, end=5.0, segment_type="build_up",
                                   confidence=0.6, emotion="neutral")
        seg_curious = StorySegment(start=0.0, end=5.0, segment_type="build_up",
                                   confidence=0.6, emotion="curiosity")
        r_neutral = estimate_retention(seg_neutral)
        r_curious = estimate_retention(seg_curious)
        assert r_curious["risk"] < r_neutral["risk"]
        assert r_curious["score"] >= r_neutral["score"]


# ── AIEditPlan story field ────────────────────────────────────────────────────

class TestEditPlanStoryField:
    def test_ai_edit_plan_has_story_field(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AIPacingPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "story")
        assert isinstance(plan.story, dict)

    def test_ai_edit_plan_to_dict_includes_story(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AIPacingPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.story = {"narrative_flow": "hook_to_climax", "retention_score": 75.0}
        d = plan.to_dict()
        assert "story" in d
        assert d["story"]["narrative_flow"] == "hook_to_climax"

    def test_ai_edit_plan_story_defaults_to_empty_dict(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert plan.story == {}


# ── Result JSON story summary ─────────────────────────────────────────────────

class TestResultJsonStorySummary:
    def test_story_analysis_to_dict_is_compact(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        d = result.to_dict()
        assert len(d["segments"]) <= 12

    def test_story_dict_has_narrative_flow(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        d = result.to_dict()
        assert "narrative_flow" in d
        assert isinstance(d["narrative_flow"], str)

    def test_story_dict_has_retention_score(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        d = result.to_dict()
        assert "retention_score" in d
        assert isinstance(d["retention_score"], (int, float))

    def test_story_dict_segments_have_type_and_timing(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        d = result.to_dict()
        for seg in d["segments"]:
            assert "type" in seg
            assert "start" in seg
            assert "end" in seg
            assert "confidence" in seg

    def test_segment_types_in_result_are_valid(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        d = result.to_dict()
        for seg in d["segments"]:
            assert seg["type"] in VALID_SEGMENT_TYPES

    def test_dominant_arc_is_string(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        d = result.to_dict()
        assert isinstance(d["dominant_arc"], str)


# ── Explainability integration ────────────────────────────────────────────────

class TestExplainabilityIntegration:
    def _make_plan_with_explainability(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AIPacingPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.explainability = {"summary": {"summary_lines": ["Existing line"]}}
        return plan

    def test_story_explainability_appends_safely(self):
        from app.ai.director.ai_director import _append_story_explainability

        plan = self._make_plan_with_explainability()
        story = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        _append_story_explainability(plan, story)
        lines = plan.explainability["summary"]["summary_lines"]
        assert "Existing line" in lines

    def test_hook_adds_hook_line_to_explainability(self):
        from app.ai.director.ai_director import _append_story_explainability

        plan = self._make_plan_with_explainability()
        story = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        _append_story_explainability(plan, story)
        lines = plan.explainability["summary"]["summary_lines"]
        if any(s.segment_type == "hook" for s in story.segments):
            assert any("hook" in l.lower() for l in lines)

    def test_explainability_append_never_raises_on_missing_explainability(self):
        from app.ai.director.ai_director import _append_story_explainability
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        story = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        _append_story_explainability(plan, story)

    def test_explainability_append_never_raises_on_garbage_story(self):
        from app.ai.director.ai_director import _append_story_explainability

        plan = self._make_plan_with_explainability()
        _append_story_explainability(plan, None)

    def test_explainability_append_never_raises_on_missing_summary(self):
        from app.ai.director.ai_director import _append_story_explainability
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

        plan = AIEditPlan(
            enabled=True, mode="test", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.explainability = {}
        story = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        _append_story_explainability(plan, story)


# ── No external dependencies ──────────────────────────────────────────────────

class TestNoExternalDependencies:
    def test_no_api_key_required(self):
        import os
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
            assert isinstance(result, StoryAnalysis)
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved

    def test_no_gpu_required(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert isinstance(result, StoryAnalysis)

    def test_no_real_rendering_required(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert isinstance(result, StoryAnalysis)

    def test_no_librosa_required(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "librosa", None)
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert isinstance(result, StoryAnalysis)

    def test_no_torch_required(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "torch", None)
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert isinstance(result, StoryAnalysis)

    def test_story_analyzer_import_is_safe(self):
        from app.ai.story import story_analyzer
        from app.ai.story import retention
        from app.ai.story import story_schema

    def test_retention_never_raises_without_external_deps(self, monkeypatch):
        import sys
        monkeypatch.setitem(sys.modules, "torch", None)
        seg = StorySegment(start=0.0, end=5.0, segment_type="hook", confidence=0.7)
        result = estimate_retention(seg)
        assert isinstance(result, dict)


# ── Narrative flow and dominant arc ──────────────────────────────────────────

class TestNarrativeFlowAndArc:
    def test_hook_to_climax_flow_with_hook_and_tension(self):
        result = analyze_story_structure(
            _HOOK_CHUNKS, pacing_context=_pacing_ctx(energy=0.8)
        )
        types = {s.segment_type for s in result.segments}
        if "hook" in types and ("tension" in types or "climax" in types):
            assert result.narrative_flow == "hook_to_climax"

    def test_retention_score_in_valid_range(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert 0.0 <= result.retention_score <= 100.0

    def test_dominant_arc_is_nonempty_string(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert isinstance(result.dominant_arc, str)
        assert len(result.dominant_arc) > 0

    def test_narrative_flow_is_nonempty_string(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert isinstance(result.narrative_flow, str)
        assert len(result.narrative_flow) > 0

    def test_story_produces_some_segments(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        assert len(result.segments) > 0

    def test_segment_timing_is_nonnegative(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        for seg in result.segments:
            assert seg.start >= 0.0
            assert seg.end >= seg.start

    def test_retention_risk_on_segments_in_valid_range(self):
        result = analyze_story_structure(_HOOK_CHUNKS, pacing_context=_pacing_ctx())
        for seg in result.segments:
            if seg.retention_risk is not None:
                assert 0.0 <= seg.retention_risk <= 1.0
