"""
Story Studio API — Story-to-Video v2 pre-render review endpoints.

The render itself goes through the shared render API (render_format="story"); this
router covers the review flow the FE Story Studio drives before render:

    POST /api/story/plan                      — ONE super call → StoryPlan v2
    POST /api/story/visual/svg-preview        — compose procedural SVG key-visual(s)
    POST /api/story/character/reference-sheet — transparent SVG character master
    POST /api/story/narration/preview         — one beat's narration to audio

Story Mode is SVG-only: all imagery is procedural (offline, $0). AI is used ONLY for
the super plan. All calls are defensive (Sacred Contract #3): a None/empty result
surfaces as a clean 4xx/502 — no unhandled raise reaches the client.
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
from app.db import story_repo, story_project_repo, story_asset_repo
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

    # Library-pick: give the Review plan the SAME asset-library catalog the render
    # pipeline injects (STORY_LIBRARY_PICK, scoped by genre group) so the AI can pick
    # `asset` slugs here too. Without this the reviewed/approved plan (rendered verbatim
    # via story_plan_override) carried no asset picks — library matching was bypassed
    # for the FE review flow. Empty catalog → prompt byte-identical (Sacred #2 rollback).
    library_catalog = ""
    if _os.getenv("STORY_LIBRARY_PICK", "1") == "1":
        try:
            from app.db import story_asset_repo
            from app.features.render.engine.pipeline.story_pipeline_v2 import _genre_group
            library_catalog = story_asset_repo.build_library_catalog(
                genres=_genre_group(req.genre or ""))
        except Exception:
            library_catalog = ""

    plan = generate_story_plan_v2(
        provider=provider, source=source, chapter=chapter, idea=idea,
        duration_sec=int(req.duration_sec or 0), genre=(req.genre or ""),
        language=(req.language or "vi"), art_style=(req.art_style or ""),
        aspect_ratio=(req.aspect_ratio or "16:9"),
        subtitle_mode=(req.subtitle_mode or "hook_only"), ceiling=req.ceiling,
        series_id=_sid, chapter_no=_cno, prior_context=prior_context,
        library_catalog=library_catalog,
        api_key=api_key, model=req.llm_model,
        resolve_key=lambda _p: _resolve_api_key(req, _p)[0],
    )
    if plan is None or plan.is_empty() or plan.image_count() == 0:
        raise HTTPException(status_code=502, detail="Story planning returned no usable plan")

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
        # Story Mode is SVG-only → all imagery is procedural + offline ($0).
        "cost_preflight": {
            "visual_count": _visual_count,
            "character_count": len(plan.characters),
            "premium_image_count": 0,
            "estimated_cost_usd": 0.0,
        },
    }


# ── SVG key-visual preview (Storyboard review — WYSIWYG, offline $0) ──────────

class SvgPreviewRequest(BaseModel):
    plan: dict = Field(default_factory=dict, description="The StoryPlan v2 being reviewed")
    visual_ids: list = Field(default_factory=list, description="Subset to compose ([] = all)")


@router.post("/visual/svg-preview")
def svg_visual_preview(req: SvgPreviewRequest) -> dict:
    """Compose the procedural SVG key-visual(s) for a StoryPlan so the FE Review shows
    exactly what the render will produce (WYSIWYG, offline, $0). Returns
    ``{items: [{visual_id, token, url}]}`` for every visual that composed. 422 on an
    empty/invalid plan; 502 when the SVG rasteriser is unavailable (resvg-py). Composes
    with characters placed so the reviewer sees who is in each scene (the render itself
    overlays the speaker per-beat). Never raises past a clean HTTP error."""
    from app.domain.story_plan_v2 import StoryPlan, ASPECT_SIZE
    from app.features.render.engine.visual import svg_raster
    from app.features.render.engine.visual.svg_compose import compose_visual

    try:
        plan = StoryPlan.from_json(json.dumps(req.plan or {}, ensure_ascii=False))
    except Exception:
        plan = None
    if plan is None or not plan.visuals:
        raise HTTPException(status_code=422, detail="a StoryPlan with visuals is required")
    if not svg_raster.available():
        raise HTTPException(status_code=502, detail="SVG rasteriser unavailable (install resvg-py)")
    w, h = ASPECT_SIZE.get((plan.aspect_ratio or "16:9"), ASPECT_SIZE["16:9"])
    wanted = {str(v) for v in (req.visual_ids or []) if v}
    _VISUAL_DIR.mkdir(parents=True, exist_ok=True)
    items: list = []
    for v in plan.visuals:
        if wanted and v.id not in wanted:
            continue
        try:
            svg = compose_visual(plan, v, w, h, chars=True)
            if not svg:
                continue
            token = uuid.uuid4().hex
            out = _VISUAL_DIR / f"{token}.png"
            if svg_raster.save_svg_png(svg, str(out), w, h, opaque_bg="#101820"):
                items.append({"visual_id": v.id, "token": token,
                              "url": f"/api/story/visual/image/{token}"})
        except Exception as exc:
            logger.info("story svg-preview: visual %s failed: %s", v.id, exc)
    return {"items": items}


@router.get("/visual/image/{token}")
def visual_image(token: str):
    """Stream a key-visual preview png by token. 404 on a malformed/expired token."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    p = _VISUAL_DIR / f"{token}.png"
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="image/png")


