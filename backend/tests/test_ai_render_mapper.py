"""
test_ai_render_mapper.py — Tests for map_knowledge_to_execution_hints().

Verifies pacing/subtitle/hook mappings, weight priority, and safe behavior.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _map(knowledge: list, existing_hints=None):
    from app.ai.render_mapper import map_knowledge_to_execution_hints
    return map_knowledge_to_execution_hints(knowledge, existing_hints)


def _item(item_id: str, weight: float, pacing=None, subtitle=None, hook=None) -> dict:
    """Build a minimal knowledge item with the given render_usage fields."""
    ru = {}
    if pacing is not None:
        ru["pacing"] = pacing
    if subtitle is not None:
        ru["subtitle_emphasis"] = subtitle
    if hook is not None:
        ru["hook"] = hook
    return {
        "id": item_id,
        "type": "pacing_rule",
        "weight": weight,
        "render_usage": ru,
    }


# ---------------------------------------------------------------------------
# 1. Pacing mappings
# ---------------------------------------------------------------------------

def test_maps_fast_pacing():
    items = [_item("p1", 0.9, pacing="fast")]
    r = _map(items)
    assert r.hints.cut_interval_min == 2.0
    assert r.hints.cut_interval_max == 4.0


def test_maps_medium_fast_pacing():
    items = [_item("p2", 0.8, pacing="medium_fast")]
    r = _map(items)
    assert r.hints.cut_interval_min == 3.0
    assert r.hints.cut_interval_max == 5.0


def test_maps_medium_pacing():
    items = [_item("p3", 0.7, pacing="medium")]
    r = _map(items)
    assert r.hints.cut_interval_min == 4.0
    assert r.hints.cut_interval_max == 7.0


def test_maps_slow_pacing():
    items = [_item("p4", 0.6, pacing="slow")]
    r = _map(items)
    assert r.hints.cut_interval_min == 6.0
    assert r.hints.cut_interval_max == 10.0


def test_unknown_pacing_gives_none():
    items = [_item("p5", 0.9, pacing="ultra_fast")]
    r = _map(items)
    assert r.hints.cut_interval_min is None
    assert r.hints.cut_interval_max is None


# ---------------------------------------------------------------------------
# 2. Subtitle emphasis mappings
# ---------------------------------------------------------------------------

def test_maps_subtitle_high_emphasis():
    items = [_item("s1", 0.9, subtitle="high_emphasis")]
    r = _map(items)
    assert r.hints.subtitle_emphasis_style == "strong"


def test_maps_subtitle_strong():
    items = [_item("s2", 0.9, subtitle="strong")]
    r = _map(items)
    assert r.hints.subtitle_emphasis_style == "strong"


def test_maps_subtitle_highlight_problem_keyword():
    items = [_item("s3", 0.9, subtitle="highlight_problem_keyword")]
    r = _map(items)
    assert r.hints.subtitle_emphasis_style == "strong"


def test_maps_subtitle_medium_emphasis():
    items = [_item("s4", 0.9, subtitle="medium_emphasis")]
    r = _map(items)
    assert r.hints.subtitle_emphasis_style == "medium"


def test_maps_subtitle_medium():
    items = [_item("s5", 0.9, subtitle="medium")]
    r = _map(items)
    assert r.hints.subtitle_emphasis_style == "medium"


def test_maps_subtitle_subtle():
    items = [_item("s6", 0.9, subtitle="subtle")]
    r = _map(items)
    assert r.hints.subtitle_emphasis_style == "subtle"


def test_unknown_subtitle_gives_none():
    items = [_item("s7", 0.9, subtitle="extra_bold")]
    r = _map(items)
    assert r.hints.subtitle_emphasis_style is None


# ---------------------------------------------------------------------------
# 3. Hook overlay mapping
# ---------------------------------------------------------------------------

def test_maps_hook_true():
    items = [_item("h1", 0.9, hook=True)]
    r = _map(items)
    assert r.hints.hook_overlay_enabled is True


def test_maps_hook_false():
    items = [_item("h2", 0.9, hook=False)]
    r = _map(items)
    assert r.hints.hook_overlay_enabled is False


def test_hook_not_present_gives_none():
    """Item has no render_usage.hook → hook_overlay_enabled stays None."""
    items = [_item("h3", 0.9, pacing="fast")]  # no hook field
    r = _map(items)
    assert r.hints.hook_overlay_enabled is None


# ---------------------------------------------------------------------------
# 4. Empty / invalid inputs
# ---------------------------------------------------------------------------

def test_empty_knowledge_safe():
    r = _map([])
    assert r.ok is True
    assert r.hints.cut_interval_min is None
    assert r.hints.cut_interval_max is None
    assert r.hints.hook_overlay_enabled is None


def test_none_knowledge_safe():
    r = _map(None)
    assert r.ok is True


def test_invalid_knowledge_items_no_crash():
    items = [None, 42, "garbage", {"no_render_usage": True}, _item("ok", 0.5, pacing="fast")]
    r = _map(items)
    assert r.ok is True
    # At minimum the valid item contributes
    assert r.hints.cut_interval_min == 2.0


# ---------------------------------------------------------------------------
# 5. Weight priority (higher weight wins)
# ---------------------------------------------------------------------------

def test_higher_weight_item_wins_pacing():
    items = [
        _item("low_weight", 0.3, pacing="slow"),
        _item("high_weight", 0.9, pacing="fast"),
    ]
    r = _map(items)
    # high_weight (fast) wins
    assert r.hints.cut_interval_min == 2.0
    assert r.hints.cut_interval_max == 4.0


def test_higher_weight_item_wins_subtitle():
    items = [
        _item("low", 0.2, subtitle="subtle"),
        _item("high", 0.8, subtitle="strong"),
    ]
    r = _map(items)
    assert r.hints.subtitle_emphasis_style == "strong"


# ---------------------------------------------------------------------------
# 6. Determinism
# ---------------------------------------------------------------------------

def test_deterministic_same_input_same_output():
    items = [
        _item("p1", 0.9, pacing="fast"),
        _item("s1", 0.8, subtitle="strong"),
        _item("h1", 0.7, hook=True),
    ]
    r1 = _map(list(items))
    r2 = _map(list(items))
    assert r1.hints.to_dict() == r2.hints.to_dict()


# ---------------------------------------------------------------------------
# 7. source_knowledge_ids populated
# ---------------------------------------------------------------------------

def test_source_knowledge_ids_populated():
    items = [
        _item("pacing_001", 0.9, pacing="fast"),
        _item("subtitle_001", 0.8, subtitle="medium"),
        _item("hook_001", 0.7, hook=True),
    ]
    r = _map(items)
    ids = r.hints.source_knowledge_ids
    assert "pacing_001" in ids
    assert "subtitle_001" in ids
    assert "hook_001" in ids


def test_source_knowledge_ids_empty_for_no_match():
    """Items without recognized render_usage fields don't add to source_ids."""
    items = [_item("no_match", 0.9)]  # empty render_usage
    r = _map(items)
    assert r.hints.source_knowledge_ids == []


# ---------------------------------------------------------------------------
# 8. AIValidationResult returned (not raw dict)
# ---------------------------------------------------------------------------

def test_returns_ai_validation_result():
    from app.ai.contracts import AIValidationResult
    r = _map([_item("x", 0.5, pacing="fast")])
    assert isinstance(r, AIValidationResult)
    assert hasattr(r, "hints")
    assert hasattr(r, "fixups")
    assert hasattr(r, "ok")


# ---------------------------------------------------------------------------
# 9. Multiple fields from different items
# ---------------------------------------------------------------------------

def test_multiple_fields_from_different_items():
    """Different items can provide different fields."""
    items = [
        _item("pacing_item", 0.9, pacing="medium_fast"),
        _item("subtitle_item", 0.8, subtitle="high_emphasis"),
    ]
    r = _map(items)
    assert r.hints.cut_interval_min == 3.0
    assert r.hints.subtitle_emphasis_style == "strong"
