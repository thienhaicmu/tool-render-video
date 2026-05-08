"""
test_ai_director_phase2_rag.py — AI Director Phase 2: Semantic Hook + Local RAG Memory.

All tests are pure-Python; no CUDA, no cloud API keys.
Optional AI libraries (sentence-transformers, faiss) are allowed to be missing.

Covers:
- RAG memory schema (RenderMemory, MemorySearchResult)
- LocalMemoryStore graceful degradation
- retrieve_ai_context return contract
- AIEditPlan.memory_context field and to_dict() inclusion
- clip_selector memory bonus
- ai_director RAG integration (ai_use_rag_memory=True / False)
"""
from __future__ import annotations

import types
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _req(**kwargs):
    defaults = {
        "ai_director_enabled": True,
        "ai_mode": "viral_tiktok",
        "ai_auto_cut": True,
        "ai_target_duration": None,
        "ai_use_semantic_hooks": True,
        "ai_use_rag_memory": False,
    }
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


_SAMPLE_CHUNKS = [
    {"start": 0.0,  "end": 5.0,  "text": "nobody tells you this secret"},
    {"start": 5.5,  "end": 10.0, "text": "most people get this wrong every time"},
    {"start": 10.5, "end": 65.0, "text": "here is why you need to stop doing this"},
    {"start": 65.5, "end": 90.0, "text": "the truth is simple and clear for everyone"},
]

