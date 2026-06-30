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
from app.features.render.ai.llm.recap_prompts import build_recap_prompt, build_story_model_prompt
from app.features.render.ai.llm.recap_parser import parse_recap_response, parse_story_model_response
from app.domain.render_plan import RenderPlan

logger = logging.getLogger("app.render.claude_client")
logger.info("claude_provider: module loaded (build=2026-06-01.i3-claude)")

_DEFAULT_MODEL = "claude-haiku-4-5-20251001"
# Architecture-review Batch D-3a (2026-06-30): provider transcript cap resolves
# via the shared helper so all three providers honour the same priority chain
# (per-provider env > global LLM_MAX_SRT_CHARS > hardcoded default). With no
# env var set, returns 50000 byte-for-byte — historical behaviour preserved.
from app.features.render.ai.llm.prompts import resolve_provider_max_srt_chars as _resolve_max_srt_chars
_MAX_SRT_CHARS = _resolve_max_srt_chars(provider_default=50000, provider_env="CLAUDE_MAX_SRT_CHARS")  # ~12K tokens
_MAX_TOKENS = 4096
_TEMPERATURE = 0.2
# Narration rewrite is creative (vs deterministic JSON extraction) — the shared
# 0.2 produced flat, robotic narration. Higher temperature gives natural rhythm
# + per-clip variation. Override via CLAUDE_REWRITE_TEMPERATURE.
_REWRITE_TEMPERATURE = float(os.getenv("CLAUDE_REWRITE_TEMPERATURE", "0.85"))

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
    reaction_intensity: str = "",
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
    # C.1 Phase 3 (2026-06-30): optional StoryModel forwarded to the
    # prompt builder. Default None → byte-identical pre-Phase-3 prompt.
    story_model: Optional[Any] = None,
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
        # Latent-bug fix (2026-06-30): _run_render_plan does NOT accept
        # reaction_intensity — passing it here used to TypeError on every
        # real LLM call. test_llm_metrics never exercised this path
        # because it mocks at the public select_render_plan entry.
        # Public signature still accepts reaction_intensity for API
        # uniformity with the rewrite path (rewrite_subtitle DOES consume
        # it); on the render-plan path it's silently dropped, same as
        # before but without the runtime crash.
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
            story_model=story_model,  # C.1 Phase 3
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
    # C.1 Phase 3 (2026-06-30) — Story Intelligence.
    story_model: Optional[Any] = None,
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
        # Note: reaction_intensity intentionally NOT forwarded here —
        # build_render_plan_prompt doesn't accept it. See public-entry
        # comment above for the historical bug + fix.
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
        video_duration_sec=video_duration,
        # C.1 Phase 3 — Story Intelligence section
        story_model=story_model,
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
    """Single Anthropic Messages API call — raises on SDK error.

    Batch D-3b: user content carries the ephemeral cache marker via the
    CLAUDE_CLIPS_CACHE gate so a re-render of the same clips prompt
    benefits from Anthropic's prompt-cache discount (typically ~90% off
    cached tokens). Marker is silently ignored when the prompt is below
    the model's min cacheable size — no behaviour change for tiny inputs.
    """
    client = _AnthClient(api_key=api_key, timeout=30)
    resp = client.messages.create(
        model=model,
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": _cached_user_content(user_prompt, "CLAUDE_CLIPS_CACHE")}],
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
    srt_segmented: str,
    clip_duration_sec: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
    content_type: str = "",
    hook_type: str = "",
    clip_title: str = "",
    target_platform: str = "",
    part_idx: int = 0,
    total_parts: int = 0,
    narration_mode: str = "",
    editorial_hint: str = "",
    reaction_intensity: str = "",
) -> Optional[list[dict]]:
    """Rewrite per-part transcript into timed TTS narration segments.

    Returns list of {start, end, text} segments, or None on any failure
    (Sacred Contract #3). Claude has no native JSON mode flag, but the
    prompt explicitly asks for a single JSON object and the parser
    tolerates surrounding text.
    """
    try:
        return _run_rewrite(
            srt_segmented=srt_segmented,
            clip_duration_sec=clip_duration_sec,
            target_language=target_language,
            tone=tone,
            api_key=api_key,
            model=model,
            content_type=content_type,
            hook_type=hook_type,
            clip_title=clip_title,
            target_platform=target_platform,
            part_idx=part_idx,
            total_parts=total_parts,
            narration_mode=narration_mode,
            editorial_hint=editorial_hint,
            reaction_intensity=reaction_intensity,
        )
    except Exception as exc:
        logger.warning("claude_client: rewrite_subtitle unexpected error %s", exc, exc_info=True)
        return None


