"""
test_gemini_tts_optimizations.py — guards for the Gemini TTS optimization batch.

O-1: synthesis rides the key-rotation pool (429 rotates instead of dropping the
     whole render to the Edge chain mid-video).
O-2: the gemini_tts_cache dir is pruned (same unbounded-growth class as
     xtts_cache).
O-3: the write-only in-memory cache dict is gone (disk file IS the cache).
O-4: a concurrency semaphore bounds parallel synthesis.

All offline — the SDK call and FFmpeg conversion are monkeypatched.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.features.render.engine.audio import tts_gemini
from app.services.maintenance import prune_gemini_tts_cache


# ── O-1: rotation wiring ─────────────────────────────────────────────────────

def test_synthesize_routes_through_rotation(monkeypatch, tmp_path):
    """The API call must go through call_gemini_with_rotation with a pool seed,
    and its PCM must flow into the WAV→MP3 pipeline."""
    calls = {}

    def fake_rotation(once_factory, *, label, seed_key):
        calls["label"] = label
        calls["seed"] = seed_key
        return b"\x00\x01" * 2400  # fake PCM

    monkeypatch.setattr(
        "app.features.render.ai.llm.key_pool.call_gemini_with_rotation", fake_rotation)
    monkeypatch.setattr(
        "app.features.render.ai.llm.key_pool.active_key", lambda seed="": "poolkey")
    monkeypatch.setattr(tts_gemini, "_resolve_api_key", lambda: "poolkey")
    monkeypatch.setattr(
        tts_gemini, "_wav_to_mp3",
        lambda wav, mp3: Path(mp3).write_bytes(b"MP3" + Path(wav).read_bytes()[:8]))
    monkeypatch.setattr("app.core.config.TEMP_DIR", tmp_path)

    out = tts_gemini.synthesize_gemini(
        text="xin chao", language="vi-VN", gender="female", job_id="job1",
        content_type="story", output_path=str(tmp_path / "out.mp3"))
    assert calls["label"] == "gemini-tts"
    assert calls["seed"] == "poolkey"
    assert Path(out).exists() and Path(out).stat().st_size > 0


def test_all_keys_exhausted_raises_for_fallback(monkeypatch, tmp_path):
    """Rotation returning None (pool exhausted) must RAISE — the dispatcher's
    fallback-to-Edge contract depends on the exception."""
    monkeypatch.setattr(
        "app.features.render.ai.llm.key_pool.call_gemini_with_rotation",
        lambda f, *, label, seed_key: None)
    monkeypatch.setattr(
        "app.features.render.ai.llm.key_pool.active_key", lambda seed="": "k")
    monkeypatch.setattr(tts_gemini, "_resolve_api_key", lambda: "k")
    monkeypatch.setattr("app.core.config.TEMP_DIR", tmp_path)
    with pytest.raises(RuntimeError, match="gemini_tts_failed"):
        tts_gemini.synthesize_gemini(
            text="hello", language="en-US", gender="male", job_id="job2")


# ── O-3: dead in-memory cache removed; disk cache still works ────────────────

def test_dead_memory_cache_removed():
    assert not hasattr(tts_gemini, "_GEMINI_SYNTHESIS_CACHE")


def test_disk_cache_hit_skips_api(monkeypatch, tmp_path):
    monkeypatch.setattr("app.core.config.TEMP_DIR", tmp_path)
    monkeypatch.setattr(tts_gemini, "_resolve_api_key", lambda: "k")

    def boom(*a, **kw):
        raise AssertionError("API must not be called on a cache hit")
    monkeypatch.setattr(tts_gemini, "_generate_pcm", boom)

    voice = tts_gemini._resolve_voice("female")
    style = tts_gemini._resolve_style("story", language="vi-VN", rate="")
    key = tts_gemini._synthesis_cache_key("cached text", "vi-VN", voice, style)
    cache_dir = tmp_path / "gemini_tts_cache"
    cache_dir.mkdir(parents=True)
    (cache_dir / f"{key}.mp3").write_bytes(b"CACHED_MP3")

    out = tts_gemini.synthesize_gemini(
        text="cached text", language="vi-VN", gender="female", job_id="job3",
        content_type="story", output_path=str(tmp_path / "dest.mp3"))
    assert Path(out).read_bytes() == b"CACHED_MP3"


# ── O-4: concurrency bound ───────────────────────────────────────────────────

def test_semaphore_default_and_floor(monkeypatch):
    assert tts_gemini._GEMINI_TTS_MAX_CONCURRENCY >= 1
    # The semaphore exists and is a bounded gate around _generate_pcm.
    assert tts_gemini._GEMINI_TTS_SEMAPHORE._value >= 1


# ── model resolved at call time ──────────────────────────────────────────────

def test_model_resolved_at_call_time(monkeypatch):
    monkeypatch.setenv("GEMINI_TTS_MODEL", "gemini-9.9-tts-test")
    assert tts_gemini._tts_model() == "gemini-9.9-tts-test"
    k1 = tts_gemini._synthesis_cache_key("t", "vi", "Kore", "s")
    monkeypatch.setenv("GEMINI_TTS_MODEL", "gemini-other")
    k2 = tts_gemini._synthesis_cache_key("t", "vi", "Kore", "s")
    assert k1 != k2  # model participates in the cache key at call time


# ── O-2: cache prune ─────────────────────────────────────────────────────────

def test_prune_gemini_tts_cache(tmp_path):
    cache = tmp_path / "gemini_tts_cache"
    cache.mkdir()
    old = cache / "old.mp3"
    new = cache / "new.mp3"
    old.write_bytes(b"x")
    new.write_bytes(b"y")
    stale = time.time() - 40 * 24 * 3600
    os.utime(old, (stale, stale))
    result = prune_gemini_tts_cache(tmp_path, max_age_days=30)
    assert result == {"removed": 1, "kept": 1}
    assert not old.exists() and new.exists()


def test_prune_gemini_tts_cache_missing_dir_is_noop(tmp_path):
    assert prune_gemini_tts_cache(tmp_path) == {"removed": 0, "kept": 0}
