"""
preset_analyzer.py — Deterministic preset performance analyzer. Phase 13.

Parses historical render memories into structured PresetPerformanceSamples,
scores them by relevance to the current market/mode context, and returns a
compact PresetEvolutionReport.

No external dependencies. No ML models. No API calls. Never raises.

Public API:
    analyze_preset_performance(memories, context=None) -> PresetEvolutionReport
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Optional

from app.ai.presets.preset_schema import (
    PresetEvolutionReport,
    PresetPerformanceSample,
)

logger = logging.getLogger("app.ai.presets.analyzer")

# Usable status values and their weight multipliers
_STATUS_WEIGHT: dict[str, float] = {
    "completed": 1.0,
    "completed_with_errors": 0.7,
    "failed": 0.2,
}
_DEFAULT_WEIGHT = 0.5

# Safe adjustable fields extracted from sample metadata
_ADJUSTABLE_FIELDS = ("subtitle_tone", "camera_behavior", "pacing_style", "ai_mode", "story_arc")

# Max best samples to carry in the report
_MAX_BEST_SAMPLES = 5


def analyze_preset_performance(
    memories: Any,
    context: Optional[dict] = None,
) -> PresetEvolutionReport:
    """Analyze historical render memories for preset performance patterns.

    Args:
        memories: list of memory result dicts or MemorySearchResult-like objects.
                  Each should have a "metadata" key (or attribute) containing
                  market, mode, score, subtitle_tone, camera_behavior, status, etc.
        context:  Optional dict with "market" and "mode" for relevance scoring.

    Returns:
        PresetEvolutionReport — never raises; returns minimal report on error.
    """
    try:
        return _analyze(list(memories) if memories else [], context or {})
    except Exception as exc:
        logger.debug("analyze_preset_performance_failed: %s", exc)
        return PresetEvolutionReport(
            available=False,
            warnings=[f"preset_analysis_error:{type(exc).__name__}"],
        )


# ── Internal analysis ─────────────────────────────────────────────────────────

def _analyze(raw_memories: list, context: dict) -> PresetEvolutionReport:
    ctx_market = str(context.get("market") or "").strip().lower()
    ctx_mode = str(context.get("mode") or "").strip().lower()

    warnings: list[str] = []

    # ── Parse samples ─────────────────────────────────────────────────────────
    samples: list[PresetPerformanceSample] = []
    for raw in raw_memories:
        sample = _parse_sample(raw)
        if sample is not None:
            samples.append(sample)

    if not samples:
        return PresetEvolutionReport(
            available=False,
            market=context.get("market"),
            ai_mode=context.get("mode"),
            warnings=["no_memory_samples"],
        )

    # ── Relevance scoring ─────────────────────────────────────────────────────
    scored: list[tuple[float, PresetPerformanceSample]] = [
        (_relevance(s, ctx_market, ctx_mode), s)
        for s in samples
    ]
    scored.sort(key=lambda x: x[0], reverse=True)

    # ── Separate usable from failed ───────────────────────────────────────────
    usable = [s for _, s in scored if _is_usable(s)]
    failed_count = sum(1 for _, s in scored if _is_failed(s))

    if not usable:
        return PresetEvolutionReport(
            available=False,
            market=context.get("market"),
            ai_mode=context.get("mode"),
            warnings=["no_usable_samples", f"failed_count={failed_count}"],
        )

    if failed_count > 0:
        warnings.append(f"failed_sample_count={failed_count}")

    # ── Top best samples ──────────────────────────────────────────────────────
    top_usable = [s for _, s in scored if _is_usable(s)][:_MAX_BEST_SAMPLES]
    best_samples = [_compact_sample(s) for s in top_usable]

    # ── Confidence ────────────────────────────────────────────────────────────
    confidence = _compute_confidence(usable, samples, ctx_market, ctx_mode)

    if confidence < 20.0:
        warnings.append("low_confidence_few_samples")

    logger.info(
        "ai_preset_evolution_generated market=%s mode=%s samples=%d usable=%d confidence=%.1f",
        ctx_market or "none",
        ctx_mode or "none",
        len(samples),
        len(usable),
        confidence,
    )

    return PresetEvolutionReport(
        available=True,
        market=context.get("market"),
        ai_mode=context.get("mode"),
        best_samples=best_samples,
        recommendation=None,  # filled by preset_recommender
        warnings=warnings,
    )


# ── Sample parsing ────────────────────────────────────────────────────────────

def _parse_sample(raw: Any) -> Optional[PresetPerformanceSample]:
    """Convert a raw memory dict or object to a PresetPerformanceSample."""
    try:
        if isinstance(raw, dict):
            meta = raw.get("metadata") or {}
            # Top-level keys take precedence, metadata fills the rest
            combined = {**meta, **{k: v for k, v in raw.items() if k != "metadata" and v is not None}}
        else:
            meta = getattr(raw, "metadata", {}) or {}
            combined = dict(meta)
            for attr in ("preset", "ai_mode", "market", "score", "duration",
                         "subtitle_tone", "camera_behavior", "pacing_style",
                         "story_arc", "status"):
                val = getattr(raw, attr, None)
                if val is not None:
                    combined[attr] = val

        return PresetPerformanceSample(
            preset=_str_or_none(combined.get("preset")),
            ai_mode=_str_or_none(combined.get("mode") or combined.get("ai_mode")),
            market=_str_or_none(combined.get("market")),
            score=_float_or_none(combined.get("score")),
            duration=_float_or_none(combined.get("duration")),
            subtitle_tone=_str_or_none(combined.get("subtitle_tone")),
            camera_behavior=_str_or_none(combined.get("camera_behavior")),
            pacing_style=_str_or_none(combined.get("pacing_style")),
            story_arc=_str_or_none(combined.get("story_arc")),
            status=_str_or_none(combined.get("status")),
            metadata=dict(combined),
        )
    except Exception:
        return None


# ── Relevance scoring ─────────────────────────────────────────────────────────

def _relevance(sample: PresetPerformanceSample, ctx_market: str, ctx_mode: str) -> float:
    """Compute 0-1 relevance score for a sample given current context."""
    rel = 0.40  # baseline

    # Status weight
    status_key = (sample.status or "").lower()
    weight = _STATUS_WEIGHT.get(status_key, _DEFAULT_WEIGHT)
    rel *= weight / _DEFAULT_WEIGHT  # normalize around default

    # Market match
    if ctx_market and sample.market and sample.market.strip().lower() == ctx_market:
        rel += 0.25

    # Mode match
    if ctx_mode and sample.ai_mode and sample.ai_mode.strip().lower() == ctx_mode:
        rel += 0.25

    # Output score contribution (scale: score/100 * 0.30)
    if sample.score is not None:
        try:
            rel += float(sample.score) / 100.0 * 0.30
        except (TypeError, ValueError):
            pass

    return max(0.0, min(1.0, rel))


# ── Confidence calculation ────────────────────────────────────────────────────

def _compute_confidence(
    usable: list[PresetPerformanceSample],
    all_samples: list[PresetPerformanceSample],
    ctx_market: str,
    ctx_mode: str,
) -> float:
    n_usable = len(usable)
    n_total = len(all_samples)
    n_failed = sum(1 for s in all_samples if _is_failed(s))

    # Base: up to 60 from sample count (12 points per sample, capped)
    base = min(60.0, n_usable * 12.0)

    # Penalty for small sample count
    if n_usable < 3:
        base -= (3 - n_usable) * 8.0

    # Failure rate penalty
    if n_total > 0:
        fail_rate = n_failed / n_total
        base -= fail_rate * 25.0

    # Market + mode match bonus (up to 20 points)
    match_bonus = 0.0
    for s in usable:
        m = bool(ctx_market and s.market and s.market.strip().lower() == ctx_market)
        a = bool(ctx_mode and s.ai_mode and s.ai_mode.strip().lower() == ctx_mode)
        if m and a:
            match_bonus += 5.0
        elif m or a:
            match_bonus += 2.0
    match_bonus = min(20.0, match_bonus)

    return round(max(0.0, min(100.0, base + match_bonus)), 1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_usable(sample: PresetPerformanceSample) -> bool:
    status = (sample.status or "").lower()
    return status in ("completed", "completed_with_errors", "")


def _is_failed(sample: PresetPerformanceSample) -> bool:
    return (sample.status or "").lower() == "failed"


def _compact_sample(s: PresetPerformanceSample) -> dict:
    return {k: v for k, v in s.to_dict().items() if v is not None}


def _str_or_none(val: Any) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _float_or_none(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
