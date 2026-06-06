
import json
import os
import re
import shutil
import threading
import time
import traceback
import uuid
import logging
import subprocess

# Guards concurrent preview-transcript requests for the same session.
# Key = session_id, Value = threading.Lock held while Whisper is running.
_transcript_locks: dict[str, threading.Lock] = {}
_transcript_locks_mu = threading.Lock()
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from app.models.schemas import RenderRequest, PrepareSourceRequest, QuickProcessRequest
from app.services.db import upsert_job, get_job, list_job_parts, update_job_progress
from app.services.job_manager import submit_job, is_running
from app.services.channel_service import ensure_channel
from app.services.downloader import slugify
from app.core import config as _cfg
from app.core.config import TEMP_DIR, CHANNELS_DIR, REQUEST_LOG
from app.core.stage import JobStage
from app.services.bin_paths import get_ffprobe_bin, get_ffmpeg_bin
from app.features.render.engine.pipeline.render_pipeline import (
    run_render_pipeline,
    _emit_render_event,
    _probe_video_duration,
    _validate_text_layers_or_400,
    _append_json_line,
)
from app.features.render.engine.preview.ffmpeg_probers import (
    _probe_video_codec,
    _probe_preview_profile,
    _is_browser_safe_preview,
    _ensure_h264_preview,
    _run_ffmpeg_checked,
    _detect_leading_black_duration,
)
from app.features.render.engine.preview.session_service import (
    _PREVIEW_SESSIONS,
    _PREVIEW_DIR,
    _SESSION_TTL_HOURS,
    _MAX_PREVIEW_SESSIONS,
    _save_session,
    _load_session,
    _cleanup_preview_session,
    evict_stale_preview_sessions,  # re-exported: main.py imports this from app.routes.render
)
from app.features.render.engine.preview.media_streaming import (
    _parse_range_header,
    _iter_file_bytes,
)

router = APIRouter(prefix="/api/render", tags=["render"])
logger = logging.getLogger("app.render")


@router.get("/queue-status")
def get_queue_status():
    """Read-only — returns active render count and max concurrent slots."""
    from app.features.render.engine.pipeline.render_pipeline import _render_active_count, _render_active_lock, _JOB_SEM_VALUE
    with _render_active_lock:
        active = _render_active_count[0]
    return {"active_renders": active, "max_renders": _JOB_SEM_VALUE}


@router.get("/system-info")
def get_system_info():
    """Read-only system snapshot for the Settings screen.

    Returns cache sizes, job counts, and runtime config. Never mutates state.
    """
    from app.core.config import APP_DATA_DIR, DATABASE_PATH
    from app.services.db import list_jobs

    def _dir_size_mb(path: Path) -> float:
        try:
            total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            return round(total / 1_048_576, 1)
        except Exception:
            return 0.0

    def _file_size_mb(path: Path) -> float:
        try:
            return round(path.stat().st_size / 1_048_576, 1) if path.exists() else 0.0
        except Exception:
            return 0.0

    cache_dir = APP_DATA_DIR / "cache"
    cache_subdirs = {}
    if cache_dir.exists():
        for sub in cache_dir.iterdir():
            if sub.is_dir():
                cache_subdirs[sub.name] = _dir_size_mb(sub)

    try:
        jobs = list_jobs()
        total_jobs     = len(jobs)
        completed_jobs = sum(1 for j in jobs if j.get("status") in ("completed", "completed_with_errors"))
        failed_jobs    = sum(1 for j in jobs if j.get("status") == "failed")
        active_jobs    = sum(1 for j in jobs if j.get("status") in ("running", "queued", "cancelling"))
    except Exception:
        total_jobs = completed_jobs = failed_jobs = active_jobs = 0

    return {
        "cache": {
            "total_mb":   round(sum(cache_subdirs.values()), 1),
            "subdirs":    cache_subdirs,
            "cache_dir":  str(cache_dir),
        },
        "database": {
            "path":    str(DATABASE_PATH),
            "size_mb": _file_size_mb(DATABASE_PATH),
        },
        "jobs": {
            "total":     total_jobs,
            "completed": completed_jobs,
            "failed":    failed_jobs,
            "active":    active_jobs,
        },
    }


@router.post("/cache/clear")
def clear_render_cache():
    """Delete all files under APP_DATA_DIR/cache. Non-destructive to job records."""
    from app.core.config import APP_DATA_DIR
    cache_dir = APP_DATA_DIR / "cache"
    deleted = 0
    freed_mb = 0.0
    if cache_dir.exists():
        for f in cache_dir.rglob("*"):
            if f.is_file():
                try:
                    freed_mb += f.stat().st_size / 1_048_576
                    f.unlink()
                    deleted += 1
                except Exception:
                    pass
    return {"deleted_files": deleted, "freed_mb": round(freed_mb, 1)}


