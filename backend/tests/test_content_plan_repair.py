"""test_content_plan_repair.py — CM-8 prompt versioning + one-shot JSON repair.

When the deterministic parser (strict → substring → balance-close salvage) still
can't recover a ContentPlan, run_content_director issues ONE repair pass asking
the model to fix its own output, then parses again — recovering a plan that would
otherwise fail the whole render. Gated by CONTENT_PLAN_REPAIR (default on).
call_fn is a stub so no network is touched. A short script keeps the two-pass
gate on the single (plan) pass.
"""
from __future__ import annotations

import json

import app.features.render.ai.llm.content_director as director
from app.features.render.ai.llm.content_prompts import CONTENT_PLAN_PROMPT_VERSION

_SHORT = "short script about cats"
_VALID = json.dumps({"topic": "Cats", "scenes": [{"index": 0, "role": "hook", "narration": "hi"}]})
_GARBAGE = "sorry, here is your plan: not really json {["


def test_repair_recovers_malformed_plan(monkeypatch):
    monkeypatch.setenv("CONTENT_PLAN_REPAIR", "1")
    seen: list[str] = []

    def _call(system: str, user: str):
        seen.append(system)
        # The repair pass is identified by its system prompt.
        return _VALID if "repair tool" in system.lower() else _GARBAGE

    plan = director.run_content_director(call_fn=_call, script=_SHORT, provider_label="test")
    assert plan is not None and plan.scene_count() == 1
    assert plan.topic == "Cats"
    assert any("repair tool" in s.lower() for s in seen), "repair pass should have run"


def test_repair_disabled_returns_none(monkeypatch):
    monkeypatch.setenv("CONTENT_PLAN_REPAIR", "0")
    seen: list[str] = []

    def _call(system: str, user: str):
        seen.append(system)
        return _GARBAGE

    plan = director.run_content_director(call_fn=_call, script=_SHORT, provider_label="test")
    assert plan is None
    assert not any("repair tool" in s.lower() for s in seen), "repair must be skipped when disabled"


def test_no_repair_when_plan_parses(monkeypatch):
    monkeypatch.setenv("CONTENT_PLAN_REPAIR", "1")
    seen: list[str] = []

    def _call(system: str, user: str):
        seen.append(system)
        return _VALID

    plan = director.run_content_director(call_fn=_call, script=_SHORT, provider_label="test")
    assert plan is not None
    assert not any("repair tool" in s.lower() for s in seen), "no repair when the plan already parses"


def test_repair_still_bad_returns_none(monkeypatch):
    monkeypatch.setenv("CONTENT_PLAN_REPAIR", "1")

    def _call(system: str, user: str):
        return _GARBAGE  # even the repair pass fails to produce valid JSON

    plan = director.run_content_director(call_fn=_call, script=_SHORT, provider_label="test")
    assert plan is None  # Sacred Contract #3 — clean None, not a raise


def test_prompt_version_present():
    assert isinstance(CONTENT_PLAN_PROMPT_VERSION, str) and CONTENT_PLAN_PROMPT_VERSION
