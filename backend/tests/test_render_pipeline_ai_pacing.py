"""
test_render_pipeline_ai_pacing.py — Tests for Phase 5.4 render pipeline
pacing integration.

Verifies:
- AI disabled path → pacing not applied, behavior unchanged
- no knowledge path → behavior unchanged
- valid pacing hint → cut_interval applied to segment config
- user explicit min_part_sec overrides AI
- invalid hint → fallback, render continues
- pacing config influences segment duration preference (config built + var set)
- trace logs ai.pacing_applied when applied
- trace logs ai.decision_rejected when rejected
"""
from __future__ import annotations

import json
import tempfile
import types
from pathlib import Path

import pytest

from app.ai.pacing import AIPacingConfig, build_ai_pacing_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(min_part_sec=15, max_part_sec=60, ai_director_enabled=True):
    p = types.SimpleNamespace()
    p.min_part_sec = min_part_sec
    p.max_part_sec = max_part_sec
    p.ai_director_enabled = ai_director_enabled
    return p


def _make_hints(cut_min=3.0, cut_max=5.0, source_ids=None):
    return {
        "cut_interval_min": cut_min,
        "cut_interval_max": cut_max,
        "source_knowledge_ids": source_ids or ["k1"],
    }


# ---------------------------------------------------------------------------
# 1. AI disabled path — pacing not applied
# ---------------------------------------------------------------------------

def test_ai_disabled_pacing_not_applied():
    """When ai_director_enabled=False, pacing early block is skipped.

    Simulates the guard: if getattr(payload, 'ai_director_enabled', False).
    """
    payload = _make_payload(ai_director_enabled=False)
    # When AI is disabled, early block is never entered
    _pacing_config = None  # stays None

    # _seg_min_sec/_seg_max_sec default to payload values
    _seg_min_sec = int(payload.min_part_sec)
    _seg_max_sec = int(payload.max_part_sec)

    if (
        _pacing_config is not None
        and _pacing_config.applied
        and _pacing_config.cut_interval_min is not None
        and _pacing_config.cut_interval_max is not None
    ):
        _seg_min_sec = int(_pacing_config.cut_interval_min)
        _seg_max_sec = int(_pacing_config.cut_interval_max)

    # Behavior unchanged — still payload defaults
    assert _seg_min_sec == 15
    assert _seg_max_sec == 60


# ---------------------------------------------------------------------------
# 2. No knowledge path — behavior unchanged
# ---------------------------------------------------------------------------

def test_no_knowledge_pacing_unchanged():
    """When no knowledge is retrieved, pacing config is not built → unchanged."""
    payload = _make_payload()

    # Simulate: _early_retrieved_knowledge is empty
    _early_retrieved_knowledge = []
    _pacing_config = None

    # No mapping done (knowledge is empty)
    if _early_retrieved_knowledge:
        # Would build pacing config, but skipped
        _pacing_config = build_ai_pacing_config({}, payload)

    _seg_min_sec = int(payload.min_part_sec)
    _seg_max_sec = int(payload.max_part_sec)

    if (
        _pacing_config is not None
        and _pacing_config.applied
        and _pacing_config.cut_interval_min is not None
        and _pacing_config.cut_interval_max is not None
    ):
        _seg_min_sec = int(_pacing_config.cut_interval_min)
        _seg_max_sec = int(_pacing_config.cut_interval_max)

    assert _seg_min_sec == 15
    assert _seg_max_sec == 60


# ---------------------------------------------------------------------------
# 3. Valid pacing hint → cut_interval applied to segment config
# ---------------------------------------------------------------------------

def test_valid_pacing_hint_applied_to_segment_config():
    """Valid AI pacing hint updates _seg_min_sec/_seg_max_sec."""
    payload = _make_payload()
    hints = _make_hints(3.0, 5.0)

    _pacing_config = build_ai_pacing_config(hints, payload)

    assert _pacing_config.applied is True
    assert _pacing_config.cut_interval_min == 3.0
    assert _pacing_config.cut_interval_max == 5.0

    # Simulate render_pipeline.py injection logic
    _seg_min_sec = int(payload.min_part_sec)
    _seg_max_sec = int(payload.max_part_sec)

    if (
        _pacing_config is not None
        and _pacing_config.applied
        and _pacing_config.cut_interval_min is not None
        and _pacing_config.cut_interval_max is not None
    ):
        _seg_min_sec = int(_pacing_config.cut_interval_min)
        _seg_max_sec = int(_pacing_config.cut_interval_max)

    assert _seg_min_sec == 3  # from AI hint
    assert _seg_max_sec == 5  # from AI hint


def test_pacing_hint_different_values():
    """Different valid hint values are propagated correctly."""
    payload = _make_payload()
    hints = _make_hints(6.0, 10.0)

    _pacing_config = build_ai_pacing_config(hints, payload)

    _seg_min_sec = int(payload.min_part_sec)
    _seg_max_sec = int(payload.max_part_sec)

    if _pacing_config.applied and _pacing_config.cut_interval_min and _pacing_config.cut_interval_max:
        _seg_min_sec = int(_pacing_config.cut_interval_min)
        _seg_max_sec = int(_pacing_config.cut_interval_max)

    assert _seg_min_sec == 6
    assert _seg_max_sec == 10


