"""
subtitle_planner.py — Deterministic subtitle behavior planning for the AI Director.

No external dependencies. Rule-based only. Never raises.
Returns a default AISubtitlePlan on any failure.

Public API:
    plan_subtitle_behavior(
        mode_config: dict,
        pacing_context: dict | None = None,
        memory_context: dict | None = None,
        transcript_context: dict | None = None,
    ) -> AISubtitlePlan
"""
from __future__ import annotations

from typing import Optional

from app.ai.director.edit_plan_schema import AISubtitlePlan

# Emotions that trigger emphasis / keyword highlighting.
_EMPHASIS_EMOTIONS = frozenset({"curiosity", "surprise", "urgency"})


def plan_subtitle_behavior(
    mode_config: dict,
    pacing_context: Optional[dict] = None,
    memory_context: Optional[dict] = None,
    transcript_context: Optional[dict] = None,
) -> AISubtitlePlan:
    """Plan subtitle behavior based on mode, pacing, and emotion signals.

    Returns a safe default AISubtitlePlan on any failure.
    """
    try:
        return _plan(
            mode_config,
            pacing_context or {},
            memory_context or {},
            transcript_context or {},
        )
    except Exception:
        return AISubtitlePlan(reason="subtitle_planner_fallback")


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _plan(
    mode_config: dict,
    pacing_ctx: dict,
    memory_ctx: dict,
    transcript_ctx: dict,
) -> AISubtitlePlan:
    mode_name = str(mode_config.get("mode_name") or "")
    pacing_style = str(
        pacing_ctx.get("pacing_style")
        or mode_config.get("pacing_style")
        or "default"
    )
    emotion = str(pacing_ctx.get("emotion") or "neutral").lower()
    beat_available = bool(pacing_ctx.get("beat_available") or False)

    # ── Base config per mode ──
    tone, highlight, emphasis, max_words, density = _base_for_mode(mode_name, mode_config)

    # ── Beat-aware override ──
    beat_aware = False
    if beat_available and pacing_style == "fast":
        beat_aware = True
        density = "compact"

    # ── Emotion-aware override ──
    emotion_aware = False
    if emotion in _EMPHASIS_EMOTIONS:
        emotion_aware = True
        highlight = True

    reason_parts = [f"mode:{mode_name}" if mode_name else "mode:unknown"]
    if beat_aware:
        reason_parts.append("beat_sync")
    if emotion_aware:
        reason_parts.append(f"emotion:{emotion}")

    return AISubtitlePlan(
        tone=tone,
        highlight_keywords=highlight,
        max_words_per_line=max_words,
        emphasis_style=emphasis,
        density=density,
        beat_aware=beat_aware,
        emotion_aware=emotion_aware,
        reason=", ".join(reason_parts),
    )


def _base_for_mode(
    mode_name: str,
    mode_config: dict,
) -> tuple[str, bool, str, Optional[int], str]:
    """Return (tone, highlight_keywords, emphasis_style, max_words_per_line, density)."""
    if mode_name == "viral_tiktok":
        return (
            "hype",
            True,
            "punch",
            4,
            str(mode_config.get("subtitle_density") or "compact"),
        )
    if mode_name == "podcast_shorts":
        return (
            "clean",
            False,
            "keyword",
            6,
            str(mode_config.get("subtitle_density") or "normal"),
        )
    if mode_name == "storytelling":
        return (
            "story",
            False,
            "soft",
            6,
            str(mode_config.get("subtitle_density") or "normal"),
        )
    if mode_name == "clean_subtitle":
        return (
            "clean",
            False,
            "none",
            7,
            str(mode_config.get("subtitle_density") or "comfortable"),
        )
    # Unknown mode — use mode_config defaults
    return (
        str(mode_config.get("subtitle_tone") or "default"),
        False,
        str(mode_config.get("subtitle_emphasis_style") or "none"),
        None,
        str(mode_config.get("subtitle_density") or "normal"),
    )
