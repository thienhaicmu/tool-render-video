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
from app.features.render.ai.llm.rewrite_prompts import build_rewrite_prompt, _compute_word_budget
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response
from app.features.render.ai.llm.recap_prompts import (
    build_recap_prompt, build_story_model_prompt, build_editorial_prompt,
)
from app.features.render.ai.llm.recap_parser import (
    parse_recap_response, parse_story_model_response, parse_editorial_response,
)
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

# 60K chars ≈ 15K tokens — captures ~30 min of dense Vietnamese speech.
# Architecture-review Batch D-3a (2026-06-30): resolves via the shared helper
# so all three providers honour the same priority chain (per-provider env >
# global LLM_MAX_SRT_CHARS > hardcoded default). With no env var set, returns
# 60000 byte-for-byte — historical behaviour preserved.
from app.features.render.ai.llm.prompts import resolve_provider_max_srt_chars as _resolve_max_srt_chars
_MAX_SRT_CHARS = _resolve_max_srt_chars(provider_default=60000, provider_env="GEMINI_MAX_SRT_CHARS")

# Hard upper bound on a single Gemini request — prevents the SDK from
# blocking the render pipeline on its built-in ~10 min default timeout.
_REQUEST_TIMEOUT_SEC = int(os.getenv("GEMINI_REQUEST_TIMEOUT", "120"))

