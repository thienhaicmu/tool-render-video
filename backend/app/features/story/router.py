"""
Story Studio API — Story-to-Video v2 pre-render review endpoints.

The render itself goes through the shared render API (render_format="story"); this
router covers the review flow the FE Story Studio drives before render:

    POST /api/story/plan                     — ONE super call → StoryPlan v2
    POST /api/story/visual/preview           — one key-visual image (preview/regen)
    POST /api/story/character/reference-sheet — canonical character reference sheet
    POST /api/story/narration/preview        — one beat's narration to audio

All AI calls are defensive (Sacred Contract #3): a None/empty result surfaces as a
clean 4xx/502 — no unhandled raise reaches the client.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import CACHE_DIR
from app.db import story_repo
from app.features.render.ai.llm import generate_story_plan_v2

logger = logging.getLogger("app.story.api")

router = APIRouter(prefix="/api/story", tags=["story"])

# Per-beat narration + key-visual PREVIEW assets live under the cache root
# (pruneable). Keyed by an opaque 32-hex token; the GET validates the token shape.
_PREVIEW_DIR = CACHE_DIR / "story_preview"
_VISUAL_DIR = CACHE_DIR / "story_preview_visual"
_MASTER_DIR = CACHE_DIR / "story_master"          # transparent character-master previews
_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")


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

    # G1: ground a later series chapter on earlier ones (no-op when series_id empty).
    from app.features.render.engine.pipeline.story_series_memory import build_prior_context
    _sid = (req.series_id or "")
    _cno = int(req.chapter_no or 0)
    prior_context = build_prior_context(_sid, before_chapter=(_cno or None))

    plan = generate_story_plan_v2(
        provider=provider, source=source, chapter=chapter, idea=idea,
        duration_sec=int(req.duration_sec or 0), genre=(req.genre or ""),
        language=(req.language or "vi"), art_style=(req.art_style or ""),
        aspect_ratio=(req.aspect_ratio or "16:9"),
        subtitle_mode=(req.subtitle_mode or "hook_only"), ceiling=req.ceiling,
        series_id=_sid, chapter_no=_cno, prior_context=prior_context,
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
    # G6: environment reference sheets are generated only for a SERIES (one per distinct
    # setting) AND only when opted in — mirror the render-time gate so the estimate is
    # honest (STORY_ENV_REFERENCE_SHEETS defaults off).
    _env_on = _sid.strip() and _os.getenv("STORY_ENV_REFERENCE_SHEETS", "0") == "1"
    _envsheet_count = len({(v.setting_id or "").strip() for v in plan.visuals
                           if (v.setting_id or "").strip()}) if _env_on else 0
    _visual_count = plan.image_count()
    # Source-truncation transparency: the super-prompt fits the chapter to
    # MAX_SOURCE_CHARS (idea path to 8000) — surface when we cut so the FE can warn
    # the user to split a very long chapter instead of silently dropping the tail.
    from app.features.render.ai.llm.story_prompts_v2 import MAX_SOURCE_CHARS
    _IDEA_MAX = 8000
    _src_len = len(chapter) if source == "paste" else len(idea)
    _src_limit = MAX_SOURCE_CHARS if source == "paste" else _IDEA_MAX
    return {
        "plan": json.loads(plan.to_json()),
        "image_count": _visual_count,
        "beat_count": plan.beat_count(),
        "estimated_total_sec": round(plan.estimated_total_sec(), 1),
        "character_count": len(plan.characters),
        "source_truncated": bool(_src_len > _src_limit),
        "source_chars": _src_len,
        "source_char_limit": _src_limit,
        "cost_preflight": {
            "visual_count": _visual_count,
            "character_count": len(plan.characters),
            "reference_sheet_count": _refsheet_count,
            "environment_sheet_count": _envsheet_count,
            "premium_image_count": _visual_count + _refsheet_count + _envsheet_count,
            # Character MASTERS are opt-in (user generates them in Review, one per
            # character) — reported separately so the estimate isn't blind to them,
            # but NOT folded into premium_image_count (which is the automatic render cost).
            "character_master_count": len(plan.characters),
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
    # True → generate a cutout-ready CHARACTER MASTER (transparent PNG) for overlay /
    # Review preview instead of the opaque conditioning reference sheet. Default False
    # keeps the legacy behaviour (Sacred Contract #2 spirit).
    transparent: bool = False


@router.post("/character/reference-sheet")
def character_reference_sheet(req: ReferenceSheetRequest) -> dict:
    """Generate a canonical Character Reference Sheet (gpt-image-1) and, when a
    series is given, PIN it on the character (characters.reference_image_path) so
    every later shot conditions generation on it. 422 without a description;
    502 when generation failed (no key / error — Sacred Contract #3)."""
    from app.domain.story_plan import StoryCharacter
    from app.features.render.engine.visual.story_reference_sheet import (
        generate_character_master,
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

    # transparent=True → cutout-ready overlay master (Phase 5): generate a PNG-alpha
    # master and expose a viewable URL so Review can show it on a checkerboard. It is
    # an OVERLAY asset, NOT the conditioning reference sheet → it is not pinned.
    if req.transparent:
        path = generate_character_master(character, art_style=(req.art_style or ""))
        if not path:
            raise HTTPException(status_code=502, detail="character master generation failed")
        url = ""
        try:
            import shutil
            _MASTER_DIR.mkdir(parents=True, exist_ok=True)
            token = uuid.uuid4().hex
            shutil.copyfile(path, _MASTER_DIR / f"{token}.png")
            url = f"/api/story/character/master/{token}"
        except Exception as exc:
            logger.warning("story: master preview copy failed: %s", exc)
        return {"path": path, "url": url}

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


@router.get("/character/master/{token}")
def character_master_image(token: str):
    """Stream a character-master preview png (transparent) by token. 404 on a
    malformed/expired token."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    p = _MASTER_DIR / f"{token}.png"
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="image/png")


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


# ── Phase 4: voice picker — available voices for the language's TTS engine ────

@router.get("/voices")
def story_voices(language: str = "vi") -> dict:
    """Return the available Story voices for a language's TTS engine, split by gender:
    ``{engine, female[], male[]}``. Lets the FE offer a per-character voice override
    (written into the plan's render.voices, preserved at render). Never raises."""
    from app.features.render.ai.llm.story_voice_cast import list_voices
    return list_voices(language or "vi")
