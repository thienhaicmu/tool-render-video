
import json
import os
import shutil
import traceback
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable
from fastapi import HTTPException
from app.models.schemas import RenderRequest
from app.services.db import upsert_job, update_job_progress, upsert_job_part, list_job_parts
from app.services.channel_service import ensure_channel
from app.services.downloader import download_youtube, slugify
from app.services.scene_detector import detect_scenes
from app.services.segment_builder import build_segments_from_scenes
from app.services.subtitle_engine import transcribe_to_srt, srt_to_ass_bounce, srt_to_ass_karaoke, slice_srt_by_time
from app.services.render_engine import cut_video, render_part_smart
from app.services.viral_scorer import score_segments
from app.services.report_service import append_rows
from app.core.config import TEMP_DIR, CHANNELS_DIR, LOGS_DIR
from app.core.stage import JobStage, JobPartStage, STAGE_TO_EVENT
from app.services.bin_paths import get_ffprobe_bin, get_ffmpeg_bin
from app.services.text_overlay import normalize_text_layers, MAX_TEXT_LAYERS

logger = logging.getLogger("app.render")

HIGH_MOTION_MIN_SCORE = 60
HIGH_MOTION_MIN_KEEP = 3
_JOB_LOG_DIRS: dict[str, Path] = {}


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
    if "ffmpeg" in text:
        return "RN004"
    if "scene" in text and ("detect" in text or "detection" in text):
        return "RN005"
    if "trim" in text:
        return "RN006"
    return "RN001"


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
):
    lvl = (level or "INFO").upper()
    err_code = ""
    if lvl in {"ERROR", "CRITICAL", "FATAL"} or event.endswith(".error"):
        err_code = _render_error_code(step, message, exc=exception)
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


def _validate_text_layers_or_400(payload: RenderRequest) -> list[dict]:
    try:
        raw_layers = [x.model_dump() if hasattr(x, "model_dump") else dict(x) for x in (payload.text_layers or [])]
        if len(raw_layers) > MAX_TEXT_LAYERS:
            raise ValueError(f"text_layers exceeds maximum {MAX_TEXT_LAYERS}")
        return normalize_text_layers(raw_layers)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid text_layers: {exc}") from exc


def _resolve_profile(payload: RenderRequest):
    profile = (payload.render_profile or "quality").lower()
    defaults = {
        # fast: quick turnaround, acceptable quality
        "fast":     {"video_preset": "faster", "video_crf": 22, "whisper_model": "tiny",  "transition_sec": 0.12},
        # balanced: good quality, reasonable speed
        "balanced": {"video_preset": "slow",   "video_crf": 18, "whisper_model": "base",  "transition_sec": 0.25},
        # quality: high quality, slower encode
        "quality":  {"video_preset": "slower", "video_crf": 15, "whisper_model": "small", "transition_sec": 0.35},
        # best: maximum quality, slowest encode — use for final master output
        "best":     {"video_preset": "veryslow","video_crf": 13, "whisper_model": "small", "transition_sec": 0.40},
    }
    picked = defaults.get(profile, defaults["quality"])
    whisper_model = payload.whisper_model
    if (whisper_model or "auto").lower() == "auto":
        whisper_model = picked["whisper_model"]
    return {
        "video_preset": payload.video_preset or picked["video_preset"],
        "video_crf": max(12, min(32, int(payload.video_crf or picked["video_crf"]))),
        "whisper_model": whisper_model,
        "transition_sec": max(0.0, min(1.5, float(payload.transition_sec if payload.transition_sec is not None else picked["transition_sec"]))),
    }


