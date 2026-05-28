
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
from urllib.parse import urlparse

# Guards concurrent preview-transcript requests for the same session.
# Key = session_id, Value = threading.Lock held while Whisper is running.
_transcript_locks: dict[str, threading.Lock] = {}
_transcript_locks_mu = threading.Lock()
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, StreamingResponse
from app.models.schemas import RenderRequest, DownloadHealthRequest, PrepareSourceRequest, QuickProcessRequest
from app.services.db import upsert_job, get_job, list_job_parts, update_job_progress
from app.services.job_manager import submit_job, is_running
from app.services.channel_service import ensure_channel
from app.services.downloader import download_youtube, slugify, check_youtube_download_health
from app.core.config import TEMP_DIR, CHANNELS_DIR, REQUEST_LOG
from app.core.stage import JobStage
from app.services.bin_paths import get_ffprobe_bin, get_ffmpeg_bin
from app.orchestration.render_pipeline import (
    run_render_pipeline,
    _emit_render_event,
    _probe_video_duration,
    _validate_text_layers_or_400,
    _append_json_line,
)
from app.services.preview.ffmpeg_probers import (
    _probe_video_codec,
    _probe_preview_profile,
    _is_browser_safe_preview,
    _ensure_h264_preview,
    _run_ffmpeg_checked,
    _detect_leading_black_duration,
)
from app.services.preview.session_service import (
    _PREVIEW_SESSIONS,
    _PREVIEW_DIR,
    _SESSION_TTL_HOURS,
    _MAX_PREVIEW_SESSIONS,
    _save_session,
    _load_session,
    _cleanup_preview_session,
    evict_stale_preview_sessions,  # re-exported: main.py imports this from app.routes.render
)
from app.services.preview.media_streaming import (
    _parse_range_header,
    _iter_file_bytes,
)

router = APIRouter(prefix="/api/render", tags=["render"])
logger = logging.getLogger("app.render")


@router.get("/queue-status")
def get_queue_status():
    """Read-only — returns active render count and max concurrent slots."""
    from app.orchestration.render_pipeline import _render_active_count, _render_active_lock, _JOB_SEM_VALUE
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