@router.get("/ai-diagnostics")
def get_ai_diagnostics():
    """Read-only AI runtime diagnostics.

    Returns dependency availability, embedding readiness, vector store mode,
    and SQLite memory health. Never loads models. Never triggers embeddings.
    """
    try:
        from app.ai.diagnostics import get_ai_runtime_diagnostics
        return get_ai_runtime_diagnostics()
    except Exception as exc:
        logger.debug("ai_diagnostics_endpoint_error: %s", exc)
        return {"startup_safe": True, "error": "diagnostics_unavailable"}


# ── Error classification ───────────────────────────────────────────────────────
# Type 1 · Request / validation errors  — HTTPException raised before process_render
#           logged as WARNING  →  desktop-backend.log  (via logger.warning)
#           NOT written to error.log (pipeline never starts)
# Type 2 · Render pipeline errors       — exception inside process_render
#           logged as ERROR   →  data/logs/error.log  (via _emit_render_event)
#                              +  channels/{code}/logs/{job_id}.log
#                              +  data/logs/app.log
# Type 3 · Unexpected / system errors   — unhandled exception in route function
#           logged as ERROR   →  desktop-backend.log  (FastAPI default handler)
#           NOT written to error.log
# ─────────────────────────────────────────────────────────────────────────────

_UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.IGNORECASE)


def _emit_request_event(
    *,
    route: str,
    status_code: int,
    detail: str,
    channel_code: str = "",
):
    """Write Type 1 (request/validation) errors to request.log as JSON-lines."""
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": "WARNING",
        "event": "render.request.rejected",
        "module": "render",
        "message": detail,
        "route": route,
        "status_code": status_code,
        "channel_code": channel_code,
    }
    _append_json_line(REQUEST_LOG, entry)


def _validate_output_dir(payload: RenderRequest):
    """Require output_dir to be non-empty."""
    if not (payload.output_dir or "").strip():
        raise HTTPException(status_code=400, detail="output_dir is required")


def _coerce_legacy_channel_payload(payload: RenderRequest) -> None:
    """Convert channel-mode payloads (from old clients/stored jobs) to manual mode in-place."""
    if (payload.output_mode or "").strip().lower() == "channel":
        logger.info(
            "Legacy channel mode payload detected — converting to manual (output_dir=%s channel=%s)",
            payload.output_dir or "",
            payload.channel_code or "",
        )
        payload.output_mode = "manual"



def _validate_render_source(payload: RenderRequest):
    output_mode = (payload.output_mode or "manual").strip().lower()
    if output_mode not in ("channel", "manual"):
        raise HTTPException(status_code=400, detail="output_mode must be 'channel' or 'manual'")

    # When an editor session is provided, the pipeline uses the session's video_path;
    # skip source-path validation entirely.
    if (getattr(payload, "edit_session_id", None) or "").strip():
        _validate_output_dir(payload)
        return

    mode = (payload.source_mode or "local").lower().strip()
    local = (payload.source_video_path or "").strip()

    # Render pipeline only accepts local files. Use the standalone Downloader
    # feature first to fetch a remote source as a local file, then submit here.
    if mode != "local":
        raise HTTPException(
            status_code=400,
            detail=(
                f"source_mode='{mode}' is not supported by /api/render/process. "
                "Use the standalone Downloader to fetch remote sources as local files."
            ),
        )

    if not local:
        raise HTTPException(status_code=400, detail="source_video_path is required when source_mode='local'")
    if not Path(local).exists():
        raise HTTPException(status_code=400, detail=f"Source file not found on disk: {local}")
    _validate_output_dir(payload)
    if output_mode == "channel":
        channel = (payload.channel_code or "").strip()
        if not channel:
            raise HTTPException(status_code=400, detail="channel_code is required when output_mode='channel'")
        out_path = Path(str(payload.output_dir).strip())
        parts = [str(p).strip().lower() for p in out_path.parts if str(p).strip()]
        chan = channel.lower()
        if chan not in parts:
            raise HTTPException(
                status_code=400,
                detail=f"output_dir must be inside selected channel folder '{channel}' (example: D:/data/{channel}/upload/video_output).",
            )


