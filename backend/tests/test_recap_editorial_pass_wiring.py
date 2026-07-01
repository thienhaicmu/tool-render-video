"""
test_recap_editorial_pass_wiring.py — guard for P0-2 (enable Editorial Blueprint).

Proves the recap dispatcher's pass-2 wiring end to end WITHOUT network:
  - flag ON  + a StoryModel present  → select_editorial_blueprint runs and its
    EditorialBlueprint is forwarded into the recap provider call.
  - flag OFF                          → pass-2 is skipped; recap call gets editorial=None.

This locks in the enablement so a future edit can't silently drop pass-2
(which would quietly regress recap pacing back to the single-call baseline).
"""
from __future__ import annotations

import app.core.config  # noqa: F401 — ensures .env is loaded before assertions
import app.features.render.ai.llm as llm
from app.domain.recap_plan import EditorialBlueprint, RecapPlan, StoryModel


def _wire_fakes(monkeypatch, *, flag_on: bool):
    """Install fakes for the editorial + recap provider calls and record usage.
    Returns the recorder dict."""
    rec = {"editorial_calls": 0, "recap_editorial_arg": "UNSET"}

    def fake_editorial(**kwargs):
        rec["editorial_calls"] += 1
        return EditorialBlueprint(episode_count=2, pacing="tense→calm")

    def fake_recap_impl(**kwargs):
        rec["recap_editorial_arg"] = kwargs.get("editorial")
        return RecapPlan()  # non-None → dispatcher returns it

    monkeypatch.setattr(llm, "_RECAP_EDITORIAL_PASS", flag_on)
    # Replace the module-level dispatcher fn (looked up as a global at call time).
    monkeypatch.setattr(llm, "select_editorial_blueprint", fake_editorial)
    monkeypatch.setattr(llm, "_get_recap_impl", lambda _p: fake_recap_impl)
    return rec


def test_pass2_runs_and_forwards_editorial_when_flag_on(monkeypatch):
    rec = _wire_fakes(monkeypatch, flag_on=True)
    # Passing story_model explicitly skips the pass-1 network call.
    story = StoryModel(summary="s", theme="t", conflict="c")
    out = llm.select_recap_plan(
        provider="gemini", srt_content="x", video_duration=100.0, story_model=story,
    )
    assert out is not None
    assert rec["editorial_calls"] == 1, "pass-2 editorial call should fire once"
    assert isinstance(rec["recap_editorial_arg"], EditorialBlueprint), \
        "editorial blueprint must be forwarded into the recap provider call"
    assert rec["recap_editorial_arg"].episode_count == 2


def test_pass2_skipped_when_flag_off(monkeypatch):
    rec = _wire_fakes(monkeypatch, flag_on=False)
    story = StoryModel(summary="s")
    out = llm.select_recap_plan(
        provider="gemini", srt_content="x", video_duration=100.0, story_model=story,
    )
    assert out is not None
    assert rec["editorial_calls"] == 0, "pass-2 must not run when flag is off"
    assert rec["recap_editorial_arg"] is None, "recap call should get editorial=None"


def test_pass2_skipped_when_no_story_model(monkeypatch):
    # Even with the flag on, no StoryModel means nothing to plan from — pass-2
    # must be skipped (guards the `story_model is not None` condition).
    rec = _wire_fakes(monkeypatch, flag_on=True)
    # Force pass-1 to yield None so story_model stays None going into pass-2.
    monkeypatch.setattr(llm, "_RECAP_TWO_PASS", True)
    monkeypatch.setattr(llm, "select_story_model", lambda **kw: None)
    out = llm.select_recap_plan(
        provider="gemini", srt_content="x", video_duration=100.0,
    )
    assert out is not None
    assert rec["editorial_calls"] == 0
    assert rec["recap_editorial_arg"] is None
