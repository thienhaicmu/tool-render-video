"""
groq_stage.py — Groq SRT analysis stage for the render pipeline.

Called by pipeline_pre_render.py after local segment scoring.
When groq_analysis_enabled=True:
  1. Reads the full SRT transcript
  2. Calls Groq to select the best segments (respects output_count + duration limits)
  3. Converts GroqSegment → scored-compatible dicts
  4. Returns the new scored list, or None on failure (caller keeps local scored)

AI Safety (Contract 3): never raises — returns None on any error.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("app.render.groq_stage")
logger.info("groq_stage: module loaded (build=2026-06-01.h2-verbose-diagnostics)")

try:
    from app.ai.analysis.groq import GroqSegment
    from app.ai.llm import select_segments as _llm_select, SUPPORTED_PROVIDERS
    _GROQ_MODULE_AVAILABLE = True
except ImportError as _import_exc:
    _GROQ_MODULE_AVAILABLE = False
    logger.warning("groq_stage: llm dispatcher import FAILED — %s", _import_exc)


def _resolve_api_key(payload: Any, provider: str) -> tuple[str, str]:
    """Return (api_key, source_label) for the given provider.

    Resolution order per provider:
      1. Per-provider payload field (e.g. payload.gemini_api_key)
      2. Generic payload field (payload.ai_cloud_api_key) — UI sends the active provider's key here
      3. Server env var (GEMINI_API_KEY / GROQ_API_KEY / etc.)
    """
    from app.core import config as _cfg
    _per_provider_attr = {
        "groq":   "groq_api_key",
        "gemini": "gemini_api_key",
        "openai": "openai_api_key",
        "claude": "claude_api_key",
    }.get(provider, "")
    _per_provider_env = {
        "groq":   "GROQ_API_KEY",
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

    # Legacy fallback for Groq path that already supports GROQ_API_KEY via _cfg
    if provider == "groq" and getattr(_cfg, "GROQ_API_KEY", ""):
        return _cfg.GROQ_API_KEY, "env.GROQ_API_KEY (cfg)"

    return "", "none"


def run_groq_segment_selection(
    full_srt: Path,
    full_srt_available: bool,
    scored: list,
    payload: Any,
    source: dict,
) -> Optional[list]:
    """
    Try to replace the local `scored` list with Groq-selected segments.

    Returns:
        list  — new scored-compatible dicts from Groq (caller replaces scored)
        None  — Groq unavailable / failed / disabled (caller keeps local scored)
    """
    try:
        return _run(full_srt, full_srt_available, scored, payload, source)
    except Exception as exc:
        logger.debug("groq_stage: unexpected error — %s", exc)
        return None


# ── Internal ──────────────────────────────────────────────────────────────────

def _run(
    full_srt: Path,
    full_srt_available: bool,
    scored: list,
    payload: Any,
    source: dict,
) -> Optional[list]:
    if not _GROQ_MODULE_AVAILABLE:
        logger.warning("groq_stage: llm dispatcher not available")
        return None

    if not full_srt_available or not full_srt.exists():
        logger.warning("groq_stage: SRT not available — skipping (path=%s)", full_srt)
        return None

    # Resolve provider — env override applied in route handler, else default groq.
    provider = (getattr(payload, "ai_provider", None) or "groq").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        logger.warning("groq_stage: unsupported provider %r — falling back to groq", provider)
        provider = "groq"

    api_key, _key_source = _resolve_api_key(payload, provider)
    if not api_key:
        logger.warning(
            "groq_stage: NO API KEY for provider=%s (checked payload + env)",
            provider,
        )
        return None
    logger.info(
        "groq_stage: provider=%s api_key_source=%s len=%d prefix=%s",
        provider, _key_source, len(api_key),
        api_key[:8] + "..." if len(api_key) > 8 else api_key,
    )

    try:
        srt_content = full_srt.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.warning("groq_stage: cannot read SRT (%s) — %s", full_srt, exc)
        return None

    output_count = max(1, int(getattr(payload, "output_count", 1)))
    min_sec      = float(getattr(payload, "min_part_sec", 15))
    max_sec      = float(getattr(payload, "max_part_sec", 60))
    video_duration = float(source.get("duration") or 0.0)
    # groq_model field stays as the universal "selected model" for all providers
    # (additive: Sacred Contract 2 — never rename existing fields).
    model        = getattr(payload, "groq_model", None) or None
    language     = getattr(payload, "groq_content_language", None) or "auto"

    logger.info(
        "groq_stage: requesting %d segments %.0f–%.0fs provider=%s model=%s "
        "srt_chars=%d dur=%.0f",
        output_count, min_sec, max_sec, provider, model or "default",
        len(srt_content), video_duration,
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
    )

    if not segments:
        logger.warning(
            "groq_stage: no segments returned from select_segments() "
            "— check groq_client logs above for raw API response",
        )
        return None

    # Apply min_quality_score filter
    min_score = float(getattr(payload, "groq_min_quality_score", 0.6))
    segments = [s for s in segments if s.score >= min_score]
    if not segments:
        logger.info("groq_stage: all segments below min_quality_score=%.2f — fallback", min_score)
        return None

    converted = [_to_scored_dict(seg) for seg in segments]
    logger.info("groq_stage: %d Groq segments will replace local scored", len(converted))
    return converted


def _to_scored_dict(seg: "GroqSegment") -> dict:
    """Convert GroqSegment → dict compatible with pipeline scored[] format."""
    viral_score = seg.score * 100.0
    return {
        # Core timing — used by render loop for FFmpeg cut
        "start":    seg.start,
        "end":      seg.end,
        "duration": seg.end - seg.start,
        # Score fields — expected by downstream selection filters
        "viral_score":     viral_score,
        "hook_score":      viral_score,
        "motion_score":    50.0,   # neutral (Groq doesn't analyze motion)
        "diversity_score": 50.0,
        "retention_score": viral_score,
        "audio_energy":    50.0,
        # Groq-specific metadata — additive, safe for existing consumers
        "clip_name":   seg.clip_name,
        "groq_title":  seg.title,
        "groq_reason": seg.reason,
        "source":      "groq",
    }
