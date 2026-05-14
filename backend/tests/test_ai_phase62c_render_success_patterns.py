"""
test_ai_phase62c_render_success_patterns.py

Phase 62C — Success Pattern Mining
Tests all gate conditions, success score formula, evidence count,
conflict detection, pattern classification, signal extraction,
camera style descriptor, pattern ID, confidence calculation,
reasoning builders, fallback behavior, determinism, and execution contracts.

REQUIRED EXECUTION TESTS (first 4 tests):
  1. build_render_success_patterns returns a dict
  2. Returns "render_success_patterns" top-level key
  3. Never raises on None input
  4. Never raises on garbage input
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from app.ai.outcome_tracking.render_success_pattern_engine import (
    _camera_style_descriptor,
    _classify_pattern,
    _compute_evidence_count,
    _compute_success_score,
    _is_conflicting,
    _make_pattern_id,
    _sanitize_id_part,
    build_render_success_patterns,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_edit_plan(
    rot_available: bool = True,
    creator_type: str = "podcast",
    platform: str = "tiktok",
    overall_result: str = "improved",
    ai_effectiveness: str = "strong",
    rot_confidence: float = 0.85,
    quality: dict | None = None,
    ai_execution: dict | None = None,
    ab_available: bool = True,
    ab_winner: str = "ai_on",
    ab_overall_delta: int = 6,
    creator_fit: str = "high",
    bench_status: str = "best_fit",
    subtitle_style: str = "clean_pro",
    camera_stability: str = "high",
    motion_energy: str = "low",
) -> SimpleNamespace:
    """Build a minimal SimpleNamespace mimicking AIEditPlan for Phase 62C."""
    if quality is None:
        quality = {"subtitle": 82, "camera": 78, "hook": 76, "overall": 80}
    if ai_execution is None:
        ai_execution = {"subtitle_applied": True, "camera_applied": True}

    crs_strategy = {
        "subtitle": {
            "style": subtitle_style,
            "density": "balanced",
            "keyword_emphasis": "selective",
        },
        "camera": {
            "stability_priority": camera_stability,
            "crop_aggressiveness": "medium",
            "motion_energy": motion_energy,
        },
        "hook": {"hook_energy": "moderate"},
        "ranking": {"priority": "retention_creator_fit"},
    }

    return SimpleNamespace(
        render_outcome_tracking={
            "available": rot_available,
            "creator_type": creator_type,
            "overall_result": overall_result,
            "ai_effectiveness": ai_effectiveness,
            "confidence": rot_confidence,
            "quality": quality,
            "ai_execution": ai_execution,
            "ab_result": {
                "winner": ab_winner,
                "overall_delta": ab_overall_delta,
            },
            "benchmark_result": {
                "creator_fit": creator_fit,
            },
        },
        creator_preference_reinforcement={},
        creator_render_strategy={"available": True, "strategy": crs_strategy},
        ai_ab_evaluation={"available": ab_available},
        creator_benchmark_summary={"benchmark_status": bench_status},
        creator_preference_profile={"platform": platform},
    )


# ---------------------------------------------------------------------------
# REQUIRED EXECUTION TESTS (4)
# ---------------------------------------------------------------------------

class TestRequiredExecution:
    def test_returns_dict(self):
        """build_render_success_patterns always returns a dict."""
        plan = _make_edit_plan()
        result = build_render_success_patterns(plan)
        assert isinstance(result, dict)

    def test_returns_top_level_key(self):
        """Return value contains 'render_success_patterns' key."""
        plan = _make_edit_plan()
        result = build_render_success_patterns(plan)
        assert "render_success_patterns" in result

    def test_never_raises_on_none(self):
        """Never raises when edit_plan is None."""
        result = build_render_success_patterns(None)
        assert isinstance(result, dict)
        rsp = result.get("render_success_patterns", {})
        assert rsp.get("available") is False

    def test_never_raises_on_garbage(self):
        """Never raises on arbitrary garbage input."""
        for bad in ("not-a-plan", 42, [], object(), True, b"bytes"):
            result = build_render_success_patterns(bad)
            assert isinstance(result, dict)
            assert "render_success_patterns" in result


# ---------------------------------------------------------------------------
# Fallback shape
# ---------------------------------------------------------------------------

class TestFallbackShape:
    def _fallback_rsp(self, plan) -> dict:
        return build_render_success_patterns(plan).get("render_success_patterns", {})

    def test_fallback_on_none_plan(self):
        rsp = self._fallback_rsp(None)
        assert rsp["available"] is False
        assert rsp["patterns"] == []
        assert rsp["confidence"] == 0.0
        assert rsp["reasoning"] == []

    def test_fallback_when_rot_unavailable(self):
        plan = _make_edit_plan(rot_available=False)
        rsp = self._fallback_rsp(plan)
        assert rsp["available"] is False

    def test_fallback_when_creator_type_unknown(self):
        plan = _make_edit_plan(creator_type="unknown")
        rsp = self._fallback_rsp(plan)
        assert rsp["available"] is False

    def test_fallback_when_all_quality_zero(self):
        plan = _make_edit_plan(quality={"subtitle": 0, "camera": 0, "hook": 0, "overall": 0})
        rsp = self._fallback_rsp(plan)
        assert rsp["available"] is False

    def test_fallback_when_quality_absent(self):
        plan = _make_edit_plan(quality={})
        rsp = self._fallback_rsp(plan)
        assert rsp["available"] is False


# ---------------------------------------------------------------------------
# Available output shape
# ---------------------------------------------------------------------------

class TestAvailableShape:
    def _rsp(self) -> dict:
        return build_render_success_patterns(_make_edit_plan()).get("render_success_patterns", {})

    def test_available_true(self):
        assert self._rsp()["available"] is True

    def test_has_patterns_list(self):
        assert isinstance(self._rsp()["patterns"], list)

    def test_one_pattern_per_render(self):
        assert len(self._rsp()["patterns"]) == 1

    def test_pattern_has_required_keys(self):
        pattern = self._rsp()["patterns"][0]
        for key in ("pattern_id", "creator_type", "platform", "signals",
                    "success_score", "evidence_count", "confidence",
                    "classification", "reasoning"):
            assert key in pattern, f"Missing key: {key}"

    def test_top_level_confidence_bounded(self):
        rsp = self._rsp()
        assert 0.0 <= rsp["confidence"] <= 1.0

    def test_top_level_reasoning_is_list(self):
        assert isinstance(self._rsp()["reasoning"], list)

    def test_pattern_confidence_bounded(self):
        pattern = self._rsp()["patterns"][0]
        assert 0.0 <= pattern["confidence"] <= 1.0

    def test_pattern_success_score_bounded(self):
        pattern = self._rsp()["patterns"][0]
        assert 0.0 <= pattern["success_score"] <= 1.0


# ---------------------------------------------------------------------------
# Success score formula
# ---------------------------------------------------------------------------

class TestComputeSuccessScore:
    def test_ab_winner_ai_on_max_delta(self):
        score = _compute_success_score(True, "ai_on", 10, {"overall": 100}, "best_fit", "strong")
        assert score == 1.0

    def test_ab_winner_ai_on_zero_delta(self):
        score = _compute_success_score(True, "ai_on", 0, {"overall": 0}, "unknown", "weak")
        # ab_norm=0, quality_norm=0, bench=0.2, eff=0.3
        expected = round(0*0.35 + 0*0.25 + 0.2*0.20 + 0.3*0.20, 4)
        assert score == expected

    def test_ab_winner_ai_off_penalised(self):
        score_off = _compute_success_score(True, "ai_off", 4, {"overall": 80}, "best_fit", "strong")
        score_on  = _compute_success_score(True, "ai_on",  4, {"overall": 80}, "best_fit", "strong")
        assert score_off < score_on

    def test_ab_tie_neutral(self):
        score = _compute_success_score(True, "tie", 0, {"overall": 80}, "best_fit", "strong")
        # ab_norm=0.5
        expected = round(0.5*0.35 + 0.8*0.25 + 1.0*0.20 + 1.0*0.20, 4)
        assert score == expected

    def test_no_baseline_neutral_assumption(self):
        score_no_ab = _compute_success_score(False, "unknown", 0, {"overall": 80}, "best_fit", "strong")
        score_tie   = _compute_success_score(True, "tie", 0, {"overall": 80}, "best_fit", "strong")
        assert score_no_ab == score_tie

    def test_bench_unknown_uses_02(self):
        score = _compute_success_score(False, "unknown", 0, {"overall": 0}, "unknown", "weak")
        expected = round(0.5*0.35 + 0.0*0.25 + 0.2*0.20 + 0.3*0.20, 4)
        assert score == expected

    def test_score_clamped_to_0_1(self):
        score = _compute_success_score(True, "ai_on", 999, {"overall": 999}, "best_fit", "strong")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# Evidence count
# ---------------------------------------------------------------------------

class TestComputeEvidenceCount:
    def test_max_evidence_6(self):
        count = _compute_evidence_count(
            ab_winner="ai_on",
            ai_effectiveness="strong",
            creator_fit="high",
            quality={"subtitle": 80, "camera": 80, "overall": 80},
            ai_execution={"subtitle_applied": True, "camera_applied": True},
        )
        assert count == 6

    def test_zero_evidence(self):
        count = _compute_evidence_count(
            ab_winner="ai_off",
            ai_effectiveness="weak",
            creator_fit="low",
            quality={"subtitle": 50, "camera": 50, "overall": 50},
            ai_execution={"subtitle_applied": False, "camera_applied": False},
        )
        assert count == 0

    def test_ab_winner_ai_on_adds_1(self):
        base = _compute_evidence_count("ai_off", "weak", "low", {}, {})
        with_ab = _compute_evidence_count("ai_on", "weak", "low", {}, {})
        assert with_ab == base + 1

    def test_effectiveness_moderate_adds_1(self):
        base = _compute_evidence_count("ai_off", "weak", "low", {}, {})
        mod  = _compute_evidence_count("ai_off", "moderate", "low", {}, {})
        assert mod == base + 1

    def test_creator_fit_medium_adds_1(self):
        base = _compute_evidence_count("ai_off", "weak", "low", {}, {})
        med  = _compute_evidence_count("ai_off", "weak", "medium", {}, {})
        assert med == base + 1

    def test_subtitle_quality_74_no_credit(self):
        """Quality exactly below threshold does not add evidence."""
        count = _compute_evidence_count(
            "ai_off", "weak", "low",
            {"subtitle": 74},
            {"subtitle_applied": True},
        )
        assert count == 0

    def test_subtitle_quality_75_adds_1_when_applied(self):
        count = _compute_evidence_count(
            "ai_off", "weak", "low",
            {"subtitle": 75},
            {"subtitle_applied": True},
        )
        assert count == 1

    def test_subtitle_quality_75_no_credit_when_not_applied(self):
        count = _compute_evidence_count(
            "ai_off", "weak", "low",
            {"subtitle": 80},
            {"subtitle_applied": False},
        )
        assert count == 0

    def test_overall_quality_75_adds_1(self):
        count = _compute_evidence_count("ai_off", "weak", "low", {"overall": 75}, {})
        assert count == 1


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

class TestIsConflicting:
    def test_ab_ai_on_creator_fit_low_is_conflicting(self):
        assert _is_conflicting("ai_on", "low", "neutral", "best_fit") is True

    def test_improved_needs_review_is_conflicting(self):
        assert _is_conflicting("ai_off", "high", "improved", "needs_review") is True

    def test_no_conflict_standard(self):
        assert _is_conflicting("ai_on", "high", "improved", "best_fit") is False

    def test_no_conflict_off_not_improved(self):
        assert _is_conflicting("ai_off", "low", "neutral", "unknown") is False

    def test_ai_on_high_improved_best_fit_not_conflicting(self):
        assert _is_conflicting("ai_on", "high", "improved", "best_fit") is False


# ---------------------------------------------------------------------------
# Pattern classification
# ---------------------------------------------------------------------------

class TestClassifyPattern:
    def test_strong_pattern(self):
        assert _classify_pattern(0.85, 4, False) == "strong_pattern"

    def test_strong_boundary(self):
        assert _classify_pattern(0.80, 3, False) == "strong_pattern"

    def test_strong_score_but_insufficient_evidence(self):
        assert _classify_pattern(0.85, 2, False) == "moderate_pattern"

    def test_moderate_pattern(self):
        assert _classify_pattern(0.70, 2, False) == "moderate_pattern"

    def test_moderate_boundary(self):
        assert _classify_pattern(0.65, 2, False) == "moderate_pattern"

    def test_weak_low_score(self):
        assert _classify_pattern(0.50, 1, False) == "weak_pattern"

    def test_weak_below_moderate_threshold(self):
        assert _classify_pattern(0.64, 3, False) == "weak_pattern"

    def test_conflicting_overrides_strong_score(self):
        assert _classify_pattern(0.90, 6, True) == "conflicting_pattern"

    def test_conflicting_overrides_moderate(self):
        assert _classify_pattern(0.70, 3, True) == "conflicting_pattern"


# ---------------------------------------------------------------------------
# Camera style descriptor
# ---------------------------------------------------------------------------

class TestCameraStyleDescriptor:
    def test_stable_high_stability_low_motion(self):
        assert _camera_style_descriptor("high", "low") == "stable"

    def test_stable_low_medium_motion(self):
        assert _camera_style_descriptor("high", "low_medium") == "stable"

    def test_dynamic_high_motion(self):
        assert _camera_style_descriptor("medium", "high") == "dynamic"

    def test_dynamic_medium_high_motion(self):
        assert _camera_style_descriptor("low", "medium_high") == "dynamic"

    def test_stable_focused_high_stability_medium_motion(self):
        assert _camera_style_descriptor("high", "medium") == "stable_focused"

    def test_balanced_fallback(self):
        assert _camera_style_descriptor("medium", "medium") == "balanced"


# ---------------------------------------------------------------------------
# Pattern ID
# ---------------------------------------------------------------------------

class TestMakePatternId:
    def test_known_inputs_produce_id(self):
        pid = _make_pattern_id("podcast", "tiktok", "clean_pro", "stable")
        assert pid == "podcast_tiktok_clean_pro_stable"

    def test_unknown_platform_excluded(self):
        pid = _make_pattern_id("podcast", "unknown", "clean_pro", "stable")
        assert "unknown" not in pid

    def test_sanitize_spaces(self):
        pid = _make_pattern_id("my creator", "tik tok", "bold big", "stable")
        assert " " not in pid

    def test_empty_inputs_fallback(self):
        pid = _make_pattern_id("", "", "", "")
        assert pid == "unknown_pattern"

    def test_id_max_80_chars(self):
        long_str = "a" * 40
        pid = _make_pattern_id(long_str, long_str, long_str, long_str)
        assert len(pid) <= 80


# ---------------------------------------------------------------------------
# Strong pattern integration test
# ---------------------------------------------------------------------------

class TestStrongPatternScenario:
    def setup_method(self):
        self.plan = _make_edit_plan(
            rot_available=True,
            creator_type="podcast",
            platform="tiktok",
            overall_result="improved",
            ai_effectiveness="strong",
            quality={"subtitle": 82, "camera": 80, "hook": 76, "overall": 84},
            ai_execution={"subtitle_applied": True, "camera_applied": True},
            ab_available=True,
            ab_winner="ai_on",
            ab_overall_delta=7,
            creator_fit="high",
            bench_status="best_fit",
        )
        self.rsp = build_render_success_patterns(self.plan)["render_success_patterns"]
        self.pattern = self.rsp["patterns"][0]

    def test_classification_strong(self):
        assert self.pattern["classification"] == "strong_pattern"

    def test_evidence_count_at_least_3(self):
        assert self.pattern["evidence_count"] >= 3

    def test_success_score_at_least_080(self):
        assert self.pattern["success_score"] >= 0.80

    def test_creator_type_correct(self):
        assert self.pattern["creator_type"] == "podcast"

    def test_platform_correct(self):
        assert self.pattern["platform"] == "tiktok"

    def test_reasoning_mentions_ab(self):
        all_reasoning = " ".join(self.pattern["reasoning"])
        assert "A/B" in all_reasoning or "a/b" in all_reasoning.lower()


# ---------------------------------------------------------------------------
# Conflicting pattern integration test
# ---------------------------------------------------------------------------

class TestConflictingPatternScenario:
    def setup_method(self):
        self.plan = _make_edit_plan(
            ab_winner="ai_on",
            creator_fit="low",
            overall_result="improved",
            bench_status="best_fit",
        )
        self.rsp = build_render_success_patterns(self.plan)["render_success_patterns"]
        self.pattern = self.rsp["patterns"][0]

    def test_classification_conflicting(self):
        assert self.pattern["classification"] == "conflicting_pattern"

    def test_reasoning_mentions_mixed(self):
        all_reasoning = " ".join(self.pattern["reasoning"]).lower()
        assert any(w in all_reasoning for w in ("mixed", "conflict", "contradict", "no clear"))


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        plan = _make_edit_plan()
        r1 = build_render_success_patterns(plan)
        r2 = build_render_success_patterns(plan)
        assert r1 == r2

    def test_different_creator_types_different_ids(self):
        p1 = _make_edit_plan(creator_type="podcast")
        p2 = _make_edit_plan(creator_type="talking_head")
        rsp1 = build_render_success_patterns(p1)["render_success_patterns"]["patterns"][0]
        rsp2 = build_render_success_patterns(p2)["render_success_patterns"]["patterns"][0]
        assert rsp1["pattern_id"] != rsp2["pattern_id"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_partial_quality_only_overall_triggers_available(self):
        """Only overall quality present and > 0 still passes gate."""
        plan = _make_edit_plan(quality={"overall": 60})
        rsp = build_render_success_patterns(plan)["render_success_patterns"]
        assert rsp["available"] is True

    def test_no_crs_signals_produces_empty_signals(self):
        """No creator_render_strategy still returns available with empty signals."""
        plan = _make_edit_plan()
        plan.creator_render_strategy = {}
        rsp = build_render_success_patterns(plan)["render_success_patterns"]
        assert rsp["available"] is True
        assert isinstance(rsp["patterns"][0]["signals"], dict)

    def test_dict_edit_plan_accepted(self):
        """Engine also works when edit_plan is a dict (duck-typed)."""
        plan = _make_edit_plan()
        plan_dict = {
            "render_outcome_tracking": plan.render_outcome_tracking,
            "creator_preference_reinforcement": {},
            "creator_render_strategy": plan.creator_render_strategy,
            "ai_ab_evaluation": plan.ai_ab_evaluation,
            "creator_benchmark_summary": plan.creator_benchmark_summary,
            "creator_preference_profile": plan.creator_preference_profile,
        }
        result = build_render_success_patterns(plan_dict)
        assert isinstance(result, dict)
        assert "render_success_patterns" in result

    def test_confidence_not_nan(self):
        plan = _make_edit_plan()
        rsp = build_render_success_patterns(plan)["render_success_patterns"]
        assert not math.isnan(rsp["confidence"])

    def test_no_ab_baseline_lowers_confidence_vs_with_ab(self):
        plan_with = _make_edit_plan(ab_available=True, ab_winner="ai_on", ab_overall_delta=6)
        plan_without = _make_edit_plan(ab_available=False, ab_winner="unknown", ab_overall_delta=0)
        conf_with    = build_render_success_patterns(plan_with)["render_success_patterns"]["confidence"]
        conf_without = build_render_success_patterns(plan_without)["render_success_patterns"]["confidence"]
        assert conf_with >= conf_without
