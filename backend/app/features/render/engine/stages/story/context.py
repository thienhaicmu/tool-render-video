"""
context.py — StoryRenderContext for run_story (P5).

Gathers the render-invariant params into one dataclass so the per-shot stage takes
``ctx`` instead of ~15 closure-captured locals (mirrors Content's CM-6 context).
Reuses Content's safe_filename / stable_seed (identical helpers — no duplication).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# Reuse Content's helpers verbatim (same deterministic behaviour).
from app.features.render.engine.stages.content.context import safe_filename, stable_seed  # noqa: F401


@dataclass
class StoryRenderContext:
    job_id: str
    effective_channel: str
    shots_dir: Path
    width: int
    height: int
    fps: float
    sample_rate: int
    language: str
    gender: str
    add_subtitle: bool
    word_by_word: bool
    art_style: str
    bg_kind: str            # fallback background kind when no AI image (color|image|video)
    bg_value: str           # fallback background value (color hex / path)
    subtitle_pick: str      # user's explicit subtitle style ("" / "auto" = AI/plan)
    vision_qa: bool
    cancel_cb: Callable[[], bool] = field(default=lambda: False)


__all__ = ["StoryRenderContext", "safe_filename", "stable_seed"]
