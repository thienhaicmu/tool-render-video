"""
beat_execution.py — Beat-aware render execution planning. Phase 11.

Builds a compact, metadata-only beat execution plan from existing pacing
analysis. Never loads audio models or calls librosa at runtime — all beat
metadata is sourced from edit_plan.pacing (populated by AIPacingPlan in
Phase 4).

Safety rules:
- Never raises.
- Never mutates segment start/end/score.
- Never mutates subtitle timing.
- Never alters playback_speed.
- BPM must be in [60, 190] or the plan is skipped.
- beat_count must be >= 4 or the plan is skipped.
- pulse_strength is clamped to max 0.15.
- execution_mode is always "metadata_only" in Phase 11.

Public API:
    build_beat_execution_plan(edit_plan, payload, context=None) -> dict
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("app.ai.director.beat_execution")

# ── Hard bounds ───────────────────────────────────────────────────────────────
_MAX_PULSE_STRENGTH = 0.15
_BPM_MIN = 60.0
_BPM_MAX = 190.0
_MIN_BEAT_COUNT = 4


def build_beat_execution_plan(
    edit_plan: Any,
    payload: Any,
    context: Optional[dict] = None,
) -> dict:
    """Build a compact beat execution plan from existing pacing metadata.

    Args:
        edit_plan: AIEditPlan (or compatible) with a .pacing attribute.
        payload:   RenderRequest-compatible object with beat-related flags.
        context:   Optional metadata dict (e.g. {"job_id": "..."}).

    Returns:
        dict with keys: enabled, beat_available, bpm, beat_count,
        pulse_strength, suggested_transition_style, execution_mode,
        applied, skipped, warnings.
    """
    report: dict = {
        "enabled": False,
        "beat_available": False,
        "bpm": None,
        "beat_count": 0,
        "pulse_strength": 0.0,
        "suggested_transition_style": "none",
        "execution_mode": "metadata_only",
        "applied": [],
        "skipped": [],
        "warnings": [],
    }
    try:
        _build(edit_plan, payload, report)
    except Exception as exc:
        report["warnings"].append(f"beat_execution_error:{type(exc).__name__}")
        logger.debug("build_beat_execution_plan_failed: %s", exc)
    return report


# ── Internal builder ──────────────────────────────────────────────────────────

def _build(edit_plan: Any, payload: Any, report: dict) -> None:
    pacing = getattr(edit_plan, "pacing", None)
    if pacing is None:
        report["skipped"].append("no_pacing_plan")
        report["warnings"].append("no_pacing_plan")
        return

    beat_available = bool(getattr(pacing, "beat_available", False))
    report["beat_available"] = beat_available

    if not beat_available:
        report["skipped"].append("beat_data_unavailable")
        report["warnings"].append("beat_data_unavailable")
        return

    raw_bpm = getattr(pacing, "bpm", None)
    beat_count = int(getattr(pacing, "beat_count", 0) or 0)

    if raw_bpm is None:
        report["skipped"].append("bpm_unavailable")
        report["warnings"].append("bpm_unavailable")
        return

    bpm = float(raw_bpm)
    report["bpm"] = bpm
    report["beat_count"] = beat_count

    # ── BPM range gate ───────────────────────────────────────────────────────
    if bpm < _BPM_MIN:
        report["skipped"].append(f"bpm_below_{int(_BPM_MIN)}({bpm:.1f})")
        report["warnings"].append(f"bpm_out_of_range:{bpm:.1f}<{_BPM_MIN}")
        return

    if bpm > _BPM_MAX:
        report["skipped"].append(f"bpm_above_{int(_BPM_MAX)}({bpm:.1f})")
        report["warnings"].append(f"bpm_out_of_range:{bpm:.1f}>{_BPM_MAX}")
        return

    # ── Beat count gate ──────────────────────────────────────────────────────
    if beat_count < _MIN_BEAT_COUNT:
        report["skipped"].append(f"beat_count_too_low({beat_count})")
        report["warnings"].append(f"beat_count_insufficient:{beat_count}<{_MIN_BEAT_COUNT}")
        return

    # ── Pulse strength calculation ────────────────────────────────────────────
    energy = getattr(pacing, "energy_level", None)
    raw_pulse = (float(energy) * 0.20) if energy is not None else 0.08
    pulse_strength = max(0.0, min(_MAX_PULSE_STRENGTH, raw_pulse))
    report["pulse_strength"] = pulse_strength

    # ── Transition style suggestion ───────────────────────────────────────────
    pacing_style = str(getattr(pacing, "pacing_style", "default") or "default").lower()
    transition_enabled = bool(getattr(payload, "ai_beat_transition_enabled", False))
    pulse_enabled = bool(getattr(payload, "ai_beat_pulse_enabled", True))

    if not transition_enabled:
        suggested = "metadata_only"
    elif pacing_style in ("fast", "dynamic") and bpm >= 120:
        suggested = "beat_pulse" if pulse_enabled else "soft_cut"
    else:
        suggested = "soft_cut"

    report["suggested_transition_style"] = suggested

    # ── Mark as enabled and record applied action ────────────────────────────
    report["enabled"] = True
    report["applied"].append(
        f"beat_metadata_planned("
        f"bpm={bpm:.1f},count={beat_count},"
        f"pulse={pulse_strength:.3f},"
        f"transition={suggested!r})"
    )

    logger.info(
        "beat_execution_plan_built bpm=%.1f beat_count=%d pulse=%.3f transition=%s",
        bpm, beat_count, pulse_strength, suggested,
    )
