"""
ranking_bias.py — Safe clip output ranking bias recommendations. Phase 48.

Allows AI to softly influence output ranking priority.

Allowed ranking priority biases:
    retention    — favour high-retention outputs
    creator_fit  — favour creator-style-aligned outputs
    market_fit   — favour market-optimized outputs
    preset_fit   — favour preset-matched outputs
    quality      — favour highest quality-score outputs

Rules:
- Ranking ONLY — no rerender, no output mutation
- Preserves existing render outputs
- Deterministic scoring
- No executor override
- Deterministic
- Never raises
"""
from __future__ import annotations

import logging
from app.ai.influence.safety_gate import is_soft_or_strong, is_strong, TIER_SOFT

logger = logging.getLogger("app.ai.influence.ranking_bias")

_ALLOWED_PRIORITIES = frozenset({
    "retention", "creator_fit", "market_fit", "preset_fit", "quality"
})

# Direct pass-through from Phase 47 ranking_priority → Phase 48 bias
# (Phase 47 already produces safe canonical values)
_PRIORITY_PASSTHROUGH = frozenset({
    "creator_fit", "market_fit", "preset_fit", "quality",
})

# Additional biases layered on top in STRONG tier
_SECONDARY_BIAS: dict[str, str] = {
    "retention":    "hook_score",
    "creator_fit":  "style_match",
    "market_fit":   "platform_score",
    "preset_fit":   "evolution_score",
    "quality":      "overall_score",
}


def compute_ranking_bias(recommended_strategy: dict, gate: dict) -> dict:
    """Produce safe output ranking bias recommendations gated by confidence tier.

    Args:
        recommended_strategy: Phase 47 recommended_strategy dict.
        gate:                 Safety gate evaluation from safety_gate.evaluate_gate().

    Returns:
        {
            "available": bool,
            "ranking_priority_bias": str,
            "secondary_sort_bias": str,
            "influence_tier": str,
        }
    """
    try:
        return _compute(recommended_strategy, gate)
    except Exception as exc:
        logger.debug("ranking_bias_error: %s", exc)
        return _empty()


def _compute(strategy: dict, gate: dict) -> dict:
    if not is_soft_or_strong(gate):
        return _empty(tier=gate.get("tier", "blocked"))

    tier = str(gate.get("tier") or TIER_SOFT)
    raw_priority = str(strategy.get("ranking_priority") or "")

    # Only surface the priority if it's in the allowed set
    priority_bias = raw_priority if raw_priority in _ALLOWED_PRIORITIES else ""
    if not priority_bias:
        return _empty(tier=tier)

    # Secondary sort bias: STRONG tier only
    secondary = ""
    if is_strong(gate):
        secondary = _SECONDARY_BIAS.get(priority_bias, "")

    return {
        "available": True,
        "ranking_priority_bias": priority_bias,
        "secondary_sort_bias": secondary,
        "influence_tier": tier,
    }


def _empty(tier: str = "blocked") -> dict:
    return {
        "available": False,
        "ranking_priority_bias": "",
        "secondary_sort_bias": "",
        "influence_tier": tier,
    }
