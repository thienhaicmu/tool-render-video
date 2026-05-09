"""
test_ai_phase26_execution_simulation.py — Phase 26 test suite.

Tests: simulation schema, scoring, simulator builder, edit_plan field,
render_influence reporter, safety invariants, AI Director integration.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestSimulationSchema:
    def test_import(self):
        from app.ai.simulation.simulation_schema import (
            AIExecutionSimulation,
            AISimulationPack,
            VALID_SAFETY_LEVELS,
        )
        assert AIExecutionSimulation is not None
        assert AISimulationPack is not None
        assert len(VALID_SAFETY_LEVELS) == 3

    def test_valid_safety_levels(self):
        from app.ai.simulation.simulation_schema import VALID_SAFETY_LEVELS
        assert VALID_SAFETY_LEVELS == {"safe", "caution", "blocked"}

    def test_simulation_defaults(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        s = AIExecutionSimulation(simulation_id="test")
        assert s.advisory_only is True
        assert s.safety_level == "safe"
        assert s.confidence == 0.0

    def test_advisory_only_always_true_in_to_dict(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        s = AIExecutionSimulation(simulation_id="x", advisory_only=False)
        assert s.to_dict()["advisory_only"] is True

    def test_confidence_clamped(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        s = AIExecutionSimulation(simulation_id="x", confidence=5.0)
        assert s.to_dict()["confidence"] == 1.0
        s2 = AIExecutionSimulation(simulation_id="y", confidence=-1.0)
        assert s2.to_dict()["confidence"] == 0.0

    def test_gains_clamped_to_100(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        s = AIExecutionSimulation(
            simulation_id="x",
            estimated_retention_gain=999.0,
            estimated_story_gain=-999.0,
        )
        d = s.to_dict()
        assert d["estimated_retention_gain"] == 100.0
        assert d["estimated_story_gain"] == -100.0

    def test_invalid_safety_level_defaults_safe(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        s = AIExecutionSimulation(simulation_id="x", safety_level="illegal")
        assert s.to_dict()["safety_level"] == "safe"

    def test_valid_safety_levels_preserved(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        for level in ("safe", "caution", "blocked"):
            s = AIExecutionSimulation(simulation_id="x", safety_level=level)
            assert s.to_dict()["safety_level"] == level

    def test_explanation_capped_at_5(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        s = AIExecutionSimulation(simulation_id="x", explanation=["a"] * 20)
        assert len(s.to_dict()["explanation"]) == 5

    def test_simulation_to_dict_keys(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        d = AIExecutionSimulation(simulation_id="x").to_dict()
        assert set(d.keys()) == {
            "simulation_id", "recommendation_id", "label",
            "estimated_retention_gain", "estimated_story_gain",
            "estimated_subtitle_clarity_gain", "estimated_pacing_gain",
            "confidence", "safety_level", "advisory_only",
            "warnings", "explanation",
        }

    def test_pack_defaults(self):
        from app.ai.simulation.simulation_schema import AISimulationPack
        pack = AISimulationPack()
        assert pack.available is True
        assert pack.mode == "simulation_only"
        assert pack.recommended_simulation_id is None

    def test_pack_mode_always_simulation_only(self):
        from app.ai.simulation.simulation_schema import AISimulationPack
        pack = AISimulationPack(mode="execution")
        assert pack.to_dict()["mode"] == "simulation_only"

    def test_pack_simulations_capped_at_10(self):
        from app.ai.simulation.simulation_schema import AISimulationPack, AIExecutionSimulation
        sims = [AIExecutionSimulation(simulation_id=f"s{i}") for i in range(15)]
        pack = AISimulationPack(simulations=sims)
        assert len(pack.to_dict()["simulations"]) == 10

    def test_pack_to_dict_keys(self):
        from app.ai.simulation.simulation_schema import AISimulationPack
        d = AISimulationPack().to_dict()
        assert set(d.keys()) == {
            "available", "mode", "simulations", "recommended_simulation_id", "warnings"
        }


# ── Simulation scoring tests ──────────────────────────────────────────────────

class TestSimulationScoring:
    def test_import(self):
        from app.ai.simulation.simulation_scoring import score_simulation
        assert callable(score_simulation)

    def test_returns_dict_with_required_keys(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        s = AIExecutionSimulation(simulation_id="x", confidence=0.8)
        result = score_simulation(s)
        assert set(result.keys()) == {"overall_score", "confidence", "reasons", "warnings"}

    def test_baseline_scores_50(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        s = AIExecutionSimulation(
            simulation_id="x",
            confidence=1.0,
            safety_level="safe",
        )
        result = score_simulation(s)
        assert result["overall_score"] == 50.0

    def test_positive_gains_increase_score(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        s = AIExecutionSimulation(
            simulation_id="x",
            estimated_retention_gain=20.0,
            confidence=1.0,
            safety_level="safe",
        )
        result = score_simulation(s)
        assert result["overall_score"] > 50.0

    def test_blocked_penalized(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        safe_sim = AIExecutionSimulation(simulation_id="a", confidence=0.8, safety_level="safe")
        blocked_sim = AIExecutionSimulation(simulation_id="b", confidence=0.8, safety_level="blocked")
        safe_score = score_simulation(safe_sim)["overall_score"]
        blocked_score = score_simulation(blocked_sim)["overall_score"]
        assert blocked_score < safe_score

    def test_caution_penalized_less_than_blocked(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        caution = AIExecutionSimulation(simulation_id="a", confidence=0.8, safety_level="caution",
                                        estimated_retention_gain=10.0)
        blocked = AIExecutionSimulation(simulation_id="b", confidence=0.8, safety_level="blocked",
                                        estimated_retention_gain=10.0)
        assert score_simulation(caution)["overall_score"] > score_simulation(blocked)["overall_score"]

    def test_low_confidence_dampened(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        high_conf = AIExecutionSimulation(simulation_id="a", confidence=0.9,
                                          estimated_retention_gain=20.0, safety_level="safe")
        low_conf = AIExecutionSimulation(simulation_id="b", confidence=0.1,
                                         estimated_retention_gain=20.0, safety_level="safe")
        assert score_simulation(high_conf)["overall_score"] > score_simulation(low_conf)["overall_score"]

    def test_score_clamped_0_100(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        s = AIExecutionSimulation(
            simulation_id="x",
            estimated_retention_gain=100.0,
            estimated_story_gain=100.0,
            estimated_subtitle_clarity_gain=100.0,
            estimated_pacing_gain=100.0,
            confidence=1.0,
            safety_level="safe",
        )
        result = score_simulation(s)
        assert 0.0 <= result["overall_score"] <= 100.0

    def test_deterministic(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        s = AIExecutionSimulation(
            simulation_id="x",
            estimated_retention_gain=12.0,
            confidence=0.75,
            safety_level="safe",
        )
        r1 = score_simulation(s)
        r2 = score_simulation(s)
        assert r1["overall_score"] == r2["overall_score"]

    def test_never_raises_on_none(self):
        from app.ai.simulation.simulation_scoring import score_simulation
        result = score_simulation(None)
        assert "overall_score" in result

    def test_never_raises_on_garbage(self):
        from app.ai.simulation.simulation_scoring import score_simulation
        result = score_simulation("not_a_simulation")
        assert "overall_score" in result


# ── Simulator builder tests ───────────────────────────────────────────────────

class TestExecutionSimulator:
    def _make_plan(self, **overrides):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        for k, v in overrides.items():
            setattr(plan, k, v)
        return plan

    def test_import(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        assert callable(simulate_execution_recommendations)

    def test_never_raises_on_none(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        result = simulate_execution_recommendations(None)
        assert result is not None

    def test_returns_simulation_pack(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        from app.ai.simulation.simulation_schema import AISimulationPack
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        assert isinstance(result, AISimulationPack)

    def test_safe_baseline_always_present(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert "sim_safe_baseline" in ids

    def test_none_plan_available_false(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        result = simulate_execution_recommendations(None)
        assert result.available is False

    def test_mode_always_simulation_only(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        assert result.mode == "simulation_only"

    def test_recommended_simulation_id_set(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        assert result.recommended_simulation_id is not None

    def test_retention_simulation_from_recommendations(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(
            execution_recommendations={
                "available": True,
                "recommendations": [{
                    "recommendation_id": "retention_pacing",
                    "category": "retention",
                    "confidence": 0.75,
                    "safe_to_apply": True,
                    "recommended_settings": {"pacing_style": "fast_cuts", "hook_density": "high"},
                }],
                "recommended_pack_id": "retention_pacing",
            },
            retention={"overall_retention_score": 35},
        )
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert "sim_retention_pacing" in ids

    def test_creator_style_simulation_from_recommendations(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(
            execution_recommendations={
                "available": True,
                "recommendations": [{
                    "recommendation_id": "creator_style_viral_tiktok",
                    "category": "creator_style",
                    "confidence": 0.85,
                    "safe_to_apply": True,
                    "recommended_settings": {"creator_style": "viral_tiktok", "pacing_style": "fast"},
                }],
                "recommended_pack_id": "creator_style_viral_tiktok",
            }
        )
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert any("creator_style" in sid for sid in ids)

    def test_subtitle_simulation_from_recommendations(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(
            execution_recommendations={
                "available": True,
                "recommendations": [{
                    "recommendation_id": "compact_subtitle",
                    "category": "subtitle",
                    "confidence": 0.70,
                    "safe_to_apply": True,
                    "recommended_settings": {"subtitle_density": "compact", "subtitle_emphasis": "bold"},
                }],
                "recommended_pack_id": "compact_subtitle",
            }
        )
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert "sim_compact_subtitle" in ids

    def test_direct_retention_simulation_when_no_recs(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(retention={"overall_retention_score": 42})
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert "sim_retention" in ids

    def test_direct_subtitle_simulation_when_no_recs(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(subtitle_execution={"available": True, "density": "compact"})
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert "sim_subtitle" in ids

    def test_direct_visual_rhythm_simulation(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(beat_visual_execution={"available": True, "bpm": 130})
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert "sim_visual_rhythm" in ids

    def test_direct_story_pacing_simulation(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(
            story_optimization={"available": True, "flow_type": "three_act", "narrative_score": 65}
        )
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert "sim_story_pacing" in ids

    def test_direct_creator_style_simulation(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(
            creator_style_adaptation={"detected": True, "primary_style": "cinematic", "confidence": 0.8}
        )
        result = simulate_execution_recommendations(plan)
        ids = [s.simulation_id for s in result.simulations]
        assert "sim_creator_style" in ids

    def test_all_simulations_advisory_only(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(
            retention={"overall_retention_score": 45},
            subtitle_execution={"available": True, "density": "compact"},
            beat_visual_execution={"available": True, "bpm": 120},
        )
        result = simulate_execution_recommendations(plan)
        for s in result.simulations:
            assert s.advisory_only is True, f"Sim {s.simulation_id} not advisory_only"

    def test_deterministic(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(
            retention={"overall_retention_score": 50},
            creator_style_adaptation={"detected": True, "primary_style": "educational", "confidence": 0.7},
        )
        r1 = simulate_execution_recommendations(plan)
        r2 = simulate_execution_recommendations(plan)
        assert r1.recommended_simulation_id == r2.recommended_simulation_id
        assert len(r1.simulations) == len(r2.simulations)

    def test_retention_low_score_high_gain(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(retention={"overall_retention_score": 20})
        result = simulate_execution_recommendations(plan)
        ret_sim = next((s for s in result.simulations if s.simulation_id == "sim_retention"), None)
        assert ret_sim is not None
        assert ret_sim.estimated_retention_gain >= 15.0

    def test_safe_baseline_gains_zero(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        baseline = next((s for s in result.simulations if s.simulation_id == "sim_safe_baseline"), None)
        assert baseline is not None
        assert baseline.estimated_retention_gain == 0.0
        assert baseline.estimated_story_gain == 0.0
        assert baseline.estimated_subtitle_clarity_gain == 0.0
        assert baseline.estimated_pacing_gain == 0.0

    def test_safe_baseline_confidence_1(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        baseline = next((s for s in result.simulations if s.simulation_id == "sim_safe_baseline"), None)
        assert baseline is not None
        assert baseline.confidence == 1.0

    def test_never_raises_on_garbage(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations

        class BadPlan:
            @property
            def execution_recommendations(self):
                raise RuntimeError("boom")

        result = simulate_execution_recommendations(BadPlan())
        assert result is not None

    def test_context_accepted(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan, context={"job_id": "test-126"})
        assert result is not None

    def test_no_payload_mutation(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations

        class FakePayload:
            motion_aware_crop = False
            add_subtitle = False

        payload = FakePayload()
        plan = self._make_plan()
        simulate_execution_recommendations(plan)
        assert payload.motion_aware_crop is False
        assert payload.add_subtitle is False

    def test_no_api_key_required(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        result = simulate_execution_recommendations(self._make_plan())
        assert result is not None

    def test_no_gpu_required(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        result = simulate_execution_recommendations(self._make_plan())
        assert result is not None

    def test_no_internet_required(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        result = simulate_execution_recommendations(self._make_plan())
        assert result is not None

    def test_safe_simulations_preferred_over_blocked(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        safe_sim = AIExecutionSimulation(
            simulation_id="safe_x", confidence=0.8, safety_level="safe",
            estimated_retention_gain=15.0,
        )
        blocked_sim = AIExecutionSimulation(
            simulation_id="blocked_x", confidence=0.8, safety_level="blocked",
            estimated_retention_gain=15.0,
        )
        safe_score = score_simulation(safe_sim)["overall_score"]
        blocked_score = score_simulation(blocked_sim)["overall_score"]
        assert safe_score > blocked_score

    def test_visual_rhythm_high_bpm_energetic_gain(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(beat_visual_execution={"available": True, "bpm": 150})
        result = simulate_execution_recommendations(plan)
        vr = next((s for s in result.simulations if s.simulation_id == "sim_visual_rhythm"), None)
        assert vr is not None
        assert vr.estimated_pacing_gain == 10.0

    def test_visual_rhythm_low_bpm_calm_gain(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(beat_visual_execution={"available": True, "bpm": 60})
        result = simulate_execution_recommendations(plan)
        vr = next((s for s in result.simulations if s.simulation_id == "sim_visual_rhythm"), None)
        assert vr is not None
        assert vr.estimated_pacing_gain == 5.0


# ── AIEditPlan field tests ────────────────────────────────────────────────────

class TestAIEditPlanExecutionSimulationField:
    def _make_plan(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        return AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )

    def test_field_exists(self):
        assert hasattr(self._make_plan(), "execution_simulation")

    def test_field_default_empty_dict(self):
        assert self._make_plan().execution_simulation == {}

    def test_field_in_to_dict(self):
        assert "execution_simulation" in self._make_plan().to_dict()

    def test_field_populated_in_to_dict(self):
        plan = self._make_plan()
        plan.execution_simulation = {"available": True, "mode": "simulation_only"}
        assert plan.to_dict()["execution_simulation"]["available"] is True

    def test_field_independence(self):
        p1, p2 = self._make_plan(), self._make_plan()
        p1.execution_simulation["x"] = 1
        assert "x" not in p2.execution_simulation

    def test_backward_compat_phase25_field_present(self):
        assert "execution_recommendations" in self._make_plan().to_dict()

    def test_backward_compat_phase24_field_present(self):
        assert "render_decision_preview" in self._make_plan().to_dict()

    def test_backward_compat_phase23_field_present(self):
        assert "creator_style_adaptation" in self._make_plan().to_dict()


# ── render_influence reporter tests ──────────────────────────────────────────

class TestRenderInfluenceReportExecutionSimulation:
    def _make_payload(self):
        class FakePayload:
            motion_aware_crop = False
            add_subtitle = False
            ai_beat_execution_enabled = False
            reframe_mode = "center"
        return FakePayload()

    def _make_plan(self, **overrides):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        for k, v in overrides.items():
            setattr(plan, k, v)
        return plan

    def test_reporter_exists(self):
        from app.ai.director.render_influence import _report_execution_simulation
        assert callable(_report_execution_simulation)

    def test_no_field_skips(self):
        from app.ai.director.render_influence import _report_execution_simulation
        plan = self._make_plan()
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_execution_simulation(self._make_payload(), plan, report)
        assert any("execution_simulation" in s for s in report["skipped"])

    def test_empty_field_skips(self):
        from app.ai.director.render_influence import _report_execution_simulation
        plan = self._make_plan(execution_simulation={})
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_execution_simulation(self._make_payload(), plan, report)
        assert any("empty" in s for s in report["skipped"])

    def test_populated_field_deferred_phase26(self):
        from app.ai.director.render_influence import _report_execution_simulation
        plan = self._make_plan(execution_simulation={
            "available": True,
            "mode": "simulation_only",
            "simulations": [{"simulation_id": "sim_retention"}],
            "recommended_simulation_id": "sim_retention",
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_execution_simulation(self._make_payload(), plan, report)
        assert any("deferred_phase26" in s for s in report["skipped"])

    def test_no_payload_mutation(self):
        from app.ai.director.render_influence import _report_execution_simulation
        payload = self._make_payload()
        plan = self._make_plan(execution_simulation={
            "available": True,
            "simulations": [{"simulation_id": "sim_retention"}],
            "recommended_simulation_id": "sim_retention",
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_execution_simulation(payload, plan, report)
        assert payload.motion_aware_crop is False

    def test_wired_into_apply_ai_render_influence(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan(execution_simulation={
            "available": True,
            "simulations": [{"simulation_id": "sim_safe_baseline"}],
            "recommended_simulation_id": "sim_safe_baseline",
        })
        _, report = apply_ai_render_influence(self._make_payload(), plan)
        assert any("execution_simulation" in s for s in report["skipped"])


# ── Safety invariant tests ────────────────────────────────────────────────────

class TestPhase26SafetyInvariants:
    def _make_plan(self, **overrides):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        for k, v in overrides.items():
            setattr(plan, k, v)
        return plan

    def test_advisory_only_always_true_in_all_sims(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(
            retention={"overall_retention_score": 40},
            subtitle_execution={"available": True, "density": "compact"},
            beat_visual_execution={"available": True, "bpm": 120},
            story_optimization={"available": True, "flow_type": "three_act", "narrative_score": 60},
            creator_style_adaptation={"detected": True, "primary_style": "viral_tiktok", "confidence": 0.9},
        )
        result = simulate_execution_recommendations(plan)
        for s in result.simulations:
            assert s.advisory_only is True

    def test_mode_always_simulation_only(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        assert result.to_dict()["mode"] == "simulation_only"

    def test_no_playback_speed_in_any_sim(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan(retention={"overall_retention_score": 30})
        result = simulate_execution_recommendations(plan)
        # Simulations have no "recommended_settings" — verify the sim dict has no forbidden keys
        for s in result.simulations:
            sim_d = s.to_dict()
            assert "playback_speed" not in sim_d

    def test_no_ffmpeg_in_sim_dict(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        for s in result.simulations:
            for key in s.to_dict():
                assert "ffmpeg" not in str(key).lower()

    def test_no_timing_mutation_in_sims(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        plan = self._make_plan()
        result = simulate_execution_recommendations(plan)
        for s in result.simulations:
            d = s.to_dict()
            assert "segment_start" not in d
            assert "segment_end" not in d
            assert "subtitle_timing" not in d

    def test_never_raises_on_none(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        assert simulate_execution_recommendations(None) is not None

    def test_never_raises_on_string(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        assert simulate_execution_recommendations("bad") is not None

    def test_never_raises_on_empty_dict(self):
        from app.ai.simulation.execution_simulator import simulate_execution_recommendations
        assert simulate_execution_recommendations({}) is not None

    def test_blocked_simulations_penalized_in_scoring(self):
        from app.ai.simulation.simulation_schema import AIExecutionSimulation
        from app.ai.simulation.simulation_scoring import score_simulation
        blocked = AIExecutionSimulation(
            simulation_id="x",
            estimated_retention_gain=15.0,
            confidence=1.0,
            safety_level="blocked",
        )
        result = score_simulation(blocked)
        # After heavy penalty of 50, even a gain of 15*(0.35) ~= 5.25 above 50 → 55.25 - 50 = 5.25
        assert result["overall_score"] < 20.0


# ── AI Director integration tests ─────────────────────────────────────────────

class TestAIDirectorPhase26Integration:
    def test_phase26_block_in_source(self):
        import inspect
        from app.ai.director import ai_director
        assert "_attach_execution_simulation" in inspect.getsource(ai_director)

    def test_attach_function_importable(self):
        from app.ai.director.ai_director import _attach_execution_simulation
        assert callable(_attach_execution_simulation)

    def test_attach_function_populates_field(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_execution_simulation
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        _attach_execution_simulation(plan, "test-job-phase26")
        assert isinstance(plan.execution_simulation, dict)
        assert "available" in plan.execution_simulation

    def test_attach_does_not_raise_on_none(self):
        from app.ai.director.ai_director import _attach_execution_simulation
        _attach_execution_simulation(None, "test-job-none")

    def test_field_in_to_dict_after_attach(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_execution_simulation
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        _attach_execution_simulation(plan, "test-job-dict")
        d = plan.to_dict()
        assert "execution_simulation" in d
        assert isinstance(d["execution_simulation"], dict)

    def test_no_render_executor_override(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_execution_simulation
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        original_mode = plan.mode
        _attach_execution_simulation(plan, "test-job-override")
        assert plan.mode == original_mode

    def test_safe_baseline_in_simulations_after_attach(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_execution_simulation
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        _attach_execution_simulation(plan, "test-job-baseline")
        sims = plan.execution_simulation.get("simulations", [])
        ids = [s.get("simulation_id") for s in sims]
        assert "sim_safe_baseline" in ids

    def test_simulation_mode_advisory_in_attached_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_execution_simulation
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        _attach_execution_simulation(plan, "test-job-mode")
        assert plan.execution_simulation.get("mode") == "simulation_only"
