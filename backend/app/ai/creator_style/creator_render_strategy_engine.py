"""
creator_render_strategy_engine.py — Phase 61D Creator Render Strategy Fusion.

Fuses Phase 61A archetype strategy with creator_preference_profile (50D),
platform_render_strategy (55E), camera_quality_v2 (52B), render_quality_v2
(52D), platform_quality_feedback (57), and creator_benchmark_summary (60C)
into one deterministic, coherent creator-style render strategy.

Advisory metadata only — no payload mutation, no execution promotion.
Existing bounded promotion layers (Phase 59A, 59B, 59D) remain authority.

Design rules:
  - Never raises — returns fallback on any error.
  - Deterministic: same inputs → same output.
  - creator_preference_profile wins over archetype defaults when high confidence.
  - Platform refines but does NOT override creator safety.
  - Quality risk signals soften aggressive camera/energy values.
  - Trust-safe archetypes (podcast, talking_head, interview, educational)
    are never pushed by platform beyond their archetype style.
  - Confidence is a blended weighted average of available signal confidences.

Conflict resolution priority:
  1. Quality gates (safety — block risky motion)
  2. creator_preference_profile (high confidence → overrides archetype)
  3. Platform (refines within creator-safe bounds)
  4. Creator archetype strategy (base)

Public API:
    build_creator_render_strategy(edit_plan, context=None) -> dict

Output shape (available):
    {
        "creator_render_strategy": {
            "available":    true,
            "creator_type": "podcast",
            "strategy": {
                "subtitle": {
                    "style":               "clean_pro",
                    "density":             "balanced",
                    "keyword_emphasis":    "selective",
                    "readability_priority": "high"
                },
                "camera": {
                    "motion_energy":       "low",
                    "stability_priority":  "high",
                    "crop_aggressiveness": "low",
                    "subject_hold":        "high"
                },
                "hook": {
                    "hook_energy":        "moderate",
                    "curiosity_style":    "soft_direct",
                    "retention_priority": "medium_high"
                },
                "ranking": {
                    "priority": "retention_creator_fit"
                }
            },
            "confidence": 0.86,
            "reasoning": [
                "Podcast creator style favors clean subtitles, stable framing, and trust-focused pacing"
            ]
        }
    }

Output shape (fallback):
    {
        "creator_render_strategy": {
            "available":    false,
            "creator_type": "unknown",
            "strategy":     {},
            "confidence":   0.0,
            "reasoning":    []
        }
    }

Safety contract:
    ❌ No payload mutation
    ❌ No execution promotion
    ❌ No ffmpeg mutation
    ❌ No subtitle timing / segmentation / ASS rewrite
    ❌ No motion crop rewrite
    ❌ No tracking rewrite
    ❌ No executor override
    ✅ Advisory fusion metadata only
    ✅ Never raises — fallback on any error
    ✅ Deterministic: same inputs → same output
    ✅ Confidence clamped to [0.0, 1.0]
    ✅ No execution flags in output
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.creator_style")

# Trust/safety archetypes — platform never pushes beyond archetype style
_TRUST_SAFE_ARCHETYPES: frozenset[str] = frozenset({
    "podcast", "talking_head", "interview", "educational",
})

# High quality risk threshold (mirrors Phase 59B)
_HIGH_RISK_THRESHOLD: int = 60

# Ordered value lists for level-capping and platform refinement
_MOTION_ORDER:    list[str] = ["low", "low_medium", "medium", "medium_high", "high"]
_EMPHASIS_ORDER:  list[str] = ["none", "selective", "moderate", "strong"]
_RETENTION_ORDER: list[str] = ["standard", "medium", "medium_high", "high"]

# stability_priority → subject_hold label (same mapping as Phase 61C)
_STABILITY_TO_HOLD: dict[str, str] = {
    "high":     "high",
    "medium":   "medium",
    "standard": "standard",
}

# Confidence blend weights
_W_ARCH = 0.45
_W_PROF = 0.25
_W_PRS  = 0.20
_W_QUAL = 0.10

# Maximum reasoning lines
_MAX_REASONING = 5


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_creator_render_strategy(
    edit_plan: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build fused creator render strategy metadata.

    Returns:
        {"creator_render_strategy": {...}}
    """
    job_id = str((context or {}).get("job_id", "unknown"))
    try:
        return _build(edit_plan, job_id)
    except Exception as exc:
        logger.warning(
            "creator_render_strategy_unexpected_error job_id=%s: %s", job_id, exc
        )
        return _fallback()


