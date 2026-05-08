"""
subtitle_emphasis.py — Subtitle emphasis intelligence. Phase 17.

Deterministic heuristics only. Never raises. No transcript mutation.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.ai.subtitles")

_HOOK_KEYWORDS: frozenset[str] = frozenset({
    "wait", "stop", "listen", "this", "you", "never", "always", "secret",
    "truth", "real", "best", "worst", "only", "first", "must", "need",
    "why", "how", "what", "amazing", "incredible", "important", "now",
    "today", "change", "know", "think", "watch", "look", "see", "believe",
})


def build_subtitle_emphasis(
    transcript_chunks=None,
    pacing_context=None,
    emotion_context=None,
    retention_context=None,
) -> dict:
    """Build subtitle emphasis metadata from transcript and context signals.

    Returns compact dict: available, emphasis_strength, beat_sync_strength,
    keyword_focus, hook_strength, warnings. Never raises.
    """
    try:
        return _build_emphasis(transcript_chunks, pacing_context, emotion_context, retention_context)
    except Exception as exc:
        logger.debug("subtitle_emphasis_failed: %s", exc)
        return {
            "available": False,
            "emphasis_strength": 0.0,
            "beat_sync_strength": 0.0,
            "keyword_focus": [],
            "hook_strength": 0.0,
            "warnings": [f"emphasis_error:{type(exc).__name__}"],
        }


def _build_emphasis(
    transcript_chunks,
    pacing_context,
    emotion_context,
    retention_context,
) -> dict:
    chunks = list(transcript_chunks or [])
    pacing_ctx = dict(pacing_context or {})
    emotion_ctx = dict(emotion_context or {})
    retention_ctx = dict(retention_context or {})

    emphasis_strength = 0.0
    beat_sync_strength = 0.0
    warnings: list[str] = []

    # Hook strength from early transcript
    hook_strength = _detect_hook_strength(chunks)
    emphasis_strength += hook_strength * 0.5

    # Emotion contribution
    emotion = str(
        pacing_ctx.get("emotion") or emotion_ctx.get("dominant") or "neutral"
    ).lower()
    emotion_score = float(
        pacing_ctx.get("emotion_score") or emotion_ctx.get("score") or 0.0
    )
    if emotion in ("urgency", "excitement", "surprise", "hype"):
        emphasis_strength += 0.3 + emotion_score * 0.2
    elif emotion in ("sadness", "emotional"):
        emphasis_strength += 0.2

    # Energy level drives pacing peaks
    energy_level = pacing_ctx.get("energy_level")
    if energy_level is not None:
        try:
            e = float(energy_level)
            if e > 0.7:
                emphasis_strength += 0.25
                beat_sync_strength += 0.3
            elif e > 0.4:
                emphasis_strength += 0.1
                beat_sync_strength += 0.1
        except (TypeError, ValueError):
            pass

    # Beat availability
    if pacing_ctx.get("beat_available"):
        beat_sync_strength += 0.2
        bpm = pacing_ctx.get("bpm")
        if bpm is not None:
            try:
                if float(bpm) >= 120:
                    beat_sync_strength += 0.2
            except (TypeError, ValueError):
                pass

    # Retention hook risk increases emphasis
    risk_regions = retention_ctx.get("risk_regions", [])
    has_hook_risk = any(
        isinstance(r, dict) and r.get("category") in ("weak_hook", "long_setup")
        for r in (risk_regions or [])[:5]
    )
    if has_hook_risk:
        emphasis_strength += 0.1

    # Keyword focus from early chunks
    keyword_focus = _extract_keyword_focus(chunks[:5])
    if not keyword_focus and has_hook_risk:
        warnings.append("no_keyword_focus_detected")

    # Clamp
    emphasis_strength = max(0.0, min(1.0, emphasis_strength))
    beat_sync_strength = max(0.0, min(1.0, beat_sync_strength))

    logger.info(
        "ai_subtitle_emphasis_generated emphasis=%.3f beat_sync=%.3f keywords=%d",
        emphasis_strength, beat_sync_strength, len(keyword_focus),
    )

    return {
        "available": True,
        "emphasis_strength": round(emphasis_strength, 3),
        "beat_sync_strength": round(beat_sync_strength, 3),
        "keyword_focus": keyword_focus[:10],
        "hook_strength": round(hook_strength, 3),
        "warnings": warnings,
    }


def _detect_hook_strength(chunks: list) -> float:
    """Estimate hook strength from early transcript keyword density."""
    if not chunks:
        return 0.0
    early = [c for c in chunks[:3] if isinstance(c, dict)]
    total_words = 0
    hook_words = 0
    for c in early:
        text = str(c.get("text") or "").lower()
        words = text.split()
        total_words += len(words)
        hook_words += sum(1 for w in words if w.strip(".,!?\"'") in _HOOK_KEYWORDS)
    if total_words == 0:
        return 0.0
    ratio = hook_words / total_words
    if ratio >= 0.15:
        return 0.85
    if ratio >= 0.08:
        return 0.6
    if ratio >= 0.03:
        return 0.3
    return 0.1


def _extract_keyword_focus(chunks: list) -> list[str]:
    """Extract high-value keywords from early transcript chunks."""
    seen: set[str] = set()
    result: list[str] = []
    for c in chunks:
        if not isinstance(c, dict):
            continue
        text = str(c.get("text") or "").lower()
        for word in text.split():
            w = word.strip(".,!?\"'")
            if len(w) >= 4 and w in _HOOK_KEYWORDS and w not in seen:
                seen.add(w)
                result.append(w)
    return result[:10]
