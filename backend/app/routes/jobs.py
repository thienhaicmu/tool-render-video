
import asyncio
import json
from collections import deque
from pathlib import Path
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from app.services.db import list_jobs, get_job, list_job_parts
from app.services.maintenance import prune_job_logs
from app.core.config import CHANNELS_DIR

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _resolve_job_log_path(row: dict, job_id: str) -> Path:
    channel = str(row.get("channel_code") or "").strip()
    candidates: list[Path] = []
    if channel:
        candidates.append(CHANNELS_DIR / channel / "logs" / f"{job_id}.log")
    try:
        payload = json.loads(row.get("payload_json") or "{}")
    except Exception:
        payload = {}
    out_raw = str(payload.get("output_dir") or "").strip()
    mode = str(payload.get("output_mode") or "").strip().lower()
    if out_raw:
        out_path = Path(out_raw).expanduser()
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
        else:
            out_path = out_path.resolve()
        if mode == "channel" and channel:
            chan = channel.lower()
            for p in [out_path, *out_path.parents]:
                if p.name.strip().lower() == chan:
                    candidates.insert(0, p / "logs" / f"{job_id}.log")
                    break
        if out_path.name.strip().lower() in ("video_output", "video_out") and out_path.parent.name.strip().lower() == "upload":
            candidates.append(out_path.parent.parent / "logs" / f"{job_id}.log")
        candidates.append(out_path / "logs" / f"{job_id}.log")

    seen = set()
    uniq: list[Path] = []
    for c in candidates:
        key = str(c).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)
    for c in uniq:
        if c.exists():
            return c
    return uniq[0] if uniq else (CHANNELS_DIR / "manual" / "logs" / f"{job_id}.log")


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


def _compute_progress_summary(parts: list) -> dict:
    """Compute aggregated per-job progress from the parts list.

    Returns a dict with:
      total_parts, completed_parts, failed_parts, pending_parts,
      processing_parts (alias: in_progress_count),
      active_parts      list of {part_no, status, progress_percent} for all active parts,
      current_part      part_no of the first active part (kept for backward compat),
      current_stage     status  of the first active part (kept for backward compat),
      overall_progress_percent  mean of all part progress_percent (alias: parts_percent),
      parts_percent     same as overall_progress_percent (backward compat alias).
    """
    total = len(parts)
    if total == 0:
        return {
            "total_parts": 0,
            "completed_parts": 0,
            "failed_parts": 0,
            "pending_parts": 0,
            "processing_parts": 0,
            "in_progress_count": 0,
            "active_parts": [],
            "current_part": None,
            "current_stage": None,
            "overall_progress_percent": 0.0,
            "parts_percent": 0.0,
        }

    _active = {"cutting", "transcribing", "rendering"}
    completed = sum(1 for p in parts if (p.get("status") or "") == "done")
    failed    = sum(1 for p in parts if (p.get("status") or "") == "failed")
    in_prog   = [p for p in parts if (p.get("status") or "") in _active]
    pending   = total - completed - failed - len(in_prog)

    pct_sum   = sum(int(p.get("progress_percent") or 0) for p in parts)
    overall   = round(pct_sum / total, 1)

    active_parts = [
        {
            "part_no":          p.get("part_no"),
            "status":           p.get("status"),
            "progress_percent": int(p.get("progress_percent") or 0),
        }
        for p in in_prog
    ]

    return {
        "total_parts":               total,
        "completed_parts":           completed,
        "failed_parts":              failed,
        "pending_parts":             max(0, pending),
        "processing_parts":          len(in_prog),
        "in_progress_count":         len(in_prog),   # backward compat
        "active_parts":              active_parts,
        "current_part":              in_prog[0].get("part_no") if in_prog else None,
        "current_stage":             in_prog[0].get("status")  if in_prog else None,
        "overall_progress_percent":  overall,
        "parts_percent":             overall,         # backward compat alias
    }


@router.websocket("/{job_id}/ws")
async def ws_job_progress(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint — streams job + parts + summary every 500 ms.
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
            parts   = list_job_parts(job_id)
            summary = _compute_progress_summary(parts)
            await websocket.send_json({"job": job, "parts": parts, "summary": summary})
            if job.get("status") in ("completed", "failed"):
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.post("/cleanup/logs")
def api_cleanup_logs(keep_last: int = 30, older_than_days: int = 10):
    return prune_job_logs(CHANNELS_DIR, keep_last=keep_last, older_than_days=older_than_days)
