"""
memory_schema.py — Lightweight data structures for RAG render memory.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RenderMemory:
    """A single render experience stored in local memory."""
    id: str
    text: str                              # searchable summary / transcript excerpt
    market: Optional[str] = None
    mode: Optional[str] = None
    duration: Optional[float] = None
    score: Optional[float] = None          # output_score from ranking
    subtitle_tone: Optional[str] = None
    camera_behavior: Optional[str] = None
    status: Optional[str] = None           # "completed" | "completed_with_errors" | etc.
    metadata: dict = field(default_factory=dict)


@dataclass
class MemorySearchResult:
    """One search hit returned by LocalMemoryStore."""
    id: str
    text: str
    score: float                           # cosine similarity in [0, 1]
    metadata: dict = field(default_factory=dict)
