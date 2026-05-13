"""
platform_quality_feedback_evaluator.py — Phase 57 Platform-Aware Quality Feedback Loop.

Evaluates whether render outputs align with the target platform strategy and quality
expectations. Produces per-domain platform fit scores and creator-facing feedback.

Quality feedback only — NO render mutation, NO rerender, NO executor override.

Public API:
    evaluate_platform_quality_feedback(plan) -> dict
        Returns {"platform_quality_feedback": {...}}

Reads from (all optional, falls back gracefully):
  - platform_render_strategy      (Phase 55E)
  - platform_strategy_influence   (Phase 56)
  - subtitle_quality_v2           (Phase 52A)
  - camera_quality_v2             (Phase 52B)
  - hook_quality_v2               (Phase 52C)
  - render_quality_v2             (Phase 52D)
  - platform_subtitle_context     (Phase 55B)
  - platform_camera_context       (Phase 55C)
  - platform_hook_context         (Phase 55D)
  - creator_subtitle_preference   (Phase 50A) — optional
  - creator_subtitle_influence    (Phase 50C) — optional
  - creator_camera_preference     (Phase 50B) — optional
  - best_strategy_reasoning       (Phase 51C) — optional
  - variant_evaluation            (Phase 51B) — optional

Scoring weights (sum = 1.00):
  subtitle_fit:              0.25
  camera_fit:                0.25
  hook_fit:                  0.25
  strategy_fit:              0.15
  platform_context_confidence: 0.10

Safety contract:
  - Local only: no internet, no subprocess, no cloud API
  - Never raises — fallback-safe
  - Deterministic: same inputs → same output
  - Quality feedback only: no render mutation, no rerender, no executor override
  - No subtitle timing rewrite, no motion_crop rewrite, no clip boundary mutation
  - No transcript rewrite, no hook text rewrite, no FFmpeg mutation
  - Advisory only: platform_quality_feedback is metadata, never alters render pipeline
  - Executor authority unchanged — render pipeline never reads platform_quality_feedback
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger("app.ai.knowledge.platform_quality_feedback_evaluator")

# ---------------------------------------------------------------------------
# Scoring weights (must sum to 1.00)
# ---------------------------------------------------------------------------

_WEIGHTS: Dict[str, float] = {
    "subtitle_fit":               0.25,
    "camera_fit":                 0.25,
    "hook_fit":                   0.25,
    "strategy_fit":               0.15,
    "platform_context_confidence": 0.10,
}

# Thresholds for feedback classification
_STRENGTH_THRESHOLD    = 75
_IMPROVEMENT_THRESHOLD = 65

# Output caps
_MAX_STRENGTHS    = 3
_MAX_IMPROVEMENTS = 3
_MAX_REASONING    = 3

# Creator classification sets (mirrors Phase 55E)
_TRUST_CREATORS         = frozenset({"podcast", "talking_head"})
_CLARITY_CREATORS       = frozenset({"educational", "storytelling"})
_HIGH_ENERGY_PLATFORMS  = frozenset({"tiktok", "instagram_reels"})
_HIGH_RETENTION_PLATFORMS = frozenset({"tiktok", "youtube_shorts", "instagram_reels"})

# Forbidden execution keys — must never appear in any output dict
_FORBIDDEN_OUTPUT_KEYS = frozenset({
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
    "crop_coordinates", "direct_execution", "executor_override",
    "output_path", "queue_priority",
})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_platform_quality_feedback(plan: Any) -> dict:
    """Evaluate platform quality feedback. Never raises. Fallback-safe.

    Returns {"platform_quality_feedback": {...}} with per-domain fit scores,
    strengths, improvement opportunities, and creator-facing reasoning.

    Advisory only — output is metadata, never alters render parameters.
    """
    try:
        return _evaluate(plan)
    except Exception as exc:
        logger.debug("platform_quality_feedback_error: %s", exc)
        return {"platform_quality_feedback": _fallback()}


# ---------------------------------------------------------------------------
# Fallback + duck-typed plan access
# ---------------------------------------------------------------------------

def _fallback() -> dict:
    return {
        "available":               False,
        "platform_fit":            0,
        "subtitle_fit":            0,
        "camera_fit":              0,
        "hook_fit":                0,
        "strategy_fit":            0,
        "overall":                 0,
        "confidence":              0.0,
        "strengths":               [],
        "improvement_opportunities": [],
        "reasoning":               [],
    }


def _get(plan: Any, key: str) -> Any:
    """Duck-typed read — works for AIEditPlan or dict."""
    if isinstance(plan, dict):
        return plan.get(key)
    return getattr(plan, key, None)


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------

def _evaluate(plan: Any) -> dict:
    if plan is None:
        return {"platform_quality_feedback": _fallback()}

    # Require Phase 55E platform_render_strategy to be available
    prs = _get(plan, "platform_render_strategy") or {}
    if not isinstance(prs, dict) or not prs.get("available"):
        return {"platform_quality_feedback": _fallback()}

    platform       = str(prs.get("platform") or "")
    creator_type   = str(prs.get("creator_type") or "")
    prs_confidence = float(prs.get("confidence") or 0.0)
    strategy       = prs.get("strategy") or {}

    # Quality metadata (Phases 52A–52D)
    sqv2 = _get(plan, "subtitle_quality_v2") or {}
    cqv2 = _get(plan, "camera_quality_v2")   or {}
    hqv2 = _get(plan, "hook_quality_v2")     or {}
    rqv2 = _get(plan, "render_quality_v2")   or {}

    # Platform context metadata (Phases 55B–55D)
    sub_ctx  = _get(plan, "platform_subtitle_context") or {}
    cam_ctx  = _get(plan, "platform_camera_context")   or {}
    hook_ctx = _get(plan, "platform_hook_context")     or {}

    # Strategy influence metadata (Phase 56)
    psi = _get(plan, "platform_strategy_influence") or {}

    # --- Per-domain fit scores ---
    subtitle_fit = _score_subtitle_fit(sqv2, sub_ctx, psi)
    camera_fit   = _score_camera_fit(cqv2, cam_ctx, psi)
    hook_fit     = _score_hook_fit(hqv2, hook_ctx, psi)
    strategy_fit = _score_strategy_fit(rqv2, prs, psi)
    ctx_score    = _score_platform_context_confidence(prs_confidence, psi)

    # --- Weighted overall ---
    overall = _compute_overall(subtitle_fit, camera_fit, hook_fit, strategy_fit, ctx_score)

    # --- Confidence (average of platform + quality evaluation confidence) ---
    rqv2_confidence = float(rqv2.get("confidence") or 0.0)
    confidence = round(max(0.0, min(1.0, (prs_confidence + rqv2_confidence) / 2.0)), 4)

    # --- Creator-facing feedback text ---
    domain_scores = {
        "subtitle_fit": subtitle_fit,
        "camera_fit":   camera_fit,
        "hook_fit":     hook_fit,
        "strategy_fit": strategy_fit,
    }
    strengths    = _build_strengths(platform, creator_type, domain_scores, psi)
    improvements = _build_improvements(platform, creator_type, domain_scores, strategy)
    reasoning    = _build_reasoning(platform, creator_type, overall, prs_confidence, domain_scores)

    logger.debug(
        "platform_quality_feedback_done platform=%s creator_type=%s "
        "subtitle_fit=%d camera_fit=%d hook_fit=%d strategy_fit=%d "
        "overall=%d confidence=%.2f",
        platform, creator_type,
        subtitle_fit, camera_fit, hook_fit, strategy_fit,
        overall, confidence,
    )

    return {
        "platform_quality_feedback": {
            "available":               True,
            "platform":                platform,
            "creator_type":            creator_type,
            "platform_fit":            overall,
            "subtitle_fit":            subtitle_fit,
            "camera_fit":              camera_fit,
            "hook_fit":                hook_fit,
            "strategy_fit":            strategy_fit,
            "overall":                 overall,
            "confidence":              confidence,
            "strengths":               strengths,
            "improvement_opportunities": improvements,
            "reasoning":               reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Per-domain fit scorers
# ---------------------------------------------------------------------------

def _score_subtitle_fit(
    sqv2: dict,
    sub_ctx: dict,
    psi: dict,
) -> int:
    raw_quality = int(sqv2.get("overall") or 0)
    if raw_quality == 0:
        return 0

    if not sub_ctx.get("available"):
        return max(0, min(100, raw_quality))

    ctx_confidence = float(sub_ctx.get("confidence") or 0.0)
    sub_support    = bool((psi.get("subtitle") or {}).get("supported"))

    # Weighted blend: 70% raw quality + 30% platform context alignment
    platform_align = round(ctx_confidence * 100)
    score = round(0.70 * raw_quality + 0.30 * platform_align)
    if sub_support:
        score = min(100, score + 3)

    return max(0, min(100, score))


def _score_camera_fit(
    cqv2: dict,
    cam_ctx: dict,
    psi: dict,
) -> int:
    raw_quality = int(cqv2.get("overall") or 0)
    if raw_quality == 0:
        return 0

    if not cam_ctx.get("available"):
        return max(0, min(100, raw_quality))

    ctx_confidence = float(cam_ctx.get("confidence") or 0.0)
    cam_support    = bool((psi.get("camera") or {}).get("supported"))

    platform_align = round(ctx_confidence * 100)
    score = round(0.70 * raw_quality + 0.30 * platform_align)
    if cam_support:
        score = min(100, score + 3)

    return max(0, min(100, score))


def _score_hook_fit(
    hqv2: dict,
    hook_ctx: dict,
    psi: dict,
) -> int:
    raw_quality = int(hqv2.get("overall") or 0)
    if raw_quality == 0:
        return 0

    if not hook_ctx.get("available"):
        return max(0, min(100, raw_quality))

    ctx_confidence = float(hook_ctx.get("confidence") or 0.0)
    # Hook domain: no dedicated influence support in Phase 56, just context weight
    platform_align = round(ctx_confidence * 100)
    score = round(0.70 * raw_quality + 0.30 * platform_align)

    return max(0, min(100, score))


def _score_strategy_fit(
    rqv2: dict,
    prs: dict,
    psi: dict,
) -> int:
    rqv2_strategy  = int(rqv2.get("strategy_fit") or 0)
    prs_confidence = float(prs.get("confidence") or 0.0)
    psi_available  = bool((psi or {}).get("available"))

    if rqv2_strategy == 0:
        # No existing strategy score — derive from PRS confidence alone
        return max(0, min(100, round(prs_confidence * 75)))

    # Weighted blend: 60% from existing strategy quality + 40% from PRS confidence
    score = round(0.60 * rqv2_strategy + 0.40 * prs_confidence * 100)
    if psi_available:
        score = min(100, score + 5)

    return max(0, min(100, score))


def _score_platform_context_confidence(
    prs_confidence: float,
    psi: dict,
) -> int:
    psi_available  = bool((psi or {}).get("available"))
    psi_confidence = float((psi or {}).get("confidence") or 0.0)
    base = round(prs_confidence * 100)

    if psi_available:
        blended = round(0.70 * base + 0.30 * psi_confidence * 100)
        return max(0, min(100, blended))

    return max(0, min(100, base))


# ---------------------------------------------------------------------------
# Overall weighted score
# ---------------------------------------------------------------------------

def _compute_overall(
    subtitle_fit: int,
    camera_fit:   int,
    hook_fit:     int,
    strategy_fit: int,
    ctx_score:    int,
) -> int:
    raw = (
        _WEIGHTS["subtitle_fit"]               * subtitle_fit
        + _WEIGHTS["camera_fit"]               * camera_fit
        + _WEIGHTS["hook_fit"]                 * hook_fit
        + _WEIGHTS["strategy_fit"]             * strategy_fit
        + _WEIGHTS["platform_context_confidence"] * ctx_score
    )
    return max(0, min(100, round(raw)))


# ---------------------------------------------------------------------------
# Feedback text builders
# ---------------------------------------------------------------------------

def _build_strengths(
    platform:     str,
    creator_type: str,
    scores:       Dict[str, int],
    psi:          dict,
) -> List[str]:
    lines: List[str] = []
    plat    = platform.replace("_", " ")    if platform    else ""
    creator = creator_type.replace("_", " ") if creator_type else ""

    subtitle_fit = scores["subtitle_fit"]
    camera_fit   = scores["camera_fit"]
    hook_fit     = scores["hook_fit"]
    strategy_fit = scores["strategy_fit"]

    # Subtitle strength
    if subtitle_fit >= _STRENGTH_THRESHOLD:
        if creator_type in _TRUST_CREATORS and plat:
            lines.append(
                f"Subtitles are compact and readable for {plat} {creator} content"
            )
        elif creator_type in _CLARITY_CREATORS:
            lines.append(
                f"Subtitle clarity and structure align well with {creator} content requirements"
            )
        elif plat:
            lines.append(f"Subtitles are well-matched to {plat} viewing expectations")
        else:
            lines.append("Subtitle quality aligns with platform expectations")

    # Camera strength
    if camera_fit >= _STRENGTH_THRESHOLD:
        if creator_type in _TRUST_CREATORS:
            lines.append(f"Camera stability fits {creator}-style content delivery")
        elif platform in _HIGH_ENERGY_PLATFORMS and plat:
            lines.append(f"Camera motion energy is well-suited to {plat}'s dynamic feed")
        elif plat:
            lines.append(f"Camera behavior aligns with {plat} expectations")
        else:
            lines.append("Camera quality aligns with platform expectations")

    # Hook strength
    if hook_fit >= _STRENGTH_THRESHOLD and len(lines) < _MAX_STRENGTHS:
        if platform in _HIGH_RETENTION_PLATFORMS and plat:
            lines.append(
                f"Hook quality is strong for {plat}'s retention-focused environment"
            )
        elif creator_type in _TRUST_CREATORS:
            lines.append(
                f"Opening establishes trust and credibility for {creator} content"
            )
        else:
            lines.append("Opening hook quality meets platform expectations")

    # Strategy strength
    if strategy_fit >= _STRENGTH_THRESHOLD and len(lines) < _MAX_STRENGTHS:
        if plat and creator:
            lines.append(f"Output aligns well with {plat} {creator} content strategy")
        elif plat:
            lines.append(f"Output aligns well with {plat} platform strategy")

    return lines[:_MAX_STRENGTHS]


def _build_improvements(
    platform:     str,
    creator_type: str,
    scores:       Dict[str, int],
    strategy:     dict,
) -> List[str]:
    lines: List[str] = []
    plat    = platform.replace("_", " ")    if platform    else ""
    creator = creator_type.replace("_", " ") if creator_type else ""

    hook_fit     = scores["hook_fit"]
    subtitle_fit = scores["subtitle_fit"]
    camera_fit   = scores["camera_fit"]
    strategy_fit = scores["strategy_fit"]

    # Hook improvement (highest impact for platform virality)
    if hook_fit < _IMPROVEMENT_THRESHOLD:
        if platform in _HIGH_RETENTION_PLATFORMS and plat:
            lines.append(
                f"Opening hook could create stronger first-3-second attention for {plat}"
            )
        else:
            lines.append("Opening hook could better capture viewer attention")

    # Subtitle improvement
    if subtitle_fit < _IMPROVEMENT_THRESHOLD:
        sub_strat  = strategy.get("subtitle") or {}
        style_bias = str(sub_strat.get("style_bias") or "")
        if style_bias and style_bias not in ("unknown", ""):
            lines.append(
                f"Subtitle style could better align with {plat} expectations"
                if plat else
                "Subtitle style could be optimized for platform expectations"
            )
        else:
            lines.append(
                "Subtitle presentation could be better tailored for the target platform"
            )

    # Camera improvement
    if camera_fit < _IMPROVEMENT_THRESHOLD and len(lines) < _MAX_IMPROVEMENTS:
        cam_strat = strategy.get("camera") or {}
        stability = str(cam_strat.get("stability_priority") or "")
        if creator_type in _TRUST_CREATORS and stability in ("high", "medium_high"):
            lines.append(f"Camera stability could be strengthened for {creator} content")
        elif plat:
            lines.append(f"Camera behavior could be better aligned with {plat} expectations")
        else:
            lines.append("Camera behavior could be better aligned with platform expectations")

    # Strategy improvement
    if strategy_fit < _IMPROVEMENT_THRESHOLD and len(lines) < _MAX_IMPROVEMENTS:
        if plat and creator:
            lines.append(
                f"Content strategy alignment with {plat} {creator} guidelines could be improved"
            )
        elif plat:
            lines.append(f"Content strategy alignment with {plat} guidelines could be improved")

    return lines[:_MAX_IMPROVEMENTS]


def _build_reasoning(
    platform:     str,
    creator_type: str,
    overall:      int,
    prs_confidence: float,
    scores:       Dict[str, int],
) -> List[str]:
    lines: List[str] = []
    plat    = platform.replace("_", " ").title() if platform    else ""
    creator = creator_type.replace("_", " ")     if creator_type else ""

    # Top-level alignment summary
    if plat and creator:
        if overall >= _STRENGTH_THRESHOLD:
            lines.append(
                f"Output aligns well with {plat} {creator} strategy"
                " while preserving creator style"
            )
        else:
            lines.append(
                f"Output partially aligns with {plat} {creator} strategy guidelines"
            )
    elif plat:
        quality_label = "high" if prs_confidence >= 0.75 else "moderate"
        lines.append(
            f"Evaluated against {plat} platform requirements with {quality_label} confidence"
        )

    # Highlight strongest contributing domain
    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    best_domain, best_score = sorted_scores[0]
    if best_score >= _STRENGTH_THRESHOLD and len(lines) < _MAX_REASONING:
        domain_name = best_domain.replace("_fit", "").replace("_", " ")
        lines.append(
            f"{domain_name.capitalize()} quality is the strongest contributor to platform fit"
        )

    # Platform confidence note
    if prs_confidence >= 0.75 and len(lines) < _MAX_REASONING:
        lines.append(
            "Platform strategy confidence is strong — guidance is highly reliable"
        )
    elif prs_confidence >= 0.50 and len(lines) < _MAX_REASONING:
        lines.append(
            "Platform strategy confidence is moderate — guidance is directionally reliable"
        )

    return lines[:_MAX_REASONING]