def _run_rewrite(
    srt_segmented: str,
    clip_duration_sec: float,
    target_language: str,
    tone: str,
    api_key: str,
    model: Optional[str],
    content_type: str = "",
    hook_type: str = "",
    clip_title: str = "",
    target_platform: str = "",
    part_idx: int = 0,
    total_parts: int = 0,
    narration_mode: str = "",
    editorial_hint: str = "",
    reaction_intensity: str = "",
) -> Optional[list[dict]]:
    if not _ANTHROPIC_SDK:
        logger.warning("claude_client: anthropic SDK not installed (rewrite path)")
        return None
    if not api_key:
        logger.warning("claude_client: no api_key supplied (rewrite path)")
        return None
    if not srt_segmented or not srt_segmented.strip():
        logger.warning("claude_client: empty srt_segmented (rewrite path)")
        return None
    system_prompt, user_prompt = build_rewrite_prompt(
        srt_segmented=srt_segmented,
        clip_duration_sec=clip_duration_sec,
        target_language=target_language,
        tone=tone,
        content_type=content_type,
        hook_type=hook_type,
        clip_title=clip_title,
        target_platform=target_platform,
        part_idx=part_idx,
        total_parts=total_parts,
        narration_mode=narration_mode,
        editorial_hint=editorial_hint,
        reaction_intensity=reaction_intensity,
    )
    resolved_model = model or _DEFAULT_MODEL
    word_budget = _compute_word_budget(clip_duration_sec, target_language)
    logger.info(
        "claude_client: calling rewrite model=%s clip_dur=%.1fs lang=%s tone=%r in_chars=%d budget=%d",
        resolved_model, clip_duration_sec, target_language, tone, len(srt_segmented), word_budget,
    )
    _up_preview = user_prompt if len(user_prompt) <= 2000 else user_prompt[:2000] + f"\n... [+{len(user_prompt)-2000} chars]"
    logger.info("claude_client: rewrite prompt preview:\n--- SYSTEM ---\n%s\n--- USER ---\n%s\n--- END ---", system_prompt, _up_preview)
    raw = _call_claude_rewrite(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("claude_client: empty rewrite response (model=%s)", resolved_model)
        return None
    segments = parse_rewrite_response(raw, clip_duration_sec, word_budget)
    if segments:
        logger.info(
            "claude_client: rewrite OK model=%s segments=%d total_chars=%d",
            resolved_model, len(segments), sum(len(s["text"]) for s in segments),
        )
    return segments


def _call_claude_rewrite_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single Anthropic Messages call for rewrite — raises on SDK error.

    Batch D-3b: user content carries the ephemeral cache marker via the
    CLAUDE_REWRITE_CACHE gate. Rewrite prompts are smaller per call but
    fire N times per render — even partial cache hits add up. Marker is
    silently ignored when below the model's min cacheable size.
    """
    client = _AnthClient(api_key=api_key, timeout=30)
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        temperature=_REWRITE_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": _cached_user_content(user_prompt, "CLAUDE_REWRITE_CACHE")}],
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



# ── Recap/Review Film selection (render_format="recap") ──────────────────────
_RECAP_MAX_TOKENS = int(os.getenv("CLAUDE_RECAP_MAX_TOKENS", "8192"))
_RECAP_TEMPERATURE = float(os.getenv("CLAUDE_RECAP_TEMPERATURE", "0.4"))


def _cached_user_content(
    user_prompt: str,
    cache_enabled_env: str = "CLAUDE_RECAP_CACHE",
) -> list:
    """Wrap ``user_prompt`` as a single text block, marking it for Anthropic
    prompt caching (ephemeral) unless the gate env var resolves to "0".

    The kill switch is per-call-site so an operator can disable caching on
    one path (e.g. rewrite) without affecting another (e.g. recap). Below
    the Anthropic model's min cacheable size (~1024 tokens for Haiku /
    Sonnet) the marker is silently ignored — no error, no cache hit.

    Architecture-review Batch D-3b (2026-06-30): the ``cache_enabled_env``
    parameter generalises the original R7 Stage C wiring (which hard-coded
    CLAUDE_RECAP_CACHE). Recap + story passes keep that env name via the
    default; clips and rewrite now ride their own gates:
      - clips    → CLAUDE_CLIPS_CACHE   (default "1" = ON)
      - rewrite  → CLAUDE_REWRITE_CACHE (default "1" = ON)
    """
    if os.getenv(cache_enabled_env, "1") != "1":
        return [{"type": "text", "text": user_prompt}]
    return [{"type": "text", "text": user_prompt, "cache_control": {"type": "ephemeral"}}]


def select_recap_plan(
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
    story_model=None,
    editorial=None,
) -> Optional["RecapPlan"]:
    """Select scenes + act structure for a recap. None on any failure (Sacred #3).
    R7: pass-3 plans FROM ``story_model`` when supplied (pass-1 by the dispatcher).
    R7.3: when ``editorial`` (pass-2 blueprint) is supplied, pass-3 EXECUTES it."""
    try:
        if not _ANTHROPIC_SDK:
            logger.warning("claude_client: anthropic SDK not installed (recap path)")
            return None
        if not api_key or not srt_content or not srt_content.strip():
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_recap_prompt(
            srt_content, video_duration, target_language, tone,
            story_model=story_model, editorial=editorial)
        logger.info("claude_client: calling recap model=%s film_dur=%.0fs two_pass=%s editorial=%s",
                    resolved_model, video_duration, story_model is not None, editorial is not None)
        raw = _call_claude_recap(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            return None
        plan = parse_recap_response(raw, video_duration)
        if plan is not None:
            if story_model is not None:
                plan.story = story_model
            if editorial is not None:
                plan.editorial = editorial
            logger.info("claude_client: recap OK acts=%d scenes=%d", len(plan.acts), plan.scene_count())
        return plan
    except Exception as exc:
        logger.warning("claude_client: select_recap_plan unexpected error %s", exc, exc_info=True)
        return None


def _call_claude_recap_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _AnthClient(api_key=api_key, timeout=60)
    resp = client.messages.create(
        model=model,
        max_tokens=_RECAP_MAX_TOKENS,
        temperature=_RECAP_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": _cached_user_content(user_prompt)}],
    )
    if not resp.content:
        return None
    parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
    return "\n".join(parts) if parts else None


def _call_claude_recap(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    cached = llm_cache_get("claude-recap", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("claude_client: recap cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_claude_recap_once(api_key, model, system_prompt, user_prompt),
        label="claude-recap",
    )
    if result is not None:
        llm_cache_put("claude-recap", model, system_prompt, user_prompt, result)
    return result


# ── R7 pass-1: Story Model (whole-film understanding) ────────────────────────
_STORY_MAX_TOKENS = int(os.getenv("CLAUDE_STORY_MAX_TOKENS", "4096"))
_STORY_TEMPERATURE = float(os.getenv("CLAUDE_STORY_TEMPERATURE", "0.4"))
# Extended thinking is OPT-IN (budget>0). When enabled, the Anthropic API requires
# temperature=1 and max_tokens > budget — both handled below. Default 0 = plain call.
_STORY_THINKING_BUDGET = int(os.getenv("CLAUDE_STORY_THINKING_BUDGET", "0"))


def select_story_model(
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional["StoryModel"]:
    """R7 pass-1 — whole-film Story Model. Returns StoryModel or None (Sacred #3)."""
    try:
        if not _ANTHROPIC_SDK or not api_key or not srt_content or not srt_content.strip():
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_story_model_prompt(srt_content, video_duration, target_language, tone)
        logger.info("claude_client: calling story model=%s film_dur=%.0fs", resolved_model, video_duration)
        raw = _call_claude_story(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            return None
        return parse_story_model_response(raw)
    except Exception as exc:
        logger.warning("claude_client: select_story_model unexpected error %s", exc, exc_info=True)
        return None


def _call_claude_story_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _AnthClient(api_key=api_key, timeout=60)
    kwargs = dict(
        model=model,
        max_tokens=_STORY_MAX_TOKENS,
        temperature=_STORY_TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": _cached_user_content(user_prompt)}],
    )
    if _STORY_THINKING_BUDGET > 0:
        # Extended thinking: temperature must be 1, max_tokens must exceed the budget.
        kwargs["temperature"] = 1.0
        kwargs["max_tokens"] = _STORY_THINKING_BUDGET + _STORY_MAX_TOKENS
        kwargs["thinking"] = {"type": "enabled", "budget_tokens": _STORY_THINKING_BUDGET}
    resp = client.messages.create(**kwargs)
    if not resp.content:
        return None
    parts = [block.text for block in resp.content if getattr(block, "type", "") == "text"]
    return "\n".join(parts) if parts else None


def _call_claude_story(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    cached = llm_cache_get("claude-story", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("claude_client: story cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_claude_story_once(api_key, model, system_prompt, user_prompt),
        label="claude-story",
    )
    if result is not None:
        llm_cache_put("claude-story", model, system_prompt, user_prompt, result)
    return result