@router.post("/prepare-source")
def prepare_source(payload: PrepareSourceRequest):
    """
    Validate a local video file and return a session_id so the frontend can
    open the editor with a live preview before rendering. Local files only —
    use the standalone Downloader feature to fetch remote sources first.
    """
    _client_sid = str(payload.session_id or "").strip()
    session_id = _client_sid if _UUID_RE.match(_client_sid) else str(uuid.uuid4())
    work_dir = TEMP_DIR / "preview" / session_id
    work_dir.mkdir(parents=True, exist_ok=True)
    _emit_render_event(
        channel_code="preview",
        job_id=session_id,
        event="render.prepare_source.start",
        level="INFO",
        message="Preparing source",
        step="render.prepare_source",
    )
    try:
        mode = (payload.source_mode or "local").lower().strip()
        _emit_render_event(
            channel_code="preview",
            job_id=session_id,
            event="render.prepare_source.detect_input",
            level="INFO",
            message=f"Detecting source type: {mode}",
            step="render.prepare_source.detect_input",
            context={"source_mode": mode},
        )
        _emit_render_event(
            channel_code="preview",
            job_id=session_id,
            event="render.prepare_source.validate_input",
            level="INFO",
            message="Validating source input",
            step="render.prepare_source.validate_input",
        )
        if mode != "local":
            raise HTTPException(
                status_code=400,
                detail=(
                    f"source_mode='{mode}' is not supported. "
                    "Use the standalone Downloader to fetch remote sources, "
                    "then call /api/render/prepare-source with source_mode='local'."
                ),
            )
        src = Path(payload.source_video_path or "").expanduser().resolve()
        if not src.exists() or not src.is_file():
            raise HTTPException(status_code=400, detail=f"File not found: {src}")
        _emit_render_event(
            channel_code="preview",
            job_id=session_id,
            event="render.prepare_source.prepare_paths",
            level="INFO",
            message="Preparing source paths",
            step="render.prepare_source.prepare_paths",
            context={"source_path": str(src), "work_dir": str(work_dir)},
        )
        _emit_render_event(
            channel_code="preview",
            job_id=session_id,
            event="render.prepare_source.select_strategy",
            level="INFO",
            message="Selecting local source strategy",
            step="render.prepare_source.select_strategy",
            context={"strategy": "local_preview"},
        )
        duration = _probe_video_duration(src)
        preview_path = _ensure_h264_preview(src, work_dir, duration_sec=duration)
        _save_session(session_id, {
            "video_path": str(src),           # original used for render
            "preview_path": str(preview_path), # h264 used for browser preview
            "duration": duration,
            "title": src.stem,
            "work_dir": str(work_dir),
            "source_mode": "local",
        })
        _emit_render_event(
            channel_code="preview",
            job_id=session_id,
            event="render.prepare_source.success",
            level="INFO",
            message="Source prepared successfully",
            step="render.prepare_source.success",
            context={"source_mode": "local", "duration": duration},
        )
        return {"session_id": session_id, "duration": duration, "title": src.stem, "export_dir": str(work_dir / "exports")}
    except HTTPException as exc:
        _emit_render_event(
            channel_code="preview",
            job_id=session_id,
            event="render.prepare_source.error",
            level="ERROR",
            message=f"Source preparation failed: {exc.detail}",
            step="render.prepare_source.error",
            context={"source_mode": (payload.source_mode or "local").lower().strip(), "path": (payload.source_video_path or "").strip()},
            exception=exc,
            traceback_text=traceback.format_exc(),
        )
        raise
    except Exception as exc:
        logger.error("prepare-source error: %s", exc)
        _emit_render_event(
            channel_code="preview",
            job_id=session_id,
            event="render.prepare_source.error",
            level="ERROR",
            message=f"Source preparation failed: {exc}",
            step="render.prepare_source.error",
            context={"source_mode": (payload.source_mode or "local").lower().strip(), "path": (payload.source_video_path or "").strip()},
            exception=exc,
            traceback_text=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/prepare-source/{session_id}")
def cancel_prepare_source(session_id: str):
    """Remove the preview work directory for a prepare-source session."""
    _cleanup_preview_session(session_id)
    return {"cancelled": True, "session_id": session_id}


@router.get("/preview-video/{session_id}")
def preview_video(session_id: str):
    """Serve H.264 preview video with proper range support for HTML5 player."""
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Preview session not found")

    # Prefer preview_path (H.264 transcoded), fall back to video_path
    video_path = Path(session.get("preview_path") or session["video_path"])
    if not video_path.exists():
        video_path = Path(session["video_path"])
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Preview video file not found")

    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"},
    )


