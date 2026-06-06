"""
diagnostics.py — AI runtime diagnostics for packaging and observability.

Returns a compact, read-only snapshot of AI system health.
Never raises. Never loads models. Never triggers embeddings.
Uses dependency detectors only — no heavy imports at call time.

Public API:
    get_ai_runtime_diagnostics() -> dict
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.diagnostics")


def get_ai_runtime_diagnostics() -> dict:
    """Return compact AI runtime diagnostics.

    Safe to call from any context — startup, health checks, packaging tests.
    Never raises. Never loads sentence-transformers, faiss, or any heavy lib.
    """
    try:
        return _collect()
    except Exception as exc:
        logger.debug("ai_diagnostics_collection_failed: %s", exc)
        return {
            "dependencies": {},
            "startup_safe": True,
            "embedding_available": False,
            "vector_store": {"faiss_available": False, "fallback_mode": True},
            "memory": {
                "sqlite_available": False,
                "count": None,
                "db_path": None,
                "warnings": ["diagnostics_collection_error"],
            },
            "warnings": ["diagnostics_collection_error"],
        }


def _collect() -> dict:
    from app.features.render.ai.dependencies import get_ai_dependency_status, has_sentence_transformers, has_faiss

    dep_status = get_ai_dependency_status()
    warnings: list[str] = []

    # Check embedding library presence — NOT model load
    embedding_available = has_sentence_transformers()

    # Vector store: FAISS or cosine fallback
    faiss_ok = has_faiss()
    vs_status = {
        "faiss_available": faiss_ok,
        "fallback_mode": not faiss_ok,
    }

    mem_status = _memory_diagnostics(warnings)

    return {
        "dependencies": dep_status,
        "startup_safe": True,
        "embedding_available": embedding_available,
        "vector_store": vs_status,
        "memory": mem_status,
        "warnings": warnings,
    }


def _memory_diagnostics(warnings: list[str]) -> dict:
    """Return static "not available" status — RAG memory store removed in Phase G."""
    return {
        "sqlite_available": False,
        "count": None,
        "db_path": None,
        "warnings": ["memory_store_retired"],
    }
