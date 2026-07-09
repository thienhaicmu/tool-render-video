"""
story_director.py — provider-agnostic Story Intelligence orchestration (P1).

Turns a raw novel chapter into a Story Bible (setting/hook/cta + canonical
characters + environments + rolling summary + topic/tone/audience/video_style)
via a MAP-REDUCE over chunked text:

    chunk_chapter → [per-chunk DIGEST via call_fn] → REDUCE via call_fn → bible

Mirrors content_director's design: parameterised by ``call_fn(system, user) ->
str | None`` so every provider (GPT default) binds its own raw model call (key
rotation / retry / cache stay inside call_fn). Adding a provider is: expose a
raw content-style call + bind it in ai/llm/__init__.analyze_story.

Sacred Contract #3: never raises — returns None on total failure. A partial
failure (reduce fails but digests exist) DEGRADES to a deterministic merge of the
per-chunk entities rather than losing everything.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Optional

from app.domain.story_plan import StoryBible, StoryPlan
from app.features.render.ai.llm.story_chunker import chunk_chapter
from app.features.render.ai.llm.story_prompts import (
    STORY_PROMPT_VERSION,
    build_story_digest_prompt,
    build_story_reduce_prompt,
    build_storyboard_prompt,
)
from app.features.render.ai.llm.story_parser import (
    parse_story_digest_response,
    parse_story_reduce_response,
    parse_storyboard_response,
)

logger = logging.getLogger("app.render.story_director")

StoryCall = Callable[[str, str], Optional[str]]

# Cap the running-summary length carried between chunks (chars).
_ROLLING_CAP = int(os.getenv("STORY_ROLLING_SUMMARY_CAP", "3000") or 3000)


def _digest_block(idx: int, digest: dict) -> str:
    """Render one chunk digest into a compact text block for the reduce prompt."""
    lines = [f"--- Part {idx} ---", f"summary: {digest.get('summary', '')}"]
    beats = digest.get("beats") or []
    if beats:
        lines.append("beats: " + "; ".join(beats[:20]))
    chars = digest.get("characters") or []
    if chars:
        lines.append("characters: " + "; ".join(
            f"[{c.id}] {c.name}: {c.description}" for c in chars
        ))
    envs = digest.get("environments") or []
    if envs:
        lines.append("environments: " + "; ".join(
            f"[{e.id}] {e.name}: {e.description}" for e in envs
        ))
    return "\n".join(lines)


def _merge_entities(digests: list[dict]) -> "tuple[list, list, str]":
    """Deterministic fallback merge — dedupe characters/environments by id/name and
    concatenate summaries. Used when the LLM reduce pass fails. Never raises."""
    chars: dict = {}
    envs: dict = {}
    summaries: list[str] = []
    for d in digests:
        if d.get("summary"):
            summaries.append(d["summary"])
        for c in (d.get("characters") or []):
            key = (c.id or c.name or "").strip().lower()
            if key and key not in chars:
                chars[key] = c
        for e in (d.get("environments") or []):
            key = (e.id or e.name or "").strip().lower()
            if key and key not in envs:
                envs[key] = e
    return list(chars.values()), list(envs.values()), " ".join(summaries)[:_ROLLING_CAP]


def run_story_intelligence(
    *,
    call_fn: StoryCall,
    chapter_text: str,
    language: str = "vi",
    tone: str = "",
    prior_context: str = "",
    provider_label: str = "",
) -> Optional[dict]:
    """Run the map-reduce Story Intelligence pass. Returns
    ``{"bible": StoryBible, "meta": {...}}`` or None (Sacred Contract #3 — never
    raises). ``call_fn`` owns provider specifics; the caller guards SDK/key BEFORE
    calling here.

    ``prior_context`` is optional cross-chapter context (earlier chapter summaries)
    so a later chapter grounds on what happened before."""
    try:
        text = (chapter_text or "").strip()
        if not text:
            return None
        _p = provider_label or "?"
        chunks = chunk_chapter(text)
        if not chunks:
            return None
        logger.info(
            "story_director[%s]: prompt=%s chunks=%d in_chars=%d lang=%s",
            _p, STORY_PROMPT_VERSION, len(chunks), len(text), language,
        )

        # ── MAP: per-chunk digest, threading a running summary ────────────────
        digests: list[dict] = []
        rolling = ""
        for i, chunk in enumerate(chunks, start=1):
            try:
                _sys, _usr = build_story_digest_prompt(
                    chunk, prior_summary=rolling, language=language,
                    chunk_index=i, total_chunks=len(chunks),
                )
                raw = call_fn(_sys, _usr)
                dg = parse_story_digest_response(raw) if raw else None
            except Exception as exc:
                logger.info("story_director[%s]: digest chunk %d failed (%s)", _p, i, exc)
                dg = None
            if dg is not None:
                digests.append(dg)
                if dg.get("summary"):
                    rolling = (rolling + " " + dg["summary"]).strip()[-_ROLLING_CAP:]
        if not digests:
            logger.warning("story_director[%s]: no chunk produced a digest", _p)
            return None

        digests_text = "\n\n".join(_digest_block(i, d) for i, d in enumerate(digests, start=1))

        # ── REDUCE: consolidate into a Story Bible ───────────────────────────
        bible: Optional[StoryBible] = None
        meta: dict = {}
        try:
            _rsys, _ruser = build_story_reduce_prompt(
                digests_text, prior_context=prior_context, language=language, tone=tone,
            )
            raw = call_fn(_rsys, _ruser)
            parsed = parse_story_reduce_response(raw) if raw else None
            if parsed is not None:
                bible, meta = parsed
        except Exception as exc:
            logger.info("story_director[%s]: reduce failed (%s) — deterministic merge", _p, exc)
            bible = None

        # ── Fallback: deterministic merge when the reduce pass yields nothing ─
        if bible is None:
            m_chars, m_envs, m_summary = _merge_entities(digests)
            bible = StoryBible(characters=m_chars, environments=m_envs)
            meta = {"rolling_summary": m_summary}
            if bible.is_empty() and not m_summary:
                return None
            logger.info(
                "story_director[%s]: reduce degraded → merged %d chars / %d envs",
                _p, len(m_chars), len(m_envs),
            )

        if not meta.get("rolling_summary"):
            meta["rolling_summary"] = rolling

        logger.info(
            "story_director[%s]: OK chars=%d envs=%d topic=%r",
            _p, len(bible.characters), len(bible.environments), meta.get("topic", ""),
        )
        return {"bible": bible, "meta": meta}
    except Exception as exc:
        logger.warning(
            "story_director[%s]: unexpected error %s", provider_label or "?", exc, exc_info=True,
        )
        return None


def inject_character_canon(plan: StoryPlan, bible: StoryBible) -> StoryPlan:
    """Deterministic visual-consistency pass (mirrors Content CU-6). For each shot,
    append the CANONICAL description of every Bible character present to the shot's
    ``visual_prompt`` (idempotent — skips a fragment already present), so the image
    generator draws the same character across shots. No-op without characters.
    Mutates + returns the plan. Never raises."""
    try:
        if plan is None or bible is None or not getattr(bible, "characters", None):
            return plan
        for shot in plan.all_shots():
            frags: list[str] = []
            for cid in (getattr(shot, "characters", None) or []):
                c = bible.character(cid)
                desc = (getattr(c, "description", "") or "").strip() if c is not None else ""
                if desc and desc not in frags:
                    frags.append(desc)
            if not frags:
                continue
            base = (shot.visual_prompt or "").strip()
            inject = "; ".join(frags)
            if inject in base:
                continue
            shot.visual_prompt = f"{base}. {inject}" if base else inject
        return plan
    except Exception as exc:
        logger.info("story_director: inject_character_canon skipped: %s", exc)
        return plan


def run_story_planning(
    *,
    call_fn: StoryCall,
    chapter_text: str,
    bible: Optional[StoryBible] = None,
    meta: Optional[dict] = None,
    language: str = "vi",
    tone: str = "",
    art_style: str = "",
    series_id: str = "",
    chapter_no: int = 0,
    aspect_ratio: str = "9:16",
    reading_pace: str = "normal",
    provider_label: str = "",
) -> Optional[StoryPlan]:
    """Adapt a chapter into a full StoryPlan (scenes → shots) grounded in the
    Bible, via a MAP over chunks (one storyboard call per chunk). Returns a
    StoryPlan or None (Sacred Contract #3 — never raises).

    Deterministic post-passes: inject character canon into each shot's
    visual_prompt (CU-6 analogue) + dense reindex + seed shot sids. quality_tier /
    transition defaults are already applied by the domain loader (by shot_type /
    2-tier cut-vs-fade)."""
    try:
        text = (chapter_text or "").strip()
        if not text:
            return None
        _p = provider_label or "?"
        meta = meta or {}
        chunks = chunk_chapter(text)
        if not chunks:
            return None
        logger.info(
            "story_director[%s]: storyboard prompt=%s chunks=%d art_style=%r",
            _p, STORY_PROMPT_VERSION, len(chunks), art_style,
        )

        all_scenes: list = []
        for i, chunk in enumerate(chunks, start=1):
            try:
                _sys, _usr = build_storyboard_prompt(
                    chunk, bible=bible, language=language, tone=tone,
                    art_style=art_style, chunk_index=i, total_chunks=len(chunks),
                )
                raw = call_fn(_sys, _usr)
                scenes = parse_storyboard_response(raw) if raw else None
            except Exception as exc:
                logger.info("story_director[%s]: storyboard chunk %d failed (%s)", _p, i, exc)
                scenes = None
            if scenes:
                all_scenes.extend(scenes)
        if not all_scenes:
            logger.warning("story_director[%s]: no storyboard scene produced", _p)
            return None

        plan = StoryPlan(
            series_id=series_id, chapter_no=chapter_no, language=language,
            art_style=art_style, aspect_ratio=aspect_ratio, reading_pace=reading_pace,
            topic=str(meta.get("topic", "") or ""), tone=(tone or str(meta.get("tone", "") or "")),
            story_bible=bible or StoryBible(), scenes=all_scenes,
        )
        if bible is not None:
            plan = inject_character_canon(plan, bible)
        plan.reindex()
        logger.info(
            "story_director[%s]: storyboard OK scenes=%d shots=%d",
            _p, plan.scene_count(), plan.shot_count(),
        )
        return plan
    except Exception as exc:
        logger.warning(
            "story_director[%s]: storyboard unexpected error %s", provider_label or "?", exc,
            exc_info=True,
        )
        return None


__all__ = [
    "run_story_intelligence", "run_story_planning", "inject_character_canon", "StoryCall",
]
