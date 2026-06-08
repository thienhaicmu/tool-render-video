"""Pin Gemini default model + (companion to test_llm_pipeline_hard_fail.py
for the LLM Call 1 error-message contract).

Live bug (2026-06-07): a render against
``D:\\T6\\S1\\05\\FASTEST MARRIAGE PROPOSAL GOES RIGHT (1080p).mp4``
failed at ``JobStage.SEGMENT_BUILDING`` with the misleading message
``LLM pipeline: LLM returned no usable segments (min_quality_score=0.6)``.
Underlying cause: 429 quota error on free-tier ``gemini-2.5-pro``. The
2026-06-06 baseline smoke ALREADY hit the same issue.

These tests pin the default-model fix:
- The default model is now ``gemini-2.5-flash`` (free-tier safe),
  overridable via the ``GEMINI_DEFAULT_MODEL`` env var.

The companion fix (error message stops blaming ``min_quality_score``)
is tested in ``test_llm_pipeline_hard_fail.py::test_llm_returns_*_raises``
and ``test_llm_pipeline_hard_fail.py::test_*_message_directs_to_provider_logs``.
"""
from __future__ import annotations

import importlib

import pytest


# ---------------------------------------------------------------------------
# 1. Default model
# ---------------------------------------------------------------------------


def test_gemini_default_model_is_flash():
    """Free-tier safe default. If you're flipping this back to ``-pro``,
    document the paid-tier requirement next to the constant."""
    from app.features.render.ai.llm.providers import gemini as _g

    assert _g._DEFAULT_MODEL == "gemini-2.5-flash", (
        f"_DEFAULT_MODEL = {_g._DEFAULT_MODEL!r} — expected gemini-2.5-flash. "
        "gemini-2.5-pro has limit:0 on free tier and causes 429 RESOURCE_EXHAUSTED."
    )


def test_gemini_default_model_env_override(monkeypatch):
    """``GEMINI_DEFAULT_MODEL`` env var lets a paid-tier deployment pick
    Pro without code changes. Re-import the module to pick up the env
    var at module load."""
    monkeypatch.setenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-pro")
    import app.features.render.ai.llm.providers.gemini as _g
    importlib.reload(_g)
    try:
        assert _g._DEFAULT_MODEL == "gemini-2.5-pro"
    finally:
        # Restore default for other tests.
        monkeypatch.delenv("GEMINI_DEFAULT_MODEL", raising=False)
        importlib.reload(_g)


def test_gemini_default_model_falls_back_when_env_blank(monkeypatch):
    """Empty or whitespace-only env value falls back to the safe default,
    not to '' (which would propagate to the SDK and error out)."""
    monkeypatch.setenv("GEMINI_DEFAULT_MODEL", "   ")
    import app.features.render.ai.llm.providers.gemini as _g
    importlib.reload(_g)
    try:
        assert _g._DEFAULT_MODEL == "gemini-2.5-flash"
    finally:
        monkeypatch.delenv("GEMINI_DEFAULT_MODEL", raising=False)
        importlib.reload(_g)


