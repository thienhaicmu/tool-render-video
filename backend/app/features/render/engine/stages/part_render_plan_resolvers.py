"""RenderPlan resolver helpers — Strategic-8 extract (Audit 2026-06-08).

Pure-move from ``stages/part_asset_planner.py``. Each helper consumes
``ctx.render_plan`` (a ``RenderPlan`` dataclass) and returns a primitive
value (str / int / tuple) that the planner's ``prepare_part_assets``
call site then folds into the legacy resolution chain.

These resolvers are the surface that wires the LLM's RenderPlan output
into the rest of the per-part planning pipeline. They are intentionally
free of I/O, exceptions, or mutable state — Sacred Contract #3 (AI
modules return None / empty values on any failure, never raise).

``part_asset_planner.py`` re-imports these names at module-top so the
in-function call sites continue to read as bare references and the
existing source-level guards (which grep the planner's text for the
resolver call patterns) keep passing.
"""
from __future__ import annotations

from app.features.render.engine.stages.part_render_context import PartRenderContext


# ────────────────────────────────────────────────────────────────────
# Sprint 4.E — RenderPlan.subtitle_policy consume helpers.
#
# When ctx.render_plan is None (flag OFF, no AI emission), both
# resolvers fall through to the caller's fallback — Sacred Contract
# #2 (default behaviour identical baseline). When ctx.render_plan is
# set, per-field merge applies: empty fields stay at fallback (the
# "empty = inherit" semantic documented at render_plan.py SubtitlePolicy);
# set fields override. Invalid style values soft-fall back per Sacred
# Contract #3.
# ────────────────────────────────────────────────────────────────────

# Allowed subtitle style strings the planner will accept from a
# RenderPlan. Superset of the SubtitlePolicy vocabulary
# (viral/clean/story/gaming) plus the registered preset_ids already
# wired into subtitle_engine. Anything outside the set soft-falls
# back to the legacy 5-tier resolution.
_RENDER_PLAN_ALLOWED_SUBTITLE_STYLES: frozenset[str] = frozenset({
    "viral", "clean", "story", "gaming",
    "tiktok_bounce_v1", "viral_bold", "story_clean_01",
    "clean_pro", "boxed_caption", "pro_karaoke",
})


def _resolve_subtitle_style_from_plan(
    ctx: PartRenderContext, fallback_value: str, part_no: int = 0
) -> tuple[str, str]:
    """Return ``(effective_subtitle_style, source_tag)``.

    Resolution order (highest to lowest priority):
      1. Per-clip: ``render_plan.clips[part_no-1].subtitle_style`` when
         ``part_no > 0`` and in bounds — source tag ``"render_plan_clip"``.
      2. Global: ``render_plan.subtitle_policy.style`` — source tag ``"render_plan"``.
      3. Fallback: caller-supplied legacy value — source tag ``"fallback"``
         or ``"fallback_invalid_style"`` when a plan style failed validation.

    Empty string in either plan field means "inherit from next level"
    (the same semantic as SubtitlePolicy). Invalid style values soft-fall
    back to the caller's legacy resolution (Sacred Contract #3).

    Phase A: when the render engine falls back (source_tag "fallback" or
    "fallback_invalid_style") because the AI left subtitle_style empty,
    the RENDER_ENGINE_EDITORIAL_OVERRIDES metric is incremented so
    operators can see how often the engine makes the editorial call.
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        _inc_editorial_override("subtitle_style")
        return fallback_value, "fallback"
    # Per-clip override (Sprint 4.E extension)
    if part_no > 0:
        try:
            clips = rp.clips
            if clips and part_no - 1 < len(clips):
                clip_style = (getattr(clips[part_no - 1], "subtitle_style", "") or "").strip()
                if clip_style and clip_style in _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES:
                    return clip_style, "render_plan_clip"
        except Exception:
            pass
    # Global subtitle_policy fallback
    plan_style = (rp.subtitle_policy.style or "").strip()
    if not plan_style:
        _inc_editorial_override("subtitle_style")
        return fallback_value, "fallback"
    if plan_style not in _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES:
        _inc_editorial_override("subtitle_style")
        return fallback_value, "fallback_invalid_style"
    return plan_style, "render_plan"


def _inc_editorial_override(field: str) -> None:
    """Increment the editorial-override counter. Never raises (metric must not crash render)."""
    try:
        from app.services.metrics import RENDER_ENGINE_EDITORIAL_OVERRIDES
        RENDER_ENGINE_EDITORIAL_OVERRIDES.labels(field=field).inc()
    except Exception:
        pass


def _resolve_market_from_plan(ctx: PartRenderContext) -> str:
    """Return the plan-supplied market override or empty string.

    Caller ``or``s the result with the upstream-derived market value
    (``ctx.mv_market``) so empty-from-plan means "inherit from the
    upstream resolver" rather than "force empty".
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return ""
    return (rp.subtitle_policy.market or "").strip()


