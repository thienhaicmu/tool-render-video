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
from app.features.render.ai.llm.key_pool import call_gemini_with_model_rotation, model_chain
from app.features.render.ai.llm.rewrite_prompts import build_rewrite_prompt, _compute_word_budget
from app.features.render.ai.llm.rewrite_parser import parse_rewrite_response
from app.features.render.ai.llm.recap_prompts import (
    build_recap_prompt, build_story_model_prompt, build_editorial_prompt,
    build_episode_narration_prompt,
)
from app.features.render.ai.llm.recap_parser import (
    parse_recap_response, parse_story_model_response, parse_editorial_response,
    parse_episode_narration_response,
)
from app.features.render.ai.llm.content_prompts import (
    build_content_plan_prompt, build_story_bible_prompt, build_publish_meta_prompt,
    build_content_narration_refine_prompt,
)
from app.features.render.ai.llm.content_parser import (
    parse_content_plan_response, parse_story_bible_response, parse_publish_meta_response,
)
from app.features.render.ai.llm.content_quality import (
    validate_and_repair, inject_character_fragments,
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

# Model-fallback chain for the TEXT LLM calls below. When the primary model is
# exhausted across EVERY key by overload (503) / quota (429), the key-pool
# rotates DOWN this chain to the next model (e.g. an overloaded
# ``gemini-3.5-flash`` → ``gemini-2.5-flash``). Override the fallbacks with
# ``GEMINI_MODEL_FALLBACKS`` (comma-separated). This is the TEXT family only —
# TTS / image models rotate within their own families (their own env vars).
_MODEL_FALLBACKS_ENV = "GEMINI_MODEL_FALLBACKS"
_DEFAULT_MODEL_FALLBACKS = ["gemini-2.5-flash"]


def _text_model_chain(model: str) -> "list[str]":
    """Primary model + configured text fallbacks (deduped, primary first)."""
    return model_chain(model, env_var=_MODEL_FALLBACKS_ENV, default_fallbacks=_DEFAULT_MODEL_FALLBACKS)

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

    # Latent-bug fix (2026-06-30): build_render_plan_prompt does not accept
    # reaction_intensity (that field is only used by the rewrite-prompt
    # path in rewrite_prompts.build_rewrite_prompt, not the render-plan
    # path). Passing it here used to TypeError on any real LLM call —
    # hidden because test_llm_metrics mocks at the public select_render_plan
    # entry, never exercising this code path. Removed from all 3 providers
    # (gemini / openai / claude) for consistency. The public select_render_plan
    # signature still ACCEPTS reaction_intensity so callers using the
    # uniform provider API don't break — it's silently dropped on the
    # render-plan path, same as before but without the runtime crash.
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
    result = call_gemini_with_model_rotation(
        lambda _k, _m: _call_gemini_once(_k, _m, system_prompt, user_prompt),
        label="gemini", seed_key=api_key, models=_text_model_chain(model),
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
    result = call_gemini_with_model_rotation(
        lambda _k, _m: _call_gemini_rewrite_once(_k, _m, system_prompt, user_prompt),
        label="gemini-rewrite", seed_key=api_key, models=_text_model_chain(model),
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


# ── Content Mode (render_format="content"): AI Content Director ───────────────
# A content plan is article-sized (a handful of scenes with short narration),
# so the token budget is modest. Temperature is a touch higher than segment
# selection (0.2) because narration authoring is a mildly creative task, but
# lower than the rewrite path (0.85) since the JSON structure must stay strict.
# Review LOW-2: a rich ContentPlan (many scenes × ~16 fields incl. narration +
# visual_prompt) can exceed 8192 tokens → the JSON is truncated and the parser
# salvages only the complete prefix (dropping tail scenes). 16384 gives the plan
# real headroom; thinking budget (below) stays well under it so output is never
# starved. Override via GEMINI_CONTENT_MAX_TOKENS.
_CONTENT_MAX_TOKENS = int(os.getenv("GEMINI_CONTENT_MAX_TOKENS", "16384"))
_CONTENT_TEMPERATURE = float(os.getenv("GEMINI_CONTENT_TEMPERATURE", "0.5"))
_CONTENT_THINKING_BUDGET = int(os.getenv("GEMINI_CONTENT_THINKING_BUDGET", "1024"))
# CU-4: two-pass Content Director. Pass A commits a Story Bible (characters +
# through-line); Pass B writes the plan GROUNDED in it → consistent narration +
# visuals. Default on. CONTENT_MULTIPASS=0 → legacy single call.
_CONTENT_MULTIPASS = os.getenv("CONTENT_MULTIPASS", "1") == "1"
# P2.1 — gate the extra Story Bible call by script length. The bible earns its
# cost on LONG multi-scene narrative scripts (character canon + through-line); a
# short script rarely has recurring characters and Pass B alone handles it — so
# skipping Pass A there saves ~1 LLM call + its latency at no quality loss.
# Below this many script chars, Pass A is skipped even when CONTENT_MULTIPASS=1.
# Set CONTENT_MULTIPASS_MIN_CHARS=0 to restore the always-on two-pass behaviour.
_CONTENT_MULTIPASS_MIN_CHARS = int(os.getenv("CONTENT_MULTIPASS_MIN_CHARS", "1200"))


def _call_gemini_content_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _genai.Client(api_key=api_key, http_options={"timeout": _REQUEST_TIMEOUT_SEC * 1000})
    resp = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "temperature": _CONTENT_TEMPERATURE,
            "max_output_tokens": _CONTENT_MAX_TOKENS,
            "thinking_config": {"thinking_budget": _CONTENT_THINKING_BUDGET},
        },
    )
    return resp.text


def _call_gemini_content(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    """Content-plan call with cache + key rotation. Cache namespaced 'gemini-content'."""
    cached = llm_cache_get("gemini-content", model, system_prompt, user_prompt)
    if cached is not None:
        logger.info("gemini_client: content cache HIT model=%s", model)
        return cached
    result = call_gemini_with_model_rotation(
        lambda _k, _m: _call_gemini_content_once(_k, _m, system_prompt, user_prompt),
        label="gemini-content", seed_key=api_key, models=_text_model_chain(model),
    )
    if result is not None:
        llm_cache_put("gemini-content", model, system_prompt, user_prompt, result)
    return result


def select_content_plan(
    script: str,
    target_duration_sec: float = 90.0,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional["ContentPlan"]:
    """Content Mode director — turn a raw script into a ContentPlan (scenes +
    narration + emotion/speed/pause + subtitle-style suggestion). Returns a
    ContentPlan or None (Sacred Contract #3 — never raises)."""
    try:
        if not _GENAI_SDK:
            logger.warning("gemini_client: google-genai SDK not installed (content path)")
            return None
        if not api_key:
            logger.warning("gemini_client: no api_key supplied (content path)")
            return None
        if not script or not script.strip():
            logger.warning("gemini_client: empty script (content path)")
            return None
        # P2.2: content planning can use a cheaper/faster model than the global
        # default (e.g. gemini-3.1-flash-lite) via CONTENT_LLM_MODEL, WITHOUT
        # affecting the clip/recap paths. Explicit payload model still wins;
        # unset env → the global _DEFAULT_MODEL (no behaviour change).
        resolved_model = model or os.getenv("CONTENT_LLM_MODEL", "").strip() or _DEFAULT_MODEL

        # ── CU-4 Pass A — Story Bible (best-effort; failure → single-pass) ────
        bible = None
        meta: dict = {}
        if _CONTENT_MULTIPASS and len((script or "").strip()) >= _CONTENT_MULTIPASS_MIN_CHARS:
            try:
                _bsys, _buser = build_story_bible_prompt(script, target_language, tone)
                _braw = _call_gemini_content(api_key, resolved_model, _bsys, _buser)
                _parsed = parse_story_bible_response(_braw) if _braw else None
                if _parsed is not None:
                    bible, meta = _parsed
                    logger.info(
                        "gemini_client: content pass-A bible OK characters=%d",
                        len(bible.characters),
                    )
            except Exception as _be:
                logger.info("gemini_client: content pass-A bible failed (%s) — single-pass", _be)
                bible = None

        # ── Pass B — the plan, GROUNDED in the Bible when available ──────────
        system_prompt, user_prompt = build_content_plan_prompt(
            script, target_duration_sec, target_language, tone, bible=bible,
        )
        logger.info(
            "gemini_client: calling content model=%s target_dur=%.0fs lang=%s in_chars=%d grounded=%s",
            resolved_model, float(target_duration_sec or 0.0), target_language, len(script),
            bible is not None,
        )
        raw = _call_gemini_content(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            logger.warning("gemini_client: empty content response (model=%s)", resolved_model)
            return None
        plan = parse_content_plan_response(raw, target_duration_sec)
        if plan is None:
            return None

        # Assemble: stamp the Bible + pass-A metadata, then deterministic CU-5/CU-6.
        if bible is not None and plan.story_bible.is_empty():
            plan.story_bible = bible
        for _k in ("topic", "tone", "audience", "video_style"):
            if meta.get(_k) and not (getattr(plan, _k, "") or "").strip():
                setattr(plan, _k, meta[_k])
        plan = validate_and_repair(plan, plan.story_bible)       # CU-5
        plan = inject_character_fragments(plan, plan.story_bible)  # CU-6
        logger.info(
            "gemini_client: content OK model=%s scenes=%d total=%.0fs topic=%r chars=%d",
            resolved_model, plan.scene_count(), plan.total_target_sec, plan.topic,
            len(plan.story_bible.characters),
        )
        return plan
    except Exception as exc:
        logger.warning("gemini_client: select_content_plan unexpected error %s", exc, exc_info=True)
        return None


def generate_publish_meta(
    topic: str = "",
    tone: str = "",
    audience: str = "",
    target_language: str = "vi-VN",
    narration_sample: str = "",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional[dict]:
    """CU-14 — SEO publish metadata (title/description/tags/thumbnail) from a
    finished plan. Returns a dict or None (Sacred Contract #3 — never raises)."""
    try:
        if not _GENAI_SDK or not api_key:
            return None
        if not (topic or narration_sample).strip():
            return None
        rm = model or _DEFAULT_MODEL
        sys_p, user_p = build_publish_meta_prompt(topic, tone, audience, target_language, narration_sample)
        raw = _call_gemini_content(api_key, rm, sys_p, user_p)
        if not raw:
            return None
        return parse_publish_meta_response(raw)
    except Exception as exc:
        logger.warning("gemini_client: generate_publish_meta error %s", exc)
        return None


# ── P1-2: per-episode narration refiner ──────────────────────────────────────
_EPISODE_NARRATION_MAX_TOKENS = int(os.getenv("GEMINI_EPISODE_NARRATION_MAX_TOKENS", "4096"))


def _call_gemini_episode_narration_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _genai.Client(api_key=api_key, http_options={"timeout": _REQUEST_TIMEOUT_SEC * 1000})
    resp = client.models.generate_content(
        model=model, contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "temperature": _RECAP_TEMPERATURE,
            "max_output_tokens": _EPISODE_NARRATION_MAX_TOKENS,
            # Narration authoring is creative, not reasoning-heavy; no thinking so
            # the answer budget can't be starved (same failure class as the story
            # call). Override via GEMINI_RECAP_THINKING if ever needed.
            "thinking_config": {"thinking_budget": 0},
        },
    )
    return resp.text


def _call_gemini_episode_narration(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    cached = llm_cache_get("gemini-episode-narration", model, system_prompt, user_prompt)
    if cached is not None:
        return cached
    result = call_gemini_with_model_rotation(
        lambda _k, _m: _call_gemini_episode_narration_once(_k, _m, system_prompt, user_prompt),
        label="gemini-episode-narration", seed_key=api_key, models=_text_model_chain(model),
    )
    if result is not None:
        llm_cache_put("gemini-episode-narration", model, system_prompt, user_prompt, result)
    return result


def select_episode_narration(
    episode_scenes: list,
    story_model=None,
    target_language: str = "vi-VN",
    tone: str = "",
    api_key: str = "",
    model: Optional[str] = None,
    episode_title: str = "",
) -> Optional[dict]:
    """P1-2 — author narration for ONE episode's scenes. Returns ``{index: text}``
    or None (Sacred Contract #3 — never raises). None / empty leaves the caller's
    original narration untouched."""
    try:
        if not _GENAI_SDK or not api_key or not episode_scenes:
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_episode_narration_prompt(
            episode_scenes, story_model=story_model, target_language=target_language,
            tone=tone, episode_title=episode_title,
        )
        raw = _call_gemini_episode_narration(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            return None
        return parse_episode_narration_response(raw) or None
    except Exception as exc:
        logger.warning("gemini_client: select_episode_narration error %s", exc, exc_info=True)
        return None


def _call_gemini_content_narration_once(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    client = _genai.Client(api_key=api_key, http_options={"timeout": _REQUEST_TIMEOUT_SEC * 1000})
    resp = client.models.generate_content(
        model=model, contents=user_prompt,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "temperature": _CONTENT_TEMPERATURE,
            "max_output_tokens": _CONTENT_MAX_TOKENS,
            # Narration authoring is creative, not reasoning-heavy — no thinking
            # budget so the answer tokens can't be starved (same class as the
            # story / episode-narration calls).
            "thinking_config": {"thinking_budget": 0},
        },
    )
    return resp.text


def _call_gemini_content_narration(api_key: str, model: str, system_prompt: str, user_prompt: str) -> Optional[str]:
    cached = llm_cache_get("gemini-content-narration", model, system_prompt, user_prompt)
    if cached is not None:
        return cached
    result = call_gemini_with_model_rotation(
        lambda _k, _m: _call_gemini_content_narration_once(_k, _m, system_prompt, user_prompt),
        label="gemini-content-narration", seed_key=api_key, models=_text_model_chain(model),
    )
    if result is not None:
        llm_cache_put("gemini-content-narration", model, system_prompt, user_prompt, result)
    return result


def select_content_narration(
    scenes: list,
    topic: str = "",
    tone: str = "",
    target_language: str = "vi-VN",
    api_key: str = "",
    model: Optional[str] = None,
) -> Optional[dict]:
    """Content per-scene narration refine — re-author the whole scene set's
    narration in ONE focused call so it flows scene→scene and each scene's length
    matches its planned seconds. ``scenes`` is a list of
    ``{index, role, seconds, narration}`` dicts. Returns ``{index: text}`` or None
    (Sacred Contract #3 — never raises). None / empty leaves the original
    narration untouched. Reuses the recap ``{"narration":[...]}`` response shape."""
    try:
        if not _GENAI_SDK or not api_key or not scenes:
            return None
        resolved_model = model or _DEFAULT_MODEL
        system_prompt, user_prompt = build_content_narration_refine_prompt(
            scenes, topic=topic, tone=tone, target_language=target_language,
        )
        raw = _call_gemini_content_narration(api_key, resolved_model, system_prompt, user_prompt)
        if not raw:
            return None
        return parse_episode_narration_response(raw) or None
    except Exception as exc:
        logger.warning("gemini_client: select_content_narration error %s", exc, exc_info=True)
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
    result = call_gemini_with_model_rotation(
        lambda _k, _m: _call_gemini_editorial_once(_k, _m, system_prompt, user_prompt),
        label="gemini-editorial", seed_key=api_key, models=_text_model_chain(model),
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
    result = call_gemini_with_model_rotation(
        lambda _k, _m: _call_gemini_recap_once(_k, _m, system_prompt, user_prompt),
        label="gemini-recap", seed_key=api_key, models=_text_model_chain(model),
    )
    if result is not None:
        llm_cache_put("gemini-recap", model, system_prompt, user_prompt, result)
    return result


# Pass-1 (Story Model) — reconstructs the whole-film understanding (characters,
# plot beats, emotional curve). For Gemini 2.5 Flash the thinking budget and
# max_output_tokens draw from one ceiling: at the old 8192/8192 the thinking step
# consumed the budget and the JSON answer was truncated to near-empty — the
# StoryModel came back with 0 characters / 0 beats (measured 2026-07 on a 91-min
# film; 16384/2048 restored 10 characters / 13 beats). Give the answer real
# headroom and cap thinking well below it so output can never be starved.
# Override GEMINI_STORY_*.
_STORY_MAX_TOKENS = int(os.getenv("GEMINI_STORY_MAX_TOKENS", "16384"))
_STORY_TEMPERATURE = float(os.getenv("GEMINI_STORY_TEMPERATURE", "0.4"))
_STORY_THINKING_BUDGET = int(os.getenv("GEMINI_STORY_THINKING_BUDGET", "2048"))


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
    result = call_gemini_with_model_rotation(
        lambda _k, _m: _call_gemini_story_once(_k, _m, system_prompt, user_prompt),
        label="gemini-story", seed_key=api_key, models=_text_model_chain(model),
    )
    if result is not None:
        llm_cache_put("gemini-story", model, system_prompt, user_prompt, result)
    return result
