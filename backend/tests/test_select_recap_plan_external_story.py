"""Architecture-review Batch C (2026-06-30) — external StoryModel into select_recap_plan.

Pins the Batch C addition: ``select_recap_plan(story_model=external_sm)`` skips
the internal pass-1 LLM call AND the ``on_pass1_done`` callback (because the
caller — the Comprehension pipeline stage — has already observed it through
its own WS events).

  1. External StoryModel provided → internal select_story_model NOT invoked.
  2. External StoryModel provided → on_pass1_done callback NOT fired.
  3. External StoryModel provided → editorial blueprint pass still runs against it.
  4. External StoryModel provided → final pass-3 binding receives the external one.
  5. story_model omitted (legacy) → Batch A path bit-identical: internal pass-1
     fires, on_pass1_done fires, on_pass2_done fires.
"""
from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest


@pytest.fixture
def llm_module(monkeypatch):
    monkeypatch.setenv("RECAP_TWO_PASS", "1")
    monkeypatch.setenv("RECAP_EDITORIAL_PASS", "1")
    import app.features.render.ai.llm as llm_pkg
    importlib.reload(llm_pkg)
    yield llm_pkg


def _stub_recap_plan():
    from app.domain.recap_plan import RecapPlan, Episode, Act, RecapScene
    return RecapPlan(
        total_target_sec=60.0,
        episodes=[Episode(title="Tập 1", acts=[
            Act(title="Setup", beat="setup", scenes=[RecapScene(start=0.0, end=30.0)]),
        ])],
    )


def _external_story():
    from app.domain.recap_plan import StoryModel, StoryBeat
    return StoryModel(
        summary="External story produced by the Comprehension stage.",
        beats=[StoryBeat(text="inciting", t=10.0)],
    )


def _editorial():
    from app.domain.recap_plan import EditorialBlueprint
    return EditorialBlueprint(episode_count=1, pacing="medium")


# ---------------------------------------------------------------------------
# External story skips internal pass-1
# ---------------------------------------------------------------------------


def test_external_story_skips_internal_pass1_call(llm_module):
    """The internal select_story_model dispatcher must NOT be invoked when the
    caller supplies a story_model."""
    external = _external_story()
    pass1_calls = {"n": 0}
    pass2_calls = []

    captured_kwargs = {}

    def fake_recap_impl(**kw):
        captured_kwargs.update(kw)
        return _stub_recap_plan()

    def fake_pass1(**kw):
        pass1_calls["n"] += 1
        return None

    with patch.object(llm_module, "select_story_model", side_effect=fake_pass1), \
         patch.object(llm_module, "select_editorial_blueprint", return_value=_editorial()), \
         patch.object(llm_module, "_get_recap_impl", return_value=fake_recap_impl):
        result = llm_module.select_recap_plan(
            provider="gemini", srt_content="x", video_duration=60.0,
            story_model=external,
            on_pass1_done=lambda m: pass2_calls.append(("p1", m)),
            on_pass2_done=lambda m: pass2_calls.append(("p2", m)),
        )

    assert result is not None
    assert pass1_calls["n"] == 0, "internal select_story_model must not run"
    # The on_pass1_done callback must NOT fire — the caller already observed
    # the StoryModel via the Comprehension stage's own WS events.
    assert not any(tag == "p1" for tag, _ in pass2_calls)
    # The external StoryModel reached the binding kwargs.
    assert captured_kwargs.get("story_model") is external


# ---------------------------------------------------------------------------
# External story still drives the editorial pass
# ---------------------------------------------------------------------------


def test_external_story_drives_editorial_pass(llm_module):
    external = _external_story()
    editorial_inputs = {}

    def fake_editorial(**kw):
        editorial_inputs.update(kw)
        return _editorial()

    pass2_models = []

    with patch.object(llm_module, "select_story_model", return_value=None), \
         patch.object(llm_module, "select_editorial_blueprint", side_effect=fake_editorial), \
         patch.object(llm_module, "_get_recap_impl", return_value=lambda **kw: _stub_recap_plan()):
        llm_module.select_recap_plan(
            provider="gemini", srt_content="x", video_duration=60.0,
            story_model=external,
            on_pass2_done=lambda m: pass2_models.append(m),
        )

    # Editorial pass got the externally-supplied StoryModel.
    assert editorial_inputs.get("story_model") is external
    # on_pass2_done still fires (Batch A behaviour preserved).
    assert len(pass2_models) == 1
    assert pass2_models[0] is not None


# ---------------------------------------------------------------------------
# Legacy path bit-identical
# ---------------------------------------------------------------------------


def test_legacy_path_without_story_model_still_runs_internal_pass1(llm_module):
    pass1_calls = []
    pass1_cb_calls = []

    def fake_pass1(**kw):
        pass1_calls.append(kw)
        return _external_story()

    with patch.object(llm_module, "select_story_model", side_effect=fake_pass1), \
         patch.object(llm_module, "select_editorial_blueprint", return_value=_editorial()), \
         patch.object(llm_module, "_get_recap_impl", return_value=lambda **kw: _stub_recap_plan()):
        llm_module.select_recap_plan(
            provider="gemini", srt_content="x", video_duration=60.0,
            on_pass1_done=lambda m: pass1_cb_calls.append(m),
        )

    # Internal pass-1 ran exactly once.
    assert len(pass1_calls) == 1
    # on_pass1_done fired exactly once (legacy callback contract — Batch A).
    assert len(pass1_cb_calls) == 1
    assert pass1_cb_calls[0] is not None


# ---------------------------------------------------------------------------
# story_model defaults to None (signature back-compat)
# ---------------------------------------------------------------------------


def test_story_model_default_is_none(llm_module):
    """Every pre-Batch-C caller passes no story_model — the default must keep
    them working without signature changes."""
    with patch.object(llm_module, "select_story_model", return_value=_external_story()), \
         patch.object(llm_module, "select_editorial_blueprint", return_value=_editorial()), \
         patch.object(llm_module, "_get_recap_impl", return_value=lambda **kw: _stub_recap_plan()):
        result = llm_module.select_recap_plan(
            provider="gemini", srt_content="x", video_duration=60.0,
        )
    assert result is not None
