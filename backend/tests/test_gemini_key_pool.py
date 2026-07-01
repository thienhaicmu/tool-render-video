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


def test_all_keys_exhausted_returns_none(monkeypatch):
    _set_pool(monkeypatch, ["k1", "k2"])

    def factory(k):
        raise RuntimeError("429 quota exceeded")

    assert key_pool.call_gemini_with_rotation(factory, label="t", seed_key="k1") is None
    assert key_pool._cooldown_until.get("k1", 0) > time.time()
    assert key_pool._cooldown_until.get("k2", 0) > time.time()


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