_MAX_OUTPUT_TOKENS = 16384
_TEMPERATURE = 0.2
# Rewrite call uses smaller token budget — narration is short.
_REWRITE_MAX_TOKENS = 2048
# Thinking budget: 1024 tokens gives Gemini 2.5 Flash enough reasoning capacity
# for clip selection + full RenderPlan emission in a single call (~2–4s extra
# latency accepted). Override via GEMINI_THINKING_BUDGET env var; set to 0 to
# disable thinking entirely (reverts to pre-upgrade speed).
_THINKING_BUDGET = int(os.getenv("GEMINI_THINKING_BUDGET", "1024"))
# Narration rewrite is a CREATIVE task (not deterministic JSON extraction like
# select_render_plan), so it gets its own, higher temperature — the shared
# 0.2 produced flat, generic, repetitive narration that sounded robotic.
# ~0.85 gives natural rhythm + per-clip variation while staying coherent.
# Override via GEMINI_REWRITE_TEMPERATURE. Rewrite needs no chain-of-thought
# reasoning, so its thinking budget defaults to 0 (saves ~2–4s latency/part);
# override via GEMINI_REWRITE_THINKING_BUDGET.
_REWRITE_TEMPERATURE = float(os.getenv("GEMINI_REWRITE_TEMPERATURE", "0.85"))
_REWRITE_THINKING_BUDGET = int(os.getenv("GEMINI_REWRITE_THINKING_BUDGET", "0"))

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
    reaction_intensity: str = "",
    target_duration: int = 0,
    clip_lock: list[dict] | None = None,
    clip_exclude: list[dict] | None = None,
    target_platform: str = "",
    # S5 — creator preference hints (B+C). Provider accepts + forwards
    # them to build_render_plan_prompt; provider-internal logic doesn't
    # use them directly. Defaults match the "no hint" pre-S5 behavior.
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
    """Send SRT to Gemini and return a RenderPlan emitted in one pass.

    Gemini ``generate_content`` call with response_mime_type=
    application/json. The editorial_hint parameter mirrors OpenAI/Claude
    so the ``ai.llm.select_render_plan`` dispatcher can forward it
    uniformly. ``target_duration`` is the creator's soft total-duration
    target in seconds (T2.4); 0 = disabled. ``clip_lock`` /
    ``clip_exclude`` are UP26 Pro Timeline Steering hard constraints
    (Strategic-1); None / empty disables the prompt sections.
    Returns None on any failure (Sacred Contract #3).
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
            reaction_intensity=reaction_intensity,
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
    reaction_intensity: str = "",
    target_duration: int = 0,
    clip_lock: list[dict] | None = None,
    clip_exclude: list[dict] | None = None,
    target_platform: str = "",
    # S5 — creator preferences forwarded to build_render_plan_prompt.
    video_type: str = "auto",
    hook_strength: str = "balanced",
    ai_target_market: str = "",
    subtitle_emphasis: Optional[str] = None,
    multi_variant: bool = False,
    structure_bias: Optional[str] = None,
    # C.1 Phase 3 (2026-06-30) — optional StoryModel for Story Intelligence.
    story_model: Optional[Any] = None,
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
        reaction_intensity=reaction_intensity,
        target_duration=target_duration,
        clip_lock=clip_lock,
        clip_exclude=clip_exclude,
        target_platform=target_platform,
        video_duration_sec=video_duration,
        # S5 — creator preferences (B+C) flow into the prompt section.
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
    (Sacred Contract #3). Uses cache + retry pattern identical to
    select_render_plan.
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
        logger.warning("gemini_client: rewrite_subtitle unexpected error %s", exc, exc_info=True)
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
    if not _GENAI_SDK:
        logger.warning("gemini_client: google-genai SDK not installed (rewrite path)")
        return None
    if not api_key:
        logger.warning("gemini_client: no api_key supplied (rewrite path)")
        return None
    if not srt_segmented or not srt_segmented.strip():
        logger.warning("gemini_client: empty srt_segmented (rewrite path)")
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
        "gemini_client: calling rewrite model=%s clip_dur=%.1fs lang=%s tone=%r in_chars=%d budget=%d",
        resolved_model, clip_duration_sec, target_language, tone, len(srt_segmented), word_budget,
    )
    # Step B (2026-06-27): log the actual prompt sent to the LLM so operators
    # can diff prompt versions against narration quality. Truncated to 2000
    # chars — full prompt is reproducible from the cache key.
    _up_preview = user_prompt if len(user_prompt) <= 2000 else user_prompt[:2000] + f"\n... [+{len(user_prompt)-2000} chars]"
    logger.info("gemini_client: rewrite prompt preview:\n--- SYSTEM ---\n%s\n--- USER ---\n%s\n--- END ---", system_prompt, _up_preview)
    raw = _call_gemini_rewrite(api_key, resolved_model, system_prompt, user_prompt)
    if not raw:
        logger.warning("gemini_client: empty rewrite response (model=%s)", resolved_model)
        return None
    segments = parse_rewrite_response(raw, clip_duration_sec, word_budget)
    if segments:
        logger.info(
            "gemini_client: rewrite OK model=%s segments=%d total_chars=%d",
            resolved_model, len(segments), sum(len(s["text"]) for s in segments),
        )
    return segments


def _call_gemini_rewrite_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Single Gemini call for rewrite — raises on SDK error. v2 uses JSON
    mime mode so segmented output parses reliably."""
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
            "temperature": _REWRITE_TEMPERATURE,
            "max_output_tokens": _REWRITE_MAX_TOKENS,
            "thinking_config": {"thinking_budget": _REWRITE_THINKING_BUDGET},
        },
    )
    return resp.text


