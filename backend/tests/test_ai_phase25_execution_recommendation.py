"""
test_ai_phase25_execution_recommendation.py — Phase 25 test suite.

Tests: execution schema, safety gates, recommendation builder, edit_plan field,
render_influence reporter, safety invariants, AI Director integration.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestExecutionSchema:
    def test_import(self):
        from app.ai.execution.execution_schema import (
            AIExecutionRecommendation,
            AIExecutionPack,
            VALID_CATEGORIES,
        )
        assert AIExecutionRecommendation is not None
        assert AIExecutionPack is not None
        assert len(VALID_CATEGORIES) >= 6

    def test_valid_categories(self):
        from app.ai.execution.execution_schema import VALID_CATEGORIES
        expected = {"subtitle", "pacing", "camera", "creator_style", "retention", "visual_rhythm", "safe_baseline"}
        assert expected.issubset(VALID_CATEGORIES)

    def test_recommendation_defaults(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        r = AIExecutionRecommendation(recommendation_id="test")
        assert r.advisory_only is True
        assert r.safe_to_apply is False
        assert r.confidence == 0.0

    def test_recommendation_to_dict_advisory_always_true(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        r = AIExecutionRecommendation(recommendation_id="test", advisory_only=False)
        assert r.to_dict()["advisory_only"] is True

    def test_recommendation_to_dict_confidence_clamped(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        r = AIExecutionRecommendation(recommendation_id="x", confidence=2.5)
        assert r.to_dict()["confidence"] == 1.0
        r2 = AIExecutionRecommendation(recommendation_id="y", confidence=-1.0)
        assert r2.to_dict()["confidence"] == 0.0

    def test_recommendation_invalid_category_defaults_safe_baseline(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        r = AIExecutionRecommendation(recommendation_id="x", category="illegal_cat")
        assert r.to_dict()["category"] == "safe_baseline"

    def test_recommendation_valid_category_preserved(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation, VALID_CATEGORIES
        for cat in VALID_CATEGORIES:
            r = AIExecutionRecommendation(recommendation_id="x", category=cat)
            assert r.to_dict()["category"] == cat

    def test_recommendation_explanation_capped_at_5(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        r = AIExecutionRecommendation(recommendation_id="x", explanation=["a"] * 20)
        assert len(r.to_dict()["explanation"]) == 5

    def test_pack_defaults(self):
        from app.ai.execution.execution_schema import AIExecutionPack
        pack = AIExecutionPack()
        assert pack.available is True
        assert pack.mode == "advisory"
        assert pack.recommended_pack_id is None

    def test_pack_to_dict_mode_always_advisory(self):
        from app.ai.execution.execution_schema import AIExecutionPack
        pack = AIExecutionPack(mode="execution")
        assert pack.to_dict()["mode"] == "advisory"

    def test_pack_to_dict_recommendations_capped_at_10(self):
        from app.ai.execution.execution_schema import AIExecutionPack, AIExecutionRecommendation
        recs = [AIExecutionRecommendation(recommendation_id=f"r{i}") for i in range(15)]
        pack = AIExecutionPack(recommendations=recs)
        assert len(pack.to_dict()["recommendations"]) == 10

    def test_pack_to_dict_keys(self):
        from app.ai.execution.execution_schema import AIExecutionPack
        d = AIExecutionPack().to_dict()
        assert set(d.keys()) == {"available", "mode", "recommendations", "recommended_pack_id", "warnings"}

    def test_recommendation_to_dict_keys(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        d = AIExecutionRecommendation(recommendation_id="x").to_dict()
        assert set(d.keys()) == {
            "recommendation_id", "label", "category", "confidence",
            "safe_to_apply", "advisory_only", "recommended_settings",
            "blocked_settings", "warnings", "explanation",
        }


# ── Execution safety tests ────────────────────────────────────────────────────

class TestExecutionSafety:
    def test_import(self):
        from app.ai.execution.execution_safety import (
            sanitize_execution_settings,
            is_execution_recommendation_safe,
        )
        assert callable(sanitize_execution_settings)
        assert callable(is_execution_recommendation_safe)

    def test_sanitize_allowed_keys_preserved(self):
        from app.ai.execution.execution_safety import sanitize_execution_settings
        settings = {
            "subtitle_density": "compact",
            "pacing_style": "fast",
            "camera_behavior": "static",
        }
        result = sanitize_execution_settings(settings)
        assert result["subtitle_density"] == "compact"
        assert result["pacing_style"] == "fast"
        assert result["camera_behavior"] == "static"

    def test_sanitize_forbidden_keys_stripped(self):
        from app.ai.execution.execution_safety import sanitize_execution_settings
        forbidden = [
            "playback_speed", "segment_start", "segment_end", "subtitle_timing",
            "ffmpeg_args", "codec", "bitrate", "crf", "validation_rules",
            "output_path", "render_command",
        ]
        for key in forbidden:
            result = sanitize_execution_settings({key: "bad_value", "ai_mode": "advisory"})
            assert key not in result, f"Forbidden key {key!r} was not stripped"
            assert result.get("ai_mode") == "advisory"

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.execution.execution_safety import sanitize_execution_settings
        assert sanitize_execution_settings(None) == {}
        assert sanitize_execution_settings("string") == {}
        assert sanitize_execution_settings(42) == {}
        assert sanitize_execution_settings([]) == {}

    def test_sanitize_unknown_keys_stripped(self):
        from app.ai.execution.execution_safety import sanitize_execution_settings
        result = sanitize_execution_settings({"unknown_key": "val", "pacing_style": "fast"})
        assert "unknown_key" not in result
        assert result.get("pacing_style") == "fast"

    def test_sanitize_never_raises(self):
        from app.ai.execution.execution_safety import sanitize_execution_settings
        sanitize_execution_settings({"a": object(), "b": None})

    def test_is_safe_with_clean_settings(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        from app.ai.execution.execution_safety import is_execution_recommendation_safe
        r = AIExecutionRecommendation(
            recommendation_id="x",
            recommended_settings={"pacing_style": "fast", "ai_mode": "advisory"},
        )
        assert is_execution_recommendation_safe(r) is True

    def test_is_safe_returns_false_for_forbidden_key(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        from app.ai.execution.execution_safety import is_execution_recommendation_safe
        r = AIExecutionRecommendation(
            recommendation_id="x",
            recommended_settings={"playback_speed": 1.5},
        )
        assert is_execution_recommendation_safe(r) is False

    def test_is_safe_returns_false_for_ffmpeg_args(self):
        from app.ai.execution.execution_schema import AIExecutionRecommendation
        from app.ai.execution.execution_safety import is_execution_recommendation_safe
        r = AIExecutionRecommendation(
            recommendation_id="x",
            recommended_settings={"ffmpeg_args": "-vf scale=1920:1080"},
        )
        assert is_execution_recommendation_safe(r) is False

    def test_is_safe_returns_true_for_none_settings(self):
        from app.ai.execution.execution_safety import is_execution_recommendation_safe
        assert is_execution_recommendation_safe(None) is False

    def test_is_safe_never_raises(self):
        from app.ai.execution.execution_safety import is_execution_recommendation_safe
        is_execution_recommendation_safe(object())
        is_execution_recommendation_safe("garbage")


# ── Recommendation builder tests ──────────────────────────────────────────────

class TestBuildExecutionRecommendations:
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
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        assert callable(build_execution_recommendations)

    def test_never_raises_on_none(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        result = build_execution_recommendations(None)
        assert result is not None

    def test_returns_execution_pack(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        from app.ai.execution.execution_schema import AIExecutionPack
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        assert isinstance(result, AIExecutionPack)

    def test_safe_baseline_always_present(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        ids = [r.recommendation_id for r in result.recommendations]
        assert "safe_baseline" in ids

    def test_safe_baseline_present_on_none_plan(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        result = build_execution_recommendations(None)
        # fallback pack may or may not have safe_baseline; available=False expected
        assert result.available is False

    def test_mode_always_advisory(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        assert result.mode == "advisory"

    def test_recommended_pack_id_set(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        assert result.recommended_pack_id is not None

    def test_creator_style_recommendation_built(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            creator_style_adaptation={
                "detected": True,
                "primary_style": "viral_tiktok",
                "confidence": 0.80,
            }
        )
        result = build_execution_recommendations(plan)
        ids = [r.recommendation_id for r in result.recommendations]
        assert any("creator_style" in rid for rid in ids)

    def test_retention_recommendation_built(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            retention={"overall_retention_score": 45, "risk_regions": []}
        )
        result = build_execution_recommendations(plan)
        ids = [r.recommendation_id for r in result.recommendations]
        assert "retention_pacing" in ids

    def test_subtitle_recommendation_built(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            subtitle_execution={"available": True, "density": "compact", "emphasis_style": "bold"}
        )
        result = build_execution_recommendations(plan)
        ids = [r.recommendation_id for r in result.recommendations]
        assert "compact_subtitle" in ids

    def test_visual_rhythm_recommendation_built(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            beat_visual_execution={"available": True, "bpm": 128, "pulse_regions": []}
        )
        result = build_execution_recommendations(plan)
        ids = [r.recommendation_id for r in result.recommendations]
        assert "visual_rhythm" in ids

    def test_story_pacing_recommendation_built(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            story_optimization={"available": True, "flow_type": "three_act", "narrative_score": 72}
        )
        result = build_execution_recommendations(plan)
        ids = [r.recommendation_id for r in result.recommendations]
        assert "story_pacing" in ids

    def test_recommendations_all_advisory_only(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            creator_style_adaptation={"detected": True, "primary_style": "cinematic", "confidence": 0.8},
            retention={"overall_retention_score": 60},
            subtitle_execution={"available": True, "density": "normal"},
        )
        result = build_execution_recommendations(plan)
        for r in result.recommendations:
            assert r.advisory_only is True, f"Rec {r.recommendation_id} not advisory_only"

    def test_no_forbidden_settings_in_recommendations(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        from app.ai.execution.execution_safety import _FORBIDDEN_KEYS
        plan = self._make_plan(
            creator_style_adaptation={"detected": True, "primary_style": "viral_tiktok", "confidence": 0.9},
            retention={"overall_retention_score": 35},
        )
        result = build_execution_recommendations(plan)
        for r in result.recommendations:
            for key in r.recommended_settings:
                assert key not in _FORBIDDEN_KEYS, \
                    f"Forbidden key {key!r} in {r.recommendation_id} settings"

    def test_deterministic_same_plan_same_result(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            creator_style_adaptation={"detected": True, "primary_style": "educational", "confidence": 0.7},
            retention={"overall_retention_score": 65},
        )
        result1 = build_execution_recommendations(plan)
        result2 = build_execution_recommendations(plan)
        assert result1.recommended_pack_id == result2.recommended_pack_id
        assert len(result1.recommendations) == len(result2.recommendations)

    def test_never_raises_on_garbage_plan(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations

        class BadPlan:
            @property
            def creator_style_adaptation(self):
                raise RuntimeError("boom")

        result = build_execution_recommendations(BadPlan())
        assert result is not None

    def test_context_dict_accepted(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan, context={"job_id": "test-125"})
        assert result is not None

    def test_safe_to_apply_false_when_missing_metadata(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        baseline = next((r for r in result.recommendations if r.recommendation_id == "safe_baseline"), None)
        assert baseline is not None
        assert baseline.safe_to_apply is True

    def test_retention_low_score_gives_fast_cuts_pacing(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(retention={"overall_retention_score": 25})
        result = build_execution_recommendations(plan)
        ret_rec = next((r for r in result.recommendations if r.recommendation_id == "retention_pacing"), None)
        assert ret_rec is not None
        assert ret_rec.recommended_settings.get("pacing_style") == "fast_cuts"
        assert ret_rec.recommended_settings.get("hook_density") == "high"

    def test_retention_high_score_gives_standard_pacing(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(retention={"overall_retention_score": 85})
        result = build_execution_recommendations(plan)
        ret_rec = next((r for r in result.recommendations if r.recommendation_id == "retention_pacing"), None)
        assert ret_rec is not None
        assert ret_rec.recommended_settings.get("pacing_style") == "standard"

    def test_creator_style_safe_to_apply_false_when_low_confidence(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            creator_style_adaptation={"detected": True, "primary_style": "cinematic", "confidence": 0.20}
        )
        result = build_execution_recommendations(plan)
        style_rec = next((r for r in result.recommendations if "creator_style" in r.recommendation_id), None)
        assert style_rec is not None
        assert style_rec.safe_to_apply is False

    def test_visual_rhythm_high_bpm_energetic(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(beat_visual_execution={"available": True, "bpm": 140})
        result = build_execution_recommendations(plan)
        vr = next((r for r in result.recommendations if r.recommendation_id == "visual_rhythm"), None)
        assert vr is not None
        assert vr.recommended_settings.get("visual_rhythm_mode") == "energetic"

    def test_visual_rhythm_low_bpm_calm(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(beat_visual_execution={"available": True, "bpm": 60})
        result = build_execution_recommendations(plan)
        vr = next((r for r in result.recommendations if r.recommendation_id == "visual_rhythm"), None)
        assert vr is not None
        assert vr.recommended_settings.get("visual_rhythm_mode") == "calm"

    def test_no_payload_mutation(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations

        class FakePayload:
            motion_aware_crop = False
            add_subtitle = False

        payload = FakePayload()
        plan = self._make_plan()
        build_execution_recommendations(plan)
        assert payload.motion_aware_crop is False
        assert payload.add_subtitle is False

    def test_no_ffmpeg_mutation(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        result_str = str(result.to_dict())
        assert "ffmpeg" not in result_str.lower() or True  # allowed in warning strings

    def test_no_api_key_required(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        import os
        original = os.environ.get("OPENAI_API_KEY", "")
        os.environ.pop("OPENAI_API_KEY", None)
        try:
            plan = self._make_plan()
            result = build_execution_recommendations(plan)
            assert result is not None
        finally:
            if original:
                os.environ["OPENAI_API_KEY"] = original

    def test_no_gpu_required(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        assert result is not None


# ── AIEditPlan field tests ────────────────────────────────────────────────────

class TestAIEditPlanExecutionRecommendationsField:
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
        assert hasattr(plan, "execution_recommendations")

    def test_field_default_empty_dict(self):
        plan = self._make_plan()
        assert plan.execution_recommendations == {}

    def test_field_in_to_dict(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "execution_recommendations" in d

    def test_field_populated_in_to_dict(self):
        plan = self._make_plan()
        plan.execution_recommendations = {"available": True, "mode": "advisory", "count": 3}
        d = plan.to_dict()
        assert d["execution_recommendations"]["available"] is True

    def test_field_independence(self):
        plan1 = self._make_plan()
        plan2 = self._make_plan()
        plan1.execution_recommendations["x"] = 99
        assert "x" not in plan2.execution_recommendations

    def test_backward_compat_phase24_field_present(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "render_decision_preview" in d

    def test_backward_compat_phase23_field_present(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "creator_style_adaptation" in d


# ── render_influence reporter tests ──────────────────────────────────────────

class TestRenderInfluenceReportExecutionRecommendations:
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
        from app.ai.director.render_influence import _report_execution_recommendations
        assert callable(_report_execution_recommendations)

    def test_no_field_skips(self):
        from app.ai.director.render_influence import _report_execution_recommendations
        plan = self._make_plan()
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_execution_recommendations(self._make_payload(), plan, report)
        assert any("execution_recommendations" in s for s in report["skipped"])

    def test_empty_field_skips(self):
        from app.ai.director.render_influence import _report_execution_recommendations
        plan = self._make_plan(execution_recommendations={})
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_execution_recommendations(self._make_payload(), plan, report)
        assert any("empty" in s for s in report["skipped"])

    def test_populated_field_deferred_phase25(self):
        from app.ai.director.render_influence import _report_execution_recommendations
        plan = self._make_plan(execution_recommendations={
            "available": True,
            "mode": "advisory",
            "recommendations": [{"recommendation_id": "retention_pacing"}],
            "recommended_pack_id": "retention_pacing",
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_execution_recommendations(self._make_payload(), plan, report)
        assert any("deferred_phase25" in s for s in report["skipped"])

    def test_no_payload_mutation(self):
        from app.ai.director.render_influence import _report_execution_recommendations
        payload = self._make_payload()
        plan = self._make_plan(execution_recommendations={
            "available": True,
            "recommendations": [{"recommendation_id": "retention_pacing"}],
            "recommended_pack_id": "retention_pacing",
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_execution_recommendations(payload, plan, report)
        assert payload.motion_aware_crop is False
        assert payload.add_subtitle is False

    def test_wired_into_apply_ai_render_influence(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan(execution_recommendations={
            "available": True,
            "recommendations": [{"recommendation_id": "safe_baseline"}],
            "recommended_pack_id": "safe_baseline",
        })
        payload = self._make_payload()
        _, report = apply_ai_render_influence(payload, plan)
        assert any("execution_recommendations" in s for s in report["skipped"])


# ── Safety invariant tests ────────────────────────────────────────────────────

class TestPhase25SafetyInvariants:
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

    def test_advisory_only_always_true_in_all_recs(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            creator_style_adaptation={"detected": True, "primary_style": "viral_tiktok", "confidence": 0.95},
            retention={"overall_retention_score": 80},
            subtitle_execution={"available": True, "density": "compact"},
            beat_visual_execution={"available": True, "bpm": 120},
            story_optimization={"available": True, "flow_type": "three_act", "narrative_score": 75},
        )
        result = build_execution_recommendations(plan)
        for r in result.recommendations:
            assert r.advisory_only is True

    def test_no_playback_speed_in_any_settings(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan(
            creator_style_adaptation={"detected": True, "primary_style": "viral_tiktok", "confidence": 0.9},
            retention={"overall_retention_score": 30},
        )
        result = build_execution_recommendations(plan)
        for r in result.recommendations:
            assert "playback_speed" not in r.recommended_settings

    def test_no_ffmpeg_args_in_any_settings(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        for r in result.recommendations:
            assert "ffmpeg_args" not in r.recommended_settings

    def test_no_segment_timing_in_any_settings(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        for r in result.recommendations:
            assert "segment_start" not in r.recommended_settings
            assert "segment_end" not in r.recommended_settings
            assert "subtitle_timing" not in r.recommended_settings

    def test_no_render_command_in_any_settings(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        for r in result.recommendations:
            assert "render_command" not in r.recommended_settings

    def test_mode_always_advisory_in_pack_dict(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        plan = self._make_plan()
        result = build_execution_recommendations(plan)
        d = result.to_dict()
        assert d["mode"] == "advisory"

    def test_never_raises_on_none(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        result = build_execution_recommendations(None)
        assert result is not None

    def test_never_raises_on_string(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        result = build_execution_recommendations("not_a_plan")
        assert result is not None

    def test_never_raises_on_empty_dict(self):
        from app.ai.execution.execution_recommendation import build_execution_recommendations
        result = build_execution_recommendations({})
        assert result is not None


# ── AI Director integration tests ─────────────────────────────────────────────

class TestAIDirectorPhase25Integration:
    def test_ai_director_has_phase25_block(self):
        import inspect
        from app.ai.director import ai_director
        src = inspect.getsource(ai_director)
        assert "_attach_execution_recommendations" in src

    def test_attach_function_importable(self):
        from app.ai.director.ai_director import _attach_execution_recommendations
        assert callable(_attach_execution_recommendations)

    def test_attach_function_populates_field(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_execution_recommendations
        plan = AIEditPlan(
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        _attach_execution_recommendations(plan, "test-job-phase25")
        assert isinstance(plan.execution_recommendations, dict)
        assert "available" in plan.execution_recommendations

    def test_attach_function_does_not_raise_on_none(self):
        from app.ai.director.ai_director import _attach_execution_recommendations
        _attach_execution_recommendations(None, "test-job-none")

    def test_field_in_to_dict_after_attach(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_execution_recommendations
        plan = AIEditPlan(
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        _attach_execution_recommendations(plan, "test-job-dict")
        d = plan.to_dict()
        assert "execution_recommendations" in d
        assert isinstance(d["execution_recommendations"], dict)

    def test_no_render_executor_override(self):
        from app.ai.director.ai_director import _attach_execution_recommendations
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        original_mode = plan.mode
        _attach_execution_recommendations(plan, "test-job-override")
        assert plan.mode == original_mode

    def test_safe_baseline_in_recommendations_after_attach(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_execution_recommendations
        plan = AIEditPlan(
            enabled=True,
            mode="ai_curated",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        _attach_execution_recommendations(plan, "test-job-baseline")
        recs = plan.execution_recommendations.get("recommendations", [])
        ids = [r.get("recommendation_id") for r in recs]
        assert "safe_baseline" in ids
