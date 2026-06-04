"""
llm_stage.py — LLM SRT analysis stage for the render pipeline.

Called by the render pipeline after source preparation.
  1. Reads the full SRT transcript
  2. Calls the configured LLM (Gemini / OpenAI / Claude) to select segments
  3. Converts LLMSegment → scored-compatible dicts
  4. Returns the new scored list, or None on failure (caller hard-fails)

AI Safety (Contract 3): never raises — returns None on any error.

Editorial hint system:
  hook_strength and video_type from the payload are translated into a short
  advisory phrase appended to the LLM system prompt. Unknown or default
  values produce an empty hint (no-op).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("app.render.llm_stage")
logger.info("llm_stage: module loaded (build=2026-06-04.gemini-default)")

try:
    from app.ai.llm import select_segments as _llm_select, SUPPORTED_PROVIDERS
    _LLM_MODULE_AVAILABLE = True
except ImportError as _import_exc:
    _LLM_MODULE_AVAILABLE = False
    logger.warning("llm_stage: llm dispatcher import FAILED — %s", _import_exc)


# ── Editorial hint tables ─────────────────────────────────────────────────────
# Values map to advisory phrases appended to the LLM system prompt.
# Empty string = no instruction added (keeps baseline behavior).
# Phrases are intentionally short to minimise prompt token overhead and
# avoid confusing JSON-mode models with long prose instructions.

_HOOK_HINTS: dict[str, str] = {
    "aggressive": (
        "Prefer segments where the first 2–3 seconds immediately hook the viewer "
        "with a bold claim, surprising reveal, or strong emotional trigger."
    ),
    "balanced": "",   # default — baseline prompt already covers this
    "soft": (
        "Prefer segments with natural, authentic openings that build trust gradually "
        "rather than aggressive shock-value hooks."
    ),
}

_VIDEO_TYPE_HINTS: dict[str, str] = {
    "auto":           "",  # no bias — let model decide
    "viral":          "Favour highly shareable moments: surprising reveals, relatable humour, or strong emotional peaks that viewers want to share.",
    "storytelling":   "Favour segments with a clear narrative arc — setup, tension, and payoff — that tell a self-contained mini-story.",
    "educational":    "Favour segments that teach something concrete: clear explanations, step-by-step logic, or actionable insights.",
    "emotional":      "Favour emotionally resonant moments: genuine reactions, vulnerability, triumph, or heartfelt exchanges.",
    "high_retention": "Favour segments that maintain consistent engagement from start to finish — avoid slow buildups or trailing-off endings.",
}


def _build_editorial_hint(payload: Any) -> str:
    """Translate hook_strength + video_type payload fields into a prompt hint.

    Returns an empty string when both fields are at their default/neutral
    values so the prompt is byte-for-byte identical to the baseline.
    The hint is ADVISORY only — it never requests new JSON fields and does
    not affect the parser, validation gates, or output dataclass shape.
    """
    parts: list[str] = []

    hook = (getattr(payload, "hook_strength", None) or "").strip().lower()
    h = _HOOK_HINTS.get(hook, "")
    if h:
        parts.append(h)

    vtype = (getattr(payload, "video_type", None) or "").strip().lower()
    v = _VIDEO_TYPE_HINTS.get(vtype, "")
    if v:
        parts.append(v)

    return " ".join(parts)


def _resolve_api_key(payload: Any, provider: str) -> tuple[str, str]:
    """Return (api_key, source_label) for the given provider.

    Resolution order per provider:
      1. Per-provider payload field (e.g. payload.gemini_api_key)
      2. Generic payload field (payload.ai_cloud_api_key) — UI sends the active provider's key here
      3. Server env var (GEMINI_API_KEY / GROQ_API_KEY / etc.)
    """
    from app.core import config as _cfg
    _per_provider_attr = {
        "gemini": "gemini_api_key",
        "openai": "openai_api_key",
        "claude": "claude_api_key",
    }.get(provider, "")
    _per_provider_env = {
        "gemini": "GEMINI_API_KEY",
        "openai": "OPENAI_API_KEY",
        "claude": "CLAUDE_API_KEY",
    }.get(provider, "")

    if _per_provider_attr:
        _key = (getattr(payload, _per_provider_attr, "") or "").strip()
        if _key:
            return _key, f"payload.{_per_provider_attr}"

    _generic = (getattr(payload, "ai_cloud_api_key", "") or "").strip()
    if _generic:
        return _generic, "payload.ai_cloud_api_key"

    if _per_provider_env:
        import os
        _env = (os.getenv(_per_provider_env) or "").strip()
        if _env:
            return _env, f"env.{_per_provider_env}"

    return "", "none"


def run_llm_segment_selection(
    full_srt: Path,
    full_srt_available: bool,
    scored: list,
    payload: Any,
    source: dict,
) -> Optional[list]:
    """
    Try to replace the local `scored` list with LLM-selected segments.

    Returns:
        list  — new scored-compatible dicts from the LLM (caller replaces scored)
        None  — LLM unavailable / failed / disabled (caller keeps local scored)
    """
    try:
        return _run(full_srt, full_srt_available, scored, payload, source)
    except Exception as exc:
        logger.debug("llm_stage: unexpected error — %s", exc)
        return None


# ── Internal ──────────────────────────────────────────────────────────────────

def _run(
    full_srt: Path,
    full_srt_available: bool,
    scored: list,
    payload: Any,
    source: dict,
) -> Optional[list]:
    if not _LLM_MODULE_AVAILABLE:
        logger.warning("llm_stage: llm dispatcher not available")
        return None

    if not full_srt_available or not full_srt.exists():
        logger.warning("llm_stage: SRT not available — skipping (path=%s)", full_srt)
        return None

    # Resolve provider — env override applied in route handler, else default gemini.
    provider = (getattr(payload, "ai_provider", None) or "gemini").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        logger.warning("llm_stage: unsupported provider %r — falling back to gemini", provider)
        provider = "gemini"

    api_key, _key_source = _resolve_api_key(payload, provider)
    if not api_key:
        logger.warning(
            "llm_stage: NO API KEY for provider=%s (checked payload + env)",
            provider,
        )
        return None
    logger.info(
        "llm_stage: provider=%s api_key_source=%s len=%d prefix=%s",
        provider, _key_source, len(api_key),
        api_key[:8] + "..." if len(api_key) > 8 else api_key,
    )

    try:
        srt_content = full_srt.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("llm_stage: cannot read SRT (%s) — %s", full_srt, exc)
        return None

    output_count = max(1, int(getattr(payload, "output_count", 1)))
    min_sec      = float(getattr(payload, "min_part_sec", 15))
    max_sec      = float(getattr(payload, "max_part_sec", 60))
    video_duration = float(source.get("duration") or 0.0)
    model        = getattr(payload, "llm_model", None) or None
    language     = getattr(payload, "llm_language", None) or "auto"
    editorial_hint = _build_editorial_hint(payload)

    logger.info(
        "llm_stage: requesting %d segments %.0f–%.0fs provider=%s model=%s "
        "srt_chars=%d dur=%.0f editorial_hint=%r",
        output_count, min_sec, max_sec, provider, model or "default",
        len(srt_content), video_duration, editorial_hint or "(none)",
    )

    segments = _llm_select(
        provider=provider,
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

    if not segments:
        logger.warning(
            "llm_stage: no segments returned from select_segments() "
            "— check llm_client logs above for raw API response",
        )
        return None

    # Apply min_quality_score filter — prefer segments above threshold but never
    # hard-fail when the LLM returned parseable segments.
    min_score = float(getattr(payload, "llm_min_quality", None) or 0.6)
    _passing = [s for s in segments if s.score >= min_score]
    if not _passing:
        logger.warning(
            "llm_stage: all %d segments scored below min_quality_score=%.2f "
            "(best=%.2f) — proceeding with best available to avoid job failure",
            len(segments), min_score,
            max((s.score for s in segments), default=0.0),
        )
        # Use all returned segments (already sorted by score desc, count capped by parser).
    else:
        segments = _passing

    converted = [_to_scored_dict(seg) for seg in segments]
    logger.info("llm_stage: %d LLM segments will replace local scored", len(converted))
    return converted


def _to_scored_dict(seg: "LLMSegment") -> dict:
    """Convert LLMSegment → dict compatible with pipeline scored[] format."""
    _base = seg.score * 100.0
    # Use real AI sub-scores when Sprint A populated them; fall back to base score.
    viral_score     = (seg.viral_score * 100.0)     if seg.viral_score     else _base
    hook_score      = (seg.hook_score * 100.0)      if seg.hook_score      else _base
    retention_score = (seg.retention_score * 100.0) if seg.retention_score else _base
    return {
        # Core timing — used by render loop for FFmpeg cut
        "start":    seg.start,
        "end":      seg.end,
        "duration": seg.end - seg.start,
        # Score fields — expected by downstream selection filters
        "viral_score":     viral_score,
        "hook_score":      hook_score,
        "motion_score":    50.0,   # neutral (LLM doesn't analyze motion)
        "diversity_score": 50.0,
        "retention_score": retention_score,
        "audio_energy":    50.0,
        # LLM-specific metadata — additive, safe for existing consumers
        "clip_name":          seg.clip_name,
        "ai_title":           seg.title,
        "ai_reason":          seg.reason,
        "source":             "llm",
        # RenderPlan routing fields (Sprint A → consumed by downstream stages)
        "ai_subtitle_style":  seg.subtitle_style,              # → part_asset_planner:395
        "content_type_hint":  seg.content_type,                # → part_render_setup:144 + 7 other sites
        "hook_type":          seg.hook_type,                   # metadata
        "cover_hint_ratio":   seg.cover_offset_ratio or None,  # → part_done:144 (Sprint E)
        "speech_density":     seg.speech_density,              # metadata
        "duration_fit_score": seg.duration_fit * 100.0,        # metadata
    }
