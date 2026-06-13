"""
signals.py — Creator feedback preference signals for LLM prompts.

Phase D — Creator Feedback Loop. Pure module: no I/O, no DB access,
no subprocess calls. Accepts aggregated feedback data (from
db.feedback_repo.get_feedback_signals) and converts it to a concise
advisory phrase for the LLM editorial hint.

Design:
  - FeedbackSignals is a plain dataclass; to_prompt_hint() returns a
    short string (< 80 words) that appends naturally after CreatorContext.
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

    # ── Public API ────────────────────────────────────────────────────────────

    def is_empty(self) -> bool:
        return (
            not self.liked_hook_types
            and not self.avoided_hook_types
            and self.preferred_duration is None
        )

    def to_prompt_hint(self) -> str:
        """Return a concise advisory phrase for the LLM system prompt.

        Returns empty string when there is not enough signal (< 3 ratings).
        """
        if self.sample_size < 3 or self.is_empty():
            return ""

        parts: list[str] = [
            f"Based on {self.sample_size} past viewer ratings for this channel:"
        ]

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

    return FeedbackSignals(
        liked_hook_types=liked,
        avoided_hook_types=avoided,
        preferred_duration=preferred_duration,
        sample_size=int(sample) if isinstance(sample, (int, float)) else 0,
    )
