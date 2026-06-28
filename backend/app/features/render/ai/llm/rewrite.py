"""
rewrite — multi-provider LLM dispatch for TTS subtitle rewrite.

v2 (2026-06-27): segmented + timed return type.
rewrite_subtitle() now returns `Optional[list[dict]]` — a list of
{start, end, text} segments — instead of a single string. The plain-text
fallback path is encapsulated in the parser: when the LLM ignores the
JSON instruction, the parser returns ONE segment spanning the whole clip.

Supported providers: gemini, openai, claude (mirrors __init__.py).
"""
from __future__ import annotations

import logging
import os
import time as _time
from typing import Optional

logger = logging.getLogger("app.render.llm.rewrite")

SUPPORTED_PROVIDERS = ("gemini", "openai", "claude")
DEFAULT_PROVIDER = "gemini"
_LLM_FALLBACK_ENABLED: bool = os.getenv("LLM_FALLBACK_ENABLED", "1") == "1"


def _get_provider_rewrite_impl(provider_name: str):
    """Return the rewrite_subtitle callable for the named provider."""
    if provider_name == "gemini":
        from app.features.render.ai.llm.providers.gemini import rewrite_subtitle as _impl
    elif provider_name == "openai":
        from app.features.render.ai.llm.providers.openai import rewrite_subtitle as _impl
    elif provider_name == "claude":
        from app.features.render.ai.llm.providers.claude import rewrite_subtitle as _impl
    else:
        logger.warning(
            "rewrite: provider %r not in %s falling back to gemini",
            provider_name, SUPPORTED_PROVIDERS,
        )
        from app.features.render.ai.llm.providers.gemini import rewrite_subtitle as _impl
    return _impl


def rewrite_subtitle(
    *,
    provider: str = DEFAULT_PROVIDER,
    srt_segmented: str,
    clip_duration_sec: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional[list[dict]]:
    """Dispatch segmented subtitle-rewrite to the named LLM provider.

    Inputs:
      srt_segmented: source SRT pre-formatted as one line per utterance
        ("[start - end] text"). Use llm.rewrite_prompts.format_segments_for_prompt
        to produce it from a parsed SRT block list.
      clip_duration_sec: total clip duration in seconds (TOTAL narration cap).

    Returns: list of {start, end, text} segments (one per spoken utterance)
    OR None on any failure. Sacred Contract #3 — provider modules catch all
    exceptions; this function adds the fallback chain wrapper.

    When LLM_FALLBACK_ENABLED=1 and primary returns None, the remaining
    SUPPORTED_PROVIDERS are tried in order until one succeeds.
    """
    primary = (provider or DEFAULT_PROVIDER).strip().lower()
    if primary not in SUPPORTED_PROVIDERS:
        logger.warning("rewrite: provider %r unsupported using gemini", provider)
        primary = "gemini"
    chain = [primary]
    if _LLM_FALLBACK_ENABLED:
        chain += [p for p in SUPPORTED_PROVIDERS if p != primary]
    kwargs = dict(
        srt_segmented=srt_segmented,
        clip_duration_sec=clip_duration_sec,
        target_language=target_language,
        tone=tone,
        api_key=api_key,
        model=model,
    )
    for _p in chain:
        _impl = _get_provider_rewrite_impl(_p)
        _t0 = _time.perf_counter()
        result = _impl(**kwargs)
        _status = "success" if result else "empty"
        try:
            from app.services.metrics import (
                LLM_REWRITE_CALLS, LLM_REWRITE_LATENCY, LLM_REWRITE_CHAR_DELTA,
            )
            LLM_REWRITE_CALLS.labels(provider=_p, status=_status).inc()
            LLM_REWRITE_LATENCY.labels(provider=_p).observe(_time.perf_counter() - _t0)
            if result:
                _out_chars = sum(len(s.get("text", "")) for s in result)
                _in_chars = len(srt_segmented or "")
                LLM_REWRITE_CHAR_DELTA.labels(provider=_p).observe(_out_chars - _in_chars)
        except Exception:
            pass
        if result:
            if _p != primary:
                logger.info(
                    "rewrite: fallback succeeded provider=%s (primary=%s None)", _p, primary,
                )
            return result
        logger.warning("rewrite: provider=%s returned None", _p)
    return None
