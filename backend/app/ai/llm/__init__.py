"""
llm — multi-provider LLM dispatch for segment selection.

Routes select_segments() to the right provider implementation by name.
Each provider module exposes `select_segments(...)` with the same signature
and returns the shared GroqSegment dataclass (kept for backward compat —
both legacy Groq path and new providers reuse the same parser + dataclass).

Adding a new provider: drop a `<name>_provider.py` with `select_segments(...)`
in this directory and add a branch in `select_segments()` below.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.ai.analysis.groq.parser import GroqSegment, LLMSegment

logger = logging.getLogger("app.render.llm")
logger.info("llm: dispatcher loaded (build=2026-06-01.i1-multi-provider)")

SUPPORTED_PROVIDERS = ("groq", "gemini", "openai", "claude")
DEFAULT_PROVIDER = "groq"


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

    Returns None on any failure — caller must hard-fail in groq_only_mode.
    editorial_hint is passed through to the prompt builder — see prompts.py.
    """
    p = (provider or DEFAULT_PROVIDER).strip().lower()
    if p == "groq":
        from app.ai.analysis.groq import select_segments as _impl
    elif p == "gemini":
        from app.ai.llm.gemini_provider import select_segments as _impl
    elif p == "openai":
        from app.ai.llm.openai_provider import select_segments as _impl
    elif p == "claude":
        from app.ai.llm.claude_provider import select_segments as _impl
    else:
        logger.warning(
            "llm: provider %r not in SUPPORTED_PROVIDERS=%s",
            provider, SUPPORTED_PROVIDERS,
        )
        return None
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
