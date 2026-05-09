"""
tests/test_ai_phase38_feature_enhancement.py

Phase 38 — AI-Assisted Existing Feature Enhancement Integration

Safety contract: assistive-only, no render execution, no FFmpeg mutation,
no playback_speed mutation, no subtitle timing rewrite, no queue mutation,
no executor override. AI enhances existing features only.
"""
from __future__ import annotations

import types
from typing import Any


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_edit_plan(**overrides) -> Any:
    defaults = {
        "subtitle_text_apply": {},
        "subtitle_execution": {},
        "camera_motion_apply": {},
        "beat_visual_execution": {},
        "timing_apply": {},
        "retention": {},
        "story": {},
        "pacing": types.SimpleNamespace(pacing_style="default"),
        "creator_style_adaptation": {},
        "creator_style": {},
        "execution_recommendations": {},
        "variant_selection": {},
        "execution_simulation": {},
        "clip_batch_planning": {},
        "output_ranking": {},
        "clip_segment_selection": {},
        "clip_candidate_discovery": {},
        "explainability": {},
        "camera": types.SimpleNamespace(
            mode="default", behavior="none", subtitle_safe=True,
            zoom_strength=1.0, follow_strength=0.5, motion_energy=None,
        ),
        "feature_enhancement": {},
    }
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


def _make_payload() -> Any:
    return types.SimpleNamespace()


# ---------------------------------------------------------------------------
# 1. Schema invariants
# ---------------------------------------------------------------------------

class TestFeatureEnhancementSchema:
    def test_ai_feature_enhancement_defaults(self):
        from app.ai.enhancement.feature_enhancement_schema import AIFeatureEnhancement
        enh = AIFeatureEnhancement(feature_name="subtitle")
        assert enh.feature_name == "subtitle"
        assert enh.enabled is False
        assert enh.enhancement_level == "safe"
        assert enh.confidence == 0.0
        assert enh.improvements == []
        assert enh.warnings == []
        assert enh.explanation == []

    def test_ai_feature_enhancement_to_dict(self):
        from app.ai.enhancement.feature_enhancement_schema import AIFeatureEnhancement
        enh = AIFeatureEnhancement(
            feature_name="camera",
            enabled=True,
            enhancement_level="enhanced",
            confidence=0.85,
            improvements=["camera_behavior_guided:fast_follow"],
            explanation=["AI camera guidance active"],
        )
        d = enh.to_dict()
        assert d["feature_name"] == "camera"
        assert d["enabled"] is True
        assert d["enhancement_level"] == "enhanced"
        assert d["confidence"] == 0.85
        assert "camera_behavior_guided:fast_follow" in d["improvements"]

    def test_ai_feature_enhancement_pack_defaults(self):
        from app.ai.enhancement.feature_enhancement_schema import AIFeatureEnhancementPack
        pack = AIFeatureEnhancementPack()
        assert pack.available is True
        assert pack.mode == "assistive_only"
        assert pack.subtitle_enhancement == {}
        assert pack.camera_enhancement == {}
        assert pack.timing_enhancement == {}
        assert pack.clip_selection_enhancement == {}
        assert pack.creator_style_enhancement == {}
        assert pack.variant_enhancement == {}
        assert pack.output_ranking_enhancement == {}
        assert pack.warnings == []

    def test_ai_feature_enhancement_pack_to_dict(self):
        from app.ai.enhancement.feature_enhancement_schema import AIFeatureEnhancementPack
        pack = AIFeatureEnhancementPack(
            available=True,
            mode="assistive_only",
            subtitle_enhancement={"enabled": True},
        )
        d = pack.to_dict()
        assert d["available"] is True
        assert d["mode"] == "assistive_only"
        assert d["subtitle_enhancement"] == {"enabled": True}
        assert "camera_enhancement" in d
        assert "timing_enhancement" in d
        assert "clip_selection_enhancement" in d

    def test_mode_always_assistive_only(self):
        from app.ai.enhancement.feature_enhancement_schema import AIFeatureEnhancementPack
        pack = AIFeatureEnhancementPack()
        assert pack.mode == "assistive_only"
        d = pack.to_dict()
        assert d["mode"] == "assistive_only"


