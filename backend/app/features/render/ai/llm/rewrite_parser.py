"""
rewrite_parser.py — Parse rewrite LLM response into a plain narration string.

Defensive: never raises, returns None on any failure. Caller treats None
as signal to fall back to original transcript text (Sacred Contract #3).
"""
from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("app.render.llm_rewrite_parser")

# Strip leading ``` or ```text fences and trailing fences.
_FENCE_RE = re.compile(r"^\s*```(?:[a-z]+)?\s*\n?|\n?\s*```\s*$", re.IGNORECASE)
# Strip common prose wrappers the LLM sometimes prepends.
_PROSE_PREFIX_RE = re.compile(
    r"^\s*(here is|here's|sure[,!:]?|certainly[,!:]?|rewritten narration[:\s]*|narration[:\s]*)",
    re.IGNORECASE,
)


def parse_rewrite_response(
    raw: str,
    target_duration_sec: float,
    word_budget: int,
) -> Optional[str]:
    """Parse the LLM's rewrite response into a clean narration string.

    Defensive rules applied in order:
      1. Coerce input to str; strip whitespace.
      2. Strip ```...``` code fences (leading + trailing).
      3. Strip common prose prefixes ("Here is the rewritten ...").
      4. Reject empty / whitespace-only output.
      5. Reject output exceeding 2x word_budget (sanity check — model
         ignored the hard cap rule; safer to fall back).
      6. Collapse runs of internal whitespace to single space.

    Returns ``None`` on any failure (Sacred Contract #3). On success
    returns the cleaned narration text ready for ``generate_narration_audio``.
    """
    try:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        # Strip code fences (start + end).
        text = _FENCE_RE.sub("", text).strip()
        text = _FENCE_RE.sub("", text).strip()  # in case both ends fenced
        # Strip prose prefix (one pass — only the first occurrence).
        text = _PROSE_PREFIX_RE.sub("", text, count=1).strip()
        if not text:
            logger.warning("rewrite_parser: empty after fence/prose strip")
            return None
        # Sanity check: word count vs 2x budget.
        word_count = len(text.split())
        if word_count > max(20, word_budget * 2):
            logger.warning(
                "rewrite_parser: rejected %d words > 2x budget (%d). Preview: %r",
                word_count, word_budget, text[:200],
            )
            return None
        # Collapse internal whitespace.
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception as exc:
        logger.warning("rewrite_parser: unexpected error %s", exc, exc_info=True)
        return None
