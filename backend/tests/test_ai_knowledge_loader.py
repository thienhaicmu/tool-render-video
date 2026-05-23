"""
test_ai_knowledge_loader.py — Tests for load_knowledge_items().

Uses tmp_path fixture to write temp files — no dependency on real knowledge files.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


def _write_jsonl(path: Path, records: list) -> None:
    """Write a list of dicts to a JSONL file."""
    path.write_text(
        "\n".join(json.dumps(r) for r in records),
        encoding="utf-8",
    )


def _valid_item(item_id: str = "item_001", platform: str = "TikTok") -> dict:
    return {
        "id": item_id,
        "type": "hook_pattern",
        "platform": [platform],
        "niche": ["education"],
        "style": ["viral"],
        "duration_range": [15, 60],
        "rule": f"Rule for {item_id}",
        "render_usage": {"hook": True},
        "weight": 0.9,
        "tags": ["hook", "retention"],
    }


# ---------------------------------------------------------------------------
# 1. Loads items from valid JSONL files
# ---------------------------------------------------------------------------

def test_loads_items_from_valid_jsonl(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    f = tmp_path / "rules.jsonl"
    _write_jsonl(f, [_valid_item("item_001"), _valid_item("item_002")])

    items = load_knowledge_items(tmp_path)
    assert len(items) == 2
    ids = {item.id for item in items}
    assert "item_001" in ids
    assert "item_002" in ids


def test_loads_from_multiple_files(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    (tmp_path / "file_a.jsonl").write_text(json.dumps(_valid_item("a_001")) + "\n", encoding="utf-8")
    (tmp_path / "file_b.jsonl").write_text(json.dumps(_valid_item("b_001")) + "\n", encoding="utf-8")

    items = load_knowledge_items(tmp_path)
    assert len(items) == 2


# ---------------------------------------------------------------------------
# 2. Skips invalid JSON lines
# ---------------------------------------------------------------------------

def test_skips_invalid_json_lines(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    f = tmp_path / "mixed.jsonl"
    f.write_text(
        json.dumps(_valid_item("item_001")) + "\n"
        + "{ this is not json }\n"
        + json.dumps(_valid_item("item_002")) + "\n",
        encoding="utf-8",
    )

    items = load_knowledge_items(tmp_path)
    assert len(items) == 2
    assert items[0].id in {"item_001", "item_002"}


# ---------------------------------------------------------------------------
# 3. Handles missing directory (returns [])
# ---------------------------------------------------------------------------

def test_missing_directory_returns_empty(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    nonexistent = tmp_path / "does_not_exist"
    items = load_knowledge_items(nonexistent)
    assert items == []


# ---------------------------------------------------------------------------
# 4. Handles empty directory (returns [])
# ---------------------------------------------------------------------------

def test_empty_directory_returns_empty(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    items = load_knowledge_items(tmp_path)
    assert items == []


# ---------------------------------------------------------------------------
# 5. Preserves IDs and rule text after loading
# ---------------------------------------------------------------------------

def test_preserves_id_and_rule(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    raw = _valid_item("unique_id_123")
    raw["rule"] = "This is the exact rule text."
    _write_jsonl(tmp_path / "rules.jsonl", [raw])

    items = load_knowledge_items(tmp_path)
    assert len(items) == 1
    assert items[0].id == "unique_id_123"
    assert items[0].rule == "This is the exact rule text."


# ---------------------------------------------------------------------------
# 6. Normalises platform/tags to lowercase
# ---------------------------------------------------------------------------

def test_normalises_platform_to_lowercase(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    raw = _valid_item("item_001", platform="TikTok")
    raw["tags"] = ["Hook", "RETENTION"]
    _write_jsonl(tmp_path / "rules.jsonl", [raw])

    items = load_knowledge_items(tmp_path)
    assert len(items) == 1
    assert "tiktok" in items[0].platform
    assert "hook" in items[0].tags
    assert "retention" in items[0].tags


# ---------------------------------------------------------------------------
# 7. Skips items with invalid schema
# ---------------------------------------------------------------------------

def test_skips_invalid_schema_items(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    valid = _valid_item("valid_item")
    invalid = {"id": "bad_item"}  # missing required fields

    _write_jsonl(tmp_path / "rules.jsonl", [valid, invalid])

    items = load_knowledge_items(tmp_path)
    assert len(items) == 1
    assert items[0].id == "valid_item"


# ---------------------------------------------------------------------------
# 8. Empty JSONL lines are skipped silently
# ---------------------------------------------------------------------------

def test_skips_empty_lines(tmp_path):
    from app.ai.rag.knowledge_loader import load_knowledge_items

    f = tmp_path / "rules.jsonl"
    f.write_text(
        "\n"
        + json.dumps(_valid_item("item_001")) + "\n"
        + "\n",
        encoding="utf-8",
    )

    items = load_knowledge_items(tmp_path)
    assert len(items) == 1


# ---------------------------------------------------------------------------
# 9. Default processed_dir resolves to backend/knowledge/processed/
# ---------------------------------------------------------------------------

def test_default_processed_dir_resolves():
    """The default processed_dir must resolve to a path ending in knowledge/processed."""
    from app.ai.rag.knowledge_loader import _DEFAULT_PROCESSED_DIR

    assert "knowledge" in str(_DEFAULT_PROCESSED_DIR)
    assert "processed" in str(_DEFAULT_PROCESSED_DIR)
