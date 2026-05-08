"""
retriever.py — Local RAG context retrieval for the AI Director.

Phase 3 upgrade: supports SQLite-backed retrieval and text-only fallback
when embeddings are unavailable but historical memories exist.

Never raises. Returns a stable dict contract.

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
    Phase 3: when embeddings are unavailable but the store has SQLite-backed
    records, returns recent memories as text-only results with a
    "text_only_fallback" warning instead of returning nothing.
    """
    # No memory store provided.
    if memory_store is None:
        if not is_embedding_available():
            return {
                "enabled": False,
                "available": False,
                "results": [],
                "warnings": ["embeddings_unavailable"],
            }
        return {
            "enabled": True,
            "available": False,
            "results": [],
            "warnings": ["no_memory_store"],
        }

    # Embeddings unavailable — try text-only fallback from SQLite.
    if not is_embedding_available():
        return _text_only_fallback(memory_store)

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

    # Semantic search.
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


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _text_only_fallback(memory_store: Any) -> dict:
    """Return recent memories without semantic search when embeddings unavailable."""
    try:
        if not callable(getattr(memory_store, "search_recent", None)):
            return {
                "enabled": False,
                "available": False,
                "results": [],
                "warnings": ["embeddings_unavailable"],
            }
        recent = memory_store.search_recent(limit=5)
        if not recent:
            return {
                "enabled": False,
                "available": False,
                "results": [],
                "warnings": ["embeddings_unavailable"],
            }
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
                for r in recent
            ],
            "warnings": ["text_only_fallback"],
        }
    except Exception:
        return {
            "enabled": False,
            "available": False,
            "results": [],
            "warnings": ["embeddings_unavailable"],
        }
