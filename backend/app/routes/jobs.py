
import asyncio
import json
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from app.services.db import list_jobs, get_job, list_job_parts
from app.services.maintenance import prune_job_logs
from app.core.config import CHANNELS_DIR

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_STUCK_THRESHOLD_S = 120   # seconds with no DB update before a part is flagged stuck
_ACTIVE_STATUSES   = {"waiting", "cutting", "transcribing", "rendering", "downloading"}


def _parse_json(raw):
    try:
        if not raw:
            return {}
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {}


def _to_iso_utc(val: str | None) -> str | None:
    if not val:
        return None
    try:
        dt = datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return None


def _safe_file_name(value: str | None) -> str:
    return (str(value or "").replace("\\", "/").split("/")[-1] or "").strip()


def _truncate_text(value: str | None, limit: int = 72) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if len(text) <= limit else f"{text[:limit - 3]}..."


def _render_title_and_hint(payload: dict) -> tuple[str, str]:
    source_mode = str(payload.get("source_mode") or ("youtube" if payload.get("youtube_url") else "local")).strip().lower()
    if source_mode == "local":
        path = str(payload.get("source_video_path") or "").strip()
        name = _safe_file_name(path) or "Local video render"
        return name, name
    url = str(payload.get("youtube_url") or "").strip()
    if not url:
        return "Render job", "Render source unavailable"
    try:
        parsed = Path(url)
        if parsed.name:
            return _truncate_text(url), _truncate_text(url)
    except Exception:
        pass
    return _truncate_text(url), _truncate_text(url)


def _download_title_and_hint(payload: dict, completed: int, total: int) -> tuple[str, str]:
    urls = payload.get("urls") or []
    count = len(urls) if isinstance(urls, list) else total
    count = max(count, total, completed, 1)
    title = f"{count} video{'s' if count != 1 else ''} downloaded"
    first = str(urls[0] or "").strip() if isinstance(urls, list) and urls else ""
    return title, _truncate_text(first) if first else title


def _parts_counts(parts: list[dict]) -> dict:
    counts = {"completed": 0, "failed": 0, "unsupported": 0, "total": len(parts)}
    for part in parts:
        status = str(part.get("status") or "").lower()
        if status == "done":
            counts["completed"] += 1
        elif status == "failed":
            counts["failed"] += 1
        elif status == "unsupported":
            counts["unsupported"] += 1
    return counts


def _render_status_and_summary(base_status: str, completed: int, failed: int) -> tuple[str, str]:
    if base_status == "interrupted":
        return "interrupted", "Render interrupted"
    if base_status in {"running", "queued"}:
        return base_status, (
            f"{completed} clips completed, {failed} failed"
            if completed or failed
            else "Render in progress"
        )
    if completed > 0 and failed == 0:
        return "completed", f"{completed} clip{'s' if completed != 1 else ''} completed"
    if completed > 0 and failed > 0:
        return "partial", f"{completed} clips completed, {failed} failed"
    return "failed", (f"{failed} clip{'s' if failed != 1 else ''} failed" if failed else "Render failed")


def _download_status_and_summary(base_status: str, completed: int, failed: int, unsupported: int) -> tuple[str, str]:
    if base_status == "interrupted":
        return "interrupted", "Download interrupted"
    if base_status in {"running", "queued"}:
        if completed or failed or unsupported:
            return base_status, f"{completed} saved, {failed} failed, {unsupported} unsupported"
        return base_status, "Download in progress"
    if completed > 0 and failed == 0 and unsupported == 0:
        return "completed", f"{completed} video{'s' if completed != 1 else ''} saved"
    if completed > 0 and (failed > 0 or unsupported > 0):
        bits = [f"{completed} saved"]
        if failed > 0:
            bits.append(f"{failed} failed")
        if unsupported > 0:
            bits.append(f"{unsupported} unsupported")
        return "partial", ", ".join(bits)
    if failed > 0 or unsupported > 0:
        bits = []
        if failed > 0:
            bits.append(f"{failed} failed")
        if unsupported > 0:
            bits.append(f"{unsupported} unsupported")
        return "failed", ", ".join(bits) or "Download failed"
    return "failed", "Download failed"


def _history_output_dir(payload: dict, result: dict) -> str:
    out = str((result or {}).get("output_dir") or payload.get("output_dir") or "").strip()
    return out