# ── Character master (transparent SVG chibi — Review preview + overlay asset) ─

class CharacterMasterRequest(BaseModel):
    character_id: str = ""
    name: str = ""
    description: str = ""       # kept for FE compatibility (unused by the SVG builder)
    archetype: str = ""        # drives the chibi look (e.g. "swordsman")
    gender: str = ""
    region: str = ""
    genre: str = ""
    art_style: str = ""        # accepted for compatibility (the chibi style is fixed)
    # 0 = canonical stand pose; >0 rotates the pose so "regenerate" yields a different look.
    variant: int = 0


@router.post("/character/reference-sheet")
def character_master(req: CharacterMasterRequest) -> dict:
    """Compose a cutout-ready transparent CHARACTER MASTER (procedural SVG chibi, offline
    $0) for the Review character panel — the SAME asset the render overlays. Returns
    ``{path, url}``. 422 without any character signal; 502 on compose failure / resvg-py
    unavailable (Sacred Contract #3)."""
    from types import SimpleNamespace
    from app.features.render.engine.visual.story_reference_sheet import generate_character_master

    name = (req.name or "").strip()
    arch = (req.archetype or "").strip()
    cid = (req.character_id or "").strip()
    if not (name or arch or cid):
        raise HTTPException(status_code=422, detail="a character (name/archetype) is required")
    character = SimpleNamespace(id=(cid or name), name=name, archetype=arch,
                                gender=(req.gender or ""))
    path = generate_character_master(
        character, art_style=(req.art_style or ""), variant=int(req.variant or 0),
        region=(req.region or ""), genre=(req.genre or ""))
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


# ── SP1: Story project persistence (save / list / open / delete) ──────────────

class StoryProjectSaveRequest(BaseModel):
    id: str = ""                       # "" → create a new project
    name: str = ""
    language: str = ""
    source: str = ""                   # paste | idea
    config: dict = Field(default_factory=dict)   # the FE StoryConfig
    plan: Optional[dict] = None         # the edited StoryPlan v2 (None → not planned yet)
    status: str = "draft"              # draft | ready


@router.post("/projects")
def save_story_project(req: StoryProjectSaveRequest) -> dict:
    """Create (id="") or update a Story project (config + edited plan). Powers the FE
    autosave + manual Save. Returns ``{id}``. Never persists render state — this is a
    pre-render authoring store only."""
    pid = (req.id or "").strip() or uuid.uuid4().hex
    ok = story_project_repo.upsert_project(
        pid, name=(req.name or ""), language=(req.language or ""),
        source=(req.source or ""),
        config_json=json.dumps(req.config or {}, ensure_ascii=False),
        plan_json=(json.dumps(req.plan, ensure_ascii=False) if req.plan else ""),
        status=(req.status or "draft"),
    )
    if not ok:
        raise HTTPException(status_code=500, detail="failed to save project")
    return {"id": pid}


@router.get("/projects")
def list_story_projects() -> dict:
    """List recent LIVE Story projects (newest first, without the heavy config/plan blobs)."""
    return {"projects": story_project_repo.list_projects()}


@router.get("/projects/trash")
def list_trashed_story_projects() -> dict:
    """List soft-deleted (trashed) Story projects. Defined BEFORE /projects/{id} so
    'trash' is never captured as a project id."""
    return {"projects": story_project_repo.list_trashed_projects()}


