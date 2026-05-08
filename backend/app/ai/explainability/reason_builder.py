"""
reason_builder.py — Deterministic human-readable AI reason generation.

Explains clip, camera, subtitle, and pacing decisions from the AI edit plan.
No randomization, no hallucination, no external deps. Never raises.

Public API:
    build_clip_reasons(segments, memory_context) -> list[str]
    build_camera_reasons(camera_plan, pacing_plan) -> list[str]
    build_subtitle_reasons(subtitle_plan, pacing_plan) -> list[str]
    build_pacing_reasons(pacing_plan) -> list[str]
"""
from __future__ import annotations

_MAX_REASONS = 5


def build_clip_reasons(
    segments: list,
    memory_context: dict,
) -> list[str]:
    """Return up to 5 deduplicated reasons why clips were selected."""
    try:
        return _dedupe(_clip_reasons(segments, memory_context))
    except Exception:
        return []


def build_camera_reasons(
    camera_plan: object,
    pacing_plan: object,
) -> list[str]:
    """Return up to 5 deduplicated reasons for camera behavior."""
    try:
        return _dedupe(_camera_reasons(camera_plan, pacing_plan))
    except Exception:
        return []


def build_subtitle_reasons(
    subtitle_plan: object,
    pacing_plan: object,
) -> list[str]:
    """Return up to 5 deduplicated reasons for subtitle behavior."""
    try:
        return _dedupe(_subtitle_reasons(subtitle_plan, pacing_plan))
    except Exception:
        return []


def build_pacing_reasons(
    pacing_plan: object,
) -> list[str]:
    """Return up to 5 deduplicated reasons for pacing decisions."""
    try:
        return _dedupe(_pacing_reasons(pacing_plan))
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal builders
# ---------------------------------------------------------------------------

def _clip_reasons(segments: list, memory_context: dict) -> list[str]:
    reasons: list[str] = []

    if not segments:
        reasons.append("no segments selected — fallback active")
        return reasons

    scores = [float(getattr(s, "score", 50.0)) for s in segments]
    avg_score = sum(scores) / len(scores)
    max_score = max(scores)

    if max_score >= 80:
        reasons.append("high-confidence hook segment detected")
    elif avg_score >= 60:
        reasons.append("above-average speech density segments selected")

    all_reason_text = " ".join(getattr(s, "reason", "") for s in segments).lower()
    if "hook" in all_reason_text:
        reasons.append("strong curiosity hook detected")
    if "speech" in all_reason_text or "density" in all_reason_text:
        reasons.append("high speech density prioritized")
    if "scene" in all_reason_text:
        reasons.append("scene-aligned clip boundaries")

    if memory_context and memory_context.get("results"):
        reasons.append("past render patterns used for selection")
    elif memory_context and memory_context.get("enabled"):
        reasons.append("memory context active")

    if len(segments) > 1:
        reasons.append("local AI semantic scoring applied")

    return reasons


def _camera_reasons(camera_plan: object, pacing_plan: object) -> list[str]:
    reasons: list[str] = []
    behavior = str(getattr(camera_plan, "behavior", "none"))
    emotion = str(getattr(pacing_plan, "emotion", "neutral")).lower()
    energy = getattr(pacing_plan, "energy_level", None)
    pacing_style = str(getattr(pacing_plan, "pacing_style", "default"))

    if behavior == "none":
        reasons.append("camera motion disabled for clean output")
        return reasons

    if behavior == "dramatic_push":
        reasons.append(f"strong {emotion} emotion triggered dramatic camera push")
    elif behavior == "fast_follow":
        if energy is not None and float(energy) > 0.75:
            reasons.append(f"high audio energy ({float(energy):.2f}) matched fast camera follow")
        else:
            reasons.append("fast pacing matched fast camera follow")
    elif behavior == "slow_reveal":
        reasons.append("slow pacing matched gradual camera reveal")
    elif behavior == "emotional_push":
        reasons.append("emotional content selected push camera behavior")
    elif behavior == "subtle_follow":
        reasons.append("conversational pacing selected subtle camera follow")
    else:
        reasons.append(f"mode default camera behavior: {behavior}")

    zoom = float(getattr(camera_plan, "zoom_strength", 1.0))
    if zoom > 1.08:
        reasons.append(f"strong zoom ({zoom:.2f}x) for high-energy content")
    elif zoom > 1.0:
        reasons.append(f"subtle zoom ({zoom:.2f}x) applied")

    return reasons


def _subtitle_reasons(subtitle_plan: object, pacing_plan: object) -> list[str]:
    reasons: list[str] = []
    tone = str(getattr(subtitle_plan, "tone", "default"))
    highlight = bool(getattr(subtitle_plan, "highlight_keywords", False))
    beat_aware = bool(getattr(subtitle_plan, "beat_aware", False))
    emotion_aware = bool(getattr(subtitle_plan, "emotion_aware", False))
    density = str(getattr(subtitle_plan, "density", "normal"))
    emphasis = str(getattr(subtitle_plan, "emphasis_style", "none"))
    emotion = str(getattr(pacing_plan, "emotion", "neutral")).lower()

    if tone == "hype":
        reasons.append("hype subtitle style selected for viral content")
    elif tone == "story":
        reasons.append("narrative subtitle style selected for storytelling")
    elif tone == "clean":
        reasons.append("clean subtitle style for professional readability")

    if highlight:
        if emotion_aware:
            reasons.append(f"keyword highlighting enabled for {emotion} emotion")
        else:
            reasons.append("keyword highlighting enabled")

    if beat_aware:
        reasons.append("compact subtitle pacing for beat-synced content")

    if density == "compact":
        reasons.append("compact subtitle density for fast-paced content")
    elif density == "comfortable":
        reasons.append("comfortable subtitle spacing for readability")

    if emphasis == "punch":
        reasons.append("punch emphasis style for maximum impact")
    elif emphasis == "keyword":
        reasons.append("keyword emphasis for speech clarity")

    return reasons


def _pacing_reasons(pacing_plan: object) -> list[str]:
    reasons: list[str] = []
    bpm = getattr(pacing_plan, "bpm", None)
    emotion = str(getattr(pacing_plan, "emotion", "neutral")).lower()
    emotion_score = float(getattr(pacing_plan, "emotion_score", 0.0))
    cut_style = str(getattr(pacing_plan, "suggested_cut_style", "standard"))
    pacing_style = str(getattr(pacing_plan, "pacing_style", "default"))
    beat_available = bool(getattr(pacing_plan, "beat_available", False))
    energy = getattr(pacing_plan, "energy_level", None)

    if bpm is not None:
        reasons.append(f"BPM analysis: {float(bpm):.0f} BPM → {cut_style}")
    elif pacing_style not in ("default", ""):
        reasons.append(f"mode pacing style: {pacing_style} → {cut_style}")

    if emotion != "neutral" and emotion_score > 0.1:
        reasons.append(f"{emotion} emotion detected (score: {emotion_score:.2f})")

    if beat_available:
        reasons.append("beat synchronization data available")

    if energy is not None:
        e = float(energy)
        if e > 0.75:
            reasons.append(f"high audio energy ({e:.2f}) detected")
        elif e > 0.4:
            reasons.append(f"moderate audio energy ({e:.2f}) detected")

    return reasons


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dedupe(reasons: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for r in reasons:
        if r not in seen:
            seen.add(r)
            result.append(r)
        if len(result) >= _MAX_REASONS:
            break
    return result
