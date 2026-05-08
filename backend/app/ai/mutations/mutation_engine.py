"""
mutation_engine.py — Safe bounded AI render mutation engine. Phase 27.

Converts validated execution recommendations into a compact bounded set of
AI guidance metadata mutations WITHOUT mutating dangerous render execution
fields.

Phase 27 is the FIRST phase where AI-decided metadata mutations are allowed.
All mutations are deterministic, bounded, and safety-gated.

Design rules:
- Deterministic only.
- Never raises.
- Only allowed keys are written (sanitize_mutation_changes enforces this).
- Payload copy always used via apply_safe_mutation — original never touched.
- No FFmpeg mutation. No timing mutation. No subtitle timing rewrite.
- No segment reorder. No render queue mutation. No executor override.

Public API:
    build_safe_mutations(edit_plan, payload=None, context=None) -> AISafeMutationPack
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.mutations.mutation_schema import (
    AISafeMutation,
    AISafeMutationPack,
    VALID_MUTATION_CATEGORIES,
)
from app.ai.mutations.mutation_safety import sanitize_mutation_changes, is_mutation_safe

logger = logging.getLogger("app.ai.mutations")

# Minimum confidence thresholds per category
_CONFIDENCE_GATE: dict[str, float] = {
    "subtitle": 0.40,
    "pacing": 0.50,
    "camera": 0.50,
    "creator_style": 0.50,
    "visual_rhythm": 0.35,
}

# Map of creator-style → safe camera behavior hint
_STYLE_TO_CAMERA_SAFE: dict[str, str] = {
    "viral_tiktok": "dynamic_safe",
    "cinematic": "dynamic_safe",
    "educational": "static",
    "podcast": "static",
    "product_demo": "static",
    "storytelling": "dynamic_safe",
    "commentary": "dynamic_safe",
    "interview": "static",
    "safe_generic": "static",
}

# Canonical pacing style values
_PACING_STYLE_MAP: dict[str, str] = {
    "fast_cuts": "fast_hook",
    "fast": "fast_hook",
    "retention_optimized": "retention_focus",
    "story_driven": "story_driven",
    "standard": "standard",
    "default": "default",
    "slow_build": "slow_build",
    "medium": "standard",
    "slow": "slow_build",
}


def build_safe_mutations(
    edit_plan: Any,
    payload: Optional[Any] = None,
    context: Optional[dict] = None,
) -> AISafeMutationPack:
    """Build a bounded pack of safe AI guidance metadata mutations.

    Reads execution_recommendations (Phase 25) from the edit plan to derive
    mutations. Each mutation is validated through safety gates before being
    marked as applied. Unsafe or low-confidence mutations become blocked
    entries.

    Args:
        edit_plan:  AIEditPlan or None. Read-only source of AI metadata.
        payload:    Optional RenderRequest-like object or dict. Used for
                    context only; never mutated in-place by this function.
        context:    Optional metadata dict.

    Returns:
        AISafeMutationPack with applied and blocked mutation lists. Never raises.
    """
    try:
        return _build(edit_plan, payload, context or {})
    except Exception as exc:
        logger.debug("build_safe_mutations_failed: %s", exc)
        return _fallback_pack(str(exc))


# ── Internal builder ──────────────────────────────────────────────────────────

def _build(edit_plan: Any, payload: Optional[Any], context: dict) -> AISafeMutationPack:
    if edit_plan is None:
        logger.info("ai_safe_mutation_skipped: no_edit_plan")
        return AISafeMutationPack(
            available=False,
            advisory_mode=True,
            warnings=["no_edit_plan"],
        )

    mutations: list[AISafeMutation] = []
    applied_ids: list[str] = []
    blocked_ids: list[str] = []

    # ── Build mutations from Phase 25 execution recommendations ───────────────
    er = _safe_dict(getattr(edit_plan, "execution_recommendations", {}))
    recs = er.get("recommendations") or []

    for rec in recs:
        if not isinstance(rec, dict):
            continue
        mut = _build_from_recommendation(rec, edit_plan)
        if mut is None:
            continue
        mutations.append(mut)
        if mut.applied:
            applied_ids.append(mut.mutation_id)
            logger.info(
                "ai_safe_mutation_applied mutation_id=%s category=%s confidence=%.4f",
                mut.mutation_id, mut.category, mut.confidence,
            )
        else:
            blocked_ids.append(mut.mutation_id)
            logger.info(
                "ai_safe_mutation_blocked mutation_id=%s reason=%s",
                mut.mutation_id,
                mut.warnings[0] if mut.warnings else "unsafe",
            )

    # ── Fallback: if no recommendations available, report skipped ─────────────
    if not mutations and not recs:
        logger.info("ai_safe_mutation_skipped: no_recommendations")
        return AISafeMutationPack(
            available=True,
            advisory_mode=True,
            warnings=["no_recommendations_available"],
        )

    logger.info(
        "ai_safe_mutations_built total=%d applied=%d blocked=%d",
        len(mutations), len(applied_ids), len(blocked_ids),
    )

    return AISafeMutationPack(
        available=True,
        advisory_mode=len(applied_ids) == 0,
        mutations=mutations,
        applied_mutation_ids=applied_ids,
        blocked_mutations=blocked_ids,
    )


# ── Per-category mutation builders ────────────────────────────────────────────

def _build_from_recommendation(rec: dict, edit_plan: Any) -> Optional[AISafeMutation]:
    """Map one Phase 25 recommendation dict to an AISafeMutation."""
    try:
        category = str(rec.get("category") or "")
        rec_id = str(rec.get("recommendation_id") or "")
        confidence = float(rec.get("confidence") or 0.0)
        safe_to_apply = bool(rec.get("safe_to_apply", False))
        settings = rec.get("recommended_settings") or {}

        if category == "safe_baseline":
            return _build_baseline_mutation(rec_id)
        elif category == "retention":
            return _build_retention_mutation(rec_id, confidence, safe_to_apply, settings)
        elif category == "creator_style":
            return _build_creator_style_mutation(rec_id, confidence, safe_to_apply, settings)
        elif category == "subtitle":
            return _build_subtitle_mutation(rec_id, confidence, safe_to_apply, settings)
        elif category == "visual_rhythm":
            return _build_visual_rhythm_mutation(rec_id, confidence, safe_to_apply, settings)
        elif category == "pacing":
            return _build_pacing_mutation(rec_id, confidence, safe_to_apply, settings)
        else:
            return None
    except Exception as exc:
        logger.debug("_build_from_recommendation_failed rec=%s: %s",
                     rec.get("recommendation_id"), exc)
        return None


def _build_baseline_mutation(rec_id: str) -> AISafeMutation:
    changes = sanitize_mutation_changes({"ai_mode": "advisory", "pacing_style": "default"})
    return AISafeMutation(
        mutation_id="m_safe_baseline",
        category="pacing",
        confidence=1.0,
        applied=True,
        safe=True,
        source_recommendation_id=rec_id,
        changes=changes,
        explanation=["Safe baseline — AI metadata fields only", "No render execution changes"],
    )


def _build_retention_mutation(
    rec_id: str, confidence: float, safe_to_apply: bool, settings: dict,
) -> AISafeMutation:
    pacing_raw = str(settings.get("pacing_style") or "standard")
    pacing_val = _PACING_STYLE_MAP.get(pacing_raw, pacing_raw)
    hook_density = str(settings.get("hook_density") or "")

    changes_in = {"pacing_style": pacing_val}
    if hook_density:
        changes_in["ai_mode"] = "advisory"
    changes = sanitize_mutation_changes(changes_in)

    threshold = _CONFIDENCE_GATE["pacing"]
    safe = safe_to_apply and confidence >= threshold and is_mutation_safe(changes)
    warnings = [] if safe else [f"confidence_below_threshold({confidence:.2f}<{threshold})"]

    return AISafeMutation(
        mutation_id=f"m_retention_{pacing_val}",
        category="pacing",
        confidence=confidence,
        applied=safe,
        safe=safe,
        source_recommendation_id=rec_id,
        changes=changes if safe else {},
        warnings=warnings,
        explanation=[
            f"Retention pacing: {pacing_val}",
            "Applied to AI guidance metadata only",
        ],
    )


def _build_creator_style_mutation(
    rec_id: str, confidence: float, safe_to_apply: bool, settings: dict,
) -> AISafeMutation:
    creator_style = str(settings.get("creator_style") or "safe_generic")
    camera_raw = str(settings.get("camera_behavior") or "static")
    camera_val = _STYLE_TO_CAMERA_SAFE.get(creator_style, "dynamic_safe")

    changes = sanitize_mutation_changes({
        "creator_style": creator_style,
        "camera_behavior": camera_val,
    })

    threshold = _CONFIDENCE_GATE["creator_style"]
    safe = safe_to_apply and confidence >= threshold and is_mutation_safe(changes)
    warnings = [] if safe else [f"confidence_below_threshold({confidence:.2f}<{threshold})"]

    style_label = creator_style.replace("_", " ").title()
    return AISafeMutation(
        mutation_id=f"m_creator_style_{creator_style}",
        category="creator_style",
        confidence=confidence,
        applied=safe,
        safe=safe,
        source_recommendation_id=rec_id,
        changes=changes if safe else {},
        warnings=warnings,
        explanation=[
            f"Creator style: {style_label}",
            f"Camera behavior: {camera_val}",
        ],
    )


def _build_subtitle_mutation(
    rec_id: str, confidence: float, safe_to_apply: bool, settings: dict,
) -> AISafeMutation:
    density = str(settings.get("subtitle_density") or "normal")
    emphasis_raw = str(settings.get("subtitle_emphasis") or "none")
    emphasis = emphasis_raw if emphasis_raw not in ("none", "") else None

    changes_in = {"subtitle_density": density}
    if emphasis:
        changes_in["subtitle_emphasis"] = emphasis
    changes = sanitize_mutation_changes(changes_in)

    threshold = _CONFIDENCE_GATE["subtitle"]
    safe = safe_to_apply and confidence >= threshold and is_mutation_safe(changes)
    warnings = [] if safe else [f"confidence_below_threshold({confidence:.2f}<{threshold})"]

    return AISafeMutation(
        mutation_id="m_subtitle_density",
        category="subtitle",
        confidence=confidence,
        applied=safe,
        safe=safe,
        source_recommendation_id=rec_id,
        changes=changes if safe else {},
        warnings=warnings,
        explanation=[
            f"Subtitle density: {density}",
            f"Emphasis: {emphasis or 'none'}",
        ],
    )


def _build_visual_rhythm_mutation(
    rec_id: str, confidence: float, safe_to_apply: bool, settings: dict,
) -> AISafeMutation:
    mode_raw = str(settings.get("visual_rhythm_mode") or "moderate")
    # Map to conservative safe values
    mode_val = {"energetic": "beat_light", "moderate": "beat_light", "calm": "beat_none"}.get(
        mode_raw, "beat_light"
    )

    changes = sanitize_mutation_changes({"visual_rhythm_mode": mode_val})

    threshold = _CONFIDENCE_GATE["visual_rhythm"]
    safe = safe_to_apply and confidence >= threshold and is_mutation_safe(changes)
    warnings = [] if safe else [f"confidence_below_threshold({confidence:.2f}<{threshold})"]

    return AISafeMutation(
        mutation_id="m_visual_rhythm",
        category="visual_rhythm",
        confidence=confidence,
        applied=safe,
        safe=safe,
        source_recommendation_id=rec_id,
        changes=changes if safe else {},
        warnings=warnings,
        explanation=[f"Visual rhythm: {mode_val}"],
    )


def _build_pacing_mutation(
    rec_id: str, confidence: float, safe_to_apply: bool, settings: dict,
) -> AISafeMutation:
    pacing_raw = str(settings.get("pacing_style") or "standard")
    pacing_val = _PACING_STYLE_MAP.get(pacing_raw, pacing_raw)
    changes = sanitize_mutation_changes({"pacing_style": pacing_val})

    threshold = _CONFIDENCE_GATE["pacing"]
    safe = safe_to_apply and confidence >= threshold and is_mutation_safe(changes)
    warnings = [] if safe else [f"confidence_below_threshold({confidence:.2f}<{threshold})"]

    return AISafeMutation(
        mutation_id=f"m_pacing_{pacing_val}",
        category="pacing",
        confidence=confidence,
        applied=safe,
        safe=safe,
        source_recommendation_id=rec_id,
        changes=changes if safe else {},
        warnings=warnings,
        explanation=[f"Pacing: {pacing_val}", "Story-driven pacing guidance"],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_dict(val: Any) -> dict:
    return val if isinstance(val, dict) else {}


def _fallback_pack(reason: str) -> AISafeMutationPack:
    logger.info("ai_safe_mutation_skipped reason=%s", reason)
    return AISafeMutationPack(
        available=False,
        advisory_mode=True,
        warnings=[f"mutation_engine_error:{reason}"],
    )
