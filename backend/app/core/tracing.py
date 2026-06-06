"""
Workflow trace — per-job ordered step log.

Lives in ``app.core`` (audit FINDING-A08 closure, 2026-06-06). Previously
located at ``app.features.render.engine.pipeline.workflow_trace`` even
though the download feature also called into it. That cross-feature
import was the "wrong-direction" coupling the Phase 3 architecture
review flagged. The render-engine path is kept as a thin re-export shim
so existing in-feature callers don't need an edit.

Writes two outputs for every render/download job:
  data/logs/workflow.log            — all jobs interleaved, sortable by time + job_id
  data/logs/jobs/{job_id}.trace     — single-job ordered trace (best for debugging)

Format (human-readable + grep-friendly):
  2026-05-30 09:17:00  [abc12345]  JOB_START    source_mode=youtube_url  clips=4
  2026-05-30 09:17:00  [abc12345]  STEP_START   download
  2026-05-30 09:17:45  [abc12345]  STEP_DONE    download      t=45.2s
  2026-05-30 09:17:45  [abc12345]  STEP_START   transcribe    model=base
  2026-05-30 09:18:08  [abc12345]  STEP_SKIP    transcribe    reason=cache_hit
  2026-05-30 09:18:08  [abc12345]  STEP_START   ai_select     provider=groq
  2026-05-30 09:18:10  [abc12345]  STEP_DONE    ai_select     t=2.1s  clips=4  fallback=False
  2026-05-30 09:18:10  [abc12345]  STEP_START   render_part   part=1  clip=0:15-1:38
  2026-05-30 09:19:33  [abc12345]  STEP_DONE    render_part   part=1  t=83s  size=45MB
  2026-05-30 09:20:31  [abc12345]  JOB_DONE     t=3m31s  clips_ok=2  clips_failed=0

Called from:
  render_events._emit_render_event()   — intercepts all render pipeline events
  downloader/router._run_download()    — download job lifecycle

All exceptions are swallowed — trace must NEVER break a render or download.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("app.downloader")  # reuse app.downloader for trace lines


# ── Event → workflow step mapping ─────────────────────────────────────────────
#
# Maps render_pipeline event names to (step_name, action).
# action: "start" | "done" | "skip" | "fail" | "job_start" | "job_done" | "job_fail"
#
_RENDER_EVENT_MAP: dict[str, tuple[str, str]] = {
    # Job lifecycle
    "render.start":                         ("job",           "job_start"),
    "render.complete":                      ("job",           "job_done"),
    "render.complete_with_errors":          ("job",           "job_done"),
    "render.error":                         ("job",           "job_fail"),

    # Transcription
    "subtitle_transcription_started":       ("transcribe",    "start"),
    "subtitle_transcription_completed":     ("transcribe",    "done"),
    "subtitle_transcription_failed":        ("transcribe",    "fail"),
    "subtitle.audio_missing":               ("transcribe",    "skip"),

    # AI selection
    "ai_director_plan_created":             ("ai_select",     "done"),

    # Scene detection
    "render.scene.detect.error":            ("scene_detect",  "fail"),

    # FFmpeg render output
    "render.ffmpeg.success":                ("render_part",   "done"),
    "render.ffmpeg.preprocess.error":       ("render_part",   "fail"),
}

# Step names where a "cache_hit" event = SKIP (not a separate start)
_CACHE_HIT_STEPS = {"subtitle.transcribe"}


# ── In-memory per-job state ────────────────────────────────────────────────────
# Cleared on job_done / job_fail.
# Not persisted across restarts — trace module is best-effort only.

_job_state: dict[str, dict[str, Any]] = {}


def _jstate(job_id: str) -> dict[str, Any]:
    if job_id not in _job_state:
        _job_state[job_id] = {
            "start_wall": time.monotonic(),
            "step_starts": {},      # step_name → monotonic start time
            "part_count": 0,        # render_part counter
            "seen_transcribe_start": False,
        }
    return _job_state[job_id]


def _cleanup(job_id: str) -> None:
    _job_state.pop(job_id, None)


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _elapsed_str(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    m, s = divmod(int(seconds), 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s"


def _kv(**kwargs: Any) -> str:
    """Format key=value pairs, skipping None/empty."""
    parts = []
    for k, v in kwargs.items():
        if v is None or v == "" or v is False:
            continue
        parts.append(f"{k}={v}")
    return "  ".join(parts)


def _size_str(size_bytes: int | float | None) -> str | None:
    if not size_bytes:
        return None
    b = float(size_bytes)
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.1f}GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f}MB"
    if b >= 1024:
        return f"{b / 1024:.1f}KB"
    return f"{int(b)}B"


# ── Writers ────────────────────────────────────────────────────────────────────

def _get_logs_dir() -> Path:
    try:
        from app.core.config import LOGS_DIR
        return LOGS_DIR
    except Exception:
        return Path("data/logs")


def _write(job_id: str, line: str) -> None:
    """Append line to both workflow.log and the per-job trace file."""
    try:
        logs_dir = _get_logs_dir()
        ts = _now_str()
        full_line = f"{ts}  [{job_id[:8]}]  {line}\n"

        # Central workflow log
        wf_log = logs_dir / "workflow.log"
        wf_log.parent.mkdir(parents=True, exist_ok=True)
        with wf_log.open("a", encoding="utf-8") as f:
            f.write(full_line)

        # Per-job trace
        jobs_dir = logs_dir / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        with (jobs_dir / f"{job_id}.trace").open("a", encoding="utf-8") as f:
            f.write(full_line)
    except Exception:
        pass  # trace must never raise


# ── Public API for download router ────────────────────────────────────────────

def dl_job_start(job_id: str, url: str, platform: str, quality: str, cookies: str) -> None:
    """Call when a download job starts."""
    try:
        _jstate(job_id)["start_wall"] = time.monotonic()
        _write(job_id, f"JOB_START     {_kv(type='download', platform=platform, quality=quality, cookies=cookies, url=url[:80])}")
    except Exception:
        pass


def dl_step_start(job_id: str, step: str, **ctx: Any) -> None:
    """Call at the start of a download step."""
    try:
        _jstate(job_id)["step_starts"][step] = time.monotonic()
        _write(job_id, f"STEP_START    {step:<20s}  {_kv(**ctx)}")
    except Exception:
        pass


def dl_step_done(job_id: str, step: str, **ctx: Any) -> None:
    """Call on successful completion of a download step."""
    try:
        st = _jstate(job_id)
        t_start = st["step_starts"].pop(step, None)
        elapsed = _elapsed_str(time.monotonic() - t_start) if t_start else "?"
        _write(job_id, f"STEP_DONE     {step:<20s}  t={elapsed}  {_kv(**ctx)}")
    except Exception:
        pass


def dl_step_fail(job_id: str, step: str, error: str, **ctx: Any) -> None:
    """Call when a download step fails."""
    try:
        st = _jstate(job_id)
        t_start = st["step_starts"].pop(step, None)
        elapsed = _elapsed_str(time.monotonic() - t_start) if t_start else "?"
        _write(job_id, f"STEP_FAIL     {step:<20s}  t={elapsed}  error={error[:120]}  {_kv(**ctx)}")
    except Exception:
        pass


def dl_job_done(job_id: str, filename: str, filesize: int, platform: str) -> None:
    """Call when a download job completes successfully."""
    try:
        st = _jstate(job_id)
        elapsed = _elapsed_str(time.monotonic() - st.get("start_wall", time.monotonic()))
        _write(job_id, f"JOB_DONE      t={elapsed}  platform={platform}  size={_size_str(filesize)}  file={filename}")
        _cleanup(job_id)
    except Exception:
        pass


def dl_job_fail(job_id: str, error: str, platform: str) -> None:
    """Call when a download job fails."""
    try:
        st = _jstate(job_id)
        elapsed = _elapsed_str(time.monotonic() - st.get("start_wall", time.monotonic()))
        _write(job_id, f"JOB_FAIL      t={elapsed}  platform={platform}  error={error[:120]}")
        _cleanup(job_id)
    except Exception:
        pass


# ── Render pipeline hook ───────────────────────────────────────────────────────

def _feed_render_event(
    *,
    job_id: str,
    event: str,
    step: str,
    context: dict,
    duration_ms: int,
    level: str,
    message: str,
    exception: Exception | None,
) -> None:
    """
    Called from render_events._emit_render_event().
    Maps pipeline events to workflow trace entries.
    All exceptions MUST be swallowed.
    """
    try:
        _feed_render_event_inner(
            job_id=job_id, event=event, step=step, context=context,
            duration_ms=duration_ms, level=level, message=message, exception=exception,
        )
    except Exception:
        pass


def _feed_render_event_inner(
    *,
    job_id: str,
    event: str,
    step: str,
    context: dict,
    duration_ms: int,
    level: str,
    message: str,
    exception: Exception | None,
) -> None:
    st = _jstate(job_id)

    # ── Special: cache hit on transcription step = SKIP ──────────────────────
    if event == "cache_hit" and step in _CACHE_HIT_STEPS:
        model = context.get("whisper_model", "?")
        _write(job_id, f"STEP_SKIP     {'transcribe':<20s}  reason=cache_hit  model={model}")
        return

    mapping = _RENDER_EVENT_MAP.get(event)
    if mapping is None:
        return  # not a traced event

    step_name, action = mapping

    # ── Deduplicate transcribe start ─────────────────────────────────────────
    if step_name == "transcribe" and action == "start":
        if st["seen_transcribe_start"]:
            return
        st["seen_transcribe_start"] = True

    # ─────────────────────────────────────────────────────────────────────────

    if action == "job_start":
        src_mode = context.get("source_mode", "?")
        clips = context.get("clip_count") or context.get("max_parts") or "?"
        lang = context.get("target_language") or context.get("language") or ""
        _write(job_id, f"JOB_START     {_kv(source_mode=src_mode, clips=clips, lang=lang or None)}")
        return

    if action == "job_done":
        elapsed = _elapsed_str(duration_ms / 1000.0) if duration_ms else _elapsed_str(time.monotonic() - st["start_wall"])
        clips_ok    = context.get("output_count") or context.get("success_count") or "?"
        clips_fail  = context.get("error_count") or context.get("failed_count") or 0
        partial     = "partial" if event == "render.complete_with_errors" else ""
        _write(job_id, f"JOB_DONE      {_kv(status=partial or 'ok', t=elapsed, clips_ok=clips_ok, clips_failed=clips_fail or None)}")
        _cleanup(job_id)
        return

    if action == "job_fail":
        elapsed = _elapsed_str(time.monotonic() - st["start_wall"])
        err = str(exception or message or "")[:120]
        _write(job_id, f"JOB_FAIL      t={elapsed}  error={err}")
        _cleanup(job_id)
        return

    if action == "start":
        st["step_starts"][step_name] = time.monotonic()
        extras = _build_start_extras(step_name, context)
        _write(job_id, f"STEP_START    {step_name:<20s}  {extras}")
        return

    if action == "done":
        t_start = st["step_starts"].pop(step_name, None)
        elapsed = _elapsed_str(time.monotonic() - t_start) if t_start else (
            _elapsed_str(duration_ms / 1000.0) if duration_ms else "?"
        )

        if step_name == "render_part":
            st["part_count"] += 1
            part_no = st["part_count"]
            size = _size_str(context.get("output_size_bytes") or context.get("filesize"))
            codec = context.get("codec") or context.get("video_codec") or ""
            _write(job_id, f"STEP_DONE     {'render_part':<20s}  part={part_no}  t={elapsed}  {_kv(size=size, codec=codec or None)}")
        elif step_name == "transcribe":
            model = context.get("whisper_model", "?")
            words = context.get("word_count") or context.get("words")
            _write(job_id, f"STEP_DONE     {'transcribe':<20s}  t={elapsed}  {_kv(model=model, words=words)}")
        elif step_name == "ai_select":
            mode    = context.get("mode", "?")
            clips   = context.get("segments") or context.get("clips_selected")
            fb      = context.get("fallback_used")
            _write(job_id, f"STEP_DONE     {'ai_select':<20s}  t={elapsed}  {_kv(mode=mode, clips=clips, fallback=fb)}")
        else:
            _write(job_id, f"STEP_DONE     {step_name:<20s}  t={elapsed}")
        return

    if action == "skip":
        reason = context.get("reason") or message[:60] if message else "skipped"
        _write(job_id, f"STEP_SKIP     {step_name:<20s}  reason={reason}")
        return

    if action == "fail":
        t_start = st["step_starts"].pop(step_name, None)
        elapsed = _elapsed_str(time.monotonic() - t_start) if t_start else "?"
        err = str(exception or "")[:120] or message[:80]
        _write(job_id, f"STEP_FAIL     {step_name:<20s}  t={elapsed}  error={err}")
        return


def _build_start_extras(step_name: str, context: dict) -> str:
    if step_name == "transcribe":
        return _kv(model=context.get("whisper_model"))
    if step_name == "ai_select":
        provider = context.get("provider") or context.get("ai_provider") or ""
        model    = context.get("model") or context.get("ai_model") or ""
        return _kv(provider=provider or None, model=model or None)
    if step_name == "render_part":
        clip_start = context.get("clip_start") or context.get("start")
        clip_end   = context.get("clip_end") or context.get("end")
        if clip_start is not None and clip_end is not None:
            def _ts(s):
                s = float(s)
                return f"{int(s//60)}:{int(s%60):02d}"
            return f"clip={_ts(clip_start)}-{_ts(clip_end)}"
    return ""
