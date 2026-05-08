"""
test_ai_phase24_render_decision_preview.py — Phase 24 test suite.

Tests: preview schema, decision_preview builder, edit_plan_schema field,
render_influence reporter, safety invariants, fallback handling.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestPreviewSchema:
    def test_import(self):
        from app.ai.preview.preview_schema import (
            AIRenderDecisionPreview,
            AIPreviewSafetyReport,
            VALID_SAFETY_STATUSES,
        )
        assert AIRenderDecisionPreview is not None
        assert AIPreviewSafetyReport is not None
        assert "safe" in VALID_SAFETY_STATUSES

    def test_valid_safety_statuses(self):
        from app.ai.preview.preview_schema import VALID_SAFETY_STATUSES
        assert VALID_SAFETY_STATUSES == frozenset({"safe", "caution", "blocked", "unavailable"})

    def test_render_decision_preview_defaults(self):
        from app.ai.preview.preview_schema import AIRenderDecisionPreview
        p = AIRenderDecisionPreview()
        assert p.available is True
        assert p.mode == "advisory"
        assert p.selected_variant_id is None
        assert p.creator_style == ""
        assert p.confidence == 0.0
        assert p.safety_status == "safe"

    def test_render_decision_preview_to_dict_mode_always_advisory(self):
        from app.ai.preview.preview_schema import AIRenderDecisionPreview
        p = AIRenderDecisionPreview(mode="execution")
        d = p.to_dict()
        assert d["mode"] == "advisory"

    def test_render_decision_preview_to_dict_confidence_clamped(self):
        from app.ai.preview.preview_schema import AIRenderDecisionPreview
        p = AIRenderDecisionPreview(confidence=1.5)
        assert p.to_dict()["confidence"] == 1.0
        p2 = AIRenderDecisionPreview(confidence=-0.5)
        assert p2.to_dict()["confidence"] == 0.0

    def test_render_decision_preview_invalid_safety_status_defaults_safe(self):
        from app.ai.preview.preview_schema import AIRenderDecisionPreview
        p = AIRenderDecisionPreview(safety_status="unknown_status")
        assert p.to_dict()["safety_status"] == "safe"

    def test_render_decision_preview_valid_safety_statuses(self):
        from app.ai.preview.preview_schema import AIRenderDecisionPreview, VALID_SAFETY_STATUSES
        for status in VALID_SAFETY_STATUSES:
            p = AIRenderDecisionPreview(safety_status=status)
            assert p.to_dict()["safety_status"] == status

    def test_safety_report_defaults(self):
        from app.ai.preview.preview_schema import AIPreviewSafetyReport
        r = AIPreviewSafetyReport()
        assert r.safe_to_preview is True
        assert r.safe_to_execute is False
        assert r.advisory_only is True

    def test_safety_report_to_dict_safe_to_execute_always_false(self):
        from app.ai.preview.preview_schema import AIPreviewSafetyReport
        r = AIPreviewSafetyReport(safe_to_execute=True)
        assert r.to_dict()["safe_to_execute"] is False

    def test_safety_report_to_dict_advisory_only_always_true(self):
        from app.ai.preview.preview_schema import AIPreviewSafetyReport
        r = AIPreviewSafetyReport(advisory_only=False)
        assert r.to_dict()["advisory_only"] is True

    def test_safety_report_to_dict_keys(self):
        from app.ai.preview.preview_schema import AIPreviewSafetyReport
        d = AIPreviewSafetyReport().to_dict()
        assert set(d.keys()) == {
            "safe_to_preview", "safe_to_execute",
            "blocked_reasons", "advisory_only", "warnings",
        }

    def test_render_decision_preview_to_dict_keys(self):
        from app.ai.preview.preview_schema import AIRenderDecisionPreview
        d = AIRenderDecisionPreview().to_dict()
        assert set(d.keys()) == {
            "available", "mode", "selected_variant_id", "creator_style",
            "decision_summary", "recommended_actions", "blocked_actions",
            "safety_status", "confidence", "warnings", "explanation",
        }

    def test_recommended_actions_capped_at_10(self):
        from app.ai.preview.preview_schema import AIRenderDecisionPreview
        p = AIRenderDecisionPreview(recommended_actions=["a"] * 20)
        assert len(p.to_dict()["recommended_actions"]) == 10

    def test_explanation_capped_at_8(self):
        from app.ai.preview.preview_schema import AIRenderDecisionPreview
        p = AIRenderDecisionPreview(explanation=["x"] * 20)
        assert len(p.to_dict()["explanation"]) == 8


# ── decision_preview builder tests ────────────────────────────────────────────

class TestBuildRenderDecisionPreview:
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
        from app.ai.preview.decision_preview import build_render_decision_preview
        assert callable(build_render_decision_preview)

    def test_none_edit_plan_returns_dict(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        result = build_render_decision_preview(None)
        assert isinstance(result, dict)
        assert result["available"] is False
        assert result["safety_status"] == "unavailable"
        assert "safety_report" in result

    def test_none_edit_plan_mode_advisory(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        result = build_render_decision_preview(None)
        assert result["mode"] == "advisory"

    def test_basic_plan_returns_dict(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert isinstance(result, dict)
        assert result["available"] is True

    def test_result_always_has_safety_report(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert "safety_report" in result
        sr = result["safety_report"]
        assert sr["safe_to_execute"] is False
        assert sr["advisory_only"] is True

    def test_blocked_actions_always_present(self):
        from app.ai.preview.decision_preview import build_render_decision_preview, _BLOCKED_ACTIONS
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        for action in _BLOCKED_ACTIONS:
            assert action in result["blocked_actions"]

    def test_mode_always_advisory(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert result["mode"] == "advisory"

    def test_safe_to_execute_always_false(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert result["safety_report"]["safe_to_execute"] is False

    def test_with_variant_selection(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            variant_selection={
                "selected_variant_id": "v_retention",
                "selection_confidence": 0.82,
                "fallback_used": False,
                "rejected_count": 2,
            },
        )
        result = build_render_decision_preview(plan)
        assert result["selected_variant_id"] == "v_retention"
        assert result["confidence"] > 0

    def test_with_creator_style_adaptation(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            creator_style_adaptation={
                "primary_style": "cinematic",
                "confidence": 0.75,
                "detected": True,
            },
        )
        result = build_render_decision_preview(plan)
        assert result["creator_style"] == "cinematic"

    def test_low_retention_gives_caution(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            retention={"overall_retention_score": 30, "risk_regions": [{"start": 0}]},
            variant_selection={"selected_variant_id": "v1", "selection_confidence": 0.9},
        )
        result = build_render_decision_preview(plan)
        assert result["safety_status"] == "caution"

    def test_low_variant_confidence_gives_caution(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            variant_selection={
                "selected_variant_id": "v1",
                "selection_confidence": 0.15,
            },
            retention={"overall_retention_score": 80},
        )
        result = build_render_decision_preview(plan)
        assert result["safety_status"] == "caution"

    def test_unavailable_when_no_variant_no_metadata(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert result["safety_status"] == "unavailable"

    def test_recommended_actions_non_empty(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert len(result["recommended_actions"]) >= 1

    def test_recommended_actions_at_most_5(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            variant_selection={"selected_variant_id": "v1", "selection_confidence": 0.9},
            creator_style_adaptation={"primary_style": "viral_tiktok", "confidence": 0.8, "detected": True},
            retention={"overall_retention_score": 45, "risk_regions": [{"s": 0}, {"s": 5}]},
            story_optimization={"narrative_score": 50, "issues": ["gap", "abrupt_end"]},
            timing_mutation={"candidates": [{"safe_to_apply": True}, {"safe_to_apply": True}]},
            subtitle_execution={"available": True},
        )
        result = build_render_decision_preview(plan)
        assert len(result["recommended_actions"]) <= 5

    def test_explanation_non_empty(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert len(result["explanation"]) >= 1

    def test_decision_summary_non_empty_string(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert isinstance(result["decision_summary"], str)
        assert len(result["decision_summary"]) > 0

    def test_confidence_in_0_1_range(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            variant_selection={"selected_variant_id": "v1", "selection_confidence": 0.9},
            retention={"overall_retention_score": 75},
        )
        result = build_render_decision_preview(plan)
        assert 0.0 <= result["confidence"] <= 1.0

    def test_variant_purpose_resolved_in_summary(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            variants={
                "available": True,
                "variants": [
                    {"variant_id": "v_retention", "purpose": "retention"},
                ],
            },
            variant_selection={
                "selected_variant_id": "v_retention",
                "selection_confidence": 0.75,
            },
        )
        result = build_render_decision_preview(plan)
        assert "retention" in result["decision_summary"]

    def test_fallback_used_in_summary(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            variant_selection={
                "selected_variant_id": "v_safe",
                "selection_confidence": 0.60,
                "fallback_used": True,
            },
            retention={"overall_retention_score": 70},
        )
        result = build_render_decision_preview(plan)
        assert "baseline" in result["decision_summary"] or "safe" in result["decision_summary"]

    def test_never_raises_on_garbage_plan(self):
        from app.ai.preview.decision_preview import build_render_decision_preview

        class BadPlan:
            @property
            def variant_selection(self):
                raise RuntimeError("boom")

        result = build_render_decision_preview(BadPlan())
        assert isinstance(result, dict)
        assert result["available"] is False

    def test_context_dict_accepted(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan, context={"job_id": "test-123"})
        assert isinstance(result, dict)


# ── Blocked actions constant tests ────────────────────────────────────────────

class TestBlockedActionsConstant:
    def test_blocked_actions_present(self):
        from app.ai.preview.decision_preview import _BLOCKED_ACTIONS
        assert isinstance(_BLOCKED_ACTIONS, list)
        assert len(_BLOCKED_ACTIONS) >= 5

    def test_ffmpeg_blocked(self):
        from app.ai.preview.decision_preview import _BLOCKED_ACTIONS
        assert "ffmpeg_filter_chain_mutation" in _BLOCKED_ACTIONS

    def test_timing_mutation_blocked(self):
        from app.ai.preview.decision_preview import _BLOCKED_ACTIONS
        assert "timing_mutation_application" in _BLOCKED_ACTIONS

    def test_playback_speed_blocked(self):
        from app.ai.preview.decision_preview import _BLOCKED_ACTIONS
        assert "playback_speed_mutation" in _BLOCKED_ACTIONS

    def test_subtitle_timing_blocked(self):
        from app.ai.preview.decision_preview import _BLOCKED_ACTIONS
        assert "subtitle_timing_rewrite" in _BLOCKED_ACTIONS

    def test_autonomous_rendering_blocked(self):
        from app.ai.preview.decision_preview import _BLOCKED_ACTIONS
        assert "autonomous_rendering_of_selected_variant" in _BLOCKED_ACTIONS

    def test_segment_reorder_blocked(self):
        from app.ai.preview.decision_preview import _BLOCKED_ACTIONS
        assert "segment_reorder" in _BLOCKED_ACTIONS


# ── AIEditPlan field tests ────────────────────────────────────────────────────

class TestAIEditPlanRenderDecisionPreviewField:
    def _make_plan(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        return AIEditPlan(
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )

    def test_field_exists(self):
        plan = self._make_plan()
        assert hasattr(plan, "render_decision_preview")

    def test_field_default_empty_dict(self):
        plan = self._make_plan()
        assert plan.render_decision_preview == {}

    def test_field_in_to_dict(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "render_decision_preview" in d

    def test_field_populated_in_to_dict(self):
        plan = self._make_plan()
        plan.render_decision_preview = {"available": True, "mode": "advisory"}
        d = plan.to_dict()
        assert d["render_decision_preview"]["available"] is True

    def test_field_independence(self):
        plan1 = self._make_plan()
        plan2 = self._make_plan()
        plan1.render_decision_preview["x"] = 1
        assert "x" not in plan2.render_decision_preview


# ── render_influence reporter tests ──────────────────────────────────────────

class TestRenderInfluenceReportRenderDecisionPreview:
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
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        for k, v in overrides.items():
            setattr(plan, k, v)
        return plan

    def test_reporter_exists(self):
        from app.ai.director.render_influence import _report_render_decision_preview
        assert callable(_report_render_decision_preview)

    def test_no_render_decision_preview_skips(self):
        from app.ai.director.render_influence import _report_render_decision_preview
        plan = self._make_plan()
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_render_decision_preview(self._make_payload(), plan, report)
        assert any("render_decision_preview" in s for s in report["skipped"])

    def test_empty_render_decision_preview_skips(self):
        from app.ai.director.render_influence import _report_render_decision_preview
        plan = self._make_plan(render_decision_preview={})
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_render_decision_preview(self._make_payload(), plan, report)
        assert any("render_decision_preview:empty" in s for s in report["skipped"])

    def test_populated_preview_deferred_phase24(self):
        from app.ai.director.render_influence import _report_render_decision_preview
        plan = self._make_plan(render_decision_preview={
            "available": True,
            "mode": "advisory",
            "safety_status": "safe",
            "confidence": 0.75,
            "selected_variant_id": "v_retention",
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_render_decision_preview(self._make_payload(), plan, report)
        assert any("deferred_phase24" in s for s in report["skipped"])

    def test_preview_status_in_report(self):
        from app.ai.director.render_influence import _report_render_decision_preview
        plan = self._make_plan(render_decision_preview={
            "available": True,
            "safety_status": "caution",
            "confidence": 0.40,
            "selected_variant_id": None,
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_render_decision_preview(self._make_payload(), plan, report)
        assert any("caution" in s for s in report["skipped"])

    def test_no_payload_mutation(self):
        from app.ai.director.render_influence import _report_render_decision_preview
        payload = self._make_payload()
        plan = self._make_plan(render_decision_preview={
            "available": True,
            "safety_status": "safe",
            "confidence": 0.80,
            "selected_variant_id": "v1",
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        original_attrs = {k: getattr(payload, k) for k in dir(payload) if not k.startswith("_")}
        _report_render_decision_preview(payload, plan, report)
        for k, v in original_attrs.items():
            assert getattr(payload, k) == v

    def test_wired_into_apply_ai_render_influence(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan(render_decision_preview={
            "available": True,
            "safety_status": "safe",
            "confidence": 0.75,
            "selected_variant_id": "v_retention",
        })
        payload = self._make_payload()
        _, report = apply_ai_render_influence(payload, plan)
        assert any("render_decision_preview" in s for s in report["skipped"])


# ── Safety invariant tests ────────────────────────────────────────────────────

class TestPhase24SafetyInvariants:
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

    def test_safe_to_execute_always_false(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        for conf in [0.0, 0.5, 0.99, 1.0]:
            plan = self._make_plan(
                variant_selection={"selected_variant_id": "v1", "selection_confidence": conf},
                retention={"overall_retention_score": 90},
            )
            result = build_render_decision_preview(plan)
            assert result["safety_report"]["safe_to_execute"] is False, f"Failed for conf={conf}"

    def test_advisory_only_always_true(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            variant_selection={"selected_variant_id": "v1", "selection_confidence": 0.95},
        )
        result = build_render_decision_preview(plan)
        assert result["safety_report"]["advisory_only"] is True

    def test_mode_always_advisory_in_result(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert result["mode"] == "advisory"

    def test_no_ffmpeg_args_in_result(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan(
            variant_selection={"selected_variant_id": "v1", "selection_confidence": 0.9},
        )
        result = build_render_decision_preview(plan)
        result_str = str(result)
        assert "ffmpeg" not in result_str.lower() or "ffmpeg_filter_chain_mutation" in result_str

    def test_phase24_advisory_only_in_blocked_reasons(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        plan = self._make_plan()
        result = build_render_decision_preview(plan)
        assert "phase24_advisory_only_mode" in result["safety_report"]["blocked_reasons"]

    def test_never_raises_on_none(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        result = build_render_decision_preview(None)
        assert isinstance(result, dict)

    def test_never_raises_on_empty_dict_plan(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        result = build_render_decision_preview({})
        assert isinstance(result, dict)

    def test_never_raises_on_string_plan(self):
        from app.ai.preview.decision_preview import build_render_decision_preview
        result = build_render_decision_preview("not_a_plan")
        assert isinstance(result, dict)


# ── AI Director integration tests ─────────────────────────────────────────────

class TestAIDirectorPhase24Integration:
    def test_ai_director_has_render_decision_preview_block(self):
        import inspect
        from app.ai.director import ai_director
        src = inspect.getsource(ai_director)
        assert "_attach_render_decision_preview" in src

    def test_attach_function_importable(self):
        from app.ai.director.ai_director import _attach_render_decision_preview
        assert callable(_attach_render_decision_preview)

    def test_attach_function_populates_field(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_render_decision_preview
        plan = AIEditPlan(
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        _attach_render_decision_preview(plan, "test-job-001")
        assert isinstance(plan.render_decision_preview, dict)

    def test_attach_function_does_not_raise(self):
        from app.ai.director.ai_director import _attach_render_decision_preview
        _attach_render_decision_preview(None, "test-job-002")

    def test_render_decision_preview_in_to_dict_after_attach(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_render_decision_preview
        plan = AIEditPlan(
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        _attach_render_decision_preview(plan, "test-job-003")
        d = plan.to_dict()
        assert "render_decision_preview" in d
        assert isinstance(d["render_decision_preview"], dict)