# Strategic-1c — Audit 2026-06-08 closure (UP26 subtitle_emphasis).
# Multipliers applied to the operator-supplied subtitle font size
# (payload.sub_font_size) before passing to the ASS / overlay
# pipelines. None / "balanced" / unknown values map to 1.0 — a
# pre-Strategic-1c byte-for-byte behaviour preservation. "subtle"
# shrinks slightly so subtitles sit lighter on busy frames;
# "aggressive" enlarges for emphasis-heavy short-form viral content.
_SUBTITLE_EMPHASIS_MULTIPLIERS: dict[str, float] = {
    "subtle":     0.85,
    "balanced":   1.0,
    "aggressive": 1.20,
}


def _apply_subtitle_emphasis(font_size: int, emphasis: "str | None") -> int:
    """Strategic-1c — return font_size scaled by the operator's
    subtitle_emphasis preference. The scaled value is clamped to
    [10, 200] for sanity (an aggressive 1.20x of a 90pt font yields
    108pt, still inside the cap). None / "balanced" / unknown
    emphasis returns font_size unchanged."""
    if not font_size:
        return font_size
    if not emphasis:
        return font_size
    key = str(emphasis).strip().lower()
    mult = _SUBTITLE_EMPHASIS_MULTIPLIERS.get(key)
    if not mult or mult == 1.0:
        return font_size
    return max(10, min(200, int(round(font_size * mult))))


_ALLOWED_SUBTITLE_MODES: frozenset[str] = frozenset({
    "word_by_word", "sentence", "phrase",
})


def _resolve_subtitle_mode_from_plan(ctx: PartRenderContext) -> str:
    """Return AI-directed subtitle timing mode or '' (inherit).

    word_by_word → karaoke writer, words_per_group=1
    phrase       → karaoke writer, words_per_group from pacing/speech_density
    sentence     → bounce writer (full sentence at once)
    ""           → inherit from existing style-based writer selection
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return ""
    mode = (getattr(rp.subtitle_policy, "subtitle_mode", "") or "").strip().lower()
    if mode not in _ALLOWED_SUBTITLE_MODES:
        return ""
    return mode


def _resolve_cta_audio_from_plan(ctx: PartRenderContext) -> str:
    """Return AI-specified CTA text from render_plan.audio_plan.cta_audio.

    Empty string means no override -- caller falls back to the CTA library.
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return ""
    return (getattr(rp.audio_plan, "cta_audio", "") or "").strip()


# Strategic-3 — Audit 2026-06-08 closure. Allowed CTA-type values that
# can come out of either the operator (payload.cta_type) or the AI
# (RenderPlan.overlays[kind=cta].type). Pre-Strategic-3 the AI's
# overlays[kind=cta] entry was silently dropped at
# render_pipeline.py:679-684 (the consumer loop only matched "hook").
# The AI's "type" field carried real intent — Strategic-3 surfaces
# it as a CTA-library lookup bias.
_ALLOWED_CTA_TYPES_FROM_PLAN: frozenset[str] = frozenset({
    "auto", "comment", "part_2", "follow",
})


