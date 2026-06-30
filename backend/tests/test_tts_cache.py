"""Architecture-review Batch D-1 (2026-06-30) — Edge-TTS cache contract.

Pins the contract for ``app.features.render.engine.audio.tts_cache``:

  1. Key composition — same inputs same key; each component is sensitive;
     TTS_HUMANIZER_VERSION bump invalidates by construction.
  2. Round-trip — put → get returns identical bytes at the destination.
  3. TTL — fresh entry returned; expired entry returns False AND is cleaned.
  4. Kill switch — TTS_CACHE_ENABLED=0 makes both get + put no-ops.
  5. Atomic write — .tmp sidecar created during copy, cleaned on success.
  6. Defensive — corrupt cache file, missing src, zero-byte src never raise.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.features.render.engine.audio import tts_cache
from app.features.render.engine.audio.tts_cache import (
    TTS_CACHE_TTL_SEC,
    _build_tts_cache_key,
    is_tts_cache_enabled,
    tts_cache_clear,
    tts_cache_get,
    tts_cache_put,
)


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    """Redirect APP_DATA_DIR so the test never touches the real cache."""
    monkeypatch.setattr(tts_cache, "APP_DATA_DIR", tmp_path, raising=False)
    monkeypatch.setenv("TTS_CACHE_ENABLED", "1")
    tts_cache_clear()
    yield tmp_path
    tts_cache_clear()


def _seed_mp3(path: Path, content: bytes = b"FAKE-MP3-BYTES") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ---------------------------------------------------------------------------
# Key composition
# ---------------------------------------------------------------------------


def test_same_inputs_same_key():
    k1 = _build_tts_cache_key("hello", "en-US", "female", "+0%", "v1", "vlog")
    k2 = _build_tts_cache_key("hello", "en-US", "female", "+0%", "v1", "vlog")
    assert k1 == k2
    assert len(k1) == 64  # SHA-256 hex


@pytest.mark.parametrize("component,a,b", [
    ("text",         {"text": "hello"},     {"text": "world"}),
    ("language",     {"language": "en-US"}, {"language": "vi-VN"}),
    ("gender",       {"gender": "female"},  {"gender": "male"}),
    ("rate",         {"rate": "+0%"},       {"rate": "-5%"}),
    ("voice_id",     {"voice_id": "v1"},    {"voice_id": "v2"}),
    ("content_type", {"content_type": "vlog"}, {"content_type": "tutorial"}),
])
def test_each_component_differentiates_key(component, a, b):
    base = dict(text="t", language="en-US", gender="female", rate="+0%",
                voice_id="v1", content_type="vlog")
    k1 = _build_tts_cache_key(**{**base, **a})
    k2 = _build_tts_cache_key(**{**base, **b})
    assert k1 != k2, f"key collision on differing {component}"


def test_humanizer_version_bump_invalidates_key():
    k1 = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog", humanizer_version=1)
    k2 = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog", humanizer_version=2)
    assert k1 != k2


def test_key_tolerates_none_components():
    """None / unexpected types must not raise — production callers
    occasionally pass None voice_id when no explicit voice was chosen."""
    k = _build_tts_cache_key(None, None, None, None, None, None)  # type: ignore[arg-type]
    assert isinstance(k, str) and len(k) == 64


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


def test_put_then_get_copies_bytes_to_dest(_isolated_cache_dir, tmp_path):
    src = _seed_mp3(tmp_path / "src.mp3", b"AUDIO-BYTES")
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    assert tts_cache_put(key, src) is True

    dest = tmp_path / "out" / "narration.mp3"
    assert tts_cache_get(key, dest) is True
    assert dest.read_bytes() == b"AUDIO-BYTES"


def test_get_on_miss_returns_false(_isolated_cache_dir, tmp_path):
    dest = tmp_path / "out.mp3"
    assert tts_cache_get("no-such-key", dest) is False
    assert not dest.exists(), "miss must not create the destination file"


def test_put_zero_byte_source_returns_false(_isolated_cache_dir, tmp_path):
    """A zero-byte src is a synth failure — caching it would mean every
    subsequent request gets a zero-byte hit."""
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    assert tts_cache_put("k", empty) is False


def test_put_missing_source_returns_false(_isolated_cache_dir, tmp_path):
    assert tts_cache_put("k", tmp_path / "does-not-exist.mp3") is False


def test_put_overwrites_previous_entry_atomically(_isolated_cache_dir, tmp_path):
    src_v1 = _seed_mp3(tmp_path / "v1.mp3", b"VERSION-ONE")
    src_v2 = _seed_mp3(tmp_path / "v2.mp3", b"VERSION-TWO")
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    tts_cache_put(key, src_v1)
    tts_cache_put(key, src_v2)

    dest = tmp_path / "out.mp3"
    tts_cache_get(key, dest)
    assert dest.read_bytes() == b"VERSION-TWO"


# ---------------------------------------------------------------------------
# TTL
# ---------------------------------------------------------------------------


def test_fresh_entry_returned_under_ttl(_isolated_cache_dir, tmp_path):
    src = _seed_mp3(tmp_path / "src.mp3")
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    tts_cache_put(key, src)
    dest = tmp_path / "out.mp3"
    assert tts_cache_get(key, dest) is True


def test_expired_entry_returns_false_and_is_cleaned_up(_isolated_cache_dir, tmp_path):
    src = _seed_mp3(tmp_path / "src.mp3")
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    tts_cache_put(key, src)

    cache_dir = _isolated_cache_dir / "cache" / "tts"
    files_before = list(cache_dir.glob("*.mp3"))
    assert files_before

    very_old = time.time() - TTS_CACHE_TTL_SEC - 60
    for f in files_before:
        os.utime(f, (very_old, very_old))

    dest = tmp_path / "out.mp3"
    assert tts_cache_get(key, dest) is False
    # Opportunistic cleanup deleted the stale file.
    assert not list(cache_dir.glob("*.mp3"))


# ---------------------------------------------------------------------------
# Kill switch
# ---------------------------------------------------------------------------


def test_kill_switch_makes_get_a_no_op(_isolated_cache_dir, tmp_path, monkeypatch):
    src = _seed_mp3(tmp_path / "src.mp3", b"AUDIO")
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    tts_cache_put(key, src)
    # Re-set the cache_dir patch since the fixture's monkeypatch is still
    # active; we only flip the env var.
    monkeypatch.setenv("TTS_CACHE_ENABLED", "0")
    dest = tmp_path / "out.mp3"
    assert tts_cache_get(key, dest) is False
    assert not dest.exists()


def test_kill_switch_makes_put_a_no_op(_isolated_cache_dir, tmp_path, monkeypatch):
    src = _seed_mp3(tmp_path / "src.mp3", b"AUDIO")
    monkeypatch.setenv("TTS_CACHE_ENABLED", "0")
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    assert tts_cache_put(key, src) is False
    # Cache dir should not contain the entry.
    cache_dir = _isolated_cache_dir / "cache" / "tts"
    assert not list(cache_dir.glob("*.mp3")) if cache_dir.exists() else True


def test_is_tts_cache_enabled_reflects_env(monkeypatch):
    monkeypatch.setenv("TTS_CACHE_ENABLED", "1")
    assert is_tts_cache_enabled() is True
    monkeypatch.setenv("TTS_CACHE_ENABLED", "0")
    assert is_tts_cache_enabled() is False


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


def test_successful_put_leaves_no_tmp_sidecar(_isolated_cache_dir, tmp_path):
    src = _seed_mp3(tmp_path / "src.mp3")
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    tts_cache_put(key, src)
    cache_dir = _isolated_cache_dir / "cache" / "tts"
    leftovers = list(cache_dir.glob("*.tmp"))
    assert leftovers == [], "atomic write must leave no .tmp behind on success"


def test_successful_get_leaves_no_tmp_sidecar(_isolated_cache_dir, tmp_path):
    src = _seed_mp3(tmp_path / "src.mp3")
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    tts_cache_put(key, src)
    dest = tmp_path / "out" / "narration.mp3"
    tts_cache_get(key, dest)
    leftovers = list(dest.parent.glob("*.tmp"))
    assert leftovers == [], "atomic copy must leave no .tmp behind on success"


# ---------------------------------------------------------------------------
# Defensive — corrupt cache file
# ---------------------------------------------------------------------------


def test_corrupt_cache_entry_treated_as_miss(_isolated_cache_dir, tmp_path):
    """A zero-byte file in the cache must NOT count as a hit — the get
    sanity-checks size > 0 (a stale partial write or pruner race could
    produce one)."""
    cache_dir = _isolated_cache_dir / "cache" / "tts"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _build_tts_cache_key("t", "en", "f", "+0%", "v", "vlog")
    (cache_dir / f"{key}.mp3").write_bytes(b"")
    dest = tmp_path / "out.mp3"
    assert tts_cache_get(key, dest) is False


def test_clear_returns_count(_isolated_cache_dir, tmp_path):
    src = _seed_mp3(tmp_path / "src.mp3")
    tts_cache_put(_build_tts_cache_key("a", "en", "f", "+0%", "v", "vlog"), src)
    tts_cache_put(_build_tts_cache_key("b", "en", "f", "+0%", "v", "vlog"), src)
    assert tts_cache_clear() == 2
    assert tts_cache_clear() == 0
