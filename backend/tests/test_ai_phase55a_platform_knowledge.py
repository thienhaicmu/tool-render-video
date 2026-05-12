"""
test_ai_phase55a_platform_knowledge.py — Phase 55A Platform Knowledge Foundation tests.

Covers:
  - Schema: AIPlatformKnowledgeItem, AIPlatformKnowledgePack, AIPlatformContext
  - Loader: valid pack loading, malformed pack skipped, safety filter, cache
  - Retriever: platform filter, creator_type filter, dual filter, no filter,
               deterministic ordering, bounded results, fallback-safe
  - Context builder: available=True / fallback
  - Edit plan: field present, to_dict includes platform_context
  - Safety: no executable content, no forbidden keys in output
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_platform_dir(base: Path, items: list[dict]) -> Path:
    """Write platform knowledge JSON files into base/platforms/."""
    plat_dir = base / "platforms"
    plat_dir.mkdir(parents=True, exist_ok=True)
    for item in items:
        fname = f"{item['knowledge_id']}.json"
        (plat_dir / fname).write_text(json.dumps(item), encoding="utf-8")
    return plat_dir


def _tiktok_item() -> dict:
    return {
        "knowledge_id": "tiktok_shortform_test",
        "platform": "tiktok",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "TikTok Short-Form Test",
        "description": "Test pack for TikTok",
        "tags": ["tiktok", "shortform", "viral"],
        "domains": ["subtitle", "camera", "hook"],
        "guidance": {
            "subtitle": {"density_bias": "compact"},
            "hook": {"first_3s_priority": "high"},
        },
        "confidence": 0.82,
    }


def _podcast_item() -> dict:
    return {
        "knowledge_id": "podcast_test",
        "platform": "general",
        "creator_type": "podcast",
        "version": 1,
        "title": "Podcast Creator Test",
        "description": "Test pack for podcast creators",
        "tags": ["podcast", "talking_head", "clean"],
        "domains": ["subtitle", "camera"],
        "guidance": {
            "subtitle": {"density_bias": "normal"},
            "camera": {"stability_priority": "high"},
        },
        "confidence": 0.81,
    }


def _edu_item() -> dict:
    return {
        "knowledge_id": "educational_test",
        "platform": "general",
        "creator_type": "educational",
        "version": 1,
        "title": "Educational Creator Test",
        "description": "Test pack for educational creators",
        "tags": ["educational", "clarity", "structured"],
        "domains": ["subtitle", "camera", "hook"],
        "guidance": {"subtitle": {"clarity_priority": "high"}},
        "confidence": 0.79,
    }


def _youtube_shorts_item() -> dict:
    return {
        "knowledge_id": "youtube_shorts_test",
        "platform": "youtube_shorts",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "YouTube Shorts Test",
        "description": "Test pack for YouTube Shorts",
        "tags": ["youtube_shorts", "shortform", "mobile"],
        "domains": ["subtitle", "camera", "hook"],
        "guidance": {"hook": {"first_3s_priority": "high"}},
        "confidence": 0.80,
    }


# ---------------------------------------------------------------------------
# Section 1: Schema
# ---------------------------------------------------------------------------

class TestPlatformKnowledgeSchema:
    def test_item_default_fields(self):
        from app.ai.knowledge.platform_knowledge_schema import AIPlatformKnowledgeItem
        item = AIPlatformKnowledgeItem(knowledge_id="test_id")
        assert item.knowledge_id == "test_id"
        assert item.platform == ""
        assert item.creator_type == ""
        assert item.version == 1
        assert item.domains == []
        assert item.guidance == {}
        assert item.confidence == 0.0

    def test_item_to_dict_complete(self):
        from app.ai.knowledge.platform_knowledge_schema import AIPlatformKnowledgeItem
        item = AIPlatformKnowledgeItem(
            knowledge_id="tiktok_test",
            platform="tiktok",
            creator_type="viral_short_form",
            version=1,
            title="Test",
            domains=["subtitle", "hook"],
            guidance={"subtitle": {"density_bias": "compact"}},
            confidence=0.82,
        )
        d = item.to_dict()
        assert d["knowledge_id"] == "tiktok_test"
        assert d["platform"] == "tiktok"
        assert d["creator_type"] == "viral_short_form"
        assert d["domains"] == ["subtitle", "hook"]
        assert d["guidance"]["subtitle"]["density_bias"] == "compact"
        assert d["confidence"] == 0.82

    def test_pack_default_available_false(self):
        from app.ai.knowledge.platform_knowledge_schema import AIPlatformKnowledgePack
        pack = AIPlatformKnowledgePack()
        assert pack.available is False
        assert pack.matches == []
        assert pack.confidence == 0.0

    def test_pack_to_dict_keys(self):
        from app.ai.knowledge.platform_knowledge_schema import AIPlatformKnowledgePack
        pack = AIPlatformKnowledgePack(available=False)
        d = pack.to_dict()
        assert "available" in d
        assert "platform" in d
        assert "creator_type" in d
        assert "matches" in d
        assert "confidence" in d
        assert "reasoning" in d
        assert "warnings" in d

    def test_context_default_available_false(self):
        from app.ai.knowledge.platform_knowledge_schema import AIPlatformContext
        ctx = AIPlatformContext()
        assert ctx.available is False
        assert ctx.matches == []
        assert ctx.reasoning == []

    def test_context_to_dict_keys(self):
        from app.ai.knowledge.platform_knowledge_schema import AIPlatformContext
        ctx = AIPlatformContext(available=True, platform="tiktok", confidence=0.80)
        d = ctx.to_dict()
        assert d["available"] is True
        assert d["platform"] == "tiktok"
        assert "reasoning" in d

    def test_known_platforms_frozenset(self):
        from app.ai.knowledge.platform_knowledge_schema import KNOWN_PLATFORMS
        assert "tiktok" in KNOWN_PLATFORMS
        assert "youtube_shorts" in KNOWN_PLATFORMS
        assert "instagram_reels" in KNOWN_PLATFORMS
        assert "general" in KNOWN_PLATFORMS

    def test_known_creator_types_frozenset(self):
        from app.ai.knowledge.platform_knowledge_schema import KNOWN_CREATOR_TYPES
        assert "podcast" in KNOWN_CREATOR_TYPES
        assert "educational" in KNOWN_CREATOR_TYPES
        assert "viral_short_form" in KNOWN_CREATOR_TYPES
        assert "talking_head" in KNOWN_CREATOR_TYPES


# ---------------------------------------------------------------------------
# Section 2: Loader
# ---------------------------------------------------------------------------

class TestPlatformKnowledgeLoader:
    def test_loads_valid_pack(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item()])
        items = load_platform_knowledge(tmp_path / "platforms")
        assert len(items) == 1
        assert items[0].knowledge_id == "tiktok_shortform_test"
        assert items[0].platform == "tiktok"

    def test_loads_multiple_packs(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item(), _podcast_item(), _edu_item()])
        items = load_platform_knowledge(tmp_path / "platforms")
        assert len(items) == 3

    def test_skips_malformed_json(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        plat_dir = tmp_path / "platforms"
        plat_dir.mkdir()
        (plat_dir / "bad.json").write_text("{invalid json", encoding="utf-8")
        (plat_dir / "good.json").write_text(json.dumps(_tiktok_item()), encoding="utf-8")
        items = load_platform_knowledge(plat_dir)
        assert len(items) == 1
        assert items[0].knowledge_id == "tiktok_shortform_test"

    def test_skips_missing_knowledge_id(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        plat_dir = tmp_path / "platforms"
        plat_dir.mkdir(parents=True, exist_ok=True)
        bad = {"platform": "tiktok", "confidence": 0.5}  # no knowledge_id
        (plat_dir / "no_id.json").write_text(json.dumps(bad), encoding="utf-8")
        items = load_platform_knowledge(plat_dir)
        assert items == []

    def test_skips_forbidden_keys(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        malicious = {
            "knowledge_id": "evil_pack",
            "platform": "tiktok",
            "ffmpeg_args": "-vf scale=1920:1080",
            "guidance": {},
        }
        _write_platform_dir(tmp_path, [malicious])
        items = load_platform_knowledge(tmp_path / "platforms")
        assert items == []

    def test_missing_directory_returns_empty(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        items = load_platform_knowledge(tmp_path / "nonexistent")
        assert items == []

    def test_deterministic_sort_by_knowledge_id(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        _write_platform_dir(tmp_path, [_edu_item(), _tiktok_item(), _podcast_item()])
        items = load_platform_knowledge(tmp_path / "platforms")
        ids = [i.knowledge_id for i in items]
        assert ids == sorted(ids)

    def test_confidence_clamped(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge_file, clear_cache,
        )
        clear_cache()
        plat_dir = tmp_path / "platforms"
        plat_dir.mkdir()
        item = _tiktok_item()
        item["confidence"] = 99.9
        path = plat_dir / "tiktok_shortform_test.json"
        path.write_text(json.dumps(item), encoding="utf-8")
        loaded = load_platform_knowledge_file(path)
        assert loaded is not None
        assert loaded.confidence <= 1.0

    def test_load_file_missing_returns_none(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import load_platform_knowledge_file
        result = load_platform_knowledge_file(tmp_path / "nonexistent.json")
        assert result is None

    def test_cache_hit_same_result(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item()])
        plat_dir = tmp_path / "platforms"
        items1 = load_platform_knowledge(plat_dir)
        items2 = load_platform_knowledge(plat_dir)
        assert len(items1) == len(items2) == 1
        assert items1[0].knowledge_id == items2[0].knowledge_id


# ---------------------------------------------------------------------------
# Section 3: Retriever — platform filter
# ---------------------------------------------------------------------------

class TestPlatformRetrieverPlatformFilter:
    def test_retrieves_tiktok_only(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item(), _podcast_item()])
        pack = retrieve_platform_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        assert pack.available is True
        assert all(m.platform == "tiktok" for m in pack.matches)

    def test_retrieves_youtube_shorts_only(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_youtube_shorts_item(), _tiktok_item()])
        pack = retrieve_platform_knowledge(
            platform="youtube_shorts", base_path=tmp_path / "platforms"
        )
        assert pack.available is True
        assert all(m.platform == "youtube_shorts" for m in pack.matches)

    def test_unknown_platform_returns_unavailable(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item()])
        pack = retrieve_platform_knowledge(
            platform="twitch", base_path=tmp_path / "platforms"
        )
        assert pack.available is False

    def test_no_platform_returns_all(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item(), _podcast_item(), _edu_item()])
        pack = retrieve_platform_knowledge(base_path=tmp_path / "platforms")
        assert pack.available is True
        assert len(pack.matches) == 3


# ---------------------------------------------------------------------------
# Section 4: Retriever — creator_type filter
# ---------------------------------------------------------------------------

class TestPlatformRetrieverCreatorTypeFilter:
    def test_retrieves_podcast_only(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_item(), _tiktok_item(), _edu_item()])
        pack = retrieve_platform_knowledge(
            creator_type="podcast", base_path=tmp_path / "platforms"
        )
        assert pack.available is True
        assert all(m.creator_type == "podcast" for m in pack.matches)

    def test_retrieves_educational_only(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_item(), _tiktok_item(), _edu_item()])
        pack = retrieve_platform_knowledge(
            creator_type="educational", base_path=tmp_path / "platforms"
        )
        assert pack.available is True
        assert all(m.creator_type == "educational" for m in pack.matches)

    def test_unknown_creator_type_returns_unavailable(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_item()])
        pack = retrieve_platform_knowledge(
            creator_type="streamer", base_path=tmp_path / "platforms"
        )
        assert pack.available is False


# ---------------------------------------------------------------------------
# Section 5: Retriever — dual filter + sort order
# ---------------------------------------------------------------------------

class TestPlatformRetrieverDualFilter:
    def test_dual_match_returns_exact(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item(), _podcast_item()])
        pack = retrieve_platform_knowledge(
            platform="tiktok", creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        assert pack.available is True
        assert pack.matches[0].knowledge_id == "tiktok_shortform_test"

    def test_dual_exact_ranked_before_partial(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        # Add a tiktok-general item that matches platform but not creator_type
        tiktok_general = {
            "knowledge_id": "aaa_tiktok_general",  # 'aaa' sorts before 'tiktok'
            "platform": "tiktok",
            "creator_type": "general",
            "version": 1,
            "title": "TikTok General",
            "description": "",
            "tags": ["tiktok"],
            "domains": ["subtitle"],
            "guidance": {},
            "confidence": 0.70,
        }
        _write_platform_dir(tmp_path, [_tiktok_item(), tiktok_general])
        pack = retrieve_platform_knowledge(
            platform="tiktok", creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        # Exact dual-match must be first regardless of alpha sort
        assert pack.matches[0].knowledge_id == "tiktok_shortform_test"

    def test_deterministic_same_inputs(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item(), _podcast_item(), _edu_item()])
        pack1 = retrieve_platform_knowledge(base_path=tmp_path / "platforms")
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item(), _podcast_item(), _edu_item()])
        pack2 = retrieve_platform_knowledge(base_path=tmp_path / "platforms")
        ids1 = [m.knowledge_id for m in pack1.matches]
        ids2 = [m.knowledge_id for m in pack2.matches]
        assert ids1 == ids2


# ---------------------------------------------------------------------------
# Section 6: Retriever — bounded results
# ---------------------------------------------------------------------------

class TestPlatformRetrieverBounds:
    def test_max_results_respected(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        items = []
        for i in range(8):
            items.append({
                "knowledge_id": f"pack_{i:02d}",
                "platform": "tiktok",
                "creator_type": "viral_short_form",
                "version": 1, "title": f"Pack {i}",
                "description": "", "tags": [], "domains": [],
                "guidance": {}, "confidence": 0.80,
            })
        _write_platform_dir(tmp_path, items)
        pack = retrieve_platform_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms", max_results=3
        )
        assert len(pack.matches) <= 3

    def test_max_results_clamped_to_1(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item(), _podcast_item()])
        pack = retrieve_platform_knowledge(
            base_path=tmp_path / "platforms", max_results=0
        )
        assert len(pack.matches) >= 1

    def test_empty_knowledge_dir_returns_unavailable(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        plat_dir = tmp_path / "platforms"
        plat_dir.mkdir()
        pack = retrieve_platform_knowledge(base_path=plat_dir)
        assert pack.available is False

    def test_none_input_never_raises(self):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        pack = retrieve_platform_knowledge(platform=None, creator_type=None)
        assert pack is not None


# ---------------------------------------------------------------------------
# Section 7: Context builder
# ---------------------------------------------------------------------------

class TestPlatformContextBuilder:
    def test_context_available_when_match_found(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import build_platform_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item()])
        result = build_platform_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        ctx = result["platform_context"]
        assert ctx["available"] is True
        assert len(ctx["matches"]) == 1

    def test_context_fallback_when_no_match(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import build_platform_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        plat_dir = tmp_path / "platforms"
        plat_dir.mkdir()
        result = build_platform_context(platform="twitch", base_path=plat_dir)
        ctx = result["platform_context"]
        assert ctx["available"] is False
        assert ctx["matches"] == []
        assert ctx["confidence"] == 0.0

    def test_context_always_returns_dict(self):
        from app.ai.knowledge.platform_knowledge_retriever import build_platform_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        result = build_platform_context()
        assert isinstance(result, dict)
        assert "platform_context" in result

    def test_context_reasoning_is_list_of_strings(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import build_platform_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item()])
        result = build_platform_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        reasoning = result["platform_context"]["reasoning"]
        assert isinstance(reasoning, list)
        for r in reasoning:
            assert isinstance(r, str)

    def test_context_confidence_in_valid_range(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import build_platform_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item()])
        result = build_platform_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        conf = result["platform_context"]["confidence"]
        assert 0.0 <= conf <= 1.0


# ---------------------------------------------------------------------------
# Section 8: Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_edit_plan_has_platform_context_field(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "platform_context")
        assert isinstance(plan.platform_context, dict)

    def test_edit_plan_to_dict_includes_platform_context(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.platform_context = {"available": True, "platform": "tiktok"}
        d = plan.to_dict()
        assert "platform_context" in d
        assert d["platform_context"]["available"] is True

    def test_edit_plan_platform_context_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert plan.platform_context == {}


# ---------------------------------------------------------------------------
# Section 9: Safety — no executable content
# ---------------------------------------------------------------------------

class TestPlatformKnowledgeSafety:
    def test_no_executable_keys_in_loaded_item(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item()])
        items = load_platform_knowledge(tmp_path / "platforms")
        for item in items:
            d = item.to_dict()
            safe_str = str(d)
            for forbidden in ("ffmpeg_args", "subprocess", "render_command", "motion_crop"):
                assert forbidden not in safe_str

    def test_no_raw_json_paths_in_reasoning(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_retriever import build_platform_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item()])
        result = build_platform_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        reasoning_str = str(result["platform_context"].get("reasoning", []))
        assert ".json" not in reasoning_str
        assert "\\" not in reasoning_str
        assert "knowledge/platforms" not in reasoning_str

    def test_forbidden_key_pack_rejected(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        evil = {
            "knowledge_id": "evil",
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "render_command": "rm -rf /",
            "guidance": {},
        }
        _write_platform_dir(tmp_path, [evil])
        items = load_platform_knowledge(tmp_path / "platforms")
        assert items == []

    def test_guidance_has_no_executable_content(self, tmp_path):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_item(), _podcast_item()])
        items = load_platform_knowledge(tmp_path / "platforms")
        for item in items:
            guidance_str = str(item.guidance)
            assert "ffmpeg" not in guidance_str
            assert "subprocess" not in guidance_str

    def test_no_runtime_internet_dependency(self):
        """Platform knowledge loads from local files only — no urllib, requests, httpx."""
        import app.ai.knowledge.platform_knowledge_loader as mod
        import inspect
        src = inspect.getsource(mod)
        for bad_import in ("urllib", "requests", "httpx", "socket", "aiohttp"):
            assert bad_import not in src


# ---------------------------------------------------------------------------
# Section 10: Real seed packs smoke test
# ---------------------------------------------------------------------------

class TestRealSeedPacks:
    def test_real_platforms_directory_loads(self):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        items = load_platform_knowledge()
        assert isinstance(items, list)
        # At least the 5 seed packs should load
        assert len(items) >= 5

    def test_real_tiktok_pack_loaded(self):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        items = load_platform_knowledge()
        ids = {i.knowledge_id for i in items}
        assert "tiktok_shortform_foundation" in ids

    def test_real_podcast_pack_loaded(self):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        items = load_platform_knowledge()
        ids = {i.knowledge_id for i in items}
        assert "podcast_creator_foundation" in ids

    def test_real_tiktok_retrieval(self):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        pack = retrieve_platform_knowledge(platform="tiktok")
        assert pack.available is True
        assert all(m.platform == "tiktok" for m in pack.matches)

    def test_real_podcast_retrieval(self):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        pack = retrieve_platform_knowledge(creator_type="podcast")
        assert pack.available is True
        assert all(m.creator_type == "podcast" for m in pack.matches)

    def test_real_educational_retrieval(self):
        from app.ai.knowledge.platform_knowledge_retriever import retrieve_platform_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        pack = retrieve_platform_knowledge(creator_type="educational")
        assert pack.available is True

    def test_real_seed_packs_have_guidance(self):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        items = load_platform_knowledge()
        for item in items:
            assert isinstance(item.guidance, dict)

    def test_real_seed_packs_have_valid_confidence(self):
        from app.ai.knowledge.platform_knowledge_loader import (
            load_platform_knowledge, clear_cache,
        )
        clear_cache()
        items = load_platform_knowledge()
        for item in items:
            assert 0.0 <= item.confidence <= 1.0