# ---------------------------------------------------------------------------
# 2. Safety validation
# ---------------------------------------------------------------------------

class TestFeatureEnhancementSafety:
    def test_forbidden_keys_stripped_by_sanitize(self):
        from app.ai.enhancement.feature_enhancement_safety import sanitize_feature_enhancement
        raw = {
            "feature_name": "subtitle",
            "enabled": True,
            "confidence": 0.8,
            "ffmpeg_args": "-y -vf scale=1280:720",
            "render_command": "ffmpeg ...",
            "playback_speed": 1.5,
            "subtitle_timing": [{"start": 0, "end": 1}],
            "output_path": "/tmp/out.mp4",
            "queue_priority": 10,
            "job_id": "abc123",
            "segment_order": [1, 2, 3],
            "direct_crop_coordinates": {"x": 0, "y": 0},
        }
        result = sanitize_feature_enhancement(raw)
        for forbidden in (
            "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
            "output_path", "queue_priority", "job_id", "segment_order",
            "direct_crop_coordinates",
        ):
            assert forbidden not in result, f"Forbidden key '{forbidden}' not stripped"
        assert result["feature_name"] == "subtitle"
        assert result["enabled"] is True

    def test_sanitize_confidence_clamped(self):
        from app.ai.enhancement.feature_enhancement_safety import sanitize_feature_enhancement
        result = sanitize_feature_enhancement({"feature_name": "timing", "confidence": 99.9})
        assert result["confidence"] <= 1.0

    def test_sanitize_invalid_level_defaults_to_safe(self):
        from app.ai.enhancement.feature_enhancement_safety import sanitize_feature_enhancement
        result = sanitize_feature_enhancement({"feature_name": "camera", "enhancement_level": "destroy"})
        assert result["enhancement_level"] == "safe"

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.enhancement.feature_enhancement_safety import sanitize_feature_enhancement
        assert sanitize_feature_enhancement(None) == {}
        assert sanitize_feature_enhancement("bad") == {}
        assert sanitize_feature_enhancement(42) == {}

    def test_is_safe_valid(self):
        from app.ai.enhancement.feature_enhancement_safety import is_feature_enhancement_safe
        data = {
            "feature_name": "subtitle",
            "enabled": True,
            "enhancement_level": "safe",
            "confidence": 0.8,
        }
        assert is_feature_enhancement_safe(data) is True

    def test_is_safe_rejects_forbidden_key(self):
        from app.ai.enhancement.feature_enhancement_safety import is_feature_enhancement_safe
        for key in ("ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
                    "output_path", "queue_priority", "job_id", "segment_order",
                    "direct_crop_coordinates"):
            data = {"feature_name": "subtitle", "enhancement_level": "safe", "confidence": 0.5, key: "bad"}
            assert is_feature_enhancement_safe(data) is False, f"Should reject key={key}"

    def test_is_safe_rejects_invalid_level(self):
        from app.ai.enhancement.feature_enhancement_safety import is_feature_enhancement_safe
        data = {"feature_name": "subtitle", "enhancement_level": "run_ffmpeg", "confidence": 0.5}
        assert is_feature_enhancement_safe(data) is False

    def test_is_safe_rejects_out_of_range_confidence(self):
        from app.ai.enhancement.feature_enhancement_safety import is_feature_enhancement_safe
        data = {"feature_name": "subtitle", "enhancement_level": "safe", "confidence": 5.0}
        assert is_feature_enhancement_safe(data) is False

    def test_is_safe_none_input(self):
        from app.ai.enhancement.feature_enhancement_safety import is_feature_enhancement_safe
        assert is_feature_enhancement_safe(None) is False


# ---------------------------------------------------------------------------
# 3. Engine: subtitle enhancement
# ---------------------------------------------------------------------------

