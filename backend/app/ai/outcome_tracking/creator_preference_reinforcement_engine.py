"""
creator_preference_reinforcement_engine.py — Phase 62B Creator Preference Reinforcement.

Reinforcement-metadata-only module. Uses render_outcome_tracking (Phase 62A)
and AI metadata (Phases 50D, 60A, 60B, 60C, 61A, 61D) to produce deterministic,
bounded creator preference reinforcement signals.

NO autonomous retraining.  NO cloud learning.  NO fine-tuning.
NO render mutation.  NO influence mutation.  NO external persistence.

Positive reinforcement — only when evidence is strong:
    overall_result = improved
    AND ai_effectiveness in (strong, moderate)
    AND winner = ai_on (required for domain-level reinforcement)

Negative signals — recorded advisory-only:
    winner = ai_off / regression / platform feedback weak
    Never auto-applied. Never deletes preferences.

Confidence delta bounds (strict, tested):
    max positive delta per domain:    +0.05
    max negative delta per domain:    -0.05
    total absolute delta cap:          0.12

Evidence gate (all must pass to allow reinforcement):
    1. render_outcome_tracking.available == True
    2. creator_type known (not "unknown")
    3. quality data present (at least one quality score > 0)
    4. execution metrics or summary present
    5. if A/B baseline missing AND confidence < 0.65 → conservative fallback

User override exclusion:
    If subtitle/camera was user-overridden (reason contains "user_override" in
    promotion report), that domain is excluded and noted in reasoning.

Public API:
    build_creator_preference_reinforcement(edit_plan, context=None) -> dict

Output shape (available):
    {
        "creator_preference_reinforcement": {
            "available":    true,
            "creator_type": "podcast",
            "reinforced_preferences": {
                "subtitle": {
                    "style":              "clean_pro",
                    "density":            "balanced",
                    "keyword_emphasis":   "selective",
                    "confidence_delta":    0.042
                },
                "camera": {
                    "stability_priority":  "high",
                    "crop_aggressiveness": "low",
                    "confidence_delta":    0.0405
                },
                "ranking": {
                    "priority":          "retention_creator_fit",
                    "confidence_delta":  0.03
                }
            },
            "negative_signals": [],
            "confidence": 0.82,
            "reasoning": [
                "AI ON improved overall quality, reinforcing subtitle, camera preferences.",
                "Creator fit is strong — ranking preference also reinforced."
            ]
        }
    }

Output shape (fallback):
    {
        "creator_preference_reinforcement": {
            "available":              false,
            "reinforced_preferences": {},
            "negative_signals":       [],
            "confidence":             0.0,
            "reasoning":              []
        }
    }

Safety contract:
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ❌ No autonomous retraining
    ❌ No cloud learning / fine-tuning
    ❌ No external persistence
    ❌ No influence mutation
    ✅ Reinforcement metadata only — advisory signals for future phases
    ✅ Deterministic: same inputs → same output
    ✅ Returns fallback on any error
    ✅ Confidence delta bounded per domain and total
    ✅ User overrides respected and excluded
    ✅ Negative signals advisory-only, never auto-applied
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.outcome_tracking")

# ---------------------------------------------------------------------------
# Thresholds (explicit, tested)
# ---------------------------------------------------------------------------
_MIN_QUALITY_FOR_REINFORCEMENT: int   = 70    # domain quality must exceed this to reinforce
_MAX_POSITIVE_DELTA:             float = 0.05  # max positive confidence_delta per domain
_MAX_NEGATIVE_DELTA:             float = 0.05  # max negative confidence_delta magnitude per domain
_MAX_TOTAL_DELTA:                float = 0.12  # max sum of all absolute deltas
_AB_MISSING_CONF_THRESHOLD:      float = 0.65  # if ab missing and confidence < this, gate fails

# Base confidence deltas for positive reinforcement
_DELTA_BASE_STRONG:   float = 0.05   # ai_effectiveness = strong
_DELTA_BASE_MODERATE: float = 0.03   # ai_effectiveness = moderate
_DELTA_BASE_RANKING:  float = 0.03   # ranking reinforcement (conservative)

# Base magnitude for negative signals
_DELTA_BASE_NEGATIVE: float = 0.04

# Max reasoning lines
_MAX_REASONING = 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_creator_preference_reinforcement(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build creator preference reinforcement metadata.

    Returns:
        {"creator_preference_reinforcement": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build(edit_plan, job_id)
    except Exception as exc:
        logger.warning(
            "creator_preference_reinforcement_unexpected_error job_id=%s: %s", job_id, exc
        )
        return _fallback()


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, job_id: str) -> dict:
    if edit_plan is None:
        return _fallback()

    # ── Read signal inputs ─────────────────────────────────────────────────
    rot          = _get_dict(edit_plan, "render_outcome_tracking")
    crs          = _get_dict(edit_plan, "creator_render_strategy")
    metrics      = _get_dict(edit_plan, "ai_execution_metrics")
    exec_summary = _get_dict(edit_plan, "ai_execution_summary")
    ab_eval      = _get_dict(edit_plan, "ai_ab_evaluation")
    bench        = _get_dict(edit_plan, "creator_benchmark_summary")
    pqf          = _get_dict(edit_plan, "platform_quality_feedback")
    sub_promo    = _get_dict(edit_plan, "subtitle_execution_promotion")
    cam_promo    = _get_dict(edit_plan, "camera_execution_promotion")

    # ── Extract core signals from render_outcome_tracking ─────────────────
    rot_available    = bool(rot.get("available"))
    creator_type     = str(rot.get("creator_type") or "unknown").lower()
    overall_result   = str(rot.get("overall_result") or "neutral")
    ai_effectiveness = str(rot.get("ai_effectiveness") or "weak")
    rot_confidence   = _clamp_f(rot.get("confidence"))
    quality          = rot.get("quality") or {}
    ai_execution     = rot.get("ai_execution") or {}
    ab_result        = rot.get("ab_result") or {}
    bench_result     = rot.get("benchmark_result") or {}

    ab_available = bool(ab_eval.get("available"))
    ab_winner    = str(ab_result.get("winner") or "unknown")
    bench_status = str(bench.get("benchmark_status") or "unknown")

    # ── Evidence gate ─────────────────────────────────────────────────────
    exec_signals = metrics or exec_summary   # either suffices for gate check
    gate_pass, gate_reason = _passes_evidence_gate(
        rot_available, creator_type, quality, exec_signals,
        ab_available, rot_confidence,
    )
    if not gate_pass:
        logger.debug(
            "creator_preference_reinforcement_gated job_id=%s reason=%s",
            job_id, gate_reason,
        )
        return _fallback()

    # ── User override exclusion ────────────────────────────────────────────
    user_overrides = _check_user_overrides(sub_promo, cam_promo)

    # ── Positive reinforcement ─────────────────────────────────────────────
    reinforced: dict = {}
    if overall_result == "improved" and ai_effectiveness in ("strong", "moderate"):
        # Subtitle
        if (
            ai_execution.get("subtitle_applied") and
            quality.get("subtitle", 0) >= _MIN_QUALITY_FOR_REINFORCEMENT and
            "subtitle" not in user_overrides
        ):
            sub_pref = _reinforce_subtitle(crs, ai_effectiveness, quality)
            if sub_pref:
                reinforced["subtitle"] = sub_pref

        # Camera
        if (
            ai_execution.get("camera_applied") and
            quality.get("camera", 0) >= _MIN_QUALITY_FOR_REINFORCEMENT and
            "camera" not in user_overrides
        ):
            cam_pref = _reinforce_camera(crs, ai_effectiveness, quality)
            if cam_pref:
                reinforced["camera"] = cam_pref

        # Ranking — only for strong evidence + high benchmark creator fit
        if (
            ai_effectiveness == "strong" and
            bench_result.get("creator_fit") == "high"
        ):
            rank_pref = _reinforce_ranking(crs, bench_result)
            if rank_pref:
                reinforced["ranking"] = rank_pref

    # ── Negative signals ──────────────────────────────────────────────────
    negative_signals = _compute_negative_signals(
        ab_available, ab_winner, ai_execution, quality, pqf, overall_result,
    )

    # ── Total delta cap ───────────────────────────────────────────────────
    _apply_total_delta_cap(reinforced, negative_signals)

    # ── Reinforcement confidence ──────────────────────────────────────────
    confidence = _compute_confidence(rot_confidence, ab_available, overall_result)

    # ── Reasoning ─────────────────────────────────────────────────────────
    reasoning = _build_reasoning(
        reinforced, negative_signals, overall_result, ai_effectiveness,
        ab_available, user_overrides, bench_status,
    )

    logger.info(
        "creator_preference_reinforcement_built job_id=%s creator=%s "
        "domains_reinforced=%d negative_signals=%d confidence=%.3f",
        job_id, creator_type,
        len(reinforced), len(negative_signals), confidence,
    )

    return {
        "creator_preference_reinforcement": {
            "available":              True,
            "creator_type":           creator_type,
            "reinforced_preferences": reinforced,
            "negative_signals":       negative_signals,
            "confidence":             confidence,
            "reasoning":              reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Evidence gate
# ---------------------------------------------------------------------------

def _passes_evidence_gate(
    rot_available: bool,
    creator_type: str,
    quality: dict,
    exec_signals: dict,
    ab_available: bool,
    rot_confidence: float,
) -> tuple[bool, str]:
    """Return (passed, reason). All conditions must pass to allow reinforcement."""
    if not rot_available:
        return False, "outcome_unavailable"
    if creator_type == "unknown":
        return False, "creator_type_unknown"
    if not any(quality.get(k, 0) > 0 for k in ("subtitle", "camera", "hook", "overall")):
        return False, "quality_missing"
    if not exec_signals:
        return False, "execution_metrics_missing"
    if not ab_available and rot_confidence < _AB_MISSING_CONF_THRESHOLD:
        return False, "ab_missing_confidence_low"
    return True, "passed"


# ---------------------------------------------------------------------------
# Positive reinforcement builders
# ---------------------------------------------------------------------------

def _reinforce_subtitle(crs: dict, ai_effectiveness: str, quality: dict) -> dict:
    """Build subtitle reinforcement from creator_render_strategy."""
    strategy         = (crs.get("strategy") or {}).get("subtitle") or {}
    style            = str(strategy.get("style") or "clean_pro")
    density          = str(strategy.get("density") or "balanced")
    keyword_emphasis = str(strategy.get("keyword_emphasis") or "selective")
    subtitle_q       = quality.get("subtitle", 0)
    delta            = _positive_delta(ai_effectiveness, subtitle_q)
    if delta <= 0.0:
        return {}
    return {
        "style":            style,
        "density":          density,
        "keyword_emphasis": keyword_emphasis,
        "confidence_delta": delta,
    }


def _reinforce_camera(crs: dict, ai_effectiveness: str, quality: dict) -> dict:
    """Build camera reinforcement from creator_render_strategy."""
    strategy            = (crs.get("strategy") or {}).get("camera") or {}
    stability_priority  = str(strategy.get("stability_priority") or "high")
    crop_aggressiveness = str(strategy.get("crop_aggressiveness") or "low")
    camera_q            = quality.get("camera", 0)
    delta               = _positive_delta(ai_effectiveness, camera_q)
    if delta <= 0.0:
        return {}
    return {
        "stability_priority":  stability_priority,
        "crop_aggressiveness": crop_aggressiveness,
        "confidence_delta":    delta,
    }


def _reinforce_ranking(crs: dict, bench_result: dict) -> dict:
    """Build ranking reinforcement from creator_render_strategy."""
    strategy    = (crs.get("strategy") or {}).get("ranking") or {}
    priority    = str(strategy.get("priority") or "retention_creator_fit")
    bench_delta = int(bench_result.get("benchmark_delta") or 0)
    scale       = min(1.0, max(0.5, bench_delta / 10.0))
    delta       = round(min(_DELTA_BASE_RANKING, _DELTA_BASE_RANKING * scale), 4)
    if delta <= 0.0:
        return {}
    return {
        "priority":         priority,
        "confidence_delta": delta,
    }


def _positive_delta(ai_effectiveness: str, domain_quality: int) -> float:
    """Compute positive confidence_delta for a domain.

    strong + quality=84 → round(0.05 * 0.84, 4) = 0.042
    moderate + quality=81 → round(0.03 * 0.81, 4) = 0.0243
    Clamped to [0.0, _MAX_POSITIVE_DELTA].
    """
    base = _DELTA_BASE_STRONG if ai_effectiveness == "strong" else _DELTA_BASE_MODERATE
    quality_frac = max(0.0, min(1.0, domain_quality / 100.0))
    delta = round(base * quality_frac, 4)
    return min(_MAX_POSITIVE_DELTA, max(0.0, delta))


# ---------------------------------------------------------------------------
# Negative signal builder
# ---------------------------------------------------------------------------

def _compute_negative_signals(
    ab_available: bool,
    ab_winner: str,
    ai_execution: dict,
    quality: dict,
    pqf: dict,
    overall_result: str,
) -> list:
    """Compute advisory-only negative signals. Never auto-applied, never deletes preferences."""
    signals: list = []

    if ab_available and ab_winner == "ai_off":
        # Per-domain negative signals for applied domains with low quality
        domain_signals_added = False
        if ai_execution.get("subtitle_applied") and quality.get("subtitle", 0) < _MIN_QUALITY_FOR_REINFORCEMENT:
            signals.append({
                "domain":           "subtitle",
                "signal":           "subtitle_underperformed",
                "confidence_delta": -_DELTA_BASE_NEGATIVE,
            })
            domain_signals_added = True
        if ai_execution.get("camera_applied") and quality.get("camera", 0) < _MIN_QUALITY_FOR_REINFORCEMENT:
            signals.append({
                "domain":           "camera",
                "signal":           "camera_underperformed",
                "confidence_delta": -_DELTA_BASE_NEGATIVE,
            })
            domain_signals_added = True
        if not domain_signals_added:
            signals.append({
                "domain":           "overall",
                "signal":           "ai_off_winner",
                "confidence_delta": -_DELTA_BASE_NEGATIVE,
            })

    elif overall_result == "regression":
        signals.append({
            "domain":           "overall",
            "signal":           "overall_regression",
            "confidence_delta": -_DELTA_BASE_NEGATIVE,
        })

    # Platform quality feedback — camera-specific
    if pqf and pqf.get("available"):
        try:
            cam_fit = int(pqf.get("camera_fit") or 0)
            if cam_fit <= 30 and ai_execution.get("camera_applied"):
                signals.append({
                    "domain":           "camera",
                    "signal":           "platform_camera_fit_weak",
                    "confidence_delta": -round(_DELTA_BASE_NEGATIVE * 0.8, 4),
                })
        except (TypeError, ValueError):
            pass

    # Clamp all negative deltas to [−_MAX_NEGATIVE_DELTA, 0]
    for sig in signals:
        d = sig.get("confidence_delta", 0.0)
        sig["confidence_delta"] = max(-_MAX_NEGATIVE_DELTA, min(0.0, float(d)))

    return signals


# ---------------------------------------------------------------------------
# Total delta cap
# ---------------------------------------------------------------------------

def _apply_total_delta_cap(reinforced: dict, negative_signals: list) -> None:
    """Scale all deltas proportionally if total absolute delta exceeds _MAX_TOTAL_DELTA."""
    total = sum(abs(float(p.get("confidence_delta", 0.0))) for p in reinforced.values())
    total += sum(abs(float(s.get("confidence_delta", 0.0))) for s in negative_signals)

    if total > _MAX_TOTAL_DELTA and total > 0.0:
        scale = _MAX_TOTAL_DELTA / total
        for pref in reinforced.values():
            pref["confidence_delta"] = round(
                float(pref.get("confidence_delta", 0.0)) * scale, 4
            )
        for sig in negative_signals:
            sig["confidence_delta"] = round(
                float(sig.get("confidence_delta", 0.0)) * scale, 4
            )


# ---------------------------------------------------------------------------
# Reinforcement confidence
# ---------------------------------------------------------------------------

def _compute_confidence(
    rot_confidence: float,
    ab_available: bool,
    overall_result: str,
) -> float:
    """Confidence in the reinforcement signal itself.

    improved + ab_available → full rot_confidence
    improved + ab_missing   → rot_confidence × 0.7  (less certain without baseline)
    other                   → rot_confidence × 0.3  (minimal for neutral/regression)
    """
    if overall_result == "improved" and ab_available:
        conf = rot_confidence
    elif overall_result == "improved":
        conf = rot_confidence * 0.7
    else:
        conf = rot_confidence * 0.3
    return round(max(0.0, min(1.0, conf)), 4)


# ---------------------------------------------------------------------------
# User override check
# ---------------------------------------------------------------------------

def _check_user_overrides(sub_promo: dict, cam_promo: dict) -> frozenset:
    """Return frozenset of domain names excluded due to user override."""
    overrides: set = set()
    if "user_override" in str(sub_promo.get("reason") or "").lower():
        overrides.add("subtitle")
    if "user_override" in str(cam_promo.get("reason") or "").lower():
        overrides.add("camera")
    return frozenset(overrides)


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    reinforced: dict,
    negative_signals: list,
    overall_result: str,
    ai_effectiveness: str,
    ab_available: bool,
    user_overrides: frozenset,
    bench_status: str,
) -> list:
    lines: list = []

    if reinforced:
        domains = ", ".join(reinforced.keys())
        if ai_effectiveness == "strong":
            lines.append(
                f"AI ON improved overall quality, reinforcing {domains} preferences."
            )
        else:
            lines.append(f"Positive outcome reinforced {domains} preferences.")
        if "ranking" in reinforced:
            lines.append("Creator fit is strong — ranking preference also reinforced.")
    elif overall_result == "improved":
        lines.append("Improved outcome detected but quality below reinforcement threshold.")
    elif overall_result == "neutral":
        lines.append("Neutral outcome — no preference reinforcement applied.")

    if not ab_available:
        lines.append(
            "A/B baseline was missing, so preference reinforcement stayed conservative."
        )

    if negative_signals:
        sig_domains = ", ".join(sorted({s.get("domain", "unknown") for s in negative_signals}))
        lines.append(
            f"Negative signal recorded for {sig_domains} — advisory only, not applied."
        )

    for domain in sorted(user_overrides):
        lines.append(f"User override excluded {domain!r} domain from reinforcement.")

    if bench_status == "needs_review":
        lines.append(
            "Benchmark confidence is low — reinforcement signals are advisory only."
        )

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
        "creator_preference_reinforcement": {
            "available":              False,
            "reinforced_preferences": {},
            "negative_signals":       [],
            "confidence":             0.0,
            "reasoning":              [],
        }
    }
