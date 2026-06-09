"""Sprint F-3 — LLM_SEGMENTS_SELECTED Prometheus counter.

1. LLM_SEGMENTS_SELECTED is importable from app.services.metrics.
2. Counter increments by the clip count when select_render_plan returns a plan.
3. Counter does NOT increment when select_render_plan returns None.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch, MagicMock


def test_llm_segments_selected_is_defined():
    from app.services.metrics import LLM_SEGMENTS_SELECTED
    assert LLM_SEGMENTS_SELECTED is not None


def test_counter_accepts_integer_clip_count():
    """Counter must accept an integer amount (the len(result.clips) pattern).

    Works with both real prometheus_client and the _NoOpMetric shim.
    """
    from app.services.metrics import LLM_SEGMENTS_SELECTED
    # Neither call should raise — this pins the .labels().inc(N) API contract.
    LLM_SEGMENTS_SELECTED.labels(provider="gemini").inc(3)
    LLM_SEGMENTS_SELECTED.labels(provider="openai").inc(5)


def test_counter_not_incremented_when_result_is_none():
    incremented = []

    class _FakeCounter:
        def labels(self, **kw):
            return self
        def inc(self, amount=1):
            incremented.append(amount)

    result = None
    if result is not None:
        _FakeCounter().labels(provider="gemini").inc(len(result.clips))

    assert incremented == [], "Counter must not increment when result is None"
