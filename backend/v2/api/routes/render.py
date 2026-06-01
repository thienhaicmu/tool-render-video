"""
routes/render.py — Render API endpoints v2.

POST   /api/v2/render               — submit render job → {job_id, status}
GET    /api/v2/render/{job_id}      — poll job state + recent events
DELETE /api/v2/render/{job_id}      — cancel job
GET    /api/v2/render               — list recent jobs (last 20)

Frozen v1 contracts không bị ảnh hưởng — v2 routes dùng /api/v2/* prefix riêng.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from v2.core.config import TEMP_DIR
from v2.core.exceptions import RenderError
from v2.domain.render.models import RenderRequest, RenderResult
from v2.services import job_manager, job_registry

router = APIRouter(prefix="/api/v2/render", tags=["render-v2"])
logger = logging.getLogger("v2.api.render")


# ── Request / Response models ─────────────────────────────────────────────────

class SubmitResponse(BaseModel):
    job_id: str
    status: str


class JobEvent(BaseModel):
    stage: str
    ts:    float
    data:  dict


class JobResponse(BaseModel):
    job_id:     str
    status:     str
    created_at: float
    updated_at: float
    error:      Optional[str]             = None
    result:     Optional[dict]            = None
    events:     list[dict]                = []


class JobListItem(BaseModel):
    job_id:     str
    status:     str
    created_at: float
    source:     str   # basename of source_path


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=SubmitResponse, status_code=202)
def post_render(request: RenderRequest, background: BackgroundTasks) -> SubmitResponse:
    """
    Submit render job. Trả về 202 Accepted với job_id.
    Pipeline chạy async trong ThreadPoolExecutor — dùng GET /{job_id} để poll.
    """
    work_dir = TEMP_DIR / "v2_jobs" / "placeholder"  # updated inside _run
    job_id = job_registry.create_job(request, work_dir)

    # Cập nhật work_dir với job_id thực
    state = job_registry.get_job(job_id)
    actual_work_dir = TEMP_DIR / "v2_jobs" / job_id
    actual_work_dir.mkdir(parents=True, exist_ok=True)
    state.work_dir = actual_work_dir  # JobState is a mutable dataclass

    emit_fn = job_registry.make_emit_fn(job_id)
    cancel_event = state.cancel_event

    future = job_manager.submit_render_job(
        job_id=job_id,
        request=request,
        work_dir=actual_work_dir,
        emit_fn=emit_fn,
        cancel_event=cancel_event,
    )

    job_registry.set_running(job_id, future)

    # Callback: cập nhật registry khi pipeline xong
    background.add_task(_watch_future, job_id, future)

    logger.info("post_render job_id=%s source=%s", job_id, request.source_path.name)
    return SubmitResponse(job_id=job_id, status="running")


@router.get("", response_model=list[JobListItem])
def list_render_jobs() -> list[JobListItem]:
    """Trả về 20 jobs gần nhất."""
    jobs = job_registry.list_jobs(limit=20)
    return [
        JobListItem(
            job_id=j.job_id,
            status=j.status,
            created_at=j.created_at,
            source=j.request.source_path.name,
        )
        for j in jobs
    ]


@router.get("/{job_id}", response_model=JobResponse)
def get_render_job(job_id: str) -> JobResponse:
    """Poll trạng thái job + 50 events gần nhất."""
    state = job_registry.get_job(job_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    result_dict: Optional[dict] = None
    if state.result is not None:
        result_dict = state.result.model_dump(mode="json")

    return JobResponse(
        job_id=state.job_id,
        status=state.status,
        created_at=state.created_at,
        updated_at=state.updated_at,
        error=state.error,
        result=result_dict,
        events=state.events[-50:],
    )


@router.delete("/{job_id}", response_model=SubmitResponse)
def cancel_render_job(job_id: str) -> SubmitResponse:
    """Cancel job đang chạy. Trả về 404 nếu job không tồn tại."""
    if not job_registry.cancel_job(job_id):
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    logger.info("cancel_render_job job_id=%s", job_id)
    return SubmitResponse(job_id=job_id, status="cancelled")


# ── WebSocket progress stream ─────────────────────────────────────────────────

_STAGE_PROGRESS: dict[str, int] = {
    "validate.ok":          5,
    "transcribe.start":     8,
    "transcribe.cache_hit": 20,
    "transcribe.done":      20,
    "groq_select.start":    22,
    "groq_select.done":     30,
    "analyze.start":        32,
    "analyze.done":         40,
    "scene_detect.done":    45,
    "score_filter.done":    50,
    "plan.done":            55,
    "render_parts.start":   57,
    "render_parts.done":    90,
    "qa_rank.done":         95,
}
_TERMINAL = {"completed", "completed_with_errors", "failed", "cancelled"}


@router.websocket("/{job_id}/ws")
async def ws_render_progress(websocket: WebSocket, job_id: str) -> None:
    """
    Streams render progress as v1-compatible events:
      {job: {job_id, status, stage, progress_percent, message},
       parts: [...], summary: {overall_progress_percent, ...}}
    Reconnect-safe: client can re-connect and receive from last state.
    """
    await websocket.accept()
    last_idx = 0
    parts_tracker: dict[int, dict] = {}
    total_parts = 0
    current_progress = 0

    try:
        while True:
            state = job_registry.get_job(job_id)
            if state is None:
                await websocket.send_json({"error": "job_not_found"})
                break

            events = state.events
            new_events = events[last_idx:]
            last_idx = len(events)

            for ev in new_events:
                stage = ev.get("stage", "")
                data  = {k: v for k, v in ev.items() if k not in ("stage", "ts", "job_id")}

                # Track total_parts
                if stage == "render_parts.start":
                    total_parts = int(data.get("total", 0))

                # Track per-part completion
                if stage == "render_parts.part_done":
                    idx = int(data.get("part_index", -1))
                    if idx >= 0:
                        parts_tracker[idx] = {
                            "part_no":         idx + 1,
                            "status":          "done" if data.get("success") else "failed",
                            "progress_percent": 100,
                        }

                # Compute progress
                if stage == "render_parts.part_done" and total_parts > 0:
                    done = sum(1 for p in parts_tracker.values() if p["status"] == "done")
                    current_progress = 57 + int(done / total_parts * 33)
                elif stage in _STAGE_PROGRESS:
                    current_progress = _STAGE_PROGRESS[stage]

                msg = _format_progress_event(
                    job_id=job_id,
                    status="running",
                    stage=stage,
                    progress=current_progress,
                    message=_stage_to_message(stage, data),
                    parts=list(parts_tracker.values()),
                    total_parts=total_parts,
                    failed_parts=sum(1 for p in parts_tracker.values() if p["status"] == "failed"),
                )
                try:
                    await websocket.send_json(msg)
                except Exception:
                    return

            # Terminal: send final event and close
            if state.status in _TERMINAL:
                result = state.result
                final_parts = list(parts_tracker.values())
                if result and result.outputs:
                    final_parts = [
                        {
                            "part_no":          i + 1,
                            "status":           "done" if o.get("qa_passed") else "failed",
                            "progress_percent":  100,
                            "output_path":      o.get("path", ""),
                        }
                        for i, o in enumerate(result.outputs)
                    ]
                msg = _format_progress_event(
                    job_id=job_id,
                    status=state.status,
                    stage="done",
                    progress=100 if state.status in ("completed", "completed_with_errors") else current_progress,
                    message=_terminal_message(state.status, result),
                    parts=final_parts,
                    total_parts=total_parts or len(final_parts),
                    failed_parts=sum(1 for p in final_parts if p.get("status") == "failed"),
                )
                try:
                    await websocket.send_json(msg)
                except Exception:
                    pass
                break

            # Keepalive ping while waiting
            try:
                await websocket.send_json({"type": "ping"})
            except Exception:
                return

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


def _format_progress_event(
    job_id: str,
    status: str,
    stage: str,
    progress: int,
    message: str,
    parts: list[dict],
    total_parts: int,
    failed_parts: int,
) -> dict:
    completed    = sum(1 for p in parts if p.get("status") == "done")
    active_parts = [p for p in parts if p.get("status") not in ("done", "failed")]
    return {
        "job": {
            "job_id":           job_id,
            "status":           status,
            "stage":            stage,
            "progress_percent": progress,
            "message":          message,
            "error_kind":       None,
        },
        "parts": parts,
        "summary": {
            "overall_progress_percent": progress,
            "completed_parts":          completed,
            "total_parts":              total_parts,
            "failed_parts":             failed_parts,
            "active_parts":             active_parts,
        },
    }


def _stage_to_message(stage: str, data: dict) -> str:
    msgs = {
        "validate.ok":          "Source validated",
        "transcribe.start":     "Transcribing audio…",
        "transcribe.cache_hit": "Transcript loaded from cache",
        "transcribe.done":      "Transcript ready",
        "groq_select.start":    "Selecting best segments with AI…",
        "groq_select.done":     f"Selected {data.get('segments', 0)} segments",
        "analyze.done":         "Content analysis complete",
        "scene_detect.done":    "Scene detection complete",
        "score_filter.done":    f"Ranked {data.get('ranked', 0)} segments",
        "plan.done":            "Render plan ready",
        "render_parts.start":   f"Rendering {data.get('total', 0)} clips…",
        "render_parts.part_done": f"Clip {data.get('part_index', 0) + 1} done",
        "render_parts.done":    f"{data.get('success', 0)} clips rendered",
        "qa_rank.done":         "Quality check complete",
    }
    return msgs.get(stage, stage.replace(".", " ").replace("_", " ").title())


def _terminal_message(status: str, result) -> str:
    if result and status in ("completed", "completed_with_errors"):
        return f"{result.success_parts}/{result.total_parts} clips ready"
    if status == "cancelled":
        return "Job cancelled"
    return "Render failed"


# ── Background watcher ────────────────────────────────────────────────────────

def _watch_future(job_id: str, future) -> None:
    """
    Chạy trong BackgroundTasks thread — đợi future xong rồi cập nhật registry.
    Không raise — mọi exception đều được log và set_failed().
    """
    try:
        result: RenderResult = future.result()
        job_registry.set_done(job_id, result)
        logger.info(
            "_watch_future job_id=%s status=%s success=%d failed=%d",
            job_id, result.status, result.success_parts, result.failed_parts,
        )
    except Exception as exc:
        logger.warning("_watch_future job_id=%s exception: %s", job_id, exc)
        job_registry.set_failed(job_id, str(exc))
