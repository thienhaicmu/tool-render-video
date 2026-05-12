"""
knowledge_registry.py — Local creator knowledge registry. Phase 39.

Loads and indexes AICreatorKnowledge from the local knowledge/ folder structure.
Local filesystem only. No internet, no network, no subprocess. Never raises.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.ai.knowledge.knowledge_schema import AICreatorKnowledge, AIKnowledgeRegistry
from app.ai.knowledge.knowledge_ingestion import ingest_knowledge_directory

logger = logging.getLogger("app.ai.knowledge.registry")

_KNOWLEDGE_SUBDIRS = ("creators", "markets", "subtitles", "pacing", "hooks", "camera")

# Module-level cache: registry instance per resolved base_path string
_REGISTRY_CACHE: Dict[str, AIKnowledgeRegistry] = {}
_ITEMS_CACHE: Dict[str, List[AICreatorKnowledge]] = {}


def load_knowledge_registry(base_path: Any = None) -> AIKnowledgeRegistry:
    """Load and index all local creator knowledge files.

    Returns an AIKnowledgeRegistry with summary metadata.
    Never raises. Falls back safely when folders are missing.
    No internet, no subprocess.
    """
    try:
        resolved = _resolve_base_path(base_path)
        cache_key = str(resolved)

        if cache_key in _REGISTRY_CACHE:
            return _REGISTRY_CACHE[cache_key]

        all_items = _load_all_items(resolved)
        _ITEMS_CACHE[cache_key] = all_items

        categories = sorted({item.category for item in all_items if item.category})
        creator_styles = sorted({item.creator_style for item in all_items if item.creator_style})

        registry = AIKnowledgeRegistry(
            available=True,
            loaded_count=len(all_items),
            categories=categories,
            creator_styles=creator_styles,
            warnings=[],
        )
        _REGISTRY_CACHE[cache_key] = registry

        logger.info(
            "ai_creator_knowledge_registry_ready base=%s loaded=%d categories=%s styles=%s",
            resolved, len(all_items), categories, creator_styles,
        )
        if all_items:
            logger.info(
                "ai_creator_knowledge_loaded count=%d", len(all_items)
            )
        return registry

    except Exception as exc:
        logger.debug("knowledge_registry_error: %s", exc)
        return AIKnowledgeRegistry(
            available=False,
            loaded_count=0,
            warnings=[f"registry_error:{type(exc).__name__}"],
        )


def load_creator_knowledge(
    style_name: str,
    base_path: Any = None,
) -> List[AICreatorKnowledge]:
    """Return all knowledge items matching a creator style. Never raises."""
    try:
        resolved = _resolve_base_path(base_path)
        cache_key = str(resolved)
        if cache_key not in _ITEMS_CACHE:
            load_knowledge_registry(base_path)
        items = _ITEMS_CACHE.get(cache_key, [])
        return [item for item in items if item.creator_style == style_name]
    except Exception:
        return []


def load_category_knowledge(
    category: str,
    base_path: Any = None,
) -> List[AICreatorKnowledge]:
    """Return all knowledge items matching a category. Never raises."""
    try:
        resolved = _resolve_base_path(base_path)
        cache_key = str(resolved)
        if cache_key not in _ITEMS_CACHE:
            load_knowledge_registry(base_path)
        items = _ITEMS_CACHE.get(cache_key, [])
        return [item for item in items if item.category == category]
    except Exception:
        return []


def list_available_knowledge(base_path: Any = None) -> List[str]:
    """Return sorted list of all knowledge_ids. Never raises."""
    try:
        resolved = _resolve_base_path(base_path)
        cache_key = str(resolved)
        if cache_key not in _ITEMS_CACHE:
            load_knowledge_registry(base_path)
        items = _ITEMS_CACHE.get(cache_key, [])
        return sorted(item.knowledge_id for item in items)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_base_path(base_path: Any) -> Path:
    """Resolve base_path; defaults to knowledge/ relative to this file's package root."""
    if base_path is not None:
        return Path(str(base_path)).resolve()
    here = Path(__file__).resolve().parent
    # Walk up to find the backend root (where app/ lives) then use knowledge/
    backend_root = here.parent.parent.parent  # app/ai/knowledge -> app/ai -> app -> backend
    return (backend_root / "knowledge").resolve()


def _load_all_items(base: Path) -> List[AICreatorKnowledge]:
    """Load items from all known subdirectories under base. Never raises."""
    all_items: List[AICreatorKnowledge] = []
    for subdir in _KNOWLEDGE_SUBDIRS:
        folder = base / subdir
        items = ingest_knowledge_directory(folder)
        all_items.extend(items)
    return all_items
