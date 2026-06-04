"""
claude_provider.py — Anthropic Claude implementation of segment selection.

Uses the anthropic SDK. Default: claude-haiku-4-5 — fast, cheap, and
follows JSON instructions reliably (Haiku 4.5 has near-Sonnet quality
on structured output tasks at ~1/5 the cost).

Context window: 200K tokens. Vietnamese support is excellent.

Claude does not have a native JSON mode flag like OpenAI/Gemini, but the
shared prompt template explicitly asks for a single JSON object and
Haiku 4.5 honours that. The parser tolerates surrounding text just in case.

AI Safety (Contract 3): never raises — returns None on any error.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.ai.llm.parser import LLMSegment, parse_segment_response
from app.ai.llm.prompts import build_segment_prompt

logger = logging.getLogger("app.render.claude_client")
logger.info("claude_provider: module loaded (build=2026-06-01.i3-claude)")

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
_MAX_SRT_CHARS = int(os.getenv("CLAUDE_MAX_SRT_CHARS", "50000"))  # ~12K tokens
_MAX_TOKENS = 4096
_TEMPERATURE = 0.2

try:
    from anthropic import Anthropic as _AnthClient
    _ANTHROPIC_SDK = True
except ImportError:
    _AnthClient = None  # type: ignore[assignment]
    _ANTHROPIC_SDK = False


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
    """Send SRT to Claude and return selected segments."""
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
        logger.warning("claude_client: unexpected error — %s", exc, exc_info=True)
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
    if not _ANTHROPIC_SDK:
        logger.warning("claude_client: anthropic SDK not installed")
        return None
    if not api_key:
        logger.warning("claude_client: no api_key supplied")
        return None
    if not srt_content or not srt_content.strip():
        logger.warning("claude_client: empty transcript")
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
        "claude_client: calling model=%s output_count=%d min_sec=%.0f max_sec=%.0f "
        "video_dur=%.0f srt_chars=%d prompt_chars=%d est_tokens=%d",
        resolved_model, output_count, min_sec, max_sec, video_duration,
        len(srt_content), _prompt_chars, _est_tokens,
    )

    raw = _call_claude(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("claude_client: empty API response (model=%s)", resolved_model)
        return None

    _preview = raw if len(raw) <= 2000 else raw[:2000] + f"... [{len(raw) - 2000} more chars]"
    logger.info("claude_client: raw response (model=%s):\n%s", resolved_model, _preview)

    segments = parse_segment_response(
        raw=raw,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
    )

    if segments is not None:
        logger.info(
            "claude_client: parsed %d/%d valid segments (model=%s)",
            len(segments), output_count, resolved_model,
        )
    return segments


def _call_claude(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Direct Anthropic Messages API call."""
    try:
        client = _AnthClient(api_key=api_key, timeout=30)
        resp = client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            temperature=_TEMPERATURE,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        # Claude returns content blocks; concatenate text-type blocks.
        if not resp.content:
            return None
        parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
        return "\n".join(parts) if parts else None
    except Exception as exc:
        logger.warning("claude_client: API call failed (model=%s) — %s", model, exc)
        return None
