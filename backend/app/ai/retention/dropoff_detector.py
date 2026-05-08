"""
dropoff_detector.py — Deterministic viewer drop-off risk detector. Phase 16.

Analyses transcript, pacing, story, subtitle, and beat signals to identify
time regions where viewer retention is likely to weaken.

No ML models, no external APIs, no internet. Deterministic heuristics only.

Public API:
    detect_retention_risks(
        transcript_chunks=None,
        pacing_context=None,
        story_context=None,
        subtitle_context=None,
        beat_context=None,
    ) -> list[RetentionRiskRegion]
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.ai.retention.retention_schema import RetentionRiskRegion

logger = logging.getLogger("app.ai.retention.dropoff")

# Hook keywords — shared with story_analyzer but kept self-contained here
_HOOK_KEYWORDS: frozenset[str] = frozenset({
    "why", "how", "secret", "truth", "reveal", "discover", "hidden",
    "never", "wait", "stop", "really", "unbelievable", "shocking", "crazy",
    "nobody", "mistake", "warning", "must", "attention", "critical",
    "turns", "before", "don't", "beware", "actually", "finally",
})

# Thresholds
_SILENCE_GAP_SECONDS = 2.5   # consecutive gap triggers silence_gap
_MAX_SILENCE_REGIONS = 2     # cap silence regions to avoid noise
_LONG_SETUP_RATIO = 0.32     # setup+build_up spanning >32% → long_setup
_MIN_PAYOFF_DURATION = 15.0  # clips shorter than this skip unclear_payoff check
_SUBTITLE_DENSE_WORDS = 14   # avg words/chunk above this → overload


def detect_retention_risks(
    transcript_chunks: Any = None,
    pacing_context: Any = None,
    story_context: Any = None,
    subtitle_context: Any = None,
    beat_context: Any = None,
) -> List[RetentionRiskRegion]:
    """Detect viewer drop-off risk regions. Never raises.

    Returns a list of RetentionRiskRegion (may be empty when no risks found).
    """
    try:
        chunks = list(transcript_chunks) if transcript_chunks else []
        pacing = dict(pacing_context) if isinstance(pacing_context, dict) else {}
        story = dict(story_context) if isinstance(story_context, dict) else {}
        subtitle = dict(subtitle_context) if isinstance(subtitle_context, dict) else {}
        beat = dict(beat_context) if isinstance(beat_context, dict) else {}

        return _detect(chunks, pacing, story, subtitle, beat)
    except Exception as exc:
        logger.debug("detect_retention_risks_failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Internal dispatcher
# ---------------------------------------------------------------------------

def _detect(
    chunks: list,
    pacing: dict,
    story: dict,
    subtitle: dict,
    beat: dict,
) -> List[RetentionRiskRegion]:
    duration = _estimate_duration(chunks)
    risks: List[RetentionRiskRegion] = []

    r = _check_weak_hook(chunks, story, duration)
    if r:
        risks.append(r)

    r = _check_long_setup(story, duration)
    if r:
        risks.append(r)

    r = _check_pacing_decay(pacing, story, duration)
    if r:
        risks.append(r)

    risks.extend(_check_silence_gaps(chunks))

    r = _check_subtitle_overload(chunks, subtitle, duration)
    if r:
        risks.append(r)

    r = _check_story_drop(story, duration)
    if r:
        risks.append(r)

    r = _check_unclear_payoff(story, duration)
    if r:
        risks.append(r)

    return risks


# ---------------------------------------------------------------------------
# Heuristic checks
# ---------------------------------------------------------------------------

def _check_weak_hook(chunks: list, story: dict, duration: float) -> Optional[RetentionRiskRegion]:
    segments = story.get("segments", [])
    has_hook_segment = any(
        isinstance(s, dict) and s.get("segment_type") == "hook"
        for s in segments
    )

    # Text-based hook signal from first 3 chunks
    early_text = " ".join(
        str(c.get("text", "")) for c in chunks[:3] if isinstance(c, dict)
    )
    hook_score = _hook_keyword_score(early_text)

    if not has_hook_segment and hook_score < 0.05:
        end_t = round(min(duration * 0.20, 8.0) if duration > 0 else 8.0, 2)
        return RetentionRiskRegion(
            start=0.0,
            end=end_t,
            risk=0.72,
            reason="Missing or weak opening hook may cause early viewer dropout",
            category="weak_hook",
            severity="high",
            suggestions=[
                "Start with a question, surprising fact, or strong statement",
                "Lead with curiosity-building language in the first 3 seconds",
            ],
        )

    if not has_hook_segment and hook_score < 0.10:
        end_t = round(min(duration * 0.15, 6.0) if duration > 0 else 6.0, 2)
        return RetentionRiskRegion(
            start=0.0,
            end=end_t,
            risk=0.45,
            reason="Opening hook could be stronger to hold early viewers",
            category="weak_hook",
            severity="medium",
            suggestions=["Add more curiosity-building language in the opening"],
        )

    return None


def _check_long_setup(story: dict, duration: float) -> Optional[RetentionRiskRegion]:
    if duration <= 0:
        return None

    segments = story.get("segments", [])
    setup_types = {"setup", "build_up"}

    setup_start: Optional[float] = None
    setup_end: Optional[float] = None

    for s in segments:
        if not isinstance(s, dict):
            continue
        if s.get("segment_type") in setup_types:
            s_start = float(s.get("start", 0))
            s_end = float(s.get("end", 0))
            setup_start = s_start if setup_start is None else min(setup_start, s_start)
            setup_end = s_end if setup_end is None else max(setup_end, s_end)

    if setup_start is None or setup_end is None:
        return None

    span = setup_end - setup_start
    if span / duration > _LONG_SETUP_RATIO:
        return RetentionRiskRegion(
            start=round(setup_start, 2),
            end=round(setup_end, 2),
            risk=0.70,
            reason=f"Long setup spans {span:.1f}s — viewers may disengage before the payoff",
            category="long_setup",
            severity="high",
            suggestions=[
                "Tighten the setup before the payoff",
                "Move a hook or highlight earlier in the edit",
            ],
        )

    return None


def _check_pacing_decay(pacing: dict, story: dict, duration: float) -> Optional[RetentionRiskRegion]:
    if duration < 10.0:
        return None

    energy = float(pacing.get("energy_level") or 0.0)
    pacing_style = str(pacing.get("pacing_style") or "").lower()
    emotion = str(pacing.get("emotion") or "").lower()

    decay_signals = 0
    if 0 < energy < 0.35:
        decay_signals += 1
    if pacing_style in ("slow", "slow_build"):
        decay_signals += 1
    if emotion in ("boredom", "calm", "sadness"):
        decay_signals += 1

    # Story-based: high-energy peak followed by low-energy outro
    segments = story.get("segments", [])
    has_peak = any(
        isinstance(s, dict) and s.get("segment_type") in ("climax", "tension")
        for s in segments
    )
    has_low_outro = any(
        isinstance(s, dict)
        and s.get("segment_type") == "outro"
        and float(s.get("start", 0)) > duration * 0.60
        for s in segments
    )
    if has_peak and has_low_outro:
        decay_signals += 1

    if decay_signals >= 2:
        return RetentionRiskRegion(
            start=round(duration * 0.55, 2),
            end=round(duration * 0.85, 2),
            risk=0.58,
            reason="Pacing energy decline after peak may weaken mid-to-late retention",
            category="pacing_decay",
            severity="medium",
            suggestions=[
                "Add a re-engagement moment in the middle section",
                "Avoid long calm stretches after high-energy peaks",
            ],
        )

    return None


def _check_silence_gaps(chunks: list) -> List[RetentionRiskRegion]:
    regions: List[RetentionRiskRegion] = []

    for i in range(len(chunks) - 1):
        if len(regions) >= _MAX_SILENCE_REGIONS:
            break
        c1 = chunks[i]
        c2 = chunks[i + 1]
        if not (isinstance(c1, dict) and isinstance(c2, dict)):
            continue
        end1 = float(c1.get("end", 0) or 0)
        start2 = float(c2.get("start", 0) or 0)
        gap = start2 - end1
        if gap >= _SILENCE_GAP_SECONDS:
            regions.append(RetentionRiskRegion(
                start=round(end1, 2),
                end=round(start2, 2),
                risk=0.52,
                reason=f"Silence gap of {gap:.1f}s may interrupt viewer flow",
                category="silence_gap",
                severity="medium",
                suggestions=[
                    "Fill the pause with a transition or subtitle cue",
                    "Tighten the cut to reduce the gap",
                ],
            ))

    return regions


def _check_subtitle_overload(
    chunks: list,
    subtitle: dict,
    duration: float,
) -> Optional[RetentionRiskRegion]:
    triggers: list[str] = []

    density = str(subtitle.get("density") or "").lower()
    if density == "dense":
        triggers.append("high subtitle density setting")

    max_wpl = subtitle.get("max_words_per_line")
    if max_wpl is not None:
        try:
            if int(max_wpl) > 8:
                triggers.append(f"subtitle lines up to {max_wpl} words")
        except (TypeError, ValueError):
            pass

    if chunks:
        total_words = sum(
            len(str(c.get("text", "")).split())
            for c in chunks
            if isinstance(c, dict)
        )
        avg_words = total_words / len(chunks)
        if avg_words > _SUBTITLE_DENSE_WORDS:
            triggers.append(f"high average word count ({avg_words:.0f} words/chunk)")

    if not triggers:
        return None

    return RetentionRiskRegion(
        start=0.0,
        end=round(duration, 2),
        risk=0.38,
        reason="Subtitle density may overwhelm viewers: " + "; ".join(triggers),
        category="subtitle_overload",
        severity="low",
        suggestions=[
            "Reduce words per subtitle line",
            "Split dense subtitle blocks into shorter segments",
        ],
    )


def _check_story_drop(story: dict, duration: float) -> Optional[RetentionRiskRegion]:
    narrative_flow = str(story.get("narrative_flow") or "").lower()

    if narrative_flow in ("unclear", "fragmented"):
        return RetentionRiskRegion(
            start=0.0,
            end=round(duration, 2) if duration > 0 else 60.0,
            risk=0.60,
            reason="Unclear or fragmented narrative structure may disorient viewers",
            category="story_drop",
            severity="medium",
            suggestions=[
                "Build a clearer hook-to-climax narrative arc",
                "Ensure each section has a clear purpose",
            ],
        )

    segments = story.get("segments", [])
    middle_unknowns = [
        s for s in segments
        if isinstance(s, dict)
        and s.get("segment_type") == "unknown"
        and float(s.get("start", 0)) > duration * 0.20
        and float(s.get("end", duration)) < duration * 0.85
    ]

    if middle_unknowns:
        seg = middle_unknowns[0]
        return RetentionRiskRegion(
            start=round(float(seg.get("start", 0)), 2),
            end=round(float(seg.get("end", duration * 0.5)), 2),
            risk=0.55,
            reason="Unclassified narrative segment in middle section",
            category="story_drop",
            severity="medium",
            suggestions=["Clarify the narrative purpose of this section"],
        )

    return None


def _check_unclear_payoff(story: dict, duration: float) -> Optional[RetentionRiskRegion]:
    if duration < _MIN_PAYOFF_DURATION:
        return None

    segments = story.get("segments", [])
    has_payoff = any(
        isinstance(s, dict) and s.get("segment_type") in ("payoff", "climax")
        for s in segments
    )

    if not has_payoff:
        return RetentionRiskRegion(
            start=round(duration * 0.70, 2),
            end=round(duration, 2),
            risk=0.65,
            reason="No clear payoff or climax detected — viewers may feel unrewarded",
            category="unclear_payoff",
            severity="high",
            suggestions=[
                "Add a clear resolution or climax moment",
                "Ensure viewers feel rewarded for watching to the end",
            ],
        )

    return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _estimate_duration(chunks: list) -> float:
    """Estimate total duration from chunk end times. Returns 0.0 if unavailable."""
    max_end = 0.0
    for c in chunks:
        if isinstance(c, dict):
            try:
                end = float(c.get("end", 0) or 0)
                if end > max_end:
                    max_end = end
            except (TypeError, ValueError):
                pass
    return max_end


def _hook_keyword_score(text: str) -> float:
    """Fraction of text tokens that are hook keywords."""
    words = text.lower().split()
    if not words:
        return 0.0
    matches = sum(1 for w in words if w in _HOOK_KEYWORDS)
    return matches / len(words)
