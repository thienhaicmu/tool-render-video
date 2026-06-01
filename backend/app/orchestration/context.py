"""
context.py — Typed dataclass replacing the untyped dict used for scored segments
throughout the pre-render pipeline.

Usage:
    ctx = PartContext.from_dict(some_scored_dict)
    ctx.viral_score = 85.0
    out_dict = ctx.to_dict()     # dict-compatible for all existing consumers

Design rules:
  - All fields default to a safe/zero value so existing callers that set only
    a subset of fields continue to work without error.
  - from_dict() never raises — missing keys get the field default.
  - to_dict() produces a flat dict that is backward-compatible with every
    existing pipeline consumer.
  - Typed attributes give IDEs and mypy static insight where previously dicts
    did not.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class PartContext:
    # ── Core timing (required by FFmpeg cut stage) ─────────────────────────
    start: float = 0.0
    end: float = 0.0
    duration: float = 0.0

    # ── Scoring (expected by selection filters + AI Director) ───────────────
    viral_score: float = 0.0
    hook_score: float = 0.0
    motion_score: float = 0.0
    audio_energy: float = 50.0
    diversity_score: float = 50.0
    retention_score: float = 0.0

    # ── Composite / bonus scores (optional, produced by AI/scoring passes) ──
    combined_score: float = 0.0
    market_viral_score: float = 0.0
    ai_blend_bonus: float = 0.0
    hook_opening_score: float = 0.0

    # ── Clip identity ────────────────────────────────────────────────────────
    clip_name: str = ""        # natural filename stem (spaces allowed, no FS-invalid chars)
    source: str = "local"      # "local" | "groq" | "ai_director"

    # ── Groq metadata (populated when source == "groq") ─────────────────────
    groq_title: str = ""
    groq_reason: str = ""

    # ── Catch-all for any extra keys callers may write ───────────────────────
    extra: Dict[str, Any] = field(default_factory=dict)

    # ── Constructors ─────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "PartContext":
        """Build a PartContext from an untyped scored dict. Never raises."""
        known = {f for f in cls.__dataclass_fields__ if f != "extra"}
        init_kwargs: Dict[str, Any] = {}
        extra: Dict[str, Any] = {}
        for k, v in d.items():
            if k in known:
                init_kwargs[k] = v
            else:
                extra[k] = v
        try:
            obj = cls(**init_kwargs)
        except TypeError:
            obj = cls()
            for k, v in init_kwargs.items():
                try:
                    setattr(obj, k, v)
                except Exception:
                    extra[k] = v
        obj.extra = extra
        return obj

    def to_dict(self) -> Dict[str, Any]:
        """Convert back to a flat dict compatible with all existing consumers."""
        d = asdict(self)
        extra = d.pop("extra", {})
        d.update(extra)
        return d

    # ── Convenience helpers ───────────────────────────────────────────────────

    def composite(self) -> float:
        """Best available composite score — used for single-field sorting."""
        if self.combined_score:
            return self.combined_score
        if self.market_viral_score:
            return self.market_viral_score
        return self.viral_score + self.ai_blend_bonus

    def is_high_motion(self, threshold: float = 60.0) -> bool:
        return self.motion_score >= threshold

    def has_groq_data(self) -> bool:
        return self.source == "groq" and bool(self.groq_title or self.groq_reason)


def parts_from_dicts(dicts: List[Dict[str, Any]]) -> List[PartContext]:
    """Bulk conversion helper."""
    return [PartContext.from_dict(d) for d in dicts]


def parts_to_dicts(parts: List[PartContext]) -> List[Dict[str, Any]]:
    """Bulk conversion back — feeds existing pipeline consumers unchanged."""
    return [p.to_dict() for p in parts]
