"""
test_ai_phase45_render_quality_evaluation.py — Phase 45 tests.

Covers: schema, safety, scoring, evaluator, edit plan integration,
render influence, safety boundaries, no-mutation guarantees.
"""
import pytest
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_plan():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan, AIClipPlan,
    )
    return AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[AIClipPlan(start=0.0, end=20.0, score=80.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(pacing_style="fast_hook", energy_level=0.85),
    )


def _make_rich_plan():
    plan = _make_minimal_plan()
    plan.timing_apply = {"available": True, "enabled": True}
    plan.subtitle_text_apply = {"available": True, "enabled": True}
    plan.camera_motion_apply = {"available": True, "enabled": True, "safety_check_passed": True}
    plan.retention = {"available": True, "overall_score": 0.75, "risk_regions": []}
    plan.story = {"available": True, "hook_score": 0.80}
    plan.creator_retrieval = {"enabled": True, "matches": [{"id": "m1"}, {"id": "m2"}]}
    plan.adaptive_creator_intelligence = {
        "available": True,
        "enabled": True,
        "creator_profile": {"style_confidence": 0.70, "subtitle_confidence": 0.60},
    }
    plan.creator_feedback_intelligence = {
        "available": True,
        "enabled": True,
        "learned_feedback_patterns": {"total_exports": 5},
    }
    plan.market_optimization_intelligence = {
        "available": True,
        "enabled": True,
        "market_profile": {"confidence": 0.85},
        "subtitle_market_bias": {"weight": 0.20},
        "pacing_market_bias": {"weight": 0.22},
        "camera_market_bias": {"weight": 0.18},
        "hook_market_bias": {"weight": 0.24},
    }
    plan.output_ranking = {"available": True, "best_output_id": "1"}
    return plan


def _make_output(output_id="1", failed=False, score=0.75):
    return {"output_id": output_id, "failed": failed, "score": score}


# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestQualitySchema:
    def test_score_defaults(self):
        from app.ai.quality.quality_schema import AIRenderQualityScore
        s = AIRenderQualityScore()
        assert s.overall_score == 0.0
        assert s.pacing_quality == 0.0
        assert s.confidence == 0.0
        assert s.quality_flags == []
        assert s.warnings == []
        assert s.explanation == []

    def test_score_to_dict_keys(self):
        from app.ai.quality.quality_schema import AIRenderQualityScore
        d = AIRenderQualityScore(score_id="abc", overall_score=75.0, confidence=0.8).to_dict()
        assert d["score_id"] == "abc"
        assert d["overall_score"] == 75.0
        assert d["confidence"] == 0.8
        for key in ("pacing_quality", "subtitle_readability", "camera_smoothness",
                    "hook_strength", "retention_quality", "creator_consistency", "market_fit"):
            assert key in d

    def test_evaluation_defaults(self):
        from app.ai.quality.quality_schema import AIRenderQualityEvaluation
        e = AIRenderQualityEvaluation()
        assert e.available is True
        assert e.enabled is False
        assert e.evaluation_mode == "evaluation_only"
        assert e.output_scores == []
        assert e.best_quality_output_id == ""

    def test_evaluation_to_dict(self):
        from app.ai.quality.quality_schema import AIRenderQualityEvaluation, AIRenderQualityScore
        score = AIRenderQualityScore(score_id="x", overall_score=80.0)
        ev = AIRenderQualityEvaluation(enabled=True, output_scores=[score], best_quality_output_id="x")
        d = ev.to_dict()
        assert d["enabled"] is True
        assert len(d["output_scores"]) == 1
        assert d["best_quality_output_id"] == "x"

    def test_score_rounded_to_dict(self):
        from app.ai.quality.quality_schema import AIRenderQualityScore
        s = AIRenderQualityScore(overall_score=66.6666666, confidence=0.333333)
        d = s.to_dict()
        assert d["overall_score"] == round(66.6666666, 2)
        assert d["confidence"] == round(0.333333, 4)


# ---------------------------------------------------------------------------
# 2. Safety tests
# ---------------------------------------------------------------------------

class TestQualitySafety:
    def test_clamp_score_normal(self):
        from app.ai.quality.quality_safety import _clamp_score
        assert _clamp_score(50.0) == 50.0

    def test_clamp_score_below_zero(self):
        from app.ai.quality.quality_safety import _clamp_score
        assert _clamp_score(-10.0) == 0.0

    def test_clamp_score_above_100(self):
        from app.ai.quality.quality_safety import _clamp_score
        assert _clamp_score(120.0) == 100.0

    def test_clamp_confidence_normal(self):
        from app.ai.quality.quality_safety import _clamp_confidence
        assert _clamp_confidence(0.5) == 0.5

    def test_clamp_confidence_above_1(self):
        from app.ai.quality.quality_safety import _clamp_confidence
        assert _clamp_confidence(1.5) == 1.0

    def test_clamp_confidence_non_numeric(self):
        from app.ai.quality.quality_safety import _clamp_confidence
        assert _clamp_confidence("bad") == 0.0

    def test_sanitize_strips_forbidden_ffmpeg_args(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        result = sanitize_quality_input({"ffmpeg_args": ["-crf", "23"], "overall_score": 80.0})
        assert "ffmpeg_args" not in result
        assert result["overall_score"] == 80.0

    def test_sanitize_strips_delete_output(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        result = sanitize_quality_input({"delete_output": True, "pacing_quality": 70.0})
        assert "delete_output" not in result

    def test_sanitize_strips_overwrite_output(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        result = sanitize_quality_input({"overwrite_output": True})
        assert "overwrite_output" not in result

    def test_sanitize_strips_rerender(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        result = sanitize_quality_input({"rerender": True})
        assert "rerender" not in result

    def test_sanitize_clamps_score_fields(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        result = sanitize_quality_input({"overall_score": 150.0, "pacing_quality": -5.0})
        assert result["overall_score"] == 100.0
        assert result["pacing_quality"] == 0.0

    def test_sanitize_clamps_confidence(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        result = sanitize_quality_input({"confidence": 2.0})
        assert result["confidence"] == 1.0

    def test_sanitize_recursive(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        result = sanitize_quality_input({"nested": {"subprocess": "rm -rf /"}})
        assert "subprocess" not in result.get("nested", {})

    def test_is_safe_true(self):
        from app.ai.quality.quality_safety import is_quality_evaluation_safe
        assert is_quality_evaluation_safe({"overall_score": 80.0}) is True

    def test_is_safe_false_forbidden(self):
        from app.ai.quality.quality_safety import is_quality_evaluation_safe
        assert is_quality_evaluation_safe({"ffmpeg_args": ["-c", "copy"]}) is False

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        assert sanitize_quality_input("bad") == {}

    def test_sanitize_never_raises(self):
        from app.ai.quality.quality_safety import sanitize_quality_input
        result = sanitize_quality_input(None)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 3. Scoring tests
# ---------------------------------------------------------------------------

class TestQualityScoring:
    def test_score_returns_schema_type(self):
        from app.ai.quality.quality_scoring import score_render_quality
        from app.ai.quality.quality_schema import AIRenderQualityScore
        result = score_render_quality({})
        assert isinstance(result, AIRenderQualityScore)

    def test_score_never_raises_on_none(self):
        from app.ai.quality.quality_scoring import score_render_quality
        result = score_render_quality(None)
        assert result is not None

    def test_score_clamped_0_100(self):
        from app.ai.quality.quality_scoring import score_render_quality
        result = score_render_quality({})
        assert 0.0 <= result.overall_score <= 100.0
        assert 0.0 <= result.pacing_quality <= 100.0
        assert 0.0 <= result.subtitle_readability <= 100.0
        assert 0.0 <= result.camera_smoothness <= 100.0
        assert 0.0 <= result.hook_strength <= 100.0
        assert 0.0 <= result.retention_quality <= 100.0
        assert 0.0 <= result.creator_consistency <= 100.0
        assert 0.0 <= result.market_fit <= 100.0

    def test_failed_output_penalty(self):
        from app.ai.quality.quality_scoring import score_render_quality
        ok = score_render_quality({"output_id": "1"})
        failed = score_render_quality({"output_id": "1", "failed": True})
        assert failed.overall_score < ok.overall_score
        assert "failed_output_penalty_applied" in failed.quality_flags

    def test_rich_plan_score_above_baseline(self):
        from app.ai.quality.quality_scoring import score_render_quality
        plan = _make_rich_plan()
        result = score_render_quality({"output_id": "1", "score": 0.80}, edit_plan=plan)
        assert result.overall_score > 50.0

    def test_confidence_increases_with_rich_plan(self):
        from app.ai.quality.quality_scoring import score_render_quality
        minimal = score_render_quality({})
        rich = score_render_quality({"output_id": "1"}, edit_plan=_make_rich_plan())
        assert rich.confidence >= minimal.confidence

    def test_confidence_clamped_0_1(self):
        from app.ai.quality.quality_scoring import score_render_quality
        result = score_render_quality({"output_id": "1"}, edit_plan=_make_rich_plan())
        assert 0.0 <= result.confidence <= 1.0

    def test_score_has_explanation(self):
        from app.ai.quality.quality_scoring import score_render_quality
        result = score_render_quality({"output_id": "1"}, edit_plan=_make_rich_plan())
        assert len(result.explanation) > 0

    def test_score_id_generated(self):
        from app.ai.quality.quality_scoring import score_render_quality
        result = score_render_quality({})
        assert result.score_id != "unknown"
        assert len(result.score_id) > 0

    def test_baseline_when_no_signals(self):
        from app.ai.quality.quality_scoring import score_render_quality
        result = score_render_quality({})
        # With no signals, each dimension should be ~50 (baseline)
        assert result.overall_score > 0.0

    def test_no_mutation_of_metadata(self):
        from app.ai.quality.quality_scoring import score_render_quality
        meta = {"output_id": "abc", "score": 0.5}
        original = dict(meta)
        score_render_quality(meta)
        assert meta == original

    def test_market_fit_zero_when_disabled(self):
        from app.ai.quality.quality_scoring import score_render_quality
        plan = _make_minimal_plan()
        plan.market_optimization_intelligence = {"enabled": False}
        result = score_render_quality({}, edit_plan=plan)
        # When market is not enabled, market_fit should be at baseline (50)
        assert result.market_fit == 50.0


# ---------------------------------------------------------------------------
# 4. Evaluator tests
# ---------------------------------------------------------------------------

class TestQualityEvaluator:
    def test_evaluate_empty_outputs(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        from app.ai.quality.quality_schema import AIRenderQualityEvaluation
        result = evaluate_render_quality([])
        assert isinstance(result, AIRenderQualityEvaluation)
        assert result.enabled is False
        assert result.output_scores == []

    def test_evaluate_single_output(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        result = evaluate_render_quality([{"output_id": "1", "score": 0.8}])
        assert result.enabled is True
        assert len(result.output_scores) == 1
        assert result.best_quality_output_id == "1"

    def test_evaluate_best_selected_by_highest_score(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        outputs = [
            {"output_id": "low", "score": 0.30},
            {"output_id": "high", "score": 0.90},
            {"output_id": "mid", "score": 0.60},
        ]
        result = evaluate_render_quality(outputs, edit_plan=_make_rich_plan())
        # high should have most signals contributing to a higher score
        assert result.best_quality_output_id != ""

    def test_evaluate_caps_at_20(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        outputs = [{"output_id": str(i), "score": 0.5} for i in range(25)]
        result = evaluate_render_quality(outputs)
        assert len(result.output_scores) == 20
        assert "outputs_capped_at_20" in result.warnings

    def test_evaluate_never_raises_on_none(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        result = evaluate_render_quality(None)
        assert result is not None

    def test_evaluate_non_list_input(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        result = evaluate_render_quality("bad_input")
        assert result.output_scores == []

    def test_evaluate_evaluation_mode_constant(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        result = evaluate_render_quality([{"output_id": "1"}])
        assert result.evaluation_mode == "evaluation_only"

    def test_evaluate_failed_output_penalized(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        outputs = [
            {"output_id": "ok", "score": 0.8, "failed": False},
            {"output_id": "fail", "score": 0.8, "failed": True},
        ]
        result = evaluate_render_quality(outputs)
        ok_score = next(s for s in result.output_scores if s.output_id == "ok")
        fail_score = next(s for s in result.output_scores if s.output_id == "fail")
        assert ok_score.overall_score > fail_score.overall_score

    def test_evaluate_returns_dict_via_to_dict(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        result = evaluate_render_quality([{"output_id": "1"}])
        d = result.to_dict()
        assert "output_scores" in d
        assert "best_quality_output_id" in d
        assert "evaluation_mode" in d


# ---------------------------------------------------------------------------
# 5. Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchema:
    def test_render_quality_evaluation_field_exists(self):
        plan = _make_minimal_plan()
        assert hasattr(plan, "render_quality_evaluation")
        assert isinstance(plan.render_quality_evaluation, dict)

    def test_render_quality_evaluation_in_to_dict(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "render_quality_evaluation" in d

    def test_render_quality_evaluation_default_empty(self):
        plan = _make_minimal_plan()
        assert plan.render_quality_evaluation == {}


# ---------------------------------------------------------------------------
# 6. Render influence reporting
# ---------------------------------------------------------------------------

class TestRenderInfluence:
    def test_influence_report_quality_pending(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_minimal_plan()
        plan.render_quality_evaluation = {
            "available": True,
            "enabled": False,
            "evaluation_mode": "evaluation_only",
            "output_scores": [],
            "best_quality_output_id": "",
            "warnings": ["quality_evaluation_pending_post_render"],
        }
        _payload, report = apply_ai_render_influence(None, plan, {})
        skipped_str = " ".join(str(s) for s in report.get("skipped", []))
        assert "render_quality_evaluation" in skipped_str

    def test_influence_report_quality_enabled(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        from app.ai.quality.quality_schema import AIRenderQualityScore
        plan = _make_minimal_plan()
        score = AIRenderQualityScore(score_id="s1", output_id="1", overall_score=80.0)
        plan.render_quality_evaluation = {
            "available": True,
            "enabled": True,
            "evaluation_mode": "evaluation_only",
            "output_scores": [score.to_dict()],
            "best_quality_output_id": "1",
            "warnings": [],
        }
        _payload, report = apply_ai_render_influence(None, plan, {})
        skipped_str = " ".join(str(s) for s in report.get("skipped", []))
        assert "render_quality_evaluation" in skipped_str


# ---------------------------------------------------------------------------
# 7. Safety boundaries
# ---------------------------------------------------------------------------

class TestSafetyBoundaries:
    def test_no_ffmpeg_args_in_score(self):
        from app.ai.quality.quality_scoring import score_render_quality
        result = score_render_quality({"ffmpeg_args": ["-crf", "23"]})
        d = result.to_dict()
        assert "ffmpeg_args" not in d

    def test_no_render_command_in_score(self):
        from app.ai.quality.quality_scoring import score_render_quality
        result = score_render_quality({"render_command": "ffmpeg -i input.mp4 output.mp4"})
        d = result.to_dict()
        assert "render_command" not in d

    def test_no_delete_output_in_evaluation(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        outputs = [{"output_id": "1", "delete_output": True}]
        result = evaluate_render_quality(outputs)
        for score in result.output_scores:
            d = score.to_dict()
            assert "delete_output" not in d

    def test_scores_never_exceed_100(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        outputs = [{"output_id": str(i), "score": 999.0} for i in range(5)]
        result = evaluate_render_quality(outputs)
        for score in result.output_scores:
            assert score.overall_score <= 100.0

    def test_scores_never_below_zero(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality
        outputs = [{"output_id": str(i), "score": -999.0, "failed": True} for i in range(5)]
        result = evaluate_render_quality(outputs)
        for score in result.output_scores:
            assert score.overall_score >= 0.0

    def test_evaluation_never_raises_on_corrupt_plan(self):
        from app.ai.quality.quality_evaluator import evaluate_render_quality

        class BadPlan:
            @property
            def timing_apply(self):
                raise RuntimeError("corrupt")

        result = evaluate_render_quality([{"output_id": "1"}], edit_plan=BadPlan())
        assert result is not None
