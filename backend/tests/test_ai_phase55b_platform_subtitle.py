"""
test_ai_phase55b_platform_subtitle.py — Phase 55B Platform Subtitle Intelligence tests.

Covers:
  - platform_subtitle_retriever: retrieval by platform, creator_type, tags
  - platform_subtitle_context: structure, guidance keys, fallback
  - Subtitle-specific JSON packs: TikTok, YouTube Shorts, Instagram Reels,
    podcast, educational
  - Integration: subtitle_quality_evaluator hint, subtitle_preference_inference signal
  - Edit plan: platform_subtitle_context field + to_dict
  - Safety: no subtitle mutation, no forbidden keys, no internet deps
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


def _tiktok_subtitle_item() -> dict:
    return {
        "knowledge_id": "tiktok_sub_test",
        "platform": "tiktok",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "TikTok Subtitle Test",
        "description": "TikTok subtitle guidance",
        "tags": ["tiktok", "subtitle", "compact", "mobile", "readability"],
        "domains": ["subtitle"],
        "guidance": {
            "subtitle": {
                "density_bias": "compact",
                "readability_priority": "high",
                "keyword_emphasis": "selective",
                "line_count_preference": 2,
                "overload_risk_sensitivity": "high",
            }
        },
        "confidence": 0.83,
    }


def _youtube_subtitle_item() -> dict:
    return {
        "knowledge_id": "youtube_sub_test",
        "platform": "youtube_shorts",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "YouTube Shorts Subtitle Test",
        "description": "YouTube Shorts subtitle guidance",
        "tags": ["youtube_shorts", "subtitle", "clarity", "balanced"],
        "domains": ["subtitle"],
        "guidance": {
            "subtitle": {
                "density_bias": "normal",
                "readability_priority": "high",
                "keyword_emphasis": "moderate",
                "line_count_preference": 2,
            }
        },
        "confidence": 0.81,
    }


def _podcast_subtitle_item() -> dict:
    return {
        "knowledge_id": "podcast_sub_test",
        "platform": "general",
        "creator_type": "podcast",
        "version": 1,
        "title": "Podcast Subtitle Test",
        "description": "Podcast subtitle guidance",
        "tags": ["podcast", "subtitle", "clean", "readable", "low_animation"],
        "domains": ["subtitle"],
        "guidance": {
            "subtitle": {
                "density_bias": "normal",
                "readability_priority": "high",
                "keyword_emphasis": "subtle",
                "animation_level": "low",
                "style_preference": "clean_pro",
            }
        },
        "confidence": 0.82,
    }


def _edu_subtitle_item() -> dict:
    return {
        "knowledge_id": "educational_sub_test",
        "platform": "general",
        "creator_type": "educational",
        "version": 1,
        "title": "Educational Subtitle Test",
        "description": "Educational subtitle guidance",
        "tags": ["educational", "subtitle", "clarity", "concept_highlighting"],
        "domains": ["subtitle"],
        "guidance": {
            "subtitle": {
                "density_bias": "normal",
                "readability_priority": "high",
                "keyword_emphasis": "moderate",
                "concept_highlighting": True,
            }
        },
        "confidence": 0.80,
    }


def _camera_only_item() -> dict:
    """A platform pack with camera domain only — should NOT be returned by subtitle retriever."""
    return {
        "knowledge_id": "camera_only_test",
        "platform": "tiktok",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "Camera Only",
        "description": "Camera only",
        "tags": ["tiktok", "camera"],
        "domains": ["camera"],
        "guidance": {"camera": {"stability_priority": "medium"}},
        "confidence": 0.75,
    }


# ---------------------------------------------------------------------------
# Section 1: Retrieval — platform filter
# ---------------------------------------------------------------------------

class TestPlatformSubtitleRetriever:
    def test_retrieves_tiktok_subtitle(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item(), _podcast_subtitle_item()])
        result = retrieve_platform_subtitle_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert all(m["platform"] == "tiktok" for m in result["matches"])

    def test_retrieves_youtube_shorts_subtitle(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_youtube_subtitle_item(), _tiktok_subtitle_item()])
        result = retrieve_platform_subtitle_knowledge(
            platform="youtube_shorts", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert all(m["platform"] == "youtube_shorts" for m in result["matches"])

    def test_retrieves_podcast_subtitle(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_subtitle_item(), _tiktok_subtitle_item()])
        result = retrieve_platform_subtitle_knowledge(
            creator_type="podcast", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert all(m["creator_type"] == "podcast" for m in result["matches"])

    def test_retrieves_educational_subtitle(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_edu_subtitle_item(), _tiktok_subtitle_item()])
        result = retrieve_platform_subtitle_knowledge(
            creator_type="educational", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert all(m["creator_type"] == "educational" for m in result["matches"])

    def test_camera_only_item_excluded(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_camera_only_item()])
        result = retrieve_platform_subtitle_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        assert result["available"] is False

    def test_unknown_platform_returns_unavailable(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item()])
        result = retrieve_platform_subtitle_knowledge(
            platform="twitch", base_path=tmp_path / "platforms"
        )
        assert result["available"] is False

    def test_unknown_creator_type_returns_unavailable(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_subtitle_item()])
        result = retrieve_platform_subtitle_knowledge(
            creator_type="streamer", base_path=tmp_path / "platforms"
        )
        assert result["available"] is False

    def test_no_filter_returns_all_subtitle_items(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [
            _tiktok_subtitle_item(), _podcast_subtitle_item(), _edu_subtitle_item(),
            _camera_only_item(),  # should be excluded
        ])
        result = retrieve_platform_subtitle_knowledge(base_path=tmp_path / "platforms")
        assert result["available"] is True
        assert len(result["matches"]) == 3  # camera-only excluded

    def test_never_raises_on_none_inputs(self):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        result = retrieve_platform_subtitle_knowledge(platform=None, creator_type=None)
        assert result is not None
        assert "available" in result


# ---------------------------------------------------------------------------
# Section 2: Tag filter
# ---------------------------------------------------------------------------

class TestPlatformSubtitleTagFilter:
    def test_tag_filter_compact(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [
            _tiktok_subtitle_item(), _podcast_subtitle_item()
        ])
        result = retrieve_platform_subtitle_knowledge(
            tags=["compact"], base_path=tmp_path / "platforms"
        )
        # Only tiktok item has "compact" tag
        assert result["available"] is True
        assert any(m["knowledge_id"] == "tiktok_sub_test" for m in result["matches"])

    def test_tag_filter_no_match_falls_back_to_unfiltered(self, tmp_path):
        """When no items match the tag, all subtitle items are returned (tag filter only narrows when there's a match)."""
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item()])
        result = retrieve_platform_subtitle_knowledge(
            tags=["unique_nonexistent_tag_xyz"], base_path=tmp_path / "platforms"
        )
        # Falls back to untagged results since no tag match
        assert result["available"] is True


