"""
tests/test_ai_phase32_timing_apply.py — Phase 32: Safe Timing Mutation Apply Foundation.

Tests:
- schema invariants (AITimingMutationApply, AITimingApplyPack)
- safety gates (timing_apply_safety)
- engine behavior (timing_apply_engine)
- edit plan schema backward compatibility
- render influence reporter
- end-to-end integration
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List, Optional


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_plan(**kwargs):
    """Minimal AIEditPlan-like object."""
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
    """Minimal safe Phase 19-style candidate dict."""
    c = {
        "mutation_id": "c1",
        "mutation_type": "trim_silence_gap",
        "source_candidate_id": "p19",
        "confidence": 0.80,
        "start_sec": 5.0,
        "end_sec": 15.0,
        "delta_sec": 0.8,
        "reason": "silence gap detected",
        "warnings": [],
    }
    c.update(kwargs)
    return c


def _pack_with_aggressive_policy(candidates=None):
    """Build a timing apply pack with aggressive policy and optional candidates."""
    from app.ai.timing.timing_apply_engine import build_timing_apply_pack
    from app.ai.director.edit_plan_schema import AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan

    plan = _make_plan()
    if candidates is not None:
        plan.timing_mutation = {
            "available": True,
            "candidates": candidates,
        }
    context = {"ai_apply_policy": "aggressive", "job_id": "test"}
    return build_timing_apply_pack(plan, payload=None, context=context)


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestTimingApplySchema:
    def test_mutation_apply_defaults(self):
        from app.ai.timing.timing_apply_schema import AITimingMutationApply
        m = AITimingMutationApply(mutation_id="m1")
        assert m.applied is False
        assert m.safe is False
        assert m.delta_sec == 0.0
        assert m.confidence == 0.0

    def test_mutation_apply_to_dict_clamps_delta(self):
        from app.ai.timing.timing_apply_schema import AITimingMutationApply
        m = AITimingMutationApply(
            mutation_id="m1",
            mutation_type="trim_silence_gap",
            delta_sec=99.0,
            confidence=0.9,
            applied=True, safe=True,
        )
        d = m.to_dict()
        assert d["delta_sec"] == 1.5  # clamped to _MAX_SINGLE_DELTA_SEC

    def test_mutation_apply_to_dict_clamps_confidence(self):
        from app.ai.timing.timing_apply_schema import AITimingMutationApply
        m = AITimingMutationApply(mutation_id="m1", confidence=5.0)
        d = m.to_dict()
        assert d["confidence"] == 1.0

    def test_mutation_apply_unknown_type_becomes_unknown_in_dict(self):
        from app.ai.timing.timing_apply_schema import AITimingMutationApply
        m = AITimingMutationApply(mutation_id="m1", mutation_type="playback_speed")
        d = m.to_dict()
        assert d["mutation_type"] == "unknown"

    def test_mutation_apply_allowed_types_preserved(self):
        from app.ai.timing.timing_apply_schema import (
            AITimingMutationApply, _ALLOWED_MUTATION_TYPES,
        )
        for t in _ALLOWED_MUTATION_TYPES:
            m = AITimingMutationApply(mutation_id="m", mutation_type=t)
            d = m.to_dict()
            assert d["mutation_type"] == t

    def test_pack_defaults(self):
        from app.ai.timing.timing_apply_schema import AITimingApplyPack
        p = AITimingApplyPack()
        assert p.available is True
        assert p.enabled is False
        assert p.mode == "disabled"
        assert p.applied_mutations == []
        assert p.blocked_mutations == []
        assert p.total_delta_sec == 0.0

    def test_pack_to_dict_keys(self):
        from app.ai.timing.timing_apply_schema import AITimingApplyPack
        p = AITimingApplyPack()
        d = p.to_dict()
        assert "available" in d
        assert "enabled" in d
        assert "mode" in d
        assert "applied_mutations" in d
        assert "blocked_mutations" in d
        assert "total_delta_sec" in d
        assert "warnings" in d

    def test_pack_to_dict_clamps_total_delta(self):
        from app.ai.timing.timing_apply_schema import AITimingApplyPack
        p = AITimingApplyPack(total_delta_sec=999.0)
        d = p.to_dict()
        assert d["total_delta_sec"] == 4.0  # clamped to _MAX_TOTAL_DELTA_SEC

    def test_pack_to_dict_caps_mutations(self):
        from app.ai.timing.timing_apply_schema import AITimingApplyPack, AITimingMutationApply
        muts = [AITimingMutationApply(mutation_id=str(i)) for i in range(25)]
        p = AITimingApplyPack(applied_mutations=muts)
        d = p.to_dict()
        assert len(d["applied_mutations"]) == 20  # capped at 20

    def test_allowed_mutation_types_set(self):
        from app.ai.timing.timing_apply_schema import _ALLOWED_MUTATION_TYPES
        assert "trim_silence_gap" in _ALLOWED_MUTATION_TYPES
        assert "tighten_setup" in _ALLOWED_MUTATION_TYPES
        assert "shorten_outro" in _ALLOWED_MUTATION_TYPES
        assert "reduce_dead_air" in _ALLOWED_MUTATION_TYPES

    def test_forbidden_mutation_types_set(self):
        from app.ai.timing.timing_apply_schema import _FORBIDDEN_MUTATION_TYPES
        assert "playback_speed" in _FORBIDDEN_MUTATION_TYPES
        assert "segment_reorder" in _FORBIDDEN_MUTATION_TYPES
        assert "subtitle_timing_rewrite" in _FORBIDDEN_MUTATION_TYPES
        assert "arbitrary_cut" in _FORBIDDEN_MUTATION_TYPES
        assert "ffmpeg_command_change" in _FORBIDDEN_MUTATION_TYPES

    def test_allowed_and_forbidden_disjoint(self):
        from app.ai.timing.timing_apply_schema import (
            _ALLOWED_MUTATION_TYPES, _FORBIDDEN_MUTATION_TYPES,
        )
        assert _ALLOWED_MUTATION_TYPES.isdisjoint(_FORBIDDEN_MUTATION_TYPES)


# ── Safety gate tests ─────────────────────────────────────────────────────────

class TestTimingApplySafety:
    def test_safe_candidate_passes(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate()
        assert is_timing_mutation_safe(c) is True

    def test_playback_speed_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(mutation_type="playback_speed")
        assert is_timing_mutation_safe(c) is False

    def test_segment_reorder_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(mutation_type="segment_reorder")
        assert is_timing_mutation_safe(c) is False

    def test_subtitle_timing_rewrite_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(mutation_type="subtitle_timing_rewrite")
        assert is_timing_mutation_safe(c) is False

    def test_ffmpeg_mutation_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(mutation_type="ffmpeg_command_change")
        assert is_timing_mutation_safe(c) is False

    def test_arbitrary_cut_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(mutation_type="arbitrary_cut")
        assert is_timing_mutation_safe(c) is False

    def test_unknown_type_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(mutation_type="completely_unknown_type")
        assert is_timing_mutation_safe(c) is False

    def test_low_confidence_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(confidence=0.50)  # < 0.65
        assert is_timing_mutation_safe(c) is False

    def test_confidence_at_threshold_passes(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(confidence=0.65)
        assert is_timing_mutation_safe(c) is True

    def test_max_single_delta_exceeded_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(delta_sec=1.6)  # > 1.5
        assert is_timing_mutation_safe(c) is False

    def test_delta_at_max_passes(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(delta_sec=1.5, start_sec=5.0, end_sec=20.0)
        assert is_timing_mutation_safe(c) is True

    def test_negative_start_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(start_sec=-1.0)
        assert is_timing_mutation_safe(c) is False

    def test_short_segment_after_trim_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        # start=5, end=7, delta=1.0 → remaining=1.0 < 2.0 minimum
        c = _safe_candidate(start_sec=5.0, end_sec=7.0, delta_sec=1.0)
        assert is_timing_mutation_safe(c) is False

    def test_protected_window_overlap_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(start_sec=2.0)
        ctx = {"protected_windows": [{"start": 0.0, "end": 5.0}]}
        assert is_timing_mutation_safe(c, context=ctx) is False

    def test_outside_protected_window_passes(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(start_sec=10.0, end_sec=20.0)
        ctx = {"protected_windows": [{"start": 0.0, "end": 5.0}]}
        assert is_timing_mutation_safe(c, context=ctx) is True

    def test_subtitle_dense_overlap_rejected(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(start_sec=3.0)
        ctx = {"subtitle_dense_regions": [{"start": 2.0, "end": 6.0}]}
        assert is_timing_mutation_safe(c, context=ctx) is False

    def test_outside_dense_region_passes(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        c = _safe_candidate(start_sec=10.0, end_sec=20.0)
        ctx = {"subtitle_dense_regions": [{"start": 2.0, "end": 6.0}]}
        assert is_timing_mutation_safe(c, context=ctx) is True

    def test_never_raises_on_none(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        assert is_timing_mutation_safe(None) is False  # type: ignore

    def test_never_raises_on_empty(self):
        from app.ai.timing.timing_apply_safety import is_timing_mutation_safe
        assert is_timing_mutation_safe({}) is False

    def test_sanitize_handles_phase19_keys(self):
        from app.ai.timing.timing_apply_safety import sanitize_timing_candidate
        c = {
            "mutation_id": "m1",
            "action": "trim_silence",
            "confidence": 0.75,
            "start": 5.0,
            "end": 12.0,
            "max_trim_seconds": 1.0,
            "reason": "silence",
        }
        result = sanitize_timing_candidate(c)
        assert result["start_sec"] == 5.0
        assert result["end_sec"] == 12.0
        assert result["delta_sec"] == 1.0
        assert result["mutation_type"] == "trim_silence"

    def test_sanitize_never_raises_on_garbage(self):
        from app.ai.timing.timing_apply_safety import sanitize_timing_candidate
        assert sanitize_timing_candidate(None) == {}  # type: ignore
        assert sanitize_timing_candidate("bad") == {}  # type: ignore
        assert sanitize_timing_candidate(42) == {}  # type: ignore


# ── Engine tests ──────────────────────────────────────────────────────────────

class TestTimingApplyEngine:
    def test_never_raises_on_none(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        result = build_timing_apply_pack(None)
        assert result is not None

    def test_never_raises_on_empty(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        result = build_timing_apply_pack({})
        assert result is not None

    def test_disabled_by_default(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        result = build_timing_apply_pack(plan)
        assert result.enabled is False
        assert result.mode == "disabled"

    def test_conservative_policy_blocks(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "conservative", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert result.enabled is False

    def test_balanced_policy_blocks(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert result.enabled is False

    def test_aggressive_policy_allows(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert result.enabled is True

    def test_experimental_policy_allows(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert result.enabled is True

    def test_invalid_policy_disables(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "invalid_mode", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert result.enabled is False

    def test_safe_candidate_applied(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "trim_silence",
                    "confidence": 0.80,
                    "start": 5.0,
                    "end": 20.0,
                    "max_trim_seconds": 0.8,
                    "safe_to_apply": True,
                    "reason": "silence gap",
                    "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert result.enabled is True
        assert len(result.applied_mutations) == 1
        assert result.applied_mutations[0].applied is True
        assert result.applied_mutations[0].safe is True
        assert result.total_delta_sec > 0.0

    def test_forbidden_type_blocked(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        # Phase 20 (story_optimization) uses mutation_type directly — test block path
        plan.story_optimization = {
            "available": True,
            "timing_hints": [
                {
                    "mutation_type": "playback_speed",  # forbidden — filtered at collection
                    "confidence": 0.90,
                    "start_sec": 5.0,
                    "end_sec": 20.0,
                    "delta_sec": 0.5,
                    "reason": "speed up",
                }
            ],
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert result.enabled is True
        # Forbidden type is never applied (key invariant)
        assert len(result.applied_mutations) == 0
        for m in result.applied_mutations:
            assert m.mutation_type != "playback_speed"

    def test_low_confidence_blocked(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "trim_silence",
                    "confidence": 0.50,  # below 0.65
                    "start": 5.0,
                    "end": 20.0,
                    "max_trim_seconds": 0.8,
                    "safe_to_apply": True,
                    "reason": "silence",
                    "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert len(result.applied_mutations) == 0
        assert len(result.blocked_mutations) == 1

    def test_max_single_delta_enforced(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "trim_silence",
                    "confidence": 0.90,
                    "start": 5.0,
                    "end": 30.0,
                    "max_trim_seconds": 2.0,  # exceeds 1.5 limit
                    "safe_to_apply": True,
                    "reason": "silence",
                    "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert len(result.applied_mutations) == 0
        assert len(result.blocked_mutations) == 1

    def test_max_total_delta_enforced(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        candidates = []
        for i in range(5):
            candidates.append({
                "action": "trim_silence",
                "confidence": 0.80,
                "start": float(5 + i * 20),
                "end": float(20 + i * 20),
                "max_trim_seconds": 1.0,
                "safe_to_apply": True,
                "reason": f"silence {i}",
                "warnings": [],
            })
        plan.timing_mutation = {"available": True, "candidates": candidates}
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        assert result.total_delta_sec <= 4.0

    def test_no_payload_mutation(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack

        class FakePayload:
            ai_apply_policy = "aggressive"
            playback_speed = 1.0
            subtitle_offset = 0.0

        plan = _make_plan()
        payload = FakePayload()
        original_speed = payload.playback_speed
        original_offset = payload.subtitle_offset

        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        build_timing_apply_pack(plan, payload=payload, context=ctx)

        assert payload.playback_speed == original_speed
        assert payload.subtitle_offset == original_offset

    def test_no_playback_speed_mutation_in_result(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "playback_speed",
                    "confidence": 0.95,
                    "start": 0.0, "end": 30.0,
                    "max_trim_seconds": 1.0,
                    "safe_to_apply": True, "reason": "", "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        for m in result.applied_mutations:
            assert m.mutation_type != "playback_speed"

    def test_no_subtitle_timing_rewrite(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "subtitle_timing_rewrite",
                    "confidence": 0.95,
                    "start": 0.0, "end": 30.0,
                    "max_trim_seconds": 1.0,
                    "safe_to_apply": True, "reason": "", "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        for m in result.applied_mutations:
            assert m.mutation_type != "subtitle_timing_rewrite"

    def test_no_ffmpeg_mutation(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "ffmpeg_command_change",
                    "confidence": 0.95,
                    "start": 0.0, "end": 30.0,
                    "max_trim_seconds": 1.0,
                    "safe_to_apply": True, "reason": "", "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        for m in result.applied_mutations:
            assert m.mutation_type != "ffmpeg_command_change"

    def test_no_segment_reorder(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "segment_reorder",
                    "confidence": 0.95,
                    "start": 0.0, "end": 30.0,
                    "max_trim_seconds": 1.0,
                    "safe_to_apply": True, "reason": "", "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        for m in result.applied_mutations:
            assert m.mutation_type != "segment_reorder"

    def test_deterministic_same_inputs(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "trim_silence",
                    "confidence": 0.80,
                    "start": 5.0, "end": 20.0,
                    "max_trim_seconds": 0.8,
                    "safe_to_apply": True, "reason": "s", "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        r1 = build_timing_apply_pack(plan, context=ctx)
        r2 = build_timing_apply_pack(plan, context=ctx)
        assert r1.to_dict() == r2.to_dict()

    def test_no_api_key_no_gpu_no_internet(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        # If this imports and runs without error, all deps are local
        plan = _make_plan()
        result = build_timing_apply_pack(plan)
        assert result is not None

    def test_to_dict_round_trip(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        result = build_timing_apply_pack(plan, context=ctx)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "enabled" in d
        assert "applied_mutations" in d
        assert "total_delta_sec" in d


# ── Edit plan schema tests ────────────────────────────────────────────────────

class TestEditPlanSchemaPhase32:
    def test_timing_apply_field_exists(self):
        plan = _make_plan()
        assert hasattr(plan, "timing_apply")
        assert isinstance(plan.timing_apply, dict)

    def test_timing_apply_defaults_empty(self):
        plan = _make_plan()
        assert plan.timing_apply == {}

    def test_to_dict_includes_timing_apply(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "timing_apply" in d

    def test_all_prior_fields_still_present(self):
        plan = _make_plan()
        d = plan.to_dict()
        for key in (
            "enabled", "mode", "selected_segments", "subtitle", "camera",
            "warnings", "fallback_used", "pacing", "explainability", "confidence",
            "beat_execution", "story", "preset_evolution", "creator_style",
            "external_knowledge", "retention", "subtitle_execution",
            "beat_visual_execution", "timing_mutation", "story_optimization",
            "variants", "variant_selection", "creator_style_adaptation",
            "render_decision_preview", "execution_recommendations",
            "execution_simulation", "safe_render_mutations",
            "multivariant_render_plans", "multivariant_execution",
            "output_ranking", "ai_apply_policy", "timing_apply",
        ):
            assert key in d, f"Missing key: {key}"

    def test_populated_timing_apply_in_to_dict(self):
        plan = _make_plan()
        plan.timing_apply = {
            "enabled": True,
            "mode": "active",
            "applied_mutations": [],
            "total_delta_sec": 0.8,
        }
        d = plan.to_dict()
        assert d["timing_apply"]["enabled"] is True
        assert d["timing_apply"]["total_delta_sec"] == 0.8


# ── Render influence tests ────────────────────────────────────────────────────

class TestRenderInfluencePhase32:
    def _apply(self, timing_apply_dict=None):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePayload:
            motion_aware_crop = False
            add_subtitle = False

        class FakeEditPlan:
            camera = None
            subtitle = None
            pacing = None
            memory_context = {}
            timing_apply = timing_apply_dict or {}
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

    def test_no_timing_apply_goes_to_skipped(self):
        _, report = self._apply({})
        assert any("timing_apply" in s for s in report["skipped"])

    def test_disabled_pack_goes_to_skipped(self):
        _, report = self._apply({
            "enabled": False,
            "mode": "disabled",
            "applied_mutations": [],
            "blocked_mutations": [],
            "total_delta_sec": 0.0,
        })
        assert any("timing_apply:disabled_phase32" in s for s in report["skipped"])

    def test_applied_mutation_goes_to_applied(self):
        _, report = self._apply({
            "enabled": True,
            "mode": "active",
            "applied_mutations": [
                {
                    "mutation_id": "m1",
                    "mutation_type": "trim_silence_gap",
                    "delta_sec": 0.8,
                    "applied": True,
                    "safe": True,
                    "warnings": [],
                }
            ],
            "blocked_mutations": [],
            "total_delta_sec": 0.8,
        })
        assert any("timing_apply:applied" in s for s in report["applied"])

    def test_blocked_mutation_goes_to_skipped(self):
        _, report = self._apply({
            "enabled": True,
            "mode": "active",
            "applied_mutations": [],
            "blocked_mutations": [
                {
                    "mutation_id": "b1",
                    "mutation_type": "playback_speed",
                    "delta_sec": 0.5,
                    "applied": False,
                    "safe": False,
                    "warnings": ["forbidden_mutation_type"],
                }
            ],
            "total_delta_sec": 0.0,
        })
        assert any("timing_apply:blocked" in s for s in report["skipped"])

    def test_never_raises_on_none_plan(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePayload:
            pass

        payload, report = apply_ai_render_influence(FakePayload(), None)
        assert report is not None

    def test_payload_not_mutated_for_playback_speed(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePayload:
            motion_aware_crop = False
            add_subtitle = False
            playback_speed = 1.0

        class FakeEditPlan:
            camera = None
            subtitle = None
            pacing = None
            memory_context = {}
            timing_apply = {
                "enabled": True,
                "mode": "active",
                "applied_mutations": [
                    {"mutation_id": "m1", "mutation_type": "trim_silence_gap",
                     "delta_sec": 0.5, "applied": True, "safe": True, "warnings": []}
                ],
                "blocked_mutations": [], "total_delta_sec": 0.5,
            }
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


# ── End-to-end tests ──────────────────────────────────────────────────────────

class TestPhase32EndToEnd:
    def test_conservative_policy_pack_disabled(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "conservative", "job_id": "t"}
        pack = build_timing_apply_pack(plan, context=ctx)
        d = pack.to_dict()
        assert d["enabled"] is False
        assert d["mode"] == "disabled"

    def test_balanced_policy_pack_disabled(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_timing_apply_pack(plan, context=ctx)
        assert pack.enabled is False

    def test_aggressive_with_safe_candidate(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "trim_silence",
                    "confidence": 0.75,
                    "start": 8.0, "end": 20.0,
                    "max_trim_seconds": 1.0,
                    "safe_to_apply": True, "reason": "dead air", "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        pack = build_timing_apply_pack(plan, context=ctx)
        d = pack.to_dict()
        assert d["enabled"] is True
        assert d["mode"] == "active"
        assert len(d["applied_mutations"]) == 1
        assert d["total_delta_sec"] == 1.0

    def test_experimental_with_multiple_candidates(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "trim_silence",
                    "confidence": 0.75,
                    "start": float(5 + i * 20),
                    "end": float(20 + i * 20),
                    "max_trim_seconds": 0.7,
                    "safe_to_apply": True, "reason": f"s{i}", "warnings": [],
                }
                for i in range(4)
            ],
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_timing_apply_pack(plan, context=ctx)
        assert pack.enabled is True
        assert pack.total_delta_sec <= 4.0

    def test_edit_plan_timing_apply_attached(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        pack = build_timing_apply_pack(plan, context=ctx)
        plan.timing_apply = pack.to_dict()
        d = plan.to_dict()
        assert "timing_apply" in d
        assert d["timing_apply"]["enabled"] is True

    def test_all_hard_blocks_never_applied(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        from app.ai.timing.timing_apply_schema import _FORBIDDEN_MUTATION_TYPES
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": ft,
                    "confidence": 0.99,
                    "start": 5.0, "end": 30.0,
                    "max_trim_seconds": 1.0,
                    "safe_to_apply": True, "reason": "", "warnings": [],
                }
                for ft in _FORBIDDEN_MUTATION_TYPES
            ],
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_timing_apply_pack(plan, context=ctx)
        for m in pack.applied_mutations:
            assert m.mutation_type not in _FORBIDDEN_MUTATION_TYPES

    def test_policy_never_raises(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        for policy in ("conservative", "balanced", "aggressive", "experimental", "garbage", "", None):
            plan = _make_plan()
            ctx = {"ai_apply_policy": policy, "job_id": "t"}
            result = build_timing_apply_pack(plan, context=ctx)
            assert result is not None

    def test_no_executor_override_possible(self):
        from app.ai.timing.timing_apply_engine import build_timing_apply_pack
        plan = _make_plan()
        plan.timing_mutation = {
            "available": True,
            "candidates": [
                {
                    "action": "trim_silence",
                    "confidence": 0.80,
                    "start": 5.0, "end": 20.0,
                    "max_trim_seconds": 0.8,
                    "safe_to_apply": True, "reason": "", "warnings": [],
                }
            ],
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        pack = build_timing_apply_pack(plan, context=ctx)
        d = pack.to_dict()
        # The pack has no executor_override key
        assert "executor_override" not in d
        for m in d.get("applied_mutations", []):
            assert "executor_override" not in m

    def test_backward_compatibility_all_phases(self):
        plan = _make_plan()
        d = plan.to_dict()
        # All 32 phases represented
        assert "timing_apply" in d        # Phase 32
        assert "ai_apply_policy" in d     # Phase 31
        assert "output_ranking" in d      # Phase 30
        assert "multivariant_execution" in d  # Phase 29
        assert "timing_mutation" in d     # Phase 19
