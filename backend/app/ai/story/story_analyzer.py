"""
story_analyzer.py — Deterministic narrative/story structure analyzer. Phase 12.

Classifies video transcript into narrative phases (hook, build_up, climax, etc.)
using position, text signals, and pacing context. No ML models, no external APIs,
no audio loading. Deterministic and fallback-safe.

Public API:
    analyze_story_structure(
        transcript_chunks,
        pacing_context=None,
        emotion_context=None,
        memory_context=None,
    ) -> StoryAnalysis
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.ai.story.story_schema import StoryAnalysis, StorySegment
from app.ai.story.retention import estimate_retention

logger = logging.getLogger("app.ai.story.analyzer")

# ── Keyword banks (self-contained — no imports from hook/emotion analyzers) ───

_HOOK_KEYWORDS: frozenset[str] = frozenset({
    "why", "how", "secret", "truth", "hidden", "reveal", "discover",
    "never", "wait", "stop", "really", "unbelievable", "shocking", "crazy",
    "nobody", "mistake", "important", "attention", "warning", "critical",
    "must", "need", "what if", "turns out", "before", "don't", "beware",
})

_ENERGY_KEYWORDS: frozenset[str] = frozenset({
    "amazing", "incredible", "insane", "best", "worst", "finally", "now",
    "quickly", "fast", "urgent", "instantly", "immediately", "huge",
    "massive", "extreme", "powerful", "ultimate", "perfect", "biggest",
    "completely", "absolutely", "literally", "seriously", "actually",
})

# ── Phase definitions — (start_ratio, end_ratio, phase_name) ─────────────────
# Covers the entire 0-1 duration range in 5 phases.
_PHASES: tuple[tuple[float, float, str], ...] = (
    (0.00, 0.20, "early"),
    (0.20, 0.50, "middle"),
    (0.50, 0.75, "peak"),
    (0.75, 0.90, "late"),
    (0.90, 1.00, "outro"),
)

# Energy multiplier per phase (applied to base energy_level from pacing_context)
_PHASE_ENERGY_FACTOR: dict[str, float] = {
    "early": 0.70,
    "middle": 1.00,
    "peak": 1.35,
    "late": 1.10,
    "outro": 0.55,
}

_DEFAULT_ENERGY = 0.50


def analyze_story_structure(
    transcript_chunks: Any,
    pacing_context: Optional[dict] = None,
    emotion_context: Optional[dict] = None,
    memory_context: Optional[dict] = None,
) -> StoryAnalysis:
    """Classify transcript into narrative story segments.

    Args:
        transcript_chunks: list[dict] with "text", "start", "end" keys.
        pacing_context:    dict with energy_level, pacing_style, emotion, bpm.
        emotion_context:   optional dict with additional emotion signals.
        memory_context:    optional dict (not yet used — reserved).

    Returns:
        StoryAnalysis — never raises; returns minimal StoryAnalysis on error.
    """
    try:
        return _analyze(transcript_chunks, pacing_context, emotion_context)
    except Exception as exc:
        logger.debug("analyze_story_structure_failed: %s", exc)
        return StoryAnalysis(
            available=False,
            warnings=[f"story_analysis_error:{type(exc).__name__}"],
        )


# ── Internal analysis ─────────────────────────────────────────────────────────

def _analyze(
    chunks: Any,
    pacing_context: Optional[dict],
    emotion_context: Optional[dict],
) -> StoryAnalysis:
    chunks = list(chunks) if chunks else []

    if not chunks:
        return StoryAnalysis(
            available=False,
            warnings=["no_transcript_chunks"],
        )

    pacing = pacing_context or {}
    base_energy: float = _coerce_float(pacing.get("energy_level"), _DEFAULT_ENERGY)
    pacing_style: str = str(pacing.get("pacing_style") or "default").lower()
    emotion: str = str(pacing.get("emotion") or "neutral").lower()

    total_dur = _total_duration(chunks)
    if total_dur <= 0:
        return StoryAnalysis(
            available=False,
            warnings=["zero_duration"],
        )

    segments: list[StorySegment] = []
    for phase_start_r, phase_end_r, phase_name in _PHASES:
        t_start = total_dur * phase_start_r
        t_end = total_dur * phase_end_r
        phase_chunks = [c for c in chunks if _chunk_mid(c) >= t_start and _chunk_mid(c) < t_end]

        if not phase_chunks:
            if phase_name == "early":
                # Always emit an early segment — hook/setup even without chunks
                seg_type = "setup"
                confidence = 0.30
                seg = StorySegment(
                    start=t_start, end=t_end,
                    segment_type=seg_type, confidence=confidence,
                    emotion=emotion,
                )
                seg.retention_risk = estimate_retention(seg)["risk"]
                segments.append(seg)
            continue

        text_score = _max_text_score(phase_chunks)
        energy_score = base_energy * _PHASE_ENERGY_FACTOR.get(phase_name, 1.0)

        seg_type, confidence, notes = _classify_phase(
            phase_name, text_score, energy_score, pacing_style
        )

        actual_start = _safe_float(phase_chunks[0].get("start"), t_start)
        actual_end = _safe_float(phase_chunks[-1].get("end"), t_end)

        seg = StorySegment(
            start=actual_start,
            end=actual_end,
            segment_type=seg_type,
            confidence=confidence,
            emotion=emotion,
            notes=notes,
        )
        seg.retention_risk = estimate_retention(seg)["risk"]
        segments.append(seg)

    dominant_arc = _compute_dominant_arc(segments)
    narrative_flow = _compute_narrative_flow(segments)
    retention_score = _compute_retention_score(segments)

    logger.info(
        "ai_story_analysis_generated segments=%d flow=%s arc=%s retention=%.1f",
        len(segments), narrative_flow, dominant_arc, retention_score,
    )

    return StoryAnalysis(
        available=True,
        narrative_flow=narrative_flow,
        segments=segments,
        dominant_arc=dominant_arc,
        retention_score=retention_score,
    )


# ── Phase classifier ──────────────────────────────────────────────────────────

def _classify_phase(
    phase_name: str,
    text_score: float,
    energy_score: float,
    pacing_style: str,
) -> tuple[str, float, list[str]]:
    """Return (segment_type, confidence, notes) for a narrative phase."""
    notes: list[str] = []

    if phase_name == "early":
        if text_score >= 0.40:
            notes.append("hook_text_detected")
            return "hook", _confidence(text_score, energy_score, boost=0.10), notes
        return "setup", _confidence(text_score, energy_score), notes

    if phase_name == "middle":
        if energy_score >= 0.50 or text_score >= 0.30:
            if energy_score >= 0.65:
                notes.append("rising_energy_strong")
            return "build_up", _confidence(text_score, energy_score, boost=0.05), notes
        return "setup", _confidence(text_score, energy_score), notes

    if phase_name == "peak":
        if energy_score >= 0.70:
            notes.append("peak_energy_detected")
            return "tension", _confidence(text_score, energy_score, boost=0.10), notes
        if energy_score >= 0.45:
            return "build_up", _confidence(text_score, energy_score), notes
        return "setup", _confidence(text_score, energy_score), notes

    if phase_name == "late":
        if energy_score >= 0.75:
            notes.append("late_energy_peak")
            return "climax", _confidence(text_score, energy_score, boost=0.10), notes
        return "payoff", _confidence(text_score, energy_score), notes

    # "outro"
    return "outro", _confidence(text_score, energy_score * 0.5), notes


def _confidence(text_score: float, energy_score: float, boost: float = 0.0) -> float:
    """Combine text + energy into a 0-1 confidence estimate."""
    raw = (text_score * 0.55 + energy_score * 0.45) + boost
    return round(min(1.0, max(0.05, raw)), 3)


# ── Narrative arc + flow inference ───────────────────────────────────────────

def _compute_dominant_arc(segments: list[StorySegment]) -> str:
    types = [s.segment_type for s in segments]
    type_set = set(types)

    if "hook" in type_set and "climax" in type_set:
        return "curiosity_build"
    if "hook" in type_set and "payoff" in type_set:
        return "setup_payoff"
    if "tension" in type_set and "payoff" in type_set:
        return "tension_release"
    if "climax" in type_set:
        return "emotional_peak"
    if "build_up" in type_set:
        return "linear_build"
    if "hook" in type_set:
        return "front_loaded"
    return "informational"


def _compute_narrative_flow(segments: list[StorySegment]) -> str:
    types = [s.segment_type for s in segments]
    type_set = set(types)

    if "hook" in type_set and ("climax" in type_set or "tension" in type_set):
        return "hook_to_climax"
    if "hook" in type_set and "payoff" in type_set:
        return "hook_to_payoff"
    if "build_up" in type_set and "climax" in type_set:
        return "linear_build"
    if "hook" in type_set:
        return "front_loaded"
    if "build_up" in type_set:
        return "linear_build"
    return "flat"


# ── Retention score aggregation ───────────────────────────────────────────────

_SEGMENT_WEIGHT: dict[str, float] = {
    "hook": 1.5, "setup": 0.8, "build_up": 1.2, "tension": 1.3,
    "climax": 1.5, "payoff": 1.0, "outro": 0.6, "unknown": 0.5,
}


def _compute_retention_score(segments: list[StorySegment]) -> float:
    if not segments:
        return 0.0
    total_dur = sum(max(0.0, s.end - s.start) for s in segments)
    if total_dur <= 0:
        return 0.0
    score = 0.0
    for seg in segments:
        dur = max(0.0, seg.end - seg.start)
        weight = _SEGMENT_WEIGHT.get(seg.segment_type, 0.5)
        base = seg.confidence * weight * 65.0
        ret_boost = (1.0 - (seg.retention_risk or 0.5)) * 35.0
        score += (base + ret_boost) * (dur / total_dur)
    return round(min(100.0, max(0.0, score)), 1)


# ── Text scoring ──────────────────────────────────────────────────────────────

def _text_hook_score(text: str) -> float:
    """Return 0-1 hook keyword density score."""
    words = re.findall(r"\b\w+\b", text.lower())
    if not words:
        return 0.0
    hits = sum(1 for w in words if w in _HOOK_KEYWORDS)
    return min(1.0, hits / max(1, len(words)) * 8.0)


def _max_text_score(chunks: list[dict]) -> float:
    """Return the maximum hook text score across all chunks in a phase."""
    if not chunks:
        return 0.0
    return max(_text_hook_score(str(c.get("text") or "")) for c in chunks)


# ── Utility helpers ───────────────────────────────────────────────────────────

def _chunk_mid(chunk: dict) -> float:
    start = _safe_float(chunk.get("start"), 0.0)
    end = _safe_float(chunk.get("end"), start)
    return (start + end) / 2.0


def _total_duration(chunks: list[dict]) -> float:
    ends = [_safe_float(c.get("end"), 0.0) for c in chunks]
    return max(ends) if ends else 0.0


def _safe_float(val: Any, default: float) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _coerce_float(val: Any, default: float) -> float:
    try:
        f = float(val)
        return f if f >= 0 else default
    except (TypeError, ValueError):
        return default