@router.get("/preview-transcript/{session_id}")
def preview_transcript(session_id: str):
    """Return a Whisper-tiny transcript for the editor subtitle preview.
    Result is cached in the session work_dir so repeat calls are instant."""
    session = _load_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.get("duration", 0) > 3600:
        return {"segments": [], "status": "too_long"}

    _work_dir_str = session.get("work_dir", "")
    if not _work_dir_str:
        raise HTTPException(status_code=400, detail="Session has no work_dir — recreate the session")
    work_dir = Path(_work_dir_str)
    cache_path = work_dir / "preview_transcript.json"

    if cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as fh:
                return {"segments": json.load(fh)}
        except Exception:
            pass

    video_path = Path(session.get("preview_path") or session.get("video_path", ""))
    if not video_path.exists():
        raise HTTPException(status_code=404, detail="Video file not found")

    # Get or create a per-session lock so only one Whisper run happens at a time.
    with _transcript_locks_mu:
        lock = _transcript_locks.setdefault(session_id, threading.Lock())

    acquired = lock.acquire(blocking=False)
    if not acquired:
        # Another request is already transcribing — tell the client to retry later.
        return {"segments": [], "status": "in_progress"}

    try:
        # Double-check cache inside the lock (another thread may have just written it).
        if cache_path.exists():
            try:
                with cache_path.open("r", encoding="utf-8") as fh:
                    return {"segments": json.load(fh)}
            except Exception:
                pass

        # Extract audio to WAV first — avoids tensor-shape errors that occur
        # when Whisper reads 60fps or high-bitrate video containers directly.
        ffmpeg_bin = get_ffmpeg_bin()
        audio_path = work_dir / "preview_audio.wav"
        if not audio_path.exists():
            subprocess.run(
                [
                    ffmpeg_bin, "-y", "-i", str(video_path),
                    "-vn", "-ac", "1", "-ar", "16000",
                    "-acodec", "pcm_s16le", str(audio_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )

        from app.services.subtitle_engine import get_whisper_model
        model = get_whisper_model("tiny")
        result = model.transcribe(str(audio_path), fp16=False, verbose=False)
        segments = [
            {
                "start": round(float(s["start"]), 3),
                "end": round(float(s["end"]), 3),
                "text": str(s.get("text", "")).strip(),
            }
            for s in result.get("segments", [])
            if str(s.get("text", "")).strip()
        ]
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump(segments, fh)
        # Remove temp audio — cache_path now holds the result
        audio_path.unlink(missing_ok=True)
        return {"segments": segments}
    except Exception as exc:
        logging.getLogger(__name__).error("preview-transcript failed for %s: %s", session_id, exc)
        return {"segments": [], "status": "error", "detail": str(exc)}
    finally:
        lock.release()
        # Clean up the lock entry once done so it doesn't grow unbounded.
        with _transcript_locks_mu:
            _transcript_locks.pop(session_id, None)


def process_render(job_id: str, payload: RenderRequest, resume_mode: bool = False):
    from app.services import cancel_registry
    from app.services.metrics import RENDER_JOB_DURATION, RENDER_JOBS_TOTAL
    ev = cancel_registry.register(job_id)
    # Sprint 6.C: instrument terminal status + wallclock per job. `final_status`
    # is initialized to "succeeded" because the happy path falls through the
    # try block without setting it. Cancellation + failure paths overwrite it.
    start_monotonic = time.monotonic()
    final_status = "succeeded"
    try:
        # A cancel requested while the job was still queued pre-sets the event
        if ev.is_set():
            raise cancel_registry.JobCancelledError()
        run_render_pipeline(
            job_id=job_id,
            payload=payload,
            resume_mode=resume_mode,
            load_session_fn=_load_session,
            cleanup_session_fn=_cleanup_preview_session,
        )
    except cancel_registry.JobCancelledError:
        # P3-B1: use the JobStage enum constant instead of the raw string
        # so any future refactor that switches to enum-only validation
        # doesn't silently break cancellation.
        update_job_progress(
            job_id, JobStage.CANCELLED, 0,
            "Job cancelled by user",
            status=JobStage.CANCELLED,
        )
        final_status = "cancelled"
    except Exception:
        final_status = "failed"
        raise
    finally:
        duration = time.monotonic() - start_monotonic
        try:
            RENDER_JOBS_TOTAL.labels(status=final_status).inc()
            RENDER_JOB_DURATION.labels(status=final_status).observe(duration)
        except Exception:
            # Metrics must NEVER fail a render. The no-op shim covers the
            # missing-prometheus path; this except catches anything else.
            pass
        cancel_registry.unregister(job_id)


def _queue_render_job(job_id: str, effective_channel: str, payload: RenderRequest, *, resume_mode: bool, queued_message: str):
    if is_running(job_id):
        raise HTTPException(status_code=409, detail="Render job is already running")
    previous = get_job(job_id)
    upsert_job(
        job_id,
        "render",
        effective_channel,
        "queued",
        payload.model_dump(),
        {},
        stage=JobStage.QUEUED,
        progress_percent=0,
        message=queued_message,
    )
    submitted = submit_job(job_id, process_render, job_id, payload, resume_mode)
    if submitted:
        return

    if previous:
        try:
            previous_payload = json.loads(previous.get("payload_json") or "{}")
        except Exception:
            previous_payload = {}
        try:
            previous_result = json.loads(previous.get("result_json") or "{}")
        except Exception:
            previous_result = {}
        upsert_job(
            job_id,
            previous.get("kind") or "render",
            previous.get("channel_code") or effective_channel,
            previous.get("status") or "queued",
            previous_payload,
            previous_result,
            stage=previous.get("stage") or JobStage.QUEUED,
            progress_percent=int(previous.get("progress_percent") or 0),
            message=previous.get("message") or "",
        )
    raise HTTPException(status_code=409, detail="Render job is already running")


@router.post("/process")
def create_render_job(payload: RenderRequest):
    _coerce_legacy_channel_payload(payload)
    # Apply server-wide LLM provider default to NEW jobs only.
    # Resume/retry: ai_provider stays as stored.
    if "ai_provider" not in payload.model_fields_set:
        payload.ai_provider = _cfg.AI_PROVIDER_DEFAULT
    try:
        _validate_render_source(payload)
        _validate_text_layers_or_400(payload)
    except HTTPException as exc:
        logger.warning("Render request rejected (HTTP %s): %s", exc.status_code, exc.detail)
        _emit_request_event(route="/api/render/process", status_code=exc.status_code, detail=str(exc.detail), channel_code=(payload.channel_code or "").strip())
        raise
    effective_channel = (payload.channel_code or "").strip() or "manual"
    job_id = payload.resume_job_id or str(uuid.uuid4())
    existing = get_job(job_id) if payload.resume_job_id else None
    resume_mode = bool(existing) and payload.resume_from_last
    _queue_render_job(job_id, effective_channel, payload, resume_mode=resume_mode, queued_message="Job queued")
    return {"job_id": job_id, "status": "queued", "resume_mode": resume_mode}


@router.post("/upload-local")
async def upload_local_video(
    file: UploadFile = File(...),
    channel_code: str = Form("T1"),
):
    """Accept a local video file upload from browser and save to channel source dir."""
    channel = (channel_code or "T1").strip()
    if not channel:
        raise HTTPException(status_code=400, detail="channel_code is required")
    ensure_channel(channel)
    source_dir = CHANNELS_DIR / channel / "upload" / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "video.mp4"
    safe_name = slugify(Path(original_name).stem) or "video"
    ext = Path(original_name).suffix or ".mp4"
    dest = source_dir / f"{safe_name}{ext}"
    # Avoid overwriting
    idx = 1
    while dest.exists():
        dest = source_dir / f"{safe_name}_{idx}{ext}"
        idx += 1

    with open(dest, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    return {"path": str(dest), "filename": dest.name, "size": dest.stat().st_size}


@router.post("/test-cloud-ai")
def test_cloud_ai(body: dict):
    """Validate cloud AI provider credentials.

    Sends a minimal prompt and returns latency. Never touches the render pipeline.
    Body: { provider: "gemini"|"openai"|"claude", api_key: str, model?: str }
    """
    import time
    provider = str(body.get("provider") or "gemini").lower()
    api_key  = str(body.get("api_key") or "").strip()
    model    = body.get("model") or None

    # If no API key in body, fall back to server env.
    if not api_key:
        _env_map = {
            "gemini": getattr(_cfg, "GEMINI_API_KEY", ""),
            "openai": getattr(_cfg, "OPENAI_API_KEY", ""),
            "claude": getattr(_cfg, "CLAUDE_API_KEY", ""),
        }
        api_key = (_env_map.get(provider) or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail=f"No API key for provider={provider} (not in body and "
                   f"{provider.upper()}_API_KEY env empty)",
        )

    _TEST_MESSAGES = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user",   "content": "Reply with the single word: ready"},
    ]

    t0 = time.monotonic()
    try:
        if provider == "openai":
            import openai as _openai
            resolved_model = model or "gpt-4o-mini"
            client = _openai.OpenAI(api_key=api_key, timeout=10)
            resp = client.chat.completions.create(
                model=resolved_model,
                messages=_TEST_MESSAGES,
                max_tokens=8,
                temperature=0.0,
            )
        elif provider == "gemini":
            from google import genai as _genai
            resolved_model = model or "gemini-2.0-flash"
            client = _genai.Client(api_key=api_key)
            _gem_resp = client.models.generate_content(
                model=resolved_model,
                contents="Reply with the single word: ready",
                config={"temperature": 0.0, "max_output_tokens": 8},
            )
            # Mock OpenAI-style response so the latency_ms path below works.
            class _R:
                pass
            resp = _R()
            resp.choices = [_R()]
            resp.choices[0].message = _R()
            resp.choices[0].message.content = (_gem_resp.text or "").strip()
        elif provider == "claude":
            try:
                from anthropic import Anthropic as _AnthClient
            except ImportError:
                raise HTTPException(status_code=501, detail="anthropic SDK not installed")
            resolved_model = model or "claude-haiku-4-5-20251001"
            client = _AnthClient(api_key=api_key, timeout=10)
            _claude_resp = client.messages.create(
                model=resolved_model,
                max_tokens=8,
                messages=[{"role": "user", "content": "Reply with the single word: ready"}],
            )
            class _R:
                pass
            resp = _R()
            resp.choices = [_R()]
            resp.choices[0].message = _R()
            resp.choices[0].message.content = _claude_resp.content[0].text if _claude_resp.content else ""
        else:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

        latency_ms = int((time.monotonic() - t0) * 1000)
        return {"ok": True, "provider": provider, "model": resolved_model, "latency_ms": latency_ms}

    except HTTPException:
        raise
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        msg = str(exc)
        # Shorten verbose SDK error messages for the UI
        if "invalid_api_key" in msg.lower() or "authentication" in msg.lower() or "401" in msg:
            msg = "Invalid API key"
        elif "model" in msg.lower() and ("not found" in msg.lower() or "does not exist" in msg.lower()):
            msg = f"Model not found: {resolved_model}"  # type: ignore[possibly-undefined]
        elif "connection" in msg.lower() or "timeout" in msg.lower():
            msg = "Connection failed — check network"
        logger.debug("test_cloud_ai_failed provider=%s: %s", provider, exc)
        return {"ok": False, "provider": provider, "error": msg, "latency_ms": latency_ms}


@router.post("/quick-process")
def quick_process(payload: QuickProcessRequest):
    """
    Simple one-shot flow over a local file:
    - Optionally apply resize/filter
    - Save to exact output file path
    """
    source = (payload.source or "local").strip().lower()
    local_path_raw = (payload.path or "").strip()
    output_raw = (payload.output or "").strip()

    quick_job_id = str(uuid.uuid4())
    _emit_render_event(
        channel_code="quick",
        job_id=quick_job_id,
        event="render.start",
        level="INFO",
        message="Quick render started",
        step="render.start",
        context={"source": source},
    )
    if source != "local":
        raise HTTPException(
            status_code=400,
            detail=(
                f"source='{source}' is not supported. "
                "Use the standalone Downloader to fetch remote sources, "
                "then call /api/render/quick-process with source='local'."
            ),
        )
    if not local_path_raw:
        raise HTTPException(status_code=400, detail="path is required when source='local'")
    if not output_raw:
        raise HTTPException(status_code=400, detail="output is required")

    if (payload.resize_width and not payload.resize_height) or (payload.resize_height and not payload.resize_width):
        raise HTTPException(status_code=400, detail="resize_width and resize_height must be provided together")
    if payload.resize_width is not None and payload.resize_width <= 0:
        raise HTTPException(status_code=400, detail="resize_width must be > 0")
    if payload.resize_width is not None and payload.resize_width > 7680:
        raise HTTPException(status_code=400, detail="resize_width must be <= 7680 (8K)")
    if payload.resize_height is not None and payload.resize_height <= 0:
        raise HTTPException(status_code=400, detail="resize_height must be > 0")
    if payload.resize_height is not None and payload.resize_height > 4320:
        raise HTTPException(status_code=400, detail="resize_height must be <= 4320 (8K)")
    if payload.black_min_duration <= 0:
        raise HTTPException(status_code=400, detail="black_min_duration must be > 0")
    if payload.black_threshold < 0 or payload.black_threshold > 1:
        raise HTTPException(status_code=400, detail="black_threshold must be between 0 and 1")

    output_path = Path(output_raw).expanduser()
    if not output_path.is_absolute():
        output_path = (Path.cwd() / output_path).resolve()
    if output_path.exists() and output_path.is_dir():
        raise HTTPException(status_code=400, detail="output must be a file path, not a directory")
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid output path: {exc}") from exc

    job_id = str(uuid.uuid4())
    work_dir = TEMP_DIR / f"quick_{job_id}"
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.input.validate.start",
            level="INFO",
            message="Validating quick render input",
            step="render.input.validate",
        )
        src_path = Path(local_path_raw).expanduser()
        if not src_path.is_absolute():
            src_path = (Path.cwd() / src_path).resolve()
        if not src_path.exists() or not src_path.is_file():
            raise HTTPException(status_code=400, detail=f"Local file not found: {src_path}")
        downloaded_title = src_path.stem
        duration = _probe_video_duration(src_path)

        vf_parts: list[str] = []
        if payload.resize_width and payload.resize_height:
            vf_parts.append(f"scale={int(payload.resize_width)}:{int(payload.resize_height)}")
        if (payload.video_filter or "").strip():
            _vf = (payload.video_filter or "").strip()
            # Security: allowlist prevents FFmpeg filter injection via crafted vf chains.
            # Filters like 'movie=', 'geq=', 'script=' can read files or run OS commands.
            _SAFE_VF_FILTERS = {
                "scale", "fps", "crop", "rotate", "transpose",
                "hflip", "vflip", "pad", "setsar", "setdar",
            }
            _vf_name = re.split(r"[=,\s]", _vf)[0].strip().lower()
            if _vf_name not in _SAFE_VF_FILTERS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported video filter '{_vf_name}'. "
                           f"Allowed filters: {sorted(_SAFE_VF_FILTERS)}",
                )
            vf_parts.append(_vf)

        overwrite_flag = "-y" if payload.overwrite else "-n"
        trim_start_sec = 0.0
        if payload.trim_black_intro:
            trim_start_sec = _detect_leading_black_duration(
                src_path,
                min_duration=float(payload.black_min_duration),
                threshold=float(payload.black_threshold),
            )

        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.input.validate.success",
            level="INFO",
            message="Quick render input validated",
            step="render.input.validate",
            context={"source_path": str(src_path), "output": str(output_path)},
        )
        has_transform = bool(vf_parts) or (trim_start_sec > 0)

        if not has_transform:
            # Fast path: no transform requested and no leading black to trim.
            copy_cmd = [
                get_ffmpeg_bin(),
                overwrite_flag,
                "-i", str(src_path),
                "-c", "copy",
                "-movflags", "+faststart",
                str(output_path),
            ]
            try:
                _run_ffmpeg_checked(copy_cmd, "FFmpeg copy failed")
            except Exception:
                has_transform = True

        if has_transform:
            # Single processing pass. Avoid intermediate temp files.
            _emit_render_event(
                channel_code="quick",
                job_id=quick_job_id,
                event="render.ffmpeg.start",
                level="INFO",
                message="Running ffmpeg quick process",
                step="render.ffmpeg",
                context={"trim_start_sec": round(trim_start_sec, 3), "filters": len(vf_parts)},
            )
            cmd = [
                get_ffmpeg_bin(),
                overwrite_flag,
            ]
            if trim_start_sec > 0:
                cmd += ["-ss", f"{trim_start_sec:.3f}"]
            cmd += ["-i", str(src_path)]
            if vf_parts:
                cmd += ["-vf", ",".join(vf_parts)]
            if trim_start_sec > 0 and not vf_parts:
                # Fast trim path with stream copy; fallback to encode for edge cases.
                trim_copy_cmd = [
                    *cmd,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
                try:
                    _run_ffmpeg_checked(trim_copy_cmd, "FFmpeg trim copy failed")
                except HTTPException:
                    trim_encode_cmd = [
                        *cmd,
                        "-c:v", "libx264",
                        "-preset", "medium",
                        "-crf", "20",
                        "-c:a", "aac",
                        "-b:a", "192k",
                        "-movflags", "+faststart",
                        str(output_path),
                    ]
                    _run_ffmpeg_checked(trim_encode_cmd, "FFmpeg trim encode failed")
            else:
                cmd += [
                    "-c:v", "libx264",
                    "-preset", "medium",
                    "-crf", "20",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-movflags", "+faststart",
                    str(output_path),
                ]
                _run_ffmpeg_checked(cmd, "FFmpeg processing failed")
            _emit_render_event(
                channel_code="quick",
                job_id=quick_job_id,
                event="render.ffmpeg.success",
                level="INFO",
                message="Quick ffmpeg processing completed",
                step="render.ffmpeg",
            )

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise RuntimeError(f"Output file was not created: {output_path}")
        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.complete",
            level="INFO",
            message="Quick render success",
            step="render.complete",
            context={"output": str(output_path)},
        )

        return {
            "status": "completed",
            "source": source,
            "url": "",
            "path": str(src_path),
            "output": str(output_path),
            "downloaded_title": downloaded_title,
            "duration": duration,
            "processed": has_transform,
            "trim_applied": trim_start_sec > 0,
            "trim_start_sec": round(trim_start_sec, 3),
        }
    except HTTPException:
        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.error",
            level="ERROR",
            message="Quick render request failed",
            step="render.error",
        )
        raise
    except Exception as exc:
        _emit_render_event(
            channel_code="quick",
            job_id=quick_job_id,
            event="render.error",
            level="ERROR",
            message=f"Quick render failed: {exc}",
            step="render.error",
            exception=exc,
            traceback_text=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        try:
            shutil.rmtree(work_dir, ignore_errors=True)
        except Exception:
            pass


@router.post("/resume/{job_id}")
def resume_render_job(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    payload_json = row.get("payload_json") or "{}"
    try:
        payload_data = json.loads(payload_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot parse payload_json for job {job_id}: {e}") from e

    payload = RenderRequest(**payload_data)
    payload.resume_from_last = True
    _coerce_legacy_channel_payload(payload)
    _validate_render_source(payload)
    effective_channel = (payload.channel_code or "").strip() or "manual"
    _queue_render_job(job_id, effective_channel, payload, resume_mode=True, queued_message="Resume job queued")
    return {"job_id": job_id, "status": "queued", "resume_mode": True}


@router.post("/retry/{job_id}")
def retry_failed_parts(job_id: str):
    """Re-run only the failed parts of a completed or partially-failed render job.

    Done parts are preserved; only parts with status='failed' are re-processed.
    Equivalent to resume, but validated to have at least one failed part.
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if (row.get("status") or "").lower() in ("running", "queued"):
        raise HTTPException(status_code=409, detail="Job is already running or queued")

    parts = list_job_parts(job_id)
    failed = [p for p in parts if (p.get("status") or "").lower() == "failed"]
    if not failed:
        raise HTTPException(status_code=400, detail="No failed parts to retry")

    payload_json = row.get("payload_json") or "{}"
    try:
        payload_data = json.loads(payload_json)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot parse payload for job {job_id}: {e}") from e

    payload = RenderRequest(**payload_data)
    payload.resume_from_last = True
    _coerce_legacy_channel_payload(payload)
    _validate_render_source(payload)
    effective_channel = (payload.channel_code or "").strip() or "manual"
    _queue_render_job(
        job_id, effective_channel, payload,
        resume_mode=True,
        queued_message=f"Retrying {len(failed)} failed part(s)",
    )
    return {"job_id": job_id, "status": "queued", "failed_parts_count": len(failed)}


@router.post("/{job_id}/cancel")
def cancel_render_job(job_id: str):
    """Signal a running or queued render job to stop.

    Returns immediately with status='cancelling'. The job transitions to
    status='cancelled' asynchronously once the current FFmpeg call is
    terminated (within ~1 s of receiving the signal).
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    status = (row.get("status") or "").lower()
    if status not in ("running", "queued"):
        raise HTTPException(status_code=409, detail=f"Job is not cancellable (status={status})")
    update_job_progress(job_id, "cancelling", 0, "Cancelling…", status="cancelling")
    from app.services import cancel_registry
    cancel_registry.request_cancel(job_id)
    return {"job_id": job_id, "status": "cancelling"}


@router.get("/jobs/{job_id}")
def get_render_job(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


# ── Rendered clip media streaming ─────────────────────────────────────────────

@router.get("/jobs/{job_id}/parts/{part_no}/media")
def stream_render_part_media(job_id: str, part_no: int, request: Request):
    """Stream a rendered clip output file with proper HTTP Range request support.

    Chrome's <video> element sends a Range probe on every load; without a real
    206 Partial Content response the element stalls until the full file is
    buffered, making clips appear broken.  This endpoint handles Range correctly
    so playback starts immediately.

    Security: the file path is looked up from the job_parts DB record, never
    taken from user input, so there is no path-traversal risk.
    """
    parts = list_job_parts(job_id)
    part = next((p for p in parts if int(p.get("part_no", -1)) == part_no), None)
    if not part or not part.get("output_file"):
        raise HTTPException(status_code=404, detail="Part not found")

    path = Path(part["output_file"])
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found on disk")

    file_size = path.stat().st_size
    if file_size == 0:
        raise HTTPException(status_code=404, detail="Output file is empty")

    range_header = request.headers.get("range", "").strip()

    if range_header:
        byte1, byte2 = _parse_range_header(range_header, file_size)
        length = byte2 - byte1 + 1
        return StreamingResponse(
            _iter_file_bytes(path, byte1, byte2),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {byte1}-{byte2}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length),
                "Cache-Control": "no-store",
            },
        )

    # No Range header — send the full file (still streaming, never buffered in-process)
    return StreamingResponse(
        _iter_file_bytes(path, 0, file_size - 1),
        status_code=200,
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Cache-Control": "no-store",
        },
    )


@router.get("/jobs/{job_id}/parts/{part_no}/thumbnail")
def get_render_part_thumbnail(job_id: str, part_no: int, t: float = 0.5, w: int = 320):
    """Return a JPEG thumbnail frame extracted from the rendered clip at offset t seconds.

    Cached by the browser for 24 hours (Cache-Control: public, max-age=86400).
    Security: file path is resolved from DB, never from user input.
    """
    from fastapi.responses import Response
    from app.services.render_engine import extract_thumbnail_frame
    parts = list_job_parts(job_id)
    part = next((p for p in parts if int(p.get("part_no", -1)) == part_no), None)
    if not part or not part.get("output_file"):
        raise HTTPException(status_code=404, detail="Part not found")
    path = Path(part["output_file"])
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Output file not found on disk")
    jpeg = extract_thumbnail_frame(str(path), offset_sec=max(0.0, t), width=max(32, min(640, w)))
    if not jpeg:
        raise HTTPException(status_code=500, detail="Thumbnail extraction failed")
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Length": str(len(jpeg)),
        },
    )


@router.get("/subtitle-preview")
def api_subtitle_preview(
    style: str = "tiktok_bounce_v1",
    aspect_ratio: str = "9:16",
    font_size: int = 0,
    text: str = "This is a preview subtitle",
):
    """Return a PNG frame with the subtitle style rendered by libass.

    Uses the same ASSPreset pipeline as real renders so the preview matches
    actual output exactly. Cached by the browser for 1 hour.
    """
    from fastapi.responses import Response
    from app.services.subtitles.ass_core import render_subtitle_preview

    safe_ratio = aspect_ratio if aspect_ratio in ("9:16", "3:4", "4:5", "1:1", "16:9") else "9:16"
    safe_size  = max(0, min(200, int(font_size)))
    safe_text  = (text or "Preview subtitle")[:200].replace("\n", " ").strip()

    try:
        png = render_subtitle_preview(
            subtitle_style=style,
            font_size=safe_size,
            aspect_ratio=safe_ratio,
            sample_text=safe_text,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Subtitle preview failed: {exc}")

    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=3600",
            "Content-Length": str(len(png)),
        },
    )
