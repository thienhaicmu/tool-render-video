"""
ai_modes.py — Local AI mode configuration registry.

Each mode defines scoring weights, style preferences, pacing hints,
and camera/subtitle defaults for the AI Director.
All modes are offline-only — no cloud API calls, no mandatory ML libraries.
"""
from __future__ import annotations

_AI_MODES: dict[str, dict] = {
    "viral_tiktok": {
        "preferred_duration_min": 60,
        "preferred_duration_max": 90,
        "subtitle_tone": "hype",
        "camera_behavior": "emotional_push",
        "speech_density_weight": 0.35,
        "hook_weight": 0.35,
        "silence_penalty_weight": 0.20,
        "duration_weight": 0.10,
        # Phase 4 — pacing hints
        "pacing_style": "fast",
        "prefer_beat_sync": True,
        "emotion_bias": "curiosity",
        # Phase 5 — camera/subtitle defaults
        "subtitle_emphasis_style": "punch",
        "subtitle_density": "compact",
        "camera_zoom_strength": 1.12,
    },
    "podcast_shorts": {
        "preferred_duration_min": 45,
        "preferred_duration_max": 120,
        "subtitle_tone": "clean",
        "camera_behavior": "subtle_follow",
        "speech_density_weight": 0.40,
        "hook_weight": 0.25,
        "silence_penalty_weight": 0.15,
        "duration_weight": 0.20,
        # Phase 4 — pacing hints
        "pacing_style": "medium",
        "prefer_beat_sync": False,
        "emotion_bias": "clarity",
        # Phase 5 — camera/subtitle defaults
        "subtitle_emphasis_style": "keyword",
        "subtitle_density": "normal",
        "camera_zoom_strength": 1.05,
    },
    "storytelling": {
        "preferred_duration_min": 60,
        "preferred_duration_max": 120,
        "subtitle_tone": "story",
        "camera_behavior": "slow_reveal",
        "speech_density_weight": 0.30,
        "hook_weight": 0.30,
        "silence_penalty_weight": 0.20,
        "duration_weight": 0.20,
        # Phase 4 — pacing hints
        "pacing_style": "slow_build",
        "prefer_beat_sync": False,
        "emotion_bias": "curiosity",
        # Phase 5 — camera/subtitle defaults
        "subtitle_emphasis_style": "soft",
        "subtitle_density": "normal",
        "camera_zoom_strength": 1.05,
    },
    "clean_subtitle": {
        "preferred_duration_min": 30,
        "preferred_duration_max": 90,
        "subtitle_tone": "clean",
        "camera_behavior": "none",
        "speech_density_weight": 0.35,
        "hook_weight": 0.25,
        "silence_penalty_weight": 0.20,
        "duration_weight": 0.20,
        # Phase 4 — pacing hints
        "pacing_style": "stable",
        "prefer_beat_sync": False,
        "emotion_bias": "neutral",
        # Phase 5 — camera/subtitle defaults
        "subtitle_emphasis_style": "none",
        "subtitle_density": "comfortable",
        "camera_zoom_strength": 1.0,
    },
}

_DEFAULT_MODE = "viral_tiktok"

VALID_AI_MODES = frozenset(_AI_MODES.keys())


def get_mode_config(mode: str) -> dict:
    """Return a copy of the mode config, falling back to viral_tiktok if unknown."""
    return dict(_AI_MODES.get(str(mode or ""), _AI_MODES[_DEFAULT_MODE]))
