"""
job_registry.py — In-memory job state store cho v2 render jobs.

Thread-safe dict: job_id → JobState.
Không dùng app.db (v2 tách biệt hoàn toàn với v1 DB).

Lifecycle: QUEUED → RUNNING → DONE | FAILED | CANCELLED

Events: mỗi pipeline emit() gọi → append vào job's event list.
        GET /api/v2/render/{job_id} trả về last N events.
"""
from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from v2.domain.render.models import RenderRequest, RenderResult

_MAX_EVENTS_PER_JOB = 200
_MAX_JOBS            = 100   # evict oldest khi vượt quá

_registry: dict[str, "JobState"] = {}
_lock = threading.RLock()


@dataclass
class JobState:
    job_id:     str
    status:     str              # "queued" | "running" | "completed" | "completed_with_errors" | "failed" | "cancelled"
    request:    RenderRequest
    work_dir:   Path
    future:     Optional[Future] = None
    result:     Optional[RenderResult] = None
    events:     list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    error:      Optional[str] = None
    cancel_event: threading.Event = field(default_factory=threading.Event)


def create_job(request: RenderRequest, work_dir: Path) -> str:
    """Tạo job mới, trả về job_id."""
    job_id = str(uuid.uuid4())
    with _lock:
        _maybe_evict()
        _registry[job_id] = JobState(
            job_id=job_id,
            status="queued",
            request=request,
            work_dir=work_dir,
        )
    return job_id


def get_job(job_id: str) -> Optional[JobState]:
    with _lock:
        return _registry.get(job_id)


def set_running(job_id: str, future: Future) -> None:
    with _lock:
        state = _registry.get(job_id)
        if state:
            state.future = future
            state.status = "running"
            state.updated_at = time.time()


def set_done(job_id: str, result: RenderResult) -> None:
    with _lock:
        state = _registry.get(job_id)
        if state:
            state.result = result
            state.status = result.status   # "completed" | "completed_with_errors" | "failed"
            state.updated_at = time.time()


def set_failed(job_id: str, error: str) -> None:
    with _lock:
        state = _registry.get(job_id)
        if state:
            state.status = "failed"
            state.error = error
            state.updated_at = time.time()


def cancel_job(job_id: str) -> bool:
    """
    Cancel job: set cancel_event + cancel future nếu còn queued.
    Trả về True nếu job tồn tại và cancel được gửi.
    """
    with _lock:
        state = _registry.get(job_id)
        if not state:
            return False
        state.cancel_event.set()
        if state.future and not state.future.done():
            state.future.cancel()
        state.status = "cancelled"
        state.updated_at = time.time()
        return True


def append_event(job_id: str, stage: str, data: dict) -> None:
    """Gọi từ pipeline emit_fn — thread-safe."""
    with _lock:
        state = _registry.get(job_id)
        if state:
            if len(state.events) >= _MAX_EVENTS_PER_JOB:
                state.events = state.events[-(_MAX_EVENTS_PER_JOB // 2):]
            state.events.append({"stage": stage, "ts": time.time(), **data})
            state.updated_at = time.time()


def make_emit_fn(job_id: str) -> Callable[[str, dict], None]:
    """Tạo emit_fn để truyền vào pipeline. Closure trên job_id."""
    def _emit(stage: str, data: dict) -> None:
        append_event(job_id, stage, data)
    return _emit


def list_jobs(limit: int = 20) -> list[JobState]:
    """Trả về các jobs gần nhất (mới nhất trước)."""
    with _lock:
        all_jobs = sorted(_registry.values(), key=lambda j: j.created_at, reverse=True)
        return all_jobs[:limit]


def _maybe_evict() -> None:
    """Evict oldest completed/failed jobs khi registry quá lớn. Gọi trong lock."""
    if len(_registry) < _MAX_JOBS:
        return
    terminal = [
        (j.created_at, j.job_id)
        for j in _registry.values()
        if j.status in ("completed", "completed_with_errors", "failed", "cancelled")
    ]
    if not terminal:
        return
    terminal.sort()
    evict_count = len(_registry) - _MAX_JOBS + 1
    for _, jid in terminal[:evict_count]:
        del _registry[jid]