# ---------------------------------------------------------------------------
# Section 3: Determinism + bounds
# ---------------------------------------------------------------------------

class TestPlatformSubtitleDeterminism:
    def test_deterministic_same_inputs(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [
            _tiktok_subtitle_item(), _podcast_subtitle_item(), _edu_subtitle_item()
        ])
        r1 = retrieve_platform_subtitle_knowledge(base_path=tmp_path / "platforms")
        clear_cache()
        _write_platform_dir(tmp_path, [
            _tiktok_subtitle_item(), _podcast_subtitle_item(), _edu_subtitle_item()
        ])
        r2 = retrieve_platform_subtitle_knowledge(base_path=tmp_path / "platforms")
        assert [m["knowledge_id"] for m in r1["matches"]] == [m["knowledge_id"] for m in r2["matches"]]

    def test_max_results_respected(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        items = []
        for i in range(8):
            items.append({
                "knowledge_id": f"sub_{i:02d}",
                "platform": "tiktok", "creator_type": "viral_short_form",
                "version": 1, "title": f"Sub {i}", "description": "",
                "tags": ["tiktok", "subtitle"], "domains": ["subtitle"],
                "guidance": {"subtitle": {"density_bias": "compact"}}, "confidence": 0.80,
            })
        _write_platform_dir(tmp_path, items)
        result = retrieve_platform_subtitle_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms", max_results=2
        )
        assert len(result["matches"]) <= 2

    def test_max_results_clamp_min_1(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item(), _podcast_subtitle_item()])
        result = retrieve_platform_subtitle_knowledge(
            base_path=tmp_path / "platforms", max_results=0
        )
        assert len(result["matches"]) >= 1

    def test_dual_exact_match_ranked_first(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        # Add a tiktok-general that sorts alphabetically before exact match
        tiktok_general = {
            "knowledge_id": "aaa_tiktok_general_sub",
            "platform": "tiktok", "creator_type": "general",
            "version": 1, "title": "TikTok General Sub",
            "description": "", "tags": ["tiktok", "subtitle"],
            "domains": ["subtitle"],
            "guidance": {"subtitle": {"density_bias": "normal"}},
            "confidence": 0.70,
        }
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item(), tiktok_general])
        result = retrieve_platform_subtitle_knowledge(
            platform="tiktok", creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        assert result["matches"][0]["knowledge_id"] == "tiktok_sub_test"


# ---------------------------------------------------------------------------
# Section 4: Context builder
# ---------------------------------------------------------------------------

class TestPlatformSubtitleContext:
    def test_context_available_when_match_found(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item()])
        result = build_platform_subtitle_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        ctx = result["platform_subtitle_context"]
        assert ctx["available"] is True
        assert ctx["platform"] == "tiktok"

    def test_context_has_guidance_dict(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item()])
        result = build_platform_subtitle_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        ctx = result["platform_subtitle_context"]
        assert isinstance(ctx["guidance"], dict)
        assert "density_bias" in ctx["guidance"]

    def test_context_guidance_keys_are_safe(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item()])
        result = build_platform_subtitle_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        guidance = result["platform_subtitle_context"]["guidance"]
        for k in guidance:
            assert k not in ("ffmpeg_args", "render_command", "motion_crop", "subprocess")

    def test_context_fallback_when_no_match(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        plat_dir = tmp_path / "platforms"
        plat_dir.mkdir()
        result = build_platform_subtitle_context(platform="twitch", base_path=plat_dir)
        ctx = result["platform_subtitle_context"]
        assert ctx["available"] is False
        assert ctx["guidance"] == {}
        assert ctx["confidence"] == 0.0

    def test_context_always_returns_dict(self):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        result = build_platform_subtitle_context()
        assert isinstance(result, dict)
        assert "platform_subtitle_context" in result

    def test_context_reasoning_is_list_of_strings(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item()])
        result = build_platform_subtitle_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        reasoning = result["platform_subtitle_context"]["reasoning"]
        assert isinstance(reasoning, list)
        assert all(isinstance(r, str) for r in reasoning)

    def test_context_confidence_in_range(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_subtitle_item()])
        result = build_platform_subtitle_context(
            creator_type="podcast", base_path=tmp_path / "platforms"
        )
        conf = result["platform_subtitle_context"]["confidence"]
        assert 0.0 <= conf <= 1.0

    def test_context_merges_guidance_from_multiple_matches(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        extra = {
            "knowledge_id": "tiktok_sub_extra",
            "platform": "tiktok", "creator_type": "viral_short_form",
            "version": 1, "title": "TikTok Sub Extra",
            "description": "", "tags": ["tiktok", "subtitle"],
            "domains": ["subtitle"],
            "guidance": {"subtitle": {"animation_level": "medium", "density_bias": "compact"}},
            "confidence": 0.75,
        }
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item(), extra])
        result = build_platform_subtitle_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        ctx = result["platform_subtitle_context"]
        assert ctx["available"] is True
        # Merged guidance should have keys from at least one item
        assert "density_bias" in ctx["guidance"]


