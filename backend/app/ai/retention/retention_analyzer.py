"""
retention_analyzer.py — Deterministic viewer retention analyzer. Phase 16.

Computes an overall retention score and identifies strengths/weaknesses
using pacing, story, subtitle, and transcript signals.

No ML models, no external APIs. Deterministic heuristics only.

Public API:
    analyze_retention(
        transcript_chunks=None,
        pacing_context=None,
        story_context=None,
        subtitle_context=None,
        beat_context=None,
        memory_context=None,
    ) -> RetentionAnalysis
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.ai.retention.retention_schema import RetentionAnalysis, RetentionRiskRegion
from app.ai.retention.dropoff_detector import detect_retention_risks

logger = logging.getLogger("app.ai.retention.analyzer")

# Score modifiers per risk severity
_SEVERITY_PENALTY: dict[str, int] = {"low": 5, "medium": 12, "high": 20}

# Score bonuses per strength label
_STRENGTH_BONUS: dict[str, int] = {
    "strong opening hook": 8,
    "clear climax or payoff": 6,
    "high pacing energy": 5,
    "compact subtitle density": 3,
    "similar successful edit found in memory": 4,
}

_BASE_SCORE = 70.0


def analyze_retention(
    transcript_chunks: Any = None,
    pacing_context: Any = None,
    story_context: Any = None,
    subtitle_context: Any = None,
    beat_context: Any = None,
    memory_context: Any = None,
) -> RetentionAnalysis:
    """Analyze viewer retention potential. Never raises.

    Returns RetentionAnalysis with overall_retention_score (0-100),
    risk_regions, strengths, and warnings.
    """
    try:
        return _analyze(
            chunks=list(transcript_chunks) if transcript_chunks else [],
            pacing=dict(pacing_context) if isinstance(pacing_context, dict) else {},
            story=dict(story_context) if isinstance(story_context, dict) else {},
            subtitle=dict(subtitle_context) if isinstance(subtitle_context, dict) else {},
            beat=dict(beat_context) if isinstance(beat_context, dict) else {},
            memory=dict(memory_context) if isinstance(memory_context, dict) else {},
        )
    except Exception as exc:
        logger.debug("analyze_retention_failed: %s", exc)
        return RetentionAnalysis(
            available=False,
            overall_retention_score=0.0,
            warnings=[f"retention_analyze_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _analyze(
    chunks: list,
    pacing: dict,
    story: dict,
    subtitle: dict,
    beat: dict,
    memory: dict,
) -> RetentionAnalysis:
    risk_regions = detect_retention_risks(
        transcript_chunks=chunks,
        pacing_context=pacing,
        story_context=story,
        subtitle_context=subtitle,
        beat_context=beat,
    )

    strengths = _compute_strengths(risk_regions, pacing, story, memory, subtitle, chunks)
    score = _compute_score(risk_regions, strengths)

    logger.info(
        "ai_retention_analysis_generated score=%.1f risks=%d strengths=%d",
        score,
        len(risk_regions),
        len(strengths),
    )

    return RetentionAnalysis(
        available=True,
        overall_retention_score=score,
        risk_regions=risk_regions,
        strengths=strengths,
        warnings=[],
    )


def _compute_score(
    risk_regions: List[RetentionRiskRegion],
    strengths: List[str],
) -> float:
    score = _BASE_SCORE

    for region in risk_regions:
        penalty = _SEVERITY_PENALTY.get(region.severity, 0)
        score -= penalty

    for strength in strengths:
        for key, bonus in _STRENGTH_BONUS.items():
            if key in strength:
                score += bonus
                break

    return max(0.0, min(100.0, score))


def _compute_strengths(
    risk_regions: List[RetentionRiskRegion],
    pacing: dict,
    story: dict,
    memory: dict,
    subtitle: dict,
    chunks: list,
) -> List[str]:
    strengths: List[str] = []
    segments = story.get("segments", [])
    risk_categories = {r.category for r in risk_regions}

    # Strong opening hook
    has_hook_segment = any(
        isinstance(s, dict) and s.get("segment_type") == "hook"
        for s in segments
    )
    if has_hook_segment and "weak_hook" not in risk_categories:
        strengths.append("strong opening hook")

    # Clear climax or payoff
    has_climax_or_payoff = any(
        isinstance(s, dict) and s.get("segment_type") in ("climax", "payoff")
        for s in segments
    )
    if has_climax_or_payoff:
        strengths.append("clear climax or payoff")

    # High pacing energy
    energy = float(pacing.get("energy_level") or 0.0)
    if energy >= 0.65:
        strengths.append("high pacing energy")

    # Compact subtitle density
    density = str(subtitle.get("density") or "normal").lower()
    max_wpl = subtitle.get("max_words_per_line")
    wpl_ok = max_wpl is None or (isinstance(max_wpl, (int, float)) and int(max_wpl) <= 7)
    if density != "dense" and wpl_ok and "subtitle_overload" not in risk_categories:
        strengths.append("compact subtitle density")

    # Memory support (similar successful render found)
    results = memory.get("results", [])
    if isinstance(results, list) and results:
        strengths.append("similar successful edit found in memory")

    return strengths[:6]
