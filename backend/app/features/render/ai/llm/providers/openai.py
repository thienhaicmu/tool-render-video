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
import time
from typing import Optional

from app.features.render.ai.llm.key_pool import call_with_key_rotation, pool_for
from app.features.render.ai.llm.cache import llm_cache_get, llm_cache_put
from app.features.render.ai.llm.parser import parse_render_plan_response
from app.features.render.ai.llm.prompts import build_render_plan_prompt
from app.features.render.ai.llm.retry import call_with_retry, is_billing_safe_retry
from app.features.render.ai.llm.usage import record_usage, record_usage_obj
from app.features.render.ai.llm.rewrite_prompts import build_rewrite_prompt, _compute_word_budget
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response
from app.features.render.ai.llm.recap_prompts import build_recap_prompt, build_story_model_prompt
from app.features.render.ai.llm.recap_parser import parse_recap_response, parse_story_model_response
from app.domain.render_plan import RenderPlan

logger = logging.getLogger("app.render.openai_client")
logger.info("openai_provider: module loaded (build=2026-06-01.i2-openai)")

_DEFAULT_MODEL = "gpt-4o-mini"
# Architecture-review Batch D-3a (2026-06-30): provider transcript cap resolves
# via the shared helper so all three providers honour the same priority chain
# (per-provider env > global LLM_MAX_SRT_CHARS > hardcoded default). With no
# env var set, returns 30000 byte-for-byte — historical behaviour preserved.
from app.features.render.ai.llm.prompts import resolve_provider_max_srt_chars as _resolve_max_srt_chars
_MAX_SRT_CHARS = _resolve_max_srt_chars(provider_default=30000, provider_env="OPENAI_MAX_SRT_CHARS")  # ~7.5K tokens
_MAX_TOKENS = 4096
_TEMPERATURE = 0.2
# Narration rewrite is creative (vs deterministic JSON extraction) — the shared
# 0.2 produced flat, robotic narration. Higher temperature gives natural rhythm
# + per-clip variation. Override via OPENAI_REWRITE_TEMPERATURE.
_REWRITE_TEMPERATURE = float(os.getenv("OPENAI_REWRITE_TEMPERATURE", "0.85"))

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
        # Latent-bug fix (2026-06-30): _run_render_plan does NOT accept
        # reaction_intensity — passing it here used to TypeError on every
        # real LLM call. test_llm_metrics never exercised this path
        # because it mocks at the public select_render_plan entry. Public
        # signature still accepts reaction_intensity for API uniformity
        # with the rewrite path (rewrite_subtitle DOES consume it); on
        # the render-plan path it's silently dropped, same as before but
        # without the runtime crash.
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
    # C.1 Phase 3 (2026-06-30) — Story Intelligence.
    story_model: Optional[Any] = None,
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
        # Note: reaction_intensity intentionally NOT forwarded here —
        # build_render_plan_prompt doesn't accept it. See public-entry
        # comment above for the historical bug + fix.
        target_duration=target_duration,
        clip_lock=clip_lock,
        clip_exclude=clip_exclude,
        target_platform=target_platform,
        video_duration_sec=video_duration,
        video_type=video_type,
        hook_strength=hook_strength,
        ai_target_market=ai_target_market,
        subtitle_emphasis=subtitle_emphasis,
        multi_variant=multi_variant,
        structure_bias=structure_bias,
        # C.1 Phase 3 — Story Intelligence section
        story_model=story_model,
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
        logger.warning("openai_client: rewrite_subtitle unexpected error %s", exc, exc_info=True)
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
        temperature=_REWRITE_TEMPERATURE,
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