# ---------------------------------------------------------------------------
# Section 5: Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_edit_plan_has_platform_subtitle_context_field(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "platform_subtitle_context")
        assert isinstance(plan.platform_subtitle_context, dict)

    def test_edit_plan_to_dict_includes_platform_subtitle_context(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.platform_subtitle_context = {"available": True, "platform": "tiktok", "guidance": {}}
        d = plan.to_dict()
        assert "platform_subtitle_context" in d
        assert d["platform_subtitle_context"]["available"] is True

    def test_edit_plan_platform_subtitle_context_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert plan.platform_subtitle_context == {}


# ---------------------------------------------------------------------------
# Section 6: Quality evaluator hint integration
# ---------------------------------------------------------------------------

class TestSubtitleQualityHintIntegration:
    def _make_plan_with_subtitle_ctx(self, guidance: dict, available: bool = True) -> Any:
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.platform_subtitle_context = {
            "available": available,
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "guidance": guidance,
            "confidence": 0.83,
            "reasoning": ["TikTok subtitle guidance supports compact density"],
        }
        return plan

    def test_hint_fires_when_context_available(self):
        from app.ai.subtitle_quality.subtitle_quality_evaluator import _platform_subtitle_hint
        plan = self._make_plan_with_subtitle_ctx({"density_bias": "compact"})
        hint = _platform_subtitle_hint(plan)
        assert isinstance(hint, str)

    def test_hint_returns_empty_when_context_unavailable(self):
        from app.ai.subtitle_quality.subtitle_quality_evaluator import _platform_subtitle_hint
        plan = self._make_plan_with_subtitle_ctx({}, available=False)
        hint = _platform_subtitle_hint(plan)
        assert hint == ""

    def test_hint_returns_empty_when_no_plan(self):
        from app.ai.subtitle_quality.subtitle_quality_evaluator import _platform_subtitle_hint
        assert _platform_subtitle_hint(None) == ""

    def test_hint_never_raises(self):
        from app.ai.subtitle_quality.subtitle_quality_evaluator import _platform_subtitle_hint
        for bad in [None, {}, object(), 42, ""]:
            result = _platform_subtitle_hint(bad)
            assert isinstance(result, str)

    def test_hint_uses_reasoning_when_available(self):
        from app.ai.subtitle_quality.subtitle_quality_evaluator import _platform_subtitle_hint
        plan = self._make_plan_with_subtitle_ctx({"density_bias": "compact"})
        hint = _platform_subtitle_hint(plan)
        assert "TikTok" in hint or "compact" in hint or "density" in hint


# ---------------------------------------------------------------------------
# Section 7: Preference inference signal integration
# ---------------------------------------------------------------------------

class TestSubtitlePreferenceSignalIntegration:
    def _make_plan_with_subtitle_ctx(self, guidance: dict, available: bool = True) -> Any:
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.platform_subtitle_context = {
            "available": available,
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "guidance": guidance,
            "confidence": 0.83,
            "reasoning": ["TikTok platform guidance supports compact subtitle density"],
        }
        return plan

    def test_signal_fires_when_context_available(self):
        from app.ai.creator_subtitle.subtitle_preference_inference import _get_platform_subtitle_signal
        plan = self._make_plan_with_subtitle_ctx({"density_bias": "compact"})
        signal = _get_platform_subtitle_signal(plan)
        assert isinstance(signal, str)

    def test_signal_returns_empty_when_context_unavailable(self):
        from app.ai.creator_subtitle.subtitle_preference_inference import _get_platform_subtitle_signal
        plan = self._make_plan_with_subtitle_ctx({}, available=False)
        signal = _get_platform_subtitle_signal(plan)
        assert signal == ""

    def test_signal_returns_empty_when_no_plan(self):
        from app.ai.creator_subtitle.subtitle_preference_inference import _get_platform_subtitle_signal
        assert _get_platform_subtitle_signal(None) == ""

    def test_signal_never_raises(self):
        from app.ai.creator_subtitle.subtitle_preference_inference import _get_platform_subtitle_signal
        for bad in [None, {}, object(), 42]:
            result = _get_platform_subtitle_signal(bad)
            assert isinstance(result, str)

    def test_signal_truncated_to_100_chars(self):
        from app.ai.creator_subtitle.subtitle_preference_inference import _get_platform_subtitle_signal
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.platform_subtitle_context = {
            "available": True, "platform": "tiktok",
            "guidance": {"density_bias": "compact"},
            "reasoning": ["x" * 200],
            "confidence": 0.83,
        }
        signal = _get_platform_subtitle_signal(plan)
        assert len(signal) <= 100


# ---------------------------------------------------------------------------
# Section 8: Safety
# ---------------------------------------------------------------------------

class TestPlatformSubtitleSafety:
    def test_no_forbidden_keys_in_guidance(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item()])
        result = build_platform_subtitle_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        guidance_str = str(result["platform_subtitle_context"]["guidance"])
        for bad_key in ("ffmpeg_args", "render_command", "motion_crop", "subprocess"):
            assert bad_key not in guidance_str

    def test_no_raw_file_paths_in_reasoning(self, tmp_path):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_subtitle_item()])
        result = build_platform_subtitle_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        reasoning_str = str(result["platform_subtitle_context"]["reasoning"])
        assert ".json" not in reasoning_str
        assert "knowledge/platforms" not in reasoning_str

    def test_no_internet_dependency_in_retriever(self):
        import app.ai.knowledge.platform_subtitle_retriever as mod
        import inspect
        src = inspect.getsource(mod)
        for bad in ("urllib", "requests", "httpx", "aiohttp", "socket"):
            assert bad not in src

    def test_evil_pack_with_forbidden_keys_rejected_entirely(self, tmp_path):
        """The loader safety filter rejects any file containing forbidden execution keys.
        The entire pack is not loaded, so no guidance is surfaced."""
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        evil = {
            "knowledge_id": "evil_sub",
            "platform": "tiktok", "creator_type": "viral_short_form",
            "version": 1, "title": "Evil", "description": "",
            "tags": ["tiktok", "subtitle"], "domains": ["subtitle"],
            "guidance": {
                "subtitle": {
                    "density_bias": "compact",
                    "ffmpeg_args": "dangerous",
                    "motion_crop": "also_dangerous",
                }
            },
            "confidence": 0.80,
        }
        _write_platform_dir(tmp_path, [evil])
        result = build_platform_subtitle_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        # The loader safety filter rejects the entire file — context is unavailable
        ctx = result["platform_subtitle_context"]
        assert ctx["available"] is False
        assert "ffmpeg_args" not in str(ctx)
        assert "motion_crop" not in str(ctx)


