"""
audio_energy_analyzer.py — Transcript-based audio energy proxy scorer (Phase 5).

Estimates acoustic energy intensity from transcript text features only.
No audio file or external library required — degrades to 0.0 gracefully.

Proxy signals (all derived from text):
  exclamation_density — "!" characters relative to word count
  emphasis_caps       — ALL-CAPS words relative to word count
  energy_keywords     — goal-specific high-intensity words
  speech_acceleration — later chunks shorter than earlier ones (climax pattern)

Public API:
    score_audio_energy(chunks, candidate_start, candidate_end, goal) -> float ([0, +20])
    AUDIO_ENERGY_INTELLIGENCE_ENABLED: bool
"""
from __future__ import annotations

import os
import re

AUDIO_ENERGY_INTELLIGENCE_ENABLED: bool = (
    os.environ.get("AUDIO_ENERGY_INTELLIGENCE_ENABLED", "1") == "1"
)

# ── Goal-specific high-energy word sets ───────────────────────────────────────
# Words that correlate with loud / intense / climax moments in speech.
_ENERGY_KEYWORDS: dict[str, list[str]] = {
    "viral": [
        "wow", "crazy", "insane", "holy", "no way", "seriously", "boom",
        "unbelievable", "shocking", "incredible", "oh my", "what the",
        "bắt đầu", "chú ý", "khủng", "điên", "không thể tin",
    ],
    "education": [
        "critical", "important", "never", "always", "must", "essential",
        "warning", "danger", "biggest mistake", "key", "vital", "remember",
        "quan trọng", "nguy hiểm", "cảnh báo", "lỗi lớn", "phải nhớ",
    ],
    "podcast": [
        "exactly", "absolutely", "honestly", "truth", "real talk",
        "wait", "stop", "listen", "seriously", "blew my mind", "changed",
        "thật ra", "thực sự", "nghe này", "điều thú vị", "bất ngờ",
    ],
    "product": [
        "amazing", "incredible", "transform", "massive", "instant",
        "100%", "guarantee", "results", "proof", "before and after",
        "thay đổi", "kết quả", "chứng minh", "đột phá", "hiệu quả",
    ],
    "storytelling": [
        "suddenly", "explosive", "shocking", "crashed", "screamed", "burst",
        "everything changed", "at that moment", "turned out", "never expected",
        "đột ngột", "bỗng nhiên", "tất cả thay đổi", "không ngờ", "cú sốc",
    ],
}
_ENERGY_KEYWORDS_DEFAULT = [
    "wow", "amazing", "incredible", "stop", "wait", "serious",
    "khủng", "điên", "thật sự", "chú ý",
]

# Score contribution weights (must sum to 1.0)
_W_EXCLAMATION  = 0.30
_W_CAPS         = 0.20
_W_KEYWORDS     = 0.30
_W_ACCELERATION = 0.20


def score_audio_energy(
    chunks: list[dict],
    candidate_start: float,
    candidate_end: float,
    goal: str = "",
) -> float:
    """Estimate audio energy intensity from transcript text features.

    Returns an additive bonus in [0, +20]. Returns 0.0 when:
      - AUDIO_ENERGY_INTELLIGENCE_ENABLED is False
      - chunks is empty or window contains no chunks

    The score is intentionally capped at +20 (same ceiling as score_best_moment)
    and is applied via a 0.20 scale factor in clip_selector for max +4 effective.
    """
    if not AUDIO_ENERGY_INTELLIGENCE_ENABLED or not chunks:
        return 0.0

    window = [
        c for c in chunks
        if float(c.get("end") or 0.0) > candidate_start
        and float(c.get("start") or 0.0) < candidate_end
    ]
    if not window:
        return 0.0

    goal_key = str(goal or "").lower().strip()
    full_text = " ".join(c.get("text", "") for c in window)

    excl  = _score_exclamation_density(full_text)
    caps  = _score_emphasis_caps(full_text)
    kw    = _score_energy_keywords(full_text, goal_key)
    accel = _score_speech_acceleration(window)

    raw = (
        excl  * _W_EXCLAMATION
        + caps  * _W_CAPS
        + kw    * _W_KEYWORDS
        + accel * _W_ACCELERATION
    )
    return max(0.0, min(20.0, raw / 5.0))


# ── Internal scorers ──────────────────────────────────────────────────────────

def _score_exclamation_density(text: str) -> float:
    """Score based on exclamation mark frequency. [0, 100]

    Calibration: 1 "!" per 10 words → 50; saturates at 2 per 10 words.
    """
    if not text:
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    excl_count = text.count("!")
    ratio = excl_count / len(words)
    return min(100.0, ratio * 500.0)


def _score_emphasis_caps(text: str) -> float:
    """Score proportion of ALL-CAPS words (≥3 chars). [0, 100]

    Short all-caps (1-2 chars) excluded — avoids counting abbreviations like "AI".
    Calibration: 5% all-caps → 50; saturates at 10%.
    """
    if not text:
        return 0.0
    words = text.split()
    if not words:
        return 0.0
    caps_words = [w for w in words if len(w) >= 3 and w.isupper() and re.search(r"[A-Z]", w)]
    ratio = len(caps_words) / len(words)
    return min(100.0, ratio * 1000.0)


def _score_energy_keywords(text: str, goal: str) -> float:
    """Goal-specific high-energy keyword density. [0, 100]

    Each keyword hit contributes 15 pts; saturates at 7 hits.
    Falls back to default keyword set when goal is unknown.
    """
    if not text:
        return 0.0
    keywords = _ENERGY_KEYWORDS.get(goal, _ENERGY_KEYWORDS_DEFAULT)
    lower = text.lower()
    hits = sum(1 for kw in keywords if kw in lower)
    return min(100.0, hits * 15.0)


def _score_speech_acceleration(chunks: list[dict]) -> float:
    """Detect climax pattern: later chunks are shorter (faster speech). [0, 100]

    Compares average duration of second half vs first half.
    A shorter second half indicates accelerating delivery — a common climax signal.
    Returns 0 for windows with fewer than 4 chunks.
    """
    if len(chunks) < 4:
        return 0.0

    mid = len(chunks) // 2
    first_half  = chunks[:mid]
    second_half = chunks[mid:]

    def avg_dur(cs: list[dict]) -> float:
        durs = [
            float(c.get("end") or 0.0) - float(c.get("start") or 0.0)
            for c in cs
            if float(c.get("end") or 0.0) > float(c.get("start") or 0.0)
        ]
        return sum(durs) / len(durs) if durs else 0.0

    first_avg  = avg_dur(first_half)
    second_avg = avg_dur(second_half)

    if first_avg <= 0 or second_avg >= first_avg:
        return 0.0

    # Acceleration ratio: how much faster the second half is
    accel_ratio = (first_avg - second_avg) / first_avg
    return min(100.0, accel_ratio * 200.0)
