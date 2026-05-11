"""
fusion_engine.py — Creator Preference Fusion Engine. Phase 50D.

Fuses all creator intelligence signals into one unified, deterministic
CreatorPreferenceProfile.  Reads from Phase 50A/B/C packs plus Phase 42–47
signal fields.  Advisory metadata only — no render mutation.

Public API:
    fuse_creator_preferences(edit_plan) -> CreatorPreferenceProfile

Safety contract:
    ❌ No render pipeline rewrite
    ❌ No subtitle timing rewrite
    ❌ No motion_crop rewrite
    ❌ No FFmpeg mutation
    ❌ No executor override
    ❌ No autonomous execution
    ✅ Deterministic — same inputs always produce same output
    ✅ Never raises
"""
from __future__ import annotations

import logging
from typing import Any

from app.ai.creator_fusion.fusion_schema import (
    CreatorPreferenceProfile,
    SubtitleFusionProfile,
    CameraFusionProfile,
    ClipFusionProfile,
    MarketAlignmentFusion,
    QualityAlignmentFusion,
)
from app.ai.creator_fusion.conflict_resolver import (
    resolve_style_conflict,
    resolve_emphasis_conflict,
    resolve_camera_conflict,
)

logger = logging.getLogger("app.ai.creator_fusion.engine")


def fuse_creator_preferences(edit_plan: Any) -> CreatorPreferenceProfile:
    """Fuse all creator intelligence signals into a unified profile. Never raises.

    Args:
        edit_plan: AIEditPlan with Phase 50A/B/C and Phase 42–47 fields (or None).

    Returns:
        CreatorPreferenceProfile — deterministic, creator-first, market-aware.
    """
    try:
        return _fuse(edit_plan)
    except Exception as exc:
        logger.debug("creator_preference_fusion_error: %s", exc)
        return CreatorPreferenceProfile(
            available=False,
            warnings=[f"fusion_error:{type(exc).__name__}"],
        )


# ---------------------------------------------------------------------------
# Core fusion
# ---------------------------------------------------------------------------

def _fuse(edit_plan: Any) -> CreatorPreferenceProfile:
    if edit_plan is None:
        return CreatorPreferenceProfile(available=False, warnings=["no_edit_plan"])

    # ── Collect signal sources ────────────────────────────────────────────────
    sub_pack  = _attr(edit_plan, "creator_subtitle_preference")
    cam_pack  = _attr(edit_plan, "creator_camera_preference")
    feedback  = _attr(edit_plan, "creator_feedback_intelligence")
    market    = _attr(edit_plan, "market_optimization_intelligence")
    quality   = _attr(edit_plan, "render_quality_evaluation")

    sub_pref  = (sub_pack.get("subtitle_preference") or {}) if sub_pack.get("available") else {}
    cam_pref  = (cam_pack.get("camera_preference")   or {}) if cam_pack.get("available") else {}

    mp            = market.get("market_profile") or {}
    target_market = str(mp.get("target_market") or "").lower()

    fb_patterns   = (
        feedback.get("learned_feedback_patterns")
        or feedback.get("learned_patterns")
        or {}
    )
    total_exports = _safe_int(
        feedback.get("total_exports")
        or fb_patterns.get("total_exports")
        or fb_patterns.get("total_signals")
    )

    reasoning:         list[str] = []
    conflicts_resolved: list[str] = []
    warnings:          list[str] = []

    # ── Build five profile dimensions ─────────────────────────────────────────
    subtitle   = _build_subtitle(sub_pref, target_market, reasoning, conflicts_resolved)
    camera     = _build_camera(cam_pref,  target_market, reasoning, conflicts_resolved)
    clip       = _build_clip(fb_patterns, target_market, quality, reasoning)
    market_al  = _build_market_alignment(mp, target_market, sub_pref, cam_pref)
    quality_al = _build_quality_alignment(quality, sub_pref, cam_pref, reasoning)

    # ── Fused confidence ──────────────────────────────────────────────────────
    sub_conf = _safe_float(sub_pref.get("confidence"))
    cam_conf = _safe_float(cam_pref.get("confidence"))
    confidence = _compute_confidence(sub_conf, cam_conf, total_exports, reasoning)

    available = any([
        subtitle.style        != "unknown",
        camera.motion_style   != "unknown",
        clip.content_style    != "unknown",
        market_al.target_market != "unknown",
    ])

    return CreatorPreferenceProfile(
        available=available,
        subtitle=subtitle,
        camera=camera,
        clip=clip,
        market_alignment=market_al,
        quality_alignment=quality_al,
        confidence=confidence,
        reasoning=reasoning[:5],
        conflicts_resolved=conflicts_resolved[:5],
        warnings=warnings[:5],
    )


# ---------------------------------------------------------------------------
# Subtitle fusion
# ---------------------------------------------------------------------------

