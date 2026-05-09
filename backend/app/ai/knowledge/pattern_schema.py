"""
pattern_schema.py — Creator pattern data structures. Phase 40.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Extraction-only: no FFmpeg mutation, no render execution, no model training.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AICreatorPattern:
    """A single extracted creator intelligence pattern. Metadata-only."""
    pattern_id: str
    pattern_type: str = ""
    creator_style: str = ""
    title: str = ""
    description: str = ""
    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    hook_patterns: List[str] = field(default_factory=list)
    subtitle_patterns: dict = field(default_factory=dict)
    pacing_patterns: dict = field(default_factory=dict)
    camera_patterns: dict = field(default_factory=dict)
    retention_patterns: dict = field(default_factory=dict)
    safe: bool = False
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pattern_id": self.pattern_id,
            "pattern_type": self.pattern_type,
            "creator_style": self.creator_style,
            "title": self.title,
            "description": self.description,
            "confidence": round(float(self.confidence), 4),
            "tags": list(self.tags),
            "hook_patterns": list(self.hook_patterns),
            "subtitle_patterns": dict(self.subtitle_patterns),
            "pacing_patterns": dict(self.pacing_patterns),
            "camera_patterns": dict(self.camera_patterns),
            "retention_patterns": dict(self.retention_patterns),
            "safe": bool(self.safe),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation),
        }


@dataclass
class AIPatternRegistry:
    """Registry summary of all extracted creator patterns. Phase 40."""
    available: bool = True
    loaded_patterns: int = 0
    pattern_types: List[str] = field(default_factory=list)
    creator_styles: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "loaded_patterns": int(self.loaded_patterns),
            "pattern_types": list(self.pattern_types),
            "creator_styles": list(self.creator_styles),
            "warnings": list(self.warnings),
        }
