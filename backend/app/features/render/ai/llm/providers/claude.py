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

from app.features.render.ai.llm.cache import llm_cache_get, llm_cache_put
from app.features.render.ai.llm.parser import parse_render_plan_response
from app.features.render.ai.llm.prompts import build_render_plan_prompt
from app.features.render.ai.llm.retry import call_with_retry
from app.features.render.ai.llm.rewrite_prompts import build_rewrite_prompt, _compute_word_budget
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response
from app.domain.render_plan import RenderPlan

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
    """Send SRT to Claude and return a RenderPlan emitted in one pass.

    Anthropic Messages API call (no native JSON mode — relies on prompt
    obedience plus the defensive JSON extractor in parser.py). The
    editorial_hint parameter mirrors Gemini/OpenAI so the
    ``ai.llm.select_render_plan`` dispatcher can forward it uniformly.
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
        logger.warning("claude_client: select_render_plan unexpected error — %s", exc, exc_info=True)
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
    if not _ANTHROPIC_SDK:
        logger.warning("claude_client: anthropic SDK not installed (render_plan path)")
        return None
    if not api_key:
        logger.warning("claude_client: no api_key supplied (render_plan path)")
        return None
    if not srt_content or not srt_content.strip():
        logger.warning("claude_client: empty transcript (render_plan path)")
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
        video_type=video_type,
        hook_strength=hook_strength,
        ai_target_market=ai_target_market,
        subtitle_emphasis=subtitle_emphasis,
        multi_variant=multi_variant,
        structure_bias=structure_bias,
        target_platform=target_platform,
    )

    resolved_model = model or _DEFAULT_MODEL
    _prompt_chars = len(system_prompt) + len(user_prompt)
    _est_tokens = _prompt_chars // 4
    logger.info(
        "claude_client: calling render_plan model=%s output_count=%d min_sec=%.0f max_sec=%.0f "
        "video_dur=%.0f srt_chars=%d prompt_chars=%d est_tokens=%d",
        resolved_model, output_count, min_sec, max_sec, video_duration,
        len(srt_content), _prompt_chars, _est_tokens,
    )

    raw = _call_claude(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("claude_client: empty render_plan API response (model=%s)", resolved_model)
        return None

    _preview = raw if len(raw) <= 2000 else raw[:2000] + f"... [{len(raw) - 2000} more chars]"
    logger.info("claude_client: raw render_plan response (model=%s):\n%s", resolved_model, _preview)

    plan = parse_render_plan_response(
        raw=raw,
        output_count=output_count,
        min_sec=min_sec,
        max_sec=max_sec,
        video_duration=video_duration,
    )
    if plan is not None:
        logger.info(
            "claude_client: parsed render_plan with %d/%d clips (model=%s)",
            len(plan.clips), output_count, resolved_model,
        )
    return plan


def _call_claude_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single Anthropic Messages API call — raises on SDK error."""
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


def _call_claude(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Anthropic Messages API call with cache + one-attempt retry (Retry-After honoured).

    Cache check (audit AI06 closure) precedes the retry loop — a hit short-circuits
    the SDK call entirely. On miss, the retry-wrapped call runs and a successful
    result is written back to the 72 h content-addressable cache.
    """
    cached = llm_cache_get("claude", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("claude_client: cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_claude_once(api_key, model, system_prompt, user_prompt),
        label="claude",
    )
    if result is not None:
        llm_cache_put("claude", model, system_prompt, user_prompt, result)
    return result


def rewrite_subtitle(
    text: str,
    target_duration_sec: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional[str]:
    """Rewrite per-part transcript into TTS narration sized for target_duration_sec.

    Returns None on any failure (Sacred Contract #3). Uses cache + retry
    pattern identical to select_render_plan.
    """
    try:
        return _run_rewrite(
            text=text,
            target_duration_sec=target_duration_sec,
            target_language=target_language,
            tone=tone,
            api_key=api_key,
            model=model,
        )
    except Exception as exc:
        logger.warning("claude_client: rewrite_subtitle unexpected error %s", exc, exc_info=True)
        return None


def _run_rewrite(
    text: str,
    target_duration_sec: float,
    target_language: str,
    tone: str,
    api_key: str,
    model: Optional[str],
) -> Optional[str]:
    if not _ANTHROPIC_SDK:
        logger.warning("claude_client: anthropic SDK not installed (rewrite path)")
        return None
    if not api_key:
        logger.warning("claude_client: no api_key supplied (rewrite path)")
        return None
    if not text or not text.strip():
        logger.warning("claude_client: empty text (rewrite path)")
        return None
    system_prompt, user_prompt = build_rewrite_prompt(
        text=text,
        target_duration_sec=target_duration_sec,
        target_language=target_language,
        tone=tone,
    )
    resolved_model = model or _DEFAULT_MODEL
    word_budget = _compute_word_budget(target_duration_sec, target_language)
    logger.info(
        "claude_client: calling rewrite model=%s dur=%.1fs lang=%s tone=%r text_chars=%d budget=%d",
        resolved_model, target_duration_sec, target_language, tone, len(text), word_budget,
    )
    raw = _call_claude_rewrite(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("claude_client: empty rewrite response (model=%s)", resolved_model)
        return None
    parsed = parse_rewrite_response(raw, target_duration_sec, word_budget)
    if parsed is not None:
        logger.info(
            "claude_client: rewrite OK model=%s in_chars=%d out_chars=%d",
            resolved_model, len(text), len(parsed),
        )
    return parsed


def _call_claude_rewrite_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single Anthropic Messages call for rewrite — raises on SDK error."""
    client = _AnthClient(api_key=api_key, timeout=30)
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    if not resp.content:
        return None
    parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
    return "\n".join(parts) if parts else None


def _call_claude_rewrite(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Rewrite call with cache + retry. Cache namespaced by 'claude-rewrite'."""
    cached = llm_cache_get("claude-rewrite", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("claude_client: rewrite cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_claude_rewrite_once(api_key, model, system_prompt, user_prompt),
        label="claude-rewrite",
    )
    if result is not None:
        llm_cache_put("claude-rewrite", model, system_prompt, user_prompt, result)
    return result

