"""
story_series_memory.py — cross-chapter series memory for Story v2 (G1).

The series tables (story_repo: characters + chapter_summary) let a character drawn
in chapter 1 stay consistent in chapter 186 and a later chapter continue coherently.
This module is the SEAM that wires that memory into the v2 super-plan pipeline:

  • READ  — ``build_prior_context`` renders a compact grounding block (known
            characters + story-so-far) that the super-prompt injects when planning a
            LATER chapter of a series.
  • WRITE — ``persist_series_memory`` stores this chapter's characters + a rolling
            summary AFTER a successful render, so the NEXT chapter grounds on it.
  • ``rolling_summary_for`` builds that summary DETERMINISTICALLY from the plan (no
    extra LLM call — $0).

All DB access goes through ``story_repo`` (defensive). Everything here is gated by
``STORY_SERIES_MEMORY`` (default on) and only does anything when ``series_id`` is set
— a one-off chapter (empty series_id, the FE default) is byte-identical to before.
Never raises (Sacred Contract #3 spirit).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.db import story_repo

logger = logging.getLogger("app.render.story.series_memory")

_MAX_CONTEXT_CHARS = int(os.getenv("STORY_SERIES_CONTEXT_CHARS", "4000") or 4000)
_MAX_SUMMARY_CHARS = int(os.getenv("STORY_SERIES_SUMMARY_CHARS", "1500") or 1500)


def _enabled() -> bool:
    return os.getenv("STORY_SERIES_MEMORY", "1") == "1"


def build_prior_context(series_id: str, before_chapter: Optional[int] = None) -> str:
    """Compact grounding block for the super-prompt: canonical characters already
    established in the series + the rolling story-so-far from earlier chapters. Returns
    "" when disabled / no series / no memory yet / on any error. Never raises."""
    if not _enabled() or not (series_id or "").strip():
        return ""
    try:
        chars = story_repo.list_characters(series_id)
        sums = story_repo.list_chapter_summaries(series_id, before_chapter=before_chapter)
        parts: list[str] = []
        if chars:
            lines = [f"- {c['id']} ({(c.get('name') or '').strip()}): "
                     f"{(c.get('canonical_desc') or '').strip()}"
                     for c in chars if (c.get('id') or '').strip()]
            if lines:
                parts.append("KNOWN CHARACTERS (reuse these ids + canonical look):\n"
                             + "\n".join(lines))
        if sums:
            so_far = "\n".join(
                f"[Ch.{s['chapter_no']}] {(s.get('rolling_summary') or '').strip()}"
                for s in sums if (s.get('rolling_summary') or '').strip())
            if so_far:
                parts.append("STORY SO FAR:\n" + so_far)
        block = "\n\n".join(parts).strip()
        return block[:_MAX_CONTEXT_CHARS].rstrip() if block else ""
    except Exception as exc:
        logger.info("series_memory: build_prior_context failed series=%s: %s", series_id, exc)
        return ""


def rolling_summary_for(plan) -> str:
    """Deterministic rolling summary of a rendered chapter (topic + narration), capped.
    No LLM call — pure + free. Never raises."""
    try:
        topic = (getattr(plan, "topic", "") or "").strip()
        narr = " ".join((b.narration or "").strip()
                        for b in getattr(plan, "timeline", []) if (b.narration or "").strip())
        s = (f"{topic}. {narr}" if topic else narr).strip()
        return s[:_MAX_SUMMARY_CHARS].rstrip()
    except Exception:
        return ""


def persist_series_memory(plan, series_id: str, chapter_no: int) -> None:
    """After a successful render, persist this chapter's canonical characters (name +
    canonical_desc + cast voice) and a rolling summary so the next chapter grounds on
    them. PRESERVES any reference_image_path already pinned on a character (the
    reference-sheet path set earlier in this render). Gated + best-effort — never
    raises, never fails a render."""
    if not _enabled() or not (series_id or "").strip():
        return
    try:
        story_repo.upsert_series(
            series_id, language=(getattr(plan, "language", "") or ""),
            art_style=(getattr(plan, "art_style", "") or ""))
        voices = getattr(getattr(plan, "render", None), "voices", {}) or {}
        for c in (getattr(plan, "characters", None) or []):
            cid = (getattr(c, "id", "") or "").strip()
            if not cid:
                continue
            v = voices.get(cid) or []
            # Preserve an already-pinned reference sheet (upsert overwrites the column).
            existing = story_repo.get_character(cid) or {}
            ref = (existing.get("reference_image_path") or "").strip()
            story_repo.upsert_character(
                cid, series_id=series_id, name=(c.name or ""),
                canonical_desc=(c.canonical_desc or ""), reference_image_path=ref,
                voice_engine=(v[0] if len(v) > 0 else ""),
                voice_id=(v[1] if len(v) > 1 else ""),
                age=(getattr(c, "age", "") or ""),
                gender=((getattr(c, "voice_gender", "") or getattr(c, "gender", "") or "")),
            )
        summary = rolling_summary_for(plan)
        if summary:
            story_repo.add_chapter_summary(series_id, int(chapter_no or 0), summary)
        logger.info("series_memory: persisted series=%s ch=%s chars=%d",
                    series_id, chapter_no, len(getattr(plan, "characters", None) or []))
    except Exception as exc:
        logger.warning("series_memory: persist failed series=%s: %s", series_id, exc)


__all__ = ["build_prior_context", "rolling_summary_for", "persist_series_memory"]
