"""
pattern_registry.py — Creator pattern registry. Phase 40.

Loads patterns from knowledge/patterns/ JSON files and the built-in extractor.
Local-only. No internet, no subprocess. Never raises.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ai.knowledge.pattern_schema import AICreatorPattern, AIPatternRegistry
from app.ai.knowledge.pattern_safety import is_pattern_safe, sanitize_pattern
from app.ai.knowledge.pattern_extractor import (
    extract_creator_patterns,
    _from_dict as _pattern_from_dict,
)

logger = logging.getLogger("app.ai.knowledge.pattern_registry")

_PATTERN_SUBDIRS = ("hooks", "subtitles", "pacing", "camera", "retention")
_MAX_FILE_SIZE_BYTES = 500_000

# Module-level cache
_PATTERN_CACHE: Dict[str, List[AICreatorPattern]] = {}
_REGISTRY_CACHE: Dict[str, AIPatternRegistry] = {}


def load_pattern_registry(base_path: Any = None) -> AIPatternRegistry:
    """Load all creator patterns from knowledge/patterns/ and built-in archetypes.

    Returns an AIPatternRegistry with summary. Never raises.
    Falls back safely when folders are missing.
    """
    try:
        resolved = _resolve_base_path(base_path)
        cache_key = str(resolved)

        if cache_key in _REGISTRY_CACHE:
            return _REGISTRY_CACHE[cache_key]

        file_patterns = _load_patterns_from_files(resolved)
        archetype_patterns = extract_creator_patterns([])
        all_patterns = file_patterns + [
            p for p in archetype_patterns
            if not any(p.pattern_id == ep.pattern_id for ep in file_patterns)
        ]
        _PATTERN_CACHE[cache_key] = all_patterns

        pattern_types = sorted({p.pattern_type for p in all_patterns if p.pattern_type})
        creator_styles = sorted({p.creator_style for p in all_patterns if p.creator_style})

        registry = AIPatternRegistry(
            available=True,
            loaded_patterns=len(all_patterns),
            pattern_types=pattern_types,
            creator_styles=creator_styles,
            warnings=[],
        )
        _REGISTRY_CACHE[cache_key] = registry

        logger.info(
            "ai_creator_pattern_registry_ready base=%s loaded=%d types=%s",
            resolved, len(all_patterns), pattern_types,
        )
        if all_patterns:
            logger.info("ai_creator_pattern_loaded count=%d", len(all_patterns))

        return registry

    except Exception as exc:
        logger.debug("pattern_registry_error: %s", exc)
        return AIPatternRegistry(
            available=False,
            loaded_count=0,
            warnings=[f"pattern_registry_error:{type(exc).__name__}"],
        )


def list_pattern_types(base_path: Any = None) -> List[str]:
    """Return sorted list of available pattern types. Never raises."""
    try:
        reg = load_pattern_registry(base_path)
        return list(reg.pattern_types)
    except Exception:
        return []


def list_creator_patterns(style: str, base_path: Any = None) -> List[AICreatorPattern]:
    """Return patterns matching a creator style. Never raises."""
    try:
        resolved = _resolve_base_path(base_path)
        cache_key = str(resolved)
        if cache_key not in _PATTERN_CACHE:
            load_pattern_registry(base_path)
        return [p for p in _PATTERN_CACHE.get(cache_key, []) if p.creator_style == style]
    except Exception:
        return []


def get_patterns_by_type(pattern_type: str, base_path: Any = None) -> List[AICreatorPattern]:
    """Return all patterns of a given type. Never raises."""
    try:
        resolved = _resolve_base_path(base_path)
        cache_key = str(resolved)
        if cache_key not in _PATTERN_CACHE:
            load_pattern_registry(base_path)
        return [p for p in _PATTERN_CACHE.get(cache_key, []) if p.pattern_type == pattern_type]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_base_path(base_path: Any) -> Path:
    if base_path is not None:
        return (Path(str(base_path)) / "patterns").resolve()
    here = Path(__file__).resolve().parent
    backend_root = here.parent.parent.parent
    return (backend_root / "knowledge" / "patterns").resolve()


def _load_patterns_from_files(base: Path) -> List[AICreatorPattern]:
    patterns: List[AICreatorPattern] = []
    try:
        for subdir in _PATTERN_SUBDIRS:
            folder = base / subdir
            if not folder.exists() or not folder.is_dir():
                continue
            for json_file in sorted(folder.glob("*.json")):
                p = _load_pattern_file(json_file)
                if p is not None:
                    patterns.append(p)
    except Exception as exc:
        logger.debug("load_patterns_from_files_error: %s", exc)
    return patterns


def _load_pattern_file(path: Path) -> Optional[AICreatorPattern]:
    try:
        if path.stat().st_size > _MAX_FILE_SIZE_BYTES:
            return None
        raw_text = path.read_text(encoding="utf-8", errors="replace")
        raw_data = json.loads(raw_text)
        if not isinstance(raw_data, dict):
            return None
        sanitized = sanitize_pattern(raw_data)
        if not sanitized or not is_pattern_safe(sanitized):
            return None
        sanitized["safe"] = True
        return _pattern_from_dict(sanitized)
    except Exception as exc:
        logger.debug("load_pattern_file_error path=%s: %s", path, exc)
        return None