def _resolve_cta_type_from_plan(ctx: PartRenderContext) -> str:
    """Return the AI's CTA type from the FIRST RenderPlan.overlays
    entry with ``kind=="cta"``. Empty string means no AI hint —
    caller continues with its existing resolution (operator-explicit
    cta_type → hook_type bias → library default).

    Validated against the allowed set so a future prompt drift to
    arbitrary type strings doesn't smuggle invalid values into the
    library lookup. Returns "" on any failure — Sacred Contract #3
    spirit applies to RenderPlan consumers.
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None or not rp.overlays:
        return ""
    try:
        for ov in rp.overlays:
            if str(ov.get("kind") or "").strip().lower() != "cta":
                continue
            t = str(ov.get("type") or "").strip().lower()
            if t in _ALLOWED_CTA_TYPES_FROM_PLAN:
                return t
            # Found a kind=cta but with an unknown type — bail out
            # rather than fall through to the next iteration (the
            # prompt instructs the AI to emit at most one per kind).
            return ""
    except Exception:
        pass
    return ""


# Phase U1 — Platform Ownership Resolution (2026-06-13).
# When ClipPlan.pacing is set (fast/medium/slow), the AI owns per-clip
# speed and the platform profile is demoted to a soft nudge clamped to
# ±_PLATFORM_SOFT_CAP. When pacing is empty or ctx has no render_plan,
# returns (0.0, full_platform_delta) — byte-for-byte pre-U1 behaviour
# (Sacred Contract #2).
_PACING_TO_SPEED_DELTA: dict[str, float] = {
    "fast":   +0.08,
    "medium":  0.00,
    "slow":   -0.06,
}
_PLATFORM_SOFT_CAP = 0.02


def _resolve_pacing_speed_delta(
    ctx: "PartRenderContext",
    idx: int,
    target_platform: str = "",
) -> tuple[float, float]:
    """Return (pacing_delta, effective_platform_delta) for playback speed.

    idx is 1-based (matches process_one_part's enumerate(start=1) convention).
    Never raises — returns (0.0, full_platform_delta) on any error
    (Sacred Contract #3 spirit for RenderPlan consumers).
    """
    try:
        from app.features.render.engine.pipeline.pipeline_segment_selection import _PLATFORM_PROFILES
        full_platform_delta: float = float(
            _PLATFORM_PROFILES.get(target_platform, {}).get("speed_delta", 0.0)
        )
        rp = getattr(ctx, "render_plan", None)
        if rp is not None and idx > 0:
            clips = getattr(rp, "clips", None) or []
            if idx - 1 < len(clips):
                pacing = (getattr(clips[idx - 1], "pacing", "") or "").strip().lower()
                if pacing in _PACING_TO_SPEED_DELTA:
                    ai_delta = _PACING_TO_SPEED_DELTA[pacing]
                    soft_platform = max(
                        -_PLATFORM_SOFT_CAP,
                        min(_PLATFORM_SOFT_CAP, full_platform_delta),
                    )
                    return ai_delta, soft_platform
        return 0.0, full_platform_delta
    except Exception:
        return 0.0, 0.0


__all__ = [
    "_RENDER_PLAN_ALLOWED_SUBTITLE_STYLES",
    "_resolve_subtitle_style_from_plan",
    "_resolve_market_from_plan",
    "_SUBTITLE_EMPHASIS_MULTIPLIERS",
    "_apply_subtitle_emphasis",
    "_ALLOWED_SUBTITLE_MODES",
    "_resolve_subtitle_mode_from_plan",
    "_resolve_cta_audio_from_plan",
    "_ALLOWED_CTA_TYPES_FROM_PLAN",
    "_resolve_cta_type_from_plan",
    "_PACING_TO_SPEED_DELTA",
    "_PLATFORM_SOFT_CAP",
    "_resolve_pacing_speed_delta",
]
