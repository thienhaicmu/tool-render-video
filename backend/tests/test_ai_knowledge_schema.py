"""
test_ai_knowledge_schema.py — Tests for KnowledgeItem schema and validate_knowledge_item().
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _valid_raw() -> dict:
    return {
        "id": "tiktok_hook_001",
        "type": "hook_pattern",
        "platform": ["TikTok", "Reels"],
        "niche": ["Education", "Marketing"],
        "style": ["Viral"],
        "duration_range": [15, 60],
        "rule": "Open with a clear problem.",
        "render_usage": {"hook": True, "pacing": "medium_fast"},
        "weight": 0.9,
        "tags": ["Hook", "Retention"],
    }


# ---------------------------------------------------------------------------
# 1. Valid item passes and returns KnowledgeItem
# ---------------------------------------------------------------------------

def test_valid_item_returns_knowledge_item():
    from app.ai.rag.knowledge_schema import validate_knowledge_item, KnowledgeItem

    item = validate_knowledge_item(_valid_raw())
    assert item is not None
    assert isinstance(item, KnowledgeItem)
    assert item.id == "tiktok_hook_001"
    assert item.type == "hook_pattern"
    assert item.rule == "Open with a clear problem."


def test_valid_item_all_optional_fields():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["aspect_ratio"] = ["9:16"]
    raw["subtitle_style"] = ["Bounce"]
    raw["target_goal"] = ["Retention"]
    raw["examples"] = ["example1"]
    raw["source"] = "human_review"
    raw["notes"] = "Very effective for education"

    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.aspect_ratio == ["9:16"]
    assert item.subtitle_style == ["bounce"]
    assert item.target_goal == ["retention"]
    assert item.source == "human_review"


# ---------------------------------------------------------------------------
# 2. Missing required field returns None
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("missing_field", [
    "id", "type", "platform", "niche", "style",
    "duration_range", "rule", "render_usage", "weight", "tags",
])
def test_missing_required_field_returns_none(missing_field):
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    del raw[missing_field]
    result = validate_knowledge_item(raw)
    assert result is None


# ---------------------------------------------------------------------------
# 3. Weight clamped to [0.0, 1.0]
# ---------------------------------------------------------------------------

def test_weight_above_max_clamped():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["weight"] = 2.5
    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.weight == 1.0


def test_weight_below_min_clamped():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["weight"] = -0.5
    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.weight == 0.0


def test_weight_in_range_unchanged():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["weight"] = 0.75
    item = validate_knowledge_item(raw)
    assert item is not None
    assert abs(item.weight - 0.75) < 1e-9


def test_weight_non_numeric_returns_none():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["weight"] = "not_a_number"
    result = validate_knowledge_item(raw)
    assert result is None


# ---------------------------------------------------------------------------
# 4. platform / niche / style / tags normalised to lowercase
# ---------------------------------------------------------------------------

def test_platform_normalised_to_lowercase():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["platform"] = ["TikTok", "REELS", "Shorts"]
    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.platform == ["tiktok", "reels", "shorts"]


def test_niche_normalised_to_lowercase():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["niche"] = ["EDUCATION", "Marketing"]
    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.niche == ["education", "marketing"]


def test_style_normalised_to_lowercase():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["style"] = ["Viral", "TALKING_HEAD"]
    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.style == ["viral", "talking_head"]


def test_tags_normalised_to_lowercase():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["tags"] = ["Hook", "RETENTION", "First_3_Seconds"]
    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.tags == ["hook", "retention", "first_3_seconds"]


# ---------------------------------------------------------------------------
# 5. duration_range validated as 2-element int list
# ---------------------------------------------------------------------------

def test_duration_range_valid():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["duration_range"] = [15, 60]
    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.duration_range == [15, 60]


def test_duration_range_converts_to_int():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["duration_range"] = [15.0, 60.0]  # floats should be cast to int
    item = validate_knowledge_item(raw)
    assert item is not None
    assert item.duration_range == [15, 60]
    assert isinstance(item.duration_range[0], int)


# ---------------------------------------------------------------------------
# 6. Invalid duration_range returns None
# ---------------------------------------------------------------------------

def test_duration_range_not_a_list_returns_none():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["duration_range"] = "15-60"
    result = validate_knowledge_item(raw)
    assert result is None


def test_duration_range_one_element_returns_none():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["duration_range"] = [15]
    result = validate_knowledge_item(raw)
    assert result is None


def test_duration_range_three_elements_returns_none():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["duration_range"] = [15, 30, 60]
    result = validate_knowledge_item(raw)
    assert result is None


def test_duration_range_non_int_elements_returns_none():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = _valid_raw()
    raw["duration_range"] = ["start", "end"]
    result = validate_knowledge_item(raw)
    assert result is None


# ---------------------------------------------------------------------------
# 7. Non-dict input returns None
# ---------------------------------------------------------------------------

def test_non_dict_input_returns_none():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    assert validate_knowledge_item(None) is None
    assert validate_knowledge_item("string") is None
    assert validate_knowledge_item(42) is None
    assert validate_knowledge_item([]) is None


# ---------------------------------------------------------------------------
# 8. Optional fields default correctly
# ---------------------------------------------------------------------------

def test_optional_fields_default_to_empty():
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    item = validate_knowledge_item(_valid_raw())
    assert item is not None
    assert item.aspect_ratio == []
    assert item.subtitle_style == []
    assert item.target_goal == []
    assert item.examples == []
    assert item.source is None
    assert item.notes is None