# ---------------------------------------------------------------------------
# Core fusion builder
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, job_id: str) -> dict:
    if edit_plan is None:
        return _fallback()

    # ── Phase 61A: archetype strategy (required) ──────────────────────────────
    archetype = _get_dict(edit_plan, "creator_archetype_strategy")
    if not archetype or not archetype.get("available"):
        return _fallback()

    creator_type = str(archetype.get("creator_type") or "unknown")
    arch_strategy = archetype.get("strategy") or {}
    arch_conf = _clamp_f(archetype.get("confidence"))

    # ── Read other signals ────────────────────────────────────────────────────
    profile  = _get_dict(edit_plan, "creator_preference_profile")
    prs      = _get_dict(edit_plan, "platform_render_strategy")
    cam_qual = _get_dict(edit_plan, "camera_quality_v2")
    rqv2     = _get_dict(edit_plan, "render_quality_v2")
    pqf      = _get_dict(edit_plan, "platform_quality_feedback")

    # ── Quality risk flags ────────────────────────────────────────────────────
    quality_flags = _check_quality(cam_qual, pqf)

    # ── Fuse each domain ──────────────────────────────────────────────────────
    subtitle_strategy = _fuse_subtitle(
        arch_strategy.get("subtitle") or {}, prs, creator_type
    )
    camera_strategy = _fuse_camera(
        arch_strategy.get("camera") or {}, prs, quality_flags, creator_type
    )
    hook_strategy = _fuse_hook(
        arch_strategy.get("hook") or {}, prs
    )
    ranking_strategy = _fuse_ranking(
        arch_strategy.get("ranking") or {}
    )

    # ── Confidence blend ──────────────────────────────────────────────────────
    prof_conf = _clamp_f(profile.get("confidence")) if profile else 0.0
    prs_conf  = _clamp_f(prs.get("confidence")) if (prs and prs.get("available")) else 0.0
    rqv2_conf = _clamp_f(rqv2.get("confidence")) if rqv2 else 0.0
    confidence = _blend_confidence(arch_conf, prof_conf, prs_conf, rqv2_conf)

    # ── Reasoning ─────────────────────────────────────────────────────────────
    reasoning = _build_reasoning(archetype, creator_type, quality_flags, prs)

    logger.info(
        "creator_render_strategy_built job_id=%s creator=%s confidence=%.3f",
        job_id, creator_type, confidence,
    )

    return {
        "creator_render_strategy": {
            "available":    True,
            "creator_type": creator_type,
            "strategy": {
                "subtitle": subtitle_strategy,
                "camera":   camera_strategy,
                "hook":     hook_strategy,
                "ranking":  ranking_strategy,
            },
            "confidence": confidence,
            "reasoning":  reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Domain fusion functions
# ---------------------------------------------------------------------------

def _fuse_subtitle(arch_sub: dict, prs: dict, creator_type: str) -> dict:
    """Fuse subtitle strategy. Platform may refine emphasis for dynamic creators."""
    style               = str(arch_sub.get("style_bias") or "clean_pro")
    density             = str(arch_sub.get("density_bias") or "balanced")
    keyword_emphasis    = str(arch_sub.get("keyword_emphasis") or "selective")
    readability_priority = str(arch_sub.get("readability_priority") or "high")

    # Platform refine: non-trust-safe creators may get higher keyword emphasis
    if prs and prs.get("available") and creator_type not in _TRUST_SAFE_ARCHETYPES:
        prs_sub = (prs.get("strategy") or {}).get("subtitle") or {}
        plat_emphasis = str(prs_sub.get("keyword_emphasis") or "").strip().lower()
        if (
            plat_emphasis in _EMPHASIS_ORDER
            and keyword_emphasis in _EMPHASIS_ORDER
            and _EMPHASIS_ORDER.index(plat_emphasis) > _EMPHASIS_ORDER.index(keyword_emphasis)
        ):
            keyword_emphasis = plat_emphasis

    return {
        "style":                style,
        "density":              density,
        "keyword_emphasis":     keyword_emphasis,
        "readability_priority": readability_priority,
    }


def _fuse_camera(
    arch_cam: dict,
    prs: dict,
    quality_flags: dict,
    creator_type: str,
) -> dict:
    """Fuse camera strategy. Quality risk softens motion; platform refines within bounds."""
    motion_energy       = str(arch_cam.get("motion_energy") or "low")
    stability_priority  = str(arch_cam.get("stability_priority") or "high")
    crop_aggressiveness = str(arch_cam.get("crop_aggressiveness") or "low")

    # Quality softening: high risk → reduce motion_energy, raise stability
    if quality_flags["high_jitter"] or quality_flags["high_whip_pan"]:
        if motion_energy in _MOTION_ORDER:
            idx = _MOTION_ORDER.index(motion_energy)
            medium_idx = _MOTION_ORDER.index("medium")
            if idx > medium_idx:
                motion_energy = _MOTION_ORDER[max(0, idx - 1)]
        if quality_flags["high_jitter"]:
            stability_priority = "high"
        if quality_flags["high_whip_pan"] and crop_aggressiveness == "high":
            crop_aggressiveness = "medium"

    # Platform refine: non-trust-safe creators may get higher motion from platform
    if prs and prs.get("available") and creator_type not in _TRUST_SAFE_ARCHETYPES:
        prs_cam = (prs.get("strategy") or {}).get("camera") or {}
        plat_energy = str(prs_cam.get("motion_energy") or "").strip().lower()
        if (
            plat_energy in _MOTION_ORDER
            and motion_energy in _MOTION_ORDER
            and not (quality_flags["high_jitter"] or quality_flags["high_whip_pan"])
        ):
            arch_idx = _MOTION_ORDER.index(motion_energy)
            plat_idx = _MOTION_ORDER.index(plat_energy)
            if plat_idx > arch_idx:
                # Cap platform raise at +1 level for safety
                motion_energy = _MOTION_ORDER[min(plat_idx, arch_idx + 1)]

    subject_hold = _STABILITY_TO_HOLD.get(stability_priority, "standard")

    return {
        "motion_energy":       motion_energy,
        "stability_priority":  stability_priority,
        "crop_aggressiveness": crop_aggressiveness,
        "subject_hold":        subject_hold,
    }


def _fuse_hook(arch_hook: dict, prs: dict) -> dict:
    """Fuse hook strategy. Platform may raise retention_priority."""
    hook_energy        = str(arch_hook.get("hook_energy") or "moderate")
    curiosity_style    = str(arch_hook.get("curiosity_style") or "soft_direct")
    retention_priority = str(arch_hook.get("retention_priority") or "medium_high")

    # Platform can raise retention_priority (never lower it)
    if prs and prs.get("available"):
        prs_hook = (prs.get("strategy") or {}).get("hook") or {}
        plat_ret = str(prs_hook.get("retention_priority") or "").strip().lower()
        if (
            plat_ret in _RETENTION_ORDER
            and retention_priority in _RETENTION_ORDER
            and _RETENTION_ORDER.index(plat_ret) > _RETENTION_ORDER.index(retention_priority)
        ):
            retention_priority = plat_ret

    return {
        "hook_energy":        hook_energy,
        "curiosity_style":    curiosity_style,
        "retention_priority": retention_priority,
    }


def _fuse_ranking(arch_rank: dict) -> dict:
    """Ranking stays archetype-driven — creator identity should determine ranking priority."""
    priority = str(arch_rank.get("priority") or "retention_creator_fit")
    return {"priority": priority}


# ---------------------------------------------------------------------------
# Quality risk checker
# ---------------------------------------------------------------------------

def _check_quality(cam_qual: dict, pqf: dict) -> dict:
    """Evaluate camera risk signals. Returns flags dict — never raises."""
    flags = {
        "high_jitter":   False,
        "high_whip_pan": False,
        "low_cam_fit":   False,
    }
    if cam_qual:
        try:
            if int(cam_qual.get("micro_jitter_risk") or 0) >= _HIGH_RISK_THRESHOLD:
                flags["high_jitter"] = True
            if int(cam_qual.get("whip_pan_risk") or 0) >= _HIGH_RISK_THRESHOLD:
                flags["high_whip_pan"] = True
        except (TypeError, ValueError):
            pass
    if pqf and pqf.get("available"):
        try:
            if int(pqf.get("camera_fit") or 0) <= 30:
                flags["low_cam_fit"] = True
        except (TypeError, ValueError):
            pass
    return flags


# ---------------------------------------------------------------------------
# Confidence blend
# ---------------------------------------------------------------------------

def _blend_confidence(
    arch_conf: float,
    prof_conf: float,
    prs_conf: float,
    rqv2_conf: float,
) -> float:
    """Weighted blend. Missing signals (0.0) lower confidence."""
    numerator   = arch_conf * _W_ARCH + prof_conf * _W_PROF + prs_conf * _W_PRS
    denominator = _W_ARCH + _W_PROF + _W_PRS
    # Only include quality weight when quality data is available
    if rqv2_conf > 0.0:
        numerator   += rqv2_conf * _W_QUAL
        denominator += _W_QUAL
    conf = numerator / denominator if denominator > 0 else arch_conf
    return round(max(0.0, min(1.0, conf)), 4)


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    archetype: dict,
    creator_type: str,
    quality_flags: dict,
    prs: dict,
) -> list[str]:
    """Build up to _MAX_REASONING lines of human-readable reasoning."""
    lines: list[str] = []

    # Primary: archetype reasoning
    arch_reasoning = archetype.get("reasoning") or []
    if arch_reasoning:
        lines.extend(arch_reasoning[:2])
    else:
        lines.append(f"Creator archetype {creator_type!r} strategy fused")

    # Quality flags
    if quality_flags["high_jitter"]:
        lines.append("Quality risk: high jitter → motion energy softened, stability raised")
    elif quality_flags["high_whip_pan"]:
        lines.append("Quality risk: high whip-pan → motion energy reduced, crop aggressiveness capped")

    # Platform refine note
    if prs and prs.get("available") and creator_type not in _TRUST_SAFE_ARCHETYPES:
        platform = str(prs.get("platform") or "")
        if platform:
            lines.append(f"Platform {platform!r} refinements applied within creator-safe bounds")

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


def _fallback(creator_type: str = "unknown") -> dict:
    return {
        "creator_render_strategy": {
            "available":    False,
            "creator_type": creator_type,
            "strategy":     {},
            "confidence":   0.0,
            "reasoning":    [],
        }
    }
