"""Filename / path naming helpers shared across features.

Audit FINDING-A08 closure (2026-06-06). ``slugify`` previously lived in
``app.features.download.engine.downloader`` even though the render
feature imported it from two places:

  app/features/render/routers/lifecycle.py
  app/features/render/engine/pipeline/pipeline_source_prep.py

That cross-feature import made the dependency graph asymmetric — a
render module reaching into a downloader module is a layering violation
the audit called out as "wrong-direction" coupling. Both call sites use
``slugify`` purely as a generic filesystem-safe name builder, with no
downloader-specific behaviour. Moving the helper to ``app/core/`` makes
it the leaf utility it always was.

The original location keeps a thin re-export so existing internal
download-engine code (and any third-party imports) continue to work
without an immediate edit.
"""
from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Return a filesystem-safe lowercase slug for ``text``.

    - lowercases and trims surrounding whitespace
    - collapses runs of non-[a-z0-9] into single hyphens
    - strips leading/trailing hyphens
    - truncates to 80 characters
    - returns the literal ``"video"`` when the result would be empty

    Pure function — no I/O, no globals. Safe to call from any layer.
    """
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "video"


__all__ = ["slugify"]
