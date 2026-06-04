"""
openai_provider.py — OpenAI implementation of segment selection.

Uses the openai SDK with native JSON mode (response_format=json_object).
Default model: gpt-4o-mini — cheapest, fastest, reliable structured output.
Context window: 128K tokens — plenty for 30K-char SRT + prompt.

AI Safety (Contract 3): never raises — returns None on any error.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.ai.llm.parser import LLMSegment, parse_segment_response
from app.ai.llm.prompts import build_segment_prompt

logger = logging.getLogger("app.render.openai_client")
logger.info("openai_provider: module loaded (build=2026-06-01.i2-openai)")

_DEFAULT_MODEL = "gpt-4o-mini"
_MAX_SRT_CHARS = int(os.getenv("OPENAI_MAX_SRT_CHARS", "30000"))  # ~7.5K tokens
_MAX_TOKENS = 4096
_TEMPERATURE = 0.2

try:
    import openai as _openai
    _OPENAI_SDK = True
except ImportError:
    _openai = None  # type: ignore[assignment]
    _OPENAI_SDK = False


def select_segments(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str = "",
    model: Optional[str] = None,
    language: str = "auto",
) -> Optional[list[LLMSegment]]:
    """Send SRT to OpenAI and return selected segments."""
    try:
        return _run(
            srt_content=srt_content,
            output_count=output_count,
            min_sec=min_sec,
            max_sec=max_sec,
            video_duration=video_duration,
            api_key=api_key,
            model=model,
            language=language,
        )
    except Exception as exc:
        logger.warning("openai_client: unexpected error — %s", exc, exc_info=True)
        return None


def _run(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str,
    model: Optional[str],
    language: str,
) -> Optional[list[LLMSegment]]:
    if not _OPENAI_SDK:
        logger.warning("openai_client: openai SDK not installed")
        return None
    if not api_key:
        logger.warning("openai_client: no api_key supplied")
        return None
    if not srt_content or not srt_content.strip():
        logger.warning("openai_client: empty transcript")
        return None

    system_prompt, user_prompt = build_segment_prompt(
        srt_content=srt_content,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        language=language,
        max_srt_chars=_MAX_SRT_CHARS,
    )

    resolved_model = model or _DEFAULT_MODEL
    _prompt_chars = len(system_prompt) + len(user_prompt)
    _est_tokens = _prompt_chars // 4
    logger.info(
        "openai_client: calling model=%s output_count=%d min_sec=%.0f max_sec=%.0f "
        "video_dur=%.0f srt_chars=%d prompt_chars=%d est_tokens=%d",
        resolved_model, output_count, min_sec, max_sec, video_duration,
        len(srt_content), _prompt_chars, _est_tokens,
    )

    raw = _call_openai(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("openai_client: empty API response (model=%s)", resolved_model)
        return None

    _preview = raw if len(raw) <= 2000 else raw[:2000] + f"... [{len(raw) - 2000} more chars]"
    logger.info("openai_client: raw response (model=%s):\n%s", resolved_model, _preview)

    segments = parse_segment_response(
        raw=raw,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
    )

    if segments is not None:
        logger.info(
            "openai_client: parsed %d/%d valid segments (model=%s)",
            len(segments), output_count, resolved_model,
        )
    return segments


def _call_openai(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Direct OpenAI Chat Completions call with JSON mode."""
    try:
        client = _openai.OpenAI(api_key=api_key, timeout=30)
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content
    except Exception as exc:
        logger.warning("openai_client: API call failed (model=%s) — %s", model, exc)
        return None
