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

# Short pause before retrying a TRANSIENT (503/504) failure on the next key —
# gives the overloaded backend a beat, mirroring the old backoff behaviour.
_TRANSIENT_BACKOFF_SEC: float = max(0.0, float(os.getenv("GEMINI_TRANSIENT_BACKOFF_SEC", "2") or 2))


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


def model_chain(
    primary: str,
    *,
    env_var: str,
    default_fallbacks: "list[str]",
) -> "list[str]":
    """Ordered model list to try for one logical call: ``primary`` first, then
    the configured fallbacks. Fallbacks come from ``env_var`` (comma-separated)
    when set, else ``default_fallbacks``. Deduped, order-preserving; blank
    entries dropped. Never raises.

    Model rotation is per-FAMILY: a text call passes a text env/defaults, a TTS
    call passes TTS ones, etc. — so an overloaded ``gemini-3.5-flash`` falls to
    ``gemini-2.5-flash`` and an overloaded TTS model falls to a TTS model, never
    across families.
    """
    raw = os.getenv(env_var, "") or ""
    if raw.strip():
        fallbacks = [m.strip() for m in raw.split(",") if m.strip()]
    else:
        fallbacks = [m for m in (default_fallbacks or []) if m]
    seq = [primary, *fallbacks]
    seen: set[str] = set()
    return [m for m in seq if m and (m not in seen and not seen.add(m))]


def _run_key_rotation(
    once_km: Callable[[str, str], Optional[object]],
    model: str,
    *,
    label: str,
    seq: "list[str]",
) -> "tuple[Optional[object], bool]":
    """Run ``once_km(key, model)`` across ``seq`` keys for a SINGLE model.

    Returns ``(result, exhausted_by_overload)``:
      - ``result``: first non-None output, or None.
      - ``exhausted_by_overload``: True only when EVERY key failed due to
        rate-limit (429/quota) or transient overload (503/504) — the signal the
        caller uses to advance to the next model. False when a hard, non-
        retryable failure (auth / bad prompt / empty response) stopped the loop,
        or when a result was found.
    Never raises."""
    from app.features.render.ai.llm.retry import _is_transient, call_with_retry

    for idx, key in enumerate(seq):
        _rl = {"hit": False}
        _last: dict = {"exc": None}

        def _on_rl(_exc, _k=key):
            _rl["hit"] = True
            note_rate_limited(_k)

        result = call_with_retry(
            lambda _k=key, _m=model: once_km(_k, _m),
            label=label, max_attempts=1, on_rate_limit=_on_rl,
            on_error=lambda _e: _last.__setitem__("exc", _e),
        )
        if result is not None:
            return result, False
        if _rl["hit"]:
            if len(seq) > 1:
                logger.info("key_pool: %s rate-limited on key …%s (model=%s) — rotating",
                            label, key[-6:], model or "-")
            continue
        if _last["exc"] is not None and _is_transient(_last["exc"]):
            logger.info("key_pool: %s transient error on key …%s (model=%s, %s) — retrying on next key",
                        label, key[-6:], model or "-", type(_last["exc"]).__name__)
            if idx < len(seq) - 1:
                time.sleep(_TRANSIENT_BACKOFF_SEC)
            continue
        # Non-retryable failure (empty response / bad request / auth) — neither a
        # different key NOR a different model will help; fail fast.
        return None, False
    # Loop completed via rate-limit/transient continues only → every key was
    # exhausted by overload/quota, so a different model is worth trying.
    return None, True


def call_gemini_with_model_rotation(
    once_km: Callable[[str, str], Optional[object]],
    *,
    label: str,
    seed_key: str,
    models: "list[str]",
) -> Optional[object]:
    """Run ``once_km(key, model)`` across the key pool for each model in
    ``models``, advancing to the next model ONLY when the current one is
    exhausted across every key by overload (503/504) or quota (429). A hard
    failure (auth / bad prompt / empty response) fails fast — a different model
    won't help. Returns the first non-None result, or None. Never raises
    (Sacred Contract #3)."""
    model_seq = [m for m in (models or []) if m] or [""]
    for m_idx, model in enumerate(model_seq):
        seq = rotation_sequence(seed_key)
        if not seq:
            return None
        result, exhausted_overload = _run_key_rotation(once_km, model, label=label, seq=seq)
        if result is not None:
            return result
        if not exhausted_overload:
            return None
        if m_idx < len(model_seq) - 1:
            logger.warning(
                "key_pool: %s exhausted all %d key(s) on model=%s (overload/quota) — "
                "falling back to model=%s",
                label, len(seq), model or "-", model_seq[m_idx + 1],
            )
    return None


