
import asyncio
import json
import logging
import re
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from app.services.db import list_jobs, list_jobs_page, list_job_parts, list_job_parts_bulk, get_job, delete_job, clear_part_output, save_error_kind
from app.services.maintenance import prune_job_logs
from app.core.config import CHANNELS_DIR, TEMP_DIR
from app.quality.report_locator import load_quality_report_for_part
from app.quality.report_summary import build_job_quality_summary

logger = logging.getLogger("app.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_STUCK_THRESHOLD_S = 120   # seconds with no DB update before a part is flagged stuck
_ACTIVE_STATUSES   = {"waiting", "cutting", "transcribing", "rendering", "downloading"}
_TERMINAL_STATUSES = frozenset({"completed", "completed_with_errors", "failed", "interrupted", "cancelled"})


def _classify_error_kind(job: dict) -> str:
    """Map job stage + message to a structured error kind for frontend display.

    Only called when job status == 'failed'. Returns a stable string constant
    that the frontend maps to a human-readable label and icon.

    Classification priority:
      1. Stage field — pipeline-controlled value, never user input.
      2. Message field — only matched against specific technical strings that
         cannot plausibly appear in user-supplied titles or paths.
    """
    stage = (job.get("stage") or "").upper().strip()
    msg   = (job.get("message") or "").lower()

    # Stage-primary: pipeline sets these, not user input
    if stage == "DOWNLOADING":
        return "DOWNLOAD_FAILED"
    if stage == "TRANSCRIBING":
        return "WHISPER_FAILED"
    if stage in ("CANCELLED", "CANCELLING"):
        return "CANCELLED"

    # Technical error strings unlikely to appear in user-supplied content
    if "not found on disk" in msg or "source file not found" in msg or "filenotfounderror" in msg:
        return "SOURCE_NOT_FOUND"
    if "ffmpeg render failed" in msg or "ffmpeg timed out" in msg or "ffmpeg cancelled" in msg:
        return "FFMPEG_FAILED"
    if "qa" in stage or "output validation failed" in msg or "output file too small" in msg or "corrupt" in msg:
        return "QA_FAILED"
    if "tts failed" in msg or "voice synthesis" in msg or "narration failed" in msg:
        return "VOICE_FAILED"
    # Fallback message signals for missing stage (e.g. old jobs, edge paths)
    if "yt-dlp" in msg or "download failed" in msg:
        return "DOWNLOAD_FAILED"
    if "whisper" in msg or "transcription failed" in msg:
        return "WHISPER_FAILED"
    if "cancel" in stage or ("cancel" in msg and "not" not in msg):
        return "CANCELLED"
    return "RENDER_FAILED"


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


def _render_title_and_hint(payload: dict, result: dict | None = None) -> tuple[str, str]:
    result = result or {}
    source_title = str(result.get("source_title") or result.get("title") or "").strip()
    source_mode = str(payload.get("source_mode") or ("youtube" if payload.get("youtube_url") else "local")).strip().lower()
    if source_mode == "local":
        path = str(payload.get("source_video_path") or "").strip()
        name = source_title or _safe_file_name(path) or "Local video render"
        return name, name
    url = str(payload.get("youtube_url") or "").strip()
    if not url:
        return source_title or "Render job", "Render source unavailable"
    if source_title:
        return _truncate_text(source_title), _truncate_text(url)
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
    counts = {"completed": 0, "failed": 0, "unsupported": 0, "cancelled": 0, "total": len(parts)}
    for part in parts:
        status = str(part.get("status") or "").lower()
        if status == "done":
            counts["completed"] += 1
        elif status == "failed":
            counts["failed"] += 1
        elif status == "unsupported":
            counts["unsupported"] += 1
        elif status == "cancelled":
            counts["cancelled"] += 1
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


def _normalize_history_item(row: dict, *, parts_lookup: "dict[str, list] | None" = None) -> dict:
    kind = str(row.get("kind") or "").lower()
    base_status = str(row.get("status") or "").lower()
    payload = _parse_json(row.get("payload_json"))
    result = _parse_json(row.get("result_json"))
    output_dir = _history_output_dir(payload, result)
    created_at = _to_iso_utc(row.get("created_at"))
    updated_at = _to_iso_utc(row.get("updated_at")) or created_at

    # Use pre-fetched parts when available (eliminates per-row DB round-trip).
    # Falls back to a direct query for callers that don't pass parts_lookup.
    def _get_parts(job_id: str) -> list:
        if parts_lookup is not None:
            return parts_lookup.get(job_id, [])
        return list_job_parts(job_id)

    completed = failed = unsupported = total = 0
    if kind == "download":
        completed = int(result.get("completed_items") or 0)
        failed = int(result.get("failed_items") or 0)
        unsupported = int(result.get("unsupported_items") or 0)
        total = int(result.get("total_items") or 0)
        if total <= 0:
            counts = _parts_counts(_get_parts(row["job_id"]))
            completed = counts["completed"]
            failed = counts["failed"]
            unsupported = counts["unsupported"]
            total = counts["total"]
        title, source_hint = _download_title_and_hint(payload, completed, total)
        status, summary_text = _download_status_and_summary(base_status, completed, failed, unsupported)
    else:
        counts = _parts_counts(_get_parts(row["job_id"]))
        completed = counts["completed"]
        failed = counts["failed"] + counts.get("cancelled", 0)
        total = counts["total"]
        title, source_hint = _render_title_and_hint(payload, result)
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
        # Security: prevent path traversal when resolving log file paths from user-supplied
        # output_dir. Only honour paths under the user's home directory or CHANNELS_DIR;
        # reject anything pointing at system directories (/etc, /proc, C:\Windows, etc.).
        _safe_roots = (Path.home().resolve(), CHANNELS_DIR.resolve())
        if not any(out_path == r or out_path.is_relative_to(r) for r in _safe_roots):
            out_path = None  # unsafe path — skip log candidates derived from this input
        if out_path is not None and mode == "channel" and channel:
            chan = channel.lower()
            for p in [out_path, *out_path.parents]:
                if p.name.strip().lower() == chan:
                    candidates.insert(0, p / "logs" / f"{job_id}.log")
                    break
        if out_path is not None and out_path.name.strip().lower() in ("video_output", "video_out") and out_path.parent.name.strip().lower() == "upload":
            candidates.append(out_path.parent.parent / "logs" / f"{job_id}.log")
        if out_path is not None:
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
def api_list_jobs(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    response: Response = None,
):
    items = list_jobs_page(limit, offset)
    if response is not None:
        response.headers["X-Deprecated"] = "use /api/jobs/history instead"
    return {"items": items, "limit": limit, "offset": offset}


@router.get("/history")
def api_jobs_history(limit: int = 20, offset: int = 0):
    safe_limit  = max(1, min(100, int(limit  or 20)))
    safe_offset = max(0,          int(offset or 0))

    # Fetch one extra row to detect has_more without a COUNT(*) round-trip.
    rows = list_jobs_page(safe_limit + 1, safe_offset)
    has_more = len(rows) > safe_limit
    rows = rows[:safe_limit]

    # Batch-fetch all parts in one query (eliminates N+1 — was one query per row).
    job_ids      = [r["job_id"] for r in rows]
    parts_lookup = list_job_parts_bulk(job_ids)

    return {
        "items":    [_normalize_history_item(r, parts_lookup=parts_lookup) for r in rows],
        "limit":    safe_limit,
        "offset":   safe_offset,
        "has_more": has_more,
    }


@router.get("/queue/status")
def api_queue_status():
    from app.services.job_manager import active_count, pending_count, MAX_CONCURRENT_JOBS
    return {
        "max_concurrent": MAX_CONCURRENT_JOBS,
        "active": active_count(),
        "pending": pending_count(),
        "available_slots": max(0, MAX_CONCURRENT_JOBS - active_count()),
    }


@router.get("/{job_id}")
def api_get_job(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row.get("status") == "failed" and not row.get("error_kind"):
        row = {**row, "error_kind": _classify_error_kind(row)}
    return row


@router.get("/{job_id}/parts")
def api_get_job_parts(job_id: str):
    return {"items": list_job_parts(job_id)}


@router.get("/{job_id}/ai-summary")
def api_get_job_ai_summary(job_id: str):
    """Return structured AI decision data for a job.

    Parses result_json and returns job-level AI reasoning: director plan, story,
    ranking summary, and segment-level context for all evaluated clips (including
    those not selected as final outputs).
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    result = _parse_json(row.get("result_json"))
    if not result:
        return {"job_id": job_id, "available": False}

    output_ranking: list[dict] = result.get("output_ranking") or []
    best_clip: dict | None     = result.get("best_clip")
    all_segments: list[dict]   = result.get("segments") or []
    ai_director: dict          = result.get("ai_director") or {}
    ai_ux: dict                = result.get("ai_ux") or {}
    story: dict                = result.get("story") or {}

    selected_part_nos = {int(e.get("part_no", 0)) for e in output_ranking}
    rejected_segments = [
        {
            "part_no":       i + 1,
            "viral_score":   float(s.get("viral_score") or 0),
            "hook_score":    float(s.get("hook_score") or 0),
            "motion_score":  float(s.get("motion_score") or 0),
            "duration":      float(s.get("duration") or 0),
            "reject_reason": s.get("reject_reason") or s.get("skip_reason") or "",
        }
        for i, s in enumerate(all_segments)
        if (i + 1) not in selected_part_nos
    ]

    ranking_summary = [
        {
            "part_no":          int(e.get("part_no", 0)),
            "rank":             int(e.get("output_rank", 0)),
            "score":            round(float(e.get("output_rank_score") or e.get("output_score") or 0), 1),
            "reason":           e.get("ranking_reason") or "",
            "dominant_signal":  e.get("dominant_signal") or "",
            "confidence_tier":  e.get("confidence_tier") or "",
            "is_best_clip":     bool(e.get("is_best_clip")),
        }
        for e in output_ranking
    ]

    hybrid_analysis: dict = ai_director.get("hybrid_analysis") or {}

    return {
        "job_id":           job_id,
        "available":        True,
        "director_enabled": bool(ai_director.get("enabled")),
        "story":            story,
        "ai_ux":            ai_ux,
        "output_count":     len(output_ranking),
        "best_part_no":     int(best_clip.get("part_no", 0)) if best_clip else None,
        "best_score":       round(float(best_clip.get("output_rank_score") or best_clip.get("output_score") or 0), 1) if best_clip else None,
        "best_reason":      best_clip.get("ranking_reason") or "" if best_clip else "",
        "confidence_tier":  best_clip.get("confidence_tier") or "" if best_clip else "",
        "score_margin":     best_clip.get("score_margin") if best_clip else None,
        "ranking_summary":  ranking_summary,
        "rejected_count":   len(rejected_segments),
        "rejected_segments": rejected_segments,
        "output_ranking_warning": result.get("output_ranking_warning") or "",
        "hybrid_analysis":  hybrid_analysis,
    }


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


_JOB_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def _validate_quality_job_id(job_id: str) -> bool:
    """Return True only if job_id contains safe characters (alphanumeric + hyphens/underscores)."""
    return bool(_JOB_ID_RE.match(job_id))


@router.get("/{job_id}/parts/{part_no}/quality")
def api_get_part_quality(job_id: str, part_no: int):
    """Return the quality report sidecar for a single rendered part.

    Security: never exposes filesystem paths; accepts only job_id + part_no.
    Read-only. No render behavior change.
    """
    if not _validate_quality_job_id(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    if part_no <= 0:
        raise HTTPException(status_code=400, detail="part_no must be a positive integer")

    # Verify job and part exist in DB
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    parts = list_job_parts(job_id)
    part = next((p for p in parts if int(p.get("part_no", -1)) == part_no), None)
    if not part:
        raise HTTPException(status_code=404, detail="Part not found")

    video_path_raw = str(part.get("output_file") or "").strip()
    if not video_path_raw:
        raise HTTPException(status_code=404, detail="quality report not available")

    try:
        video_path = Path(video_path_raw)
    except Exception:
        raise HTTPException(status_code=404, detail="quality report not available")

    report = load_quality_report_for_part(job_id, part_no, video_path)
    if report is None:
        raise HTTPException(status_code=404, detail="quality report not available")

    return report


@router.get("/{job_id}/quality")
def api_get_job_quality(job_id: str, include_reports: bool = Query(default=False)):
    """Return an aggregated quality summary for all parts of a job.

    include_reports=true embeds full report dicts per part.
    Security: never exposes filesystem paths; accepts only job_id.
    Read-only. No render behavior change.
    """
    if not _validate_quality_job_id(job_id):
        raise HTTPException(status_code=400, detail="Invalid job_id")

    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")

    parts = list_job_parts(job_id)

    # Build parts_info: only expose part_no + video_path (not raw paths in response)
    parts_info = [
        {
            "part_no": p.get("part_no"),
            "video_path": str(p.get("output_file") or "").strip() or None,
        }
        for p in parts
    ]

    return build_job_quality_summary(job_id, parts_info, include_reports=include_reports)


@router.get("/{job_id}/parts/{part_no}/stream")
def stream_part(job_id: str, part_no: int):
    parts = list_job_parts(job_id)
    part = next((p for p in parts if int(p.get("part_no", -1)) == part_no), None)
    if not part or not part.get("output_file"):
        raise HTTPException(status_code=404, detail="Part or output file not found")
    path = Path(part["output_file"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Output file not found on disk")
    return FileResponse(str(path), media_type="video/mp4", headers={"Accept-Ranges": "bytes"})


def _ws_fingerprint(job: dict, parts: list, summary: dict) -> tuple:
    """Cheap comparable tuple of material render state for change detection.

    Excludes timestamps so a pure heartbeat tick (updated_at only) is not
    treated as a meaningful change.  Terminal status always bypasses this check.
    """
    return (
        job.get('status'),
        job.get('stage'),
        job.get('progress_percent'),
        job.get('message'),
        tuple(
            (p.get('part_no'), p.get('status'), p.get('progress_percent'))
            for p in parts
        ),
        summary.get('completed_parts'),
        summary.get('failed_parts'),
        len(summary.get('stuck_parts', [])),
    )


@router.websocket("/{job_id}/ws")
async def ws_job_progress(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint — streams job + parts + summary every 500 ms.
    Closes automatically when the job reaches a terminal state.
    Frontend falls back to HTTP polling if this endpoint fails.
    """
    await websocket.accept()
    try:
        last_fp = None
        while True:
            job = get_job(job_id)
            if not job:
                await websocket.send_json({"error": "not_found"})
                break
            parts   = list_job_parts(job_id)
            summary = _compute_progress_summary(parts)
            is_terminal = job.get("status") in _TERMINAL_STATUSES
            fp = _ws_fingerprint(job, parts, summary)
            # Always send when something material changed or on terminal — never
            # suppress terminal events even if fingerprint matches a prior tick.
            if fp != last_fp or is_terminal:
                job_payload = job
                if is_terminal and job.get("status") == "failed":
                    kind = _classify_error_kind(job)
                    try:
                        save_error_kind(job_id, kind)
                    except Exception:
                        pass
                    job_payload = {**job, "error_kind": kind}
                await websocket.send_json({"job": job_payload, "parts": parts, "summary": summary})
                last_fp = fp
            # Close WS on any terminal status so the stream doesn't linger.
            # Must match TERMINAL_STATUSES in frontend transport.js.
            if is_terminal:
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws_job_progress error job_id=%s: %s", job_id, exc)


@router.post("/cleanup/logs")
def api_cleanup_logs(keep_last: int = 30, older_than_days: int = 10):
    return prune_job_logs(CHANNELS_DIR, keep_last=keep_last, older_than_days=older_than_days)


@router.delete("/{job_id}/parts/{part_no}/output")
def delete_part_output_endpoint(job_id: str, part_no: int):
    """Delete the output file of a single rendered part and clear its DB path.

    The file is only deleted when its resolved path is inside an allowed root
    (CHANNELS_DIR or TEMP_DIR). Files outside those roots are rejected.
    Cannot be called while the job is running or queued.
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if (row.get("status") or "").lower() in ("running", "queued"):
        raise HTTPException(status_code=409, detail="Cannot delete output of a running job")

    parts = list_job_parts(job_id)
    part = next((p for p in parts if p.get("part_no") == part_no), None)
    if not part:
        raise HTTPException(status_code=404, detail=f"Part {part_no} not found")

    out = str(part.get("output_file") or "").strip()
    deleted = False
    if out:
        _safe_roots = tuple(r.resolve() for r in [CHANNELS_DIR, TEMP_DIR] if r.exists())
        try:
            p = Path(out).resolve()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid output file path")
        if not any(p == r or p.is_relative_to(r) for r in _safe_roots):
            raise HTTPException(status_code=403, detail="Output file is outside allowed roots")
        try:
            p.unlink(missing_ok=True)
            deleted = True
            logger.info("delete_part_output: removed job_id=%s part_no=%d path=%s", job_id, part_no, p)
        except Exception as exc:
            logger.warning("delete_part_output: failed job_id=%s part_no=%d: %s", job_id, part_no, exc)
            raise HTTPException(status_code=500, detail=f"Failed to delete file: {exc}") from exc

    clear_part_output(job_id, part_no)
    return {"job_id": job_id, "part_no": part_no, "deleted": deleted}


@router.delete("/{job_id}")
def delete_job_endpoint(job_id: str, delete_files: bool = True):
    """Delete a completed/failed/cancelled job and optionally its output files.

    Output files are only deleted when their resolved path is inside an allowed
    root (CHANNELS_DIR or TEMP_DIR). Files outside those roots are skipped with
    a warning log — they are never deleted.
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    status = (row.get("status") or "").lower()
    if status in ("running", "queued"):
        raise HTTPException(status_code=409, detail="Cannot delete a running or queued job")

    deleted_files = 0
    skipped_files = 0

    if delete_files:
        _safe_roots = tuple(
            r.resolve() for r in [CHANNELS_DIR, TEMP_DIR]
            if r.exists()
        )
        parts = list_job_parts(job_id)
        for part in parts:
            out = str(part.get("output_file") or "").strip()
            if not out:
                continue
            try:
                p = Path(out).resolve()
            except Exception:
                skipped_files += 1
                continue
            if not any(p == r or p.is_relative_to(r) for r in _safe_roots):
                logger.warning(
                    "delete_job: skipping file outside allowed roots job_id=%s path=%s",
                    job_id, p,
                )
                skipped_files += 1
                continue
            try:
                p.unlink(missing_ok=True)
                logger.info("delete_job: removed output file job_id=%s path=%s", job_id, p)
                deleted_files += 1
            except Exception as exc:
                logger.warning(
                    "delete_job: failed to remove file job_id=%s path=%s: %s",
                    job_id, p, exc,
                )
                skipped_files += 1

    delete_job(job_id)
    logger.info(
        "delete_job: removed job from DB job_id=%s deleted_files=%d skipped_files=%d",
        job_id, deleted_files, skipped_files,
    )
    return {
        "job_id": job_id,
        "deleted": True,
        "deleted_files": deleted_files,
        "skipped_files": skipped_files,
    }
