"""
Content Studio API (CS-A) — planning endpoint.

The mandatory Review workflow needs a ContentPlan BEFORE rendering, so this
router exposes a plan-only step:

    POST /api/content/plan   {script, target_duration, voice_language, tone, …}
        → {"plan": <ContentPlan dict>}   (no render)

The FE Review screen then lets the user edit that plan and submit it to the
SHARED render pipeline via /api/render/process with
``render_format="content"`` + ``content_plan_override=<edited plan JSON>`` —
run_content renders FROM the approved plan and skips the AI call.

Later CS phases add narration-preview + asset endpoints to this same router.
Sacred Contract #3: select_content_plan already returns None on any failure;
here that surfaces as a clean 502 (no unhandled raise reaches the client).
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
from app.db.content_repo import (
    delete_content_project,
    get_content_project,
    list_content_projects,
    upsert_content_project,
)
from app.features.render.ai.llm import select_content_plan, generate_publish_meta

logger = logging.getLogger("app.content.api")

router = APIRouter(prefix="/api/content", tags=["content"])

# Per-scene narration PREVIEW audio (CS-D) lives under the cache root so the
# periodic subdir-agnostic cache prune reclaims it. Files are keyed by an opaque
# 32-hex token (uuid4) — the audio GET validates the token shape to block any
# path traversal.
_PREVIEW_DIR = CACHE_DIR / "content_preview"
_TOKEN_RE = re.compile(r"^[a-f0-9]{32}$")


class ContentPlanRequest(BaseModel):
    script: str = Field(default="", description="Raw script / article / news text")
    target_duration: int = 90
    voice_language: str = "vi-VN"
    tone: str = ""
    ai_provider: Optional[str] = None
    llm_model: Optional[str] = None


@router.post("/plan")
def generate_content_plan(req: ContentPlanRequest) -> dict:
    """Generate a ContentPlan from a script WITHOUT rendering (the Review step).

    Synchronous — a single AI Director call. Returns ``{"plan": <ContentPlan
    dict>}``. 422 when the script is empty; 502 when the AI produced no usable
    plan (e.g. missing API key / provider error — select_content_plan returned
    None per Sacred Contract #3)."""
    script = (req.script or "").strip()
    if not script:
        raise HTTPException(status_code=422, detail="script is required")

    from app.core import config as _cfg
    from app.features.render.engine.pipeline.llm_stage import _resolve_api_key

    provider = (req.ai_provider or "").strip().lower() or getattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini")
    api_key, _ = _resolve_api_key(req, provider)
    plan = select_content_plan(
        provider=provider,
        script=script,
        target_duration_sec=float(req.target_duration or 90),
        target_language=(req.voice_language or "vi-VN"),
        tone=(req.tone or ""),
        api_key=api_key,
        model=req.llm_model,
        # LOW-1: correct key per provider on cross-provider fallback.
        resolve_key=lambda _prov: _resolve_api_key(req, _prov)[0],
    )
    if plan is None or plan.scene_count() == 0:
        raise HTTPException(status_code=502, detail="AI Content Director returned no usable plan")
    return {"plan": json.loads(plan.to_json())}


# ── CS-D: per-scene narration preview / regenerate ───────────────────────────

class NarrationPreviewRequest(BaseModel):
    text: str = Field(default="", description="The scene narration to voice")
    voice_language: str = "vi-VN"
    voice_gender: str = "female"
    tts_engine: str = "edge"
    reading_speed: float = 1.0


@router.post("/narration/preview")
def narration_preview(req: NarrationPreviewRequest) -> dict:
    """Synthesize ONE scene's narration to previewable audio (the Review step's
    per-scene Preview / Regenerate). Returns ``{token, url, duration_sec}``; the
    audio is fetched from GET /api/content/narration/audio/{token}. 422 empty
    text; 502 when TTS produced nothing (Sacred Contract #3 — no unhandled raise
    reaches the client)."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="text is required")

    from app.features.render.engine.audio.tts import generate_narration_audio
    from app.features.render.engine.stages.content_scene_render import (
        _reading_speed_to_rate, probe_audio_duration,
    )

    _PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    out = _PREVIEW_DIR / f"{token}.mp3"
    try:
        path = generate_narration_audio(
            text=text, language=req.voice_language, gender=req.voice_gender,
            rate=_reading_speed_to_rate(req.reading_speed),
            job_id=f"content-preview-{token}", output_path=str(out),
            content_type="vlog", tts_engine=req.tts_engine,
        )
    except Exception as exc:
        logger.warning("content narration preview: TTS raised %s", exc)
        raise HTTPException(status_code=502, detail="TTS failed")

    # generate_narration_audio returns the written path; normalise to `out` so the
    # audio GET (keyed by token) always finds it.
    final = Path(path) if path else out
    if final != out and final.exists():
        try:
            import shutil
            shutil.move(str(final), str(out))
        except Exception:
            out = final  # serve wherever it landed (still under the preview dir)
    if not out.exists() or out.stat().st_size <= 0:
        raise HTTPException(status_code=502, detail="TTS produced no audio")

    return {
        "token": token,
        "url": f"/api/content/narration/audio/{token}",
        "duration_sec": probe_audio_duration(str(out)),
    }


@router.get("/narration/audio/{token}")
def narration_audio(token: str):
    """Stream a narration-preview mp3 by token. 404 on a malformed token or a
    missing/expired file (the cache prune may have reclaimed it)."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    p = _PREVIEW_DIR / f"{token}.mp3"
    if not p.exists() or p.stat().st_size <= 0:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(p), media_type="audio/mpeg")


