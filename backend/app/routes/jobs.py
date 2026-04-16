
import asyncio
from collections import deque
from pathlib import Path
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from app.services.db import list_jobs, get_job, list_job_parts
from app.services.maintenance import prune_job_logs
from app.core.config import LOGS_DIR

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _resolve_job_log_path(row: dict, job_id: str) -> Path:
    return LOGS_DIR / "render" / f"{job_id}.log"


@router.get("")
def api_list_jobs():
    return {"items": list_jobs()}


@router.get("/{job_id}")
def api_get_job(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return row


@router.get("/{job_id}/parts")
def api_get_job_parts(job_id: str):
    return {"items": list_job_parts(job_id)}


@router.get("/{job_id}/logs")
def api_get_job_logs(job_id: str, lines: int = 120):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    safe_lines = max(20, min(1000, int(lines or 120)))
    log_path = _resolve_job_log_path(row, job_id)
    if not log_path.exists():
        return {"job_id": job_id, "log_file": str(log_path), "items": []}

    tail = deque(maxlen=safe_lines)
    with Path(log_path).open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if line:
                tail.append(line)
    return {"job_id": job_id, "log_file": str(log_path), "items": list(tail)}


@router.websocket("/{job_id}/ws")
async def ws_job_progress(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint — streams job + parts updates every 500 ms.
    Closes automatically when the job reaches a terminal state.
    Frontend falls back to HTTP polling if this endpoint fails.
    """
    await websocket.accept()
    try:
        while True:
            job = get_job(job_id)
            if not job:
                await websocket.send_json({"error": "not_found"})
                break
            parts = list_job_parts(job_id)
            await websocket.send_json({"job": job, "parts": parts})
            if job.get("status") in ("completed", "failed"):
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.post("/cleanup/logs")
def api_cleanup_logs(keep_last: int = 30, older_than_days: int = 10):
    return prune_job_logs(LOGS_DIR, keep_last=keep_last, older_than_days=older_than_days)