_SAMPLE_SCENES = [
    {"start": 0.0, "end": 30.0, "motion_score": 80},
    {"start": 30.0, "end": 60.0, "motion_score": 60},
    {"start": 60.0, "end": 90.0, "motion_score": 90},
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. RenderMemory schema
# ─────────────────────────────────────────────────────────────────────────────

def test_render_memory_defaults():
    from app.ai.rag.memory_schema import RenderMemory

    m = RenderMemory(id="test-1", text="nobody tells you this")
    assert m.id == "test-1"
    assert m.text == "nobody tells you this"
    assert m.market is None
    assert m.mode is None
    assert m.duration is None
    assert m.score is None
    assert m.status is None
    assert m.metadata == {}


def test_render_memory_full():
    from app.ai.rag.memory_schema import RenderMemory

    m = RenderMemory(
        id="r-2",
        text="stop doing this now",
        market="VN",
        mode="viral_tiktok",
        duration=75.0,
        score=88.5,
        subtitle_tone="hype",
        camera_behavior="emotional_push",
        status="completed",
        metadata={"output_score": 91},
    )
    assert m.market == "VN"
    assert m.score == pytest.approx(88.5)
    assert m.metadata["output_score"] == 91


def test_memory_search_result_defaults():
    from app.ai.rag.memory_schema import MemorySearchResult

    r = MemorySearchResult(id="x", text="hello", score=0.85)
    assert r.id == "x"
    assert r.score == pytest.approx(0.85)
    assert r.metadata == {}


# ─────────────────────────────────────────────────────────────────────────────
# 2. LocalMemoryStore — graceful degradation
# ─────────────────────────────────────────────────────────────────────────────

def test_memory_store_count_starts_at_zero():
    from app.ai.rag.memory_store import LocalMemoryStore

    store = LocalMemoryStore()
    assert store.count() == 0


def test_memory_store_search_empty_returns_list():
    from app.ai.rag.memory_store import LocalMemoryStore

    store = LocalMemoryStore()
    results = store.search_similar("nobody tells you this")
    assert isinstance(results, list)


def test_memory_store_add_returns_bool():
    from app.ai.rag.memory_store import LocalMemoryStore
    from app.ai.rag.memory_schema import RenderMemory

    store = LocalMemoryStore()
    m = RenderMemory(id="t1", text="stop doing this now", mode="viral_tiktok")
    result = store.add_render_memory(m)
    assert isinstance(result, bool)


def test_memory_store_search_returns_typed_results():
    from app.ai.rag.memory_store import LocalMemoryStore
    from app.ai.rag.memory_schema import RenderMemory, MemorySearchResult

    store = LocalMemoryStore()
    m = RenderMemory(id="t2", text="nobody tells you this secret truth")
    store.add_render_memory(m)
    results = store.search_similar("nobody tells you this")
    assert isinstance(results, list)
    for r in results:
        assert isinstance(r, MemorySearchResult)
        assert isinstance(r.id, str)
        assert isinstance(r.score, float)
        assert 0.0 <= r.score <= 1.0


def test_memory_store_add_increments_count_if_embeddings_available():
    from app.ai.rag.memory_store import LocalMemoryStore
    from app.ai.rag.memory_schema import RenderMemory
    from app.ai.rag.embeddings import is_embedding_available

    store = LocalMemoryStore()
    m = RenderMemory(id="t3", text="viral hook text for testing count")
    added = store.add_render_memory(m)
    if is_embedding_available():
        assert added is True
        assert store.count() == 1
    else:
        assert added is False
        assert store.count() == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3. retrieve_ai_context — return contract
# ─────────────────────────────────────────────────────────────────────────────

def test_retriever_no_memory_store():
    from app.ai.rag.retriever import retrieve_ai_context

    result = retrieve_ai_context("test query", memory_store=None)
    assert "enabled" in result
    assert "available" in result
    assert "results" in result
    assert "warnings" in result
    assert isinstance(result["results"], list)
    assert isinstance(result["warnings"], list)


def test_retriever_no_memory_store_has_warning():
    from app.ai.rag.retriever import retrieve_ai_context
    from app.ai.rag.embeddings import is_embedding_available

    result = retrieve_ai_context("test query", memory_store=None)
    if is_embedding_available():
        assert "no_memory_store" in result["warnings"]
    else:
        assert "embeddings_unavailable" in result["warnings"]


def test_retriever_empty_store_has_warning():
    from app.ai.rag.retriever import retrieve_ai_context
    from app.ai.rag.memory_store import LocalMemoryStore
    from app.ai.rag.embeddings import is_embedding_available

    store = LocalMemoryStore()
    result = retrieve_ai_context("test query", memory_store=store)
    if is_embedding_available():
        assert "memory_store_empty" in result["warnings"]
        assert result["available"] is True
    else:
        assert result["enabled"] is False


def test_retriever_never_raises():
    from app.ai.rag.retriever import retrieve_ai_context

    # Bad memory_store object — should not raise.
    class BadStore:
        def count(self):
            raise RuntimeError("kaboom")
        def search_similar(self, text, top_k=5):
            raise RuntimeError("kaboom")

    result = retrieve_ai_context("query", memory_store=BadStore())
    assert isinstance(result, dict)
    assert "warnings" in result


def test_retriever_with_populated_store():
    from app.ai.rag.retriever import retrieve_ai_context
    from app.ai.rag.memory_store import LocalMemoryStore
    from app.ai.rag.memory_schema import RenderMemory
    from app.ai.rag.embeddings import is_embedding_available

    store = LocalMemoryStore()
    store.add_render_memory(RenderMemory(id="r1", text="nobody tells you this secret"))
    store.add_render_memory(RenderMemory(id="r2", text="stop doing this now to go viral"))

    result = retrieve_ai_context("nobody tells you this", memory_store=store)
    assert isinstance(result, dict)
    if is_embedding_available():
        for r in result["results"]:
            assert "id" in r
            assert "text" in r
            assert "score" in r
            assert "metadata" in r


# ─────────────────────────────────────────────────────────────────────────────
# 4. AIEditPlan memory_context field
# ─────────────────────────────────────────────────────────────────────────────

def test_edit_plan_has_memory_context_field():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan,
    )

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    assert hasattr(plan, "memory_context")
    assert isinstance(plan.memory_context, dict)


def test_edit_plan_to_dict_includes_memory_context():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan,
    )

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        memory_context={"enabled": True, "results": [], "warnings": []},
    )
    d = plan.to_dict()
    assert "memory_context" in d
    assert d["memory_context"]["enabled"] is True


