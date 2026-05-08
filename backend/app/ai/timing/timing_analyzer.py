"""
timing_analyzer.py — Retention-driven timing candidate analyzer. Phase 19.

Maps retention risk signals to conservative timing mutation candidates.
Deterministic only. Never raises. No FFmpeg mutation. No timing mutation.
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.timing.timing_schema import (
    TimingMutationCandidate,
    _MAX_CANDIDATES,
    _MAX_TRIM_SECONDS,
)
from app.ai.timing.timing_safety import clamp_trim_seconds

logger = logging.getLogger("app.ai.timing")

# Risk category → action mapping
_RISK_ACTION_MAP: dict[str, str] = {
    "long_setup":      "tighten_setup",
    "silence_gap":     "trim_silence",
    "pacing_decay":    "shorten_outro",
    "weak_hook":       "hold_hook",
    "unclear_payoff":  "no_change",
}

# Actions that propose no trim (advisory-only)
_NO_TRIM_ACTIONS: frozenset[str] = frozenset({"hold_hook", "no_change", "none"})


def analyze_timing_candidates(
    retention_context: Any = None,
    story_context: Any = None,
    pacing_context: Any = None,
    transcript_chunks: Any = None,
) -> list[TimingMutationCandidate]:
    """Produce timing mutation candidates from retention risk data.

    Returns up to _MAX_CANDIDATES candidates. Never raises.
    """
    try:
        return _analyze(
            dict(retention_context or {}),
            dict(story_context or {}),
            dict(pacing_context or {}),
            list(transcript_chunks or []),
        )
    except Exception as exc:
        logger.debug("analyze_timing_candidates_failed: %s", exc)
        return []


def _analyze(
    ret_ctx: dict,
    story_ctx: dict,
    pacing_ctx: dict,
    chunks: list,
) -> list[TimingMutationCandidate]:
    candidates: list[TimingMutationCandidate] = []

    risk_regions = ret_ctx.get("risk_regions") or []
    total_duration = float(pacing_ctx.get("total_duration") or 0.0)

    # Story segment index for pacing_decay (last-25% check)
    story_segments = story_ctx.get("segments") or []
    last_quarter_start = total_duration * 0.75 if total_duration > 0 else None

    for risk in risk_regions:
        if len(candidates) >= _MAX_CANDIDATES:
            break

        if not isinstance(risk, dict):
            continue

        category = str(risk.get("category") or risk.get("risk_category") or "")
        action = _RISK_ACTION_MAP.get(category)
        if action is None:
            continue

        try:
            start = float(risk.get("start") or 0.0)
            end = float(risk.get("end") or 0.0)
        except (TypeError, ValueError):
            continue

        if end <= start:
            continue

        # pacing_decay only applies to last 25% of content
        if category == "pacing_decay":
            if last_quarter_start is None or start < last_quarter_start:
                continue
            action = "shorten_outro"

        confidence = _resolve_confidence(risk, category, pacing_ctx)
        max_trim = _resolve_max_trim(category, risk, end - start)
        reason = _build_reason(category, risk, pacing_ctx)

        candidate = TimingMutationCandidate(
            start=start,
            end=end,
            action=action,
            confidence=confidence,
            reason=reason,
            risk_category=category,
            max_trim_seconds=clamp_trim_seconds(max_trim),
            safe_to_apply=False,
        )
        candidates.append(candidate)

    logger.info(
        "ai_timing_candidates_analyzed candidates=%d",
        len(candidates),
    )
    return candidates[:_MAX_CANDIDATES]


def _resolve_confidence(risk: dict, category: str, pacing_ctx: dict) -> float:
    """Derive candidate confidence from risk severity and pacing signal."""
    base = 0.0
    try:
        severity = float(risk.get("severity") or risk.get("score") or 0.5)
        base = max(0.0, min(1.0, severity))
    except (TypeError, ValueError):
        base = 0.5

    # Boost confidence slightly for well-understood risk categories
    boosts: dict[str, float] = {
        "long_setup":    0.05,
        "silence_gap":   0.10,
        "pacing_decay":  0.05,
        "weak_hook":     0.0,
        "unclear_payoff": 0.0,
    }
    base += boosts.get(category, 0.0)

    # Pacing energy context: high energy → more confidence in tighten actions
    try:
        energy = float(pacing_ctx.get("energy_level") or 0.5)
        if category in {"long_setup", "pacing_decay"} and energy > 0.6:
            base += 0.05
    except (TypeError, ValueError):
        pass

    return round(max(0.0, min(1.0, base)), 4)


def _resolve_max_trim(category: str, risk: dict, duration: float) -> float:
    """Compute max_trim_seconds for this category, capped at _MAX_TRIM_SECONDS."""
    if category in _NO_TRIM_ACTIONS or category in {"weak_hook", "unclear_payoff"}:
        return 0.0

    # Use explicit field if present
    try:
        explicit = risk.get("suggested_trim") or risk.get("max_trim")
        if explicit is not None:
            return clamp_trim_seconds(float(explicit))
    except (TypeError, ValueError):
        pass

    # Conservative default trims per category
    defaults: dict[str, float] = {
        "long_setup":   1.0,
        "silence_gap":  0.8,
        "pacing_decay": 1.5,
    }
    raw = defaults.get(category, 0.5)
    # Never trim more than 25% of the region
    cap = duration * 0.25
    return clamp_trim_seconds(min(raw, cap))


def _build_reason(category: str, risk: dict, pacing_ctx: dict) -> str:
    """Build a human-readable reason string."""
    style = str(pacing_ctx.get("pacing_style") or "default")
    reasons: dict[str, str] = {
        "long_setup":    f"Retention risk: setup too long (pacing={style!r})",
        "silence_gap":   "Retention risk: silence gap detected",
        "pacing_decay":  "Retention risk: pacing decays in outro",
        "weak_hook":     "Retention risk: hook needs strengthening (hold, no trim)",
        "unclear_payoff": "Retention risk: unclear payoff (no trim advised)",
    }
    base = reasons.get(category, f"Retention risk: {category}")
    label = str(risk.get("label") or "")
    if label:
        return f"{base} — {label}"
    return base
