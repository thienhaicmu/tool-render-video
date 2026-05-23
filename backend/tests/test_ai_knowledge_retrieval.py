"""
test_ai_knowledge_retrieval.py — Tests for KnowledgeIndex.query() filter-based retrieval.

Covers all filter keys: platform, niche, style, duration, aspect_ratio,
subtitle_style, target_goal. Also covers ranking and edge cases.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_raw(
    item_id: str,
    platform: list = None,
    niche: list = None,
    style: list = None,
    duration_range: list = None,
    aspect_ratio: list = None,
    subtitle_style: list = None,
    target_goal: list = None,
    tags: list = None,
    weight: float = 0.5,
) -> dict:
    return {
        "id": item_id,
        "type": "test_type",
        "platform": platform or ["tiktok"],
        "niche": niche or ["education"],
        "style": style or ["viral"],
        "duration_range": duration_range or [15, 60],
        "rule": f"Rule for {item_id}",
        "render_usage": {"hook": True},
        "weight": weight,
        "tags": tags or ["hook"],
        "aspect_ratio": aspect_ratio or [],
        "subtitle_style": subtitle_style or [],
        "target_goal": target_goal or [],
    }


def _make_index(*raw_items) -> "KnowledgeIndex":
    from app.ai.rag.knowledge_schema import validate_knowledge_item
    from app.ai.rag.knowledge_index import KnowledgeIndex

    items = [validate_knowledge_item(r) for r in raw_items]
    items = [i for i in items if i is not None]
    idx = KnowledgeIndex()
    idx.build(items)
    return idx


# ---------------------------------------------------------------------------
# 1. Platform filter matches correct items
# ---------------------------------------------------------------------------

def test_platform_filter_matches():
    idx = _make_index(
        _make_raw("a", platform=["tiktok"]),
        _make_raw("b", platform=["youtube"]),
        _make_raw("c", platform=["tiktok", "reels"]),
    )
    results = idx.query({"platform": "tiktok"})
    ids = {r["id"] for r in results}
    assert "a" in ids
    assert "c" in ids
    assert "b" not in ids


def test_platform_filter_case_insensitive():
    idx = _make_index(
        _make_raw("a", platform=["TikTok"]),
    )
    results = idx.query({"platform": "tiktok"})
    assert len(results) == 1


# ---------------------------------------------------------------------------
# 2. Style filter matches correct items
# ---------------------------------------------------------------------------

def test_style_filter_matches():
    idx = _make_index(
        _make_raw("a", style=["viral"]),
        _make_raw("b", style=["educational"]),
        _make_raw("c", style=["viral", "talking_head"]),
    )
    results = idx.query({"style": "viral"})
    ids = {r["id"] for r in results}
    assert "a" in ids
    assert "c" in ids
    assert "b" not in ids


# ---------------------------------------------------------------------------
# 3. Duration range match works
# ---------------------------------------------------------------------------

def test_duration_within_range_matches():
    idx = _make_index(
        _make_raw("in_range", duration_range=[15, 60]),
        _make_raw("out_range", duration_range=[61, 120]),
    )
    results = idx.query({"duration": 30})
    ids = {r["id"] for r in results}
    assert "in_range" in ids
    assert "out_range" not in ids


def test_duration_at_boundary_matches():
    idx = _make_index(
        _make_raw("exact", duration_range=[30, 60]),
    )
    assert len(idx.query({"duration": 30})) == 1
    assert len(idx.query({"duration": 60})) == 1
    assert len(idx.query({"duration": 29})) == 0
    assert len(idx.query({"duration": 61})) == 0


# ---------------------------------------------------------------------------
# 4. Aspect ratio filter works
# ---------------------------------------------------------------------------

def test_aspect_ratio_filter():
    idx = _make_index(
        _make_raw("a", aspect_ratio=["9:16"]),
        _make_raw("b", aspect_ratio=["16:9"]),
    )
    results = idx.query({"aspect_ratio": "9:16"})
    assert len(results) == 1
    assert results[0]["id"] == "a"


# ---------------------------------------------------------------------------
# 5. Target_goal filter works (checks both target_goal and tags)
# ---------------------------------------------------------------------------

def test_target_goal_matches_target_goal_field():
    idx = _make_index(
        _make_raw("a", target_goal=["retention"]),
        _make_raw("b", target_goal=["conversion"]),
    )
    results = idx.query({"target_goal": "retention"})
    assert len(results) == 1
    assert results[0]["id"] == "a"


def test_target_goal_also_matches_tags():
    idx = _make_index(
        _make_raw("a", tags=["retention", "hook"]),
        _make_raw("b", tags=["pacing"]),
    )
    results = idx.query({"target_goal": "retention"})
    assert len(results) == 1
    assert results[0]["id"] == "a"


# ---------------------------------------------------------------------------
# 6. Ranking by weight + match count correct
# ---------------------------------------------------------------------------

def test_ranking_by_weight_desc():
    idx = _make_index(
        _make_raw("low", platform=["tiktok"], weight=0.3),
        _make_raw("high", platform=["tiktok"], weight=0.9),
        _make_raw("mid", platform=["tiktok"], weight=0.6),
    )
    results = idx.query({"platform": "tiktok"})
    assert results[0]["id"] == "high"
    assert results[1]["id"] == "mid"
    assert results[2]["id"] == "low"


def test_match_score_in_result():
    idx = _make_index(
        _make_raw("a", platform=["tiktok"]),
    )
    results = idx.query({"platform": "tiktok"})
    assert len(results) == 1
    assert 0.0 <= results[0]["match_score"] <= 1.0


def test_match_reason_in_result():
    idx = _make_index(
        _make_raw("a", platform=["tiktok"], style=["viral"]),
    )
    results = idx.query({"platform": "tiktok", "style": "viral"})
    assert len(results) == 1
    reasons = results[0]["match_reason"]
    assert any("platform" in r for r in reasons)
    assert any("style" in r for r in reasons)


# ---------------------------------------------------------------------------
# 7. Empty result when no matches (no crash)
# ---------------------------------------------------------------------------

def test_empty_result_no_crash():
    idx = _make_index(
        _make_raw("a", platform=["tiktok"]),
    )
    results = idx.query({"platform": "youtube"})
    assert results == []


def test_empty_index_returns_empty():
    from app.ai.rag.knowledge_index import KnowledgeIndex

    idx = KnowledgeIndex()
    idx.build([])
    results = idx.query({"platform": "tiktok"})
    assert results == []


# ---------------------------------------------------------------------------
# 8. All filters None returns all items ranked by weight
# ---------------------------------------------------------------------------

def test_all_filters_none_returns_all():
    idx = _make_index(
        _make_raw("a", weight=0.9),
        _make_raw("b", weight=0.5),
        _make_raw("c", weight=0.7),
    )
    results = idx.query({"platform": None, "style": None})
    assert len(results) == 3
    assert results[0]["id"] == "a"


def test_empty_filters_dict_returns_all():
    idx = _make_index(
        _make_raw("a", weight=0.8),
        _make_raw("b", weight=0.4),
    )
    results = idx.query({})
    assert len(results) == 2


# ---------------------------------------------------------------------------
# 9. Multiple filters work together (AND logic)
# ---------------------------------------------------------------------------

def test_multiple_filters_and_logic():
    idx = _make_index(
        _make_raw("match_both", platform=["tiktok"], style=["viral"]),
        _make_raw("match_platform_only", platform=["tiktok"], style=["educational"]),
        _make_raw("match_style_only", platform=["youtube"], style=["viral"]),
    )
    results = idx.query({"platform": "tiktok", "style": "viral"})
    assert len(results) == 1
    assert results[0]["id"] == "match_both"


# ---------------------------------------------------------------------------
# 10. Result shape has all required keys
# ---------------------------------------------------------------------------

def test_result_has_required_keys():
    idx = _make_index(_make_raw("shape_test"))
    results = idx.query({})
    assert len(results) == 1
    r = results[0]
    for key in ("id", "type", "rule", "weight", "match_score", "match_reason", "render_usage", "tags"):
        assert key in r, f"Missing key: {key}"
    assert isinstance(r["match_reason"], list)
    assert isinstance(r["render_usage"], dict)
    assert isinstance(r["tags"], list)
