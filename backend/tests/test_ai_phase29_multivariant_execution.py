"""
test_ai_phase29_multivariant_execution.py — Phase 29: Safe Multi-Variant Render Execution.

Invariants tested:
  - execution never raises
  - execution disabled by default
  - execution limit clamped 1-3
  - forbidden fields stripped
  - original payload never mutated
  - safe overrides applied
  - unsafe plans blocked
  - render jobs created only when enabled
  - max execution jobs respected (<=3)
  - no FFmpeg mutation
  - no playback_speed mutation
  - no subtitle timing rewrite
  - no segment reorder
  - no validation bypass
  - safe_baseline preserved
  - execution metadata attached correctly
  - render influence reports execution summary
  - backward compatibility preserved
  - advisory_origin always True
  - no API key / GPU / internet required
"""
from __future__ import annotations

import copy
import pytest
from dataclasses import dataclass, field
from typing import List, Optional
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

@dataclass
class _FakeEditPlan:
    multivariant_render_plans: dict = field(default_factory=dict)
    multivariant_execution: dict = field(default_factory=dict)
    variants: dict = field(default_factory=dict)
    variant_selection: dict = field(default_factory=dict)
    safe_render_mutations: dict = field(default_factory=dict)
    creator_style_adaptation: dict = field(default_factory=dict)
    retention: dict = field(default_factory=dict)
    subtitle_execution: dict = field(default_factory=dict)
    execution_recommendations: dict = field(default_factory=dict)
    execution_simulation: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    explainability: dict = field(default_factory=dict)


def _make_plan(plan_id: str, safe: bool = True, overrides: dict = None) -> dict:
    return {
        "plan_id": plan_id,
        "variant_id": plan_id,
        "label": f"Plan {plan_id}",
        "renderable": True,
        "safe_to_enqueue": safe,
        "advisory_only": True,
        "mutation_ids": [],
        "planned_payload_overrides": overrides or {"ai_mode": "advisory"},
        "blocked_fields": [],
        "warnings": [],
        "explanation": "",
    }


def _make_edit_plan_with_plans(plans: list) -> _FakeEditPlan:
    ep = _FakeEditPlan()
    ep.multivariant_render_plans = {
        "available": True,
        "mode": "planning_only",
        "plans": plans,
        "recommended_plan_id": plans[0]["plan_id"] if plans else None,
    }
    return ep


def _make_context(enabled: bool = False, limit: int = 2) -> dict:
    return {
        "ai_multivariant_execution_enabled": enabled,
        "ai_multivariant_execution_limit": limit,
    }


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestMultiVariantExecutionSchema:
    def _make_exec(self, **kwargs):
        from app.ai.multivariant.multivariant_execution_schema import AIMultiVariantExecution
        defaults = dict(
            execution_id="e1",
            plan_id="p1",
            variant_id="v1",
            enabled=True,
            safe=True,
            advisory_origin=True,
            payload_overrides={"ai_mode": "advisory"},
            blocked_fields=[],
            render_job_created=True,
            warnings=[],
            explanation=["Done"],
        )
        defaults.update(kwargs)
        return AIMultiVariantExecution(**defaults)

    def test_advisory_origin_always_true(self):
        e = self._make_exec(advisory_origin=False)
        assert e.to_dict()["advisory_origin"] is True

    def test_to_dict_keys(self):
        e = self._make_exec()
        d = e.to_dict()
        for k in ("execution_id", "plan_id", "variant_id", "enabled", "safe",
                  "advisory_origin", "payload_overrides", "blocked_fields",
                  "render_job_created", "warnings", "explanation"):
            assert k in d

    def test_blocked_fields_capped_at_20(self):
        e = self._make_exec(blocked_fields=[f"f{i}" for i in range(30)])
        assert len(e.to_dict()["blocked_fields"]) == 20

    def test_warnings_capped_at_10(self):
        e = self._make_exec(warnings=[f"w{i}" for i in range(15)])
        assert len(e.to_dict()["warnings"]) == 10

    def test_explanation_capped_at_10(self):
        e = self._make_exec(explanation=[f"x{i}" for i in range(15)])
        assert len(e.to_dict()["explanation"]) == 10

    def test_bool_coercions(self):
        e = self._make_exec(enabled=1, safe=0, render_job_created=1)
        d = e.to_dict()
        assert d["enabled"] is True
        assert d["safe"] is False
        assert d["render_job_created"] is True


