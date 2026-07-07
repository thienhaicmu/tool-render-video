"""test_content_provider_fallback.py — CM-2 real cross-provider Content fallback.

Before CM-2 only gemini implemented select_content_plan, so the dispatch chain's
"fallback to openai/claude" was a no-op. CM-2 moves the two-pass CU-4/5/6
orchestration into the shared content_director and gives openai + claude a thin
select_content_plan that binds their own content call. These tests prove:

  1. openai / claude select_content_plan actually produce a ContentPlan (their
     content call is mocked — no network),
  2. the dispatcher falls through gemini(None) → openai(plan),
  3. every provider's select_content_plan returns None (never raises) when its
     SDK / key is absent (Sacred Contract #3).
"""
from __future__ import annotations

import json

import app.features.render.ai.llm as dispatch
import app.features.render.ai.llm.providers.gemini as gem
import app.features.render.ai.llm.providers.openai as oai
import app.features.render.ai.llm.providers.claude as cla

# A short script keeps the two-pass gate on the single (plan) pass — one call.
_SHORT_SCRIPT = "a tiny script about cats"
_PLAN_JSON = json.dumps({
    "topic": "Cats", "scenes": [{"index": 0, "role": "hook", "narration": "hello cats"}],
})


def test_openai_select_content_plan_produces_plan(monkeypatch):
    monkeypatch.setattr(oai, "_OPENAI_SDK", True, raising=False)
    monkeypatch.setattr(oai, "_call_openai_content", lambda *a, **k: _PLAN_JSON)
    plan = oai.select_content_plan(script=_SHORT_SCRIPT, api_key="k")
    assert plan is not None and plan.scene_count() == 1
    assert plan.topic == "Cats"


def test_claude_select_content_plan_produces_plan(monkeypatch):
    monkeypatch.setattr(cla, "_ANTHROPIC_SDK", True, raising=False)
    monkeypatch.setattr(cla, "_call_claude_content", lambda *a, **k: _PLAN_JSON)
    plan = cla.select_content_plan(script=_SHORT_SCRIPT, api_key="k")
    assert plan is not None and plan.scene_count() == 1


def test_dispatch_falls_through_gemini_to_openai(monkeypatch):
    monkeypatch.setattr(dispatch, "_LLM_FALLBACK_ENABLED", True, raising=False)
    # A local .env may set LLM_DISABLED_PROVIDERS=openai,claude — clear it so the
    # fallback chain actually includes openai (the provider under test here).
    monkeypatch.setenv("LLM_DISABLED_PROVIDERS", "")
    # Primary gemini yields nothing; openai produces the plan.
    monkeypatch.setattr(gem, "select_content_plan", lambda **k: None)
    monkeypatch.setattr(cla, "select_content_plan", lambda **k: None)

    def _openai_plan(**k):
        from app.domain.content_plan import ContentPlan
        return ContentPlan.from_json(_PLAN_JSON)

    monkeypatch.setattr(oai, "select_content_plan", _openai_plan)
    plan = dispatch.select_content_plan(provider="gemini", script=_SHORT_SCRIPT, api_key="k")
    assert plan is not None and plan.topic == "Cats"


def test_dispatch_all_providers_none_returns_none(monkeypatch):
    monkeypatch.setattr(dispatch, "_LLM_FALLBACK_ENABLED", True, raising=False)
    # Exercise the FULL chain (gemini→openai→claude), not just gemini, in case a
    # local .env disables the fallback providers.
    monkeypatch.setenv("LLM_DISABLED_PROVIDERS", "")
    for mod in (gem, oai, cla):
        monkeypatch.setattr(mod, "select_content_plan", lambda **k: None)
    plan = dispatch.select_content_plan(provider="gemini", script=_SHORT_SCRIPT, api_key="k")
    assert plan is None


def test_openai_none_without_sdk(monkeypatch):
    monkeypatch.setattr(oai, "_OPENAI_SDK", False, raising=False)
    assert oai.select_content_plan(script=_SHORT_SCRIPT, api_key="k") is None


def test_claude_none_without_key(monkeypatch):
    monkeypatch.setattr(cla, "_ANTHROPIC_SDK", True, raising=False)
    assert cla.select_content_plan(script=_SHORT_SCRIPT, api_key="") is None


def test_provider_never_raises_on_call_exception(monkeypatch):
    """A raising content call must surface as None (Sacred #3), not propagate."""
    monkeypatch.setattr(oai, "_OPENAI_SDK", True, raising=False)

    def _boom(*a, **k):
        raise RuntimeError("api exploded")

    monkeypatch.setattr(oai, "_call_openai_content", _boom)
    # content_director wraps the call — the provider returns None cleanly.
    assert oai.select_content_plan(script=_SHORT_SCRIPT, api_key="k") is None
