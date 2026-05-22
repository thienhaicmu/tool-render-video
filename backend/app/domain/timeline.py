"""
timeline.py — Source/output timeline coordinate mapping.

Pure domain object: no FFmpeg logic, no file I/O, no subprocess calls.

The render pipeline operates on two timelines that were previously implicit:

  Source timeline  — seconds from the start of source.mp4
  Output timeline  — seconds from the start of the rendered output clip

The two timelines are related by effective_speed:

  output_t = (source_t - source_start) / effective_speed

TimelineMap formalises this relationship and provides the coordinate
transforms needed by subtitle slicing, TTS, audio mixing, and output QA.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# FFmpeg atempo filter is clamped to [0.5, 2.0].
# We apply the same clamp here so TimelineMap always agrees with the renderer.
_SPEED_MIN = 0.5
_SPEED_MAX = 2.0


@dataclass
class TimelineMap:
    """Coordinate map between source timeline and output timeline for one clip.

    All durations and timestamps are in seconds (float).

    Fields set at construction time
    --------------------------------
    source_start : float
        Effective start in source video seconds (after silence/frame trim).
        Equals seg["start"] + trim_offset.

    source_end : float
        End of the clip in source video seconds.  Equals seg["end"].

    effective_speed : float
        The speed multiplier applied to the video (base + platform delta),
        clamped to [0.5, 2.0].  This is the exact value used for both
        setpts=PTS/speed (video) and atempo=speed (audio).

    trim_offset : float
        Total leading trim applied (silence_trim + visual_trim), in seconds.
        Informational; source_start already incorporates it.

    Derived fields (computed at construction time)
    ----------------------------------------------
    source_duration : float
        Length of the source window used: source_end - source_start.

    output_duration : float
        Expected length of the rendered output: source_duration / effective_speed.
    """

    source_start: float
    source_end: float
    effective_speed: float
    trim_offset: float = 0.0

    # Derived — computed in __post_init__
    source_duration: float = field(init=False)
    output_duration: float = field(init=False)

    def __post_init__(self) -> None:
        self.effective_speed = max(_SPEED_MIN, min(_SPEED_MAX, float(self.effective_speed)))
        self.source_start = float(self.source_start)
        self.source_end = float(self.source_end)
        self.trim_offset = float(self.trim_offset)
        self.source_duration = max(0.0, self.source_end - self.source_start)
        self.output_duration = self.source_duration / self.effective_speed

    # ------------------------------------------------------------------
    # Coordinate transforms
    # ------------------------------------------------------------------

    def source_to_output(self, source_t: float) -> float:
        """Convert a source-timeline timestamp to output-timeline seconds.

        source_t is relative to source_start (i.e. 0 = beginning of clip).
        Returns output seconds from the start of the rendered clip.
        """
        return float(source_t) / self.effective_speed

    def output_to_source(self, output_t: float) -> float:
        """Convert an output-timeline timestamp back to source-timeline seconds.

        Returns source seconds relative to source_start (i.e. 0 = clip start).
        """
        return float(output_t) * self.effective_speed

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_start": self.source_start,
            "source_end": self.source_end,
            "source_duration": self.source_duration,
            "effective_speed": self.effective_speed,
            "trim_offset": self.trim_offset,
            "output_duration": self.output_duration,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TimelineMap":
        obj = cls(
            source_start=float(d["source_start"]),
            source_end=float(d["source_end"]),
            effective_speed=float(d["effective_speed"]),
            trim_offset=float(d.get("trim_offset", 0.0)),
        )
        return obj
