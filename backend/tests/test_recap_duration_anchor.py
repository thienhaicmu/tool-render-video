"""
test_recap_duration_anchor.py — guard for the duration-anchor prompt fix.

Structural measurement (n=5) showed the editorial-ON recap path cannot hold
the prompt's own 10–25%-of-runtime spec (observed 4%–96%). The fix anchors a
concrete seconds budget in pass-2 and a HARD guardrail in pass-3 — but ONLY
when an editorial blueprint is present. These tests pin:
  - budget present with correct seconds on the editorial-ON path (both passes)
  - editorial-OFF prompt untouched (no budget text)
  - RECAP_DURATION_ANCHOR=0 kill switch removes it everywhere
  - format safety survives (blocks are .format values)
"""
from __future__ import annotations

from app.domain.recap_plan import EditorialBlueprint, EditorialBeat, StoryModel
from app.features.render.ai.llm.recap_prompts import (
    build_editorial_prompt,
    build_recap_prompt,
)

_DUR = 5447.0                      # the real test film
_LO, _HI = int(_DUR * 0.10), int(_DUR * 0.25)   # 544, 1361
_SRT = "1\n00:00:01,000 --> 00:00:03,000\nhello {braces} world\n"


def _editorial():
    return EditorialBlueprint(episode_count=2, pacing="tense",
                              beats=[EditorialBeat(summary="turn", treatment="hold")])


# ── pass-3 (recap binding) ───────────────────────────────────────────────────

def test_pass3_hard_budget_present_with_editorial(monkeypatch):
    monkeypatch.delenv("RECAP_DURATION_ANCHOR", raising=False)   # default ON
    _, user = build_recap_prompt(_SRT, _DUR, story_model=StoryModel(summary="s"),
                                 editorial=_editorial())
    assert "DURATION BUDGET (HARD" in user
    assert f"between {_LO} and {_HI} seconds" in user
    assert "at least 8" in user
    assert "the budget wins" in user


def test_pass3_no_budget_without_editorial(monkeypatch):
    # Editorial-OFF path must stay byte-identical: no budget text at all.
    monkeypatch.delenv("RECAP_DURATION_ANCHOR", raising=False)
    _, user = build_recap_prompt(_SRT, _DUR, story_model=StoryModel(summary="s"),
                                 editorial=None)
    assert "DURATION BUDGET (HARD" not in user


def test_pass3_kill_switch(monkeypatch):
    monkeypatch.setenv("RECAP_DURATION_ANCHOR", "0")
    _, user = build_recap_prompt(_SRT, _DUR, story_model=StoryModel(summary="s"),
                                 editorial=_editorial())
    assert "DURATION BUDGET (HARD" not in user


def test_pass3_format_safe_with_braces_everywhere(monkeypatch):
    # Story summary + transcript both carry braces; the budget block must not
    # break str.format on the template.
    monkeypatch.delenv("RECAP_DURATION_ANCHOR", raising=False)
    story = StoryModel(summary="uses {key: value} maps")
    _, user = build_recap_prompt(_SRT, _DUR, story_model=story, editorial=_editorial())
    assert "DURATION BUDGET (HARD" in user            # rendered, no exception


# ── pass-2 (editorial blueprint) ─────────────────────────────────────────────

def test_pass2_budget_line_with_concrete_seconds(monkeypatch):
    monkeypatch.delenv("RECAP_DURATION_ANCHOR", raising=False)
    _, user = build_editorial_prompt(StoryModel(summary="s"), _DUR)
    assert "DURATION BUDGET" in user
    assert f"{_LO}-{_HI} seconds" in user


def test_pass2_kill_switch_and_unknown_duration(monkeypatch):
    monkeypatch.setenv("RECAP_DURATION_ANCHOR", "0")
    _, user = build_editorial_prompt(StoryModel(summary="s"), _DUR)
    assert "DURATION BUDGET" not in user
    monkeypatch.delenv("RECAP_DURATION_ANCHOR", raising=False)
    _, user2 = build_editorial_prompt(StoryModel(summary="s"), 0.0)
    assert "DURATION BUDGET" not in user2             # unknown duration → no line
