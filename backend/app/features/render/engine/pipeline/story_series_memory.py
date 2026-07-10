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
# Budget for the STORY-SO-FAR section — keeps the MOST RECENT chapters (continuity
# matters most), not the oldest.
_MAX_SUMMARY_SECTION = int(os.getenv("STORY_SERIES_SUMMARY_SECTION_CHARS", "2000") or 2000)


def _enabled() -> bool:
    return os.getenv("STORY_SERIES_MEMORY", "1") == "1"


def _head_tail(text: str, budget: int, head_frac: float = 0.4) -> str:
    """Fit ``text`` into ``budget`` chars keeping BOTH the setup (head) and — weighted
    heavier — the ending (tail), joined by an ellipsis. A plain head cut would drop the
    climax/ending, which is exactly what the next chapter needs. Never raises."""
    t = (text or "").strip()
    if budget <= 0:
        return ""
    if len(t) <= budget:
        return t
    sep = " … "
    avail = budget - len(sep)
    if avail <= 0:
        return t[:budget].rstrip()
    head_n = max(0, int(avail * head_frac))
    tail_n = avail - head_n
    return (t[:head_n].rstrip() + sep + t[-tail_n:].lstrip()) if tail_n > 0 else t[:head_n].rstrip()


def _recent_summaries(sums: list, budget: int) -> str:
    """Render the MOST RECENT chapter summaries that fit ``budget`` (newest kept first),
    then present them chronologically. ``sums`` is oldest-first. Never raises."""
    lines: list[str] = []
    used = 0
    try:
        for s in reversed(sums or []):
            txt = (s.get("rolling_summary") or "").strip()
            if not txt:
                continue
            line = f"[Ch.{s.get('chapter_no')}] {txt}"
            if lines and used + len(line) + 1 > budget:
                break
            lines.append(line)
            used += len(line) + 1
    except Exception:
        return ""
    lines.reverse()
    return "\n".join(lines)


def build_prior_context(series_id: str, before_chapter: Optional[int] = None) -> str:
    """Compact grounding block for the super-prompt: canonical characters already
    established in the series + the rolling story-so-far from earlier chapters. Returns
    "" when disabled / no series / no memory yet / on any error. Never raises."""
    if not _enabled() or not (series_id or "").strip():
        return ""
    try:
        chars = story_repo.list_characters(series_id)
        envs = story_repo.list_environments(series_id)
        sums = story_repo.list_chapter_summaries(series_id, before_chapter=before_chapter)
        parts: list[str] = []
        if chars:
            lines = [f"- {c['id']} ({(c.get('name') or '').strip()}): "
                     f"{(c.get('canonical_desc') or '').strip()}"
                     for c in chars if (c.get('id') or '').strip()]
            if lines:
                parts.append("KNOWN CHARACTERS (reuse these ids + canonical look):\n"
                             + "\n".join(lines))
        if envs:
            elines = [f"- {e['id']} ({(e.get('name') or '').strip()}): "
                      f"{(e.get('canonical_desc') or '').strip()}"
                      for e in envs if (e.get('id') or '').strip()]
            if elines:
                parts.append("KNOWN SETTINGS (reuse these ids + look):\n" + "\n".join(elines))
        so_far = _recent_summaries(sums, _MAX_SUMMARY_SECTION)
        if so_far:
            parts.append("STORY SO FAR (most recent chapters):\n" + so_far)
        block = "\n\n".join(parts).strip()
        return block[:_MAX_CONTEXT_CHARS].rstrip() if block else ""
    except Exception as exc:
        logger.info("series_memory: build_prior_context failed series=%s: %s", series_id, exc)
        return ""


def rolling_summary_for(plan) -> str:
    """Deterministic rolling summary of a rendered chapter: topic + a head+tail slice of
    the narration (so the chapter's ENDING — what the next chapter continues from — is
    kept, not just its opening). No LLM call — pure + free. Never raises."""
    try:
        topic = (getattr(plan, "topic", "") or "").strip()
        narr = " ".join((b.narration or "").strip()
                        for b in getattr(plan, "timeline", []) if (b.narration or "").strip())
        prefix = f"{topic}. " if topic else ""
        body = _head_tail(narr, max(0, _MAX_SUMMARY_CHARS - len(prefix)))
        return (prefix + body).strip()[:_MAX_SUMMARY_CHARS].rstrip()
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
        # G6: persist canonical settings too (preserve any pinned environment ref).
        for s in (getattr(plan, "settings", None) or []):
            sid = (getattr(s, "id", "") or "").strip()
            if not sid:
                continue
            existing = story_repo.get_environment(sid) or {}
            ref = (existing.get("reference_image_path") or "").strip()
            story_repo.upsert_environment(
                sid, series_id=series_id, name=(s.name or ""),
                canonical_desc=(s.canonical_desc or ""), reference_image_path=ref)
        summary = rolling_summary_for(plan)
        if summary:
            story_repo.add_chapter_summary(series_id, int(chapter_no or 0), summary)
        logger.info("series_memory: persisted series=%s ch=%s chars=%d settings=%d",
                    series_id, chapter_no, len(getattr(plan, "characters", None) or []),
                    len(getattr(plan, "settings", None) or []))
    except Exception as exc:
        logger.warning("series_memory: persist failed series=%s: %s", series_id, exc)


__all__ = ["build_prior_context", "rolling_summary_for", "persist_series_memory"]
