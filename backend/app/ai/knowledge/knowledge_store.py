"""
knowledge_store.py — Local in-memory external knowledge store. Phase 15.

Uses sentence-transformers embeddings when available; falls back to keyword
search otherwise.  In-memory only — no SQLite persistence in Phase 15.

Public API:
    LocalKnowledgeStore
        .add_item(item: ExternalKnowledgeItem) -> bool
        .add_items(items: list[ExternalKnowledgeItem]) -> int
        .search(query, top_k=5, filters=None) -> list[KnowledgeSearchResult]
        .count() -> int
"""
from __future__ import annotations

import logging
import math
from typing import List, Optional

from app.ai.knowledge.knowledge_schema import ExternalKnowledgeItem, KnowledgeSearchResult

logger = logging.getLogger("app.ai.knowledge.store")


class LocalKnowledgeStore:
    """In-memory knowledge store with optional embedding-backed search."""

    def __init__(self) -> None:
        self._items: List[ExternalKnowledgeItem] = []
        self._vectors: List[Optional[List[float]]] = []   # parallel to _items

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add_item(self, item: ExternalKnowledgeItem) -> bool:
        """Add a single item. Returns True on success, False on error."""
        try:
            if not isinstance(item, ExternalKnowledgeItem):
                return False
            vector = _try_embed(item.text)
            self._items.append(item)
            self._vectors.append(vector)
            return True
        except Exception as exc:
            logger.debug("knowledge_store_add_item_failed: %s", exc)
            return False

    def add_items(self, items: List[ExternalKnowledgeItem]) -> int:
        """Add a list of items. Returns count of successfully added items."""
        count = 0
        for item in (items or []):
            if self.add_item(item):
                count += 1
        return count

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def count(self) -> int:
        return len(self._items)

    def search(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict] = None,
    ) -> List[KnowledgeSearchResult]:
        """Search by query. Uses vector search if embeddings are available,
        otherwise falls back to keyword token-overlap scoring. Never raises."""
        try:
            return _search(self._items, self._vectors, str(query or ""), int(top_k), filters)
        except Exception as exc:
            logger.debug("knowledge_store_search_failed: %s", exc)
            return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_embed(text: str) -> Optional[List[float]]:
    """Attempt to embed text using the shared embeddings module."""
    try:
        from app.ai.rag.embeddings import embed_text
        return embed_text(text)
    except Exception:
        return None


def _apply_filters(item: ExternalKnowledgeItem, filters: Optional[dict]) -> bool:
    """Return True when item passes all filters.

    Items whose field is None are market/style-agnostic and pass through.
    """
    if not filters:
        return True
    for key, value in filters.items():
        if value is None:
            continue
        item_value = getattr(item, key, None)
        if item_value is not None and item_value != value:
            return False
    return True


def _keyword_score(query: str, item: ExternalKnowledgeItem) -> float:
    """Score by fraction of query tokens found in item text + tags."""
    tokens = set(query.lower().split())
    if not tokens:
        return 0.0
    searchable = (item.text + " " + " ".join(item.tags)).lower()
    matches = sum(1 for t in tokens if t in searchable)
    base = matches / len(tokens)
    # Slight boost by item confidence so higher-confidence items rank higher
    return round(min(1.0, base * (0.5 + item.confidence * 0.5)), 4)


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def _build_result(item: ExternalKnowledgeItem, score: float) -> KnowledgeSearchResult:
    meta = {
        "source_type": item.source_type,
        "market": item.market,
        "platform": item.platform,
        "style": item.style,
        "topic": item.topic,
        "tags": list(item.tags),
        "confidence": item.confidence,
    }
    return KnowledgeSearchResult(
        id=item.id,
        score=round(float(score), 4),
        text=item.text,
        metadata=meta,
    )


def _search(
    items: List[ExternalKnowledgeItem],
    vectors: List[Optional[List[float]]],
    query: str,
    top_k: int,
    filters: Optional[dict],
) -> List[KnowledgeSearchResult]:
    if not items:
        return []

    top_k = max(1, top_k)

    # Attempt vector search
    query_vec = _try_embed(query)

    scored: List[tuple] = []

    if query_vec is not None:
        for i, (item, vec) in enumerate(zip(items, vectors)):
            if not _apply_filters(item, filters):
                continue
            score = _cosine(query_vec, vec) if vec is not None else 0.0
            scored.append((score, i))
    else:
        # Keyword fallback
        for i, item in enumerate(items):
            if not _apply_filters(item, filters):
                continue
            score = _keyword_score(query, item)
            scored.append((score, i))

    scored.sort(key=lambda t: t[0], reverse=True)

    return [
        _build_result(items[idx], score)
        for score, idx in scored[:top_k]
    ]
