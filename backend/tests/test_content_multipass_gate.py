"""test_content_multipass_gate.py — P2.1 Story Bible length gate.

The Content Director runs a two-pass plan: Pass A (Story Bible) then Pass B (the
plan). P2.1 skips the extra Pass A call for SHORT scripts (below
CONTENT_MULTIPASS_MIN_CHARS), where the bible rarely earns its cost. This test
spies on the shared _call_gemini_content to assert:

  - short script  → 1 LLM call  (Pass B only; no STORY EDITOR / bible call)
  - long  script  → 2 LLM calls (Pass A bible + Pass B plan)

Both still return a usable ContentPlan.
"""
from __future__ import annotations

import json

import app.features.render.ai.llm.providers.gemini as gem


def _install_spy(monkeypatch, threshold: int):
    """Force the two-pass path on, pin the char threshold, and replace the real
    Gemini call with a JSON-returning spy. Returns the list of system prompts
    seen (one per LLM call)."""
    seen: list[str] = []

    def _fake_call(api_key, model, system_prompt, user_prompt):
        seen.append(system_prompt)
        if "STORY EDITOR" in system_prompt:          # Pass A — Story Bible
            return json.dumps({
                "topic": "T", "tone": "documentary", "audience": "general",
                "characters": [{"id": "a", "name": "A", "description": "a canonical look"}],
            })
        return json.dumps({                           # Pass B — the plan
            "topic": "T", "scenes": [{"index": 0, "role": "hook", "narration": "hi there"}],
        })

    monkeypatch.setattr(gem, "_GENAI_SDK", True, raising=False)
    monkeypatch.setattr(gem, "_CONTENT_MULTIPASS", True, raising=False)
    monkeypatch.setattr(gem, "_CONTENT_MULTIPASS_MIN_CHARS", threshold, raising=False)
    monkeypatch.setattr(gem, "_call_gemini_content", _fake_call)
    return seen


def _bible_calls(seen: list[str]) -> int:
    return sum(1 for s in seen if "STORY EDITOR" in s)


def test_short_script_skips_story_bible(monkeypatch):
    seen = _install_spy(monkeypatch, threshold=50)
    plan = gem.select_content_plan(script="tiny script", api_key="k")  # len < 50
    assert plan is not None and plan.scene_count() == 1
    assert len(seen) == 1, f"expected only the plan call, got {seen}"
    assert _bible_calls(seen) == 0, "Story Bible must be skipped for a short script"


def test_long_script_runs_story_bible(monkeypatch):
    seen = _install_spy(monkeypatch, threshold=50)
    plan = gem.select_content_plan(script="x" * 200, api_key="k")       # len >= 50
    assert plan is not None and plan.scene_count() == 1
    assert len(seen) == 2, f"expected bible + plan calls, got {seen}"
    assert _bible_calls(seen) == 1, "Story Bible must run for a long script"


def test_threshold_zero_restores_always_on(monkeypatch):
    """CONTENT_MULTIPASS_MIN_CHARS=0 → the bible runs even for a 1-char script."""
    seen = _install_spy(monkeypatch, threshold=0)
    plan = gem.select_content_plan(script="x", api_key="k")
    assert plan is not None
    assert _bible_calls(seen) == 1, "threshold 0 must keep the two-pass always on"
