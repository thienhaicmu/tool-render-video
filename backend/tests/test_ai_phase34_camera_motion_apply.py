"""
tests/test_ai_phase34_camera_motion_apply.py — Phase 34: Safe Camera Motion Apply Foundation.

Tests:
- schema invariants (AICameraMotionApply, AICameraMotionApplyPack)
- safety gates (camera_apply_safety)
- engine behavior (camera_apply_engine)
- edit plan schema backward compatibility
- render influence reporter
- end-to-end integration
"""
from __future__ import annotations

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_plan(**kwargs):
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan,
    )
    defaults = dict(
        enabled=True, mode="viral_tiktok",
        selected_segments=[AIClipPlan(start=0.0, end=10.0, score=80.0)],
        subtitle=AISubtitlePlan(), camera=AICameraPlan(),
    )
    defaults.update(kwargs)
    return AIEditPlan(**defaults)


def _safe_candidate(**kwargs):
    c = {
        "apply_id": "c1",
        "camera_type": "subtitle_safe_framing",
        "source_candidate_id": "p5",
        "confidence": 0.80,
        "target_scope": "metadata",
        "changes": {"subtitle_safe_framing": True},
    }
    c.update(kwargs)
    return c


def _build_pack_with_policy(policy: str):
    from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
    plan = _make_plan()
    ctx = {"ai_apply_policy": policy, "job_id": "test"}
    return build_camera_motion_apply_pack(plan, payload=None, context=ctx)


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestCameraApplySchema:
    def test_apply_defaults(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApply
        a = AICameraMotionApply(apply_id="a1")
        assert a.applied is False
        assert a.safe is False
        assert a.confidence == 0.0
        assert a.target_scope == "metadata"

    def test_apply_to_dict_strips_forbidden_change_keys(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApply
        a = AICameraMotionApply(
            apply_id="a1",
            camera_type="dynamic_safe",
            confidence=0.8,
            applied=True, safe=True,
            changes={
                "camera_behavior": "fast_follow",
                "crop_x": 100,           # forbidden
                "ffmpeg_args": "-vf x",  # forbidden
                "playback_speed": 2.0,   # forbidden
            },
        )
        d = a.to_dict()
        assert "crop_x" not in d["changes"]
        assert "ffmpeg_args" not in d["changes"]
        assert "playback_speed" not in d["changes"]
        assert "camera_behavior" in d["changes"]

    def test_apply_to_dict_unknown_type_becomes_unknown(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApply
        a = AICameraMotionApply(apply_id="a1", camera_type="direct_crop_coordinate_rewrite")
        d = a.to_dict()
        assert d["camera_type"] == "unknown"

    def test_apply_to_dict_allowed_types_preserved(self):
        from app.ai.camera.camera_apply_schema import (
            AICameraMotionApply, _ALLOWED_CAMERA_TYPES,
        )
        for t in _ALLOWED_CAMERA_TYPES:
            a = AICameraMotionApply(apply_id="a", camera_type=t,
                                    changes={"camera_behavior": "auto"})
            d = a.to_dict()
            assert d["camera_type"] == t

    def test_apply_to_dict_clamps_confidence(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApply
        a = AICameraMotionApply(apply_id="a1", confidence=99.0)
        d = a.to_dict()
        assert d["confidence"] == 1.0

    def test_apply_to_dict_clamps_beat_pulse_strength_max(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApply
        a = AICameraMotionApply(apply_id="a1", camera_type="beat_aware_pulse",
                                changes={"beat_pulse_strength": 99.0})
        d = a.to_dict()
        assert d["changes"]["beat_pulse_strength"] == 0.35

    def test_apply_to_dict_clamps_beat_pulse_strength_min(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApply
        a = AICameraMotionApply(apply_id="a1", camera_type="beat_aware_pulse",
                                changes={"beat_pulse_strength": -5.0})
        d = a.to_dict()
        assert d["changes"]["beat_pulse_strength"] == 0.0

    def test_apply_to_dict_clamps_max_camera_intensity(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApply
        a = AICameraMotionApply(apply_id="a1", camera_type="dynamic_safe",
                                changes={"max_camera_intensity": 5.0})
        d = a.to_dict()
        assert d["changes"]["max_camera_intensity"] == 1.0

    def test_pack_defaults(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApplyPack
        p = AICameraMotionApplyPack()
        assert p.available is True
        assert p.enabled is False
        assert p.mode == "disabled"
        assert p.applied == []
        assert p.blocked == []

    def test_pack_to_dict_keys(self):
        from app.ai.camera.camera_apply_schema import AICameraMotionApplyPack
        d = AICameraMotionApplyPack().to_dict()
        for key in ("available", "enabled", "mode", "applied", "blocked", "warnings"):
            assert key in d

    def test_pack_to_dict_caps_applied(self):
        from app.ai.camera.camera_apply_schema import (
            AICameraMotionApplyPack, AICameraMotionApply,
        )
        items = [AICameraMotionApply(apply_id=str(i)) for i in range(25)]
        p = AICameraMotionApplyPack(applied=items)
        d = p.to_dict()
        assert len(d["applied"]) == 20

    def test_allowed_camera_types(self):
        from app.ai.camera.camera_apply_schema import _ALLOWED_CAMERA_TYPES
        for t in ("dynamic_safe", "subtitle_safe_framing", "beat_aware_pulse",
                  "creator_style_camera", "subject_lock_preference", "motion_smoothing_hint"):
            assert t in _ALLOWED_CAMERA_TYPES

    def test_forbidden_camera_types(self):
        from app.ai.camera.camera_apply_schema import _FORBIDDEN_CAMERA_TYPES
        for t in ("direct_crop_coordinate_rewrite", "ffmpeg_filter_rewrite",
                  "arbitrary_zoom_curve", "unsafe_subject_jump", "scene_reorder_camera"):
            assert t in _FORBIDDEN_CAMERA_TYPES

    def test_allowed_and_forbidden_camera_types_disjoint(self):
        from app.ai.camera.camera_apply_schema import (
            _ALLOWED_CAMERA_TYPES, _FORBIDDEN_CAMERA_TYPES,
        )
        assert _ALLOWED_CAMERA_TYPES.isdisjoint(_FORBIDDEN_CAMERA_TYPES)

    def test_forbidden_change_keys_include_crop(self):
        from app.ai.camera.camera_apply_schema import _FORBIDDEN_CHANGE_KEYS
        for k in ("crop_x", "crop_y", "crop_w", "crop_h", "crop_coordinates",
                  "ffmpeg_filter", "ffmpeg_args", "zoom_curve_points",
                  "direct_transform", "playback_speed",
                  "segment_start", "segment_end", "segment_order", "output_path"):
            assert k in _FORBIDDEN_CHANGE_KEYS


# ── Safety gate tests ─────────────────────────────────────────────────────────

class TestCameraApplySafety:
    def test_safe_candidate_passes(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        assert is_camera_motion_apply_safe(_safe_candidate()) is True

    def test_direct_crop_coordinate_rewrite_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(camera_type="direct_crop_coordinate_rewrite")
        assert is_camera_motion_apply_safe(c) is False

    def test_ffmpeg_filter_rewrite_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(camera_type="ffmpeg_filter_rewrite")
        assert is_camera_motion_apply_safe(c) is False

    def test_arbitrary_zoom_curve_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(camera_type="arbitrary_zoom_curve")
        assert is_camera_motion_apply_safe(c) is False

    def test_unsafe_subject_jump_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(camera_type="unsafe_subject_jump")
        assert is_camera_motion_apply_safe(c) is False

    def test_scene_reorder_camera_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(camera_type="scene_reorder_camera")
        assert is_camera_motion_apply_safe(c) is False

    def test_unknown_type_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(camera_type="totally_unknown_type")
        assert is_camera_motion_apply_safe(c) is False

    def test_low_confidence_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(confidence=0.50)
        assert is_camera_motion_apply_safe(c) is False

    def test_confidence_at_threshold_passes(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(confidence=0.65)
        assert is_camera_motion_apply_safe(c) is True

    def test_forbidden_change_key_crop_x_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(changes={"crop_x": 100, "camera_behavior": "auto"})
        assert is_camera_motion_apply_safe(c) is False

    def test_forbidden_change_key_ffmpeg_args_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(changes={"ffmpeg_args": "-vf x"})
        assert is_camera_motion_apply_safe(c) is False

    def test_forbidden_change_key_playback_speed_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(changes={"playback_speed": 2.0})
        assert is_camera_motion_apply_safe(c) is False

    def test_forbidden_change_key_zoom_curve_points_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(changes={"zoom_curve_points": [[0, 1], [1, 2]]})
        assert is_camera_motion_apply_safe(c) is False

    def test_non_metadata_scope_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(target_scope="file")
        assert is_camera_motion_apply_safe(c) is False

    def test_ffmpeg_scope_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(target_scope="ffmpeg")
        assert is_camera_motion_apply_safe(c) is False

    def test_empty_changes_after_sanitization_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(changes={})
        assert is_camera_motion_apply_safe(c) is False

    def test_only_forbidden_keys_in_changes_rejected(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        c = _safe_candidate(changes={"crop_x": 0, "crop_y": 0})
        assert is_camera_motion_apply_safe(c) is False

    def test_never_raises_on_none(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        assert is_camera_motion_apply_safe(None) is False  # type: ignore

    def test_never_raises_on_empty(self):
        from app.ai.camera.camera_apply_safety import is_camera_motion_apply_safe
        assert is_camera_motion_apply_safe({}) is False

    def test_sanitize_strips_forbidden_keys(self):
        from app.ai.camera.camera_apply_safety import sanitize_camera_motion_changes
        result = sanitize_camera_motion_changes({
            "camera_behavior": "fast_follow",
            "crop_x": 100,
            "ffmpeg_args": "-x",
            "beat_pulse_strength": 0.2,
        })
        assert "crop_x" not in result
        assert "ffmpeg_args" not in result
        assert "camera_behavior" in result
        assert result["beat_pulse_strength"] == 0.2

    def test_sanitize_clamps_beat_pulse_strength_max(self):
        from app.ai.camera.camera_apply_safety import sanitize_camera_motion_changes
        result = sanitize_camera_motion_changes({"beat_pulse_strength": 5.0})
        assert result["beat_pulse_strength"] == 0.35

    def test_sanitize_clamps_beat_pulse_strength_min(self):
        from app.ai.camera.camera_apply_safety import sanitize_camera_motion_changes
        result = sanitize_camera_motion_changes({"beat_pulse_strength": -1.0})
        assert result["beat_pulse_strength"] == 0.0

    def test_sanitize_clamps_max_camera_intensity(self):
        from app.ai.camera.camera_apply_safety import sanitize_camera_motion_changes
        result = sanitize_camera_motion_changes({"max_camera_intensity": 99.0})
        assert result["max_camera_intensity"] == 1.0

    def test_sanitize_strips_unknown_keys(self):
        from app.ai.camera.camera_apply_safety import sanitize_camera_motion_changes
        result = sanitize_camera_motion_changes({"some_unknown_key": "value"})
        assert result == {}

    def test_sanitize_never_raises(self):
        from app.ai.camera.camera_apply_safety import sanitize_camera_motion_changes
        assert sanitize_camera_motion_changes(None) == {}  # type: ignore
        assert sanitize_camera_motion_changes("bad") == {}  # type: ignore
        assert sanitize_camera_motion_changes(42) == {}  # type: ignore


# ── Engine tests ──────────────────────────────────────────────────────────────

class TestCameraApplyEngine:
    def test_never_raises_on_none(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        result = build_camera_motion_apply_pack(None)
        assert result is not None

    def test_never_raises_on_empty(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        result = build_camera_motion_apply_pack({})
        assert result is not None

    def test_disabled_by_default(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        result = build_camera_motion_apply_pack(plan)
        assert result.enabled is False
        assert result.mode == "disabled"

    def test_conservative_policy_blocks(self):
        pack = _build_pack_with_policy("conservative")
        assert pack.enabled is False

    def test_balanced_policy_allows(self):
        pack = _build_pack_with_policy("balanced")
        assert pack.enabled is True

    def test_aggressive_policy_allows(self):
        pack = _build_pack_with_policy("aggressive")
        assert pack.enabled is True

    def test_experimental_policy_allows(self):
        pack = _build_pack_with_policy("experimental")
        assert pack.enabled is True

    def test_invalid_policy_disables(self):
        pack = _build_pack_with_policy("invalid_mode")
        assert pack.enabled is False

    def test_camera_plan_subtitle_safe_produces_candidate(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        from app.ai.director.edit_plan_schema import AICameraPlan
        plan = _make_plan()
        plan.camera = AICameraPlan(mode="auto", subtitle_safe=True)
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        types = [a.camera_type for a in pack.applied]
        assert "subtitle_safe_framing" in types

    def test_beat_visual_execution_produces_candidate(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        plan.beat_visual_execution = {
            "available": True,
            "pulse_regions": [{"start": 0.0, "end": 5.0}],
            "pulse_strength": 0.25,
            "bpm": 120,
        }
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        types = [a.camera_type for a in pack.applied]
        assert "beat_aware_pulse" in types

    def test_beat_pulse_strength_clamped_in_applied(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        plan.beat_visual_execution = {
            "available": True,
            "pulse_regions": [{"start": 0.0, "end": 5.0}],
            "pulse_strength": 99.0,  # way too high
            "bpm": 120,
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            if a.camera_type == "beat_aware_pulse":
                assert a.changes.get("beat_pulse_strength", 0) <= 0.35

    def test_forbidden_camera_type_not_applied(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert a.camera_type != "direct_crop_coordinate_rewrite"

    def test_no_payload_in_place_mutation(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack

        class FakePayload:
            ai_apply_policy = "balanced"
            playback_speed = 1.0
            crop_x = 0

        plan = _make_plan()
        payload = FakePayload()
        original_speed = payload.playback_speed
        original_crop = payload.crop_x
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        build_camera_motion_apply_pack(plan, payload=payload, context=ctx)
        assert payload.playback_speed == original_speed
        assert payload.crop_x == original_crop

    def test_no_crop_coordinate_in_applied_changes(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        from app.ai.camera.camera_apply_schema import _FORBIDDEN_CHANGE_KEYS
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            for k in a.changes:
                assert k not in _FORBIDDEN_CHANGE_KEYS

    def test_no_playback_speed_in_applied_changes(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert "playback_speed" not in a.changes

    def test_no_ffmpeg_mutation(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert "ffmpeg_args" not in a.changes
            assert "ffmpeg_filter" not in a.changes

    def test_no_segment_reorder(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert a.target_scope == "metadata"
            assert "segment_order" not in a.changes

    def test_deterministic_same_inputs(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        r1 = build_camera_motion_apply_pack(plan, context=ctx)
        r2 = build_camera_motion_apply_pack(plan, context=ctx)
        assert r1.to_dict() == r2.to_dict()

    def test_no_api_key_no_gpu_no_internet(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        result = build_camera_motion_apply_pack(plan)
        assert result is not None

    def test_to_dict_round_trip(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        d = pack.to_dict()
        assert isinstance(d, dict)
        assert "enabled" in d
        assert "applied" in d
        assert "blocked" in d


# ── Edit plan schema tests ────────────────────────────────────────────────────

class TestEditPlanSchemaPhase34:
    def test_camera_motion_apply_field_exists(self):
        plan = _make_plan()
        assert hasattr(plan, "camera_motion_apply")
        assert isinstance(plan.camera_motion_apply, dict)

    def test_camera_motion_apply_defaults_empty(self):
        plan = _make_plan()
        assert plan.camera_motion_apply == {}

    def test_to_dict_includes_camera_motion_apply(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "camera_motion_apply" in d

    def test_all_prior_fields_still_present(self):
        plan = _make_plan()
        d = plan.to_dict()
        for key in (
            "enabled", "mode", "selected_segments", "subtitle", "camera",
            "warnings", "fallback_used", "pacing", "explainability",
            "beat_execution", "story", "creator_style", "retention",
            "subtitle_execution", "timing_mutation", "variants",
            "ai_apply_policy", "timing_apply", "subtitle_text_apply",
            "camera_motion_apply",
        ):
            assert key in d, f"Missing key: {key}"

    def test_populated_camera_motion_apply_in_to_dict(self):
        plan = _make_plan()
        plan.camera_motion_apply = {
            "enabled": True,
            "mode": "active",
            "applied": [{"apply_id": "a1", "camera_type": "dynamic_safe"}],
        }
        d = plan.to_dict()
        assert d["camera_motion_apply"]["enabled"] is True


# ── Render influence tests ────────────────────────────────────────────────────

class TestRenderInfluencePhase34:
    def _apply(self, camera_motion_apply_dict=None):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePayload:
            motion_aware_crop = False
            add_subtitle = False

        class FakeEditPlan:
            camera = None
            subtitle = None
            pacing = None
            memory_context = {}
            camera_motion_apply = camera_motion_apply_dict or {}
            subtitle_text_apply = {}
            timing_apply = {}
            beat_visual_execution = {}
            timing_mutation = {}
            story_optimization = {}
            variants = {}
            variant_selection = {}
            render_decision_preview = {}
            execution_recommendations = {}
            execution_simulation = {}
            safe_render_mutations = {}
            multivariant_render_plans = {}
            multivariant_execution = {}
            output_ranking = {}
            ai_apply_policy = {}
            explainability = {}

        return apply_ai_render_influence(FakePayload(), FakeEditPlan())

    def test_no_result_goes_to_skipped(self):
        _, report = self._apply({})
        assert any("camera_motion_apply" in s for s in report["skipped"])

    def test_disabled_pack_goes_to_skipped(self):
        _, report = self._apply({
            "enabled": False, "mode": "disabled",
            "applied": [], "blocked": [],
        })
        assert any("camera_motion_apply:disabled_phase34" in s for s in report["skipped"])

    def test_disabled_reports_crop_rewrite_blocked(self):
        _, report = self._apply({
            "enabled": False, "mode": "disabled",
            "applied": [], "blocked": [],
        })
        assert any("direct_crop_coordinate_rewrite:always_blocked" in s for s in report["skipped"])

    def test_applied_goes_to_applied(self):
        _, report = self._apply({
            "enabled": True, "mode": "active",
            "applied": [
                {"apply_id": "a1", "camera_type": "subtitle_safe_framing",
                 "changes": {"subtitle_safe_framing": True}}
            ],
            "blocked": [],
        })
        assert any("camera_motion_apply:applied" in s for s in report["applied"])

    def test_blocked_goes_to_skipped(self):
        _, report = self._apply({
            "enabled": True, "mode": "active",
            "applied": [],
            "blocked": [
                {"apply_id": "b1", "camera_type": "direct_crop_coordinate_rewrite",
                 "warnings": ["forbidden_camera_type"]}
            ],
        })
        assert any("camera_motion_apply:blocked" in s for s in report["skipped"])

    def test_active_also_reports_crop_rewrite_blocked(self):
        _, report = self._apply({
            "enabled": True, "mode": "active",
            "applied": [{"apply_id": "a1", "camera_type": "dynamic_safe",
                         "changes": {"camera_behavior": "auto"}}],
            "blocked": [],
        })
        assert any("direct_crop_coordinate_rewrite:always_blocked" in s for s in report["skipped"])

    def test_never_raises_on_none_plan(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePayload:
            pass

        _, report = apply_ai_render_influence(FakePayload(), None)
        assert report is not None

    def test_payload_not_mutated(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePayload:
            motion_aware_crop = False
            add_subtitle = False
            playback_speed = 1.0
            crop_x = 0

        class FakeEditPlan:
            camera = None
            subtitle = None
            pacing = None
            memory_context = {}
            camera_motion_apply = {
                "enabled": True, "mode": "active",
                "applied": [{"apply_id": "a1", "camera_type": "subtitle_safe_framing",
                             "changes": {"subtitle_safe_framing": True}}],
                "blocked": [],
            }
            subtitle_text_apply = {}
            timing_apply = {}
            beat_visual_execution = {}
            timing_mutation = {}
            story_optimization = {}
            variants = {}
            variant_selection = {}
            render_decision_preview = {}
            execution_recommendations = {}
            execution_simulation = {}
            safe_render_mutations = {}
            multivariant_render_plans = {}
            multivariant_execution = {}
            output_ranking = {}
            ai_apply_policy = {}
            explainability = {}

        payload = FakePayload()
        apply_ai_render_influence(payload, FakeEditPlan())
        assert payload.playback_speed == 1.0
        assert payload.crop_x == 0


# ── End-to-end tests ──────────────────────────────────────────────────────────

class TestPhase34EndToEnd:
    def test_conservative_pack_disabled(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "conservative", "job_id": "t"}
        d = build_camera_motion_apply_pack(plan, context=ctx).to_dict()
        assert d["enabled"] is False
        assert d["mode"] == "disabled"

    def test_balanced_with_camera_plan(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        from app.ai.director.edit_plan_schema import AICameraPlan
        plan = _make_plan()
        plan.camera = AICameraPlan(mode="auto", subtitle_safe=True)
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        d = build_camera_motion_apply_pack(plan, context=ctx).to_dict()
        assert d["enabled"] is True
        assert d["mode"] == "active"
        assert len(d["applied"]) >= 1

    def test_all_applied_have_metadata_scope(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert a.target_scope == "metadata"

    def test_no_forbidden_change_keys_in_any_applied(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        from app.ai.camera.camera_apply_schema import _FORBIDDEN_CHANGE_KEYS
        plan = _make_plan()
        plan.beat_visual_execution = {
            "available": True,
            "pulse_regions": [{"start": 0.0, "end": 5.0}],
            "pulse_strength": 0.2,
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            for k in a.changes:
                assert k not in _FORBIDDEN_CHANGE_KEYS, f"Forbidden key {k!r} in applied changes"

    def test_all_forbidden_camera_types_never_applied(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        from app.ai.camera.camera_apply_schema import _FORBIDDEN_CAMERA_TYPES
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert a.camera_type not in _FORBIDDEN_CAMERA_TYPES

    def test_edit_plan_field_attached(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        plan.camera_motion_apply = pack.to_dict()
        d = plan.to_dict()
        assert "camera_motion_apply" in d
        assert d["camera_motion_apply"]["enabled"] is True

    def test_policy_never_raises(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        for policy in ("conservative", "balanced", "aggressive", "experimental",
                       "garbage", "", None):
            plan = _make_plan()
            ctx = {"ai_apply_policy": policy, "job_id": "t"}
            result = build_camera_motion_apply_pack(plan, context=ctx)
            assert result is not None

    def test_no_executor_override_possible(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_camera_motion_apply_pack(plan, context=ctx)
        d = pack.to_dict()
        assert "executor_override" not in d
        for a in d.get("applied", []):
            assert "executor_override" not in a

    def test_backward_compatibility_all_phases(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "camera_motion_apply" in d    # Phase 34
        assert "subtitle_text_apply" in d   # Phase 33
        assert "timing_apply" in d          # Phase 32
        assert "ai_apply_policy" in d       # Phase 31
        assert "output_ranking" in d        # Phase 30
        assert "timing_mutation" in d       # Phase 19
        assert "subtitle_execution" in d    # Phase 17

    def test_no_api_key_no_gpu_no_internet(self):
        from app.ai.camera.camera_apply_engine import build_camera_motion_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        result = build_camera_motion_apply_pack(plan, context=ctx)
        assert result is not None
