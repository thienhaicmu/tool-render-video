"""
clip_packaging_planner.py — S3.1 Packaging Intelligence.

Per-clip micro-adjustment layer driven by S2 signals.
Advisory metadata only — render pipeline is NOT modified.
Creator intent ALWAYS wins: packaging is additive refinement, never override.

Signal sources:
    hook_intelligence_type — from S2.1 (hook taxonomy)
    moment_type            — derived from hook + structure phases (S2.3/S2.4)
    structure_phases       — from S2.3 (opening / development / payoff)
    content_type_hint      — optional free-form hint

Packaging dimensions (all advisory):
    subtitle_intensity     — soft / balanced / strong
    motion_intensity       — light / medium / aggressive
    subtitle_emphasis      — clean / hook-heavy / payoff-heavy
    crop_pacing            — stable / dynamic
    timing_aggressiveness  — calm / balanced / fast

Required changes applied (from approval):
    RC1: adjacent-level shifts only (soft↔balanced, balanced↔strong — NOT soft→strong)
    RC2: confidence gate: segment_score >= S3_PACKAGING_MIN_SCORE (default 60)
    RC3: explainability: each packaging dict includes "reason" list
    RC4: hard-block incompatible styles: pro_karaoke, minimal → no-op (no warning)
    RC5: render pipeline exact no-op when packaging={} — trivially satisfied (no pipeline changes)
    RC6: env naming: S3_PACKAGING_*

Set S3_PACKAGING_ENABLED=0 for full rollback.

Public API:
    plan_clip_packaging(segments, subtitle_style, subtitle_emphasis_base, goal) -> dict
    S3_PACKAGING_ENABLED: bool
    S3_PACKAGING_MIN_SCORE: float
"""
from __future__ import annotations

import os

S3_PACKAGING_ENABLED: bool = os.environ.get("S3_PACKAGING_ENABLED", "1") == "1"
S3_PACKAGING_MIN_SCORE: float = float(os.environ.get("S3_PACKAGING_MIN_SCORE", "60"))

# RC4: Hard-block these subtitle styles — no packaging, no warning.
_INCOMPATIBLE_SUBTITLE_STYLES: frozenset[str] = frozenset({"pro_karaoke", "minimal"})

# RC1: Adjacent-only ordering for subtitle intensity.
_SUBTITLE_INTENSITY_ORDER: list[str] = ["soft", "balanced", "strong"]

# Adjacent-only ordering for motion intensity.
_MOTION_INTENSITY_ORDER: list[str] = ["light", "medium", "aggressive"]

# Default motion intensity baseline (no per-mode configuration exists).
_DEFAULT_MOTION_BASE: str = "medium"

# Maps subtitle_emphasis_style (from ai_modes.py) to subtitle intensity base level.
# punch=strong (viral), keyword=balanced (podcast), soft=soft (storytelling), none=balanced.
_EMPHASIS_TO_INTENSITY_BASE: dict[str, str] = {
    "punch":   "strong",
    "keyword": "balanced",
    "soft":    "soft",
    "none":    "balanced",
    "":        "balanced",
}

# hook_type → subtitle intensity target (RC1: adjacent-clamped from mode base).
_HOOK_INTENSITY_TARGET: dict[str, str] = {
    "surprise":     "strong",
    "warning":      "strong",
    "result_first": "strong",
    "curiosity":    "balanced",
    "problem":      "balanced",
    "challenge":    "balanced",
    "story":        "soft",
    "authority":    "soft",
    "contrarian":   "soft",
}

# moment_type → packaging hint pack for subtitle_emphasis, motion, crop, timing.
# Only moment types with confident packaging signals are listed.
_MOMENT_PACKAGING: dict[str, dict[str, str]] = {
    "payoff":      {"subtitle_emphasis": "payoff-heavy", "motion_intensity": "aggressive", "crop_pacing": "dynamic",  "timing_aggressiveness": "fast"},
    "hook_payoff": {"subtitle_emphasis": "payoff-heavy", "motion_intensity": "medium",     "crop_pacing": "dynamic",  "timing_aggressiveness": "fast"},
    "hook_opener": {"subtitle_emphasis": "hook-heavy",   "motion_intensity": "medium",     "crop_pacing": "stable",   "timing_aggressiveness": "calm"},
    "full_story":  {"subtitle_emphasis": "clean",        "motion_intensity": "medium",     "crop_pacing": "stable",   "timing_aggressiveness": "balanced"},
    "explainer":   {"subtitle_emphasis": "clean",        "motion_intensity": "light",      "crop_pacing": "stable",   "timing_aggressiveness": "calm"},
    "narrative":   {"subtitle_emphasis": "clean",        "motion_intensity": "light",      "crop_pacing": "stable",   "timing_aggressiveness": "calm"},
}


