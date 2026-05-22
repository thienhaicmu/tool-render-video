from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

from app.core.config import CHANNELS_DIR, LOGS_DIR
from app.core.stage import STAGE_TO_EVENT, JobPartStage
from app.services.db import upsert_job_part

logger = logging.getLogger("app.render")

_JOB_LOG_DIRS: dict[str, Path] = {}


def _safe_unlink(path: Path):
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _append_json_line(path: Path, entry: dict):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _render_error_code(step: str, message: str, exc: Exception | None = None) -> str:
    text = f"{step} {message} {exc or ''}".lower()
    if "not found" in text or "filenotfounderror" in text:
        return "RN002"
    if "output" in text and ("invalid" in text or "permission" in text or "path" in text):
        return "RN003"
    if "voice" in text or "tts" in text or "narration" in text:
        return "VOICE001"
    if "ffmpeg" in text:
        return "RN004"
    if "scene" in text and ("detect" in text or "detection" in text):
        return "RN005"
    if "trim" in text:
        return "RN006"
    return "RN001"


def _job_log(channel_code: str, job_id: str, message: str, kind: str = "info"):
    if kind == "debug" and os.getenv("RENDER_DEBUG_LOG", "0") != "1":
        return
    line = f"[render][{channel_code}][{job_id[:8]}] {message}"
    try:
        k = (kind or "info").lower()
        if k == "debug":
            logger.debug(line)
        elif k in ("warn", "warning"):
            logger.warning(line)
        elif k == "error":
            logger.error(line)
        else:
            logger.info(line)
    except Exception:
        pass
    log_dir = _JOB_LOG_DIRS.get(job_id) or (CHANNELS_DIR / channel_code / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{job_id}.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.utcnow().isoformat()}Z] [{kind.upper()}] {message}\n")


def _emit_render_event(
    *,
    channel_code: str,
    job_id: str,
    event: str,
    level: str,
    message: str,
    step: str,
    context: dict | None = None,
    exception: Exception | None = None,
    traceback_text: str = "",
    duration_ms: int | None = None,
    error_code: str = "",
):
    lvl = (level or "INFO").upper()
    err_code = str(error_code or "")
    if lvl in {"ERROR", "CRITICAL", "FATAL"} or event.endswith(".error"):
        err_code = err_code or _render_error_code(step, message, exc=exception)
    entry = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "level": lvl,
        "event": event,
        "module": "render",
        "message": message,
        "job_id": job_id,
        "step": step,
        "error_code": err_code,
        "context": context or {},
        "exception": (str(exception) if exception else ""),
        "traceback": traceback_text or "",
        "duration_ms": duration_ms or 0,
    }
    log_dir = _JOB_LOG_DIRS.get(job_id) or (CHANNELS_DIR / channel_code / "logs")
    _append_json_line(log_dir / f"{job_id}.log", entry)
    _append_json_line(LOGS_DIR / "app.log", entry)
    if lvl in {"ERROR", "CRITICAL", "FATAL"}:
        _append_json_line(LOGS_DIR / "error.log", entry)


_PROGRESS_TICK_SEC = 3.0   # how often the timer thread wakes to update progress


def _event_from_stage(stage: str) -> str:
    return STAGE_TO_EVENT.get(stage, "render.start")


def _resolve_job_log_dir(output_dir: Path, output_mode: str, channel_code: str) -> Path:
    out = output_dir.resolve()
    if output_mode == "channel":
        chan = (channel_code or "").strip().lower()
        if chan:
            for p in [out, *out.parents]:
                if p.name.strip().lower() == chan:
                    return p / "logs"
        if out.name.strip().lower() in ("video_output", "video_out"):
            parent = out.parent
            if parent.name.strip().lower() == "upload":
                return parent.parent / "logs"
        return out / "logs"
    return out / "_logs"


def _render_progress_timer(
    stop_event: threading.Event,
    job_id: str,
    part_no: int,
    part_name: str,
    seg: dict,
    output_file: str,
    encode_start: float,
    expected_duration: float,
    channel_code: str = "",
):
    """Background thread that emits linear progress estimates while FFmpeg runs.

    Wakes every _PROGRESS_TICK_SEC seconds and writes an interpolated progress
    value in the 70–99% band to the DB.  Exits cleanly when stop_event is set.

    Design notes:
    - Uses stop_event.wait(timeout) rather than time.sleep so it wakes
      immediately when stop_event.set() is called (no lingering sleep).
    - Clamps at 99% — the caller always writes the authoritative 100% after
      render_part_smart() returns, guaranteeing that the final DB write wins.
    - All exceptions are swallowed; a noisy timer must never crash a render thread.
    """
    from app.orchestration.qa_pipeline import _stall_deadline
    stall_deadline = _stall_deadline(encode_start, expected_duration)
    _stall_suspected_emitted = False
    while not stop_event.wait(timeout=_PROGRESS_TICK_SEC):
        elapsed = time.monotonic() - encode_start
        if expected_duration > 0:
            progress = min(99, 70 + int(30 * elapsed / expected_duration))
        else:
            progress = 85  # unknown duration — park at midpoint

        # Warn once when duration is unknown and render has run for >300 s
        if expected_duration <= 0 and elapsed > 300 and not _stall_suspected_emitted:
            _stall_suspected_emitted = True
            try:
                if channel_code:
                    _emit_render_event(
                        channel_code=channel_code,
                        job_id=job_id,
                        event="render.stall_suspected",
                        level="WARNING",
                        message=f"Render has been running {elapsed:.0f}s with unknown duration",
                        step="render.progress",
                    )
            except Exception:
                pass

        # Hard stall guard: wall-clock deadline exceeded — fail the part and exit
        if not stop_event.is_set() and time.monotonic() > stall_deadline:
            try:
                if channel_code:
                    _emit_render_event(
                        channel_code=channel_code,
                        job_id=job_id,
                        event="render.stall_detected",
                        level="WARNING",
                        message=f"Render stall detected: wall-clock timeout exceeded after {elapsed:.0f}s",
                        step="render.progress",
                    )
                upsert_job_part(
                    job_id, part_no, part_name,
                    JobPartStage.FAILED, progress,
                    seg["start"], seg["end"], seg["duration"],
                    seg.get("viral_score", 0), seg.get("motion_score", 0),
                    seg.get("hook_score", 0),
                    output_file,
                    "Render stall detected: wall-clock timeout exceeded",
                )
            except Exception:
                pass
            stop_event.set()
            break

        try:
            upsert_job_part(
                job_id,
                part_no,
                part_name,
                JobPartStage.RENDERING,
                progress,
                seg["start"],
                seg["end"],
                seg["duration"],
                seg.get("viral_score", 0),
                seg.get("motion_score", 0),
                seg.get("hook_score", 0),
                output_file,
                "Rendering final video",
            )
        except Exception:
            pass  # never let a DB error kill the timer thread
