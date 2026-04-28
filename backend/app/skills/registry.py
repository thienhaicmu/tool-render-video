"""
Skill adapter registry.

Loads all skill adapters lazily on first access.  Heavy imports stay inside
each adapter's run() method so startup is never slowed or broken by missing
optional dependencies (e.g. faster_whisper).
"""
from __future__ import annotations

import importlib
import logging
from typing import Any

logger = logging.getLogger("app.skills.registry")

_ADAPTER_MODULES = [
    "app.skills.audio_pro_mix",
    "app.skills.subtitle_readability",
    "app.skills.video_quality_preset",
    "app.skills.smart_crop",
    "app.skills.fast_captions",
    "app.skills.highlight_detection",
]

_REGISTRY: dict[str, Any] = {}
_LOADED = False


def _load_adapters() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    for module_path in _ADAPTER_MODULES:
        try:
            mod = importlib.import_module(module_path)
            adapter = getattr(mod, "ADAPTER", None)
            if adapter and hasattr(adapter, "skill_id"):
                _REGISTRY[adapter.skill_id] = adapter
                logger.debug("Skill adapter loaded: %s", adapter.skill_id)
            else:
                logger.warning("Skill module %s has no ADAPTER object", module_path)
        except Exception as exc:
            logger.warning("Failed to load skill adapter %s: %s", module_path, exc)


def get_registry() -> dict[str, Any]:
    _load_adapters()
    return _REGISTRY


def get_manifest() -> list[dict]:
    """Return skill manifest list for the /api/skills/manifest endpoint."""
    reg = get_registry()
    result = []
    for skill_id, adapter in reg.items():
        try:
            available = bool(adapter.check())
        except Exception:
            available = False
        declared = getattr(adapter, "status", "available")
        effective_status = declared if declared == "experimental" else ("available" if available else "unavailable")
        result.append({
            "skill_id": skill_id,
            "label": getattr(adapter, "label", skill_id),
            "description": getattr(adapter, "description", ""),
            "status": effective_status,
            "config_schema": getattr(adapter, "config_schema", {}),
            "default_options": getattr(adapter, "default_options", {}),
        })
    return result
