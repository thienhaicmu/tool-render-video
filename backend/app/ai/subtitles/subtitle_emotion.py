"""
subtitle_emotion.py — Subtitle emotion style intelligence. Phase 17.

Deterministic heuristics only. Never raises.
Maps pacing/emotion/story signals to subtitle emotion styles.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.subtitles")

VALID_EMOTION_STYLES: frozenset[str] = frozenset({
    "neutral", "hype", "dramatic", "calm", "emotional", "punch"
})

_EMOTION_STYLE_MAP: dict[str, str] = {
    "urgency": "punch",
    "excitement": "hype",
    "hype": "hype",
    "surprise": "punch",
    "anger": "dramatic",
    "sadness": "emotional",
    "emotional": "emotional",
    "curiosity": "dramatic",
    "calm": "calm",
    "boredom": "calm",
    "neutral": "neutral",
}

_PACING_STYLE_MAP: dict[str, str] = {
    "fast": "punch",
    "dynamic": "hype",
    "medium_fast": "hype",
    "medium": "neutral",
    "slow_build": "dramatic",
    "slow": "calm",
}

_ARC_STYLE_MAP: dict[str, str] = {
    "tension_release": "dramatic",
    "curiosity_build": "dramatic",
    "emotional_peak": "emotional",
    "front_loaded": "punch",
    "setup_payoff": "dramatic",
    "linear_build": "neutral",
    "informational": "calm",
}

_CREATOR_STYLE_MAP: dict[str, str] = {
    "podcast_viral": "punch",
    "high_energy_reaction": "hype",
    "storytelling_cinematic": "dramatic",
    "documentary_clean": "calm",
    "educational_focus": "neutral",
    "anime_edit": "hype",
    "gameplay_highlight": "punch",
    "motivation_short": "punch",
    "interview_clip": "calm",
    "calm_minimal": "calm",
}


def detect_subtitle_emotion_style(
    emotion_context=None,
    story_context=None,
    creator_style_context=None,
) -> dict:
    """Map pacing/emotion/story signals to a subtitle emotion style.

    Returns compact dict: available, emotion_style, confidence, signals,
    warnings. Never raises.
    """
    try:
        return _detect_emotion_style(emotion_context, story_context, creator_style_context)
    except Exception as exc:
        logger.debug("subtitle_emotion_style_failed: %s", exc)
        return {
            "available": False,
            "emotion_style": "neutral",
            "confidence": 0.0,
            "signals": [],
            "warnings": [f"emotion_style_error:{type(exc).__name__}"],
        }


def _detect_emotion_style(
    emotion_context,
    story_context,
    creator_style_context,
) -> dict:
    emotion_ctx = dict(emotion_context or {})
    story_ctx = dict(story_context or {})
    creator_ctx = dict(creator_style_context or {})

    scores: dict[str, float] = {s: 0.0 for s in VALID_EMOTION_STYLES}
    signals: list[str] = []
    warnings: list[str] = []

    # Emotion contribution (highest weight)
    emotion = str(
        emotion_ctx.get("emotion") or emotion_ctx.get("dominant") or "neutral"
    ).lower()
    emotion_score = float(
        emotion_ctx.get("emotion_score") or emotion_ctx.get("score") or 0.0
    )
    pacing_style = str(emotion_ctx.get("pacing_style") or "").lower()

    mapped = _EMOTION_STYLE_MAP.get(emotion, "neutral")
    if mapped != "neutral":
        scores[mapped] = scores.get(mapped, 0.0) + 0.4 + emotion_score * 0.2
        signals.append(f"emotion:{emotion}")

    # Pacing style contribution
    if pacing_style:
        pacing_mapped = _PACING_STYLE_MAP.get(pacing_style)
        if pacing_mapped:
            scores[pacing_mapped] = scores.get(pacing_mapped, 0.0) + 0.3
            signals.append(f"pacing:{pacing_style}")

    # Story arc contribution
    dominant_arc = str(story_ctx.get("dominant_arc") or "").lower()
    if dominant_arc:
        arc_mapped = _ARC_STYLE_MAP.get(dominant_arc)
        if arc_mapped:
            scores[arc_mapped] = scores.get(arc_mapped, 0.0) + 0.2
            signals.append(f"arc:{dominant_arc}")

    # Creator style hint
    creator_style = str(creator_ctx.get("dominant_style") or "").lower()
    if creator_style and creator_style not in ("unknown", ""):
        cs_mapped = _CREATOR_STYLE_MAP.get(creator_style)
        if cs_mapped:
            scores[cs_mapped] = scores.get(cs_mapped, 0.0) + 0.15
            signals.append(f"creator_style:{creator_style}")

    # Select dominant style
    if all(v == 0.0 for v in scores.values()):
        dominant = "neutral"
        confidence = 0.0
    else:
        dominant = max(scores, key=lambda k: scores[k])
        top_score = scores[dominant]
        sorted_scores = sorted(scores.values(), reverse=True)
        second_score = sorted_scores[1] if len(sorted_scores) > 1 else 0.0
        confidence = min(1.0, top_score * 0.8 + (top_score - second_score) * 0.4)
        confidence = round(confidence, 3)

    logger.debug(
        "subtitle_emotion_style_detected style=%s confidence=%.3f signals=%s",
        dominant, confidence, signals,
    )

    return {
        "available": True,
        "emotion_style": dominant,
        "confidence": confidence,
        "signals": signals[:6],
        "warnings": warnings,
    }