# ── Recap/Review Film selection (render_format="recap") ──────────────────────
_RECAP_MAX_TOKENS = int(os.getenv("OPENAI_RECAP_MAX_TOKENS", "8192"))
_RECAP_TEMPERATURE = float(os.getenv("OPENAI_RECAP_TEMPERATURE", "0.4"))


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
        if not _OPENAI_SDK:
            logger.warning("openai_client: openai SDK not installed (recap path)")
            return None
        if not api_key or not srt_content or not srt_content.strip():
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_recap_prompt(
            srt_content, video_duration, target_language, tone,
            story_model=story_model, editorial=editorial)
        logger.info("openai_client: calling recap model=%s film_dur=%.0fs two_pass=%s editorial=%s",
                    resolved_model, video_duration, story_model is not None, editorial is not None)
        raw = _call_openai_recap(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            return None
        plan = parse_recap_response(raw, video_duration)
        if plan is not None:
            if story_model is not None:
                plan.story = story_model
            if editorial is not None:
                plan.editorial = editorial
            logger.info("openai_client: recap OK acts=%d scenes=%d", len(plan.acts), plan.scene_count())
        return plan
    except Exception as exc:
        logger.warning("openai_client: select_recap_plan unexpected error %s", exc, exc_info=True)
        return None


def _call_openai_recap_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _openai.OpenAI(api_key=api_key, timeout=60)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=_RECAP_MAX_TOKENS,
        temperature=_RECAP_TEMPERATURE,
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content


def _call_openai_recap(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    cached = llm_cache_get("openai-recap", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("openai_client: recap cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_openai_recap_once(api_key, model, system_prompt, user_prompt),
        label="openai-recap",
    )
    if result is not None:
        llm_cache_put("openai-recap", model, system_prompt, user_prompt, result)
    return result


# ── R7 pass-1: Story Model (whole-film understanding) ────────────────────────
_STORY_MAX_TOKENS = int(os.getenv("OPENAI_STORY_MAX_TOKENS", "4096"))
_STORY_TEMPERATURE = float(os.getenv("OPENAI_STORY_TEMPERATURE", "0.4"))
# reasoning_effort only applies to reasoning models (o-series / gpt-5). Empty = off.
_STORY_REASONING_EFFORT = os.getenv("OPENAI_STORY_REASONING_EFFORT", "").strip().lower()


def _is_reasoning_model(model: str) -> bool:
    """True for OpenAI reasoning models (o1/o3/o4/gpt-5*), which reject
    ``temperature``/``max_tokens`` and use ``max_completion_tokens`` instead."""
    m = (model or "").strip().lower()
    return m.startswith(("o1", "o3", "o4", "gpt-5"))


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
        if not _OPENAI_SDK or not api_key or not srt_content or not srt_content.strip():
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_story_model_prompt(srt_content, video_duration, target_language, tone)
        logger.info("openai_client: calling story model=%s film_dur=%.0fs", resolved_model, video_duration)
        raw = _call_openai_story(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            return None
        return parse_story_model_response(raw)
    except Exception as exc:
        logger.warning("openai_client: select_story_model unexpected error %s", exc, exc_info=True)
        return None


def _call_openai_story_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _openai.OpenAI(api_key=api_key, timeout=60)
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    if _is_reasoning_model(model):
        kwargs["max_completion_tokens"] = _STORY_MAX_TOKENS
        if _STORY_REASONING_EFFORT in ("minimal", "low", "medium", "high"):
            kwargs["reasoning_effort"] = _STORY_REASONING_EFFORT
    else:
        kwargs["max_tokens"] = _STORY_MAX_TOKENS
        kwargs["temperature"] = _STORY_TEMPERATURE
    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def _call_openai_story(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    cached = llm_cache_get("openai-story", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("openai_client: story cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_openai_story_once(api_key, model, system_prompt, user_prompt),
        label="openai-story",
    )
    if result is not None:
        llm_cache_put("openai-story", model, system_prompt, user_prompt, result)
    return result


# ── CM-2: Content Mode plan call (larger token budget than story — a multi-scene
# content plan is a big JSON) + a thin select_content_plan that delegates the
# CU-4/5/6 orchestration to the shared content_director. ─────────────────────
_CONTENT_MAX_TOKENS = int(os.getenv("OPENAI_CONTENT_MAX_TOKENS", "8192"))
_CONTENT_TEMPERATURE = float(os.getenv("OPENAI_CONTENT_TEMPERATURE", "0.5"))


def _call_openai_content_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _openai.OpenAI(api_key=api_key, timeout=90)
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    if _is_reasoning_model(model):
        kwargs["max_completion_tokens"] = _CONTENT_MAX_TOKENS
        if _STORY_REASONING_EFFORT in ("minimal", "low", "medium", "high"):
            kwargs["reasoning_effort"] = _STORY_REASONING_EFFORT
    else:
        kwargs["max_tokens"] = _CONTENT_MAX_TOKENS
        kwargs["temperature"] = _CONTENT_TEMPERATURE
    resp = client.chat.completions.create(**kwargs)
    record_usage_obj("openai", model, getattr(resp, "usage", None))
    return resp.choices[0].message.content


def _call_openai_content(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Content/Story super-plan raw call with cache + reliability.

    F-03: when an OpenAI key POOL is configured (``OPENAI_API_KEYS`` comma-
    separated, or the resolved key differs from ``OPENAI_API_KEY``) the call
    rotates across the pool on a 429/quota — the same headroom the Gemini path
    has had. With a SINGLE key (the common case) it stays on the pre-F-03
    ``call_with_retry`` path (Retry-After honoured), so behaviour is byte-
    identical for single-key deployments.
    """
    cached = llm_cache_get("openai-content", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("openai_client: content cache HIT model=%s", model)
        return cached
    if len(pool_for("openai", seed_key=api_key)) > 1:
        result = call_with_key_rotation(
            lambda _k: _call_openai_content_once(_k, model, system_prompt, user_prompt),
            label="openai-content", seed_key=api_key, provider="openai",
        )
    else:
        result = call_with_retry(
            lambda: _call_openai_content_once(api_key, model, system_prompt, user_prompt),
            label="openai-content",
        )
    if result is not None:
        llm_cache_put("openai-content", model, system_prompt, user_prompt, result)
    return result


# ── Story Mode v2 super-plan call (dedicated; SEPARATE from Content Mode) ─────
# The Story super-plan is a distinct task from Content Mode even though both emit
# a big JSON plan: it must (a) run cooler than Content's 0.5 so an ADAPT pass
# preserves facts (F-06), (b) carry a larger token budget so a ≤ceiling-visual plan
# is not truncated (F-04), and (c) surface a length-truncation instead of silently
# returning half a plan. Kept out of _call_openai_content so tuning Story never
# perturbs Content Mode. gemini/claude Story fallback still reuses their _content
# call (they have no story-specific tuning yet) — see llm._get_story_call_fn.
_STORY_PLAN_MAX_TOKENS = int(os.getenv("OPENAI_STORY_PLAN_MAX_TOKENS", "16384"))
_STORY_PLAN_TEMPERATURE = float(os.getenv("OPENAI_STORY_PLAN_TEMPERATURE", "0.4"))


def _retry_empty_enabled() -> bool:
    """Call-time env read; default OFF since streaming landed (2026-07-16 cost
    review). Pre-streaming, an empty response was often a transport hiccup and
    one blind re-buy was cheap insurance (F-09). With streaming + salvage, an
    empty stream is a genuine safety trim / hard failure — re-sending the same
    prompt usually re-buys the same nothing. OPENAI_STORY_PLAN_RETRY_EMPTY=1
    restores the old behaviour."""
    return os.getenv("OPENAI_STORY_PLAN_RETRY_EMPTY", "0") == "1"


# ── "Wait for the output, never timeout-then-rebuy" (Phase 1, 2026-07-16) ─────
# The Story planner's Writer/Structure responses run to 16K tokens — several
# MINUTES of generation. The old whole-response deadlines (120s/180s) tripped
# mid-generation; OpenAI still finished AND BILLED the aborted request, then the
# SDK's silent default (max_retries=2) re-sent it — paying up to 3× for one
# output, invisibly to the observer. Story calls now stream (the timeout that
# remains is per-chunk IDLE, not whole-response), disable SDK auto-retry, and
# treat a mid-generation break as SALVAGE, never as a retry trigger.
_STORY_STREAM = os.getenv("OPENAI_STORY_STREAM", "1") == "1"
_STORY_IDLE_TIMEOUT_SEC = float(os.getenv("OPENAI_STORY_IDLE_TIMEOUT_SEC", "60"))
_STORY_TOTAL_TIMEOUT_SEC = float(os.getenv("OPENAI_STORY_TOTAL_TIMEOUT_SEC", "600"))


def _story_client(api_key: str, streaming: bool):
    """OpenAI client for the LONG story calls. ``max_retries=0`` always — every
    retry must go through our billing-aware policy and be visible to the
    observer. Streaming: timeout = per-chunk idle window; non-streaming
    (env kill-switch / stream-open failure): one generous whole-response
    deadline instead of the old 120/180s."""
    if streaming:
        try:
            import httpx
            t = httpx.Timeout(connect=10.0, read=_STORY_IDLE_TIMEOUT_SEC,
                              write=30.0, pool=10.0)
            return _openai.OpenAI(api_key=api_key, timeout=t, max_retries=0)
        except Exception:
            pass
    return _openai.OpenAI(api_key=api_key, timeout=_STORY_TOTAL_TIMEOUT_SEC, max_retries=0)


def _stream_chat_text(client, kwargs: dict, *, label: str):
    """Stream one chat.completions request → ``(text, finish_reason, usage)``.

    Raises ONLY when nothing was received (pre-stream failure — safe for the
    caller's retry policy to classify). A break AFTER real content returns the
    partial text instead: the request is already billed server-side, so the
    salvage path (parser + repair) is strictly cheaper than re-buying."""
    stream = client.chat.completions.create(
        stream=True, stream_options={"include_usage": True}, **kwargs)
    parts: "list[str]" = []
    finish = None
    usage = None
    deadline = time.monotonic() + _STORY_TOTAL_TIMEOUT_SEC
    try:
        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk.usage
            choices = getattr(chunk, "choices", None) or []
            if choices:
                delta = getattr(choices[0], "delta", None)
                piece = getattr(delta, "content", None) if delta is not None else None
                if piece:
                    parts.append(piece)
                fr = getattr(choices[0], "finish_reason", None)
                if fr:
                    finish = fr
            if time.monotonic() > deadline:
                logger.warning(
                    "openai_client: %s stream exceeded total budget %.0fs — salvaging %d chars",
                    label, _STORY_TOTAL_TIMEOUT_SEC, sum(len(p) for p in parts))
                try:
                    stream.close()
                except Exception:
                    pass
                break
    except Exception as exc:
        if not parts:
            raise
        logger.warning(
            "openai_client: %s stream broke mid-generation (%s) — salvaging %d chars "
            "(NO retry: the request is already billed)",
            label, exc, sum(len(p) for p in parts))
    return "".join(parts), finish, usage
# F-05: native structured output (strict JSON Schema) for the super-plan. Default
# ON; set OPENAI_STORY_JSON_SCHEMA=0 to revert to plain JSON-mode. On any schema
# error (unsupported model / API rejection) the call auto-degrades to json_object
# in the SAME attempt, so a schema hiccup never fails the render.
_STORY_JSON_SCHEMA = os.getenv("OPENAI_STORY_JSON_SCHEMA", "1") == "1"


def _story_response_format(use_schema: bool) -> dict:
    if use_schema:
        from app.features.render.ai.llm.story_schema_v2 import build_story_plan_schema
        return {"type": "json_schema", "json_schema": {
            "name": "story_plan_v2", "strict": True, "schema": build_story_plan_schema()}}
    return {"type": "json_object"}


def _story_plan_create(api_key: str, model: str, system_prompt: str, user_prompt: str,
                       use_schema: bool) -> Optional[str]:
    """One super-plan create() with the chosen response_format. Returns raw content
    EVEN IF truncated (repair can salvage) but WARNs on finish_reason=length (F-04).
    Streams by default (OPENAI_STORY_STREAM) — the whole-response 120s deadline
    used to trip mid-generation on big plans and re-buy the request."""
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=_story_response_format(use_schema),
    )
    if _is_reasoning_model(model):
        kwargs["max_completion_tokens"] = _STORY_PLAN_MAX_TOKENS
        if _STORY_REASONING_EFFORT in ("minimal", "low", "medium", "high"):
            kwargs["reasoning_effort"] = _STORY_REASONING_EFFORT
    else:
        kwargs["max_tokens"] = _STORY_PLAN_MAX_TOKENS
        kwargs["temperature"] = _STORY_PLAN_TEMPERATURE
    if _STORY_STREAM:
        client = _story_client(api_key, streaming=True)
        text, finish, usage = _stream_chat_text(client, kwargs, label="story-plan")
        record_usage_obj("openai", model, usage)
    else:
        client = _story_client(api_key, streaming=False)
        resp = client.chat.completions.create(**kwargs)
        record_usage_obj("openai", model, getattr(resp, "usage", None))
        choice = resp.choices[0]
        text = choice.message.content
        finish = getattr(choice, "finish_reason", None)
    if finish == "length":
        logger.warning(
            "openai_client: story-plan TRUNCATED (finish_reason=length, max_tokens=%d) — "
            "plan may be incomplete; raise OPENAI_STORY_PLAN_MAX_TOKENS or split the chapter",
            _STORY_PLAN_MAX_TOKENS,
        )
    return text


def _call_openai_story_plan_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """One Story super-plan call. Uses strict JSON Schema (F-05) when enabled, and
    on ANY schema error auto-degrades to json_object in the same attempt so an
    unsupported model / schema rejection never fails the render."""
    if _STORY_JSON_SCHEMA:
        try:
            return _story_plan_create(api_key, model, system_prompt, user_prompt, True)
        except Exception as exc:
            logger.warning(
                "openai_client: story-plan json_schema failed (%s) — retrying json_object", exc)
            return _story_plan_create(api_key, model, system_prompt, user_prompt, False)
    return _story_plan_create(api_key, model, system_prompt, user_prompt, False)


def _call_openai_story_plan(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Story super-plan raw call: cache → key-rotation (pool) / retry → optional
    single retry-on-empty. Namespaced 'openai-story-plan' so a Story cache entry
    never aliases a Content-Mode one.

    F-10: the namespace embeds the Story super-prompt version + StoryPlan schema
    version so a prompt/schema/parser change invalidates the cache even when the
    literal prompt bytes are unchanged (the shared cache key's global
    PROMPT_VERSION belongs to the CLIP prompts.py — unrelated to Story)."""
    _ns = _story_cache_namespace()
    cached = llm_cache_get(_ns, model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("openai_client: story-plan cache HIT model=%s ns=%s", model, _ns)
        return cached

    def _run() -> Optional[str]:
        if len(pool_for("openai", seed_key=api_key)) > 1:
            return call_with_key_rotation(
                lambda _k: _call_openai_story_plan_once(_k, model, system_prompt, user_prompt),
                label="openai-story-plan", seed_key=api_key, provider="openai",
            )
        return call_with_retry(
            lambda: _call_openai_story_plan_once(api_key, model, system_prompt, user_prompt),
            label="openai-story-plan", should_retry=is_billing_safe_retry,
        )

    result = _run()
    # F-09 (default flipped OFF 2026-07-16): with streaming + salvage an empty
    # result is a genuine hard failure — a blind re-buy usually re-buys the same
    # nothing. OPENAI_STORY_PLAN_RETRY_EMPTY=1 restores the old one-retry.
    if not result and _retry_empty_enabled():
        logger.info("openai_client: story-plan empty — one retry-on-empty")
        result = _run()
    if result is not None:
        llm_cache_put(_ns, model, system_prompt, user_prompt, result)
    return result


def _story_cache_namespace() -> str:
    """'openai-story-plan|s<super_prompt_ver>|v<schema_ver>' — versioned so a
    prompt/schema change invalidates the story cache by construction. Defensive:
    falls back to the bare namespace if either version import fails."""
    try:
        from app.features.render.ai.llm.story_prompts_v2 import SUPER_PROMPT_VERSION
        from app.domain.story_plan_v2 import SCHEMA_VERSION
        return f"openai-story-plan|{SUPER_PROMPT_VERSION}|v{SCHEMA_VERSION}"
    except Exception:
        return "openai-story-plan"


# ── GĐ1 Story Compiler: WRITER call (prose — the ONLY provider call with NO
# JSON forcing). The Script pass needs free prose: JSON mode measurably flattens
# narration ("the model writes TERSE narration in JSON mode", s15), so this call
# deliberately omits response_format. Higher temperature (creative) + a large
# token budget (a 10-minute script ≈ 9-10k chars ≈ far under 16k tokens). Cache
# namespace is versioned like the story-plan one so a prompt bump invalidates it.
_STORY_WRITER_MAX_TOKENS = int(os.getenv("OPENAI_STORY_WRITER_MAX_TOKENS", "16384"))
_STORY_WRITER_TEMPERATURE = float(os.getenv("OPENAI_STORY_WRITER_TEMPERATURE", "0.8"))
# Phase 1 (2026-07-16): a Writer cut at max_tokens used to WARN and ship a
# tail-less script — which then FAILED the script gate and re-bought the whole
# compiler via the legacy fallback. One bounded continuation round ("keep
# writing from where you stopped") finishes the script for a fraction of that.
_STORY_WRITER_CONTINUE = os.getenv("OPENAI_STORY_WRITER_CONTINUE", "1") == "1"


def _writer_cache_namespace() -> str:
    try:
        from app.features.render.ai.llm.story_prompts_v2 import SUPER_PROMPT_VERSION
        return f"openai-story-writer|{SUPER_PROMPT_VERSION}"
    except Exception:
        return "openai-story-writer"


def _writer_request(client, kwargs: dict):
    """One Writer request (streamed when enabled) → (text, finish_reason, usage)."""
    if _STORY_STREAM:
        return _stream_chat_text(client, kwargs, label="story-writer")
    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    return choice.message.content or "", getattr(choice, "finish_reason", None), \
        getattr(resp, "usage", None)


def _usage_tokens(usage) -> "tuple[int, int]":
    try:
        return int(getattr(usage, "prompt_tokens", 0) or 0), \
            int(getattr(usage, "completion_tokens", 0) or 0)
    except Exception:
        return 0, 0


def _call_openai_writer_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """One prose Writer call — raises on SDK error (retry/rotation wraps it).
    Streams by default; a finish_reason=length cut gets ONE continuation round
    instead of shipping a tail-less script into the gate."""
    client = _story_client(api_key, streaming=_STORY_STREAM)
    kwargs = dict(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    if _is_reasoning_model(model):
        kwargs["max_completion_tokens"] = _STORY_WRITER_MAX_TOKENS
        if _STORY_REASONING_EFFORT in ("minimal", "low", "medium", "high"):
            kwargs["reasoning_effort"] = _STORY_REASONING_EFFORT
    else:
        kwargs["max_tokens"] = _STORY_WRITER_MAX_TOKENS
        kwargs["temperature"] = _STORY_WRITER_TEMPERATURE
    text, finish, usage = _writer_request(client, kwargs)
    in_tok, out_tok = _usage_tokens(usage)
    if finish == "length" and _STORY_WRITER_CONTINUE and (text or "").strip():
        logger.info(
            "openai_client: story-writer hit max_tokens=%d — one continuation round",
            _STORY_WRITER_MAX_TOKENS)
        try:
            cont_kwargs = dict(kwargs)
            cont_kwargs["messages"] = list(kwargs["messages"]) + [
                {"role": "assistant", "content": text},
                {"role": "user", "content":
                    "Continue the script EXACTLY from where it stopped. Same format, "
                    "same language. Do not repeat any earlier text, do not summarise — "
                    "just keep writing until the story's ending."},
            ]
            more, cont_finish, cont_usage = _writer_request(client, cont_kwargs)
            if (more or "").strip():
                text = text + ("" if text.endswith("\n") else "\n") + more
                finish = cont_finish
            c_in, c_out = _usage_tokens(cont_usage)
            in_tok, out_tok = in_tok + c_in, out_tok + c_out
        except Exception as exc:
            logger.warning("openai_client: story-writer continuation failed (%s) — "
                           "keeping the truncated script", exc)
    if finish == "length":
        logger.warning(
            "openai_client: story-writer TRUNCATED (finish_reason=length, max_tokens=%d) — "
            "script tail may be missing; raise OPENAI_STORY_WRITER_MAX_TOKENS",
            _STORY_WRITER_MAX_TOKENS,
        )
    if in_tok or out_tok:
        record_usage("openai", model, in_tok, out_tok)
    return text


def _call_openai_writer(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Story Writer (prose) raw call: cache → key-rotation (pool) / retry.
    Never raises; returns None on total failure (Sacred Contract #3)."""
    _ns = _writer_cache_namespace()
    cached = llm_cache_get(_ns, model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("openai_client: story-writer cache HIT model=%s", model)
        return cached
    if len(pool_for("openai", seed_key=api_key)) > 1:
        result = call_with_key_rotation(
            lambda _k: _call_openai_writer_once(_k, model, system_prompt, user_prompt),
            label="openai-story-writer", seed_key=api_key, provider="openai",
        )
    else:
        result = call_with_retry(
            lambda: _call_openai_writer_once(api_key, model, system_prompt, user_prompt),
            label="openai-story-writer", should_retry=is_billing_safe_retry,
        )
    if result is not None:
        llm_cache_put(_ns, model, system_prompt, user_prompt, result)
    return result


def select_content_plan(
    script: str,
    target_duration_sec: float = 90.0,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional["object"]:
    """Content Mode director (OpenAI) — turn a raw script into a ContentPlan via
    the shared two-pass content_director. Returns a ContentPlan or None (Sacred
    Contract #3 — never raises). Enables the cross-provider fallback for Content
    Mode (previously Gemini-only)."""
    try:
        if not _OPENAI_SDK or not api_key or not script or not script.strip():
            return None
        resolved_model = model or _DEFAULT_MODEL
        from app.features.render.ai.llm.content_director import run_content_director
        return run_content_director(
            call_fn=lambda _sys, _usr: _call_openai_content(api_key, resolved_model, _sys, _usr),
            script=script, target_duration_sec=target_duration_sec,
            target_language=target_language, tone=tone, provider_label="openai",
        )
    except Exception as exc:
        logger.warning("openai_client: select_content_plan unexpected error %s", exc, exc_info=True)
        return None
