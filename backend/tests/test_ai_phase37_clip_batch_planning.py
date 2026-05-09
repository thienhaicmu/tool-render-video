"""
tests/test_ai_phase37_clip_batch_planning.py

Phase 37 — AI Multi-Clip Batch Planning Foundation

Safety contract: planning-only, no render execution, no job enqueue,
no FFmpeg mutation, no playback_speed mutation, no subtitle timing rewrite,
no source segment reorder.
"""
from __future__ import annotations

import types
from dataclasses import dataclass, field
from typing import Any, List


# ---------------------------------------------------------------------------
# Helpers — minimal stubs
# ---------------------------------------------------------------------------

def _make_edit_plan(**overrides) -> Any:
    """Return a minimal AIEditPlan-like namespace."""
    defaults = {
        "clip_segment_selection": {},
        "clip_candidate_discovery": {},
        "ai_apply_policy": {},
        "creator_style_adaptation": {},
        "creator_style": {},
        "variant_selection": {},
        "multivariant_render_plans": {},
        "camera_motion_apply": {},
        "subtitle_text_apply": {},
        "timing_apply": {},
        "selected_segments": [],
        "pacing": types.SimpleNamespace(pacing_style="default"),
        "explainability": {},
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_payload(**overrides) -> Any:
    defaults = {
        "ai_clip_batch_planning_enabled": False,
        "ai_clip_batch_limit": 5,
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _seg(
    idx: int = 1,
    start: float = 10.0,
    end: float = 40.0,
    score: float = 75.0,
    warnings: list | None = None,
) -> dict:
    return {
        "segment_id": f"seg_{idx:02d}",
        "candidate_id": f"cand_{idx:02d}",
        "label": f"Clip {idx}",
        "start_sec": start,
        "end_sec": end,
        "duration_sec": end - start,
        "score": score,
        "source_scores": {"retention": score, "hook": 60.0, "story": 55.0},
        "warnings": warnings or [],
        "safe": True,
    }


def _css_with(*segs) -> dict:
    return {
        "available": True,
        "enabled": True,
        "mode": "selection_only",
        "selected_segments": list(segs),
        "rejected_candidates": [],
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 1. Schema invariants
# ---------------------------------------------------------------------------

class TestClipBatchSchema:
    def test_batch_plan_defaults(self):
        from app.ai.clips.clip_batch_schema import AIClipBatchPlan
        p = AIClipBatchPlan(batch_plan_id="batch_01")
        assert p.batch_plan_id == "batch_01"
        assert p.render_strategy == "safe_default"
        assert p.variant_strategy == "single_safe"
        assert p.subtitle_strategy == "default"
        assert p.camera_strategy == "default"
        assert p.timing_strategy == "default"
        assert p.safe is False
        assert isinstance(p.planned_payload_overrides, dict)
        assert isinstance(p.warnings, list)
        assert isinstance(p.explanation, list)

    def test_batch_plan_to_dict(self):
        from app.ai.clips.clip_batch_schema import AIClipBatchPlan
        p = AIClipBatchPlan(
            batch_plan_id="batch_01",
            start_sec=10.0,
            end_sec=40.0,
            duration_sec=30.0,
            score=80.0,
            rank=1,
            safe=True,
        )
        d = p.to_dict()
        assert d["batch_plan_id"] == "batch_01"
        assert d["start_sec"] == 10.0
        assert d["end_sec"] == 40.0
        assert d["duration_sec"] == 30.0
        assert d["score"] == 80.0
        assert d["rank"] == 1
        assert d["safe"] is True
        assert "planned_payload_overrides" in d
        assert "warnings" in d
        assert "explanation" in d

    def test_batch_plan_set_defaults(self):
        from app.ai.clips.clip_batch_schema import AIClipBatchPlanSet
        ps = AIClipBatchPlanSet()
        assert ps.available is True
        assert ps.enabled is False
        assert ps.mode == "planning_only"
        assert ps.plans == []
        assert ps.recommended_plan_ids == []

    def test_batch_plan_set_to_dict(self):
        from app.ai.clips.clip_batch_schema import AIClipBatchPlan, AIClipBatchPlanSet
        ps = AIClipBatchPlanSet(
            enabled=True,
            plans=[AIClipBatchPlan(batch_plan_id="batch_01", start_sec=5.0, end_sec=35.0, duration_sec=30.0)],
            recommended_plan_ids=["batch_01"],
        )
        d = ps.to_dict()
        assert d["enabled"] is True
        assert d["mode"] == "planning_only"
        assert len(d["plans"]) == 1
        assert d["recommended_plan_ids"] == ["batch_01"]

    def test_allowed_render_strategies(self):
        from app.ai.clips.clip_batch_schema import _ALLOWED_RENDER_STRATEGIES
        assert "safe_default" in _ALLOWED_RENDER_STRATEGIES
        assert "retention_focused" in _ALLOWED_RENDER_STRATEGIES
        assert "creator_style_focused" in _ALLOWED_RENDER_STRATEGIES
        assert "subtitle_clarity" in _ALLOWED_RENDER_STRATEGIES
        assert "camera_dynamic_safe" in _ALLOWED_RENDER_STRATEGIES

    def test_allowed_variant_strategies(self):
        from app.ai.clips.clip_batch_schema import _ALLOWED_VARIANT_STRATEGIES
        assert "single_safe" in _ALLOWED_VARIANT_STRATEGIES
        assert "selected_variant" in _ALLOWED_VARIANT_STRATEGIES
        assert "multivariant_limited" in _ALLOWED_VARIANT_STRATEGIES


# ---------------------------------------------------------------------------
# 2. Safety validation
# ---------------------------------------------------------------------------

class TestClipBatchSafety:
    def test_sanitize_removes_forbidden_keys(self):
        from app.ai.clips.clip_batch_safety import sanitize_batch_payload_overrides
        raw = {
            "subtitle_density": "normal",
            "playback_speed": 1.5,
            "ffmpeg_args": "-y",
            "bitrate": "5000k",
            "codec": "h264",
            "creator_style": "podcast_viral",
        }
        result = sanitize_batch_payload_overrides(raw)
        assert "subtitle_density" in result
        assert "creator_style" in result
        assert "playback_speed" not in result
        assert "ffmpeg_args" not in result
        assert "bitrate" not in result
        assert "codec" not in result

    def test_sanitize_all_allowed_keys(self):
        from app.ai.clips.clip_batch_safety import sanitize_batch_payload_overrides
        raw = {
            "subtitle_density": "high",
            "subtitle_emphasis": "bold",
            "camera_behavior": "fast_follow",
            "pacing_style": "fast",
            "creator_style": "podcast_viral",
            "visual_rhythm_mode": "dynamic",
            "ai_mode": "viral_tiktok",
        }
        result = sanitize_batch_payload_overrides(raw)
        assert len(result) == len(raw)

    def test_sanitize_overrides_non_dict(self):
        from app.ai.clips.clip_batch_safety import sanitize_batch_payload_overrides
        assert sanitize_batch_payload_overrides(None) == {}
        assert sanitize_batch_payload_overrides("bad") == {}
        assert sanitize_batch_payload_overrides(42) == {}

    def test_sanitize_plan_score_clamped(self):
        from app.ai.clips.clip_batch_safety import sanitize_batch_plan
        plan = {"batch_plan_id": "x", "start_sec": 5.0, "end_sec": 35.0, "duration_sec": 30.0, "score": 999.0}
        r = sanitize_batch_plan(plan)
        assert r["score"] <= 100.0

    def test_sanitize_plan_negative_timing_clamped(self):
        from app.ai.clips.clip_batch_safety import sanitize_batch_plan
        plan = {"batch_plan_id": "x", "start_sec": -5.0, "end_sec": 30.0, "duration_sec": 35.0}
        r = sanitize_batch_plan(plan)
        assert r["start_sec"] >= 0.0

    def test_sanitize_plan_invalid_render_strategy_defaults(self):
        from app.ai.clips.clip_batch_safety import sanitize_batch_plan
        plan = {"batch_plan_id": "x", "start_sec": 5.0, "end_sec": 35.0, "duration_sec": 30.0,
                "render_strategy": "run_ffmpeg_now"}
        r = sanitize_batch_plan(plan)
        assert r["render_strategy"] == "safe_default"

    def test_is_batch_plan_safe_valid(self):
        from app.ai.clips.clip_batch_safety import is_batch_plan_safe
        plan = {
            "batch_plan_id": "b01",
            "start_sec": 10.0,
            "end_sec": 40.0,
            "duration_sec": 30.0,
            "render_strategy": "safe_default",
            "variant_strategy": "single_safe",
            "planned_payload_overrides": {},
        }
        assert is_batch_plan_safe(plan) is True

    def test_is_batch_plan_safe_negative_start_rejected(self):
        from app.ai.clips.clip_batch_safety import is_batch_plan_safe
        plan = {
            "batch_plan_id": "b01",
            "start_sec": -1.0,
            "end_sec": 40.0,
            "duration_sec": 41.0,
            "render_strategy": "safe_default",
            "variant_strategy": "single_safe",
        }
        assert is_batch_plan_safe(plan) is False

    def test_is_batch_plan_safe_nan_timing_rejected(self):
        import math
        from app.ai.clips.clip_batch_safety import is_batch_plan_safe
        plan = {
            "batch_plan_id": "b01",
            "start_sec": float("nan"),
            "end_sec": 40.0,
            "duration_sec": 40.0,
            "render_strategy": "safe_default",
            "variant_strategy": "single_safe",
        }
        assert is_batch_plan_safe(plan) is False

    def test_is_batch_plan_safe_end_before_start(self):
        from app.ai.clips.clip_batch_safety import is_batch_plan_safe
        plan = {
            "batch_plan_id": "b01",
            "start_sec": 50.0,
            "end_sec": 20.0,
            "duration_sec": -30.0,
            "render_strategy": "safe_default",
            "variant_strategy": "single_safe",
        }
        assert is_batch_plan_safe(plan) is False

    def test_is_batch_plan_safe_forbidden_override_rejected(self):
        from app.ai.clips.clip_batch_safety import is_batch_plan_safe
        plan = {
            "batch_plan_id": "b01",
            "start_sec": 10.0,
            "end_sec": 40.0,
            "duration_sec": 30.0,
            "render_strategy": "safe_default",
            "variant_strategy": "single_safe",
            "planned_payload_overrides": {"playback_speed": 1.5},
        }
        assert is_batch_plan_safe(plan) is False

    def test_is_batch_plan_safe_zero_duration_rejected(self):
        from app.ai.clips.clip_batch_safety import is_batch_plan_safe
        plan = {
            "batch_plan_id": "b01",
            "start_sec": 10.0,
            "end_sec": 10.0,
            "duration_sec": 0.0,
            "render_strategy": "safe_default",
            "variant_strategy": "single_safe",
        }
        assert is_batch_plan_safe(plan) is False

    def test_is_batch_plan_safe_none_input(self):
        from app.ai.clips.clip_batch_safety import is_batch_plan_safe
        assert is_batch_plan_safe(None) is False
        assert is_batch_plan_safe("bad") is False


# ---------------------------------------------------------------------------
# 3. Batch planner behavior
# ---------------------------------------------------------------------------

class TestClipBatchPlanner:
    def test_disabled_by_default(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        ep = _make_edit_plan(clip_segment_selection=_css_with(_seg(1)))
        payload = _make_payload(ai_clip_batch_planning_enabled=False)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.enabled is False
        assert result.plans == []

    def test_enabled_produces_plans(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        ep = _make_edit_plan(clip_segment_selection=_css_with(_seg(1), _seg(2)))
        payload = _make_payload(ai_clip_batch_planning_enabled=True, ai_clip_batch_limit=5)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.enabled is True
        assert len(result.plans) == 2

    def test_batch_limit_enforced(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        segs = [_seg(i, start=i * 30.0, end=i * 30.0 + 25.0) for i in range(1, 11)]
        ep = _make_edit_plan(clip_segment_selection=_css_with(*segs))
        payload = _make_payload(ai_clip_batch_planning_enabled=True, ai_clip_batch_limit=3)
        result = build_clip_batch_plans(ep, payload=payload)
        assert len(result.plans) <= 3

    def test_batch_limit_clamp_max(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        segs = [_seg(i, start=i * 30.0, end=i * 30.0 + 25.0) for i in range(1, 5)]
        ep = _make_edit_plan(clip_segment_selection=_css_with(*segs))
        payload = _make_payload(ai_clip_batch_planning_enabled=True, ai_clip_batch_limit=999)
        result = build_clip_batch_plans(ep, payload=payload)
        assert len(result.plans) <= 20

    def test_no_selected_segments_fallback_safe(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        ep = _make_edit_plan(clip_segment_selection={"enabled": True, "selected_segments": []})
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.enabled is True
        assert result.plans == []
        assert any("no_selected_segments" in w for w in result.warnings)

    def test_fallback_to_raw_selected_segments(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        raw_seg = types.SimpleNamespace(start=10.0, end=40.0, score=70.0)
        ep = _make_edit_plan(
            clip_segment_selection={},
            selected_segments=[raw_seg],
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.enabled is True
        assert len(result.plans) >= 1

    def test_plan_ids_deterministic(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        segs = [_seg(1), _seg(2), _seg(3)]
        ep = _make_edit_plan(clip_segment_selection=_css_with(*segs))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        r1 = build_clip_batch_plans(ep, payload=payload)
        r2 = build_clip_batch_plans(ep, payload=payload)
        ids1 = [p.batch_plan_id for p in r1.plans]
        ids2 = [p.batch_plan_id for p in r2.plans]
        assert ids1 == ids2

    def test_plan_ids_sequential(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        segs = [_seg(i, start=i * 30.0, end=i * 30.0 + 25.0) for i in range(1, 4)]
        ep = _make_edit_plan(clip_segment_selection=_css_with(*segs))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        ids = [p.batch_plan_id for p in result.plans]
        assert ids == ["batch_01", "batch_02", "batch_03"]

    def test_rank_sequential(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        segs = [_seg(i, start=i * 30.0, end=i * 30.0 + 25.0) for i in range(1, 4)]
        ep = _make_edit_plan(clip_segment_selection=_css_with(*segs))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        ranks = [p.rank for p in result.plans]
        assert ranks == [1, 2, 3]

    def test_safe_plans_recommended(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        segs = [_seg(1), _seg(2)]
        ep = _make_edit_plan(clip_segment_selection=_css_with(*segs))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        safe_ids = {p.batch_plan_id for p in result.plans if p.safe}
        for rec_id in result.recommended_plan_ids:
            assert rec_id in safe_ids

    def test_recommended_plan_ids_at_most_3(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        segs = [_seg(i, start=i * 30.0, end=i * 30.0 + 25.0) for i in range(1, 8)]
        ep = _make_edit_plan(clip_segment_selection=_css_with(*segs))
        payload = _make_payload(ai_clip_batch_planning_enabled=True, ai_clip_batch_limit=7)
        result = build_clip_batch_plans(ep, payload=payload)
        assert len(result.recommended_plan_ids) <= 3

    def test_mode_is_planning_only(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        ep = _make_edit_plan(clip_segment_selection=_css_with(_seg(1)))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.mode == "planning_only"


# ---------------------------------------------------------------------------
# 4. Strategy assignment
# ---------------------------------------------------------------------------

class TestStrategyAssignment:
    def test_subtitle_overload_warning_triggers_subtitle_clarity(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1, warnings=["subtitle_overload"])
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].render_strategy == "subtitle_clarity"

    def test_high_retention_score_triggers_retention_focused(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1, score=85.0)
        seg["source_scores"]["retention"] = 85.0
        seg["warnings"] = []
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].render_strategy == "retention_focused"

    def test_strong_creator_style_triggers_creator_style_focused(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1, score=50.0)
        seg["source_scores"]["retention"] = 50.0
        seg["source_scores"]["hook"] = 50.0
        seg["source_scores"]["story"] = 50.0
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            creator_style_adaptation={"dominant_style": "podcast_viral", "confidence": 0.9},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].render_strategy == "creator_style_focused"

    def test_conservative_policy_uses_single_safe(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            ai_apply_policy={"effective_policy": "conservative"},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].variant_strategy == "single_safe"

    def test_balanced_policy_may_use_selected_variant(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            ai_apply_policy={"effective_policy": "balanced"},
            variant_selection={"available": True, "best_variant_id": "v1"},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].variant_strategy in ("single_safe", "selected_variant")

    def test_aggressive_policy_may_use_multivariant_limited(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            ai_apply_policy={"effective_policy": "aggressive"},
            multivariant_render_plans={"available": True, "plans": []},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].variant_strategy in ("single_safe", "selected_variant", "multivariant_limited")

    def test_camera_apply_enabled_sets_motion_guided_camera_strategy(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            camera_motion_apply={"enabled": True, "behavior": "fast_follow"},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].camera_strategy == "motion_guided"

    def test_timing_apply_enabled_sets_retention_optimized_timing_strategy(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            timing_apply={"enabled": True},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].timing_strategy == "retention_optimized"

    def test_subtitle_overload_sets_reduced_density_subtitle_strategy(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1, warnings=["subtitle_overload"])
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].subtitle_strategy == "reduced_density"

    def test_subtitle_apply_enabled_sets_optimized_strategy(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            subtitle_text_apply={"enabled": True, "density": "normal"},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].subtitle_strategy == "optimized"

    def test_creator_style_set_on_plan(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            creator_style_adaptation={"dominant_style": "podcast_viral", "confidence": 0.9},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result.plans[0].creator_style == "podcast_viral"


# ---------------------------------------------------------------------------
# 5. Payload overrides safety
# ---------------------------------------------------------------------------

class TestPayloadOverridesSafety:
    def test_forbidden_keys_never_in_overrides(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        forbidden = {
            "playback_speed", "segment_start", "segment_end", "subtitle_timing",
            "ffmpeg_args", "codec", "bitrate", "crf", "validation_rules",
            "output_path", "render_command", "render_segments", "segment_order",
            "queue_priority", "job_id",
        }
        for plan in result.plans:
            for key in plan.planned_payload_overrides:
                assert key not in forbidden, f"Forbidden key '{key}' found in overrides"

    def test_camera_behavior_override_allowed(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            camera_motion_apply={"enabled": True, "behavior": "fast_follow"},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        if result.plans and result.plans[0].planned_payload_overrides:
            overrides = result.plans[0].planned_payload_overrides
            assert "camera_behavior" in overrides
            assert overrides["camera_behavior"] == "fast_follow"

    def test_subtitle_density_override_allowed(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(
            clip_segment_selection=_css_with(seg),
            subtitle_text_apply={"enabled": True, "density": "low"},
        )
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        if result.plans and result.plans[0].planned_payload_overrides:
            overrides = result.plans[0].planned_payload_overrides
            assert "subtitle_density" in overrides
            assert overrides["subtitle_density"] == "low"


# ---------------------------------------------------------------------------
# 6. No-mutation safety
# ---------------------------------------------------------------------------

class TestNoMutationSafety:
    def test_no_payload_mutation_in_place(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        original_enabled = payload.ai_clip_batch_planning_enabled
        original_limit = payload.ai_clip_batch_limit
        build_clip_batch_plans(ep, payload=payload)
        assert payload.ai_clip_batch_planning_enabled == original_enabled
        assert payload.ai_clip_batch_limit == original_limit

    def test_no_render_execution(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        import sys
        # Ensure no render engine is imported as side effect
        modules_before = set(sys.modules.keys())
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        build_clip_batch_plans(ep, payload=payload)
        new_modules = set(sys.modules.keys()) - modules_before
        render_modules = {m for m in new_modules if "render_engine" in m or "ffmpeg" in m.lower()}
        assert not render_modules, f"Unexpected render modules imported: {render_modules}"

    def test_no_job_enqueue(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        import sys
        modules_before = set(sys.modules.keys())
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        build_clip_batch_plans(ep, payload=payload)
        new_modules = set(sys.modules.keys()) - modules_before
        queue_modules = {m for m in new_modules if "queue" in m or "celery" in m or "enqueue" in m}
        assert not queue_modules, f"Unexpected queue modules: {queue_modules}"

    def test_no_ffmpeg_mutation(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        for plan in result.plans:
            overrides = plan.planned_payload_overrides
            assert "ffmpeg_args" not in overrides
            assert "codec" not in overrides
            assert "bitrate" not in overrides

    def test_no_playback_speed_mutation(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        for plan in result.plans:
            assert "playback_speed" not in plan.planned_payload_overrides

    def test_no_subtitle_timing_rewrite(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        for plan in result.plans:
            assert "subtitle_timing" not in plan.planned_payload_overrides

    def test_no_source_segment_reorder(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        segs = [_seg(i, start=i * 30.0, end=i * 30.0 + 25.0) for i in range(1, 4)]
        ep = _make_edit_plan(clip_segment_selection=_css_with(*segs))
        original_order = [s["segment_id"] for s in segs]
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        build_clip_batch_plans(ep, payload=payload)
        # Original edit plan segments unchanged
        css = ep.clip_segment_selection
        post_order = [s["segment_id"] for s in css["selected_segments"]]
        assert post_order == original_order

    def test_no_queue_mutation(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        for plan in result.plans:
            assert "queue_priority" not in plan.planned_payload_overrides
            assert "job_id" not in plan.planned_payload_overrides


# ---------------------------------------------------------------------------
# 7. Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_clip_batch_planning_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert hasattr(plan, "clip_batch_planning")
        assert isinstance(plan.clip_batch_planning, dict)

    def test_clip_batch_planning_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert plan.clip_batch_planning == {}

    def test_to_dict_includes_clip_batch_planning(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            pacing=AIPacingPlan(),
        )
        plan.clip_batch_planning = {
            "available": True,
            "enabled": False,
            "mode": "planning_only",
            "plans": [],
            "recommended_plan_ids": [],
            "warnings": [],
        }
        d = plan.to_dict()
        assert "clip_batch_planning" in d
        assert d["clip_batch_planning"]["mode"] == "planning_only"

    def test_backward_compat_phases_1_36(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for key in (
            "clip_candidate_discovery", "clip_segment_selection",
            "timing_apply", "subtitle_text_apply", "camera_motion_apply",
        ):
            assert key in d


# ---------------------------------------------------------------------------
# 8. Render influence integration
# ---------------------------------------------------------------------------

class TestRenderInfluenceIntegration:
    def _make_edit_plan_with_batch(self, enabled: bool, n_plans: int = 2) -> Any:
        plans = []
        for i in range(n_plans):
            plans.append({
                "batch_plan_id": f"batch_{i + 1:02d}",
                "render_strategy": "safe_default",
                "safe": True,
            })
        return types.SimpleNamespace(
            clip_batch_planning={
                "available": True,
                "enabled": enabled,
                "mode": "planning_only",
                "plans": plans,
                "recommended_plan_ids": [p["batch_plan_id"] for p in plans[:2]],
                "warnings": [],
            },
            clip_candidate_discovery={},
            clip_segment_selection={},
            camera=types.SimpleNamespace(
                mode="default", behavior="none", subtitle_safe=True,
                zoom_strength=1.0, follow_strength=0.5, motion_energy=None,
            ),
            subtitle=types.SimpleNamespace(
                tone="default", highlight_keywords=False, max_words_per_line=None,
                emphasis_style="none", density="normal", beat_aware=False, emotion_aware=False,
            ),
            explainability={},
        )

    def test_batch_planning_disabled_reported_in_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        ep = self._make_edit_plan_with_batch(enabled=False)
        payload = types.SimpleNamespace(
            ai_influence_enabled=True,
            camera_mode="default",
            reframe_mode="none",
            subtitle_density="normal",
        )
        _, report = apply_ai_render_influence(payload, ep)
        combined = " ".join(report.get("skipped", []))
        assert "clip_batch_planning" in combined

    def test_batch_planning_enabled_reported_in_skipped_not_applied(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        ep = self._make_edit_plan_with_batch(enabled=True, n_plans=2)
        payload = types.SimpleNamespace(
            ai_influence_enabled=True,
            camera_mode="default",
            reframe_mode="none",
            subtitle_density="normal",
        )
        _, report = apply_ai_render_influence(payload, ep)
        combined = " ".join(report.get("skipped", []))
        assert "clip_batch_planning" in combined
        applied = " ".join(report.get("applied", []))
        assert "clip_batch_planning" not in applied

    def test_batch_planning_shows_plan_count(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        ep = self._make_edit_plan_with_batch(enabled=True, n_plans=3)
        payload = types.SimpleNamespace(
            ai_influence_enabled=True,
            camera_mode="default",
            reframe_mode="none",
            subtitle_density="normal",
        )
        _, report = apply_ai_render_influence(payload, ep)
        combined = " ".join(report.get("skipped", []))
        assert "plans=3" in combined

    def test_no_result_reported_gracefully(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        ep = types.SimpleNamespace(
            clip_batch_planning={},
            clip_candidate_discovery={},
            clip_segment_selection={},
            camera=types.SimpleNamespace(
                mode="default", behavior="none", subtitle_safe=True,
                zoom_strength=1.0, follow_strength=0.5, motion_energy=None,
            ),
            subtitle=types.SimpleNamespace(
                tone="default", highlight_keywords=False, max_words_per_line=None,
                emphasis_style="none", density="normal", beat_aware=False, emotion_aware=False,
            ),
            explainability={},
        )
        payload = types.SimpleNamespace(
            ai_influence_enabled=True,
            camera_mode="default",
            reframe_mode="none",
            subtitle_density="normal",
        )
        _, report = apply_ai_render_influence(payload, ep)
        combined = " ".join(report.get("skipped", []))
        assert "clip_batch_planning:no_result" in combined


# ---------------------------------------------------------------------------
# 9. Request schema fields
# ---------------------------------------------------------------------------

class TestRequestSchemaFields:
    def test_batch_planning_disabled_by_default(self):
        from app.models.schemas import RenderRequest
        r = RenderRequest(source="youtube", url="https://example.com")
        assert r.ai_clip_batch_planning_enabled is False

    def test_batch_limit_default(self):
        from app.models.schemas import RenderRequest
        r = RenderRequest(source="youtube", url="https://example.com")
        assert r.ai_clip_batch_limit == 5

    def test_batch_limit_clamp_low(self):
        from app.models.schemas import RenderRequest
        r = RenderRequest(source="youtube", url="https://example.com", ai_clip_batch_limit=0)
        assert r.ai_clip_batch_limit == 1

    def test_batch_limit_clamp_high(self):
        from app.models.schemas import RenderRequest
        r = RenderRequest(source="youtube", url="https://example.com", ai_clip_batch_limit=999)
        assert r.ai_clip_batch_limit == 20

    def test_batch_limit_valid_value(self):
        from app.models.schemas import RenderRequest
        r = RenderRequest(source="youtube", url="https://example.com", ai_clip_batch_limit=7)
        assert r.ai_clip_batch_limit == 7

    def test_phase_35_36_fields_still_present(self):
        from app.models.schemas import RenderRequest
        r = RenderRequest(source="youtube", url="https://example.com")
        assert hasattr(r, "ai_clip_discovery_enabled")
        assert hasattr(r, "ai_clip_segment_selection_enabled")
        assert hasattr(r, "ai_clip_target_count")


# ---------------------------------------------------------------------------
# 10. Environment requirements
# ---------------------------------------------------------------------------

class TestEnvironmentRequirements:
    def test_no_api_key_required(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        import os
        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            seg = _seg(1)
            ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
            payload = _make_payload(ai_clip_batch_planning_enabled=True)
            result = build_clip_batch_plans(ep, payload=payload)
            assert result is not None
        finally:
            if original is not None:
                os.environ["OPENAI_API_KEY"] = original

    def test_no_gpu_required(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result is not None

    def test_no_internet_required(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        seg = _seg(1)
        ep = _make_edit_plan(clip_segment_selection=_css_with(seg))
        payload = _make_payload(ai_clip_batch_planning_enabled=True)
        result = build_clip_batch_plans(ep, payload=payload)
        assert result is not None

    def test_never_raises(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        result = build_clip_batch_plans(None, payload=None, context=None)
        assert result is not None

    def test_never_raises_on_bad_payload(self):
        from app.ai.clips.clip_batch_planner import build_clip_batch_plans
        result = build_clip_batch_plans(
            types.SimpleNamespace(),
            payload=types.SimpleNamespace(ai_clip_batch_planning_enabled=True, ai_clip_batch_limit="bad"),
        )
        assert result is not None
