"""
subtitle_bias.py — Safe subtitle influence recommendations. Phase 48.

Produces conservative subtitle style and density bias from Phase 47 strategy.

Allowed style presets (recommendation-only):
    viral_bold     — compact, high-energy visual style
    clean_pro      — clean, professional readable style
    boxed_caption  — structured caption box style

Density transitions (conservative, lighter-only):
    high   → "lighter"   (dense → medium)
    medium → "lighter"   (medium → light)
    low    → "unchanged" (already light — no further reduction)

Rules:
- Recommendation ONLY — never applied to render execution
- Preserves existing subtitle engine authority
- No subtitle timing rewrite
- No ASS mutation
- No subtitle text mutation
- No line-split rewrite
- No transcription mutation
- Deterministic
- Never raises
"""
from __future__ import annotations

import logging
from app.ai.influence.safety_gate import is_soft_or_strong, is_strong, TIER_SOFT

logger = logging.getLogger("app.ai.influence.subtitle_bias")

# Allowed Phase 48 subtitle style presets
_ALLOWED_STYLE_PRESETS = frozenset({"viral_bold", "clean_pro", "boxed_caption"})

# Map Phase 47 strategy subtitle_style → Phase 48 allowed preset
# Conservative: only map when there is a strong semantic match
_STYLE_MAP: dict[str, str] = {
    "compact":        "viral_bold",
    "readable":       "clean_pro",
    "clean_readable": "clean_pro",
    "medium_density": "boxed_caption",
    "clean_pro":      "clean_pro",
    "minimal":        "clean_pro",
}

# Density transitions: Phase 47 subtitle_density → Phase 48 density_bias
# Only "lighter" or "unchanged" — never denser
_DENSITY_MAP: dict[str, str] = {
    "high":   "lighter",    # dense → medium
    "medium": "lighter",    # medium → light
    "low":    "unchanged",  # already light
}


def compute_subtitle_bias(recommended_strategy: dict, gate: dict) -> dict:
    """Produce safe subtitle bias recommendations gated by confidence tier.

    Args:
        recommended_strategy: Phase 47 recommended_strategy dict.
        gate:                 Safety gate evaluation from safety_gate.evaluate_gate().

    Returns:
        {
            "available": bool,
            "subtitle_style_bias": str,    # preset name or "" if blocked/absent
            "subtitle_density_bias": str,  # "lighter" | "unchanged" | ""
            "influence_tier": str,
        }
    """
    try:
        return _compute(recommended_strategy, gate)
    except Exception as exc:
        logger.debug("subtitle_bias_error: %s", exc)
        return _empty()


def _compute(strategy: dict, gate: dict) -> dict:
    if not is_soft_or_strong(gate):
        return _empty(tier=gate.get("tier", "blocked"))

    tier = str(gate.get("tier") or TIER_SOFT)
    raw_style = str(strategy.get("subtitle_style") or "")
    raw_density = str(strategy.get("subtitle_density") or "")

    # Style bias: only in STRONG tier (more confident recommendation)
    style_bias = ""
    if is_strong(gate):
        style_bias = _STYLE_MAP.get(raw_style, "")

    # Density bias: available in both SOFT and STRONG tiers
    density_bias = _DENSITY_MAP.get(raw_density, "unchanged")

    # If neither bias is meaningful, return available=False
    if not style_bias and density_bias == "unchanged":
        return {
            "available": False,
            "subtitle_style_bias": "",
            "subtitle_density_bias": "unchanged",
            "influence_tier": tier,
        }

    return {
        "available": True,
        "subtitle_style_bias": style_bias,
        "subtitle_density_bias": density_bias,
        "influence_tier": tier,
    }


def _empty(tier: str = "blocked") -> dict:
    return {
        "available": False,
        "subtitle_style_bias": "",
        "subtitle_density_bias": "",
        "influence_tier": tier,
    }
