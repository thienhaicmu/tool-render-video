"""
edit_plan_schema.py — AI edit plan data structures.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class AIClipPlan:
    start: float
    end: float
    score: float
    reason: str = ""
    source: str = "local_ai"


@dataclass
class AISubtitlePlan:
    """Subtitle behavior planning. Phase 5 expands with emphasis/density/awareness fields."""
    tone: str = "default"
    highlight_keywords: bool = False
    max_words_per_line: Optional[int] = None
    # Phase 5
    emphasis_style: str = "none"
    density: str = "normal"
    beat_aware: bool = False
    emotion_aware: bool = False
    reason: str = ""


@dataclass
class AICameraPlan:
    """Camera behavior planning. Phase 5 expands with zoom/follow/energy fields."""
    mode: str = "default"
    behavior: str = "none"
    subtitle_safe: bool = True
    # Phase 5
    zoom_strength: float = 1.0
    follow_strength: float = 0.5
    motion_energy: Optional[float] = None
    reason: str = ""


@dataclass
class AIPacingPlan:
    """Beat and emotion pacing metadata attached to the AI edit plan.

    Observation-only in Phase 4 — does not yet influence render commands.
    """
    beat_available: bool = False
    bpm: Optional[float] = None
    beat_count: int = 0
    energy_level: Optional[float] = None
    pacing_style: str = "default"
    emotion: str = "neutral"
    emotion_score: float = 0.0
    suggested_cut_style: str = "standard"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "beat_available": self.beat_available,
            "bpm": self.bpm,
            "beat_count": self.beat_count,
            "energy_level": self.energy_level,
            "pacing_style": self.pacing_style,
            "emotion": self.emotion,
            "emotion_score": self.emotion_score,
            "suggested_cut_style": self.suggested_cut_style,
            "warnings": list(self.warnings),
        }


@dataclass
class AIBeatExecutionPlan:
    """Beat-aware execution plan. Phase 11 — metadata-only, no timing mutations."""
    enabled: bool = False
    beat_available: bool = False
    bpm: Optional[float] = None
    beat_count: int = 0
    pulse_strength: float = 0.0
    suggested_transition_style: str = "none"
    execution_mode: str = "metadata_only"
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "beat_available": self.beat_available,
            "bpm": self.bpm,
            "beat_count": self.beat_count,
            "pulse_strength": self.pulse_strength,
            "suggested_transition_style": self.suggested_transition_style,
            "execution_mode": self.execution_mode,
            "warnings": list(self.warnings),
        }


@dataclass
class AIEditPlan:
    enabled: bool
    mode: str
    selected_segments: List[AIClipPlan]
    subtitle: AISubtitlePlan
    camera: AICameraPlan
    warnings: List[str] = field(default_factory=list)
    fallback_used: bool = False
    memory_context: dict = field(default_factory=dict)
    pacing: AIPacingPlan = field(default_factory=AIPacingPlan)
    # Phase 6 — explainability
    explainability: dict = field(default_factory=dict)
    confidence: dict = field(default_factory=dict)
    # Phase 11 — beat execution plan (populated by beat_execution module)
    beat_execution: dict = field(default_factory=dict)
    # Phase 12 — story intelligence (populated by story_analyzer module)
    story: dict = field(default_factory=dict)
    # Phase 13 — smart preset evolution (populated by preset_analyzer module)
    preset_evolution: dict = field(default_factory=dict)
    # Phase 14 — creator style intelligence (populated by style_classifier module)
    creator_style: dict = field(default_factory=dict)
    # Phase 15 — external knowledge (populated by knowledge_retriever module)
    external_knowledge: dict = field(default_factory=dict)
    # Phase 16 — retention intelligence (populated by retention_analyzer module)
    retention: dict = field(default_factory=dict)
    # Phase 17 — dynamic subtitle execution (populated by subtitle_execution module)
    subtitle_execution: dict = field(default_factory=dict)
    # Phase 18 — beat-synced visual execution (populated by visual_execution module)
    beat_visual_execution: dict = field(default_factory=dict)
    # Phase 19 — retention-driven timing mutation (populated by timing_recommender module)
    timing_mutation: dict = field(default_factory=dict)
    # Phase 20 — story-driven edit optimization (populated by story_recommender module)
    story_optimization: dict = field(default_factory=dict)
    # Phase 21 — safe autonomous variant rendering (populated by variant_generator module)
    variants: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        # Compact confidence subset exposed as top-level key for easy result_json access.
        compact_confidence = {
            k: self.confidence.get(k)
            for k in ("overall", "semantic", "memory", "pacing")
            if self.confidence.get(k) is not None
        }
        # Summary without the nested confidence copy to avoid duplication.
        summary = self.explainability.get("summary", {})
        ai_summary = {k: v for k, v in summary.items() if k != "confidence"}

        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "selected_segments": [
                {
                    "start": s.start,
                    "end": s.end,
                    "score": s.score,
                    "reason": s.reason,
                    "source": s.source,
                }
                for s in self.selected_segments
            ],
            "subtitle": {
                "tone": self.subtitle.tone,
                "highlight_keywords": self.subtitle.highlight_keywords,
                "max_words_per_line": self.subtitle.max_words_per_line,
                "emphasis_style": self.subtitle.emphasis_style,
                "density": self.subtitle.density,
                "beat_aware": self.subtitle.beat_aware,
                "emotion_aware": self.subtitle.emotion_aware,
                "reason": self.subtitle.reason,
            },
            "camera": {
                "mode": self.camera.mode,
                "behavior": self.camera.behavior,
                "subtitle_safe": self.camera.subtitle_safe,
                "zoom_strength": self.camera.zoom_strength,
                "follow_strength": self.camera.follow_strength,
                "motion_energy": self.camera.motion_energy,
                "reason": self.camera.reason,
            },
            "warnings": list(self.warnings),
            "fallback_used": self.fallback_used,
            "memory_context": dict(self.memory_context),
            "pacing": self.pacing.to_dict(),
            "explainability": dict(self.explainability),
            "confidence": dict(self.confidence),
            "ai_summary": ai_summary,
            "ai_confidence": compact_confidence,
            "beat_execution": dict(self.beat_execution),
            "story": dict(self.story),
            "preset_evolution": dict(self.preset_evolution),
            "creator_style": dict(self.creator_style),
            "external_knowledge": dict(self.external_knowledge),
            "retention": dict(self.retention),
            "subtitle_execution": dict(self.subtitle_execution),
            "beat_visual_execution": dict(self.beat_visual_execution),
            "timing_mutation": dict(self.timing_mutation),
            "story_optimization": dict(self.story_optimization),
            "variants": dict(self.variants),
        }
