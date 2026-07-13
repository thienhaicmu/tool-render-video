"""
P1 — dedicated OpenAI Story super-plan raw call (F-04/F-06/F-09).

Pins:
  * llm._get_story_call_fn routes OpenAI through _call_openai_story_plan (not the
    shared Content-Mode call), so Story tuning stays isolated from Content Mode.
  * _call_openai_story_plan retries ONCE on an empty (non-raising) completion
    (F-09) and returns the recovered content.
  * Story-specific temperature/token budget knobs exist (F-06/F-04) and default
    to a cooler temperature than Content Mode.

Offline: the OpenAI SDK and the LLM cache are monkeypatched — no network.
"""
from __future__ import annotations

import app.features.render.ai.llm as L
import app.features.render.ai.llm.providers.openai as oai


def test_story_call_fn_uses_story_plan(monkeypatch):
    seen = {"n": 0, "args": None}

    def _fake(api_key, model, sys, usr):
        seen["n"] += 1
        seen["args"] = (api_key, model, sys, usr)
        return '{"ok": 1}'

    monkeypatch.setattr(oai, "_call_openai_story_plan", _fake)
    fn = L._get_story_call_fn("openai", "the-key", "gpt-4o")
    assert fn is not None
    assert fn("SYS", "USR") == '{"ok": 1}'
    assert seen["n"] == 1
    assert seen["args"] == ("the-key", "gpt-4o", "SYS", "USR")


def test_story_plan_retry_on_empty(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "solo")
    monkeypatch.setenv("OPENAI_STORY_PLAN_RETRY_EMPTY", "1")
    monkeypatch.setattr(oai, "llm_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(oai, "llm_cache_put", lambda *a, **k: True)

    attempts = {"n": 0}

    def _once(api_key, model, sys, usr):
        attempts["n"] += 1
        return "" if attempts["n"] == 1 else '{"recovered": true}'

    monkeypatch.setattr(oai, "_call_openai_story_plan_once", _once)
    out = oai._call_openai_story_plan("solo", "gpt-4o", "sys", "usr")
    assert out == '{"recovered": true}'
    assert attempts["n"] == 2                 # empty → one retry-on-empty


def test_story_plan_no_retry_when_disabled(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "solo")
    # Reload flag via monkeypatch on the resolved module constant.
    monkeypatch.setattr(oai, "_STORY_PLAN_RETRY_EMPTY", False)
    monkeypatch.setattr(oai, "llm_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(oai, "llm_cache_put", lambda *a, **k: True)

    attempts = {"n": 0}
    monkeypatch.setattr(
        oai, "_call_openai_story_plan_once",
        lambda *a: (attempts.__setitem__("n", attempts["n"] + 1) or ""),
    )
    assert oai._call_openai_story_plan("solo", "gpt-4o", "s", "u") in (None, "")
    assert attempts["n"] == 1                 # no retry-on-empty when disabled


def test_story_temperature_cooler_than_content():
    # F-06 — Story adapt must run cooler than Content Mode's 0.5 default.
    assert oai._STORY_PLAN_TEMPERATURE < oai._CONTENT_TEMPERATURE
    # F-04 — Story plan gets a larger token budget than the generic content call
    # default so a full ≤ceiling plan is not truncated.
    assert oai._STORY_PLAN_MAX_TOKENS >= oai._CONTENT_MAX_TOKENS