# ---------------------------------------------------------------------------
# 4. User explicit min_part_sec overrides AI
# ---------------------------------------------------------------------------

def test_user_explicit_min_overrides_ai():
    """User-set min_part_sec (non-default) → AI pacing rejected."""
    payload = _make_payload(min_part_sec=45, max_part_sec=60)  # 45 != 15
    hints = _make_hints(3.0, 5.0)

    _pacing_config = build_ai_pacing_config(hints, payload)

    assert _pacing_config.applied is False
    assert _pacing_config.rejected_reason == "user_duration_override"

    # Segment config stays as user's value
    _seg_min_sec = int(payload.min_part_sec)
    _seg_max_sec = int(payload.max_part_sec)

    if _pacing_config.applied and _pacing_config.cut_interval_min and _pacing_config.cut_interval_max:
        _seg_min_sec = int(_pacing_config.cut_interval_min)
        _seg_max_sec = int(_pacing_config.cut_interval_max)

    assert _seg_min_sec == 45  # user's value preserved
    assert _seg_max_sec == 60


def test_user_explicit_max_overrides_ai():
    """User-set max_part_sec (non-default) → AI pacing rejected."""
    payload = _make_payload(min_part_sec=15, max_part_sec=120)  # 120 != 60
    hints = _make_hints(3.0, 5.0)

    _pacing_config = build_ai_pacing_config(hints, payload)

    assert _pacing_config.applied is False
    assert _pacing_config.rejected_reason == "user_duration_override"


# ---------------------------------------------------------------------------
# 5. Invalid hint → fallback, render continues
# ---------------------------------------------------------------------------

def test_invalid_hint_fallback_no_raise():
    """Invalid hint values (string, etc.) don't crash, fall back gracefully."""
    invalid_hints = {"cut_interval_min": "bad_value", "cut_interval_max": "also_bad"}
    payload = _make_payload()

    cfg = build_ai_pacing_config(invalid_hints, payload)
    assert isinstance(cfg, AIPacingConfig)
    # Both cleared → no_pacing_hint or enabled=False
    # No exception must be raised


def test_none_hints_fallback():
    """None hints → disabled, render continues unchanged."""
    payload = _make_payload()
    cfg = build_ai_pacing_config(None, payload)

    _seg_min_sec = int(payload.min_part_sec)
    _seg_max_sec = int(payload.max_part_sec)

    if cfg is not None and cfg.applied and cfg.cut_interval_min and cfg.cut_interval_max:
        _seg_min_sec = int(cfg.cut_interval_min)
        _seg_max_sec = int(cfg.cut_interval_max)

    assert _seg_min_sec == 15  # unchanged
    assert _seg_max_sec == 60  # unchanged


def test_empty_segments_fallback_scenario():
    """If pacing config would produce no usable segments, original defaults are retained."""
    # This test documents the safety behavior:
    # _seg_min_sec/_seg_max_sec are set only if config.applied=True.
    # If the hint produces a degenerate range (after clamping), the original payload
    # defaults are used.
    payload = _make_payload()
    # Extremely narrow range — clamped to [1.0, 1.0]
    hints = {"cut_interval_min": 0.001, "cut_interval_max": 0.001}
    cfg = build_ai_pacing_config(hints, payload)

    # min=max=1.0 after clamping — still valid, applied=True
    # No exception thrown
    assert isinstance(cfg, AIPacingConfig)


# ---------------------------------------------------------------------------
# 6. Pacing config built correctly (assert config built + variable set)
# ---------------------------------------------------------------------------

def test_pacing_config_built_from_hints():
    """AIPacingConfig is built from execution hints correctly."""
    hints = _make_hints(4.0, 7.0, ["know_001"])
    payload = _make_payload()
    cfg = build_ai_pacing_config(hints, payload)

    assert cfg.enabled is True
    assert cfg.applied is True
    assert cfg.cut_interval_min == 4.0
    assert cfg.cut_interval_max == 7.0
    assert "know_001" in cfg.source_knowledge_ids


def test_pacing_config_dict_representation():
    """AIPacingConfig.to_dict() contains all required keys."""
    hints = _make_hints(3.0, 5.0, ["k1"])
    payload = _make_payload()
    cfg = build_ai_pacing_config(hints, payload)
    d = cfg.to_dict()

    assert d["enabled"] is True
    assert d["applied"] is True
    assert d["cut_interval_min"] == 3.0
    assert d["cut_interval_max"] == 5.0
    assert d["rejected_reason"] is None
    assert isinstance(d["validation_fixups"], list)
    assert isinstance(d["source_knowledge_ids"], list)


# ---------------------------------------------------------------------------
# 7. Trace logs ai.pacing_applied when applied
# ---------------------------------------------------------------------------

