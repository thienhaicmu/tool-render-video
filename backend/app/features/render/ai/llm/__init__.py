"""
llm — multi-provider LLM dispatch for RenderPlan emission.

Routes select_render_plan() to the right provider implementation by name.
Each provider module exposes select_render_plan(...) returning a RenderPlan.

Supported providers: gemini, openai, claude.
Adding a new provider: drop a `<name>_provider.py` with
`select_render_plan(...)` in this directory and add a branch in the
dispatch function below.
"""
from __future__ import annotations

import logging
import os
import time as _time
from typing import Optional

logger = logging.getLogger("app.render.llm")
logger.info("llm: dispatcher loaded (build=2026-06-04.sprint4c-render-plan-dual)")

SUPPORTED_PROVIDERS = ("gemini", "openai", "claude")
DEFAULT_PROVIDER = "gemini"

# When LLM_FALLBACK_ENABLED=1, a None result from the primary provider
# triggers sequential fallback through the remaining SUPPORTED_PROVIDERS.
# Default OFF — preserves existing behavior for all current deployments.
_LLM_FALLBACK_ENABLED: bool = os.getenv("LLM_FALLBACK_ENABLED", "0") == "1"


def _get_provider_impl(provider_name: str):
    """Return the select_render_plan callable for the named provider."""
    if provider_name == "gemini":
        from app.features.render.ai.llm.providers.gemini import select_render_plan as _impl
    elif provider_name == "openai":
        from app.features.render.ai.llm.providers.openai import select_render_plan as _impl
    elif provider_name == "claude":
        from app.features.render.ai.llm.providers.claude import select_render_plan as _impl
    else:
        logger.warning(
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s — falling back to gemini",
            provider_name, SUPPORTED_PROVIDERS,
        )
        from app.features.render.ai.llm.providers.gemini import select_render_plan as _impl
    return _impl


def select_render_plan(
    *,
    provider: str = DEFAULT_PROVIDER,
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str = "",
    model: Optional[str] = None,
    language: str = "auto",
    editorial_hint: str = "",
    target_duration: int = 0,
    clip_lock: list[dict] | None = None,
    clip_exclude: list[dict] | None = None,
) -> Optional["RenderPlan"]:
    """Dispatch RenderPlan emission to the named LLM provider.

    The provider is asked to emit a full RenderPlan (clips + subtitle_policy +
    camera_strategy + audio_plan + overlays) in a single call.

    ``target_duration`` (T2.4 — Audit 2026-06-08 closure, Batch A
    V8-A1) is the creator's soft total-duration target in seconds, 0 =
    disabled (backward-compat default — callers that don't pass it
    behave exactly as pre-T2.4).

    ``clip_lock`` / ``clip_exclude`` (Strategic-1 — Audit 2026-06-08
    closure, Batch A V8-A12) are UP26 Pro Timeline Steering hard
    constraints — lists of {start_sec, end_sec} dicts. None / empty
    disables each prompt section (backward-compat default).

    When ``LLM_FALLBACK_ENABLED=1`` and the primary provider returns None,
    the remaining SUPPORTED_PROVIDERS are tried in order until one succeeds.
    Default is OFF — fallback behavior must be explicitly opted in.

    Returns None on any failure. Sacred Contract #3 — provider modules
    catch all exceptions and surface None at the wire.
    """
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        logger.warning(
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s — using gemini",
            provider, SUPPORTED_PROVIDERS,
        )
        primary = "gemini"

    chain = [primary]
    if _LLM_FALLBACK_ENABLED:
        chain += [p for p in SUPPORTED_PROVIDERS if p != primary]

    kwargs = dict(
        srt_content=srt_content,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
        api_key=api_key,
        model=model,
        language=language,
        editorial_hint=editorial_hint,
        target_duration=target_duration,
        clip_lock=clip_lock,
        clip_exclude=clip_exclude,
    )

    for _p in chain:
        _impl = _get_provider_impl(_p)
        _t0 = _time.perf_counter()
        result = _impl(**kwargs)
        _status = "success" if result is not None else "empty"
        try:
            from app.services.metrics import (
                LLM_RENDER_PLAN_CALLS, LLM_RENDER_PLAN_LATENCY, LLM_SEGMENTS_SELECTED,
            )
            LLM_RENDER_PLAN_CALLS.labels(provider=_p, status=_status).inc()
            LLM_RENDER_PLAN_LATENCY.labels(provider=_p).observe(_time.perf_counter() - _t0)
            if result is not None:
                LLM_SEGMENTS_SELECTED.labels(provider=_p).inc(len(result.clips))
        except Exception:
            pass
        if result is not None:
            if _p != primary:
                logger.info(
                    "llm: fallback succeeded provider=%s (primary=%s returned None)", _p, primary,
                )
            return result
        logger.warning("llm: provider=%s returned None", _p)

    return None
