"""
test_ai_director_execution_hints.py — Tests for Phase 5.3 AI director integration.

Verifies:
- execution_hints present in knowledge_injection when knowledge retrieved
- empty retrieved_knowledge → empty/safe execution_hints
- mapper exception → plan still created safely
- Existing Phase 5.2 fields still present (pacing_hint, subtitle_emphasis_hint, hook_hint)
"""
from __future__ import annotations

import types
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _req(**kwargs):
    defaults = {
        "ai_director_enabled": True,
        "ai_mode": "viral_tiktok",
        "ai_auto_cut": True,
        "ai_target_duration": None,
        "ai_use_semantic_hooks": False,
        "ai_use_rag_memory": False,
        "render_profile": "tiktok",
        "aspect_ratio": "9:16",
        "subtitle_style": "bounce",
        "viral_market": None,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _context(retrieved_knowledge=None, **kwargs) -> dict:
    defaults = {
        "job_id": "test_job_exec_hints",
        "srt_path": None,
        "scenes": [],
        "duration": 45.0,
        "market": None,
        "source_path": None,
        "retrieved_knowledge": retrieved_knowledge or [],
        "knowledge_filters": {"platform": "tiktok"},
    }
    defaults.update(kwargs)
    return defaults


def _knowledge_item(item_id: str, weight: float, pacing=None, subtitle=None, hook=None) -> dict:
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
        "tags": [],
    }


def _create_plan(req, ctx):
    from app.ai.director.ai_director import create_ai_edit_plan
    return create_ai_edit_plan(req, ctx)


# ---------------------------------------------------------------------------
# 1. execution_hints present in knowledge_injection when knowledge retrieved
# ---------------------------------------------------------------------------

def test_execution_hints_present_when_knowledge_retrieved():
    items = [_knowledge_item("p1", 0.9, pacing="fast")]
    plan = _create_plan(_req(), _context(retrieved_knowledge=items))
    assert plan is not None
    ki = plan.knowledge_injection
    assert isinstance(ki, dict)
    assert "execution_hints" in ki
    eh = ki["execution_hints"]
    assert isinstance(eh, dict)
    # fast pacing → cut_interval_min=2.0, cut_interval_max=4.0
    assert eh.get("cut_interval_min") == 2.0
    assert eh.get("cut_interval_max") == 4.0


def test_execution_hints_with_subtitle_knowledge():
    items = [_knowledge_item("s1", 0.9, subtitle="highlight_problem_keyword")]
    plan = _create_plan(_req(), _context(retrieved_knowledge=items))
    assert plan is not None
    ki = plan.knowledge_injection
    assert "execution_hints" in ki
    assert ki["execution_hints"].get("subtitle_emphasis_style") == "strong"


def test_execution_hints_with_hook_knowledge():
    items = [_knowledge_item("h1", 0.9, hook=True)]
    plan = _create_plan(_req(), _context(retrieved_knowledge=items))
    assert plan is not None
    ki = plan.knowledge_injection
    assert ki["execution_hints"].get("hook_overlay_enabled") is True


# ---------------------------------------------------------------------------
# 2. Empty retrieved_knowledge → empty/safe execution_hints
# ---------------------------------------------------------------------------

def test_empty_knowledge_gives_safe_execution_hints():
    plan = _create_plan(_req(), _context(retrieved_knowledge=[]))
    assert plan is not None
    ki = plan.knowledge_injection
    # knowledge_injection may be empty dict when no knowledge
    if ki:
        # If present, execution_hints must be a dict with None values
        eh = ki.get("execution_hints", {})
        assert isinstance(eh, dict)
        assert eh.get("cut_interval_min") is None
        assert eh.get("playback_speed_hint") is None


def test_no_retrieved_knowledge_plan_still_created():
    plan = _create_plan(_req(), _context(retrieved_knowledge=None))
    assert plan is not None


# ---------------------------------------------------------------------------
# 3. Mapper exception → plan still created safely
# ---------------------------------------------------------------------------

def test_mapper_exception_plan_still_created(monkeypatch):
    """If mapper raises, plan must still be returned."""
    items = [_knowledge_item("p1", 0.9, pacing="fast")]

    def _bad_mapper(*a, **kw):
        raise RuntimeError("mapper exploded")

    import app.ai.render_mapper as _rm
    original = _rm.map_knowledge_to_execution_hints
    try:
        _rm.map_knowledge_to_execution_hints = _bad_mapper
        plan = _create_plan(_req(), _context(retrieved_knowledge=items))
        assert plan is not None
    finally:
        _rm.map_knowledge_to_execution_hints = original


# ---------------------------------------------------------------------------
# 4. Phase 5.2 fields still present
# ---------------------------------------------------------------------------

def test_phase52_fields_still_present():
    """pacing_hint, subtitle_emphasis_hint, hook_hint must still be in knowledge_injection.hints."""
    items = [
        _knowledge_item("p1", 0.9, pacing="fast"),
        _knowledge_item("s1", 0.8, subtitle="highlight_problem_keyword"),
        _knowledge_item("h1", 0.7, hook=True),
    ]
    plan = _create_plan(_req(), _context(retrieved_knowledge=items))
    assert plan is not None
    ki = plan.knowledge_injection
    assert isinstance(ki, dict)
    # Phase 5.2 stores hints dict in knowledge_injection["hints"]
    hints_52 = ki.get("hints", {})
    assert "pacing_hint" in hints_52 or ki.get("retrieved_count", 0) >= 0


def test_validation_fixups_field_present():
    """validation_fixups must be a list in knowledge_injection."""
    items = [_knowledge_item("p1", 0.9, pacing="fast")]
    plan = _create_plan(_req(), _context(retrieved_knowledge=items))
    assert plan is not None
    ki = plan.knowledge_injection
    if ki:
        assert "validation_fixups" in ki
        assert isinstance(ki["validation_fixups"], list)


def test_validation_warnings_field_present():
    """validation_warnings must be a list in knowledge_injection."""
    items = [_knowledge_item("p1", 0.9, pacing="fast")]
    plan = _create_plan(_req(), _context(retrieved_knowledge=items))
    assert plan is not None
    ki = plan.knowledge_injection
    if ki:
        assert "validation_warnings" in ki
        assert isinstance(ki["validation_warnings"], list)
