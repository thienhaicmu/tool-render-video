"""
memory_store.py — Local in-memory render experience store.

Wraps LocalVectorStore with RenderMemory-typed API.
If embeddings are unavailable, add() silently returns False and
search_similar() returns [] — the caller continues normally.

No SQLite persistence in this phase — memory is session-scoped.

Public API:
    LocalMemoryStore
        .add_render_memory(memory: RenderMemory) -> bool
        .search_similar(text: str, top_k: int = 5) -> list[MemorySearchResult]
        .count() -> int
"""
from __future__ import annotations

from app.ai.rag.memory_schema import RenderMemory, MemorySearchResult
from app.ai.rag.embeddings import embed_text, is_embedding_available
from app.ai.rag.vector_store import LocalVectorStore


class LocalMemoryStore:
    """Session-scoped in-memory store for render experiences."""

    def __init__(self) -> None:
        self._store = LocalVectorStore()

    def add_render_memory(self, memory: RenderMemory) -> bool:
        """Embed and store a render memory. Returns False if embeddings unavailable."""
        if not is_embedding_available():
            return False
        try:
            vec = embed_text(memory.text)
            if vec is None:
                return False
            meta = {
                "market": memory.market,
                "mode": memory.mode,
                "duration": memory.duration,
                "score": memory.score,
                "subtitle_tone": memory.subtitle_tone,
                "camera_behavior": memory.camera_behavior,
                "status": memory.status,
            }
            meta.update(memory.metadata)
            self._store.add(memory.id, memory.text, vec, meta)
            return True
        except Exception:
            return False

    def search_similar(self, text: str, top_k: int = 5) -> list[MemorySearchResult]:
        """Return the top-k most similar stored memories. Returns [] on any failure."""
        if not is_embedding_available():
            return []
        try:
            vec = embed_text(text)
            if vec is None:
                return []
            raw = self._store.search(vec, top_k=top_k)
            return [
                MemorySearchResult(
                    id=r["id"],
                    text=r["text"],
                    score=float(r["score"]),
                    metadata=dict(r.get("metadata") or {}),
                )
                for r in raw
            ]
        except Exception:
            return []

    def count(self) -> int:
        return self._store.count()
