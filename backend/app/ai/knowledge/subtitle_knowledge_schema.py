"""
subtitle_knowledge_schema.py — Phase 53B subtitle knowledge pack schema.

Plain dataclasses. No Pydantic, no heavy deps. Safe to import anywhere.

Carries retrieved subtitle knowledge items and reasoning hints for use by:
  - subtitle preference reasoning (Phase 50A)
  - subtitle influence (Phase 50C)
  - strategy reasoning (Phase 51)
  - subtitle quality intelligence (Phase 52A)

Metadata-only: never mutates subtitle execution, timing, or segmentation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AISubtitleKnowledgeItem:
    """A single retrieved subtitle knowledge item. Phase 53B."""
    knowledge_id: str
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    subtitle_patterns: dict = field(default_factory=dict)
    creator_style: str = ""

    def to_dict(self) -> dict:
        return {
            "knowledge_id": self.knowledge_id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "subtitle_patterns": dict(self.subtitle_patterns),
            "creator_style": self.creator_style,
        }


@dataclass
class AISubtitleKnowledgePack:
    """Subtitle knowledge pack for AI reasoning support. Phase 53B.

    Carries retrieved subtitle knowledge items and reasoning hints.

    Safety contract:
      - Metadata-only influence: never mutates subtitle execution
      - No subtitle timing rewrite
      - No subtitle segmentation rewrite
      - No ASS generation rewrite
      - No executor override
      - Deterministic: same inputs → same output
    """
    available: bool = False
    domain: str = "subtitle"
    items: List[AISubtitleKnowledgeItem] = field(default_factory=list)
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
