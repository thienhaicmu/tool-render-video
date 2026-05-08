"""
beat_pulse.py — Beat pulse visual region planning. Phase 18.

Deterministic heuristics only. Never raises. Uses existing pacing/beat
metadata — no audio analysis, no librosa at runtime.
"""
from __future__ import annotations

import logging

from app.ai.visuals.beat_visual_schema import (
    BeatPulseRegion,
    VALID_PULSE_STYLES,
    _MAX_PULSE_STRENGTH,
    _BPM_MIN,
    _BPM_MAX,
    _MIN_BEAT_COUNT,
    _MAX_PULSE_REGIONS,
)

logger = logging.getLogger("app.ai.visuals")

# Story arcs that favour cinematic pulse style
_CINEMATIC_ARCS: frozenset[str] = frozenset({
    "tension_release", "emotional_peak", "curiosity_build", "setup_payoff",
})

# Segment types that earn higher pulse intensity
_HIGH_PULSE_SEGMENT_TYPES: frozenset[str] = frozenset({
    "hook", "climax", "tension", "build_up",
})

# Retention risk categories that soften the pulse in that region
_RISK_SOFTENING_CATEGORIES: frozenset[str] = frozenset({
    "weak_hook", "pacing_decay", "low_energy", "silence_gap",
})


def build_beat_pulse_regions(
    pacing_context=None,
    beat_execution_context=None,
    story_context=None,
    retention_context=None,
) -> list[BeatPulseRegion]:
    """Build compact beat pulse regions from existing AI metadata.

    Returns up to 12 BeatPulseRegion objects. Never raises.
    Uses only already-computed metadata — no audio loading, no librosa.
    """
    try:
        return _build_regions(
            pacing_context,
            beat_execution_context,
            story_context,
            retention_context,
        )
    except Exception as exc:
        logger.debug("build_beat_pulse_regions_failed: %s", exc)
        return []


def _build_regions(
    pacing_context,
    beat_execution_context,
    story_context,
    retention_context,
) -> list[BeatPulseRegion]:
    pacing_ctx = dict(pacing_context or {})
    beat_ctx = dict(beat_execution_context or {})
    story_ctx = dict(story_context or {})
    retention_ctx = dict(retention_context or {})

    # --- Gate checks (mirrors Phase 11 hard rules) ---
    beat_available = bool(pacing_ctx.get("beat_available") or beat_ctx.get("beat_available"))
    if not beat_available:
        return []

    raw_bpm = pacing_ctx.get("bpm") or beat_ctx.get("bpm")
    if raw_bpm is None:
        return []

    try:
        bpm = float(raw_bpm)
    except (TypeError, ValueError):
        return []

    if bpm < _BPM_MIN or bpm > _BPM_MAX:
        return []

    raw_beat_count = pacing_ctx.get("beat_count") or beat_ctx.get("beat_count") or 0
    beat_count = int(raw_beat_count)
    if beat_count < _MIN_BEAT_COUNT:
        return []

    # --- Base pulse strength from energy ---
    energy = pacing_ctx.get("energy_level")
    if energy is not None:
        try:
            base_pulse = float(energy) * 0.20
        except (TypeError, ValueError):
            base_pulse = 0.08
    else:
        base_pulse = 0.08
    base_pulse = _clamp_pulse(base_pulse)

    # --- Global style selection ---
    pacing_style = str(pacing_ctx.get("pacing_style") or "default").lower()
    dominant_arc = str(story_ctx.get("dominant_arc") or "").lower()
    energy_val = float(energy) if energy is not None else 0.0

    global_style = _select_pulse_style(
        energy_val, pacing_style, dominant_arc, bpm
    )

    # --- Build retention risk lookup for region softening ---
    risk_regions = list(retention_ctx.get("risk_regions", []) or [])

    # --- Generate regions from story segments or single global region ---
    story_segments = list(story_ctx.get("segments", []) or [])

    if story_segments:
        regions = _regions_from_story(
            story_segments, bpm, beat_count, base_pulse, global_style, risk_regions
        )
    else:
        # Fallback: one global region if we have story duration hint
        regions = _regions_fallback(bpm, beat_count, base_pulse, global_style)

    logger.info(
        "ai_beat_pulse_regions_generated bpm=%.1f style=%s regions=%d "
        "base_pulse=%.3f",
        bpm, global_style, len(regions), base_pulse,
    )

    return regions[:_MAX_PULSE_REGIONS]


