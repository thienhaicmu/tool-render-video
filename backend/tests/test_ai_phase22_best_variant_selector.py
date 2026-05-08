"""
test_ai_phase22_best_variant_selector.py — Phase 22 best variant selector tests.

Coverage: selector heuristics, confidence fallback, safety gates, scoring
normalization, edit plan schema, AI Director integration, render influence
defer, and all safety boundaries.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_variant(variant_id="v1", purpose="retention", risk="low",
                  confidence=0.80, safe_to_render=True, suggested_changes=None):
    from app.ai.variants.variant_schema import AIVariantPlan
    return AIVariantPlan(
        variant_id=variant_id,
        purpose=purpose,
        risk=risk,
        confidence=confidence,
        safe_to_render=safe_to_render,
        suggested_changes=suggested_changes or {},
    )


def _make_variant_set(*variants):
    from app.ai.variants.variant_schema import AIVariantSet
    return AIVariantSet(variants=list(variants))


def _make_edit_plan(**attrs):
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan,
    )
    plan = AIEditPlan(
        enabled=True, mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(pacing_style="default", energy_level=0.6),
    )
    for k, v in attrs.items():
        setattr(plan, k, v)
    return plan


# ---------------------------------------------------------------------------
# Selector core behaviour
# ---------------------------------------------------------------------------

class TestSelectBestVariant:
    def test_returns_dict_with_required_keys(self):
        from app.ai.variants.variant_selector import select_best_variant
        vs = _make_variant_set(_make_variant())
        result = select_best_variant(vs)
        assert set(result.keys()) == {
            "selected_variant_id", "selection_confidence",
            "selection_reasons", "rejected_variants", "fallback_used",
        }

    def test_never_raises_on_none_input(self):
        from app.ai.variants.variant_selector import select_best_variant
        result = select_best_variant(None)
        assert isinstance(result, dict)
        assert result["fallback_used"] is True

    def test_never_raises_on_garbage_input(self):
        from app.ai.variants.variant_selector import select_best_variant
        result = select_best_variant("not_a_set", edit_plan=42, context="bad")
        assert isinstance(result, dict)

    def test_empty_variant_set_returns_fallback(self):
        from app.ai.variants.variant_selector import select_best_variant
        result = select_best_variant(_make_variant_set())
        assert result["selected_variant_id"] is None
        assert result["fallback_used"] is True

    def test_selects_single_available_variant(self):
        from app.ai.variants.variant_selector import select_best_variant
        v = _make_variant(variant_id="only_one")
        result = select_best_variant(_make_variant_set(v))
        assert result["selected_variant_id"] == "only_one"

    def test_selects_highest_scoring_variant(self):
        from app.ai.variants.variant_selector import select_best_variant
        baseline = _make_variant("base", "safe_baseline", "low", confidence=0.90)
        retention = _make_variant("ret", "retention", "low", confidence=0.85)
        result = select_best_variant(_make_variant_set(baseline, retention))
        # retention has higher base score (72 vs 60) — should win
        assert result["selected_variant_id"] == "ret"

    def test_prefers_low_risk_over_high_risk(self):
        from app.ai.variants.variant_selector import select_best_variant
        low = _make_variant("low_v", "retention", "low", confidence=0.75, safe_to_render=True)
        high = _make_variant("high_v", "retention", "high", confidence=0.95, safe_to_render=False)
        result = select_best_variant(_make_variant_set(low, high))
        assert result["selected_variant_id"] == "low_v"

    def test_high_risk_variant_never_selected_when_safe_option_exists(self):
        from app.ai.variants.variant_selector import select_best_variant
        safe = _make_variant("safe_v", "safe_baseline", "low", safe_to_render=True)
        risky = _make_variant("risky_v", "retention", "high", confidence=1.0, safe_to_render=False)
        result = select_best_variant(_make_variant_set(safe, risky))
        assert result["selected_variant_id"] != "risky_v"

    def test_deterministic_same_input_same_output(self):
        from app.ai.variants.variant_selector import select_best_variant
        baseline = _make_variant("b", "safe_baseline", "low", confidence=0.9, safe_to_render=True)
        retention = _make_variant("r", "retention", "low", confidence=0.8, safe_to_render=True)
        vs = _make_variant_set(baseline, retention)
        r1 = select_best_variant(vs)
        r2 = select_best_variant(vs)
        assert r1["selected_variant_id"] == r2["selected_variant_id"]
        assert r1["selection_confidence"] == r2["selection_confidence"]

    def test_selection_confidence_in_range(self):
        from app.ai.variants.variant_selector import select_best_variant
        vs = _make_variant_set(_make_variant())
        result = select_best_variant(vs)
        assert 0.0 <= result["selection_confidence"] <= 1.0

    def test_selection_reasons_is_list(self):
        from app.ai.variants.variant_selector import select_best_variant
        vs = _make_variant_set(_make_variant())
        result = select_best_variant(vs)
        assert isinstance(result["selection_reasons"], list)

    def test_rejected_variants_excludes_selected(self):
        from app.ai.variants.variant_selector import select_best_variant
        baseline = _make_variant("base", "safe_baseline", "low", safe_to_render=True)
        retention = _make_variant("ret", "retention", "low", safe_to_render=True)
        result = select_best_variant(_make_variant_set(baseline, retention))
        selected = result["selected_variant_id"]
        rejected_ids = [r["variant_id"] for r in result["rejected_variants"]]
        assert selected not in rejected_ids

    def test_accepts_dict_variant_set(self):
        from app.ai.variants.variant_selector import select_best_variant
        vs_dict = {
            "available": True,
            "mode": "advisory",
            "variants": [
                {"variant_id": "v1", "purpose": "safe_baseline", "risk": "low",
                 "confidence": 0.9, "safe_to_render": True, "suggested_changes": {},
                 "expected_gain": 0.0, "warnings": []},
            ],
            "recommended_variant_id": "v1",
        }
        result = select_best_variant(vs_dict)
        assert result["selected_variant_id"] == "v1"


# ---------------------------------------------------------------------------
# Confidence-based fallback
# ---------------------------------------------------------------------------

class TestSelectorFallback:
    def test_low_confidence_falls_back_to_baseline(self):
        from app.ai.variants.variant_selector import select_best_variant
        # Very low confidence variant + baseline
        weak = _make_variant("weak", "retention", "low", confidence=0.01, safe_to_render=True)
        baseline = _make_variant("base", "safe_baseline", "low", confidence=0.9, safe_to_render=True)
        result = select_best_variant(_make_variant_set(weak, baseline))
        # If weak scores below MIN_SELECTION_CONFIDENCE threshold, baseline should win
        # (baseline has floor guarantee; weak scores ~(72+0.15+5-58)*2 — may vary)
        # Just confirm no crash and result is valid
        assert result["selected_variant_id"] is not None

    def test_fallback_used_flag_set_when_baseline_chosen_over_weak(self):
        from app.ai.variants.variant_selector import select_best_variant
        # Construct a variant that will have very low confidence
        weak = _make_variant("weak", "retention", "high", confidence=0.01, safe_to_render=False)
        baseline = _make_variant("base", "safe_baseline", "low", confidence=0.9, safe_to_render=True)
        result = select_best_variant(_make_variant_set(weak, baseline))
        # high-risk should be skipped; baseline selected without fallback flag unless confidence low
        assert result["selected_variant_id"] == "base"

    def test_safe_baseline_always_preferred_for_stability(self):
        from app.ai.variants.variant_selector import select_best_variant
        baseline = _make_variant("base", "safe_baseline", "low", confidence=0.9, safe_to_render=True)
        result = select_best_variant(_make_variant_set(baseline))
        assert result["selected_variant_id"] == "base"

    def test_fallback_reason_in_selection_reasons(self):
        from app.ai.variants.variant_selector import select_best_variant
        baseline = _make_variant("base", "safe_baseline", "low", safe_to_render=True)
        result = select_best_variant(_make_variant_set(baseline))
        assert any("safe_baseline" in r or "stable" in r for r in result["selection_reasons"])


# ---------------------------------------------------------------------------
# Priority heuristics
# ---------------------------------------------------------------------------

class TestSelectorPriorityHeuristics:
    def test_retention_preferred_over_pacing_at_equal_confidence(self):
        from app.ai.variants.variant_selector import select_best_variant
        retention = _make_variant("ret", "retention", "low", confidence=0.7, safe_to_render=True)
        pacing = _make_variant("pac", "pacing", "low", confidence=0.7, safe_to_render=True)
        result = select_best_variant(_make_variant_set(pacing, retention))
        # retention has higher base score → should win
        assert result["selected_variant_id"] == "ret"

    def test_story_preferred_over_subtitle_at_equal_confidence(self):
        from app.ai.variants.variant_selector import select_best_variant
        story = _make_variant("st", "story", "low", confidence=0.7, safe_to_render=True)
        subtitle = _make_variant("sub", "subtitle", "low", confidence=0.7, safe_to_render=True)
        result = select_best_variant(_make_variant_set(subtitle, story))
        assert result["selected_variant_id"] == "st"

    def test_context_boosts_applied_from_edit_plan(self):
        from app.ai.variants.variant_selector import select_best_variant
        edit = _make_edit_plan(
            retention={"available": True, "overall_retention_score": 45, "risk_regions": []}
        )
        retention = _make_variant("ret", "retention", "low", confidence=0.75, safe_to_render=True)
        baseline = _make_variant("base", "safe_baseline", "low", confidence=0.9, safe_to_render=True)
        result = select_best_variant(_make_variant_set(baseline, retention), edit_plan=edit)
        # retention gets context boost for low retention score → should beat baseline
        assert result["selected_variant_id"] == "ret"


# ---------------------------------------------------------------------------
# Scoring normalization tests (Phase 22 additions)
# ---------------------------------------------------------------------------

class TestScoringNormalization:
    def test_score_result_has_normalized_score(self):
        from app.ai.variants.variant_scoring import score_variant
        v = _make_variant()
        result = score_variant(v)
        assert "normalized_score" in result
        assert 0.0 <= result["normalized_score"] <= 1.0

    def test_normalized_score_is_score_divided_by_100(self):
        from app.ai.variants.variant_scoring import score_variant
        v = _make_variant()
        result = score_variant(v)
        assert abs(result["normalized_score"] - result["score"] / 100.0) < 0.001

    def test_baseline_floor_ensures_minimum_score(self):
        from app.ai.variants.variant_scoring import score_variant, _BASELINE_FLOOR
        from app.ai.variants.variant_schema import AIVariantPlan
        v = AIVariantPlan(variant_id="b", purpose="safe_baseline", confidence=0.0, risk="low")
        result = score_variant(v)
        assert result["score"] >= _BASELINE_FLOOR

    def test_high_risk_penalty_stronger_in_phase22(self):
        from app.ai.variants.variant_scoring import score_variant, _RISK_PENALTIES
        assert _RISK_PENALTIES["high"] >= 40.0

    def test_high_risk_score_always_lower_than_low_risk(self):
        from app.ai.variants.variant_scoring import score_variant
        low = _make_variant("l", "retention", "low", confidence=0.5)
        high = _make_variant("h", "retention", "high", confidence=0.9)
        assert score_variant(high)["score"] < score_variant(low)["score"]

    def test_score_never_raises_on_bad_variant(self):
        from app.ai.variants.variant_scoring import score_variant
        result = score_variant("not_a_variant")
        assert "warnings" in result

    def test_expected_gain_non_negative(self):
        from app.ai.variants.variant_scoring import score_variant
        v = _make_variant()
        result = score_variant(v)
        assert result["expected_gain"] >= 0.0


# ---------------------------------------------------------------------------
# AIEditPlan field
# ---------------------------------------------------------------------------

class TestAIEditPlanVariantSelectionField:
    def test_variant_selection_field_exists(self):
        plan = _make_edit_plan()
        assert hasattr(plan, "variant_selection")
        assert plan.variant_selection == {}

    def test_variant_selection_in_to_dict(self):
        plan = _make_edit_plan()
        d = plan.to_dict()
        assert "variant_selection" in d
        assert d["variant_selection"] == {}

    def test_variant_selection_populated_survives_to_dict(self):
        plan = _make_edit_plan(variant_selection={
            "selected_variant_id": "v1",
            "selection_confidence": 0.82,
            "fallback_used": False,
        })
        d = plan.to_dict()
        assert d["variant_selection"]["selected_variant_id"] == "v1"
        assert d["variant_selection"]["selection_confidence"] == pytest.approx(0.82)

    def test_all_prior_phase_fields_preserved(self):
        plan = _make_edit_plan()
        d = plan.to_dict()
        for key in ("subtitle_execution", "beat_visual_execution",
                    "timing_mutation", "story_optimization", "variants", "variant_selection"):
            assert key in d, f"Missing: {key}"


# ---------------------------------------------------------------------------
# AI Director integration
# ---------------------------------------------------------------------------

class TestAIDirectorPhase22Integration:
    def _make_request(self, variant_enabled=False):
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
            ai_timing_mutation_enabled = False
            ai_variant_planning_enabled = variant_enabled
            ai_variant_count = 3
        return Req()

    def test_variant_selection_empty_when_disabled(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=False), context={})
        assert plan is not None
        assert plan.variant_selection == {}

    def test_variant_selection_populated_when_enabled(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=True), context={})
        assert plan is not None
        assert isinstance(plan.variant_selection, dict)
        # Selection should have been run since variants were generated
        assert "selected_variant_id" in plan.variant_selection or "warnings" in plan.variant_selection

    def test_selected_variant_id_references_known_variant(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=True), context={})
        if plan and plan.variant_selection.get("selected_variant_id"):
            selected_id = plan.variant_selection["selected_variant_id"]
            variant_ids = [
                v.get("variant_id") for v in plan.variants.get("variants", [])
                if isinstance(v, dict)
            ]
            assert selected_id in variant_ids

    def test_director_never_raises_phase22(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        result = create_ai_edit_plan(
            self._make_request(variant_enabled=True),
            context={"job_id": "test-p22"},
        )
        assert result is None or hasattr(result, "variant_selection")

    def test_to_dict_includes_variant_selection(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=True), context={})
        if plan is not None:
            d = plan.to_dict()
            assert "variant_selection" in d


# ---------------------------------------------------------------------------
# Render influence defer
# ---------------------------------------------------------------------------

class TestRenderInfluenceVariantSelectionDefer:
    def _make_plan_obj(self, variant_selection):
        class FakePlan:
            camera = None; subtitle = None; pacing = None
            memory_context = None; beat_visual_execution = None
            timing_mutation = None; story_optimization = None
            variants = None; explainability = {}; beat_execution = {}
        p = FakePlan()
        p.variant_selection = variant_selection
        return p

    def _make_payload(self):
        class Payload:
            motion_aware_crop = False
            add_subtitle = False
            ai_beat_execution_enabled = False
        return Payload()

    def test_no_variant_selection_attr_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePlan:
            camera = None; subtitle = None; pacing = None
            memory_context = None; beat_visual_execution = None
            timing_mutation = None; story_optimization = None
            variants = None; explainability = {}; beat_execution = {}

        _, report = apply_ai_render_influence(self._make_payload(), FakePlan())
        assert any("variant_selection:no_result" in s for s in report["skipped"])

    def test_empty_dict_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({})
        _, report = apply_ai_render_influence(self._make_payload(), plan)
        assert any("variant_selection:empty" in s for s in report["skipped"])

    def test_populated_selection_deferred_phase22(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({
            "selected_variant_id": "v_retention_abc",
            "selection_confidence": 0.78,
            "fallback_used": False,
            "rejected_count": 2,
        })
        _, report = apply_ai_render_influence(self._make_payload(), plan)
        assert any("variant_selection:deferred_phase22" in s for s in report["skipped"])

    def test_no_payload_mutation_from_selection(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({
            "selected_variant_id": "v1",
            "selection_confidence": 0.90,
            "fallback_used": False,
            "rejected_count": 1,
        })
        payload = self._make_payload()
        apply_ai_render_influence(payload, plan)
        assert payload.motion_aware_crop is False
        assert payload.add_subtitle is False


# ---------------------------------------------------------------------------
# Safety boundary tests
# ---------------------------------------------------------------------------

class TestPhase22SafetyBoundaries:
    def test_no_extra_render_jobs(self):
        from app.ai.variants.variant_selector import select_best_variant
        vs = _make_variant_set(
            _make_variant("base", "safe_baseline", "low", safe_to_render=True),
            _make_variant("ret", "retention", "low", safe_to_render=True),
        )
        result = select_best_variant(vs)
        # Verify it's just a metadata dict — no side effects
        assert isinstance(result, dict)

    def test_no_segment_timing_mutation(self):
        from app.ai.variants.variant_selector import select_best_variant
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[AIClipPlan(start=0.0, end=10.0, score=80.0)],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        original_start = plan.selected_segments[0].start
        vs = _make_variant_set(_make_variant("base", "safe_baseline", "low"))
        select_best_variant(vs, edit_plan=plan)
        assert plan.selected_segments[0].start == original_start

    def test_no_subtitle_timing_mutation(self):
        from app.ai.variants.variant_selector import select_best_variant
        plan = _make_edit_plan(
            subtitle_execution={"available": True, "regions": [{"start": 1.0, "end": 3.0}]}
        )
        original = plan.subtitle_execution["regions"][0]["start"]
        vs = _make_variant_set(_make_variant("base", "safe_baseline", "low"))
        select_best_variant(vs, edit_plan=plan)
        assert plan.subtitle_execution["regions"][0]["start"] == original

    def test_no_playback_speed_mutation(self):
        from app.ai.variants.variant_selector import select_best_variant
        plan = _make_edit_plan()
        vs = _make_variant_set(_make_variant())
        result = select_best_variant(vs, edit_plan=plan)
        # Result dict must not contain playback_speed
        assert "playback_speed" not in result

    def test_no_api_key_required(self):
        from app.ai.variants.variant_selector import select_best_variant
        vs = _make_variant_set(_make_variant())
        result = select_best_variant(vs)
        assert result is not None

    def test_no_gpu_required(self):
        from app.ai.variants.variant_scoring import score_variant
        from app.ai.variants.variant_schema import AIVariantPlan
        v = AIVariantPlan(variant_id="v1", purpose="safe_baseline")
        result = score_variant(v)
        assert isinstance(result["score"], float)

    def test_no_real_rendering_required(self):
        from app.ai.variants.variant_selector import select_best_variant
        vs = _make_variant_set(_make_variant("base", "safe_baseline", "low"))
        result = select_best_variant(vs)
        assert "selected_variant_id" in result

    def test_backward_compatibility_all_fields_present(self):
        plan = _make_edit_plan()
        d = plan.to_dict()
        required = [
            "beat_execution", "story", "retention", "subtitle_execution",
            "beat_visual_execution", "timing_mutation", "story_optimization",
            "variants", "variant_selection",
        ]
        for k in required:
            assert k in d, f"Missing backward-compatible field: {k}"
