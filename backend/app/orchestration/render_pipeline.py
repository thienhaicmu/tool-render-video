
import json
import os
import re
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
from app.services.db import upsert_job, update_job_progress, upsert_job_part, list_job_parts, close_thread_conn
from app.services.channel_service import ensure_channel
from app.services.downloader import download_youtube, slugify
from app.services.scene_detector import detect_scenes
from app.services.segment_builder import build_segments_from_scenes
from app.services.subtitle_engine import (
    srt_to_ass_bounce, srt_to_ass_karaoke, slice_srt_by_time,
    slice_srt_to_text, has_audio_stream, apply_market_line_break_to_srt,
    apply_market_hook_text_to_srt, apply_hook_subtitle_format, resolve_hook_overlay_text,
    subtitle_emphasis_pass, parse_srt_blocks, write_srt_blocks,
)
from app.services.subtitle_transcription_adapters import transcribe_with_adapter
from app.services.render_engine import cut_video, render_part_smart, nvenc_available, resolve_ffmpeg_threads, detect_silence_trim_offset, apply_micro_pacing, detect_bad_first_frame, set_thread_cancel_event
from app.services import cancel_registry
from app.services.job_manager import MAX_CONCURRENT_JOBS as _MAX_CONCURRENT_JOBS
from app.services.viral_scorer import score_segments
from app.services.viral_scoring import score_part_for_market as _mv_score_part
from app.services.report_service import append_rows
from app.core.config import TEMP_DIR, CHANNELS_DIR, LOGS_DIR
from app.core.stage import JobStage, JobPartStage, STAGE_TO_EVENT
from app.services.bin_paths import get_ffprobe_bin, get_ffmpeg_bin, _summarize_ffmpeg_stderr
from app.services.text_overlay import normalize_text_layers, MAX_TEXT_LAYERS
from app.services.tts_service import generate_narration_mp3
from app.services.audio_mix_service import mix_narration_audio
from app.services.audio_cleanup_adapters import cleanup_audio_with_adapter
from app.services.translation_service import translate_srt_file
from app.services.remotion_adapter import generate_hook_intro, prepend_intro_clip
from app.ai.visibility.ai_visibility_summary import attach_ai_visibility_summaries

logger = logging.getLogger("app.render")


def _safe_output_name(text: str) -> str:
    """Human-readable safe filename stem. Preserves case and apostrophes."""
    if not text:
        return ""
    text = text.strip()
    text = re.sub(r'[\\/:*?"<>|]', '-', text)
    text = re.sub(r'[\r\n\t]+', ' ', text)
    text = re.sub(r'-{2,}', '-', text)
    text = re.sub(r' {2,}', ' ', text)
    text = text.strip('- ')
    if len(text) > 80:
        text = text[:80].rsplit(' ', 1)[0] or text[:80]
    return text.strip('- ')


def _smart_output_stem(hook_text: str, source_title: str, job_id: str) -> str:
    """Fallback chain: AI hook → source title → render_{job_id[:8]}."""
    for candidate in [hook_text, source_title]:
        safe = _safe_output_name(candidate)
        if safe:
            return safe
    return f"render_{job_id[:8]}"


_PLAY_RES_Y_MAP = {"9:16": 1920, "1:1": 1080, "3:4": 1440, "4:5": 1440, "16:9": 1080}

def _aspect_play_res_y(aspect_ratio: str) -> int:
    ar = (aspect_ratio or "").strip()
    val = _PLAY_RES_Y_MAP.get(ar)
    if val is None:
        logger.warning("_aspect_play_res_y: unrecognised aspect_ratio=%r, defaulting to 1440", ar)
        return 1440
    return val

def resolve_combined_score_weights(
    target_market: "str | None",
    has_market_score: bool,
    has_hook_score: bool,
    duration: "float | None",
    adaptive_enabled: bool,
) -> dict:
    """Return combined-score weights that always sum to 1.0.

    When adaptive_enabled=False returns fixed P3-2 defaults.
    When True applies market/availability/duration adjustments then normalizes.
    """
    BASE_VIRAL  = 0.50
    BASE_MARKET = 0.30
    BASE_HOOK   = 0.20

    if not adaptive_enabled:
        return {
            "viral_weight":  BASE_VIRAL,
            "market_weight": BASE_MARKET,
            "hook_weight":   BASE_HOOK,
            "reason":        "fixed",
        }

    w_v = BASE_VIRAL
    w_m = BASE_MARKET
    w_h = BASE_HOOK
    reasons: list[str] = []

    # ── Market adjustment ──────────────────────────────────────────────────
    market = (target_market or "US").upper()
    if market == "US":
        w_h += 0.05; w_v += 0.05; w_m -= 0.10
        reasons.append("US:hook+viral")
    elif market == "EU":
        w_m += 0.10; w_h -= 0.05; w_v -= 0.05
        reasons.append("EU:market+")
    elif market == "JP":
        w_m += 0.05; w_h += 0.05; w_v -= 0.10
        reasons.append("JP:market+hook")

    # ── Missing score redistribution ───────────────────────────────────────
    if not has_market_score:
        half = w_m / 2.0
        w_v += half; w_h += half; w_m = 0.0
        reasons.append("no_mv:redistribute")

    if not has_hook_score:
        half = w_h / 2.0
        w_v += half; w_m += half; w_h = 0.0
        reasons.append("no_hook:redistribute")

    # ── Duration adjustment ────────────────────────────────────────────────
    dur = float(duration or 0)
    if dur > 90:
        w_v += 0.05; w_h -= 0.05
        reasons.append("long:viral+")
    elif 0 < dur < 10:
        w_h += 0.05; w_m -= 0.05
        reasons.append("short:hook+")
    # 10–90 s: no change

    # ── Clamp each active weight to [0.10, 0.70] ──────────────────────────
    W_MIN, W_MAX = 0.10, 0.70
    w_v = max(W_MIN, min(W_MAX, w_v))
    if has_market_score and w_m > 0:
        w_m = max(W_MIN, min(W_MAX, w_m))
    if has_hook_score and w_h > 0:
        w_h = max(W_MIN, min(W_MAX, w_h))

    # ── Normalize → sum = 1.0 ─────────────────────────────────────────────
    total = w_v + w_m + w_h
    if total > 0:
        w_v /= total; w_m /= total; w_h /= total
    else:
        w_v, w_m, w_h = 1.0, 0.0, 0.0

    return {
        "viral_weight":  round(w_v, 4),
        "market_weight": round(w_m, 4),
        "hook_weight":   round(w_h, 4),
        "reason":        ";".join(reasons) or "adaptive_default",
    }


def _score_component(value, default: float = 50.0) -> float:
    """Return a clamped 0-100 score, using neutral default only when missing."""
    if value is None or value == "":
        return default
    try:
        return max(0.0, min(100.0, float(value)))
    except (TypeError, ValueError):
        return default


def _maybe_prepend_remotion_hook_intro(
    final_part: Path,
    payload: RenderRequest,
    *,
    effective_channel: str,
    job_id: str,
    part_no: int,
    headline_text: str | None = None,
    duration_sec: float = 1.0,
) -> float:
    if not bool(getattr(payload, "remotion_hook_intro", False)):
        return 0.0

    started = time.perf_counter()
    intro_path = final_part.with_name(f"{final_part.stem}.hook_intro.mp4")
    concat_path = final_part.with_name(f"{final_part.stem}.with_intro.mp4")
    _job_log(
        effective_channel,
        job_id,
        f"remotion_requested part={part_no} duration_sec={duration_sec:.2f}",
    )
    try:
        intro = generate_hook_intro(
            str(intro_path),
            aspect_ratio=str(getattr(payload, "aspect_ratio", "3:4") or "3:4"),
            duration_sec=duration_sec,
            headline_text=headline_text,
        )
        if not intro:
            _job_log(
                effective_channel,
                job_id,
                f"remotion_failed part={part_no} reason=intro_generation_failed",
                kind="warning",
            )
            return 0.0
        merged = prepend_intro_clip(str(final_part), intro, str(concat_path))
        if not merged:
            _job_log(
                effective_channel,
                job_id,
                f"remotion_failed part={part_no} reason=concat_failed",
                kind="warning",
            )
            return 0.0
        os.replace(merged, final_part)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _job_log(
            effective_channel,
            job_id,
            f"remotion_generated part={part_no} intro_duration_ms={int(duration_sec * 1000)} elapsed_ms={elapsed_ms}",
        )
        return duration_sec
    except Exception as exc:
        _job_log(
            effective_channel,
            job_id,
            f"remotion_failed part={part_no} error={type(exc).__name__}: {exc}",
            kind="warning",
        )
        return 0.0
    finally:
        _safe_unlink(intro_path)
        _safe_unlink(concat_path)


def _maybe_cleanup_narration_audio(
    narration_audio_path: str,
    payload: RenderRequest,
    *,
    effective_channel: str,
    job_id: str,
    part_no: int | None = None,
    source: str = "manual",
) -> str:
    engine = str(getattr(payload, "audio_cleanup_engine", "none") or "none").strip().lower()
    if engine == "none":
        return narration_audio_path

    input_path = Path(narration_audio_path)
    cleaned_path = input_path.with_name(f"{input_path.stem}.cleaned{input_path.suffix}")
    context = f"part_no={part_no} " if part_no is not None else ""
    _job_log(
        effective_channel,
        job_id,
        f"audio_cleanup_requested {context}source={source} audio_cleanup_engine={engine}",
    )
    try:
        result = cleanup_audio_with_adapter(
            str(input_path),
            str(cleaned_path),
            engine=engine,
            logger=logger,
        )
    except Exception as exc:
        _job_log(
            effective_channel,
            job_id,
            f"audio_cleanup_failed {context}source={source} audio_cleanup_engine={engine} "
            f"audio_cleanup_warning={type(exc).__name__}",
            kind="warning",
        )
        _safe_unlink(cleaned_path)
        return narration_audio_path

    candidate = Path(result.output_path) if result.applied and result.output_path else None
    if candidate and candidate.exists() and candidate.stat().st_size > 0:
        _job_log(
            effective_channel,
            job_id,
            f"audio_cleanup_applied {context}source={source} audio_cleanup_engine={engine} "
            f"elapsed_ms={result.elapsed_ms}",
        )
        return str(candidate)

    warning = ",".join(result.warnings) if result.warnings else "audio_cleanup_not_applied"
    _job_log(
        effective_channel,
        job_id,
        f"audio_cleanup_failed {context}source={source} audio_cleanup_engine={engine} "
        f"audio_cleanup_warning={warning}",
        kind="warning",
    )
    if cleaned_path != input_path:
        _safe_unlink(cleaned_path)
    return narration_audio_path


def _first_score(seg: dict, names: list[str], default: float = 50.0) -> float:
    for name in names:
        if name in seg and seg.get(name) not in (None, ""):
            return _score_component(seg.get(name), default=default)
    return default


def _output_ranking_reason(components: dict) -> str:
    reasons: list[str] = []
    content_type = str(components.get("content_type_hint") or "")

    if components["hook_score"] >= 70:
        if content_type in ("interview", "commentary", "podcast"):
            reasons.append("Strong spoken hook")
        else:
            reasons.append("Strong hook")
    elif components["hook_score"] < 40:
        reasons.append("Weak hook")

    if components["retention_score"] >= 70:
        if content_type == "interview":
            reasons.append("High engagement energy")
        else:
            reasons.append("High retention")
    elif components.get("continuity_score", 50.0) >= 70:
        reasons.append("Stable pacing")

    if components["speech_density_score"] >= 60:
        if content_type in ("interview", "commentary", "podcast"):
            reasons.append("Dense spoken content")
        else:
            reasons.append("Speech-heavy segment")
    elif components["speech_density_score"] < 25:
        if content_type == "montage":
            reasons.append("Visual montage")
        else:
            reasons.append("Low speech density")

    if components["market_score"] >= 65:
        reasons.append("Good market match")

    if components["duration_fit_score"] >= 75 and len(reasons) < 3:
        reasons.append("Good duration fit")

    if not reasons:
        if content_type == "montage":
            reasons.append("High-energy montage")
        elif content_type in ("interview", "commentary"):
            reasons.append("Quality spoken content")
        else:
            reasons.append("Balanced clip signals")

    return ", ".join(reasons[:3])


