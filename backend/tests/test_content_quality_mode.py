"""test_content_quality_mode.py — CM-7 multi-step "quality" planning mode.

CONTENT_PLAN_MODE=quality adds ONE focused narration-refine pass over the planned
scenes (reusing the existing refine prompt + parser via call_fn — no new prompt)
so voice-over flows scene→scene and each scene's length matches its planned
seconds. Default "fast" = single plan pass, unchanged (zero regression). A short
script keeps the two-pass gate off (bible skipped), so the only extra call is the
refine one. call_fn is a stub — no network.
"""
from __future__ import annotations

import json

import app.features.render.ai.llm.content_director as director

_SHORT = "short script about cats"
_PLAN = json.dumps({
    "topic": "Cats",
    "scenes": [
        {"index": 0, "role": "hook", "narration": "orig one"},
        {"index": 1, "role": "conclusion", "narration": "orig two"},
    ],
})
_REFINE = json.dumps({"narration": [
    {"index": 0, "text": "refined one"},
    {"index": 1, "text": "refined two"},
]})


def _router(refine_out: str):
    """call_fn stub: 'scriptwriter' system → the refine pass; else the plan pass.
    Records the system prompts seen so a test can assert the refine ran or not."""
    seen: list[str] = []

    def _call(system: str, user: str):
        seen.append(system)
        if "scriptwriter" in system.lower():
            return refine_out
        return _PLAN

    return _call, seen


def test_quality_mode_refines_narration(monkeypatch):
    monkeypatch.setenv("CONTENT_PLAN_MODE", "quality")
    call, seen = _router(_REFINE)
    plan = director.run_content_director(call_fn=call, script=_SHORT, provider_label="test")
    assert plan is not None and plan.scene_count() == 2
    assert plan.scenes[0].narration == "refined one"
    assert plan.scenes[1].narration == "refined two"
    assert any("scriptwriter" in s.lower() for s in seen), "refine pass should have run"


def test_fast_mode_skips_refine(monkeypatch):
    monkeypatch.setenv("CONTENT_PLAN_MODE", "fast")
    call, seen = _router(_REFINE)
    plan = director.run_content_director(call_fn=call, script=_SHORT, provider_label="test")
    assert plan is not None
    assert plan.scenes[0].narration == "orig one"  # untouched
    assert not any("scriptwriter" in s.lower() for s in seen), "fast mode must not refine"


def test_default_mode_is_fast(monkeypatch):
    monkeypatch.delenv("CONTENT_PLAN_MODE", raising=False)
    call, seen = _router(_REFINE)
    plan = director.run_content_director(call_fn=call, script=_SHORT, provider_label="test")
    assert plan is not None
    assert plan.scenes[0].narration == "orig one"
    assert not any("scriptwriter" in s.lower() for s in seen)


def test_quality_refine_failure_keeps_original(monkeypatch):
    monkeypatch.setenv("CONTENT_PLAN_MODE", "quality")
    call, _seen = _router("not valid json {[")  # refine pass yields garbage
    plan = director.run_content_director(call_fn=call, script=_SHORT, provider_label="test")
    assert plan is not None
    assert plan.scenes[0].narration == "orig one"  # best-effort: original kept
    assert plan.scenes[1].narration == "orig two"
