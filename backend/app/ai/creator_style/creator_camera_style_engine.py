"""
creator_camera_style_engine.py — Phase 61C Creator Camera Style Promotion.

Reads Phase 61A creator_archetype_strategy.camera and produces a structured
camera bias recommendation. Consumed by Phase 59B camera_promotion_engine as
a lowest-priority fallback signal source.

Design rules:
  - Never raises — returns fallback on any error.
  - Advisory metadata only — no payload mutation here.
  - Phase 59B priority order ensures higher-priority signals (50B, 55E, 56) win.
  - Confidence threshold adjusts per ai_execution_mode (Phase 60D).
  - mode=off → never activates (respects execution mode safety contract).
  - Hard tuning bounds preserved: hold_delta ≤ 12, deadzone_delta ≤ 0.05.
  - Deterministic: same inputs → same output.

motion_energy → reframe_preference mapping:
  low         → None     (conservative — don't promote reframe change)
  low_medium  → subject  (stable subject tracking)
  medium      → subject
  medium_high → motion
  high        → motion

stability_priority → subject_hold label:
  high     → high   (→ subject_hold_delta +8 frames in advisory tuning)
  medium   → medium (→ subject_hold_delta +4 frames)
  standard → standard (no change)

Mode confidence thresholds:
  safe       ≥ 0.88
  balanced   ≥ 0.82
  aggressive ≥ 0.76
  off        → ∞ (never activates)

Public API:
    build_creator_camera_style(edit_plan, context=None) -> dict

Output shape (available):
    {
        "creator_camera_style_promotion": {
            "available":          true,
            "creator_type":       "podcast",
            "supported":          true,
            "bias": {
                "motion_energy":       "low",
                "stability_priority":  "high",
                "crop_aggressiveness": "low",
                "subject_hold":        "high",
                "jitter_sensitivity":  "high"
            },
            "reframe_preference": null,
            "confidence":         0.8200,
            "mode":               "balanced",
            "reasoning":          ["Podcast creator style favors stable framing and low camera aggressiveness"]
        }
    }

Output shape (unavailable / fallback):
    {
        "creator_camera_style_promotion": {
            "available":          false,
            "creator_type":       "unknown",
            "supported":          false,
            "bias":               {},
            "reframe_preference": null,
            "confidence":         0.0,
            "mode":               "unknown",
            "reasoning":          [],
            "reason":             "no_archetype_strategy"
        }
    }

Safety contract:
    ❌ No payload mutation
    ❌ No motion_crop rewrite
    ❌ No tracking rewrite
    ❌ No scene detection rewrite
    ❌ No execution promotion
    ❌ No Phase 59B override
    ✅ Advisory metadata only
    ✅ Reads edit_plan attributes; never raises
    ✅ reframe_preference is either None or in ALLOWED_PROMOTION_MODES
    ✅ Confidence clamped to [0.0, 1.0]
    ✅ mode=off → available=False
    ✅ Deterministic: same inputs → same output
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.creator_style")

# Allowed reframe modes Phase 59B promotes to
_ALLOWED_REFRAME_MODES: frozenset[str] = frozenset({"motion", "subject", "face"})

# motion_energy → reframe_mode preference (conservative mapping)
_MOTION_ENERGY_TO_REFRAME: dict[str, Optional[str]] = {
    "low":         None,       # conservative — don't suggest reframe change
    "low_medium":  "subject",  # stable subject tracking
    "medium":      "subject",
    "medium_high": "motion",
    "high":        "motion",
}

# stability_priority → subject_hold advisory label
_STABILITY_TO_HOLD: dict[str, str] = {
    "high":     "high",
    "medium":   "medium",
    "standard": "standard",
}

# Hard-bounded advisory subject_hold deltas per stability level (frames)
_STABILITY_HOLD_DELTA: dict[str, int] = {
    "high":   8,   # within _MAX_SUBJECT_HOLD_DELTA=12 in Phase 59B
    "medium": 4,
}

# Mode-specific confidence thresholds — conservative to avoid noise
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

def build_creator_camera_style(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build creator camera style promotion metadata.

    Returns:
        {"creator_camera_style_promotion": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build(edit_plan, job_id)
    except Exception as exc:
        logger.warning(
            "creator_camera_style_unexpected_error job_id=%s: %s", job_id, exc
        )
        return _fallback("promotion_error")


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, job_id: str) -> dict:
    if edit_plan is None:
        return _fallback("no_edit_plan")

    # ── Read Phase 61A archetype strategy camera domain ───────────────────────
    archetype_strategy = _get_dict(edit_plan, "creator_archetype_strategy")
    if not archetype_strategy or not archetype_strategy.get("available"):
        return _fallback("no_archetype_strategy")

    archetype_camera = (archetype_strategy.get("strategy") or {}).get("camera") or {}
    if not archetype_camera:
        return _fallback("no_camera_strategy")

    archetype_conf = max(0.0, min(1.0, float(archetype_strategy.get("confidence") or 0.0)))
    creator_type = str(archetype_strategy.get("creator_type") or "unknown")

    # ── Mode gating (Phase 60D) ───────────────────────────────────────────────
    exec_mode_data = _get_dict(edit_plan, "ai_execution_mode")
    effective_mode = str(exec_mode_data.get("effective_mode") or "safe").strip().lower()

    if effective_mode == "off":
        return _fallback("mode_off", confidence=archetype_conf)

    threshold = _MODE_THRESHOLDS.get(effective_mode, _DEFAULT_THRESHOLD)

    if archetype_conf < threshold:
        logger.debug(
            "creator_camera_style_below_threshold job_id=%s conf=%.3f threshold=%.2f mode=%s",
            job_id, archetype_conf, threshold, effective_mode,
        )
        return _fallback("confidence_below_threshold", confidence=archetype_conf)

    # ── Build camera bias ─────────────────────────────────────────────────────
    motion_energy       = str(archetype_camera.get("motion_energy") or "").strip().lower()
    stability_priority  = str(archetype_camera.get("stability_priority") or "").strip().lower()
    crop_aggressiveness = str(archetype_camera.get("crop_aggressiveness") or "").strip().lower()
    jitter_sensitivity  = str(archetype_camera.get("jitter_sensitivity") or "").strip().lower()

    # Map motion_energy → reframe_preference
    reframe_preference: Optional[str] = _MOTION_ENERGY_TO_REFRAME.get(motion_energy)
    if reframe_preference and reframe_preference not in _ALLOWED_REFRAME_MODES:
        reframe_preference = None   # safety guard

    # Map stability_priority → subject_hold label
    subject_hold = _STABILITY_TO_HOLD.get(stability_priority, "standard")

    bias: dict = {}
    if motion_energy:
        bias["motion_energy"] = motion_energy
    if stability_priority:
        bias["stability_priority"] = stability_priority
    if crop_aggressiveness:
        bias["crop_aggressiveness"] = crop_aggressiveness
    if subject_hold:
        bias["subject_hold"] = subject_hold
    if jitter_sensitivity:
        bias["jitter_sensitivity"] = jitter_sensitivity

    # ── Reasoning ─────────────────────────────────────────────────────────────
    arch_reasoning = archetype_strategy.get("reasoning") or []
    reasoning: list[str] = (
        list(arch_reasoning[:1])
        if arch_reasoning
        else [f"Creator archetype {creator_type!r} camera strategy applied"]
    )

    logger.info(
        "creator_camera_style_built job_id=%s creator=%s reframe_pref=%r conf=%.3f mode=%s",
        job_id, creator_type, reframe_preference, archetype_conf, effective_mode,
    )

    return {
        "creator_camera_style_promotion": {
            "available":          True,
            "creator_type":       creator_type,
            "supported":          True,
            "bias":               bias,
            "reframe_preference": reframe_preference,
            "confidence":         round(archetype_conf, 4),
            "mode":               effective_mode,
            "reasoning":          reasoning,
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
        "creator_camera_style_promotion": {
            "available":          False,
            "creator_type":       "unknown",
            "supported":          False,
            "bias":               {},
            "reframe_preference": None,
            "confidence":         round(confidence, 4),
            "mode":               "unknown",
            "reasoning":          [],
            "reason":             reason,
        }
    }
