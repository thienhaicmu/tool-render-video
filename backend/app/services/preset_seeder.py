"""
preset_seeder.py — Seeds built-in render presets at startup.

Phase E — Smart Render Presets. Called once from main.py lifespan.
Uses upsert_preset (ON CONFLICT UPDATE) so it is idempotent — safe to
run on every startup. Built-in preset IDs are stable slugs so they
survive across restarts without duplication.

Never raises — a seeder failure must not block app startup.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.services.preset_seeder")

# Stable IDs for built-in presets (never change these after release).
_BUILTIN_PRESETS: list[dict] = [
    {
        "preset_id": "builtin-tiktok-viral",
        "name": "TikTok Viral",
        "description": "5 clips, aggressive hooks, viral framing. Best for trending content.",
        "platform": "tiktok",
        "params": {
            "output_count": 5,
            "target_platform": "tiktok",
            "target_duration": 180,
            "video_type": "viral",
            "hook_strength": "aggressive",
            "add_subtitle": True,
            "llm_enabled": True,
            "ai_clip_min_duration_sec": 15,
            "ai_clip_max_duration_sec": 60,
        },
    },
    {
        "preset_id": "builtin-youtube-shorts",
        "name": "YouTube Shorts",
        "description": "3 clips ≤60s, balanced hooks, informative style.",
        "platform": "youtube_shorts",
        "params": {
            "output_count": 3,
            "target_platform": "youtube_shorts",
            "target_duration": 120,
            "video_type": "educational",
            "hook_strength": "balanced",
            "add_subtitle": True,
            "llm_enabled": True,
            "ai_clip_min_duration_sec": 20,
            "ai_clip_max_duration_sec": 60,
        },
    },
    {
        "preset_id": "builtin-instagram-reels",
        "name": "Instagram Reels",
        "description": "3 clips, polished emotional moments, story or clean subtitles.",
        "platform": "instagram_reels",
        "params": {
            "output_count": 3,
            "target_platform": "instagram_reels",
            "target_duration": 90,
            "video_type": "emotional",
            "hook_strength": "soft",
            "add_subtitle": True,
            "llm_enabled": True,
            "ai_clip_min_duration_sec": 15,
            "ai_clip_max_duration_sec": 90,
        },
    },
    {
        "preset_id": "builtin-podcast-clips",
        "name": "Podcast Clips",
        "description": "5 longer clips (45–90s), soft hooks, storytelling style.",
        "platform": "",
        "params": {
            "output_count": 5,
            "target_duration": 300,
            "video_type": "storytelling",
            "hook_strength": "soft",
            "add_subtitle": True,
            "llm_enabled": True,
            "ai_clip_min_duration_sec": 45,
            "ai_clip_max_duration_sec": 90,
        },
    },
    {
        "preset_id": "builtin-quick-preview",
        "name": "Quick Preview",
        "description": "Single 30s clip, no LLM — fast local heuristic pick.",
        "platform": "",
        "params": {
            "output_count": 1,
            "target_duration": 30,
            "llm_enabled": False,
            "ai_clip_min_duration_sec": 15,
            "ai_clip_max_duration_sec": 45,
        },
    },
]


def seed_builtin_presets() -> None:
    """Insert or update all built-in presets. Never raises."""
    try:
        from app.db.presets_repo import upsert_preset
        for p in _BUILTIN_PRESETS:
            try:
                upsert_preset(
                    preset_id=p["preset_id"],
                    name=p["name"],
                    params=p["params"],
                    description=p.get("description", ""),
                    platform=p.get("platform", ""),
                    is_builtin=True,
                )
            except Exception as exc:
                logger.warning("preset_seeder: failed to seed %r — %s", p["preset_id"], exc)
        logger.info("preset_seeder: seeded %d built-in presets", len(_BUILTIN_PRESETS))
    except Exception as exc:
        logger.warning("preset_seeder: seed_builtin_presets failed — %s", exc)
