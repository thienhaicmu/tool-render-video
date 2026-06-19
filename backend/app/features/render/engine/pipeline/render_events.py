from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.config import CHANNELS_DIR, LOGS_DIR
from app.core.stage import STAGE_TO_EVENT, JobPartStage
from app.db.jobs_repo import upsert_job_part
logger = logging.getLogger("app.render")

# Maps job_id -> log directory for the active render. Read by _job_log()
# and _emit_render_event() to route per-job log lines. Cleaned up by
# unregister_job_log_dir() at job completion (see render_pipeline.py finally
# block). Mutations guarded by _JOB_LOG_DIRS_LOCK — Sprint 4.3, audit 2026-06-02.
_JOB_LOG_DIRS: dict[str, Path] = {}
_JOB_LOG_DIRS_LOCK = threading.Lock()


# T3.1 — Audit 2026-06-08 closure (Batch A V8-C1). EventBroadcaster
# bridges worker-thread render events to the FastAPI event loop's WS
# handler. Pre-T3.1 the structured event stream (`render.plan.ai_
# emitted`, `output_validation_warning`, `motion_crop_fallback`,
# ~50 event types) was trapped in JSONL log files — the FE only saw
# DB-snapshot polling, which carries only stage/status/progress but
# not the structured event detail. With this bridge in place,
# subscribed WS sessions receive a parallel ``type="event"`` stream
# alongside the existing ``type="snapshot"`` shape.
#
# Sacred Contract #6 impact: ADDITIVE only. The snapshot message keeps
# its frozen ``{job, parts, summary}`` shape; the new event message is
# a separate channel keyed by the ``type`` discriminator. Old FE
# consumers that don't dispatch on ``type`` see only the snapshot
# messages (whose top-level keys are unchanged).
#
# Thread safety: `push` runs in worker threads (the render pipeline's
# ThreadPoolExecutor). The WS handler runs in the FastAPI event loop.
# Each registered queue captures its event loop at registration; push
# crosses the boundary via ``loop.call_soon_threadsafe``.
#
# Backpressure: each per-job queue is bounded (default 200 events). If
# the FE consumer falls behind, the OLDEST events are dropped so the
# newest ones still arrive. Dropped events also remain in the JSONL
# log file, so the operator can recover them offline.
class EventBroadcaster:
    """Thread-safe event bus from worker threads to WS consumers.

    One queue per registered WS session, keyed by ``job_id``.
    Multiple WS sessions for the same job are supported (the queue
    list per job is a small set, default cap 8).
    """

    DEFAULT_QUEUE_SIZE = int(os.getenv("EVENT_BROADCASTER_QUEUE_SIZE", "200"))
    MAX_SUBSCRIBERS_PER_JOB = int(os.getenv("EVENT_BROADCASTER_MAX_SUBS", "8"))

    def __init__(self) -> None:
        # job_id → list of (queue, loop) tuples for each subscriber.
        # The loop reference is captured at register time so push from
        # any thread can use call_soon_threadsafe to enqueue.
        self._subscribers: dict[str, list[tuple[asyncio.Queue, asyncio.AbstractEventLoop]]] = {}
        self._lock = threading.Lock()
        self._dropped_counts: dict[str, int] = {}

    def register(self, job_id: str, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop) -> bool:
        """Register a queue for ``job_id``. Returns False if at cap."""
        with self._lock:
            subs = self._subscribers.setdefault(job_id, [])
            if len(subs) >= self.MAX_SUBSCRIBERS_PER_JOB:
                logger.warning(
                    "event_broadcaster: refusing register — job_id=%s already has "
                    "%d subscribers (cap=%d)",
                    job_id, len(subs), self.MAX_SUBSCRIBERS_PER_JOB,
                )
                return False
            subs.append((queue, loop))
            return True

    def unregister(self, job_id: str, queue: asyncio.Queue) -> None:
        """Remove a queue. Idempotent; safe to call on already-removed."""
        with self._lock:
            subs = self._subscribers.get(job_id) or []
            self._subscribers[job_id] = [
                (q, l) for (q, l) in subs if q is not queue
            ]
            if not self._subscribers[job_id]:
                self._subscribers.pop(job_id, None)

    def push(self, job_id: str, event: dict[str, Any]) -> None:
        """Enqueue an event for all subscribers of ``job_id``.

        No-op when no subscriber is registered for ``job_id``. Drops
        OLDEST queued event when a per-subscriber queue is full, so
        the freshest events always arrive. Drops are counted per
        job_id and surface via ``dropped_count``. Never raises.
        """
        with self._lock:
            subs = list(self._subscribers.get(job_id) or [])
        if not subs:
            return
        for queue, loop in subs:
            try:
                loop.call_soon_threadsafe(self._enqueue_drop_oldest, queue, event, job_id)
            except RuntimeError:
                # Loop closed (e.g. WS torn down between snapshot of subs
                # list and the call_soon dispatch). Drop quietly.
                pass
            except Exception as exc:
                logger.warning("event_broadcaster: push failed job=%s err=%s", job_id, exc)

    def _enqueue_drop_oldest(self, queue: asyncio.Queue, event: dict, job_id: str) -> None:
        """Try put_nowait; if full, drop the oldest queued event."""
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop oldest: pop one and try again. Only one drop per
            # call — if the queue stays full the NEXT push will drop
            # the next oldest. This caps the work per push at O(1).
            try:
                queue.get_nowait()
                queue.task_done()
            except Exception:
                pass
            try:
                queue.put_nowait(event)
                with self._lock:
                    self._dropped_counts[job_id] = self._dropped_counts.get(job_id, 0) + 1
            except Exception:
                # If still full something is very wrong; give up on
                # this event.
                pass

    def dropped_count(self, job_id: str) -> int:
        """Return the cumulative drop count for ``job_id``."""
        with self._lock:
            return self._dropped_counts.get(job_id, 0)


