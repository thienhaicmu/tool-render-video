"""
knowledge_retriever.py — External knowledge retrieval facade. Phase 15.

Wraps LocalKnowledgeStore search behind a fallback-safe interface.
The knowledge store is expected in context["knowledge_store"]; if absent
the function returns available=False without raising.

Public API:
    retrieve_external_knowledge(query, context=None, top_k=5) -> dict

Return shape:
    {
        "available": bool,
        "results":   list[dict],   # KnowledgeSearchResult.to_dict()
        "warnings":  list[str],
    }
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("app.ai.knowledge.retriever")


def retrieve_external_knowledge(
    query: str,
    context: Optional[dict] = None,
    top_k: int = 5,
) -> dict:
    """Retrieve relevant external knowledge items. Never raises.

    Args:
        query:   Free-text search query (mode + market + transcript excerpt).
        context: Dict that may contain:
                   knowledge_store — LocalKnowledgeStore instance
                   market          — filter string or None
                   style           — filter string or None
        top_k:   Maximum number of results.

    Returns:
        {"available": bool, "results": [...], "warnings": [...]}
    """
    try:
        return _retrieve(str(query or ""), context or {}, int(top_k))
    except Exception as exc:
        logger.debug("knowledge_retriever_failed: %s", exc)
        return {
            "available": False,
            "results": [],
            "warnings": [f"retriever_error:{type(exc).__name__}"],
        }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _retrieve(query: str, context: dict, top_k: int) -> dict:
    store = context.get("knowledge_store")

    if store is None:
        return {
            "available": False,
            "results": [],
            "warnings": ["no_knowledge_store"],
        }

    if not hasattr(store, "count") or store.count() == 0:
        return {
            "available": False,
            "results": [],
            "warnings": ["knowledge_store_empty"],
        }

    # Build field filters from context
    filters: dict = {}
    if context.get("market"):
        filters["market"] = context["market"]
    if context.get("style"):
        filters["style"] = context["style"]

    results = store.search(query, top_k=top_k, filters=filters or None)

    if not results:
        logger.debug("ai_external_knowledge_skipped: no results for query")
        return {
            "available": True,
            "results": [],
            "warnings": [],
        }

    result_dicts = [
        r.to_dict() if hasattr(r, "to_dict") else dict(r)
        for r in results
    ]

    logger.info(
        "ai_external_knowledge_matched count=%d top_score=%.3f",
        len(result_dicts),
        result_dicts[0].get("score", 0.0) if result_dicts else 0.0,
    )

    return {
        "available": True,
        "results": result_dicts,
        "warnings": [],
    }
