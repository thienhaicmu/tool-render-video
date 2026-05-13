"""
test_ai_phase55e_platform_render_strategy.py — Phase 55E Platform-Aware Render Strategy tests.

Covers:
  - Full platform render strategy fusion (all 55A–55D contexts available)
  - TikTok + podcast conflict resolution behavior
  - YouTube Shorts + educational strategy
  - Missing platform fallback
  - Missing creator profile fallback
  - Deterministic output (same inputs → same output)
  - Allowed value normalization (invalid → "unknown")
  - Confidence clamping [0, 1]
  - No direct execution flags in output
  - No unsafe/internal fields exposed
  - No crash on empty input
  - Edit plan field presence + to_dict()
  - Schema allowed value sets are exact frozensets
  - Advisory-only: no executor override, no render mutation flags
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from app.ai.knowledge.platform_render_strategy_engine import build_platform_render_strategy
from app.ai.knowledge.platform_render_strategy_schema import (
    AIPlatformRenderStrategy,
    ALLOWED_SUBTITLE_STYLE_BIAS,
    ALLOWED_SUBTITLE_DENSITY_BIAS,
    ALLOWED_SUBTITLE_KEYWORD_EMPHASIS,
    ALLOWED_SUBTITLE_READABILITY_PRIORITY,
    ALLOWED_CAMERA_MOTION_ENERGY,
    ALLOWED_CAMERA_STABILITY_PRIORITY,
    ALLOWED_CAMERA_CROP_AGGRESSIVENESS,
    ALLOWED_CAMERA_JITTER_SENSITIVITY,
    ALLOWED_HOOK_FIRST_3S_PRIORITY,
    ALLOWED_HOOK_RETENTION_PRIORITY,
    ALLOWED_HOOK_ENERGY,
    ALLOWED_HOOK_CURIOSITY_STYLE,
    ALLOWED_RANKING_PRIORITY,
    _fallback_strategy,
    _normalize,
)


# ---------------------------------------------------------------------------
# Fixtures / plan builders
# ---------------------------------------------------------------------------

def _plan_dict(
    platform: str = "",
    creator_type: str = "",
    subtitle_available: bool = False,
    subtitle_guidance: Optional[dict] = None,
    subtitle_confidence: float = 0.0,
    camera_available: bool = False,
    camera_guidance: Optional[dict] = None,
    camera_confidence: float = 0.0,
    hook_available: bool = False,
    hook_guidance: Optional[dict] = None,
    hook_confidence: float = 0.0,
    platform_ctx_available: bool = False,
    creator_profile: Optional[dict] = None,
    quality_ctx: Optional[dict] = None,
) -> dict:
    """Build a minimal plan dict mimicking populated AIEditPlan fields."""
    return {
        "platform_context": {
            "available": platform_ctx_available,
            "platform": platform,
            "creator_type": creator_type,
            "confidence": 0.8 if platform_ctx_available else 0.0,
            "reasoning": [],
        },
        "platform_subtitle_context": {
            "available": subtitle_available,
            "platform": platform,
            "creator_type": creator_type,
            "guidance": subtitle_guidance or {},
            "confidence": subtitle_confidence,
            "reasoning": [],
        },
        "platform_camera_context": {
            "available": camera_available,
            "platform": platform,
            "creator_type": creator_type,
            "guidance": camera_guidance or {},
            "confidence": camera_confidence,
            "reasoning": [],
        },
        "platform_hook_context": {
            "available": hook_available,
            "platform": platform,
            "creator_type": creator_type,
            "guidance": hook_guidance or {},
            "confidence": hook_confidence,
            "reasoning": [],
        },
        "creator_preference_profile": creator_profile or {},
        "render_quality_v2": quality_ctx or {},
        "knowledge_reasoning_context": {},
    }


def _tiktok_podcast_plan() -> dict:
    """TikTok platform + podcast creator — key conflict scenario."""
    return _plan_dict(
        platform="tiktok",
        creator_type="podcast",
        platform_ctx_available=True,
        subtitle_available=True,
        subtitle_guidance={
            "density_bias": "compact",
            "readability_priority": "high",
            "style_preference": "viral_bold",  # Platform wants viral — creator should override
            "keyword_emphasis": "strong",
        },
        subtitle_confidence=0.84,
        camera_available=True,
        camera_guidance={
            "motion_energy": "high",   # Platform wants high — creator should cap it
            "stability_priority": "medium",
            "crop_aggressiveness_guidance": "high",
            "jitter_sensitivity": "low",
        },
        camera_confidence=0.82,
        hook_available=True,
        hook_guidance={
            "first_3s_priority": "high",
            "retention_priority": "high",
            "hook_energy": "high",     # Platform wants high — creator moderates it
            "hook_style": "direct_promise",
        },
        hook_confidence=0.84,
    )


def _youtube_educational_plan() -> dict:
    """YouTube Shorts + educational creator."""
    return _plan_dict(
        platform="youtube_shorts",
        creator_type="educational",
        platform_ctx_available=True,
        subtitle_available=True,
        subtitle_guidance={
            "density_bias": "balanced",
            "readability_priority": "high",
            "keyword_emphasis": "selective",
        },
        subtitle_confidence=0.78,
        camera_available=True,
        camera_guidance={
            "motion_energy": "medium",
            "stability_priority": "high",
            "crop_aggressiveness_guidance": "low",
            "jitter_sensitivity": "high",
        },
        camera_confidence=0.76,
        hook_available=True,
        hook_guidance={
            "first_3s_priority": "medium",
            "retention_priority": "high",
            "hook_energy": "medium",
            "hook_style": "concept_first",
        },
        hook_confidence=0.78,
    )


def _tiktok_viral_plan() -> dict:
    """TikTok + viral_short_form — high energy, no conflict."""
    return _plan_dict(
        platform="tiktok",
        creator_type="viral_short_form",
        platform_ctx_available=True,
        subtitle_available=True,
        subtitle_guidance={
            "density_bias": "compact",
            "readability_priority": "high",
            "keyword_emphasis": "moderate",
        },
        subtitle_confidence=0.85,
        camera_available=True,
        camera_guidance={
            "motion_energy": "high",
            "stability_priority": "medium",
            "crop_aggressiveness_guidance": "medium",
            "jitter_sensitivity": "high",
        },
        camera_confidence=0.83,
        hook_available=True,
        hook_guidance={
            "first_3s_priority": "high",
            "retention_priority": "high",
            "hook_energy": "high",
            "hook_style": "direct_promise",
        },
        hook_confidence=0.85,
    )


def _empty_plan() -> dict:
    """All contexts unavailable, no platform, no creator_type."""
    return {
        "platform_context": {"available": False, "platform": "", "creator_type": ""},
        "platform_subtitle_context": {"available": False, "platform": "", "creator_type": "", "guidance": {}},
        "platform_camera_context": {"available": False, "platform": "", "creator_type": "", "guidance": {}},
        "platform_hook_context": {"available": False, "platform": "", "creator_type": "", "guidance": {}},
        "creator_preference_profile": {},
        "render_quality_v2": {},
        "knowledge_reasoning_context": {},
    }


# ---------------------------------------------------------------------------
# Schema unit tests
# ---------------------------------------------------------------------------

class TestAllowedValueSets:
    """Verify that all allowed-value frozensets are correct and non-empty."""

    def test_subtitle_style_bias_members(self):
        assert "viral_bold" in ALLOWED_SUBTITLE_STYLE_BIAS
        assert "clean_pro" in ALLOWED_SUBTITLE_STYLE_BIAS
        assert "boxed_caption" in ALLOWED_SUBTITLE_STYLE_BIAS
        assert "unknown" in ALLOWED_SUBTITLE_STYLE_BIAS
        assert len(ALLOWED_SUBTITLE_STYLE_BIAS) == 4

    def test_subtitle_density_bias_members(self):
        assert ALLOWED_SUBTITLE_DENSITY_BIAS == frozenset({"compact", "balanced", "dense", "unknown"})

    def test_subtitle_keyword_emphasis_members(self):
        assert ALLOWED_SUBTITLE_KEYWORD_EMPHASIS == frozenset({"none", "selective", "moderate", "strong", "unknown"})

    def test_subtitle_readability_priority_members(self):
        assert ALLOWED_SUBTITLE_READABILITY_PRIORITY == frozenset({"high", "medium", "low", "unknown"})

    def test_camera_motion_energy_members(self):
        assert ALLOWED_CAMERA_MOTION_ENERGY == frozenset({"low", "low_medium", "medium", "medium_high", "high", "unknown"})

    def test_camera_stability_priority_members(self):
        assert ALLOWED_CAMERA_STABILITY_PRIORITY == frozenset({"low", "medium", "medium_high", "high", "unknown"})

    def test_camera_crop_aggressiveness_members(self):
        assert ALLOWED_CAMERA_CROP_AGGRESSIVENESS == frozenset({"low", "medium", "high", "unknown"})

    def test_hook_energy_members(self):
        assert ALLOWED_HOOK_ENERGY == frozenset({"low", "moderate", "high", "unknown"})

    def test_hook_curiosity_style_members(self):
        assert ALLOWED_HOOK_CURIOSITY_STYLE == frozenset({"subtle", "soft_direct", "direct", "open_loop", "unknown"})

    def test_ranking_priority_members(self):
        assert ALLOWED_RANKING_PRIORITY == frozenset({
            "creator_fit", "retention", "hook_strength", "readability",
            "retention_creator_fit", "balanced", "unknown",
        })


class TestNormalize:
    """_normalize helper."""

    def test_valid_value_passes(self):
        assert _normalize("compact", ALLOWED_SUBTITLE_DENSITY_BIAS) == "compact"

    def test_invalid_value_becomes_unknown(self):
        assert _normalize("super_dense", ALLOWED_SUBTITLE_DENSITY_BIAS) == "unknown"

    def test_empty_string_becomes_unknown(self):
        assert _normalize("", ALLOWED_SUBTITLE_DENSITY_BIAS) == "unknown"

    def test_none_becomes_unknown(self):
        assert _normalize(None, ALLOWED_SUBTITLE_DENSITY_BIAS) == "unknown"  # type: ignore

    def test_custom_default(self):
        assert _normalize("bad_val", ALLOWED_SUBTITLE_DENSITY_BIAS, "balanced") == "balanced"

    def test_case_insensitive(self):
        assert _normalize("COMPACT", ALLOWED_SUBTITLE_DENSITY_BIAS) == "compact"


class TestFallbackStrategy:
    """_fallback_strategy returns a valid safe dict."""

    def test_fallback_shape(self):
        fb = _fallback_strategy()
        prs = fb["platform_render_strategy"]
        assert prs["available"] is False
        assert prs["strategy"] == {}
        assert prs["confidence"] == 0.0
        assert prs["reasoning"] == []

    def test_fallback_with_args(self):
        fb = _fallback_strategy(platform="tiktok", creator_type="podcast")
        prs = fb["platform_render_strategy"]
        assert prs["platform"] == "tiktok"
        assert prs["creator_type"] == "podcast"
        assert prs["available"] is False


class TestAIPlatformRenderStrategyDataclass:
    """AIPlatformRenderStrategy.to_dict() safety."""

    def test_confidence_clamped_above(self):
        s = AIPlatformRenderStrategy(available=True, confidence=2.5)
        assert s.to_dict()["confidence"] == 1.0

    def test_confidence_clamped_below(self):
        s = AIPlatformRenderStrategy(available=True, confidence=-0.5)
        assert s.to_dict()["confidence"] == 0.0

    def test_forbidden_keys_stripped_from_strategy(self):
        s = AIPlatformRenderStrategy(
            available=True,
            strategy={
                "subtitle": {"style_bias": "clean_pro", "ffmpeg_args": "EVIL"},
                "executor_override": {"do_it": True},
            },
        )
        d = s.to_dict()
        assert "executor_override" not in d["strategy"]
        assert "ffmpeg_args" not in d["strategy"].get("subtitle", {})
        assert d["strategy"]["subtitle"]["style_bias"] == "clean_pro"

    def test_reasoning_capped_at_8(self):
        s = AIPlatformRenderStrategy(
            available=True,
            reasoning=[f"line {i}" for i in range(20)],
        )
        assert len(s.to_dict()["reasoning"]) == 8

    def test_to_dict_returns_expected_keys(self):
        s = AIPlatformRenderStrategy(available=True, platform="tiktok", creator_type="podcast")
        d = s.to_dict()
        assert set(d.keys()) == {"available", "platform", "creator_type", "strategy", "confidence", "reasoning"}


# ---------------------------------------------------------------------------
# Engine: full fusion tests
# ---------------------------------------------------------------------------

class TestBuildPlatformRenderStrategyFallback:
    """Empty / unavailable input → fallback."""

    def test_empty_plan_dict_returns_fallback(self):
        result = build_platform_render_strategy(_empty_plan())
        prs = result["platform_render_strategy"]
        assert prs["available"] is False
        assert prs["strategy"] == {}
        assert prs["confidence"] == 0.0

    def test_none_dict_values_no_crash(self):
        plan = {
            "platform_context": None,
            "platform_subtitle_context": None,
            "platform_camera_context": None,
            "platform_hook_context": None,
            "creator_preference_profile": None,
            "render_quality_v2": None,
        }
        result = build_platform_render_strategy(plan)
        assert "platform_render_strategy" in result
        assert result["platform_render_strategy"]["available"] is False

    def test_no_crash_on_empty_dict(self):
        result = build_platform_render_strategy({})
        assert "platform_render_strategy" in result

    def test_no_crash_on_none_input(self):
        result = build_platform_render_strategy(None)
        assert "platform_render_strategy" in result

    def test_missing_platform_no_creator_fallback(self):
        plan = _plan_dict(platform="", creator_type="")
        result = build_platform_render_strategy(plan)
        prs = result["platform_render_strategy"]
        assert prs["available"] is False


class TestBuildPlatformRenderStrategyStructure:
    """Output shape: required keys, allowed-value conformance."""

    def test_full_strategy_has_required_top_keys(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        prs = result["platform_render_strategy"]
        assert prs["available"] is True
        assert set(prs.keys()) == {
            "available", "platform", "creator_type", "strategy", "confidence", "reasoning"
        }

    def test_strategy_has_four_domains(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        strategy = result["platform_render_strategy"]["strategy"]
        assert set(strategy.keys()) == {"subtitle", "camera", "hook", "ranking"}

    def test_subtitle_domain_keys(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        subtitle = result["platform_render_strategy"]["strategy"]["subtitle"]
        assert set(subtitle.keys()) == {"style_bias", "density_bias", "keyword_emphasis", "readability_priority"}

    def test_camera_domain_keys(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        camera = result["platform_render_strategy"]["strategy"]["camera"]
        assert set(camera.keys()) == {"motion_energy", "stability_priority", "crop_aggressiveness", "jitter_sensitivity"}

    def test_hook_domain_keys(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        hook = result["platform_render_strategy"]["strategy"]["hook"]
        assert set(hook.keys()) == {"first_3s_priority", "retention_priority", "hook_energy", "curiosity_style"}

    def test_ranking_domain_keys(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        ranking = result["platform_render_strategy"]["strategy"]["ranking"]
        assert "priority" in ranking

    def test_all_subtitle_values_in_allowed_sets(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        sub = result["platform_render_strategy"]["strategy"]["subtitle"]
        assert sub["style_bias"] in ALLOWED_SUBTITLE_STYLE_BIAS
        assert sub["density_bias"] in ALLOWED_SUBTITLE_DENSITY_BIAS
        assert sub["keyword_emphasis"] in ALLOWED_SUBTITLE_KEYWORD_EMPHASIS
        assert sub["readability_priority"] in ALLOWED_SUBTITLE_READABILITY_PRIORITY

    def test_all_camera_values_in_allowed_sets(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        cam = result["platform_render_strategy"]["strategy"]["camera"]
        assert cam["motion_energy"] in ALLOWED_CAMERA_MOTION_ENERGY
        assert cam["stability_priority"] in ALLOWED_CAMERA_STABILITY_PRIORITY
        assert cam["crop_aggressiveness"] in ALLOWED_CAMERA_CROP_AGGRESSIVENESS
        assert cam["jitter_sensitivity"] in ALLOWED_CAMERA_JITTER_SENSITIVITY

    def test_all_hook_values_in_allowed_sets(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        hook = result["platform_render_strategy"]["strategy"]["hook"]
        assert hook["first_3s_priority"] in ALLOWED_HOOK_FIRST_3S_PRIORITY
        assert hook["retention_priority"] in ALLOWED_HOOK_RETENTION_PRIORITY
        assert hook["hook_energy"] in ALLOWED_HOOK_ENERGY
        assert hook["curiosity_style"] in ALLOWED_HOOK_CURIOSITY_STYLE

    def test_ranking_value_in_allowed_set(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        ranking = result["platform_render_strategy"]["strategy"]["ranking"]
        assert ranking["priority"] in ALLOWED_RANKING_PRIORITY

    def test_confidence_is_clamped_between_0_and_1(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        conf = result["platform_render_strategy"]["confidence"]
        assert 0.0 <= conf <= 1.0

    def test_reasoning_is_list(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        reasoning = result["platform_render_strategy"]["reasoning"]
        assert isinstance(reasoning, list)
        assert len(reasoning) > 0

    def test_reasoning_max_8_lines(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        reasoning = result["platform_render_strategy"]["reasoning"]
        assert len(reasoning) <= 8


# ---------------------------------------------------------------------------
# TikTok + Podcast conflict resolution
# ---------------------------------------------------------------------------

class TestTikTokPodcastConflict:
    """TikTok wants high energy; podcast creator prefers stable trust style."""

    def _prs(self) -> dict:
        return build_platform_render_strategy(_tiktok_podcast_plan())["platform_render_strategy"]

    def test_available_is_true(self):
        assert self._prs()["available"] is True

    def test_platform_is_tiktok(self):
        assert self._prs()["platform"] == "tiktok"

    def test_creator_type_is_podcast(self):
        assert self._prs()["creator_type"] == "podcast"

    def test_subtitle_style_is_clean_pro_not_viral_bold(self):
        # Podcast creator overrides TikTok viral_bold platform preference
        sub = self._prs()["strategy"]["subtitle"]
        assert sub["style_bias"] == "clean_pro"

    def test_subtitle_density_is_compact(self):
        # TikTok compact density is also podcast-safe (short lines)
        sub = self._prs()["strategy"]["subtitle"]
        assert sub["density_bias"] == "compact"

    def test_subtitle_readability_is_high(self):
        sub = self._prs()["strategy"]["subtitle"]
        assert sub["readability_priority"] == "high"

    def test_camera_motion_energy_not_high(self):
        # Podcast creator caps TikTok high motion energy
        cam = self._prs()["strategy"]["camera"]
        assert cam["motion_energy"] not in ("high", "medium_high")

    def test_camera_motion_energy_is_low_medium(self):
        # Expected: low_medium (retention platform + trust creator conflict resolution)
        cam = self._prs()["strategy"]["camera"]
        assert cam["motion_energy"] == "low_medium"

    def test_camera_stability_priority_is_high(self):
        # Trust creator forces high stability despite low platform signal
        cam = self._prs()["strategy"]["camera"]
        assert cam["stability_priority"] == "high"

    def test_camera_crop_aggressiveness_is_low(self):
        # Trust creator overrides high platform crop aggressiveness
        cam = self._prs()["strategy"]["camera"]
        assert cam["crop_aggressiveness"] == "low"

    def test_hook_energy_is_moderate_not_high(self):
        # Platform wants high; podcast creator moderates it
        hook = self._prs()["strategy"]["hook"]
        assert hook["hook_energy"] == "moderate"

    def test_hook_first_3s_priority_is_high(self):
        # TikTok drives this regardless of creator type
        hook = self._prs()["strategy"]["hook"]
        assert hook["first_3s_priority"] == "high"

    def test_hook_retention_priority_is_high(self):
        hook = self._prs()["strategy"]["hook"]
        assert hook["retention_priority"] == "high"

    def test_hook_curiosity_style_is_soft_direct_not_direct(self):
        # Trust creator on high-energy platform → soft_direct (not hard "direct")
        hook = self._prs()["strategy"]["hook"]
        assert hook["curiosity_style"] == "soft_direct"

    def test_ranking_priority_is_retention_creator_fit(self):
        # Retention platform + trust creator → retention_creator_fit
        ranking = self._prs()["strategy"]["ranking"]
        assert ranking["priority"] == "retention_creator_fit"

    def test_reasoning_mentions_balance(self):
        reasoning_text = " ".join(self._prs()["reasoning"]).lower()
        assert any(word in reasoning_text for word in ["balance", "retention", "stable", "clean"])


# ---------------------------------------------------------------------------
# YouTube Shorts + Educational strategy
# ---------------------------------------------------------------------------

class TestYouTubeShortsEducationalStrategy:
    """YouTube Shorts + educational — balanced, clarity-focused."""

    def _prs(self) -> dict:
        return build_platform_render_strategy(_youtube_educational_plan())["platform_render_strategy"]

    def test_available_is_true(self):
        assert self._prs()["available"] is True

    def test_platform_is_youtube_shorts(self):
        assert self._prs()["platform"] == "youtube_shorts"

    def test_creator_type_is_educational(self):
        assert self._prs()["creator_type"] == "educational"

    def test_subtitle_style_is_clean_pro(self):
        # Educational creator → clean_pro style
        sub = self._prs()["strategy"]["subtitle"]
        assert sub["style_bias"] == "clean_pro"

    def test_subtitle_readability_is_high(self):
        sub = self._prs()["strategy"]["subtitle"]
        assert sub["readability_priority"] == "high"

    def test_camera_stability_priority_is_high(self):
        cam = self._prs()["strategy"]["camera"]
        assert cam["stability_priority"] == "high"

    def test_camera_motion_energy_is_low_medium(self):
        # Educational creator → low_medium (not "medium" or higher)
        cam = self._prs()["strategy"]["camera"]
        assert cam["motion_energy"] == "low_medium"

    def test_camera_crop_aggressiveness_is_low(self):
        cam = self._prs()["strategy"]["camera"]
        assert cam["crop_aggressiveness"] == "low"

    def test_hook_energy_is_moderate(self):
        # "medium" from guidance remapped to "moderate"
        hook = self._prs()["strategy"]["hook"]
        assert hook["hook_energy"] == "moderate"

    def test_hook_curiosity_style_is_soft_direct(self):
        # concept_first hook_style → soft_direct curiosity_style
        hook = self._prs()["strategy"]["hook"]
        assert hook["curiosity_style"] == "soft_direct"

    def test_ranking_priority_is_retention_creator_fit(self):
        # YouTube Shorts (retention platform) + educational (clarity creator) → retention_creator_fit
        ranking = self._prs()["strategy"]["ranking"]
        assert ranking["priority"] == "retention_creator_fit"


# ---------------------------------------------------------------------------
# TikTok + Viral (no conflict) strategy
# ---------------------------------------------------------------------------

class TestTikTokViralStrategy:
    """TikTok + viral_short_form — high energy, no creator-platform conflict."""

    def _prs(self) -> dict:
        return build_platform_render_strategy(_tiktok_viral_plan())["platform_render_strategy"]

    def test_available_is_true(self):
        assert self._prs()["available"] is True

    def test_subtitle_style_is_viral_bold(self):
        sub = self._prs()["strategy"]["subtitle"]
        assert sub["style_bias"] == "viral_bold"

    def test_camera_motion_energy_not_capped(self):
        cam = self._prs()["strategy"]["camera"]
        # No trust-creator cap — platform high energy should come through
        assert cam["motion_energy"] in ("medium_high", "high", "medium")

    def test_hook_energy_is_high(self):
        hook = self._prs()["strategy"]["hook"]
        assert hook["hook_energy"] == "high"

    def test_hook_curiosity_style_is_direct(self):
        hook = self._prs()["strategy"]["hook"]
        assert hook["curiosity_style"] == "direct"

    def test_ranking_priority_is_retention(self):
        ranking = self._prs()["strategy"]["ranking"]
        assert ranking["priority"] == "retention"


# ---------------------------------------------------------------------------
# Missing platform / creator fallback
# ---------------------------------------------------------------------------

class TestMissingContextFallback:

    def test_missing_platform_only_creator_type_produces_strategy(self):
        plan = _plan_dict(
            platform="",
            creator_type="podcast",
            subtitle_available=True,
            subtitle_guidance={"density_bias": "compact"},
            subtitle_confidence=0.7,
        )
        result = build_platform_render_strategy(plan)
        prs = result["platform_render_strategy"]
        assert prs["available"] is True
        assert prs["creator_type"] == "podcast"

    def test_missing_creator_type_only_platform_produces_strategy(self):
        plan = _plan_dict(
            platform="tiktok",
            creator_type="",
            hook_available=True,
            hook_guidance={"first_3s_priority": "high"},
            hook_confidence=0.75,
        )
        result = build_platform_render_strategy(plan)
        prs = result["platform_render_strategy"]
        assert prs["available"] is True
        assert prs["platform"] == "tiktok"

    def test_empty_platform_empty_creator_type_is_fallback(self):
        plan = _plan_dict(platform="", creator_type="")
        result = build_platform_render_strategy(plan)
        prs = result["platform_render_strategy"]
        assert prs["available"] is False

    def test_no_domain_context_but_known_platform_and_creator(self):
        plan = {
            "platform_context": {
                "available": True,
                "platform": "tiktok",
                "creator_type": "podcast",
                "confidence": 0.8,
            },
            "platform_subtitle_context": {"available": False, "platform": "tiktok", "creator_type": "podcast", "guidance": {}},
            "platform_camera_context": {"available": False, "platform": "tiktok", "creator_type": "podcast", "guidance": {}},
            "platform_hook_context": {"available": False, "platform": "tiktok", "creator_type": "podcast", "guidance": {}},
            "creator_preference_profile": {},
            "render_quality_v2": {},
        }
        result = build_platform_render_strategy(plan)
        prs = result["platform_render_strategy"]
        assert prs["available"] is True
        assert prs["platform"] == "tiktok"
        assert prs["creator_type"] == "podcast"

    def test_missing_creator_profile_no_crash(self):
        plan = _tiktok_podcast_plan()
        plan["creator_preference_profile"] = {}
        result = build_platform_render_strategy(plan)
        assert result["platform_render_strategy"]["available"] is True

    def test_malformed_guidance_no_crash(self):
        plan = _plan_dict(
            platform="tiktok",
            creator_type="podcast",
            subtitle_available=True,
            subtitle_guidance={"density_bias": 12345, "readability_priority": None},
            subtitle_confidence=0.7,
        )
        result = build_platform_render_strategy(plan)
        assert "platform_render_strategy" in result


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

class TestDeterministicOutput:

    def test_same_plan_same_output_twice(self):
        plan = _tiktok_podcast_plan()
        r1 = build_platform_render_strategy(plan)
        r2 = build_platform_render_strategy(plan)
        assert r1 == r2

    def test_youtube_educational_deterministic(self):
        plan = _youtube_educational_plan()
        r1 = build_platform_render_strategy(plan)
        r2 = build_platform_render_strategy(plan)
        assert r1["platform_render_strategy"]["strategy"] == r2["platform_render_strategy"]["strategy"]

    def test_confidence_same_on_repeated_calls(self):
        plan = _tiktok_podcast_plan()
        c1 = build_platform_render_strategy(plan)["platform_render_strategy"]["confidence"]
        c2 = build_platform_render_strategy(plan)["platform_render_strategy"]["confidence"]
        assert c1 == c2


# ---------------------------------------------------------------------------
# Confidence computation
# ---------------------------------------------------------------------------

class TestConfidenceComputation:

    def test_confidence_averages_available_contexts(self):
        plan = _plan_dict(
            platform="tiktok",
            creator_type="podcast",
            subtitle_available=True,
            subtitle_confidence=0.8,
            camera_available=True,
            camera_confidence=0.6,
            hook_available=True,
            hook_confidence=1.0,
        )
        result = build_platform_render_strategy(plan)
        conf = result["platform_render_strategy"]["confidence"]
        expected = round((0.8 + 0.6 + 1.0) / 3, 4)
        assert abs(conf - expected) < 0.001

    def test_confidence_never_exceeds_1(self):
        plan = _plan_dict(
            platform="tiktok",
            creator_type="podcast",
            subtitle_available=True,
            subtitle_confidence=1.5,
        )
        result = build_platform_render_strategy(plan)
        assert result["platform_render_strategy"]["confidence"] <= 1.0

    def test_confidence_never_below_0(self):
        plan = _plan_dict(
            platform="tiktok",
            creator_type="podcast",
            subtitle_available=True,
            subtitle_confidence=-0.5,
        )
        result = build_platform_render_strategy(plan)
        assert result["platform_render_strategy"]["confidence"] >= 0.0


# ---------------------------------------------------------------------------
# Allowed value normalization (invalid → "unknown")
# ---------------------------------------------------------------------------

class TestAllowedValueNormalization:

    def test_invalid_subtitle_style_becomes_unknown_then_default(self):
        plan = _plan_dict(
            platform="tiktok",
            creator_type="viral_short_form",
            subtitle_available=True,
            subtitle_guidance={"style_preference": "super_flashy_gradient"},
            subtitle_confidence=0.7,
        )
        result = build_platform_render_strategy(plan)
        sub = result["platform_render_strategy"]["strategy"]["subtitle"]
        # Falls back to platform default for tiktok+viral: viral_bold
        assert sub["style_bias"] in ALLOWED_SUBTITLE_STYLE_BIAS

    def test_invalid_camera_motion_energy_normalized(self):
        plan = _plan_dict(
            platform="tiktok",
            creator_type="podcast",
            camera_available=True,
            camera_guidance={"motion_energy": "EXTREME_SHAKY"},
            camera_confidence=0.7,
        )
        result = build_platform_render_strategy(plan)
        cam = result["platform_render_strategy"]["strategy"]["camera"]
        assert cam["motion_energy"] in ALLOWED_CAMERA_MOTION_ENERGY

    def test_hook_energy_medium_remapped_to_moderate(self):
        plan = _plan_dict(
            platform="youtube_shorts",
            creator_type="talking_head",
            hook_available=True,
            hook_guidance={"hook_energy": "medium"},  # raw "medium" must become "moderate"
            hook_confidence=0.75,
        )
        result = build_platform_render_strategy(plan)
        hook = result["platform_render_strategy"]["strategy"]["hook"]
        # "medium" → remap → "moderate" → in allowed set
        assert hook["hook_energy"] in ALLOWED_HOOK_ENERGY
        assert hook["hook_energy"] != "medium"

    def test_all_output_values_in_allowed_sets_with_garbage_input(self):
        plan = _plan_dict(
            platform="tiktok",
            creator_type="podcast",
            subtitle_available=True,
            subtitle_guidance={
                "density_bias": "garbage",
                "readability_priority": "ultra_high",
                "style_preference": "neon_glow",
                "keyword_emphasis": "maximum_always",
            },
            subtitle_confidence=0.7,
            camera_available=True,
            camera_guidance={
                "motion_energy": "hyperactive",
                "stability_priority": "none",
                "crop_aggressiveness_guidance": "extreme",
                "jitter_sensitivity": "zero",
            },
            camera_confidence=0.7,
            hook_available=True,
            hook_guidance={
                "first_3s_priority": "critical",
                "retention_priority": "essential",
                "hook_energy": "nuclear",
                "hook_style": "unknown_style_xyz",
            },
            hook_confidence=0.7,
        )
        result = build_platform_render_strategy(plan)
        prs = result["platform_render_strategy"]
        s = prs["strategy"]

        assert s["subtitle"]["style_bias"] in ALLOWED_SUBTITLE_STYLE_BIAS
        assert s["subtitle"]["density_bias"] in ALLOWED_SUBTITLE_DENSITY_BIAS
        assert s["subtitle"]["keyword_emphasis"] in ALLOWED_SUBTITLE_KEYWORD_EMPHASIS
        assert s["subtitle"]["readability_priority"] in ALLOWED_SUBTITLE_READABILITY_PRIORITY
        assert s["camera"]["motion_energy"] in ALLOWED_CAMERA_MOTION_ENERGY
        assert s["camera"]["stability_priority"] in ALLOWED_CAMERA_STABILITY_PRIORITY
        assert s["camera"]["crop_aggressiveness"] in ALLOWED_CAMERA_CROP_AGGRESSIVENESS
        assert s["camera"]["jitter_sensitivity"] in ALLOWED_CAMERA_JITTER_SENSITIVITY
        assert s["hook"]["first_3s_priority"] in ALLOWED_HOOK_FIRST_3S_PRIORITY
        assert s["hook"]["retention_priority"] in ALLOWED_HOOK_RETENTION_PRIORITY
        assert s["hook"]["hook_energy"] in ALLOWED_HOOK_ENERGY
        assert s["hook"]["curiosity_style"] in ALLOWED_HOOK_CURIOSITY_STYLE
        assert s["ranking"]["priority"] in ALLOWED_RANKING_PRIORITY


# ---------------------------------------------------------------------------
# Safety: no execution fields, no internal leakage
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
    "crop_coordinates", "direct_execution", "executor_override",
    "output_path", "queue_priority",
}


def _collect_all_keys(obj: Any, keys: set) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            keys.add(k)
            _collect_all_keys(v, keys)
    elif isinstance(obj, list):
        for item in obj:
            _collect_all_keys(item, keys)


class TestSafetyNoExecutionFields:

    def test_no_forbidden_keys_in_tiktok_podcast_output(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        all_keys: set = set()
        _collect_all_keys(result, all_keys)
        forbidden_found = all_keys & _FORBIDDEN_KEYS
        assert not forbidden_found, f"Forbidden keys found in output: {forbidden_found}"

    def test_no_forbidden_keys_in_youtube_educational_output(self):
        result = build_platform_render_strategy(_youtube_educational_plan())
        all_keys: set = set()
        _collect_all_keys(result, all_keys)
        forbidden_found = all_keys & _FORBIDDEN_KEYS
        assert not forbidden_found, f"Forbidden keys found in output: {forbidden_found}"

    def test_no_executor_override_key(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        prs = result["platform_render_strategy"]
        assert "executor_override" not in prs
        assert "executor_override" not in prs.get("strategy", {})

    def test_no_direct_execution_flag(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        prs = result["platform_render_strategy"]
        assert "direct_execution" not in prs
        assert "direct_execution" not in prs.get("strategy", {})

    def test_no_ffmpeg_args(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        all_keys: set = set()
        _collect_all_keys(result, all_keys)
        assert "ffmpeg_args" not in all_keys

    def test_no_playback_speed(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        all_keys: set = set()
        _collect_all_keys(result, all_keys)
        assert "playback_speed" not in all_keys

    def test_no_crop_coordinates(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        all_keys: set = set()
        _collect_all_keys(result, all_keys)
        assert "crop_coordinates" not in all_keys

    def test_no_subprocess_key(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        all_keys: set = set()
        _collect_all_keys(result, all_keys)
        assert "subprocess" not in all_keys

    def test_no_internal_file_paths_in_reasoning(self):
        result = build_platform_render_strategy(_tiktok_podcast_plan())
        reasoning_text = " ".join(result["platform_render_strategy"]["reasoning"])
        assert ".py" not in reasoning_text
        assert "traceback" not in reasoning_text.lower()
        assert "error" not in reasoning_text.lower()


# ---------------------------------------------------------------------------
# Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:

    def test_edit_plan_has_platform_render_strategy_field(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert hasattr(plan, "platform_render_strategy")
        assert plan.platform_render_strategy == {}

    def test_edit_plan_to_dict_includes_platform_render_strategy(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        plan.platform_render_strategy = {"available": True, "platform": "tiktok"}
        d = plan.to_dict()
        assert "platform_render_strategy" in d
        assert d["platform_render_strategy"]["platform"] == "tiktok"

    def test_edit_plan_to_dict_default_platform_render_strategy_is_empty_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert d["platform_render_strategy"] == {}

    def test_edit_plan_platform_render_strategy_is_backward_compatible(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        # All prior platform context fields still present
        for key in ("platform_context", "platform_subtitle_context",
                    "platform_camera_context", "platform_hook_context",
                    "platform_render_strategy"):
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# Duck-typed plan object (AIEditPlan-like)
# ---------------------------------------------------------------------------

class TestDuckTypedPlanObject:
    """Engine works with an object that has attributes (not just dict)."""

    def test_accepts_object_with_attributes(self):
        class FakePlan:
            platform_context = {
                "available": True, "platform": "tiktok",
                "creator_type": "podcast", "confidence": 0.8,
            }
            platform_subtitle_context = {
                "available": True, "platform": "tiktok",
                "creator_type": "podcast",
                "guidance": {"density_bias": "compact"},
                "confidence": 0.82,
            }
            platform_camera_context = {
                "available": True, "platform": "tiktok",
                "creator_type": "podcast",
                "guidance": {"motion_energy": "high", "stability_priority": "medium"},
                "confidence": 0.80,
            }
            platform_hook_context = {
                "available": True, "platform": "tiktok",
                "creator_type": "podcast",
                "guidance": {"hook_energy": "high", "first_3s_priority": "high"},
                "confidence": 0.84,
            }
            creator_preference_profile = {}
            render_quality_v2 = {}
            knowledge_reasoning_context = {}

        result = build_platform_render_strategy(FakePlan())
        prs = result["platform_render_strategy"]
        assert prs["available"] is True
        assert prs["platform"] == "tiktok"
        # Conflict resolution: podcast + tiktok → motion_energy capped, hook moderated
        cam = prs["strategy"]["camera"]
        assert cam["motion_energy"] not in ("high", "medium_high")
        hook = prs["strategy"]["hook"]
        assert hook["hook_energy"] != "high"
