"""
decision_preview.py — Deterministic AI render decision preview builder. Phase 24.

Aggregates all prior-phase AI metadata into a compact advisory preview that
describes what AI would recommend before any render execution mutation is
allowed. Useful for developer/creator review and explainability.

Design rules:
- Deterministic only.
- Never raises.
- Advisory metadata only — no payload mutation, no FFmpeg, no render trigger.
- Reads from: variants, variant_selection, creator_style_adaptation,
  retention, story_optimization, subtitle_execution, timing_mutation,
  beat_visual_execution, explainability.
- safe_to_execute is always False.

Public API:
    build_render_decision_preview(edit_plan, context=None) -> dict
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.preview.preview_schema import (
    AIRenderDecisionPreview,
    AIPreviewSafetyReport,
    VALID_SAFETY_STATUSES,
)

logger = logging.getLogger("app.ai.preview")

# ── Blocked actions — always included regardless of metadata ─────────────────
# These actions are blocked in Phase 24 and must be stated explicitly.
_BLOCKED_ACTIONS: list[str] = [
    "autonomous_rendering_of_selected_variant",
    "ffmpeg_filter_chain_mutation",
    "timing_mutation_application",
    "subtitle_timing_rewrite",
    "playback_speed_mutation",
    "segment_reorder",
]


def build_render_decision_preview(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build a compact advisory render decision preview from edit plan metadata.

    Aggregates variant selection, creator style, retention risk, story
    optimization, subtitle, visual rhythm, and timing plan metadata into a
    single human-readable advisory summary.

    Args:
        edit_plan:  AIEditPlan or None. Read-only.
        context:    Optional metadata dict.

    Returns:
        Serialised dict of AIRenderDecisionPreview. Never raises.
    """
    try:
        preview = _build(edit_plan, context or {})
        result = preview.to_dict()
        result["safety_report"] = _build_safety_report(preview).to_dict()
        return result
    except Exception as exc:
        logger.debug("build_render_decision_preview_failed: %s", exc)
        return _fallback_preview(str(exc))


# ── Internal builder ──────────────────────────────────────────────────────────

def _build(edit_plan: Any, context: dict) -> AIRenderDecisionPreview:
    warnings: list[str] = []
    explanation: list[str] = []

    if edit_plan is None:
        logger.info("ai_render_decision_preview_skipped: no_edit_plan")
        return AIRenderDecisionPreview(
            available=False,
            safety_status="unavailable",
            decision_summary="No edit plan available",
            blocked_actions=list(_BLOCKED_ACTIONS),
            warnings=["no_edit_plan"],
        )

    # ── Variant selection metadata ────────────────────────────────────────────
    vs = _safe_dict(getattr(edit_plan, "variant_selection", {}))
    selected_variant_id = vs.get("selected_variant_id") or None
    variant_confidence = float(vs.get("selection_confidence") or 0.0)
    variant_fallback = bool(vs.get("fallback_used", False))
    variant_purpose = _resolve_variant_purpose(
        selected_variant_id, getattr(edit_plan, "variants", {})
    )

    # ── Creator style metadata ────────────────────────────────────────────────
    csa = _safe_dict(getattr(edit_plan, "creator_style_adaptation", {}))
    creator_style = str(csa.get("primary_style") or "")
    style_confidence = float(csa.get("confidence") or 0.0)
    style_detected = bool(csa.get("detected", False))

    # ── Retention intelligence ────────────────────────────────────────────────
    retention = _safe_dict(getattr(edit_plan, "retention", {}))
    ret_score = float(retention.get("overall_retention_score") or 50)
    ret_risks = list(retention.get("risk_regions") or [])

    # ── Story optimization ────────────────────────────────────────────────────
    so = _safe_dict(getattr(edit_plan, "story_optimization", {}))
    narrative_score = float(so.get("narrative_score") or 0)
    so_issues = list(so.get("issues") or [])

    # ── Subtitle execution ────────────────────────────────────────────────────
    se = _safe_dict(getattr(edit_plan, "subtitle_execution", {}))
    subtitle_available = bool(se.get("available", False))

    # ── Timing mutation ───────────────────────────────────────────────────────
    tm = _safe_dict(getattr(edit_plan, "timing_mutation", {}))
    timing_candidates = list(tm.get("candidates") or [])
    timing_safe_count = sum(
        1 for c in timing_candidates
        if isinstance(c, dict) and c.get("safe_to_apply")
    )

    # ── Overall confidence (weighted blend) ───────────────────────────────────
    confidence = _compute_overall_confidence(
        variant_confidence, style_confidence, ret_score, narrative_score
    )

    # ── Safety status ─────────────────────────────────────────────────────────
    safety_status = _determine_safety_status(
        selected_variant_id, variant_confidence, ret_score, vs, warnings
    )

    # ── Recommended advisory actions ──────────────────────────────────────────
    recommended_actions = _build_recommended_actions(
        selected_variant_id, variant_purpose, variant_fallback,
        creator_style, style_detected,
        ret_score, ret_risks,
        so_issues, narrative_score,
        timing_safe_count, subtitle_available,
    )

    # ── Decision summary string ───────────────────────────────────────────────
    decision_summary = _build_summary(
        selected_variant_id, variant_purpose, variant_fallback,
        creator_style, style_detected, confidence,
    )

    # ── Explanation lines ─────────────────────────────────────────────────────
    explanation = _build_explanation(
        selected_variant_id, variant_purpose, creator_style,
        style_detected, ret_score, narrative_score,
        timing_safe_count, subtitle_available,
    )

    logger.info(
        "ai_render_decision_preview_created variant=%s style=%s confidence=%.4f status=%s",
        selected_variant_id or "none",
        creator_style or "none",
        confidence,
        safety_status,
    )

    return AIRenderDecisionPreview(
        available=True,
        mode="advisory",
        selected_variant_id=selected_variant_id,
        creator_style=creator_style,
        decision_summary=decision_summary,
        recommended_actions=recommended_actions,
        blocked_actions=list(_BLOCKED_ACTIONS),
        safety_status=safety_status,
        confidence=confidence,
        warnings=warnings,
        explanation=explanation,
    )


