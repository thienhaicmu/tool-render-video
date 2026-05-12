"""
camera_knowledge_schema.py — Phase 53C camera knowledge pack schema.

Plain dataclasses. No Pydantic, no heavy deps. Safe to import anywhere.

Carries retrieved camera knowledge items and reasoning hints for use by:
  - camera preference reasoning (Phase 50B)
  - safe camera influence (Phase 48)
  - camera quality intelligence (Phase 52B)
  - strategy reasoning (Phase 51)

Metadata-only: never mutates motion_crop, tracking, scene detection, or FFmpeg.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AICameraKnowledgeItem:
    """A single retrieved camera knowledge item. Phase 53C."""
    knowledge_id: str
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    camera_patterns: dict = field(default_factory=dict)
    creator_style: str = ""

    def to_dict(self) -> dict:
        return {
            "knowledge_id": self.knowledge_id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "camera_patterns": dict(self.camera_patterns),
            "creator_style": self.creator_style,
        }


@dataclass
class AICameraKnowledgePack:
    """Camera knowledge pack for AI reasoning support. Phase 53C.

    Carries retrieved camera knowledge items and reasoning hints.

    Safety contract:
      - Metadata-only influence: never mutates motion_crop or tracking
      - No motion_crop rewrite
      - No tracking rewrite
      - No scene detection rewrite
      - No FFmpeg mutation
      - No executor override
      - Deterministic: same inputs → same output
    """
    available: bool = False
    domain: str = "camera"
    items: List[AICameraKnowledgeItem] = field(default_factory=list)
    matched_tags: List[str] = field(default_factory=list)
    reasoning_hints: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "domain": str(self.domain),
            "items": [i.to_dict() for i in self.items],
            "matched_tags": list(self.matched_tags),
            "reasoning_hints": list(self.reasoning_hints),
            "warnings": list(self.warnings),
        }