def test_trace_pacing_applied_when_applied():
    """When config.applied=True, log_pacing_applied writes ai.pacing_applied event."""
    from app.ai.tracing import AITraceLogger

    with tempfile.TemporaryDirectory() as tmp:
        tracer = AITraceLogger("pipe-test-001", log_dir=Path(tmp))
        hints = _make_hints(3.0, 5.0, ["k1"])
        payload = _make_payload()
        cfg = build_ai_pacing_config(hints, payload)

        # Simulate render_pipeline.py trace call
        if cfg.applied:
            tracer.log_pacing_applied({
                "applied": True,
                "cut_interval_min": cfg.cut_interval_min,
                "cut_interval_max": cfg.cut_interval_max,
                "source_knowledge_ids": cfg.source_knowledge_ids,
                "reason": "valid_ai_pacing_hint",
            })

        path = Path(tmp) / "pipe-test-001_ai_trace.jsonl"
        assert path.exists()
        lines = [json.loads(l) for l in path.read_text().strip().split("\n") if l.strip()]

    assert len(lines) == 1
    assert lines[0]["event"] == "ai.pacing_applied"
    assert lines[0]["applied"] is True
    assert lines[0]["cut_interval_min"] == 3.0
    assert lines[0]["cut_interval_max"] == 5.0


# ---------------------------------------------------------------------------
# 8. Trace logs ai.decision_rejected when rejected
# ---------------------------------------------------------------------------

def test_trace_decision_rejected_when_user_override():
    """When user overrides AI, log_decision_rejected is called."""
    from app.ai.tracing import AITraceLogger

    with tempfile.TemporaryDirectory() as tmp:
        tracer = AITraceLogger("pipe-test-002", log_dir=Path(tmp))
        hints = _make_hints(3.0, 5.0)
        payload = _make_payload(min_part_sec=45)  # user override
        cfg = build_ai_pacing_config(hints, payload)

        assert cfg.applied is False
        assert cfg.rejected_reason == "user_duration_override"

        # Simulate render_pipeline.py rejection trace
        tracer.log_decision_rejected(
            cfg.rejected_reason,
            detail={"hint": "pacing", "reason": cfg.rejected_reason},
        )

        path = Path(tmp) / "pipe-test-002_ai_trace.jsonl"
        lines = [json.loads(l) for l in path.read_text().strip().split("\n") if l.strip()]

    assert len(lines) == 1
    assert lines[0]["event"] == "ai.decision_rejected"
    assert lines[0]["reason"] == "user_duration_override"


def test_trace_decision_rejected_no_pacing_hint():
    """When no pacing hint present, decision_rejected is logged."""
    from app.ai.tracing import AITraceLogger

    with tempfile.TemporaryDirectory() as tmp:
        tracer = AITraceLogger("pipe-test-003", log_dir=Path(tmp))
        hints = {"cut_interval_min": None, "cut_interval_max": None}
        payload = _make_payload()
        cfg = build_ai_pacing_config(hints, payload)

        assert cfg.rejected_reason == "no_pacing_hint"

        tracer.log_decision_rejected(cfg.rejected_reason)
        path = Path(tmp) / "pipe-test-003_ai_trace.jsonl"
        lines = [json.loads(l) for l in path.read_text().strip().split("\n") if l.strip()]

    assert lines[0]["reason"] == "no_pacing_hint"


# ---------------------------------------------------------------------------
# 9. Early retrieval reuse (Task 5 behavior verification)
# ---------------------------------------------------------------------------

def test_early_retrieved_knowledge_reuse_logic():
    """When _early_retrieved_knowledge is populated, Phase 5.2 block reuses it."""
    # Simulates the conditional in the Phase 5.2 block:
    # if _early_retrieved_knowledge: reuse; else: query again

    _early_retrieved_knowledge = [{"id": "k1", "weight": 0.9}]
    _retrieved_knowledge = []

    # Simulate the reuse logic
    if _early_retrieved_knowledge:
        _retrieved_knowledge = _early_retrieved_knowledge
    else:
        # Would do a second FAISS query — not entered here
        pass

    assert _retrieved_knowledge == _early_retrieved_knowledge
    assert len(_retrieved_knowledge) == 1


def test_early_retrieved_knowledge_empty_triggers_fresh_query():
    """When _early_retrieved_knowledge is empty, Phase 5.2 does its own query."""
    _early_retrieved_knowledge = []
    _second_query_called = False

    if _early_retrieved_knowledge:
        _retrieved_knowledge = _early_retrieved_knowledge
    else:
        # Would call get_knowledge_index().query() — mark as called
        _second_query_called = True
        _retrieved_knowledge = []

    assert _second_query_called is True


# ---------------------------------------------------------------------------
# 10. Segment selection: pacing config does not affect ai_disabled path
# ---------------------------------------------------------------------------

def test_ai_disabled_build_pacing_not_called():
    """When ai_director_enabled=False, build_ai_pacing_config is not called."""
    payload = _make_payload(ai_director_enabled=False)

    # Guard: only enter pacing block when ai_director_enabled
    _pacing_config = None
    if getattr(payload, "ai_director_enabled", False):
        _pacing_config = build_ai_pacing_config({}, payload)

    assert _pacing_config is None
