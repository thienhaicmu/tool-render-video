"""
camera_planner.py — Deterministic camera behavior planning for the AI Director.

No external dependencies. Rule-based only. Never raises.
Returns a default AICameraPlan on any failure.

Public API:
    plan_camera_behavior(
        mode_config: dict,
        pacing_context: dict | None = None,
        memory_context: dict | None = None,
        transcript_context: dict | None = None,
    ) -> AICameraPlan
"""
from __future__ import annotations

from typing import Optional

from app.ai.director.edit_plan_schema import AICameraPlan


def plan_camera_behavior(
    mode_config: dict,
    pacing_context: Optional[dict] = None,
    memory_context: Optional[dict] = None,
    transcript_context: Optional[dict] = None,
) -> AICameraPlan:
    """Plan camera behavior based on mode, pacing, and emotion signals.

    Returns a safe default AICameraPlan on any failure.
    subtitle_safe is always True.
    """
    try:
        return _plan(
            mode_config,
            pacing_context or {},
            memory_context or {},
            transcript_context or {},
        )
    except Exception:
        return AICameraPlan(
            mode="auto",
            behavior="none",
            subtitle_safe=True,
            reason="camera_planner_fallback",
        )


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _plan(
    mode_config: dict,
    pacing_ctx: dict,
    memory_ctx: dict,
    transcript_ctx: dict,
) -> AICameraPlan:
    mode_name = str(mode_config.get("mode_name") or "")
    pacing_style = str(
        pacing_ctx.get("pacing_style")
        or mode_config.get("pacing_style")
        or "default"
    )
    energy_level: Optional[float] = _safe_float(pacing_ctx.get("energy_level"))
    emotion = str(pacing_ctx.get("emotion") or "neutral").lower()
    default_behavior = str(mode_config.get("camera_behavior") or "none")
    default_zoom = float(mode_config.get("camera_zoom_strength") or 1.0)

    # ── Priority 1: clean_subtitle — camera disabled ──
    if mode_name == "clean_subtitle" or default_behavior == "none":
        return AICameraPlan(
            mode="auto",
            behavior="none",
            subtitle_safe=True,
            zoom_strength=1.0,
            follow_strength=0.5,
            reason="clean_subtitle: camera disabled",
        )

    # ── Priority 2: strong emotion → dramatic push ──
    if emotion in ("surprise", "urgency"):
        return AICameraPlan(
            mode="auto",
            behavior="dramatic_push",
            subtitle_safe=True,
            zoom_strength=1.12,
            follow_strength=0.65,
            reason=f"emotion={emotion}: dramatic push",
        )

    # ── Priority 3: fast pacing or high energy → fast follow ──
    high_energy = energy_level is not None and energy_level > 0.75
    if pacing_style == "fast" or high_energy:
        energy_note = f"energy={energy_level:.2f}" if high_energy else "pacing=fast"
        return AICameraPlan(
            mode="auto",
            behavior="fast_follow",
            subtitle_safe=True,
            zoom_strength=1.10,
            follow_strength=0.75,
            reason=f"fast pacing/energy: {energy_note}",
        )

    # ── Priority 4: storytelling / slow build → slow reveal ──
    if mode_name == "storytelling" or pacing_style == "slow_build":
        return AICameraPlan(
            mode="auto",
            behavior="slow_reveal",
            subtitle_safe=True,
            zoom_strength=1.05,
            follow_strength=0.45,
            reason="storytelling/slow_build: gradual reveal",
        )

    # ── Default: use mode config values ──
    return AICameraPlan(
        mode="auto",
        behavior=default_behavior,
        subtitle_safe=True,
        zoom_strength=default_zoom,
        follow_strength=0.5,
        reason=f"mode_default:{mode_name or 'unknown'}",
    )


def _safe_float(val: object) -> Optional[float]:
    try:
        return float(val)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
