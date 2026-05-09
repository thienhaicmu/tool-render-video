"""
market_profiles.py — Built-in market optimization profiles. Phase 44.

Defines safe, deterministic default profiles for each target platform.
All profiles are metadata-only: no FFmpeg, no playback_speed, no subtitle timing.

Public API:
    get_market_profile(name: str) -> AIMarketOptimizationProfile
    list_market_profiles() -> list[str]
"""
from __future__ import annotations

from app.ai.market.market_schema import AIMarketOptimizationProfile

# ── Profile registry ──────────────────────────────────────────────────────────

_PROFILES: dict[str, AIMarketOptimizationProfile] = {
    "viral_tiktok": AIMarketOptimizationProfile(
        market_id="viral_tiktok",
        platform_type="tiktok",
        preferred_subtitle_style="compact",
        preferred_pacing_style="fast_hook",
        preferred_camera_style="dynamic_safe",
        preferred_hook_style="aggressive_question",
        subtitle_density_bias=0.70,
        pacing_energy_bias=0.85,
        camera_motion_bias=0.75,
        hook_strength_bias=0.90,
        retention_preferences={
            "loop_payoff": True,
            "rapid_reengagement": True,
            "hook_within_first_3s": True,
        },
        confidence=0.90,
        tags=["tiktok", "viral", "short_form", "fast_paced"],
    ),

    "youtube_shorts": AIMarketOptimizationProfile(
        market_id="youtube_shorts",
        platform_type="youtube_shorts",
        preferred_subtitle_style="readable",
        preferred_pacing_style="medium_fast",
        preferred_camera_style="creator_framing",
        preferred_hook_style="curiosity_question",
        subtitle_density_bias=0.55,
        pacing_energy_bias=0.65,
        camera_motion_bias=0.55,
        hook_strength_bias=0.75,
        retention_preferences={
            "creator_framing": True,
            "payoff_reinforcement": True,
            "hook_within_first_5s": True,
        },
        confidence=0.85,
        tags=["youtube", "shorts", "short_form", "creator"],
    ),

    "facebook_reels": AIMarketOptimizationProfile(
        market_id="facebook_reels",
        platform_type="facebook_reels",
        preferred_subtitle_style="medium_density",
        preferred_pacing_style="smooth_engagement",
        preferred_camera_style="social_framing",
        preferred_hook_style="emotional_hook",
        subtitle_density_bias=0.50,
        pacing_energy_bias=0.55,
        camera_motion_bias=0.45,
        hook_strength_bias=0.65,
        retention_preferences={
            "engagement_loops": True,
            "emotional_retention": True,
        },
        confidence=0.80,
        tags=["facebook", "reels", "social", "engagement"],
    ),

    "podcast": AIMarketOptimizationProfile(
        market_id="podcast",
        platform_type="podcast",
        preferred_subtitle_style="readable",
        preferred_pacing_style="calm_storytelling",
        preferred_camera_style="static_podcast",
        preferred_hook_style="narrative_hook",
        subtitle_density_bias=0.35,
        pacing_energy_bias=0.30,
        camera_motion_bias=0.20,
        hook_strength_bias=0.40,
        retention_preferences={
            "long_form_retention": True,
            "narrative_flow": True,
        },
        confidence=0.85,
        tags=["podcast", "long_form", "storytelling", "calm"],
    ),

    "educational": AIMarketOptimizationProfile(
        market_id="educational",
        platform_type="educational",
        preferred_subtitle_style="clean_readable",
        preferred_pacing_style="measured",
        preferred_camera_style="static_framing",
        preferred_hook_style="question_hook",
        subtitle_density_bias=0.40,
        pacing_energy_bias=0.35,
        camera_motion_bias=0.25,
        hook_strength_bias=0.50,
        retention_preferences={
            "comprehension_pacing": True,
            "readability_first": True,
        },
        confidence=0.85,
        tags=["educational", "explainer", "readability", "measured"],
    ),
}

# Aliases for flexible market name matching
_ALIASES: dict[str, str] = {
    "tiktok": "viral_tiktok",
    "tiktok_viral": "viral_tiktok",
    "shorts": "youtube_shorts",
    "yt_shorts": "youtube_shorts",
    "youtube": "youtube_shorts",
    "reels": "facebook_reels",
    "fb_reels": "facebook_reels",
    "facebook": "facebook_reels",
    "longform": "podcast",
    "long_form": "podcast",
    "explainer": "educational",
    "education": "educational",
}


def get_market_profile(name: str) -> AIMarketOptimizationProfile:
    """Return the market profile for the given name. Falls back to a safe default. Never raises."""
    try:
        key = str(name or "").lower().strip().replace(" ", "_").replace("-", "_")
        canonical = _ALIASES.get(key, key)
        profile = _PROFILES.get(canonical)
        if profile is not None:
            return profile
        # Partial match: check if any key starts with the requested name
        for pid, prof in _PROFILES.items():
            if pid.startswith(key) or key in pid:
                return prof
        return _build_generic_profile(name)
    except Exception:
        return _build_generic_profile(name)


def list_market_profiles() -> list[str]:
    """Return sorted list of registered market profile IDs. Never raises."""
    try:
        return sorted(_PROFILES.keys())
    except Exception:
        return []


def _build_generic_profile(name: str) -> AIMarketOptimizationProfile:
    """Return a safe low-bias default profile when no match found. Never raises."""
    return AIMarketOptimizationProfile(
        market_id=str(name or "generic").lower()[:32],
        platform_type="generic",
        preferred_subtitle_style="readable",
        preferred_pacing_style="balanced",
        preferred_camera_style="default",
        preferred_hook_style="standard",
        subtitle_density_bias=0.40,
        pacing_energy_bias=0.45,
        camera_motion_bias=0.35,
        hook_strength_bias=0.45,
        confidence=0.50,
        tags=["generic"],
        warnings=["unknown_market_using_generic_profile"],
    )
