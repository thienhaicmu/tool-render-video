"""
client.py — Groq segment selection client.

Calls Groq directly with our segment-selection system prompt + JSON mode.
Bypasses the shared GroqProvider (which uses a different system prompt
for the deleted cloud-analyzer flow and would confuse the model).

AI Safety (Contract 3): all exceptions caught internally — never raises.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.ai.analysis.groq.parser import GroqSegment, parse_segment_response
from app.ai.analysis.groq.prompts import build_segment_prompt

logger = logging.getLogger("app.ai.analysis.groq.client")

_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
_DEFAULT_MODEL = "llama-3.1-8b-instant"
_MAX_TOKENS = 4096   # plenty for ~20 segments × ~200 chars each
_TEMPERATURE = 0.2

try:
    from groq import Groq as _GroqClient
    _GROQ_SDK = True
except ImportError:
    _GROQ_SDK = False

try:
    import openai as _openai
    _OPENAI_COMPAT = True
except ImportError:
    _OPENAI_COMPAT = False


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
    """Send SRT transcript to Groq and return selected segments.

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
        logger.warning("groq_client: unexpected error — %s", exc, exc_info=True)
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
    if not (_GROQ_SDK or _OPENAI_COMPAT):
        logger.warning("groq_client: no SDK available (install 'groq' or 'openai')")
        return None
    if not api_key:
        logger.warning("groq_client: no api_key supplied")
        return None
    if not srt_content or not srt_content.strip():
        logger.warning("groq_client: empty transcript")
        return None

    system_prompt, user_prompt = build_segment_prompt(
        srt_content=srt_content,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        language=language,
    )

    resolved_model = model or _DEFAULT_MODEL
    logger.info(
        "groq_client: calling model=%s output_count=%d min_sec=%.0f max_sec=%.0f "
        "video_dur=%.0f srt_chars=%d",
        resolved_model, output_count, min_sec, max_sec, video_duration, len(srt_content),
    )

    raw = _call_groq(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("groq_client: empty API response (model=%s)", resolved_model)
        return None

    # Log raw response at INFO so prompt/parser mismatches are visible in prod.
    # Cap length to avoid log spam on long responses.
    _preview = raw if len(raw) <= 2000 else raw[:2000] + f"... [{len(raw) - 2000} more chars]"
    logger.info("groq_client: raw response (model=%s):\n%s", resolved_model, _preview)

    segments = parse_segment_response(
        raw=raw,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
    )

    if segments is not None:
        logger.info(
            "groq_client: parsed %d/%d valid segments (model=%s)",
            len(segments), output_count, resolved_model,
        )
    return segments


def _call_groq(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Direct call to Groq Chat Completions with JSON mode.

    Prefers the native groq SDK; falls back to openai-compatible client.
    """
    # JSON mode requires the word "json" in the prompt — already present
    # in our user template, but enforce defensively.
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    if _GROQ_SDK:
        try:
            client = _GroqClient(api_key=api_key)
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                response_format={"type": "json_object"},
                timeout=30,
            )
            return resp.choices[0].message.content
        except Exception as exc:
            logger.warning("groq_client: native SDK call failed (model=%s) — %s", model, exc)

    if _OPENAI_COMPAT:
        try:
            client = _openai.OpenAI(api_key=api_key, base_url=_GROQ_BASE_URL, timeout=30)
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=_MAX_TOKENS,
                temperature=_TEMPERATURE,
                response_format={"type": "json_object"},
            )
            return resp.choices[0].message.content
        except Exception as exc:
            logger.warning("groq_client: openai-compat call failed (model=%s) — %s", model, exc)

    return None
