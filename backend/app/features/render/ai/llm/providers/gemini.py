"""
gemini_provider.py â€” Google Gemini implementation of segment selection.

Uses the unified google-genai SDK (Gemini 2.0 Flash by default).
Free tier: 1M tokens/day, 15 RPM. Context window: 1M tokens.

AI Safety (Contract 3): never raises â€” returns None on any error.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.features.render.ai.llm.parser import LLMSegment, parse_render_plan_response, parse_segment_response
from app.features.render.ai.llm.prompts import build_render_plan_prompt, build_segment_prompt
from app.domain.render_plan import RenderPlan

logger = logging.getLogger("app.render.gemini_client")
logger.info("gemini_provider: module loaded (build=2026-06-01.i1-multi-provider)")

# Gemini Pro (latest): powerful, free tier, 1M context. The "latest" alias
# auto-tracks the newest Pro release the account has access to â€”
# important because raw "gemini-2.5-pro" returns quota-exceeded on many
# accounts where "gemini-2.5-pro" works.
_DEFAULT_MODEL = "gemini-2.5-pro"

# 60K chars â‰ˆ 15K tokens â€” captures ~30 min of dense Vietnamese speech.
_MAX_SRT_CHARS = int(os.getenv("GEMINI_MAX_SRT_CHARS", "60000"))

# Hard upper bound on a single Gemini request â€” prevents the SDK from
# blocking the render pipeline on its built-in ~10 min default timeout.
_REQUEST_TIMEOUT_SEC = int(os.getenv("GEMINI_REQUEST_TIMEOUT", "120"))

_MAX_OUTPUT_TOKENS = 16384
_TEMPERATURE = 0.2

try:
    from google import genai as _genai
    _GENAI_SDK = True
except ImportError:
    _genai = None  # type: ignore[assignment]
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
    editorial_hint: str = "",
) -> Optional[list[LLMSegment]]:
    """Send SRT to Gemini and return selected segments.

    Returns None on any failure â€” caller hard-fails the pipeline.
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
            editorial_hint=editorial_hint,
        )
    except Exception as exc:
        logger.warning("gemini_client: unexpected error â€” %s", exc, exc_info=True)
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
    editorial_hint: str = "",
) -> Optional[list[LLMSegment]]:
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
        max_srt_chars=_MAX_SRT_CHARS,
        editorial_hint=editorial_hint,
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


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Sprint 4.C â€” RenderPlan path (dual-mode alongside select_segments)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def select_render_plan(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str = "",
    model: Optional[str] = None,
    language: str = "auto",
    editorial_hint: str = "",
) -> Optional[RenderPlan]:
    """Send SRT to Gemini and return a RenderPlan emitted in one pass.

    Sprint 4.C â€” additive partner of select_segments. Uses the same
    Gemini API call helper; only the prompt builder and the parser
    differ. Sprint 4.D will gate which entry point the orchestrator
    invokes behind a feature flag.

    Returns None on any failure â€” caller falls back to the segment-only
    path (Sprint 2.2 builder shim).
    """
    try:
        return _run_render_plan(
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
    except Exception as exc:
        logger.warning("gemini_client: select_render_plan unexpected error â€” %s", exc, exc_info=True)
        return None


def _run_render_plan(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
    api_key: str,
    model: Optional[str],
    language: str,
    editorial_hint: str,
) -> Optional[RenderPlan]:
    if not _GENAI_SDK:
        logger.warning("gemini_client: google-genai SDK not installed (render_plan path)")
        return None
    if not api_key:
        logger.warning("gemini_client: no api_key supplied (render_plan path)")
        return None
    if not srt_content or not srt_content.strip():
        logger.warning("gemini_client: empty transcript (render_plan path)")
        return None

    system_prompt, user_prompt = build_render_plan_prompt(
        srt_content=srt_content,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        language=language,
        max_srt_chars=_MAX_SRT_CHARS,
        editorial_hint=editorial_hint,
    )

    resolved_model = model or _DEFAULT_MODEL
    _prompt_chars = len(system_prompt) + len(user_prompt)
    _est_tokens = _prompt_chars // 4
    logger.info(
        "gemini_client: calling render_plan model=%s output_count=%d min_sec=%.0f max_sec=%.0f "
        "video_dur=%.0f srt_chars=%d prompt_chars=%d est_tokens=%d",
        resolved_model, output_count, min_sec, max_sec, video_duration,
        len(srt_content), _prompt_chars, _est_tokens,
    )

    raw = _call_gemini(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("gemini_client: empty render_plan API response (model=%s)", resolved_model)
        return None

    _preview = raw if len(raw) <= 2000 else raw[:2000] + f"... [{len(raw) - 2000} more chars]"
    logger.info("gemini_client: raw render_plan response (model=%s):\n%s", resolved_model, _preview)

    plan = parse_render_plan_response(
        raw=raw,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
    )
    if plan is not None:
        logger.info(
            "gemini_client: parsed render_plan with %d/%d clips (model=%s)",
            len(plan.clips), output_count, resolved_model,
        )
    return plan


def _call_gemini(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Call Gemini Chat with JSON-object output mode.

    Timeout is enforced via http_options on the Client. google-genai accepts
    a plain dict for http_options (Client converts to HttpOptions internally
    â€” see client.py:448-449 in the installed SDK). Timeout value is in
    MILLISECONDS (client.py:178: `http_opts.timeout / 1000`). The 30s default
    Override via GEMINI_REQUEST_TIMEOUT env.
    """
    try:
        client = _genai.Client(
            api_key=api_key,
            http_options={"timeout": _REQUEST_TIMEOUT_SEC * 1000},
        )
        resp = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "temperature": _TEMPERATURE,
                "max_output_tokens": _MAX_OUTPUT_TOKENS,
                "thinking_config": {"thinking_budget": 0},
            },
        )
        return resp.text
    except Exception as exc:
        logger.warning("gemini_client: API call failed (model=%s) â€” %s", model, exc)
        return None