@router.get("/projects/{project_id}")
def get_story_project(project_id: str) -> dict:
    """Return one project with ``config`` + ``plan`` parsed back to objects. 404 missing."""
    row = story_project_repo.get_project(project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    try:
        row["config"] = json.loads(row.get("config_json") or "") if row.get("config_json") else {}
    except Exception:
        row["config"] = {}
    try:
        row["plan"] = json.loads(row.get("plan_json") or "") if row.get("plan_json") else None
    except Exception:
        row["plan"] = None
    row.pop("config_json", None)
    row.pop("plan_json", None)
    return row


@router.delete("/projects/{project_id}")
def delete_story_project(project_id: str) -> dict:
    """SOFT-delete a Story project (move to trash). Idempotent — always reports success.
    Restore via /projects/{id}/restore; hard-remove via /projects/{id}/purge."""
    story_project_repo.delete_project(project_id)
    return {"deleted": True, "id": project_id}


@router.post("/projects/{project_id}/restore")
def restore_story_project(project_id: str) -> dict:
    """Restore a trashed Story project (clear deleted_at)."""
    story_project_repo.restore_project(project_id)
    return {"restored": True, "id": project_id}


@router.delete("/projects/{project_id}/purge")
def purge_story_project(project_id: str) -> dict:
    """HARD-delete a Story project + all its versions (empty-trash). Irreversible."""
    story_project_repo.purge_project(project_id)
    return {"purged": True, "id": project_id}


# ── SP3+: project version history (snapshot / list / restore) ─────────────────

class SaveVersionRequest(BaseModel):
    label: str = ""


@router.post("/projects/{project_id}/versions")
def snapshot_story_project_version(project_id: str, req: SaveVersionRequest) -> dict:
    """Snapshot the project's CURRENT stored plan+config as a version. 404 when the
    project doesn't exist. Returns ``{version_id}``."""
    row = story_project_repo.get_project(project_id)
    if row is None:
        raise HTTPException(status_code=404, detail="project not found")
    vid = story_project_repo.save_version(
        project_id, label=(req.label or ""),
        plan_json=(row.get("plan_json") or ""), config_json=(row.get("config_json") or ""),
    )
    if not vid:
        raise HTTPException(status_code=500, detail="failed to snapshot version")
    return {"version_id": vid}


@router.get("/projects/{project_id}/versions")
def list_story_project_versions(project_id: str) -> dict:
    """List a project's version snapshots (newest first, without the heavy blobs)."""
    return {"versions": story_project_repo.list_versions(project_id)}


@router.post("/projects/{project_id}/restore-version/{version_id}")
def restore_story_project_version(project_id: str, version_id: str) -> dict:
    """Restore a version's plan+config back INTO the project (overwrites current) and
    return the restored ``{config, plan}`` for the FE to reload. 404 on a missing version."""
    ver = story_project_repo.get_version(version_id)
    if ver is None or (ver.get("project_id") or "") != project_id:
        raise HTTPException(status_code=404, detail="version not found")
    proj = story_project_repo.get_project(project_id) or {}
    story_project_repo.upsert_project(
        project_id, name=(proj.get("name") or ""), language=(proj.get("language") or ""),
        source=(proj.get("source") or ""),
        config_json=(ver.get("config_json") or ""), plan_json=(ver.get("plan_json") or ""),
        status=(proj.get("status") or "draft"),
    )
    try:
        config = json.loads(ver.get("config_json") or "") if ver.get("config_json") else {}
    except Exception:
        config = {}
    try:
        plan = json.loads(ver.get("plan_json") or "") if ver.get("plan_json") else None
    except Exception:
        plan = None
    return {"restored": True, "config": config, "plan": plan}


# ── AL2: offline asset library (list / get / thumb / scan / delete) ───────────

@router.get("/assets")
def list_story_assets(kind: str = "", region: str = "", genre: str = "", q: str = "") -> dict:
    """List indexed library assets, filtered by kind/region/genre + free-text q."""
    return {"assets": story_asset_repo.list_assets(kind=kind, region=region, genre=genre, q=q)}


@router.post("/assets/scan")
def scan_story_assets() -> dict:
    """(Re)index the asset library folder → story_assets. Returns {indexed, pruned, root}."""
    return story_asset_repo.scan_library()


@router.get("/assets/{asset_id}")
def get_story_asset(asset_id: str) -> dict:
    """Return one asset's metadata. 404 when missing."""
    row = story_asset_repo.get_asset(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    return row


@router.get("/assets/{asset_id}/image")
def get_story_asset_image(asset_id: str):
    """Stream the asset's image file. 404 when the asset / file is missing."""
    row = story_asset_repo.get_asset(asset_id)
    if row is None:
        raise HTTPException(status_code=404, detail="asset not found")
    p = Path(row.get("path") or "")
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="asset file not found")
    _media = "image/webp" if p.suffix.lower() == ".webp" else "image/png"
    return FileResponse(str(p), media_type=_media)


@router.delete("/assets/{asset_id}")
def delete_story_asset(asset_id: str) -> dict:
    """Remove an asset's DB row (does NOT delete the file on disk). Idempotent."""
    story_asset_repo.delete_asset(asset_id)
    return {"deleted": True, "id": asset_id}
