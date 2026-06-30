"""Architecture-review Batch A — Story Intelligence pass callbacks.

Pins the contract for ``select_recap_plan(on_pass1_done=..., on_pass2_done=...)``:

  1. ``on_pass1_done`` fires exactly once when pass-1 is enabled
     (RECAP_TWO_PASS=1), with the produced StoryModel or None on failure.
  2. ``on_pass2_done`` fires exactly once when pass-2 is enabled
     (RECAP_EDITORIAL_PASS=1) AND pass-1 produced a model.
  3. ``on_pass2_done`` is SKIPPED when pass-1 failed (no story → no pass-2).
  4. A callback that raises does NOT break the dispatch — the LLM call
     still returns the RecapPlan, and the exception is swallowed.
  5. Both callbacks default to ``None`` so existing callers (every site
     pre-Batch-A) keep working with no signature change required.
"""
from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


@pytest.fixture
def llm_module(monkeypatch):
    """Reload the llm dispatcher after toggling the pass-gate env vars so
    the module-level constants pick up the test settings."""
    monkeypatch.setenv("RECAP_TWO_PASS", "1")
    monkeypatch.setenv("RECAP_EDITORIAL_PASS", "1")
    import app.features.render.ai.llm as llm_pkg
    importlib.reload(llm_pkg)
    yield llm_pkg


def _stub_recap_plan():
    """Build a minimal valid RecapPlan so the dispatch loop short-circuits."""
    from app.domain.recap_plan import RecapPlan, Episode, Act, RecapScene
    return RecapPlan(
        total_target_sec=60.0,
        episodes=[Episode(title="Tập 1", acts=[
            Act(title="Setup", beat="setup", scenes=[RecapScene(start=0.0, end=30.0)]),
        ])],
    )


def _stub_story_model(empty: bool = False):
    from app.domain.recap_plan import StoryModel
    if empty:
        return None
    return StoryModel(summary="Test story summary.")


def _stub_editorial(empty: bool = False):
    from app.domain.recap_plan import EditorialBlueprint
    if empty:
        return None
    return EditorialBlueprint(episode_count=1, pacing="medium")


def test_pass1_callback_fires_once_with_story_model(llm_module):
    pass1_calls = []
    pass2_calls = []
    with patch.object(llm_module, "select_story_model", return_value=_stub_story_model()), \
         patch.object(llm_module, "select_editorial_blueprint", return_value=_stub_editorial()), \
         patch.object(llm_module, "_get_recap_impl", return_value=lambda **kw: _stub_recap_plan()):
        result = llm_module.select_recap_plan(
            provider="gemini", srt_content="00:00:00,000 --> 00:00:10,000\nhello",
            video_duration=60.0,
            on_pass1_done=lambda m: pass1_calls.append(m),
            on_pass2_done=lambda m: pass2_calls.append(m),
        )
    assert result is not None
    assert len(pass1_calls) == 1
    assert pass1_calls[0] is not None
    assert pass1_calls[0].summary == "Test story summary."
    assert len(pass2_calls) == 1
    assert pass2_calls[0] is not None


def test_pass1_callback_fires_with_none_on_failure(llm_module):
    pass1_calls = []
    pass2_calls = []
    with patch.object(llm_module, "select_story_model", return_value=None), \
         patch.object(llm_module, "select_editorial_blueprint", return_value=_stub_editorial()), \
         patch.object(llm_module, "_get_recap_impl", return_value=lambda **kw: _stub_recap_plan()):
        llm_module.select_recap_plan(
            provider="gemini", srt_content="x", video_duration=60.0,
            on_pass1_done=lambda m: pass1_calls.append(m),
            on_pass2_done=lambda m: pass2_calls.append(m),
        )
    # Pass 1 still fires — with None — so the UI knows the pass ran and produced nothing.
    assert pass1_calls == [None]
    # Pass 2 is gated on pass-1 success → it must NOT have run.
    assert pass2_calls == []


def test_pass2_skipped_when_pass1_failed(llm_module):
    """Contract: pass-2 requires a non-empty StoryModel from pass-1."""
    pass2_calls = []
    with patch.object(llm_module, "select_story_model", return_value=None), \
         patch.object(llm_module, "select_editorial_blueprint", return_value=_stub_editorial()) as p2_mock, \
         patch.object(llm_module, "_get_recap_impl", return_value=lambda **kw: _stub_recap_plan()):
        llm_module.select_recap_plan(
            provider="gemini", srt_content="x", video_duration=60.0,
            on_pass2_done=lambda m: pass2_calls.append(m),
        )
    assert p2_mock.call_count == 0, "select_editorial_blueprint must not be invoked when pass-1 failed"
    assert pass2_calls == []


def test_callback_raise_does_not_break_dispatch(llm_module):
    """A buggy callback must not abort the LLM call — it's pure observation."""
    def boom(_):
        raise RuntimeError("test callback failure")

    with patch.object(llm_module, "select_story_model", return_value=_stub_story_model()), \
         patch.object(llm_module, "select_editorial_blueprint", return_value=_stub_editorial()), \
         patch.object(llm_module, "_get_recap_impl", return_value=lambda **kw: _stub_recap_plan()):
        result = llm_module.select_recap_plan(
            provider="gemini", srt_content="x", video_duration=60.0,
            on_pass1_done=boom,
            on_pass2_done=boom,
        )
    assert result is not None  # dispatch survived both callbacks raising


def test_callbacks_default_to_none(llm_module):
    """Existing callers (every site pre-Batch-A) keep working — no kwargs required."""
    with patch.object(llm_module, "select_story_model", return_value=_stub_story_model()), \
         patch.object(llm_module, "select_editorial_blueprint", return_value=_stub_editorial()), \
         patch.object(llm_module, "_get_recap_impl", return_value=lambda **kw: _stub_recap_plan()):
        result = llm_module.select_recap_plan(
            provider="gemini", srt_content="x", video_duration=60.0,
        )
    assert result is not None


def test_safe_callback_handles_none(llm_module):
    """The _safe_callback helper is a no-op when no callback is registered."""
    # Should not raise.
    llm_module._safe_callback(None)
    llm_module._safe_callback(None, "ignored", x=1)


def test_safe_callback_swallows_exception(llm_module):
    def boom(*a, **kw):
        raise ValueError("boom")
    # Should not raise.
    llm_module._safe_callback(boom, "x")
