"""
platform_knowledge_schema.py — Phase 55A Platform Knowledge Foundation schema.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Carries retrieved platform and creator-archetype knowledge items for use by:
  - platform context metadata (Phase 55A)
  - future platform subtitle intelligence (Phase 55B)
  - future platform camera intelligence (Phase 55C)
  - future platform hook intelligence (Phase 55D)

Metadata-only: never mutates rendering, subtitle timing, motion_crop, or
any render pipeline parameter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# Recognised platform identifiers (open-ended — unknown platforms degrade to available=False)
KNOWN_PLATFORMS = frozenset({"tiktok", "youtube_shorts", "instagram_reels", "general"})

# Recognised creator archetype identifiers
KNOWN_CREATOR_TYPES = frozenset({
    "podcast", "talking_head", "educational", "storytelling",
    "viral_short_form", "general",
})


@dataclass
class AIPlatformKnowledgeItem:
    """A single retrieved platform knowledge item. Phase 55A.

    Represents one platform + creator-type guidance pack loaded from a local
    JSON file. All fields are read-only advisory data.
    """
    knowledge_id: str
    platform: str = ""
    creator_type: str = ""
    version: int = 1
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    guidance: dict = field(default_factory=dict)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "knowledge_id": self.knowledge_id,
            "platform": self.platform,
            "creator_type": self.creator_type,
            "version": self.version,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "domains": list(self.domains),
            "guidance": dict(self.guidance),
            "confidence": round(float(self.confidence), 4),
        }


@dataclass
class AIPlatformKnowledgePack:
    """Platform knowledge retrieval result pack. Phase 55A.

    Contains zero or more matched platform knowledge items plus aggregated
    metadata for downstream advisory systems.

    Safety contract:
      - Metadata-only: no render mutation, no executor override
      - No subtitle timing rewrite
      - No motion_crop mutation
      - No FFmpeg mutation
      - Deterministic: same inputs → same output
      - Never raises — fallback-safe
    """
    available: bool = False
    platform: str = ""
    creator_type: str = ""
    matches: List[AIPlatformKnowledgeItem] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "platform": str(self.platform),
            "creator_type": str(self.creator_type),
            "matches": [m.to_dict() for m in self.matches],
            "confidence": round(float(self.confidence), 4),
            "reasoning": list(self.reasoning),
            "warnings": list(self.warnings),
        }


@dataclass
class AIPlatformContext:
    """Platform context metadata for the edit plan. Phase 55A.

    Attached to AIEditPlan.platform_context as an advisory metadata dict.
    Never influences render execution directly.

    Fallback:
        available=False, empty matches, confidence=0.0, empty reasoning.
    """
    available: bool = False
    platform: str = ""
    creator_type: str = ""
    matches: List[dict] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "platform": str(self.platform),
            "creator_type": str(self.creator_type),
            "matches": list(self.matches),
            "confidence": round(float(self.confidence), 4),
            "reasoning": list(self.reasoning),
        }
