"""
hook_knowledge_schema.py — Phase 53D hook / retention knowledge pack schema.

Plain dataclasses. No Pydantic, no heavy deps. Safe to import anywhere.

Carries retrieved hook and retention knowledge items and reasoning hints for use by:
  - hook quality intelligence (Phase 52C)
  - strategy reasoning (Phase 51)
  - unified quality score (Phase 52D)

Metadata-only: never mutates hook text, transcript, clip boundaries,
subtitle timing, motion_crop, or FFmpeg.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AIHookKnowledgeItem:
    """A single retrieved hook / retention knowledge item. Phase 53D."""
    knowledge_id: str
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    hook_patterns: List[str] = field(default_factory=list)
    retention_patterns: dict = field(default_factory=dict)
    creator_style: str = ""

    def to_dict(self) -> dict:
        return {
            "knowledge_id": self.knowledge_id,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "hook_patterns": list(self.hook_patterns),
            "retention_patterns": dict(self.retention_patterns),
            "creator_style": self.creator_style,
        }


@dataclass
class AIHookKnowledgePack:
    """Hook / retention knowledge pack for AI reasoning support. Phase 53D.

    Carries retrieved hook knowledge items and reasoning hints.

    Safety contract:
      - Metadata-only influence: never mutates hook text or transcript
      - No clip boundary mutation
      - No render pipeline rewrite
      - No subtitle engine mutation
      - No motion_crop rewrite
      - No FFmpeg mutation
      - No executor override
      - Deterministic: same inputs → same output
    """
    available: bool = False
    domain: str = "hook"
    items: List[AIHookKnowledgeItem] = field(default_factory=list)
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