# Module-level singleton. All call sites import this name.
EVENT_BROADCASTER = EventBroadcaster()


def register_job_log_dir(job_id: str, log_dir: Path) -> None:
    """Register the log directory for a render job. Idempotent."""
    with _JOB_LOG_DIRS_LOCK:
        _JOB_LOG_DIRS[job_id] = log_dir


def unregister_job_log_dir(job_id: str) -> None:
    """Remove a job's log-dir entry. Safe to call multiple times."""
    with _JOB_LOG_DIRS_LOCK:
        _JOB_LOG_DIRS.pop(job_id, None)


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
    except Exception as exc:
        try:
            logger.warning("log.write_failed  path=%s  error=%s", path.name, exc)
        except Exception:
            pass  # never raise from a logging helper


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
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.utcnow().isoformat()}Z] [{kind.upper()}] {message}\n")
    except Exception as exc:
        try:
            logger.warning("job_log.write_failed  job=%s  path=%s  error=%s", job_id[:8], log_path.name, exc)
        except Exception:
            pass  # never raise from a logging helper


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
    # Feed workflow trace — swallowed, never raises
    try:
        from app.core.tracing import _feed_render_event
        _feed_render_event(
            job_id=job_id, event=event, step=step,
            context=context or {}, duration_ms=duration_ms or 0,
            level=lvl, message=message, exception=exception,
        )
    except Exception:
        pass
    # T3.1 — Audit 2026-06-08 closure (Batch A V8-C1). Push the event
    # to any WS subscriber for this job. EVENT_BROADCASTER.push is a
    # no-op when no subscriber is registered (the common case during
    # tests or when no UI is connected), so the cost is one dict
    # lookup + lock + None compare. When a subscriber is registered
    # the event is enqueued via call_soon_threadsafe to cross the
    # worker-thread → event-loop boundary safely. Never raises.
    try:
        EVENT_BROADCASTER.push(job_id, entry)
    except Exception:
        pass


_PROGRESS_TICK_SEC = 3.0   # how often the timer thread wakes (stall guard cadence)

# Perf-opt Phase 2 (R1) — coalesce DB writes inside _render_progress_timer.
# Tick rate stays 3 s so stall guards react quickly, but the DB write only
# fires when the progress moved by ≥ _DB_WRITE_MIN_DELTA_PCT OR
# ≥ _DB_WRITE_MIN_INTERVAL_SEC has elapsed since the last write. Stall-guard
# writes (failure path) are NOT subject to this throttle — they always
# bypass it. The orchestrator emits the authoritative 100 % via the
# caller's path, not through this timer.
# Phase 4 polish (2026-06-18) — tightened from 10 s / 10 % to 5 s / 5 % so the
# HTTP polling fallback (GET /api/jobs/{id}) refreshes a slowly-advancing part
# with better fidelity, while still coalescing the bulk of the per-tick writes.
_DB_WRITE_MIN_INTERVAL_SEC = 5.0
_DB_WRITE_MIN_DELTA_PCT = 5


def _event_from_stage(stage: str) -> str:
    return STAGE_TO_EVENT.get(stage, "render.start")


def _resolve_job_log_dir(output_dir: Path, channel_code: str) -> Path:
    return output_dir.resolve() / "_logs"


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
    from app.features.render.engine.pipeline.qa_pipeline import _stall_deadline
    stall_deadline = _stall_deadline(encode_start, expected_duration)
    _stall_suspected_emitted = False
    # Perf-opt Phase 2 (R1) — track last-write state so the DB upsert
    # only fires when the progress meaningfully changed or the stale-write
    # interval elapsed. Stall-guard writes always bypass this throttle.
    _last_db_write_t = 0.0
    _last_db_write_pct = -1
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

        # Perf-opt Phase 2 (R1) — coalesce: skip DB write unless the
        # progress moved by ≥ _DB_WRITE_MIN_DELTA_PCT OR the staleness
        # interval has elapsed. The first iteration (_last_db_write_pct < 0)
        # always writes so the polling endpoint sees an initial value
        # without waiting for the threshold.
        _now = time.monotonic()
        _should_write = (
            _last_db_write_pct < 0
            or abs(progress - _last_db_write_pct) >= _DB_WRITE_MIN_DELTA_PCT
            or (_now - _last_db_write_t) >= _DB_WRITE_MIN_INTERVAL_SEC
        )
        if not _should_write:
            continue
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
            _last_db_write_t = _now
            _last_db_write_pct = progress
        except Exception:
            pass  # never let a DB error kill the timer thread
