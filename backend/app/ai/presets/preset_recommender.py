"""
preset_recommender.py — Advisory preset recommender. Phase 13.

Derives suggested adjustments from PresetEvolutionReport best_samples.
Advisory only — never mutates payload, never auto-applies preset changes.

Allowed suggested adjustments:
    subtitle_tone, camera_behavior, pacing_style, target_duration_hint, ai_mode_hint

NEVER suggests:
    playback_speed, codec changes, FFmpeg flags, timing mutations, validation changes.

Public API:
    recommend_preset(report, current_context=None) -> PresetRecommendation
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Optional

from app.ai.presets.preset_schema import PresetEvolutionReport, PresetRecommendation

logger = logging.getLogger("app.ai.presets.recommender")

# Fields that are safe to suggest as adjustments
_SAFE_ADJUSTMENT_FIELDS = ("subtitle_tone", "camera_behavior", "pacing_style")

# Fields that must never appear in suggested_adjustments
_UNSAFE_FIELDS = frozenset({
    "playback_speed", "codec", "bitrate", "fps", "resolution",
    "output_format", "validation", "ffmpeg", "timing",
})


def recommend_preset(
    report: PresetEvolutionReport,
    current_context: Optional[dict] = None,
) -> PresetRecommendation:
    """Build an advisory PresetRecommendation from a PresetEvolutionReport.

    Args:
        report:          PresetEvolutionReport from preset_analyzer.
        current_context: Optional dict with "market", "mode", and other context.

    Returns:
        PresetRecommendation — never raises; returns minimal recommendation on error.
    """
    try:
        return _recommend(report, current_context or {})
    except Exception as exc:
        logger.debug("recommend_preset_failed: %s", exc)
        return PresetRecommendation(
            warnings=[f"recommend_error:{type(exc).__name__}"],
        )


# ── Internal recommender ──────────────────────────────────────────────────────

def _recommend(report: PresetEvolutionReport, context: dict) -> PresetRecommendation:
    if not report.available:
        return PresetRecommendation(
            confidence=0.0,
            warnings=["report_unavailable"],
        )

    samples = report.best_samples  # list[dict], already compacted
    if not samples:
        return PresetRecommendation(
            confidence=0.0,
            warnings=["no_best_samples"],
        )

    ctx_market = str(context.get("market") or report.market or "").strip()
    ctx_mode = str(context.get("mode") or report.ai_mode or "").strip()

    # ── Dominant preset name ──────────────────────────────────────────────────
    preset_names = [s.get("preset") for s in samples if s.get("preset")]
    recommended_preset = (
        Counter(preset_names).most_common(1)[0][0] if preset_names else None
    )

    # ── Safe adjustments from dominant patterns ───────────────────────────────
    adjustments: dict = {}

    for field in _SAFE_ADJUSTMENT_FIELDS:
        vals = [s.get(field) for s in samples if s.get(field)]
        if vals:
            dominant = Counter(vals).most_common(1)[0][0]
            adjustments[field] = dominant

    # target_duration_hint: median duration of high-score samples
    high_score_samples = [s for s in samples if (s.get("score") or 0) >= 60]
    durations = [s.get("duration") for s in high_score_samples if s.get("duration")]
    if durations:
        durations_sorted = sorted(float(d) for d in durations)
        adjustments["target_duration_hint"] = round(durations_sorted[len(durations_sorted) // 2], 1)

    # ai_mode_hint: most common mode in best samples
    modes = [s.get("ai_mode") for s in samples if s.get("ai_mode")]
    if modes:
        adjustments["ai_mode_hint"] = Counter(modes).most_common(1)[0][0]

    # Safety gate: strip any unsafe fields that may have slipped through
    adjustments = {k: v for k, v in adjustments.items() if k not in _UNSAFE_FIELDS}

    # ── Confidence ────────────────────────────────────────────────────────────
    confidence = _compute_confidence(samples, ctx_market, ctx_mode)

    # ── Reasons (max 5) ───────────────────────────────────────────────────────
    reasons: list[str] = []

    market_samples = [s for s in samples if s.get("market", "").lower() == ctx_market.lower() and ctx_market]
    mode_samples = [s for s in samples if s.get("ai_mode", "").lower() == ctx_mode.lower() and ctx_mode]

    if market_samples:
        reasons.append(
            f"Similar high-score {ctx_market} renders inform this suggestion"
        )
    if mode_samples:
        reasons.append(
            f"Fast pacing correlated with stronger {ctx_mode} output scores"
        )
    if adjustments.get("subtitle_tone"):
        reasons.append(
            f"Similar successful renders used {adjustments['subtitle_tone']!r} subtitle tone"
        )
    if adjustments.get("camera_behavior"):
        reasons.append(
            f"{adjustments['camera_behavior']!r} camera behavior common in high-score outputs"
        )
    if adjustments.get("pacing_style"):
        reasons.append(
            f"{adjustments['pacing_style']!r} pacing style correlated with better retention"
        )
    # Generic fallback reason if none were added
    if not reasons:
        reasons.append("Preset recommendation based on similar successful renders")

    logger.info(
        "ai_preset_evolution_generated recommendation preset=%s confidence=%.1f adjustments=%d",
        recommended_preset or "none",
        confidence,
        len(adjustments),
    )

    return PresetRecommendation(
        recommended_preset=recommended_preset,
        confidence=confidence,
        reasons=reasons[:5],
        suggested_adjustments=adjustments,
    )


# ── Confidence for recommendation ─────────────────────────────────────────────

def _compute_confidence(samples: list[dict], ctx_market: str, ctx_mode: str) -> float:
    n = len(samples)
    base = min(50.0, n * 15.0)

    # Penalty for very few samples
    if n < 2:
        base -= 15.0

    # High-score bonus
    high_score = [s for s in samples if (s.get("score") or 0) >= 70]
    base += min(20.0, len(high_score) * 8.0)

    # Context match bonus
    match_bonus = 0.0
    for s in samples:
        m = bool(ctx_market and s.get("market", "").lower() == ctx_market.lower())
        a = bool(ctx_mode and s.get("ai_mode", "").lower() == ctx_mode.lower())
        if m and a:
            match_bonus += 5.0
        elif m or a:
            match_bonus += 2.0
    base += min(20.0, match_bonus)

    return round(max(0.0, min(100.0, base)), 1)