def _build_subtitle(
    sub_pref: dict,
    target_market: str,
    reasoning: list[str],
    conflicts: list[str],
) -> SubtitleFusionProfile:
    if not sub_pref:
        return SubtitleFusionProfile()

    creator_style    = str(sub_pref.get("style")               or "unknown")
    creator_emphasis = str(sub_pref.get("keyword_emphasis")    or "unknown")
    creator_density  = str(sub_pref.get("density")             or "unknown")
    creator_read     = str(sub_pref.get("readability_priority") or "unknown")

    market_style    = _market_subtitle_style(target_market)
    market_emphasis = _market_emphasis(target_market)

    resolved_style, style_note = resolve_style_conflict(creator_style, market_style)
    if style_note:
        conflicts.append(style_note)

    resolved_emphasis, emp_note = resolve_emphasis_conflict(creator_emphasis, market_emphasis)
    if emp_note:
        conflicts.append(emp_note)

    if resolved_style != "unknown":
        reasoning.append(
            f"Subtitle: style={resolved_style!r} emphasis={resolved_emphasis!r}"
            f" (creator:{creator_style!r}, market:{market_style!r})"
        )

    return SubtitleFusionProfile(
        style=resolved_style,
        density=creator_density,
        keyword_emphasis=resolved_emphasis,
        readability_priority=creator_read,
    )


# ---------------------------------------------------------------------------
# Camera fusion
# ---------------------------------------------------------------------------

def _build_camera(
    cam_pref: dict,
    target_market: str,
    reasoning: list[str],
    conflicts: list[str],
) -> CameraFusionProfile:
    if not cam_pref:
        return CameraFusionProfile()

    creator_motion     = str(cam_pref.get("motion_style")        or "unknown")
    creator_crop       = str(cam_pref.get("crop_aggressiveness") or "unknown")
    creator_stability  = str(cam_pref.get("stability_priority")  or "unknown")
    creator_smoothness = str(cam_pref.get("smoothness_priority") or "unknown")

    market_motion = _market_camera_style(target_market)

    resolved_motion, motion_note = resolve_camera_conflict(creator_motion, market_motion)
    if motion_note:
        conflicts.append(motion_note)

    if resolved_motion != "unknown":
        reasoning.append(
            f"Camera: motion={resolved_motion!r} stability={creator_stability!r}"
            f" (creator:{creator_motion!r}, market:{market_motion!r})"
        )

    return CameraFusionProfile(
        motion_style=resolved_motion,
        crop_aggressiveness=creator_crop,
        stability_priority=creator_stability,
        smoothness_priority=creator_smoothness,
    )


# ---------------------------------------------------------------------------
# Clip profile
# ---------------------------------------------------------------------------

def _build_clip(
    fb_patterns: dict,
    target_market: str,
    quality: dict,
    reasoning: list[str],
) -> ClipFusionProfile:
    creator_style_raw = str(fb_patterns.get("creator_style_pattern") or "").lower()
    content_style     = _map_creator_style(creator_style_raw)
    if content_style == "unknown":
        content_style = _market_content_style(target_market)

    avg_rank      = _safe_float(fb_patterns.get("avg_export_rank"))
    total_exports = _safe_int(
        fb_patterns.get("total_exports") or fb_patterns.get("total_signals")
    )
    ranking_pref  = _derive_ranking_preference(avg_rank, total_exports, target_market, quality)

    if content_style != "unknown":
        reasoning.append(f"Content style: {content_style!r} (ranking_preference={ranking_pref!r})")

    return ClipFusionProfile(
        content_style=content_style,
        ranking_preference=ranking_pref,
    )


# ---------------------------------------------------------------------------
# Market alignment
# ---------------------------------------------------------------------------

def _build_market_alignment(
    mp: dict,
    target_market: str,
    sub_pref: dict,
    cam_pref: dict,
) -> MarketAlignmentFusion:
    market_fit = str(mp.get("market_fit") or "unknown")
    if market_fit == "unknown":
        market_fit = _derive_market_fit(target_market, sub_pref, cam_pref)

    return MarketAlignmentFusion(
        target_market=target_market or "unknown",
        market_fit=market_fit,
    )


# ---------------------------------------------------------------------------
# Quality alignment
# ---------------------------------------------------------------------------

def _build_quality_alignment(
    quality: dict,
    sub_pref: dict,
    cam_pref: dict,
    reasoning: list[str],
) -> QualityAlignmentFusion:
    output_scores = quality.get("output_scores") or []
    cam_scores    = [
        float(s.get("camera_smoothness") or 0.0)
        for s in output_scores if isinstance(s, dict)
    ]

    if cam_scores:
        avg = sum(cam_scores) / len(cam_scores)
        smoothness = "high" if avg >= 0.70 else ("medium" if avg >= 0.40 else "low")
    else:
        smoothness = str(cam_pref.get("smoothness_priority") or "unknown")

    readability = str(sub_pref.get("readability_priority") or "unknown")

    if smoothness != "unknown" or readability != "unknown":
        reasoning.append(
            f"Quality: readability={readability!r} smoothness={smoothness!r}"
        )

    return QualityAlignmentFusion(
        readability_priority=readability,
        smoothness_priority=smoothness,
    )


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