def _select_pulse_style(
    energy: float,
    pacing_style: str,
    dominant_arc: str,
    bpm: float,
) -> str:
    """Select global pulse style from energy/pacing/arc signals."""
    if dominant_arc in _CINEMATIC_ARCS:
        return "cinematic_pulse"
    if energy >= 0.7 and (pacing_style in ("fast", "dynamic") or bpm >= 120):
        return "punch_pulse"
    if energy < 0.3:
        return "soft_pulse"
    return "soft_pulse"


def _regions_from_story(
    segments: list,
    bpm: float,
    beat_count: int,
    base_pulse: float,
    global_style: str,
    risk_regions: list,
) -> list[BeatPulseRegion]:
    """Build one pulse region per story segment (up to _MAX_PULSE_REGIONS)."""
    regions: list[BeatPulseRegion] = []
    beats_per_segment = max(1, beat_count // max(1, len(segments)))

    for seg in segments[:_MAX_PULSE_REGIONS]:
        if not isinstance(seg, dict):
            continue
        start = float(seg.get("start", 0.0))
        end = float(seg.get("end", start + 1.0))
        if end <= start:
            continue

        seg_type = str(seg.get("segment_type", "unknown")).lower()

        # Override style for high-intensity segment types
        if seg_type in _HIGH_PULSE_SEGMENT_TYPES:
            style = global_style
            pulse = _clamp_pulse(base_pulse * 1.3)
        elif seg_type in ("outro", "payoff"):
            style = "soft_pulse"
            pulse = _clamp_pulse(base_pulse * 0.6)
        else:
            style = global_style
            pulse = base_pulse

        # Soften near retention risk regions
        if _overlaps_risk(start, end, risk_regions):
            pulse = _clamp_pulse(pulse * 0.5)
            style = "soft_pulse"

        regions.append(BeatPulseRegion(
            start=round(start, 3),
            end=round(end, 3),
            pulse_strength=_clamp_pulse(pulse),
            pulse_style=style if style in VALID_PULSE_STYLES else "soft_pulse",
            beat_count=beats_per_segment,
            warnings=[],
        ))

    return regions


def _regions_fallback(
    bpm: float,
    beat_count: int,
    base_pulse: float,
    global_style: str,
) -> list[BeatPulseRegion]:
    """Generate a single generic region when story segments are not available."""
    # Estimate a safe duration from beat count + bpm (seconds per beat * count)
    beat_duration_sec = 60.0 / max(bpm, 1.0)
    estimated_end = round(beat_duration_sec * beat_count, 3)
    return [BeatPulseRegion(
        start=0.0,
        end=min(estimated_end, 600.0),
        pulse_strength=base_pulse,
        pulse_style=global_style if global_style in VALID_PULSE_STYLES else "soft_pulse",
        beat_count=beat_count,
        warnings=[],
    )]


def _overlaps_risk(start: float, end: float, risk_regions: list) -> bool:
    """Check if a time range overlaps any retention risk region."""
    for r in risk_regions:
        if not isinstance(r, dict):
            continue
        cat = str(r.get("category", ""))
        if cat not in _RISK_SOFTENING_CATEGORIES:
            continue
        r_start = float(r.get("start", 0.0))
        r_end = float(r.get("end", r_start + 1.0))
        if start < r_end and end > r_start:
            return True
    return False


def _clamp_pulse(value: float) -> float:
    return max(0.0, min(_MAX_PULSE_STRENGTH, float(value)))
