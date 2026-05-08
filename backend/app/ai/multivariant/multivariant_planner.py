"""
multivariant_planner.py — Safe multi-variant render plan builder.

Phase 28: builds a set of up to 5 render variant plans from AI planning metadata.
Mode is always planning_only. Plans are NEVER enqueued or executed here.
advisory_only is always True. safe_to_enqueue requires zero blocked fields.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from .multivariant_schema import (
    AIMultiVariantRenderPlan,
    AIMultiVariantRenderSet,
)
from .multivariant_safety import (
    sanitize_variant_payload_overrides,
    collect_blocked_fields,
)

logger = logging.getLogger(__name__)

_MAX_PLANS = 5

_STYLE_TO_CAMERA: dict[str, str] = {
    "viral_tiktok": "dynamic_safe",
    "cinematic": "dynamic_safe",
    "storytelling": "dynamic_safe",
    "commentary": "dynamic_safe",
}

_PACING_STYLE_MAP: dict[str, str] = {
    "fast": "fast_cut",
    "slow": "slow_cut",
    "moderate": "moderate",
    "standard": "standard",
    "dynamic": "fast_cut",
    "story_driven": "standard",
}


def build_multivariant_render_plans(
    edit_plan: Any,
    payload: Optional[Any] = None,
    context: Optional[dict] = None,
) -> AIMultiVariantRenderSet:
    """Build a safe multi-variant render planning set. Never raises. Never enqueues."""
    try:
        plans = _collect_plans(edit_plan)
        recommended_id = _select_recommended(plans)
        warnings: list[str] = []
        if not plans:
            warnings.append("no_variant_plans_generated")
        return AIMultiVariantRenderSet(
            available=bool(plans),
            mode="planning_only",
            plans=plans[:_MAX_PLANS],
            recommended_plan_id=recommended_id,
            warnings=warnings,
        )
    except Exception as exc:
        logger.warning("multivariant_planner_error: %s", exc)
        return _fallback_set(str(exc))


def _collect_plans(edit_plan: Any) -> list[AIMultiVariantRenderPlan]:
    plans: list[AIMultiVariantRenderPlan] = []

    plans.append(_build_baseline_plan(edit_plan))

    recommended = _build_recommended_variant_plan(edit_plan)
    if recommended is not None:
        plans.append(recommended)

    compact = _build_compact_subtitle_plan(edit_plan)
    if compact is not None:
        plans.append(compact)

    creator = _build_creator_style_plan(edit_plan)
    if creator is not None:
        plans.append(creator)

    retention = _build_retention_plan(edit_plan)
    if retention is not None and len(plans) < _MAX_PLANS:
        plans.append(retention)

    return plans[:_MAX_PLANS]


def _build_baseline_plan(edit_plan: Any) -> AIMultiVariantRenderPlan:
    overrides = {"ai_mode": "advisory", "pacing_style": "standard"}
    sanitized = sanitize_variant_payload_overrides(overrides)
    blocked = collect_blocked_fields(overrides)
    return AIMultiVariantRenderPlan(
        plan_id="mvplan_baseline",
        variant_id="baseline",
        label="Baseline Safe Render Plan",
        renderable=True,
        safe_to_enqueue=len(blocked) == 0,
        advisory_only=True,
        mutation_ids=[],
        planned_payload_overrides=sanitized,
        blocked_fields=blocked,
        warnings=[],
        explanation="Conservative baseline with default settings. Always safe.",
    )


def _build_recommended_variant_plan(edit_plan: Any) -> Optional[AIMultiVariantRenderPlan]:
    try:
        variant_selection = getattr(edit_plan, "variant_selection", {}) or {}
        recommended_variant = variant_selection.get("recommended_variant_id") or variant_selection.get("selected_id")

        variants = getattr(edit_plan, "variants", {}) or {}
        variant_list = variants.get("variants", [])

        safe_mutations = getattr(edit_plan, "safe_render_mutations", {}) or {}
        applied_ids = safe_mutations.get("applied_mutation_ids", []) or []

        if not recommended_variant and not variant_list:
            return None

        overrides: dict = {"ai_mode": "advisory"}
        if variant_list:
            top_variant = variant_list[0] if isinstance(variant_list, list) and variant_list else {}
            overrides_raw = top_variant.get("planned_overrides") or top_variant.get("settings") or {}
            if isinstance(overrides_raw, dict):
                overrides.update(overrides_raw)

        sanitized = sanitize_variant_payload_overrides(overrides)
        blocked = collect_blocked_fields(overrides)

        return AIMultiVariantRenderPlan(
            plan_id="mvplan_recommended_variant",
            variant_id=recommended_variant or "recommended",
            label="Recommended Variant Render Plan",
            renderable=True,
            safe_to_enqueue=len(blocked) == 0,
            advisory_only=True,
            mutation_ids=list(applied_ids)[:10],
            planned_payload_overrides=sanitized,
            blocked_fields=blocked,
            warnings=[],
            explanation="Based on AI-selected best variant with applied safe mutations.",
        )
    except Exception:
        return None


def _build_compact_subtitle_plan(edit_plan: Any) -> Optional[AIMultiVariantRenderPlan]:
    try:
        subtitle_execution = getattr(edit_plan, "subtitle_execution", {}) or {}
        density = subtitle_execution.get("density", "")
        emphasis = subtitle_execution.get("emphasis_style", "")

        safe_mutations = getattr(edit_plan, "safe_render_mutations", {}) or {}
        mutations_list = safe_mutations.get("mutations", []) or []
        sub_mutation_ids = [
            m.get("mutation_id", "")
            for m in mutations_list
            if isinstance(m, dict) and m.get("category") == "subtitle"
        ]

        if not density and not emphasis and not sub_mutation_ids:
            return None

        overrides: dict = {"ai_mode": "advisory"}
        if density and density not in ("none", ""):
            overrides["subtitle_density"] = density
        if emphasis and emphasis not in ("none", ""):
            overrides["subtitle_emphasis"] = emphasis

        sanitized = sanitize_variant_payload_overrides(overrides)
        blocked = collect_blocked_fields(overrides)

        return AIMultiVariantRenderPlan(
            plan_id="mvplan_compact_subtitle",
            variant_id="compact_subtitle",
            label="Compact Subtitle Render Plan",
            renderable=True,
            safe_to_enqueue=len(blocked) == 0,
            advisory_only=True,
            mutation_ids=sub_mutation_ids[:5],
            planned_payload_overrides=sanitized,
            blocked_fields=blocked,
            warnings=[],
            explanation="Optimized subtitle density and emphasis based on AI analysis.",
        )
    except Exception:
        return None


def _build_creator_style_plan(edit_plan: Any) -> Optional[AIMultiVariantRenderPlan]:
    try:
        csa = getattr(edit_plan, "creator_style_adaptation", {}) or {}
        style = csa.get("adapted_style") or csa.get("detected_style") or ""
        confidence = float(csa.get("confidence", 0.0))

        creator_style_raw = getattr(edit_plan, "creator_style", {}) or {}
        if not style:
            style = creator_style_raw.get("style_label") or creator_style_raw.get("creator_style") or ""

        if not style or confidence < 0.40:
            return None

        camera = _STYLE_TO_CAMERA.get(style, "static")
        pacing = "fast_cut" if style in ("viral_tiktok",) else "standard"

        overrides: dict = {
            "ai_mode": "advisory",
            "creator_style": style,
            "camera_behavior": camera,
            "pacing_style": pacing,
        }
        sanitized = sanitize_variant_payload_overrides(overrides)
        blocked = collect_blocked_fields(overrides)

        return AIMultiVariantRenderPlan(
            plan_id="mvplan_creator_style",
            variant_id=f"creator_style_{style}",
            label="Creator Style Render Plan",
            renderable=True,
            safe_to_enqueue=len(blocked) == 0,
            advisory_only=True,
            mutation_ids=[],
            planned_payload_overrides=sanitized,
            blocked_fields=blocked,
            warnings=[] if confidence >= 0.60 else ["low_style_confidence"],
            explanation=f"Creator style '{style}' applied with camera={camera}, pacing={pacing}.",
        )
    except Exception:
        return None


def _build_retention_plan(edit_plan: Any) -> Optional[AIMultiVariantRenderPlan]:
    try:
        retention = getattr(edit_plan, "retention", {}) or {}
        score = retention.get("retention_score")
        if score is None:
            return None

        score = float(score)
        if score >= 70:
            return None  # retention is already good; no special plan needed

        pacing = "fast_cut" if score < 40 else "moderate"
        overrides: dict = {
            "ai_mode": "advisory",
            "pacing_style": pacing,
        }
        sanitized = sanitize_variant_payload_overrides(overrides)
        blocked = collect_blocked_fields(overrides)

        return AIMultiVariantRenderPlan(
            plan_id="mvplan_retention_optimized",
            variant_id="retention_optimized",
            label="Retention-Optimized Render Plan",
            renderable=True,
            safe_to_enqueue=len(blocked) == 0,
            advisory_only=True,
            mutation_ids=[],
            planned_payload_overrides=sanitized,
            blocked_fields=blocked,
            warnings=["low_retention_score"] if score < 40 else [],
            explanation=f"Retention score={score:.0f}: pacing adjusted to '{pacing}'.",
        )
    except Exception:
        return None


def _select_recommended(plans: list[AIMultiVariantRenderPlan]) -> Optional[str]:
    """Pick the recommended plan_id. Prefers safe_to_enqueue non-baseline plans."""
    if not plans:
        return None
    safe_non_baseline = [
        p for p in plans
        if p.safe_to_enqueue and p.plan_id != "mvplan_baseline"
    ]
    if safe_non_baseline:
        return safe_non_baseline[0].plan_id
    safe_any = [p for p in plans if p.safe_to_enqueue]
    if safe_any:
        return safe_any[0].plan_id
    return plans[0].plan_id


def _fallback_set(reason: str) -> AIMultiVariantRenderSet:
    baseline = AIMultiVariantRenderPlan(
        plan_id="mvplan_baseline",
        variant_id="baseline",
        label="Baseline Safe Render Plan",
        renderable=True,
        safe_to_enqueue=True,
        advisory_only=True,
        mutation_ids=[],
        planned_payload_overrides={"ai_mode": "advisory", "pacing_style": "standard"},
        blocked_fields=[],
        warnings=[f"fallback_reason:{reason}"],
        explanation="Fallback baseline — planner error encountered.",
    )
    return AIMultiVariantRenderSet(
        available=False,
        mode="planning_only",
        plans=[baseline],
        recommended_plan_id="mvplan_baseline",
        warnings=[f"multivariant_planner_error:{reason}"],
    )
