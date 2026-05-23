"""
vector_store.py — Local in-memory vector store with optional FAISS persistence.

Uses FAISS if available; falls back to pure-Python cosine similarity.

FAISS persistence:
    - save_index(path)  — serialize the FAISS index to disk (.index file)
    - load_index(path)  — deserialize from disk; requires entry count to match
    The canonical index path is backend/knowledge/index/faiss.index.
    Index rebuild from knowledge/*.jsonl files is handled externally (knowledge_loader).

NOTE on naming:
    memory_store  (app/ai/rag/memory_store.py) = RAG infrastructure for render
                  experience memory (per-job history, semantic search of past renders).
    knowledge/    (backend/knowledge/) = desired usage = filter-based platform and
                  video-quality knowledge retrieval. These are separate concerns.
    LocalVectorStore here is shared infrastructure used by both.

Public API:
    LocalVectorStore
        .add(id, text, vector, metadata=None) -> None
        .search(vector, top_k=5)             -> list[dict]
        .count()                             -> int
        .save_index(path)                    -> bool
        .load_index(path)                    -> bool

Search result format:
    {"id": str, "score": float, "text": str, "metadata": dict}
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.ai.dependencies import has_faiss

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal record
# ---------------------------------------------------------------------------

@dataclass
class _Entry:
    id: str
    text: str
    vector: list[float]
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cosine fallback
# ---------------------------------------------------------------------------

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class LocalVectorStore:
    """In-memory vector store backed by FAISS or Python cosine fallback."""

    def __init__(self) -> None:
        self._entries: list[_Entry] = []
        self._faiss_index: Any = None
        self._dim: Optional[int] = None
        self._use_faiss = has_faiss()

    # -- mutation --

    def add(
        self,
        id: str,
        text: str,
        vector: list[float],
        metadata: Optional[dict] = None,
    ) -> None:
        entry = _Entry(
            id=id,
            text=str(text),
            vector=list(float(v) for v in vector),
            metadata=dict(metadata or {}),
        )
        self._entries.append(entry)

        if self._use_faiss:
            self._faiss_add(entry.vector)

    def _faiss_add(self, vector: list[float]) -> None:
        try:
            import faiss  # type: ignore
            import numpy as np

            vec = np.array([vector], dtype="float32")
            dim = vec.shape[1]

            if self._faiss_index is None:
                self._dim = dim
                self._faiss_index = faiss.IndexFlatIP(dim)
                faiss.normalize_L2(vec)
            else:
                faiss.normalize_L2(vec)

            self._faiss_index.add(vec)
        except Exception:
            # FAISS call failed — disable and keep entries for fallback
            self._use_faiss = False
            self._faiss_index = None

    # -- query --

    def search(self, vector: list[float], top_k: int = 5) -> list[dict]:
        if not self._entries:
            return []

        if self._use_faiss and self._faiss_index is not None:
            return self._faiss_search(vector, top_k)

        return self._cosine_search(vector, top_k)

    def _faiss_search(self, vector: list[float], top_k: int) -> list[dict]:
        try:
            import faiss  # type: ignore
            import numpy as np

            vec = np.array([vector], dtype="float32")
            faiss.normalize_L2(vec)
            k = min(top_k, len(self._entries))
            scores, indices = self._faiss_index.search(vec, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._entries):
                    continue
                e = self._entries[idx]
                results.append(
                    {"id": e.id, "score": float(score), "text": e.text, "metadata": e.metadata}
                )
            return results
        except Exception:
            self._use_faiss = False
            return self._cosine_search(vector, top_k)

    def _cosine_search(self, vector: list[float], top_k: int) -> list[dict]:
        scored = [
            (e, _cosine(vector, e.vector)) for e in self._entries
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            {"id": e.id, "score": score, "text": e.text, "metadata": e.metadata}
            for e, score in scored[:top_k]
        ]

    # -- metadata --

    # -- persistence --

    def save_index(self, path: "str | Path") -> bool:
        """Serialize the FAISS index to disk.

        Returns True on success, False on any failure (e.g. FAISS unavailable,
        index empty, I/O error). Never raises.

        Only the FAISS index geometry is saved — entry metadata (id, text,
        metadata) must be re-added via add() before save_index() for a
        meaningful reload. Callers are responsible for persisting entry data
        separately (e.g. via SQLiteMemoryStore or knowledge/*.jsonl files).
        """
        if not self._use_faiss or self._faiss_index is None:
            logger.debug("vector_store.save_index: skipped (faiss not active or index empty)")
            return False
        try:
            import faiss  # type: ignore
            dest = Path(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            faiss.write_index(self._faiss_index, str(dest))
            logger.info("vector_store.save_index: saved %d vectors to %s", len(self._entries), dest)
            return True
        except Exception as exc:
            logger.warning("vector_store.save_index: failed: %s", exc)
            return False

    def load_index(self, path: "str | Path") -> bool:
        """Deserialize a FAISS index from disk.

        Returns True if the index was loaded successfully, False otherwise.
        Never raises. The caller must have already added the same entries via
        add() (in the same order) so that index positions map to _entries.

        If the entry count does not match the loaded index size, the load is
        rejected to prevent position mismatches and search corruption.
        """
        src = Path(path)
        if not src.exists():
            logger.debug("vector_store.load_index: file not found: %s", src)
            return False
        if not has_faiss():
            logger.debug("vector_store.load_index: faiss not available, skipping")
            return False
        try:
            import faiss  # type: ignore
            loaded = faiss.read_index(str(src))
            ntotal = int(loaded.ntotal)
            if ntotal != len(self._entries):
                logger.warning(
                    "vector_store.load_index: entry count mismatch "
                    "(index=%d entries=%d) — rejecting load, will rebuild",
                    ntotal, len(self._entries),
                )
                return False
            self._faiss_index = loaded
            self._use_faiss = True
            if ntotal > 0:
                # Infer dimension from index for health checks
                try:
                    self._dim = loaded.d
                except Exception:
                    pass
            logger.info("vector_store.load_index: loaded %d vectors from %s", ntotal, src)
            return True
        except Exception as exc:
            logger.warning("vector_store.load_index: failed: %s", exc)
            return False

    def count(self) -> int:
        return len(self._entries)

    def health(self) -> dict:
        """Return compact health snapshot. Never raises."""
        try:
            warnings: list[str] = []
            count = len(self._entries)
            faiss_ok = has_faiss()
            fallback = not self._use_faiss
            if self._use_faiss and self._faiss_index is None and count > 0:
                warnings.append("faiss_index_not_built")
            return {
                "count": count,
                "faiss_available": faiss_ok,
                "fallback_mode": fallback,
                "warnings": warnings,
            }
        except Exception:
            return {
                "count": 0,
                "faiss_available": False,
                "fallback_mode": True,
                "warnings": ["health_check_failed"],
            }
