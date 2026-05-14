"""
ai_execution_metrics_engine.py — Phase 60A AI Influence Metrics & Telemetry.

Observability-only module. Reads the promotion reports already stored on edit_plan
(by Phases 59A–59D) and produces a compact, deterministic telemetry dict.

NO render behavior change. NO influence change. NO execution mutation.

Reads from (all already computed by the time this runs):
    edit_plan.subtitle_execution_promotion   — Phase 59A result
    edit_plan.camera_execution_promotion     — Phase 59B result
    edit_plan.segment_selection_promotion    — Phase 59C result
    edit_plan.quality_gated_influence        — Phase 59D result
        .subtitle  — subtitle gate
        .camera    — camera gate
        .segment   — segment gate (merged by render_pipeline.py)

Output shape:
    {
        "ai_execution_metrics": {
            "subtitle": {
                "eligible": bool,
                "applied":  bool,         # net applied (after quality gate)
                "blocked":  bool,         # quality gate reverted it
                "fallback_used": bool,
                "reason":   str,
                "confidence": float
            },
            "camera": {
                "eligible": bool,
                "applied":  bool,
                "blocked":  bool,
                "reframe_applied": str | None,
                "crop_applied":    bool,
                "tuning_applied":  bool,
                "fallback_used":   bool,
                "reason":   str,
                "confidence": float
            },
            "segment": {
                "eligible":       bool,
                "applied":        bool,
                "blocked":        bool,
                "selected_count": int,
                "total_count":    int,
                "fallback_used":  bool,
                "reason":   str,
                "confidence": float
            },
            "quality_gate": {
                "subtitle_blocked":      bool,
                "camera_blocked":        bool,
                "segment_blocked":       bool,
                "subtitle_gate_action":  str,
                "camera_gate_action":    str,
                "segment_gate_action":   str
            },
            "user_override": {
                "subtitle": bool,
                "camera":   bool,
                "segment":  bool
            },
            "confidence": float       # mean of non-zero per-domain confidences
        },
        "ai_execution_summary": {
            "subtitle_apply":       bool,
            "camera_apply":         bool,
            "segment_apply":        bool,
            "quality_gate_blocks":  int,
            "user_override_count":  int,
            "overall_ai_assistance": str  # "none"|"low"|"medium"|"high"
        }
    }

Safety contract:
    ❌ Never raises
    ❌ No render mutation
    ❌ No payload mutation
    ❌ No influence change
    ✅ Reads existing edit_plan attributes only
    ✅ Deterministic: same inputs → same output
    ✅ Bounded output size
    ✅ Returns fallback dict on any error

Public API:
    build_ai_execution_metrics(edit_plan, payload=None, context=None) -> dict
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.metrics")

# ---------------------------------------------------------------------------
# System-disabled reason prefixes: these mean the system was not eligible,
# not that AI failed to help.
# ---------------------------------------------------------------------------
_SYSTEM_DISABLED_REASONS: frozenset[str] = frozenset({
    "ai_director_disabled",
    "ai_render_influence_disabled",
    "add_subtitle_false",
    "no_edit_plan",
    "empty_scored_list",
    "promotion_error",
    "gate_error",
    "not_attempted",
})

# Valid overall_ai_assistance levels
_ASSISTANCE_LEVELS: tuple[str, ...] = ("none", "low", "medium", "high")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_ai_execution_metrics(
    edit_plan: Any,
    payload: Any = None,
    context: Optional[dict] = None,
) -> dict:
    """Build compact telemetry from Phase 59A–59D promotion results.

    Reads existing edit_plan attributes — no side-effects, no mutations.

    Returns:
        {
            "ai_execution_metrics": {...},
            "ai_execution_summary": {...}
        }
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build(edit_plan, job_id)
    except Exception as exc:
        logger.warning("ai_execution_metrics_build_error job_id=%s: %s", job_id, exc)
        return _fallback_metrics()


