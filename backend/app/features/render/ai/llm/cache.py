"""Content-addressable cache for raw LLM responses.

Closes audit FINDING-AI06 (Phase 6, 2026-06-06). Before this module,
re-rendering the same source against the same prompt re-paid the full
LLM API cost. Whisper transcription is already cached (72 h TTL, see
``pipeline_cache.py``), so the only un-cached cost on a re-render was
the LLM round-trip and its associated latency.

Design (mirrors the Sprint 7.3 ASS content-addressable cache):

- **Key**: SHA-256 of ``provider | model | system_prompt | user_prompt``.
  The same prompt produced by the same provider+model is always the same
  cache entry. Switching provider or model invalidates automatically.
- **NOT keyed on** the API key — credentials rotate without invalidating
  the cache, and the API key is never written to disk via this module.
- **Value**: the raw LLM response string (the same value the un-cached
  ``_call_<provider>`` helper would have returned).
- **Store**: ``APP_DATA_DIR/cache/llm/<sha256>.txt``.
- **TTL**: 72 h, matching the transcription cache (same Sprint 6 P1
  scheduler that prunes ``cache/transcription/`` also handles this dir).
- **Defensive (Sacred Contract #3 spirit)**: every public helper catches
  all exceptions and returns ``None`` / ``False``. A cache failure must
  never break a live render.

Wire-in: each provider's ``_call_<provider>`` consults the cache before
the retry loop. On a miss, the result of the loop is written back.
``call_with_retry`` is unaware of the cache — composition cleanly
separates the "expensive retry-able call" concern from the
"is-this-already-on-disk" concern.
"""
from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

from app.core.config import APP_DATA_DIR

logger = logging.getLogger("app.render.llm.cache")

# Same horizon as the transcription cache. The cleanup scheduler in
# ``services/maintenance.py`` walks every subdir of ``cache/`` so adding
# this one is automatic — no scheduler wiring change needed (see test).
LLM_CACHE_TTL_SEC = 72 * 3600

# Subdir name used both here and by the maintenance scheduler.
_LLM_CACHE_SUBDIR = "llm"


def _cache_dir() -> Path:
    return APP_DATA_DIR / "cache" / _LLM_CACHE_SUBDIR


def _build_key(provider: str, model: str, system_prompt: str, user_prompt: str) -> str:
    """Return the SHA-256 hex digest used to address the cache entry.

    All four inputs are coerced to ``str`` so callers can pass enum
    members or None without raising. None is normalised to the empty
    string so a missing model behaves identically across callers.
    """
    parts = "|".join([
        str(provider or ""),
        str(model or ""),
        str(system_prompt or ""),
        str(user_prompt or ""),
    ])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def llm_cache_get(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
) -> Optional[str]:
    """Return the cached LLM response string, or None on miss / expiry.

    Never raises. A failed read for ANY reason — corrupted file,
    permission error, race with the pruner — is treated as a cache miss
    so the caller re-issues the LLM request.
    """
    try:
        key = _build_key(provider, model, system_prompt, user_prompt)
        path = _cache_dir() / f"{key}.txt"
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > LLM_CACHE_TTL_SEC:
            # Stale — opportunistically clean up so the dir doesn't grow.
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return None
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.debug("llm_cache_get: miss due to error — %s", exc)
        return None


def llm_cache_put(
    provider: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    response: str,
) -> bool:
    """Write the LLM response to the cache. Returns True on success.

    Never raises. An empty / None response is NOT cached — caching a
    failure would mean the next attempt also returned ''. The provider
    layer treats both as cache misses on read, but we want the on-disk
    cache to only carry positive results.
    """
    try:
        if not response or not isinstance(response, str):
            return False
        key = _build_key(provider, model, system_prompt, user_prompt)
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / f"{key}.txt").write_text(response, encoding="utf-8")
        return True
    except Exception as exc:
        logger.debug("llm_cache_put: skipped due to error — %s", exc)
        return False


def llm_cache_clear() -> int:
    """Delete every cached LLM response. Returns the count deleted.

    Test-only helper used by the suite; not wired to a route. The
    operational prune comes from ``services.maintenance.prune_render_cache``
    which walks every subdir of ``cache/`` for TTL-aged files.
    """
    try:
        cache_dir = _cache_dir()
        if not cache_dir.exists():
            return 0
        deleted = 0
        for f in cache_dir.glob("*.txt"):
            try:
                f.unlink()
                deleted += 1
            except Exception:
                pass
        return deleted
    except Exception:
        return 0
