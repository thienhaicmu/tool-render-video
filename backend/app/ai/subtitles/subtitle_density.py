"""
subtitle_density.py — Subtitle density intelligence. Phase 17.

Deterministic heuristics only. Never raises. No transcript mutation.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.subtitles")

_DENSITY_OVERLOAD_AVG = 6.0   # avg words/chunk above this → compact
_DENSITY_OVERLOAD_MAX = 12    # single chunk word count above this → overload
_DENSITY_EXPRESSIVE_AVG = 3.0 # avg words/chunk below this → expressive


def analyze_subtitle_density(
    transcript_chunks=None,
    pacing_context=None,
    story_context=None,
) -> dict:
    """Analyze subtitle density from transcript and pacing signals.

    Returns compact dict: available, density_mode, overload_detected,
    avg_words_per_chunk, max_words_chunk, warnings. Never raises.
    """
    try:
        return _analyze_density(transcript_chunks, pacing_context, story_context)
    except Exception as exc:
        logger.debug("subtitle_density_failed: %s", exc)
        return {
            "available": False,
            "density_mode": "normal",
            "overload_detected": False,
            "avg_words_per_chunk": 0.0,
            "max_words_chunk": 0,
            "warnings": [f"density_error:{type(exc).__name__}"],
        }


def _analyze_density(transcript_chunks, pacing_context, story_context) -> dict:
    chunks = list(transcript_chunks or [])
    pacing_ctx = dict(pacing_context or {})
    story_ctx = dict(story_context or {})

    warnings: list[str] = []
    density_mode = "normal"
    overload_detected = False

    if not chunks:
        return {
            "available": False,
            "density_mode": "normal",
            "overload_detected": False,
            "avg_words_per_chunk": 0.0,
            "max_words_chunk": 0,
            "warnings": ["no_chunks"],
        }

    word_counts = [
        len(str(c.get("text") or "").split())
        for c in chunks
        if isinstance(c, dict)
    ]

    if not word_counts:
        return {
            "available": False,
            "density_mode": "normal",
            "overload_detected": False,
            "avg_words_per_chunk": 0.0,
            "max_words_chunk": 0,
            "warnings": ["no_valid_chunks"],
        }

    avg_words = sum(word_counts) / len(word_counts)
    max_words = max(word_counts)

    # Overload detection
    if avg_words > _DENSITY_OVERLOAD_AVG or max_words > _DENSITY_OVERLOAD_MAX:
        overload_detected = True
        density_mode = "compact"
        warnings.append("subtitle_density_overload")

    if not overload_detected:
        pacing_style = str(pacing_ctx.get("pacing_style") or "").lower()
        if pacing_style in ("fast", "dynamic"):
            density_mode = "compact"
        elif pacing_style in ("slow_build", "slow"):
            density_mode = "expressive"
        elif avg_words < _DENSITY_EXPRESSIVE_AVG:
            density_mode = "expressive"

        # Story arc override
        dominant_arc = str(story_ctx.get("dominant_arc") or "").lower()
        if dominant_arc in ("curiosity_build", "tension_release", "front_loaded"):
            density_mode = "compact"

    logger.info(
        "ai_subtitle_density_detected density_mode=%s overload=%s avg_words=%.1f",
        density_mode, overload_detected, avg_words,
    )

    return {
        "available": True,
        "density_mode": density_mode,
        "overload_detected": overload_detected,
        "avg_words_per_chunk": round(avg_words, 2),
        "max_words_chunk": max_words,
        "warnings": warnings,
    }
