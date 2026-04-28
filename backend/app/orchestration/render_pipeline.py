
import json
import os
import shutil
import threading
import time
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
from app.services.subtitle_engine import transcribe_to_srt, srt_to_ass_bounce, srt_to_ass_karaoke, slice_srt_by_time, slice_srt_to_text, has_audio_stream, apply_market_line_break_to_srt
from app.services.render_engine import cut_video, render_part_smart, nvenc_available, resolve_ffmpeg_threads
from app.services.viral_scorer import score_segments
from app.services.viral_scoring import score_part_for_market as _mv_score_part
from app.services.report_service import append_rows
from app.core.config import TEMP_DIR, CHANNELS_DIR, LOGS_DIR
from app.core.stage import JobStage, JobPartStage, STAGE_TO_EVENT
from app.services.bin_paths import get_ffprobe_bin, get_ffmpeg_bin
from app.services.text_overlay import normalize_text_layers, MAX_TEXT_LAYERS
from app.services.tts_service import generate_narration_mp3
from app.services.audio_mix_service import mix_narration_audio
from app.services.translation_service import translate_srt_file

logger = logging.getLogger("app.render")


_PLAY_RES_Y_MAP = {"9:16": 1920, "1:1": 1080, "3:4": 1440, "4:5": 1440, "16:9": 1080}

def _aspect_play_res_y(aspect_ratio: str) -> int:
    ar = (aspect_ratio or "").strip()
    val = _PLAY_RES_Y_MAP.get(ar)
    if val is None:
        logger.warning("_aspect_play_res_y: unrecognised aspect_ratio=%r, defaulting to 1440", ar)
        return 1440
    return val

_PROGRESS_TICK_SEC = 3.0   # how often the timer thread wakes to update progress

# ---------------------------------------------------------------------------
# Resource throttling
# ---------------------------------------------------------------------------
# JOB_SEMAPHORE caps how many render pipelines can be in the FFmpeg-encode
# section simultaneously.  This prevents CPU saturation when multiple jobs
# are dispatched by the scheduler at the same time.
# Override with MAX_RENDER_JOBS env var (e.g. MAX_RENDER_JOBS=3 for 32-core).
_JOB_SEM_VALUE: int = max(1, int(os.getenv("MAX_RENDER_JOBS", "2")))
JOB_SEMAPHORE = threading.Semaphore(_JOB_SEM_VALUE)
_render_active_lock = threading.Lock()
_render_active_count: list[int] = [0]   # mutable int; guarded by _render_active_lock


def _apply_subtitle_edits_to_srt(srt_path: str, edits: list) -> None:
    """Patch specific SRT blocks in-place with user-supplied text.

    Matches by index (0-based segment position in file).  For each edit,
    verifies that the block's start-time is within 0.5 s of the stored value
    to guard against offset drift.  On any mismatch or error the edit is
    silently skipped and the original block is preserved.
    """
    import re as _re
    if not edits:
        return
    edit_map = {}
    for e in edits:
        try:
            edit_map[int(e['index'])] = e
        except (KeyError, TypeError, ValueError):
            pass
    if not edit_map:
        return

    _srt_ts_re = _re.compile(
        r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})'
    )

    def _ts_to_sec(h, m, s, ms):
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

    try:
        raw = Path(srt_path).read_text(encoding='utf-8', errors='replace')
    except Exception:
        return

    blocks = _re.split(r'\n{2,}', raw.strip())
    changed = False
    out_blocks = []
    for blk_idx, blk in enumerate(blocks):
        lines = blk.strip().splitlines()
        if blk_idx in edit_map and len(lines) >= 3:
            edit = edit_map[blk_idx]
            ts_match = _srt_ts_re.search(blk)
            if ts_match:
                blk_start = _ts_to_sec(*ts_match.groups()[:4])
                try:
                    expected_start = float(edit.get('start', blk_start))
                except (TypeError, ValueError):
                    expected_start = blk_start
                if abs(blk_start - expected_start) <= 0.5:
                    seq_line = lines[0]
                    ts_line  = lines[1]
                    new_blk  = f"{seq_line}\n{ts_line}\n{str(edit['text']).strip()}"
                    out_blocks.append(new_blk)
                    changed = True
                    continue
        out_blocks.append(blk)

    if changed:
        try:
            Path(srt_path).write_text('\n\n'.join(out_blocks) + '\n', encoding='utf-8')
        except Exception as exc:
            logger.warning("subtitle_edits: failed to write patched SRT (%s): %s", srt_path, exc)


def _render_progress_timer(
    stop_event: threading.Event,
    job_id: str,
    part_no: int,
    part_name: str,
    seg: dict,
    output_file: str,
    encode_start: float,
    expected_duration: float,
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
    while not stop_event.wait(timeout=_PROGRESS_TICK_SEC):
        elapsed = time.monotonic() - encode_start
        if expected_duration > 0:
            progress = min(99, 70 + int(30 * elapsed / expected_duration))
        else:
            progress = 85  # unknown duration — park at midpoint
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
    if "voice" in text or "tts" in text or "narration" in text:
        return "VOICE001"
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
        "fast":     {"video_preset": "veryfast", "video_crf": 23, "whisper_model": "tiny",  "transition_sec": 0.10},
        # balanced: good quality/speed tradeoff — medium is ~3-4x faster than slow with <5% quality delta
        "balanced": {"video_preset": "medium",   "video_crf": 18, "whisper_model": "base",  "transition_sec": 0.25},
        # quality: high quality — slow preset gives meaningful gains over medium for large screens
        "quality":  {"video_preset": "slow",     "video_crf": 15, "whisper_model": "small", "transition_sec": 0.35},
        # best: maximum quality, slowest encode — use for final master output
        "best":     {"video_preset": "slower",   "video_crf": 13, "whisper_model": "small", "transition_sec": 0.40},
    }
    picked = defaults.get(profile, defaults["quality"])
    if payload.video_preset:
        logger.info("profile_override_used: video_preset=%s (profile=%s default=%s)", payload.video_preset, profile, picked["video_preset"])
    if payload.video_crf is not None:
        logger.info("profile_override_used: video_crf=%s (profile=%s default=%s)", payload.video_crf, profile, picked["video_crf"])
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


