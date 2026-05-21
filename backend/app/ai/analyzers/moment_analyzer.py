"""
moment_analyzer.py — Goal-aware best moment scorer (S2.2).

Scores the full content window of a clip candidate — not just its opening hook.
Detects peak emotional intensity, goal-relevant keyword density, and emotional arc.

Set BEST_MOMENT_INTELLIGENCE_ENABLED=0 to disable entirely (rollback gate).

Public API:
    get_window_chunks(chunks, candidate_start, candidate_end) -> list[dict]
    score_best_moment(chunks, candidate_start, candidate_end, goal) -> float ([0, +20])
    BEST_MOMENT_INTELLIGENCE_ENABLED: bool
"""
from __future__ import annotations

import os

BEST_MOMENT_INTELLIGENCE_ENABLED: bool = (
    os.environ.get("BEST_MOMENT_INTELLIGENCE_ENABLED", "1") == "1"
)

# ---------------------------------------------------------------------------
# Goal-aware emotion weighting
# Applied to each chunk's dominant emotion score before taking the peak.
# Multipliers bias toward emotions that resonate with the creator's goal.
# Neutral goal uses 1.0 throughout.
# ---------------------------------------------------------------------------

_GOAL_EMOTION_WEIGHTS: dict[str, dict[str, float]] = {
    "viral": {
        "urgency":   1.8,
        "surprise":  2.0,
        "curiosity": 1.5,
        "excitement":2.0,
        "warning":   0.7,
    },
    "education": {
        "urgency":   1.0,
        "surprise":  0.6,
        "curiosity": 1.8,
        "excitement":1.0,
        "warning":   1.8,
    },
    "podcast": {
        "urgency":   0.6,
        "surprise":  1.5,
        "curiosity": 1.8,
        "excitement":1.2,
        "warning":   0.8,
    },
    "product": {
        "urgency":   1.5,
        "surprise":  1.5,
        "curiosity": 1.0,
        "excitement":1.8,
        "warning":   0.8,
    },
    "storytelling": {
        "urgency":   0.5,
        "surprise":  2.0,
        "curiosity": 1.5,
        "excitement":1.5,
        "warning":   0.6,
    },
}

# ---------------------------------------------------------------------------
# Goal-specific keyword sets for full-window density scoring
# ---------------------------------------------------------------------------

_GOAL_KEYWORDS: dict[str, list[str]] = {
    "viral": [
        "reaction", "insane", "crazy", "wait", "you won't believe",
        "no way", "omg", "seriously", "actually", "plot twist",
    ],
    "education": [
        "here's how", "the answer", "this means", "the key is",
        "for example", "in other words", "proof", "because", "the reason",
    ],
    "podcast": [
        "the thing is", "actually", "here's what", "the point is",
        "interesting", "but wait", "think about", "consider", "what i mean",
    ],
    "product": [
        "result", "before", "after", "proof", "it works", "you can",
        "transform", "difference", "better", "improved",
    ],
    "storytelling": [
        "suddenly", "then", "everything changed", "at that moment",
        "finally", "that's when", "realized", "turned out", "never expected",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_window_chunks(
    chunks: list[dict],
    candidate_start: float,
    candidate_end: float,
) -> list[dict]:
    """Filter transcript chunks that fall within the candidate window."""
    return [
        c for c in (chunks or [])
        if float(c.get("end") or 0.0) > candidate_start
        and float(c.get("start") or 0.0) < candidate_end
    ]


def score_best_moment(
    chunks: list[dict],
    candidate_start: float,
    candidate_end: float,
    goal: str = "",
) -> float:
    """Score best-moment quality across the full candidate window.

    Returns an additive bonus in [0, +20]. Returns 0.0 when:
      - BEST_MOMENT_INTELLIGENCE_ENABLED is False (env gate)
      - chunks is empty or no window chunks found (graceful degradation)

    Weighting (S2.2):
      peak_emotion  60% — single strongest moment in the window drives score
      goal_density  25% — goal-relevant keyword presence across full window
      emotion_arc   15% — rising emotional arc (conservative weight; prone to
                          false positives in podcasts / tutorials)
    """
    if not BEST_MOMENT_INTELLIGENCE_ENABLED or not chunks:
        return 0.0

    window = get_window_chunks(chunks, candidate_start, candidate_end)
    if not window:
        return 0.0

    goal_key = str(goal or "").lower().strip()
    full_text = " ".join(c.get("text", "") for c in window)

    peak  = _score_peak_emotion(window, goal_key)
    dense = _score_goal_keywords(full_text, goal_key)
    arc   = _score_emotion_arc(window)

    raw = peak * 0.60 + dense * 0.25 + arc * 0.15
    return max(0.0, min(20.0, raw / 5.0))


# ---------------------------------------------------------------------------
# Internal scoring components
# ---------------------------------------------------------------------------

def _score_peak_emotion(chunks: list[dict], goal: str) -> float:
    """Highest goal-weighted emotion score across any single chunk. [0, 100]

    Uses the maximum, not the aggregate, to avoid saturation on long windows
    (a 60-minute podcast should not automatically score 100 due to volume).
    """
    from app.ai.analyzers.emotion_analyzer import analyze_text_emotion

    goal_weights = _GOAL_EMOTION_WEIGHTS.get(goal, {})
    peak = 0.0
    for chunk in chunks:
        text = chunk.get("text") or ""
        if not text.strip():
            continue
        result = analyze_text_emotion(text)
        raw = float(result.get("score") or 0.0)
        dominant = result.get("dominant", "neutral")
        if dominant == "neutral" or raw <= 0:
            continue
        multiplier = goal_weights.get(dominant, 1.0)
        weighted = min(100.0, raw * multiplier)
        if weighted > peak:
            peak = weighted
    return peak


def _score_emotion_arc(chunks: list[dict]) -> float:
    """Score upward emotional build: second half more intense than first. [0, 100]

    Returns 0 for short windows (< 4 chunks) and for flat or declining arcs.
    """
    if len(chunks) < 4:
        return 0.0

    from app.ai.analyzers.emotion_analyzer import analyze_pacing_emotion

    mid = len(chunks) // 2
    first_score  = float(analyze_pacing_emotion(chunks[:mid]).get("score") or 0.0)
    second_score = float(analyze_pacing_emotion(chunks[mid:]).get("score") or 0.0)

    if second_score > first_score:
        return min(100.0, (second_score - first_score) * 2.0)
    return 0.0


def _score_goal_keywords(text: str, goal: str) -> float:
    """Goal-specific keyword density in the full window text. [0, 100]

    Each keyword hit adds 15 pts; saturates at 7 hits (100).
    """
    if not text or not goal:
        return 0.0
    keywords = _GOAL_KEYWORDS.get(goal, [])
    if not keywords:
        return 0.0
    lower = text.lower()
    hits = sum(1 for kw in keywords if kw in lower)
    return min(100.0, hits * 15.0)
