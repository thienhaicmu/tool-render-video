"""
client.py — Groq segment selection client.

Thin orchestration layer:
  1. Build prompt via prompts.py
  2. Call Groq API via existing GroqProvider (reuses SDK + fallback logic)
  3. Parse response via parser.py
  4. Return list[GroqSegment] or None (caller uses local fallback)

AI Safety (Contract 3): all exceptions caught internally — never raises.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.ai.analysis.groq.parser import GroqSegment, parse_segment_response
from app.ai.analysis.groq.prompts import build_segment_prompt

logger = logging.getLogger("app.ai.analysis.groq.client")

try:
    from app.ai.analysis.cloud.groq_provider import GroqProvider as _GroqProvider
    _PROVIDER_AVAILABLE = True
except ImportError:
    _PROVIDER_AVAILABLE = False


def select_segments(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str = "",
    model: Optional[str] = None,
    language: str = "auto",
) -> Optional[list[GroqSegment]]:
    """
    Send SRT transcript to Groq and return selected segments.

    Returns None on any failure — pipeline falls back to local scorer.
    """
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
        logger.debug("groq_client: unexpected error — %s", exc)
        return None


# ── Internal ──────────────────────────────────────────────────────────────────

def _run(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str,
    model: Optional[str],
    language: str,
) -> Optional[list[GroqSegment]]:
    if not _PROVIDER_AVAILABLE:
        logger.debug("groq_client: GroqProvider not available (SDK missing)")
        return None

    if not api_key:
        logger.debug("groq_client: no api_key supplied")
        return None

    if not srt_content or not srt_content.strip():
        logger.debug("groq_client: empty transcript")
        return None

    system_prompt, user_prompt = build_segment_prompt(
        srt_content=srt_content,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        language=language,
    )

    # Build a combined prompt string for GroqProvider._call_api()
    # GroqProvider uses get_system_prompt() internally, so we pass
    # a self-contained prompt that includes both roles.
    provider = _GroqProvider(api_key=api_key, model=model)

    # Inject system instruction into the user message since GroqProvider
    # uses its own fixed system prompt. Override by subclassing is not
    # needed — instead we prepend our system as a header in the user turn.
    full_prompt = f"[INSTRUCTION]\n{system_prompt}\n\n[TASK]\n{user_prompt}"
    raw = provider._call_api(full_prompt)

    if not raw:
        logger.debug("groq_client: empty API response")
        return None

    segments = parse_segment_response(
        raw=raw,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
    )

    if segments is not None:
        logger.info(
            "groq_client: selected %d/%d segments (model=%s)",
            len(segments), output_count, model or "default",
        )
    return segments