def plan_clip_packaging(
    segments: list[dict],
    subtitle_style: str = "",
    subtitle_emphasis_base: str = "",
    goal: str = "",
) -> dict:
    """Plan per-clip packaging micro-adjustments driven by S2 signals.

    Returns {clip_index (int): packaging_dict} for clips that received guidance.
    Clips with no applicable signal produce no entry (empty dict → no-op).

    packaging_dict shape:
        subtitle_intensity     str   — soft / balanced / strong
        motion_intensity       str   — light / medium / aggressive
        subtitle_emphasis      str   — clean / hook-heavy / payoff-heavy
        crop_pacing            str   — stable / dynamic
        timing_aggressiveness  str   — calm / balanced / fast
        reason                 list  — signal annotations (RC3 explainability)
        packaging_applied      bool  — always True when entry exists

    Graceful degradation:
        S3_PACKAGING_ENABLED=0 → returns {}
        subtitle_style in incompatible set → returns {} (RC4, no warning)
        segment_score < S3_PACKAGING_MIN_SCORE → clip skipped (RC2)
        S2 signals absent (hook=none, moment=unknown) → clip produces no entry
    """
    if not S3_PACKAGING_ENABLED:
        return {}

    # RC4: Hard-block incompatible subtitle styles.
    if str(subtitle_style or "").lower().strip() in _INCOMPATIBLE_SUBTITLE_STYLES:
        return {}

    intensity_base = _EMPHASIS_TO_INTENSITY_BASE.get(
        str(subtitle_emphasis_base or "").lower().strip(), "balanced"
    )

    result: dict = {}
    for idx, seg in enumerate(segments):
        score = float(seg.get("score", 0.0) or 0.0)
        # RC2: Confidence gate — only package clips with sufficient AI confidence.
        if score < S3_PACKAGING_MIN_SCORE:
            continue

        packaging = _derive_clip_packaging(seg, intensity_base)
        if packaging:
            result[idx] = packaging

    return result


def _derive_clip_packaging(seg: dict, intensity_base: str) -> dict:
    """Derive packaging guidance for one segment from its S2 signals.

    Returns {} when no signals produce a useful adjustment.
    """
    hook_type   = str(seg.get("hook_intelligence_type", "none") or "none").lower().strip()
    moment_type = str(seg.get("moment_type", "unknown") or "unknown").lower().strip()

    reasons: list[str] = []

    # Start from per-mode defaults.
    subtitle_intensity    = intensity_base
    motion_intensity      = _DEFAULT_MOTION_BASE
    subtitle_emphasis     = "balanced"
    crop_pacing           = "stable"
    timing_aggressiveness = "balanced"

    changed = False

    # ── Hook type drives subtitle intensity (RC1: adjacent shift only) ──────
    if hook_type in _HOOK_INTENSITY_TARGET:
        target  = _HOOK_INTENSITY_TARGET[hook_type]
        clamped = _clamp_adjacent(target, intensity_base, _SUBTITLE_INTENSITY_ORDER)
        if clamped != intensity_base:
            subtitle_intensity = clamped
            reasons.append(f"hook={hook_type}")
            changed = True

    # ── Moment type drives emphasis shape, motion, crop, timing ─────────────
    if moment_type in _MOMENT_PACKAGING:
        hints = _MOMENT_PACKAGING[moment_type]

        # Motion intensity (RC1: adjacent from "medium" baseline).
        mt_motion      = hints.get("motion_intensity", _DEFAULT_MOTION_BASE)
        clamped_motion = _clamp_adjacent(mt_motion, _DEFAULT_MOTION_BASE, _MOTION_INTENSITY_ORDER)
        motion_intensity = clamped_motion

        subtitle_emphasis     = hints.get("subtitle_emphasis",     "balanced")
        crop_pacing           = hints.get("crop_pacing",           "stable")
        timing_aggressiveness = hints.get("timing_aggressiveness", "balanced")

        reasons.append(f"moment={moment_type}")
        changed = True

    if not changed:
        return {}

    return {
        "subtitle_intensity":    subtitle_intensity,
        "motion_intensity":      motion_intensity,
        "subtitle_emphasis":     subtitle_emphasis,
        "crop_pacing":           crop_pacing,
        "timing_aggressiveness": timing_aggressiveness,
        "reason":                reasons,
        "packaging_applied":     True,
    }


def _clamp_adjacent(target: str, base: str, order: list[str]) -> str:
    """RC1: Micro-adjustment only — adjacent levels, no multi-level jumps.

    Same level: return base (no change).
    Adjacent (1 step): return target.
    Multi-level gap: return one step toward target from base.
    """
    if target not in order or base not in order:
        return base
    ti = order.index(target)
    bi = order.index(base)
    if ti == bi:
        return base
    step = 1 if ti > bi else -1
    return order[bi + step]
