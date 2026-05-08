"""
style_profiles.py — Safe editing archetype profiles. Phase 14.

Defines generic editing archetypes by tendency, NOT by replicating any
specific creator. No copyrighted creator names are used. No platform
scraping. No claims of exact replication.

Public API:
    get_profile(style_id) -> CreatorStyleProfile | None
    get_all_profiles()    -> dict[str, CreatorStyleProfile]
    STYLE_IDS             -> frozenset[str]
"""
from __future__ import annotations

from app.ai.styles.style_schema import CreatorStyleProfile

# ── Archetype registry ────────────────────────────────────────────────────────

_PROFILES: dict[str, CreatorStyleProfile] = {

    "podcast_viral": CreatorStyleProfile(
        style_id="podcast_viral",
        display_name="Podcast Viral",
        pacing_style="fast",
        subtitle_style="punch",
        camera_behavior="fast_follow",
        hook_style="urgency",
        story_arc_style="hook_to_climax",
        energy_level="high",
        notes=["High-energy fast-cut content designed for viral reach on short-form platforms"],
    ),

    "high_energy_reaction": CreatorStyleProfile(
        style_id="high_energy_reaction",
        display_name="High Energy Reaction",
        pacing_style="fast",
        subtitle_style="punch",
        camera_behavior="dramatic_push",
        hook_style="surprise",
        story_arc_style="emotional_peak",
        energy_level="very_high",
        notes=["Very fast cuts with surprise-driven reactions and peak emotional moments"],
    ),

    "storytelling_cinematic": CreatorStyleProfile(
        style_id="storytelling_cinematic",
        display_name="Storytelling Cinematic",
        pacing_style="slow_build",
        subtitle_style="minimal",
        camera_behavior="slow_reveal",
        hook_style="curiosity",
        story_arc_style="hook_to_payoff",
        energy_level="medium",
        notes=["Deliberate narrative arc with cinematic pacing and story-first structure"],
    ),

    "documentary_clean": CreatorStyleProfile(
        style_id="documentary_clean",
        display_name="Documentary Clean",
        pacing_style="slow",
        subtitle_style="clean",
        camera_behavior="static",
        hook_style="informational",
        story_arc_style="linear_build",
        energy_level="low",
        notes=["Calm, clean presentation with informational structure and minimal cuts"],
    ),

    "educational_focus": CreatorStyleProfile(
        style_id="educational_focus",
        display_name="Educational Focus",
        pacing_style="medium",
        subtitle_style="bold",
        camera_behavior="static",
        hook_style="question",
        story_arc_style="informational",
        energy_level="medium",
        notes=["Tutorial or explainer format with clear pacing and dense information delivery"],
    ),

    "anime_edit": CreatorStyleProfile(
        style_id="anime_edit",
        display_name="Anime Edit",
        pacing_style="fast",
        subtitle_style="bold",
        camera_behavior="dramatic_push",
        hook_style="dramatic",
        story_arc_style="tension_release",
        energy_level="very_high",
        notes=["Very fast beat-matched cuts with dramatic tension arcs and bold overlays"],
    ),

    "gameplay_highlight": CreatorStyleProfile(
        style_id="gameplay_highlight",
        display_name="Gameplay Highlight",
        pacing_style="fast",
        subtitle_style="overlay",
        camera_behavior="fast_follow",
        hook_style="reaction",
        story_arc_style="emotional_peak",
        energy_level="high",
        notes=["Fast-paced clips showcasing peak gameplay moments with reaction emphasis"],
    ),

    "motivation_short": CreatorStyleProfile(
        style_id="motivation_short",
        display_name="Motivation Short",
        pacing_style="medium_fast",
        subtitle_style="bold",
        camera_behavior="slow_reveal",
        hook_style="urgency",
        story_arc_style="front_loaded",
        energy_level="high",
        notes=["Urgency-driven short-form motivation with front-loaded hook and punchy delivery"],
    ),

    "interview_clip": CreatorStyleProfile(
        style_id="interview_clip",
        display_name="Interview Clip",
        pacing_style="slow",
        subtitle_style="clean",
        camera_behavior="static",
        hook_style="question",
        story_arc_style="informational",
        energy_level="low",
        notes=["Conversational clips with clean subtitles, static framing, and steady pacing"],
    ),

    "calm_minimal": CreatorStyleProfile(
        style_id="calm_minimal",
        display_name="Calm Minimal",
        pacing_style="slow",
        subtitle_style="minimal",
        camera_behavior="static",
        hook_style="story",
        story_arc_style="flat",
        energy_level="very_low",
        notes=["Minimal aesthetic with very slow pacing and quiet, story-first presentation"],
    ),
}

# ── Public constants ──────────────────────────────────────────────────────────

STYLE_IDS: frozenset[str] = frozenset(_PROFILES.keys())

# Advisory target duration hints per style (seconds) — informational only
STYLE_DURATION_HINTS: dict[str, float] = {
    "podcast_viral": 60.0,
    "high_energy_reaction": 45.0,
    "storytelling_cinematic": 90.0,
    "documentary_clean": 120.0,
    "educational_focus": 90.0,
    "anime_edit": 30.0,
    "gameplay_highlight": 60.0,
    "motivation_short": 30.0,
    "interview_clip": 90.0,
    "calm_minimal": 60.0,
}


# ── Public API ────────────────────────────────────────────────────────────────

def get_profile(style_id: str) -> CreatorStyleProfile | None:
    """Return the profile for a known style_id, or None."""
    return _PROFILES.get(str(style_id))


def get_all_profiles() -> dict[str, CreatorStyleProfile]:
    """Return a copy of the full profile registry."""
    return dict(_PROFILES)
