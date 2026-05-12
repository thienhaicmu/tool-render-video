"""
platform_knowledge_loader.py — Phase 55A platform knowledge JSON loader.

Loads AIPlatformKnowledgeItem instances from the local knowledge/platforms/
directory. Completely separate from the AICreatorKnowledge registry (Phase 39)
because platform knowledge uses a different schema shape.

Local filesystem only. No internet, no network, no subprocess. Never raises.
Malformed files are silently skipped.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ai.knowledge.platform_knowledge_schema import AIPlatformKnowledgeItem

logger = logging.getLogger("app.ai.knowledge.platform_loader")

_MAX_FILE_SIZE_BYTES = 500_000  # 500 KB hard cap per platform knowledge file
_MAX_ITEMS = 100                # safety cap on total loaded items

# Keys that MUST NOT appear in platform knowledge files (execution safety)
_FORBIDDEN_KEYS: frozenset = frozenset({
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
    "crop_coordinates", "scene_detection_mutation",
})

# Module-level cache: path → list of items
_LOAD_CACHE: Dict[str, List[AIPlatformKnowledgeItem]] = {}


def load_platform_knowledge(base_path: Any = None) -> List[AIPlatformKnowledgeItem]:
    """Load all platform knowledge items from knowledge/platforms/.

    Returns a list of AIPlatformKnowledgeItem sorted deterministically by
    knowledge_id. Malformed or unsafe files are skipped. Never raises.
    """
    try:
        resolved = _resolve_platforms_path(base_path)
        cache_key = str(resolved)
        if cache_key in _LOAD_CACHE:
            return list(_LOAD_CACHE[cache_key])
        items = _load_from_directory(resolved)
        _LOAD_CACHE[cache_key] = items
        logger.debug(
            "platform_knowledge_loaded path=%s count=%d", resolved, len(items)
        )
        return list(items)
    except Exception as exc:
        logger.debug("platform_knowledge_load_error: %s", exc)
        return []


def load_platform_knowledge_file(path: Any) -> Optional[AIPlatformKnowledgeItem]:
    """Parse a single local JSON file into an AIPlatformKnowledgeItem.

    Returns None when the file is missing, malformed, or fails safety checks.
    Never raises.
    """
    try:
        p = Path(str(path))
        if not p.exists() or not p.is_file():
            logger.debug("platform_knowledge_file_missing path=%s", path)
            return None

        if p.stat().st_size > _MAX_FILE_SIZE_BYTES:
            logger.debug("platform_knowledge_file_too_large path=%s", path)
            return None

        raw_text = p.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.debug("platform_knowledge_malformed_json path=%s: %s", path, exc)
            return None

        if not isinstance(data, dict):
            logger.debug("platform_knowledge_not_dict path=%s", path)
            return None

        if not _is_safe(data):
            logger.debug("platform_knowledge_safety_rejected path=%s", path)
            return None

        item = _build_item(data)
        if not item:
            logger.debug("platform_knowledge_build_failed path=%s", path)
            return None

        logger.debug(
            "platform_knowledge_item_loaded id=%s platform=%s creator_type=%s",
            item.knowledge_id, item.platform, item.creator_type,
        )
        return item

    except Exception as exc:
        logger.debug("platform_knowledge_file_error path=%s: %s", path, exc)
        return None


def clear_cache() -> None:
    """Clear the module-level load cache. Useful for tests."""
    _LOAD_CACHE.clear()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_platforms_path(base_path: Any) -> Path:
    """Resolve the platforms/ subdirectory path."""
    if base_path is not None:
        return Path(str(base_path)).resolve()
    here = Path(__file__).resolve().parent
    # app/ai/knowledge -> app/ai -> app -> backend -> knowledge/platforms
    backend_root = here.parent.parent.parent
    return (backend_root / "knowledge" / "platforms").resolve()


def _load_from_directory(directory: Path) -> List[AIPlatformKnowledgeItem]:
    """Load all *.json files from a directory. Never raises."""
    items: List[AIPlatformKnowledgeItem] = []
    try:
        if not directory.exists() or not directory.is_dir():
            logger.debug("platform_knowledge_directory_missing path=%s", directory)
            return items

        json_files = sorted(directory.glob("*.json"))
        for json_file in json_files:
            item = load_platform_knowledge_file(json_file)
            if item is not None:
                items.append(item)
            if len(items) >= _MAX_ITEMS:
                logger.debug("platform_knowledge_cap_reached limit=%d", _MAX_ITEMS)
                break

        # Deterministic final sort by knowledge_id
        items.sort(key=lambda x: x.knowledge_id)
        logger.debug(
            "platform_knowledge_directory_scanned files=%d loaded=%d",
            len(json_files), len(items),
        )
    except Exception as exc:
        logger.debug("platform_knowledge_directory_error: %s", exc)
    return items


def _is_safe(data: dict) -> bool:
    """Return True if the data dict contains no forbidden execution keys."""
    data_str = str(data)
    return not any(k in data_str for k in _FORBIDDEN_KEYS)


def _build_item(data: dict) -> Optional[AIPlatformKnowledgeItem]:
    """Build an AIPlatformKnowledgeItem from a parsed, sanitised dict."""
    knowledge_id = str(data.get("knowledge_id") or "").strip()
    if not knowledge_id:
        return None

    platform = str(data.get("platform") or "").strip().lower()
    creator_type = str(data.get("creator_type") or "").strip().lower()

    version_raw = data.get("version", 1)
    try:
        version = max(1, int(version_raw))
    except (TypeError, ValueError):
        version = 1

    title = str(data.get("title") or "")[:200]
    description = str(data.get("description") or "")[:500]

    raw_tags = data.get("tags") or []
    tags = [str(t).strip().lower() for t in raw_tags if isinstance(t, str) and t.strip()][:30]

    raw_domains = data.get("domains") or []
    domains = [str(d).strip().lower() for d in raw_domains if isinstance(d, str) and d.strip()][:10]

    guidance_raw = data.get("guidance")
    guidance = dict(guidance_raw) if isinstance(guidance_raw, dict) else {}

    confidence_raw = data.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence_raw)))
    except (TypeError, ValueError):
        confidence = 0.0

    return AIPlatformKnowledgeItem(
        knowledge_id=knowledge_id,
        platform=platform,
        creator_type=creator_type,
        version=version,
        title=title,
        description=description,
        tags=tags,
        domains=domains,
        guidance=guidance,
        confidence=confidence,
    )
