"""
test_ai_phase28_multivariant_planning.py — Phase 28: Safe Multi-Variant Render Planning.

All tests follow these invariants:
  - mode is always "planning_only"
  - advisory_only is always True on every plan
  - safe_to_enqueue is False if any forbidden field in planned_payload_overrides
  - max 5 plans in any render set
  - Never raises
  - Fallback-safe on any input
  - Backward compatible: AIEditPlan still works without multivariant_render_plans
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers / minimal stubs
# ---------------------------------------------------------------------------

@dataclass
class _FakeEditPlan:
    """Minimal edit plan stub for Phase 28 tests."""
    variants: dict = field(default_factory=dict)
    variant_selection: dict = field(default_factory=dict)
    safe_render_mutations: dict = field(default_factory=dict)
    creator_style_adaptation: dict = field(default_factory=dict)
    creator_style: dict = field(default_factory=dict)
    retention: dict = field(default_factory=dict)
    subtitle_execution: dict = field(default_factory=dict)
    render_decision_preview: dict = field(default_factory=dict)
    execution_recommendations: dict = field(default_factory=dict)
    execution_simulation: dict = field(default_factory=dict)
    multivariant_render_plans: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestMultiVariantSchema:
    def _make_plan(self, **kwargs):
        from app.ai.multivariant.multivariant_schema import AIMultiVariantRenderPlan
        defaults = dict(
            plan_id="p1",
            variant_id="v1",
            label="Test Plan",
            renderable=True,
            safe_to_enqueue=True,
            advisory_only=True,
            mutation_ids=[],
            planned_payload_overrides={"ai_mode": "advisory"},
            blocked_fields=[],
            warnings=[],
            explanation="Test.",
        )
        defaults.update(kwargs)
        return AIMultiVariantRenderPlan(**defaults)

    def test_advisory_only_always_true_in_to_dict(self):
        plan = self._make_plan(advisory_only=False)
        d = plan.to_dict()
        assert d["advisory_only"] is True

    def test_to_dict_keys_present(self):
        plan = self._make_plan()
        d = plan.to_dict()
        for k in ("plan_id", "variant_id", "label", "renderable", "safe_to_enqueue",
                  "advisory_only", "mutation_ids", "planned_payload_overrides",
                  "blocked_fields", "warnings", "explanation"):
            assert k in d

    def test_mutation_ids_capped_at_20(self):
        plan = self._make_plan(mutation_ids=[f"m{i}" for i in range(30)])
        d = plan.to_dict()
        assert len(d["mutation_ids"]) == 20

    def test_explanation_capped_at_300_chars(self):
        plan = self._make_plan(explanation="x" * 500)
        d = plan.to_dict()
        assert len(d["explanation"]) == 300

    def test_renderable_bool_coercion(self):
        plan = self._make_plan(renderable=1)
        d = plan.to_dict()
        assert d["renderable"] is True

    def test_safe_to_enqueue_bool_coercion(self):
        plan = self._make_plan(safe_to_enqueue=0)
        d = plan.to_dict()
        assert d["safe_to_enqueue"] is False


class TestMultiVariantRenderSet:
    def _make_set(self, plans=None, **kwargs):
        from app.ai.multivariant.multivariant_schema import AIMultiVariantRenderSet, AIMultiVariantRenderPlan
        if plans is None:
            plans = []
        defaults = dict(
            available=True,
            mode="planning_only",
            plans=plans,
            recommended_plan_id=None,
            warnings=[],
        )
        defaults.update(kwargs)
        return AIMultiVariantRenderSet(**defaults)

    def test_mode_always_planning_only(self):
        s = self._make_set(mode="execute_now")
        d = s.to_dict()
        assert d["mode"] == "planning_only"

    def test_plans_capped_at_5(self):
        from app.ai.multivariant.multivariant_schema import AIMultiVariantRenderPlan
        plans = [
            AIMultiVariantRenderPlan(
                plan_id=f"p{i}", variant_id=f"v{i}", label=f"Plan {i}",
                renderable=True, safe_to_enqueue=True, advisory_only=True,
                mutation_ids=[], planned_payload_overrides={},
                blocked_fields=[], warnings=[], explanation="",
            )
            for i in range(8)
        ]
        s = self._make_set(plans=plans)
        d = s.to_dict()
        assert len(d["plans"]) == 5

    def test_to_dict_structure(self):
        s = self._make_set()
        d = s.to_dict()
        for k in ("available", "mode", "plans", "recommended_plan_id", "warnings"):
            assert k in d

    def test_available_bool_coercion(self):
        s = self._make_set(available=1)
        d = s.to_dict()
        assert d["available"] is True


# ---------------------------------------------------------------------------
# Safety tests
# ---------------------------------------------------------------------------

class TestMultiVariantSafety:
    def test_sanitize_removes_forbidden_keys(self):
        from app.ai.multivariant.multivariant_safety import sanitize_variant_payload_overrides
        overrides = {
            "subtitle_density": "compact",
            "playback_speed": 1.5,
            "queue_priority": 10,
            "job_id": "abc123",
        }
        result = sanitize_variant_payload_overrides(overrides)
        assert "playback_speed" not in result
        assert "queue_priority" not in result
        assert "job_id" not in result
        assert result.get("subtitle_density") == "compact"

    def test_sanitize_removes_unknown_keys(self):
        from app.ai.multivariant.multivariant_safety import sanitize_variant_payload_overrides
        result = sanitize_variant_payload_overrides({"unknown_key": "val", "ai_mode": "advisory"})
        assert "unknown_key" not in result
        assert result.get("ai_mode") == "advisory"

    def test_sanitize_drops_none_values(self):
        from app.ai.multivariant.multivariant_safety import sanitize_variant_payload_overrides
        result = sanitize_variant_payload_overrides({"ai_mode": None, "pacing_style": "standard"})
        assert "ai_mode" not in result
        assert result.get("pacing_style") == "standard"

    def test_sanitize_empty_dict(self):
        from app.ai.multivariant.multivariant_safety import sanitize_variant_payload_overrides
        assert sanitize_variant_payload_overrides({}) == {}

    def test_sanitize_non_dict(self):
        from app.ai.multivariant.multivariant_safety import sanitize_variant_payload_overrides
        assert sanitize_variant_payload_overrides(None) == {}
        assert sanitize_variant_payload_overrides("not_a_dict") == {}
        assert sanitize_variant_payload_overrides(42) == {}

    def test_is_safe_with_clean_overrides(self):
        from app.ai.multivariant.multivariant_safety import is_multivariant_plan_safe
        assert is_multivariant_plan_safe({"ai_mode": "advisory"}) is True

    def test_is_safe_with_forbidden_key(self):
        from app.ai.multivariant.multivariant_safety import is_multivariant_plan_safe
        assert is_multivariant_plan_safe({"playback_speed": 1.5}) is False
        assert is_multivariant_plan_safe({"queue_priority": 1}) is False
        assert is_multivariant_plan_safe({"job_id": "x"}) is False

    def test_is_safe_with_render_command(self):
        from app.ai.multivariant.multivariant_safety import is_multivariant_plan_safe
        assert is_multivariant_plan_safe({"render_command": "ffmpeg -i"}) is False

    def test_is_safe_non_dict(self):
        from app.ai.multivariant.multivariant_safety import is_multivariant_plan_safe
        assert is_multivariant_plan_safe(None) is True
        assert is_multivariant_plan_safe("str") is True

    def test_collect_blocked_fields(self):
        from app.ai.multivariant.multivariant_safety import collect_blocked_fields
        overrides = {"playback_speed": 1.5, "queue_priority": 1, "ai_mode": "advisory"}
        blocked = collect_blocked_fields(overrides)
        assert "playback_speed" in blocked
        assert "queue_priority" in blocked
        assert "ai_mode" not in blocked

    def test_collect_blocked_empty(self):
        from app.ai.multivariant.multivariant_safety import collect_blocked_fields
        assert collect_blocked_fields({}) == []
        assert collect_blocked_fields(None) == []

    def test_phase28_adds_queue_priority_and_job_id(self):
        """Phase 28 forbidden set must include queue_priority and job_id (new vs Phase 27)."""
        from app.ai.multivariant.multivariant_safety import _FORBIDDEN_KEYS
        assert "queue_priority" in _FORBIDDEN_KEYS
        assert "job_id" in _FORBIDDEN_KEYS

    def test_all_phase27_forbidden_keys_present(self):
        """Phase 28 must include all Phase 27 forbidden keys."""
        from app.ai.multivariant.multivariant_safety import _FORBIDDEN_KEYS
        phase27_keys = {
            "playback_speed", "segment_start", "segment_end", "subtitle_timing",
            "ffmpeg_args", "codec", "bitrate", "crf", "validation_rules",
            "output_path", "render_command", "render_segments", "segment_order",
        }
        assert phase27_keys.issubset(_FORBIDDEN_KEYS)

    def test_forbidden_key_count_is_15(self):
        from app.ai.multivariant.multivariant_safety import _FORBIDDEN_KEYS
        assert len(_FORBIDDEN_KEYS) == 15


# ---------------------------------------------------------------------------
# Planner tests
# ---------------------------------------------------------------------------

class TestMultiVariantPlanner:
    def test_returns_render_set(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_schema import AIMultiVariantRenderSet
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        assert isinstance(result, AIMultiVariantRenderSet)

    def test_mode_always_planning_only(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        assert result.mode == "planning_only"
        assert result.to_dict()["mode"] == "planning_only"

    def test_baseline_plan_always_present(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_baseline" in plan_ids

    def test_baseline_plan_always_renderable(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        baseline = next(p for p in result.plans if p.plan_id == "mvplan_baseline")
        assert baseline.renderable is True

    def test_baseline_plan_advisory_only(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        baseline = next(p for p in result.plans if p.plan_id == "mvplan_baseline")
        assert baseline.advisory_only is True

    def test_all_plans_advisory_only(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.85},
            retention={"retention_score": 30},
        )
        result = build_multivariant_render_plans(plan)
        for p in result.plans:
            assert p.advisory_only is True
            assert p.to_dict()["advisory_only"] is True

    def test_max_5_plans(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.9},
            retention={"retention_score": 30},
            subtitle_execution={"density": "compact", "emphasis_style": "bold"},
            variant_selection={"recommended_variant_id": "v1"},
        )
        result = build_multivariant_render_plans(plan)
        assert len(result.plans) <= 5

    def test_safe_to_enqueue_false_when_forbidden_fields(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_schema import AIMultiVariantRenderPlan
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        for p in result.plans:
            # If blocked_fields is non-empty, safe_to_enqueue must be False
            if p.blocked_fields:
                assert p.safe_to_enqueue is False

    def test_baseline_safe_to_enqueue_true(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        baseline = next(p for p in result.plans if p.plan_id == "mvplan_baseline")
        assert baseline.safe_to_enqueue is True
        assert baseline.blocked_fields == []

    def test_no_forbidden_keys_in_payload_overrides(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_safety import _FORBIDDEN_KEYS
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "viral_tiktok", "confidence": 0.9},
            retention={"retention_score": 25},
        )
        result = build_multivariant_render_plans(plan)
        for p in result.plans:
            overrides = p.planned_payload_overrides
            for fk in _FORBIDDEN_KEYS:
                assert fk not in overrides, f"Forbidden key {fk!r} in plan {p.plan_id}"

    def test_never_raises_on_none_input(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        result = build_multivariant_render_plans(None)
        assert result is not None
        assert result.mode == "planning_only"

    def test_never_raises_on_empty_plan(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        result = build_multivariant_render_plans(_FakeEditPlan())
        assert result is not None

    def test_recommended_plan_id_is_valid_plan(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        if result.recommended_plan_id is not None:
            plan_ids = [p.plan_id for p in result.plans]
            assert result.recommended_plan_id in plan_ids

    def test_with_creator_style_high_confidence(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.85},
        )
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_creator_style" in plan_ids

    def test_creator_style_plan_skipped_when_low_confidence(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.30},
        )
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_creator_style" not in plan_ids

    def test_creator_style_plan_skipped_when_no_style(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            creator_style_adaptation={"confidence": 0.90},
        )
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_creator_style" not in plan_ids

    def test_retention_plan_generated_when_low_score(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(retention={"retention_score": 30})
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_retention_optimized" in plan_ids

    def test_retention_plan_skipped_when_high_score(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(retention={"retention_score": 80})
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_retention_optimized" not in plan_ids

    def test_retention_plan_skipped_when_no_score(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(retention={})
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_retention_optimized" not in plan_ids

    def test_compact_subtitle_plan_generated(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            subtitle_execution={"density": "compact", "emphasis_style": "bold"},
        )
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_compact_subtitle" in plan_ids

    def test_compact_subtitle_plan_skipped_when_empty(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(subtitle_execution={})
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_compact_subtitle" not in plan_ids

    def test_recommended_variant_plan_generated_with_variant_selection(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(variant_selection={"recommended_variant_id": "v_top"})
        result = build_multivariant_render_plans(plan)
        plan_ids = [p.plan_id for p in result.plans]
        assert "mvplan_recommended_variant" in plan_ids

    def test_recommended_variant_plan_uses_selected_id(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(variant_selection={"recommended_variant_id": "v_top"})
        result = build_multivariant_render_plans(plan)
        rec = next((p for p in result.plans if p.plan_id == "mvplan_recommended_variant"), None)
        assert rec is not None
        assert rec.variant_id == "v_top"

    def test_recommended_prefers_non_baseline_safe_plan(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.9},
        )
        result = build_multivariant_render_plans(plan)
        assert result.recommended_plan_id != "mvplan_baseline"

    def test_recommended_falls_back_to_baseline_when_only_baseline(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan()  # minimal — only baseline plan expected
        result = build_multivariant_render_plans(plan)
        assert result.recommended_plan_id == "mvplan_baseline"

    def test_fallback_set_on_complete_failure(self):
        from app.ai.multivariant.multivariant_planner import _fallback_set
        result = _fallback_set("SomeError")
        assert result.available is False
        assert result.mode == "planning_only"
        assert len(result.plans) == 1
        assert result.plans[0].plan_id == "mvplan_baseline"
        assert result.recommended_plan_id == "mvplan_baseline"

    def test_to_dict_round_trip(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan()
        result = build_multivariant_render_plans(plan)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["mode"] == "planning_only"
        assert isinstance(d["plans"], list)

    def test_viral_tiktok_creator_style(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "viral_tiktok", "confidence": 0.9},
        )
        result = build_multivariant_render_plans(plan)
        cp = next((p for p in result.plans if p.plan_id == "mvplan_creator_style"), None)
        assert cp is not None
        overrides = cp.planned_payload_overrides
        assert overrides.get("camera_behavior") == "dynamic_safe"
        assert overrides.get("pacing_style") == "fast_cut"

    def test_low_retention_gets_fast_cut_pacing(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(retention={"retention_score": 25})
        result = build_multivariant_render_plans(plan)
        rp = next((p for p in result.plans if p.plan_id == "mvplan_retention_optimized"), None)
        assert rp is not None
        assert rp.planned_payload_overrides.get("pacing_style") == "fast_cut"

    def test_medium_retention_gets_moderate_pacing(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(retention={"retention_score": 55})
        result = build_multivariant_render_plans(plan)
        rp = next((p for p in result.plans if p.plan_id == "mvplan_retention_optimized"), None)
        assert rp is not None
        assert rp.planned_payload_overrides.get("pacing_style") == "moderate"

    def test_mutation_ids_from_safe_mutations(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            variant_selection={"recommended_variant_id": "v1"},
            safe_render_mutations={
                "applied_mutation_ids": ["m_sub", "m_pacing"],
                "mutations": [],
            },
        )
        result = build_multivariant_render_plans(plan)
        rec = next((p for p in result.plans if p.plan_id == "mvplan_recommended_variant"), None)
        assert rec is not None
        assert "m_sub" in rec.mutation_ids
        assert "m_pacing" in rec.mutation_ids


# ---------------------------------------------------------------------------
# edit_plan_schema backward-compat tests
# ---------------------------------------------------------------------------

class TestEditPlanSchemaPhase28:
    def test_multivariant_render_plans_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert hasattr(plan, "multivariant_render_plans")
        assert plan.multivariant_render_plans == {}

    def test_to_dict_includes_multivariant_render_plans(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "multivariant_render_plans" in d
        assert d["multivariant_render_plans"] == {}

    def test_to_dict_with_populated_multivariant_plans(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        plan.multivariant_render_plans = {"available": True, "mode": "planning_only", "plans": []}
        d = plan.to_dict()
        assert d["multivariant_render_plans"]["mode"] == "planning_only"

    def test_all_prior_phase_fields_still_present(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for key in (
            "execution_recommendations", "execution_simulation", "safe_render_mutations",
            "multivariant_render_plans",
        ):
            assert key in d


# ---------------------------------------------------------------------------
# render_influence integration tests
# ---------------------------------------------------------------------------

class TestRenderInfluencePhase28:
    def _make_payload(self):
        return MagicMock()

    def _make_report(self):
        return {"applied": [], "skipped": [], "warnings": []}

    def _call_report(self, plan_dict: dict):
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        plan = _FakeEditPlan()
        plan.multivariant_render_plans = plan_dict
        report = self._make_report()
        ri._report_multivariant_plans(self._make_payload(), plan, report)
        return report

    def test_deferred_in_skipped_on_valid_set(self):
        report = self._call_report({
            "available": True,
            "mode": "planning_only",
            "plans": [
                {"plan_id": "mvplan_baseline", "safe_to_enqueue": True},
                {"plan_id": "mvplan_creator_style", "safe_to_enqueue": True},
            ],
            "recommended_plan_id": "mvplan_creator_style",
        })
        assert any("deferred_phase28" in s for s in report["skipped"])

    def test_no_applied_mutations_from_multivariant(self):
        report = self._call_report({
            "available": True,
            "mode": "planning_only",
            "plans": [{"plan_id": "mvplan_baseline", "safe_to_enqueue": True}],
            "recommended_plan_id": "mvplan_baseline",
        })
        assert not any("mvplan" in a for a in report["applied"])

    def test_skipped_when_empty_dict(self):
        report = self._call_report({})
        assert any("no_result" in s for s in report["skipped"])

    def test_count_in_skipped_message(self):
        report = self._call_report({
            "available": True,
            "mode": "planning_only",
            "plans": [
                {"plan_id": "p1", "safe_to_enqueue": True},
                {"plan_id": "p2", "safe_to_enqueue": False},
            ],
            "recommended_plan_id": "p1",
        })
        skipped_str = " ".join(report["skipped"])
        assert "count=2" in skipped_str

    def test_safe_count_in_skipped_message(self):
        report = self._call_report({
            "available": True,
            "mode": "planning_only",
            "plans": [
                {"plan_id": "p1", "safe_to_enqueue": True},
                {"plan_id": "p2", "safe_to_enqueue": False},
            ],
            "recommended_plan_id": "p1",
        })
        skipped_str = " ".join(report["skipped"])
        assert "safe=1" in skipped_str

    def test_recommended_id_in_skipped_message(self):
        report = self._call_report({
            "available": True,
            "mode": "planning_only",
            "plans": [{"plan_id": "mvplan_creator_style", "safe_to_enqueue": True}],
            "recommended_plan_id": "mvplan_creator_style",
        })
        skipped_str = " ".join(report["skipped"])
        assert "mvplan_creator_style" in skipped_str

    def test_never_raises_on_none_edit_plan(self):
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        report = self._make_report()
        ri._report_multivariant_plans(self._make_payload(), None, report)  # should not raise


# ---------------------------------------------------------------------------
# Full planner integration: to_dict then influence pipeline
# ---------------------------------------------------------------------------

class TestPhase28EndToEnd:
    def test_full_pipeline_no_exception(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")

        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.85},
            retention={"retention_score": 45},
            subtitle_execution={"density": "compact", "emphasis_style": "bold"},
        )
        render_set = build_multivariant_render_plans(plan)
        plan.multivariant_render_plans = render_set.to_dict()

        payload = MagicMock()
        report = {"applied": [], "skipped": [], "warnings": []}
        ri._report_multivariant_plans(payload, plan, report)

        assert any("deferred_phase28" in s for s in report["skipped"])
        assert not any("mvplan" in a for a in report["applied"])

    def test_full_pipeline_payload_not_mutated(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")

        plan = _FakeEditPlan(retention={"retention_score": 20})
        render_set = build_multivariant_render_plans(plan)
        plan.multivariant_render_plans = render_set.to_dict()

        payload = MagicMock()
        report = {"applied": [], "skipped": [], "warnings": []}
        ri._report_multivariant_plans(payload, plan, report)

        # Payload should have no attribute-sets triggered by Phase 28
        payload.assert_not_called()

    def test_all_plans_in_to_dict_have_advisory_only_true(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "viral_tiktok", "confidence": 0.9},
            retention={"retention_score": 25},
        )
        result = build_multivariant_render_plans(plan)
        d = result.to_dict()
        for p in d["plans"]:
            assert p["advisory_only"] is True

    def test_plans_in_to_dict_have_no_forbidden_keys_in_overrides(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_safety import _FORBIDDEN_KEYS
        plan = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "storytelling", "confidence": 0.75},
            retention={"retention_score": 35},
            subtitle_execution={"density": "normal", "emphasis_style": "highlight"},
        )
        result = build_multivariant_render_plans(plan)
        d = result.to_dict()
        for p in d["plans"]:
            overrides = p.get("planned_payload_overrides", {})
            for fk in _FORBIDDEN_KEYS:
                assert fk not in overrides, f"Forbidden {fk!r} in plan {p['plan_id']}"