# ── CU-1: Content Studio project (draft) persistence ─────────────────────────

class ContentProjectPayload(BaseModel):
    title: str = ""
    script: str = ""
    plan: Optional[dict] = None       # the (editable) ContentPlan
    config: Optional[dict] = None     # studio config (aspect/voice/bg/...)
    status: str = "draft"             # draft | rendered
    last_job_id: str = ""


def _project_out(p: dict) -> dict:
    """Parse the stored JSON columns back into objects for the FE."""
    def _load(s):
        try:
            return json.loads(s) if s else None
        except Exception:
            return None
    return {
        "id": p.get("id"), "title": p.get("title", ""), "script": p.get("script", ""),
        "plan": _load(p.get("plan_json")), "config": _load(p.get("config_json")),
        "status": p.get("status", "draft"), "last_job_id": p.get("last_job_id", ""),
        "created_at": p.get("created_at"), "updated_at": p.get("updated_at"),
    }


def _project_summary(p: dict) -> dict:
    """Lightweight list entry — no full plan/config payload."""
    plan = None
    try:
        plan = json.loads(p.get("plan_json")) if p.get("plan_json") else None
    except Exception:
        plan = None
    scenes = len((plan or {}).get("scenes") or []) if isinstance(plan, dict) else 0
    return {
        "id": p.get("id"), "title": p.get("title", ""),
        "topic": (plan or {}).get("topic", "") if isinstance(plan, dict) else "",
        "scenes": scenes, "status": p.get("status", "draft"),
        "updated_at": p.get("updated_at"),
    }


def _save(project_id: str, body: ContentProjectPayload) -> bool:
    return upsert_content_project(
        project_id, title=body.title, script=body.script,
        plan_json=(json.dumps(body.plan, ensure_ascii=False) if body.plan is not None else None),
        config_json=(json.dumps(body.config, ensure_ascii=False) if body.config is not None else None),
        status=(body.status or "draft"), last_job_id=(body.last_job_id or ""),
    )


@router.post("/projects")
def create_project(body: ContentProjectPayload) -> dict:
    pid = uuid.uuid4().hex
    if not _save(pid, body):
        raise HTTPException(status_code=500, detail="failed to save project")
    return {"id": pid}


@router.put("/projects/{project_id}")
def save_project(project_id: str, body: ContentProjectPayload) -> dict:
    """Autosave / update a project (idempotent upsert by id)."""
    if not _save(project_id, body):
        raise HTTPException(status_code=500, detail="failed to save project")
    return {"id": project_id, "ok": True}


@router.get("/projects")
def list_projects(limit: int = 50) -> dict:
    return {"projects": [_project_summary(p) for p in list_content_projects(limit)]}


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict:
    p = get_content_project(project_id)
    if p is None:
        raise HTTPException(status_code=404, detail="not found")
    return _project_out(p)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict:
    delete_content_project(project_id)
    return {"ok": True}


# ── CU-14: publish intelligence ──────────────────────────────────────────────

class PublishMetaRequest(BaseModel):
    topic: str = ""
    tone: str = ""
    audience: str = ""
    voice_language: str = "vi-VN"
    narration_sample: str = ""
    ai_provider: Optional[str] = None
    llm_model: Optional[str] = None


@router.post("/publish-meta")
def publish_meta(req: PublishMetaRequest) -> dict:
    """Generate SEO publish metadata (title/description/tags/thumbnail) from the
    finished plan. 422 empty input; 502 when the AI produced nothing."""
    if not (req.topic or req.narration_sample or "").strip():
        raise HTTPException(status_code=422, detail="topic or narration_sample is required")
    from app.core import config as _cfg
    from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
    provider = (req.ai_provider or "").strip().lower() or getattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini")
    api_key, _ = _resolve_api_key(req, provider)
    meta = generate_publish_meta(
        provider=provider, topic=req.topic, tone=req.tone, audience=req.audience,
        target_language=(req.voice_language or "vi-VN"), narration_sample=req.narration_sample,
        api_key=api_key, model=req.llm_model,
        resolve_key=lambda _p: _resolve_api_key(req, _p)[0],
    )
    if meta is None:
        raise HTTPException(status_code=502, detail="publish metadata generation failed")
    return {"meta": meta}
