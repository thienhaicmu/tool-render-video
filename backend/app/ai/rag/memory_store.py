"""
memory_store.py — Local render experience store with optional SQLite persistence.

Phase 3 upgrade: integrates SQLiteMemoryStore for cross-session memory.
Falls back to in-memory-only if SQLite is unavailable.
If embeddings are unavailable, add() still writes to SQLite (text-only)
and search_recent() returns recent memories without semantic scoring.

Public API:
    LocalMemoryStore
        .initialize_with_sqlite(db_path=None) -> bool
        .add_render_memory(memory: RenderMemory) -> bool
        .search_similar(text: str, top_k: int = 5) -> list[MemorySearchResult]
        .search_recent(limit: int = 5) -> list[MemorySearchResult]
        .count() -> int

    initialize_memory_system(db_path=None) -> LocalMemoryStore
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from app.ai.rag.memory_schema import RenderMemory, MemorySearchResult
from app.ai.rag.embeddings import embed_text, is_embedding_available
from app.ai.rag.vector_store import LocalVectorStore


class LocalMemoryStore:
    """Render experience store backed by in-memory vectors + optional SQLite."""

    def __init__(self) -> None:
        self._store = LocalVectorStore()
        self._sqlite: Optional[object] = None   # SQLiteMemoryStore | None
        self._hydrated = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def initialize_with_sqlite(self, db_path: Optional[Path] = None) -> bool:
        """Attach SQLite backing, create tables, and hydrate in-memory vectors.

        Returns True if SQLite initialized successfully, False otherwise.
        The in-memory store is still usable when this returns False.
        """
        try:
            from app.ai.rag.sqlite_store import SQLiteMemoryStore
            sq = SQLiteMemoryStore(db_path=db_path)
            if not sq.initialize():
                return False
            self._sqlite = sq
            self._hydrate_from_sqlite()
            return True
        except Exception:
            return False

    def _hydrate_from_sqlite(self) -> None:
        """Load stored vectors from SQLite into the in-memory LocalVectorStore."""
        if self._sqlite is None or self._hydrated:
            return
        try:
            entries = self._sqlite.load_vectors()
            for e in entries:
                try:
                    self._store.add(
                        e["id"],
                        e["text"],
                        e["vector"],
                        e.get("metadata") or {},
                    )
                except Exception:
                    continue
            self._hydrated = True
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_render_memory(self, memory: RenderMemory) -> bool:
        """Embed and store a render memory.

        - Writes to SQLite always (when available), with or without embeddings.
        - Writes to in-memory vector store only when embeddings are available.
        - Returns True if at least one store accepted the record.
        """
        saved_sqlite = False
        saved_vector = False

        # --- SQLite (text + optional vector) ---
        if self._sqlite is not None:
            try:
                vec = embed_text(memory.text) if is_embedding_available() else None
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
                saved_sqlite = self._sqlite.add_memory(memory, vector=vec)
            except Exception:
                pass

        # --- In-memory vector store ---
        if is_embedding_available():
            try:
                vec = embed_text(memory.text)
                if vec is not None:
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
                    saved_vector = True
            except Exception:
                pass

        return saved_sqlite or saved_vector

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def search_similar(self, text: str, top_k: int = 5) -> list[MemorySearchResult]:
        """Return the top-k most similar stored memories via semantic search.

        Returns [] when embeddings are unavailable (use search_recent instead).
        """
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

    def search_recent(self, limit: int = 5) -> list[MemorySearchResult]:
        """Return recent memories from SQLite without semantic scoring.

        Used as text-only fallback when embeddings are unavailable.
        Score is fixed at 0.5 (neutral confidence).
        Returns [] if SQLite unavailable or empty.
        """
        if self._sqlite is None:
            return []
        try:
            memories = self._sqlite.search_memories(limit=limit)
            return [
                MemorySearchResult(
                    id=m.id,
                    text=m.text,
                    score=0.5,
                    metadata={
                        "market": m.market,
                        "mode": m.mode,
                        "status": m.status,
                        "score": m.score,
                    },
                )
                for m in memories
            ]
        except Exception:
            return []

    def count(self) -> int:
        """Total count: prefers SQLite count (persistent), falls back to in-memory."""
        if self._sqlite is not None:
            try:
                n = self._sqlite.count()
                if n > 0:
                    return n
            except Exception:
                pass
        return self._store.count()


# ---------------------------------------------------------------------------
# Module-level factory
# ---------------------------------------------------------------------------

def initialize_memory_system(db_path: Optional[Path] = None) -> LocalMemoryStore:
    """Create a LocalMemoryStore, attach SQLite, and hydrate in-memory vectors.

    Always returns a usable LocalMemoryStore regardless of SQLite availability.
    """
    store = LocalMemoryStore()
    store.initialize_with_sqlite(db_path=db_path)
    return store
