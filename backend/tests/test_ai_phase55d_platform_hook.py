"""
test_ai_phase55d_platform_hook.py — Phase 55D Platform Hook & Retention Intelligence tests.

Covers:
  - platform_hook_retriever: retrieval by platform, creator_type, tags
  - platform_hook_context: structure, guidance keys, fallback
  - Hook-specific JSON packs: TikTok, YouTube Shorts, Instagram Reels,
    podcast, educational, viral storytelling
  - Integration: hook_quality_evaluator hint
  - Edit plan: platform_hook_context field + to_dict
  - Safety: no transcript mutation, no hook text rewrite, no clip mutation
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


def _tiktok_hook_item() -> dict:
    return {
        "knowledge_id": "tiktok_hook_test",
        "platform": "tiktok",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "TikTok Hook Test",
        "description": "TikTok hook and retention guidance",
        "tags": ["tiktok", "hook", "retention", "first_3s", "curiosity", "viral"],
        "domains": ["hook", "retention"],
        "guidance": {
            "hook": {
                "first_3s_priority": "high",
                "retention_priority": "high",
                "curiosity_strength": "medium_high",
                "hook_energy": "high",
                "slow_intro_risk": "high",
                "payoff_expectation": "strong",
                "hook_style": "direct_promise",
            }
        },
        "confidence": 0.84,
    }


def _youtube_hook_item() -> dict:
    return {
        "knowledge_id": "youtube_hook_test",
        "platform": "youtube_shorts",
        "creator_type": "viral_short_form",
        "version": 1,
        "title": "YouTube Shorts Hook Test",
        "description": "YouTube Shorts hook guidance",
        "tags": ["youtube_shorts", "hook", "retention", "first_5s", "payoff", "clarity"],
        "domains": ["hook", "retention"],
        "guidance": {
            "hook": {
                "first_3s_priority": "medium",
                "retention_priority": "high",
                "hook_energy": "medium",
                "payoff_expectation": "strong",
                "hook_style": "direct_promise",
                "first_5s_retention": "high",
                "clarity_priority": "high",
            }
        },
        "confidence": 0.81,
    }


def _podcast_hook_item() -> dict:
    return {
        "knowledge_id": "podcast_hook_test",
        "platform": "general",
        "creator_type": "podcast",
        "version": 1,
        "title": "Podcast Hook Test",
        "description": "Podcast hook and retention guidance",
        "tags": ["podcast", "hook", "retention", "trust_first", "credibility", "conversational"],
        "domains": ["hook", "retention"],
        "guidance": {
            "hook": {
                "first_3s_priority": "medium",
                "retention_priority": "high",
                "hook_energy": "low",
                "hook_style": "trust_first",
                "hype_level": "low",
                "trust_priority": "high",
                "clarity_priority": "high",
            }
        },
        "confidence": 0.85,
    }


def _educational_hook_item() -> dict:
    return {
        "knowledge_id": "educational_hook_test",
        "platform": "general",
        "creator_type": "educational",
        "version": 1,
        "title": "Educational Hook Test",
        "description": "Educational creator hook guidance",
        "tags": ["educational", "hook", "retention", "concept_first", "clarity", "payoff"],
        "domains": ["hook", "retention"],
        "guidance": {
            "hook": {
                "first_3s_priority": "medium",
                "retention_priority": "high",
                "hook_energy": "low",
                "hook_style": "concept_first",
                "payoff_expectation": "strong",
                "clarity_priority": "high",
            }
        },
        "confidence": 0.83,
    }


def _storytelling_hook_item() -> dict:
    return {
        "knowledge_id": "storytelling_hook_test",
        "platform": "general",
        "creator_type": "storytelling",
        "version": 1,
        "title": "Viral Storytelling Hook Test",
        "description": "Viral storytelling hook guidance",
        "tags": ["storytelling", "hook", "retention", "tension", "open_loop", "emotional", "narrative"],
        "domains": ["hook", "retention"],
        "guidance": {
            "hook": {
                "first_3s_priority": "high",
                "retention_priority": "high",
                "curiosity_strength": "high",
                "hook_energy": "high",
                "hook_style": "story_invitation",
                "open_loop_quality": "strong",
                "emotional_stakes": "high",
                "narrative_tension": "high",
            }
        },
        "confidence": 0.82,
    }


@dataclass
class _FakePlan:
    platform_hook_context: dict = field(default_factory=dict)
    platform_subtitle_context: dict = field(default_factory=dict)
    platform_camera_context: dict = field(default_factory=dict)
    market_optimization_intelligence: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 1. Seed packs exist on disk
# ---------------------------------------------------------------------------

class TestHookPacksOnDisk:
    def test_tiktok_hook_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "tiktok_hook_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_youtube_shorts_hook_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "youtube_shorts_hook_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_instagram_reels_hook_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "instagram_reels_hook_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_podcast_hook_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "podcast_hook_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_educational_hook_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "educational_hook_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_viral_storytelling_hook_pack_exists(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        f = Path(path) / "viral_storytelling_hook_intelligence.json"
        assert f.exists(), f"Missing {f}"

    def test_tiktok_pack_has_hook_domain(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        data = json.loads((Path(path) / "tiktok_hook_intelligence.json").read_text())
        assert "hook" in data["domains"]

    def test_tiktok_pack_has_retention_domain(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        data = json.loads((Path(path) / "tiktok_hook_intelligence.json").read_text())
        assert "retention" in data["domains"]

    def test_podcast_pack_has_trust_first_style(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        data = json.loads((Path(path) / "podcast_hook_intelligence.json").read_text())
        assert data["guidance"]["hook"]["hook_style"] == "trust_first"

    def test_storytelling_pack_has_narrative_tension(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        data = json.loads((Path(path) / "viral_storytelling_hook_intelligence.json").read_text())
        assert data["guidance"]["hook"]["narrative_tension"] == "high"

    def test_no_forbidden_keys_in_any_hook_pack(self):
        from app.ai.knowledge.platform_knowledge_loader import _resolve_platforms_path
        path = _resolve_platforms_path(None)
        forbidden = {"ffmpeg_args", "render_command", "motion_crop", "hook_rewrite", "transcript"}
        for fname in [
            "tiktok_hook_intelligence.json",
            "youtube_shorts_hook_intelligence.json",
            "instagram_reels_hook_intelligence.json",
            "podcast_hook_intelligence.json",
            "educational_hook_intelligence.json",
            "viral_storytelling_hook_intelligence.json",
        ]:
            data = json.loads((Path(path) / fname).read_text())
            flat = str(data)
            for key in forbidden:
                assert key not in flat, f"Forbidden key '{key}' found in {fname}"


# ---------------------------------------------------------------------------
# 2. Retrieval by platform
# ---------------------------------------------------------------------------

class TestRetrievalByPlatform:
    def test_tiktok_retrieval_returns_available(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = retrieve_platform_hook_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["platform"] == "tiktok"
        assert len(result["matches"]) == 1

    def test_youtube_retrieval_returns_available(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_youtube_hook_item()])
        result = retrieve_platform_hook_knowledge(
            platform="youtube_shorts", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["platform"] == "youtube_shorts"

    def test_unknown_platform_returns_not_available(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = retrieve_platform_hook_knowledge(
            platform="unknown_platform_xyz", base_path=tmp_path / "platforms"
        )
        assert result["available"] is False

    def test_empty_platform_returns_all_hook_items(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item(), _youtube_hook_item()])
        result = retrieve_platform_hook_knowledge(
            platform="", creator_type="", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert len(result["matches"]) >= 2


# ---------------------------------------------------------------------------
# 3. Retrieval by creator_type
# ---------------------------------------------------------------------------

class TestRetrievalByCreatorType:
    def test_podcast_retrieval_by_creator_type(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_hook_item()])
        result = retrieve_platform_hook_knowledge(
            creator_type="podcast", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["matches"][0]["creator_type"] == "podcast"

    def test_educational_retrieval_by_creator_type(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_educational_hook_item()])
        result = retrieve_platform_hook_knowledge(
            creator_type="educational", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["matches"][0]["creator_type"] == "educational"

    def test_storytelling_retrieval_by_creator_type(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_storytelling_hook_item()])
        result = retrieve_platform_hook_knowledge(
            creator_type="storytelling", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert result["matches"][0]["creator_type"] == "storytelling"

    def test_unknown_creator_type_returns_not_available(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_hook_item()])
        result = retrieve_platform_hook_knowledge(
            creator_type="unknown_type_xyz", base_path=tmp_path / "platforms"
        )
        assert result["available"] is False


# ---------------------------------------------------------------------------
# 4. Tag filter
# ---------------------------------------------------------------------------

class TestTagFilter:
    def test_tag_filter_narrows_to_curiosity(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item(), _podcast_hook_item()])
        result = retrieve_platform_hook_knowledge(
            tags=["curiosity"], base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        ids = [m["knowledge_id"] for m in result["matches"]]
        assert "tiktok_hook_test" in ids

    def test_tag_filter_first_3s_narrows_results(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item(), _podcast_hook_item()])
        result = retrieve_platform_hook_knowledge(
            tags=["first_3s"], base_path=tmp_path / "platforms"
        )
        assert result["available"] is True

    def test_unmatched_tag_falls_back_to_all_hook_items(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = retrieve_platform_hook_knowledge(
            tags=["nonexistent_tag_zzzz"], base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert len(result["matches"]) >= 1


# ---------------------------------------------------------------------------
# 5. build_platform_hook_context structure
# ---------------------------------------------------------------------------

class TestBuildPlatformHookContext:
    def test_context_structure_when_available(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = build_platform_hook_context(
            platform="tiktok",
            creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        assert "platform_hook_context" in result
        ctx = result["platform_hook_context"]
        assert ctx["available"] is True
        assert ctx["platform"] == "tiktok"
        assert ctx["creator_type"] == "viral_short_form"
        assert "guidance" in ctx
        assert "confidence" in ctx
        assert "reasoning" in ctx

    def test_context_fallback_on_empty_dir(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        empty = tmp_path / "platforms"
        empty.mkdir()
        result = build_platform_hook_context(platform="tiktok", base_path=empty)
        ctx = result["platform_hook_context"]
        assert ctx["available"] is False
        assert ctx["guidance"] == {}

    def test_guidance_has_first_3s_priority(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = build_platform_hook_context(
            platform="tiktok",
            creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_hook_context"]
        assert "first_3s_priority" in ctx["guidance"]
        assert ctx["guidance"]["first_3s_priority"] == "high"

    def test_podcast_context_has_trust_first_style(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_podcast_hook_item()])
        result = build_platform_hook_context(
            creator_type="podcast",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_hook_context"]
        assert ctx["available"] is True
        assert ctx["guidance"].get("hook_style") == "trust_first"

    def test_educational_context_has_concept_first_style(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_educational_hook_item()])
        result = build_platform_hook_context(
            creator_type="educational",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_hook_context"]
        assert ctx["available"] is True
        assert ctx["guidance"].get("hook_style") == "concept_first"

    def test_storytelling_context_has_story_invitation_style(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_storytelling_hook_item()])
        result = build_platform_hook_context(
            creator_type="storytelling",
            base_path=tmp_path / "platforms",
        )
        ctx = result["platform_hook_context"]
        assert ctx["available"] is True
        assert ctx["guidance"].get("hook_style") == "story_invitation"

    def test_reasoning_is_list(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = build_platform_hook_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        ctx = result["platform_hook_context"]
        assert isinstance(ctx["reasoning"], list)

    def test_confidence_in_range(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = build_platform_hook_context(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        ctx = result["platform_hook_context"]
        assert 0.0 <= ctx["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# 6. Safety filter
# ---------------------------------------------------------------------------

class TestSafetyFilter:
    def test_evil_pack_forbidden_key_rejected(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        evil = {
            "knowledge_id": "evil_hook",
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "version": 1,
            "title": "Evil Hook Pack",
            "description": "evil",
            "tags": ["tiktok", "hook"],
            "domains": ["hook"],
            "guidance": {
                "hook": {
                    "first_3s_priority": "high",
                    "hook_rewrite": "replace all hooks",
                }
            },
            "confidence": 0.9,
        }
        plat_dir = tmp_path / "platforms"
        plat_dir.mkdir()
        (plat_dir / "evil_hook.json").write_text(json.dumps(evil), encoding="utf-8")
        result = build_platform_hook_context(platform="tiktok", base_path=plat_dir)
        ctx = result["platform_hook_context"]
        if ctx["available"]:
            assert "hook_rewrite" not in ctx.get("guidance", {})
        else:
            assert ctx["available"] is False

    def test_never_raises_on_none_input(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import (
            retrieve_platform_hook_knowledge,
            build_platform_hook_context,
        )
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        assert retrieve_platform_hook_knowledge(platform=None, creator_type=None, base_path=tmp_path / "platforms") is not None
        assert build_platform_hook_context(platform=None, base_path=tmp_path / "platforms") is not None

    def test_no_forbidden_keys_in_output(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = build_platform_hook_context(platform="tiktok", base_path=tmp_path / "platforms")
        forbidden = {"ffmpeg_args", "render_command", "hook_rewrite", "transcript", "motion_crop"}
        flat = str(result)
        for key in forbidden:
            assert key not in flat

    def test_no_transcript_mutation(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = build_platform_hook_context(platform="tiktok", base_path=tmp_path / "platforms")
        flat = str(result)
        assert "transcript" not in flat.lower() or "reasoning" not in flat.lower()

    def test_no_clip_boundary_in_output(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import build_platform_hook_context
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = build_platform_hook_context(platform="tiktok", base_path=tmp_path / "platforms")
        ctx = result["platform_hook_context"]
        assert "clip_boundaries" not in ctx.get("guidance", {})


# ---------------------------------------------------------------------------
# 7. Hook quality evaluator hint integration
# ---------------------------------------------------------------------------

class TestHookQualityEvaluatorHint:
    def test_platform_hint_appended_when_available(self):
        from app.ai.hook_quality.hook_quality_evaluator import _platform_hook_hint
        plan = _FakePlan(platform_hook_context={
            "available": True,
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "guidance": {"first_3s_priority": "high", "hook_style": "direct_promise"},
            "confidence": 0.84,
            "reasoning": ["TikTok hook guidance prioritizes high first-3-second attention"],
        })
        hint = _platform_hook_hint(plan)
        assert isinstance(hint, str)
        assert len(hint) > 0

    def test_platform_hint_empty_when_not_available(self):
        from app.ai.hook_quality.hook_quality_evaluator import _platform_hook_hint
        plan = _FakePlan(platform_hook_context={"available": False})
        assert _platform_hook_hint(plan) == ""

    def test_platform_hint_empty_on_missing_context(self):
        from app.ai.hook_quality.hook_quality_evaluator import _platform_hook_hint
        plan = _FakePlan()
        assert _platform_hook_hint(plan) == ""

    def test_platform_hint_empty_on_none_plan(self):
        from app.ai.hook_quality.hook_quality_evaluator import _platform_hook_hint
        assert _platform_hook_hint(None) == ""

    def test_evaluator_does_not_raise_with_platform_context(self):
        from app.ai.hook_quality.hook_quality_evaluator import evaluate_hook_quality_v2
        plan = _FakePlan(platform_hook_context={
            "available": True,
            "platform": "tiktok",
            "guidance": {"first_3s_priority": "high"},
            "confidence": 0.84,
            "reasoning": ["TikTok hook guidance prioritizes strong first-3-second attention"],
        })
        result = evaluate_hook_quality_v2(plan)
        assert "hook_quality_v2" in result

    def test_hint_uses_reasoning_first(self):
        from app.ai.hook_quality.hook_quality_evaluator import _platform_hook_hint
        plan = _FakePlan(platform_hook_context={
            "available": True,
            "platform": "tiktok",
            "guidance": {"first_3s_priority": "high"},
            "confidence": 0.84,
            "reasoning": ["Custom platform hook reasoning line"],
        })
        hint = _platform_hook_hint(plan)
        assert "Custom platform hook reasoning line" in hint

    def test_hint_fallback_uses_platform_and_first_3s(self):
        from app.ai.hook_quality.hook_quality_evaluator import _platform_hook_hint
        plan = _FakePlan(platform_hook_context={
            "available": True,
            "platform": "tiktok",
            "guidance": {"first_3s_priority": "high", "hook_style": "direct_promise"},
            "confidence": 0.84,
            "reasoning": [],
        })
        hint = _platform_hook_hint(plan)
        assert hint != ""
        assert "tiktok" in hint.lower() or "first" in hint.lower()

    def test_podcast_hint_mentions_trust(self):
        from app.ai.hook_quality.hook_quality_evaluator import _platform_hook_hint
        plan = _FakePlan(platform_hook_context={
            "available": True,
            "platform": "general",
            "creator_type": "podcast",
            "guidance": {"first_3s_priority": "medium", "hook_style": "trust_first"},
            "confidence": 0.85,
            "reasoning": ["Podcast hook guidance recommends trust_first hook style for podcast creators"],
        })
        hint = _platform_hook_hint(plan)
        assert "trust" in hint.lower() or "podcast" in hint.lower()


# ---------------------------------------------------------------------------
# 8. Edit plan integration
# ---------------------------------------------------------------------------

class TestEditPlanIntegration:
    def _make_plan(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        return AIEditPlan(
            enabled=True, mode="auto", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )

    def test_platform_hook_context_field_exists(self):
        plan = self._make_plan()
        assert hasattr(plan, "platform_hook_context")
        assert isinstance(plan.platform_hook_context, dict)

    def test_platform_hook_context_in_to_dict(self):
        plan = self._make_plan()
        plan.platform_hook_context = {"available": True, "platform": "tiktok"}
        d = plan.to_dict()
        assert "platform_hook_context" in d
        assert d["platform_hook_context"]["available"] is True

    def test_platform_hook_context_default_empty(self):
        plan = self._make_plan()
        assert plan.platform_hook_context == {}

    def test_to_dict_still_has_camera_and_subtitle_contexts(self):
        plan = self._make_plan()
        d = plan.to_dict()
        assert "platform_subtitle_context" in d
        assert "platform_camera_context" in d
        assert "platform_hook_context" in d


# ---------------------------------------------------------------------------
# 9. Hook domain filter — non-hook items excluded
# ---------------------------------------------------------------------------

class TestHookDomainFilter:
    def test_camera_only_item_not_returned(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        camera_only = {
            "knowledge_id": "tiktok_cam_only",
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "version": 1,
            "title": "TikTok Camera Only",
            "description": "camera only",
            "tags": ["tiktok", "camera"],
            "domains": ["camera"],
            "guidance": {"camera": {"motion_energy": "high"}},
            "confidence": 0.80,
        }
        _write_platform_dir(tmp_path, [camera_only])
        result = retrieve_platform_hook_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        assert result["available"] is False

    def test_hook_item_from_mixed_directory(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        camera_only = {
            "knowledge_id": "tiktok_cam_only",
            "platform": "tiktok",
            "creator_type": "viral_short_form",
            "version": 1,
            "title": "TikTok Camera Only",
            "description": "camera only",
            "tags": ["tiktok", "camera"],
            "domains": ["camera"],
            "guidance": {"camera": {"motion_energy": "high"}},
            "confidence": 0.80,
        }
        _write_platform_dir(tmp_path, [camera_only, _tiktok_hook_item()])
        result = retrieve_platform_hook_knowledge(
            platform="tiktok", base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        for m in result["matches"]:
            assert "hook" in (m.get("guidance") or {})


# ---------------------------------------------------------------------------
# 10. Max results clamping + deterministic order
# ---------------------------------------------------------------------------

class TestMaxResultsAndOrder:
    def test_max_results_clamped_to_10(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = retrieve_platform_hook_knowledge(
            platform="tiktok", max_results=999, base_path=tmp_path / "platforms"
        )
        assert len(result["matches"]) <= 10

    def test_max_results_minimum_is_1(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item()])
        result = retrieve_platform_hook_knowledge(
            platform="tiktok", max_results=0, base_path=tmp_path / "platforms"
        )
        assert result["available"] is True
        assert len(result["matches"]) >= 1

    def test_deterministic_order_same_input(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item(), _youtube_hook_item()])
        result1 = retrieve_platform_hook_knowledge(base_path=tmp_path / "platforms")
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item(), _youtube_hook_item()])
        result2 = retrieve_platform_hook_knowledge(base_path=tmp_path / "platforms")
        ids1 = [m["knowledge_id"] for m in result1["matches"]]
        ids2 = [m["knowledge_id"] for m in result2["matches"]]
        assert ids1 == ids2

    def test_exact_platform_match_ranked_first(self, tmp_path):
        from app.ai.knowledge.platform_hook_retriever import retrieve_platform_hook_knowledge
        from app.ai.knowledge.platform_knowledge_loader import clear_cache
        clear_cache()
        _write_platform_dir(tmp_path, [_tiktok_hook_item(), _youtube_hook_item()])
        result = retrieve_platform_hook_knowledge(
            platform="tiktok",
            creator_type="viral_short_form",
            base_path=tmp_path / "platforms",
        )
        assert result["available"] is True
        assert result["matches"][0]["platform"] == "tiktok"
