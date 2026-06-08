"""Sacred Contract #3 tests — AI provider public entry points must return None
on any failure, never raise.

The contract: every public function under backend/app/features/render/ai/llm/
must catch all exceptions internally and return None. The render pipeline
treats None as "fall back / skip", but an uncaught exception kills the active
render job.

Verified entry points:
- llm/providers/claude.py::select_render_plan
- llm/providers/openai.py::select_render_plan
- llm/providers/gemini.py::select_render_plan
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
