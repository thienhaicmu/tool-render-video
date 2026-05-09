"""
preset_memory.py — Creator preset evolution persistence. Phase 46.

Rules:
- Deterministic only
- Never raises
- Local JSON persistence only
- Safe fallback if missing/corrupt
- No internet access
- No file deletion
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from app.ai.preset_evolution.preset_schema import AICreatorPreset
from app.ai.preset_evolution.preset_safety import sanitize_preset

logger = logging.getLogger("app.ai.preset_evolution.memory")

_PRESET_DIR = Path("data/preset_evolution/presets")
_PRESET_FILE = "evolved_presets.json"
_MAX_EVOLVED_PRESETS = 50

# Built-in starter presets: 3 market archetypes, generation 1
_BUILTIN_PRESETS: list[dict] = [
    {
        "preset_id": "tiktok_viral_v1",
        "preset_name": "TikTok Viral",
        "creator_style": "viral_tiktok",
        "market_type": "tiktok",
        "subtitle_style": "compact",
        "pacing_style": "fast_hook",
        "camera_style": "dynamic_safe",
        "hook_style": "strong_open",
        "quality_score": 70.0,
        "creator_fit_score": 70.0,
        "market_fit_score": 75.0,
        "evolution_generation": 1,
        "confidence": 0.70,
        "tags": ["tiktok", "viral", "fast"],
        "warnings": [],
        "explanation": ["Built-in TikTok Viral preset"],
    },
    {
        "preset_id": "podcast_clean_v1",
        "preset_name": "Podcast Clean",
        "creator_style": "podcast",
        "market_type": "podcast",
        "subtitle_style": "readable",
        "pacing_style": "calm_storytelling",
        "camera_style": "static_podcast",
        "hook_style": "soft_open",
        "quality_score": 65.0,
        "creator_fit_score": 68.0,
        "market_fit_score": 65.0,
        "evolution_generation": 1,
        "confidence": 0.65,
        "tags": ["podcast", "calm", "readability"],
        "warnings": [],
        "explanation": ["Built-in Podcast Clean preset"],
    },
    {
        "preset_id": "educational_v1",
        "preset_name": "Educational",
        "creator_style": "educational",
        "market_type": "educational",
        "subtitle_style": "clean_readable",
        "pacing_style": "measured",
        "camera_style": "static_framing",
        "hook_style": "curiosity_hook",
        "quality_score": 65.0,
        "creator_fit_score": 65.0,
        "market_fit_score": 65.0,
        "evolution_generation": 1,
        "confidence": 0.65,
        "tags": ["educational", "clear", "measured"],
        "warnings": [],
        "explanation": ["Built-in Educational preset"],
    },
]


def build_default_presets() -> List[AICreatorPreset]:
    """Return the built-in starter presets. Never raises."""
    try:
        return [AICreatorPreset.from_dict(p) for p in _BUILTIN_PRESETS]
    except Exception as exc:
        logger.debug("preset_memory_build_default_error: %s", exc)
        return []


def load_evolved_presets() -> List[AICreatorPreset]:
    """Load persisted evolved presets; fall back to built-ins on any error. Never raises."""
    try:
        preset_path = _PRESET_DIR / _PRESET_FILE
        if not preset_path.exists():
            logger.debug("preset_memory_file_missing path=%s using defaults", preset_path)
            return build_default_presets()

        raw = preset_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        presets_raw = data.get("presets") if isinstance(data, dict) else data
        if not isinstance(presets_raw, list):
            logger.debug("preset_memory_corrupt_structure path=%s using defaults", preset_path)
            return build_default_presets()

        loaded = [AICreatorPreset.from_dict(sanitize_preset(p)) for p in presets_raw if isinstance(p, dict)]
        if not loaded:
            return build_default_presets()

        logger.debug("preset_memory_loaded count=%d path=%s", len(loaded), preset_path)
        return loaded
    except Exception as exc:
        logger.debug("preset_memory_load_error: %s using defaults", exc)
        return build_default_presets()


def save_evolved_presets(presets: List[AICreatorPreset]) -> bool:
    """Persist evolved presets to disk. Returns True on success. Never raises."""
    try:
        if not isinstance(presets, list):
            return False

        # Enforce cap
        capped = presets[:_MAX_EVOLVED_PRESETS]

        _PRESET_DIR.mkdir(parents=True, exist_ok=True)
        preset_path = _PRESET_DIR / _PRESET_FILE

        data = {
            "version": "1",
            "presets": [sanitize_preset(p.to_dict()) for p in capped if hasattr(p, "to_dict")],
        }
        preset_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("preset_memory_saved count=%d path=%s", len(capped), preset_path)
        return True
    except Exception as exc:
        logger.debug("preset_memory_save_error: %s", exc)
        return False
