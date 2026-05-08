"""
vector_store.py — Local in-memory vector store.

Uses FAISS if available; falls back to pure-Python cosine similarity.
No SQLite persistence in this phase — memory only.

Public API:
    LocalVectorStore
        .add(id, text, vector, metadata=None) -> None
        .search(vector, top_k=5)             -> list[dict]
        .count()                             -> int

Search result format:
    {"id": str, "score": float, "text": str, "metadata": dict}
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from app.ai.dependencies import has_faiss


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
