"""
Phase 3 — per-role model routing defaults (2026-07-16 cost review).

Pins:
  * Default routing: Understanding + Structure ride the MINI tier
    (STORY_MINI_MODEL, default gpt-4o-mini); the Writer keeps the super model —
    it must never silently inherit the mini tier through the fallback chain.
  * An EXPLICIT user model (llm_model) pins all three roles (no mini).
  * STORY_MINI_ROUTING=0 restores the single-model default.
  * Per-role STORY_*_MODEL env still wins over the mini default.
  * Non-OpenAI providers keep their own provider defaults (no OpenAI mini name).
  * estimate_super_plan_cost prices the mini-routed calls at the mini rates.

Offline: _get_story_call_fn is monkeypatched to None — the role routes are read
from the provider_attempt observer event, no call is ever dispatched.
"""
from __future__ import annotations

import pytest

import app.features.render.ai.llm as L
from app.features.render.ai.llm.story_director_v2 import estimate_super_plan_cost


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("STORY_MINI_ROUTING", "STORY_MINI_MODEL", "STORY_SUPER_MODEL",
                "STORY_ROLE_ROUTING", "STORY_PROVIDER_FALLBACK",
                "STORY_STRUCTURE_PROVIDER", "STORY_WRITER_PROVIDER",
                "STORY_UNDERSTANDING_PROVIDER", "STORY_STRUCTURE_MODEL",
                "STORY_WRITER_MODEL", "STORY_UNDERSTANDING_MODEL",
                "LLM_DISABLED_PROVIDERS"):
        monkeypatch.delenv(var, raising=False)


def _routes(monkeypatch, *, provider="openai", model=None, env=None):
    """Run generate_story_plan_v2 far enough to capture role_routes, no calls."""
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(L, "_get_story_call_fn", lambda p, k, m: None)
    events = []
    out = L.generate_story_plan_v2(
        provider=provider, source="paste", chapter="text", api_key="k",
        model=model, resolve_key=lambda _p: "k", observer=events.append)
    assert out is None
    attempts = [e for e in events if e.get("event") == "provider_attempt"]
    assert attempts, "no provider_attempt captured"
    return attempts[0]["role_routes"]


def test_default_routes_mini_for_understanding_and_structure(monkeypatch):
    routes = _routes(monkeypatch)
    assert routes["understanding"]["model"] == "gpt-4o-mini"
    assert routes["structure"]["model"] == "gpt-4o-mini"
    assert routes["writer"]["model"] == "gpt-4o"          # never inherits mini


def test_explicit_user_model_pins_all_roles(monkeypatch):
    routes = _routes(monkeypatch, model="gpt-4.1")
    assert routes["understanding"]["model"] == "gpt-4.1"
    assert routes["writer"]["model"] == "gpt-4.1"
    assert routes["structure"]["model"] == "gpt-4.1"


def test_mini_routing_kill_switch(monkeypatch):
    routes = _routes(monkeypatch, env={"STORY_MINI_ROUTING": "0"})
    assert routes["understanding"]["model"] == "gpt-4o"
    assert routes["structure"]["model"] == "gpt-4o"
    assert routes["writer"]["model"] == "gpt-4o"


def test_role_env_beats_mini_default(monkeypatch):
    routes = _routes(monkeypatch, env={"STORY_STRUCTURE_MODEL": "custom-x"})
    assert routes["structure"]["model"] == "custom-x"
    assert routes["understanding"]["model"] == "gpt-4o-mini"


def test_mini_model_env_override(monkeypatch):
    routes = _routes(monkeypatch, env={"STORY_MINI_MODEL": "gpt-5-mini"})
    assert routes["understanding"]["model"] == "gpt-5-mini"
    assert routes["structure"]["model"] == "gpt-5-mini"


def test_non_openai_provider_keeps_provider_default(monkeypatch):
    routes = _routes(monkeypatch, provider="gemini")
    # gemini resolves model=None → "provider_default" label; the OpenAI mini
    # name must never be forced onto another provider's API.
    assert routes["understanding"]["model"] == "provider_default"
    assert routes["structure"]["model"] == "provider_default"
    assert routes["writer"]["model"] == "provider_default"


def test_estimate_mini_routing_is_cheaper(monkeypatch):
    monkeypatch.setenv("STORY_COMPILER", "1")
    monkeypatch.setenv("STORY_MINI_ROUTING", "1")
    mini = estimate_super_plan_cost(source_chars=15000, ceiling=10, source="paste")
    monkeypatch.setenv("STORY_MINI_ROUTING", "0")
    full = estimate_super_plan_cost(source_chars=15000, ceiling=10, source="paste")
    assert mini["cost_usd"] < full["cost_usd"]
    assert mini["llm_calls"] == full["llm_calls"] == 3