def extract_text_from_srt(srt_path: str) -> str:
    import re
    try:
        text_lines = []
        with open(srt_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if re.match(r"^\d+$", line):
                    continue
                if "-->" in line:
                    continue
                text_lines.append(line)
        text = " ".join(text_lines)
        text = re.sub(r" {2,}", " ", text).strip()
        if text and text[-1] not in ".!?":
            text += "."
        return text
    except Exception:
        return ""


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


def _failed_part_progress(job_id: str, part_no: int, fallback: int = 95) -> int:
    try:
        for part in list_job_parts(job_id):
            if int(part.get("part_no") or 0) != int(part_no):
                continue
            current = int(part.get("progress_percent") or 0)
            if current >= 100:
                return min(99, fallback)
            return max(0, min(99, current))
    except Exception:
        pass
    return max(0, min(99, fallback))


def _validate_render_output(
    output_path: Path,
    expected_duration: float | None = None,
    expect_audio: bool | None = None,
) -> dict:
    """Validate a rendered output file before marking its part as DONE.

    Returns a dict:
        ok           – True only when all hard checks pass
        warnings     – non-fatal issues (e.g. audio missing when not confirmed required)
        error        – human-readable failure reason when ok=False
        metadata     – {size_bytes, duration, has_video, has_audio}

    Never raises; callers convert a non-ok result into a part failure.
    """
    result: dict = {
        "ok": False,
        "warnings": [],
        "error": None,
        "metadata": {"size_bytes": 0, "duration": 0.0, "has_video": False, "has_audio": False},
    }

    # 1. File existence
    if not output_path.exists():
        result["error"] = "output file does not exist"
        return result

    # 2. Size — 10 KB floor catches zero-byte and near-empty files while
    #    allowing extremely short test clips (~1 s h264 is ~40 KB).
    size = output_path.stat().st_size
    result["metadata"]["size_bytes"] = size
    if size < 10_240:
        result["error"] = f"output file too small: {size} bytes (minimum 10 KB)"
        return result

    # 3. ffprobe readability — single pass for all stream/format data
    try:
        cmd = [
            get_ffprobe_bin(),
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(output_path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0:
            result["error"] = (
                f"ffprobe could not read output "
                f"(exit {proc.returncode}): {(proc.stderr or '').strip()[:200]}"
            )
            return result
        probe = json.loads(proc.stdout or "{}")
    except subprocess.TimeoutExpired:
        result["error"] = "ffprobe timed out reading output"
        return result
    except Exception as exc:
        result["error"] = f"ffprobe error: {exc}"
        return result

    # 4. Stream presence
    streams = probe.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    result["metadata"]["has_video"] = has_video
    result["metadata"]["has_audio"] = has_audio

    if not has_video:
        result["error"] = "output contains no video stream"
        return result

    # 5. Duration sanity
    fmt = probe.get("format", {})
    duration = float(fmt.get("duration") or 0)
    result["metadata"]["duration"] = duration

    if duration <= 0:
        result["error"] = "output duration is zero"
        return result

    if expected_duration and expected_duration > 0:
        tolerance = max(1.0, expected_duration * 0.15)
        if abs(duration - expected_duration) > tolerance:
            result["error"] = (
                f"duration mismatch: output {duration:.2f}s vs "
                f"expected ~{expected_duration:.2f}s "
                f"(tolerance ±{tolerance:.2f}s)"
            )
            return result

    # 6. Audio sanity — warn-only unless caller is confident audio is required
    if expect_audio is True and not has_audio:
        result["warnings"].append("audio stream expected but missing from output")

    result["ok"] = True
    return result


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

    # Market Viral — resolve target market once; used by all part workers via closure
    _mv_cfg = getattr(payload, "market_viral", None) or {}
    _mv_market = str((_mv_cfg.get("target_market") or "US") if isinstance(_mv_cfg, dict) else "US").upper()
    if _mv_market not in {"US", "EU", "JP"}:
        _mv_market = "US"
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
    current_progress = 1

    def _set_stage(stage: str, progress: int, message: str):
        nonlocal current_stage, current_progress
        current_stage = stage
        current_progress = max(0, min(99, int(progress)))
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
    _job_log(
        effective_channel, job_id,
        f"profile_resolved | render_profile={payload.render_profile} | preset={tuned['video_preset']} crf={tuned['video_crf']} whisper={tuned['whisper_model']} trans={tuned['transition_sec']:.2f}",
    )
    if payload.video_preset:
        _job_log(effective_channel, job_id, f"profile_override_used video_preset={payload.video_preset}", kind="warning")
    if payload.video_crf is not None:
        _job_log(effective_channel, job_id, f"profile_override_used video_crf={payload.video_crf}", kind="warning")
    try:
        normalized_text_layers = _validate_text_layers_or_400(payload)
    except Exception as layer_exc:
        normalized_text_layers = []
        _job_log(effective_channel, job_id, f"Text layer parse warning: {layer_exc}", kind="warning")
        update_job_progress(
            job_id, "starting", 0,
            f"⚠️ Text overlays skipped (parse error): {layer_exc}",
        )
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
                context={"url": yt_url, "source_quality_mode": payload.source_quality_mode},
            )
            source = download_youtube(yt_url, work_dir, quality_mode=payload.source_quality_mode)
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
                    try:
                        os.link(source_path, keep_path)
                        _job_log(effective_channel, job_id, f"local_source.copy_skipped path={source_path} hardlink={keep_path}")
                    except OSError:
                        shutil.copy2(source_path, keep_path)
                        _job_log(effective_channel, job_id, f"local_source.copy_required path={source_path} dest={keep_path}")
            source_path = keep_path

        voice_audio_path = None
        _voice_tts_failed = False
        _voice_mix_ok = []
        _voice_part_tts_attempts = []
        _sub_translate_attempts = []
        _sub_translate_clean = []
        _sub_translate_partial = []
        _sub_translate_failed_parts = []
        if getattr(payload, "voice_enabled", False) and getattr(payload, "voice_source", "manual") == "manual":
            try:
                update_job_progress(job_id, current_stage, current_progress, "Generating AI voice...")
                _job_log(effective_channel, job_id, "Generating AI narration audio")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_tts_started",
                    level="INFO",
                    message="Generating AI voice",
                    step="voice.tts",
                    context={"language": payload.voice_language, "gender": payload.voice_gender},
                )
                voice_audio_path = generate_narration_mp3(
                    text=str(payload.voice_text or ""),
                    language=payload.voice_language,
                    gender=payload.voice_gender,
                    rate=payload.voice_rate,
                    job_id=job_id,
                    voice_id=getattr(payload, "voice_id", None),
                )
                update_job_progress(job_id, current_stage, current_progress, "AI voice generated")
                _job_log(effective_channel, job_id, f"AI narration audio ready: {voice_audio_path}")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_tts_completed",
                    level="INFO",
                    message="AI voice generated",
                    step="voice.tts",
                    context={"audio_path": str(voice_audio_path), "voice_text_length": len(str(payload.voice_text or ""))},
                )
            except Exception as voice_exc:
                voice_audio_path = None
                _voice_tts_failed = True
                update_job_progress(job_id, current_stage, current_progress, "AI voice failed - continuing with original audio")
                _job_log(effective_channel, job_id, f"AI voice generation failed: {voice_exc}", kind="error")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_failed",
                    level="ERROR",
                    message=f"AI voice generation failed: {voice_exc}",
                    step="voice.tts",
                    exception=voice_exc,
                    traceback_text=traceback.format_exc(),
                    context={"error_code": "VOICE001"},
                )

        _set_stage(JobStage.SCENE_DETECTION, 15, "Detecting scenes")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.scene.detect.start",
            level="INFO",
            message="Detecting scenes",
            step="render.scene.detect",
        )
        _t_scene = time.perf_counter()
        scenes = detect_scenes(str(source_path)) if payload.auto_detect_scene else []
        _scene_ms = int((time.perf_counter() - _t_scene) * 1000)
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.scene.detect.success",
            level="INFO",
            message=f"Detected {len(scenes)} scenes",
            step="render.scene.detect",
            context={"scene_count": len(scenes), "duration_ms": _scene_ms},
            duration_ms=_scene_ms,
        )
        _job_log(effective_channel, job_id, f"Scene detection done: {len(scenes)} scenes in {_scene_ms}ms")

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
        full_srt_available = False
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
            if payload.resume_from_last and full_srt.exists() and full_srt.stat().st_size > 0:
                full_srt_available = True
                _job_log(effective_channel, job_id, "Reuse existing full transcription", kind="debug")
            else:
                source_has_audio = has_audio_stream(str(source_path))
                if not source_has_audio:
                    _job_log(effective_channel, job_id, f"subtitle.audio_missing source={source_path}; subtitles skipped", kind="warning")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="subtitle.audio_missing",
                        level="WARNING",
                        message="Source video has no usable audio stream; subtitles skipped",
                        step="subtitle.transcribe",
                        context={"source_path": str(source_path)},
                    )
                else:
                    _whisper_model = tuned["whisper_model"]
                    _src_name = Path(source_path).name
                    _t_transcribe = time.perf_counter()
                    _hb_stop = threading.Event()

                    def _hb_thread_fn(_stop=_hb_stop, _m=_whisper_model, _s=_src_name):
                        _pct = 29
                        while not _stop.wait(12):
                            _elapsed = round(time.perf_counter() - _t_transcribe)
                            update_job_progress(job_id, JobStage.TRANSCRIBING_FULL, _pct, f"Still transcribing… ({_elapsed}s)")
                            _job_log(effective_channel, job_id, f"subtitle_transcription_progress elapsed_sec={_elapsed} model={_m} source={_s}")
                            _emit_render_event(
                                channel_code=effective_channel, job_id=job_id,
                                event="subtitle_transcription_progress",
                                level="INFO",
                                message=f"Still transcribing… elapsed={_elapsed}s",
                                step="subtitle.transcribe",
                                context={"elapsed_sec": _elapsed, "whisper_model": _m, "source": _s},
                            )
                            _pct = _pct + 1 if _pct < 34 else (33 if _pct == 34 else 34)

                    _job_log(effective_channel, job_id, f"subtitle_transcription_started model={_whisper_model} source={_src_name}")
                    _emit_render_event(
                        channel_code=effective_channel, job_id=job_id,
                        event="subtitle_transcription_started",
                        level="INFO",
                        message=f"Transcription started: model={_whisper_model}",
                        step="subtitle.transcribe",
                        context={"whisper_model": _whisper_model, "source": _src_name},
                    )
                    _hb = threading.Thread(target=_hb_thread_fn, daemon=True, name=f"transcribe_hb_{job_id[:8]}")
                    _hb.start()
                    try:
                        transcribe_to_srt(str(source_path), str(full_srt), model_name=_whisper_model, retry_count=retry_count, highlight_per_word=payload.highlight_per_word)
                        full_srt_available = bool(full_srt.exists() and full_srt.stat().st_size > 0)
                        _transcribe_ms = int((time.perf_counter() - _t_transcribe) * 1000)
                        _srt_size = full_srt.stat().st_size if full_srt_available else 0
                        _job_log(effective_channel, job_id, f"subtitle_transcription_completed model={_whisper_model} elapsed_ms={_transcribe_ms} srt_exists={full_srt_available} size_bytes={_srt_size}")
                        _emit_render_event(
                            channel_code=effective_channel, job_id=job_id,
                            event="subtitle_transcription_completed",
                            level="INFO",
                            message=f"Transcription complete: model={_whisper_model} elapsed={_transcribe_ms}ms",
                            step="subtitle.transcribe",
                            context={"whisper_model": _whisper_model, "elapsed_ms": _transcribe_ms, "srt_path": str(full_srt), "file_exists": full_srt_available, "size_bytes": _srt_size},
                        )
                    except Exception as transcribe_exc:
                        full_srt_available = False
                        _safe_unlink(full_srt)
                        _transcribe_ms = int((time.perf_counter() - _t_transcribe) * 1000)
                        _job_log(effective_channel, job_id, f"subtitle_transcription_failed source={source_path} model={_whisper_model} elapsed_ms={_transcribe_ms}: {transcribe_exc}", kind="warning")
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="subtitle_transcription_failed",
                            level="WARNING",
                            message=f"Subtitle transcription failed: {transcribe_exc}",
                            step="subtitle.transcribe",
                            context={"source_path": str(source_path), "whisper_model": _whisper_model, "elapsed_ms": _transcribe_ms},
                            exception=transcribe_exc,
                        )
                    finally:
                        _hb_stop.set()
                        _hb.join(timeout=2)

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
            _sub_target_lang = getattr(payload, "subtitle_target_language", "en")
            translated_srt_part = work_dir / f"{source['slug']}_part_{idx:03d}.{_sub_target_lang}.srt"
            _job_log(effective_channel, job_id, f"Part {idx}/{total_parts} start", kind="debug")

            _existing_part_info = existing_parts.get(idx, {})
            if (
                payload.resume_from_last
                and ((_existing_part_info.get("status") or "").lower() == "done")
                and final_part.exists()
                and final_part.stat().st_size > 0
            ):
                upsert_job_part(job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Skipped (already rendered)")
                _job_log(effective_channel, job_id, f"Part {idx} skipped: final output already exists", kind="debug")
                return {"idx": idx, "output": str(final_part), "row": None, "skipped": True}

            # Worker thread has claimed this part — mark as WAITING before any I/O so
            # the UI can distinguish "queued but not yet started" from "claimed by a thread".
            upsert_job_part(job_id, idx, part_name, JobPartStage.WAITING, 5, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), "", "Waiting for worker")

            upsert_job_part(job_id, idx, part_name, JobPartStage.CUTTING, 10, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Cutting raw part")
            if not (payload.resume_from_last and raw_part.exists() and raw_part.stat().st_size > 0):
                cut_video(str(source_path), str(raw_part), seg["start"], seg["end"], retry_count=retry_count)
                _job_log(effective_channel, job_id, f"Part {idx} cut done", kind="debug")
            else:
                _job_log(effective_channel, job_id, f"Part {idx} cut skipped (raw exists)", kind="debug")

            subtitle_selected_by_rule = subtitle_enabled_by_idx.get(idx, False)
            part_subtitle_enabled = subtitle_selected_by_rule
            if part_subtitle_enabled and not full_srt_available:
                part_subtitle_enabled = False
                _job_log(effective_channel, job_id, f"Part {idx} subtitle skipped: full transcript unavailable", kind="warning")
            if payload.add_subtitle and not part_subtitle_enabled and not subtitle_selected_by_rule:
                _job_log(effective_channel, job_id, f"Part {idx} subtitle skipped (viral={int(seg.get('viral_score', 0))} < cutoff={int(subtitle_cutoff)})")

            if part_subtitle_enabled:
                upsert_job_part(job_id, idx, part_name, JobPartStage.TRANSCRIBING, 35, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Preparing subtitle")
                needs_srt = not (payload.resume_from_last and srt_part.exists() and srt_part.stat().st_size > 0)
                needs_ass = not (payload.resume_from_last and ass_part.exists() and ass_part.stat().st_size > 0)
                if needs_srt:
                    slice_srt_by_time(str(full_srt), str(srt_part), seg["start"], seg["end"], rebase_to_zero=True)
                    _job_log(effective_channel, job_id, f"Part {idx} subtitle sliced from full transcript", kind="debug")
                _ass_srt_source = srt_part
                if getattr(payload, "subtitle_translate_enabled", False) and srt_part.exists() and srt_part.stat().st_size > 0:
                    _needs_translated = not (payload.resume_from_last and translated_srt_part.exists() and translated_srt_part.stat().st_size > 0)
                    if _needs_translated:
                        _sub_translate_attempts.append(idx)
                        try:
                            _job_log(effective_channel, job_id, f"subtitle_translate_started part_no={idx} target={_sub_target_lang}", kind="debug")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_translate_started",
                                level="INFO",
                                message=f"Translating subtitle (part {idx})",
                                step="subtitle.translate",
                                context={"part_no": idx, "target": _sub_target_lang},
                            )
                            _, _block_failures = translate_srt_file(str(srt_part), str(translated_srt_part), target_language=_sub_target_lang)
                            for _bfi in _block_failures:
                                _job_log(effective_channel, job_id, f"subtitle_translate_block_failed part_no={idx} block={_bfi} target={_sub_target_lang}", kind="warning")
                            if _block_failures:
                                _sub_translate_partial.append(idx)
                            else:
                                _sub_translate_clean.append(idx)
                            _job_log(effective_channel, job_id, f"subtitle_translate_completed part_no={idx} output={translated_srt_part}")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_translate_completed",
                                level="INFO",
                                message=f"Subtitle translated (part {idx})",
                                step="subtitle.translate",
                                context={"part_no": idx, "output": str(translated_srt_part), "block_failures": len(_block_failures)},
                            )
                            needs_ass = True
                        except Exception as _trans_exc:
                            _sub_translate_failed_parts.append(idx)
                            _job_log(effective_channel, job_id, f"subtitle_translate_failed part_no={idx}: {_trans_exc}", kind="warning")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_translate_failed",
                                level="WARNING",
                                message=f"Subtitle translation failed (part {idx}): {_trans_exc}",
                                step="subtitle.translate",
                                context={"part_no": idx},
                            )
                    if translated_srt_part.exists() and translated_srt_part.stat().st_size > 0:
                        _ass_srt_source = translated_srt_part
                _sub_edits = getattr(payload, 'subtitle_edits', None)
                if _sub_edits and _ass_srt_source.exists():
                    try:
                        _apply_subtitle_edits_to_srt(str(_ass_srt_source), _sub_edits)
                    except Exception as _se_exc:
                        logger.warning("subtitle_edits: skipped due to error: %s", _se_exc)
                if _mv_cfg and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        apply_market_line_break_to_srt(str(_ass_srt_source), _mv_cfg)
                        needs_ass = True
                    except Exception:
                        pass
                if needs_ass:
                    _play_res_y = _aspect_play_res_y(payload.aspect_ratio)
                    _margin_v = getattr(payload, "sub_margin_v", 180)
                    if payload.subtitle_style == "pro_karaoke":
                        from app.services.subtitle_engine import _hex_to_ass
                        srt_to_ass_karaoke(
                            str(_ass_srt_source), str(ass_part),
                            scale_y=payload.frame_scale_y,
                            font_size=getattr(payload, "sub_font_size", 46),
                            font_name=getattr(payload, "sub_font", "Bungee"),
                            margin_v=_margin_v,
                            play_res_y=_play_res_y,
                            base_color=_hex_to_ass(getattr(payload, "sub_color", "#FFFFFF")),
                            highlight_color=_hex_to_ass(getattr(payload, "sub_highlight", "#FFFF00")),
                            outline_size=getattr(payload, "sub_outline", 3),
                            x_percent=getattr(payload, "sub_x_percent", 50.0),
                        )
                    else:
                        srt_to_ass_bounce(
                            str(_ass_srt_source),
                            str(ass_part),
                            subtitle_style=payload.subtitle_style,
                            scale_y=payload.frame_scale_y,
                            highlight_per_word=payload.highlight_per_word,
                            font_name=getattr(payload, "sub_font", "Bungee"),
                            margin_v=_margin_v,
                            play_res_y=_play_res_y,
                            x_percent=getattr(payload, "sub_x_percent", 50.0),
                        )
                    _job_log(effective_channel, job_id, f"Part {idx} subtitle: style={payload.subtitle_style} play_res_y={_play_res_y} margin_v={_margin_v} aspect={payload.aspect_ratio}", kind="info")
            else:
                _job_log(effective_channel, job_id, f"Part {idx} subtitle disabled", kind="debug")

            overlay_title = (payload.title_overlay_text or "").strip() or source["title"]
            upsert_job_part(job_id, idx, part_name, JobPartStage.RENDERING, 70, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Rendering final video")

            # Start a background timer that writes linear progress estimates
            # (70–99%) every _PROGRESS_TICK_SEC seconds while FFmpeg runs.
            # Stopped in `finally` before the authoritative 100% write.
            _encode_stop = threading.Event()
            _encode_timer = threading.Thread(
                target=_render_progress_timer,
                args=(
                    _encode_stop, job_id, idx, part_name, seg,
                    str(final_part),
                    time.monotonic(),
                    max(float(seg.get("duration") or 0), 1.0),
                ),
                daemon=True,
                name=f"progress-timer-{job_id[:8]}-p{idx}",
            )
            _encode_timer.start()
            _t_encode = time.perf_counter()
            try:
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
                    loudnorm_enabled=getattr(payload, "loudnorm_enabled", False),
                    ffmpeg_threads=_ffmpeg_threads,
                )
            finally:
                _encode_stop.set()
                _encode_timer.join(timeout=5.0)
            _part_subtitle_voice_path = None
            if (
                getattr(payload, "voice_enabled", False)
                and getattr(payload, "voice_source", "manual") == "subtitle"
                and voice_audio_path is None
            ):
                _part_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
                _part_srt_inmem_text: str | None = None
                if _part_srt is None and full_srt_available:
                    try:
                        _part_srt_inmem_text = slice_srt_to_text(str(full_srt), seg["start"], seg["end"])
                        _part_srt = full_srt  # truthy sentinel: text loaded in-memory
                        _job_log(effective_channel, job_id, f"voice.srt_in_memory part_no={idx} (no temp file written)", kind="debug")
                    except Exception:
                        _part_srt = None
                if _part_srt:
                    _part_narration_text = _part_srt_inmem_text if _part_srt_inmem_text is not None else extract_text_from_srt(str(_part_srt))
                    if _part_narration_text.strip():
                        _voice_part_tts_attempts.append(idx)
                        _part_mp3 = str(TEMP_DIR / job_id / "voice" / f"part_{idx:03d}.mp3")
                        try:
                            _job_log(effective_channel, job_id, f"Generating AI narration for part {idx}/{total_parts} from subtitle", kind="debug")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_tts_started",
                                level="INFO",
                                message=f"Generating AI voice from subtitle (part {idx})",
                                step="voice.tts",
                                context={"part_no": idx, "language": payload.voice_language, "source": "subtitle"},
                            )
                            _part_subtitle_voice_path = generate_narration_mp3(
                                text=_part_narration_text,
                                language=payload.voice_language,
                                gender=payload.voice_gender,
                                rate=payload.voice_rate,
                                job_id=job_id,
                                voice_id=getattr(payload, "voice_id", None),
                                output_path=_part_mp3,
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_tts_completed",
                                level="INFO",
                                message=f"AI voice from subtitle generated (part {idx})",
                                step="voice.tts",
                                context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                            )
                        except Exception as _part_tts_exc:
                            _part_subtitle_voice_path = None
                            _job_log(effective_channel, job_id, f"voice_part_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_failed",
                                level="ERROR",
                                message=f"AI voice (subtitle, part {idx}) failed: {_part_tts_exc}",
                                step="voice.tts",
                                exception=_part_tts_exc,
                                traceback_text=traceback.format_exc(),
                                context={"part_no": idx, "error_code": "VOICE001"},
                            )
                    else:
                        _job_log(effective_channel, job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} subtitle text empty; narration skipped", kind="warning")
                else:
                    _job_log(effective_channel, job_id, f"voice_subtitle_source_missing part_no={idx} source=subtitle; narration skipped", kind="warning")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_subtitle_source_missing",
                        level="WARNING",
                        message=f"Subtitle voice source missing for part {idx}; narration skipped",
                        step="voice.tts",
                        context={"part_no": idx, "source": "subtitle"},
                    )
            elif (
                getattr(payload, "voice_enabled", False)
                and getattr(payload, "voice_source", "manual") == "translated_subtitle"
                and voice_audio_path is None
            ):
                _tgt_lang_voice = getattr(payload, "subtitle_target_language", "en")
                if not payload.voice_language.lower().startswith(_tgt_lang_voice.lower()):
                    _job_log(effective_channel, job_id, f"VOICE_LANGUAGE_TARGET_MISMATCH: voice_language={payload.voice_language} target={_tgt_lang_voice}", kind="warning")
                _voice_srt = translated_srt_part if translated_srt_part.exists() and translated_srt_part.stat().st_size > 0 else None
                if _voice_srt is None:
                    _job_log(effective_channel, job_id, f"VOICE_TRANSLATED_SUBTITLE_MISSING: part {idx} translated SRT not found; falling back to original", kind="warning")
                    _voice_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
                _voice_srt_inmem_text: str | None = None
                if _voice_srt is None and full_srt_available:
                    try:
                        _voice_srt_inmem_text = slice_srt_to_text(str(full_srt), seg["start"], seg["end"])
                        _voice_srt = full_srt  # truthy sentinel: text loaded in-memory
                        _job_log(effective_channel, job_id, f"voice.translated_srt_in_memory part_no={idx} (no temp file written)", kind="debug")
                    except Exception:
                        _voice_srt = None
                if _voice_srt:
                    _part_narration_text = _voice_srt_inmem_text if _voice_srt_inmem_text is not None else extract_text_from_srt(str(_voice_srt))
                    if _part_narration_text.strip():
                        _voice_part_tts_attempts.append(idx)
                        _part_mp3 = str(TEMP_DIR / job_id / "voice" / f"part_{idx:03d}.mp3")
                        try:
                            _job_log(effective_channel, job_id, f"voice_translated_subtitle_tts_started part_no={idx}", kind="debug")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_translated_subtitle_tts_started",
                                level="INFO",
                                message=f"Generating AI voice from translated subtitle (part {idx})",
                                step="voice.tts",
                                context={"part_no": idx, "language": payload.voice_language, "target": _tgt_lang_voice},
                            )
                            _part_subtitle_voice_path = generate_narration_mp3(
                                text=_part_narration_text,
                                language=payload.voice_language,
                                gender=payload.voice_gender,
                                rate=payload.voice_rate,
                                job_id=job_id,
                                voice_id=getattr(payload, "voice_id", None),
                                output_path=_part_mp3,
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_translated_subtitle_tts_completed",
                                level="INFO",
                                message=f"AI voice from translated subtitle generated (part {idx})",
                                step="voice.tts",
                                context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                            )
                        except Exception as _part_tts_exc:
                            _part_subtitle_voice_path = None
                            _job_log(effective_channel, job_id, f"voice_translated_subtitle_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="voice_failed",
                                level="ERROR",
                                message=f"AI voice (translated subtitle, part {idx}) failed: {_part_tts_exc}",
                                step="voice.tts",
                                exception=_part_tts_exc,
                                traceback_text=traceback.format_exc(),
                                context={"part_no": idx, "error_code": "VOICE001"},
                            )
                    else:
                        _job_log(effective_channel, job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} translated subtitle text empty; narration skipped", kind="warning")
                else:
                    _job_log(effective_channel, job_id, f"voice_subtitle_source_missing part_no={idx} source=translated_subtitle; narration skipped", kind="warning")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_subtitle_source_missing",
                        level="WARNING",
                        message=f"Translated subtitle voice source missing for part {idx}; narration skipped",
                        step="voice.tts",
                        context={"part_no": idx, "source": "translated_subtitle"},
                    )
            _final_voice_path = voice_audio_path or _part_subtitle_voice_path
            if _final_voice_path:
                mixed_part = final_part.with_name(final_part.stem + ".voice_tmp.mp4")
                try:
                    _job_log(effective_channel, job_id, f"Mixing AI narration into part {idx}/{total_parts}", kind="debug")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_mix_started",
                        level="INFO",
                        message="Mixing narration audio",
                        step="voice.mix",
                        context={"part_no": idx, "mix_mode": payload.voice_mix_mode},
                    )
                    mix_narration_audio(
                        video_path=str(final_part),
                        narration_audio_path=str(_final_voice_path),
                        mix_mode=payload.voice_mix_mode,
                        output_path=str(mixed_part),
                    )
                    os.replace(str(mixed_part), str(final_part))
                    _job_log(effective_channel, job_id, f"voice_mix_completed part_no={idx}/{total_parts}")
                    _voice_mix_ok.append(idx)
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_mix_completed",
                        level="INFO",
                        message="Voice narration completed",
                        step="voice.mix",
                        context={"part_no": idx, "output_file": str(final_part)},
                    )
                except Exception as mix_exc:
                    _safe_unlink(mixed_part)
                    _job_log(effective_channel, job_id, f"voice_mix_failed part_no={idx}: {mix_exc}", kind="error")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="voice_failed",
                        level="ERROR",
                        message=f"voice_mix_failed part_no={idx}: {mix_exc}",
                        step="voice.mix",
                        context={"part_no": idx, "output_file": str(final_part), "error_code": "VOICE001"},
                        exception=mix_exc,
                        traceback_text=traceback.format_exc(),
                    )
            _encode_ms = int((time.perf_counter() - _t_encode) * 1000)
            _part_dur = float(seg.get("duration") or 0)
            _speed_ratio = round(_part_dur * 1000 / max(_encode_ms, 1), 2)
            if normalized_text_layers:
                _job_log(
                    effective_channel,
                    job_id,
                    f"Applied {len(normalized_text_layers)} text layer(s) on part {idx}/{total_parts}",
                    kind="debug",
                )
            _job_log(
                effective_channel, job_id,
                f"Part {idx}/{total_parts} done: encode_ms={_encode_ms} "
                f"part_dur={_part_dur:.1f}s speed_ratio={_speed_ratio}x "
                f"(>1 = faster than realtime)",
                kind="info",
            )

            # ── Market Viral scoring — safe, never breaks render ──────────
            try:
                _mv_text = ""
                if srt_part.exists() and srt_part.stat().st_size > 0:
                    _mv_text = extract_text_from_srt(str(srt_part))
                _mv_dur = float(seg.get("duration") or 0) or None
                _mv_result = _mv_score_part(_mv_text, _mv_dur, _mv_market)
                seg["mv_viral_score"]   = _mv_result.get("viral_score",  0)
                seg["mv_viral_tier"]    = _mv_result.get("viral_tier",   "weak")
                seg["mv_viral_market"]  = _mv_result.get("viral_market", _mv_market)
                seg["mv_viral_reasons"] = _mv_result.get("reasons",      [])
            except Exception:
                pass

            # ── Post-render output validation ─────────────────────────────
            _expect_audio: bool | None = None
            if getattr(payload, "voice_enabled", False):
                _expect_audio = True
            elif (getattr(payload, "reup_bgm_enable", False)
                  and bool(str(getattr(payload, "reup_bgm_path", None) or "").strip())):
                _expect_audio = True
            _qa = _validate_render_output(
                final_part,
                expected_duration=_part_dur if _part_dur > 0 else None,
                expect_audio=_expect_audio,
            )
            if not _qa["ok"]:
                _job_log(effective_channel, job_id,
                         f"Part {idx} output_validation_failed: {_qa['error']} | "
                         f"meta={_qa['metadata']}", kind="error")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_validation_failed",
                    level="ERROR",
                    message=f"Part {idx} output validation failed: {_qa['error']}",
                    step="render.output.validate",
                    context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
                )
                raise RuntimeError(f"output_validation_failed: {_qa['error']}")
            if _qa["warnings"]:
                _job_log(effective_channel, job_id,
                         f"Part {idx} output_validation_warning: {'; '.join(_qa['warnings'])} | "
                         f"meta={_qa['metadata']}", kind="warning")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_validation_warning",
                    level="WARNING",
                    message=f"Part {idx} output validation passed with warnings: {'; '.join(_qa['warnings'])}",
                    step="render.output.validate",
                    context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
                )
            else:
                _job_log(effective_channel, job_id,
                         f"Part {idx} output_validation_passed: "
                         f"dur={_qa['metadata']['duration']:.2f}s "
                         f"size={_qa['metadata']['size_bytes']} "
                         f"has_video={_qa['metadata']['has_video']} "
                         f"has_audio={_qa['metadata']['has_audio']}")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_validation_passed",
                    level="INFO",
                    message=f"Part {idx} output validation passed",
                    step="render.output.validate",
                    context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
                )

            upsert_job_part(job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Completed")
            row = [job_id, effective_channel, source["title"], idx, seg["start"], seg["end"], seg["duration"], seg["viral_score"], seg["priority_rank"], str(final_part)]
            if payload.cleanup_temp_files:
                _safe_unlink(raw_part)
                _safe_unlink(srt_part)
                _safe_unlink(ass_part)
            return {"idx": idx, "output": str(final_part), "row": row, "skipped": False}

        cpu_total = os.cpu_count() or 2
        gpu_ready = nvenc_available()

        # Distinguish which options add TRUE CPU parallelism cost outside the ffmpeg vf chain.
        # - add_subtitle / text_layers: run INSIDE ffmpeg's filter pipeline; they slow each
        #   job but do not prevent N jobs from running in parallel (no extra process spawned).
        # - motion_aware_crop: runs OpenCV optical-flow as a blocking CPU pre-pass BEFORE
        #   ffmpeg; this competes directly with parallel workers on CPU.
        # - reup_mode: BGM audio subprocess; moderate overhead on CPU.
        if gpu_ready:
            # GPU handles encode; CPU cost per worker is low.
            # Only penalise the pre-pass operations that stay on CPU.
            cpu_extra = sum([
                bool(payload.motion_aware_crop),
                bool(payload.reup_mode),
            ])
            heavy_penalty = min(cpu_extra, 2)
            base = max(2, cpu_total // 3)
            hard_ceiling = 6
        else:
            # CPU-only: libx264/libx265 uses -threads 0 (all cores per worker).
            # Count all heavy opts but cap penalty at 2 (not 3) so higher core counts
            # can still unlock a second parallel worker.
            all_heavy = sum([
                bool(payload.motion_aware_crop),
                bool(payload.add_subtitle),
                bool(payload.reup_mode),
                bool(payload.text_layers),
            ])
            heavy_penalty = min(all_heavy, 2)
            base = max(1, cpu_total // 4)
            hard_ceiling = 4

        hw_cap = max(1, min(base - heavy_penalty, hard_ceiling))

        # max_parallel_parts == 0 means "adaptive / let backend decide"
        # max_parallel_parts >= 1 means user ceiling — honour it but never exceed hw_cap
        user_req = int(payload.max_parallel_parts or 0)
        if user_req >= 1:
            max_workers = max(1, min(user_req, hw_cap))
        else:
            max_workers = hw_cap

        from app.services.render_engine import _resolve_codec
        _effective_codec = _resolve_codec(payload.video_codec, encoder_mode=payload.encoder_mode)
        _job_log(
            effective_channel, job_id,
            f"Using max_workers={max_workers} "
            f"(cpu={cpu_total}, gpu={gpu_ready}, heavy_penalty={heavy_penalty}, "
            f"base={base}, hw_cap={hw_cap}, user_req={user_req}) | "
            f"codec={_effective_codec} preset={tuned['video_preset']} crf={tuned['video_crf']}",
        )
        # Acquire JOB_SEMAPHORE before entering the FFmpeg-encode section.
        # Blocks until a slot opens when MAX_RENDER_JOBS pipelines are already active.
        # Reduces per-job part parallelism proportionally under contention so that
        # two simultaneous jobs share CPU rather than fighting at 100%.
        JOB_SEMAPHORE.acquire()
        with _render_active_lock:
            _render_active_count[0] += 1
            _render_slot = _render_active_count[0]
        if _render_slot > 1:
            max_workers = max(1, max_workers // _render_slot)
            _job_log(
                effective_channel, job_id,
                f"Throttling to {max_workers} worker(s) — {_render_slot} concurrent render(s) active",
                kind="info",
            )
        try:
            _ffmpeg_threads = resolve_ffmpeg_threads(max_workers)
            _job_log(effective_channel, job_id, f"ffmpeg_threads={_ffmpeg_threads} cpu_total={os.cpu_count() or 4} max_workers={max_workers}")
            completed_parts = 0
            failed_parts = []
            _set_stage(JobStage.RENDERING_PARALLEL if max_workers > 1 else JobStage.RENDERING, 30, f"Rendering parts 0/{total_parts}")
            _t_render_loop = time.perf_counter()
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
                            _failed_part_progress(job_id, idx),
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
                                _failed_part_progress(job_id, idx),
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

            _render_loop_ms = int((time.perf_counter() - _t_render_loop) * 1000)
            _job_log(
                effective_channel, job_id,
                f"Render loop done: {len(outputs)}/{total_parts} parts in {_render_loop_ms}ms "
                f"({_render_loop_ms // 1000}s) with {max_workers} worker(s)",
            )
        finally:
            with _render_active_lock:
                _render_active_count[0] -= 1
            JOB_SEMAPHORE.release()

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
        if not getattr(payload, "voice_enabled", False):
            _voice_summary = "not used"
        elif _voice_tts_failed:
            _voice_summary = "failed"
        elif _voice_mix_ok:
            _voice_summary = "applied"
        elif _voice_part_tts_attempts and not _voice_mix_ok:
            _voice_summary = "failed"
        else:
            _voice_summary = "not used"
        if not getattr(payload, "subtitle_translate_enabled", False) or not _sub_translate_attempts:
            _subtitle_translate_summary = "not used"
        elif _sub_translate_clean and not _sub_translate_partial and not _sub_translate_failed_parts:
            _subtitle_translate_summary = "applied"
        elif _sub_translate_failed_parts and not _sub_translate_clean and not _sub_translate_partial:
            _subtitle_translate_summary = "failed"
        else:
            _subtitle_translate_summary = "partial"
        _job_log(effective_channel, job_id, f"Voice: {_voice_summary}")
        _job_log(effective_channel, job_id, f"Subtitle translation: {_subtitle_translate_summary}")
        upsert_job(job_id, "render", effective_channel, "completed", payload.model_dump(), {"outputs": outputs, "segments": scored, "voice_summary": _voice_summary, "subtitle_translate_summary": _subtitle_translate_summary}, stage=JobStage.DONE, progress_percent=100, message="Render completed")
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
            context={"outputs": len(outputs), "total_parts": total_parts, "voice_summary": _voice_summary, "subtitle_translate_summary": _subtitle_translate_summary},
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
            progress_percent=max(0, min(99, int(current_progress))),
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
