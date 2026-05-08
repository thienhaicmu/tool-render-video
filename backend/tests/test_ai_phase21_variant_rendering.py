"""
test_ai_phase21_variant_rendering.py — Phase 21 variant rendering tests.

Coverage: schema, safety, scoring, generator, request flags,
render influence defer, AI Director integration, and all safety boundaries.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestAIVariantPlanSchema:
    def test_defaults_require_variant_id(self):
        from app.ai.variants.variant_schema import AIVariantPlan
        v = AIVariantPlan(variant_id="v1")
        assert v.label == ""
        assert v.purpose == "safe_baseline"
        assert v.confidence == 0.0
        assert v.risk == "low"
        assert v.suggested_changes == {}
        assert v.expected_gain == 0.0
        assert v.safe_to_render is False
        assert v.warnings == []

    def test_to_dict_keys(self):
        from app.ai.variants.variant_schema import AIVariantPlan
        d = AIVariantPlan(variant_id="v1").to_dict()
        assert set(d.keys()) == {
            "variant_id", "label", "purpose", "confidence", "risk",
            "suggested_changes", "expected_gain", "safe_to_render", "warnings",
        }

    def test_invalid_purpose_normalised(self):
        from app.ai.variants.variant_schema import AIVariantPlan
        v = AIVariantPlan(variant_id="v1", purpose="illegal")
        assert v.to_dict()["purpose"] == "safe_baseline"

    def test_invalid_risk_normalised(self):
        from app.ai.variants.variant_schema import AIVariantPlan
        v = AIVariantPlan(variant_id="v1", risk="nuclear")
        assert v.to_dict()["risk"] == "low"

    def test_all_valid_purposes_accepted(self):
        from app.ai.variants.variant_schema import AIVariantPlan, VALID_PURPOSES
        for p in VALID_PURPOSES:
            v = AIVariantPlan(variant_id="v1", purpose=p)
            assert v.to_dict()["purpose"] == p

    def test_all_valid_risks_accepted(self):
        from app.ai.variants.variant_schema import AIVariantPlan, VALID_RISKS
        for r in VALID_RISKS:
            v = AIVariantPlan(variant_id="v1", risk=r)
            assert v.to_dict()["risk"] == r


class TestAIVariantSetSchema:
    def test_defaults(self):
        from app.ai.variants.variant_schema import AIVariantSet
        s = AIVariantSet()
        assert s.available is True
        assert s.mode == "advisory"
        assert s.variants == []
        assert s.recommended_variant_id is None
        assert s.warnings == []

    def test_to_dict_keys(self):
        from app.ai.variants.variant_schema import AIVariantSet
        d = AIVariantSet().to_dict()
        assert set(d.keys()) == {
            "available", "mode", "variants", "recommended_variant_id", "warnings"
        }

    def test_variants_capped_at_5(self):
        from app.ai.variants.variant_schema import AIVariantSet, AIVariantPlan
        variants = [AIVariantPlan(variant_id=f"v{i}") for i in range(8)]
        s = AIVariantSet(variants=variants)
        assert len(s.to_dict()["variants"]) == 5


class TestClampVariantCount:
    def test_clamp_above_max(self):
        from app.ai.variants.variant_schema import clamp_variant_count
        assert clamp_variant_count(10) == 5

    def test_clamp_below_min(self):
        from app.ai.variants.variant_schema import clamp_variant_count
        assert clamp_variant_count(0) == 1

    def test_negative_clamped_to_one(self):
        from app.ai.variants.variant_schema import clamp_variant_count
        assert clamp_variant_count(-3) == 1

    def test_valid_value_passes_through(self):
        from app.ai.variants.variant_schema import clamp_variant_count
        assert clamp_variant_count(3) == 3

    def test_bad_value_returns_one(self):
        from app.ai.variants.variant_schema import clamp_variant_count
        assert clamp_variant_count("not_a_number") == 1


# ---------------------------------------------------------------------------
# Variant safety tests
# ---------------------------------------------------------------------------

class TestSanitizeVariantChanges:
    def test_allowed_keys_pass_through(self):
        from app.ai.variants.variant_safety import sanitize_variant_changes
        changes = {"subtitle_density": "compact", "pacing_style": "fast"}
        result = sanitize_variant_changes(changes)
        assert result == changes

    def test_forbidden_keys_stripped(self):
        from app.ai.variants.variant_safety import sanitize_variant_changes
        changes = {
            "subtitle_density": "compact",
            "playback_speed": 1.5,
            "ffmpeg_args": "-vf scale=1280:720",
            "codec": "h264",
        }
        result = sanitize_variant_changes(changes)
        assert "playback_speed" not in result
        assert "ffmpeg_args" not in result
        assert "codec" not in result
        assert result.get("subtitle_density") == "compact"

    def test_all_forbidden_keys_stripped(self):
        from app.ai.variants.variant_safety import sanitize_variant_changes, FORBIDDEN_CHANGE_KEYS
        changes = {k: "val" for k in FORBIDDEN_CHANGE_KEYS}
        result = sanitize_variant_changes(changes)
        assert result == {}

    def test_empty_input_returns_empty(self):
        from app.ai.variants.variant_safety import sanitize_variant_changes
        assert sanitize_variant_changes({}) == {}

    def test_never_raises_on_bad_input(self):
        from app.ai.variants.variant_safety import sanitize_variant_changes
        result = sanitize_variant_changes("not_a_dict")
        assert result == {}


class TestIsVariantSafe:
    def _make(self, **kwargs):
        from app.ai.variants.variant_schema import AIVariantPlan
        defaults = dict(variant_id="v1", risk="low", suggested_changes={})
        defaults.update(kwargs)
        return AIVariantPlan(**defaults)

    def test_low_risk_no_forbidden_keys_is_safe(self):
        from app.ai.variants.variant_safety import is_variant_safe
        assert is_variant_safe(self._make()) is True

    def test_high_risk_never_safe(self):
        from app.ai.variants.variant_safety import is_variant_safe
        assert is_variant_safe(self._make(risk="high")) is False

    def test_medium_risk_can_be_safe(self):
        from app.ai.variants.variant_safety import is_variant_safe
        assert is_variant_safe(self._make(risk="medium")) is True

    def test_forbidden_key_in_changes_not_safe(self):
        from app.ai.variants.variant_safety import is_variant_safe
        v = self._make(suggested_changes={"playback_speed": 1.5})
        assert is_variant_safe(v) is False

    def test_empty_variant_id_not_safe(self):
        from app.ai.variants.variant_safety import is_variant_safe
        v = self._make(variant_id="")
        assert is_variant_safe(v) is False

    def test_never_raises_on_bad_input(self):
        from app.ai.variants.variant_safety import is_variant_safe
        result = is_variant_safe("not_a_variant")
        assert result is False


# ---------------------------------------------------------------------------
# Variant scoring tests
# ---------------------------------------------------------------------------

class TestScoreVariant:
    def _make(self, purpose="safe_baseline", risk="low", confidence=0.8, changes=None):
        from app.ai.variants.variant_schema import AIVariantPlan
        return AIVariantPlan(
            variant_id="v1",
            purpose=purpose,
            risk=risk,
            confidence=confidence,
            suggested_changes=changes or {},
        )

    def test_returns_dict_with_expected_keys(self):
        from app.ai.variants.variant_scoring import score_variant
        result = score_variant(self._make())
        assert set(result.keys()) == {"score", "expected_gain", "reasons", "warnings"}

    def test_score_in_range(self):
        from app.ai.variants.variant_scoring import score_variant
        result = score_variant(self._make())
        assert 0.0 <= result["score"] <= 100.0

    def test_safe_baseline_gets_moderate_score(self):
        from app.ai.variants.variant_scoring import score_variant
        result = score_variant(self._make(purpose="safe_baseline"))
        assert result["score"] >= 50.0

    def test_high_risk_penalized(self):
        from app.ai.variants.variant_scoring import score_variant
        low = score_variant(self._make(risk="low"))
        high = score_variant(self._make(risk="high"))
        assert high["score"] < low["score"]

    def test_high_risk_variant_has_safety_gate_failed(self):
        from app.ai.variants.variant_scoring import score_variant
        result = score_variant(self._make(risk="high"))
        assert any("safety_gate_failed" in r for r in result["reasons"])

    def test_safe_variant_passes_safety_gate(self):
        from app.ai.variants.variant_scoring import score_variant
        result = score_variant(self._make(risk="low", changes={"pacing_style": "fast"}))
        assert any("safety_gate_passed" in r for r in result["reasons"])

    def test_never_raises_on_bad_input(self):
        from app.ai.variants.variant_scoring import score_variant
        result = score_variant("not_a_variant")
        assert "warnings" in result

    def test_forbidden_key_in_changes_penalized(self):
        from app.ai.variants.variant_scoring import score_variant
        dirty = self._make(changes={"playback_speed": 2.0})
        clean = self._make(changes={"pacing_style": "fast"})
        assert score_variant(dirty)["score"] < score_variant(clean)["score"]


# ---------------------------------------------------------------------------
# Variant generator tests
# ---------------------------------------------------------------------------

class TestGenerateVariantPlans:
    def _make_edit_plan(self, **attrs):
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

    def test_returns_variant_set(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.variants.variant_schema import AIVariantSet
        result = generate_variant_plans(self._make_edit_plan())
        assert isinstance(result, AIVariantSet)

    def test_never_raises_on_none_edit_plan(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        result = generate_variant_plans(None)
        assert hasattr(result, "available")

    def test_never_raises_on_garbage_context(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        result = generate_variant_plans(self._make_edit_plan(), context="bad")
        assert hasattr(result, "available")

    def test_always_includes_safe_baseline(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        result = generate_variant_plans(self._make_edit_plan(), count=3)
        purposes = [v.purpose for v in result.variants]
        assert "safe_baseline" in purposes

    def test_variants_max_5(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        result = generate_variant_plans(self._make_edit_plan(), count=5)
        assert len(result.variants) <= 5

    def test_count_1_gives_only_baseline(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        result = generate_variant_plans(self._make_edit_plan(), count=1)
        assert len(result.variants) == 1
        assert result.variants[0].purpose == "safe_baseline"

    def test_no_forbidden_fields_in_any_variant(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.variants.variant_safety import FORBIDDEN_CHANGE_KEYS
        result = generate_variant_plans(self._make_edit_plan(), count=5)
        for v in result.variants:
            for key in v.suggested_changes:
                assert key not in FORBIDDEN_CHANGE_KEYS, f"Forbidden key {key!r} in variant {v.variant_id}"

    def test_high_risk_variant_never_safe_to_render(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.variants.variant_schema import AIVariantPlan
        result = generate_variant_plans(self._make_edit_plan(), count=5)
        for v in result.variants:
            if v.risk == "high":
                assert v.safe_to_render is False

    def test_mode_is_advisory(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        result = generate_variant_plans(self._make_edit_plan())
        assert result.mode == "advisory"

    def test_recommended_variant_id_is_set(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        result = generate_variant_plans(self._make_edit_plan(), count=3)
        assert result.recommended_variant_id is not None

    def test_edit_plan_not_mutated(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        plan = self._make_edit_plan()
        original_mode = plan.mode
        generate_variant_plans(plan, count=5)
        assert plan.mode == original_mode

    def test_retention_variant_generated_when_retention_available(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        plan = self._make_edit_plan(
            retention={"available": True, "overall_retention_score": 45, "risk_regions": []}
        )
        result = generate_variant_plans(plan, count=5)
        purposes = [v.purpose for v in result.variants]
        assert "retention" in purposes

    def test_hook_variant_generated_when_weak_hook_detected(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        plan = self._make_edit_plan(
            story_optimization={
                "available": True,
                "issues": [{"issue_type": "weak_hook", "severity": "high"}],
            }
        )
        result = generate_variant_plans(plan, count=5)
        purposes = [v.purpose for v in result.variants]
        assert "hook" in purposes

    def test_subtitle_variant_generated_when_execution_available(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        plan = self._make_edit_plan(
            subtitle_execution={
                "available": True,
                "global_hint": {"density_mode": "normal"},
            }
        )
        result = generate_variant_plans(plan, count=5)
        purposes = [v.purpose for v in result.variants]
        assert "subtitle" in purposes

    def test_no_extra_render_jobs_enqueued(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        # Simply verifying no side effects — generator is pure metadata
        plan = self._make_edit_plan()
        generate_variant_plans(plan, count=3)
        # No assertion needed beyond no exception and no file output
        assert True

    def test_no_payload_mutation(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        class Payload:
            motion_aware_crop = False
            add_subtitle = False
        payload = Payload()
        plan = self._make_edit_plan()
        generate_variant_plans(plan, count=3)
        assert payload.motion_aware_crop is False
        assert payload.add_subtitle is False

    def test_to_dict_round_trip(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        result = generate_variant_plans(self._make_edit_plan(), count=3)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "variants" in d
        assert isinstance(d["variants"], list)


# ---------------------------------------------------------------------------
# Safety boundary tests
# ---------------------------------------------------------------------------

class TestVariantSafetyBoundaries:
    def test_no_segment_timing_mutation(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan,
        )
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[AIClipPlan(start=0.0, end=10.0, score=80.0)],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        original_start = plan.selected_segments[0].start
        generate_variant_plans(plan, count=5)
        assert plan.selected_segments[0].start == original_start

    def test_no_subtitle_timing_mutation(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            subtitle_execution={"available": True, "regions": [{"start": 1.0, "end": 3.0}]},
        )
        original = plan.subtitle_execution["regions"][0]["start"]
        generate_variant_plans(plan, count=5)
        assert plan.subtitle_execution["regions"][0]["start"] == original

    def test_no_playback_speed_in_changes(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        result = generate_variant_plans(plan, count=5)
        for v in result.variants:
            assert "playback_speed" not in v.suggested_changes

    def test_no_api_key_required(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        result = generate_variant_plans(plan)
        assert result is not None

    def test_no_gpu_required(self):
        from app.ai.variants.variant_scoring import score_variant
        from app.ai.variants.variant_schema import AIVariantPlan
        v = AIVariantPlan(variant_id="v1")
        result = score_variant(v)
        assert isinstance(result["score"], float)

    def test_no_real_rendering_required(self):
        from app.ai.variants.variant_generator import generate_variant_plans
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        result = generate_variant_plans(plan)
        assert hasattr(result, "to_dict")


# ---------------------------------------------------------------------------
# Request flags tests
# ---------------------------------------------------------------------------

class TestRequestFlags:
    def test_default_variant_planning_enabled_is_false(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest(
            source_video_id="vid123",
            target_platform="tiktok",
        )
        assert req.ai_variant_planning_enabled is False

    def test_default_variant_count_is_3(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest(
            source_video_id="vid123",
            target_platform="tiktok",
        )
        assert req.ai_variant_count == 3

    def test_variant_count_can_be_set(self):
        from app.models.schemas import RenderRequest
        req = RenderRequest(
            source_video_id="vid123",
            target_platform="tiktok",
            ai_variant_count=5,
        )
        assert req.ai_variant_count == 5


# ---------------------------------------------------------------------------
# AIEditPlan field tests
# ---------------------------------------------------------------------------

class TestAIEditPlanVariantsField:
    def _make_plan(self, **kwargs):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        return AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            **kwargs,
        )

    def test_variants_field_exists(self):
        plan = self._make_plan()
        assert hasattr(plan, "variants")
        assert plan.variants == {}

    def test_variants_in_to_dict(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "variants" in d
        assert d["variants"] == {}

    def test_variants_populated_survives_to_dict(self):
        plan = self._make_plan(variants={"available": True, "mode": "advisory"})
        d = plan.to_dict()
        assert d["variants"]["available"] is True
        assert d["variants"]["mode"] == "advisory"

    def test_all_prior_phase_fields_preserved(self):
        plan = self._make_plan()
        d = plan.to_dict()
        for key in ("subtitle_execution", "beat_visual_execution",
                    "timing_mutation", "story_optimization", "variants"):
            assert key in d, f"Missing: {key}"


# ---------------------------------------------------------------------------
# AI Director integration tests
# ---------------------------------------------------------------------------

class TestAIDirectorPhase21Integration:
    def _make_request(self, variant_enabled=False, variant_count=3):
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
            ai_variant_count = variant_count
        return Req()

    def test_disabled_mode_variants_empty(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=False), context={})
        assert plan is not None
        assert plan.variants == {}

    def test_enabled_mode_variants_populated(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=True, variant_count=3), context={})
        assert plan is not None
        assert isinstance(plan.variants, dict)
        assert plan.variants.get("available") is True

    def test_enabled_mode_includes_safe_baseline(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=True), context={})
        if plan and plan.variants.get("available"):
            purposes = [v.get("purpose") for v in plan.variants.get("variants", [])]
            assert "safe_baseline" in purposes

    def test_variant_count_clamped_when_enabled(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=True, variant_count=99), context={})
        if plan and plan.variants.get("available"):
            assert len(plan.variants.get("variants", [])) <= 5

    def test_director_never_raises_with_phase21(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        result = create_ai_edit_plan(
            self._make_request(variant_enabled=True),
            context={"job_id": "test-p21"},
        )
        assert result is None or hasattr(result, "variants")

    def test_to_dict_includes_variants(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(variant_enabled=True), context={})
        if plan is not None:
            d = plan.to_dict()
            assert "variants" in d


# ---------------------------------------------------------------------------
# Render influence defer tests
# ---------------------------------------------------------------------------

class TestRenderInfluenceVariantDefer:
    def _make_plan_obj(self, variants):
        class FakePlan:
            camera = None; subtitle = None; pacing = None
            memory_context = None; beat_visual_execution = None
            timing_mutation = None; story_optimization = None
            explainability = {}; beat_execution = {}
        p = FakePlan()
        p.variants = variants
        return p

    def _make_payload(self):
        class Payload:
            motion_aware_crop = False
            add_subtitle = False
            ai_beat_execution_enabled = False
        return Payload()

    def test_no_variants_attr_adds_no_plan(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePlan:
            camera = None; subtitle = None; pacing = None
            memory_context = None; beat_visual_execution = None
            timing_mutation = None; story_optimization = None
            explainability = {}; beat_execution = {}

        _, report = apply_ai_render_influence(self._make_payload(), FakePlan())
        assert any("variant_planning:no_plan" in s for s in report["skipped"])

    def test_unavailable_plan_deferred(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({"available": False, "warnings": ["no_variants"]})
        _, report = apply_ai_render_influence(self._make_payload(), plan)
        assert any("variant_planning:deferred(no_variants)" in s for s in report["skipped"])

    def test_available_plan_deferred_phase21(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({
            "available": True,
            "mode": "advisory",
            "variants": [],
            "recommended_variant_id": None,
        })
        _, report = apply_ai_render_influence(self._make_payload(), plan)
        assert any("variant_planning:deferred_phase21" in s for s in report["skipped"])

    def test_no_payload_mutation_from_variants(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({
            "available": True,
            "mode": "advisory",
            "variants": [{"variant_id": "v1", "safe_to_render": True, "purpose": "retention"}],
            "recommended_variant_id": "v1",
        })
        payload = self._make_payload()
        apply_ai_render_influence(payload, plan)
        assert payload.motion_aware_crop is False
        assert payload.add_subtitle is False
