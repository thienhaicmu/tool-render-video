"""
rewrite_parser.py — Parse rewrite LLM response into a list of timed segments.

v2 (2026-06-27): JSON-first segmented parser. Returns list of
{start, end, text} segments suitable for synthesize_timed_narration.

Defensive: never raises, returns None on any failure. Caller treats None
as signal to fall back to original transcript text (Sacred Contract #3).
Plain-text responses (LLM ignored the JSON instruction) are coerced into
a single segment spanning [0.0, clip_duration_sec] so the upstream
pipeline still has SOMETHING to feed TTS.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger("app.render.llm_rewrite_parser")

# Strip leading ``` or ```json fences and trailing fences.
_FENCE_RE = re.compile(r"^\s*```(?:[a-z]+)?\s*\n?|\n?\s*```\s*$", re.IGNORECASE)
# Strip common prose wrappers the LLM sometimes prepends.
_PROSE_PREFIX_RE = re.compile(
    r"^\s*(here is|here's|sure[,!:]?|certainly[,!:]?|rewritten narration[:\s]*|narration[:\s]*)",
    re.IGNORECASE,
)
# Find a top-level JSON object in a string that may contain surrounding prose.
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _strip_wrappers(text: str) -> str:
    """Remove code fences + common prose prefixes from raw LLM output."""
    text = _FENCE_RE.sub("", text).strip()
    text = _FENCE_RE.sub("", text).strip()  # in case both ends fenced
    text = _PROSE_PREFIX_RE.sub("", text, count=1).strip()
    return text


def _extract_json_object(raw: str) -> Optional[dict]:
    """Try hard to parse `raw` as a JSON object. Returns None on any failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass
    m = _JSON_OBJECT_RE.search(raw)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (json.JSONDecodeError, TypeError):
        return None


def _coerce_segments(
    raw_segments: list,
    clip_duration_sec: float,
) -> list[dict]:
    """Validate + clamp segments. Drops invalid ones. Returns sorted list."""
    out: list[dict] = []
    for entry in raw_segments:
        if not isinstance(entry, dict):
            continue
        try:
            s = float(entry.get("start"))
            e = float(entry.get("end"))
        except (TypeError, ValueError):
            continue
        t = str(entry.get("text", "")).strip()
        if not t:
            continue
        # Clamp to clip duration. Allow a small overrun (+0.5s) since LLMs
        # sometimes round up. Reject anything wildly out of bounds.
        if s < 0:
            s = 0.0
        if e > clip_duration_sec + 0.5:
            e = clip_duration_sec
        if e <= s:
            continue
        if (e - s) < 0.3:  # too short to be a meaningful TTS segment
            continue
        # Collapse internal whitespace inside the segment text.
        t = re.sub(r"\s+", " ", t).strip()
        out.append({"start": round(s, 3), "end": round(e, 3), "text": t})

    # Sort by start time; drop later segment if it overlaps an earlier one.
    out.sort(key=lambda x: x["start"])
    deduped: list[dict] = []
    for seg in out:
        if deduped and seg["start"] < deduped[-1]["end"]:
            # Overlap — keep the earlier (already higher fidelity to source).
            continue
        deduped.append(seg)
    return deduped


def parse_rewrite_response(
    raw: str,
    clip_duration_sec: float,
    word_budget: int,
) -> Optional[list[dict]]:
    """Parse the LLM's rewrite response into a list of timed segments.

    Try order:
      1. Strip fences/prose, try JSON parse. If valid + has segments → use them.
      2. JSON parse failed but raw text is non-empty → treat as ONE segment
         spanning [0.0, clip_duration_sec]. This is the v1 plain-text fallback.
      3. Empty / nothing usable → return None.

    Returns ``None`` on any failure (Sacred Contract #3). On success returns
    a non-empty list of {start, end, text} dicts.
    """
    try:
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        text = _strip_wrappers(text)
        if not text:
            logger.warning("rewrite_parser: empty after fence/prose strip")
            return None

        # 1. JSON path
        data = _extract_json_object(text)
        if isinstance(data, dict):
            raw_segs = data.get("segments")
            if isinstance(raw_segs, list) and raw_segs:
                segs = _coerce_segments(raw_segs, clip_duration_sec)
                if segs:
                    return segs
                logger.warning(
                    "rewrite_parser: JSON segments all invalid after coercion (n=%d)",
                    len(raw_segs),
                )
                # Fall through to plain-text fallback below.

        # 2. Plain-text fallback — single segment spanning the whole clip.
        # Sanity check on word count (re-uses v1 rule).
        word_count = len(text.split())
        if word_count > max(20, word_budget * 2):
            logger.warning(
                "rewrite_parser: plain-text fallback rejected — %d words > 2x budget (%d)",
                word_count, word_budget,
            )
            return None
        collapsed = re.sub(r"\s+", " ", text).strip()
        if not collapsed:
            return None
        logger.info(
            "rewrite_parser: JSON parse failed — using plain-text fallback (1 segment, %d chars)",
            len(collapsed),
        )
        return [{"start": 0.0, "end": float(clip_duration_sec), "text": collapsed}]

    except Exception as exc:
        logger.warning("rewrite_parser: unexpected error %s", exc, exc_info=True)
        return None
