
import json
import re
import shutil
import traceback
import uuid
import logging
import subprocess
from urllib.parse import urlparse
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from app.models.schemas import RenderRequest, DownloadHealthRequest, PrepareSourceRequest, QuickProcessRequest
from app.services.db import upsert_job, get_job
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

router = APIRouter(prefix="/api/render", tags=["render"])
logger = logging.getLogger("app.render")

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

_PREVIEW_SESSIONS: dict[str, dict] = {}  # session_id -> {video_path, duration, title, work_dir}
_PREVIEW_DIR = TEMP_DIR / "preview"


def _save_session(session_id: str, data: dict):
    """Persist session to memory + JSON file (survives server restart)."""
    _PREVIEW_SESSIONS[session_id] = data
    try:
        meta_path = Path(data["work_dir"]) / "session.json"
        meta_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _load_session(session_id: str) -> dict | None:
    """Load session from memory or fallback to disk JSON."""
    if session_id in _PREVIEW_SESSIONS:
        return _PREVIEW_SESSIONS[session_id]
    meta_path = _PREVIEW_DIR / session_id / "session.json"
    if meta_path.exists():
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            if Path(data.get("video_path", "")).exists():
                _PREVIEW_SESSIONS[session_id] = data
                return data
        except Exception:
            pass
    return None


def _cleanup_preview_session(session_id: str):
    """Remove preview session from memory and disk after render consumes it."""
    _PREVIEW_SESSIONS.pop(session_id, None)
    preview_dir = _PREVIEW_DIR / session_id
    if preview_dir.exists():
        try:
            shutil.rmtree(preview_dir, ignore_errors=True)
        except Exception:
            pass


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
    """Validate output_dir leaf name. Shared by full validation and session bypass."""
    if not (payload.output_dir or "").strip():
        raise HTTPException(status_code=400, detail="output_dir is required")
    out_path = Path(str(payload.output_dir).strip())
    out_leaf = (out_path.name or "").strip().lower()
    if out_leaf not in {"video_output", "video_out"}:
        raise HTTPException(
            status_code=400,
            detail="output_dir must point to a video output folder named 'video_output' or 'video_out'.",
        )


def _validate_render_source(payload: RenderRequest):
    output_mode = (payload.output_mode or "channel").strip().lower()
    if output_mode not in ("channel", "manual"):
        raise HTTPException(status_code=400, detail="output_mode must be 'channel' or 'manual'")

    # When an editor session is provided, the pipeline uses the session's video_path
    # instead of downloading; skip source-URL/path validation entirely.
    if (getattr(payload, "edit_session_id", None) or "").strip():
        _validate_output_dir(payload)
        return

    channel = (payload.channel_code or "").strip()
    if output_mode == "channel" and not channel:
        raise HTTPException(status_code=400, detail="channel_code is required when output_mode='channel'")
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
    _validate_output_dir(payload)
    if output_mode == "channel":
        out_path = Path(str(payload.output_dir).strip())
        parts = [str(p).strip().lower() for p in out_path.parts if str(p).strip()]
        chan = channel.lower()
        if chan not in parts:
            raise HTTPException(
                status_code=400,
                detail=f"output_dir must be inside selected channel folder '{channel}' (example: D:/data/{channel}/upload/video_output).",
            )


