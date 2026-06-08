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
from typing import Optional

logger = logging.getLogger("app.render.llm")
logger.info("llm: dispatcher loaded (build=2026-06-04.sprint4c-render-plan-dual)")

SUPPORTED_PROVIDERS = ("gemini", "openai", "claude")
DEFAULT_PROVIDER = "gemini"


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
) -> Optional["RenderPlan"]:
    """Dispatch RenderPlan emission to the named LLM provider.

    The provider is asked to emit a full RenderPlan (clips + subtitle_policy +
    camera_strategy + audio_plan + overlays) in a single call.

    Returns None on any failure. Sacred Contract #3 — provider modules
    catch all exceptions and surface None at the wire.
    """
    p = (provider or DEFAULT_PROVIDER).strip().lower()
    if p == "gemini":
        from app.features.render.ai.llm.providers.gemini import select_render_plan as _impl
    elif p == "openai":
        from app.features.render.ai.llm.providers.openai import select_render_plan as _impl
    elif p == "claude":
        from app.features.render.ai.llm.providers.claude import select_render_plan as _impl
    else:
        logger.warning(
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s — render_plan falling back to gemini",
            provider, SUPPORTED_PROVIDERS,
        )
        from app.features.render.ai.llm.providers.gemini import select_render_plan as _impl
    return _impl(
        srt_content=srt_content,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
        api_key=api_key,
        model=model,
        language=language,
        editorial_hint=editorial_hint,
    )

