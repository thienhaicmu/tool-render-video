"""
F-03 — OpenAI multi-key rotation for the Story/Content super-plan raw call.

Pins two guarantees:
  1. pool_for("openai") sources OPENAI_API_KEYS / OPENAI_API_KEY and places the
     resolved seed key first, deduped — a single-key deployment yields len==1
     (so _call_openai_content stays on the byte-identical call_with_retry path).
  2. When a pool (>1 key) is configured, _call_openai_content rotates OFF a
     rate-limited (429) key onto the next pool key instead of failing the render.

Deterministic + offline: the OpenAI SDK is never touched — we monkeypatch the
single-attempt _call_openai_content_once and the LLM cache.
"""
from __future__ import annotations

import app.features.render.ai.llm.key_pool as key_pool
from app.features.render.ai.llm.providers import openai as oai


def _clear_cooldowns():
    with key_pool._lock:
        key_pool._cooldown_until.clear()


# ── pool_for -------------------------------------------------------------------

def test_pool_for_single_key_no_pool(monkeypatch):
    """seed == the sole env key → deduped to len 1 → no rotation engaged."""
    monkeypatch.delenv("OPENAI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-solo")
    assert key_pool.pool_for("openai", seed_key="sk-solo") == ["sk-solo"]


def test_pool_for_seed_first_then_env_pool(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEYS", "sk-a, sk-b ,sk-c")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert key_pool.pool_for("openai", seed_key="sk-seed") == ["sk-seed", "sk-a", "sk-b", "sk-c"]
    # No seed → just the env pool, deduped/order-preserving.
    assert key_pool.pool_for("openai") == ["sk-a", "sk-b", "sk-c"]


# ── rotation on 429 ------------------------------------------------------------

def test_content_rotates_off_rate_limited_key(monkeypatch):
    _clear_cooldowns()
    monkeypatch.setenv("OPENAI_API_KEYS", "k1,k2")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    # Force a cache miss both ways so the SDK path is exercised.
    monkeypatch.setattr(oai, "llm_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(oai, "llm_cache_put", lambda *a, **k: True)

    seen: list[str] = []

    def _fake_once(api_key, model, system_prompt, user_prompt):
        seen.append(api_key)
        if api_key == "k1":
            raise RuntimeError("429 Too Many Requests: rate limit exceeded")
        return '{"ok": true}'

    monkeypatch.setattr(oai, "_call_openai_content_once", _fake_once)

    out = oai._call_openai_content("k1", "gpt-4o", "sys", "usr")
    assert out == '{"ok": true}'
    assert seen == ["k1", "k2"]          # tried k1 (429) → rotated to k2
    _clear_cooldowns()


def test_content_single_key_uses_retry_path(monkeypatch):
    """One key → no rotation; a hard (non-rate-limit) failure returns None once."""
    _clear_cooldowns()
    monkeypatch.delenv("OPENAI_API_KEYS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "only")
    monkeypatch.setattr(oai, "llm_cache_get", lambda *a, **k: None)
    monkeypatch.setattr(oai, "llm_cache_put", lambda *a, **k: True)

    calls = {"n": 0}

    def _fake_once(api_key, model, system_prompt, user_prompt):
        calls["n"] += 1
        return None                       # empty completion → no retry, no rotation

    monkeypatch.setattr(oai, "_call_openai_content_once", _fake_once)
    assert oai._call_openai_content("only", "gpt-4o", "sys", "usr") is None
    assert calls["n"] == 1
