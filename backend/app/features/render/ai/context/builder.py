"""
ai/context/creator_context.py — CreatorContextBuilder.

Sprint 3.2 deliverable. A thin facade in front of `db.creator_repo` that:

1. Reads the persisted `CreatorContext` from the singleton creator_prefs
   row (Sprint 3.1).
2. Exposes a single `build()` entry point so the LLM pipeline never
   reaches into the DB / domain layers directly.

Sacred Contract #3 (AI modules return None on failure, never raise) is
the absolute rule here — every public method swallows exceptions and
returns a safe default. The pipeline reads the result with a falsy
guard and emits no editorial hint when None.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.domain.creator_context import CreatorContext


logger = logging.getLogger("app.ai.context.creator_context")


class CreatorContextBuilder:
    """Build the CreatorContext the AI Director should consider."""

    def build(self) -> Optional[CreatorContext]:
        """Return the active CreatorContext or None when none is configured.

        Returns None when:
        - the repo helper returns None (no creator_prefs row, no
          creator_context key, or DB error swallowed at the repo layer)
        - the loaded context is empty (is_empty() True). An empty
          context is functionally equivalent to None — the AI prompt
          treats both as "no editorial hint" — but returning None here
          lets callers short-circuit the to_prompt_hint() call entirely.
        - any unexpected exception bubbles up (caught here as a
          defensive belt-and-braces over the repo's own try/except).
        """
        try:
            ctx = self._fetch_persisted()
            if ctx is None:
                return None
            if ctx.is_empty():
                return None
            return ctx
        except Exception as exc:
            logger.warning("CreatorContextBuilder.build failed: %s", exc, exc_info=True)
            return None

    def _fetch_persisted(self) -> Optional[CreatorContext]:
        """Read from `db.creator_repo`. Local import avoids the DB layer
        being touched at module import time (keeps cold-start cheap).
        """
        from app.db.creator_repo import get_creator_context as _get
        return _get()


def build_creator_context() -> Optional[CreatorContext]:
    """Module-level convenience wrapper. The LLM pipeline imports this
    rather than instantiating CreatorContextBuilder directly so unit
    tests can monkeypatch the symbol cleanly."""
    return CreatorContextBuilder().build()

