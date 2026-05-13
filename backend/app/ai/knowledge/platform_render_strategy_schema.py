"""
platform_render_strategy_schema.py — Phase 55E Platform-Aware Render Strategy schema.

Plain dataclasses — no Pydantic, no heavy deps. Safe to import at any time.

Carries the fused platform-aware render strategy built from Phases 55A–55D
platform contexts. Advisory-only: never executes rendering, never overrides
the stable render executor, never mutates render pipeline parameters.

Safety contract:
  - Metadata-only: no render mutation, no executor override
  - No subtitle timing rewrite, no motion_crop mutation, no FFmpeg mutation
  - Deterministic: same inputs → same output
  - Never raises — fallback-safe
  - Confidence clamped [0, 1]
  - All values normalized to explicit allowed sets (unknown on invalid input)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Allowed value sets per strategy domain
# Values outside these sets are normalized to "unknown"
# ---------------------------------------------------------------------------

ALLOWED_SUBTITLE_STYLE_BIAS = frozenset({
    "viral_bold", "clean_pro", "boxed_caption", "unknown",
})
ALLOWED_SUBTITLE_DENSITY_BIAS = frozenset({
    "compact", "balanced", "dense", "unknown",
})
ALLOWED_SUBTITLE_KEYWORD_EMPHASIS = frozenset({
    "none", "selective", "moderate", "strong", "unknown",
})
ALLOWED_SUBTITLE_READABILITY_PRIORITY = frozenset({
    "high", "medium", "low", "unknown",
})

ALLOWED_CAMERA_MOTION_ENERGY = frozenset({
    "low", "low_medium", "medium", "medium_high", "high", "unknown",
})
ALLOWED_CAMERA_STABILITY_PRIORITY = frozenset({
    "low", "medium", "medium_high", "high", "unknown",
})
ALLOWED_CAMERA_CROP_AGGRESSIVENESS = frozenset({
    "low", "medium", "high", "unknown",
})
ALLOWED_CAMERA_JITTER_SENSITIVITY = frozenset({
    "high", "medium", "low", "unknown",
})

ALLOWED_HOOK_FIRST_3S_PRIORITY = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_HOOK_RETENTION_PRIORITY = frozenset({"low", "medium", "high", "unknown"})
ALLOWED_HOOK_ENERGY = frozenset({"low", "moderate", "high", "unknown"})
ALLOWED_HOOK_CURIOSITY_STYLE = frozenset({
    "subtle", "soft_direct", "direct", "open_loop", "unknown",
})

ALLOWED_RANKING_PRIORITY = frozenset({
    "creator_fit", "retention", "hook_strength", "readability",
    "retention_creator_fit", "balanced", "unknown",
})

# ---------------------------------------------------------------------------
# Execution-forbidden keys — must never appear in strategy output
# ---------------------------------------------------------------------------

_FORBIDDEN_OUTPUT_KEYS = frozenset({
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
    "crop_coordinates", "direct_execution", "executor_override",
    "output_path", "queue_priority",
})

_MAX_REASONING_LINES = 8


# ---------------------------------------------------------------------------
# Normalization helper
# ---------------------------------------------------------------------------

def _normalize(value: str, allowed: frozenset, default: str = "unknown") -> str:
    """Normalize a string to an allowed value or return default."""
    v = str(value or "").strip().lower()
    return v if v in allowed else default


# ---------------------------------------------------------------------------
# Strategy dataclass
# ---------------------------------------------------------------------------

@dataclass
class AIPlatformRenderStrategy:
    """Unified platform-aware render strategy. Phase 55E.

    Fuses platform subtitle (55B), camera (55C), and hook (55D) intelligence
    into one deterministic advisory strategy for use by the orchestrator,
    variant evaluator, and AI UX reasoning layers.

    Advisory-only contract:
      - Informs strategy reasoning and variant evaluation
      - Must NOT execute rendering
      - Must NOT override executor authority
      - Must NOT mutate render pipeline parameters

    Fallback shape:
        available=False, platform="", creator_type="",
        strategy={}, confidence=0.0, reasoning=[]
    """
    available: bool = False
    platform: str = ""
    creator_type: str = ""
    strategy: dict = field(default_factory=dict)
    confidence: float = 0.0
    reasoning: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        strategy = _sanitize_strategy(dict(self.strategy))
        return {
            "available": bool(self.available),
            "platform": str(self.platform),
            "creator_type": str(self.creator_type),
            "strategy": strategy,
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 4),
            "reasoning": list(self.reasoning)[:_MAX_REASONING_LINES],
        }


# ---------------------------------------------------------------------------
# Safety sanitization
# ---------------------------------------------------------------------------

def _sanitize_strategy(strategy: dict) -> dict:
    """Strip forbidden execution keys from all nested strategy dicts."""
    out = {}
    for domain, vals in strategy.items():
        if domain in _FORBIDDEN_OUTPUT_KEYS:
            continue
        if isinstance(vals, dict):
            out[domain] = {k: v for k, v in vals.items() if k not in _FORBIDDEN_OUTPUT_KEYS}
        else:
            out[domain] = vals
    return out


# ---------------------------------------------------------------------------
# Fallback helpers
# ---------------------------------------------------------------------------

def _fallback_strategy(platform: str = "", creator_type: str = "") -> dict:
    """Return a valid fallback strategy dict. Never raises."""
    return {
        "platform_render_strategy": {
            "available": False,
            "platform": str(platform or ""),
            "creator_type": str(creator_type or ""),
            "strategy": {},
            "confidence": 0.0,
            "reasoning": [],
        }
    }
