"""
market_weighting.py — Safe market-aware weight bias recommendations. Phase 48.

Produces conservative market-specific weight adjustments from aggregated signals.

Market profiles:
    US / viral_tiktok / youtube_shorts:
        hook_weight_bias ↑, retention_weight_bias ↑, energy_weight_bias ↑
    JP / calm markets:
        calm_pacing_bias ↑, subtitle_simplicity_bias ↑, story_weight_bias ↑
    Podcast:
        readability_bias ↑, creator_fit_bias ↑
    Educational:
        readability_bias ↑, clarity_bias ↑

Rules:
- Weighting ONLY — recommendation only
- No destructive optimization
- Confidence-aware
- Deterministic
- Never raises

All bias weights bounded [0.0, 0.20] — conservative ceiling enforced.
"""
from __future__ import annotations

import logging
from app.ai.influence.safety_gate import is_soft_or_strong, is_strong, TIER_SOFT

logger = logging.getLogger("app.ai.influence.market_weighting")

# Conservative maximum bias weight — never exceeded
_MAX_BIAS = 0.20
# Soft-tier bias multiplier (more conservative)
_SOFT_MULT = 0.6
# Strong-tier bias multiplier (still bounded)
_STRONG_MULT = 1.0

# Per-market weight bias profiles
# Weights are expressed as fractions of _MAX_BIAS (0.0–1.0 internally)
_MARKET_PROFILES: dict[str, dict[str, float]] = {
    "viral_tiktok": {
        "hook_weight_bias":       1.0,
        "retention_weight_bias":  0.9,
        "energy_weight_bias":     0.8,
        "readability_bias":       0.2,
        "story_weight_bias":      0.3,
        "calm_pacing_bias":       0.0,
    },
    "tiktok": {
        "hook_weight_bias":       1.0,
        "retention_weight_bias":  0.9,
        "energy_weight_bias":     0.8,
        "readability_bias":       0.2,
        "story_weight_bias":      0.3,
        "calm_pacing_bias":       0.0,
    },
    "youtube_shorts": {
        "hook_weight_bias":       0.7,
        "retention_weight_bias":  0.8,
        "energy_weight_bias":     0.6,
        "readability_bias":       0.5,
        "story_weight_bias":      0.4,
        "calm_pacing_bias":       0.1,
    },
    "facebook_reels": {
        "hook_weight_bias":       0.6,
        "retention_weight_bias":  0.7,
        "energy_weight_bias":     0.5,
        "readability_bias":       0.6,
        "story_weight_bias":      0.5,
        "calm_pacing_bias":       0.2,
    },
    "podcast": {
        "hook_weight_bias":       0.1,
        "retention_weight_bias":  0.4,
        "energy_weight_bias":     0.1,
        "readability_bias":       1.0,
        "story_weight_bias":      0.7,
        "calm_pacing_bias":       0.9,
    },
    "educational": {
        "hook_weight_bias":       0.2,
        "retention_weight_bias":  0.5,
        "energy_weight_bias":     0.2,
        "readability_bias":       1.0,
        "story_weight_bias":      0.8,
        "calm_pacing_bias":       0.7,
    },
}

_DEFAULT_PROFILE: dict[str, float] = {
    "hook_weight_bias":       0.5,
    "retention_weight_bias":  0.5,
    "energy_weight_bias":     0.3,
    "readability_bias":       0.5,
    "story_weight_bias":      0.4,
    "calm_pacing_bias":       0.3,
}


def compute_market_weights(aggregated_signals: dict, gate: dict) -> dict:
    """Produce market-aware weight bias recommendations gated by confidence tier.

    Args:
        aggregated_signals: Aggregated signals from Phase 47 signal_aggregation.
        gate:               Safety gate evaluation from safety_gate.evaluate_gate().

    Returns:
        {
            "available": bool,
            "target_market": str,
            "hook_weight_bias": float,
            "retention_weight_bias": float,
            "energy_weight_bias": float,
            "readability_bias": float,
            "story_weight_bias": float,
            "calm_pacing_bias": float,
            "influence_tier": str,
        }
    """
    try:
        return _compute(aggregated_signals, gate)
    except Exception as exc:
        logger.debug("market_weighting_error: %s", exc)
        return _empty()


def _compute(signals: dict, gate: dict) -> dict:
    if not is_soft_or_strong(gate):
        return _empty(tier=gate.get("tier", "blocked"))

    tier = str(gate.get("tier") or TIER_SOFT)
    mult = _STRONG_MULT if is_strong(gate) else _SOFT_MULT

    market_sig = signals.get("market_signal") or {}
    target_market = str(market_sig.get("target_market") or "").lower()

    if not target_market:
        return _empty(tier=tier)

    profile = _MARKET_PROFILES.get(target_market, _DEFAULT_PROFILE)

    # Apply multiplier and bound to [0.0, MAX_BIAS]
    biases = {
        key: round(min(_MAX_BIAS, float(val) * _MAX_BIAS * mult), 4)
        for key, val in profile.items()
    }

    # Filter out near-zero biases (< 1% of max) — cleaner output
    significant = {k: v for k, v in biases.items() if v >= 0.002}

    if not significant:
        return _empty(tier=tier)

    return {
        "available": True,
        "target_market": target_market,
        "influence_tier": tier,
        **significant,
    }


def _empty(tier: str = "blocked") -> dict:
    return {
        "available": False,
        "target_market": "",
        "influence_tier": tier,
    }
