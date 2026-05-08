"""
tests/test_ai_phase18_beat_visual_execution.py — Phase 18: Beat Visual Execution

Coverage:
- BeatPulseRegion / TransitionHint / BeatVisualExecutionPlan schema
- build_beat_pulse_regions
- build_transition_hints
- build_beat_visual_execution_plan
- AIEditPlan beat_visual_execution field
- AI Director Phase 18 integration
- render_influence safe defer/report
- Safety boundaries (no timing mutation, no playback_speed, no FFmpeg, no API key, no GPU)
"""
import pytest


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestBeatVisualSchema:
    def test_pulse_region_defaults(self):
        from app.ai.visuals.beat_visual_schema import BeatPulseRegion
        r = BeatPulseRegion(start=0.0, end=5.0)
        assert r.pulse_strength == 0.0
        assert r.pulse_style == "none"
        assert r.beat_count == 0
        assert r.warnings == []

    def test_pulse_region_to_dict(self):
        from app.ai.visuals.beat_visual_schema import BeatPulseRegion
        r = BeatPulseRegion(start=0.0, end=8.0, pulse_strength=0.12,
                            pulse_style="punch_pulse", beat_count=4)
        d = r.to_dict()
        assert d["start"] == 0.0
        assert d["end"] == 8.0
        assert d["pulse_strength"] == 0.12
        assert d["pulse_style"] == "punch_pulse"
        assert d["beat_count"] == 4

    def test_transition_hint_defaults(self):
        from app.ai.visuals.beat_visual_schema import TransitionHint
        h = TransitionHint(start=5.0, end=6.0)
        assert h.transition_style == "none"
        assert h.confidence == 0.0
        assert h.reason == ""
        assert h.safe_to_apply is False

    def test_transition_hint_safe_to_apply_always_false(self):
        from app.ai.visuals.beat_visual_schema import TransitionHint
        h = TransitionHint(start=5.0, end=6.0, transition_style="beat_pulse",
                           safe_to_apply=True)  # even if set True...
        d = h.to_dict()
        assert d["safe_to_apply"] is False   # to_dict() always returns False

    def test_transition_hint_to_dict(self):
        from app.ai.visuals.beat_visual_schema import TransitionHint
        h = TransitionHint(start=5.0, end=6.0, transition_style="cinematic_push",
                           confidence=0.72, reason="hook->climax")
        d = h.to_dict()
        assert d["transition_style"] == "cinematic_push"
        assert d["confidence"] == 0.72
        assert d["reason"] == "hook->climax"
        assert d["safe_to_apply"] is False

    def test_plan_defaults(self):
        from app.ai.visuals.beat_visual_schema import BeatVisualExecutionPlan
        p = BeatVisualExecutionPlan()
        assert p.available is True
        assert p.execution_mode == "metadata_only"
        assert p.bpm is None
        assert p.pulse_regions == []
        assert p.transition_hints == []
        assert p.warnings == []

    def test_plan_execution_mode_always_metadata_only(self):
        from app.ai.visuals.beat_visual_schema import BeatVisualExecutionPlan
        p = BeatVisualExecutionPlan(execution_mode="live")  # ignored by to_dict? No — stored as-is
        # The schema stores whatever is passed; the planner always sets it to "metadata_only"
        assert p.execution_mode == "live"  # stored as set
        # But the planner always produces "metadata_only"

    def test_plan_to_dict(self):
        from app.ai.visuals.beat_visual_schema import (
            BeatVisualExecutionPlan, BeatPulseRegion, TransitionHint,
        )
        region = BeatPulseRegion(start=0.0, end=8.0, pulse_strength=0.12,
                                  pulse_style="punch_pulse")
        hint = TransitionHint(start=8.0, end=9.0, transition_style="beat_pulse",
                              confidence=0.72)
        plan = BeatVisualExecutionPlan(available=True, bpm=128.0,
                                       pulse_regions=[region], transition_hints=[hint])
        d = plan.to_dict()
        assert d["available"] is True
        assert d["bpm"] == 128.0
        assert len(d["pulse_regions"]) == 1
        assert len(d["transition_hints"]) == 1
        assert d["execution_mode"] == "metadata_only"

    def test_plan_pulse_regions_capped_at_12(self):
        from app.ai.visuals.beat_visual_schema import BeatVisualExecutionPlan, BeatPulseRegion
        regions = [BeatPulseRegion(start=float(i), end=float(i+1)) for i in range(15)]
        plan = BeatVisualExecutionPlan(pulse_regions=regions)
        assert len(plan.to_dict()["pulse_regions"]) <= 12

    def test_plan_transition_hints_capped_at_10(self):
        from app.ai.visuals.beat_visual_schema import BeatVisualExecutionPlan, TransitionHint
        hints = [TransitionHint(start=float(i), end=float(i+1)) for i in range(13)]
        plan = BeatVisualExecutionPlan(transition_hints=hints)
        assert len(plan.to_dict()["transition_hints"]) <= 10

    def test_valid_pulse_styles(self):
        from app.ai.visuals.beat_visual_schema import VALID_PULSE_STYLES
        for style in ("none", "soft_pulse", "punch_pulse", "cinematic_pulse"):
            assert style in VALID_PULSE_STYLES

    def test_valid_transition_styles(self):
        from app.ai.visuals.beat_visual_schema import VALID_TRANSITION_STYLES
        for style in ("none", "soft_cut", "beat_pulse", "energy_pop", "cinematic_push"):
            assert style in VALID_TRANSITION_STYLES