# ── Safety report ─────────────────────────────────────────────────────────────

def _build_safety_report(preview: AIRenderDecisionPreview) -> AIPreviewSafetyReport:
    blocked_reasons: list[str] = []
    warnings: list[str] = []

    # Advisory mode always blocks execution
    blocked_reasons.append("phase24_advisory_only_mode")
    if preview.selected_variant_id:
        blocked_reasons.append("variant_not_auto_executed_in_advisory_mode")
    if preview.safety_status == "caution":
        blocked_reasons.append("caution_signals_detected_in_metadata")
        warnings.append("review_recommended_before_execution")

    return AIPreviewSafetyReport(
        safe_to_preview=preview.available,
        safe_to_execute=False,       # always False
        blocked_reasons=blocked_reasons,
        advisory_only=True,          # always True
        warnings=warnings,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_variant_purpose(selected_id: Optional[str], variants_meta: Any) -> str:
    """Find the purpose of the selected variant from variants metadata."""
    if not selected_id:
        return ""
    try:
        vd = _safe_dict(variants_meta)
        for v in vd.get("variants") or []:
            if isinstance(v, dict) and str(v.get("variant_id")) == str(selected_id):
                return str(v.get("purpose") or "")
    except Exception:
        pass
    return ""


def _compute_overall_confidence(
    variant_conf: float,
    style_conf: float,
    ret_score: float,
    narrative_score: float,
) -> float:
    """Weighted blend of available confidence signals → 0-1 range."""
    try:
        signals = []
        if variant_conf > 0:
            signals.append(variant_conf)
        if style_conf > 0:
            signals.append(style_conf)
        if ret_score > 0:
            signals.append(min(1.0, ret_score / 100.0))
        if narrative_score > 0:
            signals.append(min(1.0, narrative_score / 100.0))
        if not signals:
            return 0.0
        return round(sum(signals) / len(signals), 4)
    except Exception:
        return 0.0


def _determine_safety_status(
    selected_id: Optional[str],
    variant_confidence: float,
    ret_score: float,
    vs: dict,
    warnings: list[str],
) -> str:
    if selected_id is None and not vs:
        return "unavailable"
    if ret_score < 40 or variant_confidence < 0.30:
        warnings.append("low_confidence_or_retention_signals")
        return "caution"
    return "safe"


def _build_recommended_actions(
    selected_id: Optional[str],
    variant_purpose: str,
    variant_fallback: bool,
    creator_style: str,
    style_detected: bool,
    ret_score: float,
    ret_risks: list,
    so_issues: list,
    narrative_score: float,
    timing_safe_count: int,
    subtitle_available: bool,
) -> list[str]:
    actions: list[str] = []

    if selected_id:
        if variant_fallback:
            actions.append("Review AI-selected safe baseline variant (low confidence fallback)")
        elif variant_purpose:
            purpose_label = variant_purpose.replace("_", " ")
            actions.append(f"Review AI-selected {purpose_label} variant before rendering")
        else:
            actions.append("Review AI-selected advisory variant before rendering")

    if style_detected and creator_style and creator_style != "safe_generic":
        style_label = creator_style.replace("_", " ")
        actions.append(f"Consider {style_label} style preset and pacing hints")

    if ret_score < 60 and ret_risks:
        actions.append(f"Review {len(ret_risks)} retention risk region(s) before rendering")

    if so_issues and narrative_score < 65:
        issue_count = len(so_issues)
        actions.append(f"Review {issue_count} story arc issue(s) for optimization")

    if timing_safe_count > 0:
        actions.append(
            f"Review {timing_safe_count} safe timing mutation candidate(s) before applying"
        )

    if subtitle_available:
        actions.append("Review subtitle density and emphasis hints")

    if not actions:
        actions.append("Review AI advisory metadata before rendering")

    return actions[:5]


def _build_summary(
    selected_id: Optional[str],
    variant_purpose: str,
    variant_fallback: bool,
    creator_style: str,
    style_detected: bool,
    confidence: float,
) -> str:
    parts: list[str] = []

    if selected_id:
        if variant_fallback:
            parts.append("AI recommends safe baseline variant")
        elif variant_purpose:
            parts.append(f"AI recommends {variant_purpose.replace('_', ' ')} variant")
        else:
            parts.append("AI variant selected")
    else:
        parts.append("AI advisory preview ready")

    if style_detected and creator_style and creator_style != "safe_generic":
        parts.append(f"with {creator_style.replace('_', ' ')} style")

    if confidence >= 0.70:
        parts.append(f"(high confidence {confidence:.0%})")
    elif confidence >= 0.40:
        parts.append(f"(moderate confidence {confidence:.0%})")
    elif confidence > 0:
        parts.append(f"(low confidence {confidence:.0%})")

    return " ".join(parts) if parts else "AI render decision preview — advisory mode"


def _build_explanation(
    selected_id: Optional[str],
    variant_purpose: str,
    creator_style: str,
    style_detected: bool,
    ret_score: float,
    narrative_score: float,
    timing_safe_count: int,
    subtitle_available: bool,
) -> list[str]:
    lines: list[str] = ["AI render decision preview prepared", "Advisory mode — no autonomous actions"]

    if selected_id:
        purpose_label = variant_purpose.replace("_", " ") if variant_purpose else "advisory"
        lines.append(f"Selected advisory variant summarized ({purpose_label})")
    else:
        lines.append("No variant selected — using baseline advisory mode")

    if style_detected and creator_style:
        lines.append(f"Creator style: {creator_style.replace('_', ' ')}")

    if ret_score > 0:
        lines.append(f"Retention score: {ret_score:.0f}/100")

    if narrative_score > 0:
        lines.append(f"Narrative score: {narrative_score:.0f}/100")

    lines.append("Autonomous render actions remain blocked")
    return lines[:8]


def _safe_dict(val: Any) -> dict:
    """Return val if it is a dict, else an empty dict."""
    return val if isinstance(val, dict) else {}


def _fallback_preview(reason: str) -> dict:
    logger.info("ai_render_decision_preview_fallback reason=%s", reason)
    return AIRenderDecisionPreview(
        available=False,
        mode="advisory",
        safety_status="unavailable",
        decision_summary="Preview unavailable due to internal error",
        blocked_actions=list(_BLOCKED_ACTIONS),
        warnings=[f"preview_error:{reason}"],
        explanation=["Preview builder encountered an error", "Advisory mode preserved"],
    ).to_dict() | {
        "safety_report": AIPreviewSafetyReport(
            safe_to_preview=False,
            safe_to_execute=False,
            blocked_reasons=["preview_error", "phase24_advisory_only_mode"],
            advisory_only=True,
            warnings=[f"preview_error:{reason}"],
        ).to_dict()
    }