class TestMultiVariantExecutionSetSchema:
    def _make_set(self, **kwargs):
        from app.ai.multivariant.multivariant_execution_schema import AIMultiVariantExecutionSet
        defaults = dict(
            available=True,
            execution_enabled=False,
            executions=[],
            executed_plan_ids=[],
            blocked_plan_ids=[],
            warnings=[],
        )
        defaults.update(kwargs)
        return AIMultiVariantExecutionSet(**defaults)

    def test_to_dict_keys(self):
        s = self._make_set()
        d = s.to_dict()
        for k in ("available", "execution_enabled", "executions",
                  "executed_plan_ids", "blocked_plan_ids", "warnings"):
            assert k in d

    def test_executions_capped_at_3(self):
        from app.ai.multivariant.multivariant_execution_schema import (
            AIMultiVariantExecutionSet, AIMultiVariantExecution,
        )
        execs = [
            AIMultiVariantExecution(execution_id=f"e{i}", plan_id=f"p{i}")
            for i in range(6)
        ]
        s = AIMultiVariantExecutionSet(executions=execs)
        assert len(s.to_dict()["executions"]) == 3

    def test_bool_coercions(self):
        s = self._make_set(available=1, execution_enabled=0)
        d = s.to_dict()
        assert d["available"] is True
        assert d["execution_enabled"] is False


# ---------------------------------------------------------------------------
# Safety tests
# ---------------------------------------------------------------------------

class TestMultiVariantExecutionSafety:
    def test_sanitize_strips_forbidden(self):
        from app.ai.multivariant.multivariant_execution_safety import sanitize_execution_overrides
        result = sanitize_execution_overrides({
            "playback_speed": 1.5,
            "queue_priority": 1,
            "job_id": "abc",
            "ai_mode": "advisory",
        })
        assert "playback_speed" not in result
        assert "queue_priority" not in result
        assert "job_id" not in result
        assert result.get("ai_mode") == "advisory"

    def test_sanitize_strips_unknown(self):
        from app.ai.multivariant.multivariant_execution_safety import sanitize_execution_overrides
        result = sanitize_execution_overrides({"unknown_key": "x", "pacing_style": "fast_cut"})
        assert "unknown_key" not in result
        assert result.get("pacing_style") == "fast_cut"

    def test_sanitize_drops_none(self):
        from app.ai.multivariant.multivariant_execution_safety import sanitize_execution_overrides
        result = sanitize_execution_overrides({"ai_mode": None, "pacing_style": "standard"})
        assert "ai_mode" not in result

    def test_sanitize_non_dict(self):
        from app.ai.multivariant.multivariant_execution_safety import sanitize_execution_overrides
        assert sanitize_execution_overrides(None) == {}
        assert sanitize_execution_overrides(42) == {}
        assert sanitize_execution_overrides("str") == {}

    def test_is_safe_clean(self):
        from app.ai.multivariant.multivariant_execution_safety import is_execution_override_safe
        assert is_execution_override_safe({"ai_mode": "advisory"}) is True

    def test_is_safe_forbidden(self):
        from app.ai.multivariant.multivariant_execution_safety import is_execution_override_safe
        assert is_execution_override_safe({"playback_speed": 2.0}) is False
        assert is_execution_override_safe({"ffmpeg_args": "-x"}) is False
        assert is_execution_override_safe({"render_command": "ffmpeg"}) is False
        assert is_execution_override_safe({"queue_priority": 1}) is False
        assert is_execution_override_safe({"job_id": "x"}) is False

    def test_is_safe_non_dict(self):
        from app.ai.multivariant.multivariant_execution_safety import is_execution_override_safe
        assert is_execution_override_safe(None) is True

    def test_collect_blocked_fields(self):
        from app.ai.multivariant.multivariant_execution_safety import collect_execution_blocked_fields
        blocked = collect_execution_blocked_fields({"playback_speed": 1.5, "ai_mode": "advisory"})
        assert "playback_speed" in blocked
        assert "ai_mode" not in blocked

    def test_forbidden_key_count_is_15(self):
        from app.ai.multivariant.multivariant_execution_safety import _FORBIDDEN_KEYS
        assert len(_FORBIDDEN_KEYS) == 15

    def test_queue_priority_and_job_id_forbidden(self):
        from app.ai.multivariant.multivariant_execution_safety import _FORBIDDEN_KEYS
        assert "queue_priority" in _FORBIDDEN_KEYS
        assert "job_id" in _FORBIDDEN_KEYS

    def test_ffmpeg_forbidden(self):
        from app.ai.multivariant.multivariant_execution_safety import _FORBIDDEN_KEYS
        assert "ffmpeg_args" in _FORBIDDEN_KEYS
        assert "render_command" in _FORBIDDEN_KEYS
        assert "codec" in _FORBIDDEN_KEYS

    def test_timing_forbidden(self):
        from app.ai.multivariant.multivariant_execution_safety import _FORBIDDEN_KEYS
        assert "segment_start" in _FORBIDDEN_KEYS
        assert "segment_end" in _FORBIDDEN_KEYS
        assert "subtitle_timing" in _FORBIDDEN_KEYS
        assert "segment_order" in _FORBIDDEN_KEYS
        assert "render_segments" in _FORBIDDEN_KEYS

    def test_allowed_key_set(self):
        from app.ai.multivariant.multivariant_execution_safety import _ALLOWED_KEYS
        expected = {
            "subtitle_density", "subtitle_emphasis", "camera_behavior",
            "pacing_style", "creator_style", "visual_rhythm_mode", "ai_mode",
        }
        assert expected == _ALLOWED_KEYS


