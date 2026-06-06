"""Tests for the content-addressable LLM response cache (audit AI06).

Pins the contract:
1. Same inputs (provider, model, system_prompt, user_prompt) → same key.
2. Different inputs → different keys.
3. The API key is NOT part of the cache key (credentials rotate without
   invalidating the cache, and the key is never written to disk).
4. Read-after-write returns the stored response unchanged.
5. Read after the TTL expires returns None (and opportunistically cleans
   up the stale file).
6. Failed writes (empty / None response) are silently skipped.
7. The cache is robust to corrupted files and FS errors — every public
   helper returns None / False, never raises.
8. The maintenance prune is dir-agnostic and covers the LLM subdir
   without explicit wiring.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.features.render.ai.llm import cache as llm_cache
from app.features.render.ai.llm.cache import (
    LLM_CACHE_TTL_SEC,
    _build_key,
    llm_cache_clear,
    llm_cache_get,
    llm_cache_put,
)


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """Redirect APP_DATA_DIR so the test never touches the real cache."""
    monkeypatch.setattr(llm_cache, "APP_DATA_DIR", tmp_path, raising=False)
    # Clear before + after so tests don't leak into each other.
    llm_cache_clear()
    yield
    llm_cache_clear()


# ---------------------------------------------------------------------------
# Key determinism
# ---------------------------------------------------------------------------

def test_same_inputs_same_key():
    k1 = _build_key("gemini", "flash", "sysA", "userA")
    k2 = _build_key("gemini", "flash", "sysA", "userA")
    assert k1 == k2
    assert len(k1) == 64  # SHA-256 hex


def test_provider_differentiates_key():
    k1 = _build_key("gemini", "x", "s", "u")
    k2 = _build_key("openai", "x", "s", "u")
    assert k1 != k2


def test_model_differentiates_key():
    k1 = _build_key("gemini", "gemini-2.5-pro", "s", "u")
    k2 = _build_key("gemini", "gemini-2.5-flash", "s", "u")
    assert k1 != k2


def test_system_prompt_differentiates_key():
    k1 = _build_key("gemini", "x", "sysA", "u")
    k2 = _build_key("gemini", "x", "sysB", "u")
    assert k1 != k2


def test_user_prompt_differentiates_key():
    k1 = _build_key("gemini", "x", "s", "userA")
    k2 = _build_key("gemini", "x", "s", "userB")
    assert k1 != k2


def test_key_tolerates_none_and_enum_like_values():
    # Should not raise on None / unexpected types.
    k = _build_key(None, None, None, None)  # type: ignore[arg-type]
    assert isinstance(k, str) and len(k) == 64


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_round_trip_get_returns_what_was_put():
    payload = '{"segments": [{"start": 0, "end": 5}]}'
    assert llm_cache_put("gemini", "flash", "sys", "user", payload) is True
    got = llm_cache_get("gemini", "flash", "sys", "user")
    assert got == payload


def test_get_returns_none_on_miss():
    assert llm_cache_get("gemini", "flash", "never", "stored") is None


def test_get_returns_none_when_provider_differs():
    """Same prompt, different provider → different cache slot."""
    llm_cache_put("gemini", "flash", "sys", "user", "from-gemini")
    assert llm_cache_get("openai", "flash", "sys", "user") is None


def test_get_returns_none_when_model_differs():
    llm_cache_put("gemini", "flash", "sys", "user", "from-flash")
    assert llm_cache_get("gemini", "pro", "sys", "user") is None


def test_put_does_not_cache_empty_response():
    assert llm_cache_put("gemini", "flash", "s", "u", "") is False
    assert llm_cache_get("gemini", "flash", "s", "u") is None


def test_put_does_not_cache_none_response():
    assert llm_cache_put("gemini", "flash", "s", "u", None) is False  # type: ignore[arg-type]
    assert llm_cache_get("gemini", "flash", "s", "u") is None


def test_put_does_not_cache_non_string():
    assert llm_cache_put("gemini", "flash", "s", "u", {"x": 1}) is False  # type: ignore[arg-type]


def test_put_unicode_round_trip():
    payload = '{"clip_name": "Người chạy đua 🚀"}'
    llm_cache_put("gemini", "flash", "sys", "user", payload)
    assert llm_cache_get("gemini", "flash", "sys", "user") == payload


# ---------------------------------------------------------------------------
# TTL
# ---------------------------------------------------------------------------

def test_expired_entry_returns_none_and_is_cleaned_up(tmp_path):
    payload = "stale"
    llm_cache_put("gemini", "flash", "sys", "user", payload)
    cache_dir = tmp_path / "cache" / "llm"
    files_before = list(cache_dir.glob("*.txt"))
    assert files_before

    # Backdate the mtime past the TTL.
    very_old = time.time() - LLM_CACHE_TTL_SEC - 60
    for f in files_before:
        os.utime(f, (very_old, very_old))

    assert llm_cache_get("gemini", "flash", "sys", "user") is None
    # Opportunistic cleanup deleted the stale file.
    assert not list(cache_dir.glob("*.txt"))


def test_fresh_entry_is_returned_under_ttl():
    llm_cache_put("gemini", "flash", "sys", "user", "fresh")
    # mtime is the time of write; well under the TTL.
    assert llm_cache_get("gemini", "flash", "sys", "user") == "fresh"


# ---------------------------------------------------------------------------
# Robustness — corrupted file / FS errors must not raise
# ---------------------------------------------------------------------------

def test_corrupted_file_does_not_raise(tmp_path):
    llm_cache_put("gemini", "flash", "sys", "user", "ok")
    # Find the file and clobber it with bytes that aren't valid utf-8.
    cache_dir = tmp_path / "cache" / "llm"
    target = next(iter(cache_dir.glob("*.txt")))
    target.write_bytes(b"\xff\xfe\xfd")  # invalid UTF-8 sequence

    # Must NOT raise; treats as miss.
    assert llm_cache_get("gemini", "flash", "sys", "user") is None


def test_clear_returns_count_and_works_on_empty_dir():
    # No entries → 0 deletes.
    assert llm_cache_clear() == 0
    # Two entries → 2 deletes.
    llm_cache_put("a", "m", "s", "u1", "ok1")
    llm_cache_put("a", "m", "s", "u2", "ok2")
    assert llm_cache_clear() == 2
    assert llm_cache_get("a", "m", "s", "u1") is None


# ---------------------------------------------------------------------------
# Maintenance prune coverage — Phase 1 §I.3 promises subdir-agnostic walk
# ---------------------------------------------------------------------------

def test_prune_render_cache_handles_llm_subdir(tmp_path):
    """The Sprint 5.2 prune_render_cache walks every subdir. Adding the new
    cache/llm/ folder requires zero scheduler change — verify the prune
    helper handles it for arbitrary subdirs and removes a stale LLM entry.
    """
    from app.services.maintenance import prune_render_cache

    llm_cache_put("gemini", "flash", "sys", "user", "old")
    # Backdate the entry.
    cache_root = tmp_path / "cache"
    llm_dir = cache_root / "llm"
    very_old = time.time() - (72 * 3600) - 60
    for f in llm_dir.glob("*.txt"):
        os.utime(f, (very_old, very_old))

    stats = prune_render_cache(cache_root, max_age_hours=72)
    assert stats["removed"] >= 1
    assert llm_cache_get("gemini", "flash", "sys", "user") is None


def test_prune_render_cache_preserves_fresh_entries(tmp_path):
    from app.services.maintenance import prune_render_cache

    llm_cache_put("gemini", "flash", "sys", "user", "fresh")
    cache_root = tmp_path / "cache"
    stats = prune_render_cache(cache_root, max_age_hours=72)
    # Fresh entries must not be removed.
    assert stats["removed"] == 0
    assert llm_cache_get("gemini", "flash", "sys", "user") == "fresh"
