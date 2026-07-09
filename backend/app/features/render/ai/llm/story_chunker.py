"""
story_chunker.py — deterministic chapter chunking for Story Intelligence (P1).

A novel chapter (10k-20k words) is too long for one LLM call and Content Mode's
single-shot ``_fit_script`` would just TRUNCATE the tail. This splits the chapter
into semantic-ish windows (paragraph/sentence boundaries, never mid-word) with a
small overlap so per-chunk understanding keeps continuity across the seam.

Pure Python — no LLM, no I/O, deterministic, never raises (returns a best-effort
split, or a single whole-text chunk on any error). Under Sacred Contract #3 spirit
the AI layer above treats this as infallible.
"""
from __future__ import annotations

import logging
import os
import re

logger = logging.getLogger("app.render.story_chunker")

# Target chunk size in CHARACTERS (~2.5-3.5k tokens for CJK/Latin mixed). A GPT
# reasoning pass reads chunk + rolling summary comfortably at this size.
_DEFAULT_MAX_CHARS = int(os.getenv("STORY_CHUNK_CHARS", "12000") or 12000)
# Overlap carried from the previous chunk's tail so a beat split across the seam
# is still understood in context.
_DEFAULT_OVERLAP = int(os.getenv("STORY_CHUNK_OVERLAP", "600") or 600)

# Paragraph split on blank lines; sentence split on terminal punctuation
# (incl. CJK 。！？) followed by whitespace. Conservative — falls back to hard
# slicing only when a single "unit" already exceeds the cap.
_PARA_RE = re.compile(r"\n\s*\n+")
_SENT_RE = re.compile(r"(?<=[.!?。！？…])\s+")


def _split_units(text: str) -> list[str]:
    """Split into paragraphs, then further split any over-long paragraph into
    sentences. Never raises."""
    units: list[str] = []
    for para in _PARA_RE.split(text):
        p = para.strip()
        if not p:
            continue
        if len(p) <= _DEFAULT_MAX_CHARS:
            units.append(p)
        else:
            # Over-long paragraph → sentence split; still-too-long sentences are
            # hard-sliced below by the packer.
            sents = [s.strip() for s in _SENT_RE.split(p) if s.strip()]
            units.extend(sents or [p])
    return units


def _hard_slice(unit: str, max_chars: int) -> list[str]:
    """Last-resort slice of a single unit that alone exceeds the cap."""
    return [unit[i:i + max_chars] for i in range(0, len(unit), max_chars)]


def chunk_chapter(
    text: str,
    max_chars: int = _DEFAULT_MAX_CHARS,
    overlap: int = _DEFAULT_OVERLAP,
) -> list[str]:
    """Split a chapter into ordered windows of <= ``max_chars`` with a trailing
    ``overlap`` carried into the next window. Returns [whole text] for short input
    and [] for empty. Never raises.

    Boundaries prefer paragraph, then sentence; a unit larger than the cap is
    hard-sliced. The overlap is taken from the END of the previous emitted chunk
    so continuity is preserved without duplicating whole units."""
    try:
        s = (text or "").strip()
        if not s:
            return []
        cap = max(100, int(max_chars or _DEFAULT_MAX_CHARS))
        ov = max(0, min(int(overlap or 0), cap // 2))
        if len(s) <= cap:
            return [s]

        units = _split_units(s)
        chunks: list[str] = []
        buf = ""
        for unit in units:
            u = unit
            # A single unit larger than the cap → flush buffer, hard-slice it.
            if len(u) > cap:
                if buf:
                    chunks.append(buf)
                    buf = ""
                chunks.extend(_hard_slice(u, cap))
                continue
            if not buf:
                buf = u
            elif len(buf) + 1 + len(u) <= cap:
                buf = f"{buf}\n{u}"
            else:
                chunks.append(buf)
                # Seed the next buffer with the overlap tail of the flushed chunk.
                tail = buf[-ov:] if ov else ""
                buf = f"{tail}\n{u}" if tail else u
        if buf:
            chunks.append(buf)
        return chunks or [s]
    except Exception as exc:
        logger.info("story_chunker: split failed (%s) — single chunk", exc)
        return [(text or "").strip()] if (text or "").strip() else []


__all__ = ["chunk_chapter"]