_ACTIVE_DOWNLOADS: dict[str, threading.Event] = {}  # session_id -> cancel event for in-progress YouTube downloads
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

    # When an editor session is provided, the pipeline uses the session's video_path
    # instead of downloading; skip source-URL/path validation entirely.
    if (getattr(payload, "edit_session_id", None) or "").strip():
        _validate_output_dir(payload)
        return

    mode = (payload.source_mode or "youtube").lower().strip()
    yt = (payload.youtube_url or "").strip()
    yt_many = [str(x).strip() for x in (payload.youtube_urls or []) if str(x).strip()]
    local = (payload.source_video_path or "").strip()
    if mode not in ("youtube", "local"):
        raise HTTPException(status_code=400, detail="source_mode must be 'youtube' or 'local'")
    if mode == "youtube":
        if not yt and not yt_many:
            raise HTTPException(status_code=400, detail="youtube_url or youtube_urls is required when source_mode='youtube'")
        if local:
            raise HTTPException(status_code=400, detail="source_video_path must be empty when source_mode='youtube'")
    else:
        if not local:
            raise HTTPException(status_code=400, detail="source_video_path is required when source_mode='local'")
        if yt:
            raise HTTPException(status_code=400, detail="youtube_url must be empty when source_mode='local'")
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
    Download YouTube video OR validate local file and return a session_id
    so the frontend can open the editor with a live preview before rendering.
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
        if mode == "local":
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
        else:
            yt_url = (payload.youtube_url or "").strip()
            if not yt_url:
                raise HTTPException(status_code=400, detail="youtube_url is required")
            _emit_render_event(
                channel_code="preview",
                job_id=session_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code="preview",
                job_id=session_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting YouTube download strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "youtube_download", "url": yt_url},
            )
            _cancel_ev = threading.Event()
            _ACTIVE_DOWNLOADS[session_id] = _cancel_ev
            try:
                source = download_youtube(yt_url, work_dir, context="preview", cancel_event=_cancel_ev)
            finally:
                _ACTIVE_DOWNLOADS.pop(session_id, None)
            src = Path(source["filepath"])
            preview_path = _ensure_h264_preview(src, work_dir, duration_sec=int(source.get("duration") or 0))
            _save_session(session_id, {
                "video_path": source["filepath"],  # original used for render
                "preview_path": str(preview_path), # h264 used for browser preview
                "duration": source["duration"],
                "title": source["title"],
                "work_dir": str(work_dir),
                "source_mode": "youtube",
            })
            _emit_render_event(
                channel_code="preview",
                job_id=session_id,
                event="render.prepare_source.success",
                level="INFO",
                message="Source prepared successfully",
                step="render.prepare_source.success",
                context={"source_mode": "youtube", "duration": source.get("duration", 0), "title": source.get("title", "")},
            )
            return {"session_id": session_id, "duration": source["duration"], "title": source["title"], "export_dir": str(work_dir / "exports")}
    except HTTPException as exc:
        _emit_render_event(
            channel_code="preview",
            job_id=session_id,
            event="render.prepare_source.error",
            level="ERROR",
            message=f"Source preparation failed: {exc.detail}",
            step="render.prepare_source.error",
            context={"source_mode": (payload.source_mode or "local").lower().strip(), "url": (payload.youtube_url or "").strip(), "path": (payload.source_video_path or "").strip()},
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
            context={"source_mode": (payload.source_mode or "local").lower().strip(), "url": (payload.youtube_url or "").strip(), "path": (payload.source_video_path or "").strip()},
            exception=exc,
            traceback_text=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/prepare-source/{session_id}")
def cancel_prepare_source(session_id: str):
    """Signal an active YouTube download to stop and remove the preview work directory."""
    ev = _ACTIVE_DOWNLOADS.get(session_id)
    if ev:
        ev.set()
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
    ev = cancel_registry.register(job_id)
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
        update_job_progress(job_id, "cancelled", 0, "Job cancelled by user", status="cancelled")
    finally:
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


@router.post("/process/batch")
def create_render_batch(payload: RenderRequest):
    try:
        _validate_render_source(payload)
        _validate_text_layers_or_400(payload)
    except HTTPException as exc:
        logger.warning("Batch render request rejected (HTTP %s): %s", exc.status_code, exc.detail)
        _emit_request_event(route="/api/render/process/batch", status_code=exc.status_code, detail=str(exc.detail), channel_code=(payload.channel_code or "").strip())
        raise
    effective_channel = (payload.channel_code or "").strip() or "manual"
    if (payload.source_mode or "youtube").lower() != "youtube":
        raise HTTPException(status_code=400, detail="Batch mode supports youtube source only")
    urls = [str(x).strip() for x in (payload.youtube_urls or []) if str(x).strip()]
    if not urls and (payload.youtube_url or "").strip():
        urls = [(payload.youtube_url or "").strip()]
    if len(urls) < 2:
        raise HTTPException(status_code=400, detail="Batch mode requires at least 2 youtube URLs")

    batch_id = str(uuid.uuid4())
    child_job_ids: list[str] = [str(uuid.uuid4()) for _ in urls]
    upsert_job(
        batch_id,
        "render_batch",
        effective_channel,
        "queued",
        payload.model_dump(),
        {"count": len(urls)},
        stage=JobStage.QUEUED,
        progress_percent=0,
        message=f"Batch queued with {len(urls)} urls",
    )

    def _run_batch():
        try:
            upsert_job(
                batch_id,
                "render_batch",
                effective_channel,
                "running",
                payload.model_dump(),
                {"count": len(urls), "jobs": child_job_ids},
                stage=JobStage.RUNNING,
                progress_percent=1,
                message="Batch running",
            )
            for idx, (url, child_id) in enumerate(zip(urls, child_job_ids), start=1):
                from app.services import cancel_registry
                if cancel_registry.is_cancelled(batch_id):
                    logger.info("Batch %s: cancel requested — stopping after %d/%d", batch_id, idx - 1, len(urls))
                    upsert_job(
                        batch_id, "render_batch", effective_channel, "cancelled",
                        payload.model_dump(), {"count": len(urls), "jobs": child_job_ids},
                        stage=JobStage.DONE, progress_percent=100,
                        message=f"Batch cancelled after {idx - 1}/{len(urls)} items",
                    )
                    return
                child_payload = RenderRequest(**{**payload.model_dump(), "youtube_url": url, "youtube_urls": [url], "resume_job_id": None})
                upsert_job(
                    child_id,
                    "render",
                    effective_channel,
                    "queued",
                    child_payload.model_dump(),
                    {},
                    stage=JobStage.QUEUED,
                    progress_percent=0,
                    message=f"Queued by batch {batch_id[:8]} ({idx}/{len(urls)})",
                )
                # Route child through submit_job so it is tracked by job_manager
                # (appears in _active_job_ids, respects MAX_CONCURRENT_JOBS).
                # A threading.Event lets the batch coordinator wait for this child
                # to finish before moving to the next without busy-polling.
                # The try/finally inside _child_fn guarantees _done is always set,
                # even if process_render raises an exception.
                _done = threading.Event()
                def _child_fn(_id=child_id, _p=child_payload, _ev=_done):
                    try:
                        process_render(_id, _p, False)
                    finally:
                        _ev.set()
                submitted = submit_job(child_id, _child_fn)
                if submitted:
                    completed_in_time = _done.wait(timeout=7200)  # 2h hard ceiling per child
                    if not completed_in_time:
                        logger.error(
                            "Batch child %s timed out waiting (7200s) — marking failed and continuing", child_id
                        )
                        update_job_progress(child_id, "timeout", 100, "Child timed out in batch", status="failed")
                # If submit_job returned False the child_id was already tracked
                # (duplicate submission guard) — skip the wait; the DB status
                # reflects the real outcome when batch progress is written below.
                pct = int((idx / len(urls)) * 100)
                upsert_job(
                    batch_id,
                    "render_batch",
                    effective_channel,
                    "running",
                    payload.model_dump(),
                    {"count": len(urls), "jobs": child_job_ids},
                    stage=JobStage.RUNNING,
                    progress_percent=pct,
                    message=f"Processed {idx}/{len(urls)} links",
                )
            upsert_job(
                batch_id,
                "render_batch",
                effective_channel,
                "completed",
                payload.model_dump(),
                {"count": len(urls), "jobs": child_job_ids},
                stage=JobStage.DONE,
                progress_percent=100,
                message=f"Batch completed: {len(urls)} links",
            )
        except Exception as exc:
            upsert_job(
                batch_id,
                "render_batch",
                effective_channel,
                "failed",
                payload.model_dump(),
                {"count": len(urls), "jobs": child_job_ids, "error": str(exc)},
                stage=JobStage.FAILED,
                progress_percent=100,
                message=f"Batch failed: {exc}",
            )

    # The batch coordinator is a supervisor, not a render worker: it submits
    # child jobs and waits for each one — it does no CPU/GPU work itself.
    # Running it via submit_job() would occupy a job_manager slot, causing
    # deadlock when MAX_CONCURRENT_JOBS=1 (coordinator holds the only slot;
    # no slot is free for children to be dispatched).
    # A daemon thread avoids this: the coordinator is never in _active_job_ids,
    # so children submitted via submit_job() can be dispatched at any concurrency
    # level. All FFmpeg-level limits (JOB_SEMAPHORE, MAX_CONCURRENT_JOBS) still
    # apply to each child through the normal submit_job path.
    threading.Thread(target=_run_batch, daemon=True, name=f"batch-{batch_id[:8]}").start()
    return {"batch_id": batch_id, "job_ids": child_job_ids, "count": len(urls), "status": "queued"}


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


@router.post("/download-health")
def download_health(payload: DownloadHealthRequest):
    url = (payload.youtube_url or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="youtube_url is required")
    return check_youtube_download_health(url)



@router.post("/quick-process")
def quick_process(payload: QuickProcessRequest):
    """
    Simple one-shot flow:
    - Download from YouTube URL
    - Optionally apply resize/filter
    - Save to exact output file path
    """
    source = (payload.source or "").strip().lower()
    url = (payload.url or "").strip()
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
    if source not in ("youtube", "local"):
        raise HTTPException(status_code=400, detail="source must be 'youtube' or 'local'")
    if source == "youtube" and not url:
        raise HTTPException(status_code=400, detail="url is required when source='youtube'")
    if source == "youtube":
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise HTTPException(status_code=400, detail="url must be a valid http(s) URL")
    if source == "local" and not local_path_raw:
        raise HTTPException(status_code=400, detail="path is required when source='local'")
    if not output_raw:
        raise HTTPException(status_code=400, detail="output is required")

    if (payload.resize_width and not payload.resize_height) or (payload.resize_height and not payload.resize_width):
        raise HTTPException(status_code=400, detail="resize_width and resize_height must be provided together")
    if payload.resize_width is not None and payload.resize_width <= 0:
        raise HTTPException(status_code=400, detail="resize_width must be > 0")
    if payload.resize_height is not None and payload.resize_height <= 0:
        raise HTTPException(status_code=400, detail="resize_height must be > 0")
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
        if source == "youtube":
            try:
                _emit_render_event(
                    channel_code="quick",
                    job_id=quick_job_id,
                    event="render.download.start",
                    level="INFO",
                    message="Downloading YouTube source",
                    step="render.download",
                    context={"url": url},
                )
                downloaded = download_youtube(url, work_dir)
                _emit_render_event(
                    channel_code="quick",
                    job_id=quick_job_id,
                    event="render.download.success",
                    level="INFO",
                    message="YouTube download success",
                    step="render.download",
                    context={"title": downloaded.get("title", ""), "duration": downloaded.get("duration", 0)},
                )
            except Exception as exc:
                _emit_render_event(
                    channel_code="quick",
                    job_id=quick_job_id,
                    event="render.download.error",
                    level="ERROR",
                    message=f"YouTube download failed: {exc}",
                    step="render.download",
                    exception=exc,
                    traceback_text=traceback.format_exc(),
                )
                raise HTTPException(status_code=400, detail=f"Failed to download YouTube URL: {exc}") from exc
            src_path = Path(downloaded["filepath"]).resolve()
            downloaded_title = downloaded.get("title", "")
            duration = int(downloaded.get("duration") or 0)
        else:
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
            "url": url if source == "youtube" else "",
            "path": str(src_path) if source == "local" else "",
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
