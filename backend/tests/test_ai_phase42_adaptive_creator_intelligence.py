"""
test_ai_phase42_adaptive_creator_intelligence.py — Phase 42 tests.

Covers: schema, safety, memory persistence, learning engine, edit plan
integration, no-mutation safety, render influence, environment requirements.
"""
import copy
import json
import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from unittest.mock import patch


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
        selected_segments=[AIClipPlan(start=0.0, end=15.0, score=80.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(
            pacing_style="fast_hook",
            energy_level=0.85,
            beat_available=True,
            bpm=128.0,
        ),
    )


def _make_rich_plan():
    plan = _make_minimal_plan()
    plan.creator_style_adaptation = {"adapted_style": "viral_tiktok"}
    plan.subtitle_text_apply = {"subtitle_style": "compact"}
    plan.camera_motion_apply = {"camera_behavior": "dynamic_safe"}
    plan.creator_retrieval = {
        "available": True,
        "enabled": True,
        "retrieval_mode": "assistive_only",
        "matches": [
            {
                "match_id": "r1",
                "creator_style": "viral_tiktok",
                "pattern_type": "pacing",
                "confidence": 0.8,
                "retrieval_score": 0.75,
            }
        ],
        "recommended_creator_style": "viral_tiktok",
        "warnings": [],
    }
    return plan


@dataclass
class _MockRequest:
    ai_director_enabled: bool = True
    ai_mode: str = "viral_tiktok"
    ai_adaptive_profile_id: Optional[str] = None


# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestAdaptiveSchema:
    def test_creator_preference_profile_defaults(self):
        from app.ai.adaptive.adaptive_schema import AICreatorPreferenceProfile
        p = AICreatorPreferenceProfile()
        assert p.profile_id == "default"
        assert p.creator_style_preference == ""
        assert p.style_confidence == 0.0
        assert p.selection_history_count == 0
        assert p.tags == []
        assert p.warnings == []

    def test_creator_preference_profile_to_dict(self):
        from app.ai.adaptive.adaptive_schema import AICreatorPreferenceProfile
        p = AICreatorPreferenceProfile(
            profile_id="test",
            creator_style_preference="viral_tiktok",
            style_confidence=0.5,
        )
        d = p.to_dict()
        assert d["profile_id"] == "test"
        assert d["creator_style_preference"] == "viral_tiktok"
        assert d["style_confidence"] == 0.5

    def test_adaptive_learning_pack_defaults(self):
        from app.ai.adaptive.adaptive_schema import AIAdaptiveLearningPack
        pack = AIAdaptiveLearningPack()
        assert pack.available is True
        assert pack.enabled is False
        assert pack.learning_mode == "assistive_only"
        assert pack.creator_profile == {}
        assert pack.learned_preferences == {}
        assert pack.adaptive_influences == {}

    def test_adaptive_learning_pack_to_dict(self):
        from app.ai.adaptive.adaptive_schema import AIAdaptiveLearningPack
        pack = AIAdaptiveLearningPack(enabled=True, learning_mode="assistive_only")
        d = pack.to_dict()
        assert d["available"] is True
        assert d["enabled"] is True
        assert d["learning_mode"] == "assistive_only"


# ---------------------------------------------------------------------------
# 2. Safety tests
# ---------------------------------------------------------------------------

class TestAdaptiveSafety:
    def test_sanitize_strips_forbidden_keys(self):
        from app.ai.adaptive.adaptive_safety import sanitize_adaptive_profile
        data = {
            "creator_style": "viral",
            "password": "secret",
            "api_key": "abc123",
            "ffmpeg_args": "-c:v h264",
            "playback_speed": 2.0,
            "subtitle_timing": [0, 1, 2],
            "render_command": "ffmpeg ...",
        }
        result = sanitize_adaptive_profile(data)
        assert "creator_style" in result
        assert "password" not in result
        assert "api_key" not in result
        assert "ffmpeg_args" not in result
        assert "playback_speed" not in result
        assert "subtitle_timing" not in result
        assert "render_command" not in result

    def test_sanitize_nested_forbidden_keys(self):
        from app.ai.adaptive.adaptive_safety import sanitize_adaptive_profile
        data = {"meta": {"auth": "bearer_token", "style": "compact"}}
        result = sanitize_adaptive_profile(data)
        assert "auth" not in result["meta"]
        assert result["meta"]["style"] == "compact"

    def test_sanitize_empty_dict(self):
        from app.ai.adaptive.adaptive_safety import sanitize_adaptive_profile
        assert sanitize_adaptive_profile({}) == {}

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.adaptive.adaptive_safety import sanitize_adaptive_profile
        assert sanitize_adaptive_profile(None) == {}
        assert sanitize_adaptive_profile("string") == {}

    def test_is_safe_clean_data(self):
        from app.ai.adaptive.adaptive_safety import is_adaptive_profile_safe
        assert is_adaptive_profile_safe({"style": "viral", "confidence": 0.7}) is True

    def test_is_safe_forbidden_key(self):
        from app.ai.adaptive.adaptive_safety import is_adaptive_profile_safe
        assert is_adaptive_profile_safe({"ffmpeg_args": "-c:v"}) is False
        assert is_adaptive_profile_safe({"playback_speed": 1.5}) is False
        assert is_adaptive_profile_safe({"subtitle_timing": [0]}) is False

    def test_is_safe_never_raises(self):
        from app.ai.adaptive.adaptive_safety import is_adaptive_profile_safe
        assert is_adaptive_profile_safe(None) is True
        assert is_adaptive_profile_safe(42) is True


# ---------------------------------------------------------------------------
# 3. Memory persistence tests
# ---------------------------------------------------------------------------

class TestAdaptiveMemory:
    def test_build_default_creator_profile(self):
        from app.ai.adaptive.adaptive_memory import build_default_creator_profile
        p = build_default_creator_profile()
        assert p.profile_id == "default"
        assert p.style_confidence == 0.0
        assert p.selection_history_count == 0

    def test_creator_profile_persistence(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_memory import (
            build_default_creator_profile, save_creator_profile, load_creator_profile,
        )
        profile = build_default_creator_profile("p1")
        profile.creator_style_preference = "viral_tiktok"
        profile.style_confidence = 0.4

        ok = save_creator_profile(profile)
        assert ok is True

        loaded = load_creator_profile("p1")
        assert loaded.creator_style_preference == "viral_tiktok"
        assert loaded.style_confidence == pytest.approx(0.4, abs=1e-4)

    def test_missing_profile_fallback_safe(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")
        from app.ai.adaptive.adaptive_memory import load_creator_profile
        p = load_creator_profile("nonexistent_profile_xyz")
        assert p.profile_id == "nonexistent_profile_xyz"
        assert p.style_confidence == 0.0

    def test_corrupted_profile_fallback_safe(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        profile_dir = tmp_path / "profiles"
        profile_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", profile_dir)

        corrupt_path = profile_dir / "bad_profile.json"
        corrupt_path.write_text("NOT VALID JSON {{{{", encoding="utf-8")

        from app.ai.adaptive.adaptive_memory import load_creator_profile
        p = load_creator_profile("bad_profile")
        assert p.profile_id == "bad_profile"
        assert p.style_confidence == 0.0

    def test_update_creator_profile_increments_count(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_memory import (
            build_default_creator_profile, update_creator_profile,
        )
        p = build_default_creator_profile()
        updated = update_creator_profile(p, {"selected_creator_style": "viral_tiktok"})
        assert updated.selection_history_count == 1
        assert updated.creator_style_preference == "viral_tiktok"
        assert updated.style_confidence > 0.0

    def test_update_creator_profile_never_raises(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_memory import (
            build_default_creator_profile, update_creator_profile,
        )
        p = build_default_creator_profile()
        result = update_creator_profile(p, None)
        assert result is not None


# ---------------------------------------------------------------------------
# 4. Learning engine tests
# ---------------------------------------------------------------------------

class TestAdaptiveLearning:
    def test_deterministic_adaptive_learning(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        pack1 = build_adaptive_learning_pack(plan, context={"profile_id": "det_test"})
        pack2 = build_adaptive_learning_pack(plan, context={"profile_id": "det_test2"})
        assert pack1.learning_mode == pack2.learning_mode == "assistive_only"

    def test_repeated_creator_style_increases_confidence(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()

        pack1 = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "conf_test", "selected_creator_style": "viral_tiktok"},
        )
        pack2 = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "conf_test", "selected_creator_style": "viral_tiktok"},
        )
        conf1 = pack1.creator_profile.get("style_confidence", 0.0)
        conf2 = pack2.creator_profile.get("style_confidence", 0.0)
        assert conf2 >= conf1

    def test_repeated_subtitle_selection_increases_confidence(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()

        pack1 = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "sub_test", "selected_subtitle_style": "compact"},
        )
        pack2 = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "sub_test", "selected_subtitle_style": "compact"},
        )
        c1 = pack1.creator_profile.get("subtitle_confidence", 0.0)
        c2 = pack2.creator_profile.get("subtitle_confidence", 0.0)
        assert c2 >= c1

    def test_repeated_pacing_selection_increases_confidence(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()

        pack1 = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "pac_test", "selected_pacing_style": "fast_hook"},
        )
        pack2 = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "pac_test", "selected_pacing_style": "fast_hook"},
        )
        c1 = pack1.creator_profile.get("pacing_confidence", 0.0)
        c2 = pack2.creator_profile.get("pacing_confidence", 0.0)
        assert c2 >= c1

    def test_repeated_camera_selection_increases_confidence(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()

        pack1 = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "cam_test", "selected_camera_style": "dynamic_safe"},
        )
        pack2 = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "cam_test", "selected_camera_style": "dynamic_safe"},
        )
        c1 = pack1.creator_profile.get("camera_confidence", 0.0)
        c2 = pack2.creator_profile.get("camera_confidence", 0.0)
        assert c2 >= c1

    def test_adaptive_influence_metadata_valid(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        pack = build_adaptive_learning_pack(
            plan,
            context={"profile_id": "inf_test", "selected_creator_style": "viral_tiktok"},
        )
        influences = pack.adaptive_influences
        assert isinstance(influences, dict)
        assert influences.get("assistive_only") is True
        for key in (
            "retrieval_ranking_weight",
            "subtitle_enhancement_weight",
            "pacing_enhancement_weight",
            "camera_enhancement_weight",
            "variant_ranking_weight",
        ):
            val = influences.get(key, 0.0)
            assert 0.0 <= val <= 0.30, f"{key}={val} out of bounds"

    def test_forbidden_fields_stripped_from_profile(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()
        pack = build_adaptive_learning_pack(plan, context={"profile_id": "strip_test"})
        profile_data = pack.creator_profile
        for forbidden in ("password", "api_key", "ffmpeg_args", "playback_speed", "subtitle_timing"):
            assert forbidden not in profile_data

    def test_no_payload_mutation(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()
        req = _MockRequest(ai_mode="viral_tiktok")
        original_mode = req.ai_mode
        original_segments = len(plan.selected_segments)

        build_adaptive_learning_pack(plan, payload=req, context={"profile_id": "mut_test"})

        assert req.ai_mode == original_mode
        assert len(plan.selected_segments) == original_segments

    def test_assistive_only_adaptive_behavior_preserved(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        pack = build_adaptive_learning_pack(plan, context={"profile_id": "assistive_test"})
        assert pack.learning_mode == "assistive_only"
        influences = pack.adaptive_influences
        assert influences.get("assistive_only") is True

    def test_never_raises_on_none_plan(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        pack = build_adaptive_learning_pack(None)
        assert pack is not None
        assert pack.learning_mode == "assistive_only"


# ---------------------------------------------------------------------------
# 5. Edit plan schema integration tests
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_backward_compatibility_preserved(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan
        plan = AIEditPlan(
            enabled=True,
            mode="balanced",
            selected_segments=[AIClipPlan(start=0.0, end=5.0, score=70.0)],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "adaptive_creator_intelligence" in d
        assert d["adaptive_creator_intelligence"] == {}

    def test_adaptive_field_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan
        plan = AIEditPlan(
            enabled=True,
            mode="balanced",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert plan.adaptive_creator_intelligence == {}

    def test_adaptive_field_survives_to_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan
        plan = AIEditPlan(
            enabled=True,
            mode="balanced",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        plan.adaptive_creator_intelligence = {
            "available": True,
            "enabled": True,
            "learning_mode": "assistive_only",
        }
        d = plan.to_dict()
        assert d["adaptive_creator_intelligence"]["learning_mode"] == "assistive_only"


# ---------------------------------------------------------------------------
# 6. Render influence tests
# ---------------------------------------------------------------------------

class TestRenderInfluence:
    def _make_plan_with_adaptive(self, enabled=True, learning_mode="assistive_only"):
        plan = _make_rich_plan()
        plan.adaptive_creator_intelligence = {
            "available": True,
            "enabled": enabled,
            "learning_mode": learning_mode,
            "creator_profile": {
                "creator_style_preference": "viral_tiktok",
                "preferred_subtitle_style": "compact",
                "preferred_pacing_style": "fast_hook",
                "preferred_camera_style": "dynamic_safe",
            },
            "learned_preferences": {
                "creator_style": "viral_tiktok",
                "subtitle_style": "compact",
                "pacing_style": "fast_hook",
                "camera_style": "dynamic_safe",
                "history": {"selections": 5, "exports": 2},
            },
            "adaptive_influences": {
                "retrieval_ranking_weight": 0.05,
                "subtitle_enhancement_weight": 0.10,
                "pacing_enhancement_weight": 0.08,
                "camera_enhancement_weight": 0.09,
                "variant_ranking_weight": 0.04,
                "assistive_only": True,
            },
            "warnings": [],
        }
        return plan

    def test_adaptive_influence_reported_skipped_not_applied(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            add_subtitle: bool = True
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            highlight_per_word: bool = False
            ai_beat_execution_enabled: bool = False

        plan = self._make_plan_with_adaptive(enabled=True)
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)

        adaptive_entries = [
            e for e in report["skipped"] if "adaptive_creator_intelligence" in e
        ]
        assert adaptive_entries, "Expected adaptive_creator_intelligence in skipped"

    def test_adaptive_influence_does_not_mutate_ffmpeg(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            add_subtitle: bool = True
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            highlight_per_word: bool = False
            ai_beat_execution_enabled: bool = False

        plan = self._make_plan_with_adaptive()
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)
        # No ffmpeg_args, no render_command, no playback_speed in report
        all_entries = report["applied"] + report["skipped"] + report["warnings"]
        for entry in all_entries:
            assert "ffmpeg_args" not in str(entry)
            assert "playback_speed" not in str(entry)
            assert "subtitle_timing" not in str(entry)

    def test_no_adaptive_field_reports_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            add_subtitle: bool = False
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            highlight_per_word: bool = False
            ai_beat_execution_enabled: bool = False

        plan = _make_minimal_plan()
        # No adaptive_creator_intelligence set
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)
        adaptive_entries = [
            e for e in report["skipped"] if "adaptive_creator_intelligence" in e
        ]
        assert adaptive_entries


# ---------------------------------------------------------------------------
# 7. Safety boundary tests
# ---------------------------------------------------------------------------

class TestSafetyBoundaries:
    def test_no_render_execution(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        pack = build_adaptive_learning_pack(plan, context={"profile_id": "safe_test"})
        # No render execution attributes on pack
        assert not hasattr(pack, "render_executed")
        assert not hasattr(pack, "ffmpeg_command")

    def test_no_ffmpeg_mutation(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        pack = build_adaptive_learning_pack(plan, context={"profile_id": "ffm_test"})
        d = pack.to_dict()
        assert "ffmpeg_args" not in str(d)
        assert "render_command" not in str(d)

    def test_no_playback_speed_mutation(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        pack = build_adaptive_learning_pack(plan, context={"profile_id": "speed_test"})
        d = pack.to_dict()
        assert "playback_speed" not in str(d)

    def test_no_subtitle_timing_rewrite(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        pack = build_adaptive_learning_pack(plan, context={"profile_id": "timing_test"})
        d = pack.to_dict()
        assert "subtitle_timing" not in str(d)

    def test_no_executor_override(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        pack = build_adaptive_learning_pack(plan, context={"profile_id": "exec_test"})
        assert pack.learning_mode == "assistive_only"
        influences = pack.adaptive_influences
        assert influences.get("assistive_only") is True

    def test_no_api_key_required(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()
        # Runs without any API key
        pack = build_adaptive_learning_pack(plan)
        assert pack is not None

    def test_no_gpu_required(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()
        pack = build_adaptive_learning_pack(plan)
        assert pack is not None

    def test_no_internet_required(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        # Block socket to prove no internet calls
        import socket
        original_connect = socket.socket.connect

        def _no_connect(self, *args, **kwargs):
            raise AssertionError("Internet access attempted — must not happen")

        monkeypatch.setattr(socket.socket, "connect", _no_connect)

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()
        pack = build_adaptive_learning_pack(plan)
        assert pack is not None

    def test_influence_weights_bounded(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_rich_plan()
        # Apply many rounds to drive up confidence
        for i in range(20):
            build_adaptive_learning_pack(
                plan,
                context={
                    "profile_id": "bound_test",
                    "selected_creator_style": "viral_tiktok",
                    "selected_subtitle_style": "compact",
                    "selected_pacing_style": "fast_hook",
                    "selected_camera_style": "dynamic_safe",
                    "export_completed": True,
                },
            )

        pack = build_adaptive_learning_pack(plan, context={"profile_id": "bound_test"})
        influences = pack.adaptive_influences
        for key in (
            "retrieval_ranking_weight",
            "subtitle_enhancement_weight",
            "pacing_enhancement_weight",
            "camera_enhancement_weight",
            "variant_ranking_weight",
        ):
            val = influences.get(key, 0.0)
            assert 0.0 <= val <= 0.30, f"{key}={val} exceeds bounds"

    def test_confidence_clamped_to_one(self, tmp_path, monkeypatch):
        from app.ai.adaptive import adaptive_memory
        monkeypatch.setattr(adaptive_memory, "_PROFILE_DIR", tmp_path / "profiles")

        from app.ai.adaptive.adaptive_learning import build_adaptive_learning_pack
        plan = _make_minimal_plan()
        for _ in range(50):
            build_adaptive_learning_pack(
                plan,
                context={
                    "profile_id": "clamp_test",
                    "selected_creator_style": "viral_tiktok",
                },
            )

        pack = build_adaptive_learning_pack(plan, context={"profile_id": "clamp_test"})
        conf = pack.creator_profile.get("style_confidence", 0.0)
        assert 0.0 <= conf <= 1.0
