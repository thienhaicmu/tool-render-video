"""
test_ai_knowledge_index.py — Tests for KnowledgeIndex and knowledge_warmup.

Covers:
- Build from KnowledgeItem list
- Save/load metadata persistence
- Fallback retrieval without FAISS
- is_ready() state transitions
- Corrupt/missing index graceful handling
- warmup_knowledge_index() and get_knowledge_index() singleton behaviour
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_item(item_id: str, platform: str = "tiktok", weight: float = 0.8) -> "KnowledgeItem":
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = {
        "id": item_id,
        "type": "hook_pattern",
        "platform": [platform],
        "niche": ["education"],
        "style": ["viral"],
        "duration_range": [15, 60],
        "rule": f"Rule for {item_id}",
        "render_usage": {"hook": True, "pacing": "medium_fast"},
        "weight": weight,
        "tags": ["hook", "retention"],
    }
    return validate_knowledge_item(raw)


# ---------------------------------------------------------------------------
# 1. Builds index from KnowledgeItem list
# ---------------------------------------------------------------------------

def test_build_from_items():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    items = [_make_item("a"), _make_item("b"), _make_item("c")]
    idx = KnowledgeIndex()
    idx.build(items)
    assert idx.is_ready()
    assert len(idx._items) == 3


def test_build_empty_list():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    idx = KnowledgeIndex()
    idx.build([])
    assert idx.is_ready()
    assert idx._items == []


# ---------------------------------------------------------------------------
# 2. is_ready() returns False when not built
# ---------------------------------------------------------------------------

def test_is_ready_false_before_build():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    idx = KnowledgeIndex()
    assert not idx.is_ready()


# ---------------------------------------------------------------------------
# 3. Save and load metadata
# ---------------------------------------------------------------------------

def test_save_and_load_metadata(tmp_path):
    from app.ai.rag.knowledge_index import KnowledgeIndex

    index_path = tmp_path / "faiss.index"
    items = [_make_item("x1"), _make_item("x2")]

    # Build and save
    idx = KnowledgeIndex(index_path=index_path)
    idx.build(items)
    idx.save()

    # Verify metadata file exists
    meta_path = index_path.with_suffix(".meta.json")
    assert meta_path.exists()
    saved_data = json.loads(meta_path.read_text())
    assert len(saved_data) == 2
    saved_ids = {d["id"] for d in saved_data}
    assert "x1" in saved_ids
    assert "x2" in saved_ids


def test_load_returns_true_when_metadata_exists(tmp_path):
    from app.ai.rag.knowledge_index import KnowledgeIndex

    index_path = tmp_path / "faiss.index"
    items = [_make_item("load_001")]

    # Build and save
    idx_save = KnowledgeIndex(index_path=index_path)
    idx_save.build(items)
    idx_save.save()

    # Load in fresh instance
    idx_load = KnowledgeIndex(index_path=index_path)
    result = idx_load.load()
    assert result is True
    assert idx_load.is_ready()
    assert len(idx_load._items) == 1
    assert idx_load._items[0].id == "load_001"


def test_load_returns_false_when_no_metadata(tmp_path):
    from app.ai.rag.knowledge_index import KnowledgeIndex

    index_path = tmp_path / "nonexistent" / "faiss.index"
    idx = KnowledgeIndex(index_path=index_path)
    result = idx.load()
    assert result is False
    assert not idx.is_ready()


# ---------------------------------------------------------------------------
# 4. Corrupt/missing index handled gracefully
# ---------------------------------------------------------------------------

def test_corrupt_metadata_returns_false(tmp_path):
    from app.ai.rag.knowledge_index import KnowledgeIndex

    index_path = tmp_path / "faiss.index"
    meta_path = index_path.with_suffix(".meta.json")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text("{ this is not valid json }", encoding="utf-8")

    idx = KnowledgeIndex(index_path=index_path)
    result = idx.load()
    assert result is False


def test_empty_metadata_returns_false(tmp_path):
    from app.ai.rag.knowledge_index import KnowledgeIndex

    index_path = tmp_path / "faiss.index"
    meta_path = index_path.with_suffix(".meta.json")
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text("[]", encoding="utf-8")

    idx = KnowledgeIndex(index_path=index_path)
    result = idx.load()
    assert result is False


# ---------------------------------------------------------------------------
# 5. Fallback retrieval works without FAISS
# ---------------------------------------------------------------------------

def test_query_fallback_returns_results():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    items = [
        _make_item("a", platform="tiktok", weight=0.9),
        _make_item("b", platform="reels", weight=0.5),
        _make_item("c", platform="tiktok", weight=0.7),
    ]
    idx = KnowledgeIndex()
    idx.build(items)

    results = idx.query({"platform": "tiktok"})
    assert len(results) == 2
    assert all(r["id"] in {"a", "c"} for r in results)


def test_query_returns_empty_when_no_match():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    items = [_make_item("a", platform="tiktok")]
    idx = KnowledgeIndex()
    idx.build(items)

    results = idx.query({"platform": "youtube"})
    assert results == []


def test_query_empty_filters_returns_all_ranked_by_weight():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    items = [
        _make_item("low", platform="tiktok", weight=0.3),
        _make_item("high", platform="tiktok", weight=0.9),
        _make_item("mid", platform="tiktok", weight=0.6),
    ]
    idx = KnowledgeIndex()
    idx.build(items)

    results = idx.query({})
    assert len(results) == 3
    assert results[0]["id"] == "high"
    assert results[1]["id"] == "mid"
    assert results[2]["id"] == "low"


def test_query_none_filters_returns_all():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    items = [_make_item("a"), _make_item("b")]
    idx = KnowledgeIndex()
    idx.build(items)

    results = idx.query(None)
    assert len(results) == 2


def test_query_not_ready_returns_empty():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    idx = KnowledgeIndex()
    results = idx.query({"platform": "tiktok"})
    assert results == []


# ---------------------------------------------------------------------------
# 6. Metadata maps results back to knowledge item IDs
# ---------------------------------------------------------------------------

def test_result_shape():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    items = [_make_item("shape_test")]
    idx = KnowledgeIndex()
    idx.build(items)

    results = idx.query({})
    assert len(results) == 1
    r = results[0]
    assert "id" in r
    assert "type" in r
    assert "rule" in r
    assert "weight" in r
    assert "match_score" in r
    assert "match_reason" in r
    assert "render_usage" in r
    assert "tags" in r
    assert isinstance(r["tags"], list)
    assert isinstance(r["render_usage"], dict)


# ---------------------------------------------------------------------------
# 7. Rebuild from processed_dir
# ---------------------------------------------------------------------------

def test_rebuild_from_processed_dir(tmp_path):
    from app.ai.rag.knowledge_index import KnowledgeIndex
    import json as _json

    processed_dir = tmp_path / "processed"
    processed_dir.mkdir()
    index_path = tmp_path / "index" / "faiss.index"

    raw = {
        "id": "rebuilt_001",
        "type": "pacing_rule",
        "platform": ["tiktok"],
        "niche": ["education"],
        "style": ["viral"],
        "duration_range": [15, 60],
        "rule": "Rebuilt item rule",
        "render_usage": {},
        "weight": 0.7,
        "tags": ["pacing"],
    }
    (processed_dir / "rules.jsonl").write_text(_json.dumps(raw), encoding="utf-8")

    idx = KnowledgeIndex(index_path=index_path, processed_dir=processed_dir)
    idx.rebuild()

    assert idx.is_ready()
    assert len(idx._items) == 1
    assert idx._items[0].id == "rebuilt_001"


def test_rebuild_with_empty_dir_does_not_crash(tmp_path):
    from app.ai.rag.knowledge_index import KnowledgeIndex

    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    idx = KnowledgeIndex(processed_dir=empty_dir)
    idx.rebuild()  # must not raise
    assert idx.is_ready()


# ---------------------------------------------------------------------------
# 8. warmup_knowledge_index never raises
# ---------------------------------------------------------------------------

def test_warmup_does_not_raise():
    from app.ai.rag.knowledge_warmup import warmup_knowledge_index
    # Must not raise regardless of what's on disk
    warmup_knowledge_index()


def test_warmup_with_missing_knowledge(tmp_path, monkeypatch):
    from app.ai.rag import knowledge_warmup as _warmup_mod
    from app.ai.rag.knowledge_index import KnowledgeIndex

    # Reset singleton for isolation
    monkeypatch.setattr(_warmup_mod, "_knowledge_index_singleton", None)

    def _empty_index(*a, **kw):
        i = KnowledgeIndex(processed_dir=tmp_path / "nonexistent")
        return i

    monkeypatch.setattr(_warmup_mod, "KnowledgeIndex", _empty_index)

    # Must not raise
    _warmup_mod.warmup_knowledge_index()


# ---------------------------------------------------------------------------
# 9. get_knowledge_index returns same singleton on repeated calls
# ---------------------------------------------------------------------------

def test_get_knowledge_index_singleton(monkeypatch):
    from app.ai.rag import knowledge_warmup as _warmup_mod

    # Reset singleton
    monkeypatch.setattr(_warmup_mod, "_knowledge_index_singleton", None)

    idx1 = _warmup_mod.get_knowledge_index()
    idx2 = _warmup_mod.get_knowledge_index()

    assert idx1 is idx2


# ---------------------------------------------------------------------------
# 10. top_k limits results
# ---------------------------------------------------------------------------

def test_top_k_limits_results():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    items = [_make_item(f"item_{i}", weight=float(i) / 10) for i in range(1, 11)]
    idx = KnowledgeIndex()
    idx.build(items)

    results = idx.query({}, top_k=3)
    assert len(results) == 3