# ---------------------------------------------------------------------------
# Section 9: Real seed packs smoke tests
# ---------------------------------------------------------------------------

class TestRealSubtitleSeedPacks:
    def test_real_tiktok_subtitle_pack_loads(self):
        from app.ai.knowledge.platform_knowledge_loader import load_platform_knowledge, clear_cache
        clear_cache()
        items = load_platform_knowledge()
        ids = {i.knowledge_id for i in items}
        assert "tiktok_subtitle_intelligence" in ids

    def test_real_youtube_shorts_subtitle_pack_loads(self):
        from app.ai.knowledge.platform_knowledge_loader import load_platform_knowledge, clear_cache
        clear_cache()
        items = load_platform_knowledge()
        ids = {i.knowledge_id for i in items}
        assert "youtube_shorts_subtitle_intelligence" in ids

    def test_real_podcast_subtitle_pack_loads(self):
        from app.ai.knowledge.platform_knowledge_loader import load_platform_knowledge, clear_cache
        clear_cache()
        items = load_platform_knowledge()
        ids = {i.knowledge_id for i in items}
        assert "podcast_subtitle_intelligence" in ids

    def test_real_educational_subtitle_pack_loads(self):
        from app.ai.knowledge.platform_knowledge_loader import load_platform_knowledge, clear_cache
        clear_cache()
        items = load_platform_knowledge()
        ids = {i.knowledge_id for i in items}
        assert "educational_subtitle_intelligence" in ids

    def test_real_instagram_subtitle_pack_loads(self):
        from app.ai.knowledge.platform_knowledge_loader import load_platform_knowledge, clear_cache
        clear_cache()
        items = load_platform_knowledge()
        ids = {i.knowledge_id for i in items}
        assert "instagram_reels_subtitle_intelligence" in ids

    def test_real_tiktok_subtitle_context_available(self):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        result = build_platform_subtitle_context(platform="tiktok")
        ctx = result["platform_subtitle_context"]
        assert ctx["available"] is True
        assert "density_bias" in ctx["guidance"]

    def test_real_podcast_subtitle_context_available(self):
        from app.ai.knowledge.platform_subtitle_retriever import build_platform_subtitle_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        result = build_platform_subtitle_context(creator_type="podcast")
        ctx = result["platform_subtitle_context"]
        assert ctx["available"] is True

    def test_real_seed_packs_subtitle_guidance_valid(self):
        from app.ai.knowledge.platform_subtitle_retriever import retrieve_platform_subtitle_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        result = retrieve_platform_subtitle_knowledge()
        # All subtitle packs should have guidance.subtitle.density_bias
        for m in result["matches"]:
            subtitle_g = (m.get("guidance") or {}).get("subtitle", {})
            assert "density_bias" in subtitle_g