def _probe_video_duration(video_path: Path) -> int:
    cmd = [
        get_ffprobe_bin(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return max(0, int(float((r.stdout or "0").strip() or 0)))
    except Exception:
        return 0


def _reserve_source_path_in_dir(source_dir: Path, slug: str, ext: str = ".mp4") -> Path:
    source_dir.mkdir(parents=True, exist_ok=True)
    base = source_dir / f"{slug}{ext}"
    if not base.exists():
        return base
    idx = 1
    while True:
        candidate = source_dir / f"{slug}_{idx}{ext}"
        if not candidate.exists():
            return candidate
        idx += 1


def _reserve_source_path(channel_code: str, slug: str, ext: str = ".mp4") -> Path:
    return _reserve_source_path_in_dir(CHANNELS_DIR / channel_code / "upload" / "source", slug, ext=ext)


def _safe_unlink(path: Path):
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _sanitize_channel_subdir(value: str | None) -> str:
    raw = (value or "Video").strip().replace("\\", "/")
    raw = raw.strip("/")
    if not raw:
        return "Video"
    parts = [p for p in raw.split("/") if p not in ("", ".", "..")]
    safe = "/".join(parts).strip()
    return safe or "Video"


def _resolve_output_dir(channel_code: str, raw_output_dir: str, render_output_subdir: str | None = None) -> Path:
    raw = (raw_output_dir or "").strip()
    channel_base = (CHANNELS_DIR / channel_code).resolve()
    fallback = channel_base / _sanitize_channel_subdir(render_output_subdir)
    if not raw:
        return fallback

    norm = raw.replace("\\", "/")
    legacy_prefix = f"/data/channels/{channel_code}/"
    legacy_prefix_no_slash = f"data/channels/{channel_code}/"
    if norm.startswith(legacy_prefix):
        rel = norm[len(legacy_prefix):]
        return (channel_base / rel).resolve()
    if norm.startswith(legacy_prefix_no_slash):
        rel = norm[len(legacy_prefix_no_slash):]
        return (channel_base / rel).resolve()
    if norm.startswith("/data/channels/"):
        return fallback

    p = Path(raw)
    if p.is_absolute():
        return p
    return (Path.cwd() / p).resolve()


def run_render_pipeline(
    job_id: str,
    payload: RenderRequest,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
):
    output_mode = (payload.output_mode or "channel").strip().lower()
    effective_channel = (payload.channel_code or "").strip() or "manual"
    started_at = datetime.utcnow()
    if output_mode == "channel":
        ensure_channel(effective_channel)
        if not (payload.render_output_subdir or "").strip():
            raise RuntimeError("render_output_subdir is required")
        output_dir = _resolve_output_dir(effective_channel, payload.output_dir, payload.render_output_subdir)
    else:
        output_dir = Path(payload.output_dir).expanduser()
        if not output_dir.is_absolute():
            output_dir = (Path.cwd() / output_dir).resolve()
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.output.prepare.start",
        level="INFO",
        message="Preparing output directory",
        step="render.output.prepare",
        context={"output_dir": str(output_dir)},
    )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.output.prepare.success",
            level="INFO",
            message="Output directory ready",
            step="render.output.prepare",
            context={"output_dir": str(output_dir)},
        )
    except Exception as output_exc:
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.output.prepare.error",
            level="ERROR",
            message=f"Failed to prepare output directory: {output_exc}",
            step="render.output.prepare",
            context={"output_dir": str(output_dir)},
            exception=output_exc,
            traceback_text=traceback.format_exc(),
        )
        raise
    _JOB_LOG_DIRS[job_id] = _resolve_job_log_dir(output_dir, output_mode, effective_channel)
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    tuned = _resolve_profile(payload)
    retry_count = max(0, min(5, int(payload.retry_count)))
    current_stage = JobStage.STARTING

    def _set_stage(stage: str, progress: int, message: str):
        nonlocal current_stage
        current_stage = stage
        update_job_progress(job_id, stage, progress, message)
        _job_log(effective_channel, job_id, f"[STAGE] {stage} | {message}")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event=_event_from_stage(stage),
            level="INFO",
            message=message,
            step=stage,
            context={"progress_percent": progress},
        )

    _job_log(
        effective_channel,
        job_id,
        f"Render started | resume={resume_mode} | profile={payload.render_profile} | codec={payload.video_codec} | reup_mode={payload.reup_mode} | source_mode={payload.source_mode} | output_mode={output_mode}",
    )
    try:
        normalized_text_layers = _validate_text_layers_or_400(payload)
    except Exception as layer_exc:
        normalized_text_layers = []
        _job_log(effective_channel, job_id, f"Text layer parse warning: {layer_exc}", kind="warning")
    _job_log(
        effective_channel,
        job_id,
        f"Text overlay layers accepted: {len(normalized_text_layers)}",
    )
    for layer_idx, layer in enumerate(normalized_text_layers, start=1):
        _job_log(
            effective_channel,
            job_id,
            f"Text layer {layer_idx}: order={layer.get('order', layer_idx-1)} "
            f"pos={layer.get('position', 'bottom-center')} "
            f"xy={float(layer.get('x_percent', 50) or 50):.1f}%,{float(layer.get('y_percent', 90) or 90):.1f}% "
            f"time={float(layer.get('start_time', 0) or 0):.2f}->{float(layer.get('end_time', 0) or 0):.2f}",
            kind="debug",
        )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.text_layers.accepted",
        level="INFO",
        message=f"Accepted {len(normalized_text_layers)} text layer(s)",
        step="render.text_layers",
        context={"layer_count": len(normalized_text_layers)},
    )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.start",
        level="INFO",
        message="Render started",
        step="render.start",
        context={
            "resume_mode": bool(resume_mode),
            "profile": payload.render_profile,
            "codec": payload.video_codec,
            "source_mode": payload.source_mode,
            "output_mode": output_mode,
        },
    )
    upsert_job(
        job_id,
        "render",
        effective_channel,
        "running",
        payload.model_dump(),
        {},
        stage=JobStage.STARTING,
        progress_percent=1,
        message="Resuming render job" if resume_mode else "Initializing render job",
    )
    try:
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.start",
            level="INFO",
            message="Preparing source",
            step="render.prepare_source",
            context={"source_mode": payload.source_mode},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.input.validate.start",
            level="INFO",
            message="Validating render input",
            step="render.input.validate",
        )
        _set_stage(JobStage.DOWNLOADING, 5, "Preparing source video")
        edit_session_id = (getattr(payload, "edit_session_id", None) or "").strip()
        sess = load_session_fn(edit_session_id) if edit_session_id else None
        if edit_session_id and not sess:
            raise RuntimeError(
                f"Editor session '{edit_session_id}' not found — "
                "the session may have expired or the server was restarted. "
                "Please re-open the editor to re-prepare the source."
            )
        detected_source_mode = "session" if sess else ((payload.source_mode or "youtube").lower())
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.detect_input",
            level="INFO",
            message=f"Detecting source type: {detected_source_mode}",
            step="render.prepare_source.detect_input",
            context={"source_mode": detected_source_mode},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.validate_input",
            level="INFO",
            message="Validating source input",
            step="render.prepare_source.validate_input",
        )
        if sess:
            source_path = Path(sess["video_path"])
            if not source_path.exists():
                raise RuntimeError(f"Editor session video not found: {source_path}")
            source = {
                "title": sess.get("title", source_path.stem),
                "slug": slugify(sess.get("title", source_path.stem)),
                "duration": sess.get("duration") or _probe_video_duration(source_path),
                "filepath": str(source_path),
            }
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"source_path": str(source_path), "work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting editor-session source strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "editor_session"},
            )
            _job_log(effective_channel, job_id, f"Reusing editor session video: {source_path}")
        elif (payload.source_mode or "youtube").lower() == "local":
            source_path = Path(payload.source_video_path or "").expanduser().resolve()
            if not source_path.exists() or not source_path.is_file():
                raise RuntimeError(f"Local source video not found: {source_path}")
            source = {
                "title": source_path.stem.replace("_", " ").replace("-", " "),
                "slug": slugify(source_path.stem),
                "duration": _probe_video_duration(source_path),
                "filepath": str(source_path),
            }
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"source_path": str(source_path), "work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting local source strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "local_source"},
            )
            _job_log(effective_channel, job_id, f"Local source selected: {source_path}")
        else:
            yt_url = (payload.youtube_url or "").strip() or (payload.youtube_urls[0] if payload.youtube_urls else "")
            _job_log(effective_channel, job_id, f"YouTube source URL: {yt_url}")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting YouTube download strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "youtube_download", "url": yt_url},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.download.start",
                level="INFO",
                message="Downloading source from YouTube",
                step="render.download",
                context={"url": yt_url},
            )
            source = download_youtube(yt_url, work_dir)
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.download.success",
                level="INFO",
                message="YouTube source downloaded",
                step="render.download",
                context={
                    "title": source.get("title", ""),
                    "duration": source.get("duration", 0),
                    "format": source.get("selected_format", ""),
                },
            )
            _job_log(
                effective_channel,
                job_id,
                f"Downloaded source: {source['title']} ({source['duration']}s) | "
                f"height={source.get('selected_height', 0)} fps={source.get('selected_fps', 0)} "
                f"format={source.get('selected_format', '')}",
            )
            source_path = Path(source["filepath"])
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.input.validate.success",
            level="INFO",
            message="Render input validated",
            step="render.input.validate",
            context={"source_path": str(source_path)},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.success",
            level="INFO",
            message="Source prepared successfully",
            step="render.prepare_source.success",
            context={"source_mode": detected_source_mode, "source_path": str(source_path)},
        )

        # Apply editor edits: trim and/or volume adjustment
        trim_in = float(getattr(payload, "edit_trim_in", 0) or 0)
        trim_out = float(getattr(payload, "edit_trim_out", 0) or 0)
        edit_volume = float(getattr(payload, "edit_volume", 1.0) or 1.0)
        needs_trim = trim_in > 0.5 or (trim_out > 0.5 and trim_out < source["duration"] - 0.5)
        needs_volume = abs(edit_volume - 1.0) > 0.02
        if needs_trim or needs_volume:
            edited_path = work_dir / f"edited_{source_path.stem}.mp4"
            cmd = [get_ffmpeg_bin(), "-y"]
            if trim_in > 0.5:
                cmd += ["-ss", f"{trim_in:.3f}"]
            cmd += ["-i", str(source_path)]
            if needs_trim and trim_out > 0.5 and trim_out < source["duration"] - 0.5:
                duration_t = trim_out - (trim_in if trim_in > 0.5 else 0)
                cmd += ["-t", f"{max(1.0, duration_t):.3f}"]
            if needs_volume:
                cmd += ["-af", f"volume={edit_volume:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k"]
            else:
                cmd += ["-c:v", "copy", "-c:a", "copy"]
            cmd += ["-avoid_negative_ts", "make_zero", str(edited_path)]
            _job_log(effective_channel, job_id, f"Applying edits: trim_in={trim_in:.1f}s trim_out={trim_out:.1f}s volume={edit_volume:.2f}")
            subprocess.run(cmd, check=True, capture_output=True)
            new_dur = _probe_video_duration(edited_path)
            source["duration"] = new_dur or max(1, source["duration"] - trim_in)
            source_path = edited_path
            source["filepath"] = str(edited_path)
            _job_log(effective_channel, job_id, f"Edits applied → {edited_path} | new_duration={source['duration']}s")

        if payload.keep_source_copy:
            ext = source_path.suffix or ".mp4"
            keep_source_dir = output_dir / "source"
            # If output is a typical "video_output/video_out" folder, keep source as sibling under upload/source.
            if output_dir.name.lower() in ("video_output", "video_out"):
                keep_source_dir = output_dir.parent / "source"
            keep_path = _reserve_source_path_in_dir(keep_source_dir, source["slug"], ext=ext)
            if not keep_path.exists():
                # Move instead of copy when source is in temp dir (instant on same drive, saves I/O + disk)
                is_temp_source = str(source_path).startswith(str(TEMP_DIR))
                if is_temp_source:
                    try:
                        shutil.move(str(source_path), str(keep_path))
                        _job_log(effective_channel, job_id, f"Source moved (zero-copy) to: {keep_path}")
                    except Exception:
                        shutil.copy2(source_path, keep_path)
                        _job_log(effective_channel, job_id, f"Source copied to: {keep_path}")
                else:
                    shutil.copy2(source_path, keep_path)
                    _job_log(effective_channel, job_id, f"Source copied to: {keep_path}")
            source_path = keep_path

        _set_stage(JobStage.SCENE_DETECTION, 15, "Detecting scenes")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.scene.detect.start",
            level="INFO",
            message="Detecting scenes",
            step="render.scene.detect",
        )
        scenes = detect_scenes(str(source_path)) if payload.auto_detect_scene else []
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.scene.detect.success",
            level="INFO",
            message=f"Detected {len(scenes)} scenes",
            step="render.scene.detect",
            context={"scene_count": len(scenes)},
        )
        _job_log(effective_channel, job_id, f"Scene detection done: {len(scenes)} scenes")

        _set_stage(JobStage.SEGMENT_BUILDING, 25, "Building smart segments")
        segments = build_segments_from_scenes(scenes, source["duration"], payload.min_part_sec, payload.max_part_sec)
        scored = score_segments(segments, scenes)
        # Fixed mode: High motion priority (no UI option). Keep enough parts to avoid empty output.
        high_motion = [s for s in scored if int(s.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE]
        if len(high_motion) >= HIGH_MOTION_MIN_KEEP:
            scored = high_motion
        # Sort by viral/motion score first for selection (top N), then re-order for output numbering
        scored.sort(key=lambda x: (int(x.get("motion_score", 0)), int(x.get("viral_score", 0))), reverse=True)
        if payload.max_export_parts and payload.max_export_parts > 0:
            scored = scored[:payload.max_export_parts]
        # Re-order for output numbering: timeline = chronological, viral = by score
        part_order = str(getattr(payload, "part_order", "viral") or "viral").strip().lower()
        if part_order == "timeline":
            scored.sort(key=lambda x: float(x.get("start", 0)))
            _job_log(effective_channel, job_id, f"Part order: timeline (chronological)")
        else:
            _job_log(effective_channel, job_id, f"Part order: viral score (highest first)")

        if not scored:
            raise RuntimeError("No exportable segments were created")

        total_parts = len(scored)
        rows = []
        outputs = []
        full_srt = work_dir / f"{source['slug']}_full.srt"
        existing_parts = {int(x["part_no"]): x for x in list_job_parts(job_id)}
        _job_log(effective_channel, job_id, f"Segment building done: {total_parts} parts")

        subtitle_cutoff = payload.subtitle_viral_min_score
        subtitle_top_count = max(1, int(total_parts * max(0.1, min(1.0, float(payload.subtitle_viral_top_ratio)))))
        if scored:
            ranked_scores = sorted([int(s.get("viral_score", 0)) for s in scored], reverse=True)
            subtitle_cutoff = max(subtitle_cutoff, ranked_scores[min(subtitle_top_count - 1, len(ranked_scores) - 1)])
        _job_log(effective_channel, job_id, f"Subtitle viral cutoff={subtitle_cutoff}, top_count={subtitle_top_count}")

        subtitle_enabled_by_idx = {}
        for idx, seg in enumerate(scored, start=1):
            subtitle_enabled_by_idx[idx] = payload.add_subtitle and (
                (not payload.subtitle_only_viral_high) or int(seg.get("viral_score", 0)) >= int(subtitle_cutoff)
            )
        if payload.add_subtitle and not any(subtitle_enabled_by_idx.values()):
            # Safety fallback: avoid "no subtitle at all" when viral gates are too strict.
            for idx in range(1, total_parts + 1):
                subtitle_enabled_by_idx[idx] = True
            _job_log(
                effective_channel,
                job_id,
                "No parts passed subtitle viral filters; fallback enabled subtitles for all parts",
                kind="warning",
            )

        if payload.add_subtitle and any(subtitle_enabled_by_idx.values()):
            _set_stage(JobStage.TRANSCRIBING_FULL, 28, "Transcribing full video once")
            if not (payload.resume_from_last and full_srt.exists() and full_srt.stat().st_size > 0):
                transcribe_to_srt(str(source_path), str(full_srt), model_name=tuned["whisper_model"], retry_count=retry_count, highlight_per_word=payload.highlight_per_word)
                _job_log(effective_channel, job_id, f"Full transcription done with model={tuned['whisper_model']}")
            else:
                _job_log(effective_channel, job_id, "Reuse existing full transcription", kind="debug")

        for idx, seg in enumerate(scored, start=1):
            existing = existing_parts.get(idx, {})
            existing_status = (existing.get("status") or "").lower()
            if existing_status == "done" and payload.resume_from_last:
                continue
            upsert_job_part(
                job_id=job_id,
                part_no=idx,
                part_name=f"part_{idx:03d}",
                status=JobPartStage.QUEUED,
                progress_percent=0,
                start_sec=seg["start"],
                end_sec=seg["end"],
                duration=seg["duration"],
                viral_score=seg.get("viral_score", 0),
                motion_score=seg.get("motion_score", 0),
                hook_score=seg.get("hook_score", 0),
            )

        def _process_one_part(idx: int, seg: dict):
            raw_part = work_dir / f"{source['slug']}_part_{idx:03d}_raw.mp4"
            srt_part = work_dir / f"{source['slug']}_part_{idx:03d}.srt"
            ass_part = work_dir / f"{source['slug']}_part_{idx:03d}.ass"
            final_part = output_dir / f"{source['slug']}_part_{idx:03d}.mp4"
            part_name = f"{source['slug']}_part_{idx:03d}.mp4"
            _job_log(effective_channel, job_id, f"Part {idx}/{total_parts} start", kind="debug")

            if payload.resume_from_last and final_part.exists() and final_part.stat().st_size > 0:
                upsert_job_part(job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Skipped (already rendered)")
                _job_log(effective_channel, job_id, f"Part {idx} skipped: final output already exists", kind="debug")
                return {"idx": idx, "output": str(final_part), "row": None, "skipped": True}

            upsert_job_part(job_id, idx, part_name, JobPartStage.CUTTING, 10, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Cutting raw part")
            if not (payload.resume_from_last and raw_part.exists() and raw_part.stat().st_size > 0):
                cut_video(str(source_path), str(raw_part), seg["start"], seg["end"], retry_count=retry_count)
                _job_log(effective_channel, job_id, f"Part {idx} cut done", kind="debug")
            else:
                _job_log(effective_channel, job_id, f"Part {idx} cut skipped (raw exists)", kind="debug")

            part_subtitle_enabled = subtitle_enabled_by_idx.get(idx, False)
            if payload.add_subtitle and not part_subtitle_enabled:
                _job_log(effective_channel, job_id, f"Part {idx} subtitle skipped (viral={int(seg.get('viral_score', 0))} < cutoff={int(subtitle_cutoff)})")

            if part_subtitle_enabled:
                upsert_job_part(job_id, idx, part_name, JobPartStage.TRANSCRIBING, 35, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Preparing subtitle")
                needs_srt = not (payload.resume_from_last and srt_part.exists() and srt_part.stat().st_size > 0)
                needs_ass = not (payload.resume_from_last and ass_part.exists() and ass_part.stat().st_size > 0)
                if needs_srt:
                    slice_srt_by_time(str(full_srt), str(srt_part), seg["start"], seg["end"], rebase_to_zero=True)
                    _job_log(effective_channel, job_id, f"Part {idx} subtitle sliced from full transcript", kind="debug")
                if needs_ass:
                    if payload.subtitle_style == "pro_karaoke":
                        from app.services.subtitle_engine import _hex_to_ass
                        srt_to_ass_karaoke(
                            str(srt_part), str(ass_part),
                            scale_y=payload.frame_scale_y,
                            font_size=getattr(payload, "sub_font_size", 46),
                            font_name=getattr(payload, "sub_font", "Bungee"),
                            margin_v=getattr(payload, "sub_margin_v", 170),
                            base_color=_hex_to_ass(getattr(payload, "sub_color", "#FFFFFF")),
                            highlight_color=_hex_to_ass(getattr(payload, "sub_highlight", "#FFFF00")),
                            outline_size=getattr(payload, "sub_outline", 3),
                        )
                    else:
                        srt_to_ass_bounce(
                            str(srt_part),
                            str(ass_part),
                            subtitle_style=payload.subtitle_style,
                            scale_y=payload.frame_scale_y,
                            highlight_per_word=payload.highlight_per_word,
                            font_name=getattr(payload, "sub_font", "Bungee"),
                            margin_v=getattr(payload, "sub_margin_v", 170),
                        )
                    _job_log(effective_channel, job_id, f"Part {idx} subtitle style rendered: {payload.subtitle_style}", kind="debug")
            else:
                _job_log(effective_channel, job_id, f"Part {idx} subtitle disabled", kind="debug")

            overlay_title = (payload.title_overlay_text or "").strip() or source["title"]
            upsert_job_part(job_id, idx, part_name, JobPartStage.RENDERING, 70, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Rendering final video")
            render_part_smart(
                str(raw_part), str(final_part), str(ass_part) if part_subtitle_enabled else None, overlay_title if payload.add_title_overlay else "",
                payload.aspect_ratio, payload.frame_scale_x, payload.frame_scale_y,
                payload.motion_aware_crop,
                reframe_mode=payload.reframe_mode,
                add_subtitle=part_subtitle_enabled,
                add_title_overlay=payload.add_title_overlay,
                effect_preset=payload.effect_preset,
                transition_sec=tuned["transition_sec"],
                video_codec=payload.video_codec,
                video_crf=tuned["video_crf"],
                video_preset=tuned["video_preset"],
                audio_bitrate=payload.audio_bitrate,
                retry_count=retry_count,
                encoder_mode=payload.encoder_mode,
                output_fps=payload.output_fps,
                reup_mode=payload.reup_mode,
                reup_overlay_enable=payload.reup_overlay_enable,
                reup_overlay_opacity=payload.reup_overlay_opacity,
                reup_bgm_enable=payload.reup_bgm_enable,
                reup_bgm_path=payload.reup_bgm_path,
                reup_bgm_gain=payload.reup_bgm_gain,
                playback_speed=float(payload.playback_speed or 1.07),
                text_layers=normalized_text_layers,
            )
            if normalized_text_layers:
                _job_log(
                    effective_channel,
                    job_id,
                    f"Applied {len(normalized_text_layers)} text layer(s) on part {idx}/{total_parts}",
                    kind="debug",
                )
            _job_log(effective_channel, job_id, f"Part {idx}/{total_parts} done", kind="info")

            upsert_job_part(job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Completed")
            row = [job_id, effective_channel, source["title"], idx, seg["start"], seg["end"], seg["duration"], seg["viral_score"], seg["priority_rank"], str(final_part)]
            if payload.cleanup_temp_files:
                _safe_unlink(raw_part)
                _safe_unlink(srt_part)
                _safe_unlink(ass_part)
            return {"idx": idx, "output": str(final_part), "row": row, "skipped": False}

        heavy_pipeline = bool(payload.motion_aware_crop or payload.add_subtitle or payload.reup_mode)
        mode = (payload.encoder_mode or "auto").lower()
        cpu_total = os.cpu_count() or 2

        # Adaptive hardware cap:
        #  - CPU encoder: each ffmpeg process consumes many threads; allow ~1 per 4 cores
        #  - NVENC/auto: GPU handles encode; limit by motion-analysis CPU and I/O
        if mode == "cpu":
            hw_cap = max(1, min(3, cpu_total // 4))
        else:
            hw_cap = max(1, min(4, cpu_total // 2))
        # Heavy pipeline (motion-crop / subtitle / reup): halve the cap to avoid CPU saturation
        if heavy_pipeline:
            hw_cap = max(1, hw_cap // 2)

        # max_parallel_parts == 0 means "adaptive / let backend decide"
        # max_parallel_parts >= 1 means user ceiling — honour it but never exceed hw_cap
        user_req = int(payload.max_parallel_parts or 0)
        if user_req >= 1:
            max_workers = max(1, min(user_req, hw_cap))
        else:
            max_workers = hw_cap

        _job_log(
            effective_channel, job_id,
            f"Adaptive workers={max_workers} "
            f"(cpu={cpu_total}, mode={mode}, heavy={heavy_pipeline}, "
            f"hw_cap={hw_cap}, user_req={user_req})",
        )
        completed_parts = 0
        failed_parts = []
        _set_stage(JobStage.RENDERING_PARALLEL if max_workers > 1 else JobStage.RENDERING, 30, f"Rendering parts 0/{total_parts}")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.ffmpeg.start",
            level="INFO",
            message="Running ffmpeg render",
            step="render.ffmpeg",
            context={"total_parts": total_parts, "workers": max_workers},
        )
        if normalized_text_layers:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.text_layers.apply",
                level="INFO",
                message="Applying text overlay layers during render",
                step="render.text_layers",
                context={"layer_count": len(normalized_text_layers), "total_parts": total_parts},
            )

        if max_workers == 1:
            for idx, seg in enumerate(scored, start=1):
                try:
                    result = _process_one_part(idx, seg)
                    if result["output"]:
                        outputs.append(result["output"])
                    if result["row"]:
                        rows.append(result["row"])
                except Exception as part_err:
                    failed_parts.append((idx, str(part_err)))
                    upsert_job_part(
                        job_id,
                        idx,
                        f"{source['slug']}_part_{idx:03d}.mp4",
                        JobPartStage.FAILED,
                        100,
                        seg["start"],
                        seg["end"],
                        seg["duration"],
                        seg.get("viral_score", 0),
                        seg.get("motion_score", 0),
                        seg.get("hook_score", 0),
                        "",
                        f"Failed: {part_err}",
                    )
                    _job_log(effective_channel, job_id, f"Part {idx}/{total_parts} failed: {part_err}")
                completed_parts += 1
                progress = 30 + int((completed_parts / total_parts) * 60)
                _set_stage(JobStage.RENDERING, progress, f"Processed {completed_parts}/{total_parts} parts")
        else:
            future_map = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for idx, seg in enumerate(scored, start=1):
                    future_map[executor.submit(_process_one_part, idx, seg)] = idx

                for future in as_completed(future_map):
                    idx = future_map[future]
                    seg = scored[idx - 1]
                    try:
                        result = future.result()
                        if result["output"]:
                            outputs.append(result["output"])
                        if result["row"]:
                            rows.append(result["row"])
                    except Exception as part_err:
                        failed_parts.append((idx, str(part_err)))
                        upsert_job_part(
                            job_id,
                            idx,
                            f"{source['slug']}_part_{idx:03d}.mp4",
                            JobPartStage.FAILED,
                            100,
                            seg["start"],
                            seg["end"],
                            seg["duration"],
                            seg.get("viral_score", 0),
                            seg.get("motion_score", 0),
                            seg.get("hook_score", 0),
                            "",
                            f"Failed: {part_err}",
                        )
                        _job_log(effective_channel, job_id, f"Part {idx}/{total_parts} failed: {part_err}")
                    completed_parts += 1
                    progress = 30 + int((completed_parts / total_parts) * 60)
                    _set_stage(JobStage.RENDERING_PARALLEL, progress, f"Processed {completed_parts}/{total_parts} parts")

        if failed_parts and not outputs:
            raise RuntimeError(f"All parts failed ({len(failed_parts)}/{total_parts})")
        if failed_parts:
            _job_log(effective_channel, job_id, f"Partial success: {len(outputs)} done, {len(failed_parts)} failed")

        rows.sort(key=lambda x: int(x[3]))
        outputs = sorted(outputs)
        _set_stage(JobStage.WRITING_REPORT, 95, "Writing render report")
        report_path = output_dir / "render_report.xlsx"
        append_rows(report_path, ["job_id", "channel_code", "video_title", "part_no", "start", "end", "duration", "viral_score", "priority_rank", "output_file"], rows)
        _job_log(effective_channel, job_id, f"Report written: {report_path}")
        upsert_job(job_id, "render", effective_channel, "completed", payload.model_dump(), {"outputs": outputs, "segments": scored}, stage=JobStage.DONE, progress_percent=100, message="Render completed")
        _job_log(effective_channel, job_id, f"Render completed with {len(outputs)}/{total_parts} outputs")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.ffmpeg.success",
            level="INFO",
            message="FFmpeg render completed",
            step="render.ffmpeg",
            context={"outputs": len(outputs), "total_parts": total_parts},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.complete",
            level="INFO",
            message="Render success",
            step="render.complete",
            duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            context={"outputs": len(outputs), "total_parts": total_parts},
        )
    except Exception as e:
        fail_message = f"Failed at step '{current_stage}': {e}"
        tb = traceback.format_exc()
        _job_log(effective_channel, job_id, f"[ERROR_STEP] {current_stage}")
        _job_log(effective_channel, job_id, f"Render failed: {e}")
        _job_log(effective_channel, job_id, tb)
        if current_stage == JobStage.SCENE_DETECTION:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.scene.detect.error",
                level="ERROR",
                message=f"Scene detection failed: {e}",
                step="render.scene.detect",
                exception=e,
                traceback_text=tb,
            )
        if current_stage == JobStage.DOWNLOADING:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.download.error",
                level="ERROR",
                message=f"Source download failed: {e}",
                step="render.download",
                exception=e,
                traceback_text=tb,
            )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.error",
            level="ERROR",
            message=fail_message,
            step=current_stage,
            exception=e,
            traceback_text=tb,
            duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            context={"current_stage": current_stage, "source_mode": payload.source_mode, "youtube_url": (payload.youtube_url or ""), "source_video_path": (payload.source_video_path or "")},
        )
        if current_stage in {JobStage.STARTING, JobStage.DOWNLOADING}:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.error",
                level="ERROR",
                message=f"Source preparation failed: {e}",
                step="render.prepare_source.error",
                exception=e,
                traceback_text=tb,
                context={"current_stage": current_stage, "source_mode": payload.source_mode, "youtube_url": (payload.youtube_url or ""), "source_video_path": (payload.source_video_path or "")},
            )
        upsert_job(
            job_id,
            "render",
            effective_channel,
            "failed",
            payload.model_dump(),
            {"error": str(e), "failed_step": current_stage},
            stage=JobStage.FAILED,
            progress_percent=100,
            message=fail_message,
        )
        return
    finally:
        if payload.cleanup_temp_files:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
                _job_log(effective_channel, job_id, "Temporary files cleaned")
            except Exception as cleanup_err:
                _job_log(effective_channel, job_id, f"Temp cleanup warning: {cleanup_err}")
        # Cleanup preview session (video already moved/copied to output)
        if edit_session_id:
            cleanup_session_fn(edit_session_id)
        _JOB_LOG_DIRS.pop(job_id, None)
