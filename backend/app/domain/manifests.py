"""
manifests.py — Per-clip timing manifest.

Pure domain object: no FFmpeg logic, no file I/O, no subprocess calls.

BaseClipManifest is written beside each render artifact so that downstream
stages (subtitle slicing, TTS, audio mixing, output QA, AI feedback) can
read confirmed timing decisions rather than recomputing them from scattered
payload fields.

Phase 1: write-only foundation.  Consumers are added in Phase 2+.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.domain.timeline import TimelineMap


@dataclass
class BaseClipManifest:
    """All timing decisions made for a single rendered clip.

    Fields are populated progressively as the per-part pipeline advances.
    Optional artifact paths are None until the corresponding stage completes.

    The manifest is written atomically to disk after each mutation so that
    a crash mid-render leaves a consistent record up to the last completed step.
    """

    # Identity
    job_id: str
    part_no: int

    # Source location
    source_path: str
    source_start: float
    source_end: float

    # Speed decisions
    payload_speed: float      # creator-selected base speed (payload.playback_speed)
    platform: str             # _target_platform string
    platform_delta: float     # _PLATFORM_PROFILES[platform]["speed_delta"]
    effective_speed: float    # payload_speed + platform_delta, clamped [0.5, 2.0]

    # Variant (multi-variant mode; None for normal renders)
    variant_type: Optional[str]    # "aggressive" | "balanced" | "story_first" | None
    variant_speed: Optional[float] # seg["variant_playback_speed"] if multi-variant

    # Trim decisions
    silence_trim_offset: float  # seconds of leading silence removed
    visual_trim_offset: float   # seconds removed by bad-first-frame scan

    # Timeline map — authoritative coordinate transform for this clip
    timeline: TimelineMap

    # AI involvement
    ai_enabled: bool           # payload.ai_director_enabled
    ai_mode: Optional[str]     # ai_edit_plan.mode if plan was created
    ai_selected: bool          # True if AI director selected this segment
    ai_speed_hint: Optional[float]  # AI-recommended speed (Phase 3+, None for now)

    # Artifact paths — filled progressively, None until stage completes
    cut_path: Optional[str] = field(default=None)
    srt_path: Optional[str] = field(default=None)
    ass_path: Optional[str] = field(default=None)
    narration_path: Optional[str] = field(default=None)
    rendered_path: Optional[str] = field(default=None)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "part_no": self.part_no,
            "source_path": self.source_path,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "payload_speed": self.payload_speed,
            "platform": self.platform,
            "platform_delta": self.platform_delta,
            "effective_speed": self.effective_speed,
            "variant_type": self.variant_type,
            "variant_speed": self.variant_speed,
            "silence_trim_offset": self.silence_trim_offset,
            "visual_trim_offset": self.visual_trim_offset,
            "timeline": self.timeline.to_dict(),
            "ai_enabled": self.ai_enabled,
            "ai_mode": self.ai_mode,
            "ai_selected": self.ai_selected,
            "ai_speed_hint": self.ai_speed_hint,
            "cut_path": self.cut_path,
            "srt_path": self.srt_path,
            "ass_path": self.ass_path,
            "narration_path": self.narration_path,
            "rendered_path": self.rendered_path,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BaseClipManifest":
        return cls(
            job_id=str(d["job_id"]),
            part_no=int(d["part_no"]),
            source_path=str(d["source_path"]),
            source_start=float(d["source_start"]),
            source_end=float(d["source_end"]),
            payload_speed=float(d["payload_speed"]),
            platform=str(d["platform"]),
            platform_delta=float(d["platform_delta"]),
            effective_speed=float(d["effective_speed"]),
            variant_type=d.get("variant_type"),
            variant_speed=float(d["variant_speed"]) if d.get("variant_speed") is not None else None,
            silence_trim_offset=float(d.get("silence_trim_offset", 0.0)),
            visual_trim_offset=float(d.get("visual_trim_offset", 0.0)),
            timeline=TimelineMap.from_dict(d["timeline"]),
            ai_enabled=bool(d.get("ai_enabled", False)),
            ai_mode=d.get("ai_mode"),
            ai_selected=bool(d.get("ai_selected", False)),
            ai_speed_hint=float(d["ai_speed_hint"]) if d.get("ai_speed_hint") is not None else None,
            cut_path=d.get("cut_path"),
            srt_path=d.get("srt_path"),
            ass_path=d.get("ass_path"),
            narration_path=d.get("narration_path"),
            rendered_path=d.get("rendered_path"),
        )
