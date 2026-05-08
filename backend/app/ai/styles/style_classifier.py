"""
style_classifier.py — Deterministic creator style classifier. Phase 14.

Scores transcript/pacing/emotion/story signals against known editing
archetypes and returns the best match. No external deps, no ML models,
no API calls. Deterministic and fallback-safe.

Public API:
    classify_creator_style(
        transcript_context=None,
        pacing_context=None,
        emotion_context=None,
        story_context=None,
        memory_context=None,
    ) -> StyleClassification
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.ai.styles.style_schema import StyleClassification
from app.ai.styles.style_profiles import STYLE_IDS

logger = logging.getLogger("app.ai.styles.classifier")


def classify_creator_style(
    transcript_context: Optional[dict] = None,
    pacing_context: Optional[dict] = None,
    emotion_context: Optional[dict] = None,
    story_context: Optional[dict] = None,
    memory_context: Optional[dict] = None,
) -> StyleClassification:
    """Classify editing signals into a known creator archetype.

    Args:
        transcript_context: {"text": str, "chunk_count": int, "hook_intensity": float}
        pacing_context:     {"energy_level": float, "pacing_style": str, "emotion": str, "bpm": float|None}
        emotion_context:    {"dominant": str, "score": float}
        story_context:      {"narrative_flow": str, "dominant_arc": str, "retention_score": float}
        memory_context:     dict from RAG retriever (reserved, not yet used)

    Returns:
        StyleClassification — never raises; returns unknown/available=False on error.
    """
    try:
        return _classify(
            transcript_context or {},
            pacing_context or {},
            emotion_context or {},
            story_context or {},
        )
    except Exception as exc:
        logger.debug("classify_creator_style_failed: %s", exc)
        return StyleClassification(
            available=False,
            warnings=[f"style_classification_error:{type(exc).__name__}"],
        )


# ── Internal classification ───────────────────────────────────────────────────

def _classify(
    transcript_ctx: dict,
    pacing_ctx: dict,
    emotion_ctx: dict,
    story_ctx: dict,
) -> StyleClassification:
    signals = _build_signals(transcript_ctx, pacing_ctx, emotion_ctx, story_ctx)

    # Score all archetypes
    scored: list[tuple[float, str, list[str]]] = []
    for style_id in STYLE_IDS:
        score, traits = _score_style(style_id, signals)
        scored.append((score, style_id, traits))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored or scored[0][0] <= 0:
        return StyleClassification(
            available=True,
            dominant_style="unknown",
            confidence=0.0,
            warnings=["no_style_signal_matched"],
        )

    best_score, best_id, best_traits = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    secondary = [sid for _, sid, _ in scored[1:4] if _ and sid != best_id]

    confidence = _compute_confidence(best_score, second_score)

    logger.info(
        "ai_creator_style_classified style=%s confidence=%.1f traits=%d",
        best_id, confidence, len(best_traits),
    )

    return StyleClassification(
        available=True,
        dominant_style=best_id,
        confidence=confidence,
        secondary_styles=secondary[:3],
        matched_traits=best_traits[:6],
    )


# ── Signal extraction ─────────────────────────────────────────────────────────

def _build_signals(
    transcript_ctx: dict,
    pacing_ctx: dict,
    emotion_ctx: dict,
    story_ctx: dict,
) -> dict:
    energy = _f(pacing_ctx.get("energy_level"), 0.5)
    pacing = str(pacing_ctx.get("pacing_style") or "default").lower()
    emotion = str(pacing_ctx.get("emotion") or "neutral").lower()
    bpm = _f(pacing_ctx.get("bpm"), None)

    # emotion_context overrides pacing emotion if richer
    if emotion_ctx:
        dominant = str(emotion_ctx.get("dominant") or "").lower()
        if dominant:
            emotion = dominant

    narrative_flow = str(story_ctx.get("narrative_flow") or "unknown").lower()
    dominant_arc = str(story_ctx.get("dominant_arc") or "unknown").lower()
    retention_score = _f(story_ctx.get("retention_score"), 50.0)

    chunk_count = int(transcript_ctx.get("chunk_count") or 0)
    hook_intensity = _f(transcript_ctx.get("hook_intensity"), 0.5)

    return {
        "energy_level": energy,
        "pacing_style": pacing,
        "emotion": emotion,
        "bpm": bpm,
        "narrative_flow": narrative_flow,
        "dominant_arc": dominant_arc,
        "retention_score": retention_score,
        "chunk_count": chunk_count,
        "hook_intensity": hook_intensity,
    }


# ── Per-archetype scoring ─────────────────────────────────────────────────────

def _score_style(style_id: str, s: dict) -> tuple[float, list[str]]:
    """Score signals for one archetype. Returns (score, matched_traits)."""
    energy: float = s["energy_level"]
    pacing: str = s["pacing_style"]
    emotion: str = s["emotion"]
    bpm = s["bpm"]
    narrative_flow: str = s["narrative_flow"]
    dominant_arc: str = s["dominant_arc"]
    chunk_count: int = s["chunk_count"]

    score = 0.0
    traits: list[str] = []

    if style_id == "podcast_viral":
        if energy > 0.60:
            score += 20; traits.append("high energy")
        if pacing in ("fast", "dynamic"):
            score += 15; traits.append("fast pacing")
        if emotion in ("urgency", "excitement"):
            score += 15; traits.append("urgency/excitement signal")
        if narrative_flow in ("hook_to_climax", "front_loaded"):
            score += 10; traits.append("hook-forward narrative")
        if bpm is not None and bpm >= 110:
            score += 10; traits.append("high BPM")

    elif style_id == "high_energy_reaction":
        if energy > 0.75:
            score += 25; traits.append("very high energy")
        if emotion in ("surprise", "excitement"):
            score += 20; traits.append("surprise/excitement emotion")
        if pacing == "fast":
            score += 10; traits.append("fast pacing")
        if bpm is not None and bpm >= 130:
            score += 10; traits.append("high BPM")
        if dominant_arc == "emotional_peak":
            score += 10; traits.append("emotional peak arc")

    elif style_id == "storytelling_cinematic":
        if dominant_arc in ("curiosity_build", "setup_payoff", "tension_release"):
            score += 25; traits.append("strong narrative arc")
        if narrative_flow in ("hook_to_climax", "hook_to_payoff", "linear_build"):
            score += 15; traits.append("structured narrative flow")
        if emotion in ("curiosity",):
            score += 15; traits.append("curiosity-driven emotion")
        if pacing in ("slow_build", "medium", "default"):
            score += 10; traits.append("measured pacing")

    elif style_id == "documentary_clean":
        if energy < 0.35:
            score += 20; traits.append("low energy")
        if pacing in ("slow", "default") and energy < 0.45:
            score += 15; traits.append("calm pacing")
        if emotion in ("neutral", "calm"):
            score += 15; traits.append("neutral/calm tone")
        if narrative_flow == "flat":
            score += 10; traits.append("flat narrative structure")

    elif style_id == "educational_focus":
        if dominant_arc == "informational":
            score += 25; traits.append("informational arc")
        if emotion in ("curiosity",):
            score += 15; traits.append("curiosity-driven tone")
        if pacing in ("medium", "default"):
            score += 10; traits.append("measured pacing")
        if chunk_count > 10:
            score += 10; traits.append("high transcript density")

    elif style_id == "anime_edit":
        if energy > 0.80:
            score += 25; traits.append("very high energy")
        if bpm is not None and bpm >= 140:
            score += 20; traits.append("very high BPM")
        if dominant_arc in ("tension_release", "emotional_peak"):
            score += 15; traits.append("peak emotional arc")
        if pacing == "fast":
            score += 10; traits.append("fast pacing")

    elif style_id == "gameplay_highlight":
        if energy > 0.65:
            score += 20; traits.append("high energy")
        if pacing == "fast":
            score += 15; traits.append("fast pacing")
        if emotion in ("excitement",):
            score += 15; traits.append("excitement-driven emotion")
        if dominant_arc == "emotional_peak":
            score += 10; traits.append("peak moment arc")

    elif style_id == "motivation_short":
        if emotion in ("urgency", "excitement"):
            score += 20; traits.append("urgency/excitement")
        if dominant_arc in ("curiosity_build", "emotional_peak"):
            score += 15; traits.append("motivational arc")
        if narrative_flow == "front_loaded":
            score += 15; traits.append("front-loaded narrative")
        if 0.45 <= energy <= 0.80:
            score += 10; traits.append("moderate-high energy")

    elif style_id == "interview_clip":
        if pacing in ("slow", "medium", "default") and energy < 0.55:
            score += 20; traits.append("relaxed pacing")
        if emotion in ("neutral", "curiosity"):
            score += 15; traits.append("neutral/curious tone")
        if dominant_arc in ("informational",):
            score += 15; traits.append("informational arc")
        if energy < 0.50:
            score += 10; traits.append("lower energy level")

    elif style_id == "calm_minimal":
        if energy < 0.30:
            score += 25; traits.append("very low energy")
        if pacing == "slow":
            score += 20; traits.append("slow pacing")
        if emotion in ("neutral", "calm"):
            score += 15; traits.append("calm/neutral tone")
        if narrative_flow == "flat":
            score += 10; traits.append("minimal narrative structure")

    return score, traits


# ── Confidence calculation ────────────────────────────────────────────────────

def _compute_confidence(best_score: float, second_score: float) -> float:
    if best_score <= 0:
        return 0.0
    # Base: scale absolute score to 0-80 range (max ~75 raw points)
    base = min(75.0, best_score)
    # Clarity bonus when gap is large
    gap = best_score - max(0.0, second_score)
    clarity = min(25.0, gap * 0.8)
    return round(min(100.0, base + clarity), 1)


# ── Utility ───────────────────────────────────────────────────────────────────

def _f(val: Any, default: Any) -> Any:
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default
