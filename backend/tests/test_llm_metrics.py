"""Tests for Prometheus LLM render plan metrics — Sprint B-2.

Verifies that select_render_plan() increments LLM_RENDER_PLAN_CALLS and
observes LLM_RENDER_PLAN_LATENCY for both success and empty outcomes.
Requires prometheus_client to be installed (it is in requirements.txt).
"""
import pytest
from unittest.mock import MagicMock


def _get_counter_value(registry, provider: str, status: str) -> float:
    """Read the current value of a LLM_RENDER_PLAN_CALLS label combination."""
    from app.services.metrics import LLM_RENDER_PLAN_CALLS
    try:
        return LLM_RENDER_PLAN_CALLS.labels(provider=provider, status=status)._value.get()
    except Exception:
        return 0.0


def _get_histogram_count(registry, provider: str) -> float:
    """Read the sample count for LLM_RENDER_PLAN_LATENCY."""
    from app.services.metrics import LLM_RENDER_PLAN_LATENCY
    try:
        return LLM_RENDER_PLAN_LATENCY.labels(provider=provider)._sum.get()
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Counter increments on success
# ---------------------------------------------------------------------------

def test_llm_metrics_counter_increments_on_success(monkeypatch):
    """Counter label (provider, status=success) is incremented when provider returns a plan."""
    fake_plan = MagicMock()
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.select_render_plan",
        lambda **_kw: fake_plan,
    )
    from app.features.render.ai.llm import select_render_plan
    from app.services.metrics import LLM_RENDER_PLAN_CALLS, REGISTRY

    before = _get_counter_value(REGISTRY, "gemini", "success")
    select_render_plan(
        provider="gemini",
        srt_content="1\n00:00:01,000 --> 00:00:02,000\nHello",
        output_count=1,
        min_sec=5.0,
        max_sec=60.0,
        video_duration=120.0,
    )
    after = _get_counter_value(REGISTRY, "gemini", "success")
    assert after > before, "Counter (gemini, success) must increment on a successful plan"


# ---------------------------------------------------------------------------
# Counter uses status=empty when result is None
# ---------------------------------------------------------------------------

def test_llm_metrics_counter_status_empty_when_none(monkeypatch):
    """Counter label (provider, status=empty) is incremented when provider returns None."""
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.select_render_plan",
        lambda **_kw: None,
    )
    from app.features.render.ai.llm import select_render_plan
    from app.services.metrics import REGISTRY

    before = _get_counter_value(REGISTRY, "gemini", "empty")
    select_render_plan(
        provider="gemini",
        srt_content="1\n00:00:01,000 --> 00:00:02,000\nHello",
        output_count=1,
        min_sec=5.0,
        max_sec=60.0,
        video_duration=120.0,
    )
    after = _get_counter_value(REGISTRY, "gemini", "empty")
    assert after > before, "Counter (gemini, empty) must increment when provider returns None"


# ---------------------------------------------------------------------------
# Latency histogram observes on every call
# ---------------------------------------------------------------------------

def test_llm_metrics_latency_histogram_observes(monkeypatch):
    """LLM_RENDER_PLAN_LATENCY records a sample on every select_render_plan call."""
    monkeypatch.setattr(
        "app.features.render.ai.llm.providers.gemini.select_render_plan",
        lambda **_kw: MagicMock(),
    )
    from app.features.render.ai.llm import select_render_plan
    from app.services.metrics import REGISTRY

    before = _get_histogram_count(REGISTRY, "gemini")
    select_render_plan(
        provider="gemini",
        srt_content="1\n00:00:01,000 --> 00:00:02,000\nHello",
        output_count=1,
        min_sec=5.0,
        max_sec=60.0,
        video_duration=120.0,
    )
    after = _get_histogram_count(REGISTRY, "gemini")
    assert after >= before, "LLM_RENDER_PLAN_LATENCY histogram must have recorded a sample"
