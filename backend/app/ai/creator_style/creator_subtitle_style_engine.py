"""
creator_subtitle_style_engine.py — Phase 61B Creator Subtitle Style Promotion.

Reads Phase 61A creator_archetype_strategy.subtitle and produces a concrete
subtitle preset recommendation. This is consumed by Phase 59A
subtitle_promotion_engine as a lowest-priority fallback signal.

Design rules:
  - Never raises — returns fallback on any error.
  - Advisory metadata only — no payload mutation here.
  - Phase 59A priority order already ensures higher-priority signals win.
  - Confidence threshold adjusts per ai_execution_mode (Phase 60D).
  - mode=off → never activates (respects execution mode safety contract).
  - Deterministic: same inputs → same output.

Style bias → preset mapping:
  clean_pro       → clean_pro
  bold_impact     → viral_bold
  compact_dynamic → viral_bold
  minimal_clean   → clean_pro

Mode confidence thresholds:
  safe       ≥ 0.88
  balanced   ≥ 0.82
  aggressive ≥ 0.76
  off        → ∞ (never activates)

Public API:
    build_creator_subtitle_style(edit_plan, context=None) -> dict

Output shape (available):
    {
        "creator_subtitle_style_promotion": {
            "available":           true,
            "recommended_preset":  "clean_pro",
            "archetype_style_bias": "clean_pro",
            "keyword_emphasis":    "selective",
            "confidence":          0.8200,
            "mode":                "balanced",
            "creator_type":        "podcast",
            "reasoning":           ["Archetype style_bias 'clean_pro' maps to 'clean_pro' preset"]
        }
    }

Output shape (unavailable / fallback):
    {
        "creator_subtitle_style_promotion": {
            "available":           false,
            "recommended_preset":  null,
            "archetype_style_bias": null,
            "keyword_emphasis":    null,
            "confidence":          0.0,
            "mode":                "unknown",
            "creator_type":        "unknown",
            "reasoning":           [],
            "reason":              "no_archetype_strategy"
        }
    }

Safety contract:
    ❌ No payload mutation
    ❌ No execution promotion
    ❌ No Phase 59A override
    ✅ Advisory metadata only
    ✅ Reads edit_plan attributes; never raises
    ✅ All recommended_preset values in ALLOWED_PROMOTION_PRESETS
    ✅ Confidence clamped to [0.0, 1.0]
    ✅ Deterministic: same inputs → same output
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.creator_style")

# Phase 61A style_bias → Phase 59A allowed preset
_STYLE_TO_PRESET: dict[str, str] = {
    "clean_pro":       "clean_pro",
    "bold_impact":     "viral_bold",
    "compact_dynamic": "viral_bold",
    "minimal_clean":   "clean_pro",
}

# Mode-specific confidence thresholds — conservative to avoid low-signal promotions
_MODE_THRESHOLDS: dict[str, float] = {
    "off":        float("inf"),   # mode=off → never activates
    "safe":       0.88,
    "balanced":   0.82,
    "aggressive": 0.76,
}
_DEFAULT_THRESHOLD: float = 0.88  # safe-mode threshold as fallback


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_creator_subtitle_style(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build creator subtitle style promotion metadata.

    Returns:
        {"creator_subtitle_style_promotion": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build(edit_plan, job_id)
    except Exception as exc:
        logger.warning(
            "creator_subtitle_style_unexpected_error job_id=%s: %s", job_id, exc
        )
        return _fallback("promotion_error")


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, job_id: str) -> dict:
    if edit_plan is None:
        return _fallback("no_edit_plan")

    # ── Read Phase 61A archetype strategy ────────────────────────────────────
    archetype_strategy = _get_dict(edit_plan, "creator_archetype_strategy")
    if not archetype_strategy or not archetype_strategy.get("available"):
        return _fallback("no_archetype_strategy")

    archetype_subtitle = (archetype_strategy.get("strategy") or {}).get("subtitle") or {}
    style_bias = str(archetype_subtitle.get("style_bias") or "").strip().lower()
    archetype_conf = max(0.0, min(1.0, float(archetype_strategy.get("confidence") or 0.0)))

    if not style_bias:
        return _fallback("no_style_bias")

    # ── Map style_bias to allowed preset ────────────────────────────────────
    recommended_preset = _STYLE_TO_PRESET.get(style_bias)
    if not recommended_preset:
        return _fallback(f"unmapped_style_bias:{style_bias}", confidence=archetype_conf)

    # ── Mode gating (Phase 60D) ──────────────────────────────────────────────
    exec_mode_data = _get_dict(edit_plan, "ai_execution_mode")
    effective_mode = str(exec_mode_data.get("effective_mode") or "safe").strip().lower()

    if effective_mode == "off":
        return _fallback("mode_off", confidence=archetype_conf)

    threshold = _MODE_THRESHOLDS.get(effective_mode, _DEFAULT_THRESHOLD)

    if archetype_conf < threshold:
        logger.debug(
            "creator_subtitle_style_below_threshold job_id=%s conf=%.3f threshold=%.2f mode=%s",
            job_id, archetype_conf, threshold, effective_mode,
        )
        return _fallback(
            f"confidence_below_threshold",
            confidence=archetype_conf,
        )

    # ── Build output ─────────────────────────────────────────────────────────
    keyword_emphasis = str(archetype_subtitle.get("keyword_emphasis") or "").strip().lower() or None
    creator_type = str(archetype_strategy.get("creator_type") or "unknown")

    reasoning: list[str] = [
        f"Archetype style_bias {style_bias!r} maps to {recommended_preset!r} preset",
    ]
    if keyword_emphasis and keyword_emphasis != "none":
        reasoning.append(f"Archetype keyword emphasis: {keyword_emphasis!r}")

    logger.info(
        "creator_subtitle_style_recommended job_id=%s creator=%s preset=%r conf=%.3f mode=%s",
        job_id, creator_type, recommended_preset, archetype_conf, effective_mode,
    )

    return {
        "creator_subtitle_style_promotion": {
            "available":            True,
            "recommended_preset":   recommended_preset,
            "archetype_style_bias": style_bias,
            "keyword_emphasis":     keyword_emphasis,
            "confidence":           round(archetype_conf, 4),
            "mode":                 effective_mode,
            "creator_type":         creator_type,
            "reasoning":            reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_dict(edit_plan: Any, attr: str) -> dict:
    try:
        val = (
            edit_plan.get(attr) if isinstance(edit_plan, dict)
            else getattr(edit_plan, attr, None)
        )
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _fallback(reason: str, confidence: float = 0.0) -> dict:
    return {
        "creator_subtitle_style_promotion": {
            "available":            False,
            "recommended_preset":   None,
            "archetype_style_bias": None,
            "keyword_emphasis":     None,
            "confidence":           round(confidence, 4),
            "mode":                 "unknown",
            "creator_type":         "unknown",
            "reasoning":            [],
            "reason":               reason,
        }
    }
