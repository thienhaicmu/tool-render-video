"""
variant_generator.py — Deterministic AI variant plan generator. Phase 21.

Generates advisory render variants from existing AI metadata.
Never raises. Never enqueues render jobs. Never mutates payload.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from app.ai.variants.variant_schema import (
    AIVariantPlan,
    AIVariantSet,
    _VARIANT_COUNT_MAX,
    clamp_variant_count,
)
from app.ai.variants.variant_safety import sanitize_variant_changes, is_variant_safe
from app.ai.variants.variant_scoring import score_variant

logger = logging.getLogger("app.ai.variants")


def generate_variant_plans(
    edit_plan: Any,
    context: Optional[dict] = None,
    count: int = 3,
) -> AIVariantSet:
    """Generate up to `count` advisory render variant plans.

    Always includes safe_baseline. Never raises. Never mutates edit_plan or context.
    Returns AIVariantSet with mode='advisory', all safe_to_render=False by default
    unless safety gate passes.
    """
    try:
        return _generate(edit_plan, context or {}, clamp_variant_count(count))
    except Exception as exc:
        logger.debug("generate_variant_plans_failed: %s", exc)
        return AIVariantSet(
            available=False,
            mode="advisory",
            warnings=[f"variant_generation_error:{type(exc).__name__}"],
        )


def _generate(edit_plan: Any, context: dict, count: int) -> AIVariantSet:
    warnings: list[str] = []
    candidates: list[AIVariantPlan] = []

    # --- Always start with safe_baseline ---
    baseline = _make_baseline(edit_plan)
    candidates.append(baseline)

    # --- Candidate factories in priority order ---
    factories = [
        _make_retention_variant,
        _make_hook_variant,
        _make_subtitle_variant,
        _make_pacing_variant,
        _make_story_variant,
        _make_creator_style_variant,
    ]

    for factory in factories:
        if len(candidates) >= count:
            break
        try:
            variant = factory(edit_plan, context)
            if variant is not None:
                candidates.append(variant)
        except Exception as exc:
            logger.debug("variant_factory_failed %s: %s", factory.__name__, exc)
            warnings.append(f"variant_factory_skipped:{factory.__name__}")

    # Apply safety gate and scoring to all candidates
    for v in candidates:
        v.suggested_changes = sanitize_variant_changes(v.suggested_changes)
        v.safe_to_render = is_variant_safe(v, context)
        result = score_variant(v, edit_plan, context)
        v.expected_gain = float(result.get("expected_gain", 0.0))
        if result.get("warnings"):
            v.warnings.extend(result["warnings"])

    # Cap to max
    variants = candidates[:_VARIANT_COUNT_MAX]

    # Recommend the highest-scoring safe variant (baseline as fallback)
    safe_variants = [v for v in variants if v.safe_to_render]
    if safe_variants:
        best = max(safe_variants, key=lambda v: v.expected_gain)
        recommended_id = best.variant_id
    else:
        recommended_id = baseline.variant_id

    logger.info(
        "ai_variant_plans_generated count=%d safe=%d recommended=%s",
        len(variants),
        len(safe_variants),
        recommended_id,
    )

    return AIVariantSet(
        available=True,
        mode="advisory",
        variants=variants,
        recommended_variant_id=recommended_id,
        warnings=warnings,
    )


# ── Variant factories ────────────────────────────────────────────────────────

def _make_baseline(edit_plan: Any) -> AIVariantPlan:
    """Safe baseline variant — current settings, no changes."""
    pacing_style = "default"
    try:
        pacing = getattr(edit_plan, "pacing", None)
        if pacing is not None:
            pacing_style = str(getattr(pacing, "pacing_style", "default") or "default")
    except Exception:
        pass

    return AIVariantPlan(
        variant_id=_make_id("baseline"),
        label="Baseline Safe",
        purpose="safe_baseline",
        confidence=0.90,
        risk="low",
        suggested_changes={"pacing_style": pacing_style},
        safe_to_render=False,  # will be set after safety gate
    )


def _make_retention_variant(edit_plan: Any, context: dict) -> Optional[AIVariantPlan]:
    """Retention-focused variant — suggested if retention score is low."""
    retention = {}
    try:
        retention = dict(getattr(edit_plan, "retention", {}) or {})
    except Exception:
        pass

    score = retention.get("overall_retention_score")
    if score is None:
        return None

    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return None

    confidence = 0.70 if score_f < 60 else 0.55
    return AIVariantPlan(
        variant_id=_make_id("retention"),
        label="Retention Boost",
        purpose="retention",
        confidence=confidence,
        risk="low",
        suggested_changes={
            "pacing_style": "fast",
            "subtitle_emphasis": "high",
        },
    )


def _make_hook_variant(edit_plan: Any, context: dict) -> Optional[AIVariantPlan]:
    """Hook-focused variant — suggested if weak_hook issue detected."""
    so = {}
    try:
        so = dict(getattr(edit_plan, "story_optimization", {}) or {})
    except Exception:
        pass

    issues = so.get("issues") or []
    has_weak_hook = any(
        isinstance(i, dict) and i.get("issue_type") == "weak_hook"
        for i in issues
    )
    if not has_weak_hook:
        return None

    return AIVariantPlan(
        variant_id=_make_id("hook"),
        label="Stronger Hook",
        purpose="hook",
        confidence=0.68,
        risk="low",
        suggested_changes={
            "pacing_style": "fast",
            "subtitle_emphasis": "high",
            "camera_behavior": "dramatic_push",
        },
    )


def _make_subtitle_variant(edit_plan: Any, context: dict) -> Optional[AIVariantPlan]:
    """Compact subtitle variant — suggested when subtitle execution is available."""
    se = {}
    try:
        se = dict(getattr(edit_plan, "subtitle_execution", {}) or {})
    except Exception:
        pass

    if not se.get("available"):
        return None

    global_hint = se.get("global_hint") or {}
    current_density = global_hint.get("density_mode") if isinstance(global_hint, dict) else None
    target_density = "compact" if current_density != "compact" else "normal"

    return AIVariantPlan(
        variant_id=_make_id("subtitle"),
        label="Compact Subtitle",
        purpose="subtitle",
        confidence=0.72,
        risk="low",
        suggested_changes={
            "subtitle_density": target_density,
            "subtitle_emphasis": "medium",
        },
    )


def _make_pacing_variant(edit_plan: Any, context: dict) -> Optional[AIVariantPlan]:
    """Faster pacing variant — suggested when energy is available."""
    pacing = None
    try:
        pacing = getattr(edit_plan, "pacing", None)
    except Exception:
        pass

    if pacing is None:
        return None

    energy = getattr(pacing, "energy_level", None)
    current_style = str(getattr(pacing, "pacing_style", "default") or "default")

    # Suggest faster pacing only when not already fast
    if current_style == "fast":
        return None

    confidence = 0.62
    try:
        if energy is not None and float(energy) > 0.5:
            confidence = 0.70
    except (TypeError, ValueError):
        pass

    return AIVariantPlan(
        variant_id=_make_id("pacing"),
        label="Faster Pacing",
        purpose="pacing",
        confidence=confidence,
        risk="low",
        suggested_changes={
            "pacing_style": "fast",
        },
    )


def _make_story_variant(edit_plan: Any, context: dict) -> Optional[AIVariantPlan]:
    """Story arc variant — suggested when narrative score is low."""
    so = {}
    try:
        so = dict(getattr(edit_plan, "story_optimization", {}) or {})
    except Exception:
        pass

    if not so.get("available"):
        return None

    score = so.get("narrative_score")
    if score is None:
        return None

    try:
        score_f = float(score)
    except (TypeError, ValueError):
        return None

    if score_f >= 70:
        return None

    return AIVariantPlan(
        variant_id=_make_id("story"),
        label="Story Arc",
        purpose="story",
        confidence=0.60,
        risk="medium",
        suggested_changes={
            "pacing_style": "slow_build",
            "camera_behavior": "slow_reveal",
        },
    )


def _make_creator_style_variant(edit_plan: Any, context: dict) -> Optional[AIVariantPlan]:
    """Creator style variant — suggested when a dominant style is classified."""
    cs = {}
    try:
        cs = dict(getattr(edit_plan, "creator_style", {}) or {})
    except Exception:
        pass

    dominant_style = cs.get("dominant_style")
    if not dominant_style or dominant_style in ("unknown", ""):
        return None

    return AIVariantPlan(
        variant_id=_make_id("creator_style"),
        label="Creator Style Match",
        purpose="creator_style",
        confidence=0.65,
        risk="low",
        suggested_changes={
            "creator_style": str(dominant_style),
            "ai_mode": _style_to_mode(dominant_style),
        },
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_id(purpose: str) -> str:
    """Generate a short deterministic-looking variant ID."""
    short = uuid.uuid4().hex[:8]
    return f"variant_{purpose}_{short}"


_STYLE_MODE_MAP: dict[str, str] = {
    "anime_edit":              "viral_tiktok",
    "high_energy_reaction":    "viral_tiktok",
    "gameplay_highlight":      "viral_tiktok",
    "podcast_viral":           "viral_tiktok",
    "storytelling_cinematic":  "cinematic",
    "documentary_clean":       "cinematic",
    "educational_focus":       "educational",
    "motivation_short":        "viral_tiktok",
    "interview_clip":          "cinematic",
    "calm_minimal":            "cinematic",
}


def _style_to_mode(style: str) -> str:
    return _STYLE_MODE_MAP.get(style, "viral_tiktok")