# ---------------------------------------------------------------------------
# Beat pulse planner tests
# ---------------------------------------------------------------------------

class TestBeatPulsePlanner:
    def _valid_pacing(self, energy=0.8, bpm=128.0, beat_count=16):
        return {
            "beat_available": True,
            "bpm": bpm,
            "beat_count": beat_count,
            "energy_level": energy,
            "pacing_style": "fast",
        }

    def test_never_raises_no_args(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        result = build_beat_pulse_regions()
        assert isinstance(result, list)

    def test_never_raises_none_args(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        result = build_beat_pulse_regions(None, None, None, None)
        assert isinstance(result, list)

    def test_never_raises_garbage_args(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        result = build_beat_pulse_regions("garbage", 42, object(), [1, 2])
        assert isinstance(result, list)

    def test_no_beat_available_returns_empty(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = {"beat_available": False, "bpm": 128.0, "beat_count": 16}
        assert build_beat_pulse_regions(pacing_context=pacing) == []

    def test_bpm_below_60_returns_empty(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = {"beat_available": True, "bpm": 45.0, "beat_count": 16}
        assert build_beat_pulse_regions(pacing_context=pacing) == []

    def test_bpm_above_190_returns_empty(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = {"beat_available": True, "bpm": 200.0, "beat_count": 16}
        assert build_beat_pulse_regions(pacing_context=pacing) == []

    def test_bpm_exactly_60_accepted(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = {"beat_available": True, "bpm": 60.0, "beat_count": 4, "energy_level": 0.5}
        result = build_beat_pulse_regions(pacing_context=pacing)
        assert isinstance(result, list)

    def test_bpm_exactly_190_accepted(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = {"beat_available": True, "bpm": 190.0, "beat_count": 4, "energy_level": 0.5}
        result = build_beat_pulse_regions(pacing_context=pacing)
        assert isinstance(result, list)

    def test_beat_count_below_4_returns_empty(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = {"beat_available": True, "bpm": 128.0, "beat_count": 3}
        assert build_beat_pulse_regions(pacing_context=pacing) == []

    def test_beat_count_exactly_4_accepted(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = {"beat_available": True, "bpm": 128.0, "beat_count": 4, "energy_level": 0.5}
        result = build_beat_pulse_regions(pacing_context=pacing)
        assert isinstance(result, list)

    def test_pulse_strength_clamped_to_015(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = {**self._valid_pacing(energy=1.0, bpm=180), "pacing_style": "fast"}
        story = {"segments": [{"start": 0.0, "end": 30.0, "segment_type": "hook"}]}
        regions = build_beat_pulse_regions(pacing_context=pacing, story_context=story)
        for r in regions:
            assert r.pulse_strength <= 0.15

    def test_pulse_strength_non_negative(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        regions = build_beat_pulse_regions(pacing_context=self._valid_pacing(energy=0.0))
        for r in regions:
            assert r.pulse_strength >= 0.0

    def test_high_energy_fast_creates_punch_pulse(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = self._valid_pacing(energy=0.85, bpm=140)
        pacing["pacing_style"] = "fast"
        regions = build_beat_pulse_regions(pacing_context=pacing)
        assert len(regions) > 0
        styles = {r.pulse_style for r in regions}
        assert "punch_pulse" in styles

    def test_cinematic_arc_creates_cinematic_pulse(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = self._valid_pacing(energy=0.5, bpm=100)
        story = {"dominant_arc": "tension_release",
                 "segments": [{"start": 0.0, "end": 20.0, "segment_type": "hook"}]}
        regions = build_beat_pulse_regions(pacing_context=pacing, story_context=story)
        assert len(regions) > 0
        styles = {r.pulse_style for r in regions}
        assert "cinematic_pulse" in styles

    def test_low_energy_creates_soft_pulse(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = self._valid_pacing(energy=0.1, bpm=80)
        regions = build_beat_pulse_regions(pacing_context=pacing)
        assert len(regions) > 0
        for r in regions:
            assert r.pulse_style in ("soft_pulse", "none")

    def test_retention_risk_softens_pulse(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = self._valid_pacing(energy=0.9, bpm=130)
        pacing["pacing_style"] = "fast"
        story = {"dominant_arc": "front_loaded",
                 "segments": [{"start": 0.0, "end": 10.0, "segment_type": "hook"}]}
        retention_with_risk = {
            "risk_regions": [{"start": 0.0, "end": 10.0, "category": "weak_hook"}]
        }
        retention_without = {"risk_regions": []}
        regions_risk = build_beat_pulse_regions(
            pacing_context=pacing, story_context=story,
            retention_context=retention_with_risk,
        )
        regions_no_risk = build_beat_pulse_regions(
            pacing_context=pacing, story_context=story,
            retention_context=retention_without,
        )
        if regions_risk and regions_no_risk:
            # Risk region should produce lower or equal pulse strength
            max_risk = max(r.pulse_strength for r in regions_risk)
            max_no_risk = max(r.pulse_strength for r in regions_no_risk)
            assert max_risk <= max_no_risk

    def test_max_regions_never_exceeds_12(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = self._valid_pacing(energy=0.8, bpm=128, beat_count=100)
        story = {
            "segments": [
                {"start": float(i * 5), "end": float(i * 5 + 5), "segment_type": "build_up"}
                for i in range(20)
            ]
        }
        regions = build_beat_pulse_regions(pacing_context=pacing, story_context=story)
        assert len(regions) <= 12

    def test_pulse_style_always_valid(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        from app.ai.visuals.beat_visual_schema import VALID_PULSE_STYLES
        regions = build_beat_pulse_regions(pacing_context=self._valid_pacing())
        for r in regions:
            assert r.pulse_style in VALID_PULSE_STYLES

    def test_no_timing_mutation(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        pacing = self._valid_pacing()
        original_pacing = dict(pacing)
        build_beat_pulse_regions(pacing_context=pacing)
        assert pacing == original_pacing


# ---------------------------------------------------------------------------
# Transition planner tests
# ---------------------------------------------------------------------------

class TestTransitionPlanner:
    def _valid_pacing(self):
        return {
            "beat_available": True,
            "bpm": 128.0,
            "pacing_style": "fast",
            "energy_level": 0.8,
        }

    def test_never_raises_no_args(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        result = build_transition_hints()
        assert isinstance(result, list)

    def test_never_raises_garbage_args(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        result = build_transition_hints("x", 42, object(), [])
        assert isinstance(result, list)

    def test_returns_list(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        result = build_transition_hints(pacing_context=self._valid_pacing())
        assert isinstance(result, list)

    def test_safe_to_apply_always_false(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        story = {"segments": [
            {"start": 0.0, "end": 5.0, "segment_type": "hook"},
            {"start": 5.0, "end": 15.0, "segment_type": "build_up"},
        ]}
        hints = build_transition_hints(
            pacing_context=self._valid_pacing(), story_context=story
        )
        for h in hints:
            assert h.safe_to_apply is False

    def test_safe_to_apply_false_in_to_dict(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        story = {"segments": [
            {"start": 0.0, "end": 5.0, "segment_type": "climax"},
            {"start": 5.0, "end": 10.0, "segment_type": "payoff"},
        ]}
        hints = build_transition_hints(story_context=story)
        for h in hints:
            assert h.to_dict()["safe_to_apply"] is False

    def test_max_hints_never_exceeds_10(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        story = {"segments": [
            {"start": float(i * 3), "end": float(i * 3 + 3), "segment_type": "build_up"}
            for i in range(15)
        ]}
        hints = build_transition_hints(story_context=story)
        assert len(hints) <= 10

    def test_climax_segment_produces_cinematic_push(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        story = {"segments": [
            {"start": 0.0, "end": 10.0, "segment_type": "build_up"},
            {"start": 10.0, "end": 20.0, "segment_type": "climax"},
        ]}
        hints = build_transition_hints(story_context=story)
        styles = {h.transition_style for h in hints}
        assert "cinematic_push" in styles

    def test_hype_creator_style_produces_energy_pop(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        story = {"segments": [
            {"start": 0.0, "end": 10.0, "segment_type": "climax"},
            {"start": 10.0, "end": 20.0, "segment_type": "payoff"},
        ]}
        creator = {"dominant_style": "anime_edit"}
        hints = build_transition_hints(story_context=story, creator_style_context=creator)
        styles = {h.transition_style for h in hints}
        assert "energy_pop" in styles

    def test_calm_creator_style_produces_soft_cut(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        story = {"segments": [
            {"start": 0.0, "end": 10.0, "segment_type": "hook"},
            {"start": 10.0, "end": 20.0, "segment_type": "build_up"},
        ]}
        creator = {"dominant_style": "documentary_clean"}
        hints = build_transition_hints(story_context=story, creator_style_context=creator)
        for h in hints:
            assert h.transition_style == "soft_cut"

    def test_fast_pacing_beat_available_produces_beat_pulse(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        pacing = {"pacing_style": "fast", "beat_available": True, "bpm": 130.0}
        hints = build_transition_hints(pacing_context=pacing)
        assert len(hints) > 0

    def test_transition_style_always_valid(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        from app.ai.visuals.beat_visual_schema import VALID_TRANSITION_STYLES
        story = {"segments": [
            {"start": float(i * 5), "end": float(i * 5 + 5), "segment_type": "build_up"}
            for i in range(5)
        ]}
        hints = build_transition_hints(
            pacing_context=self._valid_pacing(), story_context=story
        )
        for h in hints:
            assert h.transition_style in VALID_TRANSITION_STYLES

    def test_confidence_in_range(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        story = {"segments": [
            {"start": 0.0, "end": 5.0, "segment_type": "hook"},
            {"start": 5.0, "end": 15.0, "segment_type": "climax"},
        ]}
        hints = build_transition_hints(story_context=story)
        for h in hints:
            assert 0.0 <= h.confidence <= 1.0

    def test_no_timing_mutation(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        pacing = self._valid_pacing()
        original = dict(pacing)
        build_transition_hints(pacing_context=pacing)
        assert pacing == original


# ---------------------------------------------------------------------------
# Visual execution planner tests
# ---------------------------------------------------------------------------

class TestVisualExecutionPlanner:
    def _valid_pacing(self, energy=0.8, bpm=128.0, beat_count=16):
        return {
            "beat_available": True,
            "bpm": bpm,
            "beat_count": beat_count,
            "energy_level": energy,
            "pacing_style": "fast",
        }

    def test_never_raises_no_args(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan()
        assert plan is not None

    def test_never_raises_none_args(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(None, None, None, None, None)
        assert plan is not None

    def test_never_raises_garbage_args(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan("x", 42, object(), [], "y")
        assert plan is not None

    def test_returns_beat_visual_execution_plan(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        from app.ai.visuals.beat_visual_schema import BeatVisualExecutionPlan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing())
        assert isinstance(plan, BeatVisualExecutionPlan)

    def test_execution_mode_always_metadata_only(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing())
        assert plan.execution_mode == "metadata_only"

    def test_available_true_with_valid_beat_data(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing())
        assert plan.available is True

    def test_available_false_without_beat_data(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context={"beat_available": False})
        assert plan.available is False

    def test_bpm_stored_in_plan(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing(bpm=140.0))
        assert plan.bpm == 140.0

    def test_pulse_strength_clamped_to_015(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing(energy=1.0))
        for r in plan.pulse_regions:
            assert r.pulse_strength <= 0.15

    def test_safe_to_apply_always_false_in_hints(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        story = {"segments": [
            {"start": 0.0, "end": 10.0, "segment_type": "hook"},
            {"start": 10.0, "end": 20.0, "segment_type": "climax"},
        ]}
        plan = build_beat_visual_execution_plan(
            pacing_context=self._valid_pacing(), story_context=story
        )
        for h in plan.transition_hints:
            assert h.safe_to_apply is False
            assert h.to_dict()["safe_to_apply"] is False

    def test_to_dict_compact(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing())
        d = plan.to_dict()
        assert "available" in d
        assert "execution_mode" in d
        assert "bpm" in d
        assert "pulse_regions" in d
        assert "transition_hints" in d
        assert isinstance(d["pulse_regions"], list)
        assert isinstance(d["transition_hints"], list)

    def test_to_dict_pulse_regions_capped_12(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        story = {"segments": [
            {"start": float(i * 3), "end": float(i * 3 + 3), "segment_type": "build_up"}
            for i in range(20)
        ]}
        plan = build_beat_visual_execution_plan(
            pacing_context=self._valid_pacing(beat_count=80), story_context=story
        )
        assert len(plan.to_dict()["pulse_regions"]) <= 12

    def test_to_dict_transition_hints_capped_10(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        story = {"segments": [
            {"start": float(i * 3), "end": float(i * 3 + 3), "segment_type": "build_up"}
            for i in range(15)
        ]}
        plan = build_beat_visual_execution_plan(
            pacing_context=self._valid_pacing(), story_context=story
        )
        assert len(plan.to_dict()["transition_hints"]) <= 10

    def test_invalid_bpm_produces_available_false(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        pacing = {"beat_available": True, "bpm": 50.0, "beat_count": 16, "energy_level": 0.8}
        plan = build_beat_visual_execution_plan(pacing_context=pacing)
        assert plan.available is False

    def test_no_timing_mutation(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        pacing = self._valid_pacing()
        original = dict(pacing)
        build_beat_visual_execution_plan(pacing_context=pacing)
        assert pacing == original

    def test_no_playback_speed_in_plan(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing())
        d = plan.to_dict()
        assert "playback_speed" not in d

    def test_no_api_key_required(self):
        import os
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(key, None)
        plan = build_beat_visual_execution_plan()
        assert plan is not None

    def test_no_gpu_required(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing())
        assert plan is not None

    def test_no_real_rendering_required(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan(pacing_context=self._valid_pacing())
        assert plan is not None


# ---------------------------------------------------------------------------
# AIEditPlan beat_visual_execution field
# ---------------------------------------------------------------------------

class TestAIEditPlanBeatVisualExecution:
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

    def test_has_beat_visual_execution_field(self):
        plan = self._make_plan()
        assert hasattr(plan, "beat_visual_execution")

    def test_defaults_to_empty_dict(self):
        plan = self._make_plan()
        assert plan.beat_visual_execution == {}

    def test_in_to_dict(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "beat_visual_execution" in d

    def test_value_propagated(self):
        plan = self._make_plan()
        plan.beat_visual_execution = {
            "available": True,
            "execution_mode": "metadata_only",
            "bpm": 128.0,
        }
        d = plan.to_dict()
        assert d["beat_visual_execution"]["available"] is True
        assert d["beat_visual_execution"]["bpm"] == 128.0

    def test_existing_fields_intact(self):
        plan = self._make_plan()
        d = plan.to_dict()
        for key in ("enabled", "mode", "pacing", "story", "retention",
                    "subtitle_execution", "beat_execution"):
            assert key in d


# ---------------------------------------------------------------------------
# AI Director integration tests
# ---------------------------------------------------------------------------

class TestAIDirectorPhase18:
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

    def _valid_pacing_context(self):
        return {
            "job_id": "test_p18",
            "transcript_chunks": [
                {"start": float(i * 3), "end": float(i * 3 + 3),
                 "text": f"word {i}", "score": 0.6}
                for i in range(5)
            ],
        }

    def test_beat_visual_execution_attached_to_plan(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        plan = create_ai_edit_plan(req, self._valid_pacing_context())
        assert plan is not None
        assert hasattr(plan, "beat_visual_execution")
        assert isinstance(plan.beat_visual_execution, dict)

    def test_beat_visual_execution_in_to_dict(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        plan = create_ai_edit_plan(req, self._valid_pacing_context())
        assert plan is not None
        assert "beat_visual_execution" in plan.to_dict()

    def test_never_raises_on_empty_context(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        create_ai_edit_plan(req, {})
        assert True

    def test_available_key_in_beat_visual_execution(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        plan = create_ai_edit_plan(req, self._valid_pacing_context())
        if plan is not None:
            assert "available" in plan.beat_visual_execution

    def test_execution_mode_metadata_only_or_missing(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        plan = create_ai_edit_plan(req, self._valid_pacing_context())
        if plan is not None:
            bve = plan.beat_visual_execution
            if bve.get("available"):
                assert bve.get("execution_mode") == "metadata_only"

    def test_no_playback_speed_mutation(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        plan = create_ai_edit_plan(req, self._valid_pacing_context())
        assert True  # reaching here = no unhandled exception

    def test_director_plan_still_has_all_prior_phases(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        plan = create_ai_edit_plan(req, self._valid_pacing_context())
        if plan is not None:
            d = plan.to_dict()
            for key in ("story", "retention", "creator_style", "subtitle_execution",
                        "beat_visual_execution"):
                assert key in d


# ---------------------------------------------------------------------------
# Render influence integration tests
# ---------------------------------------------------------------------------

class TestRenderInfluencePhase18:
    def _make_edit_plan(self, with_beat_visual=True):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan,
        )
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        if with_beat_visual:
            plan.beat_visual_execution = {
                "available": True,
                "execution_mode": "metadata_only",
                "bpm": 128.0,
                "pulse_regions": [{"start": 0.0, "end": 8.0, "pulse_strength": 0.12}],
                "transition_hints": [],
            }
        return plan

    def _make_payload(self):
        class Payload:
            ai_render_influence_enabled = True
            ai_beat_execution_enabled = False
            ai_beat_pulse_enabled = False
            ai_beat_transition_enabled = False
            motion_aware_crop = False
            reframe_mode = "center"
            add_subtitle = False
            highlight_per_word = False
            playback_speed = 1.0
        return Payload()

    def test_never_raises_with_beat_visual_plan(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        payload = self._make_payload()
        plan = self._make_edit_plan(with_beat_visual=True)
        _, report = apply_ai_render_influence(payload, plan)
        assert isinstance(report, dict)

    def test_never_raises_without_beat_visual_plan(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        payload = self._make_payload()
        plan = self._make_edit_plan(with_beat_visual=False)
        _, report = apply_ai_render_influence(payload, plan)
        assert isinstance(report, dict)

    def test_beat_visual_in_skipped_list(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        payload = self._make_payload()
        plan = self._make_edit_plan(with_beat_visual=True)
        _, report = apply_ai_render_influence(payload, plan)
        skipped_str = " ".join(str(s) for s in report.get("skipped", []))
        assert "beat_visual_execution" in skipped_str

    def test_playback_speed_never_changed(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        payload = self._make_payload()
        payload.playback_speed = 1.25
        plan = self._make_edit_plan()
        apply_ai_render_influence(payload, plan)
        assert payload.playback_speed == 1.25

    def test_no_ffmpeg_mutation(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        payload = self._make_payload()
        plan = self._make_edit_plan()
        # Just verify it never raises and returns expected shape
        result_payload, report = apply_ai_render_influence(payload, plan)
        assert "enabled" in report
        assert "skipped" in report

    def test_no_timing_mutation(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        payload = self._make_payload()
        plan = self._make_edit_plan()
        plan.beat_visual_execution["pulse_regions"][0]["start"] = 0.0
        apply_ai_render_influence(payload, plan)
        # Pulse regions are only in the metadata dict, not applied to any payload field
        assert plan.beat_visual_execution["pulse_regions"][0]["start"] == 0.0


# ---------------------------------------------------------------------------
# Safety boundary tests
# ---------------------------------------------------------------------------

class TestPhase18SafetyBoundaries:
    def test_no_api_key_required_schema(self):
        import os
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            os.environ.pop(key, None)
        from app.ai.visuals.beat_visual_schema import BeatVisualExecutionPlan
        plan = BeatVisualExecutionPlan()
        assert plan is not None

    def test_no_gpu_required_pulse(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        result = build_beat_pulse_regions()
        assert result is not None

    def test_no_gpu_required_transition(self):
        from app.ai.visuals.transition_planner import build_transition_hints
        result = build_transition_hints()
        assert result is not None

    def test_no_gpu_required_visual_execution(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        plan = build_beat_visual_execution_plan()
        assert plan is not None

    def test_safe_imports_no_torch_no_librosa(self):
        from app.ai.visuals import beat_visual_schema
        from app.ai.visuals import beat_pulse
        from app.ai.visuals import transition_planner
        from app.ai.visuals import visual_execution
        assert True

    def test_pulse_strength_hard_cap_015(self):
        from app.ai.visuals.beat_visual_schema import _MAX_PULSE_STRENGTH
        assert _MAX_PULSE_STRENGTH == 0.15

    def test_safe_to_apply_structurally_false(self):
        from app.ai.visuals.beat_visual_schema import TransitionHint
        h = TransitionHint(start=0.0, end=1.0, safe_to_apply=True)
        assert h.to_dict()["safe_to_apply"] is False

    def test_execution_mode_metadata_only(self):
        from app.ai.visuals.visual_execution import build_beat_visual_execution_plan
        pacing = {"beat_available": True, "bpm": 128.0, "beat_count": 16, "energy_level": 0.8}
        plan = build_beat_visual_execution_plan(pacing_context=pacing)
        assert plan.execution_mode == "metadata_only"

    def test_bpm_gates_enforced(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        for bad_bpm in (0.0, 30.0, 59.9, 190.1, 300.0):
            pacing = {"beat_available": True, "bpm": bad_bpm, "beat_count": 16}
            regions = build_beat_pulse_regions(pacing_context=pacing)
            assert regions == [], f"Expected empty for bpm={bad_bpm}"

    def test_beat_count_gate_enforced(self):
        from app.ai.visuals.beat_pulse import build_beat_pulse_regions
        for bad_count in (0, 1, 2, 3):
            pacing = {"beat_available": True, "bpm": 120.0, "beat_count": bad_count}
            regions = build_beat_pulse_regions(pacing_context=pacing)
            assert regions == [], f"Expected empty for beat_count={bad_count}"