# ---------------------------------------------------------------------------
# Execution engine tests
# ---------------------------------------------------------------------------

class TestMultiVariantExecutionEngine:
    def test_never_raises_on_none(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        result = build_multivariant_execution_set(None, None, None)
        assert result is not None

    def test_never_raises_on_empty_plan(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        result = build_multivariant_execution_set(_FakeEditPlan(), None, {})
        assert result is not None

    def test_disabled_by_default(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1")])
        result = build_multivariant_execution_set(ep, None, {})
        assert result.execution_enabled is False

    def test_disabled_when_flag_false(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1")])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=False))
        assert result.execution_enabled is False

    def test_no_executed_plans_when_disabled(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1"), _make_plan("p2")])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=False))
        assert result.executed_plan_ids == []

    def test_enabled_when_flag_true(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1")])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        assert result.execution_enabled is True

    def test_executes_safe_plans_when_enabled(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1", safe=True)])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        assert "p1" in result.executed_plan_ids

    def test_blocks_unsafe_plans(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        unsafe = _make_plan("p_unsafe", safe=False)
        ep = _make_edit_plan_with_plans([unsafe])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        assert "p_unsafe" in result.blocked_plan_ids
        assert "p_unsafe" not in result.executed_plan_ids

    def test_blocks_plans_with_forbidden_overrides(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        bad_plan = _make_plan("p_bad", safe=True, overrides={"playback_speed": 2.0})
        ep = _make_edit_plan_with_plans([bad_plan])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        assert "p_bad" in result.blocked_plan_ids

    def test_limit_clamped_to_max_3(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        plans = [_make_plan(f"p{i}") for i in range(5)]
        ep = _make_edit_plan_with_plans(plans)
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True, limit=10))
        assert len(result.executed_plan_ids) <= 3

    def test_limit_clamped_to_min_1(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        plans = [_make_plan(f"p{i}") for i in range(3)]
        ep = _make_edit_plan_with_plans(plans)
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True, limit=0))
        assert len(result.executed_plan_ids) <= 1

    def test_limit_2_executes_at_most_2(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        plans = [_make_plan(f"p{i}") for i in range(4)]
        ep = _make_edit_plan_with_plans(plans)
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True, limit=2))
        assert len(result.executed_plan_ids) <= 2

    def test_original_payload_not_mutated(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        payload = {"some_key": "original_value", "other": 42}
        original_copy = dict(payload)
        ep = _make_edit_plan_with_plans([_make_plan("p1", overrides={"ai_mode": "advisory"})])
        build_multivariant_execution_set(ep, payload, _make_context(enabled=True))
        assert payload == original_copy

    def test_no_playback_speed_in_payload_copies(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        payload = {"playback_speed": 1.0}
        ep = _make_edit_plan_with_plans([_make_plan("p1", overrides={"ai_mode": "advisory"})])
        result = build_multivariant_execution_set(ep, payload, _make_context(enabled=True))
        for ex in result.executions:
            assert "playback_speed" not in ex.payload_overrides

    def test_no_ffmpeg_args_in_payload_overrides(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1", overrides={"ffmpeg_args": "-x"})])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        for ex in result.executions:
            assert "ffmpeg_args" not in ex.payload_overrides

    def test_no_subtitle_timing_in_overrides(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1", overrides={"subtitle_timing": [1, 2]})])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        for ex in result.executions:
            assert "subtitle_timing" not in ex.payload_overrides

    def test_no_segment_reorder(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1", overrides={"segment_order": [2, 1, 0]})])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        for ex in result.executions:
            assert "segment_order" not in ex.payload_overrides

    def test_no_render_segments_mutation(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1", overrides={"render_segments": [[0, 5]]})])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        for ex in result.executions:
            assert "render_segments" not in ex.payload_overrides

    def test_advisory_origin_always_true(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1")])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        for ex in result.executions:
            assert ex.advisory_origin is True
            assert ex.to_dict()["advisory_origin"] is True

    def test_render_job_created_false_when_disabled(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1")])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=False))
        for ex in result.executions:
            assert ex.render_job_created is False

    def test_render_job_created_true_when_enabled_and_safe(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1", safe=True)])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        executed = [ex for ex in result.executions if ex.plan_id in result.executed_plan_ids]
        assert all(ex.render_job_created for ex in executed)

    def test_to_dict_round_trip(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1")])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "executions" in d
        assert "executed_plan_ids" in d
        assert "blocked_plan_ids" in d

    def test_safe_overrides_applied_in_payload_copy(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([
            _make_plan("p1", overrides={"ai_mode": "advisory", "pacing_style": "fast_cut"})
        ])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        for ex in result.executions:
            if ex.enabled and ex.safe:
                assert ex.payload_overrides.get("pacing_style") == "fast_cut"

    def test_deterministic_same_input_same_output(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1"), _make_plan("p2")])
        ctx = _make_context(enabled=True, limit=2)
        result1 = build_multivariant_execution_set(ep, None, ctx)
        result2 = build_multivariant_execution_set(ep, None, ctx)
        assert result1.executed_plan_ids == result2.executed_plan_ids
        assert result1.blocked_plan_ids == result2.blocked_plan_ids

    def test_empty_plans_no_execution(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        assert result.executed_plan_ids == []

    def test_fallback_set(self):
        from app.ai.multivariant.multivariant_execution import _fallback_set
        result = _fallback_set("SomeError")
        assert result.available is False
        assert result.execution_enabled is False
        assert result.executions == []
        assert any("SomeError" in w for w in result.warnings)

    def test_disabled_set_has_all_plans_blocked(self):
        from app.ai.multivariant.multivariant_execution import _disabled_set
        plans = [_make_plan("p1"), _make_plan("p2")]
        result = _disabled_set(plans)
        assert result.execution_enabled is False
        assert "p1" in result.blocked_plan_ids
        assert "p2" in result.blocked_plan_ids
        assert result.executed_plan_ids == []

    def test_no_api_key_no_gpu_no_internet(self):
        """Execution engine must run without any external dependencies."""
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _make_edit_plan_with_plans([_make_plan("p1")])
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        assert result is not None

    def test_mixed_safe_unsafe_plans(self):
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        plans = [
            _make_plan("safe_plan", safe=True),
            _make_plan("unsafe_plan", safe=False),
        ]
        ep = _make_edit_plan_with_plans(plans)
        result = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        assert "safe_plan" in result.executed_plan_ids
        assert "unsafe_plan" in result.blocked_plan_ids


# ---------------------------------------------------------------------------
# edit_plan_schema backward-compat tests
# ---------------------------------------------------------------------------

class TestEditPlanSchemaPhase29:
    def test_multivariant_execution_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert hasattr(plan, "multivariant_execution")
        assert plan.multivariant_execution == {}

    def test_to_dict_includes_multivariant_execution(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "multivariant_execution" in d
        assert d["multivariant_execution"] == {}

    def test_all_prior_fields_still_present(self):
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
            "execution_recommendations", "execution_simulation",
            "safe_render_mutations", "multivariant_render_plans",
            "multivariant_execution",
        ):
            assert key in d

    def test_populated_multivariant_execution_in_to_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        plan.multivariant_execution = {
            "available": True,
            "execution_enabled": False,
            "executions": [],
            "executed_plan_ids": [],
            "blocked_plan_ids": [],
        }
        d = plan.to_dict()
        assert d["multivariant_execution"]["execution_enabled"] is False


# ---------------------------------------------------------------------------
# render_influence integration tests
# ---------------------------------------------------------------------------

class TestRenderInfluencePhase29:
    def _make_report(self):
        return {"applied": [], "skipped": [], "warnings": []}

    def _call_report(self, exec_dict: dict):
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        plan = _FakeEditPlan()
        plan.multivariant_execution = exec_dict
        report = self._make_report()
        ri._report_multivariant_execution(MagicMock(), plan, report)
        return report

    def test_disabled_appears_in_skipped(self):
        report = self._call_report({
            "available": True,
            "execution_enabled": False,
            "executions": [{"execution_id": "e1", "plan_id": "p1"}],
            "executed_plan_ids": [],
            "blocked_plan_ids": ["p1"],
        })
        assert any("disabled_phase29" in s for s in report["skipped"])

    def test_disabled_not_in_applied(self):
        report = self._call_report({
            "available": True,
            "execution_enabled": False,
            "executions": [{"execution_id": "e1", "plan_id": "p1"}],
            "executed_plan_ids": [],
            "blocked_plan_ids": ["p1"],
        })
        assert not any("executed" in a for a in report["applied"])

    def test_executed_appears_in_applied(self):
        report = self._call_report({
            "available": True,
            "execution_enabled": True,
            "executions": [{
                "execution_id": "mvexec_p1",
                "plan_id": "p1",
                "enabled": True,
                "safe": True,
                "payload_overrides": {"ai_mode": "advisory"},
                "warnings": [],
            }],
            "executed_plan_ids": ["p1"],
            "blocked_plan_ids": [],
        })
        assert any("executed" in a for a in report["applied"])

    def test_blocked_appears_in_skipped(self):
        report = self._call_report({
            "available": True,
            "execution_enabled": True,
            "executions": [{
                "execution_id": "mvexec_pb",
                "plan_id": "pb",
                "enabled": False,
                "safe": False,
                "payload_overrides": {},
                "warnings": ["unsafe_overrides"],
            }],
            "executed_plan_ids": [],
            "blocked_plan_ids": ["pb"],
        })
        assert any("blocked" in s for s in report["skipped"])

    def test_empty_dict_skipped(self):
        report = self._call_report({})
        assert any("no_result" in s for s in report["skipped"])

    def test_never_raises_on_none_edit_plan(self):
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        report = self._make_report()
        ri._report_multivariant_execution(MagicMock(), None, report)

    def test_payload_not_mutated_in_reporter(self):
        payload = MagicMock()
        report = self._call_report({
            "available": True,
            "execution_enabled": True,
            "executions": [{
                "execution_id": "e1",
                "plan_id": "p1",
                "enabled": True,
                "safe": True,
                "payload_overrides": {"ai_mode": "advisory"},
                "warnings": [],
            }],
            "executed_plan_ids": ["p1"],
            "blocked_plan_ids": [],
        })
        payload.assert_not_called()

    def test_count_in_disabled_message(self):
        report = self._call_report({
            "available": True,
            "execution_enabled": False,
            "executions": [
                {"execution_id": "e1", "plan_id": "p1"},
                {"execution_id": "e2", "plan_id": "p2"},
            ],
            "executed_plan_ids": [],
            "blocked_plan_ids": ["p1", "p2"],
        })
        skipped_str = " ".join(report["skipped"])
        assert "plans=2" in skipped_str


# ---------------------------------------------------------------------------
# End-to-end integration
# ---------------------------------------------------------------------------

class TestPhase29EndToEnd:
    def test_full_disabled_pipeline(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")

        ep = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.85},
            retention={"retention_score": 40},
        )
        render_set = build_multivariant_render_plans(ep)
        ep.multivariant_render_plans = render_set.to_dict()

        exec_set = build_multivariant_execution_set(ep, None, _make_context(enabled=False))
        ep.multivariant_execution = exec_set.to_dict()

        assert exec_set.executed_plan_ids == []

        report = {"applied": [], "skipped": [], "warnings": []}
        ri._report_multivariant_execution(MagicMock(), ep, report)
        assert any("disabled_phase29" in s for s in report["skipped"])
        assert not any("executed" in a for a in report["applied"])

    def test_full_enabled_pipeline(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")

        ep = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "cinematic", "confidence": 0.85},
        )
        render_set = build_multivariant_render_plans(ep)
        ep.multivariant_render_plans = render_set.to_dict()

        exec_set = build_multivariant_execution_set(ep, None, _make_context(enabled=True, limit=2))
        ep.multivariant_execution = exec_set.to_dict()

        assert exec_set.execution_enabled is True
        assert len(exec_set.executed_plan_ids) <= 2

        report = {"applied": [], "skipped": [], "warnings": []}
        ri._report_multivariant_execution(MagicMock(), ep, report)
        # executed plans in applied
        assert any("executed" in a for a in report["applied"])

    def test_advisory_origin_preserved_throughout(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _FakeEditPlan()
        render_set = build_multivariant_render_plans(ep)
        ep.multivariant_render_plans = render_set.to_dict()
        exec_set = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        for ex in exec_set.executions:
            assert ex.advisory_origin is True

    def test_no_forbidden_keys_in_any_execution_overrides(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        from app.ai.multivariant.multivariant_execution_safety import _FORBIDDEN_KEYS
        ep = _FakeEditPlan(
            creator_style_adaptation={"adapted_style": "viral_tiktok", "confidence": 0.9},
            retention={"retention_score": 30},
        )
        render_set = build_multivariant_render_plans(ep)
        ep.multivariant_render_plans = render_set.to_dict()
        exec_set = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        for ex in exec_set.executions:
            for fk in _FORBIDDEN_KEYS:
                assert fk not in ex.payload_overrides, f"Forbidden {fk!r} in {ex.execution_id}"

    def test_to_dict_end_to_end(self):
        from app.ai.multivariant.multivariant_planner import build_multivariant_render_plans
        from app.ai.multivariant.multivariant_execution import build_multivariant_execution_set
        ep = _FakeEditPlan()
        render_set = build_multivariant_render_plans(ep)
        ep.multivariant_render_plans = render_set.to_dict()
        exec_set = build_multivariant_execution_set(ep, None, _make_context(enabled=True))
        d = exec_set.to_dict()
        assert isinstance(d, dict)
        assert d["execution_enabled"] is True
        assert isinstance(d["executions"], list)
        assert len(d["executions"]) <= 3