# ---------------------------------------------------------------------------
# Core builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, job_id: str) -> dict:
    # Read all four promotion reports
    sub_promo = _attr_dict(edit_plan, "subtitle_execution_promotion")
    cam_promo = _attr_dict(edit_plan, "camera_execution_promotion")
    seg_promo = _attr_dict(edit_plan, "segment_selection_promotion")
    quality   = _attr_dict(edit_plan, "quality_gated_influence")

    sub_gate = quality.get("subtitle") or {}
    cam_gate = quality.get("camera")   or {}
    seg_gate = quality.get("segment")  or {}

    # ── Phase 60D: execution mode metadata ────────────────────────────────
    exec_mode_data = _attr_dict(edit_plan, "ai_execution_mode")
    exec_mode      = str(exec_mode_data.get("effective_mode") or exec_mode_data.get("mode") or "unknown")
    rollback_data  = _attr_dict(edit_plan, "ai_execution_rollback")
    rollback_active = bool(rollback_data.get("active"))

    # ── Per-domain metrics ─────────────────────────────────────────────────
    sub_metrics = _subtitle_metrics(sub_promo, sub_gate)
    cam_metrics = _camera_metrics(cam_promo, cam_gate)
    seg_metrics = _segment_metrics(seg_promo, seg_gate)

    # ── Quality gate summary ───────────────────────────────────────────────
    qg = {
        "subtitle_blocked":     bool(sub_gate.get("applied")),
        "camera_blocked":       bool(cam_gate.get("applied")),
        "segment_blocked":      bool(seg_gate.get("applied")),
        "subtitle_gate_action": str(sub_gate.get("gate_action") or "no_change"),
        "camera_gate_action":   str(cam_gate.get("gate_action") or "no_change"),
        "segment_gate_action":  str(seg_gate.get("gate_action") or "no_change"),
    }

    # ── User override summary ──────────────────────────────────────────────
    uo = {
        "subtitle": _is_user_override(str(sub_promo.get("reason") or "")),
        "camera":   _is_user_override(str(cam_promo.get("reason") or "")),
        "segment":  _is_user_override(str(seg_promo.get("reason") or "")),
    }

    # ── Aggregate confidence ───────────────────────────────────────────────
    confs = [
        sub_metrics["confidence"],
        cam_metrics["confidence"],
        seg_metrics["confidence"],
    ]
    non_zero = [c for c in confs if c > 0.0]
    agg_conf = round(sum(non_zero) / len(non_zero), 4) if non_zero else 0.0

    metrics = {
        "subtitle":      sub_metrics,
        "camera":        cam_metrics,
        "segment":       seg_metrics,
        "quality_gate":  qg,
        "user_override": uo,
        "confidence":    agg_conf,
        "mode":          exec_mode,          # Phase 60D: effective execution mode
        "rollback_active": rollback_active,  # Phase 60D: mode_off rollback active
    }

    # ── Summary ───────────────────────────────────────────────────────────
    summary = _build_summary(sub_metrics, cam_metrics, seg_metrics, qg, uo)

    logger.debug(
        "ai_execution_metrics_built job_id=%s sub_applied=%s cam_applied=%s "
        "seg_applied=%s qg_blocks=%d uo_count=%d assistance=%s",
        job_id,
        sub_metrics["applied"],
        cam_metrics["applied"],
        seg_metrics["applied"],
        summary["quality_gate_blocks"],
        summary["user_override_count"],
        summary["overall_ai_assistance"],
    )

    return {
        "ai_execution_metrics": metrics,
        "ai_execution_summary": summary,
    }


# ---------------------------------------------------------------------------
# Per-domain extractors
# ---------------------------------------------------------------------------

def _subtitle_metrics(promo: dict, gate: dict) -> dict:
    if not promo:
        return _empty_domain_metrics("not_attempted")

    reason        = str(promo.get("reason") or "")
    promo_applied = bool(promo.get("applied"))
    # Phase 60D: promo.blocked=True when mode_off blocked the promotion
    gate_blocked  = bool(gate.get("applied")) or bool(promo.get("blocked"))
    confidence    = _clamp_conf(promo.get("confidence"))
    fallback      = bool(promo.get("fallback_used", not promo_applied))
    eligible      = _is_eligible(reason)

    # Net applied = promotion ran AND neither quality gate nor mode blocked it
    net_applied = promo_applied and not gate_blocked

    return {
        "eligible":     eligible,
        "applied":      net_applied,
        "blocked":      gate_blocked,
        "fallback_used": fallback,
        "reason":       reason,
        "confidence":   confidence,
    }


