"""
summary.py — Compact AI summary builder for the AI Director.

Generates a human-readable headline, summary lines, and strengths from
the AI edit plan and confidence scores.
No external deps, no randomization, no LLM. Never raises.

Public API:
    build_ai_summary(edit_plan, confidence) -> dict

Return shape:
    {
        "headline": str,
        "summary_lines": list[str],   # max 6
        "strengths": list[str],       # max 6
        "warnings": list[str],
        "confidence": dict,
    }
"""
from __future__ import annotations

from typing import Any

_MAX_SUMMARY_LINES = 6
_MAX_STRENGTHS = 6

_MODE_LABELS: dict[str, str] = {
    "viral_tiktok": "viral edit plan",
    "podcast_shorts": "podcast short plan",
    "storytelling": "storytelling edit plan",
    "clean_subtitle": "clean subtitle plan",
}


def build_ai_summary(edit_plan: Any, confidence: dict) -> dict:
    """Build a compact human-readable summary of the AI edit plan.

    Returns a dict with headline, summary_lines, strengths, warnings, confidence.
    Never raises.
    """
    try:
        return _build(edit_plan, confidence)
    except Exception:
        return {
            "headline": "AI edit plan generated",
            "summary_lines": [],
            "strengths": [],
            "warnings": ["summary_builder_failed"],
            "confidence": confidence,
        }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _build(edit_plan: Any, confidence: dict) -> dict:
    pacing = getattr(edit_plan, "pacing", None)
    camera = getattr(edit_plan, "camera", None)
    subtitle = getattr(edit_plan, "subtitle", None)
    segments: list = list(getattr(edit_plan, "selected_segments", []) or [])
    memory_ctx: dict = dict(getattr(edit_plan, "memory_context", {}) or {})
    plan_warnings: list[str] = list(getattr(edit_plan, "warnings", []) or [])
    mode: str = str(getattr(edit_plan, "mode", "unknown"))

    emotion = str(getattr(pacing, "emotion", "neutral")).lower() if pacing else "neutral"
    energy = getattr(pacing, "energy_level", None) if pacing else None
    pacing_style = str(getattr(pacing, "pacing_style", "default")).lower() if pacing else "default"
    beat_available = bool(getattr(pacing, "beat_available", False)) if pacing else False

    headline = _build_headline(mode, emotion, energy, pacing_style, confidence)
    summary_lines = _build_summary_lines(
        segments, memory_ctx, pacing, camera, subtitle, beat_available
    )
    strengths = _build_strengths(
        confidence, segments, memory_ctx, pacing, camera, subtitle
    )
    warnings = _build_warnings(plan_warnings, confidence)

    return {
        "headline": headline,
        "summary_lines": summary_lines[:_MAX_SUMMARY_LINES],
        "strengths": strengths[:_MAX_STRENGTHS],
        "warnings": warnings,
        "confidence": confidence,
    }


def _build_headline(
    mode: str,
    emotion: str,
    energy: Any,
    pacing_style: str,
    confidence: dict,
) -> str:
    overall = int(confidence.get("overall", 50) or 0)

    energy_adj = ""
    if energy is not None:
        e = float(energy)
        if e > 0.75:
            energy_adj = "High-energy "
        elif e > 0.4:
            energy_adj = "Moderate-energy "
    elif pacing_style == "fast":
        energy_adj = "Fast-paced "
    elif pacing_style == "slow_build":
        energy_adj = "Slow-build "

    emotion_adj = ""
    if emotion not in ("neutral", "default", ""):
        emotion_adj = f"{emotion}-driven "

    mode_label = _MODE_LABELS.get(mode, "edit plan")

    if overall >= 80:
        quality = "Strong "
    elif overall >= 60:
        quality = "Solid "
    elif overall < 40:
        quality = "Basic "
    else:
        quality = ""

    return f"{quality}{energy_adj}{emotion_adj}{mode_label}".strip()


