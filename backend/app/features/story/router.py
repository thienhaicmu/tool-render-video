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
from app.features.render.ai.llm import analyze_story, generate_story_plan_v2

logger = logging.getLogger("app.story.api")

router = APIRouter(prefix="/api/story", tags=["story"])

# Per-beat narration + key-visual PREVIEW assets live under the cache root
# (pruneable). Keyed by an opaque 32-hex token; the GET validates the token shape.
_PREVIEW_DIR = CACHE_DIR / "story_preview"
_VISUAL_DIR = CACHE_DIR / "story_preview_visual"
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
    source: str = "paste"              # paste (source A) | idea (source B)
    chapter_text: str = Field(default="", description="Raw chapter text (source=paste)")
    idea: str = ""                     # short idea (source=idea)
    duration_sec: int = 0              # target length (source=idea)
    genre: str = ""
    language: str = "vi"
    art_style: str = ""
    aspect_ratio: str = "16:9"
    subtitle_mode: str = "hook_only"   # hook_only | full | off
    ceiling: Optional[int] = None      # max key-visuals (default env STORY_MAX_IMAGES)
    series_id: str = ""
    chapter_no: int = 0
    ai_provider: Optional[str] = None
    llm_model: Optional[str] = None


@router.post("/plan")
def plan_storyboard(req: StoryPlanRequest) -> dict:
    """Story v2 — ONE super call → StoryPlan v2 (characters/settings/visuals/timeline).
    source=paste (A) adapts a whole chapter; source=idea (B) authors from a short idea
    + target duration — SAME output schema. Returns the plan + counts for the FE
    review screen. 422 when the chosen source's text is empty; 502 when the AI
    produced no usable plan (Sacred Contract #3 — generate_story_plan_v2 returned
    None)."""
    import os as _os

    source = (req.source or "paste").strip().lower()
    if source not in ("paste", "idea"):
        source = "paste"
    chapter = (req.chapter_text or "").strip()
    idea = (req.idea or "").strip()
    if source == "idea":
        if not idea:
            raise HTTPException(status_code=422, detail="idea is required for source=idea")
    elif not chapter:
        raise HTTPException(status_code=422, detail="chapter_text is required")

    from app.features.render.engine.pipeline.llm_stage import _resolve_api_key

    # GPT-centric like the render pipeline: provider from payload else STORY_AI_PROVIDER
    # (.env, default "openai") — NOT the global AI_PROVIDER_DEFAULT.
    provider = (req.ai_provider or "").strip().lower() or (
        _os.getenv("STORY_AI_PROVIDER", "openai") or "openai").strip().lower()
    api_key, _ = _resolve_api_key(req, provider)

    plan = generate_story_plan_v2(
        provider=provider, source=source, chapter=chapter, idea=idea,
        duration_sec=int(req.duration_sec or 0), genre=(req.genre or ""),
        language=(req.language or "vi"), art_style=(req.art_style or ""),
        aspect_ratio=(req.aspect_ratio or "16:9"),
        subtitle_mode=(req.subtitle_mode or "hook_only"), ceiling=req.ceiling,
        series_id=(req.series_id or ""), chapter_no=int(req.chapter_no or 0),
        api_key=api_key, model=req.llm_model,
        resolve_key=lambda _p: _resolve_api_key(req, _p)[0],
    )
    if plan is None or plan.is_empty() or plan.image_count() == 0:
        raise HTTPException(status_code=502, detail="Story planning returned no usable plan")

    # Cost preflight (C6): the gpt_image (premium) render generates one image per
    # Visual PLUS one reference sheet per distinct character present in the visuals.
    # Surface both counts so a consumer's cost estimate isn't blind to the sheets
    # (upper bound — series-pinned sheets are reused at render, so actual may be fewer).
    _ref_chars = {cid for v in plan.visuals for cid in (v.character_ids or []) if cid}
    _refsheet_count = len(_ref_chars)
    _visual_count = plan.image_count()
    return {
        "plan": json.loads(plan.to_json()),
        "image_count": _visual_count,
        "beat_count": plan.beat_count(),
        "estimated_total_sec": round(plan.estimated_total_sec(), 1),
        "character_count": len(plan.characters),
        "cost_preflight": {
            "visual_count": _visual_count,
            "character_count": len(plan.characters),
            "reference_sheet_count": _refsheet_count,
            "premium_image_count": _visual_count + _refsheet_count,
        },
    }


# ── B8: single key-visual preview (Storyboard review) ─────────────────────────

class StoryVisualPreviewRequest(BaseModel):
    prompt: str = Field(default="", description="The key-visual image prompt")
    negative_prompt: str = ""
    art_style: str = ""
    aspect_ratio: str = "16:9"
    tier: str = "medium"               # low | medium | high (capped at STORY_IMAGE_MAX_TIER)
    # Phase 2 — draft/final split: the Storyboard review previews with the FREE
    # provider by default ($0 to regenerate). "gpt_image" available for a paid preview.
    provider: str = "pollinations"     # pollinations (free) | gpt_image (paid)


@router.post("/visual/preview")
def visual_preview(req: StoryVisualPreviewRequest) -> dict:
    """Story v2 — generate ONE key-visual image from a prompt so the FE storyboard
    can preview/regenerate a Visual before render. Returns ``{token, url}``. 422 empty
    prompt; 502 when generation failed (no key / error — Sacred Contract #3)."""
    from app.domain.story_plan_v2 import Visual, ASPECT_SIZE
    from app.features.render.engine.visual.story_image import generate_visual_image

    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt is required")
    w, h = ASPECT_SIZE.get((req.aspect_ratio or "16:9"), ASPECT_SIZE["16:9"])
    _VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    out = _VISUAL_DIR / f"{token}.png"
    visual = Visual(id=token, prompt=prompt, negative_prompt=(req.negative_prompt or ""),
                    tier=(req.tier or "medium"))
    provider = (req.provider or "pollinations").strip().lower()
    if provider not in ("pollinations", "gpt_image"):
        provider = "pollinations"
    path = generate_visual_image(visual, {}, (req.art_style or ""), w, h, str(out), provider=provider)
    if not path or not Path(path).exists() or Path(path).stat().st_size <= 0:
        raise HTTPException(status_code=502, detail="visual generation failed")
    return {"token": token, "url": f"/api/story/visual/image/{token}"}


@router.get("/visual/image/{token}")
def visual_image(token: str):
    """Stream a key-visual preview png by token. 404 on a malformed/expired token."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    p = _VISUAL_DIR / f"{token}.png"
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="image/png")


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