def _camera_metrics(promo: dict, gate: dict) -> dict:
    if not promo:
        return {**_empty_domain_metrics("not_attempted"),
                "reframe_applied": None, "crop_applied": False, "tuning_applied": False}

    reason        = str(promo.get("reason") or "")
    promo_applied = bool(promo.get("applied"))
    # Phase 60D: promo.blocked=True when mode_off blocked the promotion
    gate_blocked  = bool(gate.get("applied")) or bool(promo.get("blocked"))
    confidence    = _clamp_conf(promo.get("confidence"))
    fallback      = bool(promo.get("fallback_used", not promo_applied))
    eligible      = _is_eligible(reason)
    net_applied   = promo_applied and not gate_blocked

    tuning = promo.get("tuning_applied")
    tuning_applied = bool(tuning) if isinstance(tuning, dict) else False

    return {
        "eligible":       eligible,
        "applied":        net_applied,
        "blocked":        gate_blocked,
        "reframe_applied": promo.get("reframe_mode_applied") if promo_applied else None,
        "crop_applied":    bool(promo.get("motion_aware_crop_applied")) if promo_applied else False,
        "tuning_applied":  tuning_applied,
        "fallback_used":   fallback,
        "reason":          reason,
        "confidence":      confidence,
    }


def _segment_metrics(promo: dict, gate: dict) -> dict:
    if not promo:
        return {**_empty_domain_metrics("not_attempted"),
                "selected_count": 0, "total_count": 0}

    reason        = str(promo.get("reason") or "")
    promo_applied = bool(promo.get("applied"))
    # Phase 60D: promo.blocked=True when mode_off blocked the promotion
    gate_blocked  = bool(gate.get("applied")) or bool(promo.get("blocked"))
    confidence    = _clamp_conf(promo.get("confidence"))
    fallback      = bool(promo.get("fallback_used", not promo_applied))
    eligible      = _is_eligible(reason)
    net_applied   = promo_applied and not gate_blocked

    return {
        "eligible":      eligible,
        "applied":       net_applied,
        "blocked":       gate_blocked,
        "selected_count": int(promo.get("selected_count") or 0),
        "total_count":   int(promo.get("total_count") or 0),
        "fallback_used": fallback,
        "reason":        reason,
        "confidence":    confidence,
    }


# ---------------------------------------------------------------------------
# Summary builder
# ---------------------------------------------------------------------------

def _build_summary(
    sub: dict,
    cam: dict,
    seg: dict,
    qg:  dict,
    uo:  dict,
) -> dict:
    subtitle_apply = sub["applied"]
    camera_apply   = cam["applied"]
    segment_apply  = seg["applied"]

    qg_blocks = sum([
        qg["subtitle_blocked"],
        qg["camera_blocked"],
        qg["segment_blocked"],
    ])
    uo_count = sum([uo["subtitle"], uo["camera"], uo["segment"]])

    applied_count = sum([subtitle_apply, camera_apply, segment_apply])
    assistance = _ASSISTANCE_LEVELS[min(applied_count, 3)]

    return {
        "subtitle_apply":       subtitle_apply,
        "camera_apply":         camera_apply,
        "segment_apply":        segment_apply,
        "quality_gate_blocks":  qg_blocks,
        "user_override_count":  uo_count,
        "overall_ai_assistance": assistance,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attr_dict(obj: Any, attr: str) -> dict:
    """Duck-typed attribute access returning a dict or {}."""
    try:
        val = obj.get(attr) if isinstance(obj, dict) else getattr(obj, attr, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _is_eligible(reason: str) -> bool:
    """True if the reason does not indicate a system-level disable."""
    base = reason.split(":")[0]
    return base not in _SYSTEM_DISABLED_REASONS


def _is_user_override(reason: str) -> bool:
    return reason.startswith("user_override")


def _clamp_conf(val: Any) -> float:
    """Clamp confidence to [0.0, 1.0], return 0.0 on any error."""
    try:
        f = float(val or 0.0)
        return round(max(0.0, min(1.0, f)), 4)
    except (TypeError, ValueError):
        return 0.0


def _empty_domain_metrics(reason: str = "not_attempted") -> dict:
    return {
        "eligible":     False,
        "applied":      False,
        "blocked":      False,
        "fallback_used": True,
        "reason":       reason,
        "confidence":   0.0,
    }


def _fallback_metrics() -> dict:
    return {
        "ai_execution_metrics": {
            "subtitle":      {},
            "camera":        {},
            "segment":       {},
            "quality_gate":  {},
            "user_override": {},
            "confidence":    0.0,
            "mode":          "unknown",
            "rollback_active": False,
        },
        "ai_execution_summary": {
            "subtitle_apply":       False,
            "camera_apply":         False,
            "segment_apply":        False,
            "quality_gate_blocks":  0,
            "user_override_count":  0,
            "overall_ai_assistance": "none",
        },
    }
