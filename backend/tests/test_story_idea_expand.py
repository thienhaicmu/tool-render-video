"""s21 — Story idea: SKELETON/DRAMATIZE prompt + escalate-and-regenerate length loop.

Covers:
  · build_super_idea_prompt — skeleton/dramatize brief + length_factor override
  · story_director_v2._plan_idea_with_expand — bounded regenerate-when-short loop,
    keeps the plan closest to target, never raises (Sacred Contract #3).
"""
from __future__ import annotations

import re

from app.features.render.ai.llm import story_director_v2 as sd
from app.features.render.ai.llm.story_prompts_v2 import build_super_idea_prompt


# ── Prompt ───────────────────────────────────────────────────────────────────

def _budget(user: str) -> int:
    m = re.search(r"about ([\d,]+) CHARACTERS", user)
    return int(m.group(1).replace(",", "")) if m else 0


def test_idea_prompt_dramatize_instruction_present_with_duration():
    _, u = build_super_idea_prompt("some idea", 120, language="vi")
    assert "never the script" in u          # brief-only skeleton clause
    assert "DRAMATIZE" in u


def test_idea_prompt_no_budget_drops_brief_skeleton_clause():
    # no duration + no env default → budget 0 → brief is "model decides"; the
    # brief-only "never the script" clause must be absent (header may still mention it).
    _, u = build_super_idea_prompt("some idea", 0, language="vi")
    assert "model decides" in u
    assert "never the script" not in u


def test_length_factor_override_increases_budget():
    _, u1 = build_super_idea_prompt("idea", 120, language="vi", length_factor=1.0)
    _, u5 = build_super_idea_prompt("idea", 120, language="vi", length_factor=5.0)
    assert _budget(u5) > _budget(u1) > 0


def test_length_factor_zero_uses_default(monkeypatch):
    monkeypatch.setenv("STORY_IDEA_LENGTH_FACTOR", "2.0")
    _, u = build_super_idea_prompt("idea", 100, language="vi", length_factor=0.0)
    # 100s * 2.0 * cps(vi=15) = 3000
    assert _budget(u) == 3000


# ── Expand loop ──────────────────────────────────────────────────────────────

class _FakePlan:
    def __init__(self, est: float):
        self._est = est
        self.language = ""

    def estimated_total_sec(self) -> float:
        return self._est


def _patch_plans(monkeypatch, plans):
    """Make _call_and_parse hand back the queued plans in order; record call count."""
    calls = {"n": 0}
    seq = list(plans)

    def fake(call_fn, sysm, user, ceiling):
        i = calls["n"]
        calls["n"] += 1
        return seq[i] if i < len(seq) else None

    monkeypatch.setattr(sd, "_call_and_parse", fake)
    return calls


def _run(**over):
    kw = dict(call_fn=lambda s, u: "x", idea="idea", duration_sec=120, genre="",
              language="vi", art_style="", aspect_ratio="16:9", subtitle_mode="hook_only",
              ceiling=15, prior_context="", library_catalog="", provider_label="?")
    kw.update(over)
    return sd._plan_idea_with_expand(
        kw["call_fn"], kw["idea"], kw["duration_sec"], kw["genre"], kw["language"],
        kw["art_style"], kw["aspect_ratio"], kw["subtitle_mode"], kw["ceiling"],
        kw["prior_context"], kw["library_catalog"], kw["provider_label"])


def test_expand_regenerates_when_short(monkeypatch):
    calls = _patch_plans(monkeypatch, [_FakePlan(38.0), _FakePlan(120.0)])
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "1")
    out = _run()
    assert out.estimated_total_sec() == 120.0   # kept the longer, on-target plan
    assert calls["n"] == 2                       # first + one escalated retry


def test_expand_disabled_when_tries_zero(monkeypatch):
    calls = _patch_plans(monkeypatch, [_FakePlan(38.0), _FakePlan(120.0)])
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "0")
    out = _run()
    assert out.estimated_total_sec() == 38.0
    assert calls["n"] == 1


def test_expand_noop_when_first_plan_long_enough(monkeypatch):
    calls = _patch_plans(monkeypatch, [_FakePlan(130.0), _FakePlan(400.0)])
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "1")
    out = _run()
    assert out.estimated_total_sec() == 130.0   # >= 0.7*120 floor → no retry
    assert calls["n"] == 1


def test_expand_keeps_first_when_retry_fails(monkeypatch):
    calls = _patch_plans(monkeypatch, [_FakePlan(38.0), None])   # retry returns None
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "1")
    out = _run()
    assert out.estimated_total_sec() == 38.0
    assert calls["n"] == 2


def test_expand_none_first_is_safe(monkeypatch):
    calls = _patch_plans(monkeypatch, [None])
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "1")
    assert _run() is None
    assert calls["n"] == 1


def test_expand_no_duration_skips_loop(monkeypatch):
    calls = _patch_plans(monkeypatch, [_FakePlan(38.0), _FakePlan(120.0)])
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "1")
    out = _run(duration_sec=0)
    assert out.estimated_total_sec() == 38.0
    assert calls["n"] == 1


def test_expand_prefers_longer_when_all_short(monkeypatch):
    # both under the floor → keep the longest (short is failure; get as close as we can)
    calls = _patch_plans(monkeypatch, [_FakePlan(40.0), _FakePlan(70.0)])
    monkeypatch.setenv("STORY_IDEA_EXPAND_TRIES", "1")
    out = _run()
    assert out.estimated_total_sec() == 70.0
    assert calls["n"] == 2
