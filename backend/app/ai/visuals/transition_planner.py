"""
transition_planner.py — Transition hint planning. Phase 18.

Advisory only. safe_to_apply is structurally False. Deterministic only.
Never raises. No timing mutation.
"""
from __future__ import annotations

import logging

from app.ai.visuals.beat_visual_schema import (
    TransitionHint,
    VALID_TRANSITION_STYLES,
    _BPM_MIN,
    _BPM_MAX,
    _MAX_TRANSITION_HINTS,
)

logger = logging.getLogger("app.ai.visuals")

# Segment type pairs (from → to) and the transition hint they suggest
_SEGMENT_TRANSITION_MAP: dict[tuple[str, str], str] = {
    ("hook", "build_up"):    "beat_pulse",
    ("hook", "setup"):       "soft_cut",
    ("build_up", "tension"): "cinematic_push",
    ("build_up", "climax"):  "cinematic_push",
    ("tension", "climax"):   "cinematic_push",
    ("climax", "payoff"):    "energy_pop",
    ("climax", "outro"):     "soft_cut",
    ("payoff", "outro"):     "soft_cut",
    ("setup", "build_up"):   "beat_pulse",
}

# Creator styles that favour high-energy transitions
_HYPE_CREATOR_STYLES: frozenset[str] = frozenset({
    "high_energy_reaction", "anime_edit", "gameplay_highlight", "podcast_viral",
})

# Creator styles that favour calm transitions
_CALM_CREATOR_STYLES: frozenset[str] = frozenset({
    "documentary_clean", "calm_minimal", "interview_clip",
})


def build_transition_hints(
    pacing_context=None,
    story_context=None,
    retention_context=None,
    creator_style_context=None,
) -> list[TransitionHint]:
    """Build advisory transition hints from pacing/story/creator_style signals.

    Returns up to 10 TransitionHint objects. Never raises.
    safe_to_apply is always False — Phase 18 metadata-only.
    """
    try:
        return _build_hints(
            pacing_context,
            story_context,
            retention_context,
            creator_style_context,
        )
    except Exception as exc:
        logger.debug("build_transition_hints_failed: %s", exc)
        return []


def _build_hints(
    pacing_context,
    story_context,
    retention_context,
    creator_style_context,
) -> list[TransitionHint]:
    pacing_ctx = dict(pacing_context or {})
    story_ctx = dict(story_context or {})
    retention_ctx = dict(retention_context or {})
    creator_ctx = dict(creator_style_context or {})

    hints: list[TransitionHint] = []

    # --- Pacing signals ---
    pacing_style = str(pacing_ctx.get("pacing_style") or "default").lower()
    beat_available = bool(pacing_ctx.get("beat_available"))
    raw_bpm = pacing_ctx.get("bpm")
    bpm_valid = False
    if raw_bpm is not None:
        try:
            bpm = float(raw_bpm)
            bpm_valid = _BPM_MIN <= bpm <= _BPM_MAX
        except (TypeError, ValueError):
            bpm_valid = False

    # --- Creator style signals ---
    dominant_style = str(creator_ctx.get("dominant_style") or "").lower()

    # --- Global fallback style ---
    global_style = _global_transition_style(
        pacing_style, beat_available, bpm_valid, dominant_style
    )

    # --- Story-segment-based transition hints ---
    story_segments = list(story_ctx.get("segments", []) or [])
    if len(story_segments) >= 2:
        hints.extend(_hints_from_story_segments(
            story_segments, global_style, dominant_style
        ))

    # --- Fallback: global pacing hint when no segments ---
    if not hints:
        dominant_arc = str(story_ctx.get("dominant_arc") or "").lower()
        style = _arc_to_transition(dominant_arc) or global_style
        hints.append(TransitionHint(
            start=0.0,
            end=0.0,
            transition_style=style if style in VALID_TRANSITION_STYLES else "soft_cut",
            confidence=0.5,
            reason=f"pacing:{pacing_style}",
            safe_to_apply=False,
        ))

    logger.info(
        "ai_transition_hints_generated hints=%d global_style=%s",
        len(hints), global_style,
    )

    return hints[:_MAX_TRANSITION_HINTS]


def _global_transition_style(
    pacing_style: str,
    beat_available: bool,
    bpm_valid: bool,
    dominant_style: str,
) -> str:
    """Select a global fallback transition style."""
    if dominant_style in _CALM_CREATOR_STYLES:
        return "soft_cut"
    if dominant_style in _HYPE_CREATOR_STYLES:
        return "energy_pop"
    if beat_available and bpm_valid and pacing_style in ("fast", "dynamic"):
        return "beat_pulse"
    if pacing_style in ("slow_build", "slow"):
        return "soft_cut"
    return "soft_cut"


def _hints_from_story_segments(
    segments: list,
    global_style: str,
    dominant_style: str,
) -> list[TransitionHint]:
    """Generate one transition hint per adjacent segment pair."""
    hints: list[TransitionHint] = []

    valid_segs = [s for s in segments if isinstance(s, dict)]
    for i in range(len(valid_segs) - 1):
        from_seg = valid_segs[i]
        to_seg = valid_segs[i + 1]

        from_type = str(from_seg.get("segment_type", "unknown")).lower()
        to_type = str(to_seg.get("segment_type", "unknown")).lower()

        boundary_start = float(from_seg.get("end", 0.0))
        boundary_end = float(to_seg.get("start", boundary_start + 0.5))
        if boundary_end < boundary_start:
            boundary_end = boundary_start + 0.5

        # Look up specific pair in map
        pair_style = _SEGMENT_TRANSITION_MAP.get((from_type, to_type))

        # Override for hype/calm creator styles
        if dominant_style in _HYPE_CREATOR_STYLES:
            style = "energy_pop" if from_type in ("climax", "build_up") else pair_style or global_style
        elif dominant_style in _CALM_CREATOR_STYLES:
            style = "soft_cut"
        else:
            style = pair_style or global_style

        if style not in VALID_TRANSITION_STYLES:
            style = "soft_cut"

        confidence = _transition_confidence(from_type, to_type, pair_style is not None)

        hints.append(TransitionHint(
            start=round(boundary_start, 3),
            end=round(boundary_end, 3),
            transition_style=style,
            confidence=round(confidence, 3),
            reason=f"{from_type}->{to_type}",
            safe_to_apply=False,
        ))

        if len(hints) >= _MAX_TRANSITION_HINTS:
            break

    return hints


def _transition_confidence(from_type: str, to_type: str, has_explicit_rule: bool) -> float:
    """Estimate confidence for a transition hint."""
    if has_explicit_rule:
        return 0.75
    if from_type in ("climax", "tension") or to_type in ("climax", "payoff"):
        return 0.60
    return 0.45


def _arc_to_transition(dominant_arc: str) -> str:
    """Map story arc to a fallback transition style."""
    _MAP: dict[str, str] = {
        "tension_release": "cinematic_push",
        "emotional_peak": "cinematic_push",
        "curiosity_build": "beat_pulse",
        "front_loaded": "energy_pop",
        "setup_payoff": "cinematic_push",
        "linear_build": "soft_cut",
        "informational": "soft_cut",
    }
    return _MAP.get(dominant_arc, "")
