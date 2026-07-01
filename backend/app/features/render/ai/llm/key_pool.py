"""
key_pool.py — Gemini API key rotation for quota headroom.

Free-tier Gemini keys are capped (~20 requests/key/day). When a call hits a
429/RESOURCE_EXHAUSTED, ``call_gemini_with_rotation`` cools the exhausted key and
retries the SAME request on the next pool key, so a job (or a measurement run)
transparently fans out across every configured key. N keys ≈ N × the daily cap.

Pool source: ``config.GEMINI_API_KEYS`` (from the ``GEMINI_API_KEYS`` env, comma-
separated), falling back to ``[GEMINI_API_KEY]`` — so a single-key deployment
behaves exactly as before.

Thread-safe. Defensive: never raises; on total exhaustion the wrapped call
returns None, which every provider already treats as a clean failure
(Sacred Contract #3).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger("app.render.llm.key_pool")

_lock = threading.Lock()
_cooldown_until: dict[str, float] = {}   # key -> unix ts it is skippable until
_rr_index = [0]                          # round-robin cursor (guarded by _lock)


def _cooldown_sec() -> int:
    try:
        return max(0, int(os.getenv("GEMINI_KEY_COOLDOWN_SEC", "1800")))
    except (TypeError, ValueError):
        return 1800


def pool() -> "list[str]":
    """The configured key pool (deduped, order-preserving). Reads config each
    call so a hot-reloaded env is honoured; falls back to the single key."""
    try:
        from app.core import config as _cfg
        keys = list(getattr(_cfg, "GEMINI_API_KEYS", None) or [])
        if not keys:
            single = getattr(_cfg, "GEMINI_API_KEY", "") or ""
            keys = [single] if single else []
    except Exception:
        single = os.getenv("GEMINI_API_KEY", "") or ""
        keys = [k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()] or (
            [single] if single else []
        )
    seen: set[str] = set()
    out: list[str] = []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def size() -> int:
    return len(pool())


def note_rate_limited(key: str, cooldown_sec: "int | None" = None) -> None:
    """Mark ``key`` as quota-exhausted so it is skipped for a cooldown window."""
    if not key:
        return
    with _lock:
        _cooldown_until[key] = time.time() + (cooldown_sec if cooldown_sec is not None else _cooldown_sec())
    logger.warning("key_pool: gemini key …%s cooled down for %ds (429)", key[-6:],
                   cooldown_sec if cooldown_sec is not None else _cooldown_sec())


def _is_cooled(key: str, now: float) -> bool:
    return _cooldown_until.get(key, 0.0) > now


def active_key(seed: str = "") -> str:
    """Return a usable key: ``seed`` if it is not cooled, else the next non-cooled
    pool key (round-robin), else ``seed``/first key as a last resort. Never raises."""
    keys = pool()
    now = time.time()
    with _lock:
        if seed and not _is_cooled(seed, now):
            return seed
        n = len(keys)
        for _ in range(n):
            k = keys[_rr_index[0] % n] if n else ""
            _rr_index[0] = (_rr_index[0] + 1) % n if n else 0
            if k and not _is_cooled(k, now):
                return k
    return seed or (keys[0] if keys else "")


def rotation_sequence(seed: str) -> "list[str]":
    """Ordered keys to try for one request: ``seed`` first (if real), then the
    remaining pool keys, non-cooled before cooled. Deduped."""
    keys = pool()
    now = time.time()
    with _lock:
        others = [k for k in keys if k != seed]
        fresh = [k for k in others if not _is_cooled(k, now)]
        cooled = [k for k in others if _is_cooled(k, now)]
    seq: list[str] = []
    if seed:
        seq.append(seed)
    seq.extend(fresh)
    seq.extend(cooled)
    # Dedup, preserve order.
    seen: set[str] = set()
    return [k for k in seq if k and (k not in seen and not seen.add(k))]


def call_gemini_with_rotation(
    once_factory: Callable[[str], Optional[str]],
    *,
    label: str,
    seed_key: str,
) -> Optional[str]:
    """Run ``once_factory(key)`` across the pool, rotating on rate-limit.

    ``once_factory`` builds+runs one SDK call for a given key and may raise.
    Each key is tried once (no per-key backoff sleep — rotation IS the retry).
    On a rate-limit error the key is cooled and the next key is tried. On a
    NON-rate-limit failure we stop and return None (a different key won't fix a
    bad prompt). Returns the first non-None result, or None. Never raises."""
    from app.features.render.ai.llm.retry import call_with_retry

    seq = rotation_sequence(seed_key)
    if not seq:
        return None
    for key in seq:
        _rl = {"hit": False}

        def _on_rl(_exc, _k=key):
            _rl["hit"] = True
            note_rate_limited(_k)

        result = call_with_retry(
            lambda _k=key: once_factory(_k),
            label=label, max_attempts=1, on_rate_limit=_on_rl,
        )
        if result is not None:
            return result
        if not _rl["hit"]:
            # Non-rate-limit failure (empty response / bad request / network) —
            # another key won't help; fail fast like the pre-rotation behaviour.
            return None
        if len(seq) > 1:
            logger.info("key_pool: %s rate-limited on key …%s — rotating", label, key[-6:])
    return None
