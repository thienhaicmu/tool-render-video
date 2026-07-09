"""
Story Studio API (P1) — Story Intelligence endpoint.

Story-to-Video's first pipeline step reads a whole chapter and reconstructs a
Story Bible (setting/hook/cta + canonical characters + environments + rolling
summary) BEFORE any storyboard/render. This router exposes it plan-only so the FE
Bible-review screen (Duyệt #1) can show/edit it, and so P1 is testable in
isolation:

    POST /api/story/analyze  {chapter_text, language, tone, series_id, chapter_no, ...}
        → {"bible": <StoryBible dict>, "meta": {...}}   (no render)

When ``series_id`` is provided the result is PERSISTED to the cross-chapter
Character/Environment DB (story_repo) and the chapter's rolling summary is
appended — so a later chapter grounds on it. A one-off chapter (empty series_id)
just returns the bible without persisting.

Sacred Contract #3: analyze_story already returns None on any failure; here that
surfaces as a clean 502 (no unhandled raise reaches the client).
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import CACHE_DIR
from app.db import story_repo
from app.features.render.ai.llm import analyze_story, generate_story_plan

logger = logging.getLogger("app.story.api")

router = APIRouter(prefix="/api/story", tags=["story"])

# Per-scene narration PREVIEW audio lives under the cache root (pruneable). Keyed
# by an opaque 32-hex token; the audio GET validates the token shape.
_PREVIEW_DIR = CACHE_DIR / "story_preview"
_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")


class StoryAnalyzeRequest(BaseModel):
    chapter_text: str = Field(default="", description="Raw chapter text")
    language: str = "vi"
    tone: str = ""
    series_id: str = ""          # "" = one-off chapter (no cross-chapter persist)
    chapter_no: int = 0
    ai_provider: Optional[str] = None
    llm_model: Optional[str] = None


def _persist_bible(series_id: str, chapter_no: int, bible, rolling_summary: str) -> None:
    """Persist canonical characters/environments + the rolling summary for a
    series so later chapters reuse them. Best-effort — story_repo is defensive."""
    try:
        story_repo.upsert_series(series_id)
        for c in bible.characters:
            story_repo.upsert_character(
                c.id or c.name, series_id=series_id, name=c.name,
                canonical_desc=c.description, reference_image_path=c.reference_image_path,
                voice_engine=c.voice_engine, voice_id=c.voice_id, age=c.age, gender=c.gender,
            )
        for e in bible.environments:
            story_repo.upsert_environment(
                e.id or e.name, series_id=series_id, name=e.name,
                canonical_desc=e.description, reference_image_path=e.reference_image_path,
            )
        if rolling_summary:
            story_repo.add_chapter_summary(series_id, chapter_no, rolling_summary)
    except Exception as exc:  # never break the response on a persist hiccup
        logger.warning("story: persist bible failed series=%s: %s", series_id, exc)


@router.post("/analyze")
def analyze_chapter(req: StoryAnalyzeRequest) -> dict:
    """Run Story Intelligence on a chapter (no render). 422 empty text; 502 when
    the AI produced no usable bible (missing key / provider error — analyze_story
    returned None per Sacred Contract #3)."""
    text = (req.chapter_text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="chapter_text is required")

    from app.core import config as _cfg
    from app.features.render.engine.pipeline.llm_stage import _resolve_api_key

    provider = (req.ai_provider or "").strip().lower() or getattr(_cfg, "AI_PROVIDER_DEFAULT", "openai")
    api_key, _ = _resolve_api_key(req, provider)

    # Cross-chapter context: earlier chapter summaries of this series (if any).
    prior_context = ""
    if (req.series_id or "").strip():
        try:
            prior = story_repo.list_chapter_summaries(req.series_id, before_chapter=req.chapter_no or None)
            prior_context = "\n".join(
                f"[Ch.{p['chapter_no']}] {p['rolling_summary']}" for p in prior if p.get("rolling_summary")
            )
        except Exception:
            prior_context = ""

    result = analyze_story(
        provider=provider, chapter_text=text, language=(req.language or "vi"),
        tone=(req.tone or ""), prior_context=prior_context, api_key=api_key,
        model=req.llm_model, resolve_key=lambda _p: _resolve_api_key(req, _p)[0],
    )
    if result is None or result.get("bible") is None:
        raise HTTPException(status_code=502, detail="Story Intelligence returned no usable bible")

    bible = result["bible"]
    meta = result.get("meta") or {}

    if (req.series_id or "").strip():
        _persist_bible(req.series_id, req.chapter_no or 0, bible, meta.get("rolling_summary", ""))

    return {"bible": asdict(bible), "meta": meta}


class StoryPlanRequest(BaseModel):
    chapter_text: str = Field(default="", description="Raw chapter text")
    language: str = "vi"
    tone: str = ""
    art_style: str = ""
    series_id: str = ""
    chapter_no: int = 0
    aspect_ratio: str = "9:16"
    reading_pace: str = "normal"       # slow|normal|fast
    bible: Optional[dict] = None       # a pre-analysed Story Bible (skip re-analysis)
    ai_provider: Optional[str] = None
    llm_model: Optional[str] = None


@router.post("/plan")
def plan_storyboard(req: StoryPlanRequest) -> dict:
    """Generate a full StoryPlan (scenes → shots → narration → visual prompts) from
    a chapter (the Storyboard-review step, Duyệt #2). Runs Story Intelligence first
    when no ``bible`` is supplied. Returns the plan + a narration audit + duration
    estimate. 422 empty text; 502 when the AI produced no usable plan (Sacred
    Contract #3 — analyze/plan returned None)."""
    text = (req.chapter_text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="chapter_text is required")

    from app.core import config as _cfg
    from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
    from app.domain.story_plan import _story_bible_from_dict

    provider = (req.ai_provider or "").strip().lower() or getattr(_cfg, "AI_PROVIDER_DEFAULT", "openai")
    api_key, _ = _resolve_api_key(req, provider)
    bible = _story_bible_from_dict(req.bible) if req.bible else None

    plan = generate_story_plan(
        provider=provider, chapter_text=text, bible=bible, language=(req.language or "vi"),
        tone=(req.tone or ""), art_style=(req.art_style or ""), series_id=(req.series_id or ""),
        chapter_no=(req.chapter_no or 0), aspect_ratio=(req.aspect_ratio or "9:16"),
        reading_pace=(req.reading_pace or "normal"), api_key=api_key, model=req.llm_model,
        resolve_key=lambda _p: _resolve_api_key(req, _p)[0],
    )
    if plan is None or plan.scene_count() == 0:
        raise HTTPException(status_code=502, detail="Story planning returned no usable plan")

    return {
        "plan": json.loads(plan.to_json()),
        "scene_count": plan.scene_count(),
        "shot_count": plan.shot_count(),
        "estimated_total_sec": round(plan.estimated_total_sec(), 1),
        "narration_audit": plan.narration_audit(),
    }


# ── P3: Character Reference Sheet (Duyệt #1 — visual consistency) ─────────────

class ReferenceSheetRequest(BaseModel):
    series_id: str = ""
    character_id: str = ""
    name: str = ""              # used when generating ad-hoc (no series persistence)
    description: str = ""
    art_style: str = ""


@router.post("/character/reference-sheet")
def character_reference_sheet(req: ReferenceSheetRequest) -> dict:
    """Generate a canonical Character Reference Sheet (gpt-image-1) and, when a
    series is given, PIN it on the character (characters.reference_image_path) so
    every later shot conditions generation on it. 422 without a description;
    502 when generation failed (no key / error — Sacred Contract #3)."""
    from app.domain.story_plan import StoryCharacter
    from app.features.render.engine.visual.story_reference_sheet import (
        generate_character_reference_sheet,
    )

    # Prefer the persisted canonical description when a character id is given.
    desc = (req.description or "").strip()
    name = (req.name or "").strip()
    cid = (req.character_id or "").strip()
    if cid and (req.series_id or "").strip() and not desc:
        row = story_repo.get_character(cid)
        if row is not None:
            desc = (row.get("canonical_desc") or "").strip()
            name = name or (row.get("name") or "").strip()
    if not (desc or name):
        raise HTTPException(status_code=422, detail="description or a persisted character is required")

    character = StoryCharacter(id=cid or name, name=name, description=desc)
    path = generate_character_reference_sheet(character, art_style=(req.art_style or ""))
    if not path:
        raise HTTPException(status_code=502, detail="reference sheet generation failed")

    # Pin on the character so later shots reuse it (only when persisting to a series).
    if cid and (req.series_id or "").strip():
        try:
            story_repo.upsert_character(
                cid, series_id=req.series_id, name=name,
                canonical_desc=desc, reference_image_path=path,
            )
        except Exception as exc:
            logger.warning("story: pin reference sheet failed cid=%s: %s", cid, exc)

    return {"path": path}


# ── P4: per-shot narration preview (cast voice + language-routed engine) ──────

class NarrationPreviewRequest(BaseModel):
    text: str = Field(default="", description="The shot narration to voice")
    language: str = "vi"
    gender: str = "female"
    voice_id: str = ""          # from Voice Casting (engine-specific)
    reading_speed: float = 1.0


@router.post("/narration/preview")
def narration_preview(req: NarrationPreviewRequest) -> dict:
    """Synthesize ONE shot's narration to previewable audio, routing the engine by
    language (Gemini VI / ElevenLabs EN-JP; edge fallback). Returns
    ``{token, url, engine, duration_sec}``. 422 empty text; 502 when TTS produced
    nothing (Sacred Contract #3 — no unhandled raise reaches the client)."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")

    from app.features.render.engine.audio.tts import (
        generate_narration_audio, resolve_story_tts_engine,
    )
    from app.features.render.engine.stages.content_scene_render import (
        _reading_speed_to_rate, probe_audio_duration,
    )

    engine = resolve_story_tts_engine(req.language)
    _PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    out = _PREVIEW_DIR / f"{token}.mp3"
    try:
        path = generate_narration_audio(
            text=text, language=(req.language or "vi"), gender=(req.gender or "female"),
            rate=_reading_speed_to_rate(req.reading_speed),
            job_id=f"story-preview-{token}", voice_id=(req.voice_id or None),
            output_path=str(out), content_type="vlog", tts_engine=engine,
        )
    except Exception as exc:
        logger.warning("story narration preview: TTS raised %s", exc)
        raise HTTPException(status_code=502, detail="TTS failed")

    final = Path(path) if path else out
    if final != out and final.exists():
        try:
            import shutil
            shutil.move(str(final), str(out))
        except Exception:
            out = final
    if not out.exists() or out.stat().st_size <= 0:
        raise HTTPException(status_code=502, detail="TTS produced no audio")

    return {
        "token": token, "url": f"/api/story/narration/audio/{token}",
        "engine": engine, "duration_sec": probe_audio_duration(str(out)),
    }


@router.get("/narration/audio/{token}")
def narration_audio(token: str):
    """Stream a narration-preview mp3 by token. 404 on a malformed/expired token."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    p = _PREVIEW_DIR / f"{token}.mp3"
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="audio/mpeg")
