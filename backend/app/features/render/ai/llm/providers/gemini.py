"""
gemini_provider.py — Google Gemini implementation of segment selection.

Uses the unified google-genai SDK (Gemini 2.0 Flash by default).
Free tier: 1M tokens/day, 15 RPM. Context window: 1M tokens.

AI Safety (Contract 3): never raises — returns None on any error.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.features.render.ai.llm.cache import llm_cache_get, llm_cache_put
from app.features.render.ai.llm.parser import parse_render_plan_response
from app.features.render.ai.llm.prompts import build_render_plan_prompt
from app.features.render.ai.llm.retry import call_with_retry
from app.domain.render_plan import RenderPlan

logger = logging.getLogger("app.render.gemini_client")
logger.info("gemini_provider: module loaded (build=2026-06-01.i1-multi-provider)")

# Default model: ``gemini-2.5-flash``. The audit's 2026-06-06 smoke test
# AND a live render on 2026-06-07 both hit ``429 RESOURCE_EXHAUSTED``
# with ``limit: 0`` on free-tier ``gemini-2.5-pro``. The Flash model
# works on the same free tier and is fast enough for segment-selection
# (we need correct JSON + a handful of viral picks, not heavy reasoning).
# Override via ``GEMINI_DEFAULT_MODEL`` env var when on a paid tier that
# unlocks Pro. The prior comment here claimed ``gemini-2.5-pro`` works
# where ``gemini-2.5-pro`` doesn't — almost certainly a typo for Flash.
_DEFAULT_MODEL = os.getenv("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"

# 60K chars â‰ˆ 15K tokens — captures ~30 min of dense Vietnamese speech.
_MAX_SRT_CHARS = int(os.getenv("GEMINI_MAX_SRT_CHARS", "60000"))

# Hard upper bound on a single Gemini request — prevents the SDK from
# blocking the render pipeline on its built-in ~10 min default timeout.
_REQUEST_TIMEOUT_SEC = int(os.getenv("GEMINI_REQUEST_TIMEOUT", "120"))

_MAX_OUTPUT_TOKENS = 16384
_TEMPERATURE = 0.2
# Thinking budget: 1024 tokens gives Gemini 2.5 Flash enough reasoning capacity
# for clip selection + full RenderPlan emission in a single call (~2–4s extra
# latency accepted). Override via GEMINI_THINKING_BUDGET env var; set to 0 to
# disable thinking entirely (reverts to pre-upgrade speed).
_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "1024"))

try:
    from google import genai as _genai
    _GENAI_SDK = True
except ImportError:
    _genai = None  # type: ignore[assignment]
    _GENAI_SDK = False


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
    target_duration: int = 0,
) -> Optional[RenderPlan]:
    """Send SRT to Gemini and return a RenderPlan emitted in one pass.

    Gemini ``generate_content`` call with response_mime_type=
    application/json. The editorial_hint parameter mirrors OpenAI/Claude
    so the ``ai.llm.select_render_plan`` dispatcher can forward it
    uniformly. ``target_duration`` is the creator's soft total-duration
    target in seconds (T2.4); 0 = disabled. Returns None on any failure
    (Sacred Contract #3).
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
            target_duration=target_duration,
        )
    except Exception as exc:
        logger.warning("gemini_client: select_render_plan unexpected error — %s", exc, exc_info=True)
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
    target_duration: int = 0,
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
        target_duration=target_duration,
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


def _call_gemini_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single Gemini call — raises on SDK error.

    Timeout is enforced via http_options on the Client. google-genai accepts
    a plain dict for http_options (Client converts to HttpOptions internally
    — see client.py:448-449 in the installed SDK). Timeout value is in
    MILLISECONDS (client.py:178: `http_opts.timeout / 1000`). The 30s default
    Override via GEMINI_REQUEST_TIMEOUT env.
    """
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
            "thinking_config": {"thinking_budget": _THINKING_BUDGET},
        },
    )
    return resp.text


def _call_gemini(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Gemini call with cache + one-attempt retry (Retry-After honoured).

    Cache check (audit AI06 closure) precedes the retry loop — a hit short-circuits
    the SDK call entirely. On miss, the retry-wrapped call runs and a successful
    result is written back to the 72 h content-addressable cache.
    """
    cached = llm_cache_get("gemini", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("gemini_client: cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_gemini_once(api_key, model, system_prompt, user_prompt),
        label="gemini",
    )
    if result is not None:
        llm_cache_put("gemini", model, system_prompt, user_prompt, result)
    return result

