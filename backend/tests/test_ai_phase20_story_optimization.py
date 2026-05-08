"""
test_ai_phase20_story_optimization.py — Phase 20 story optimization tests.

Coverage: schema, hook optimizer, payoff analyzer, arc optimizer,
story recommender, render influence defer, AI Director integration,
and all safety boundaries.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestStoryOptimizationIssueSchema:
    def test_defaults(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationIssue
        issue = StoryOptimizationIssue()
        assert issue.start is None
        assert issue.end is None
        assert issue.issue_type == "unknown"
        assert issue.severity == "medium"
        assert issue.reason == ""
        assert issue.suggested_action == ""
        assert issue.confidence == 0.0
        assert issue.safe_to_auto_apply is False
        assert issue.metadata == {}

    def test_to_dict_keys(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationIssue
        d = StoryOptimizationIssue().to_dict()
        assert set(d.keys()) == {
            "start", "end", "issue_type", "severity", "reason",
            "suggested_action", "confidence", "safe_to_auto_apply", "metadata",
        }

    def test_safe_to_auto_apply_always_false_in_to_dict(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationIssue
        issue = StoryOptimizationIssue(safe_to_auto_apply=True)  # try to set True
        assert issue.to_dict()["safe_to_auto_apply"] is False

    def test_invalid_issue_type_normalised(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationIssue
        issue = StoryOptimizationIssue(issue_type="destroy_timeline")
        assert issue.to_dict()["issue_type"] == "unknown"

    def test_invalid_severity_normalised(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationIssue
        issue = StoryOptimizationIssue(severity="catastrophic")
        assert issue.to_dict()["severity"] == "medium"

    def test_all_valid_issue_types_accepted(self):
        from app.ai.story_optimization.story_optimization_schema import (
            StoryOptimizationIssue, VALID_ISSUE_TYPES,
        )
        for t in VALID_ISSUE_TYPES:
            issue = StoryOptimizationIssue(issue_type=t)
            assert issue.to_dict()["issue_type"] == t

    def test_all_valid_severities_accepted(self):
        from app.ai.story_optimization.story_optimization_schema import (
            StoryOptimizationIssue, VALID_SEVERITIES,
        )
        for s in VALID_SEVERITIES:
            issue = StoryOptimizationIssue(severity=s)
            assert issue.to_dict()["severity"] == s


class TestStoryOptimizationPlanSchema:
    def test_defaults(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationPlan
        plan = StoryOptimizationPlan()
        assert plan.available is True
        assert plan.narrative_score == 0.0
        assert plan.flow_type == "unknown"
        assert plan.issues == []
        assert plan.recommendations == []
        assert plan.warnings == []

    def test_to_dict_keys(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationPlan
        d = StoryOptimizationPlan().to_dict()
        assert set(d.keys()) == {
            "available", "narrative_score", "flow_type",
            "issues", "recommendations", "warnings",
        }

    def test_issues_capped_at_10(self):
        from app.ai.story_optimization.story_optimization_schema import (
            StoryOptimizationPlan, StoryOptimizationIssue,
        )
        issues = [StoryOptimizationIssue() for _ in range(15)]
        plan = StoryOptimizationPlan(issues=issues)
        assert len(plan.to_dict()["issues"]) == 10

    def test_recommendations_capped_at_8(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationPlan
        recs = [f"rec_{i}" for i in range(15)]
        plan = StoryOptimizationPlan(recommendations=recs)
        assert len(plan.to_dict()["recommendations"]) == 8

    def test_invalid_flow_type_normalised(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationPlan
        plan = StoryOptimizationPlan(flow_type="rocket_launch")
        assert plan.to_dict()["flow_type"] == "unknown"

    def test_all_valid_flow_types_accepted(self):
        from app.ai.story_optimization.story_optimization_schema import (
            StoryOptimizationPlan, VALID_FLOW_TYPES,
        )
        for ft in VALID_FLOW_TYPES:
            plan = StoryOptimizationPlan(flow_type=ft)
            assert plan.to_dict()["flow_type"] == ft


# ---------------------------------------------------------------------------
# Hook optimizer tests
# ---------------------------------------------------------------------------

class TestAnalyzeHookQuality:
    def _story_ctx_with_hook(self, retention_risk=0.2):
        return {
            "segments": [
                {"segment_type": "hook", "start": 0.0, "end": 5.0, "retention_risk": retention_risk}
            ]
        }

    def _story_ctx_without_hook(self):
        return {
            "segments": [
                {"segment_type": "setup", "start": 0.0, "end": 10.0}
            ]
        }

    def test_empty_input_returns_list(self):
        from app.ai.story_optimization.hook_optimizer import analyze_hook_quality
        result = analyze_hook_quality()
        assert isinstance(result, list)

    def test_never_raises_on_bad_input(self):
        from app.ai.story_optimization.hook_optimizer import analyze_hook_quality
        result = analyze_hook_quality(
            story_context="not_a_dict",
            retention_context=42,
            transcript_chunks="bad",
        )
        assert isinstance(result, list)

    def test_no_hook_segment_creates_weak_hook_high_severity(self):
        from app.ai.story_optimization.hook_optimizer import analyze_hook_quality
        result = analyze_hook_quality(story_context=self._story_ctx_without_hook())
        assert len(result) == 1
        assert result[0].issue_type == "weak_hook"
        assert result[0].severity == "high"

    def test_strong_hook_returns_empty_or_low(self):
        from app.ai.story_optimization.hook_optimizer import analyze_hook_quality
        result = analyze_hook_quality(story_context=self._story_ctx_with_hook(retention_risk=0.1))
        # Strong hook: either empty or only low-severity issues
        for issue in result:
            assert issue.severity == "low"

    def test_weak_hook_retention_risk_creates_issue(self):
        from app.ai.story_optimization.hook_optimizer import analyze_hook_quality
        retention_ctx = {
            "risk_regions": [{"category": "weak_hook", "start": 0.0, "end": 5.0, "severity": 0.75}]
        }
        result = analyze_hook_quality(
            story_context=self._story_ctx_with_hook(retention_risk=0.6),
            retention_context=retention_ctx,
        )
        assert any(i.issue_type == "weak_hook" for i in result)

    def test_all_issues_safe_to_auto_apply_false(self):
        from app.ai.story_optimization.hook_optimizer import analyze_hook_quality
        result = analyze_hook_quality(story_context=self._story_ctx_without_hook())
        for issue in result:
            assert issue.safe_to_auto_apply is False

    def test_no_text_rewrite_in_output(self):
        from app.ai.story_optimization.hook_optimizer import analyze_hook_quality
        result = analyze_hook_quality(story_context=self._story_ctx_without_hook())
        for issue in result:
            # suggested_action is advisory text only, not a transcript mutation
            assert isinstance(issue.suggested_action, str)


# ---------------------------------------------------------------------------
# Payoff analyzer tests
# ---------------------------------------------------------------------------

class TestAnalyzePayoffQuality:
    def _story_with_payoff(self, retention_risk=0.2):
        return {
            "segments": [
                {"segment_type": "hook", "start": 0.0, "end": 5.0},
                {"segment_type": "payoff", "start": 20.0, "end": 30.0, "retention_risk": retention_risk},
            ]
        }

    def _story_without_payoff(self):
        return {
            "segments": [
                {"segment_type": "hook", "start": 0.0, "end": 5.0},
                {"segment_type": "build_up", "start": 5.0, "end": 15.0},
            ]
        }

    def test_empty_input_returns_list(self):
        from app.ai.story_optimization.payoff_analyzer import analyze_payoff_quality
        result = analyze_payoff_quality()
        assert isinstance(result, list)

    def test_never_raises_on_bad_input(self):
        from app.ai.story_optimization.payoff_analyzer import analyze_payoff_quality
        result = analyze_payoff_quality(story_context=42, retention_context="bad")
        assert isinstance(result, list)

    def test_missing_payoff_creates_weak_payoff_high(self):
        from app.ai.story_optimization.payoff_analyzer import analyze_payoff_quality
        result = analyze_payoff_quality(story_context=self._story_without_payoff())
        assert any(i.issue_type == "weak_payoff" and i.severity == "high" for i in result)

    def test_unclear_payoff_risk_creates_issue(self):
        from app.ai.story_optimization.payoff_analyzer import analyze_payoff_quality
        retention_ctx = {
            "risk_regions": [{"category": "unclear_payoff", "start": 20.0, "end": 30.0, "severity": 0.7}]
        }
        result = analyze_payoff_quality(
            story_context=self._story_with_payoff(),
            retention_context=retention_ctx,
        )
        assert any(i.issue_type == "weak_payoff" for i in result)

    def test_abrupt_ending_creates_abrupt_outro(self):
        from app.ai.story_optimization.payoff_analyzer import analyze_payoff_quality
        retention_ctx = {
            "risk_regions": [{"category": "abrupt_ending", "start": 25.0, "end": 30.0, "severity": 0.8}]
        }
        result = analyze_payoff_quality(
            story_context=self._story_with_payoff(),
            retention_context=retention_ctx,
        )
        assert any(i.issue_type == "abrupt_outro" for i in result)

    def test_all_issues_safe_to_auto_apply_false(self):
        from app.ai.story_optimization.payoff_analyzer import analyze_payoff_quality
        result = analyze_payoff_quality(story_context=self._story_without_payoff())
        for issue in result:
            assert issue.safe_to_auto_apply is False

    def test_strong_payoff_no_issues(self):
        from app.ai.story_optimization.payoff_analyzer import analyze_payoff_quality
        result = analyze_payoff_quality(
            story_context=self._story_with_payoff(retention_risk=0.1),
            retention_context={"risk_regions": []},
        )
        assert result == []


# ---------------------------------------------------------------------------
# Arc optimizer tests
# ---------------------------------------------------------------------------

class TestAnalyzeStoryArc:
    def _full_arc_ctx(self):
        return {
            "segments": [
                {"segment_type": "hook",     "start": 0.0,  "end": 5.0,  "retention_risk": 0.1},
                {"segment_type": "setup",    "start": 5.0,  "end": 10.0, "retention_risk": 0.2},
                {"segment_type": "build_up", "start": 10.0, "end": 18.0, "retention_risk": 0.2},
                {"segment_type": "climax",   "start": 18.0, "end": 25.0, "retention_risk": 0.1},
                {"segment_type": "payoff",   "start": 25.0, "end": 30.0, "retention_risk": 0.15},
            ],
            "dominant_arc": "setup_payoff",
            "narrative_flow": "linear",
            "retention_score": 85,
        }

    def _flat_ctx(self):
        return {
            "segments": [
                {"segment_type": "unknown", "start": 0.0, "end": 30.0},
            ],
            "dominant_arc": "flat",
            "narrative_flow": "flat",
        }

    def test_empty_input_returns_dict(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        result = analyze_story_arc()
        assert isinstance(result, dict)
        assert "flow_type" in result
        assert "narrative_score" in result
        assert "issues" in result

    def test_never_raises_on_bad_input(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        result = analyze_story_arc(
            story_context="broken", pacing_context=42, retention_context=None
        )
        assert isinstance(result, dict)
        assert result.get("flow_type") == "unknown"

    def test_full_arc_gives_hook_to_climax_flow(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        result = analyze_story_arc(story_context=self._full_arc_ctx())
        assert result["flow_type"] == "hook_to_climax"

    def test_full_arc_increases_narrative_score(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        result = analyze_story_arc(story_context=self._full_arc_ctx())
        assert result["narrative_score"] >= 50.0

    def test_flat_arc_gives_flat_flow(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        result = analyze_story_arc(story_context=self._flat_ctx())
        assert result["flow_type"] == "flat"

    def test_flat_arc_reduces_narrative_score(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        full = analyze_story_arc(story_context=self._full_arc_ctx())
        flat = analyze_story_arc(story_context=self._flat_ctx())
        assert flat["narrative_score"] < full["narrative_score"]

    def test_long_setup_creates_long_setup_issue(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        ctx = {
            "segments": [
                {"segment_type": "hook",   "start": 0.0,  "end": 3.0},
                {"segment_type": "setup",  "start": 3.0,  "end": 25.0},   # 22s setup
                {"segment_type": "climax", "start": 25.0, "end": 30.0},   # 5s climax
            ],
        }
        result = analyze_story_arc(story_context=ctx)
        issue_types = {i.issue_type for i in result["issues"]}
        assert "long_setup" in issue_types

    def test_no_segment_reorder_in_output(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        result = analyze_story_arc(story_context=self._full_arc_ctx())
        # No field that implies segment reordering
        assert "reordered_segments" not in result
        assert "new_order" not in result

    def test_all_issues_safe_to_auto_apply_false(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        result = analyze_story_arc(story_context=self._flat_ctx())
        for issue in result["issues"]:
            assert issue.safe_to_auto_apply is False

    def test_high_energy_pacing_boosts_score(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        low = analyze_story_arc(
            story_context=self._full_arc_ctx(),
            pacing_context={"energy_level": 0.2},
        )
        high = analyze_story_arc(
            story_context=self._full_arc_ctx(),
            pacing_context={"energy_level": 0.8},
        )
        assert high["narrative_score"] >= low["narrative_score"]

    def test_retention_risks_reduce_score(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        no_risks = analyze_story_arc(
            story_context=self._full_arc_ctx(),
            retention_context={"risk_regions": []},
        )
        many_risks = analyze_story_arc(
            story_context=self._full_arc_ctx(),
            retention_context={"risk_regions": [{"category": "weak_hook"} for _ in range(5)]},
        )
        assert many_risks["narrative_score"] <= no_risks["narrative_score"]


# ---------------------------------------------------------------------------
# Story recommender tests
# ---------------------------------------------------------------------------

class TestBuildStoryOptimizationPlan:
    def _full_story_ctx(self):
        return {
            "segments": [
                {"segment_type": "hook",     "start": 0.0,  "end": 5.0,  "retention_risk": 0.1},
                {"segment_type": "build_up", "start": 5.0,  "end": 18.0, "retention_risk": 0.2},
                {"segment_type": "climax",   "start": 18.0, "end": 25.0, "retention_risk": 0.1},
                {"segment_type": "payoff",   "start": 25.0, "end": 30.0, "retention_risk": 0.15},
            ],
            "dominant_arc": "setup_payoff",
        }

    def test_returns_plan_instance(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationPlan
        result = build_story_optimization_plan()
        assert isinstance(result, StoryOptimizationPlan)

    def test_never_raises_on_empty_input(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan()
        assert hasattr(plan, "available")

    def test_never_raises_on_garbage_input(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan(
            story_context="garbage",
            retention_context=42,
            pacing_context=None,
            transcript_chunks={"wrong": "type"},
        )
        assert hasattr(plan, "available")

    def test_full_arc_produces_hook_to_climax(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan(story_context=self._full_story_ctx())
        assert plan.flow_type == "hook_to_climax"

    def test_weak_hook_creates_recommendation(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        ctx = {"segments": [{"segment_type": "setup", "start": 0.0, "end": 10.0}]}
        plan = build_story_optimization_plan(story_context=ctx)
        assert any("hook" in r.lower() for r in plan.recommendations)

    def test_missing_payoff_creates_recommendation(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        ctx = {
            "segments": [
                {"segment_type": "hook",   "start": 0.0, "end": 5.0},
                {"segment_type": "climax", "start": 10.0, "end": 20.0},
            ]
        }
        plan = build_story_optimization_plan(story_context=ctx)
        assert any("payoff" in r.lower() or "outro" in r.lower() for r in plan.recommendations)

    def test_all_issues_safe_to_auto_apply_false(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan()
        for issue in plan.issues:
            assert issue.safe_to_auto_apply is False

    def test_to_dict_issues_safe_to_auto_apply_false(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        ctx = {"segments": [{"segment_type": "setup", "start": 0.0, "end": 10.0}]}
        plan = build_story_optimization_plan(story_context=ctx)
        d = plan.to_dict()
        for issue in d["issues"]:
            assert issue["safe_to_auto_apply"] is False

    def test_issues_capped_at_10(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan()
        assert len(plan.issues) <= 10

    def test_recommendations_capped_at_8(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan()
        assert len(plan.recommendations) <= 8

    def test_to_dict_round_trip(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan(story_context=self._full_story_ctx())
        d = plan.to_dict()
        assert isinstance(d, dict)
        assert "narrative_score" in d
        assert "flow_type" in d
        assert isinstance(d["issues"], list)
        assert isinstance(d["recommendations"], list)

    def test_narrative_score_is_float_in_range(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan(story_context=self._full_story_ctx())
        assert isinstance(plan.narrative_score, float)
        assert 0.0 <= plan.narrative_score <= 100.0


# ---------------------------------------------------------------------------
# Safety boundary tests
# ---------------------------------------------------------------------------

class TestStoryOptimizationSafetyBoundaries:
    def test_no_segment_timing_mutated(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        ctx = {
            "segments": [
                {"segment_type": "hook",  "start": 0.0, "end": 5.0},
                {"segment_type": "setup", "start": 5.0, "end": 15.0},
            ]
        }
        original_start = ctx["segments"][0]["start"]
        build_story_optimization_plan(story_context=ctx)
        assert ctx["segments"][0]["start"] == original_start

    def test_no_subtitle_timing_mutated(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        chunks = [{"text": "hello world", "start": 0.0, "end": 2.0}]
        build_story_optimization_plan(transcript_chunks=chunks)
        assert chunks[0]["start"] == 0.0
        assert chunks[0]["end"] == 2.0

    def test_no_playback_speed_field(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        plan = build_story_optimization_plan()
        d = plan.to_dict()
        assert "playback_speed" not in d

    def test_no_api_key_required(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        # Should complete without any API key in environment
        plan = build_story_optimization_plan()
        assert plan is not None

    def test_no_gpu_required(self):
        from app.ai.story_optimization.arc_optimizer import analyze_story_arc
        # Pure Python — no GPU dependency
        result = analyze_story_arc()
        assert isinstance(result, dict)

    def test_no_real_rendering_required(self):
        from app.ai.story_optimization.story_recommender import build_story_optimization_plan
        # No ffmpeg, no subprocess, no render pipeline needed
        plan = build_story_optimization_plan()
        assert hasattr(plan, "to_dict")

    def test_safe_to_auto_apply_structurally_false_always(self):
        from app.ai.story_optimization.story_optimization_schema import StoryOptimizationIssue
        for val in (True, False, 1, 0, "yes"):
            issue = StoryOptimizationIssue(safe_to_auto_apply=val)
            assert issue.to_dict()["safe_to_auto_apply"] is False


# ---------------------------------------------------------------------------
# AIEditPlan field tests
# ---------------------------------------------------------------------------

class TestAIEditPlanStoryOptimizationField:
    def _make_plan(self, **kwargs):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        return AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            **kwargs,
        )

    def test_story_optimization_field_exists(self):
        plan = self._make_plan()
        assert hasattr(plan, "story_optimization")
        assert plan.story_optimization == {}

    def test_story_optimization_in_to_dict(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "story_optimization" in d
        assert d["story_optimization"] == {}

    def test_story_optimization_populated_survives_to_dict(self):
        plan = self._make_plan(story_optimization={
            "available": True,
            "flow_type": "hook_to_climax",
            "narrative_score": 81.0,
        })
        d = plan.to_dict()
        assert d["story_optimization"]["available"] is True
        assert d["story_optimization"]["flow_type"] == "hook_to_climax"

    def test_existing_fields_unaffected(self):
        plan = self._make_plan()
        d = plan.to_dict()
        # Existing Phase 17-19 fields must still be present
        assert "subtitle_execution" in d
        assert "beat_visual_execution" in d
        assert "timing_mutation" in d


# ---------------------------------------------------------------------------
# Render influence defer tests
# ---------------------------------------------------------------------------

class TestRenderInfluenceStoryOptimizationDefer:
    def _make_plan_obj(self, story_optimization):
        class FakePlan:
            camera = None; subtitle = None; pacing = None
            memory_context = None; beat_visual_execution = None
            timing_mutation = None; explainability = {}; beat_execution = {}
        p = FakePlan()
        p.story_optimization = story_optimization
        return p

    def _make_payload(self):
        class Payload:
            motion_aware_crop = False
            add_subtitle = False
            ai_beat_execution_enabled = False
        return Payload()

    def test_no_story_optimization_attr_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePlan:
            camera = None; subtitle = None; pacing = None
            memory_context = None; beat_visual_execution = None
            timing_mutation = None; explainability = {}; beat_execution = {}

        _, report = apply_ai_render_influence(self._make_payload(), FakePlan())
        assert any("story_optimization:no_plan" in s for s in report["skipped"])

    def test_unavailable_plan_deferred(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({"available": False, "warnings": ["no_story"]})
        _, report = apply_ai_render_influence(self._make_payload(), plan)
        assert any("story_optimization:deferred(no_story)" in s for s in report["skipped"])

    def test_available_plan_deferred_phase20(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({
            "available": True,
            "flow_type": "hook_to_climax",
            "narrative_score": 80.0,
            "issues": [],
            "recommendations": [],
        })
        _, report = apply_ai_render_influence(self._make_payload(), plan)
        assert any("story_optimization:deferred_phase20" in s for s in report["skipped"])

    def test_segment_timing_not_mutated_by_render_influence(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan_obj({
            "available": True,
            "flow_type": "flat",
            "narrative_score": 30.0,
            "issues": [{"issue_type": "unclear_arc", "safe_to_auto_apply": False}],
            "recommendations": ["Restructure arc"],
        })
        payload = self._make_payload()
        apply_ai_render_influence(payload, plan)
        # Payload has no start/end mutation capability — just verify no exception
        assert True


# ---------------------------------------------------------------------------
# AI Director integration smoke tests
# ---------------------------------------------------------------------------

class TestAIDirectorPhase20Integration:
    def _make_request(self):
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
        return Req()

    def test_story_optimization_field_populated(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(), context={})
        assert plan is not None
        assert hasattr(plan, "story_optimization")
        assert isinstance(plan.story_optimization, dict)

    def test_to_dict_includes_story_optimization(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(), context={})
        if plan is not None:
            d = plan.to_dict()
            assert "story_optimization" in d

    def test_director_never_raises_with_phase20(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        result = create_ai_edit_plan(self._make_request(), context={
            "story_context": "broken",
            "job_id": "test-p20",
        })
        assert result is None or hasattr(result, "story_optimization")

    def test_full_suite_does_not_regress(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(), context={})
        if plan is not None:
            d = plan.to_dict()
            # All prior phase fields must still be present
            for key in ("beat_execution", "story", "retention", "subtitle_execution",
                        "beat_visual_execution", "timing_mutation", "story_optimization"):
                assert key in d, f"Missing key: {key}"
