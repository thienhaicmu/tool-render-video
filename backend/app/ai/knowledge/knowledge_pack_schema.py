"""
knowledge_pack_schema.py — Local knowledge pack schema. Phase 53A.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Knowledge packs are advisory metadata only:
  - no executable code inside packs
  - no arbitrary Python import triggered by pack content
  - no prompt injection behavior
  - JSON-serializable at all levels
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Required top-level fields for a valid pack
_REQUIRED_PACK_FIELDS: frozenset = frozenset({"id", "domain", "title", "version", "rules"})

# Required rule fields
_REQUIRED_RULE_FIELDS: frozenset = frozenset({"id", "title", "description", "confidence"})

# Valid domains (extendable in 53B/C/D without schema change)
VALID_DOMAINS: frozenset = frozenset({
    "subtitle", "camera", "hook", "pacing", "market", "retention", "creator",
})

_MAX_MATCHES: int = 20
_MAX_REASONING: int = 5


# ---------------------------------------------------------------------------
# Rule
# ---------------------------------------------------------------------------

@dataclass
class KnowledgePackRule:
    """A single advisory rule within a knowledge pack. Never executes directly."""

    id: str
    title: str
    description: str
    applies_to: List[str] = field(default_factory=list)
    recommendation: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.5

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "applies_to": list(self.applies_to),
            "recommendation": dict(self.recommendation),
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 2),
        }


# ---------------------------------------------------------------------------
# Pack
# ---------------------------------------------------------------------------

@dataclass
class KnowledgePack:
    """A curated local knowledge pack loaded from JSON. Advisory metadata only."""

    id: str
    domain: str
    title: str
    version: int
    tags: List[str] = field(default_factory=list)
    rules: List[KnowledgePackRule] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain,
            "title": self.title,
            "version": self.version,
            "tags": list(self.tags),
            "rules": [r.to_dict() for r in self.rules],
        }


# ---------------------------------------------------------------------------
# Match (retriever output unit)
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeMatch:
    """A single knowledge rule match returned by the retriever. Advisory only."""

    pack_id: str
    rule_id: str
    domain: str
    title: str
    recommendation: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    _score: float = 0.0  # internal retrieval relevance — not user-facing

    def to_dict(self) -> dict:
        return {
            "pack_id": self.pack_id,
            "rule_id": self.rule_id,
            "domain": self.domain,
            "title": self.title,
            "recommendation": dict(self.recommendation),
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 2),
        }


# ---------------------------------------------------------------------------
# Context (final output shape)
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeContext:
    """Unified knowledge injection result. Advisory metadata only — never executes."""

    available: bool = False
    domains: List[str] = field(default_factory=list)
    matches: List[KnowledgeMatch] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "domains": sorted(set(self.domains)),
            "matches": [m.to_dict() for m in self.matches[:_MAX_MATCHES]],
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 2),
            "reasoning": list(self.reasoning[:_MAX_REASONING]),
        }


# ---------------------------------------------------------------------------
# Fallback
# ---------------------------------------------------------------------------

_FALLBACK_CONTEXT: dict = {
    "available": False,
    "domains": [],
    "matches": [],
    "confidence": 0.0,
    "reasoning": [],
}


def fallback_knowledge_context() -> dict:
    """Return the spec-mandated empty knowledge context. Never raises."""
    return {
        "available": False,
        "domains": [],
        "matches": [],
        "confidence": 0.0,
        "reasoning": [],
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_pack_dict(raw: Any) -> bool:
    """Return True if raw has all required pack-level fields. Never raises."""
    try:
        if not isinstance(raw, dict):
            return False
        if not _REQUIRED_PACK_FIELDS.issubset(raw.keys()):
            return False
        if not isinstance(raw.get("rules"), list):
            return False
        return True
    except Exception:
        return False


def validate_rule_dict(raw: Any) -> bool:
    """Return True if raw has all required rule-level fields. Never raises."""
    try:
        if not isinstance(raw, dict):
            return False
        return _REQUIRED_RULE_FIELDS.issubset(raw.keys())
    except Exception:
        return False


def parse_pack(raw: Any) -> Optional[KnowledgePack]:
    """Parse a raw dict into a KnowledgePack. Returns None if invalid or malformed."""
    try:
        if not validate_pack_dict(raw):
            return None

        rules: List[KnowledgePackRule] = []
        for r in (raw.get("rules") or []):
            if not validate_rule_dict(r):
                continue
            conf = max(0.0, min(1.0, float(r.get("confidence") or 0.0)))
            rules.append(KnowledgePackRule(
                id=str(r["id"]),
                title=str(r["title"]),
                description=str(r["description"]),
                applies_to=[str(t) for t in (r.get("applies_to") or [])],
                recommendation=dict(r.get("recommendation") or {}),
                confidence=conf,
            ))

        return KnowledgePack(
            id=str(raw["id"]),
            domain=str(raw["domain"]),
            title=str(raw["title"]),
            version=int(raw.get("version") or 1),
            tags=[str(t) for t in (raw.get("tags") or [])],
            rules=rules,
        )
    except Exception:
        return None
