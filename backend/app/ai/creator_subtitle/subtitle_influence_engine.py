"""
subtitle_influence_engine.py — Creator Subtitle Safe Influence Engine. Phase 50C.

Translates Phase 50A AICameraPreference pack into six bounded subtitle tuning
recommendations (preset bias, density nudge, emphasis delta, line-count bias,
motion-style bias, mobile-readability nudge).

Public API:
    compute_subtitle_influence(subtitle_pref_pack) -> AISubtitleInfluencePack

Safety contract:
    ❌ No subtitle engine rewrite
    ❌ No ASS generation rewrite
    ❌ No subtitle timing rewrite
    ❌ No segmentation rewrite
    ❌ No FFmpeg mutation
    ❌ No executor override
    ❌ No autonomous execution
    ✅ All values clamped to absolute bounds
    ✅ Never raises
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.creator_subtitle.subtitle_influence_schema import (
    AISubtitleInfluencePack,
    ALLOWED_PRESET_BIAS, ALLOWED_MOTION_STYLE_BIAS,
    EMPHASIS_DELTA_MIN, EMPHASIS_DELTA_MAX,
    PRESET_BIAS_MIN, PRESET_BIAS_MAX,
    MOBILE_NUDGE_MIN, MOBILE_NUDGE_MAX,
    LINE_COUNT_BIAS_MIN, LINE_COUNT_BIAS_MAX,
    SOFT_TIER_MULTIPLIER,
)

logger = logging.getLogger("app.ai.creator_subtitle.influence")

# Confidence tier thresholds
_CONFIDENCE_HIGH   = 0.88
_CONFIDENCE_MEDIUM = 0.75

# Preset bias full-tier strength (before tier multiplier)
_PRESET_STRENGTH_FULL = 0.60

# Mobile nudge values (before tier multiplier)
_MOBILE_NUDGE_HIGH_READABILITY = 0.10
_MOBILE_NUDGE_MOBILE_SAFE_ONLY = 0.05


def compute_subtitle_influence(subtitle_pref_pack: Any) -> AISubtitleInfluencePack:
    """Compute bounded subtitle influence recommendations from a Phase 50A preference pack.

    Never raises.  Returns a zeroed-out pack with available=False when
    confidence is below threshold or input is missing/malformed.

    Args:
        subtitle_pref_pack: dict produced by infer_subtitle_preference(), or None.

    Returns:
        AISubtitleInfluencePack with safe bounded tuning recommendations.
    """
    try:
        return _compute_influence(subtitle_pref_pack)
    except Exception as exc:
        logger.debug("subtitle_influence_compute_error: %s", exc)
        return AISubtitleInfluencePack(
            available=False,
            confidence_tier="low",
            warnings=[f"compute_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Core influence computation
# ---------------------------------------------------------------------------

def _compute_influence(pack: Any) -> AISubtitleInfluencePack:
    if not isinstance(pack, dict) or not pack.get("available"):
        return AISubtitleInfluencePack(available=False, confidence_tier="low")

    pref = pack.get("subtitle_preference") or {}
    conf = _safe_float(pref.get("confidence"))

    # Confidence gate ─────────────────────────────────────────────────────────
    if conf < _CONFIDENCE_MEDIUM:
        return AISubtitleInfluencePack(
            available=False,
            confidence_tier="low",
            reasoning=[
                f"Confidence {conf:.2f} below threshold {_CONFIDENCE_MEDIUM} — no subtitle influence applied"
            ],
        )

    tier = "high" if conf >= _CONFIDENCE_HIGH else "medium"
    multiplier = 1.0 if tier == "high" else SOFT_TIER_MULTIPLIER

    # Extract preference dimensions
    style             = str(pref.get("style")              or "unknown")
    density           = str(pref.get("density")            or "unknown")
    keyword_emphasis  = str(pref.get("keyword_emphasis")   or "unknown")
    line_count        = _safe_int(pref.get("line_count"), default=2)
    motion_style      = str(pref.get("motion_style")       or "unknown")
    readability       = str(pref.get("readability_priority") or "unknown")
    mobile_safe       = bool(pref.get("mobile_safe", True))

    reasoning: list[str] = [f"Confidence tier={tier} (conf={conf:.2f})"]
    warnings:  list[str] = []

    # A. Preset bias ──────────────────────────────────────────────────────────
    preset_bias, preset_bias_strength = _compute_preset_bias(style, multiplier)
    if preset_bias not in ("unknown", "none") and preset_bias_strength > 0.0:
        reasoning.append(
            f"preset_bias={preset_bias!r} strength={preset_bias_strength:.2f} from style={style!r}"
        )

    # B. Density nudge — reduction only ───────────────────────────────────────
    density_nudge = _compute_density_nudge(density)
    if density_nudge == "reduce":
        reasoning.append(f"density_nudge=reduce (dense→medium for readability)")

    # C. Emphasis delta ───────────────────────────────────────────────────────
    emphasis_delta = _compute_emphasis_delta(keyword_emphasis, style, multiplier)
    if emphasis_delta != 0.0:
        reasoning.append(f"emphasis_delta={emphasis_delta:+.2f} from emphasis={keyword_emphasis!r}")

    # D. Line count bias ──────────────────────────────────────────────────────
    line_count_bias = _compute_line_count_bias(line_count)
    if line_count_bias != 0:
        direction = "fewer" if line_count_bias < 0 else "more"
        reasoning.append(f"line_count_bias={line_count_bias:+d} (prefer {direction} lines)")

    # E. Motion style bias ────────────────────────────────────────────────────
    motion_style_bias = _compute_motion_style_bias(motion_style)
    if motion_style_bias not in ("unknown", "none"):
        reasoning.append(f"motion_style_bias={motion_style_bias!r}")

    # F. Mobile readability nudge ─────────────────────────────────────────────
    mobile_readability_nudge = _compute_mobile_nudge(readability, mobile_safe, multiplier)
    if mobile_readability_nudge > 0.0:
        reasoning.append(
            f"mobile_readability_nudge={mobile_readability_nudge:.2f}"
            f" (readability={readability!r}, mobile_safe={mobile_safe})"
        )

    applied = any([
        preset_bias_strength > 0.0,
        density_nudge != "none",
        emphasis_delta != 0.0,
        line_count_bias != 0,
        motion_style_bias not in ("unknown", "none"),
        mobile_readability_nudge > 0.0,
    ])

    return AISubtitleInfluencePack(
        available=applied,
        confidence_tier=tier,
        preset_bias=preset_bias,
        preset_bias_strength=preset_bias_strength,
        density_nudge=density_nudge,
        emphasis_delta=emphasis_delta,
        line_count_bias=line_count_bias,
        motion_style_bias=motion_style_bias,
        mobile_readability_nudge=mobile_readability_nudge,
        reasoning=reasoning[:5],
        warnings=warnings[:5],
    )


# ---------------------------------------------------------------------------
# Dimension helpers
# ---------------------------------------------------------------------------

def _compute_preset_bias(style: str, multiplier: float) -> tuple[str, float]:
    """Map inferred style to a preset bias + strength. Always bounded."""
    if style in ("viral_bold", "clean_pro", "boxed_caption"):
        strength = _clamp(_PRESET_STRENGTH_FULL * multiplier, PRESET_BIAS_MIN, PRESET_BIAS_MAX)
        return style, strength
    return "unknown", 0.0


def _compute_density_nudge(density: str) -> str:
    """Density can only be reduced — never forced higher.

    dense → signal to reduce to medium
    medium / light / unknown → no change
    """
    if density == "dense":
        return "reduce"
    return "none"


def _compute_emphasis_delta(keyword_emphasis: str, style: str, multiplier: float) -> float:
    """Map keyword emphasis preference to a signed intensity delta.

    Raw delta magnitudes (before multiplier):
      none     → -0.20  (suppress emphasis)
      subtle   → -0.10  (soft de-emphasis)
      moderate → +0.10  (mild boost)
      strong   → +0.20  (stronger boost)
    Style-driven fallback when emphasis is unknown:
      viral_bold   → +0.15
      clean_pro    → -0.10
      boxed_caption → 0.0
    """
    raw_map = {
        "none":     -0.20,
        "subtle":   -0.10,
        "moderate": +0.10,
        "strong":   +0.20,
    }
    if keyword_emphasis in raw_map:
        raw = raw_map[keyword_emphasis]
    elif keyword_emphasis == "unknown":
        style_map = {"viral_bold": +0.15, "clean_pro": -0.10, "boxed_caption": 0.0}
        raw = style_map.get(style, 0.0)
    else:
        raw = 0.0

    return _clamp(raw * multiplier, EMPHASIS_DELTA_MIN, EMPHASIS_DELTA_MAX)


def _compute_line_count_bias(line_count: int) -> int:
    """Directional line-count bias within safe range [-1, +1].

    1 line → prefer fewer → -1
    2 lines → default, no change → 0
    ≥3 lines → prefer more → +1
    """
    if line_count <= 1:
        return max(LINE_COUNT_BIAS_MIN, -1)
    if line_count >= 3:
        return min(LINE_COUNT_BIAS_MAX, +1)
    return 0


def _compute_motion_style_bias(motion_style: str) -> str:
    """Direct mapping — only known motion styles are passed through."""
    if motion_style in ("clean", "bounce", "karaoke"):
        return motion_style
    return "unknown"


def _compute_mobile_nudge(readability: str, mobile_safe: bool, multiplier: float) -> float:
    """Compute mobile readability nudge.

    readability=high + mobile_safe=True  → strongest nudge (0.10)
    readability=high only                → moderate nudge (0.10)
    mobile_safe=True only                → soft nudge (0.05)
    otherwise                            → 0.0
    """
    if readability == "high" and mobile_safe:
        raw = _MOBILE_NUDGE_HIGH_READABILITY
    elif readability == "high":
        raw = _MOBILE_NUDGE_HIGH_READABILITY
    elif mobile_safe:
        raw = _MOBILE_NUDGE_MOBILE_SAFE_ONLY
    else:
        return 0.0
    return _clamp(raw * multiplier, MOBILE_NUDGE_MIN, MOBILE_NUDGE_MAX)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _safe_float(val: Any) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(val: Any, default: int = 0) -> int:
    try:
        return int(val or default)
    except (TypeError, ValueError):
        return default
