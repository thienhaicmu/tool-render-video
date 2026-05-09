"""
knowledge_schema.py — External knowledge item data structures. Phase 15 + Phase 39.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
Phase 15: ExternalKnowledgeItem, KnowledgeSearchResult
Phase 39: AICreatorKnowledge, AIKnowledgeRegistry
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


VALID_SOURCE_TYPES: frozenset[str] = frozenset({
    "manual_note",
    "trend_summary",
    "style_pattern",
    "hook_pattern",
    "subtitle_pattern",
    "pacing_pattern",
    "market_pattern",
})


@dataclass
class ExternalKnowledgeItem:
    id: str
    source_type: str
    text: str
    market: Optional[str] = None
    platform: Optional[str] = None
    style: Optional[str] = None
    topic: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    confidence: float = 0.5
    metadata: dict = field(default_factory=dict)


@dataclass
class KnowledgeSearchResult:
    id: str
    score: float
    text: str
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "score": round(float(self.score), 4),
            "text": str(self.text)[:500],
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# Phase 39 — Creator knowledge ingestion types
# ---------------------------------------------------------------------------

@dataclass
class AICreatorKnowledge:
    """Structured creator knowledge item ingested from local JSON. Phase 39."""
    knowledge_id: str
    category: str = ""
    source_type: str = "local_json"
    creator_style: str = ""
    title: str = ""
    description: str = ""
    tags: List[str] = field(default_factory=list)
    hook_patterns: List[str] = field(default_factory=list)
    subtitle_patterns: dict = field(default_factory=dict)
    pacing_patterns: dict = field(default_factory=dict)
    camera_patterns: dict = field(default_factory=dict)
    retention_patterns: dict = field(default_factory=dict)
    creator_patterns: dict = field(default_factory=dict)
    safe: bool = False
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "knowledge_id": self.knowledge_id,
            "category": self.category,
            "source_type": self.source_type,
            "creator_style": self.creator_style,
            "title": self.title,
            "description": self.description,
            "tags": list(self.tags),
            "hook_patterns": list(self.hook_patterns),
            "subtitle_patterns": dict(self.subtitle_patterns),
            "pacing_patterns": dict(self.pacing_patterns),
            "camera_patterns": dict(self.camera_patterns),
            "retention_patterns": dict(self.retention_patterns),
            "creator_patterns": dict(self.creator_patterns),
            "safe": bool(self.safe),
            "warnings": list(self.warnings),
        }


@dataclass
class AIKnowledgeRegistry:
    """Registry summary of all loaded creator knowledge. Phase 39."""
    available: bool = True
    loaded_count: int = 0
    categories: List[str] = field(default_factory=list)
    creator_styles: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "loaded_count": int(self.loaded_count),
            "categories": list(self.categories),
            "creator_styles": list(self.creator_styles),
            "warnings": list(self.warnings),
        }
