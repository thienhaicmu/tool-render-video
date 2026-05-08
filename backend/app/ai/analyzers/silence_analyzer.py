"""
silence_analyzer.py — Lightweight silence scoring from transcript timing.

Uses only transcript gap data — no FFmpeg subprocess, no audio analysis.
Both functions are pure-Python and always return safe values.

Public API:
    estimate_silence_penalty(chunks) -> float   (0-100; higher = more silence)
    score_speech_density(chunk)      -> float   (0-100; higher = denser speech)
"""
from __future__ import annotations

# Gaps shorter than this (seconds) are treated as normal breath pauses, not silence.
_MICRO_PAUSE_THRESHOLD = 0.30


def estimate_silence_penalty(chunks: list[dict]) -> float:
    """Return a silence penalty in [0, 100] based on transcript gap analysis.

    Measures the fraction of the overall span occupied by gaps > 300 ms.
    A chunk list with no gaps scores 0; one that is mostly silence scores 100.
    """
    if not chunks or len(chunks) < 2:
        return 0.0

    try:
        sorted_chunks = sorted(chunks, key=lambda c: float(c.get("start") or 0.0))
        first_start = float(sorted_chunks[0].get("start") or 0.0)
        last_end = float(sorted_chunks[-1].get("end") or 0.0)
        total_span = max(0.0, last_end - first_start)

        if total_span <= 0:
            return 0.0

        total_gap = 0.0
        for i in range(1, len(sorted_chunks)):
            gap = float(sorted_chunks[i].get("start") or 0.0) - float(
                sorted_chunks[i - 1].get("end") or 0.0
            )
            if gap > _MICRO_PAUSE_THRESHOLD:
                total_gap += gap

        gap_ratio = total_gap / total_span
        return min(100.0, round(gap_ratio * 100.0, 2))
    except Exception:
        return 0.0


def score_speech_density(chunk: dict) -> float:
    """Score speech density of a single chunk on a 0-100 scale.

    Calibration:
    - Optimal conversational rate ≈ 2.5 words/second → score 100
    - Below 2.5 wps: linear ramp from 0
    - Above 2.5 wps: mild penalty for very fast speech
    """
    try:
        density = float(chunk.get("speech_density") or 0.0)
    except (TypeError, ValueError):
        return 0.0

    if density <= 0:
        return 0.0
    if density <= 2.5:
        return round((density / 2.5) * 100.0, 2)
    # Slight penalty for too-fast delivery
    overshoot = (density - 2.5) / 2.5
    return round(max(60.0, 100.0 - overshoot * 20.0), 2)
