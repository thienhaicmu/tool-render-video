"""Integration tests: LLM cache short-circuits provider _call_*_once
(audit AI06 wire-in verification).

Confirms each of the three providers consults the cache BEFORE invoking
its retry-wrapped SDK call. On a cache hit, the SDK is never touched —
the cached response flows straight to the parser.

These tests run with no SDK installed: the providers use lazy SDK
imports gated by a module-level flag (_ANTHROPIC_SDK / _OPENAI_SDK /
_GENAI_SDK). The cache check happens before those guards, so even on a
system without the cloud SDK installed, a previously cached response is
served correctly.
"""
from __future__ import annotations

import pytest

from app.features.render.ai.llm import cache as llm_cache
from app.features.render.ai.llm.cache import (
    llm_cache_clear,
    llm_cache_get,
    llm_cache_put,
)
from app.features.render.ai.llm.providers import claude as claude_mod
from app.features.render.ai.llm.providers import gemini as gemini_mod
from app.features.render.ai.llm.providers import openai as openai_mod


_PROVIDERS = [
    pytest.param(claude_mod, "claude", "_call_claude_once",
                 "_call_claude", id="claude"),
    pytest.param(openai_mod, "openai", "_call_openai_once",
                 "_call_openai", id="openai"),
    pytest.param(gemini_mod, "gemini", "_call_gemini_once",
                 "_call_gemini", id="gemini"),
]


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """Redirect APP_DATA_DIR so the test never touches the real cache."""
    monkeypatch.setattr(llm_cache, "APP_DATA_DIR", tmp_path, raising=False)
    llm_cache_clear()
    yield
    llm_cache_clear()


@pytest.mark.parametrize("module,label,once_name,wrapper_name", _PROVIDERS)
def test_cache_hit_short_circuits_sdk_call(
    module, label, once_name, wrapper_name, monkeypatch
):
    """Pre-seed the cache. The wrapper must return the cached value
    without invoking _call_*_once even a single time.
    """
    sdk_called = {"count": 0}

    def _track_call(api_key, model, system_prompt, user_prompt):
        sdk_called["count"] += 1
        return "FROM_SDK"

    monkeypatch.setattr(module, once_name, _track_call)

    # Pre-seed cache for THIS provider's exact inputs.
    llm_cache_put(label, "test-model", "sys-prompt", "user-prompt", "FROM_CACHE")

    wrapper = getattr(module, wrapper_name)
    result = wrapper(
        api_key="test-key",
        model="test-model",
        system_prompt="sys-prompt",
        user_prompt="user-prompt",
    )
    assert result == "FROM_CACHE"
    assert sdk_called["count"] == 0, (
        f"{label}: SDK was invoked despite a cache hit — cache wiring is broken."
    )


@pytest.mark.parametrize("module,label,once_name,wrapper_name", _PROVIDERS)
def test_cache_miss_calls_sdk_and_writes_back(
    module, label, once_name, wrapper_name, monkeypatch
):
    """On a cache miss, the wrapper must call the SDK and then store
    the result for the next call.
    """
    sdk_called = {"count": 0}

    def _track_call(api_key, model, system_prompt, user_prompt):
        sdk_called["count"] += 1
        return "FROM_SDK_FRESH"

    monkeypatch.setattr(module, once_name, _track_call)

    wrapper = getattr(module, wrapper_name)
    result = wrapper(
        api_key="test-key",
        model="test-model",
        system_prompt="sys-prompt",
        user_prompt="user-prompt-miss",
    )
    assert result == "FROM_SDK_FRESH"
    assert sdk_called["count"] == 1

    # Now the cache holds the response — a second call must be a hit.
    result2 = wrapper(
        api_key="test-key",
        model="test-model",
        system_prompt="sys-prompt",
        user_prompt="user-prompt-miss",
    )
    assert result2 == "FROM_SDK_FRESH"
    assert sdk_called["count"] == 1, (
        f"{label}: SDK was re-invoked on a hit after a fresh write."
    )


@pytest.mark.parametrize("module,label,once_name,wrapper_name", _PROVIDERS)
def test_sdk_failure_is_not_cached(
    module, label, once_name, wrapper_name, monkeypatch
):
    """When the SDK raises (and the retry wrapper exhausts), the
    wrapper returns None. That None must NOT poison the cache for the
    next request — the next attempt should retry the SDK.
    """
    sdk_called = {"count": 0}

    def _always_raises(api_key, model, system_prompt, user_prompt):
        sdk_called["count"] += 1
        raise RuntimeError("simulated SDK outage")

    monkeypatch.setattr(module, once_name, _always_raises)
    # Bypass real time.sleep so the retry test runs fast.
    import app.features.render.ai.llm.retry as retry_mod
    monkeypatch.setattr(retry_mod.time, "sleep", lambda *_: None)

    wrapper = getattr(module, wrapper_name)
    result = wrapper(
        api_key="test-key",
        model="m",
        system_prompt="s",
        user_prompt="u",
    )
    assert result is None
    sdk_count_after_first = sdk_called["count"]
    assert sdk_count_after_first >= 1

    # Cache must still be empty — a subsequent call retries the SDK.
    assert llm_cache_get(label, "m", "s", "u") is None
    result2 = wrapper(
        api_key="test-key",
        model="m",
        system_prompt="s",
        user_prompt="u",
    )
    assert result2 is None
    assert sdk_called["count"] > sdk_count_after_first, (
        f"{label}: failure was cached — second attempt did not re-call SDK."
    )


@pytest.mark.parametrize("module,label,once_name,wrapper_name", _PROVIDERS)
def test_different_models_get_separate_cache_entries(
    module, label, once_name, wrapper_name, monkeypatch
):
    """Switching model on the same prompt must miss the cache."""
    sdk_called = {"count": 0}

    def _track_call(api_key, model, system_prompt, user_prompt):
        sdk_called["count"] += 1
        return f"FROM_SDK_{model}"

    monkeypatch.setattr(module, once_name, _track_call)
    wrapper = getattr(module, wrapper_name)

    r1 = wrapper(api_key="k", model="modelA", system_prompt="s", user_prompt="u")
    r2 = wrapper(api_key="k", model="modelB", system_prompt="s", user_prompt="u")
    assert r1 == "FROM_SDK_modelA"
    assert r2 == "FROM_SDK_modelB"
    assert sdk_called["count"] == 2, (
        f"{label}: model change did not invalidate cache key."
    )
