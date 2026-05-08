"""
test_ai_phase27_safe_render_mutations.py — Phase 27 test suite.

Tests: mutation schema, safety gates, mutation engine, edit_plan field,
render_influence reporter, safety invariants, AI Director integration.
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestMutationSchema:
    def test_import(self):
        from app.ai.mutations.mutation_schema import (
            AISafeMutation,
            AISafeMutationPack,
            VALID_MUTATION_CATEGORIES,
        )
        assert AISafeMutation is not None
        assert AISafeMutationPack is not None
        assert len(VALID_MUTATION_CATEGORIES) == 5

    def test_valid_mutation_categories(self):
        from app.ai.mutations.mutation_schema import VALID_MUTATION_CATEGORIES
        expected = {"subtitle", "pacing", "camera", "creator_style", "visual_rhythm"}
        assert expected == VALID_MUTATION_CATEGORIES

    def test_mutation_defaults(self):
        from app.ai.mutations.mutation_schema import AISafeMutation
        m = AISafeMutation(mutation_id="test")
        assert m.applied is False
        assert m.safe is False
        assert m.confidence == 0.0

    def test_mutation_confidence_clamped(self):
        from app.ai.mutations.mutation_schema import AISafeMutation
        m = AISafeMutation(mutation_id="x", confidence=5.0)
        assert m.to_dict()["confidence"] == 1.0
        m2 = AISafeMutation(mutation_id="y", confidence=-1.0)
        assert m2.to_dict()["confidence"] == 0.0

    def test_mutation_invalid_category_empty(self):
        from app.ai.mutations.mutation_schema import AISafeMutation
        m = AISafeMutation(mutation_id="x", category="illegal")
        assert m.to_dict()["category"] == ""

    def test_mutation_valid_categories(self):
        from app.ai.mutations.mutation_schema import AISafeMutation, VALID_MUTATION_CATEGORIES
        for cat in VALID_MUTATION_CATEGORIES:
            m = AISafeMutation(mutation_id="x", category=cat)
            assert m.to_dict()["category"] == cat

    def test_mutation_explanation_capped(self):
        from app.ai.mutations.mutation_schema import AISafeMutation
        m = AISafeMutation(mutation_id="x", explanation=["a"] * 20)
        assert len(m.to_dict()["explanation"]) == 5

    def test_mutation_to_dict_keys(self):
        from app.ai.mutations.mutation_schema import AISafeMutation
        d = AISafeMutation(mutation_id="x").to_dict()
        assert set(d.keys()) == {
            "mutation_id", "category", "confidence", "applied", "safe",
            "source_recommendation_id", "changes", "warnings", "explanation",
        }

    def test_pack_defaults(self):
        from app.ai.mutations.mutation_schema import AISafeMutationPack
        pack = AISafeMutationPack()
        assert pack.available is True
        assert pack.advisory_mode is False

    def test_pack_mutations_capped_at_10(self):
        from app.ai.mutations.mutation_schema import AISafeMutationPack, AISafeMutation
        muts = [AISafeMutation(mutation_id=f"m{i}") for i in range(15)]
        pack = AISafeMutationPack(mutations=muts)
        assert len(pack.to_dict()["mutations"]) == 10

    def test_pack_to_dict_keys(self):
        from app.ai.mutations.mutation_schema import AISafeMutationPack
        d = AISafeMutationPack().to_dict()
        assert set(d.keys()) == {
            "available", "advisory_mode", "mutations",
            "applied_mutation_ids", "blocked_mutations", "warnings",
        }


# ── Mutation safety tests ─────────────────────────────────────────────────────

class TestMutationSafety:
    def test_import(self):
        from app.ai.mutations.mutation_safety import (
            sanitize_mutation_changes,
            is_mutation_safe,
            apply_safe_mutation,
        )
        assert callable(sanitize_mutation_changes)
        assert callable(is_mutation_safe)
        assert callable(apply_safe_mutation)

    def test_sanitize_allowed_keys_preserved(self):
        from app.ai.mutations.mutation_safety import sanitize_mutation_changes
        changes = {
            "subtitle_density": "compact",
            "pacing_style": "fast_hook",
            "camera_behavior": "dynamic_safe",
            "creator_style": "viral_tiktok",
            "visual_rhythm_mode": "beat_light",
            "ai_mode": "advisory",
            "subtitle_emphasis": "punch",
        }
        result = sanitize_mutation_changes(changes)
        assert result == changes

    def test_sanitize_forbidden_keys_stripped(self):
        from app.ai.mutations.mutation_safety import sanitize_mutation_changes
        forbidden = [
            "playback_speed", "segment_start", "segment_end", "subtitle_timing",
            "ffmpeg_args", "codec", "bitrate", "crf", "validation_rules",
            "output_path", "render_command", "render_segments", "segment_order",
        ]
        for key in forbidden:
            result = sanitize_mutation_changes({key: "bad", "ai_mode": "advisory"})
            assert key not in result, f"Forbidden key {key!r} was not stripped"
            assert result.get("ai_mode") == "advisory"

    def test_sanitize_unknown_keys_stripped(self):
        from app.ai.mutations.mutation_safety import sanitize_mutation_changes
        result = sanitize_mutation_changes({"unknown_key": "val", "pacing_style": "fast_hook"})
        assert "unknown_key" not in result
        assert result.get("pacing_style") == "fast_hook"

    def test_sanitize_none_value_stripped(self):
        from app.ai.mutations.mutation_safety import sanitize_mutation_changes
        result = sanitize_mutation_changes({"subtitle_density": None, "pacing_style": "fast"})
        assert "subtitle_density" not in result
        assert result.get("pacing_style") == "fast"

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.mutations.mutation_safety import sanitize_mutation_changes
        assert sanitize_mutation_changes(None) == {}
        assert sanitize_mutation_changes("string") == {}
        assert sanitize_mutation_changes(42) == {}
        assert sanitize_mutation_changes([]) == {}

    def test_sanitize_never_raises(self):
        from app.ai.mutations.mutation_safety import sanitize_mutation_changes
        sanitize_mutation_changes({"a": object(), "b": None})

    def test_is_safe_clean_changes(self):
        from app.ai.mutations.mutation_safety import is_mutation_safe
        assert is_mutation_safe({"pacing_style": "fast_hook", "ai_mode": "advisory"}) is True

    def test_is_safe_empty_changes(self):
        from app.ai.mutations.mutation_safety import is_mutation_safe
        assert is_mutation_safe({}) is True

    def test_is_safe_forbidden_key_false(self):
        from app.ai.mutations.mutation_safety import is_mutation_safe
        assert is_mutation_safe({"playback_speed": 1.5}) is False
        assert is_mutation_safe({"ffmpeg_args": "-vf scale"}) is False
        assert is_mutation_safe({"subtitle_timing": [0, 1, 2]}) is False
        assert is_mutation_safe({"segment_order": [2, 1, 0]}) is False
        assert is_mutation_safe({"render_segments": []}) is False

    def test_is_safe_non_dict_false(self):
        from app.ai.mutations.mutation_safety import is_mutation_safe
        assert is_mutation_safe(None) is False
        assert is_mutation_safe("string") is False

    def test_is_safe_never_raises(self):
        from app.ai.mutations.mutation_safety import is_mutation_safe
        is_mutation_safe(object())

    def test_apply_safe_mutation_returns_copy(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        original = {"pacing_style": "slow", "other_field": "keep"}
        result = apply_safe_mutation(original, {"pacing_style": "fast_hook"})
        assert result is not original

    def test_apply_safe_mutation_original_not_mutated(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        original = {"pacing_style": "slow"}
        apply_safe_mutation(original, {"pacing_style": "fast_hook"})
        assert original["pacing_style"] == "slow"

    def test_apply_safe_mutation_applies_allowed_keys(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        original = {"pacing_style": "slow", "other_field": "keep"}
        result = apply_safe_mutation(original, {"pacing_style": "fast_hook"})
        assert result["pacing_style"] == "fast_hook"
        assert result["other_field"] == "keep"

    def test_apply_safe_mutation_strips_forbidden(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        original = {"pacing_style": "slow"}
        result = apply_safe_mutation(original, {"pacing_style": "fast_hook", "playback_speed": 1.5})
        assert result["pacing_style"] == "fast_hook"
        assert "playback_speed" not in result

    def test_apply_safe_mutation_never_raises(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        apply_safe_mutation(None, {"pacing_style": "fast"})
        apply_safe_mutation("string", {})
        apply_safe_mutation({}, None)

    def test_apply_safe_mutation_works_on_object(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation

        class FakePayload:
            pacing_style = "slow"
            ai_mode = "off"

        result = apply_safe_mutation(FakePayload(), {"pacing_style": "fast_hook"})
        assert isinstance(result, dict)
        assert result["pacing_style"] == "fast_hook"


# ── Mutation engine tests ─────────────────────────────────────────────────────

class TestMutationEngine:
    def _make_plan(self, **overrides):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        for k, v in overrides.items():
            setattr(plan, k, v)
        return plan

    def _make_recs(self, *recs):
        return {
            "available": True,
            "recommendations": list(recs),
            "recommended_pack_id": recs[0]["recommendation_id"] if recs else None,
        }

    def test_import(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        assert callable(build_safe_mutations)

    def test_never_raises_on_none(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        result = build_safe_mutations(None)
        assert result is not None

    def test_returns_mutation_pack(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        from app.ai.mutations.mutation_schema import AISafeMutationPack
        plan = self._make_plan()
        result = build_safe_mutations(plan)
        assert isinstance(result, AISafeMutationPack)

    def test_safe_baseline_rec_creates_applied_mutation(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "safe_baseline",
            "category": "safe_baseline",
            "confidence": 1.0,
            "safe_to_apply": True,
            "recommended_settings": {"ai_mode": "advisory", "pacing_style": "default"},
        }))
        result = build_safe_mutations(plan)
        assert "m_safe_baseline" in result.applied_mutation_ids

    def test_retention_high_confidence_applied(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "retention_pacing",
            "category": "retention",
            "confidence": 0.80,
            "safe_to_apply": True,
            "recommended_settings": {"pacing_style": "fast_cuts", "hook_density": "high"},
        }))
        result = build_safe_mutations(plan)
        applied = result.applied_mutation_ids
        assert any("retention" in mid for mid in applied)

    def test_retention_low_confidence_blocked(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "retention_pacing",
            "category": "retention",
            "confidence": 0.20,
            "safe_to_apply": False,
            "recommended_settings": {"pacing_style": "fast_cuts"},
        }))
        result = build_safe_mutations(plan)
        applied = result.applied_mutation_ids
        assert not any("retention" in mid for mid in applied)

    def test_creator_style_high_confidence_applied(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "creator_style_viral_tiktok",
            "category": "creator_style",
            "confidence": 0.85,
            "safe_to_apply": True,
            "recommended_settings": {"creator_style": "viral_tiktok", "camera_behavior": "fast_follow"},
        }))
        result = build_safe_mutations(plan)
        assert any("creator_style" in mid for mid in result.applied_mutation_ids)

    def test_creator_style_low_confidence_blocked(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "creator_style_cinematic",
            "category": "creator_style",
            "confidence": 0.30,
            "safe_to_apply": False,
            "recommended_settings": {"creator_style": "cinematic"},
        }))
        result = build_safe_mutations(plan)
        assert any("creator_style" in mid for mid in result.blocked_mutations)

    def test_subtitle_mutation_applied(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "compact_subtitle",
            "category": "subtitle",
            "confidence": 0.70,
            "safe_to_apply": True,
            "recommended_settings": {"subtitle_density": "compact", "subtitle_emphasis": "punch"},
        }))
        result = build_safe_mutations(plan)
        assert "m_subtitle_density" in result.applied_mutation_ids

    def test_subtitle_changes_have_allowed_keys_only(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        from app.ai.mutations.mutation_safety import _FORBIDDEN_KEYS
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "compact_subtitle",
            "category": "subtitle",
            "confidence": 0.70,
            "safe_to_apply": True,
            "recommended_settings": {"subtitle_density": "compact"},
        }))
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            for key in mut.changes:
                assert key not in _FORBIDDEN_KEYS

    def test_visual_rhythm_mutation_applied(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "visual_rhythm",
            "category": "visual_rhythm",
            "confidence": 0.60,
            "safe_to_apply": True,
            "recommended_settings": {"visual_rhythm_mode": "energetic"},
        }))
        result = build_safe_mutations(plan)
        assert "m_visual_rhythm" in result.applied_mutation_ids

    def test_visual_rhythm_mode_mapped_to_safe_value(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "visual_rhythm",
            "category": "visual_rhythm",
            "confidence": 0.60,
            "safe_to_apply": True,
            "recommended_settings": {"visual_rhythm_mode": "energetic"},
        }))
        result = build_safe_mutations(plan)
        vr_mut = next((m for m in result.mutations if m.mutation_id == "m_visual_rhythm"), None)
        assert vr_mut is not None
        assert vr_mut.changes.get("visual_rhythm_mode") == "beat_light"

    def test_pacing_mutation_applied(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "story_pacing",
            "category": "pacing",
            "confidence": 0.65,
            "safe_to_apply": True,
            "recommended_settings": {"pacing_style": "story_driven"},
        }))
        result = build_safe_mutations(plan)
        assert any("pacing" in mid for mid in result.applied_mutation_ids)

    def test_no_recommendations_advisory_mode(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan()  # no execution_recommendations
        result = build_safe_mutations(plan)
        assert result.advisory_mode is True

    def test_with_applied_mutations_not_advisory(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "safe_baseline",
            "category": "safe_baseline",
            "confidence": 1.0,
            "safe_to_apply": True,
            "recommended_settings": {"ai_mode": "advisory"},
        }))
        result = build_safe_mutations(plan)
        assert result.advisory_mode is False

    def test_deterministic(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs(
            {
                "recommendation_id": "safe_baseline",
                "category": "safe_baseline",
                "confidence": 1.0,
                "safe_to_apply": True,
                "recommended_settings": {"ai_mode": "advisory"},
            },
            {
                "recommendation_id": "retention_pacing",
                "category": "retention",
                "confidence": 0.75,
                "safe_to_apply": True,
                "recommended_settings": {"pacing_style": "fast_cuts"},
            },
        ))
        r1 = build_safe_mutations(plan)
        r2 = build_safe_mutations(plan)
        assert r1.applied_mutation_ids == r2.applied_mutation_ids
        assert r1.blocked_mutations == r2.blocked_mutations

    def test_no_forbidden_keys_in_any_changes(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        from app.ai.mutations.mutation_safety import _FORBIDDEN_KEYS
        plan = self._make_plan(execution_recommendations=self._make_recs(
            {
                "recommendation_id": "safe_baseline",
                "category": "safe_baseline",
                "confidence": 1.0,
                "safe_to_apply": True,
                "recommended_settings": {"ai_mode": "advisory"},
            },
            {
                "recommendation_id": "creator_style_cinematic",
                "category": "creator_style",
                "confidence": 0.80,
                "safe_to_apply": True,
                "recommended_settings": {"creator_style": "cinematic"},
            },
        ))
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            for key in mut.changes:
                assert key not in _FORBIDDEN_KEYS, f"Forbidden key {key!r} in {mut.mutation_id}"

    def test_no_ffmpeg_mutation(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "safe_baseline",
            "category": "safe_baseline",
            "confidence": 1.0,
            "safe_to_apply": True,
            "recommended_settings": {},
        }))
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            assert "ffmpeg_args" not in mut.changes

    def test_no_playback_speed_mutation(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "retention_pacing",
            "category": "retention",
            "confidence": 0.80,
            "safe_to_apply": True,
            "recommended_settings": {"pacing_style": "fast_cuts"},
        }))
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            assert "playback_speed" not in mut.changes

    def test_no_subtitle_timing_mutation(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "compact_subtitle",
            "category": "subtitle",
            "confidence": 0.70,
            "safe_to_apply": True,
            "recommended_settings": {"subtitle_density": "compact"},
        }))
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            assert "subtitle_timing" not in mut.changes

    def test_no_segment_reorder(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "retention_pacing",
            "category": "retention",
            "confidence": 0.80,
            "safe_to_apply": True,
            "recommended_settings": {"pacing_style": "fast_cuts"},
        }))
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            assert "segment_order" not in mut.changes
            assert "render_segments" not in mut.changes

    def test_payload_not_passed_still_works(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan(execution_recommendations=self._make_recs({
            "recommendation_id": "safe_baseline",
            "category": "safe_baseline",
            "confidence": 1.0,
            "safe_to_apply": True,
            "recommended_settings": {},
        }))
        result = build_safe_mutations(plan, payload=None)
        assert result is not None

    def test_no_api_key_required(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        import os
        os.environ.pop("OPENAI_API_KEY", None)
        plan = self._make_plan()
        result = build_safe_mutations(plan)
        assert result is not None

    def test_no_gpu_required(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan()
        assert build_safe_mutations(plan) is not None

    def test_never_raises_on_garbage_plan(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations

        class BadPlan:
            @property
            def execution_recommendations(self):
                raise RuntimeError("boom")

        result = build_safe_mutations(BadPlan())
        assert result is not None


# ── Apply-safe-mutation payload invariant tests ───────────────────────────────

class TestApplySafeMutationPayloadInvariants:
    def test_original_payload_dict_not_mutated(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        original = {"pacing_style": "slow", "subtitle_density": "normal"}
        apply_safe_mutation(original, {"pacing_style": "fast_hook", "subtitle_density": "compact"})
        assert original["pacing_style"] == "slow"
        assert original["subtitle_density"] == "normal"

    def test_copy_has_applied_changes(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        result = apply_safe_mutation(
            {"pacing_style": "slow"},
            {"pacing_style": "fast_hook", "ai_mode": "advisory"},
        )
        assert result["pacing_style"] == "fast_hook"
        assert result["ai_mode"] == "advisory"

    def test_copy_preserves_existing_fields(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        original = {"pacing_style": "slow", "unrelated_field": "keep_me"}
        result = apply_safe_mutation(original, {"pacing_style": "fast_hook"})
        assert result["unrelated_field"] == "keep_me"

    def test_forbidden_keys_not_in_copy(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        result = apply_safe_mutation(
            {"pacing_style": "slow"},
            {"pacing_style": "fast_hook", "playback_speed": 2.0, "ffmpeg_args": "-vf"},
        )
        assert "playback_speed" not in result
        assert "ffmpeg_args" not in result
        assert result["pacing_style"] == "fast_hook"

    def test_returns_new_dict_instance(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        original = {"pacing_style": "slow"}
        result = apply_safe_mutation(original, {})
        assert result is not original
        assert isinstance(result, dict)

    def test_no_render_queue_mutation(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        result = apply_safe_mutation(
            {"render_queue": ["job1", "job2"]},
            {"pacing_style": "fast_hook", "render_command": "ffmpeg ..."},
        )
        assert "render_command" not in result

    def test_no_output_validation_mutation(self):
        from app.ai.mutations.mutation_safety import apply_safe_mutation
        result = apply_safe_mutation(
            {"output_path": "/videos/out.mp4"},
            {"pacing_style": "fast_hook", "validation_rules": "strict"},
        )
        assert "validation_rules" not in result


# ── AIEditPlan field tests ────────────────────────────────────────────────────

class TestAIEditPlanSafeRenderMutationsField:
    def _make_plan(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        return AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )

    def test_field_exists(self):
        assert hasattr(self._make_plan(), "safe_render_mutations")

    def test_field_default_empty_dict(self):
        assert self._make_plan().safe_render_mutations == {}

    def test_field_in_to_dict(self):
        assert "safe_render_mutations" in self._make_plan().to_dict()

    def test_field_populated_in_to_dict(self):
        plan = self._make_plan()
        plan.safe_render_mutations = {"available": True, "applied_mutation_ids": ["m_safe_baseline"]}
        d = plan.to_dict()
        assert d["safe_render_mutations"]["available"] is True

    def test_field_independence(self):
        p1, p2 = self._make_plan(), self._make_plan()
        p1.safe_render_mutations["x"] = 1
        assert "x" not in p2.safe_render_mutations

    def test_backward_compat_phase26_present(self):
        assert "execution_simulation" in self._make_plan().to_dict()

    def test_backward_compat_phase25_present(self):
        assert "execution_recommendations" in self._make_plan().to_dict()

    def test_backward_compat_phase24_present(self):
        assert "render_decision_preview" in self._make_plan().to_dict()


# ── render_influence reporter tests ──────────────────────────────────────────

class TestRenderInfluenceReportSafeMutations:
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
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        for k, v in overrides.items():
            setattr(plan, k, v)
        return plan

    def test_reporter_exists(self):
        from app.ai.director.render_influence import _report_safe_mutations
        assert callable(_report_safe_mutations)

    def test_no_field_skips(self):
        from app.ai.director.render_influence import _report_safe_mutations
        plan = self._make_plan()
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_safe_mutations(self._make_payload(), plan, report)
        assert any("safe_render_mutations" in s for s in report["skipped"])

    def test_applied_mutation_goes_to_applied_list(self):
        from app.ai.director.render_influence import _report_safe_mutations
        plan = self._make_plan(safe_render_mutations={
            "available": True,
            "advisory_mode": False,
            "mutations": [{
                "mutation_id": "m_safe_baseline",
                "category": "pacing",
                "applied": True,
                "safe": True,
                "changes": {"ai_mode": "advisory"},
            }],
            "applied_mutation_ids": ["m_safe_baseline"],
            "blocked_mutations": [],
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_safe_mutations(self._make_payload(), plan, report)
        assert any("safe_mutation:applied" in s for s in report["applied"])

    def test_blocked_mutation_goes_to_skipped_list(self):
        from app.ai.director.render_influence import _report_safe_mutations
        plan = self._make_plan(safe_render_mutations={
            "available": True,
            "advisory_mode": True,
            "mutations": [{
                "mutation_id": "m_creator_style_cinematic",
                "category": "creator_style",
                "applied": False,
                "safe": False,
                "changes": {},
            }],
            "applied_mutation_ids": [],
            "blocked_mutations": ["m_creator_style_cinematic"],
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_safe_mutations(self._make_payload(), plan, report)
        assert any("safe_mutation:blocked" in s for s in report["skipped"])

    def test_no_payload_mutation(self):
        from app.ai.director.render_influence import _report_safe_mutations
        payload = self._make_payload()
        plan = self._make_plan(safe_render_mutations={
            "available": True,
            "mutations": [{"mutation_id": "m_safe_baseline", "applied": True, "changes": {}}],
            "applied_mutation_ids": ["m_safe_baseline"],
            "blocked_mutations": [],
        })
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_safe_mutations(payload, plan, report)
        assert payload.motion_aware_crop is False
        assert payload.add_subtitle is False

    def test_wired_into_apply_ai_render_influence(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = self._make_plan(safe_render_mutations={
            "available": True,
            "mutations": [{"mutation_id": "m_safe_baseline", "category": "pacing",
                          "applied": True, "safe": True, "changes": {"ai_mode": "advisory"}}],
            "applied_mutation_ids": ["m_safe_baseline"],
            "blocked_mutations": [],
        })
        _, report = apply_ai_render_influence(self._make_payload(), plan)
        assert any("safe_mutation" in s for s in report["applied"] + report["skipped"])


# ── Safety invariant tests ────────────────────────────────────────────────────

class TestPhase27SafetyInvariants:
    def _make_plan_with_recs(self, *recs):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
            execution_recommendations={
                "available": True,
                "recommendations": list(recs),
                "recommended_pack_id": recs[0]["recommendation_id"] if recs else None,
            }
        )
        return plan

    def test_no_ffmpeg_args_in_applied_mutations(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan_with_recs(
            {"recommendation_id": "safe_baseline", "category": "safe_baseline",
             "confidence": 1.0, "safe_to_apply": True,
             "recommended_settings": {"ai_mode": "advisory"}},
        )
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            assert "ffmpeg_args" not in mut.changes

    def test_no_playback_speed_in_any_mutation(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan_with_recs(
            {"recommendation_id": "retention_pacing", "category": "retention",
             "confidence": 0.9, "safe_to_apply": True,
             "recommended_settings": {"pacing_style": "fast_cuts"}},
        )
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            assert "playback_speed" not in mut.changes

    def test_no_segment_order_in_any_mutation(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan_with_recs(
            {"recommendation_id": "story_pacing", "category": "pacing",
             "confidence": 0.7, "safe_to_apply": True,
             "recommended_settings": {"pacing_style": "story_driven"}},
        )
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            assert "segment_order" not in mut.changes
            assert "render_segments" not in mut.changes

    def test_no_subtitle_timing_in_any_mutation(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan_with_recs(
            {"recommendation_id": "compact_subtitle", "category": "subtitle",
             "confidence": 0.75, "safe_to_apply": True,
             "recommended_settings": {"subtitle_density": "compact"}},
        )
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            assert "subtitle_timing" not in mut.changes

    def test_never_raises_on_none(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        assert build_safe_mutations(None) is not None

    def test_never_raises_on_string(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        assert build_safe_mutations("not_a_plan") is not None

    def test_never_raises_on_empty_dict(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        assert build_safe_mutations({}) is not None

    def test_unsafe_mutations_have_no_changes(self):
        from app.ai.mutations.mutation_engine import build_safe_mutations
        plan = self._make_plan_with_recs(
            {"recommendation_id": "creator_style_cinematic", "category": "creator_style",
             "confidence": 0.10, "safe_to_apply": False,
             "recommended_settings": {"creator_style": "cinematic"}},
        )
        result = build_safe_mutations(plan)
        for mut in result.mutations:
            if not mut.applied:
                assert mut.changes == {}


# ── AI Director integration tests ─────────────────────────────────────────────

class TestAIDirectorPhase27Integration:
    def test_phase27_block_in_source(self):
        import inspect
        from app.ai.director import ai_director
        assert "_attach_safe_render_mutations" in inspect.getsource(ai_director)

    def test_attach_function_importable(self):
        from app.ai.director.ai_director import _attach_safe_render_mutations
        assert callable(_attach_safe_render_mutations)

    def test_attach_populates_field(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_safe_render_mutations
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        _attach_safe_render_mutations(plan, "test-job-p27")
        assert isinstance(plan.safe_render_mutations, dict)
        assert "available" in plan.safe_render_mutations

    def test_attach_does_not_raise_on_none(self):
        from app.ai.director.ai_director import _attach_safe_render_mutations
        _attach_safe_render_mutations(None, "test-job-none")

    def test_field_in_to_dict_after_attach(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_safe_render_mutations
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        _attach_safe_render_mutations(plan, "test-job-dict")
        d = plan.to_dict()
        assert "safe_render_mutations" in d
        assert isinstance(d["safe_render_mutations"], dict)

    def test_no_render_executor_override(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_safe_render_mutations
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        original_mode = plan.mode
        _attach_safe_render_mutations(plan, "test-job-override")
        assert plan.mode == original_mode

    def test_mutation_metadata_attached_correctly(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        from app.ai.director.ai_director import _attach_safe_render_mutations
        plan = AIEditPlan(
            enabled=True, mode="ai_curated", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
            execution_recommendations={
                "available": True,
                "recommendations": [{
                    "recommendation_id": "safe_baseline",
                    "category": "safe_baseline",
                    "confidence": 1.0,
                    "safe_to_apply": True,
                    "recommended_settings": {"ai_mode": "advisory"},
                }],
                "recommended_pack_id": "safe_baseline",
            }
        )
        _attach_safe_render_mutations(plan, "test-job-attach")
        srm = plan.safe_render_mutations
        assert srm.get("available") is True
        assert isinstance(srm.get("applied_mutation_ids"), list)
        assert "m_safe_baseline" in srm.get("applied_mutation_ids", [])
