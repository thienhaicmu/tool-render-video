"""
story_plan.py — StoryCharacter domain object for Story Mode.

The v1 Story-Director storyboard model (StoryBible / StoryScene / Shot / StoryPlan)
was removed with the v1 pipeline (S1); Story v2 uses ``domain/story_plan_v2.py``. What
survives here is ``StoryCharacter`` — the canonical character record consumed by the
Character Reference Sheet endpoint (/api/story/character/reference-sheet) and the
cross-chapter Character DB (story_repo).

Pure domain: no FFmpeg, no I/O, no LLM SDK.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StoryCharacter:
    """A recurring character. ``description`` is the CANONICAL visual/role
    description injected into every shot the character appears in — the basis of
    visual consistency. ``reference_image_path`` (when set) is the pinned Character
    Reference Sheet used to condition image generation. Voice fields drive
    per-character casting (Gemini VI / ElevenLabs EN-JP)."""
    id: str = ""
    name: str = ""
    description: str = ""
    age: str = ""
    gender: str = ""
    voice_engine: str = ""
    voice_id: str = ""
    reference_image_path: str = ""


__all__ = ["StoryCharacter"]
