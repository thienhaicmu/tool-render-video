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

from app.features.render.ai.llm.cache import llm_cache_get, llm_cache_put
from app.features.render.ai.llm.parser import parse_render_plan_response
from app.features.render.ai.llm.prompts import build_render_plan_prompt
from app.features.render.ai.llm.retry import call_with_retry
from app.features.render.ai.llm.rewrite_prompts import build_rewrite_prompt, _compute_word_budget
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response
from app.domain.render_plan import RenderPlan

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
    clip_lock: list[dict] | None = None,
    clip_exclude: list[dict] | None = None,
    target_platform: str = "",
    # S5 — creator preferences (B+C). Forwarded to build_render_plan_prompt.
    video_type: str = "auto",
    hook_strength: str = "balanced",
    ai_target_market: str = "",
    subtitle_emphasis: Optional[str] = None,
    multi_variant: bool = False,
    structure_bias: Optional[str] = None,
) -> Optional[RenderPlan]:
    """Send SRT to OpenAI and return a RenderPlan emitted in one pass.

    OpenAI Chat Completions call in JSON mode (response_format =
    json_object). The editorial_hint parameter mirrors Gemini/Claude so
    the ``ai.llm.select_render_plan`` dispatcher can forward it uniformly.
    ``target_duration`` is the creator's soft total-duration target in
    seconds (T2.4); 0 = disabled. ``clip_lock`` / ``clip_exclude`` are
    UP26 Pro Timeline Steering hard constraints (Strategic-1); None /
    empty disables the prompt sections. Returns None on any failure
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
            clip_lock=clip_lock,
            clip_exclude=clip_exclude,
            target_platform=target_platform,
            video_type=video_type,
            hook_strength=hook_strength,
            ai_target_market=ai_target_market,
            subtitle_emphasis=subtitle_emphasis,
            multi_variant=multi_variant,
            structure_bias=structure_bias,
        )
    except Exception as exc:
        logger.warning("openai_client: select_render_plan unexpected error — %s", exc, exc_info=True)
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
    clip_lock: list[dict] | None = None,
    clip_exclude: list[dict] | None = None,
    target_platform: str = "",
    # S5 — creator preferences.
    video_type: str = "auto",
    hook_strength: str = "balanced",
    ai_target_market: str = "",
    subtitle_emphasis: Optional[str] = None,
    multi_variant: bool = False,
    structure_bias: Optional[str] = None,
) -> Optional[RenderPlan]:
    if not _OPENAI_SDK:
        logger.warning("openai_client: openai SDK not installed (render_plan path)")
        return None
    if not api_key:
        logger.warning("openai_client: no api_key supplied (render_plan path)")
        return None
    if not srt_content or not srt_content.strip():
        logger.warning("openai_client: empty transcript (render_plan path)")
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
        clip_lock=clip_lock,
        clip_exclude=clip_exclude,
        target_platform=target_platform,
        video_type=video_type,
        hook_strength=hook_strength,
        ai_target_market=ai_target_market,
        subtitle_emphasis=subtitle_emphasis,
        multi_variant=multi_variant,
        structure_bias=structure_bias,
    )

    resolved_model = model or _DEFAULT_MODEL
    _prompt_chars = len(system_prompt) + len(user_prompt)
    _est_tokens = _prompt_chars // 4
    logger.info(
        "openai_client: calling render_plan model=%s output_count=%d min_sec=%.0f max_sec=%.0f "
        "video_dur=%.0f srt_chars=%d prompt_chars=%d est_tokens=%d",
        resolved_model, output_count, min_sec, max_sec, video_duration,
        len(srt_content), _prompt_chars, _est_tokens,
    )

    raw = _call_openai(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("openai_client: empty render_plan API response (model=%s)", resolved_model)
        return None

    _preview = raw if len(raw) <= 2000 else raw[:2000] + f"... [{len(raw) - 2000} more chars]"
    logger.info("openai_client: raw render_plan response (model=%s):\n%s", resolved_model, _preview)

    plan = parse_render_plan_response(
        raw=raw,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
    )
    if plan is not None:
        logger.info(
            "openai_client: parsed render_plan with %d/%d clips (model=%s)",
            len(plan.clips), output_count, resolved_model,
        )
    return plan


def _call_openai_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single OpenAI Chat Completions call — raises on SDK error."""
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


