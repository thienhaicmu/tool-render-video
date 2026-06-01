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

try:
    from app.ai.analysis.groq import select_segments, GroqSegment
    _GROQ_MODULE_AVAILABLE = True
except ImportError:
    _GROQ_MODULE_AVAILABLE = False


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
        logger.debug("groq_stage: module not available")
        return None

    if not full_srt_available or not full_srt.exists():
        logger.debug("groq_stage: SRT not available — skipping")
        return None

    # Read API key: prefer request-level (UI input), fallback to server env.
    from app.core import config as _cfg
    api_key = (getattr(payload, "ai_cloud_api_key", "") or "").strip() or _cfg.GROQ_API_KEY
    if not api_key:
        logger.debug("groq_stage: no GROQ_API_KEY configured")
        return None

    try:
        srt_content = full_srt.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        logger.debug("groq_stage: cannot read SRT — %s", exc)
        return None

    output_count = max(1, int(getattr(payload, "output_count", 1)))
    min_sec      = float(getattr(payload, "min_part_sec", 15))
    max_sec      = float(getattr(payload, "max_part_sec", 60))
    video_duration = float(source.get("duration") or 0.0)
    model        = getattr(payload, "groq_model", None) or None
    language     = getattr(payload, "groq_content_language", None) or "auto"

    logger.info(
        "groq_stage: requesting %d segments %.0f–%.0fs model=%s",
        output_count, min_sec, max_sec, model or "default",
    )

    segments = select_segments(
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
        logger.info("groq_stage: no segments returned — keeping local scored")
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
