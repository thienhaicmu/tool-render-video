"""Sacred Contract #3 tests — AI provider public entry points must return None
on any failure, never raise.

The contract: every public function under backend/app/features/render/ai/llm/
must catch all exceptions internally and return None. The render pipeline
treats None as "fall back / skip", but an uncaught exception kills the active
render job. The previous Phase F1 design moved the hard-fail upstream to
llm_pipeline.py — but each provider must still honour Contract #3 at its own
public boundary.

Verified entry points:
- llm/providers/claude.py::select_segments / select_render_plan
- llm/providers/openai.py::select_segments / select_render_plan
- llm/providers/gemini.py::select_segments / select_render_plan
"""
from __future__ import annotations

import pytest

from app.features.render.ai.llm.providers import claude as claude_mod
from app.features.render.ai.llm.providers import openai as openai_mod
from app.features.render.ai.llm.providers import gemini as gemini_mod


PROVIDERS = pytest.mark.parametrize(
    "module",
    [claude_mod, openai_mod, gemini_mod],
    ids=["claude", "openai", "gemini"],
)


# ---------------------------------------------------------------------------
# select_segments
# ---------------------------------------------------------------------------

@PROVIDERS
def test_select_segments_no_api_key_returns_none(module):
    """Missing API key must short-circuit to None, never raise."""
    result = module.select_segments(
        srt_content="1\n00:00:00,000 --> 00:00:05,000\nhello\n",
        output_count=1,
        min_sec=2.0,
        max_sec=10.0,
        video_duration=60.0,
        api_key="",  # explicit empty
        model=None,
        language="auto",
    )
    assert result is None


@PROVIDERS
def test_select_segments_empty_srt_returns_none(module):
    """Empty transcript must short-circuit to None, never raise."""
    result = module.select_segments(
        srt_content="",
        output_count=1,
        min_sec=2.0,
        max_sec=10.0,
        video_duration=60.0,
        api_key="dummy-key-for-test",
        model=None,
        language="auto",
    )
    assert result is None


@PROVIDERS
def test_select_segments_whitespace_srt_returns_none(module):
    """Whitespace-only SRT must short-circuit to None, never raise."""
    result = module.select_segments(
        srt_content="   \n\t\n  ",
        output_count=1,
        min_sec=2.0,
        max_sec=10.0,
        video_duration=60.0,
        api_key="dummy-key-for-test",
        model=None,
        language="auto",
    )
    assert result is None


@PROVIDERS
def test_select_segments_sdk_raises_returns_none(module, monkeypatch):
    """A raising SDK call must be caught and converted to None.

    Monkey-patches the inner _run to raise, which exercises the outer
    try/except in select_segments. This is the exact contract: an unexpected
    failure in the inner call path becomes a None return at the public
    boundary.
    """
    def boom(**kwargs):
        raise RuntimeError("simulated SDK failure")

    monkeypatch.setattr(module, "_run", boom)

    result = module.select_segments(
        srt_content="1\n00:00:00,000 --> 00:00:05,000\nhello\n",
        output_count=1,
        min_sec=2.0,
        max_sec=10.0,
        video_duration=60.0,
        api_key="dummy-key-for-test",
        model=None,
        language="auto",
    )
    assert result is None


# ---------------------------------------------------------------------------
# select_render_plan
# ---------------------------------------------------------------------------

@PROVIDERS
def test_select_render_plan_no_api_key_returns_none(module):
    result = module.select_render_plan(
        srt_content="1\n00:00:00,000 --> 00:00:05,000\nhello\n",
        output_count=1,
        min_sec=2.0,
        max_sec=10.0,
        video_duration=60.0,
        api_key="",
        model=None,
        language="auto",
        editorial_hint="",
    )
    assert result is None


@PROVIDERS
def test_select_render_plan_empty_srt_returns_none(module):
    result = module.select_render_plan(
        srt_content="",
        output_count=1,
        min_sec=2.0,
        max_sec=10.0,
        video_duration=60.0,
        api_key="dummy-key-for-test",
        model=None,
        language="auto",
        editorial_hint="",
    )
    assert result is None


@PROVIDERS
def test_select_render_plan_sdk_raises_returns_none(module, monkeypatch):
    def boom(**kwargs):
        raise RuntimeError("simulated SDK failure")

    monkeypatch.setattr(module, "_run_render_plan", boom)

    result = module.select_render_plan(
        srt_content="1\n00:00:00,000 --> 00:00:05,000\nhello\n",
        output_count=1,
        min_sec=2.0,
        max_sec=10.0,
        video_duration=60.0,
        api_key="dummy-key-for-test",
        model=None,
        language="auto",
        editorial_hint="",
    )
    assert result is None
