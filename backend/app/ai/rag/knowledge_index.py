"""
knowledge_index.py — KnowledgeIndex: build, persist, and query the local knowledge base.

Uses FAISS via LocalVectorStore if available; falls back to in-memory filter+rank.

Public API:
    KnowledgeIndex
        .build(items)  -> None
        .save()        -> None
        .load()        -> bool
        .rebuild()     -> None
        .query(filters, top_k=10) -> list[dict]
        .is_ready()    -> bool

Result shape per item:
    {
        "id":           str,
        "type":         str,
        "rule":         str,
        "weight":       float,
        "match_score":  float,   # 0.0–1.0, based on matched filter count
        "match_reason": list[str],
        "render_usage": dict,
        "tags":         list[str],
    }
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default index path: backend/knowledge/index/faiss.index
# This file lives at: backend/app/ai/rag/knowledge_index.py
_DEFAULT_INDEX_PATH = Path(__file__).resolve().parents[3] / "knowledge" / "index" / "faiss.index"
_DEFAULT_PROCESSED_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "processed"


class KnowledgeIndex:
    """Local knowledge index with filter-based retrieval and optional FAISS support."""

    def __init__(
        self,
        index_path: Optional[Path] = None,
        processed_dir: Optional[Path] = None,
    ) -> None:
        self._index_path = Path(index_path) if index_path else _DEFAULT_INDEX_PATH
        self._processed_dir = Path(processed_dir) if processed_dir else _DEFAULT_PROCESSED_DIR
        self._items: list = []          # list[KnowledgeItem]
        self._vector_store: Any = None  # LocalVectorStore or None
        self._ready = False

    # -----------------------------------------------------------------------
    # Build
    # -----------------------------------------------------------------------

    def build(self, items: list) -> None:
        """Build the index from a list of KnowledgeItem objects.

        Attempts to build a FAISS vector index if embeddings are available.
        Falls back to in-memory list if not. Never raises.
        """
        self._items = list(items)
        self._vector_store = None
        self._ready = False

        if not self._items:
            logger.warning("knowledge_index.build: no items provided — index will be empty")
            self._ready = True
            return

        # Try to build vector store
        try:
            from app.ai.rag.vector_store import LocalVectorStore
            from app.ai.rag.embeddings import embed_text, is_embedding_available

            vs = LocalVectorStore()

            if is_embedding_available():
                for item in self._items:
                    text_repr = _item_to_text(item)
                    vec = embed_text(text_repr)
                    if vec is not None:
                        vs.add(
                            id=item.id,
                            text=text_repr,
                            vector=vec,
                            metadata={"id": item.id, "type": item.type},
                        )
                logger.info(
                    "knowledge_index.build: built FAISS/vector index with %d items "
                    "(embeddings=yes)",
                    vs.count(),
                )
            else:
                logger.info(
                    "knowledge_index.build: embeddings unavailable — "
                    "vector search disabled, using filter fallback",
                )

            self._vector_store = vs

        except Exception as exc:
            logger.warning("knowledge_index.build: vector store failed: %s — using filter fallback", exc)
            self._vector_store = None

        self._ready = True
        logger.info("knowledge_index.build: complete, %d items indexed", len(self._items))

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    def save(self) -> None:
        """Save the FAISS index and item metadata to disk. Never raises."""
        if not self._ready or not self._items:
            return

        # Save metadata (items) to JSON
        meta_path = self._index_path.with_suffix(".meta.json")
        try:
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_data = [_item_to_dict(item) for item in self._items]
            meta_path.write_text(json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info("knowledge_index.save: metadata saved to %s (%d items)", meta_path, len(meta_data))
        except Exception as exc:
            logger.warning("knowledge_index.save: metadata save failed: %s", exc)

        # Save FAISS index
        if self._vector_store is not None:
            try:
                saved = self._vector_store.save_index(str(self._index_path))
                if saved:
                    logger.info("knowledge_index.save: FAISS index saved to %s", self._index_path)
            except Exception as exc:
                logger.warning("knowledge_index.save: FAISS index save failed: %s", exc)

    def load(self) -> bool:
        """Load index from disk. Returns True if metadata loaded, False otherwise. Never raises."""
        meta_path = self._index_path.with_suffix(".meta.json")

        if not meta_path.exists():
            logger.info(
                "knowledge_index.load: metadata file not found at %s — will rebuild",
                meta_path,
            )
            return False

        try:
            raw_items = json.loads(meta_path.read_text(encoding="utf-8"))
            if not isinstance(raw_items, list):
                logger.warning("knowledge_index.load: metadata is not a list — will rebuild")
                return False

            from app.ai.rag.knowledge_schema import validate_knowledge_item
            items = []
            for raw in raw_items:
                item = validate_knowledge_item(raw)
                if item is not None:
                    items.append(item)

            if not items:
                logger.warning("knowledge_index.load: no valid items in metadata — will rebuild")
                return False

            self._items = items
            logger.info("knowledge_index.load: loaded %d items from metadata", len(self._items))

        except Exception as exc:
            logger.warning("knowledge_index.load: metadata load failed: %s — will rebuild", exc)
            return False

        # Try to load FAISS index
        try:
            from app.ai.rag.vector_store import LocalVectorStore
            from app.ai.rag.embeddings import embed_text, is_embedding_available

            vs = LocalVectorStore()

            if is_embedding_available():
                # Re-add entries so positions match FAISS index
                for item in self._items:
                    text_repr = _item_to_text(item)
                    vec = embed_text(text_repr)
                    if vec is not None:
                        vs.add(
                            id=item.id,
                            text=text_repr,
                            vector=vec,
                            metadata={"id": item.id, "type": item.type},
                        )
                # Load the saved index geometry
                loaded = vs.load_index(str(self._index_path))
                if loaded:
                    logger.info("knowledge_index.load: FAISS index loaded from %s", self._index_path)
                else:
                    logger.info("knowledge_index.load: FAISS index not found — fallback to cosine/filter")

            self._vector_store = vs

        except Exception as exc:
            logger.warning("knowledge_index.load: vector store load failed: %s — using filter fallback", exc)
            self._vector_store = None

        self._ready = True
        return True

    def rebuild(self) -> None:
        """Load knowledge items from processed_dir, build index, and save. Never raises."""
        try:
            from app.ai.rag.knowledge_loader import load_knowledge_items
            items = load_knowledge_items(self._processed_dir)
            if not items:
                logger.warning(
                    "knowledge_index.rebuild: no items loaded from %s — "
                    "index will be empty (renders proceed with defaults)",
                    self._processed_dir,
                )
            self.build(items)
            self.save()
        except Exception as exc:
            logger.warning("knowledge_index.rebuild: failed: %s", exc)

    # -----------------------------------------------------------------------
    # Query
    # -----------------------------------------------------------------------

    def query(self, filters: Optional[dict], top_k: int = 10) -> list:
        """Filter-based retrieval with optional FAISS ranking.

        Filter keys (all optional):
            platform      str   — item.platform must contain this value
            niche         str   — item.niche must contain this value
            style         str   — item.style must contain this value
            duration      float — must be within item.duration_range [min, max]
            aspect_ratio  str   — item.aspect_ratio must contain this value
            subtitle_style str  — item.subtitle_style must contain this value
            target_goal   str   — item.target_goal or item.tags must contain this value

        Returns list of result dicts, sorted by weight desc + match_score desc.
        Returns [] when no items match. Never raises.
        """
        if not self._ready or not self._items:
            return []

        filters = filters or {}

        results = []
        for item in self._items:
            matched, reasons = _match_item(item, filters)
            match_score = len(reasons) / max(len(_active_filter_keys(filters)), 1)
            results.append({
                "item": item,
                "matched": matched,
                "match_score": match_score,
                "match_reason": reasons,
            })

        # Keep only matched items (if any filters active)
        active_keys = _active_filter_keys(filters)
        if active_keys:
            results = [r for r in results if r["matched"]]

        if not results:
            return []

        # Sort by weight desc, then match_score desc
        results.sort(key=lambda r: (r["item"].weight, r["match_score"]), reverse=True)

        # Apply top_k
        results = results[:top_k]

        # Shape output
        return [_format_result(r) for r in results]

    # -----------------------------------------------------------------------
    # Ready check
    # -----------------------------------------------------------------------

    def is_ready(self) -> bool:
        """Return True if index is built and has items."""
        return self._ready


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _item_to_text(item: Any) -> str:
    """Build a searchable text representation of a KnowledgeItem."""
    parts = [
        item.type,
        " ".join(item.platform),
        " ".join(item.niche),
        " ".join(item.style),
        " ".join(item.tags),
        item.rule,
    ]
    return " ".join(p for p in parts if p)


def _item_to_dict(item: Any) -> dict:
    """Convert a KnowledgeItem to a plain dict for JSON serialisation."""
    return {
        "id": item.id,
        "type": item.type,
        "platform": item.platform,
        "niche": item.niche,
        "style": item.style,
        "duration_range": item.duration_range,
        "rule": item.rule,
        "render_usage": item.render_usage,
        "weight": item.weight,
        "tags": item.tags,
        "aspect_ratio": item.aspect_ratio,
        "subtitle_style": item.subtitle_style,
        "target_goal": item.target_goal,
        "examples": item.examples,
        "source": item.source,
        "notes": item.notes,
    }


def _active_filter_keys(filters: dict) -> list:
    """Return filter keys that have a non-None value."""
    return [k for k, v in filters.items() if v is not None]


def _match_item(item: Any, filters: dict) -> tuple:
    """Return (matched: bool, reasons: list[str]).

    matched = True if every active filter matches the item.
    """
    reasons: list[str] = []

    for key, value in filters.items():
        if value is None:
            continue

        value_lower = str(value).lower()

        if key == "platform":
            if value_lower in [p.lower() for p in item.platform]:
                reasons.append(f"platform:{value_lower}")
            else:
                return False, []

        elif key == "niche":
            if value_lower in [n.lower() for n in item.niche]:
                reasons.append(f"niche:{value_lower}")
            else:
                return False, []

        elif key == "style":
            if value_lower in [s.lower() for s in item.style]:
                reasons.append(f"style:{value_lower}")
            else:
                return False, []

        elif key == "duration":
            try:
                dur = float(value)
                dr = item.duration_range
                if dr[0] <= dur <= dr[1]:
                    reasons.append(f"duration:{dur}")
                else:
                    return False, []
            except (TypeError, ValueError, IndexError):
                pass

        elif key == "aspect_ratio":
            item_ar = [x.lower() for x in (item.aspect_ratio or [])]
            if value_lower in item_ar:
                reasons.append(f"aspect_ratio:{value_lower}")
            else:
                return False, []

        elif key == "subtitle_style":
            item_ss = [x.lower() for x in (item.subtitle_style or [])]
            if value_lower in item_ss:
                reasons.append(f"subtitle_style:{value_lower}")
            else:
                return False, []

        elif key == "target_goal":
            item_tg = [x.lower() for x in (item.target_goal or [])]
            item_tags_lower = [t.lower() for t in item.tags]
            if value_lower in item_tg or value_lower in item_tags_lower:
                reasons.append(f"target_goal:{value_lower}")
            else:
                return False, []

    return True, reasons


def _format_result(r: dict) -> dict:
    item = r["item"]
    return {
        "id": item.id,
        "type": item.type,
        "rule": item.rule,
        "weight": item.weight,
        "match_score": r["match_score"],
        "match_reason": r["match_reason"],
        "render_usage": dict(item.render_usage),
        "tags": list(item.tags),
    }