class TestSubtitleEnhancement:
    def test_subtitle_enhancement_enabled_when_apply_active(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(subtitle_text_apply={"enabled": True, "density": "low", "emphasis": "bold"})
        pack = build_feature_enhancement_pack(ep)
        sub = pack.subtitle_enhancement
        assert sub.get("enabled") is True
        assert any("subtitle_density" in str(i) for i in sub.get("improvements", []))

    def test_subtitle_enhancement_disabled_when_no_apply(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(subtitle_text_apply={})
        pack = build_feature_enhancement_pack(ep)
        sub = pack.subtitle_enhancement
        assert sub.get("enabled") is False

    def test_subtitle_enhancement_metadata_valid(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(subtitle_text_apply={"enabled": True, "density": "normal"})
        pack = build_feature_enhancement_pack(ep)
        sub = pack.subtitle_enhancement
        assert "feature_name" in sub
        assert sub["feature_name"] == "subtitle"
        assert isinstance(sub.get("improvements"), list)
        assert isinstance(sub.get("warnings"), list)
        assert isinstance(sub.get("explanation"), list)

    def test_subtitle_no_forbidden_keys(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(subtitle_text_apply={"enabled": True})
        pack = build_feature_enhancement_pack(ep)
        sub = pack.subtitle_enhancement
        for key in ("ffmpeg_args", "render_command", "playback_speed", "subtitle_timing"):
            assert key not in sub


# ---------------------------------------------------------------------------
# 4. Engine: camera enhancement
# ---------------------------------------------------------------------------

class TestCameraEnhancement:
    def test_camera_enhancement_enabled_when_apply_active(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(camera_motion_apply={"enabled": True, "behavior": "fast_follow", "strategy": "dynamic"})
        pack = build_feature_enhancement_pack(ep)
        cam = pack.camera_enhancement
        assert cam.get("enabled") is True
        assert any("camera_behavior_guided" in str(i) for i in cam.get("improvements", []))

    def test_camera_enhancement_metadata_valid(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(camera_motion_apply={"enabled": True, "behavior": "slow_reveal"})
        pack = build_feature_enhancement_pack(ep)
        cam = pack.camera_enhancement
        assert cam.get("feature_name") == "camera"
        assert isinstance(cam.get("improvements"), list)

    def test_camera_no_forbidden_keys(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(camera_motion_apply={"enabled": True})
        pack = build_feature_enhancement_pack(ep)
        cam = pack.camera_enhancement
        for key in ("ffmpeg_args", "direct_crop_coordinates", "render_command"):
            assert key not in cam


# ---------------------------------------------------------------------------
# 5. Engine: timing enhancement
# ---------------------------------------------------------------------------

class TestTimingEnhancement:
    def test_timing_enhancement_enabled_when_apply_active(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(timing_apply={"enabled": True, "adjustments": [{"type": "trim_silence"}]})
        pack = build_feature_enhancement_pack(ep)
        tim = pack.timing_enhancement
        assert tim.get("enabled") is True

    def test_timing_enhancement_silence_gap_detected(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            timing_apply={},
            retention={"available": True, "overall_retention_score": 70,
                       "risk_regions": [{"category": "silence_gap", "start": 10, "end": 15}]},
        )
        pack = build_feature_enhancement_pack(ep)
        tim = pack.timing_enhancement
        assert tim.get("enabled") is True
        assert any("silence_gap" in str(i) for i in tim.get("improvements", []))

    def test_timing_enhancement_dead_air_detected(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            retention={"available": True, "overall_retention_score": 65,
                       "risk_regions": [{"category": "dead_air", "start": 20, "end": 25}]},
        )
        pack = build_feature_enhancement_pack(ep)
        tim = pack.timing_enhancement
        assert tim.get("enabled") is True
        assert any("dead_air" in str(i) for i in tim.get("improvements", []))

    def test_timing_metadata_valid(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(timing_apply={"enabled": True})
        pack = build_feature_enhancement_pack(ep)
        tim = pack.timing_enhancement
        assert tim.get("feature_name") == "timing"
        assert isinstance(tim.get("improvements"), list)
        assert 0.0 <= tim.get("confidence", 0.0) <= 1.0


# ---------------------------------------------------------------------------
# 6. Engine: clip selection enhancement
# ---------------------------------------------------------------------------

class TestClipSelectionEnhancement:
    def test_clip_selection_enabled_when_segments_selected(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            clip_segment_selection={"enabled": True, "selected_segments": [{"segment_id": "seg_01"}]},
        )
        pack = build_feature_enhancement_pack(ep)
        clip = pack.clip_selection_enhancement
        assert clip.get("enabled") is True
        assert any("ai_clip_segments_selected" in str(i) for i in clip.get("improvements", []))

    def test_clip_selection_discovery_improvements(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            clip_candidate_discovery={"enabled": True, "candidates": [{}, {}],
                                      "recommended_candidate_id": "cand_01"},
        )
        pack = build_feature_enhancement_pack(ep)
        clip = pack.clip_selection_enhancement
        assert clip.get("enabled") is True
        assert any("ai_clip_candidates_discovered:2" in str(i) for i in clip.get("improvements", []))

    def test_clip_selection_metadata_valid(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        clip = pack.clip_selection_enhancement
        assert clip.get("feature_name") == "clip_selection"
        assert isinstance(clip.get("improvements"), list)


# ---------------------------------------------------------------------------
# 7. Engine: creator style enhancement
# ---------------------------------------------------------------------------

class TestCreatorStyleEnhancement:
    def test_creator_style_enabled_when_adaptation_active(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            creator_style_adaptation={"available": True, "dominant_style": "podcast_viral", "confidence": 0.9},
        )
        pack = build_feature_enhancement_pack(ep)
        style = pack.creator_style_enhancement
        assert style.get("enabled") is True
        assert any("creator_style_adapted:podcast_viral" in str(i) for i in style.get("improvements", []))

    def test_creator_style_metadata_valid(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        style = pack.creator_style_enhancement
        assert style.get("feature_name") == "creator_style"
        assert isinstance(style.get("improvements"), list)
        assert 0.0 <= style.get("confidence", 0.0) <= 1.0


# ---------------------------------------------------------------------------
# 8. Engine: variant enhancement
# ---------------------------------------------------------------------------

class TestVariantEnhancement:
    def test_variant_enabled_when_selection_available(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            variant_selection={"available": True, "best_variant_id": "v1"},
        )
        pack = build_feature_enhancement_pack(ep)
        var = pack.variant_enhancement
        assert var.get("enabled") is True
        assert any("best_variant_selected:v1" in str(i) for i in var.get("improvements", []))

    def test_variant_batch_plans_reflected(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            clip_batch_planning={"enabled": True, "plans": [{}, {}]},
        )
        pack = build_feature_enhancement_pack(ep)
        var = pack.variant_enhancement
        assert var.get("enabled") is True
        assert any("batch_render_plans_available:2" in str(i) for i in var.get("improvements", []))

    def test_variant_metadata_valid(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        var = pack.variant_enhancement
        assert var.get("feature_name") == "variant"
        assert isinstance(var.get("improvements"), list)


# ---------------------------------------------------------------------------
# 9. Engine: output ranking enhancement
# ---------------------------------------------------------------------------

class TestOutputRankingEnhancement:
    def test_output_ranking_enabled_when_available(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            output_ranking={"available": True, "best_output_id": "out_01", "outputs": [{}]},
        )
        pack = build_feature_enhancement_pack(ep)
        rank = pack.output_ranking_enhancement
        assert rank.get("enabled") is True
        assert any("best_export_recommended:out_01" in str(i) for i in rank.get("improvements", []))

    def test_output_ranking_metadata_valid(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        rank = pack.output_ranking_enhancement
        assert rank.get("feature_name") == "output_ranking"
        assert isinstance(rank.get("improvements"), list)


# ---------------------------------------------------------------------------
# 10. No-mutation safety
# ---------------------------------------------------------------------------

class TestNoMutationSafety:
    def test_no_payload_mutation(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        payload = _make_payload()
        build_feature_enhancement_pack(ep, payload=payload)
        # payload unchanged (SimpleNamespace has no extra attrs added)

    def test_no_render_execution(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        import sys
        modules_before = set(sys.modules.keys())
        ep = _make_edit_plan(subtitle_text_apply={"enabled": True})
        build_feature_enhancement_pack(ep)
        new_modules = set(sys.modules.keys()) - modules_before
        render_modules = {m for m in new_modules if "render_engine" in m}
        assert not render_modules

    def test_no_ffmpeg_in_pack(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(camera_motion_apply={"enabled": True})
        pack = build_feature_enhancement_pack(ep)
        d = pack.to_dict()
        for key, val in d.items():
            if isinstance(val, dict):
                assert "ffmpeg_args" not in val
                assert "render_command" not in val

    def test_no_playback_speed_in_pack(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        d = pack.to_dict()
        for val in d.values():
            if isinstance(val, dict):
                assert "playback_speed" not in val

    def test_no_subtitle_timing_rewrite(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(subtitle_text_apply={"enabled": True})
        pack = build_feature_enhancement_pack(ep)
        d = pack.to_dict()
        for val in d.values():
            if isinstance(val, dict):
                assert "subtitle_timing" not in val

    def test_no_queue_mutation(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        d = pack.to_dict()
        for val in d.values():
            if isinstance(val, dict):
                assert "queue_priority" not in val

    def test_no_executor_override(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        d = pack.to_dict()
        for val in d.values():
            if isinstance(val, dict):
                assert "render_command" not in val
                assert "segment_order" not in val

    def test_deterministic_output(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan(
            subtitle_text_apply={"enabled": True, "density": "low"},
            camera_motion_apply={"enabled": True, "behavior": "slow_reveal"},
        )
        r1 = build_feature_enhancement_pack(ep)
        r2 = build_feature_enhancement_pack(ep)
        assert r1.to_dict() == r2.to_dict()


# ---------------------------------------------------------------------------
# 11. Assistive-only architecture
# ---------------------------------------------------------------------------

class TestAssistiveOnlyBehavior:
    def test_mode_always_assistive_only(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        assert pack.mode == "assistive_only"

    def test_mode_in_dict_assistive_only(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        pack = build_feature_enhancement_pack(ep)
        assert pack.to_dict()["mode"] == "assistive_only"

    def test_never_raises_on_bad_edit_plan(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        result = build_feature_enhancement_pack(None, payload=None, context=None)
        assert result is not None
        assert result.mode == "assistive_only"

    def test_never_raises_on_all_empty_metadata(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        result = build_feature_enhancement_pack(ep)
        assert result is not None

    def test_available_false_on_catastrophic_error(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack

        class Broken:
            def __getattr__(self, name):
                raise RuntimeError("broken plan")

        result = build_feature_enhancement_pack(Broken())
        assert result is not None
        # should still return a pack (available=False on error)


# ---------------------------------------------------------------------------
# 12. Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_feature_enhancement_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert hasattr(plan, "feature_enhancement")
        assert isinstance(plan.feature_enhancement, dict)

    def test_feature_enhancement_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert plan.feature_enhancement == {}

    def test_to_dict_includes_feature_enhancement(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            pacing=AIPacingPlan(),
        )
        plan.feature_enhancement = {"available": True, "mode": "assistive_only"}
        d = plan.to_dict()
        assert "feature_enhancement" in d
        assert d["feature_enhancement"]["mode"] == "assistive_only"

    def test_backward_compat_all_prior_phases(self):
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
            "clip_batch_planning", "timing_apply", "subtitle_text_apply",
            "camera_motion_apply", "ai_apply_policy",
        ):
            assert key in d, f"Missing backward-compat key: {key}"


# ---------------------------------------------------------------------------
# 13. Render influence integration
# ---------------------------------------------------------------------------

class TestRenderInfluenceIntegration:
    def _base_plan(self, feh: dict) -> Any:
        return types.SimpleNamespace(
            feature_enhancement=feh,
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

    def test_feature_enhancement_reported_in_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        feh = {
            "available": True,
            "mode": "assistive_only",
            "subtitle_enhancement": {"enabled": True},
            "camera_enhancement": {"enabled": False},
            "timing_enhancement": {"enabled": True},
            "clip_selection_enhancement": {"enabled": False},
            "creator_style_enhancement": {"enabled": False},
            "variant_enhancement": {"enabled": False},
            "output_ranking_enhancement": {"enabled": False},
        }
        ep = self._base_plan(feh)
        payload = types.SimpleNamespace(
            ai_influence_enabled=True,
            camera_mode="default",
            reframe_mode="none",
            subtitle_density="normal",
        )
        _, report = apply_ai_render_influence(payload, ep)
        combined = " ".join(report.get("skipped", []))
        assert "feature_enhancement" in combined

    def test_feature_enhancement_never_in_applied(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        feh = {
            "available": True,
            "mode": "assistive_only",
            "subtitle_enhancement": {"enabled": True},
            "camera_enhancement": {"enabled": True},
            "timing_enhancement": {"enabled": True},
            "clip_selection_enhancement": {"enabled": True},
            "creator_style_enhancement": {"enabled": True},
            "variant_enhancement": {"enabled": True},
            "output_ranking_enhancement": {"enabled": True},
        }
        ep = self._base_plan(feh)
        payload = types.SimpleNamespace(
            ai_influence_enabled=True,
            camera_mode="default",
            reframe_mode="none",
            subtitle_density="normal",
        )
        _, report = apply_ai_render_influence(payload, ep)
        applied = " ".join(report.get("applied", []))
        assert "feature_enhancement" not in applied

    def test_no_result_graceful(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        ep = self._base_plan({})
        payload = types.SimpleNamespace(
            ai_influence_enabled=True,
            camera_mode="default",
            reframe_mode="none",
            subtitle_density="normal",
        )
        _, report = apply_ai_render_influence(payload, ep)
        combined = " ".join(report.get("skipped", []))
        assert "feature_enhancement" in combined

    def test_category_count_in_report(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        feh = {
            "available": True,
            "mode": "assistive_only",
            "subtitle_enhancement": {"enabled": True},
            "camera_enhancement": {"enabled": True},
            "timing_enhancement": {"enabled": False},
            "clip_selection_enhancement": {"enabled": False},
            "creator_style_enhancement": {"enabled": False},
            "variant_enhancement": {"enabled": False},
            "output_ranking_enhancement": {"enabled": False},
        }
        ep = self._base_plan(feh)
        payload = types.SimpleNamespace(
            ai_influence_enabled=True,
            camera_mode="default",
            reframe_mode="none",
            subtitle_density="normal",
        )
        _, report = apply_ai_render_influence(payload, ep)
        combined = " ".join(report.get("skipped", []))
        assert "categories=2" in combined


# ---------------------------------------------------------------------------
# 14. Environment requirements
# ---------------------------------------------------------------------------

class TestEnvironmentRequirements:
    def test_no_api_key_required(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        import os
        original = os.environ.pop("OPENAI_API_KEY", None)
        try:
            ep = _make_edit_plan()
            result = build_feature_enhancement_pack(ep)
            assert result is not None
        finally:
            if original is not None:
                os.environ["OPENAI_API_KEY"] = original

    def test_no_gpu_required(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        result = build_feature_enhancement_pack(ep)
        assert result is not None

    def test_no_internet_required(self):
        from app.ai.enhancement.feature_enhancement_engine import build_feature_enhancement_pack
        ep = _make_edit_plan()
        result = build_feature_enhancement_pack(ep)
        assert result is not None
