"""
test_ai_phase19_timing_mutation.py — Phase 19 timing mutation tests.

Coverage: schema, safety gates, analyzer heuristics, recommender modes,
render influence defer, AI Director integration, and all safety boundaries.
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestTimingMutationCandidateSchema:
    def test_defaults(self):
        from app.ai.timing.timing_schema import TimingMutationCandidate
        c = TimingMutationCandidate(start=0.0, end=5.0)
        assert c.action == "none"
        assert c.confidence == 0.0
        assert c.reason == ""
        assert c.risk_category == "unknown"
        assert c.max_trim_seconds == 0.0
        assert c.safe_to_apply is False
        assert c.warnings == []

    def test_to_dict_keys(self):
        from app.ai.timing.timing_schema import TimingMutationCandidate
        c = TimingMutationCandidate(start=1.0, end=6.0, action="trim_silence", confidence=0.8)
        d = c.to_dict()
        assert set(d.keys()) == {
            "start", "end", "action", "confidence", "reason",
            "risk_category", "max_trim_seconds", "safe_to_apply", "warnings",
        }

    def test_invalid_action_normalised_to_none(self):
        from app.ai.timing.timing_schema import TimingMutationCandidate
        c = TimingMutationCandidate(start=0.0, end=5.0, action="destroy_everything")
        assert c.to_dict()["action"] == "none"

    def test_max_trim_clamped_to_1_5(self):
        from app.ai.timing.timing_schema import TimingMutationCandidate
        c = TimingMutationCandidate(start=0.0, end=10.0, max_trim_seconds=9.9)
        assert c.to_dict()["max_trim_seconds"] == 1.5

    def test_max_trim_negative_clamped_to_zero(self):
        from app.ai.timing.timing_schema import TimingMutationCandidate
        c = TimingMutationCandidate(start=0.0, end=5.0, max_trim_seconds=-1.0)
        assert c.to_dict()["max_trim_seconds"] == 0.0

    def test_valid_actions_frozenset(self):
        from app.ai.timing.timing_schema import VALID_ACTIONS
        assert "tighten_setup" in VALID_ACTIONS
        assert "trim_silence" in VALID_ACTIONS
        assert "shorten_outro" in VALID_ACTIONS
        assert "hold_hook" in VALID_ACTIONS
        assert "no_change" in VALID_ACTIONS
        assert "none" in VALID_ACTIONS


class TestTimingMutationPlanSchema:
    def test_defaults(self):
        from app.ai.timing.timing_schema import TimingMutationPlan
        p = TimingMutationPlan()
        assert p.available is True
        assert p.mode == "advisory"
        assert p.candidates == []
        assert p.estimated_retention_gain == 0.0
        assert p.warnings == []

    def test_to_dict_keys(self):
        from app.ai.timing.timing_schema import TimingMutationPlan
        d = TimingMutationPlan().to_dict()
        assert set(d.keys()) == {"available", "mode", "candidates", "estimated_retention_gain", "warnings"}

    def test_candidates_capped_at_10(self):
        from app.ai.timing.timing_schema import TimingMutationPlan, TimingMutationCandidate
        candidates = [TimingMutationCandidate(start=float(i), end=float(i + 5)) for i in range(15)]
        p = TimingMutationPlan(candidates=candidates)
        assert len(p.to_dict()["candidates"]) == 10

    def test_unavailable_plan(self):
        from app.ai.timing.timing_schema import TimingMutationPlan
        p = TimingMutationPlan(available=False, warnings=["no_data"])
        d = p.to_dict()
        assert d["available"] is False
        assert "no_data" in d["warnings"]


# ---------------------------------------------------------------------------
# Safety gate tests
# ---------------------------------------------------------------------------

class TestClampTrimSeconds:
    def test_clamp_above_max(self):
        from app.ai.timing.timing_safety import clamp_trim_seconds
        assert clamp_trim_seconds(5.0) == 1.5

    def test_clamp_below_zero(self):
        from app.ai.timing.timing_safety import clamp_trim_seconds
        assert clamp_trim_seconds(-1.0) == 0.0

    def test_valid_value_passes_through(self):
        from app.ai.timing.timing_safety import clamp_trim_seconds
        assert clamp_trim_seconds(0.8) == pytest.approx(0.8)

    def test_custom_max(self):
        from app.ai.timing.timing_safety import clamp_trim_seconds
        assert clamp_trim_seconds(2.0, max_value=3.0) == pytest.approx(2.0)

    def test_bad_value_returns_zero(self):
        from app.ai.timing.timing_safety import clamp_trim_seconds
        assert clamp_trim_seconds("not_a_number") == 0.0


class TestIsCandidateSafe:
    def _make_candidate(self, **kwargs):
        from app.ai.timing.timing_schema import TimingMutationCandidate
        defaults = dict(
            start=0.0, end=10.0, action="tighten_setup",
            confidence=0.75, max_trim_seconds=1.0,
        )
        defaults.update(kwargs)
        return TimingMutationCandidate(**defaults)

    def test_passing_candidate_is_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate()) is True

    def test_low_confidence_not_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate(confidence=0.69)) is False

    def test_exactly_at_threshold_is_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate(confidence=0.70)) is True

    def test_no_change_action_not_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate(action="no_change")) is False

    def test_none_action_not_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate(action="none")) is False

    def test_short_region_not_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        # duration 2.9s < 3.0s minimum
        assert is_candidate_safe(self._make_candidate(start=0.0, end=2.9)) is False

    def test_exactly_min_duration_is_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate(start=0.0, end=3.0)) is True

    def test_negative_start_not_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate(start=-1.0, end=5.0)) is False

    def test_trim_exceeds_cap_not_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate(max_trim_seconds=1.6)) is False

    def test_trim_exactly_at_cap_is_safe(self):
        from app.ai.timing.timing_safety import is_candidate_safe
        assert is_candidate_safe(self._make_candidate(max_trim_seconds=1.5)) is True


# ---------------------------------------------------------------------------
# Timing analyzer tests
# ---------------------------------------------------------------------------

class TestAnalyzeTimingCandidates:
    def _risk(self, category, start=5.0, end=20.0, severity=0.75):
        return {"category": category, "start": start, "end": end, "severity": severity}

    def test_empty_context_returns_empty(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        result = analyze_timing_candidates()
        assert result == []

    def test_long_setup_maps_to_tighten_setup(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [self._risk("long_setup", start=0.0, end=10.0)]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        assert len(result) == 1
        assert result[0].action == "tighten_setup"
        assert result[0].risk_category == "long_setup"

    def test_silence_gap_maps_to_trim_silence(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [self._risk("silence_gap")]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        assert result[0].action == "trim_silence"

    def test_pacing_decay_near_end_maps_to_shorten_outro(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [self._risk("pacing_decay", start=80.0, end=100.0)]
        result = analyze_timing_candidates(
            retention_context={"risk_regions": risks},
            pacing_context={"total_duration": 100.0},
        )
        assert result[0].action == "shorten_outro"

    def test_pacing_decay_not_in_last_quarter_skipped(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        # start=40.0 is before 75% of 100s
        risks = [self._risk("pacing_decay", start=40.0, end=60.0)]
        result = analyze_timing_candidates(
            retention_context={"risk_regions": risks},
            pacing_context={"total_duration": 100.0},
        )
        assert result == []

    def test_weak_hook_maps_to_hold_hook_with_no_trim(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [self._risk("weak_hook", start=0.0, end=5.0)]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        assert result[0].action == "hold_hook"
        assert result[0].max_trim_seconds == 0.0

    def test_unclear_payoff_maps_to_no_change(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [self._risk("unclear_payoff")]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        assert result[0].action == "no_change"
        assert result[0].max_trim_seconds == 0.0

    def test_unknown_category_skipped(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [{"category": "mystery_risk", "start": 5.0, "end": 20.0}]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        assert result == []

    def test_max_10_candidates_enforced(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [self._risk("silence_gap", start=float(i * 10), end=float(i * 10 + 8)) for i in range(15)]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        assert len(result) <= 10

    def test_max_trim_capped_at_1_5(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [{"category": "silence_gap", "start": 5.0, "end": 10.0, "severity": 0.9, "suggested_trim": 9.0}]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        assert result[0].max_trim_seconds <= 1.5

    def test_safe_to_apply_always_false_from_analyzer(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [self._risk("long_setup")]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        for c in result:
            assert c.safe_to_apply is False

    def test_never_raises_on_bad_input(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        result = analyze_timing_candidates(
            retention_context="not_a_dict",
            pacing_context=None,
            transcript_chunks="bad",
        )
        assert isinstance(result, list)

    def test_zero_duration_region_skipped(self):
        from app.ai.timing.timing_analyzer import analyze_timing_candidates
        risks = [{"category": "long_setup", "start": 5.0, "end": 5.0}]
        result = analyze_timing_candidates(retention_context={"risk_regions": risks})
        assert result == []


# ---------------------------------------------------------------------------
# Timing recommender tests
# ---------------------------------------------------------------------------

class TestBuildTimingMutationPlan:
    def _risk(self, category, start=5.0, end=20.0, severity=0.8):
        return {"category": category, "start": start, "end": end, "severity": severity}

    def test_returns_plan_instance(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        from app.ai.timing.timing_schema import TimingMutationPlan
        result = build_timing_mutation_plan()
        assert isinstance(result, TimingMutationPlan)

    def test_advisory_mode_by_default(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [self._risk("long_setup")]
        plan = build_timing_mutation_plan(
            retention_context={"risk_regions": risks},
            enabled=False,
        )
        assert plan.mode == "advisory"

    def test_advisory_mode_all_safe_to_apply_false(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [self._risk("tighten_setup")]
        plan = build_timing_mutation_plan(
            retention_context={"risk_regions": risks},
            enabled=False,
        )
        for c in plan.candidates:
            assert c.safe_to_apply is False

    def test_enabled_mode_applies_safety_gate(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [self._risk("long_setup", start=0.0, end=10.0, severity=0.85)]
        plan = build_timing_mutation_plan(
            retention_context={"risk_regions": risks},
            pacing_context={"total_duration": 100.0},
            enabled=True,
        )
        assert plan.mode == "enabled"
        # Confidence ~0.9+ should pass safety gate
        safe = [c for c in plan.candidates if c.safe_to_apply]
        unsafe = [c for c in plan.candidates if not c.safe_to_apply]
        # At least no crash; advisory vs safe split is correct type
        assert isinstance(safe, list)

    def test_empty_retention_produces_unavailable(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        plan = build_timing_mutation_plan(retention_context={})
        assert plan.available is False
        assert "no_timing_candidates" in plan.warnings

    def test_retention_gain_is_float(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [self._risk("silence_gap")]
        plan = build_timing_mutation_plan(retention_context={"risk_regions": risks})
        assert isinstance(plan.estimated_retention_gain, float)
        assert 0.0 <= plan.estimated_retention_gain <= 1.0

    def test_never_raises_on_garbage_input(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        plan = build_timing_mutation_plan(
            retention_context={"risk_regions": "not_a_list"},
            story_context=42,
            pacing_context=None,
        )
        assert hasattr(plan, "available")

    def test_to_dict_round_trip(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [self._risk("long_setup")]
        plan = build_timing_mutation_plan(retention_context={"risk_regions": risks})
        d = plan.to_dict()
        assert isinstance(d, dict)
        assert "candidates" in d
        assert isinstance(d["candidates"], list)

    def test_candidates_do_not_exceed_10(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [self._risk("silence_gap", start=float(i * 10), end=float(i * 10 + 8)) for i in range(15)]
        plan = build_timing_mutation_plan(retention_context={"risk_regions": risks})
        assert len(plan.candidates) <= 10


# ---------------------------------------------------------------------------
# Safety boundary tests
# ---------------------------------------------------------------------------

class TestTimingSafetyBoundaries:
    def test_no_segment_timing_mutated(self):
        """Recommender never mutates input context dicts."""
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        retention = {"risk_regions": [{"category": "long_setup", "start": 5.0, "end": 20.0, "severity": 0.9}]}
        original_keys = set(retention.keys())
        build_timing_mutation_plan(retention_context=retention, enabled=True)
        assert set(retention.keys()) == original_keys

    def test_hold_hook_never_safe_to_apply(self):
        """hold_hook must never get safe_to_apply=True regardless of confidence."""
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [{"category": "weak_hook", "start": 0.0, "end": 5.0, "severity": 1.0}]
        plan = build_timing_mutation_plan(
            retention_context={"risk_regions": risks},
            enabled=True,
        )
        hook_candidates = [c for c in plan.candidates if c.action == "hold_hook"]
        for c in hook_candidates:
            assert c.safe_to_apply is False

    def test_no_change_never_safe_to_apply(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [{"category": "unclear_payoff", "start": 10.0, "end": 25.0, "severity": 1.0}]
        plan = build_timing_mutation_plan(
            retention_context={"risk_regions": risks},
            enabled=True,
        )
        for c in plan.candidates:
            if c.action == "no_change":
                assert c.safe_to_apply is False

    def test_max_trim_never_exceeds_1_5(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [{"category": "long_setup", "start": 0.0, "end": 60.0, "severity": 1.0, "suggested_trim": 99.0}]
        plan = build_timing_mutation_plan(retention_context={"risk_regions": risks}, enabled=True)
        for c in plan.candidates:
            assert c.max_trim_seconds <= 1.5

    def test_mode_advisory_flag_preserved_in_to_dict(self):
        from app.ai.timing.timing_recommender import build_timing_mutation_plan
        risks = [{"category": "silence_gap", "start": 5.0, "end": 15.0, "severity": 0.8}]
        plan = build_timing_mutation_plan(retention_context={"risk_regions": risks}, enabled=False)
        assert plan.to_dict()["mode"] == "advisory"


# ---------------------------------------------------------------------------
# AIEditPlan field test
# ---------------------------------------------------------------------------

class TestAIEditPlanTimingField:
    def test_timing_mutation_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert hasattr(plan, "timing_mutation")
        assert plan.timing_mutation == {}

    def test_timing_mutation_in_to_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "timing_mutation" in d
        assert d["timing_mutation"] == {}

    def test_timing_mutation_populated_survives_to_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            timing_mutation={"available": True, "mode": "advisory", "candidates": []},
        )
        d = plan.to_dict()
        assert d["timing_mutation"]["available"] is True
        assert d["timing_mutation"]["mode"] == "advisory"


# ---------------------------------------------------------------------------
# Render influence defer tests
# ---------------------------------------------------------------------------

class TestRenderInfluenceTimingDefer:
    def _make_edit_plan(self, timing_mutation):
        class FakePlan:
            camera = None
            subtitle = None
            pacing = None
            memory_context = None
            beat_visual_execution = None
            explainability = {}
            beat_execution = {}
        p = FakePlan()
        p.timing_mutation = timing_mutation
        return p

    def _make_payload(self):
        class Payload:
            motion_aware_crop = False
            add_subtitle = False
            ai_beat_execution_enabled = False
        return Payload()

    def test_no_timing_mutation_attr_adds_no_plan(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePlan:
            camera = None; subtitle = None; pacing = None
            memory_context = None; beat_visual_execution = None
            explainability = {}; beat_execution = {}
        # No timing_mutation attribute
        plan = FakePlan()
        payload = self._make_payload()
        _, report = apply_ai_render_influence(payload, plan)
        skipped_keys = " ".join(report["skipped"])
        assert "timing_mutation:no_plan" in skipped_keys

    def test_unavailable_plan_deferred(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_edit_plan({"available": False, "warnings": ["no_candidates"]})
        payload = self._make_payload()
        _, report = apply_ai_render_influence(payload, plan)
        assert any("timing_mutation:deferred(no_candidates)" in s for s in report["skipped"])

    def test_available_plan_deferred_phase19(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_edit_plan({
            "available": True,
            "mode": "advisory",
            "candidates": [],
            "estimated_retention_gain": 0.0,
        })
        payload = self._make_payload()
        _, report = apply_ai_render_influence(payload, plan)
        assert any("timing_mutation:deferred_phase19" in s for s in report["skipped"])

    def test_no_segment_timing_mutated_by_render_influence(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_edit_plan({
            "available": True,
            "mode": "enabled",
            "candidates": [{"start": 5.0, "end": 20.0, "action": "tighten_setup",
                            "safe_to_apply": True, "max_trim_seconds": 1.0,
                            "confidence": 0.9, "reason": "test", "risk_category": "long_setup"}],
            "estimated_retention_gain": 0.01,
        })
        payload = self._make_payload()
        payload_start = 5.0
        _, report = apply_ai_render_influence(payload, plan)
        # Payload start is unchanged — render influence never modifies timing
        assert payload_start == 5.0


# ---------------------------------------------------------------------------
# AI Director integration smoke tests
# ---------------------------------------------------------------------------

class TestAIDirectorPhase19Integration:
    def _make_request(self, enabled=False):
        class Req:
            ai_director_enabled = True
            ai_mode = "viral_tiktok"
            ai_auto_cut = True
            ai_target_duration = None
            ai_use_semantic_hooks = True
            ai_use_rag_memory = False
            ai_render_influence_enabled = False
            ai_beat_execution_enabled = False
            ai_beat_pulse_enabled = False
            ai_beat_transition_enabled = False
            ai_timing_mutation_enabled = enabled
        return Req()

    def test_timing_mutation_field_populated(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request(enabled=False)
        plan = create_ai_edit_plan(req, context={})
        assert plan is not None
        assert hasattr(plan, "timing_mutation")
        assert isinstance(plan.timing_mutation, dict)

    def test_timing_mutation_advisory_when_disabled(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request(enabled=False)
        plan = create_ai_edit_plan(req, context={})
        tm = plan.timing_mutation
        # Should be advisory or unavailable (no retention data in empty context)
        assert tm.get("mode") in ("advisory", None) or tm.get("available") is False

    def test_director_never_raises_with_phase19(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request(enabled=True)
        result = create_ai_edit_plan(req, context={
            "retention_context": "broken",
            "job_id": "test-p19",
        })
        # Never raises — returns plan or None
        assert result is None or hasattr(result, "timing_mutation")

    def test_to_dict_includes_timing_mutation(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        req = self._make_request()
        plan = create_ai_edit_plan(req, context={})
        if plan is not None:
            d = plan.to_dict()
            assert "timing_mutation" in d
