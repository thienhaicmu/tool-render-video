"""
market_schema.py — Market optimization data structures. Phase 44.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Optimization-only: no FFmpeg mutation, no render execution, no model training.
No internet, no cloud AI, no executor override.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class AIMarketOptimizationProfile:
    """Market-specific optimization profile. Local-only, deterministic. Phase 44."""
    market_id: str = "default"
    platform_type: str = ""

    # Style preferences for this market
    preferred_subtitle_style: str = ""
    preferred_pacing_style: str = ""
    preferred_camera_style: str = ""
    preferred_hook_style: str = ""

    # Optimization bias weights (0.0–1.0)
    subtitle_density_bias: float = 0.0
    pacing_energy_bias: float = 0.0
    camera_motion_bias: float = 0.0
    hook_strength_bias: float = 0.0

    retention_preferences: dict = field(default_factory=dict)

    confidence: float = 0.0
    tags: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "platform_type": self.platform_type,
            "preferred_subtitle_style": self.preferred_subtitle_style,
            "preferred_pacing_style": self.preferred_pacing_style,
            "preferred_camera_style": self.preferred_camera_style,
            "preferred_hook_style": self.preferred_hook_style,
            "subtitle_density_bias": round(float(self.subtitle_density_bias), 4),
            "pacing_energy_bias": round(float(self.pacing_energy_bias), 4),
            "camera_motion_bias": round(float(self.camera_motion_bias), 4),
            "hook_strength_bias": round(float(self.hook_strength_bias), 4),
            "retention_preferences": dict(self.retention_preferences),
            "confidence": round(float(self.confidence), 4),
            "tags": list(self.tags),
            "warnings": list(self.warnings),
        }


@dataclass
class AIMarketOptimizationPack:
    """Market optimization pack. Phase 44.

    Assistive-only: influences metadata and weighting only.
    Never overrides user settings, never mutates FFmpeg.
    """
    available: bool = True
    enabled: bool = False
    optimization_mode: str = "assistive_only"

    target_market: str = ""
    market_profile: dict = field(default_factory=dict)

    subtitle_market_bias: dict = field(default_factory=dict)
    pacing_market_bias: dict = field(default_factory=dict)
    camera_market_bias: dict = field(default_factory=dict)
    hook_market_bias: dict = field(default_factory=dict)

    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "optimization_mode": self.optimization_mode,
            "target_market": self.target_market,
            "market_profile": dict(self.market_profile),
            "subtitle_market_bias": dict(self.subtitle_market_bias),
            "pacing_market_bias": dict(self.pacing_market_bias),
            "camera_market_bias": dict(self.camera_market_bias),
            "hook_market_bias": dict(self.hook_market_bias),
            "warnings": list(self.warnings),
        }