def _call_openai(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """OpenAI Chat Completions call with cache + one-attempt retry (Retry-After honoured).

    Cache check (audit AI06 closure) precedes the retry loop — a hit short-circuits
    the SDK call entirely. On miss, the retry-wrapped call runs and a successful
    result is written back to the 72 h content-addressable cache.
    """
    cached = llm_cache_get("openai", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("openai_client: cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_openai_once(api_key, model, system_prompt, user_prompt),
        label="openai",
    )
    if result is not None:
        llm_cache_put("openai", model, system_prompt, user_prompt, result)
    return result


def rewrite_subtitle(
    srt_segmented: str,
    clip_duration_sec: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional[list[dict]]:
    """Rewrite per-part transcript into timed TTS narration segments.

    Returns list of {start, end, text} segments, or None on any failure
    (Sacred Contract #3).
    """
    try:
        return _run_rewrite(
            srt_segmented=srt_segmented,
            clip_duration_sec=clip_duration_sec,
            target_language=target_language,
            tone=tone,
            api_key=api_key,
            model=model,
        )
    except Exception as exc:
        logger.warning("openai_client: rewrite_subtitle unexpected error %s", exc, exc_info=True)
        return None


def _run_rewrite(
    srt_segmented: str,
    clip_duration_sec: float,
    target_language: str,
    tone: str,
    api_key: str,
    model: Optional[str],
) -> Optional[list[dict]]:
    if not _OPENAI_SDK:
        logger.warning("openai_client: openai SDK not installed (rewrite path)")
        return None
    if not api_key:
        logger.warning("openai_client: no api_key supplied (rewrite path)")
        return None
    if not srt_segmented or not srt_segmented.strip():
        logger.warning("openai_client: empty srt_segmented (rewrite path)")
        return None
    system_prompt, user_prompt = build_rewrite_prompt(
        srt_segmented=srt_segmented,
        clip_duration_sec=clip_duration_sec,
        target_language=target_language,
        tone=tone,
    )
    resolved_model = model or _DEFAULT_MODEL
    word_budget = _compute_word_budget(clip_duration_sec, target_language)
    logger.info(
        "openai_client: calling rewrite model=%s clip_dur=%.1fs lang=%s tone=%r in_chars=%d budget=%d",
        resolved_model, clip_duration_sec, target_language, tone, len(srt_segmented), word_budget,
    )
    _up_preview = user_prompt if len(user_prompt) <= 2000 else user_prompt[:2000] + f"\n... [+{len(user_prompt)-2000} chars]"
    logger.info("openai_client: rewrite prompt preview:\n--- SYSTEM ---\n%s\n--- USER ---\n%s\n--- END ---", system_prompt, _up_preview)
    raw = _call_openai_rewrite(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("openai_client: empty rewrite response (model=%s)", resolved_model)
        return None
    segments = parse_rewrite_response(raw, clip_duration_sec, word_budget)
    if segments:
        logger.info(
            "openai_client: rewrite OK model=%s segments=%d total_chars=%d",
            resolved_model, len(segments), sum(len(s["text"]) for s in segments),
        )
    return segments


def _call_openai_rewrite_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single OpenAI Chat Completions call for rewrite — raises on SDK error.
    v2 uses JSON mode (response_format=json_object) so segmented output parses
    reliably."""
    client = _openai.OpenAI(api_key=api_key, timeout=30)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=2048,
        temperature=_TEMPERATURE,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _call_openai_rewrite(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Rewrite call with cache + retry. Cache namespaced by 'openai-rewrite'."""
    cached = llm_cache_get("openai-rewrite", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("openai_client: rewrite cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_openai_rewrite_once(api_key, model, system_prompt, user_prompt),
        label="openai-rewrite",
    )
    if result is not None:
        llm_cache_put("openai-rewrite", model, system_prompt, user_prompt, result)
    return result