def _probe_video_codec(video_path: Path) -> str:
    """Return the video codec name, e.g. 'h264', 'vp9', 'av1'."""
    cmd = [
        get_ffprobe_bin(),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (r.stdout or "").strip().lower()
    except Exception:
        return ""


def _probe_preview_profile(video_path: Path) -> dict:
    """Return container/video/audio details used to decide browser preview compatibility."""
    cmd = [
        get_ffprobe_bin(),
        "-v", "error",
        "-show_entries", "format=format_name:stream=index,codec_type,codec_name",
        "-of", "json",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        format_name = str((data.get("format") or {}).get("format_name") or "").lower()
        video_codec = ""
        audio_codec = ""
        for stream in streams:
            codec_type = str(stream.get("codec_type") or "").lower()
            codec_name = str(stream.get("codec_name") or "").lower()
            if codec_type == "video" and not video_codec:
                video_codec = codec_name
            elif codec_type == "audio" and not audio_codec:
                audio_codec = codec_name
        return {
            "format_name": format_name,
            "video_codec": video_codec,
            "audio_codec": audio_codec,
        }
    except Exception:
        return {
            "format_name": "",
            "video_codec": _probe_video_codec(video_path),
            "audio_codec": "",
        }


def _is_browser_safe_preview(video_path: Path) -> bool:
    """Return True when the source should play reliably in Chromium without preview transcoding."""
    profile = _probe_preview_profile(video_path)
    container = profile.get("format_name") or ""
    video_codec = profile.get("video_codec") or ""
    audio_codec = profile.get("audio_codec") or ""

    container_ok = any(name in container for name in ("mp4", "mov"))
    video_ok = video_codec in ("h264", "avc", "avc1")
    audio_ok = (not audio_codec) or audio_codec in ("aac", "mp3")
    return container_ok and video_ok and audio_ok


def _ensure_h264_preview(src: Path, work_dir: Path, duration_sec: int = 0) -> Path:
    """
    Reuse the source only when it is already browser-safe for Chromium playback.
    Otherwise generate a cached H.264 preview for the editor.

    Timeout is duration-aware: base 120s + 2s per second of video, capped at 3600s.
    Returns src unchanged when transcoding fails so the caller can still serve it.
    """
    out = work_dir / "preview_h264.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out
    if _is_browser_safe_preview(src):
        return src

    timeout_sec = min(3600, 120 + 2 * max(0, int(duration_sec)))
    profile = _probe_preview_profile(src)
    has_audio = bool(profile.get("audio_codec"))
    logger.info(
        "Transcoding preview to browser-safe H.264 (format=%s video=%s audio=%s duration=%ss timeout=%ss)",
        profile.get("format_name") or "",
        profile.get("video_codec") or "",
        profile.get("audio_codec") or "",
        duration_sec,
        timeout_sec,
    )

    cmd = [
        get_ffmpeg_bin(),
        "-y",
        "-i", str(src),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-vf", "scale='min(1280,iw)':-2",
        "-movflags", "+faststart",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd.append(str(out))

    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout_sec, check=False)
        if out.exists() and out.stat().st_size > 0:
            logger.info("Preview transcode OK (output=%s)", out)
            return out
    except subprocess.TimeoutExpired:
        logger.error(
            "Preview transcode timed out after %ss (src=%s duration=%ss). Falling back to original file.",
            timeout_sec,
            src,
            duration_sec,
        )
    except Exception as exc:
        logger.warning("Preview transcode failed for %s: %s", src, exc)

    try:
        out.unlink(missing_ok=True)
    except Exception:
        pass

    return src


@router.post("/prepare-source")
def prepare_source(payload: PrepareSourceRequest):
    """
    Download YouTube video OR validate local file and return a session_id
    so the frontend can open the editor with a live preview before rendering.
    """
    session_id = str(uuid.uuid4())
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
        mode = (payload.source_mode or "youtube").lower().strip()
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
            source = download_youtube(yt_url, work_dir)
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
            context={"source_mode": (payload.source_mode or "youtube").lower().strip(), "url": (payload.youtube_url or "").strip(), "path": (payload.source_video_path or "").strip()},
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
            context={"source_mode": (payload.source_mode or "youtube").lower().strip(), "url": (payload.youtube_url or "").strip(), "path": (payload.source_video_path or "").strip()},
            exception=exc,
            traceback_text=traceback.format_exc(),
        )
        raise HTTPException(status_code=500, detail=str(exc))


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

    work_dir = Path(session.get("work_dir", ""))
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

    try:
        from app.services.subtitle_engine import get_whisper_model
        model = get_whisper_model("tiny")
        result = model.transcribe(str(video_path), fp16=False, verbose=False)
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
        return {"segments": segments}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {exc}")


def process_render(job_id: str, payload: RenderRequest, resume_mode: bool = False):
    run_render_pipeline(
        job_id=job_id,
        payload=payload,
        resume_mode=resume_mode,
        load_session_fn=_load_session,
        cleanup_session_fn=_cleanup_preview_session,
    )


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
                process_render(child_id, child_payload, False)
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

    submitted = submit_job(batch_id, _run_batch)
    if not submitted:
        raise HTTPException(status_code=409, detail="Render batch is already running")
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


def _run_ffmpeg_checked(cmd: list[str], fail_message: str):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise HTTPException(status_code=500, detail=f"{fail_message}: {detail or 'unknown ffmpeg error'}")
    return proc


def _detect_leading_black_duration(input_path: Path, min_duration: float, threshold: float) -> float:
    """
    Detect black frames only at the beginning and return trim seconds (black_end).
    Returns 0.0 when no leading black intro matches criteria.
    """
    cmd = [
        get_ffmpeg_bin(),
        "-hide_banner",
        "-loglevel", "info",
        "-i", str(input_path),
        "-vf", f"blackdetect=d={min_duration:.3f}:pic_th={threshold:.3f}",
        "-an",
        "-f", "null",
        "-",
    ]
    proc = _run_ffmpeg_checked(cmd, "FFmpeg black-intro detection failed")
    output = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()

    pattern = re.compile(r"black_start:(?P<start>\d+(\.\d+)?)\s+black_end:(?P<end>\d+(\.\d+)?)\s+black_duration:(?P<dur>\d+(\.\d+)?)")
    for match in pattern.finditer(output):
        start = float(match.group("start"))
        end = float(match.group("end"))
        dur = float(match.group("dur"))
        # Trim only if black section starts at beginning.
        if start <= 0.12 and dur >= min_duration:
            return max(0.0, end)
        break
    return 0.0


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
            vf_parts.append((payload.video_filter or "").strip())

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
    _validate_render_source(payload)
    effective_channel = (payload.channel_code or "").strip() or "manual"
    _queue_render_job(job_id, effective_channel, payload, resume_mode=True, queued_message="Resume job queued")
    return {"job_id": job_id, "status": "queued", "resume_mode": True}


@router.get("/jobs/{job_id}")
def get_render_job(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row
