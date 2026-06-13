"""
signals.py — Creator feedback preference signals for LLM prompts.

Phase D — Creator Feedback Loop. Pure module: no I/O, no DB access,
no subprocess calls. Accepts aggregated feedback data (from
db.feedback_repo.get_feedback_signals) and converts it to a concise
advisory phrase for the LLM editorial hint.

Phase V1 — Platform Performance Ingestion. Extended FeedbackSignals
with avg_watch_pct, avg_ctr, platform_sample_size from real platform
analytics so the LLM hint can reference watch-through and CTR data.

Phase V2 — Frame Signal Integration. Extended FeedbackSignals with
pct_sharp_cover, pct_face_cover, quality_sample_size from thumbnail
quality tags persisted per part, so the LLM hint can reflect visual
cover quality trends.

Design:
  - FeedbackSignals is a plain dataclass; to_prompt_hint() returns a
    short string (< 150 words) that appends naturally after CreatorContext.
  - build_signals() is the factory — converts the raw dict from the
    repo into a typed object and validates the data defensively.
  - Both are safe to call in a try/except block inside the render
    pipeline (Sacred Contract #3 spirit: never raises).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FeedbackSignals:
    liked_hook_types: list[str] = field(default_factory=list)
    avoided_hook_types: list[str] = field(default_factory=list)
    preferred_duration: Optional[tuple[float, float]] = None
    sample_size: int = 0
    # Phase V1: real platform performance signals
    avg_watch_pct: Optional[float] = None
    avg_ctr: Optional[float] = None
    platform_sample_size: int = 0
    # Phase V2: cover frame visual quality signals
    pct_sharp_cover: float = 0.0
    pct_face_cover: float = 0.0
    quality_sample_size: int = 0
    # Phase V3: content fingerprinting / segment repeat detection
    segment_repeat_pct: float = 0.0
    repeat_sample_size: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def is_empty(self) -> bool:
        return (
            not self.liked_hook_types
            and not self.avoided_hook_types
            and self.preferred_duration is None
            and self.avg_watch_pct is None
            and self.quality_sample_size == 0
            and self.repeat_sample_size == 0
        )

    def to_prompt_hint(self) -> str:
        """Return a concise advisory phrase for the LLM system prompt.

        Returns empty string when there is not enough signal.
        """
        has_clip_data = self.sample_size >= 3 and not (
            not self.liked_hook_types
            and not self.avoided_hook_types
            and self.preferred_duration is None
        )
        has_platform_data = (
            self.avg_watch_pct is not None and self.platform_sample_size >= 3
        )
        has_quality_data = self.quality_sample_size >= 5
        has_repeat_data = (
            self.repeat_sample_size >= 5 and self.segment_repeat_pct > 0.30
        )

        if not has_clip_data and not has_platform_data and not has_quality_data and not has_repeat_data:
            return ""

        parts: list[str] = []

        if has_clip_data:
            parts.append(
                f"Based on {self.sample_size} past viewer ratings for this channel:"
            )
            if self.liked_hook_types:
                hooks = " and ".join(f"'{h}'" for h in self.liked_hook_types[:3])
                parts.append(f"viewers engaged most with {hooks} hook types.")
            if self.avoided_hook_types:
                avoided = " and ".join(f"'{h}'" for h in self.avoided_hook_types[:2])
                parts.append(f"Avoid {avoided} hooks (previously disliked).")
            if self.preferred_duration:
                lo, hi = self.preferred_duration
                if lo < hi:
                    parts.append(f"Preferred clip length: {lo:.0f}–{hi:.0f}s.")
                elif lo > 0:
                    parts.append(f"Preferred clip length: around {lo:.0f}s.")

        if has_platform_data:
            watch_str = f"{self.avg_watch_pct * 100:.0f}%"  # type: ignore[operator]
            ctr_str = (
                f"{self.avg_ctr * 100:.1f}%"  # type: ignore[operator]
                if self.avg_ctr is not None
                else "n/a"
            )
            parts.append(
                f"Real platform data ({self.platform_sample_size} posts): "
                f"avg watch-through {watch_str}, CTR {ctr_str}."
            )

        if has_quality_data:
            sharp_str = f"{self.pct_sharp_cover * 100:.0f}%"
            face_str = f"{self.pct_face_cover * 100:.0f}%"
            parts.append(
                f"Cover frame quality ({self.quality_sample_size} renders): "
                f"{sharp_str} sharp, {face_str} with clear face."
            )

        if has_repeat_data:
            pct_str = f"{self.segment_repeat_pct * 100:.0f}%"
            parts.append(
                f"Content diversity: {pct_str} of segments across "
                f"{self.repeat_sample_size} positions reused prior time ranges — "
                f"prefer selecting different parts of the source."
            )

        return " ".join(parts)


def build_signals(raw: dict) -> FeedbackSignals:
    """Convert the raw dict from get_feedback_signals() into a FeedbackSignals.

    Defensive: any unexpected type or missing key falls back to an empty
    signal rather than raising. Safe to call in any context.
    """
    if not isinstance(raw, dict):
        return FeedbackSignals()

    liked = raw.get("liked_hook_types") or []
    avoided = raw.get("avoided_hook_types") or []
    dur_raw = raw.get("preferred_duration")
    sample = raw.get("sample_size") or 0

    liked = [str(h) for h in liked if h and isinstance(h, str)]
    avoided = [str(h) for h in avoided if h and isinstance(h, str)]

    preferred_duration: Optional[tuple[float, float]] = None
    if isinstance(dur_raw, (list, tuple)) and len(dur_raw) == 2:
        try:
            lo, hi = float(dur_raw[0]), float(dur_raw[1])
            if lo >= 0 and hi >= lo:
                preferred_duration = (lo, hi)
        except (TypeError, ValueError):
            pass

    # Phase V1: platform performance fields
    avg_watch_pct: Optional[float] = None
    avg_ctr: Optional[float] = None
    platform_sample_size = 0
    try:
        raw_watch = raw.get("avg_watch_pct")
        if raw_watch is not None:
            avg_watch_pct = float(raw_watch)
        raw_ctr = raw.get("avg_ctr")
        if raw_ctr is not None:
            avg_ctr = float(raw_ctr)
        platform_sample_size = int(raw.get("platform_sample_size") or 0)
    except (TypeError, ValueError):
        pass

    # Phase V2: cover quality fields
    pct_sharp_cover = 0.0
    pct_face_cover = 0.0
    quality_sample_size = 0
    try:
        pct_sharp_cover = float(raw.get("pct_sharp_cover") or 0.0)
        pct_face_cover = float(raw.get("pct_face_cover") or 0.0)
        quality_sample_size = int(raw.get("quality_sample_size") or 0)
    except (TypeError, ValueError):
        pass

    # Phase V3: segment repeat rate
    segment_repeat_pct = 0.0
    repeat_sample_size = 0
    try:
        segment_repeat_pct = float(raw.get("segment_repeat_pct") or 0.0)
        repeat_sample_size = int(raw.get("repeat_sample_size") or 0)
    except (TypeError, ValueError):
        pass

    return FeedbackSignals(
        liked_hook_types=liked,
        avoided_hook_types=avoided,
        preferred_duration=preferred_duration,
        sample_size=int(sample) if isinstance(sample, (int, float)) else 0,
        avg_watch_pct=avg_watch_pct,
        avg_ctr=avg_ctr,
        platform_sample_size=platform_sample_size,
        pct_sharp_cover=pct_sharp_cover,
        pct_face_cover=pct_face_cover,
        quality_sample_size=quality_sample_size,
        segment_repeat_pct=segment_repeat_pct,
        repeat_sample_size=repeat_sample_size,
    )
