"""
knowledge_store_builder.py — Singleton LocalKnowledgeStore built from knowledge packs.

Converts all KnowledgePack rules → ExternalKnowledgeItem and populates a
LocalKnowledgeStore instance once at first call. Subsequent calls return the
cached instance (thread-safe via threading.Lock).

Public API:
    get_pack_knowledge_store() -> LocalKnowledgeStore | None
        Returns the singleton store, or None if packs failed to load.
        Never raises.

Safety contract (matches AI module rules):
    ✅ Never raises — returns None on any failure
    ✅ Import-safe — lazy deps, no GPU required
    ✅ Singleton — built once, no per-render overhead
    ✅ Advisory only — pack content is metadata, not executable code
"""
from __future__ import annotations

import logging
import threading
from typing import List, Optional

logger = logging.getLogger("app.ai.knowledge.store_builder")

# Market and platform tag sets for field mapping
_MARKET_TAGS: frozenset[str] = frozenset({
    "us", "eu", "jp", "sea", "kr", "latam", "in", "uk", "de", "fr",
})
_PLATFORM_TAGS: frozenset[str] = frozenset({
    "tiktok", "youtube_shorts", "instagram_reels",
})

# Map knowledge pack domain → ExternalKnowledgeItem source_type
_DOMAIN_TO_SOURCE_TYPE: dict[str, str] = {
    "market":    "market_pattern",
    "hook":      "hook_pattern",
    "pacing":    "pacing_pattern",
    "subtitle":  "subtitle_pattern",
    "retention": "trend_summary",
    "camera":    "style_pattern",
    "creator":   "style_pattern",
    "audio":     "style_pattern",
}

# Singleton state
_store_lock: threading.Lock = threading.Lock()
_store_instance = None          # LocalKnowledgeStore | None
_store_initialized: bool = False


def get_pack_knowledge_store():
    """Return the singleton LocalKnowledgeStore populated from knowledge packs.

    Returns None if packs could not be loaded or an error occurs.
    Thread-safe. Never raises.
    """
    global _store_instance, _store_initialized
    if _store_initialized:
        return _store_instance
    with _store_lock:
        if _store_initialized:
            return _store_instance
        try:
            _store_instance = _build()
        except Exception as exc:
            logger.debug("pack_knowledge_store_build_failed: %s", exc)
            _store_instance = None
        _store_initialized = True
    return _store_instance


def _build():
    """Build and populate the LocalKnowledgeStore. May raise — caller handles."""
    from app.ai.knowledge.knowledge_pack_loader import load_knowledge_packs
    from app.ai.knowledge.knowledge_store import LocalKnowledgeStore
    from app.ai.knowledge.knowledge_schema import ExternalKnowledgeItem

    packs = load_knowledge_packs()
    if not packs:
        logger.debug("pack_knowledge_store_empty: no packs loaded")
        return None

    store = LocalKnowledgeStore()
    items = _packs_to_items(packs, ExternalKnowledgeItem)
    added = store.add_items(items)
    logger.info("pack_knowledge_store_built count=%d packs=%d", added, len(packs))
    return store


def _packs_to_items(packs, ExternalKnowledgeItem) -> List:
    items = []
    for pack in packs:
        source_type = _DOMAIN_TO_SOURCE_TYPE.get(pack.domain, "manual_note")
        for rule in pack.rules:
            applies = rule.applies_to or []
            item = ExternalKnowledgeItem(
                id=f"{pack.id}__{rule.id}",
                source_type=source_type,
                text=f"{rule.title} — {rule.description}",
                market=_first_match(applies, _MARKET_TAGS),
                platform=_first_match(applies, _PLATFORM_TAGS),
                style=rule.recommendation.get("subtitle_emphasis") or None,
                topic=pack.domain,
                tags=list(applies) + [pack.domain],
                confidence=float(rule.confidence),
                metadata={
                    "pack_id": pack.id,
                    "rule_id": rule.id,
                    "recommendation": rule.recommendation,
                },
            )
            items.append(item)
    return items


def _first_match(applies_to: List[str], tag_set: frozenset) -> Optional[str]:
    for tag in applies_to:
        if tag in tag_set:
            return tag
    return None
