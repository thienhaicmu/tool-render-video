"""Source-preview / preview-session endpoints (audit FINDING-A03 prepare bucket).

Covers the 4 endpoints used by the FE's "Source" step of the render
workflow: prepare-source, cancel session, stream the H.264 preview,
and serve a Whisper-tiny transcript for the editor subtitle preview.
"""
from __future__ import annotations

import json
import logging
import subprocess
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.core.config import TEMP_DIR
from app.features.render.engine.pipeline.render_pipeline import (
    _emit_render_event,
    _probe_video_duration,
)
from app.features.render.engine.preview.ffmpeg_probers import _ensure_h264_preview
from app.features.render.engine.preview.session_service import (
    _cleanup_preview_session,
    _load_session,
    _save_session,
)
from app.models.schemas import PrepareSourceRequest
from app.services.bin_paths import get_ffmpeg_bin

from ._common import _UUID_RE

router = APIRouter(tags=["render"])
logger = logging.getLogger("app.render")

# Guards concurrent preview-transcript requests for the same session.
# Key = session_id, Value = threading.Lock held while Whisper is running.
_transcript_locks: dict[str, threading.Lock] = {}
_transcript_locks_mu = threading.Lock()


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
            "video_path": str(src),            # original used for render
            "preview_path": str(preview_path),  # h264 used for browser preview
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

    # Prefer preview_path (H.264 transcoded), fall back to video_path.
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

    Result is cached in the session work_dir so repeat calls are instant.
    """
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

        # Extract audio to WAV first — avoids tensor-shape errors that occur when
        # Whisper reads 60fps or high-bitrate video containers directly.
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

        # openai-whisper's model.transcribe() mutates KV-cache state on the
        # shared module-level singleton model. Without serialization across
        # concurrent sessions, a second call inherits stale K/V tensors from
        # the first → PyTorch broadcast error "tensor a (N) vs tensor b (3)
        # at non-singleton dimension 3" inside MultiHeadAttention.
        # Use the module-level transcribe lock that adapter callers already
        # rely on (whisper._get_transcribe_lock) to serialize on model_name.
        from app.features.render.engine.subtitle.transcription.whisper import (
            get_whisper_model,
            _get_transcribe_lock,
        )
        model = get_whisper_model("tiny")
        with _get_transcribe_lock("tiny"):
            # Hallucination defense (mirrors engine/subtitle/transcription/whisper.py):
            # disable previous-text conditioning + temperature fallback schedule
            # so the decoder breaks out of phantom-token loops instead of
            # spinning forever on silence/music segments.
            result = model.transcribe(
                str(audio_path),
                fp16=False,
                verbose=False,
                condition_on_previous_text=False,
                temperature=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            )
        segments = [
            {
                "start": round(float(s["start"]), 3),
                "end":   round(float(s["end"]), 3),
                "text":  str(s.get("text", "")).strip(),
            }
            for s in result.get("segments", [])
            if str(s.get("text", "")).strip()
        ]
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump(segments, fh)
        # Remove temp audio — cache_path now holds the result.
        audio_path.unlink(missing_ok=True)
        return {"segments": segments}
    except Exception as exc:
        logger.error("preview-transcript failed for %s: %s", session_id, exc)
        return {"segments": [], "status": "error", "detail": str(exc)}
    finally:
        lock.release()
        # Clean up the lock entry once done so it doesn't grow unbounded.
        with _transcript_locks_mu:
            _transcript_locks.pop(session_id, None)
