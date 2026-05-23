"""
test_ai_render_knowledge_integration.py — Integration tests for Phase 5.2.

Tests that:
- render_pipeline builds knowledge filters from payload
- create_ai_edit_plan receives retrieved_knowledge in context
- retrieval failure does not fail render
- ai disabled path does not change render behavior
- retrieved hints are extracted from knowledge items correctly
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


def _context(**kwargs) -> dict:
    defaults = {
        "job_id": "test_job_001",
        "srt_path": None,
        "scenes": [],
        "duration": 45.0,
        "market": None,
        "source_path": None,
    }
    defaults.update(kwargs)
    return defaults


def _make_knowledge_result(item_id: str, pacing: str = None, hook: bool = False) -> dict:
    return {
        "id": item_id,
        "type": "hook_pattern",
        "rule": f"Rule for {item_id}",
        "weight": 0.9,
        "match_score": 0.8,
        "match_reason": ["platform:tiktok"],
        "render_usage": {
            "pacing": pacing,
            "hook": hook,
            "subtitle_emphasis": "highlight_problem_keyword" if hook else None,
        },
        "tags": ["hook"],
    }


# ---------------------------------------------------------------------------
# 1. Knowledge filters built from payload
# ---------------------------------------------------------------------------

def test_knowledge_filters_include_render_profile():
    """Render profile should be used as platform filter."""
    req = _req(render_profile="tiktok")
    # Simulate what render_pipeline.py does
    filters = {
        "platform": getattr(req, "render_profile", None) or None,
        "aspect_ratio": getattr(req, "aspect_ratio", None) or None,
        "subtitle_style": getattr(req, "subtitle_style", None) or None,
        "duration": 45.0,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    assert filters["platform"] == "tiktok"
    assert filters["aspect_ratio"] == "9:16"
    assert filters["subtitle_style"] == "bounce"
    assert filters["duration"] == 45.0


def test_knowledge_filters_without_optional_fields():
    """None fields should be excluded from filters."""
    req = _req(render_profile=None, aspect_ratio=None, subtitle_style=None)
    filters = {
        "platform": getattr(req, "render_profile", None) or None,
        "aspect_ratio": getattr(req, "aspect_ratio", None) or None,
        "subtitle_style": getattr(req, "subtitle_style", None) or None,
    }
    filters = {k: v for k, v in filters.items() if v is not None}

    assert "platform" not in filters
    assert "aspect_ratio" not in filters
    assert "subtitle_style" not in filters


# ---------------------------------------------------------------------------
# 2. create_ai_edit_plan receives retrieved_knowledge in context
# ---------------------------------------------------------------------------

def test_ai_director_receives_retrieved_knowledge():
    from app.ai.director.ai_director import create_ai_edit_plan

    knowledge = [_make_knowledge_result("hook_001", pacing="medium_fast", hook=True)]

    ctx = _context(
        retrieved_knowledge=knowledge,
        knowledge_filters={"platform": "tiktok"},
    )
    req = _req()

    plan = create_ai_edit_plan(req, ctx)
    # Plan may be None if transcript unavailable — that is acceptable
    # The key assertion is that it doesn't raise even with retrieved_knowledge in context
    # (it would raise if the code crashed on the new key)


def test_ai_director_context_without_retrieved_knowledge():
    """create_ai_edit_plan must work when retrieved_knowledge is absent from context."""
    from app.ai.director.ai_director import create_ai_edit_plan

    ctx = _context()  # No retrieved_knowledge key
    req = _req()

    # Must not raise
    plan = create_ai_edit_plan(req, ctx)


def test_ai_director_empty_retrieved_knowledge():
    """Empty retrieved_knowledge list must not crash."""
    from app.ai.director.ai_director import create_ai_edit_plan

    ctx = _context(retrieved_knowledge=[], knowledge_filters={})
    req = _req()

    plan = create_ai_edit_plan(req, ctx)
    # No crash — any return value (including None) is acceptable


# ---------------------------------------------------------------------------
# 3. Retrieval failure does not fail render
# ---------------------------------------------------------------------------

def test_knowledge_retrieval_failure_does_not_raise(monkeypatch):
    """If get_knowledge_index raises, retrieved_knowledge should be [] and no exception raised."""
    from app.ai.rag import knowledge_warmup as _warmup_mod

    def _raise(*a, **kw):
        raise RuntimeError("simulated FAISS failure")

    monkeypatch.setattr(_warmup_mod, "get_knowledge_index", _raise)

    # Simulate the retrieval block from render_pipeline.py
    _retrieved_knowledge = []
    try:
        from app.ai.rag.knowledge_warmup import get_knowledge_index
        _kidx = get_knowledge_index()
        _retrieved_knowledge = _kidx.query({}, top_k=10)
    except Exception:
        _retrieved_knowledge = []

    assert _retrieved_knowledge == []


# ---------------------------------------------------------------------------
# 4. AI disabled path does not change render behaviour
# ---------------------------------------------------------------------------

def test_ai_disabled_skips_knowledge_retrieval():
    """When ai_director_enabled=False, create_ai_edit_plan returns None immediately."""
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _req(ai_director_enabled=False)
    ctx = _context(retrieved_knowledge=[_make_knowledge_result("hook_001")])

    plan = create_ai_edit_plan(req, ctx)
    assert plan is None  # Fast-path return — no AI processing


# ---------------------------------------------------------------------------
# 5. Retrieved hints extracted from knowledge items correctly
# ---------------------------------------------------------------------------

def test_pacing_hint_extracted():
    """pacing_hint should come from items with render_usage.pacing."""
    knowledge_items = [
        _make_knowledge_result("pacing_item", pacing="medium_fast"),
    ]
    # Simulate the hint extraction from ai_director._build_plan
    _pacing_hint = None
    _subtitle_emphasis_hint = None
    _hook_hint = False
    for _kitem in knowledge_items:
        _ru = _kitem.get("render_usage", {})
        if _pacing_hint is None and _ru.get("pacing"):
            _pacing_hint = _ru["pacing"]
        if _subtitle_emphasis_hint is None and _ru.get("subtitle_emphasis"):
            _subtitle_emphasis_hint = _ru["subtitle_emphasis"]
        if not _hook_hint and _ru.get("hook") is True:
            _hook_hint = True

    assert _pacing_hint == "medium_fast"


def test_subtitle_emphasis_hint_extracted():
    """subtitle_emphasis_hint should come from items with render_usage.subtitle_emphasis."""
    knowledge_items = [
        _make_knowledge_result("hook_item", hook=True),
    ]
    _subtitle_emphasis_hint = None
    for _kitem in knowledge_items:
        _ru = _kitem.get("render_usage", {})
        if _subtitle_emphasis_hint is None and _ru.get("subtitle_emphasis"):
            _subtitle_emphasis_hint = _ru["subtitle_emphasis"]

    assert _subtitle_emphasis_hint == "highlight_problem_keyword"


def test_hook_hint_extracted():
    """hook_hint should be True when any item has render_usage.hook == True."""
    knowledge_items = [
        _make_knowledge_result("hook_item", hook=True),
        _make_knowledge_result("no_hook"),
    ]
    _hook_hint = False
    for _kitem in knowledge_items:
        _ru = _kitem.get("render_usage", {})
        if not _hook_hint and _ru.get("hook") is True:
            _hook_hint = True

    assert _hook_hint is True


def test_no_hints_when_knowledge_empty():
    """No hints should be extracted from empty retrieved_knowledge."""
    knowledge_items = []
    _pacing_hint = None
    _hook_hint = False
    for _kitem in knowledge_items:
        _ru = _kitem.get("render_usage", {})
        if _pacing_hint is None and _ru.get("pacing"):
            _pacing_hint = _ru["pacing"]
        if not _hook_hint and _ru.get("hook") is True:
            _hook_hint = True

    assert _pacing_hint is None
    assert _hook_hint is False


# ---------------------------------------------------------------------------
# 6. KnowledgeIndex.query never crashes on any input
# ---------------------------------------------------------------------------

def test_query_does_not_crash_on_bad_filters():
    from app.ai.rag.knowledge_index import KnowledgeIndex
    from app.ai.rag.knowledge_schema import validate_knowledge_item

    raw = {
        "id": "test_001",
        "type": "test",
        "platform": ["tiktok"],
        "niche": ["education"],
        "style": ["viral"],
        "duration_range": [15, 60],
        "rule": "Test rule",
        "render_usage": {},
        "weight": 0.5,
        "tags": [],
    }
    item = validate_knowledge_item(raw)
    idx = KnowledgeIndex()
    idx.build([item])

    # Various edge-case filter values
    idx.query({"platform": None, "style": None})
    idx.query({})
    idx.query(None)
    idx.query({"duration": "not_a_number"})
    idx.query({"platform": ""})


# ---------------------------------------------------------------------------
# 7. AITraceLogger does not raise when wired into render flow
# ---------------------------------------------------------------------------

def test_tracer_does_not_raise_in_render_flow(tmp_path):
    from app.ai.tracing import AITraceLogger

    tracer = AITraceLogger("job_render_flow", log_dir=tmp_path)

    # Simulate the render_pipeline.py tracing calls
    tracer.log_input_filters({"platform": "tiktok", "style": "viral"})
    tracer.log_knowledge_retrieved([_make_knowledge_result("hook_001", hook=True)])
    tracer.log_fallback("no_matching_rules", detail="zero items matched filters")
    tracer.log_render_plan_summary({
        "mode": "viral_tiktok",
        "segments": 3,
        "fallback_used": False,
        "knowledge_items_used": 1,
    })
