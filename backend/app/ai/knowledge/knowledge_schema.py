"""
knowledge_schema.py — External knowledge item data structures. Phase 15.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
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