def _compute_output_ranking_entry(part_no: int, seg: dict, output_file: str, payload_hook_score=None) -> dict:
    segment_viral_score = _first_score(seg, ["viral_score"], default=50.0)
    hook_score = _first_score(
        seg,
        ["hook_text_score", "hook_timing_score", "hook_score", "hook_opening_score"],
        default=_score_component(payload_hook_score, default=50.0),
    )
    retention_score = _first_score(seg, ["retention_score"], default=50.0)
    speech_density_score = _first_score(seg, ["speech_density_score"], default=50.0)
    market_score = _first_score(seg, ["mv_viral_score", "market_viral_score"], default=50.0)
    duration_fit_score = _first_score(seg, ["duration_fit_score"], default=50.0)
    continuity_score = _first_score(seg, ["continuity_score"], default=50.0)

    raw_score = (
        segment_viral_score * 0.35
        + hook_score * 0.20
        + retention_score * 0.20
        + speech_density_score * 0.10
        + market_score * 0.10
        + duration_fit_score * 0.05
    )
    output_score = round(max(0.0, min(100.0, raw_score)), 1)
    components = {
        "segment_viral_score": round(segment_viral_score, 1),
        "hook_score": round(hook_score, 1),
        "retention_score": round(retention_score, 1),
        "speech_density_score": round(speech_density_score, 1),
        "market_score": round(market_score, 1),
        "duration_fit_score": round(duration_fit_score, 1),
        "continuity_score": round(continuity_score, 1),
        "content_type_hint": str(seg.get("content_type_hint") or ""),
    }

    return {
        "part_no": part_no,
        "output_file": output_file,
        "output_rank": 0,
        "output_score": output_score,
        "is_best_clip": False,
        "ranking_reason": _output_ranking_reason(components),
        "ranking_components": components,
        "selection_reason": seg.get("selection_reason", ""),
        # Backward-compatible aliases consumed by existing render UI.
        "output_rank_score": output_score,
        "is_best_output": False,
        "reasons": [
            f"segment_viral={components['segment_viral_score']}",
            f"hook={components['hook_score']}",
            f"retention={components['retention_score']}",
            f"speech_density={components['speech_density_score']}",
            f"market={components['market_score']}",
            f"duration_fit={components['duration_fit_score']}",
        ],
    }


_PROGRESS_TICK_SEC = 3.0   # how often the timer thread wakes to update progress

# ---------------------------------------------------------------------------
# Resource throttling
# ---------------------------------------------------------------------------
# JOB_SEMAPHORE caps how many render pipelines can be in the FFmpeg-encode
# section simultaneously.  This prevents CPU saturation when multiple jobs
# are dispatched by the scheduler at the same time.
# Default derives from MAX_CONCURRENT_JOBS so the semaphore never silently
# under-utilises slots that the scheduler has already granted.
# Override with MAX_RENDER_JOBS env var to set an explicit ceiling.
_JOB_SEM_VALUE: int = max(1, int(os.getenv("MAX_RENDER_JOBS", str(_MAX_CONCURRENT_JOBS))))
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


def _duration_tolerance(expected_duration: float) -> float:
    """Return the acceptable deviation window for output duration validation.

    Very short clips get at least 0.5 s; long clips are capped at 3.0 s.
    """
    if expected_duration > 0:
        return max(0.5, min(expected_duration * 0.15, 3.0))
    return 1.0  # safe fallback for unknown/zero expected duration


def _stall_deadline(encode_start: float, expected_duration: float) -> float:
    """Return the monotonic time beyond which a running render is considered stalled."""
    return encode_start + max(120.0, (expected_duration or 60.0) * 10)


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
        "fast":     {"video_preset": "veryfast", "video_crf": 23, "whisper_model": "base",  "transition_sec": 0.05},
        # balanced: good quality/speed tradeoff — medium is ~3-4x faster than slow with <5% quality delta
        "balanced": {"video_preset": "medium",   "video_crf": 18, "whisper_model": "base",  "transition_sec": 0.06},
        # quality: high quality — slow preset gives meaningful gains over medium for large screens
        "quality":  {"video_preset": "slow",     "video_crf": 15, "whisper_model": "small", "transition_sec": 0.06},
        # best: maximum quality, slowest encode — use for final master output
        "best":     {"video_preset": "slower",   "video_crf": 13, "whisper_model": "small", "transition_sec": 0.08},
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
        "code": "",
        "phase": "validation",
        "metadata": {"size_bytes": 0, "duration": 0.0, "has_video": False, "has_audio": False},
    }

    # 1. File existence
    if not output_path.exists():
        result["error"] = "output file does not exist"
        result["code"] = "RN001"
        return result

    # 2. Size — 10 KB floor catches zero-byte and near-empty files while
    #    allowing extremely short test clips (~1 s h264 is ~40 KB).
    size = output_path.stat().st_size
    result["metadata"]["size_bytes"] = size
    if size < 10_240:
        result["error"] = f"output file too small: {size} bytes (minimum 10 KB)"
        result["code"] = "RN001"
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
            result["code"] = "RN001"
            return result
        probe = json.loads(proc.stdout or "{}")
    except subprocess.TimeoutExpired:
        result["error"] = "ffprobe timed out reading output"
        result["code"] = "RN001"
        return result
    except Exception as exc:
        result["error"] = f"ffprobe error: {exc}"
        result["code"] = "RN001"
        return result

    # 4. Stream presence
    streams = probe.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    result["metadata"]["has_video"] = has_video
    result["metadata"]["has_audio"] = has_audio

    if not has_video:
        result["error"] = "output contains no video stream"
        result["code"] = "RN001"
        return result

    # 5. Duration sanity
    fmt = probe.get("format", {})
    duration = float(fmt.get("duration") or 0)
    result["metadata"]["duration"] = duration

    if duration <= 0:
        result["error"] = "output duration is zero"
        result["code"] = "RN001"
        return result

    if expected_duration and expected_duration > 0:
        tolerance = _duration_tolerance(expected_duration)
        result["metadata"]["expected_duration"] = float(expected_duration)
        result["metadata"]["duration_tolerance"] = float(tolerance)
        if abs(duration - expected_duration) > tolerance:
            result["error"] = (
                f"duration mismatch: output {duration:.2f}s vs "
                f"expected ~{expected_duration:.2f}s "
                f"(tolerance ±{tolerance:.2f}s)"
            )
            result["code"] = "RN001"
            return result

    # 6. Audio sanity — warn-only unless caller is confident audio is required
    if expect_audio is True and not has_audio:
        result["warnings"].append("audio stream expected but missing from output")

    result["ok"] = True
    return result


def _assess_output_quality(
    output_path: Path,
    output_dir: Path,
    *,
    expect_subtitle: bool = False,
    subtitle_file: "Path | None" = None,
    expect_hook: bool = False,
    hook_applied: bool = False,
) -> dict:
    """Non-blocking perceptual quality checks run after hard validation passes.

    Returns a report dict:
        passed         – True when no hard failures (currently all checks are warn-only)
        hard_failures  – list of blocking error strings (reserved; currently always empty)
        warnings       – list of non-fatal issue strings
        checks         – per-check boolean/float results
        score_penalty  – total points to deduct from output_score (clamped by caller)

    Never raises — all exceptions produce a None check value rather than propagating.
    """
    hard_failures: list[str] = []
    warnings: list[str] = []
    checks: dict = {}
    penalty = 0

    # 1. Output path safety: must resolve inside output_dir
    try:
        is_inside = output_path.resolve().is_relative_to(output_dir.resolve())
        checks["output_path_safe"] = is_inside
        if not is_inside:
            warnings.append(f"output file is outside the selected output folder: {output_path}")
    except Exception:
        checks["output_path_safe"] = None

    # 2. First-frame darkness — blackdetect on first 0.5 s of the rendered output
    checks["first_frame_dark"] = False
    try:
        _bdet_cmd = [
            get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
            "-t", "0.5", "-i", str(output_path),
            "-vf", "blackdetect=d=0.0:pix_th=0.10",
            "-an", "-f", "null", "-",
        ]
        _bdet_r = subprocess.run(_bdet_cmd, capture_output=True, text=True, timeout=10)
        for _bd_line in (_bdet_r.stderr or "").splitlines():
            if "black_start:" not in _bd_line or "black_end:" not in _bd_line:
                continue
            try:
                _b_start = _b_end = None
                for _tok in _bd_line.split():
                    if _tok.startswith("black_start:"):
                        _b_start = float(_tok.split(":", 1)[1])
                    elif _tok.startswith("black_end:"):
                        _b_end = float(_tok.split(":", 1)[1])
                if _b_start is not None and _b_end is not None and _b_start <= 0.08 and _b_end > 0.12:
                    checks["first_frame_dark"] = True
                    warnings.append(f"first frame appears dark (black_end={_b_end:.2f}s)")
                    penalty += 8
            except (ValueError, IndexError):
                continue
    except Exception:
        checks["first_frame_dark"] = None

    # 3. First-frame blur — blurdetect on first 0.5 s
    checks["first_frame_blur"] = False
    checks["first_frame_blur_score"] = None
    try:
        _blur_cmd = [
            get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
            "-t", "0.5", "-i", str(output_path),
            "-vf", "blurdetect=high=0.35:low=0.25",
            "-an", "-f", "null", "-",
        ]
        _blur_r = subprocess.run(_blur_cmd, capture_output=True, text=True, timeout=10)
        _blur_vals: list[float] = []
        for _bl_line in (_blur_r.stderr or "").splitlines():
            if "blur:" not in _bl_line.lower():
                continue
            try:
                _val_str = _bl_line.split("blur:")[-1].strip().split()[0]
                _blur_vals.append(float(_val_str))
            except (ValueError, IndexError):
                continue
        if _blur_vals:
            _avg_blur = sum(_blur_vals) / len(_blur_vals)
            checks["first_frame_blur_score"] = round(_avg_blur, 3)
            if _avg_blur > 0.60:
                checks["first_frame_blur"] = True
                warnings.append(f"first frames appear blurry (avg_blur={_avg_blur:.2f})")
                penalty += 6
    except Exception:
        checks["first_frame_blur"] = None

    # 4. Subtitle file present when subtitles were requested for this part
    if expect_subtitle:
        _sub_ok = (
            subtitle_file is not None
            and subtitle_file.exists()
            and subtitle_file.stat().st_size > 0
        )
        checks["subtitle_file_present"] = _sub_ok
        if not _sub_ok:
            warnings.append("subtitle file missing or empty (subtitles were requested for this part)")
            penalty += 10
    else:
        checks["subtitle_file_present"] = None  # not applicable

    # 5. Hook overlay confirmed when hook overlay was expected
    if expect_hook:
        checks["hook_overlay_applied"] = hook_applied
        if not hook_applied:
            warnings.append("hook overlay was enabled but no suitable text was found to apply")
            penalty += 6
    else:
        checks["hook_overlay_applied"] = None  # not applicable

    return {
        "passed": len(hard_failures) == 0,
        "hard_failures": hard_failures,
        "warnings": warnings,
        "checks": checks,
        "score_penalty": penalty,
    }


