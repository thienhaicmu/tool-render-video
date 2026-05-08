"""
retriever.py — Local RAG context retrieval for the AI Director.

Wraps LocalMemoryStore with a stable return schema that the director
can attach directly to AIEditPlan.memory_context. Never raises.

Public API:
    retrieve_ai_context(query, memory_store=None, top_k=5) -> dict

Return format:
    {
        "enabled":   bool,
        "available": bool,
        "results":   list[dict],   # {"id", "text", "score", "metadata"}
        "warnings":  list[str],
    }
"""
from __future__ import annotations

from typing import Any, Optional

from app.ai.rag.embeddings import is_embedding_available


def retrieve_ai_context(
    query: str,
    memory_store: Optional[Any] = None,
    top_k: int = 5,
) -> dict:
    """Retrieve similar render memories for the given query text.

    Returns a safe dict regardless of library availability or errors.
    The director attaches this directly to AIEditPlan.memory_context.
    """
    # Fast path: embeddings not installed.
    if not is_embedding_available():
        return {
            "enabled": False,
            "available": False,
            "results": [],
            "warnings": ["embeddings_unavailable"],
        }

    # No memory store provided (nothing stored yet in this session).
    if memory_store is None:
        return {
            "enabled": True,
            "available": False,
            "results": [],
            "warnings": ["no_memory_store"],
        }

    # Empty store — valid but no results.
    try:
        if memory_store.count() == 0:
            return {
                "enabled": True,
                "available": True,
                "results": [],
                "warnings": ["memory_store_empty"],
            }
    except Exception:
        pass

    try:
        results = memory_store.search_similar(str(query or ""), top_k=top_k)
        return {
            "enabled": True,
            "available": True,
            "results": [
                {
                    "id": r.id,
                    "text": r.text,
                    "score": r.score,
                    "metadata": r.metadata,
                }
                for r in results
            ],
            "warnings": [],
        }
    except Exception as exc:
        return {
            "enabled": True,
            "available": False,
            "results": [],
            "warnings": [f"retrieval_failed: {type(exc).__name__}"],
        }
