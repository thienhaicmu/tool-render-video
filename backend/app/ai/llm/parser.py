"""
parser.py — Parse LLM segment-selection response into LLMSegment list.

All parsing is defensive: never raises, returns None on any failure.
Caller treats None as signal to hard-fail the pipeline.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("app.render.llm_parser")

_INVALID_FS_CHARS = re.compile(r'[/\\:*?"<>|\t\n\r]')


@dataclass
class LLMSegment:
    start: float      # seconds
    end: float        # seconds
    score: float      # 0.0–1.0
    clip_name: str    # natural name used as output filename stem
    title: str        # display title
    reason: str       # model's explanation


# Backward-compat alias — existing consumers that reference GroqSegment still work.
GroqSegment = LLMSegment


def sanitize_clip_name(raw: str) -> str:
    """Keep natural name (spaces, Vietnamese chars OK), strip only FS-invalid chars."""
    clean = _INVALID_FS_CHARS.sub("", raw).strip()
    clean = re.sub(r" {2,}", " ", clean)[:80]
    return clean or "clip"


def parse_segment_response(
    raw: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
) -> Optional[list[LLMSegment]]:
    """
    Parse LLM raw text response into validated LLMSegment list.

    Returns None only when no valid segments can be parsed at all.
    When the LLM returns fewer valid segments than requested, returns the
    valid subset (lenient — better some clips than render failure).
    """
    try:
        data = _extract_json_array(raw)
        if isinstance(data, dict):
            for _key in ("segments", "clips", "items", "results", "data"):
                if isinstance(data.get(_key), list):
                    data = data[_key]
                    break
        if not isinstance(data, list):
            logger.warning(
                "llm_parser: expected list (or object with 'segments' key), "
                "got %s — raw preview: %r",
                type(data).__name__, raw[:300],
            )
            return None

        segments: list[LLMSegment] = []
        rejected = 0
        for item in data:
            seg = _parse_item(item, min_sec, max_sec, video_duration)
            if seg is not None:
                segments.append(seg)
            else:
                rejected += 1

        if not segments:
            logger.warning(
                "llm_parser: 0 valid segments out of %d returned "
                "(min_sec=%.0f max_sec=%.0f video_dur=%.0f) — raw preview: %r",
                len(data), min_sec, max_sec, video_duration, raw[:300],
            )
            return None

        segments.sort(key=lambda s: s.score, reverse=True)
        result = segments[:output_count]

        if len(result) < output_count:
            logger.info(
                "llm_parser: %d/%d valid segments (%d rejected) — proceeding with subset",
                len(result), output_count, rejected,
            )

        return result

    except Exception as exc:
        logger.warning("llm_parser: unexpected error — %s", exc, exc_info=True)
        return None


def _extract_json_array(raw: str) -> object:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _parse_item(
    item: object,
    min_sec: float,
    max_sec: float,
    video_duration: float,
) -> Optional[LLMSegment]:
    if not isinstance(item, dict):
        return None
    try:
        start = float(item["start"])
        end   = float(item["end"])
    except (KeyError, TypeError, ValueError):
        return None

    duration = end - start
    if not (min_sec <= duration <= max_sec):
        logger.debug("llm_parser: segment %.1f-%.1f rejected (dur=%.1fs)", start, end, duration)
        return None
    if start < 0 or end > video_duration + 1.0:
        logger.debug("llm_parser: segment %.1f-%.1f out of bounds (video=%.1fs)", start, end, video_duration)
        return None

    raw_name  = str(item.get("clip_name") or item.get("title") or "clip")
    raw_title = str(item.get("title")     or raw_name)
    score     = float(item.get("score", 0.5))
    score     = max(0.0, min(1.0, score))

    return LLMSegment(
        start=start,
        end=end,
        score=score,
        clip_name=sanitize_clip_name(raw_name),
        title=raw_title.strip()[:120],
        reason=str(item.get("reason", "")).strip()[:300],
    )
