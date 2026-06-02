"""
gemini_provider.py — Google Gemini implementation of segment selection.

Uses the unified google-genai SDK (Gemini 2.0 Flash by default).
Free tier: 1M tokens/day, 15 RPM. Context window: 1M tokens — large
enough to skip the aggressive truncation Groq needs.

Reuses the shared prompt template and parser from app.ai.analysis.groq.*
so prompt evolution stays in one place.

AI Safety (Contract 3): never raises — returns None on any error.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.ai.analysis.groq.parser import GroqSegment, parse_segment_response
from app.ai.analysis.groq.prompts import build_segment_prompt

logger = logging.getLogger("app.render.gemini_client")
logger.info("gemini_provider: module loaded (build=2026-06-01.i1-multi-provider)")

# Gemini Flash (latest): fast, free tier, 1M context. The "latest" alias
# auto-tracks the newest Flash release the account has access to —
# important because raw "gemini-2.0-flash" returns quota-exceeded on many
# accounts where "gemini-flash-latest" works.
_DEFAULT_MODEL = "gemini-flash-latest"

# Gemini 1M context lets us send much more transcript than Groq.
# 60K chars ≈ 15K tokens, still under any sane rate limit, captures
# ~30 min of dense Vietnamese speech.
_MAX_SRT_CHARS = int(os.getenv("GEMINI_MAX_SRT_CHARS", "60000"))

_MAX_OUTPUT_TOKENS = 4096
_TEMPERATURE = 0.2

try:
    from google import genai as _genai
    _GENAI_SDK = True
except ImportError:
    _GENAI_SDK = False


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
    """Send SRT to Gemini and return selected segments.

    Returns None on any failure — caller hard-fails the job in groq_only_mode.
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
        logger.warning("gemini_client: unexpected error — %s", exc, exc_info=True)
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
) -> Optional[list[GroqSegment]]:
    if not _GENAI_SDK:
        logger.warning("gemini_client: google-genai SDK not installed")
        return None
    if not api_key:
        logger.warning("gemini_client: no api_key supplied")
        return None
    if not srt_content or not srt_content.strip():
        logger.warning("gemini_client: empty transcript")
        return None

    system_prompt, user_prompt = build_segment_prompt(
        srt_content=srt_content,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        language=language,
        max_srt_chars=_MAX_SRT_CHARS,  # bigger cap than Groq
    )

    resolved_model = model or _DEFAULT_MODEL
    _prompt_chars = len(system_prompt) + len(user_prompt)
    _est_tokens = _prompt_chars // 4  # Gemini tokenization closer to 4 chars/token
    logger.info(
        "gemini_client: calling model=%s output_count=%d min_sec=%.0f max_sec=%.0f "
        "video_dur=%.0f srt_chars=%d prompt_chars=%d est_tokens=%d",
        resolved_model, output_count, min_sec, max_sec, video_duration,
        len(srt_content), _prompt_chars, _est_tokens,
    )

    raw = _call_gemini(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("gemini_client: empty API response (model=%s)", resolved_model)
        return None

    _preview = raw if len(raw) <= 2000 else raw[:2000] + f"... [{len(raw) - 2000} more chars]"
    logger.info("gemini_client: raw response (model=%s):\n%s", resolved_model, _preview)

    segments = parse_segment_response(
        raw=raw,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
    )

    if segments is not None:
        logger.info(
            "gemini_client: parsed %d/%d valid segments (model=%s)",
            len(segments), output_count, resolved_model,
        )
    return segments


def _call_gemini(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Call Gemini Chat with JSON-object output mode.

    TODO (Sprint 4.5 follow-up, audit 2026-06-02 P2-B2): google-genai SDK's
    timeout API is via `http_options={'timeout': milliseconds}` on Client(),
    but the exact signature varies across SDK versions. Add a verified
    timeout once the deployed google-genai version is pinned. Currently
    relies on SDK default (~10 min in 0.x; subject to change).
    """
    try:
        client = _genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "temperature": _TEMPERATURE,
                "max_output_tokens": _MAX_OUTPUT_TOKENS,
            },
        )
        return resp.text
    except Exception as exc:
        logger.warning("gemini_client: API call failed (model=%s) — %s", model, exc)
        return None
