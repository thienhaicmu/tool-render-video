"""
confidence.py — Deterministic AI confidence scoring for the AI Director.

Scores degrade safely when data sources are unavailable.
No ML models, no external deps, no randomization. Never raises.

Public API:
    calculate_ai_confidence(edit_plan) -> dict

Return shape:
    {
        "overall": 0-100,
        "clip_selection": 0-100,
        "semantic": 0-100,
        "memory": 0-100,
        "pacing": 0-100,
        "camera": 0-100,
        "subtitle": 0-100,
        "warnings": []
    }
"""
from __future__ import annotations

from typing import Any


def calculate_ai_confidence(edit_plan: Any) -> dict:
    """Calculate confidence scores (0-100) for each AI dimension.

    Scores degrade when transcript/memory/beat are unavailable.
    Never raises.
    """
    try:
        return _calculate(edit_plan)
    except Exception:
        return _fallback_confidence()


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _calculate(edit_plan: Any) -> dict:
    conf_warnings: list[str] = []

    plan_warnings: list[str] = list(getattr(edit_plan, "warnings", []) or [])
    segments: list = list(getattr(edit_plan, "selected_segments", []) or [])
    memory_ctx: dict = dict(getattr(edit_plan, "memory_context", {}) or {})
    pacing = getattr(edit_plan, "pacing", None)
    camera = getattr(edit_plan, "camera", None)
    subtitle = getattr(edit_plan, "subtitle", None)
    fallback_used: bool = bool(getattr(edit_plan, "fallback_used", False))

    clip_conf = _clip_confidence(segments, plan_warnings, fallback_used)
    semantic_conf = _semantic_confidence(plan_warnings, memory_ctx)
    memory_conf = _memory_confidence(plan_warnings, memory_ctx)
    pacing_conf = _pacing_confidence(pacing, plan_warnings)
    camera_conf = _camera_confidence(camera)
    subtitle_conf = _subtitle_confidence(subtitle)

    if semantic_conf <= 40:
        conf_warnings.append("semantic_confidence_low")
    if memory_conf <= 30:
        conf_warnings.append("memory_confidence_low")

    overall = int(
        clip_conf * 0.30
        + semantic_conf * 0.20
        + memory_conf * 0.15
        + pacing_conf * 0.20
        + camera_conf * 0.075
        + subtitle_conf * 0.075
    )
    overall = max(0, min(100, overall))

    return {
        "overall": overall,
        "clip_selection": clip_conf,
        "semantic": semantic_conf,
        "memory": memory_conf,
        "pacing": pacing_conf,
        "camera": camera_conf,
        "subtitle": subtitle_conf,
        "warnings": conf_warnings,
    }


def _clip_confidence(
    segments: list, plan_warnings: list[str], fallback_used: bool
) -> int:
    if not segments:
        return 20

    scores = [float(getattr(s, "score", 50.0)) for s in segments]
    avg_score = sum(scores) / len(scores)

    base = 70
    if avg_score >= 75:
        base += 20
    elif avg_score >= 60:
        base += 10
    elif avg_score < 40:
        base -= 15

    if fallback_used:
        base -= 15
    if "no_segments_selected" in plan_warnings:
        base = 20

    return max(0, min(100, base))


def _semantic_confidence(plan_warnings: list[str], memory_ctx: dict) -> int:
    for w in plan_warnings:
        if "rag_error" in w:
            return 25
        if "embeddings_unavailable" in w or "semantic_unavailable" in w:
            return 30

    if memory_ctx:
        if memory_ctx.get("results"):
            return 85
        if memory_ctx.get("enabled") is False:
            return 30
        return 60

    return 35


def _memory_confidence(plan_warnings: list[str], memory_ctx: dict) -> int:
    for w in plan_warnings:
        if "rag_error" in w:
            return 20
        if "rag:no_results" in w:
            return 25

    if not memory_ctx:
        return 25

    results = list(memory_ctx.get("results") or [])
    if len(results) >= 3:
        return 80
    if len(results) >= 1:
        return 60

    if memory_ctx.get("enabled") is False:
        return 20

    return 30


def _pacing_confidence(pacing: Any, plan_warnings: list[str]) -> int:
    if pacing is None:
        return 40

    base = 60

    beat_available = bool(getattr(pacing, "beat_available", False))
    emotion = str(getattr(pacing, "emotion", "neutral")).lower()
    emotion_score = float(getattr(pacing, "emotion_score", 0.0))
    energy = getattr(pacing, "energy_level", None)

    if beat_available:
        base += 20
    else:
        for w in plan_warnings:
            if "beat_analysis_unavailable" in w or "beat_error" in w:
                base -= 10

    if emotion != "neutral" and emotion_score > 0.2:
        base += 10

    if energy is not None:
        base += 5

    return max(0, min(100, base))


def _camera_confidence(camera: Any) -> int:
    if camera is None:
        return 50

    behavior = str(getattr(camera, "behavior", "none"))
    reason = str(getattr(camera, "reason", ""))

    if "fallback" in reason.lower():
        return 50
    if behavior == "none":
        return 70
    return 75


def _subtitle_confidence(subtitle: Any) -> int:
    if subtitle is None:
        return 50

    tone = str(getattr(subtitle, "tone", "default"))
    reason = str(getattr(subtitle, "reason", ""))

    if "fallback" in reason.lower():
        return 50
    if tone == "default":
        return 50
    return 75


def _fallback_confidence() -> dict:
    return {
        "overall": 0,
        "clip_selection": 0,
        "semantic": 0,
        "memory": 0,
        "pacing": 0,
        "camera": 0,
        "subtitle": 0,
        "warnings": ["confidence_calculation_failed"],
    }
