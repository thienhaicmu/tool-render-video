"""
test_gemini_key_pool.py — guard for Gemini API key rotation.

Verifies the pool rotates to the next key on a 429 (quota) and cools the
exhausted one, does NOT waste keys on a non-rate-limit error, and that the
retry hook fires on rate-limit errors only.
"""
from __future__ import annotations

import time

import pytest

from app.features.render.ai.llm import key_pool
from app.features.render.ai.llm.retry import _is_rate_limit, call_with_retry


@pytest.fixture(autouse=True)
def _reset_pool():
    key_pool._cooldown_until.clear()
    key_pool._rr_index[0] = 0
    yield
    key_pool._cooldown_until.clear()
    key_pool._rr_index[0] = 0


def _set_pool(monkeypatch, keys):
    monkeypatch.setattr("app.core.config.GEMINI_API_KEYS", list(keys), raising=False)
    monkeypatch.setattr("app.core.config.GEMINI_API_KEY", keys[0] if keys else "", raising=False)


# ── pool + rotation sequence ─────────────────────────────────────────────────

def test_pool_dedups_and_reads_config(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2", "k2", "k3"])
    assert key_pool.pool() == ["k1", "k2", "k3"]
    assert key_pool.size() == 3


def test_rotation_sequence_seed_first_then_fresh(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2", "k3"])
    assert key_pool.rotation_sequence("k2") == ["k2", "k1", "k3"]


def test_active_key_skips_cooled(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2"])
    key_pool.note_rate_limited("k1", cooldown_sec=999)
    assert key_pool.active_key("k1") == "k2"        # seed cooled → next
    assert key_pool._cooldown_until["k1"] > time.time()


# ── call_gemini_with_rotation ────────────────────────────────────────────────

def test_success_on_first_key_no_rotation(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2", "k3"])
    calls = []
    out = key_pool.call_gemini_with_rotation(
        lambda k: calls.append(k) or "ok", label="t", seed_key="k1")
    assert out == "ok" and calls == ["k1"]


def test_rotates_and_cools_on_429(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2", "k3"])
    calls = []

    def factory(k):
        calls.append(k)
        if k == "k1":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota")
        return "ok"

    out = key_pool.call_gemini_with_rotation(factory, label="t", seed_key="k1")
    assert out == "ok"
    assert calls == ["k1", "k2"]                     # rotated past exhausted k1
    assert key_pool._cooldown_until.get("k1", 0) > time.time()   # k1 cooled


def test_non_rate_limit_does_not_rotate(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2"])
    calls = []

    def factory(k):
        calls.append(k)
        raise ValueError("malformed prompt")         # not a rate-limit

    out = key_pool.call_gemini_with_rotation(factory, label="t", seed_key="k1")
    assert out is None and calls == ["k1"]           # no key wasted


def test_transient_503_rotates_without_cooling(monkeypatch):
    # 503 model-overload is NOT the key's fault: rotate to the next key but do
    # NOT cool the failing key. (Regression guard: before this fix, 503 was
    # classified non-retryable and failed the whole call instantly.)
    _set_pool(monkeypatch, ["k1", "k2"])
    monkeypatch.setattr(key_pool, "_TRANSIENT_BACKOFF_SEC", 0.0)  # no sleep in tests
    calls = []

    def factory(k):
        calls.append(k)
        if k == "k1":
            raise RuntimeError("503 UNAVAILABLE: model is experiencing high demand")
        return "ok"

    out = key_pool.call_gemini_with_rotation(factory, label="t", seed_key="k1")
    assert out == "ok" and calls == ["k1", "k2"]
    assert "k1" not in key_pool._cooldown_until     # transient → no cooldown


def test_transient_504_timeout_rotates(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2"])
    monkeypatch.setattr(key_pool, "_TRANSIENT_BACKOFF_SEC", 0.0)
    calls = []

    def factory(k):
        calls.append(k)
        if k == "k1":
            raise RuntimeError("504 DEADLINE_EXCEEDED. The request timed out.")
        return "ok"

    assert key_pool.call_gemini_with_rotation(factory, label="t", seed_key="k1") == "ok"
    assert calls == ["k1", "k2"]


def test_all_transient_returns_none_no_cooldowns(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2"])
    monkeypatch.setattr(key_pool, "_TRANSIENT_BACKOFF_SEC", 0.0)

    def factory(k):
        raise RuntimeError("503 UNAVAILABLE")

    assert key_pool.call_gemini_with_rotation(factory, label="t", seed_key="k1") is None
    assert key_pool._cooldown_until == {}           # nothing cooled


def test_all_keys_exhausted_returns_none(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2"])

    def factory(k):
        raise RuntimeError("429 quota exceeded")

    assert key_pool.call_gemini_with_rotation(factory, label="t", seed_key="k1") is None
    assert key_pool._cooldown_until.get("k1", 0) > time.time()
    assert key_pool._cooldown_until.get("k2", 0) > time.time()


# ── model rotation (per-family fallback) ─────────────────────────────────────

def test_model_chain_primary_first_then_fallbacks(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL_FALLBACKS", raising=False)
    assert key_pool.model_chain(
        "m-a", env_var="GEMINI_MODEL_FALLBACKS", default_fallbacks=["m-b", "m-c"]
    ) == ["m-a", "m-b", "m-c"]
    # env override replaces the defaults; primary still leads.
    monkeypatch.setenv("GEMINI_MODEL_FALLBACKS", "m-x, m-y")
    assert key_pool.model_chain(
        "m-a", env_var="GEMINI_MODEL_FALLBACKS", default_fallbacks=["m-b"]
    ) == ["m-a", "m-x", "m-y"]
    # dedup + drop blanks.
    monkeypatch.delenv("GEMINI_MODEL_FALLBACKS", raising=False)
    assert key_pool.model_chain(
        "m-a", env_var="GEMINI_MODEL_FALLBACKS", default_fallbacks=["m-a", "m-b", ""]
    ) == ["m-a", "m-b"]


def test_model_rotates_on_overload_exhaustion(monkeypatch):
    # Primary model 503s on EVERY key → fall back to the next model, which works.
    _set_pool(monkeypatch, ["k1", "k2"])
    monkeypatch.setattr(key_pool, "_TRANSIENT_BACKOFF_SEC", 0.0)
    seen = []

    def once(key, model):
        seen.append((key, model))
        if model == "primary":
            raise RuntimeError("503 UNAVAILABLE: high demand")
        return f"ok:{model}"

    out = key_pool.call_gemini_with_model_rotation(
        once, label="t", seed_key="k1", models=["primary", "fallback"])
    assert out == "ok:fallback"
    assert ("k1", "primary") in seen and ("k2", "primary") in seen   # primary exhausted
    assert seen[-1][1] == "fallback"                                  # then advanced


def test_hard_failure_does_not_rotate_model(monkeypatch):
    # A non-retryable error (bad prompt) must NOT waste keys OR advance models.
    _set_pool(monkeypatch, ["k1", "k2"])
    seen = []

    def once(key, model):
        seen.append(model)
        raise ValueError("malformed prompt")

    out = key_pool.call_gemini_with_model_rotation(
        once, label="t", seed_key="k1", models=["primary", "fallback"])
    assert out is None
    assert seen == ["primary"]   # fail-fast on the first key, first model


def test_quota_exhaustion_rotates_model(monkeypatch):
    # 429 on every key of the primary model → try the next model too.
    _set_pool(monkeypatch, ["k1", "k2"])
    seen = []

    def once(key, model):
        seen.append(model)
        if model == "primary":
            raise RuntimeError("429 RESOURCE_EXHAUSTED: quota")
        return "ok"

    assert key_pool.call_gemini_with_model_rotation(
        once, label="t", seed_key="k1", models=["primary", "fallback"]) == "ok"
    assert seen.count("primary") == 2 and "fallback" in seen


# ── retry hook ───────────────────────────────────────────────────────────────

def test_is_rate_limit_detection():
    assert _is_rate_limit(RuntimeError("429 RESOURCE_EXHAUSTED"))
    assert _is_rate_limit(Exception("You exceeded your quota"))
    assert not _is_rate_limit(ValueError("bad prompt"))


def test_call_with_retry_fires_on_rate_limit_only():
    hits = []
    call_with_retry(lambda: (_ for _ in ()).throw(RuntimeError("429 quota")),
                    label="t", max_attempts=1, on_rate_limit=lambda e: hits.append(e))
    assert len(hits) == 1
    hits.clear()
    call_with_retry(lambda: (_ for _ in ()).throw(ValueError("nope")),
                    label="t", max_attempts=1, on_rate_limit=lambda e: hits.append(e))
    assert hits == []