def _render_part_failure_detail(part_no: int, error: Exception | str) -> dict:
    message = str(error)
    is_validation = "output_validation_failed" in message or "duration mismatch" in message
    return {
        "part_no": int(part_no),
        "error": message,
        "code": "RN001" if is_validation else "RN004",
        "phase": "validation" if is_validation else "render",
    }


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
    _mv_cfg_enabled = isinstance(_mv_cfg, dict) and bool(_mv_cfg)
    _mv_payload_market = getattr(payload, "viral_market", None)
    _mv_market = str(
        _mv_payload_market
        or ((_mv_cfg.get("target_market") or "US") if isinstance(_mv_cfg, dict) else "US")
    ).upper()
    if _mv_market not in {"US", "EU", "JP"}:
        _mv_market = "US"
    if _mv_cfg_enabled:
        _mv_cfg = {**_mv_cfg, "target_market": _mv_market}
    else:
        _mv_cfg = {}
    _hook_apply_enabled = bool(getattr(payload, "hook_apply_enabled", False))
    _hook_applied_text = str(getattr(payload, "hook_applied_text", None) or "").strip()
    _hook_score = getattr(payload, "hook_score", None)
    _hook_overlay_enabled = bool(getattr(payload, "hook_overlay_enabled", False))
    if not _hook_applied_text:
        _hook_apply_enabled = False
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
        effective_channel,
        job_id,
        f"Market Viral hook | market={_mv_market} | hook_apply_enabled={_hook_apply_enabled} | hook_score={_hook_score}",
    )
    _preset_name = str(getattr(payload, "render_preset", None) or "").strip() or "custom"
    _preset_id = str(getattr(payload, "render_preset_id", None) or _preset_name or "").strip() or "custom"
    _preset_label = str(getattr(payload, "render_preset_label", None) or "").strip()
    if not _preset_label:
        _preset_label = "Custom" if _preset_id.lower() == "custom" else _preset_id
    if _preset_id and _preset_id.lower() != "custom":
        _job_log(
            effective_channel,
            job_id,
            f"Render preset applied | id={_preset_id} | label={_preset_label}",
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

        # Compute once; captured by _process_one_part closure and auto_best_export
        _output_stem = _smart_output_stem(_hook_applied_text, source.get("title", ""), job_id)

        # Apply editor edits: trim and/or volume adjustment
        trim_in = float(getattr(payload, "edit_trim_in", 0) or 0)
        trim_out = float(getattr(payload, "edit_trim_out", 0) or 0)
        edit_volume = float(getattr(payload, "edit_volume", 1.0) or 1.0)
        needs_trim = trim_in > 0.5 or (trim_out > 0.5 and trim_out < source["duration"] - 0.5)
        needs_volume = abs(edit_volume - 1.0) > 0.005
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
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as _preprocess_exc:
                _pp_stderr = _preprocess_exc.stderr or ""
                _pp_diag = _summarize_ffmpeg_stderr(_pp_stderr)
                _pp_tail = _pp_stderr[-2000:].strip()
                _job_log(
                    effective_channel, job_id,
                    f"FFmpeg preprocess failed exit={_preprocess_exc.returncode} diag={_pp_diag!r}",
                    kind="warning",
                )
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.ffmpeg.preprocess.error",
                    level="ERROR",
                    message=f"FFmpeg preprocess failed: {_pp_diag}",
                    step="render.preprocess",
                    context={
                        "exit_code": _preprocess_exc.returncode,
                        "diagnostic": _pp_diag,
                        "stderr_tail": _pp_tail,
                        "input_path": str(source_path),
                        "output_path": str(edited_path),
                    },
                )
                raise RuntimeError(f"FFmpeg preprocess failed: {_pp_diag}") from _preprocess_exc
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
            # Only temp-origin files (YouTube downloads, edited locals) need to be
            # persisted into source/. A user's original local file is already permanent —
            # copying it would waste disk space (10 GB+) and slow render startup.
            is_temp_source = str(source_path).startswith(str(TEMP_DIR))
            if is_temp_source:
                keep_path = _reserve_source_path_in_dir(keep_source_dir, source["slug"], ext=ext)
                if not keep_path.exists():
                    # Move instead of copy when source is in temp dir (instant on same drive, saves I/O + disk)
                    try:
                        shutil.move(str(source_path), str(keep_path))
                        _job_log(effective_channel, job_id, f"Source moved (zero-copy) to: {keep_path}")
                    except Exception:
                        shutil.copy2(source_path, keep_path)
                        _job_log(effective_channel, job_id, f"Source copied to: {keep_path}")
                source_path = keep_path
            else:
                # Local original (not temp): render directly from user's file — no copy, no hardlink.
                _job_log(effective_channel, job_id, f"local_source.passthrough path={source_path} (source copy skipped)")

        voice_audio_path = None
        _voice_tts_failed = False
        _voice_mix_ok = []
        _voice_part_tts_attempts = []
        _sub_translate_attempts = []
        _sub_translate_clean = []
        _sub_translate_partial = []
        _sub_translate_failed_parts = []
        if getattr(payload, "voice_enabled", False) and getattr(payload, "voice_source", "manual") == "manual":
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()
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
                voice_audio_path = _maybe_cleanup_narration_audio(
                    str(voice_audio_path),
                    payload,
                    effective_channel=effective_channel,
                    job_id=job_id,
                    source="manual",
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
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()
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
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()
        scored = score_segments(segments, scenes)
        # High-motion preference: boost high-energy clips without hard eviction.
        # Talking-head, interview, and commentary content remain competitive in the pool.
        _high_motion_count = sum(1 for s in scored if int(s.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE)
        _apply_motion_boost = _high_motion_count >= HIGH_MOTION_MIN_KEEP
        if _apply_motion_boost:
            _job_log(effective_channel, job_id,
                     f"high_motion_preference: {_high_motion_count} high-energy clips detected — "
                     f"preference boost applied (no eviction); low-motion clips remain in pool")
        # Sort by viral/motion score first for selection (top N), then re-order for output numbering.
        # viral_score is primary — it now incorporates transition quality, not just cut density.
        _combined_enabled = bool(getattr(payload, "combined_scoring_enabled", False))
        if _combined_enabled:
            def _provisional_combined(s):
                vs = float(s.get("viral_score", 0) or 0)
                hs = float(s.get("hook_text_score") or s.get("hook_timing_score") or
                           s.get("hook_opening_score") or s.get("hook_score") or 0)
                # mv not yet computed; fallback = vs → vs*0.50 + vs*0.30 + hs*0.20 = vs*0.80 + hs*0.20
                return vs * 0.80 + hs * 0.20
            scored.sort(key=_provisional_combined, reverse=True)
        else:
            scored.sort(
                key=lambda x: (
                    int(x.get("viral_score", 0)) + (8 if _apply_motion_boost and int(x.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE else 0),
                    int(x.get("motion_score", 0)),
                ),
                reverse=True,
            )
        if payload.max_export_parts and payload.max_export_parts > 0:
            scored = scored[:payload.max_export_parts]
        # Re-order for output numbering: timeline = chronological, viral/combined = by score
        part_order = str(getattr(payload, "part_order", "viral") or "viral").strip().lower()
        if part_order == "timeline":
            scored.sort(key=lambda x: float(x.get("start", 0)))
            _job_log(effective_channel, job_id, f"Part order: timeline (chronological)")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="hook_first_skipped",
                level="INFO",
                message="Hook-first skipped: timeline mode",
                step="render.hook_first",
                context={"reason": "timeline_mode", "total_clips": len(scored)},
            )
        elif part_order == "viral" and _combined_enabled:
            # P4-1: Hook-first sequencing — strongest hook at index 0
            def _hook_score(c):
                return (
                    c.get("combined_score")
                    or c.get("market_viral_score")
                    or c.get("viral_score")
                    or 0
                )
            _sorted = sorted(scored, key=_hook_score, reverse=True)
            _best = _sorted[0]
            _best_score = _hook_score(_best)
            _used_combined = bool(_best.get("combined_score"))
            scored = [_best] + [c for c in _sorted if c is not _best]
            _job_log(effective_channel, job_id, f"Part order: hook-first (combined+viral, best_score={_best_score})")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="hook_first_applied",
                level="INFO",
                message=f"Hook-first applied: best_part_no=1 score={_best_score} total={len(scored)}",
                step="render.hook_first",
                context={
                    "best_part_no": 1,
                    "best_score": _best_score,
                    "used_combined_score": _used_combined,
                    "total_clips": len(scored),
                },
            )
        elif _combined_enabled:
            scored.sort(key=_provisional_combined, reverse=True)
            _job_log(effective_channel, job_id, "Part order: combined score (viral+hook, experimental)")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="hook_first_skipped",
                level="INFO",
                message="Hook-first skipped: part_order is not viral",
                step="render.hook_first",
                context={"reason": "part_order_not_viral", "part_order": part_order, "total_clips": len(scored)},
            )
        else:
            _job_log(effective_channel, job_id, f"Part order: viral score (highest first)")
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="hook_first_skipped",
                level="INFO",
                message="Hook-first skipped: combined scoring disabled",
                step="render.hook_first",
                context={"reason": "combined_disabled", "total_clips": len(scored)},
            )

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
                    if cancel_registry.is_cancelled(job_id):
                        raise cancel_registry.JobCancelledError()
                    try:
                        _transcription_result = transcribe_with_adapter(
                            str(source_path),
                            str(full_srt),
                            engine=getattr(payload, "subtitle_transcription_engine", "default"),
                            model_name=_whisper_model,
                            retry_count=retry_count,
                            highlight_per_word=payload.highlight_per_word,
                            logger=logger,
                        )
                        if _transcription_result.warnings:
                            _job_log(
                                effective_channel,
                                job_id,
                                "subtitle_transcription_adapter_warning "
                                f"requested={getattr(payload, 'subtitle_transcription_engine', 'default')} "
                                f"used={_transcription_result.engine} "
                                f"warnings={','.join(_transcription_result.warnings)}",
                                kind="warning",
                            )
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

        # ── AI Director Phase 1 — safe edit plan (observation only, no override) ──
        _ai_edit_plan = None
        if getattr(payload, "ai_director_enabled", False):
            try:
                from app.ai.director.ai_director import create_ai_edit_plan as _create_ai_plan
                _ai_context = {
                    "job_id": job_id,
                    "srt_path": str(full_srt) if full_srt_available else None,
                    "scenes": scenes,
                    "duration": source.get("duration", 0.0),
                    "market": getattr(payload, "viral_market", None),
                    # Phase 4: source path for optional beat analysis
                    "source_path": str(source_path) if source_path else None,
                }
                _ai_edit_plan = _create_ai_plan(payload, _ai_context)
                if _ai_edit_plan is not None:
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="ai_director_plan_created",
                        level="INFO",
                        message=(
                            f"AI Director plan: mode={_ai_edit_plan.mode} "
                            f"segments={len(_ai_edit_plan.selected_segments)} "
                            f"fallback={_ai_edit_plan.fallback_used}"
                        ),
                        step="ai_director",
                        context=_ai_edit_plan.to_dict(),
                    )
            except Exception as _ai_err:
                _job_log(
                    effective_channel, job_id,
                    f"ai_director_failed_fallback: {_ai_err}",
                    kind="warning",
                )

        # ── AI Execution Mode Resolution (Phase 60D) — control only ─────────────
        # Resolve BEFORE Phase 59 blocks so they can be gated correctly.
        # mode=off blocks all Phase 59 promotion; other modes run Phase 59 normally.
        _ai_exec_mode: str = "safe"
        if _ai_edit_plan is not None:
            try:
                from app.ai.execution_mode.execution_mode_engine import (
                    resolve_execution_mode as _resolve_exec_mode,
                )
                _mode_result = _resolve_exec_mode(payload, context={"job_id": job_id})
                _mode_data = _mode_result.get("ai_execution_mode") or {}
                _ai_exec_mode = str(_mode_data.get("effective_mode") or "safe")
                try:
                    _ai_edit_plan.ai_execution_mode = _mode_data
                except Exception:
                    pass
                logger.info(
                    "ai_execution_mode_resolved job_id=%s mode=%s source=%s",
                    job_id, _ai_exec_mode, _mode_data.get("source", "unknown"),
                )
            except Exception as _mode_err:
                _ai_exec_mode = "safe"
                logger.warning(
                    "ai_execution_mode_resolution_failed job_id=%s: %s", job_id, _mode_err
                )

        # mode=off: write rollback metadata + stub promotion reports, then skip Phase 59
        if _ai_edit_plan is not None and _ai_exec_mode == "off":
            _rollback = {
                "active":          True,
                "reason":          "mode_off",
                "blocked_domains": ["subtitle", "camera", "segment"],
            }
            try:
                _ai_edit_plan.ai_execution_rollback = _rollback
            except Exception:
                pass
            _mode_off_stub = {
                "applied":  False,
                "eligible": True,
                "reason":   "mode_off",
                "blocked":  True,
                "confidence": 0.0,
            }
            try:
                _ai_edit_plan.subtitle_execution_promotion = dict(_mode_off_stub)
                _ai_edit_plan.camera_execution_promotion   = dict(_mode_off_stub)
                _ai_edit_plan.segment_selection_promotion  = dict(_mode_off_stub)
            except Exception:
                pass
            logger.info(
                "ai_execution_rollback_active job_id=%s reason=mode_off blocked=subtitle,camera,segment",
                job_id,
            )

        # ── AI Render Influence (Phase 10) — bounded opt-in payload adjustments ──
        _ai_influence_report: dict = {"enabled": False}
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.director.render_influence import apply_ai_render_influence as _apply_ai_influence
                payload, _ai_influence_report = _apply_ai_influence(
                    payload,
                    _ai_edit_plan,
                    context={"job_id": job_id},
                )
                logger.info(
                    "ai_render_influence_applied job_id=%s applied=%d skipped=%d",
                    job_id,
                    len(_ai_influence_report.get("applied", [])),
                    len(_ai_influence_report.get("skipped", [])),
                )
            except Exception as _inf_err:
                _ai_influence_report = {
                    "enabled": True,
                    "applied": [],
                    "skipped": [],
                    "warnings": [f"influence_module_error:{type(_inf_err).__name__}"],
                }
                logger.warning("ai_render_influence_module_failed job_id=%s: %s", job_id, _inf_err)
        elif _ai_edit_plan is not None:
            logger.debug("ai_render_influence_skipped job_id=%s (disabled)", job_id)

        # ── AI Beat Execution (Phase 11) — metadata-only beat plan ───────────
        _ai_beat_report: dict = {"enabled": False}
        if _ai_edit_plan is not None and getattr(payload, "ai_beat_execution_enabled", False):
            beat_exec_cached = getattr(_ai_edit_plan, "beat_execution", None)
            if isinstance(beat_exec_cached, dict) and beat_exec_cached.get("beat_available"):
                _ai_beat_report = beat_exec_cached
                logger.info(
                    "ai_beat_execution_planned job_id=%s bpm=%s count=%d enabled=%s",
                    job_id,
                    _ai_beat_report.get("bpm"),
                    _ai_beat_report.get("beat_count", 0),
                    _ai_beat_report.get("enabled", False),
                )
            else:
                try:
                    from app.ai.director.beat_execution import build_beat_execution_plan as _build_beat
                    _ai_beat_report = _build_beat(
                        _ai_edit_plan, payload, context={"job_id": job_id}
                    )
                    _ai_edit_plan.beat_execution = _ai_beat_report
                    logger.info(
                        "ai_beat_execution_planned job_id=%s bpm=%s count=%d enabled=%s",
                        job_id,
                        _ai_beat_report.get("bpm"),
                        _ai_beat_report.get("beat_count", 0),
                        _ai_beat_report.get("enabled", False),
                    )
                except Exception as _beat_err:
                    _ai_beat_report = {
                        "enabled": False,
                        "warnings": [f"beat_execution_module_error:{type(_beat_err).__name__}"],
                    }
                    logger.warning("ai_beat_execution_module_failed job_id=%s: %s", job_id, _beat_err)
        elif _ai_edit_plan is not None:
            logger.debug("ai_beat_execution_skipped job_id=%s (disabled)", job_id)

        # Save original scored order before Phase 59C (used by Phase 59D segment gate)
        _scored_original: list = list(scored)

        # ── AI Segment Selection Promotion (Phase 59C) ───────────────────────
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.segment_promotion.segment_promotion_engine import (
                    promote_segment_selection as _promote_segments,
                )
                scored, _seg_promo = _promote_segments(
                    scored, _ai_edit_plan, payload, context={"job_id": job_id}
                )
                _promo = _seg_promo.get("segment_selection_promotion") or {}
                try:
                    _ai_edit_plan.segment_selection_promotion = _promo
                except Exception:
                    pass
                if _promo.get("applied"):
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="ai_segment_promotion_applied",
                        level="INFO",
                        message=(
                            f"AI segment promotion: {_promo.get('selected_count', 0)}"
                            f"/{_promo.get('total_count', 0)} segments reordered"
                        ),
                        step="ai_segment_promotion",
                        context=_promo,
                    )
                    logger.info(
                        "ai_segment_promotion_applied job_id=%s selected=%d total=%d conf=%.3f",
                        job_id,
                        _promo.get("selected_count", 0),
                        _promo.get("total_count", 0),
                        _promo.get("confidence", 0.0),
                    )
                else:
                    logger.debug(
                        "ai_segment_promotion_skipped job_id=%s reason=%s",
                        job_id,
                        _promo.get("reason", "not_eligible"),
                    )
            except Exception as _seg_err:
                logger.warning(
                    "ai_segment_promotion_failed job_id=%s: %s", job_id, _seg_err
                )

        # ── AI Quality Gate — Segment (Phase 59D) ────────────────────────────
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.quality_gate.quality_gate_engine import (
                    apply_segment_quality_gate as _segment_quality_gate,
                )
                scored, _seg_gate = _segment_quality_gate(
                    scored, _scored_original, _ai_edit_plan, context={"job_id": job_id}
                )
                _sg = _seg_gate.get("segment_quality_gate") or {}
                try:
                    existing_qg = getattr(_ai_edit_plan, "quality_gated_influence", {}) or {}
                    existing_qg["segment"] = _sg
                    _ai_edit_plan.quality_gated_influence = existing_qg
                except Exception:
                    pass
                if _sg.get("applied"):
                    logger.info(
                        "ai_segment_quality_gate_applied job_id=%s action=%s reverted=%s",
                        job_id,
                        _sg.get("gate_action"),
                        _sg.get("reverted"),
                    )
                else:
                    logger.debug(
                        "ai_segment_quality_gate_no_change job_id=%s action=%s",
                        job_id,
                        _sg.get("gate_action", "no_change"),
                    )
            except Exception as _qg_err:
                logger.warning(
                    "ai_segment_quality_gate_failed job_id=%s: %s", job_id, _qg_err
                )

        # ── AI Execution Metrics (Phase 60A) — observability only ────────
        if _ai_edit_plan is not None:
            try:
                from app.ai.metrics.ai_execution_metrics_engine import (
                    build_ai_execution_metrics as _build_metrics,
                )
                _metrics_result = _build_metrics(
                    _ai_edit_plan, payload, context={"job_id": job_id}
                )
                try:
                    _ai_edit_plan.ai_execution_metrics = (
                        _metrics_result.get("ai_execution_metrics") or {}
                    )
                    _ai_edit_plan.ai_execution_summary = (
                        _metrics_result.get("ai_execution_summary") or {}
                    )
                except Exception:
                    pass
                _summary = _metrics_result.get("ai_execution_summary") or {}
                logger.info(
                    "ai_execution_metrics_collected job_id=%s "
                    "sub=%s cam=%s seg=%s qg_blocks=%d uo=%d assistance=%s",
                    job_id,
                    _summary.get("subtitle_apply"),
                    _summary.get("camera_apply"),
                    _summary.get("segment_apply"),
                    _summary.get("quality_gate_blocks", 0),
                    _summary.get("user_override_count", 0),
                    _summary.get("overall_ai_assistance", "none"),
                )
            except Exception as _met_err:
                logger.warning(
                    "ai_execution_metrics_failed job_id=%s: %s", job_id, _met_err
                )

        # ── A/B Render Evaluation (Phase 60B) — evaluation only ──────────
        # baseline=None in single renders → returns available=False candidate summary.
        # Full A/B comparison requires an explicit baseline from a prior AI-OFF render.
        if _ai_edit_plan is not None:
            try:
                from app.ai.ab_evaluation.ab_evaluation_engine import (
                    build_ab_evaluation as _build_ab_eval,
                )
                _ab_result = _build_ab_eval(
                    _ai_edit_plan,
                    baseline=None,
                    context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.ai_ab_evaluation = (
                        _ab_result.get("ai_ab_evaluation") or {}
                    )
                except Exception:
                    pass
                _ab = _ab_result.get("ai_ab_evaluation") or {}
                logger.info(
                    "ai_ab_evaluation_collected job_id=%s available=%s winner=%s confidence=%.3f",
                    job_id,
                    _ab.get("available"),
                    _ab.get("winner", "unknown"),
                    float(_ab.get("confidence") or 0.0),
                )
            except Exception as _ab_err:
                logger.warning(
                    "ai_ab_evaluation_failed job_id=%s: %s", job_id, _ab_err
                )

        # ── Creator Benchmark Suite (Phase 60C) — benchmarking only ──────────
        # Evaluates AI quality against creator archetype benchmarks using
        # Phase 60B A/B evaluation signals. No render mutation.
        if _ai_edit_plan is not None:
            try:
                from app.ai.creator_benchmark.creator_benchmark_engine import (
                    build_creator_benchmark as _build_creator_benchmark,
                )
                _cb_result = _build_creator_benchmark(
                    _ai_edit_plan,
                    context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.creator_benchmark_summary = (
                        _cb_result.get("creator_benchmark_summary") or {}
                    )
                except Exception:
                    pass
                _cb = _cb_result.get("creator_benchmark_summary") or {}
                logger.info(
                    "creator_benchmark_collected job_id=%s available=%s "
                    "creator_type=%s status=%s delta=%s",
                    job_id,
                    _cb.get("available"),
                    _cb.get("creator_type", "unknown"),
                    _cb.get("benchmark_status", "unknown"),
                    _cb.get("overall_delta"),
                )
            except Exception as _cb_err:
                logger.warning(
                    "creator_benchmark_failed job_id=%s: %s", job_id, _cb_err
                )

        # ── Creator Archetype Strategy (Phase 61A) — advisory metadata only ──────
        # Maps creator type to deterministic style strategy preferences.
        # Does NOT mutate render execution. Advisory guidance for future influence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.creator_archetype.creator_archetype_engine import (
                    build_creator_archetype_strategy as _build_archetype_strategy,
                )
                _arch_result = _build_archetype_strategy(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.creator_archetype_strategy = (
                        _arch_result.get("creator_archetype_strategy") or {}
                    )
                except Exception:
                    pass
                _arch = _arch_result.get("creator_archetype_strategy") or {}
                logger.info(
                    "creator_archetype_strategy_built job_id=%s available=%s "
                    "creator_type=%s confidence=%.3f",
                    job_id,
                    _arch.get("available"),
                    _arch.get("creator_type", "unknown"),
                    float(_arch.get("confidence") or 0.0),
                )
            except Exception as _arch_err:
                logger.warning(
                    "creator_archetype_strategy_failed job_id=%s: %s", job_id, _arch_err
                )

        # ── Creator Render Strategy Fusion (Phase 61D) — advisory metadata only ──
        # Fuses Phase 61A archetype + creator_preference_profile + platform strategy
        # + quality metadata into a coherent creator-style render strategy.
        # Does NOT mutate render execution. Metadata for UX and future influence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.creator_style.creator_render_strategy_engine import (
                    build_creator_render_strategy as _build_creator_render_strategy,
                )
                _crs_result = _build_creator_render_strategy(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.creator_render_strategy = (
                        _crs_result.get("creator_render_strategy") or {}
                    )
                except Exception:
                    pass
                _crs = _crs_result.get("creator_render_strategy") or {}
                logger.info(
                    "creator_render_strategy_built job_id=%s available=%s "
                    "creator_type=%s confidence=%.3f",
                    job_id,
                    _crs.get("available"),
                    _crs.get("creator_type", "unknown"),
                    float(_crs.get("confidence") or 0.0),
                )
            except Exception as _crs_err:
                logger.warning(
                    "creator_render_strategy_failed job_id=%s: %s", job_id, _crs_err
                )

        # ── Render Outcome Tracking (Phase 62A) — tracking-only, no mutation ────
        # Aggregates Phase 60A/60B/60C/61D metadata into a structured outcome
        # record for audit, debug, and future learning. No render mutation.
        if _ai_edit_plan is not None:
            try:
                from app.ai.outcome_tracking.render_outcome_tracking_engine import (
                    build_render_outcome_tracking as _build_render_outcome_tracking,
                )
                _rot_result = _build_render_outcome_tracking(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.render_outcome_tracking = (
                        _rot_result.get("render_outcome_tracking") or {}
                    )
                except Exception:
                    pass
                _rot = _rot_result.get("render_outcome_tracking") or {}
                logger.info(
                    "render_outcome_tracking_built job_id=%s available=%s "
                    "overall_result=%s ai_effectiveness=%s creator_fit=%s confidence=%.3f",
                    job_id,
                    _rot.get("available"),
                    _rot.get("overall_result", "unknown"),
                    _rot.get("ai_effectiveness", "unknown"),
                    (_rot.get("benchmark_result") or {}).get("creator_fit", "unknown"),
                    float(_rot.get("confidence") or 0.0),
                )
            except Exception as _rot_err:
                logger.warning(
                    "render_outcome_tracking_failed job_id=%s: %s", job_id, _rot_err
                )

        # ── Creator Preference Reinforcement (Phase 62B) — metadata only ─────
        # Converts positive/negative outcomes into bounded preference signals.
        # No render mutation, no autonomous retraining, no external persistence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.outcome_tracking.creator_preference_reinforcement_engine import (
                    build_creator_preference_reinforcement as _build_cpr,
                )
                _cpr_result = _build_cpr(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.creator_preference_reinforcement = (
                        _cpr_result.get("creator_preference_reinforcement") or {}
                    )
                except Exception:
                    pass
                _cpr = _cpr_result.get("creator_preference_reinforcement") or {}
                logger.info(
                    "creator_preference_reinforcement_built job_id=%s available=%s "
                    "domains_reinforced=%d negative_signals=%d confidence=%.3f",
                    job_id,
                    _cpr.get("available"),
                    len(_cpr.get("reinforced_preferences") or {}),
                    len(_cpr.get("negative_signals") or []),
                    float(_cpr.get("confidence") or 0.0),
                )
            except Exception as _cpr_err:
                logger.warning(
                    "creator_preference_reinforcement_failed job_id=%s: %s", job_id, _cpr_err
                )

        # ── Success Pattern Mining (Phase 62C) — pattern metadata only ──────
        # Discovers deterministic success patterns from this render's outcome.
        # No render mutation, no autonomous training, no external persistence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.outcome_tracking.render_success_pattern_engine import (
                    build_render_success_patterns as _build_rsp,
                )
                _rsp_result = _build_rsp(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.render_success_patterns = (
                        _rsp_result.get("render_success_patterns") or {}
                    )
                except Exception:
                    pass
                _rsp = _rsp_result.get("render_success_patterns") or {}
                logger.info(
                    "render_success_patterns_built job_id=%s available=%s "
                    "pattern_count=%d confidence=%.3f",
                    job_id,
                    _rsp.get("available"),
                    len(_rsp.get("patterns") or []),
                    float(_rsp.get("confidence") or 0.0),
                )
            except Exception as _rsp_err:
                logger.warning(
                    "render_success_patterns_failed job_id=%s: %s", job_id, _rsp_err
                )

        # ── Learning-Aware Influence Calibration (Phase 62D) — metadata only ─
        # Calibrates bounded AI influence using patterns/reinforcement signals.
        # No render mutation, no autonomous retraining, no external persistence.
        if _ai_edit_plan is not None:
            try:
                from app.ai.outcome_tracking.learning_influence_calibration_engine import (
                    build_learning_influence_calibration as _build_lic,
                )
                _lic_result = _build_lic(
                    _ai_edit_plan, context={"job_id": job_id},
                )
                try:
                    _ai_edit_plan.learning_influence_calibration = (
                        _lic_result.get("learning_influence_calibration") or {}
                    )
                except Exception:
                    pass
                _lic = _lic_result.get("learning_influence_calibration") or {}
                logger.info(
                    "learning_influence_calibration_built job_id=%s available=%s "
                    "mode=%s pos_domains=%d neg_entries=%d confidence=%.3f",
                    job_id,
                    _lic.get("available"),
                    _lic.get("execution_mode", "unknown"),
                    len(_lic.get("calibration") or {}),
                    len(_lic.get("negative_calibration") or []),
                    float(_lic.get("confidence") or 0.0),
                )
            except Exception as _lic_err:
                logger.warning(
                    "learning_influence_calibration_failed job_id=%s: %s", job_id, _lic_err
                )

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
            final_part = output_dir / f"{_output_stem}_part_{idx:03d}.mp4"
            part_name = f"{_output_stem}_part_{idx:03d}.mp4"
            _sub_target_lang = getattr(payload, "subtitle_target_language", "en")
            translated_srt_part = work_dir / f"{source['slug']}_part_{idx:03d}.{_sub_target_lang}.srt"
            _job_log(effective_channel, job_id, f"Part {idx}/{total_parts} start", kind="debug")

            # Bail out immediately if job was cancelled before this part started
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()
            # Expose the cancel event to _run_ffmpeg_with_retry via thread-local so
            # FFmpeg Popen can be killed mid-encode without changing every call site.
            _cancel_ev = cancel_registry.get_event(job_id)
            if _cancel_ev is not None:
                set_thread_cancel_event(_cancel_ev)

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

            # P4 per-output opening optimization state
            _trim_offset = 0.0
            _hook_subtitle_formatted = False
            _srt_count = 0

            # Performance timing — all in milliseconds, logged at part end
            _t_part_start = time.perf_counter()
            _cut_ms = _first_frame_scan_ms = _subtitle_ass_ms = 0
            _render_ms = _micro_pacing_ms = _quality_validation_ms = 0

            # P4-3: Start silence trim — detect and skip leading dead air (all output clips)
            try:
                _trim_offset = detect_silence_trim_offset(str(source_path), seg["start"], seg["end"])
            except Exception:
                _trim_offset = 0.0
            # Safety: don't trim if effective clip would be shorter than 3 seconds
            if _trim_offset > 0 and (seg["end"] - seg["start"] - _trim_offset) < 3.0:
                _trim_offset = 0.0
            if _trim_offset > 0:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="silence_trim_applied",
                    level="INFO",
                    message=f"Silence trim: {_trim_offset:.3f}s removed from part {idx} start",
                    step="render.silence_trim",
                    context={
                        "part_no": idx,
                        "trim_offset_sec": _trim_offset,
                        "original_start": seg["start"],
                        "effective_start": seg["start"] + _trim_offset,
                    },
                )
                _job_log(effective_channel, job_id, f"Part {idx} silence trim: {_trim_offset:.3f}s offset applied")
            _effective_start = seg["start"] + _trim_offset

            # P4-X: Bad first-frame scan — detect black/dark opening frames and shift start up to 1.0s.
            _visual_trim = 0.0
            _force_accurate_cut = False
            try:
                logger.info("first_frame_scan_started part_no=%d effective_start=%.3f", idx, _effective_start)
                _t_ff = time.perf_counter()
                _visual_trim = detect_bad_first_frame(str(source_path), _effective_start, seg["end"])
                _first_frame_scan_ms = int((time.perf_counter() - _t_ff) * 1000)
                logger.info("first_frame_scan_ms=%d part=%d shift=%.3f", _first_frame_scan_ms, idx, _visual_trim)
            except Exception:
                _visual_trim = 0.0
            if _visual_trim > 0:
                _candidate_total = _trim_offset + _visual_trim
                if (seg["end"] - seg["start"] - _candidate_total) >= 3.0:
                    _trim_offset = _candidate_total
                    _effective_start = seg["start"] + _trim_offset
                    _force_accurate_cut = True
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="first_frame_shift_applied",
                        level="INFO",
                        message=f"Bad first frame detected: shifted part {idx} start by {_visual_trim:.3f}s",
                        step="render.first_frame_scan",
                        context={
                            "part_no": idx,
                            "visual_trim_sec": _visual_trim,
                            "total_trim_sec": _trim_offset,
                            "effective_start": _effective_start,
                            "force_accurate_cut": True,
                        },
                    )
                    _job_log(effective_channel, job_id,
                        f"first_frame_shift_applied part={idx} visual_trim={_visual_trim:.3f}s "
                        f"total_trim={_trim_offset:.3f}s effective_start={_effective_start:.3f}s accurate_cut=True")

            upsert_job_part(job_id, idx, part_name, JobPartStage.CUTTING, 10, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Cutting raw part")
            if not (payload.resume_from_last and raw_part.exists() and raw_part.stat().st_size > 0):
                _t_cut = time.perf_counter()
                cut_video(str(source_path), str(raw_part), _effective_start, seg["end"],
                          retry_count=retry_count, force_accurate_cut=_force_accurate_cut)
                _cut_ms = int((time.perf_counter() - _t_cut) * 1000)
                logger.info("cut_video_ms=%d part=%d", _cut_ms, idx)
                if _force_accurate_cut:
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="accurate_cut_forced",
                        level="INFO",
                        message=f"Accurate re-encode cut used for part {idx} (bad first frame shift)",
                        step="render.cut",
                        context={"part_no": idx, "effective_start": _effective_start},
                    )
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
                    _eff_speed = max(0.5, min(1.5, float(payload.playback_speed or 1.0)))
                    _visual_apply_speed = False
                    _srt_meta = slice_srt_by_time(
                        str(full_srt),
                        str(srt_part),
                        _effective_start,
                        seg["end"],
                        rebase_to_zero=True,
                        playback_speed=_eff_speed,
                        apply_playback_speed=_visual_apply_speed,
                    )
                    _srt_count = _srt_meta.get("subtitle_count", 0)
                    _job_log(
                        effective_channel, job_id,
                        f"subtitle_part_sync part_no={idx} subtitle_slice_mode=visual_burn_in "
                        f"start={seg['start']:.1f}s effective_start={_effective_start:.1f}s end={seg['end']:.1f}s "
                        f"playback_speed={_eff_speed} apply_playback_speed={_visual_apply_speed} count={_srt_count}"
                        + (
                            f" first={_srt_meta['first_start']:.3f}->{_srt_meta['first_end']:.3f}s"
                            f" last={_srt_meta['last_start']:.3f}->{_srt_meta['last_end']:.3f}s"
                            if _srt_count > 0 else " (no speech)"
                        ),
                        kind="debug" if _srt_count > 0 else "warning",
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="subtitle_part_sync",
                        level="INFO" if _srt_count > 0 else "WARNING",
                        message=f"Subtitle sliced for part {idx}: {_srt_count} entries",
                        step="subtitle.slice",
                        context={
                            "part_no": idx,
                            "part_start": seg["start"],
                            "part_end": seg["end"],
                            "effective_start": _effective_start,
                            "subtitle_slice_mode": "visual_burn_in",
                            "playback_speed": _eff_speed,
                            "apply_playback_speed": _visual_apply_speed,
                            "subtitle_count": _srt_count,
                            "first_sub_start": _srt_meta.get("first_start"),
                            "first_sub_end": _srt_meta.get("first_end"),
                            "last_sub_start": _srt_meta.get("last_start"),
                            "last_sub_end": _srt_meta.get("last_end"),
                            "part_srt_path": str(srt_part),
                        },
                    )
                _ass_srt_source = srt_part
                if getattr(payload, "subtitle_translate_enabled", False) and srt_part.exists() and srt_part.stat().st_size > 0:
                    _needs_translated = not (payload.resume_from_last and translated_srt_part.exists() and translated_srt_part.stat().st_size > 0)
                    if _needs_translated:
                        _sub_translate_attempts.append(idx)
                        if cancel_registry.is_cancelled(job_id):
                            raise cancel_registry.JobCancelledError()
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
                                _job_log(
                                    effective_channel, job_id,
                                    f"Translation partially failed for {_sub_target_lang} export — "
                                    f"{len(_block_failures)} subtitle block(s) could not be translated. "
                                    f"Original text preserved for those blocks.",
                                    kind="warning",
                                )
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
                            _job_log(
                                effective_channel, job_id,
                                f"Translation failed for {_sub_target_lang} export (part {idx}). "
                                f"Subtitles will use original language.",
                                kind="warning",
                            )
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
                if _hook_apply_enabled and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        _hook_apply_meta = apply_market_hook_text_to_srt(
                            str(_ass_srt_source),
                            _hook_applied_text,
                            max_hook_blocks=1,
                            max_hook_seconds=5.0,
                        )
                        _hook_affected = int(_hook_apply_meta.get("affected_count") or 0)
                        if _hook_apply_meta.get("applied"):
                            needs_ass = True
                        _job_log(
                            effective_channel,
                            job_id,
                            "market_viral_hook_apply "
                            f"part_no={idx} market={_mv_market} "
                            f"hook_apply_enabled={_hook_apply_enabled} "
                            f"hook_score={_hook_score} "
                            f"subtitle_blocks_affected={_hook_affected} "
                            f"original_hook_text={_hook_apply_meta.get('original_hook_text', '')!r} "
                            f"applied_hook_text={_hook_apply_meta.get('applied_hook_text', '')!r}",
                        )
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="market_viral_hook_applied",
                            level="INFO",
                            message=f"Market Viral hook applied to {_hook_affected} subtitle block(s) (part {idx})",
                            step="subtitle.market_hook",
                            context={
                                "part_no": idx,
                                "market": _mv_market,
                                "hook_apply_enabled": _hook_apply_enabled,
                                "hook_score": _hook_score,
                                "subtitle_blocks_affected": _hook_affected,
                                "original_hook_text": _hook_apply_meta.get("original_hook_text", ""),
                                "applied_hook_text": _hook_apply_meta.get("applied_hook_text", ""),
                            },
                        )
                    except Exception as _hook_exc:
                        logger.warning("market_viral_hook_apply: skipped due to error: %s", _hook_exc)
                elif _hook_apply_enabled:
                    _job_log(
                        effective_channel,
                        job_id,
                        "market_viral_hook_apply "
                        f"part_no={idx} market={_mv_market} "
                        f"hook_apply_enabled={_hook_apply_enabled} "
                        f"hook_score={_hook_score} "
                        "subtitle_blocks_affected=0 "
                        "original_hook_text='' "
                        f"applied_hook_text={_hook_applied_text!r}",
                        kind="warning",
                    )
                if _mv_cfg and _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        apply_market_line_break_to_srt(str(_ass_srt_source), _mv_cfg)
                        needs_ass = True
                    except Exception:
                        pass
                # P4-2: Hook subtitle impact — opening lines of every output clip
                if _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    _hook_orig_len = _ass_srt_source.stat().st_size
                    _hook_blocks = apply_hook_subtitle_format(str(_ass_srt_source))
                    if _hook_blocks > 0:
                        needs_ass = True
                        _hook_subtitle_formatted = True
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="subtitle_hook_format_applied",
                            level="INFO",
                            message=f"Hook subtitle impact applied: {_hook_blocks} blocks (part {idx})",
                            step="subtitle.hook_format",
                            context={
                                "part_no": idx,
                                "original_length": _hook_orig_len,
                                "new_length": _ass_srt_source.stat().st_size,
                                "lines_count": _hook_blocks,
                            },
                        )
                # Content-type subtitle auto-default — fires only when no explicit style set.
                # Creator's explicit choice (any non-empty subtitle_style) always wins.
                _CONTENT_TYPE_SUB_DEFAULTS: dict[str, str] = {
                    "interview":  "clean",
                    "commentary": "viral",
                    "vlog":       "story",
                    "tutorial":   "clean",
                    "montage":    "gaming",
                }
                _raw_sub_style = (payload.subtitle_style or "").strip()
                _effective_subtitle_style = (
                    _CONTENT_TYPE_SUB_DEFAULTS.get(
                        seg.get("content_type_hint", "vlog"), "tiktok_bounce_v1"
                    )
                    if not _raw_sub_style
                    else _raw_sub_style
                )

                # S4: Subtitle emphasis — semantic wrap + keyword uppercase + highlight markers
                if _ass_srt_source.exists() and _ass_srt_source.stat().st_size > 0:
                    try:
                        _emph_blocks = parse_srt_blocks(str(_ass_srt_source))
                        if _emph_blocks:
                            subtitle_emphasis_pass(
                                _emph_blocks,
                                preset_id=_effective_subtitle_style,
                                market=_mv_market,
                                language=_sub_target_lang,
                            )
                            write_srt_blocks(_emph_blocks, str(_ass_srt_source))
                            needs_ass = True
                            _job_log(
                                effective_channel, job_id,
                                f"subtitle_emphasis_applied part={idx} "
                                f"style={_effective_subtitle_style} market={_mv_market} "
                                f"lang={_sub_target_lang} blocks={len(_emph_blocks)}",
                                kind="info",
                            )
                        else:
                            _job_log(
                                effective_channel, job_id,
                                f"subtitle_emphasis_skipped part={idx} reason=empty_blocks "
                                f"style={_effective_subtitle_style}",
                                kind="debug",
                            )
                    except Exception:
                        _job_log(
                            effective_channel, job_id,
                            f"subtitle_emphasis_error part={idx} style={_effective_subtitle_style} "
                            f"market={_mv_market} — emphasis pass skipped, render continues",
                            kind="warning",
                        )
                if needs_ass:
                    _play_res_y = _aspect_play_res_y(payload.aspect_ratio)
                    _margin_v = getattr(payload, "sub_margin_v", 180)
                    _t_sub = time.perf_counter()
                    if _effective_subtitle_style == "pro_karaoke":
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
                            subtitle_style=_effective_subtitle_style,
                            scale_y=payload.frame_scale_y,
                            highlight_per_word=payload.highlight_per_word,
                            font_name=getattr(payload, "sub_font", "Bungee"),
                            margin_v=_margin_v,
                            play_res_y=_play_res_y,
                            x_percent=getattr(payload, "sub_x_percent", 50.0),
                            font_size=getattr(payload, "sub_font_size", 0),
                        )
                    _subtitle_ass_ms = int((time.perf_counter() - _t_sub) * 1000)
                    logger.info(
                        "subtitle_ass_ms=%d part=%d style=%s content_type=%s",
                        _subtitle_ass_ms, idx, _effective_subtitle_style,
                        seg.get("content_type_hint", ""),
                    )
                    _job_log(
                        effective_channel, job_id,
                        f"Part {idx} subtitle: style={_effective_subtitle_style} "
                        f"(payload={payload.subtitle_style or 'auto'}) "
                        f"font_size={getattr(payload, 'sub_font_size', 0)} "
                        f"margin_v={_margin_v} x_pct={getattr(payload, 'sub_x_percent', 50.0):.1f} "
                        f"play_res_y={_play_res_y} aspect={payload.aspect_ratio}",
                        kind="info",
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="subtitle_style_applied",
                        level="INFO",
                        message=f"Subtitle style applied for part {idx}: {_effective_subtitle_style}",
                        step="render.subtitle",
                        context={
                            "part_no": idx,
                            "subtitle_style": _effective_subtitle_style,
                            "subtitle_style_source": "auto" if not _raw_sub_style else "explicit",
                            "content_type_hint": seg.get("content_type_hint", ""),
                            "font_size": getattr(payload, "sub_font_size", 0),
                            "margin_v": _margin_v,
                            "play_res_y": _play_res_y,
                            "aspect_ratio": payload.aspect_ratio,
                        },
                    )
            else:
                _job_log(effective_channel, job_id, f"Part {idx} subtitle disabled", kind="debug")

            # ── Hook overlay: build per-part text_layers with optional opening banner ──
            # Operates on a copy so the global normalized_text_layers is never mutated.
            _hook_overlay_applied_for_part = False
            _part_text_layers = list(normalized_text_layers)
            if _hook_overlay_enabled and len(_part_text_layers) < MAX_TEXT_LAYERS:
                _hook_srt_path = str(srt_part) if srt_part.exists() and srt_part.stat().st_size > 0 else None
                _hook_text, _hook_source = resolve_hook_overlay_text(
                    _hook_applied_text if _hook_applied_text else None,
                    _hook_srt_path,
                )
                if _hook_text:
                    _hook_overlay_applied_for_part = True
                    # end_time is pre-setpts, so multiply by speed so the overlay
                    # shows for ~1.5 s of perceived output time at any playback rate.
                    _hook_spd = max(0.5, min(1.5, float(payload.playback_speed or 1.07)))
                    _hook_end_t = round(min(2.5, 1.5 * _hook_spd), 3)
                    _part_text_layers = [
                        {
                            "id": f"hook_overlay_{idx}",
                            "text": _hook_text,
                            "font_family": "Bungee",
                            "font_size": 52,
                            "color": "#FFFFFF",
                            "position": "top-center",
                            "x_percent": 50.0,
                            "y_percent": 26.0,
                            "alignment": "center",
                            "bold": False,
                            "outline": {"enabled": True, "thickness": 4},
                            "shadow": {"enabled": False, "offset_x": 0, "offset_y": 0},
                            "background": {"enabled": True, "color": "#000000CC", "padding": 18},
                            "start_time": 0.0,
                            "end_time": _hook_end_t,
                            "order": -1,
                        }
                    ] + _part_text_layers
                    logger.info(
                        "hook_overlay_selected part=%d text=%r source=%s end_t=%.3f",
                        idx, _hook_text, _hook_source, _hook_end_t,
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="hook_overlay_applied",
                        level="INFO",
                        message=f"Hook overlay applied for part {idx}: {_hook_text!r}",
                        step="render.hook_overlay",
                        context={
                            "part_no": idx,
                            "hook_text": _hook_text,
                            "source": _hook_source,
                            "end_time": _hook_end_t,
                            "hook_overlay_duration": _hook_end_t,
                        },
                    )
                    _job_log(effective_channel, job_id,
                        f"hook_overlay_applied part={idx} text={_hook_text!r} source={_hook_source} "
                        f"end_t={_hook_end_t:.3f}s")
                else:
                    logger.info("hook_overlay_skipped_reason part=%d reason=%s", idx, _hook_source)
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="hook_overlay_skipped",
                        level="INFO",
                        message=f"Hook overlay skipped for part {idx}: {_hook_source}",
                        step="render.hook_overlay",
                        context={"part_no": idx, "reason": _hook_source},
                    )

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
                    effective_channel,
                ),
                daemon=True,
                name=f"progress-timer-{job_id[:8]}-p{idx}",
            )
            _encode_timer.start()
            _t_encode = time.perf_counter()
            _t_render = time.perf_counter()
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
                    text_layers=_part_text_layers,
                    loudnorm_enabled=getattr(payload, "loudnorm_enabled", False),
                    ffmpeg_threads=_ffmpeg_threads,
                    content_type=seg.get("content_type_hint", "vlog"),
                )
            finally:
                _encode_stop.set()
                _encode_timer.join(timeout=5.0)
            _render_ms = int((time.perf_counter() - _t_render) * 1000)
            logger.info("render_part_ms=%d part=%d codec=%s crop=%s",
                        _render_ms, idx, payload.video_codec, payload.motion_aware_crop)
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
                        if cancel_registry.is_cancelled(job_id):
                            raise cancel_registry.JobCancelledError()
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
                            _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                                str(_part_subtitle_voice_path),
                                payload,
                                effective_channel=effective_channel,
                                job_id=job_id,
                                part_no=idx,
                                source="subtitle",
                            )
                        except Exception as _part_tts_exc:
                            _part_subtitle_voice_path = None
                            _job_log(effective_channel, job_id, f"voice_part_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                            _job_log(effective_channel, job_id, f"Narration generation failed for part {idx}. Continuing without narration.", kind="warning")
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
                            _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                                str(_part_subtitle_voice_path),
                                payload,
                                effective_channel=effective_channel,
                                job_id=job_id,
                                part_no=idx,
                                source="translated_subtitle",
                            )
                        except Exception as _part_tts_exc:
                            _part_subtitle_voice_path = None
                            _job_log(effective_channel, job_id, f"voice_translated_subtitle_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                            _job_log(effective_channel, job_id, f"Narration generation failed for part {idx}. Continuing without narration.", kind="warning")
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

            # P4-4: Micro pacing — compress mid-clip silences (all output clips)
            _micro_pacing_applied = False
            _micro_pacing_trim_sec = 0.0
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()
            if final_part.exists() and final_part.stat().st_size > 0:
                _paced_part = work_dir / f"{source['slug']}_part_{idx:03d}_paced.mp4"
                _t_mp = time.perf_counter()
                try:
                    _seg_content_type = seg.get("content_type_hint", "vlog")
                    _pacing = apply_micro_pacing(
                        str(final_part), str(_paced_part),
                        content_type=_seg_content_type,
                    )
                    _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
                    if _pacing["applied"] and _paced_part.exists() and _paced_part.stat().st_size > 0:
                        os.replace(str(_paced_part), str(final_part))
                        _micro_pacing_applied = True
                        _micro_pacing_trim_sec = max(0.0, float(_pacing.get("total_trim_ms") or 0) / 1000.0)
                        _job_log(
                            effective_channel, job_id,
                            f"Part {idx} micro pacing: {_pacing['segments_trimmed']} segments, "
                            f"{_pacing['total_trim_ms']}ms trimmed, "
                            f"content_type={_seg_content_type}",
                        )
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="micro_pacing_applied",
                            level="INFO",
                            message=(
                                f"Micro pacing applied: {_pacing['segments_trimmed']} segments, "
                                f"{_pacing['total_trim_ms']}ms removed"
                            ),
                            step="render.micro_pacing",
                            context={
                                "part_no": idx,
                                "segments_trimmed": _pacing["segments_trimmed"],
                                "total_trim_ms": _pacing["total_trim_ms"],
                                "method": _pacing["method"],
                                "content_type": _seg_content_type,
                            },
                        )
                    else:
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="micro_pacing_skipped",
                            level="INFO",
                            message="Micro pacing skipped: no qualifying silence segments",
                            step="render.micro_pacing",
                            context={"part_no": idx},
                        )
                except subprocess.TimeoutExpired:
                    _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
                    _job_log(
                        effective_channel, job_id,
                        f"micro_pacing_timeout part_no={idx} elapsed_ms={_micro_pacing_ms} — skipped, original kept",
                        kind="warning",
                    )
                except Exception as _pace_exc:
                    _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
                    _job_log(
                        effective_channel, job_id,
                        f"micro_pacing_failed part_no={idx}: {_pace_exc}",
                        kind="warning",
                    )
                finally:
                    _safe_unlink(_paced_part)
                logger.info("micro_pacing_ms=%d part=%d applied=%s", _micro_pacing_ms, idx, _micro_pacing_applied)

            # P4 combined opening optimization summary — emitted for every output part
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="p4_output_opening_optimized",
                level="INFO",
                message=(
                    f"P4 opening: part {idx} trim={_trim_offset:.3f}s "
                    f"hook={_hook_subtitle_formatted} pacing={_micro_pacing_applied}"
                ),
                step="render.p4_opening",
                context={
                    "part_no": idx,
                    "original_start": seg["start"],
                    "effective_start": _effective_start,
                    "trim_offset": _trim_offset,
                    "original_duration": seg["end"] - seg["start"],
                    "effective_duration": seg["end"] - _effective_start,
                    "subtitle_count": _srt_count,
                    "hook_subtitle_formatted": _hook_subtitle_formatted,
                    "micro_pacing_applied": _micro_pacing_applied,
                    "micro_pacing_trim_sec": _micro_pacing_trim_sec,
                },
            )

            _encode_ms = int((time.perf_counter() - _t_encode) * 1000)
            _total_part_ms = int((time.perf_counter() - _t_part_start) * 1000)
            _effective_duration = max(0.0, float(seg["end"]) - float(_effective_start))
            _render_speed = max(0.5, min(1.5, float(payload.playback_speed or 1.0)))
            _remotion_intro_sec = _maybe_prepend_remotion_hook_intro(
                final_part,
                payload,
                effective_channel=effective_channel,
                job_id=job_id,
                part_no=idx,
                headline_text="STOP SCROLLING",
                duration_sec=1.0,
            )
            _expected_final_duration = max(
                0.0,
                (_effective_duration / _render_speed) - _micro_pacing_trim_sec + _remotion_intro_sec,
            )
            _speed_ratio = round(_expected_final_duration * 1000 / max(_encode_ms, 1), 2)
            logger.info(
                "total_part_render_ms=%d part=%d "
                "cut_ms=%d first_frame_ms=%d subtitle_ass_ms=%d "
                "render_ms=%d pacing_ms=%d quality_ms=%d",
                _total_part_ms, idx,
                _cut_ms, _first_frame_scan_ms, _subtitle_ass_ms,
                _render_ms, _micro_pacing_ms, _quality_validation_ms,
            )
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
                f"expected_final_duration={_expected_final_duration:.2f}s speed_ratio={_speed_ratio}x "
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
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="market_viral_scored",
                    level="INFO",
                    message=(
                        f"Part {idx} market viral: {seg['mv_viral_score']} "
                        f"{seg['mv_viral_tier']} ({seg['mv_viral_market']})"
                    ),
                    step="render.market_viral",
                    context={
                        "part_no":              idx,
                        "market_viral_score":   seg["mv_viral_score"],
                        "market_viral_tier":    seg["mv_viral_tier"],
                        "market_viral_market":  seg["mv_viral_market"],
                        "market_viral_reasons": seg["mv_viral_reasons"][:2],
                    },
                )
            except Exception:
                pass

            # ── Combined Score computation ─────────────────────────────────
            try:
                _cs_enabled  = bool(getattr(payload, "combined_scoring_enabled", False))
                _cs_adaptive = bool(getattr(payload, "adaptive_scoring_enabled", False))
                _cs_viral    = float(seg.get("viral_score", 0) or 0)
                _cs_mv_raw   = seg.get("mv_viral_score")
                _cs_mv       = float(_cs_mv_raw) if _cs_mv_raw is not None else _cs_viral
                _cs_hook_raw = (seg.get("hook_text_score") or seg.get("hook_timing_score") or
                                seg.get("hook_opening_score") or seg.get("hook_score"))
                _cs_hook     = float(_cs_hook_raw or 0)
                _cs_dur      = float(seg.get("duration") or 0) or None

                _cs_weights = resolve_combined_score_weights(
                    target_market=_mv_market,
                    has_market_score=(_cs_mv_raw is not None),
                    has_hook_score=(_cs_hook_raw is not None and float(_cs_hook_raw) > 0),
                    duration=_cs_dur,
                    adaptive_enabled=_cs_adaptive,
                )
                seg["combined_weights"] = _cs_weights

                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="adaptive_score_weights_resolved",
                    level="INFO",
                    message=f"Part {idx} weights v={_cs_weights['viral_weight']} m={_cs_weights['market_weight']} h={_cs_weights['hook_weight']} reason={_cs_weights['reason']}",
                    step="render.combined_score",
                    context={
                        "part_no":                  idx,
                        "adaptive_scoring_enabled": _cs_adaptive,
                        "target_market":            _mv_market,
                        "duration":                 _cs_dur,
                        "viral_weight":             _cs_weights["viral_weight"],
                        "market_weight":            _cs_weights["market_weight"],
                        "hook_weight":              _cs_weights["hook_weight"],
                        "reason":                   _cs_weights["reason"],
                    },
                )

                _cs_raw = (
                    _cs_viral * _cs_weights["viral_weight"] +
                    _cs_mv    * _cs_weights["market_weight"] +
                    _cs_hook  * _cs_weights["hook_weight"]
                )
                seg["combined_score"] = round(max(0.0, min(100.0, _cs_raw)), 1)
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="combined_score_computed",
                    level="INFO",
                    message=f"Part {idx} combined_score={seg['combined_score']}",
                    step="render.combined_score",
                    context={
                        "part_no":                  idx,
                        "viral_score":              _cs_viral,
                        "market_viral_score":       _cs_mv,
                        "hook_score_component":     _cs_hook,
                        "combined_score":           seg["combined_score"],
                        "combined_scoring_enabled": _cs_enabled,
                        "viral_weight":             _cs_weights["viral_weight"],
                        "market_weight":            _cs_weights["market_weight"],
                        "hook_weight":              _cs_weights["hook_weight"],
                    },
                )
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
                expected_duration=_expected_final_duration if _expected_final_duration > 0 else None,
                expect_audio=_expect_audio,
            )
            _actual_final_duration = float((_qa.get("metadata") or {}).get("duration") or 0.0)
            _job_log(
                effective_channel,
                job_id,
                f"Part {idx} duration validation: expected_final_duration={_expected_final_duration:.3f}s "
                f"actual_final_duration={_actual_final_duration:.3f}s "
                f"effective_start={float(_effective_start):.3f}s segment_end={float(seg['end']):.3f}s "
                f"playback_speed={_render_speed:.4f}",
                kind="debug",
            )
            if not _qa["ok"]:
                _qa_code = str(_qa.get("code") or "RN001")
                _job_log(effective_channel, job_id,
                         f"Part {idx} output_validation_failed: {_qa['error']} | "
                         f"code={_qa_code} output={final_part} meta={_qa['metadata']}", kind="error")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_validation_failed",
                    level="ERROR",
                    message=f"Part {idx} output validation failed: {_qa['error']}",
                    step="render.output.validate",
                    error_code=_qa_code,
                    context={
                        "part_no": idx,
                        "output_file": str(final_part),
                        "validation_code": _qa_code,
                        **_qa["metadata"],
                    },
                )
                raise RuntimeError(f"output_validation_failed[{_qa_code}]: {_qa['error']}")
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

            # ── Output quality validator: perceptual checks + score penalty ──────
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="output_quality_validation_started",
                level="INFO",
                message=f"Part {idx} quality validation started",
                step="render.output.quality",
                context={"part_no": idx, "output_file": str(final_part)},
            )
            _t_qq = time.perf_counter()
            _qq = _assess_output_quality(
                final_part,
                output_dir,
                expect_subtitle=part_subtitle_enabled,
                subtitle_file=ass_part if part_subtitle_enabled else None,
                expect_hook=_hook_overlay_enabled,
                hook_applied=_hook_overlay_applied_for_part,
            )
            _quality_validation_ms = int((time.perf_counter() - _t_qq) * 1000)
            logger.info("quality_validation_ms=%d part=%d penalty=%d",
                        _quality_validation_ms, idx, int(_qq["score_penalty"]))
            _quality_penalty = int(_qq["score_penalty"])
            seg["quality_penalty"] = _quality_penalty
            if _qq["warnings"] or not _qq["passed"]:
                _qq_level = "ERROR" if not _qq["passed"] else "WARNING"
                _qq_evt = "output_quality_validation_failed" if not _qq["passed"] else "output_quality_validation_warning"
                for _qw in _qq["warnings"]:
                    _job_log(effective_channel, job_id, f"Part {idx} quality_warning: {_qw}", kind="warning")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event=_qq_evt,
                    level=_qq_level,
                    message=f"Part {idx} quality validation: {len(_qq['warnings'])} warning(s)",
                    step="render.output.quality",
                    context={
                        "part_no": idx,
                        "output_file": str(final_part),
                        "warnings": _qq["warnings"],
                        "hard_failures": _qq["hard_failures"],
                        "checks": _qq["checks"],
                        "score_penalty": _quality_penalty,
                    },
                )
            else:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_quality_validation_passed",
                    level="INFO",
                    message=f"Part {idx} quality validation passed",
                    step="render.output.quality",
                    context={"part_no": idx, "output_file": str(final_part), "checks": _qq["checks"]},
                )
            if _quality_penalty > 0:
                _job_log(
                    effective_channel, job_id,
                    f"Part {idx} quality_score_penalty: -{_quality_penalty} checks={_qq['checks']}",
                    kind="warning",
                )
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="output_quality_score_penalty_applied",
                    level="WARNING",
                    message=f"Part {idx} quality penalty applied: -{_quality_penalty} points",
                    step="render.output.quality",
                    context={
                        "part_no": idx,
                        "score_penalty": _quality_penalty,
                        "checks": _qq["checks"],
                        "warnings": _qq["warnings"],
                    },
                )
            if _quality_penalty > 20:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.quality_penalty_high",
                    level="WARNING",
                    message=f"Part {idx} quality penalty high: -{_quality_penalty} points",
                    step="render.output.quality",
                    context={
                        "part_no": idx,
                        "warnings": _qq["warnings"],
                        "score_penalty": _quality_penalty,
                    },
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
                    if cancel_registry.is_cancelled(job_id):
                        raise cancel_registry.JobCancelledError()
                    try:
                        result = _process_one_part(idx, seg)
                        if result["output"]:
                            outputs.append(result["output"])
                        if result["row"]:
                            rows.append(result["row"])
                    except Exception as part_err:
                        failure_detail = _render_part_failure_detail(idx, part_err)
                        failed_parts.append(failure_detail)
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
                        _job_log(
                            effective_channel,
                            job_id,
                            f"Part {idx}/{total_parts} failed: "
                            f"phase={failure_detail['phase']} code={failure_detail['code']} error={part_err}",
                            kind="error",
                        )
                    completed_parts += 1
                    progress = 30 + int((completed_parts / total_parts) * 60)
                    _set_stage(JobStage.RENDERING, progress, f"Processed {completed_parts}/{total_parts} parts")
            else:
                future_map = {}
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    for idx, seg in enumerate(scored, start=1):
                        if cancel_registry.is_cancelled(job_id):
                            break  # stop submitting; running futures will self-cancel
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
                        except cancel_registry.JobCancelledError:
                            raise  # propagate immediately; executor.__exit__ waits for running futures
                        except Exception as part_err:
                            failure_detail = _render_part_failure_detail(idx, part_err)
                            failed_parts.append(failure_detail)
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
                            _job_log(
                                effective_channel,
                                job_id,
                                f"Part {idx}/{total_parts} failed: "
                                f"phase={failure_detail['phase']} code={failure_detail['code']} error={part_err}",
                                kind="error",
                            )
                        completed_parts += 1
                        progress = 30 + int((completed_parts / total_parts) * 60)
                        _set_stage(JobStage.RENDERING_PARALLEL, progress, f"Processed {completed_parts}/{total_parts} parts")
                # Catch cancel that completed all futures before propagating (e.g. last part cancelled)
                if cancel_registry.is_cancelled(job_id):
                    raise cancel_registry.JobCancelledError()

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
        _mv_parts = [
            {
                "part_no":              _i + 1,
                "market_viral_score":   _s.get("mv_viral_score",  0),
                "market_viral_tier":    _s.get("mv_viral_tier",   ""),
                "market_viral_market":  _s.get("mv_viral_market", _mv_market),
                "market_viral_reasons": _s.get("mv_viral_reasons", []),
            }
            for _i, _s in enumerate(scored)
            if "mv_viral_score" in _s
        ]

        # ── P5-1 Output Ranking ───────────────────────────────────────────────
        _failed_idx_set = {int(f.get("part_no", 0)) for f in failed_parts}
        _rank_entries: list[dict] = []
        for _r_idx, _r_seg in enumerate(scored, start=1):
            if _r_idx in _failed_idx_set:
                continue
            _r_output   = str(output_dir / f"{source['slug']}_part_{_r_idx:03d}.mp4")
            _rank_entry = _compute_output_ranking_entry(
                _r_idx,
                _r_seg,
                _r_output,
                payload_hook_score=_hook_score,
            )
            # Apply quality penalty from per-part validator
            _rank_raw_score = float(_rank_entry["output_score"])
            _rank_q_penalty = int(_r_seg.get("quality_penalty", 0))
            _rank_final_score = round(max(0.0, min(100.0, _rank_raw_score - _rank_q_penalty)), 1)
            _rank_entry["raw_score"] = _rank_raw_score
            _rank_entry["quality_penalty"] = _rank_q_penalty
            _rank_entry["final_score"] = _rank_final_score
            _rank_entry["output_score"] = _rank_final_score
            _rank_entry["output_rank_score"] = _rank_final_score
            _rank_entries.append(_rank_entry)
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="output_rank_computed",
                level="INFO",
                message=f"Part {_r_idx} output_score={_rank_entry['output_score']}",
                step="render.output_rank",
                context={
                    "part_no": _r_idx,
                    "output_score": _rank_entry["output_score"],
                    "output_rank_score": _rank_entry["output_rank_score"],
                    "ranking_reason": _rank_entry["ranking_reason"],
                    "ranking_components": _rank_entry["ranking_components"],
                },
            )
        _rank_entries.sort(key=lambda x: x["output_score"], reverse=True)
        for _ri, _re in enumerate(_rank_entries, start=1):
            _re["output_rank"]    = _ri
            _re["is_best_clip"]   = (_ri == 1)
            _re["is_best_output"] = (_ri == 1)
            _seg = scored[_re["part_no"] - 1]
            _seg["output_rank"] = _re["output_rank"]
            _seg["output_score"] = _re["output_score"]
            _seg["is_best_clip"] = _re["is_best_clip"]
            _seg["ranking_reason"] = _re["ranking_reason"]
        _rank_entries_ordered = sorted(_rank_entries, key=lambda x: x["part_no"])
        _best_rank_entry = _rank_entries[0] if _rank_entries else None
        _partial_warning = (
            f"{len(failed_parts)} of {total_parts} selected part(s) failed; "
            "ranking includes successful outputs only."
            if failed_parts else ""
        )
        if _partial_warning:
            for _re in _rank_entries_ordered:
                _re["partial_failure_warning"] = _partial_warning
            if _best_rank_entry:
                _best_rank_entry["partial_failure_warning"] = _partial_warning
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()
        _rank_entries_ordered = attach_ai_visibility_summaries(_rank_entries_ordered)
        _best_rank_entry = next(
            (_entry for _entry in _rank_entries_ordered if bool(_entry.get("is_best_clip"))),
            None,
        )
        if _best_rank_entry:
            _job_log(
                effective_channel,
                job_id,
                f"Output ranking: ranked={len(_rank_entries)} "
                f"best_part_no={_best_rank_entry['part_no']} "
                f"best_output_score={_best_rank_entry['output_score']} "
                f"reason={_best_rank_entry['ranking_reason']}",
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="output_ranking_completed",
                level="INFO",
                message=(
                    f"Output ranking: best=part_{_best_rank_entry['part_no']:03d} "
                    f"score={_best_rank_entry['output_score']} total={len(_rank_entries)}"
                ),
                step="render.output_rank",
                context={
                    "total_outputs":   len(_rank_entries),
                    "failed_outputs":  len(failed_parts),
                    "warning":         _partial_warning,
                    "best_part_no":    _best_rank_entry["part_no"],
                    "best_score":      _best_rank_entry["output_score"],
                    "best_reason":     _best_rank_entry["ranking_reason"],
                    "ranking_summary": [
                        {
                            "part_no": e["part_no"],
                            "rank": e["output_rank"],
                            "score": e["output_score"],
                            "reason": e["ranking_reason"],
                        }
                        for e in _rank_entries[:5]
                    ],
                },
            )

        # ── P5-2 Auto Best Export ─────────────────────────────────────────────
        _best_exports_list: list[dict] = []
        if getattr(payload, "auto_best_export_enabled", False):
            if _rank_entries:
                _abe_count = max(1, min(10, int(getattr(payload, "auto_best_export_count", 3) or 3)))
                _abe_top   = _rank_entries[:_abe_count]  # already sorted desc by score
                _best_dir  = output_dir / "best"
                try:
                    _best_dir.mkdir(parents=True, exist_ok=True)
                    for _abe in _abe_top:
                        _abe_src = Path(_abe["output_file"])
                        _abe_dst = _best_dir / f"{_output_stem}_rank_{_abe['output_rank']:02d}.mp4"
                        try:
                            shutil.copy2(str(_abe_src), str(_abe_dst))
                            _best_exports_list.append({
                                "rank":              _abe["output_rank"],
                                "part_no":           _abe["part_no"],
                                "source_file":       str(_abe_src),
                                "best_file":         str(_abe_dst),
                                "output_score":      _abe["output_score"],
                                "output_rank_score": _abe["output_rank_score"],
                                "ranking_reason":    _abe["ranking_reason"],
                            })
                        except Exception as _abe_copy_err:
                            _job_log(
                                effective_channel, job_id,
                                f"best_export copy failed part_{_abe['part_no']:03d}: {_abe_copy_err}",
                                kind="warning",
                            )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="best_export_completed",
                        level="INFO",
                        message=f"Best export: {len(_best_exports_list)}/{len(_abe_top)} files → {_best_dir}",
                        step="render.best_export",
                        context={
                            "count":          len(_best_exports_list),
                            "best_dir":       str(_best_dir),
                            "exported_files": [e["best_file"] for e in _best_exports_list],
                        },
                    )
                except Exception as _abe_err:
                    _job_log(
                        effective_channel, job_id,
                        f"best_export_failed: {_abe_err}",
                        kind="warning",
                    )
            else:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="best_export_skipped",
                    level="INFO",
                    message="Best export skipped: no ranked outputs available",
                    step="render.best_export",
                    context={"reason": "no_ranked_outputs"},
                )

        _is_partial_success = bool(failed_parts)
        _final_status = "completed_with_errors" if _is_partial_success else "completed"
        _final_message = "Render completed with errors" if _is_partial_success else "Render completed"

        # ── Phase 30: AI Output Ranking — best-effort, never blocks render ──
        _ai_output_ranking: dict = {"available": False, "mode": "recommendation_only"}
        try:
            from app.ai.output.output_ranker import rank_variant_outputs as _rank_ai_outputs
            _ai_rank_inputs = [
                {
                    "output_id": str(_re.get("part_no") or i),
                    "path": str(_re.get("output_file") or ""),
                    "variant_id": str(_re.get("variant_id") or ""),
                    "output_rank_score": float(_re.get("output_rank_score") or _re.get("output_score") or 0.0),
                    "failed": False,
                    "warnings": [],
                }
                for i, _re in enumerate(_rank_entries_ordered)
            ] + [
                {
                    "output_id": str(_fp.get("part_no") or f"failed_{i}"),
                    "path": "",
                    "variant_id": "",
                    "output_rank_score": 0.0,
                    "failed": True,
                    "warnings": [str(_fp.get("error") or "render_failed")],
                }
                for i, _fp in enumerate(failed_parts)
            ]
            _ai_rank_result = _rank_ai_outputs(
                _ai_rank_inputs,
                edit_plan=_ai_edit_plan,
                context={"job_id": job_id},
            )
            _ai_output_ranking = _ai_rank_result.to_dict()
            if _ai_edit_plan is not None:
                _ai_edit_plan.output_ranking = _ai_output_ranking
            logger.info(
                "ai_output_ranking_created job_id=%s best=%s outputs=%d",
                job_id,
                _ai_output_ranking.get("best_output_id") or "none",
                len(_ai_output_ranking.get("outputs") or []),
            )
        except Exception as _rank_err:
            logger.warning("ai_output_ranking_skipped job_id=%s: %s", job_id, _rank_err)
            _ai_output_ranking = {
                "available": False,
                "mode": "recommendation_only",
                "warnings": [f"ranking_error:{type(_rank_err).__name__}"],
            }

        # ── Phase 45: AI Render Quality Evaluation — evaluation-only, never blocks render ──
        _ai_render_quality: dict = {"available": False, "evaluation_mode": "evaluation_only"}
        try:
            from app.ai.quality.quality_evaluator import evaluate_render_quality as _eval_quality
            _quality_eval = _eval_quality(
                outputs,
                edit_plan=_ai_edit_plan,
                context={"job_id": job_id},
            )
            _ai_render_quality = _quality_eval.to_dict()
            if _ai_edit_plan is not None:
                _ai_edit_plan.render_quality_evaluation = _ai_render_quality
            logger.info(
                "ai_render_quality_evaluated job_id=%s best=%s outputs=%d",
                job_id,
                _ai_render_quality.get("best_quality_output_id") or "none",
                len(_ai_render_quality.get("output_scores") or []),
            )
        except Exception as _quality_err:
            logger.warning("ai_render_quality_evaluation_skipped job_id=%s: %s", job_id, _quality_err)
            _ai_render_quality = {
                "available": False,
                "evaluation_mode": "evaluation_only",
                "warnings": [f"quality_evaluation_error:{type(_quality_err).__name__}"],
            }

        # Phase 49A — Build stable UI-safe AI UX metadata contract
        _ai_ux_metadata: dict = {"available": False}
        try:
            from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata as _build_ai_ux
            _ai_ux_metadata = _build_ai_ux(_ai_edit_plan, output_ranking=_ai_output_ranking)
        except Exception as _ux_err:
            logger.debug("ai_ux_metadata_skipped job_id=%s: %s", job_id, _ux_err)

        _result_payload = {
            "outputs": outputs,
            "render_preset": _preset_name,
            "render_preset_id": _preset_id,
            "render_preset_label": _preset_label,
            "segments": scored,
            "market_viral_parts": _mv_parts,
            "output_ranking": _rank_entries_ordered,
            "output_ranking_warning": _partial_warning,
            "best_clip": _best_rank_entry,
            "best_exports": _best_exports_list,
            "voice_summary": _voice_summary,
            "subtitle_translate_summary": _subtitle_translate_summary,
            "failed_parts": [int(f["part_no"]) for f in failed_parts],
            "failed_parts_detail": failed_parts,
            "selected_segments_count": total_parts,
            "successful_outputs_count": len(outputs),
            "failed_outputs_count": len(failed_parts),
            "is_partial_success": _is_partial_success,
            "ai_director": _ai_edit_plan.to_dict() if _ai_edit_plan is not None else {"enabled": False},
            "ai_render_influence": _ai_influence_report,
            "ai_beat_execution": _ai_beat_report,
            "story": _ai_edit_plan.story if _ai_edit_plan is not None else {},
            "preset_evolution": _ai_edit_plan.preset_evolution if _ai_edit_plan is not None else {},
            "creator_style": _ai_edit_plan.creator_style if _ai_edit_plan is not None else {},
            "ai_output_ranking": _ai_output_ranking,
            "ai_render_quality_evaluation": _ai_render_quality,
            "ai_ux": _ai_ux_metadata,
        }
        upsert_job(
            job_id,
            "render",
            effective_channel,
            _final_status,
            payload.model_dump(),
            _result_payload,
            stage=JobStage.DONE,
            progress_percent=100,
            message=_final_message,
        )
        # ── AI Memory write (Phase 3) — after job finalized, never blocks render ──
        if getattr(payload, "ai_director_enabled", False) or _ai_edit_plan is not None:
            try:
                from app.ai.rag.memory_writer import write_render_memory as _write_mem
                _write_mem(
                    _result_payload,
                    context={
                        "market": getattr(payload, "viral_market", None),
                        "mode": getattr(payload, "ai_mode", "viral_tiktok"),
                        "duration": source.get("duration", 0.0),
                    },
                )
            except Exception:
                pass

        _job_log(
            effective_channel,
            job_id,
            f"Render final summary: status={_final_status} "
            f"successful_outputs={len(outputs)} failed_outputs={len(failed_parts)} "
            f"selected_segments={total_parts}",
            kind="warning" if _is_partial_success else "info",
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.ffmpeg.success",
            level="WARNING" if _is_partial_success else "INFO",
            message="FFmpeg render completed with errors" if _is_partial_success else "FFmpeg render completed",
            step="render.ffmpeg",
            context={"outputs": len(outputs), "failed_outputs": len(failed_parts), "total_parts": total_parts},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.complete_with_errors" if _is_partial_success else "render.complete",
            level="WARNING" if _is_partial_success else "INFO",
            message=_final_message,
            step="render.complete",
            duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            context={
                "outputs": len(outputs),
                "failed_outputs": len(failed_parts),
                "total_parts": total_parts,
                "is_partial_success": _is_partial_success,
                "voice_summary": _voice_summary,
                "subtitle_translate_summary": _subtitle_translate_summary,
            },
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
            try:
                cleanup_session_fn(edit_session_id)
            except Exception:
                pass
        _JOB_LOG_DIRS.pop(job_id, None)
        close_thread_conn()  # release render thread's cached DB connection
