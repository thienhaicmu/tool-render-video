"""
knowledge_warmup.py — Singleton access and startup warmup for KnowledgeIndex.

Public API:
    get_knowledge_index() -> KnowledgeIndex   — thread-safe singleton, lazy init
    warmup_knowledge_index() -> None          — trigger load/build at startup
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

from app.ai.rag.knowledge_index import KnowledgeIndex

logger = logging.getLogger(__name__)

_knowledge_index_singleton: Optional[KnowledgeIndex] = None
_knowledge_index_lock = threading.Lock()


def get_knowledge_index() -> KnowledgeIndex:
    """Return the singleton KnowledgeIndex, loading lazily on first call.

    Thread-safe. Never raises — if load/rebuild fails, returns an empty index.
    First call sequence:
        1. try load() from disk (index_path)
        2. if failed, try rebuild() from processed_dir
        3. if rebuild fails (no files, no embeddings), log warning, continue
    """
    global _knowledge_index_singleton

    if _knowledge_index_singleton is not None:
        return _knowledge_index_singleton

    with _knowledge_index_lock:
        # Double-checked locking
        if _knowledge_index_singleton is not None:
            return _knowledge_index_singleton

        idx = KnowledgeIndex()

        try:
            loaded = idx.load()
            if loaded:
                logger.info("knowledge_warmup: index loaded from disk (%s items)", len(idx._items))
            else:
                logger.info("knowledge_warmup: disk load failed — rebuilding from processed dir")
                idx.rebuild()
                if idx.is_ready() and idx._items:
                    logger.info(
                        "knowledge_warmup: rebuild complete (%d items)",
                        len(idx._items),
                    )
                else:
                    logger.warning(
                        "knowledge_warmup: rebuild produced empty index — "
                        "no knowledge files found; renders will use safe defaults"
                    )
        except Exception as exc:
            logger.warning(
                "knowledge_warmup: failed to load/rebuild index: %s — "
                "renders will use safe defaults",
                exc,
            )

        _knowledge_index_singleton = idx
        return _knowledge_index_singleton


def warmup_knowledge_index() -> None:
    """Trigger knowledge index load/build at startup.

    Designed to be called in a background thread. Never raises.
    """
    try:
        idx = get_knowledge_index()
        if idx.is_ready() and idx._items:
            logger.info(
                "knowledge_warmup: warmup complete — %d items ready",
                len(idx._items),
            )
        else:
            logger.warning(
                "knowledge_warmup: warmup complete but index is empty — "
                "AI knowledge augmentation will be skipped at render time"
            )
    except Exception as exc:
        logger.warning("knowledge_warmup: warmup failed: %s — renders will use safe defaults", exc)
