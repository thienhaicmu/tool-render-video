"""
llm â€” multi-provider LLM dispatch for segment selection and RenderPlan emission.

Routes select_segments() / select_render_plan() to the right provider
implementation by name. Each provider module exposes both entry points
with matching signatures; `select_segments` returns a list of LLMSegment
dataclasses (legacy path), `select_render_plan` returns a RenderPlan
(Sprint 4.C dual-mode foundation â€” wired by Sprint 4.D behind a flag).

Supported providers: gemini, openai, claude.
Adding a new provider: drop a `<name>_provider.py` with `select_segments(...)`
AND `select_render_plan(...)` in this directory and add a branch in each
dispatch function below.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.features.render.ai.llm.providers.gemini import LLMSegment
    from app.domain.render_plan import RenderPlan

logger = logging.getLogger("app.render.llm")
logger.info("llm: dispatcher loaded (build=2026-06-04.sprint4c-render-plan-dual)")

SUPPORTED_PROVIDERS = ("gemini", "openai", "claude")
DEFAULT_PROVIDER = "gemini"


def select_segments(
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
) -> Optional[list["LLMSegment"]]:
    """Dispatch segment selection to the named LLM provider.

    Returns None on any failure â€” caller must hard-fail the pipeline.
    editorial_hint is passed through to the prompt builder.
    """
    p = (provider or DEFAULT_PROVIDER).strip().lower()
    if p == "gemini":
        from app.features.render.ai.llm.providers.gemini import select_segments as _impl
    elif p == "openai":
        from app.features.render.ai.llm.providers.openai import select_segments as _impl
    elif p == "claude":
        from app.features.render.ai.llm.providers.claude import select_segments as _impl
    else:
        logger.warning(
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s â€” falling back to gemini",
            provider, SUPPORTED_PROVIDERS,
        )
        from app.features.render.ai.llm.providers.gemini import select_segments as _impl
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

    Sprint 4.C â€” additive partner of select_segments. The provider is
    asked to emit a full RenderPlan (clips + subtitle_policy +
    camera_strategy + audio_plan + overlays) in a single call. Sprint
    4.D will gate the orchestrator behind a feature flag and treat a
    None return as the signal to fall back to the Sprint 2.2 builder
    shim path.

    Returns None on any failure. Sacred Contract #3 â€” provider modules
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
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s â€” render_plan falling back to gemini",
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

