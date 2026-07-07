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
import os
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


# ── CM-1: preview cost / abuse guard ─────────────────────────────────────────
# The /visual/preview + /narration/preview endpoints are unauthenticated
# (loopback) and a visual preview can trigger a PAID provider call (Imagen/Veo)
# — one paid asset per click, previously with no rate limit or spend cap. Two
# guards, both per-process + in-memory (this is a single-user desktop backend):
#   1. a token-bucket rate limit SHARED by both endpoints (abuse / runaway loops)
#   2. a per-CALENDAR-DAY cap on PAID visual previews (accidental large spend)
# Plus a hard off-switch (CONTENT_PREVIEW_PAID_DISABLED) for locked-down installs.
# Defaults are deliberately generous so the normal Review flow (explicit,
# warned per-click in the FE) is never impeded; the guards only catch abuse.
import threading as _threading  # noqa: E402
import time as _time  # noqa: E402
from datetime import date as _date  # noqa: E402

# A resolved asset whose provider is one of these actually cost money.
_PAID_VISUAL_PROVIDERS = {"ai_image", "ai_video"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return default


# 0 disables the corresponding guard. Read once at import (env is process-static).
_PREVIEW_RATE_PER_MIN = _env_int("CONTENT_PREVIEW_RATE_PER_MIN", 20)
_PREVIEW_DAILY_CAP = _env_int("CONTENT_PREVIEW_DAILY_CAP", 0)  # 0 = unlimited
_PREVIEW_PAID_DISABLED = (os.getenv("CONTENT_PREVIEW_PAID_DISABLED", "0") or "0").strip() == "1"


class _PreviewGuard:
    """Per-process rate limit (shared, per-minute) + paid-preview daily cap.
    Thread-safe (endpoints run in FastAPI's sync threadpool). Never raises."""

    def __init__(self) -> None:
        self._lock = _threading.Lock()
        self._window_start = 0.0
        self._count = 0
        self._paid_day: Optional[str] = None
        self._paid_count = 0

    def allow_call(self) -> bool:
        """True if under the per-minute limit; records the call. 0 = unlimited."""
        if _PREVIEW_RATE_PER_MIN <= 0:
            return True
        now = _time.monotonic()
        with self._lock:
            if now - self._window_start >= 60.0:
                self._window_start = now
                self._count = 0
            if self._count >= _PREVIEW_RATE_PER_MIN:
                return False
            self._count += 1
            return True

    def paid_would_exceed(self) -> bool:
        """True if today's paid-preview count is already at the daily cap."""
        if _PREVIEW_DAILY_CAP <= 0:
            return False
        today = _date.today().isoformat()
        with self._lock:
            if self._paid_day != today:
                self._paid_day, self._paid_count = today, 0
            return self._paid_count >= _PREVIEW_DAILY_CAP

    def record_paid(self) -> None:
        """Count one paid preview that actually produced a paid asset."""
        today = _date.today().isoformat()
        with self._lock:
            if self._paid_day != today:
                self._paid_day, self._paid_count = today, 0
            self._paid_count += 1


_preview_guard = _PreviewGuard()


def _metric_preview(endpoint: str, provider: str, outcome: str) -> None:
    """Emit content_preview_total. Best-effort — never breaks a request."""
    try:
        from app.services.metrics import CONTENT_PREVIEW_TOTAL
        CONTENT_PREVIEW_TOTAL.labels(
            endpoint=endpoint, provider=(provider or "?"), outcome=outcome,
        ).inc()
    except Exception:
        pass


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
    # Deterministic duration fit so the Review screen shows (and lets the user
    # edit) the plan that will actually be rendered. Same env kill-switch as the
    # render path (content_pipeline). Best-effort — never fails the request.
    _fit = None
    if os.getenv("CONTENT_FIT_DURATION", "1") == "1":
        try:
            _f = plan.fit_to_target_duration(float(req.target_duration or 0))
            if _f.get("changed"):
                _fit = _f
        except Exception:
            _fit = None
    _audit = None
    try:
        _a = plan.narration_audit()
        if _a.get("rated"):
            _audit = _a
    except Exception:
        _audit = None
    return {"plan": json.loads(plan.to_json()), "duration_fit": _fit, "narration_audit": _audit}


class ContentEstimateRequest(BaseModel):
    plan: Optional[dict] = None          # an already-generated ContentPlan
    script: str = ""                     # or a raw script to plan-then-estimate
    target_duration: int = 90
    voice_language: str = "vi-VN"
    tone: str = ""
    visual_provider: str = "local"       # job-level content_visual_provider
    budget_cap: float = 0.0              # CONTENT_AI_BUDGET-equivalent (0 = unlimited)
    ai_provider: Optional[str] = None
    llm_model: Optional[str] = None


@router.post("/estimate")
def estimate_content_cost(req: ContentEstimateRequest) -> dict:
    """Preflight AI cost/provider estimate BEFORE rendering (Content uses paid
    visual providers). Runs the SAME deterministic decision tree + budget guard
    the render uses (``decide_provider`` / ``BudgetTracker``) read-only over the
    plan — no render, no paid API call. Accepts an existing ``plan`` or a
    ``script`` (planned first). Returns per-scene provider choices + estimated
    paid cost. 422 when neither plan nor script is usable."""
    from app.domain.content_plan import ContentPlan
    from app.features.render.engine.visual.decision import (
        BudgetTracker, decide_provider, estimate_cost,
    )

    plan = ContentPlan.from_json(json.dumps(req.plan)) if req.plan else None
    if plan is None or plan.scene_count() == 0:
        script = (req.script or "").strip()
        if not script:
            raise HTTPException(status_code=422, detail="plan or script is required")
        from app.core import config as _cfg
        from app.features.render.engine.pipeline.llm_stage import _resolve_api_key
        provider = (req.ai_provider or "").strip().lower() or getattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini")
        api_key, _ = _resolve_api_key(req, provider)
        plan = select_content_plan(
            provider=provider, script=script,
            target_duration_sec=float(req.target_duration or 90),
            target_language=(req.voice_language or "vi-VN"), tone=(req.tone or ""),
            api_key=api_key, model=req.llm_model,
            resolve_key=lambda _p: _resolve_api_key(req, _p)[0],
        )
    if plan is None or plan.scene_count() == 0:
        raise HTTPException(status_code=502, detail="no usable plan to estimate")

    budget = BudgetTracker(float(req.budget_cap or 0))
    per_scene: list[dict] = []
    for i, s in enumerate(plan.scenes, start=1):
        prov = decide_provider(
            s, req.visual_provider, budget,
            float(getattr(s, "est_duration_sec", 0.0) or 0.0),
        )
        per_scene.append({"scene": i, "provider": prov, "cost": round(estimate_cost(prov), 3)})
    by_provider: dict[str, int] = {}
    for e in per_scene:
        by_provider[e["provider"]] = by_provider.get(e["provider"], 0) + 1
    return {
        "estimated_cost": round(budget.spent, 3),
        "budget_cap": budget.cap,
        "scenes": plan.scene_count(),
        "by_provider": by_provider,
        "per_scene": per_scene,
        "estimated_duration_sec": round(plan.estimated_total_sec(), 1),
        "narration_audit": plan.narration_audit(),
    }


# ── P3.1: visual-provider availability (which sources are usable right now) ──

@router.get("/visual-providers")
def visual_providers() -> dict:
    """Report which Content visual providers are usable right now, from the API
    keys present in the environment. Read-only — never triggers a paid call.

    The FE uses this to label each source "free / ready / needs key" and to
    auto-select the free stock provider when a key is configured. ``local`` is
    always available; ``stock`` is free (Pexels/Pixabay); ``ai_image`` / ``ai_video``
    are paid. Mirrors the key checks the providers themselves make. Never raises."""
    def _has(*names: str) -> bool:
        return any((os.getenv(n) or "").strip() for n in names)
    return {
        "providers": {
            "local":         {"available": True, "free": True},
            "stock":         {"available": _has("PEXELS_API_KEY", "PIXABAY_API_KEY"), "free": True},
            # Pollinations — free AI image, no key needed → always available.
            "ai_image_free": {"available": True, "free": True},
            "ai_image":      {"available": _has("GEMINI_API_KEY", "GEMINI_API_KEYS", "OPENAI_API_KEY"), "free": False},
            "ai_video":      {"available": _has("GEMINI_API_KEY", "GOOGLE_API_KEY"), "free": False},
        }
    }


# ── C1: per-scene visual preview (Review) ────────────────────────────────────

_VISUAL_PREVIEW_DIR = CACHE_DIR / "content_visual_preview"
_IMG_EXT_MEDIA = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


class VisualPreviewRequest(BaseModel):
    prompt: str = Field(default="", description="The scene's visual_prompt")
    provider: str = "ai_image_free"      # stock | ai_image | ai_video | ai_image_free | local
    aspect_ratio: str = "9:16"
    seed: int = 0
    style: str = ""
    negative_prompt: str = ""
    imagen_tier: str = ""


@router.post("/visual/preview")
def visual_preview(req: VisualPreviewRequest) -> dict:
    """Resolve ONE scene's visual via the SAME seam the render uses (incl. the B2
    stepped fallback) and return a previewable image. Runs the user's chosen
    provider — free for stock/Pollinations; a paid provider (Imagen) costs one
    image per call. Returns ``{kind:"image", provider, token, url}`` for an image,
    or ``{kind, provider, value}`` when it fell back to a colour/video background
    (no still to show). 422 empty prompt."""
    prompt = (req.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="prompt is required")

    # CM-1: cost / abuse guard (rate limit + paid-preview daily cap + off-switch).
    _prov = (req.provider or "ai_image_free").strip().lower()
    _is_paid = _prov in _PAID_VISUAL_PROVIDERS
    if not _preview_guard.allow_call():
        _metric_preview("visual", _prov, "rate_limited")
        raise HTTPException(status_code=429, detail="preview rate limit exceeded — slow down")
    if _is_paid and _PREVIEW_PAID_DISABLED:
        _metric_preview("visual", _prov, "paid_disabled")
        raise HTTPException(
            status_code=403,
            detail="paid visual preview is disabled — use a free source (stock / ai_image_free)",
        )
    if _is_paid and _preview_guard.paid_would_exceed():
        _metric_preview("visual", _prov, "budget_capped")
        raise HTTPException(
            status_code=429,
            detail="daily paid-preview cap reached — try a free source or raise CONTENT_PREVIEW_DAILY_CAP",
        )

    from app.features.render.engine.visual import SceneVisualRequest, resolve_scene_visual
    from app.features.render.engine.encoder.ffmpeg_helpers import resolve_target_dimensions

    w, h = resolve_target_dimensions(req.aspect_ratio or "9:16")
    _VISUAL_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    asset = resolve_scene_visual(
        SceneVisualRequest(
            scene_index=0, kind="color", value="#101820", prompt=prompt,
            negative_prompt=(req.negative_prompt or ""), style=(req.style or ""),
            seed=int(req.seed or 0), width=w, height=h, fps=30.0, duration_sec=3.0,
            work_dir=str(_VISUAL_PREVIEW_DIR), imagen_tier=(req.imagen_tier or ""),
        ),
        provider=(req.provider or "ai_image_free"),
    )
    if asset is None:
        _metric_preview("visual", _prov, "failed")
        raise HTTPException(status_code=502, detail="visual generation failed")
    # Count spend only when a PAID provider actually produced the asset — a silent
    # fallback to local (no key / error) yields provider="local" and costs nothing.
    if (asset.provider or "").strip().lower() in _PAID_VISUAL_PROVIDERS:
        _preview_guard.record_paid()
    _metric_preview("visual", (asset.provider or _prov), "ok")
    if asset.kind == "image" and asset.value and Path(asset.value).exists():
        token = uuid.uuid4().hex
        ext = Path(asset.value).suffix.lower()
        if ext not in _IMG_EXT_MEDIA:
            ext = ".jpg"
        dst = _VISUAL_PREVIEW_DIR / f"{token}{ext}"
        try:
            import shutil as _sh
            _sh.copyfile(asset.value, dst)
        except Exception as exc:
            logger.warning("content visual preview: copy failed %s", exc)
            raise HTTPException(status_code=502, detail="preview copy failed")
        return {"kind": "image", "provider": asset.provider, "token": token,
                "url": f"/api/content/visual/image/{token}"}
    # Fell back to a colour/video background — no still image to preview.
    return {"kind": asset.kind, "provider": asset.provider, "value": asset.value}


@router.get("/visual/image/{token}")
def visual_image(token: str):
    """Serve a visual-preview image by token. 404 on a malformed token or a
    missing/expired file (the cache prune may have reclaimed it)."""
    if not _TOKEN_RE.match(token or ""):
        raise HTTPException(status_code=404, detail="not found")
    for ext, media in _IMG_EXT_MEDIA.items():
        p = _VISUAL_PREVIEW_DIR / f"{token}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return FileResponse(str(p), media_type=media)
    raise HTTPException(status_code=404, detail="not found")


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

    # CM-1: shared rate limit (abuse / runaway loops). TTS is normally free/edge,
    # so no paid cap here — the rate limit alone bounds any online-TTS spend.
    _engine = (req.tts_engine or "edge").strip().lower()
    if not _preview_guard.allow_call():
        _metric_preview("narration", _engine, "rate_limited")
        raise HTTPException(status_code=429, detail="preview rate limit exceeded — slow down")

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
        _metric_preview("narration", _engine, "failed")
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
        _metric_preview("narration", _engine, "failed")
        raise HTTPException(status_code=502, detail="TTS produced no audio")

    _metric_preview("narration", _engine, "ok")
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