def _build_summary_lines(
    segments: list,
    memory_ctx: dict,
    pacing: Any,
    camera: Any,
    subtitle: Any,
    beat_available: bool,
) -> list[str]:
    lines: list[str] = []

    count = len(segments)
    if count:
        lines.append(f"{count} clip segment{'s' if count != 1 else ''} selected")

    if memory_ctx and memory_ctx.get("results"):
        lines.append("Similar successful renders found in memory")

    if pacing is not None:
        bpm = getattr(pacing, "bpm", None)
        emotion = str(getattr(pacing, "emotion", "neutral")).lower()
        cut_style = str(getattr(pacing, "suggested_cut_style", "standard"))

        if bpm is not None:
            lines.append(f"Beat analysis: {float(bpm):.0f} BPM, {cut_style}")
        elif cut_style not in ("standard", ""):
            lines.append(f"{cut_style.replace('_', ' ').title()} pacing recommended")

        if emotion not in ("neutral", ""):
            lines.append(f"Dominant emotion: {emotion}")

    if beat_available:
        lines.append("Beat synchronization data available")

    if camera is not None:
        behavior = str(getattr(camera, "behavior", "none"))
        if behavior != "none":
            lines.append(f"Camera behavior: {behavior.replace('_', ' ')}")

    if subtitle is not None:
        tone = str(getattr(subtitle, "tone", "default"))
        if tone != "default":
            hl = bool(getattr(subtitle, "highlight_keywords", False))
            hl_note = " with keyword highlighting" if hl else ""
            lines.append(f"Subtitle style: {tone}{hl_note}")

    return lines


def _build_strengths(
    confidence: dict,
    segments: list,
    memory_ctx: dict,
    pacing: Any,
    camera: Any,
    subtitle: Any,
) -> list[str]:
    strengths: list[str] = []

    clip_conf = int(confidence.get("clip_selection", 0) or 0)
    semantic_conf = int(confidence.get("semantic", 0) or 0)
    memory_conf = int(confidence.get("memory", 0) or 0)
    pacing_conf = int(confidence.get("pacing", 0) or 0)
    overall = int(confidence.get("overall", 0) or 0)

    if clip_conf >= 80:
        strengths.append("High-confidence clip selection")
    elif clip_conf >= 60 and segments:
        strengths.append("Good segment coverage")

    if semantic_conf >= 70:
        strengths.append("Strong semantic understanding")

    if memory_conf >= 60:
        strengths.append("Memory context enhanced selection")

    beat_ok = pacing is not None and bool(getattr(pacing, "beat_available", False))
    if pacing_conf >= 80:
        strengths.append("Strong pacing analysis")
    elif pacing_conf >= 60 and beat_ok:
        strengths.append("Beat-synchronized pacing")

    if camera is not None and str(getattr(camera, "behavior", "none")) != "none":
        strengths.append("Adaptive camera behavior planned")

    if subtitle is not None and bool(getattr(subtitle, "beat_aware", False)):
        strengths.append("Beat-aware subtitle density applied")

    if overall >= 80:
        strengths.append("High overall AI confidence")

    return strengths


def _build_warnings(plan_warnings: list[str], confidence: dict) -> list[str]:
    warnings: list[str] = []
    conf_warnings: list[str] = list(confidence.get("warnings", []) or [])

    if "no_transcript_available" in plan_warnings:
        warnings.append("No transcript — AI accuracy reduced")
    if "no_segments_selected" in plan_warnings:
        warnings.append("No clips selected — fallback active")
    if any("rag_error" in w for w in plan_warnings):
        warnings.append("Memory retrieval failed")
    if any("beat_error" in w for w in plan_warnings):
        warnings.append("Beat analysis failed")
    if any("emotion_error" in w for w in plan_warnings):
        warnings.append("Emotion analysis failed")
    if "semantic_confidence_low" in conf_warnings:
        warnings.append("Semantic confidence low")
    if "memory_confidence_low" in conf_warnings:
        warnings.append("Memory confidence low")

    return warnings
