"""
embeddings.py — Optional sentence-transformers embedding layer.

No heavy import at module level. Model is loaded lazily on first call.
All functions return None if sentence-transformers is unavailable or
model load fails — they never raise.

Public API:
    embed_text(text)   -> list[float] | None
    embed_texts(texts) -> list[list[float]] | None
    is_embedding_available() -> bool
"""
from __future__ import annotations

from typing import Optional

from app.ai.dependencies import has_sentence_transformers

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_model = None   # SentenceTransformer instance, or False on failure


def _load_model() -> bool:
    global _model
    if _model is not None:
        return _model is not False

    if not has_sentence_transformers():
        _model = False
        return False

    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        _model = SentenceTransformer(_MODEL_NAME)
        return True
    except Exception:
        _model = False
        return False


def is_embedding_available() -> bool:
    return _load_model()


def embed_text(text: str) -> Optional[list[float]]:
    """Embed a single string. Returns None if unavailable."""
    if not _load_model():
        return None
    try:
        vec = _model.encode([str(text or "")], convert_to_numpy=False)[0]
        return list(float(v) for v in vec)
    except Exception:
        return None


def embed_texts(texts: list[str]) -> Optional[list[list[float]]]:
    """Embed a list of strings. Returns None if unavailable."""
    if not _load_model():
        return None
    try:
        vecs = _model.encode([str(t or "") for t in texts], convert_to_numpy=False)
        return [list(float(v) for v in row) for row in vecs]
    except Exception:
        return None
