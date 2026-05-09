"""
subtitle_apply_schema.py — Subtitle text optimization apply schema. Phase 33.

Dataclasses only. No Pydantic. No heavy deps. Never raises.
No subtitle timestamp rewrite. No FFmpeg mutation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

# ── Allowed optimization types ────────────────────────────────────────────────
_ALLOWED_OPTIMIZATION_TYPES: frozenset[str] = frozenset({
    "compact_overload",
    "keyword_emphasis",
    "safer_line_breaks",
    "density_reduce",
    "creator_style_tone",
    "hook_emphasis",
})

# ── Forbidden optimization types (NEVER applied) ──────────────────────────────
_FORBIDDEN_OPTIMIZATION_TYPES: frozenset[str] = frozenset({
    "timestamp_rewrite",
    "subtitle_shift",
    "subtitle_speed_sync",
    "generated_script_replace",
    "full_transcript_rewrite",
})

# ── Allowed change keys (metadata/style only) ─────────────────────────────────
_ALLOWED_CHANGE_KEYS: frozenset[str] = frozenset({
    "subtitle_density",
    "subtitle_emphasis",
    "keyword_emphasis",
    "line_break_style",
    "max_chars_per_line",
    "creator_style_tone",
    "hook_emphasis",
    "readability_mode",
})

# ── Forbidden change keys (NEVER written) ─────────────────────────────────────
_FORBIDDEN_CHANGE_KEYS: frozenset[str] = frozenset({
    "start_time",
    "end_time",
    "timestamp",
    "subtitle_timing",
    "subtitle_shift",
    "playback_speed",
    "ffmpeg_args",
    "full_text_rewrite",
    "generated_script",
    "output_path",
})

# ── Safety bounds ─────────────────────────────────────────────────────────────
_MIN_CHARS_PER_LINE: int = 18
_MAX_CHARS_PER_LINE: int = 42
_MIN_CONFIDENCE: float = 0.65


@dataclass
class AISubtitleTextApply:
    apply_id: str
    optimization_type: str = ""
    source_candidate_id: str = ""
    confidence: float = 0.0
    applied: bool = False
    safe: bool = False
    target_scope: str = "metadata"
    changes: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    explanation: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        opt_type = (
            self.optimization_type
            if self.optimization_type in _ALLOWED_OPTIMIZATION_TYPES
            else "unknown"
        )
        # Sanitize changes: strip forbidden keys, clamp max_chars_per_line
        safe_changes: dict = {}
        for k, v in (self.changes or {}).items():
            if k in _FORBIDDEN_CHANGE_KEYS:
                continue
            if k not in _ALLOWED_CHANGE_KEYS:
                continue
            if k == "max_chars_per_line":
                try:
                    v = max(_MIN_CHARS_PER_LINE, min(_MAX_CHARS_PER_LINE, int(v)))
                except Exception:
                    v = _MAX_CHARS_PER_LINE
            safe_changes[k] = v

        return {
            "apply_id": str(self.apply_id),
            "optimization_type": opt_type,
            "source_candidate_id": str(self.source_candidate_id),
            "confidence": round(max(0.0, min(1.0, float(self.confidence))), 4),
            "applied": bool(self.applied),
            "safe": bool(self.safe),
            "target_scope": str(self.target_scope),
            "changes": safe_changes,
            "warnings": list(self.warnings)[:10],
            "explanation": list(self.explanation)[:10],
        }


@dataclass
class AISubtitleTextApplyPack:
    available: bool = True
    enabled: bool = False
    mode: str = "disabled"
    applied: List[AISubtitleTextApply] = field(default_factory=list)
    blocked: List[AISubtitleTextApply] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "available": bool(self.available),
            "enabled": bool(self.enabled),
            "mode": str(self.mode),
            "applied": [a.to_dict() for a in self.applied[:20]],
            "blocked": [b.to_dict() for b in self.blocked[:20]],
            "warnings": list(self.warnings)[:10],
        }
