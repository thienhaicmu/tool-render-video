"""
test_ai_phase55c_platform_camera.py — Phase 55C Platform Camera Intelligence tests.

Covers:
  - platform_camera_retriever: retrieval by platform, creator_type, tags
  - platform_camera_context: structure, guidance keys, fallback
  - Camera-specific JSON packs: TikTok, YouTube Shorts, Instagram Reels,
    podcast, educational
  - Integration: camera_quality_evaluator hint, camera_preference_inference signal
  - Edit plan: platform_camera_context field + to_dict
  - Safety: no camera mutation, no forbidden keys, no internet deps
  - Fallback: missing platform, unknown creator_type, empty directory
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_platform_dir(base: Path, items: list) -> Path:
    plat_dir = base / "platforms"
    plat_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        fname = f"{item['knowledge_id']}.json"
        (plat_dir / fname).write_text(json.dumps(item), encoding="utf-8")
    return plat_dir


def _tiktok_camera_item() -> dict:
    return {
        "knowledge_id": "tiktok_cam_test",
        "platform": "tiktok",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "TikTok Camera Test",
        "description": "TikTok camera guidance",
        "tags": ["tiktok", "camera", "dynamic", "motion_energy", "tracking"],
        "domains": ["camera"],
        "guidance": {
            "camera": {
                "motion_energy": "high",
                "stability_priority": "medium",
                "jitter_sensitivity": "low",
                "subject_continuity": "high",
                "deadzone_bias": "narrow",
                "crop_aggressiveness_guidance": "medium",
                "smoothness_priority": "medium",
            }
        },
        "confidence": 0.82,
    }


def _youtube_camera_item() -> dict:
    return {
        "knowledge_id": "youtube_cam_test",
        "platform": "youtube_shorts",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "YouTube Shorts Camera Test",
        "description": "YouTube Shorts camera guidance",
        "tags": ["youtube_shorts", "camera", "smooth", "stable", "balanced"],
        "domains": ["camera"],
        "guidance": {
            "camera": {
                "motion_energy": "medium",
                "stability_priority": "high",
                "jitter_sensitivity": "medium",
                "subject_continuity": "high",
                "deadzone_bias": "medium",
                "crop_aggressiveness_guidance": "low",
                "smoothness_priority": "high",
            }
        },
        "confidence": 0.80,
    }


def _podcast_camera_item() -> dict:
    return {
        "knowledge_id": "podcast_cam_test",
        "platform": "general",
        "creator_type": "podcast",
        "version": 1,
        "title": "Podcast Camera Test",
        "description": "Podcast camera guidance",
        "tags": ["podcast", "camera", "stable", "static", "wide_deadzone"],
        "domains": ["camera"],
        "guidance": {
            "camera": {
                "motion_energy": "low",
                "stability_priority": "high",
                "jitter_sensitivity": "high",
                "subject_continuity": "high",
                "deadzone_bias": "wide",
                "crop_aggressiveness_guidance": "low",
                "smoothness_priority": "high",
            }
        },
        "confidence": 0.85,
    }


def _educational_camera_item() -> dict:
    return {
        "knowledge_id": "educational_cam_test",
        "platform": "general",
        "creator_type": "educational",
        "version": 1,
        "title": "Educational Camera Test",
        "description": "Educational creator camera guidance",
        "tags": ["educational", "camera", "stable", "smooth", "focus"],
        "domains": ["camera"],
        "guidance": {
            "camera": {
                "motion_energy": "low",
                "stability_priority": "high",
                "jitter_sensitivity": "high",
                "subject_continuity": "high",
                "deadzone_bias": "wide",
                "crop_aggressiveness_guidance": "low",
                "smoothness_priority": "high",
            }
        },
        "confidence": 0.84,
    }


@dataclass
class _FakePlan:
    platform_camera_context: dict = field(default_factory=dict)
    platform_subtitle_context: dict = field(default_factory=dict)

    camera_motion_apply: dict = field(default_factory=dict)
    adaptive_creator_intelligence: dict = field(default_factory=dict)
    creator_feedback_intelligence: dict = field(default_factory=dict)
    market_optimization_intelligence: dict = field(default_factory=dict)
    render_quality_evaluation: dict = field(default_factory=dict)
    creator_preset_evolution: dict = field(default_factory=dict)
    safe_influence_pack: dict = field(default_factory=dict)
    multi_signal_orchestration: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1. Seed packs exist and load correctly
# ---------------------------------------------------------------------------

class TestCameraPacksOnDisk:
    def test_tiktok_camera_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "tiktok_camera_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_youtube_shorts_camera_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "youtube_shorts_camera_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_instagram_reels_camera_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "instagram_reels_camera_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_podcast_camera_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "podcast_camera_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_educational_camera_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "educational_camera_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_tiktok_pack_has_camera_domain(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        data = json.loads((Path(path) / "tiktok_camera_intelligence.json").read_text())
        assert "camera" in data["domains"]

    def test_podcast_pack_has_motion_energy_low(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        data = json.loads((Path(path) / "podcast_camera_intelligence.json").read_text())
        assert data["guidance"]["camera"]["motion_energy"] == "low"

    def test_tiktok_pack_has_motion_energy_high(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        data = json.loads((Path(path) / "tiktok_camera_intelligence.json").read_text())
        assert data["guidance"]["camera"]["motion_energy"] == "high"

    def test_no_forbidden_keys_in_any_camera_pack(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        forbidden = {"ffmpeg_args", "render_command", "motion_crop", "tracking_config"}
        for fname in ["tiktok_camera_intelligence.json", "youtube_shorts_camera_intelligence.json",
                      "instagram_reels_camera_intelligence.json", "podcast_camera_intelligence.json",
                      "educational_camera_intelligence.json"]:
            data = json.loads((Path(path) / fname).read_text())
            flat = str(data)
            for key in forbidden:
                assert key not in flat, f"Forbidden key '{key}' found in {fname}"


# ---------------------------------------------------------------------------
# 2. Retrieval by platform
# ---------------------------------------------------------------------------

class TestRetrievalByPlatform:
    def test_tiktok_retrieval_returns_available(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = retrieve_platform_camera_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["platform"] == "tiktok"
        assert len(result["matches"]) == 1

    def test_youtube_retrieval_returns_available(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_youtube_camera_item()])
        result = retrieve_platform_camera_knowledge(
            platform="youtube_shorts", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["platform"] == "youtube_shorts"

    def test_unknown_platform_returns_not_available(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = retrieve_platform_camera_knowledge(
            platform="unknown_platform", base_path=tmp_path / "platforms"
        )
        assert result["available"] is False

    def test_empty_platform_returns_all_camera_items(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item(), _youtube_camera_item()])
        result = retrieve_platform_camera_knowledge(
            platform="", creator_type="", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert len(result["matches"]) >= 2


# ---------------------------------------------------------------------------
# 3. Retrieval by creator_type
# ---------------------------------------------------------------------------

class TestRetrievalByCreatorType:
    def test_podcast_retrieval_by_creator_type(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_camera_item()])
        result = retrieve_platform_camera_knowledge(
            creator_type="podcast", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["matches"][0]["creator_type"] == "podcast"

    def test_educational_retrieval_by_creator_type(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_educational_camera_item()])
        result = retrieve_platform_camera_knowledge(
            creator_type="educational", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["matches"][0]["creator_type"] == "educational"

    def test_unknown_creator_type_returns_not_available(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_camera_item()])
        result = retrieve_platform_camera_knowledge(
            creator_type="unknown_type", base_path=tmp_path / "platforms"
        )
        assert result["available"] is False


# ---------------------------------------------------------------------------
# 4. Dual-match prioritization
# ---------------------------------------------------------------------------

class TestDualMatchPriority:
    def test_exact_dual_match_ranked_first(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        items = [_tiktok_camera_item(), _youtube_camera_item()]
        _write_platform_dir(tmp_path, items)
        result = retrieve_platform_camera_knowledge(
            platform="tiktok",
            creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        assert result["available"] is True
        assert result["matches"][0]["platform"] == "tiktok"

    def test_platform_filter_excludes_non_matching_items(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        items = [_tiktok_camera_item(), _podcast_camera_item()]
        _write_platform_dir(tmp_path, items)
        result = retrieve_platform_camera_knowledge(
            platform="tiktok",
            base_path=tmp_path / "platforms",
            max_results=5,
        )
        assert result["available"] is True
        platforms = [m["platform"] for m in result["matches"]]
        assert "tiktok" in platforms
        assert "general" not in platforms


# ---------------------------------------------------------------------------
# 5. Tag filter
# ---------------------------------------------------------------------------

class TestTagFilter:
    def test_tag_filter_narrows_results(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item(), _youtube_camera_item()])
        result = retrieve_platform_camera_knowledge(
            tags=["smooth"],
            base_path=tmp_path / "platforms",
        )
        assert result["available"] is True
        ids = [m["knowledge_id"] for m in result["matches"]]
        assert "youtube_cam_test" in ids

    def test_unmatched_tag_falls_back_to_all_camera_items(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = retrieve_platform_camera_knowledge(
            tags=["nonexistent_tag_xyz"],
            base_path=tmp_path / "platforms",
        )
        assert result["available"] is True
        assert len(result["matches"]) >= 1


# ---------------------------------------------------------------------------
# 6. build_platform_camera_context structure
# ---------------------------------------------------------------------------

class TestBuildPlatformCameraContext:
    def test_context_structure_when_available(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = build_platform_camera_context(
            platform="tiktok",
            creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        assert "platform_camera_context" in result
        ctx = result["platform_camera_context"]
        assert ctx["available"] is True
        assert ctx["platform"] == "tiktok"
        assert ctx["creator_type"] == "viral_short_form"
        assert "guidance" in ctx
        assert "confidence" in ctx
        assert "reasoning" in ctx

    def test_context_fallback_on_empty_dir(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        empty = tmp_path / "platforms"
        empty.mkdir()
        result = build_platform_camera_context(
            platform="tiktok",
            base_path=empty,
        )
        ctx = result["platform_camera_context"]
        assert ctx["available"] is False
        assert ctx["guidance"] == {}

    def test_guidance_contains_only_safe_keys(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        item = _tiktok_camera_item()
        item["guidance"]["camera"]["ffmpeg_args"] = "evil"
        _write_platform_dir(tmp_path, [item])
        from app.ai.knowledge.platform_knowledge_loader import _is_safe
        if not _is_safe(item):
            pytest.skip("Loader rejects file entirely — no guidance to check")
        result = build_platform_camera_context(
            platform="tiktok",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_camera_context"]
        guidance = ctx.get("guidance", {})
        assert "ffmpeg_args" not in guidance

    def test_guidance_has_motion_energy(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = build_platform_camera_context(
            platform="tiktok",
            creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_camera_context"]
        assert "motion_energy" in ctx["guidance"]
        assert ctx["guidance"]["motion_energy"] == "high"

    def test_podcast_context_has_low_motion_energy(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_camera_item()])
        result = build_platform_camera_context(
            creator_type="podcast",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_camera_context"]
        assert ctx["available"] is True
        assert ctx["guidance"].get("motion_energy") == "low"

    def test_reasoning_is_list(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = build_platform_camera_context(
            platform="tiktok",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_camera_context"]
        assert isinstance(ctx["reasoning"], list)

    def test_confidence_in_range(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = build_platform_camera_context(
            platform="tiktok",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_camera_context"]
        assert 0.0 <= ctx["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# 7. Safety filter
# ---------------------------------------------------------------------------

class TestSafetyFilter:
    def test_evil_pack_forbidden_key_rejected(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        evil = {
            "knowledge_id": "evil_cam",
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "version": 1,
            "title": "Evil Camera Pack",
            "description": "evil",
            "tags": ["tiktok", "camera"],
            "domains": ["camera"],
            "guidance": {
                "camera": {
                    "motion_energy": "high",
                    "ffmpeg_args": "-vf scale=1920:1080",
                }
            },
            "confidence": 0.9,
        }
        plat_dir = tmp_path / "platforms"
        plat_dir.mkdir()
        (plat_dir / "evil_cam.json").write_text(json.dumps(evil), encoding="utf-8")
        result = build_platform_camera_context(
            platform="tiktok",
            base_path=plat_dir,
        )
        ctx = result["platform_camera_context"]
        # Either the whole file is rejected (available=False) or forbidden keys stripped
        if ctx["available"]:
            assert "ffmpeg_args" not in ctx.get("guidance", {})
        else:
            assert ctx["available"] is False

    def test_never_raises_on_bad_input(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import (
            retrieve_platform_camera_knowledge,
            build_platform_camera_context,
        )
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        assert retrieve_platform_camera_knowledge(platform=None, creator_type=None, base_path=tmp_path / "platforms") is not None
        assert build_platform_camera_context(platform=None, base_path=tmp_path / "platforms") is not None

    def test_no_forbidden_keys_in_output(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import build_platform_camera_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = build_platform_camera_context(
            platform="tiktok",
            base_path=tmp_path / "platforms",
        )
        forbidden = {"ffmpeg_args", "render_command", "motion_crop", "tracking_config"}
        flat = str(result)
        for key in forbidden:
            assert key not in flat


# ---------------------------------------------------------------------------
# 8. camera_quality_evaluator hint integration
# ---------------------------------------------------------------------------

class TestCameraQualityEvaluatorHint:
    def test_platform_hint_appended_when_available(self):
        from app.ai.camera_quality.camera_quality_evaluator import _platform_camera_hint
        plan = _FakePlan(platform_camera_context={
            "available": True,
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "guidance": {"motion_energy": "high", "stability_priority": "medium"},
            "confidence": 0.82,
            "reasoning": ["TikTok Camera Test recommends high motion energy with medium stability priority"],
        })
        hint = _platform_camera_hint(plan)
        assert isinstance(hint, str)
        assert len(hint) > 0

    def test_platform_hint_empty_when_not_available(self):
        from app.ai.camera_quality.camera_quality_evaluator import _platform_camera_hint
        plan = _FakePlan(platform_camera_context={"available": False})
        assert _platform_camera_hint(plan) == ""

    def test_platform_hint_empty_on_missing_context(self):
        from app.ai.camera_quality.camera_quality_evaluator import _platform_camera_hint
        plan = _FakePlan()
        assert _platform_camera_hint(plan) == ""

    def test_platform_hint_empty_on_none_plan(self):
        from app.ai.camera_quality.camera_quality_evaluator import _platform_camera_hint
        assert _platform_camera_hint(None) == ""

    def test_evaluator_does_not_raise_with_platform_context(self):
        from app.ai.camera_quality.camera_quality_evaluator import evaluate_camera_quality_v2
        plan = _FakePlan(platform_camera_context={
            "available": True,
            "platform": "tiktok",
            "guidance": {"motion_energy": "high"},
            "confidence": 0.82,
            "reasoning": ["Platform recommends high motion energy"],
        })
        result = evaluate_camera_quality_v2(plan)
        assert "camera_quality_v2" in result

    def test_hint_uses_reasoning_first(self):
        from app.ai.camera_quality.camera_quality_evaluator import _platform_camera_hint
        plan = _FakePlan(platform_camera_context={
            "available": True,
            "platform": "tiktok",
            "guidance": {"motion_energy": "high"},
            "confidence": 0.82,
            "reasoning": ["Custom reasoning line from platform"],
        })
        hint = _platform_camera_hint(plan)
        assert "Custom reasoning line from platform" in hint

    def test_hint_fallback_uses_platform_and_motion(self):
        from app.ai.camera_quality.camera_quality_evaluator import _platform_camera_hint
        plan = _FakePlan(platform_camera_context={
            "available": True,
            "platform": "tiktok",
            "guidance": {"motion_energy": "high", "stability_priority": "medium"},
            "confidence": 0.82,
            "reasoning": [],
        })
        hint = _platform_camera_hint(plan)
        assert hint != ""
        assert "tiktok" in hint.lower() or "motion" in hint.lower()


# ---------------------------------------------------------------------------
# 9. camera_preference_inference signal integration
# ---------------------------------------------------------------------------

class TestCameraPreferenceInferenceSignal:
    def test_platform_signal_appended_when_available(self):
        from app.ai.creator_camera.camera_preference_inference import _get_platform_camera_signal
        plan = _FakePlan(platform_camera_context={
            "available": True,
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "guidance": {"motion_energy": "high", "stability_priority": "medium"},
            "confidence": 0.82,
            "reasoning": ["TikTok favors high motion energy for dynamic tracking"],
        })
        signal = _get_platform_camera_signal(plan)
        assert isinstance(signal, str)
        assert len(signal) > 0

    def test_platform_signal_empty_when_not_available(self):
        from app.ai.creator_camera.camera_preference_inference import _get_platform_camera_signal
        plan = _FakePlan(platform_camera_context={"available": False})
        assert _get_platform_camera_signal(plan) == ""

    def test_platform_signal_empty_on_none_plan(self):
        from app.ai.creator_camera.camera_preference_inference import _get_platform_camera_signal
        assert _get_platform_camera_signal(None) == ""

    def test_platform_signal_truncated_to_100_chars(self):
        from app.ai.creator_camera.camera_preference_inference import _get_platform_camera_signal
        long_reason = "X" * 200
        plan = _FakePlan(platform_camera_context={
            "available": True,
            "platform": "tiktok",
            "guidance": {},
            "confidence": 0.8,
            "reasoning": [long_reason],
        })
        signal = _get_platform_camera_signal(plan)
        assert len(signal) <= 100

    def test_infer_camera_preference_does_not_raise_with_platform_context(self):
        from app.ai.creator_camera.camera_preference_inference import infer_camera_preference
        plan = _FakePlan(platform_camera_context={
            "available": True,
            "platform": "tiktok",
            "guidance": {"motion_energy": "high"},
            "confidence": 0.82,
            "reasoning": ["Platform recommends high motion energy"],
        })
        result = infer_camera_preference(plan)
        assert result is not None

    def test_signal_does_not_exceed_max_signals(self):
        from app.ai.creator_camera.camera_preference_inference import infer_camera_preference
        plan = _FakePlan(
            safe_influence_pack={"safe_influence": {"camera_motion_bias": "dynamic_subject"}},
            platform_camera_context={
                "available": True,
                "platform": "tiktok",
                "guidance": {"motion_energy": "high"},
                "confidence": 0.82,
                "reasoning": ["TikTok recommends high motion energy"],
            },
        )
        result = infer_camera_preference(plan)
        assert len(result.signals) <= 5


# ---------------------------------------------------------------------------
# 10. Edit plan integration
# ---------------------------------------------------------------------------

class TestEditPlanIntegration:
    def _make_plan(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        return AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )

    def test_platform_camera_context_field_exists(self):
        plan = self._make_plan()
        assert hasattr(plan, "platform_camera_context")
        assert isinstance(plan.platform_camera_context, dict)

    def test_platform_camera_context_in_to_dict(self):
        plan = self._make_plan()
        plan.platform_camera_context = {"available": True, "platform": "tiktok"}
        d = plan.to_dict()
        assert "platform_camera_context" in d
        assert d["platform_camera_context"]["available"] is True

    def test_platform_camera_context_default_empty(self):
        plan = self._make_plan()
        assert plan.platform_camera_context == {}

    def test_to_dict_still_has_platform_subtitle_context(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "platform_subtitle_context" in d
        assert "platform_camera_context" in d


# ---------------------------------------------------------------------------
# 11. Max results clamping
# ---------------------------------------------------------------------------

class TestMaxResultsClamping:
    def test_max_results_clamped_to_10(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        items = [_tiktok_camera_item()]
        _write_platform_dir(tmp_path, items)
        result = retrieve_platform_camera_knowledge(
            platform="tiktok",
            max_results=999,
            base_path=tmp_path / "platforms",
        )
        assert len(result["matches"]) <= 10

    def test_max_results_minimum_is_1(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_camera_item()])
        result = retrieve_platform_camera_knowledge(
            platform="tiktok",
            max_results=0,
            base_path=tmp_path / "platforms",
        )
        assert result["available"] is True
        assert len(result["matches"]) >= 1


# ---------------------------------------------------------------------------
# 12. Non-camera items are filtered out
# ---------------------------------------------------------------------------

class TestCameraDomainFilter:
    def test_subtitle_only_item_not_returned(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        subtitle_only = {
            "knowledge_id": "tiktok_sub_only",
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "version": 1,
            "title": "TikTok Subtitle Only",
            "description": "subtitle only",
            "tags": ["tiktok", "subtitle"],
            "domains": ["subtitle"],
            "guidance": {"subtitle": {"density_bias": "compact"}},
            "confidence": 0.80,
        }
        _write_platform_dir(tmp_path, [subtitle_only])
        result = retrieve_platform_camera_knowledge(
            platform="tiktok",
            base_path=tmp_path / "platforms",
        )
        assert result["available"] is False

    def test_camera_item_from_mixed_directory(self, tmp_path):
        from app.ai.knowledge.platform_camera_retriever import retrieve_platform_camera_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        subtitle_only = {
            "knowledge_id": "tiktok_sub_only",
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "version": 1,
            "title": "TikTok Subtitle Only",
            "description": "subtitle only",
            "tags": ["tiktok", "subtitle"],
            "domains": ["subtitle"],
            "guidance": {"subtitle": {"density_bias": "compact"}},
            "confidence": 0.80,
        }
        _write_platform_dir(tmp_path, [subtitle_only, _tiktok_camera_item()])
        result = retrieve_platform_camera_knowledge(
            platform="tiktok",
            base_path=tmp_path / "platforms",
        )
        assert result["available"] is True
        assert all("camera" in (m.get("guidance") or {}) for m in result["matches"])
