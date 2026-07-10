"""
context.py — Story render helpers.

The v1 ``StoryRenderContext`` dataclass went with the v1 run_story pipeline (S1).
What survives is the re-export of Content's ``safe_filename`` / ``stable_seed`` — the
identical deterministic helpers the v2 pipeline imports from here (no duplication).
"""
from __future__ import annotations

# Reuse Content's helpers verbatim (same deterministic behaviour).
from app.features.render.engine.stages.content.context import safe_filename, stable_seed  # noqa: F401

__all__ = ["safe_filename", "stable_seed"]
