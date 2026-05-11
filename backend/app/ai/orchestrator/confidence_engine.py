"""
confidence_engine.py — Per-signal weighted confidence scoring. Phase 47.

Computes a conservative confidence score per signal category.

Rules:
- Conservative weighting (scale factors < 1.0 for derivative signals)
- Low confidence = weaker recommendation (never forced)
- High confidence = stronger recommendation
- Never raises
- No render execution, no mutation
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.orchestrator.confidence_engine")

# Conservative scale factors per signal (bounded [0.0, 1.0] after scaling)
_CREATOR_SCALE = 1.00   # style_confidence is already normalized
_MARKET_SCALE = 1.00    # market_confidence already normalized
_QUALITY_SCALE = 0.80   # quality score 0–100, dampen derivative uncertainty
_PRESET_SCALE = 0.70    # preset score is compound — more conservative
_FEEDBACK_SCALE = 0.90  # direct creator behavior, high reliability
_RETRIEVAL_SCALE = 1.00 # retrieval_confidence already normalized


def compute_signal_confidence(aggregated_signals: dict) -> dict:
    """Compute per-signal confidence scores from aggregated signals.

    Args:
        aggregated_signals: Output of signal_aggregation.aggregate_signals()

    Returns:
        {
            "creator_confidence": float,
            "market_confidence": float,
            "quality_confidence": float,
            "preset_confidence": float,
            "feedback_confidence": float,
            "retrieval_confidence": float,
            "aggregate_confidence": float,
        }
    """
    try:
        return _compute(aggregated_signals)
    except Exception as exc:
        logger.debug("confidence_engine_error: %s", exc)
        return _zero_confidence()


def _compute(signals: dict) -> dict:
    creator = _score_creator(signals.get("creator_signal") or {})
    market = _score_market(signals.get("market_signal") or {})
    quality = _score_quality(signals.get("quality_signal") or {})
    preset = _score_preset(signals.get("preset_signal") or {})
    feedback = _score_feedback(signals.get("feedback_signal") or {})
    retrieval = _score_retrieval(signals.get("retrieval_signal") or {})

    active = [s for s in (creator, market, quality, preset, feedback, retrieval) if s > 0.0]
    aggregate = round(sum(active) / max(len(active), 1), 4) if active else 0.0

    return {
        "creator_confidence": round(creator, 4),
        "market_confidence": round(market, 4),
        "quality_confidence": round(quality, 4),
        "preset_confidence": round(preset, 4),
        "feedback_confidence": round(feedback, 4),
        "retrieval_confidence": round(retrieval, 4),
        "aggregate_confidence": aggregate,
    }


def _score_creator(signal: dict) -> float:
    if not signal.get("available"):
        return 0.0
    try:
        base = float(signal.get("style_confidence") or 0.0)
        return _clamp(base * _CREATOR_SCALE)
    except Exception:
        return 0.0


def _score_market(signal: dict) -> float:
    if not signal.get("available"):
        return 0.0
    try:
        base = float(signal.get("market_confidence") or 0.0)
        return _clamp(base * _MARKET_SCALE)
    except Exception:
        return 0.0


def _score_quality(signal: dict) -> float:
    if not signal.get("available"):
        return 0.0
    try:
        # Quality score is 0–100; normalize then scale
        raw = float(signal.get("best_overall_score") or 0.0)
        return _clamp((raw / 100.0) * _QUALITY_SCALE)
    except Exception:
        return 0.0


def _score_preset(signal: dict) -> float:
    if not signal.get("available"):
        return 0.0
    try:
        raw = float(signal.get("best_preset_score") or 0.0)
        return _clamp((raw / 100.0) * _PRESET_SCALE)
    except Exception:
        return 0.0


def _score_feedback(signal: dict) -> float:
    if not signal.get("available"):
        return 0.0
    try:
        # 10+ exports → full confidence; scales linearly below
        exports = int(signal.get("total_exports") or 0)
        base = min(exports / 10.0, 1.0)
        return _clamp(base * _FEEDBACK_SCALE)
    except Exception:
        return 0.0


def _score_retrieval(signal: dict) -> float:
    if not signal.get("available"):
        return 0.0
    try:
        return _clamp(float(signal.get("retrieval_confidence") or 0.0) * _RETRIEVAL_SCALE)
    except Exception:
        return 0.0


def _zero_confidence() -> dict:
    return {
        "creator_confidence": 0.0,
        "market_confidence": 0.0,
        "quality_confidence": 0.0,
        "preset_confidence": 0.0,
        "feedback_confidence": 0.0,
        "retrieval_confidence": 0.0,
        "aggregate_confidence": 0.0,
    }


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except Exception:
        return lo
