"""
signals.py — Unified analysis output schema for the AI analysis layer.

All analyzers (local and cloud) return AnalysisSignals.
This is the single contract between the analysis layer and the AI Director.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class ClipSignal:
    """Scoring signal for a candidate clip window."""
    start: float
    end: float
    hook_score: float = 50.0          # 0-100
    hook_type: str = "none"
    relevance_score: float = 50.0     # 0-100, semantic relevance from cloud
    reason: str = ""
    source: str = "local"             # "local" | "cloud" | "hybrid"


@dataclass
class EmotionSignal:
    """Dominant emotion for the transcript."""
    dominant: str = "neutral"         # urgency|surprise|curiosity|excitement|warning|neutral
    score: float = 0.0                # 0-100
    source: str = "local"


@dataclass
class SubtitleHints:
    """Subtitle style recommendations from the analysis layer."""
    style_preset: Optional[str] = None           # "viral_bold" | "clean_pro" | "boxed_caption"
    highlight_keywords: list[str] = field(default_factory=list)
    density: str = "normal"                       # "compact" | "normal" | "relaxed"
    source: str = "local"


@dataclass
class CameraHints:
    """Camera behavior recommendations from the analysis layer."""
    behavior: str = "none"            # "dramatic_push" | "fast_follow" | "slow_reveal" | "subject_lock" | "none"
    zoom_strength: float = 1.0        # 1.0 – 1.18
    follow_strength: float = 0.5      # 0.0 – 0.85
    source: str = "local"


@dataclass
class AnalysisSignals:
    """Unified output from any analyzer (local, cloud, or hybrid merge)."""
    clip_signals: list[ClipSignal] = field(default_factory=list)
    emotion: EmotionSignal = field(default_factory=EmotionSignal)
    subtitle_hints: Optional[SubtitleHints] = None
    camera_hints: Optional[CameraHints] = None
    confidence: float = 0.5           # 0-1
    source: Literal["local", "cloud", "hybrid"] = "local"
    warnings: list[str] = field(default_factory=list)
