"""
comprehension_stage.py — whole-source semantic understanding pipeline stage.

Architecture-review Batch C (2026-06-30). Hoists what used to be the recap
dispatcher's hidden pass-1 ("Story Intelligence") into a named pipeline stage
that:

  1. Both Recap and Clip pipelines CAN call (Recap wires it in Batch C;
     Clip wires it in Batch C.1). The stage produces a StoryModel — the
     domain object that represents whole-film understanding.
  2. Persists the StoryModel to ``jobs.story_model_json`` so re-edit UI,
     QA gates, and future consumers can read it without re-running the LLM.
  3. Caches the result on disk at ``APP_DATA_DIR/cache/comprehension/`` so
     a re-render with the same transcript + provider + model + PROMPT_VERSION
     skips the LLM entirely.
  4. Emits Sacred Contract #6-additive WS events (``comprehension.start``
     and ``comprehension.done``) so the UI sees progress between Whisper
     and the recap binding pass.
  5. Also fires the legacy ``recap.pass1.done`` event with the same shape
     (Q3=a — forever alias for back-compat with Batch A consumers).

Guarantees (Sacred Contract #3):
  - Every public entry point catches all exceptions and returns ``None``.
  - A failing Comprehension call NEVER crashes a live render — Recap
    falls back to letting ``select_recap_plan`` run its internal pass-1.

Kill switch (one env var, no code revert needed):
  ``STORY_INTELLIGENCE_HOIST_ENABLED=0`` → ``run_comprehension`` returns
  ``None`` immediately. The Recap pipeline then calls ``select_recap_plan``
  with no ``story_model=`` kwarg, which restores the legacy Batch-A
  internal pass-1 path bit-identically.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.config import APP_DATA_DIR
from app.domain.recap_plan import StoryModel, story_model_from_dict
from app.services.metrics import instrument_cache as _instrument_cache

logger = logging.getLogger("app.render.comprehension")

# Subdir under cache/ — the maintenance pruner walks every cache subdir, so
# adding this one requires no scheduler wiring change (covered by the existing
# subdir-agnostic prune test in test_llm_cache.py).
_COMPREHENSION_CACHE_SUBDIR = "comprehension"

# TTL aligned with the LLM disk cache (72h, see ai/llm/cache.py). A different
# value here would create surprising "the StoryModel says X but the Recap
# response is from a different generation" race windows.
_COMPREHENSION_CACHE_TTL_SEC = 72 * 3600


def is_hoist_enabled() -> bool:
    """Public form of the kill switch — the recap_pipeline calls this once to
    decide whether to use the Comprehension stage (hoist ON) or the legacy
    Batch-A in-dispatcher pass-1 path (hoist OFF). Read on every call (not at
    module load) so an operator can flip the env var without restarting."""
    return os.getenv("STORY_INTELLIGENCE_HOIST_ENABLED", "1") == "1"


# Internal alias for back-compat with this module's tests.
_is_hoist_enabled = is_hoist_enabled


def _resolve_prompt_version() -> int:
    """Late import keeps comprehension_stage importable even if prompts.py is
    partially broken during a hot reload. Mirrors ai/llm/cache.py exactly."""
    try:
        from app.features.render.ai.llm.prompts import PROMPT_VERSION as _PV
        return int(_PV)
    except Exception:
        return 0


def _transcript_hash(srt_content: str) -> str:
    """SHA-256 of the (truncated) transcript bytes — same hash function as
    the LLM cache so the two caches naturally invalidate in lockstep when the
    transcript content changes."""
    return hashlib.sha256((srt_content or "").encode("utf-8", errors="replace")).hexdigest()


def _build_cache_key(
    provider: str,
    model: str,
    target_language: str,
    tone: str,
    transcript_hash: str,
) -> str:
    """Content-addressable cache key. Folds in PROMPT_VERSION so a Batch A-style
    prompt bump invalidates the Comprehension cache by construction."""
    pv = _resolve_prompt_version()
    parts = "|".join([
        f"v{pv}",
        str(provider or ""),
        str(model or ""),
        str(target_language or ""),
        str(tone or ""),
        str(transcript_hash or ""),
    ])
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()


def _cache_dir() -> Path:
    return APP_DATA_DIR / "cache" / _COMPREHENSION_CACHE_SUBDIR


@_instrument_cache("comprehension")
def _comprehension_cache_get(cache_key: str) -> Optional[StoryModel]:
    """Return a cached StoryModel by key, or None on miss / expiry / error.

    Never raises. The decorator emits the cache_lookups_total counter with
    outcome ``hit`` / ``miss`` per call.
    """
    try:
        path = _cache_dir() / f"{cache_key}.json"
        if not path.exists():
            return None
        age = time.time() - path.stat().st_mtime
        if age > _COMPREHENSION_CACHE_TTL_SEC:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            return None
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        sm = story_model_from_dict(data)
        # Defensive: an empty StoryModel on a cache hit means the on-disk blob
        # is corrupt or schema-incompatible — treat it as a miss.
        return None if sm.is_empty() else sm
    except Exception as exc:
        logger.debug("comprehension cache_get miss due to error: %s", exc)
        return None


def _comprehension_cache_put(cache_key: str, story_model: StoryModel) -> bool:
    """Atomically persist a StoryModel to disk. Returns True on success.

    Never raises. Empty models are NOT cached — caching a failure would
    silently shadow a future successful pass-1 attempt.
    """
    try:
        if story_model is None or story_model.is_empty():
            return False
        cache_dir = _cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{cache_key}.json"
        payload = json.dumps(
            story_model.to_public_dict(), sort_keys=True, ensure_ascii=False,
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.debug("comprehension cache_put skipped due to error: %s", exc)
        return False


def _safe_emit(emit_fn: Optional[Callable[..., None]], **kwargs) -> None:
    """Invoke the WS emit callback, swallowing every exception. The emitter
    is observation-only — a broken metric backend or WS pump must never
    abort the Comprehension stage (Sacred Contract #6 ADDITIVE spirit)."""
    if emit_fn is None:
        return
    try:
        emit_fn(**kwargs)
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("comprehension: emit callback raised %s — ignored", exc)


def run_comprehension(
    *,
    job_id: str,
    channel_code: str,
    srt_content: str,
    video_duration: float,
    provider: str,
    api_key: str = "",
    model: Optional[str] = None,
    target_language: str = "vi-VN",
    tone: str = "",
    persist: bool = True,
    emit_fn: Optional[Callable[..., None]] = None,
    select_story_model_fn: Optional[Callable[..., Optional[StoryModel]]] = None,
    update_story_model_fn: Optional[Callable[[str, str], None]] = None,
) -> Optional[StoryModel]:
    """Run the Comprehension stage end-to-end.

    Returns the produced ``StoryModel`` or ``None``. ``None`` is the signal
    to the caller (recap_pipeline) to fall back to its legacy in-dispatcher
    pass-1 path; the rest of the render proceeds untouched.

    Parameters
    ----------
    job_id, channel_code : str
        Identify the WS event stream.
    srt_content : str
        The full Whisper transcript. Hashed for the cache key.
    video_duration : float
        Forwarded verbatim to ``select_story_model``.
    provider, api_key, model, target_language, tone :
        Forwarded verbatim to ``select_story_model``.
    persist : bool
        When True, write the result to ``jobs.story_model_json`` on success.
        Set False in tests / dry runs.
    emit_fn : Optional[Callable]
        ``_emit_render_event`` from render_events.py — injected so this
        module avoids a circular import. The stage emits
        ``comprehension.start``, ``comprehension.done``, and the
        ``recap.pass1.done`` alias.
    select_story_model_fn : Optional[Callable]
        Inject the dispatcher (``ai.llm.select_story_model``) for testability.
        Defaults to a late import of the real dispatcher.
    update_story_model_fn : Optional[Callable]
        Inject the persistence helper (``jobs_repo.update_story_model``) for
        testability. Defaults to a late import.

    Returns
    -------
    Optional[StoryModel]
        The produced model, or None on kill-switch / cache miss + LLM
        failure / any internal error.
    """
    # Kill switch — single env var = full revert to Batch-A internal pass-1.
    if not _is_hoist_enabled():
        logger.info(
            "comprehension: STORY_INTELLIGENCE_HOIST_ENABLED=0 — skipped for job_id=%s",
            job_id,
        )
        return None

    try:
        # 1. Compute the cache key BEFORE the LLM call so the same key fires
        # the WS event and the persistence path consistently.
        srt_hash = _transcript_hash(srt_content)
        cache_key = _build_cache_key(
            provider=provider, model=(model or ""),
            target_language=target_language, tone=tone,
            transcript_hash=srt_hash,
        )

        _safe_emit(
            emit_fn,
            channel_code=channel_code, job_id=job_id,
            event="comprehension.start",
            level="INFO",
            message="Comprehension: building Story Model",
            step="render.comprehension",
            context={"cache_key_prefix": cache_key[:12], "provider": provider},
        )

        # 2. Cache lookup.
        cached = _comprehension_cache_get(cache_key)
        if cached is not None:
            logger.info("comprehension: cache hit for job_id=%s", job_id)
            _persist_and_emit_done(
                story_model=cached, source="cache",
                job_id=job_id, channel_code=channel_code,
                persist=persist, emit_fn=emit_fn,
                update_story_model_fn=update_story_model_fn,
            )
            return cached

        # 3. LLM call.
        if select_story_model_fn is None:
            from app.features.render.ai.llm import select_story_model as _impl
            select_story_model_fn = _impl

        sm = None
        try:
            sm = select_story_model_fn(
                provider=provider, srt_content=srt_content,
                video_duration=video_duration, target_language=target_language,
                tone=tone, api_key=api_key, model=model,
            )
        except Exception as exc:
            # Defensive — providers already wrap, but a future regression
            # in the dispatcher should never break a live render.
            logger.warning("comprehension: select_story_model raised %s", exc)
            sm = None

        if sm is None or sm.is_empty():
            _safe_emit(
                emit_fn,
                channel_code=channel_code, job_id=job_id,
                event="comprehension.done",
                level="WARNING",
                message="Comprehension returned empty — fallback to legacy pass-1",
                step="render.comprehension",
                context={"ok": False, "source": "failed", "story_model": None},
            )
            # Legacy alias (Q3=a) — keep Batch A consumers working.
            _safe_emit(
                emit_fn,
                channel_code=channel_code, job_id=job_id,
                event="recap.pass1.done",
                level="WARNING",
                message="Pass 1 (Story Understanding) returned empty — single-pass fallback",
                step="render.recap",
                context={"pass": "story", "ok": False, "story_model": None},
            )
            return None

        # 4. Cache the result + persist + emit done.
        _comprehension_cache_put(cache_key, sm)
        _persist_and_emit_done(
            story_model=sm, source="llm",
            job_id=job_id, channel_code=channel_code,
            persist=persist, emit_fn=emit_fn,
            update_story_model_fn=update_story_model_fn,
        )
        return sm
    except Exception as exc:
        # Last-line catch — Sacred Contract #3. Recap falls back to legacy.
        logger.warning("comprehension: unhandled error for job_id=%s — %s", job_id, exc)
        return None


def _persist_and_emit_done(
    *,
    story_model: StoryModel,
    source: str,
    job_id: str,
    channel_code: str,
    persist: bool,
    emit_fn: Optional[Callable[..., None]],
    update_story_model_fn: Optional[Callable[[str, str], None]],
) -> None:
    """Side-effect helper: persist (if requested) and emit the done event +
    legacy alias. Pure best-effort — never raises out."""
    try:
        if persist:
            if update_story_model_fn is None:
                from app.db.jobs_repo import update_story_model as _impl
                update_story_model_fn = _impl
            try:
                update_story_model_fn(
                    job_id, json.dumps(story_model.to_public_dict(),
                                       sort_keys=True, ensure_ascii=False)
                )
            except Exception as exc:
                logger.warning("comprehension: persist failed for job_id=%s — %s", job_id, exc)
    except Exception:
        pass

    public = story_model.to_public_dict()
    _safe_emit(
        emit_fn,
        channel_code=channel_code, job_id=job_id,
        event="comprehension.done",
        level="INFO",
        message=f"Comprehension: Story Model ready ({source})",
        step="render.comprehension",
        context={"ok": True, "source": source, "story_model": public},
    )
    # Legacy alias — same shape Batch A used.
    _safe_emit(
        emit_fn,
        channel_code=channel_code, job_id=job_id,
        event="recap.pass1.done",
        level="INFO",
        message="Pass 1 (Story Understanding) complete",
        step="render.recap",
        context={"pass": "story", "ok": True, "story_model": public},
    )