def pool_for(provider: str, seed_key: str = "") -> "list[str]":
    """Provider-agnostic key pool. For ``gemini`` this is exactly :func:`pool`
    (``GEMINI_API_KEYS`` → ``GEMINI_API_KEY``). For any other provider it reads
    ``<PROVIDER>_API_KEYS`` (comma-separated) else ``<PROVIDER>_API_KEY``.

    ``seed_key`` (the already-resolved key, which may come from a request payload
    rather than the env) is placed FIRST when present so an explicitly supplied
    key is always tried before the env pool. Deduped, order-preserving; blank
    entries dropped. Never raises — returns ``[seed_key]`` (or ``[]``) on any error."""
    keys: list[str] = []
    try:
        p = (provider or "").strip().lower()
        if p == "gemini":
            keys = pool()
        elif p:
            up = p.upper()
            multi = [k.strip() for k in (os.getenv(f"{up}_API_KEYS", "") or "").split(",") if k.strip()]
            if multi:
                keys = multi
            else:
                single = (os.getenv(f"{up}_API_KEY", "") or "").strip()
                keys = [single] if single else []
    except Exception:
        keys = []
    out: list[str] = []
    if seed_key and seed_key not in out:
        out.append(seed_key)
    for k in keys:
        if k and k not in out:
            out.append(k)
    return out


def _rotation_sequence_keys(seed: str, keys: "list[str]") -> "list[str]":
    """Ordered keys to try for one request over an explicit ``keys`` list: ``seed``
    first (if real), then the remaining keys non-cooled before cooled. Deduped.
    The provider-agnostic sibling of :func:`rotation_sequence` (which is gemini-only)."""
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
    seen: set[str] = set()
    return [k for k in seq if k and (k not in seen and not seen.add(k))]


def call_with_key_rotation(
    once_factory: Callable[[str], Optional[object]],
    *,
    label: str,
    seed_key: str,
    provider: str,
) -> Optional[object]:
    """Provider-agnostic single-model key rotation for OpenAI / Claude (and any
    future provider), mirroring :func:`call_gemini_with_rotation` but sourcing the
    pool from ``<PROVIDER>_API_KEYS``/``<PROVIDER>_API_KEY`` via :func:`pool_for`.

    Rotates ``once_factory(key)`` across the pool: RATE-LIMIT (429/quota) cools the
    key and advances; TRANSIENT (503/504) advances without cooling; a hard failure
    (auth / bad prompt / empty response) fails fast. Returns the first non-None
    result, or None. Never raises (Sacred Contract #3). The shared ``_cooldown_until``
    map is keyed by the raw key string, so cooldowns are correct across providers."""
    keys = pool_for(provider, seed_key=seed_key)
    seq = _rotation_sequence_keys(seed_key, keys)
    if not seq:
        return None
    result, _exhausted = _run_key_rotation(
        lambda _k, _m: once_factory(_k), "", label=label, seq=seq,
    )
    return result


def call_gemini_with_rotation(
    once_factory: Callable[[str], Optional[object]],
    *,
    label: str,
    seed_key: str,
) -> Optional[object]:
    """Single-model key rotation (frozen public API — used by TTS + image
    providers). Rotates ``once_factory(key)`` across the pool:
      - RATE-LIMIT (429/quota): cool the key, try the next one.
      - TRANSIENT (503 overload / 504 timeout): key is NOT at fault — do not
        cool it; sleep briefly and try the next key.
      - anything else (bad prompt / parse / auth): fail fast.
    Returns the first non-None result, or None. Never raises.

    Backed by :func:`call_gemini_with_model_rotation` with a single
    (caller-baked) model so behaviour is byte-identical to the pre-model-
    rotation implementation. Callers that ALSO want model fallback use
    ``call_gemini_with_model_rotation`` directly with a ``model_chain``."""
    return call_gemini_with_model_rotation(
        lambda _k, _m: once_factory(_k),
        label=label, seed_key=seed_key, models=[""],
    )
