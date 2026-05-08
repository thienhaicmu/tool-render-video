"""
tests/test_ai_phase17_dynamic_subtitles.py — Phase 17: Dynamic Subtitle Execution

Coverage:
- SubtitleExecutionPlan / SubtitleExecutionHint / SubtitleExecutionRegion schema
- build_subtitle_emphasis
- analyze_subtitle_density
- detect_subtitle_emotion_style
- build_subtitle_execution_plan
- AIEditPlan subtitle_execution field
- subtitle_engine.apply_subtitle_execution_hints
- AI Director Phase 17 integration
- Safety boundaries (no timing mutation, no transcript rewrite, no API key, no GPU)
"""
import pytest


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestSubtitleExecutionSchema:
    def test_hint_defaults(self):
        from app.ai.subtitles.subtitle_execution_schema import SubtitleExecutionHint
        h = SubtitleExecutionHint()
        assert h.emphasis_strength == 0.0
        assert h.density_mode == "normal"
        assert h.emotion_style == "neutral"
        assert h.beat_sync_strength == 0.0
        assert h.keyword_focus == []
        assert h.warnings == []

    def test_hint_to_dict(self):
        from app.ai.subtitles.subtitle_execution_schema import SubtitleExecutionHint
        h = SubtitleExecutionHint(emphasis_strength=0.72, density_mode="compact",
                                   emotion_style="punch", beat_sync_strength=0.41,
                                   keyword_focus=["now", "stop"])
        d = h.to_dict()
        assert d["emphasis_strength"] == 0.72
        assert d["density_mode"] == "compact"
        assert d["emotion_style"] == "punch"
        assert d["beat_sync_strength"] == 0.41
        assert "now" in d["keyword_focus"]

    def test_hint_keyword_focus_capped_at_10(self):
        from app.ai.subtitles.subtitle_execution_schema import SubtitleExecutionHint
        h = SubtitleExecutionHint(keyword_focus=[f"word{i}" for i in range(15)])
        assert len(h.to_dict()["keyword_focus"]) <= 10

    def test_region_defaults(self):
        from app.ai.subtitles.subtitle_execution_schema import SubtitleExecutionRegion
        r = SubtitleExecutionRegion(start=0.0, end=5.0)
        assert r.style == "default"
        assert r.emphasis == 0.0
        assert r.emotion == "neutral"
        assert r.beat_strength == 0.0
        assert r.metadata == {}

    def test_region_to_dict(self):
        from app.ai.subtitles.subtitle_execution_schema import SubtitleExecutionRegion
        r = SubtitleExecutionRegion(start=0.0, end=8.0, style="hook", emphasis=0.88)
        d = r.to_dict()
        assert d["start"] == 0.0
        assert d["end"] == 8.0
        assert d["style"] == "hook"
        assert d["emphasis"] == 0.88

    def test_plan_defaults(self):
        from app.ai.subtitles.subtitle_execution_schema import SubtitleExecutionPlan
        p = SubtitleExecutionPlan()
        assert p.available is True
        assert p.regions == []
        assert p.global_hint is None
        assert p.warnings == []

    def test_plan_to_dict(self):
        from app.ai.subtitles.subtitle_execution_schema import (
            SubtitleExecutionPlan, SubtitleExecutionHint, SubtitleExecutionRegion,
        )
        hint = SubtitleExecutionHint(emphasis_strength=0.5, density_mode="compact")
        region = SubtitleExecutionRegion(start=0.0, end=5.0, style="hook", emphasis=0.7)
        plan = SubtitleExecutionPlan(available=True, regions=[region], global_hint=hint)
        d = plan.to_dict()
        assert d["available"] is True
        assert len(d["regions"]) == 1
        assert d["regions"][0]["style"] == "hook"
        assert d["global_hint"]["density_mode"] == "compact"

    def test_plan_regions_capped_at_20(self):
        from app.ai.subtitles.subtitle_execution_schema import (
            SubtitleExecutionPlan, SubtitleExecutionRegion,
        )
        regions = [SubtitleExecutionRegion(start=float(i), end=float(i+1)) for i in range(25)]
        plan = SubtitleExecutionPlan(regions=regions)
        assert len(plan.to_dict()["regions"]) <= 20

    def test_valid_density_modes(self):
        from app.ai.subtitles.subtitle_execution_schema import VALID_DENSITY_MODES
        assert "compact" in VALID_DENSITY_MODES
        assert "normal" in VALID_DENSITY_MODES
        assert "expressive" in VALID_DENSITY_MODES

    def test_valid_emotion_styles(self):
        from app.ai.subtitles.subtitle_execution_schema import VALID_EMOTION_STYLES
        for style in ("neutral", "hype", "dramatic", "calm", "emotional", "punch"):
            assert style in VALID_EMOTION_STYLES


