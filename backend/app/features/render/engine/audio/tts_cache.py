"""
tts_cache.py — content-addressable cache for Edge-TTS narration output.

Architecture-review Batch D-1 (2026-06-30). Closes the "TTS not cached" gap
flagged in the review: Edge-TTS is the ONLY narration engine without a
cache today (Piper has TEMP_DIR/piper_cache/, XTTS has TEMP_DIR/xtts_cache/)
yet it is the only engine that hits the network — making it the biggest
perf win on a recap re-render where every scene's narration text is
unchanged.

Key
    SHA-256(text | language | gender | rate | voice_id | content_type |
            TTS_HUMANIZER_VERSION)

    Folds the rate AND voice_id into the key — Piper's and XTTS's
    existing per-engine caches OMIT both, which is a latent bug
    (different voice_id → same cache hit). Documented here but NOT
    fixed in D-1 (out of scope; tracked as D-1.1 follow-up).

    ``TTS_HUMANIZER_VERSION`` bumps when ``humanize_narration_text`` or
    ``ssml_humanize_for_edge`` change in ways that affect the audio. Same
    invalidation-by-construction pattern as Batch A's ``PROMPT_VERSION``.

Storage
    APP_DATA_DIR/cache/tts/<sha256>.mp3
    - 7-day TTL (longer than the LLM 72h since narration text is
      creator-stable across re-renders).
    - Atomic write via ``.tmp`` sidecar + ``os.replace`` (mirrors
      comprehension_stage.py / pipeline_cache.py).
    - Subdir-agnostic prune handles it — the maintenance walker is
      already cache/* level (no scheduler wiring change).

Wire-in
    ``tts.generate_narration_mp3`` consults the cache before
    ``edge_tts.Communicate`` and writes the result on success. Kill switch
    ``TTS_CACHE_ENABLED=0`` disables both lookup and put — recap falls
    back to synth-every-time (legacy behaviour).

Sacred Contract #3 spirit
    Every public helper catches all exceptions and returns
    ``None`` / ``False``. A cache failure must never break a live render.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from app.core.config import APP_DATA_DIR
# Reuse the shared cache-instrumentation decorator so the new "tts" label
# joins render_cache_lookups_total{cache, outcome} on the existing dashboard.
from app.services.metrics import instrument_cache as _instrument_cache

logger = logging.getLogger("app.render.tts.cache")

# Humanizer schema version. Bump when ``humanize_narration_text`` or
# ``ssml_humanize_for_edge`` change in a way that affects the audio (rate
# nudges, pause style insertions, SSML break shape). The cache key folds
# this in so a humanizer edit invalidates old cached audio by construction.
#
# History:
#   1 — D-1 inaugural version (2026-06-30).
TTS_HUMANIZER_VERSION: int = 1

# Subdir name under cache/. The maintenance scheduler walks every
# subdir of cache/ for TTL-aged files (verified by the Batch A
# test_prune_render_cache_handles_llm_subdir test). Adding this one
# requires zero scheduler wiring change.
_TTS_CACHE_SUBDIR = "tts"

# Longer than render/LLM caches (72h) because narration text is
# creator-stable across re-renders — a re-render days later hits the
# same scenes verbatim. 7d strikes a balance between hit rate and disk
# footprint (MP3s are tiny; tens of MB tops for an active workflow).
TTS_CACHE_TTL_SEC = 7 * 24 * 3600


def is_tts_cache_enabled() -> bool:
    """Read the kill switch on every call (not at module load) so an operator
    can flip the env var without restarting the worker process."""
    return os.getenv("TTS_CACHE_ENABLED", "1") == "1"


def _cache_dir() -> Path:
    return APP_DATA_DIR / "cache" / _TTS_CACHE_SUBDIR


def _build_tts_cache_key(
    text: str,
    language: str,
    gender: str,
    rate: str,
    voice_id: str,
    content_type: str,
    *,
    humanizer_version: int | None = None,
) -> str:
    """Return the SHA-256 hex digest used to address the cache entry.

    All inputs are coerced to ``str`` so callers can pass enum members or
    None without raising. ``humanizer_version`` defaults to the live
    ``TTS_HUMANIZER_VERSION`` — tests inject an explicit value to assert
    version-keyed isolation.
    """
    hv = TTS_HUMANIZER_VERSION if humanizer_version is None else int(humanizer_version)
    parts = "|".join([
        f"h{hv}",
        str(text or ""),
        str(language or ""),
        str(gender or ""),
        str(rate or ""),
        str(voice_id or ""),
        str(content_type or ""),
    ])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


@_instrument_cache("tts")
def tts_cache_get(cache_key: str, dest_path: Path) -> bool:
    """Copy the cached MP3 to ``dest_path`` if present and fresh. Returns
    True on a hit, False on miss / expiry / error.

    Never raises. A failed read for ANY reason — corrupted file, permission
    error, race with the pruner — is treated as a cache miss so the caller
    re-issues the Edge-TTS request.

    Decorator emits ``render_cache_lookups_total{cache="tts", outcome=...}``
    via the shared instrument_cache shim. Return-value truthiness governs
    the outcome label (True → hit, False → miss).
    """
    try:
        if not is_tts_cache_enabled():
            return False
        path = _cache_dir() / f"{cache_key}.mp3"
        if not path.exists() or path.stat().st_size <= 0:
            return False
        age = time.time() - path.stat().st_mtime
        if age > TTS_CACHE_TTL_SEC:
            # Stale — opportunistically clean up so the dir doesn't grow.
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return False
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Atomic copy via .tmp sidecar so a concurrent reader of the
        # destination never observes a partial copy.
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        shutil.copy2(str(path), str(tmp))
        os.replace(tmp, dest)
        return True
    except Exception as exc:
        logger.debug("tts_cache_get: miss due to error — %s", exc)
        return False


def tts_cache_put(cache_key: str, src_path: Path) -> bool:
    """Copy ``src_path`` into the cache under ``cache_key``. Returns True on
    success.

    Never raises. An empty / missing source file is NOT cached — caching a
    failure would mean every subsequent request gets a zero-byte hit.
    """
    try:
        if not is_tts_cache_enabled():
            return False
        src = Path(src_path)
        if not src.exists() or src.stat().st_size <= 0:
            return False
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{cache_key}.mp3"
        tmp = path.with_suffix(path.suffix + ".tmp")
        shutil.copy2(str(src), str(tmp))
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.debug("tts_cache_put: skipped due to error — %s", exc)
        return False


def tts_cache_clear() -> int:
    """Delete every cached TTS file. Returns the count deleted.

    Test-only helper; the operational prune comes from
    ``services.maintenance.prune_render_cache`` which walks every subdir
    of ``cache/`` for TTL-aged files.
    """
    try:
        cache_dir = _cache_dir()
        if not cache_dir.exists():
            return 0
        deleted = 0
        for f in cache_dir.glob("*.mp3"):
            try:
                f.unlink()
                deleted += 1
            except Exception:
                pass
        return deleted
    except Exception:
        return 0
