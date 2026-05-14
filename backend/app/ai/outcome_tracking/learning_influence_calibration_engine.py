"""
learning_influence_calibration_engine.py — Phase 62D Learning-Aware Influence Calibration.

Learning-aware calibration only. Uses creator preference reinforcement (62B) and
render success patterns (62C) to calibrate existing bounded AI influence more
intelligently.

NO autonomous retraining.  NO cloud learning.  NO fine-tuning.
NO unbounded optimization.  NO rerender.  NO new render knobs.
Calibration may ONLY adjust confidence deltas slightly, supply support/block
reasoning, and inform future safe influence decisions.

Inputs (existing metadata only — no new render):
    render_outcome_tracking         (Phase 62A) — outcome, quality, ai_execution
    creator_preference_reinforcement (Phase 62B) — reinforcement signals
    render_success_patterns         (Phase 62C) — pattern classification + signals
    creator_render_strategy         (Phase 61D) — strategy signals
    subtitle_execution_promotion    (Phase 59A/61B) — for user override check
    camera_execution_promotion      (Phase 59B/61C) — for user override check
    ai_execution_mode               (Phase 60D) — resolved execution mode
    ai_execution_metrics            (Phase 60A) — execution metadata
    ai_ab_evaluation                (Phase 60B) — A/B result
    creator_benchmark_summary       (Phase 60C) — benchmark status
    render_quality_v2               (Phase 52D) — quality scores
    platform_quality_feedback       (Phase 57)  — platform feedback signals
    quality_gated_influence         (Phase 59D) — quality gate result

Public API:
    build_learning_influence_calibration(edit_plan, context=None) -> dict

Output shape (available):
    {
        "learning_influence_calibration": {
            "available":    true,
            "creator_type": "podcast",
            "platform":     "tiktok",
            "execution_mode": "balanced",
            "calibration": {
                "subtitle": {
                    "confidence_delta": 0.03,
                    "action":           "support_clean_compact_subtitles",
                    "reason":           "clean subtitle pattern improved podcast TikTok renders"
                },
                "camera": {
                    "confidence_delta": 0.04,
                    "action":           "support_stable_camera",
                    "reason":           "stable framing pattern showed strong outcomes"
                },
                "segment": {
                    "confidence_delta": 0.02,
                    "action":           "support_retention_creator_fit_ranking",
                    "reason":           "retention creator-fit ranking correlated with improved outcomes"
                }
            },
            "negative_calibration": [],
            "user_override_excluded": [],
            "confidence": 0.82,
            "reasoning": [
                "Learning signals support clean subtitles and stable camera for this creator/platform."
            ]
        }
    }

Output shape (fallback):
    {
        "learning_influence_calibration": {
            "available":          false,
            "calibration":        {},
            "negative_calibration": [],
            "user_override_excluded": [],
            "confidence":         0.0,
            "reasoning":          []
        }
    }

Positive calibration rules:
    strong_pattern  → subtitle +0.03, camera +0.04, segment +0.02
    moderate_pattern → subtitle +0.02, camera +0.02, segment +0.01
    weak_pattern    → no positive calibration
    conflicting_pattern → only negative calibration applied

Negative calibration rules:
    conflicting_pattern → camera -0.03, subtitle -0.02
    CPR negative signals → domain negative delta (capped)

Confidence delta bounds (strict):
    max positive per domain:  +0.04
    max negative per domain:  -0.04
    total absolute cap:        0.10

Execution mode behaviour:
    off:        calibration={}, metadata only, reason included
    safe:       positive ×0.5, negative ×1.0 (can block risky)
    balanced:   positive ×1.0, negative ×1.0
    aggressive: positive ×1.2 (still capped at 0.04), negative ×0.8

User override exclusion:
    If subtitle_execution_promotion.reason contains "user_override"
        → subtitle excluded, noted in user_override_excluded
    If camera_execution_promotion.reason contains "user_override"
        → camera excluded, noted in user_override_excluded

Gate (all required):
    render_outcome_tracking.available == True
    creator_type != "unknown"
    at least one quality score > 0
    render_success_patterns.available == True  (patterns list non-empty)

Safety contract:
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ❌ No autonomous retraining
    ❌ No cloud learning / fine-tuning
    ❌ No external persistence
    ❌ No influence mutation
    ✅ Calibration metadata only — advisory to existing bounded influence
    ✅ Deterministic: same inputs → same output
    ✅ Returns fallback on any error
    ✅ Confidence deltas bounded per domain and total
    ✅ User overrides respected
    ✅ Never claims strong calibration without pattern evidence
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.outcome_tracking")

# ---------------------------------------------------------------------------
# Bounds (strict, tested)
# ---------------------------------------------------------------------------
_MAX_POSITIVE_DELTA: float = 0.04
_MAX_NEGATIVE_DELTA: float = 0.04   # stored positive, applied as negative
_MAX_TOTAL_DELTA:    float = 0.10

# ---------------------------------------------------------------------------
# Base deltas per classification
# ---------------------------------------------------------------------------
_BASE_SUBTITLE: dict[str, float] = {
    "strong_pattern":   0.03,
    "moderate_pattern": 0.02,
}
_BASE_CAMERA: dict[str, float] = {
    "strong_pattern":   0.04,
    "moderate_pattern": 0.02,
}
_BASE_SEGMENT: dict[str, float] = {
    "strong_pattern":   0.02,
    "moderate_pattern": 0.01,
}

# ---------------------------------------------------------------------------
# Execution mode multipliers
# ---------------------------------------------------------------------------
_MODE_POS_SCALE: dict[str, float] = {
    "off":        0.0,
    "safe":       0.5,
    "balanced":   1.0,
    "aggressive": 1.2,
}
_MODE_NEG_SCALE: dict[str, float] = {
    "off":        0.0,
    "safe":       1.0,
    "balanced":   1.0,
    "aggressive": 0.8,
}

# ---------------------------------------------------------------------------
# Confidence multipliers per classification
# ---------------------------------------------------------------------------
_CLASS_CONF_SCALE: dict[str, float] = {
    "strong_pattern":     1.0,
    "moderate_pattern":   0.8,
    "weak_pattern":       0.0,
    "conflicting_pattern": 0.5,
}

_MAX_REASONING = 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_learning_influence_calibration(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build learning-aware influence calibration metadata.

    Returns:
        {"learning_influence_calibration": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build(edit_plan, job_id)
    except Exception as exc:
        logger.warning(
            "learning_influence_calibration_unexpected_error job_id=%s: %s", job_id, exc
        )
        return _fallback()


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, job_id: str) -> dict:
    if edit_plan is None:
        return _fallback()

    # ── Read all inputs ────────────────────────────────────────────────────
    rot       = _get_dict(edit_plan, "render_outcome_tracking")
    cpr       = _get_dict(edit_plan, "creator_preference_reinforcement")
    rsp       = _get_dict(edit_plan, "render_success_patterns")
    mode_data = _get_dict(edit_plan, "ai_execution_mode")
    sub_promo = _get_dict(edit_plan, "subtitle_execution_promotion")
    cam_promo = _get_dict(edit_plan, "camera_execution_promotion")

    # ── Gate check ─────────────────────────────────────────────────────────
    rot_available = bool(rot.get("available"))
    creator_type  = str(rot.get("creator_type") or "unknown").lower()
    quality       = rot.get("quality") or {}

    rsp_patterns  = rsp.get("patterns") or []
    rsp_available = bool(rsp.get("available")) and len(rsp_patterns) > 0

    if not rot_available or creator_type == "unknown":
        return _fallback()
    if not any(quality.get(k, 0) > 0 for k in ("subtitle", "camera", "hook", "overall")):
        return _fallback()
    if not rsp_available:
        return _fallback()

    # ── Core signal extraction ─────────────────────────────────────────────
    creator_prof = _get_dict(edit_plan, "creator_preference_profile")
    platform = str(creator_prof.get("platform") or "unknown").lower()

    # Execution mode from Phase 60D
    raw_mode = (
        mode_data.get("mode")
        or mode_data.get("effective_mode")
        or "balanced"
    )
    execution_mode = str(raw_mode).lower()
    if execution_mode not in ("off", "safe", "balanced", "aggressive"):
        execution_mode = "balanced"

    # Pattern signals
    pattern            = rsp_patterns[0]
    classification     = str(pattern.get("classification") or "weak_pattern")
    signals            = pattern.get("signals") or {}
    pattern_confidence = _clamp_f(pattern.get("confidence"))

    # Reinforcement signals
    cpr_reinforced = cpr.get("reinforced_preferences") or {}
    cpr_negative   = list(cpr.get("negative_signals") or [])
    cpr_confidence = _clamp_f(cpr.get("confidence"))

    # ── User override detection ────────────────────────────────────────────
    sub_override = "user_override" in str(sub_promo.get("reason") or "").lower()
    cam_override = "user_override" in str(cam_promo.get("reason") or "").lower()

    # ── Mode "off" — metadata only, no execution calibration ──────────────
    if execution_mode == "off":
        reasoning: list = [
            "Execution mode 'off' — calibration computed but not applied to execution influence.",
        ]
        if classification != "weak_pattern":
            reasoning.append(
                f"Pattern classification: {classification} for {creator_type}"
                + (f" on {platform}." if platform != "unknown" else ".")
            )
        if sub_override:
            reasoning.append("Subtitle domain excluded — user override detected.")
        if cam_override:
            reasoning.append("Camera domain excluded — user override detected.")

        uo = (["subtitle"] if sub_override else []) + (["camera"] if cam_override else [])
        return {
            "learning_influence_calibration": {
                "available":           True,
                "creator_type":        creator_type,
                "platform":            platform,
                "execution_mode":      execution_mode,
                "calibration":         {},
                "negative_calibration": [],
                "user_override_excluded": uo,
                "confidence":          round(pattern_confidence * 0.5, 4),
                "reasoning":           reasoning[:_MAX_REASONING],
            }
        }

    # ── Positive calibration ───────────────────────────────────────────────
    pos_scale = _MODE_POS_SCALE.get(execution_mode, 1.0)
    calibration: dict = {}

    if classification in _BASE_SUBTITLE:
        # Subtitle
        if not sub_override:
            sub_base  = _BASE_SUBTITLE[classification]
            sub_delta = round(min(_MAX_POSITIVE_DELTA, sub_base * pos_scale), 4)
            if sub_delta > 0.0:
                calibration["subtitle"] = {
                    "confidence_delta": sub_delta,
                    "action":           _subtitle_action(signals),
                    "reason":           _subtitle_reason(classification, creator_type, platform, signals),
                }

        # Camera
        if not cam_override:
            cam_base  = _BASE_CAMERA[classification]
            cam_delta = round(min(_MAX_POSITIVE_DELTA, cam_base * pos_scale), 4)
            if cam_delta > 0.0:
                calibration["camera"] = {
                    "confidence_delta": cam_delta,
                    "action":           _camera_action(signals),
                    "reason":           _camera_reason(classification, creator_type, platform, signals),
                }

        # Segment (not promotable by user override — always eligible)
        seg_base  = _BASE_SEGMENT[classification]
        seg_delta = round(min(_MAX_POSITIVE_DELTA, seg_base * pos_scale), 4)
        if seg_delta > 0.0:
            calibration["segment"] = {
                "confidence_delta": seg_delta,
                "action":           "support_retention_creator_fit_ranking",
                "reason":           (
                    f"Retention creator-fit ranking correlated with "
                    f"{classification.replace('_', ' ')} outcomes for {creator_type}."
                ),
            }

    # ── Negative calibration ───────────────────────────────────────────────
    neg_scale = _MODE_NEG_SCALE.get(execution_mode, 1.0)
    negative_calibration: list = []

    if classification == "conflicting_pattern":
        if not cam_override:
            cam_neg = round(min(_MAX_NEGATIVE_DELTA, 0.03 * neg_scale), 4)
            if cam_neg > 0.0:
                negative_calibration.append({
                    "domain":           "camera",
                    "confidence_delta": -cam_neg,
                    "action":           "soften_aggressive_camera",
                    "reason":           (
                        f"Conflicting pattern for {creator_type}"
                        + (f" on {platform}" if platform != "unknown" else "")
                        + " — softening camera influence confidence."
                    ),
                })
        if not sub_override:
            sub_neg = round(min(_MAX_NEGATIVE_DELTA, 0.02 * neg_scale), 4)
            if sub_neg > 0.0:
                negative_calibration.append({
                    "domain":           "subtitle",
                    "confidence_delta": -sub_neg,
                    "action":           "soften_subtitle_emphasis",
                    "reason":           (
                        f"Conflicting signals for {creator_type} — "
                        "reducing subtitle influence for caution."
                    ),
                })

    # CPR negative signals → additional negative calibration entries
    for neg_sig in cpr_negative[:3]:
        domain = str(neg_sig.get("domain") or "")
        if domain not in ("subtitle", "camera", "segment", "ranking"):
            continue
        if domain == "subtitle" and sub_override:
            continue
        if domain == "camera" and cam_override:
            continue
        # Skip if we already have a negative entry for this domain
        if any(e["domain"] == domain for e in negative_calibration):
            continue
        raw_delta = _clamp_f(neg_sig.get("confidence_delta"))
        if raw_delta <= 0.0:
            continue
        neg_delta = round(min(_MAX_NEGATIVE_DELTA, abs(raw_delta) * neg_scale), 4)
        if neg_delta > 0.0:
            negative_calibration.append({
                "domain":           domain,
                "confidence_delta": -neg_delta,
                "action":           _neg_action_for_domain(domain),
                "reason":           str(
                    neg_sig.get("signal") or f"Negative signal in {domain} domain."
                ),
            })

    # ── Apply total absolute delta cap ─────────────────────────────────────
    calibration, negative_calibration = _apply_total_cap(calibration, negative_calibration)

    # ── Confidence ─────────────────────────────────────────────────────────
    confidence = _compute_confidence(
        pattern_confidence, cpr_confidence, execution_mode, classification
    )

    # ── Reasoning ─────────────────────────────────────────────────────────
    user_override_excluded = (
        (["subtitle"] if sub_override else []) +
        (["camera"] if cam_override else [])
    )
    reasoning_lines = _build_reasoning(
        classification, creator_type, platform, execution_mode,
        calibration, negative_calibration, sub_override, cam_override,
    )

    logger.info(
        "learning_influence_calibration_built job_id=%s creator=%s platform=%s "
        "mode=%s classification=%s pos_domains=%d neg_entries=%d confidence=%.3f",
        job_id, creator_type, platform,
        execution_mode, classification,
        len(calibration), len(negative_calibration), confidence,
    )

    return {
        "learning_influence_calibration": {
            "available":              True,
            "creator_type":           creator_type,
            "platform":               platform,
            "execution_mode":         execution_mode,
            "calibration":            calibration,
            "negative_calibration":   negative_calibration,
            "user_override_excluded": user_override_excluded,
            "confidence":             confidence,
            "reasoning":              reasoning_lines,
        }
    }


# ---------------------------------------------------------------------------
# Total delta cap
# ---------------------------------------------------------------------------

def _apply_total_cap(
    calibration: dict,
    negative_calibration: list,
) -> tuple[dict, list]:
    """Proportionally scale all deltas if total absolute sum exceeds 0.10."""
    pos_total = sum(v["confidence_delta"] for v in calibration.values())
    neg_total = sum(abs(e["confidence_delta"]) for e in negative_calibration)
    total_abs = pos_total + neg_total

    if total_abs <= _MAX_TOTAL_DELTA or total_abs == 0.0:
        return calibration, negative_calibration

    scale = _MAX_TOTAL_DELTA / total_abs

    scaled_cal = {}
    for domain, entry in calibration.items():
        scaled_cal[domain] = dict(entry)
        scaled_cal[domain]["confidence_delta"] = round(entry["confidence_delta"] * scale, 4)

    scaled_neg = []
    for entry in negative_calibration:
        new_entry = dict(entry)
        new_entry["confidence_delta"] = round(entry["confidence_delta"] * scale, 4)
        scaled_neg.append(new_entry)

    return scaled_cal, scaled_neg


# ---------------------------------------------------------------------------
# Confidence computation
# ---------------------------------------------------------------------------

def _compute_confidence(
    pattern_confidence: float,
    cpr_confidence: float,
    execution_mode: str,
    classification: str,
) -> float:
    """Blend pattern + CPR confidence, scale by classification and mode."""
    class_scale = _CLASS_CONF_SCALE.get(classification, 0.0)
    if class_scale == 0.0:
        return 0.0

    blended = pattern_confidence * 0.6 + cpr_confidence * 0.4
    mode_scale = {"safe": 0.9, "aggressive": 1.0}.get(execution_mode, 1.0)
    raw = blended * class_scale * mode_scale
    return round(max(0.0, min(1.0, raw)), 4)


# ---------------------------------------------------------------------------
# Action labels
# ---------------------------------------------------------------------------

def _subtitle_action(signals: dict) -> str:
    style = str(signals.get("subtitle_style") or "").lower()
    if any(k in style for k in ("clean", "compact", "minimal")):
        return "support_clean_compact_subtitles"
    if any(k in style for k in ("bold", "emphasis", "impact")):
        return "support_emphasis_subtitles"
    return "support_subtitle_influence"


def _camera_action(signals: dict) -> str:
    cam_style = str(signals.get("camera_style") or "").lower()
    stability = str(signals.get("camera_stability") or "").lower()
    if "stable" in cam_style or stability == "high":
        return "support_stable_camera"
    if "dynamic" in cam_style:
        return "support_dynamic_camera"
    return "support_camera_influence"


def _neg_action_for_domain(domain: str) -> str:
    return {
        "subtitle": "soften_subtitle_emphasis",
        "camera":   "soften_aggressive_camera",
        "segment":  "reduce_segment_ranking_confidence",
        "ranking":  "reduce_segment_ranking_confidence",
    }.get(domain, "reduce_domain_confidence")


# ---------------------------------------------------------------------------
# Reason text builders
# ---------------------------------------------------------------------------

def _subtitle_reason(
    classification: str,
    creator_type: str,
    platform: str,
    signals: dict,
) -> str:
    style = signals.get("subtitle_style") or "current"
    plat  = f" {platform}" if platform != "unknown" else ""
    if classification == "strong_pattern":
        return (
            f"{style} subtitle pattern improved {creator_type}{plat} renders — "
            "supporting clean subtitle influence."
        )
    return (
        f"{style} subtitle style showed improvement for {creator_type}{plat}."
    )


def _camera_reason(
    classification: str,
    creator_type: str,
    platform: str,
    signals: dict,
) -> str:
    cam_style = signals.get("camera_style") or signals.get("camera_stability") or "current"
    plat      = f" {platform}" if platform != "unknown" else ""
    if classification == "strong_pattern":
        return (
            f"{cam_style} framing pattern showed strong outcomes for {creator_type}{plat} — "
            "supporting stable camera influence."
        )
    return (
        f"{cam_style} camera settings showed improvement for {creator_type}{plat}."
    )


# ---------------------------------------------------------------------------
# Overall reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    classification: str,
    creator_type: str,
    platform: str,
    execution_mode: str,
    calibration: dict,
    negative_calibration: list,
    sub_override: bool,
    cam_override: bool,
) -> list:
    lines: list = []
    plat_str = f" on {platform}" if platform and platform != "unknown" else ""

    if classification == "strong_pattern":
        domains = list(calibration.keys())
        dom_str = " and ".join(domains) if domains else "available"
        lines.append(
            f"Learning signals support {dom_str} influence for {creator_type}{plat_str}."
        )
    elif classification == "moderate_pattern":
        lines.append(
            f"Moderate pattern for {creator_type}{plat_str} — "
            "conservative positive calibration applied."
        )
    elif classification == "conflicting_pattern":
        lines.append(
            f"Conflicting outcome signals for {creator_type}{plat_str} — "
            "only negative calibration applied."
        )
    else:
        lines.append(
            f"Insufficient pattern evidence for {creator_type}{plat_str} — "
            "no learning calibration applied."
        )
        return lines[:_MAX_REASONING]

    if negative_calibration:
        neg_domains = [e["domain"] for e in negative_calibration]
        lines.append(
            f"Negative calibration applied to: {', '.join(neg_domains)}."
        )

    if execution_mode == "safe":
        lines.append("Safe mode — positive calibration scaled to 50% of normal.")
    elif execution_mode == "aggressive":
        lines.append("Aggressive mode — positive calibration at 120% (hard caps apply).")

    if sub_override:
        lines.append("Subtitle excluded from calibration — user override in effect.")
    if cam_override:
        lines.append("Camera excluded from calibration — user override in effect.")

    return lines[:_MAX_REASONING]


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


def _clamp_f(val: Any) -> float:
    try:
        return max(0.0, min(1.0, float(val or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _fallback() -> dict:
    return {
        "learning_influence_calibration": {
            "available":              False,
            "calibration":            {},
            "negative_calibration":   [],
            "user_override_excluded": [],
            "confidence":             0.0,
            "reasoning":              [],
        }
    }