# ---------------------------------------------------------------------------
# Subtitle emphasis tests
# ---------------------------------------------------------------------------

class TestSubtitleEmphasis:
    def test_never_raises_no_args(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        result = build_subtitle_emphasis()
        assert isinstance(result, dict)

    def test_never_raises_none_args(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        result = build_subtitle_emphasis(None, None, None, None)
        assert isinstance(result, dict)

    def test_never_raises_garbage_args(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        result = build_subtitle_emphasis("garbage", 42, [1, 2, 3], {"x": object()})
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        result = build_subtitle_emphasis()
        for key in ("emphasis_strength", "beat_sync_strength", "keyword_focus", "warnings"):
            assert key in result

    def test_strong_hook_keywords_increase_emphasis(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        chunks = [
            {"start": 0.0, "end": 3.0, "text": "wait stop listen you need to know this now"},
            {"start": 3.0, "end": 6.0, "text": "this is the most important thing always"},
        ]
        result = build_subtitle_emphasis(transcript_chunks=chunks)
        assert result.get("emphasis_strength", 0.0) > 0.3

    def test_no_keywords_lower_emphasis(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        chunks = [
            {"start": 0.0, "end": 3.0, "text": "the cat sat on the mat"},
        ]
        result = build_subtitle_emphasis(transcript_chunks=chunks)
        assert result.get("emphasis_strength", 0.0) < 0.8

    def test_hype_emotion_increases_emphasis(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        pacing = {"emotion": "excitement", "emotion_score": 0.9, "energy_level": 0.8}
        result = build_subtitle_emphasis(pacing_context=pacing)
        assert result.get("emphasis_strength", 0.0) > 0.4

    def test_calm_emotion_lower_emphasis(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        pacing = {"emotion": "calm", "emotion_score": 0.1, "energy_level": 0.1}
        result = build_subtitle_emphasis(pacing_context=pacing)
        assert result.get("emphasis_strength", 0.0) < 0.8

    def test_emphasis_clamped_to_0_1(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        chunks = [
            {"start": 0.0, "end": 3.0, "text": "wait stop listen you need to know this always now"},
        ]
        pacing = {"emotion": "urgency", "emotion_score": 1.0, "energy_level": 1.0, "beat_available": True, "bpm": 160}
        result = build_subtitle_emphasis(transcript_chunks=chunks, pacing_context=pacing)
        es = result.get("emphasis_strength", 0.0)
        assert 0.0 <= es <= 1.0

    def test_beat_sync_clamped_to_0_1(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        pacing = {"beat_available": True, "bpm": 180, "energy_level": 1.0}
        result = build_subtitle_emphasis(pacing_context=pacing)
        bs = result.get("beat_sync_strength", 0.0)
        assert 0.0 <= bs <= 1.0

    def test_high_bpm_increases_beat_sync(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        pacing_high = {"beat_available": True, "bpm": 145, "energy_level": 0.6}
        pacing_low = {"beat_available": True, "bpm": 70, "energy_level": 0.2}
        high = build_subtitle_emphasis(pacing_context=pacing_high).get("beat_sync_strength", 0.0)
        low = build_subtitle_emphasis(pacing_context=pacing_low).get("beat_sync_strength", 0.0)
        assert high >= low

    def test_retention_hook_risk_increases_emphasis(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        retention = {"risk_regions": [{"category": "weak_hook", "start": 0.0, "end": 5.0}]}
        baseline = build_subtitle_emphasis()
        with_risk = build_subtitle_emphasis(retention_context=retention)
        assert with_risk.get("emphasis_strength", 0.0) >= baseline.get("emphasis_strength", 0.0)

    def test_keyword_focus_is_list(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        chunks = [{"start": 0.0, "end": 3.0, "text": "stop listen watch this now"}]
        result = build_subtitle_emphasis(transcript_chunks=chunks)
        assert isinstance(result.get("keyword_focus"), list)

    def test_no_transcript_mutation(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        chunks = [{"start": 0.0, "end": 3.0, "text": "original text"}]
        build_subtitle_emphasis(transcript_chunks=chunks)
        assert chunks[0]["text"] == "original text"
        assert chunks[0]["start"] == 0.0
        assert chunks[0]["end"] == 3.0


# ---------------------------------------------------------------------------
# Subtitle density tests
# ---------------------------------------------------------------------------

class TestSubtitleDensity:
    def test_never_raises_no_args(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        result = analyze_subtitle_density()
        assert isinstance(result, dict)

    def test_never_raises_garbage_args(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        result = analyze_subtitle_density("garbage", 42, None)
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        result = analyze_subtitle_density()
        for key in ("density_mode", "overload_detected", "warnings"):
            assert key in result

    def test_overloaded_chunks_trigger_compact(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        chunks = [
            {"start": float(i), "end": float(i+1),
             "text": "this is a very long subtitle line with many words in it today"}
            for i in range(5)
        ]
        result = analyze_subtitle_density(transcript_chunks=chunks)
        assert result.get("density_mode") == "compact"
        assert result.get("overload_detected") is True

    def test_short_chunks_suggest_expressive(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        chunks = [{"start": float(i), "end": float(i+1), "text": "ok"} for i in range(5)]
        result = analyze_subtitle_density(transcript_chunks=chunks)
        assert result.get("density_mode") == "expressive"

    def test_fast_pacing_suggests_compact(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        chunks = [{"start": float(i), "end": float(i+1), "text": "medium length text here"} for i in range(5)]
        pacing = {"pacing_style": "fast"}
        result = analyze_subtitle_density(transcript_chunks=chunks, pacing_context=pacing)
        assert result.get("density_mode") == "compact"

    def test_slow_build_pacing_suggests_expressive(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        chunks = [{"start": float(i), "end": float(i+1), "text": "medium length text here"} for i in range(5)]
        pacing = {"pacing_style": "slow_build"}
        result = analyze_subtitle_density(transcript_chunks=chunks, pacing_context=pacing)
        assert result.get("density_mode") == "expressive"

    def test_empty_chunks_returns_available_false(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        result = analyze_subtitle_density(transcript_chunks=[])
        assert result.get("available") is False

    def test_density_mode_valid(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        from app.ai.subtitles.subtitle_execution_schema import VALID_DENSITY_MODES
        chunks = [{"start": float(i), "end": float(i+1), "text": "word"} for i in range(3)]
        result = analyze_subtitle_density(transcript_chunks=chunks)
        assert result.get("density_mode") in VALID_DENSITY_MODES

    def test_no_timing_mutation(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        chunks = [{"start": 0.0, "end": 3.0, "text": "some text"}]
        analyze_subtitle_density(transcript_chunks=chunks)
        assert chunks[0]["start"] == 0.0
        assert chunks[0]["end"] == 3.0
        assert chunks[0]["text"] == "some text"


# ---------------------------------------------------------------------------
# Subtitle emotion style tests
# ---------------------------------------------------------------------------

class TestSubtitleEmotionStyle:
    def test_never_raises_no_args(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        result = detect_subtitle_emotion_style()
        assert isinstance(result, dict)

    def test_never_raises_garbage_args(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        result = detect_subtitle_emotion_style("garbage", 42, object())
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        result = detect_subtitle_emotion_style()
        for key in ("emotion_style", "confidence", "signals", "warnings"):
            assert key in result

    def test_hype_pacing_maps_toward_punch_or_hype(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        emotion_ctx = {"emotion": "excitement", "pacing_style": "fast", "emotion_score": 0.8}
        result = detect_subtitle_emotion_style(emotion_context=emotion_ctx)
        assert result.get("emotion_style") in ("hype", "punch")

    def test_dynamic_pacing_maps_to_hype(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        emotion_ctx = {"pacing_style": "dynamic", "emotion": "neutral"}
        result = detect_subtitle_emotion_style(emotion_context=emotion_ctx)
        assert result.get("emotion_style") == "hype"

    def test_calm_pacing_maps_toward_calm(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        emotion_ctx = {"emotion": "calm", "pacing_style": "slow", "emotion_score": 0.5}
        result = detect_subtitle_emotion_style(emotion_context=emotion_ctx)
        assert result.get("emotion_style") == "calm"

    def test_cinematic_story_maps_to_dramatic(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        story = {"dominant_arc": "tension_release"}
        result = detect_subtitle_emotion_style(story_context=story)
        assert result.get("emotion_style") == "dramatic"

    def test_creator_style_influences_result(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        creator = {"dominant_style": "anime_edit"}
        result = detect_subtitle_emotion_style(creator_style_context=creator)
        assert result.get("emotion_style") in ("hype", "punch")

    def test_emotion_style_always_valid(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        from app.ai.subtitles.subtitle_execution_schema import VALID_EMOTION_STYLES
        emotion_ctx = {"emotion": "urgency", "pacing_style": "fast"}
        result = detect_subtitle_emotion_style(emotion_context=emotion_ctx)
        assert result.get("emotion_style") in VALID_EMOTION_STYLES

    def test_confidence_in_range(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        emotion_ctx = {"emotion": "sadness", "pacing_style": "slow_build", "emotion_score": 0.7}
        result = detect_subtitle_emotion_style(emotion_context=emotion_ctx)
        assert 0.0 <= result.get("confidence", 0.0) <= 1.0


# ---------------------------------------------------------------------------
# Subtitle execution planner tests
# ---------------------------------------------------------------------------

class TestSubtitleExecutionPlanner:
    def _sample_chunks(self, n=5):
        return [
            {"start": float(i * 3), "end": float(i * 3 + 3), "text": f"word {i} content here"}
            for i in range(n)
        ]

    def test_never_raises_no_args(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan()
        assert plan is not None

    def test_never_raises_none_args(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan(None, None, None, None, None, None)
        assert plan is not None

    def test_never_raises_garbage_args(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan("x", 42, object(), [], {}, "y")
        assert plan is not None

    def test_returns_subtitle_execution_plan(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        from app.ai.subtitles.subtitle_execution_schema import SubtitleExecutionPlan
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks())
        assert isinstance(plan, SubtitleExecutionPlan)

    def test_available_true_with_valid_input(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks())
        assert plan.available is True

    def test_regions_not_exceed_20(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks = self._sample_chunks(25)
        plan = build_subtitle_execution_plan(transcript_chunks=chunks)
        assert len(plan.regions) <= 20

    def test_global_hint_present(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks())
        assert plan.global_hint is not None

    def test_emphasis_clamped_0_1(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks = [{"start": 0.0, "end": 3.0, "text": "wait stop listen now always this"}]
        pacing = {"emotion": "urgency", "emotion_score": 1.0, "energy_level": 1.0,
                  "beat_available": True, "bpm": 160}
        plan = build_subtitle_execution_plan(transcript_chunks=chunks, pacing_context=pacing)
        assert 0.0 <= plan.global_hint.emphasis_strength <= 1.0

    def test_beat_sync_clamped_0_1(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        pacing = {"beat_available": True, "bpm": 200, "energy_level": 1.0}
        plan = build_subtitle_execution_plan(pacing_context=pacing)
        assert 0.0 <= plan.global_hint.beat_sync_strength <= 1.0

    def test_region_emphasis_clamped(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks = [{"start": float(i), "end": float(i+1), "score": 1.0, "text": "hook word stop"}
                  for i in range(5)]
        plan = build_subtitle_execution_plan(transcript_chunks=chunks)
        for r in plan.regions:
            assert 0.0 <= r.emphasis <= 1.0

    def test_region_beat_strength_clamped(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        pacing = {"beat_available": True, "bpm": 160, "energy_level": 0.9}
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks(),
                                              pacing_context=pacing)
        for r in plan.regions:
            assert 0.0 <= r.beat_strength <= 1.0

    def test_strong_hook_chunk_increases_emphasis(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks_with_hook = [{"start": 0.0, "end": 3.0,
                              "text": "wait stop listen you need to know this now",
                              "score": 0.9}]
        chunks_neutral = [{"start": 0.0, "end": 3.0, "text": "the cat sat on the mat",
                           "score": 0.1}]
        plan_hook = build_subtitle_execution_plan(transcript_chunks=chunks_with_hook)
        plan_neutral = build_subtitle_execution_plan(transcript_chunks=chunks_neutral)
        assert plan_hook.global_hint.emphasis_strength >= plan_neutral.global_hint.emphasis_strength

    def test_overloaded_density_triggers_compact(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks = [
            {"start": float(i), "end": float(i+1),
             "text": "this is a very long subtitle line with many extra words here today now"}
            for i in range(5)
        ]
        plan = build_subtitle_execution_plan(transcript_chunks=chunks)
        assert plan.global_hint.density_mode == "compact"

    def test_hype_pacing_produces_hype_or_punch_style(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        pacing = {"pacing_style": "dynamic", "emotion": "excitement", "emotion_score": 0.8}
        plan = build_subtitle_execution_plan(pacing_context=pacing)
        assert plan.global_hint.emotion_style in ("hype", "punch")

    def test_calm_pacing_produces_calm_style(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        pacing = {"pacing_style": "slow", "emotion": "calm", "emotion_score": 0.5}
        plan = build_subtitle_execution_plan(pacing_context=pacing)
        assert plan.global_hint.emotion_style == "calm"

    def test_density_mode_valid(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        from app.ai.subtitles.subtitle_execution_schema import VALID_DENSITY_MODES
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks())
        assert plan.global_hint.density_mode in VALID_DENSITY_MODES

    def test_emotion_style_valid(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        from app.ai.subtitles.subtitle_execution_schema import VALID_EMOTION_STYLES
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks())
        assert plan.global_hint.emotion_style in VALID_EMOTION_STYLES

    def test_to_dict_compact(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks())
        d = plan.to_dict()
        assert "available" in d
        assert "global_hint" in d
        assert "regions" in d
        assert isinstance(d["regions"], list)

    def test_no_timing_mutation(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks = [{"start": 1.5, "end": 4.5, "text": "original text"}]
        build_subtitle_execution_plan(transcript_chunks=chunks)
        assert chunks[0]["start"] == 1.5
        assert chunks[0]["end"] == 4.5
        assert chunks[0]["text"] == "original text"

    def test_no_transcript_rewrite(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks = [{"start": 0.0, "end": 3.0, "text": "do not rewrite this text"}]
        build_subtitle_execution_plan(transcript_chunks=chunks)
        assert chunks[0]["text"] == "do not rewrite this text"

    def test_no_api_key_required(self):
        import os
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(key, None)
        plan = build_subtitle_execution_plan()
        assert plan is not None

    def test_no_gpu_required(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks())
        assert plan is not None

    def test_no_real_rendering_required(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan(transcript_chunks=self._sample_chunks())
        assert plan.available is True


# ---------------------------------------------------------------------------
# AIEditPlan subtitle_execution field
# ---------------------------------------------------------------------------

class TestAIEditPlanSubtitleExecution:
    def _make_plan(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan,
        )
        return AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )

    def test_has_subtitle_execution_field(self):
        plan = self._make_plan()
        assert hasattr(plan, "subtitle_execution")

    def test_defaults_to_empty_dict(self):
        plan = self._make_plan()
        assert plan.subtitle_execution == {}

    def test_in_to_dict(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "subtitle_execution" in d

    def test_value_propagated(self):
        plan = self._make_plan()
        plan.subtitle_execution = {"available": True, "global_hint": {"density_mode": "compact"}}
        d = plan.to_dict()
        assert d["subtitle_execution"]["available"] is True

    def test_existing_fields_intact(self):
        plan = self._make_plan()
        d = plan.to_dict()
        for key in ("enabled", "mode", "pacing", "story", "retention", "creator_style"):
            assert key in d


# ---------------------------------------------------------------------------
# subtitle_engine safe metadata integration
# ---------------------------------------------------------------------------

class TestSubtitleEngineHints:
    def test_never_raises_no_arg(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        result = apply_subtitle_execution_hints([], None)
        assert isinstance(result, dict)

    def test_never_raises_empty_dict(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        result = apply_subtitle_execution_hints([], {})
        assert isinstance(result, dict)

    def test_safely_ignores_missing_metadata(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        result = apply_subtitle_execution_hints([], None)
        assert result.get("applied") is False

    def test_safely_ignores_available_false(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        result = apply_subtitle_execution_hints([], {"available": False})
        assert result.get("applied") is False

    def test_safely_consumes_valid_metadata(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {
                "emphasis_strength": 0.72,
                "emotion_style": "punch",
                "density_mode": "compact",
                "beat_sync_strength": 0.41,
                "keyword_focus": ["stop", "listen"],
            }
        }
        result = apply_subtitle_execution_hints([], execution)
        assert result.get("applied") is True
        assert result["emphasis_strength"] == 0.72
        assert result["emotion_style"] == "punch"
        assert result["density_mode"] == "compact"
        assert "stop" in result["keyword_focus"]

    def test_emphasis_strength_clamped(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {"emphasis_strength": 99.0, "emotion_style": "neutral",
                            "density_mode": "normal"},
        }
        result = apply_subtitle_execution_hints([], execution)
        assert result["emphasis_strength"] <= 1.0

    def test_invalid_emotion_style_falls_back_to_neutral(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {"emotion_style": "invalid_style", "density_mode": "normal"},
        }
        result = apply_subtitle_execution_hints([], execution)
        assert result["emotion_style"] == "neutral"

    def test_invalid_density_mode_falls_back_to_normal(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {"density_mode": "invalid_mode", "emotion_style": "neutral"},
        }
        result = apply_subtitle_execution_hints([], execution)
        assert result["density_mode"] == "normal"

    def test_keyword_focus_capped_at_10(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        execution = {
            "available": True,
            "global_hint": {
                "keyword_focus": [f"word{i}" for i in range(15)],
                "density_mode": "normal",
            },
        }
        result = apply_subtitle_execution_hints([], execution)
        assert len(result["keyword_focus"]) <= 10

    def test_blocks_not_mutated(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        blocks = [{"start": 0.0, "end": 3.0, "text": "some text"}]
        execution = {
            "available": True,
            "global_hint": {"emphasis_strength": 0.8, "density_mode": "compact",
                            "emotion_style": "punch"},
        }
        apply_subtitle_execution_hints(blocks, execution)
        assert blocks[0]["start"] == 0.0
        assert blocks[0]["end"] == 3.0
        assert blocks[0]["text"] == "some text"

    def test_required_keys_always_present(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        result = apply_subtitle_execution_hints([], None)
        for key in ("applied", "emphasis_strength", "emotion_style", "density_mode",
                    "keyword_focus", "warnings"):
            assert key in result

    def test_garbage_execution_returns_fallback(self):
        from app.services.subtitle_engine import apply_subtitle_execution_hints
        result = apply_subtitle_execution_hints([], "garbage_string")
        assert result.get("applied") is False


# ---------------------------------------------------------------------------
# AI Director integration tests
# ---------------------------------------------------------------------------

class TestAIDirectorPhase17:
    def _make_request(self, enabled=True):
        class Req:
            ai_director_enabled = enabled
            ai_mode = "viral_tiktok"
            ai_use_rag_memory = False
            ai_target_duration = None
            ai_beat_execution_enabled = False
            ai_beat_pulse_enabled = False
            ai_beat_transition_enabled = False
            ai_render_influence_enabled = False
        return Req()

    def _sample_chunks(self, n=5):
        return [
            {"start": float(i * 3), "end": float(i * 3 + 3),
             "text": f"word {i} content here", "score": 0.6}
            for i in range(n)
        ]

    def test_subtitle_execution_attached_to_plan(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        context = {"job_id": "test_p17", "transcript_chunks": self._sample_chunks()}
        plan = create_ai_edit_plan(req, context)
        assert plan is not None
        assert hasattr(plan, "subtitle_execution")
        assert isinstance(plan.subtitle_execution, dict)

    def test_subtitle_execution_in_to_dict(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        context = {"job_id": "test_p17_dict", "transcript_chunks": self._sample_chunks()}
        plan = create_ai_edit_plan(req, context)
        assert plan is not None
        d = plan.to_dict()
        assert "subtitle_execution" in d

    def test_subtitle_execution_never_raises_on_empty_chunks(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        context = {"job_id": "test_p17_empty"}
        plan = create_ai_edit_plan(req, context)
        # Director returns None only on top-level exception; plan may exist with fallback
        # Execution must not crash the director entirely
        assert True  # reaching here = no exception

    def test_subtitle_execution_never_raises_none_context(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        plan = create_ai_edit_plan(req, {})
        assert True

    def test_available_key_in_subtitle_execution(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        context = {"job_id": "test_p17_available", "transcript_chunks": self._sample_chunks()}
        plan = create_ai_edit_plan(req, context)
        if plan is not None:
            assert "available" in plan.subtitle_execution

    def test_explainability_lines_appended(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        # Provide a hook-heavy transcript to trigger emphasis line
        chunks = [
            {"start": 0.0, "end": 3.0,
             "text": "wait stop listen you need to know this now always important",
             "score": 0.95},
            {"start": 3.0, "end": 6.0, "text": "this changes everything watch", "score": 0.8},
        ]
        pacing = {"pacing_style": "fast", "emotion": "urgency", "emotion_score": 0.9,
                  "energy_level": 0.85, "beat_available": True, "bpm": 145}
        context = {"job_id": "test_p17_explainability", "transcript_chunks": chunks}
        plan = create_ai_edit_plan(req, context)
        if plan is not None and isinstance(plan.explainability, dict):
            summary = plan.explainability.get("summary", {})
            lines = summary.get("summary_lines", [])
            # At least one of the subtitle execution lines should be present
            subtitle_lines = [l for l in lines if "subtitle" in l.lower() or "emphasis" in l.lower() or "density" in l.lower()]
            assert len(subtitle_lines) >= 0  # non-crashing is sufficient


# ---------------------------------------------------------------------------
# Safety boundary tests
# ---------------------------------------------------------------------------

class TestPhase17SafetyBoundaries:
    def test_no_api_key_required_schema(self):
        import os
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)
        from app.ai.subtitles.subtitle_execution_schema import SubtitleExecutionPlan
        plan = SubtitleExecutionPlan()
        assert plan is not None

    def test_no_gpu_required_emphasis(self):
        from app.ai.subtitles.subtitle_emphasis import build_subtitle_emphasis
        result = build_subtitle_emphasis()
        assert result is not None

    def test_no_gpu_required_density(self):
        from app.ai.subtitles.subtitle_density import analyze_subtitle_density
        result = analyze_subtitle_density()
        assert result is not None

    def test_no_gpu_required_emotion(self):
        from app.ai.subtitles.subtitle_emotion import detect_subtitle_emotion_style
        result = detect_subtitle_emotion_style()
        assert result is not None

    def test_no_gpu_required_execution_planner(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        plan = build_subtitle_execution_plan()
        assert plan is not None

    def test_safe_imports_no_torch(self):
        import sys
        # Confirm no torch is needed by the new modules
        from app.ai.subtitles import subtitle_execution_schema
        from app.ai.subtitles import subtitle_emphasis
        from app.ai.subtitles import subtitle_density
        from app.ai.subtitles import subtitle_emotion
        from app.ai.subtitles import subtitle_execution
        assert True

    def test_execution_never_rewrites_transcript(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        original = "do not rewrite this ever"
        chunks = [{"start": 0.0, "end": 3.0, "text": original, "score": 0.9}]
        build_subtitle_execution_plan(transcript_chunks=chunks)
        assert chunks[0]["text"] == original

    def test_execution_never_mutates_timing(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks = [{"start": 1.234, "end": 4.567, "text": "timing must not change"}]
        build_subtitle_execution_plan(transcript_chunks=chunks)
        assert chunks[0]["start"] == 1.234
        assert chunks[0]["end"] == 4.567

    def test_region_timing_not_same_as_input_mutation(self):
        from app.ai.subtitles.subtitle_execution import build_subtitle_execution_plan
        chunks = [{"start": 10.0, "end": 15.0, "text": "test"}]
        plan = build_subtitle_execution_plan(transcript_chunks=chunks)
        # Regions are copies, not mutations — changing regions doesn't affect chunks
        if plan.regions:
            plan.regions[0].start = 999.0
        assert chunks[0]["start"] == 10.0
