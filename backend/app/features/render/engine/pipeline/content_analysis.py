"""
content_analysis.py — ContentAnalysisResult: Layer 4.5 boundary dataclass.

Produced by ContentAnalyzer after transcription + analysis, before segment
building. Shared by AI Director, segment scoring, and S4.x refinements so
each downstream consumer reads pre-computed analysis instead of re-running
the same analyzers independently.

Layer 4 → Layer 4.5 → Layer 5:
    detect_scenes()  →  ContentAnalyzer.analyze()  →  score_segments()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContentAnalysisResult:
    """Pre-computed content understanding for one source video.

    All fields have safe defaults so callers never need None-guard every access.
    available=False means transcript was absent — fields carry empty/default values.
    """
    # ── Availability ─────────────────────────────────────────────────────────
    available: bool = False

    # ── Transcript (normalized, shared across all consumers) ─────────────────
    # normalize_transcript_chunks() output: [{start, end, text, word_count, speech_density}]
    chunks: list = field(default_factory=list)

    # ── Narrative structure ───────────────────────────────────────────────────
    # [{start, end, phase: "hook"|"build"|"climax"|"outro", confidence: float}]
    narrative_arc: list = field(default_factory=list)

    # ── Hook intelligence ─────────────────────────────────────────────────────
    # [{time: float, score: float, hook_type: str, text: str}]
    hook_positions: list = field(default_factory=list)

    # ── Emotion ───────────────────────────────────────────────────────────────
    dominant_emotion: str = "neutral"
    emotion_score: float = 0.0
    # [{start, end, emotion: str, intensity: float}]
    emotion_arc: list = field(default_factory=list)

    # ── Speaker / pacing segments ─────────────────────────────────────────────
    # [{start, end, speech_density: float, is_question: bool}]
    speaker_segments: list = field(default_factory=list)

    # ── Audio pacing ──────────────────────────────────────────────────────────
    beat_available: bool = False
    bpm: Optional[float] = None
    beat_count: int = 0
    energy_level: Optional[float] = None
    pacing_style: str = "default"
    suggested_cut_style: str = "standard"

    # ── Silence map ───────────────────────────────────────────────────────────
    silence_penalty: float = 0.0

    # ── Source context ────────────────────────────────────────────────────────
    source_duration: float = 0.0
    analysis_ms: int = 0
    warnings: list = field(default_factory=list)
