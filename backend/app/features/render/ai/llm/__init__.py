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
# Default ON — set LLM_FALLBACK_ENABLED=0 to opt out (primary-only, no
# cross-provider fallback; lower cost/latency on a failing render).
_LLM_FALLBACK_ENABLED: bool = os.getenv("LLM_FALLBACK_ENABLED", "1") == "1"

# R7 two-pass recap: when ON, a pass-1 "Story Model" call precedes scene
# selection so pass-2 plans FROM a committed whole-film understanding. Default ON
# — set RECAP_TWO_PASS=0 for the v1 single-pass behaviour (instant rollback, no
# code revert). Pass-1 failure is non-fatal: the plan falls back to single-pass.
_RECAP_TWO_PASS: bool = os.getenv("RECAP_TWO_PASS", "1") == "1"


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


def _get_recap_impl(provider_name: str):
    """Return the select_recap_plan callable for the named provider."""
    if provider_name == "openai":
        from app.features.render.ai.llm.providers.openai import select_recap_plan as _impl
    elif provider_name == "claude":
        from app.features.render.ai.llm.providers.claude import select_recap_plan as _impl
    else:
        from app.features.render.ai.llm.providers.gemini import select_recap_plan as _impl
    return _impl


def _get_story_impl(provider_name: str):
    """Return the select_story_model (pass-1) callable for the named provider, or
    None if that provider has no pass-1 implementation. Defensive — never raises."""
    try:
        if provider_name == "openai":
            from app.features.render.ai.llm.providers import openai as _mod
        elif provider_name == "claude":
            from app.features.render.ai.llm.providers import claude as _mod
        else:
            from app.features.render.ai.llm.providers import gemini as _mod
        return getattr(_mod, "select_story_model", None)
    except Exception as exc:
        logger.warning("llm: _get_story_impl(%s) import failed %s", provider_name, exc)
        return None


def select_story_model(
    *,
    provider: str = DEFAULT_PROVIDER,
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
):
    """Dispatch pass-1 Story Model selection to a provider. Returns a StoryModel or
    None (Sacred Contract #3). With LLM_FALLBACK_ENABLED, providers that have a
    pass-1 impl are tried in order until one yields a model."""
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    chain = [primary]
    if _LLM_FALLBACK_ENABLED:
        chain += [p for p in SUPPORTED_PROVIDERS if p != primary]
    kwargs = dict(
        srt_content=srt_content, video_duration=video_duration,
        target_language=target_language, tone=tone, api_key=api_key, model=model,
    )
    for _p in chain:
        impl = _get_story_impl(_p)
        if impl is None:
            continue
        try:
            result = impl(**kwargs)
        except Exception as exc:  # defensive — provider modules already never raise
            logger.warning("llm: select_story_model provider=%s raised %s", _p, exc)
            result = None
        if result is not None:
            if _p != primary:
                logger.info("llm: story fallback succeeded provider=%s (primary=%s None)", _p, primary)
            return result
    return None


def select_recap_plan(
    *,
    provider: str = DEFAULT_PROVIDER,
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional["RecapPlan"]:
    """Dispatch recap scene-selection (render_format="recap") to a provider.

    The provider selects chronological, act-structured scenes covering the
    whole film. Returns a RecapPlan or None (Sacred Contract #3). When
    LLM_FALLBACK_ENABLED=1 and the primary returns None, the remaining
    providers are tried in order.
    """
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        primary = "gemini"
    chain = [primary]
    if _LLM_FALLBACK_ENABLED:
        chain += [p for p in SUPPORTED_PROVIDERS if p != primary]
    # R7 pass-1: build the Story Model first (best-effort). None → single-pass,
    # so a flaky pass-1 never blocks a render (Sacred Contract #3).
    story_model = None
    if _RECAP_TWO_PASS:
        try:
            story_model = select_story_model(
                provider=primary, srt_content=srt_content, video_duration=video_duration,
                target_language=target_language, tone=tone, api_key=api_key, model=model,
            )
        except Exception as exc:
            logger.warning("llm: pass-1 story model raised %s — single-pass", exc)
            story_model = None
        logger.info("llm: recap two-pass enabled story_model=%s", story_model is not None)
    kwargs = dict(
        srt_content=srt_content,
        video_duration=video_duration,
        target_language=target_language,
        tone=tone,
        api_key=api_key,
        model=model,
        story_model=story_model,
    )
    for _p in chain:
        try:
            result = _get_recap_impl(_p)(**kwargs)
        except Exception as exc:  # defensive — provider modules already never raise
            logger.warning("llm: select_recap_plan provider=%s raised %s", _p, exc)
            result = None
        if result is not None:
            if _p != primary:
                logger.info("llm: recap fallback succeeded provider=%s (primary=%s None)", _p, primary)
            return result
        logger.warning("llm: recap provider=%s returned None", _p)
    return None


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
    target_platform: str = "",
    # S5 — creator preference hints (B+C). Defaults match what
    # build_render_plan_prompt treats as "no hint" so providers that
    # don't yet thread these through behave exactly as before.
    video_type: str = "auto",
    hook_strength: str = "balanced",
    ai_target_market: str = "",
    subtitle_emphasis: Optional[str] = None,
    multi_variant: bool = False,
    structure_bias: Optional[str] = None,
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
    Default is ON — set ``LLM_FALLBACK_ENABLED=0`` to opt out.

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
        target_platform=target_platform,
        # S5 — creator preferences (B+C)
        video_type=video_type,
        hook_strength=hook_strength,
        ai_target_market=ai_target_market,
        subtitle_emphasis=subtitle_emphasis,
        multi_variant=multi_variant,
        structure_bias=structure_bias,
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
