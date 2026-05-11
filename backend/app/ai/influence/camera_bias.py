"""
camera_bias.py — Safe camera motion influence recommendations. Phase 48.

Produces conservative camera motion bias from Phase 47 strategy.

Allowed influence (metadata-only):
    smoothing_preference  — how aggressively to smooth camera motion
    motion_stability_bias — stable vs. dynamic preference
    deadzone_preference   — motion deadzone preference

Blocked — strictly never:
    crop engine rewrite
    tracking logic rewrite
    motion algorithm replacement
    scene detection mutation

Rules:
- Recommendation ONLY — never applied to render execution
- Preserves motion crop engine authority
- Preserves scene tracking logic
- Preserves subject tracking logic
- Deterministic
- Never raises
"""
from __future__ import annotations

import logging
from app.ai.influence.safety_gate import is_soft_or_strong, is_strong, TIER_SOFT

logger = logging.getLogger("app.ai.influence.camera_bias")

# Map Phase 47 camera_motion → smoothing preference
# Conservative: only smooth or static — never force dynamic
_SMOOTHING_MAP: dict[str, str] = {
    "dynamic_subject": "standard",     # already dynamic — no additional push
    "smooth_subject":  "prefer_smooth",
    "smooth_social":   "prefer_smooth",
    "static":          "prefer_static",
    "cinematic":       "prefer_smooth",
}

# Map Phase 47 camera_motion → stability bias (in STRONG tier only)
_STABILITY_MAP: dict[str, str] = {
    "dynamic_subject": "dynamic_safe",
    "smooth_subject":  "stable",
    "smooth_social":   "stable",
    "static":          "locked",
    "cinematic":       "stable",
}

# Deadzone preference only when stability is stable or locked
_DEADZONE_MAP: dict[str, str] = {
    "stable": "moderate",
    "locked": "wide",
    "dynamic_safe": "narrow",
    "dynamic_safe": "narrow",
}


def compute_camera_bias(recommended_strategy: dict, gate: dict) -> dict:
    """Produce safe camera motion bias recommendations gated by confidence tier.

    Args:
        recommended_strategy: Phase 47 recommended_strategy dict.
        gate:                 Safety gate evaluation from safety_gate.evaluate_gate().

    Returns:
        {
            "available": bool,
            "camera_motion_bias": str,
            "smoothing_preference": str,
            "motion_stability_bias": str,
            "deadzone_preference": str,
            "influence_tier": str,
        }
    """
    try:
        return _compute(recommended_strategy, gate)
    except Exception as exc:
        logger.debug("camera_bias_error: %s", exc)
        return _empty()


def _compute(strategy: dict, gate: dict) -> dict:
    if not is_soft_or_strong(gate):
        return _empty(tier=gate.get("tier", "blocked"))

    tier = str(gate.get("tier") or TIER_SOFT)
    raw_motion = str(strategy.get("camera_motion") or "")

    # Smoothing preference: available in both SOFT and STRONG tiers
    smoothing = _SMOOTHING_MAP.get(raw_motion, "")

    # Stability bias and deadzone: STRONG tier only
    stability = ""
    deadzone = ""
    if is_strong(gate):
        stability = _STABILITY_MAP.get(raw_motion, "")
        deadzone = _DEADZONE_MAP.get(stability, "")

    # Camera motion bias = the raw Phase 47 value (safe to surface as a preference hint)
    camera_bias = raw_motion if raw_motion else ""

    if not smoothing and not camera_bias:
        return _empty(tier=tier)

    return {
        "available": True,
        "camera_motion_bias": camera_bias,
        "smoothing_preference": smoothing,
        "motion_stability_bias": stability,
        "deadzone_preference": deadzone,
        "influence_tier": tier,
    }


def _empty(tier: str = "blocked") -> dict:
    return {
        "available": False,
        "camera_motion_bias": "",
        "smoothing_preference": "",
        "motion_stability_bias": "",
        "deadzone_preference": "",
        "influence_tier": tier,
    }
