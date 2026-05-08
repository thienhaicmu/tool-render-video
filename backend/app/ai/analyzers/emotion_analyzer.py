"""
emotion_analyzer.py — Lightweight rule-based emotion/pacing analyzer.

No external dependencies. Pure keyword matching on transcript text.
Used by the AI Director to build pacing context for edit planning.

Public API:
    analyze_text_emotion(text: str) -> dict
    analyze_pacing_emotion(chunks: list) -> dict

Return shape:
    {
        "dominant": str,     # emotion label
        "score":    float,   # 0-100
        "signals":  dict,    # {emotion: count} per detected emotion
        "warnings": list[str],
    }
"""
from __future__ import annotations

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Keyword registry
# ---------------------------------------------------------------------------

_EMOTION_KEYWORDS: dict[str, list[str]] = {
    "urgency": [
        "now", "stop", "before", "immediately", "don't", "hurry",
        "quickly", "fast", "urgent", "critical", "deadline", "must",
    ],
    "surprise": [
        "shocked", "unbelievable", "crazy", "unexpected", "wow", "whoa",
        "omg", "suddenly", "never", "wait", "really", "actually",
    ],
    "curiosity": [
        "why", "how", "secret", "nobody", "truth", "hidden", "reveal",
        "discover", "find out", "what if", "did you know", "turns out",
    ],
    "excitement": [
        "amazing", "insane", "best", "finally", "incredible", "awesome",
        "love", "perfect", "great", "unreal", "fantastic", "brilliant",
    ],
    "warning": [
        "careful", "danger", "avoid", "mistake", "bad", "wrong",
        "problem", "risk", "beware", "warning", "caution", "never do",
    ],
}

_ALL_EMOTIONS = list(_EMOTION_KEYWORDS.keys())
_NEUTRAL = "neutral"

# Max raw signal count that maps to score=100
_SCORE_SATURATION = 6


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_text_emotion(text: str) -> dict:
    """Detect dominant emotion in a single text string.

    Returns a safe dict regardless of input quality. Never raises.
    """
    if not text or not isinstance(text, str):
        return _neutral_result(warnings=["empty_text"])

    signals = _count_signals(text)
    return _build_result(signals)


def analyze_pacing_emotion(chunks: list) -> dict:
    """Aggregate emotion signals across a list of transcript chunks.

    Each chunk is expected to have a "text" key (str).
    Falls back gracefully on malformed input. Never raises.
    """
    if not chunks:
        return _neutral_result(warnings=["no_chunks"])

    combined_signals: dict[str, int] = {e: 0 for e in _ALL_EMOTIONS}
    valid_chunks = 0

    for chunk in chunks:
        try:
            text = ""
            if isinstance(chunk, dict):
                text = str(chunk.get("text") or "")
            elif hasattr(chunk, "text"):
                text = str(chunk.text or "")
            else:
                text = str(chunk or "")

            if not text.strip():
                continue

            chunk_signals = _count_signals(text)
            for emotion, count in chunk_signals.items():
                combined_signals[emotion] = combined_signals.get(emotion, 0) + count
            valid_chunks += 1
        except Exception:
            continue

    if valid_chunks == 0:
        return _neutral_result(warnings=["no_valid_chunks"])

    return _build_result(combined_signals)


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _count_signals(text: str) -> dict[str, int]:
    """Count keyword hits per emotion category."""
    normalized = text.lower()
    tokens = set(re.findall(r"\b\w+\b", normalized))
    signals: dict[str, int] = {}

    for emotion, keywords in _EMOTION_KEYWORDS.items():
        count = 0
        for kw in keywords:
            if " " in kw:
                # Multi-word phrase check.
                if kw in normalized:
                    count += 1
            else:
                if kw in tokens:
                    count += 1
        if count:
            signals[emotion] = count

    return signals


def _build_result(signals: dict[str, int]) -> dict:
    if not signals:
        return _neutral_result()

    dominant = max(signals, key=lambda e: signals[e])
    raw_count = signals[dominant]
    score = min(100.0, (raw_count / _SCORE_SATURATION) * 100.0)

    return {
        "dominant": dominant,
        "score": round(score, 1),
        "signals": dict(signals),
        "warnings": [],
    }


def _neutral_result(warnings: Optional[list[str]] = None) -> dict:
    return {
        "dominant": _NEUTRAL,
        "score": 0.0,
        "signals": {},
        "warnings": list(warnings or []),
    }
