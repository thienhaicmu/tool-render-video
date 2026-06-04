"""
llm — multi-provider LLM dispatch for segment selection.

Routes select_segments() to the right provider implementation by name.
Each provider module exposes `select_segments(...)` with the same signature
and returns the shared LLMSegment dataclass.

Supported providers: gemini, openai, claude.
Adding a new provider: drop a `<name>_provider.py` with `select_segments(...)`
in this directory and add a branch in `select_segments()` below.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.ai.llm.gemini_provider import LLMSegment

logger = logging.getLogger("app.render.llm")
logger.info("llm: dispatcher loaded (build=2026-06-04.gemini-default)")

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

    Returns None on any failure — caller must hard-fail the pipeline.
    editorial_hint is passed through to the prompt builder.
    """
    p = (provider or DEFAULT_PROVIDER).strip().lower()
    if p == "gemini":
        from app.ai.llm.gemini_provider import select_segments as _impl
    elif p == "openai":
        from app.ai.llm.openai_provider import select_segments as _impl
    elif p == "claude":
        from app.ai.llm.claude_provider import select_segments as _impl
    else:
        logger.warning(
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s — falling back to gemini",
            provider, SUPPORTED_PROVIDERS,
        )
        from app.ai.llm.gemini_provider import select_segments as _impl
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