def _call_gemini_rewrite(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Rewrite call with cache + one-attempt retry. Cache key namespaced by
    provider=gemini-rewrite to avoid collision with select_render_plan cache."""
    cached = llm_cache_get("gemini-rewrite", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("gemini_client: rewrite cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_gemini_rewrite_once(api_key, model, system_prompt, user_prompt),
        label="gemini-rewrite",
    )
    if result is not None:
        llm_cache_put("gemini-rewrite", model, system_prompt, user_prompt, result)
    return result



# ── Recap/Review Film selection (render_format="recap") ──────────────────────
# Recap now ALSO authors the full narration per scene → the JSON output is large
# (a feature film = many scenes × real narration text). 16384 truncated the JSON
# mid-stream (esp. with thinking eating the budget) → "no JSON object found" →
# recap failed. Gemini 2.5 Flash supports up to 65536 output tokens — use it.
# Recap is a STORY-UNDERSTANDING task, not flat extraction: the model must rebuild
# the whole-film arc (setup→climax→resolution) before selecting scenes. Give it a
# thinking budget so it reasons first — quality lever from the 2026-06-30 recap
# architecture review (was 0 = single-pass, shallow). 8192 is a small slice of the
# 65536 answer budget; thinking tokens are billed/budgeted separately from
# max_output_tokens. Override (incl. back to 0) via GEMINI_RECAP_THINKING_BUDGET.
_RECAP_MAX_TOKENS = int(os.getenv("GEMINI_RECAP_MAX_TOKENS", "65536"))
_RECAP_TEMPERATURE = float(os.getenv("GEMINI_RECAP_TEMPERATURE", "0.4"))
_RECAP_THINKING_BUDGET = int(os.getenv("GEMINI_RECAP_THINKING_BUDGET", "8192"))


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
        if not _GENAI_SDK or not api_key or not srt_content or not srt_content.strip():
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_story_model_prompt(srt_content, video_duration, target_language, tone)
        logger.info("gemini_client: calling story model=%s film_dur=%.0fs", resolved_model, video_duration)
        raw = _call_gemini_story(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            logger.warning("gemini_client: empty story response (model=%s)", resolved_model)
            return None
        sm = parse_story_model_response(raw)
        if sm is not None:
            logger.info(
                "gemini_client: story OK model=%s chars=%d beats=%d",
                resolved_model, len(sm.characters), len(sm.beats),
            )
        return sm
    except Exception as exc:
        logger.warning("gemini_client: select_story_model unexpected error %s", exc, exc_info=True)
        return None


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
    """Select scenes + act structure for a recap. Returns RecapPlan or None
    (Sacred Contract #3 — never raises). R7: when ``story_model`` is provided
    (pass-1), pass-3 plans FROM it and the model is stamped onto the plan. R7.3:
    when ``editorial`` (pass-2 blueprint) is provided, pass-3 EXECUTES it and it
    is stamped onto the plan too."""
    try:
        if not _GENAI_SDK:
            logger.warning("gemini_client: google-genai SDK not installed (recap path)")
            return None
        if not api_key:
            logger.warning("gemini_client: no api_key supplied (recap path)")
            return None
        if not srt_content or not srt_content.strip():
            logger.warning("gemini_client: empty srt_content (recap path)")
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_recap_prompt(
            srt_content, video_duration, target_language, tone,
            story_model=story_model, editorial=editorial)
        logger.info(
            "gemini_client: calling recap model=%s film_dur=%.0fs lang=%s in_chars=%d two_pass=%s editorial=%s",
            resolved_model, video_duration, target_language, len(srt_content),
            story_model is not None, editorial is not None,
        )
        raw = _call_gemini_recap(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            logger.warning("gemini_client: empty recap response (model=%s)", resolved_model)
            return None
        plan = parse_recap_response(raw, video_duration)
        if plan is not None:
            if story_model is not None:
                plan.story = story_model     # pass-1 understanding is authoritative
            if editorial is not None:
                plan.editorial = editorial   # pass-2 editorial plan is authoritative
            logger.info(
                "gemini_client: recap OK model=%s acts=%d scenes=%d total=%.0fs",
                resolved_model, len(plan.acts), plan.scene_count(), plan.total_target_sec,
            )
        return plan
    except Exception as exc:
        logger.warning("gemini_client: select_recap_plan unexpected error %s", exc, exc_info=True)
        return None


# ── R7.3 pass-2: Editorial Blueprint (cheap — StoryModel input, no transcript) ──
_EDITORIAL_MAX_TOKENS = int(os.getenv("GEMINI_EDITORIAL_MAX_TOKENS", "8192"))
_EDITORIAL_TEMPERATURE = float(os.getenv("GEMINI_EDITORIAL_TEMPERATURE", "0.4"))
_EDITORIAL_THINKING_BUDGET = int(os.getenv("GEMINI_EDITORIAL_THINKING_BUDGET", "8192"))


def _call_gemini_editorial_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _genai.Client(api_key=api_key, http_options={"timeout": _REQUEST_TIMEOUT_SEC * 1000})
    resp = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "temperature": _EDITORIAL_TEMPERATURE,
            "max_output_tokens": _EDITORIAL_MAX_TOKENS,
            "thinking_config": {"thinking_budget": _EDITORIAL_THINKING_BUDGET},
        },
    )
    return resp.text


def _call_gemini_editorial(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Editorial Blueprint call with cache + retry. Cache namespaced 'gemini-editorial'."""
    cached = llm_cache_get("gemini-editorial", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("gemini_client: editorial cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_gemini_editorial_once(api_key, model, system_prompt, user_prompt),
        label="gemini-editorial",
    )
    if result is not None:
        llm_cache_put("gemini-editorial", model, system_prompt, user_prompt, result)
    return result


def select_editorial_blueprint(
    story_model,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional["EditorialBlueprint"]:
    """R7.3 pass-2 — plan HOW to tell the recap, FROM the StoryModel (no transcript
    → cheap). Returns EditorialBlueprint or None (Sacred #3)."""
    try:
        if not _GENAI_SDK or not api_key or story_model is None:
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_editorial_prompt(story_model, video_duration, target_language, tone)
        logger.info("gemini_client: calling editorial model=%s film_dur=%.0fs", resolved_model, video_duration)
        raw = _call_gemini_editorial(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            logger.warning("gemini_client: empty editorial response (model=%s)", resolved_model)
            return None
        eb = parse_editorial_response(raw)
        if eb is not None:
            logger.info(
                "gemini_client: editorial OK model=%s episodes=%d beats=%d",
                resolved_model, eb.episode_count, len(eb.beats),
            )
        return eb
    except Exception as exc:
        logger.warning("gemini_client: select_editorial_blueprint unexpected error %s", exc, exc_info=True)
        return None


def _call_gemini_recap_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _genai.Client(api_key=api_key, http_options={"timeout": _REQUEST_TIMEOUT_SEC * 1000})
    resp = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "temperature": _RECAP_TEMPERATURE,
            "max_output_tokens": _RECAP_MAX_TOKENS,
            "thinking_config": {"thinking_budget": _RECAP_THINKING_BUDGET},
        },
    )
    return resp.text


def _call_gemini_recap(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Recap call with cache + retry. Cache namespaced 'gemini-recap'."""
    cached = llm_cache_get("gemini-recap", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("gemini_client: recap cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_gemini_recap_once(api_key, model, system_prompt, user_prompt),
        label="gemini-recap",
    )
    if result is not None:
        llm_cache_put("gemini-recap", model, system_prompt, user_prompt, result)
    return result


# Pass-1 (Story Model) — a short synopsis, so a smaller answer budget, but a real
# thinking budget (understanding is the reasoning-heavy step). Override GEMINI_STORY_*.
_STORY_MAX_TOKENS = int(os.getenv("GEMINI_STORY_MAX_TOKENS", "8192"))
_STORY_TEMPERATURE = float(os.getenv("GEMINI_STORY_TEMPERATURE", "0.4"))
_STORY_THINKING_BUDGET = int(os.getenv("GEMINI_STORY_THINKING_BUDGET", "8192"))


def _call_gemini_story_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _genai.Client(api_key=api_key, http_options={"timeout": _REQUEST_TIMEOUT_SEC * 1000})
    resp = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "temperature": _STORY_TEMPERATURE,
            "max_output_tokens": _STORY_MAX_TOKENS,
            "thinking_config": {"thinking_budget": _STORY_THINKING_BUDGET},
        },
    )
    return resp.text


def _call_gemini_story(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Story Model call with cache + retry. Cache namespaced 'gemini-story'."""
    cached = llm_cache_get("gemini-story", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("gemini_client: story cache HIT model=%s", model)
        return cached
    result = call_with_retry(
        lambda: _call_gemini_story_once(api_key, model, system_prompt, user_prompt),
        label="gemini-story",
    )
    if result is not None:
        llm_cache_put("gemini-story", model, system_prompt, user_prompt, result)
    return result
