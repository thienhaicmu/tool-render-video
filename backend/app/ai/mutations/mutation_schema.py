"""
mutation_schema.py — Safe AI render mutation data structures. Phase 27.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Phase 27 is the first phase where bounded AI mutations are allowed.
Mutations affect only AI guidance metadata fields — never FFmpeg commands,
render timings, segment structure, or subtitle timestamps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Allowed category values
VALID_MUTATION_CATEGORIES: frozenset[str] = frozenset({
    "subtitle",
    "pacing",
    "camera",
    "creator_style",
    "visual_rhythm",
})


@dataclass
class AISafeMutation:
    """Phase 27 — A single bounded safe render mutation.

    Records one AI-decided change to AI guidance metadata. Applied only when
    safety gates pass. Never mutates FFmpeg commands, timings, or payload
    execution fields.
    """
    mutation_id: str
    category: str = ""
    confidence: float = 0.0
    applied: bool = False
    safe: bool = False
    source_recommendation_id: str = ""
    changes: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        category = self.category if self.category in VALID_MUTATION_CATEGORIES else ""
        return {
            "mutation_id": str(self.mutation_id),
            "category": category,
            "confidence": round(min(1.0, max(0.0, float(self.confidence))), 4),
            "applied": bool(self.applied),
            "safe": bool(self.safe),
            "source_recommendation_id": str(self.source_recommendation_id),
            "changes": dict(self.changes),
            "warnings": list(self.warnings),
            "explanation": list(self.explanation[:5]),
        }


@dataclass
class AISafeMutationPack:
    """Phase 27 — Pack of bounded safe render mutations.

    Phase 27: first phase where mutations are applied (advisory_mode=False
    for safe mutations, True for fallback). All mutations affect only AI
    guidance metadata fields. Never triggers render execution.
    """
    available: bool = True
    advisory_mode: bool = False
    mutations: List[AISafeMutation] = field(default_factory=list)
    applied_mutation_ids: List[str] = field(default_factory=list)
    blocked_mutations: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "advisory_mode": bool(self.advisory_mode),
            "mutations": [m.to_dict() for m in self.mutations[:10]],
            "applied_mutation_ids": list(self.applied_mutation_ids[:20]),
            "blocked_mutations": list(self.blocked_mutations[:20]),
            "warnings": list(self.warnings),
        }
