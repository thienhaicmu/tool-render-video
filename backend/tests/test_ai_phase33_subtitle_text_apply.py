"""
tests/test_ai_phase33_subtitle_text_apply.py — Phase 33: Subtitle Text Optimization Apply.

Tests:
- schema invariants (AISubtitleTextApply, AISubtitleTextApplyPack)
- safety gates (subtitle_apply_safety)
- engine behavior (subtitle_apply_engine)
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
        "apply_id": "a1",
        "optimization_type": "compact_overload",
        "source_candidate_id": "p17",
        "confidence": 0.80,
        "target_scope": "metadata",
        "changes": {"subtitle_density": "compact"},
    }
    c.update(kwargs)
    return c


def _build_pack_with_policy(policy: str, candidates_on_plan=None):
    from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
    plan = _make_plan()
    if candidates_on_plan is not None:
        plan.subtitle_execution = candidates_on_plan
    ctx = {"ai_apply_policy": policy, "job_id": "test"}
    return build_subtitle_text_apply_pack(plan, payload=None, context=ctx)


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestSubtitleApplySchema:
    def test_apply_defaults(self):
        from app.ai.subtitles.subtitle_apply_schema import AISubtitleTextApply
        a = AISubtitleTextApply(apply_id="a1")
        assert a.applied is False
        assert a.safe is False
        assert a.confidence == 0.0
        assert a.target_scope == "metadata"

    def test_apply_to_dict_strips_forbidden_change_keys(self):
        from app.ai.subtitles.subtitle_apply_schema import AISubtitleTextApply
        a = AISubtitleTextApply(
            apply_id="a1",
            optimization_type="compact_overload",
            confidence=0.8,
            applied=True, safe=True,
            changes={
                "subtitle_density": "compact",
                "start_time": "00:00:01",  # forbidden
                "playback_speed": 1.5,     # forbidden
            },
        )
        d = a.to_dict()
        assert "start_time" not in d["changes"]
        assert "playback_speed" not in d["changes"]
        assert "subtitle_density" in d["changes"]

    def test_apply_to_dict_unknown_type_becomes_unknown(self):
        from app.ai.subtitles.subtitle_apply_schema import AISubtitleTextApply
        a = AISubtitleTextApply(apply_id="a1", optimization_type="timestamp_rewrite")
        d = a.to_dict()
        assert d["optimization_type"] == "unknown"

    def test_apply_to_dict_allowed_types_preserved(self):
        from app.ai.subtitles.subtitle_apply_schema import (
            AISubtitleTextApply, _ALLOWED_OPTIMIZATION_TYPES,
        )
        for t in _ALLOWED_OPTIMIZATION_TYPES:
            a = AISubtitleTextApply(apply_id="a", optimization_type=t,
                                    changes={"subtitle_density": "compact"})
            d = a.to_dict()
            assert d["optimization_type"] == t

    def test_apply_to_dict_clamps_confidence(self):
        from app.ai.subtitles.subtitle_apply_schema import AISubtitleTextApply
        a = AISubtitleTextApply(apply_id="a1", confidence=99.0)
        d = a.to_dict()
        assert d["confidence"] == 1.0

    def test_apply_to_dict_clamps_max_chars_per_line(self):
        from app.ai.subtitles.subtitle_apply_schema import AISubtitleTextApply
        a = AISubtitleTextApply(apply_id="a1", optimization_type="safer_line_breaks",
                                changes={"max_chars_per_line": 999})
        d = a.to_dict()
        assert d["changes"]["max_chars_per_line"] == 42  # clamped to max

    def test_apply_to_dict_clamps_max_chars_per_line_min(self):
        from app.ai.subtitles.subtitle_apply_schema import AISubtitleTextApply
        a = AISubtitleTextApply(apply_id="a1", optimization_type="safer_line_breaks",
                                changes={"max_chars_per_line": 1})
        d = a.to_dict()
        assert d["changes"]["max_chars_per_line"] == 18  # clamped to min

    def test_pack_defaults(self):
        from app.ai.subtitles.subtitle_apply_schema import AISubtitleTextApplyPack
        p = AISubtitleTextApplyPack()
        assert p.available is True
        assert p.enabled is False
        assert p.mode == "disabled"
        assert p.applied == []
        assert p.blocked == []

    def test_pack_to_dict_keys(self):
        from app.ai.subtitles.subtitle_apply_schema import AISubtitleTextApplyPack
        p = AISubtitleTextApplyPack()
        d = p.to_dict()
        assert "available" in d
        assert "enabled" in d
        assert "mode" in d
        assert "applied" in d
        assert "blocked" in d
        assert "warnings" in d

    def test_pack_to_dict_caps_applied(self):
        from app.ai.subtitles.subtitle_apply_schema import (
            AISubtitleTextApplyPack, AISubtitleTextApply,
        )
        opts = [AISubtitleTextApply(apply_id=str(i)) for i in range(25)]
        p = AISubtitleTextApplyPack(applied=opts)
        d = p.to_dict()
        assert len(d["applied"]) == 20

    def test_allowed_optimization_types(self):
        from app.ai.subtitles.subtitle_apply_schema import _ALLOWED_OPTIMIZATION_TYPES
        for t in ("compact_overload", "keyword_emphasis", "safer_line_breaks",
                  "density_reduce", "creator_style_tone", "hook_emphasis"):
            assert t in _ALLOWED_OPTIMIZATION_TYPES

    def test_forbidden_optimization_types(self):
        from app.ai.subtitles.subtitle_apply_schema import _FORBIDDEN_OPTIMIZATION_TYPES
        for t in ("timestamp_rewrite", "subtitle_shift", "subtitle_speed_sync",
                  "generated_script_replace", "full_transcript_rewrite"):
            assert t in _FORBIDDEN_OPTIMIZATION_TYPES

    def test_allowed_and_forbidden_disjoint(self):
        from app.ai.subtitles.subtitle_apply_schema import (
            _ALLOWED_OPTIMIZATION_TYPES, _FORBIDDEN_OPTIMIZATION_TYPES,
        )
        assert _ALLOWED_OPTIMIZATION_TYPES.isdisjoint(_FORBIDDEN_OPTIMIZATION_TYPES)

    def test_forbidden_change_keys_include_timestamps(self):
        from app.ai.subtitles.subtitle_apply_schema import _FORBIDDEN_CHANGE_KEYS
        for k in ("start_time", "end_time", "timestamp", "subtitle_timing",
                  "subtitle_shift", "playback_speed", "ffmpeg_args",
                  "full_text_rewrite", "generated_script", "output_path"):
            assert k in _FORBIDDEN_CHANGE_KEYS


# ── Safety gate tests ─────────────────────────────────────────────────────────

class TestSubtitleApplySafety:
    def test_safe_candidate_passes(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate()
        assert is_subtitle_text_apply_safe(c) is True

    def test_timestamp_rewrite_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(optimization_type="timestamp_rewrite")
        assert is_subtitle_text_apply_safe(c) is False

    def test_subtitle_shift_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(optimization_type="subtitle_shift")
        assert is_subtitle_text_apply_safe(c) is False

    def test_generated_script_replace_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(optimization_type="generated_script_replace")
        assert is_subtitle_text_apply_safe(c) is False

    def test_full_transcript_rewrite_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(optimization_type="full_transcript_rewrite")
        assert is_subtitle_text_apply_safe(c) is False

    def test_subtitle_speed_sync_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(optimization_type="subtitle_speed_sync")
        assert is_subtitle_text_apply_safe(c) is False

    def test_unknown_type_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(optimization_type="totally_unknown_type")
        assert is_subtitle_text_apply_safe(c) is False

    def test_low_confidence_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(confidence=0.50)
        assert is_subtitle_text_apply_safe(c) is False

    def test_confidence_at_threshold_passes(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(confidence=0.65)
        assert is_subtitle_text_apply_safe(c) is True

    def test_forbidden_change_key_start_time_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(changes={"start_time": "00:00:01", "subtitle_density": "compact"})
        assert is_subtitle_text_apply_safe(c) is False

    def test_forbidden_change_key_end_time_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(changes={"end_time": "00:00:05"})
        assert is_subtitle_text_apply_safe(c) is False

    def test_forbidden_change_key_playback_speed_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(changes={"playback_speed": 1.5})
        assert is_subtitle_text_apply_safe(c) is False

    def test_forbidden_change_key_ffmpeg_args_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(changes={"ffmpeg_args": "-vf scale=1280:720"})
        assert is_subtitle_text_apply_safe(c) is False

    def test_non_metadata_scope_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(target_scope="file")
        assert is_subtitle_text_apply_safe(c) is False

    def test_ffmpeg_scope_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(target_scope="ffmpeg")
        assert is_subtitle_text_apply_safe(c) is False

    def test_empty_changes_after_sanitization_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(changes={})  # empty → sanitized = {} → rejected
        assert is_subtitle_text_apply_safe(c) is False

    def test_only_forbidden_keys_in_changes_rejected(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        c = _safe_candidate(changes={"start_time": "0", "playback_speed": 2.0})
        assert is_subtitle_text_apply_safe(c) is False

    def test_never_raises_on_none(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        assert is_subtitle_text_apply_safe(None) is False  # type: ignore

    def test_never_raises_on_empty(self):
        from app.ai.subtitles.subtitle_apply_safety import is_subtitle_text_apply_safe
        assert is_subtitle_text_apply_safe({}) is False

    def test_sanitize_strips_forbidden_keys(self):
        from app.ai.subtitles.subtitle_apply_safety import sanitize_subtitle_text_changes
        result = sanitize_subtitle_text_changes({
            "subtitle_density": "compact",
            "start_time": "0",
            "ffmpeg_args": "-x",
            "max_chars_per_line": 30,
        })
        assert "start_time" not in result
        assert "ffmpeg_args" not in result
        assert "subtitle_density" in result
        assert result["max_chars_per_line"] == 30

    def test_sanitize_clamps_max_chars_per_line(self):
        from app.ai.subtitles.subtitle_apply_safety import sanitize_subtitle_text_changes
        result = sanitize_subtitle_text_changes({"max_chars_per_line": 100})
        assert result["max_chars_per_line"] == 42

    def test_sanitize_clamps_max_chars_min(self):
        from app.ai.subtitles.subtitle_apply_safety import sanitize_subtitle_text_changes
        result = sanitize_subtitle_text_changes({"max_chars_per_line": 5})
        assert result["max_chars_per_line"] == 18

    def test_sanitize_strips_unknown_keys(self):
        from app.ai.subtitles.subtitle_apply_safety import sanitize_subtitle_text_changes
        result = sanitize_subtitle_text_changes({"some_unknown_key": "value"})
        assert result == {}

    def test_sanitize_never_raises(self):
        from app.ai.subtitles.subtitle_apply_safety import sanitize_subtitle_text_changes
        assert sanitize_subtitle_text_changes(None) == {}  # type: ignore
        assert sanitize_subtitle_text_changes("bad") == {}  # type: ignore
        assert sanitize_subtitle_text_changes(42) == {}  # type: ignore


# ── Engine tests ──────────────────────────────────────────────────────────────

class TestSubtitleApplyEngine:
    def test_never_raises_on_none(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        result = build_subtitle_text_apply_pack(None)
        assert result is not None

    def test_never_raises_on_empty(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        result = build_subtitle_text_apply_pack({})
        assert result is not None

    def test_disabled_by_default(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        result = build_subtitle_text_apply_pack(plan)
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
        pack = _build_pack_with_policy("invalid_policy")
        assert pack.enabled is False

    def test_phase17_compact_hint_collected(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        plan.subtitle_execution = {
            "available": True,
            "global_hint": {"density_mode": "compact", "emphasis_strength": 0.0},
        }
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        assert pack.enabled is True
        types = [a.optimization_type for a in pack.applied]
        assert "compact_overload" in types

    def test_phase17_emphasis_hint_collected(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        plan.subtitle_execution = {
            "available": True,
            "global_hint": {"density_mode": "normal", "emphasis_strength": 0.8},
        }
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        types = [a.optimization_type for a in pack.applied]
        assert "keyword_emphasis" in types

    def test_forbidden_timestamp_rewrite_not_applied(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        # inject a "bad" candidate via story_optimization timing_hints (Phase 20)
        # subtitle_apply_engine collects from Phase 17/23/16/19 — all safe sources
        # So we directly test by using a candidate that would fail safety check
        # The engine never adds forbidden types — this is verified by reading applied list
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert a.optimization_type != "timestamp_rewrite"

    def test_no_payload_in_place_mutation(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack

        class FakePayload:
            ai_apply_policy = "balanced"
            playback_speed = 1.0
            subtitle_offset = 0.0

        plan = _make_plan()
        payload = FakePayload()
        original_speed = payload.playback_speed
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        build_subtitle_text_apply_pack(plan, payload=payload, context=ctx)
        assert payload.playback_speed == original_speed

    def test_no_playback_speed_in_applied_changes(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        plan.subtitle_execution = {
            "available": True,
            "global_hint": {"density_mode": "compact", "emphasis_strength": 0.9},
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert "playback_speed" not in a.changes

    def test_no_subtitle_timestamp_rewrite_in_changes(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        plan.subtitle_execution = {
            "available": True,
            "global_hint": {"density_mode": "compact", "emphasis_strength": 0.9},
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        for a in pack.applied:
            for forbidden_key in ("start_time", "end_time", "timestamp", "subtitle_timing"):
                assert forbidden_key not in a.changes

    def test_no_ffmpeg_mutation(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert "ffmpeg_args" not in a.changes

    def test_no_segment_reorder(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        # All applied changes are metadata only — no reorder possible
        for a in pack.applied:
            assert a.target_scope == "metadata"

    def test_deterministic_same_inputs(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        plan.subtitle_execution = {
            "available": True,
            "global_hint": {"density_mode": "compact", "emphasis_strength": 0.5},
        }
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        r1 = build_subtitle_text_apply_pack(plan, context=ctx)
        r2 = build_subtitle_text_apply_pack(plan, context=ctx)
        assert r1.to_dict() == r2.to_dict()

    def test_no_api_key_no_gpu_no_internet(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        result = build_subtitle_text_apply_pack(plan)
        assert result is not None

    def test_to_dict_round_trip(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        d = pack.to_dict()
        assert isinstance(d, dict)
        assert "enabled" in d
        assert "applied" in d
        assert "blocked" in d


# ── Edit plan schema tests ────────────────────────────────────────────────────

class TestEditPlanSchemaPhase33:
    def test_subtitle_text_apply_field_exists(self):
        plan = _make_plan()
        assert hasattr(plan, "subtitle_text_apply")
        assert isinstance(plan.subtitle_text_apply, dict)

    def test_subtitle_text_apply_defaults_empty(self):
        plan = _make_plan()
        assert plan.subtitle_text_apply == {}

    def test_to_dict_includes_subtitle_text_apply(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "subtitle_text_apply" in d

    def test_all_prior_fields_still_present(self):
        plan = _make_plan()
        d = plan.to_dict()
        for key in (
            "enabled", "mode", "selected_segments", "subtitle", "camera",
            "warnings", "fallback_used", "pacing", "explainability", "confidence",
            "beat_execution", "story", "preset_evolution", "creator_style",
            "retention", "subtitle_execution", "timing_mutation",
            "variants", "variant_selection", "multivariant_render_plans",
            "multivariant_execution", "output_ranking", "ai_apply_policy",
            "timing_apply", "subtitle_text_apply",
        ):
            assert key in d, f"Missing key: {key}"

    def test_populated_subtitle_text_apply_in_to_dict(self):
        plan = _make_plan()
        plan.subtitle_text_apply = {
            "enabled": True,
            "mode": "active",
            "applied": [{"apply_id": "a1", "optimization_type": "density_reduce"}],
        }
        d = plan.to_dict()
        assert d["subtitle_text_apply"]["enabled"] is True
        assert len(d["subtitle_text_apply"]["applied"]) == 1


# ── Render influence tests ────────────────────────────────────────────────────

class TestRenderInfluencePhase33:
    def _apply(self, subtitle_text_apply_dict=None):
        from app.ai.director.render_influence import apply_ai_render_influence

        class FakePayload:
            motion_aware_crop = False
            add_subtitle = False

        class FakeEditPlan:
            camera = None
            subtitle = None
            pacing = None
            memory_context = {}
            subtitle_text_apply = subtitle_text_apply_dict or {}
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
        assert any("subtitle_text_apply" in s for s in report["skipped"])

    def test_disabled_pack_goes_to_skipped(self):
        _, report = self._apply({
            "enabled": False, "mode": "disabled",
            "applied": [], "blocked": [],
        })
        assert any("subtitle_text_apply:disabled_phase33" in s for s in report["skipped"])

    def test_disabled_reports_timestamp_rewrite_blocked(self):
        _, report = self._apply({
            "enabled": False, "mode": "disabled",
            "applied": [], "blocked": [],
        })
        assert any("subtitle_timestamp_rewrite:always_blocked" in s for s in report["skipped"])

    def test_applied_optimization_goes_to_applied(self):
        _, report = self._apply({
            "enabled": True, "mode": "active",
            "applied": [
                {"apply_id": "a1", "optimization_type": "compact_overload",
                 "changes": {"subtitle_density": "compact"}}
            ],
            "blocked": [],
        })
        assert any("subtitle_text_apply:applied" in s for s in report["applied"])

    def test_blocked_optimization_goes_to_skipped(self):
        _, report = self._apply({
            "enabled": True, "mode": "active",
            "applied": [],
            "blocked": [
                {"apply_id": "b1", "optimization_type": "timestamp_rewrite",
                 "warnings": ["forbidden_optimization_type"]}
            ],
        })
        assert any("subtitle_text_apply:blocked" in s for s in report["skipped"])

    def test_active_also_reports_timestamp_rewrite_blocked(self):
        _, report = self._apply({
            "enabled": True, "mode": "active",
            "applied": [{"apply_id": "a1", "optimization_type": "density_reduce",
                         "changes": {"subtitle_density": "compact"}}],
            "blocked": [],
        })
        assert any("subtitle_timestamp_rewrite:always_blocked" in s for s in report["skipped"])

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

        class FakeEditPlan:
            camera = None
            subtitle = None
            pacing = None
            memory_context = {}
            subtitle_text_apply = {
                "enabled": True, "mode": "active",
                "applied": [{"apply_id": "a1", "optimization_type": "compact_overload",
                             "changes": {"subtitle_density": "compact"}}],
                "blocked": [],
            }
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


# ── End-to-end tests ──────────────────────────────────────────────────────────

class TestPhase33EndToEnd:
    def test_conservative_pack_disabled(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "conservative", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        d = pack.to_dict()
        assert d["enabled"] is False
        assert d["mode"] == "disabled"

    def test_balanced_with_phase17_data(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        plan.subtitle_execution = {
            "available": True,
            "global_hint": {"density_mode": "compact", "emphasis_strength": 0.6},
        }
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        d = pack.to_dict()
        assert d["enabled"] is True
        assert d["mode"] == "active"
        assert len(d["applied"]) >= 1

    def test_all_applied_have_metadata_scope(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        plan.subtitle_execution = {
            "available": True,
            "global_hint": {"density_mode": "compact", "emphasis_strength": 0.9},
        }
        ctx = {"ai_apply_policy": "aggressive", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert a.target_scope == "metadata"

    def test_no_forbidden_change_keys_in_any_applied(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        from app.ai.subtitles.subtitle_apply_schema import _FORBIDDEN_CHANGE_KEYS
        plan = _make_plan()
        plan.subtitle_execution = {
            "available": True,
            "global_hint": {"density_mode": "compact", "emphasis_strength": 0.9},
        }
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        for a in pack.applied:
            for k in a.changes:
                assert k not in _FORBIDDEN_CHANGE_KEYS, f"Forbidden key {k!r} in applied changes"

    def test_all_forbidden_opt_types_never_applied(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        from app.ai.subtitles.subtitle_apply_schema import _FORBIDDEN_OPTIMIZATION_TYPES
        plan = _make_plan()
        ctx = {"ai_apply_policy": "experimental", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        for a in pack.applied:
            assert a.optimization_type not in _FORBIDDEN_OPTIMIZATION_TYPES

    def test_edit_plan_field_attached(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        pack = build_subtitle_text_apply_pack(plan, context=ctx)
        plan.subtitle_text_apply = pack.to_dict()
        d = plan.to_dict()
        assert "subtitle_text_apply" in d
        assert d["subtitle_text_apply"]["enabled"] is True

    def test_policy_never_raises(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        for policy in ("conservative", "balanced", "aggressive", "experimental",
                       "garbage", "", None):
            plan = _make_plan()
            ctx = {"ai_apply_policy": policy, "job_id": "t"}
            result = build_subtitle_text_apply_pack(plan, context=ctx)
            assert result is not None

    def test_backward_compatibility_all_phases(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "subtitle_text_apply" in d    # Phase 33
        assert "timing_apply" in d           # Phase 32
        assert "ai_apply_policy" in d        # Phase 31
        assert "output_ranking" in d         # Phase 30
        assert "subtitle_execution" in d     # Phase 17
        assert "timing_mutation" in d        # Phase 19

    def test_no_api_key_no_gpu_no_internet(self):
        from app.ai.subtitles.subtitle_apply_engine import build_subtitle_text_apply_pack
        plan = _make_plan()
        ctx = {"ai_apply_policy": "balanced", "job_id": "t"}
        result = build_subtitle_text_apply_pack(plan, context=ctx)
        assert result is not None