def _normalize_history_item(row: dict) -> dict:
    kind = str(row.get("kind") or "").lower()
    base_status = str(row.get("status") or "").lower()
    payload = _parse_json(row.get("payload_json"))
    result = _parse_json(row.get("result_json"))
    output_dir = _history_output_dir(payload, result)
    created_at = _to_iso_utc(row.get("created_at"))
    updated_at = _to_iso_utc(row.get("updated_at")) or created_at

    completed = failed = unsupported = total = 0
    if kind == "download":
        completed = int(result.get("completed_items") or 0)
        failed = int(result.get("failed_items") or 0)
        unsupported = int(result.get("unsupported_items") or 0)
        total = int(result.get("total_items") or 0)
        if total <= 0:
            counts = _parts_counts(list_job_parts(row["job_id"]))
            completed = counts["completed"]
            failed = counts["failed"]
            unsupported = counts["unsupported"]
            total = counts["total"]
        title, source_hint = _download_title_and_hint(payload, completed, total)
        status, summary_text = _download_status_and_summary(base_status, completed, failed, unsupported)
    else:
        counts = _parts_counts(list_job_parts(row["job_id"]))
        completed = counts["completed"]
        failed = counts["failed"]
        total = counts["total"]
        title, source_hint = _render_title_and_hint(payload)
        status, summary_text = _render_status_and_summary(base_status, completed, failed)

    return {
        "job_id": row["job_id"],
        "kind": "download" if kind == "download" else "render",
        "status": status,
        "stage": str(row.get("stage") or "").strip().lower(),
        "title": title or ("Download job" if kind == "download" else "Render job"),
        "source_hint": source_hint or None,
        "timestamp": updated_at or created_at,
        "created_at": created_at,
        "updated_at": updated_at,
        "output_dir": output_dir or None,
        "completed_count": completed,
        "failed_count": failed,
        "unsupported_count": unsupported,
        "total_count": total,
        "summary_text": summary_text,
        "can_open_folder": bool(output_dir),
        "can_retry": kind == "download" and failed > 0 and base_status not in {"running", "queued"},
        "can_rerun": kind == "render",
    }


def _updated_at_ts(val: str | None) -> float:
    """Parse a SQLite UTC timestamp string ('YYYY-MM-DD HH:MM:SS') to a Unix float.

    Returns 0.0 on any parse failure so callers can treat it as 'never updated'.
    """
    if not val:
        return 0.0
    try:
        dt = datetime.strptime(val.strip(), "%Y-%m-%d %H:%M:%S")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except Exception:
        return 0.0


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


@router.get("/history")
def api_jobs_history(limit: int = 20):
    safe_limit = max(1, min(30, int(limit or 20)))
    rows = list_jobs()
    rows = sorted(
        rows,
        key=lambda row: (_updated_at_ts(row.get("updated_at")), _updated_at_ts(row.get("created_at"))),
        reverse=True,
    )[:safe_limit]
    return {"items": [_normalize_history_item(row) for row in rows]}


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
            "stuck_parts": [],
            "current_part": None,
            "current_stage": None,
            "overall_progress_percent": 0.0,
            "parts_percent": 0.0,
        }

    completed = sum(1 for p in parts if (p.get("status") or "") == "done")
    failed    = sum(1 for p in parts if (p.get("status") or "") == "failed")
    in_prog   = [p for p in parts if (p.get("status") or "") in _ACTIVE_STATUSES]
    pending   = total - completed - failed - len(in_prog)

    pct_sum   = sum(int(p.get("progress_percent") or 0) for p in parts)
    overall   = round(pct_sum / total, 1)

    now_ts = time.time()
    active_parts = []
    stuck_parts  = []
    for p in in_prog:
        active_parts.append({
            "part_no":          p.get("part_no"),
            "status":           p.get("status"),
            "progress_percent": int(p.get("progress_percent") or 0),
        })
        last_ts = _updated_at_ts(p.get("updated_at"))
        if last_ts > 0 and (now_ts - last_ts) > _STUCK_THRESHOLD_S:
            stuck_parts.append({
                "part_no":      p.get("part_no"),
                "status":       p.get("status"),
                "stuck_seconds": int(now_ts - last_ts),
            })

    return {
        "total_parts":               total,
        "completed_parts":           completed,
        "failed_parts":              failed,
        "pending_parts":             max(0, pending),
        "processing_parts":          len(in_prog),
        "in_progress_count":         len(in_prog),   # backward compat
        "active_parts":              active_parts,
        "stuck_parts":               stuck_parts,
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