def test_edit_plan_memory_context_default_is_empty_dict():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan,
    )

    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    assert plan.memory_context == {}
    assert plan.to_dict()["memory_context"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Clip selector memory bonus
# ─────────────────────────────────────────────────────────────────────────────

def test_clip_selector_memory_bonus_applied():
    from app.ai.director.clip_selector import select_ai_segments
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("viral_tiktok")
    memory_ctx_strong = {
        "enabled": True,
        "available": True,
        "results": [
            {"id": "m1", "text": "hook text", "score": 0.85, "metadata": {}},
            {"id": "m2", "text": "viral", "score": 0.90, "metadata": {}},
        ],
        "warnings": [],
    }
    memory_ctx_none = None

    segs_with = select_ai_segments(
        chunks=_SAMPLE_CHUNKS, scenes=_SAMPLE_SCENES,
        duration=90.0, mode_config=cfg, memory_context=memory_ctx_strong,
    )
    segs_without = select_ai_segments(
        chunks=_SAMPLE_CHUNKS, scenes=_SAMPLE_SCENES,
        duration=90.0, mode_config=cfg, memory_context=memory_ctx_none,
    )

    if segs_with and segs_without:
        # The top segment should have a higher or equal score with memory bonus.
        assert segs_with[0]["score"] >= segs_without[0]["score"]


def test_clip_selector_memory_bonus_annotates_reason():
    from app.ai.director.clip_selector import select_ai_segments
    from app.ai.config.ai_modes import get_mode_config

    cfg = get_mode_config("viral_tiktok")
    memory_ctx = {
        "enabled": True,
        "available": True,
        "results": [{"id": "m1", "text": "x", "score": 0.95, "metadata": {}}],
        "warnings": [],
    }
    segs = select_ai_segments(
        chunks=_SAMPLE_CHUNKS, scenes=_SAMPLE_SCENES,
        duration=90.0, mode_config=cfg, memory_context=memory_ctx,
    )
    if segs:
        assert "rag_match" in segs[0]["reason"]


def test_clip_selector_weak_memory_no_bonus():
    from app.ai.director.clip_selector import select_ai_segments, _apply_memory_bonus

    segs = [{"start": 0.0, "end": 60.0, "score": 75.0, "reason": "hook=80", "source": "local_ai"}]
    weak_ctx = {
        "results": [{"id": "m1", "text": "x", "score": 0.5, "metadata": {}}],
    }
    result = _apply_memory_bonus(segs, weak_ctx)
    assert result[0]["score"] == pytest.approx(75.0)
    assert "rag_match" not in result[0]["reason"]


def test_clip_selector_empty_segments_no_crash():
    from app.ai.director.clip_selector import _apply_memory_bonus

    result = _apply_memory_bonus([], {"results": [{"score": 0.9}]})
    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 6. AI Director RAG integration — end-to-end
# ─────────────────────────────────────────────────────────────────────────────

def test_ai_director_rag_disabled_no_memory_context():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _req(ai_use_rag_memory=False)
    context = {"job_id": "p2-test-1", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert plan.memory_context == {}


def test_ai_director_rag_enabled_no_store():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _req(ai_use_rag_memory=True)
    context = {"job_id": "p2-test-2", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    # Should not crash; memory_context present with no_memory_store or embeddings_unavailable warning
    assert plan is not None
    assert isinstance(plan.memory_context, dict)
    assert any("rag:" in w for w in plan.warnings) or plan.memory_context == {}


def test_ai_director_rag_enabled_with_store():
    from app.ai.director.ai_director import create_ai_edit_plan
    from app.ai.rag.memory_store import LocalMemoryStore
    from app.ai.rag.memory_schema import RenderMemory

    store = LocalMemoryStore()
    store.add_render_memory(RenderMemory(id="s1", text="nobody tells you this secret"))

    req = _req(ai_use_rag_memory=True)
    context = {
        "job_id": "p2-test-3",
        "transcript_blocks": _SAMPLE_CHUNKS,
        "duration": 90.0,
        "memory_store": store,
    }
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert isinstance(plan.memory_context, dict)
    assert "enabled" in plan.memory_context


def test_ai_director_rag_plan_to_dict_has_memory_context():
    from app.ai.director.ai_director import create_ai_edit_plan

    req = _req(ai_use_rag_memory=True)
    context = {"job_id": "p2-test-4", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    d = plan.to_dict()
    assert "memory_context" in d
    assert isinstance(d["memory_context"], dict)


def test_ai_director_phase1_tests_still_pass():
    """Regression: Phase 1 plan structure must not regress with Phase 2 additions."""
    from app.ai.director.ai_director import create_ai_edit_plan
    from app.ai.director.edit_plan_schema import AIEditPlan

    req = _req()
    context = {"job_id": "p2-regression", "transcript_blocks": _SAMPLE_CHUNKS, "duration": 90.0}
    plan = create_ai_edit_plan(req, context)

    assert plan is not None
    assert isinstance(plan, AIEditPlan)
    assert plan.enabled is True
    d = plan.to_dict()
    for key in ("enabled", "mode", "selected_segments", "subtitle", "camera", "warnings", "fallback_used", "memory_context"):
        assert key in d, f"Missing key: {key}"