def _compute_confidence(
    sub_conf: float,
    cam_conf: float,
    total_exports: int,
    reasoning: list[str],
) -> float:
    """Weighted average of available signal confidences, amplified by export history."""
    scores: list[float] = []
    if sub_conf > 0.0:
        scores.append(sub_conf)
    if cam_conf > 0.0:
        scores.append(cam_conf)
    if total_exports > 0:
        scores.append(min(total_exports / 10.0, 1.0))

    if not scores:
        return 0.0

    base = sum(scores) / len(scores)

    amplifier = 0.0
    if total_exports >= 5:
        amplifier = min(total_exports * 0.005, 0.05)

    result = round(max(0.0, min(1.0, base + amplifier)), 2)

    if result > 0.0:
        reasoning.append(
            f"Fused confidence={result:.2f} from {len(scores)} signal(s)"
            f" (sub={sub_conf:.2f}, cam={cam_conf:.2f}, exports={total_exports})"
        )
    return result


# ---------------------------------------------------------------------------
# Market signal inference helpers
# ---------------------------------------------------------------------------

def _market_subtitle_style(target_market: str) -> str:
    if "tiktok" in target_market or "reels" in target_market or "instagram" in target_market:
        return "viral_bold"
    if "podcast" in target_market or "educational" in target_market:
        return "clean_pro"
    if "youtube" in target_market or "shorts" in target_market:
        return "clean_pro"
    return "unknown"


def _market_emphasis(target_market: str) -> str:
    if "tiktok" in target_market or "reels" in target_market or "instagram" in target_market:
        return "strong"
    if "podcast" in target_market or "educational" in target_market:
        return "subtle"
    if "youtube" in target_market or "shorts" in target_market:
        return "moderate"
    return "unknown"


def _market_camera_style(target_market: str) -> str:
    if "tiktok" in target_market or "reels" in target_market or "instagram" in target_market:
        return "dynamic_subject"
    if "podcast" in target_market or "educational" in target_market:
        return "static_center"
    if "shorts" in target_market or "youtube" in target_market:
        return "smooth_subject"
    return "unknown"


def _market_content_style(target_market: str) -> str:
    if "podcast" in target_market or "audio" in target_market:
        return "podcast"
    if "educational" in target_market or "tutorial" in target_market:
        return "educational"
    if "tiktok" in target_market or "reels" in target_market or "viral" in target_market:
        return "viral"
    if "youtube" in target_market or "shorts" in target_market:
        return "educational"
    return "unknown"


def _map_creator_style(raw: str) -> str:
    if not raw:
        return "unknown"
    if raw in ("podcast", "interview", "talk_show", "audio_visual"):
        return "podcast"
    if raw in ("educational", "tutorial", "explainer", "how_to"):
        return "educational"
    if raw in ("viral", "viral_bold", "energetic", "entertainment"):
        return "viral"
    if raw in ("clean", "clean_pro", "minimal", "professional"):
        return "educational"
    return "unknown"


# ---------------------------------------------------------------------------
# Ranking preference derivation
# ---------------------------------------------------------------------------

def _derive_ranking_preference(
    avg_rank: float,
    total_exports: int,
    target_market: str,
    quality: dict,
) -> str:
    if total_exports >= 3 and avg_rank > 0.0:
        if avg_rank <= 1.5:
            return "engagement"
        if avg_rank <= 2.5:
            return "retention"
        return "reach"

    if "tiktok" in target_market or "reels" in target_market:
        return "reach"
    if "educational" in target_market or "podcast" in target_market:
        return "retention"
    if "shorts" in target_market or "youtube" in target_market:
        return "engagement"
    return "unknown"


# ---------------------------------------------------------------------------
# Market fit derivation
# ---------------------------------------------------------------------------

def _derive_market_fit(target_market: str, sub_pref: dict, cam_pref: dict) -> str:
    if not target_market or target_market == "unknown":
        return "unknown"

    market_sub = _market_subtitle_style(target_market)
    market_cam = _market_camera_style(target_market)
    creator_sub = str(sub_pref.get("style")        or "unknown")
    creator_cam = str(cam_pref.get("motion_style") or "unknown")

    score = 0
    checks = 0
    if creator_sub != "unknown" and market_sub != "unknown":
        score  += 1 if creator_sub == market_sub else 0
        checks += 1
    if creator_cam != "unknown" and market_cam != "unknown":
        score  += 1 if creator_cam == market_cam else 0
        checks += 1

    if checks == 0:
        return "unknown"
    ratio = score / checks
    if ratio >= 0.75:
        return "high"
    if ratio >= 0.50:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _attr(obj: Any, name: str) -> dict:
    try:
        val = getattr(obj, name, None)
        return val if isinstance(val, dict) else {}
    except Exception:
        return {}


def _safe_float(val: Any) -> float:
    try:
        return float(val or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(val: Any) -> int:
    try:
        return int(val or 0)
    except (TypeError, ValueError):
        return 0
