"""
transcript_analyzer.py — Fallback-safe transcript normalization.

Accepts transcript/subtitle blocks in multiple formats and normalizes
them to a list of timing-enriched chunks. Never raises; returns [] on
any failure or missing input.

Public API:
    normalize_transcript_chunks(source) -> list[dict]
"""
from __future__ import annotations

import re
from typing import Any


def normalize_transcript_chunks(source: Any) -> list[dict]:
    """Normalize diverse transcript formats into enriched chunk dicts.

    Accepted inputs:
    - list[dict]  — blocks with start/end/text keys (SRT parse output, Whisper result)
    - list[Any]   — objects with start/end/text attributes
    - str         — SRT-format text or plain text fallback
    - None / empty — returns []

    Each output chunk:
        {"start": float, "end": float, "text": str, "word_count": int, "speech_density": float}
    """
    if not source:
        return []
    try:
        if isinstance(source, list):
            raw = [_normalize_one(item) for item in source]
            chunks = [c for c in raw if c is not None]
        elif isinstance(source, str):
            chunks = _parse_srt_or_text(source)
        else:
            return []
        return [_enrich(c) for c in chunks]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_one(item: Any) -> dict | None:
    if item is None:
        return None
    if isinstance(item, dict):
        text = str(
            item.get("text") or item.get("content") or item.get("transcript") or ""
        ).strip()
        if not text:
            return None
        start = _to_float(
            item.get("start") or item.get("start_sec") or item.get("start_time") or 0.0
        )
        end = _to_float(
            item.get("end") or item.get("end_sec") or item.get("end_time") or 0.0
        )
        return {"start": start, "end": end, "text": text}
    # Try attribute access (Whisper result objects, dataclasses, etc.)
    try:
        text = str(
            getattr(item, "text", None) or getattr(item, "content", None) or ""
        ).strip()
        if not text:
            return None
        start = _to_float(getattr(item, "start", 0.0) or getattr(item, "start_sec", 0.0))
        end = _to_float(getattr(item, "end", 0.0) or getattr(item, "end_sec", 0.0))
        return {"start": start, "end": end, "text": text}
    except Exception:
        return None


def _to_float(v: Any) -> float:
    try:
        return float(v or 0.0)
    except (ValueError, TypeError):
        return 0.0


_SRT_TIMESTAMP_RE = re.compile(
    r"(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{1,3})"
)


def _srt_time_to_sec(ts: str) -> float:
    try:
        ts = ts.strip().replace(",", ".")
        parts = ts.split(":")
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(ts)
    except Exception:
        return 0.0


def _parse_srt_or_text(text: str) -> list[dict]:
    """Parse SRT-formatted string; fall back to single plain-text chunk."""
    text = text.strip()
    if not text:
        return []

    # Check if it looks like SRT (contains --> arrows)
    if "-->" in text:
        return _parse_srt_blocks(text)

    # Plain text: return as a single untimed chunk
    return [{"start": 0.0, "end": 0.0, "text": text}]


def _parse_srt_blocks(srt_text: str) -> list[dict]:
    chunks = []
    lines = srt_text.splitlines()
    i = 0
    while i < len(lines):
        # Skip blank lines and sequence numbers
        line = lines[i].strip()
        if not line or line.isdigit():
            i += 1
            continue
        # Look for timestamp line
        m = _SRT_TIMESTAMP_RE.match(line)
        if m:
            start_ts, end_ts = m.group(1), m.group(2)
            i += 1
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            content = " ".join(text_lines)
            # Strip HTML/ASS tags
            content = re.sub(r"<[^>]+>|\{[^}]+\}", "", content).strip()
            if content:
                chunks.append({
                    "start": _srt_time_to_sec(start_ts),
                    "end": _srt_time_to_sec(end_ts),
                    "text": content,
                })
        else:
            i += 1
    return chunks


def _enrich(chunk: dict) -> dict:
    text = chunk.get("text", "")
    words = len(text.split()) if text else 0
    duration = max(0.0, chunk.get("end", 0.0) - chunk.get("start", 0.0))
    density = round(words / duration, 3) if duration > 0 else 0.0
    return {
        "start": chunk["start"],
        "end": chunk["end"],
        "text": text,
        "word_count": words,
        "speech_density": density,
    }
