"""
contracts.py — AI contract models for Phase 5.3.

Plain dataclasses — no Pydantic, no heavy deps. Matches existing ai/ code style.
Safe to import at any time. All to_dict() methods produce stable key sets.

Public API:
    CreativeBrief       — high-level creative strategy hints
    RenderExecutionHints — validated, bounded execution parameters
    AIValidationResult   — result of validate_execution_hints()
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class CreativeBrief:
    """High-level creative strategy brief.

    Advisory only — never directly controls render commands.
    All fields are optional; None means "no preference / use default".
    """
    pacing_style: Optional[str] = None
    subtitle_emphasis: Optional[str] = None
    hook_strategy: Optional[str] = None
    visual_energy: Optional[str] = None
    cta_strategy: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "pacing_style": self.pacing_style,
            "subtitle_emphasis": self.subtitle_emphasis,
            "hook_strategy": self.hook_strategy,
            "visual_energy": self.visual_energy,
            "cta_strategy": self.cta_strategy,
        }


@dataclass
class RenderExecutionHints:
    """Validated, bounded execution hints derived from retrieved knowledge.

    All numeric values are pre-validated and clamped to safe render ranges.
    None means "no hint / use render pipeline default".

    Contracts:
    - cut_interval_min/max: float in [1.0, 12.0] or None
    - playback_speed_hint: float in [0.5, 1.5] or None
    - subtitle_emphasis_style: one of "subtle"/"medium"/"strong"/"word_only" or None
    - hook_overlay_enabled: bool or None
    - visual_intensity: one of "low"/"medium"/"high" or None
    - source_knowledge_ids: list of str (IDs of knowledge items that contributed)
    - validation_notes: list of str (notes from validation process)
    """
    cut_interval_min: Optional[float] = None
    cut_interval_max: Optional[float] = None
    playback_speed_hint: Optional[float] = None
    subtitle_emphasis_style: Optional[str] = None
    hook_overlay_enabled: Optional[bool] = None
    visual_intensity: Optional[str] = None
    source_knowledge_ids: List[str] = field(default_factory=list)
    validation_notes: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cut_interval_min": self.cut_interval_min,
            "cut_interval_max": self.cut_interval_max,
            "playback_speed_hint": self.playback_speed_hint,
            "subtitle_emphasis_style": self.subtitle_emphasis_style,
            "hook_overlay_enabled": self.hook_overlay_enabled,
            "visual_intensity": self.visual_intensity,
            "source_knowledge_ids": list(self.source_knowledge_ids),
            "validation_notes": list(self.validation_notes),
        }


@dataclass
class AIValidationResult:
    """Result of validate_execution_hints().

    ok=True means all fields passed or were safely adjusted.
    ok=False means critical validation failure (hints should be ignored entirely).
    fixups: list of per-field adjustments made during validation.
    warnings: list of advisory warnings (non-fatal).
    """
    ok: bool
    hints: RenderExecutionHints
    fixups: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "hints": self.hints.to_dict(),
            "fixups": list(self.fixups),
            "warnings": list(self.warnings),
        }
