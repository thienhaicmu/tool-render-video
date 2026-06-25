
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
from app.db.jobs_repo import clear_part_output, delete_job, get_job, list_job_parts, list_job_parts_bulk, list_jobs_page, save_error_kind
from app.services.maintenance import prune_job_logs
from app.core.config import CHANNELS_DIR, TEMP_DIR
from app.models.schemas import JobStatusResponse
from app.features.render.engine.quality.report_locator import load_quality_report_for_part
from app.features.render.engine.quality.report_summary import build_job_quality_summary
from app.routes.jobs_history import (
    _parse_json,
    _normalize_history_item,
)

logger = logging.getLogger("app.jobs")

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

_STUCK_THRESHOLD_S = 120   # seconds with no DB update before a part is flagged stuck
_ACTIVE_STATUSES   = {"waiting", "cutting", "transcribing", "rendering", "downloading"}
_TERMINAL_STATUSES = frozenset({"completed", "completed_with_errors", "failed", "interrupted", "cancelled"})
_WS_PING_INTERVAL_S = 25   # keepalive ping interval — prevents proxy/OS from dropping long renders


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
    from app.jobs.manager import active_count, pending_count, MAX_CONCURRENT_JOBS
    return {
        "max_concurrent": MAX_CONCURRENT_JOBS,
        "active": active_count(),
        "pending": pending_count(),
        "available_slots": max(0, MAX_CONCURRENT_JOBS - active_count()),
    }


@router.get("/{job_id}", response_model=JobStatusResponse)
def api_get_job(job_id: str):
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    if row.get("status") == "failed" and not row.get("error_kind"):
        row = {**row, "error_kind": _classify_error_kind(row)}
    return row


_PART_AI_FIELDS = ("clip_name", "ai_title", "ai_reason", "source")


def _enrich_parts_with_segment_ai_fields(parts: list, result_json_raw) -> list:
    """Merge AI-decision metadata from result_json.segments into each part.

    Closes audit FINDING-C03 (2026-06-06). The FE's JobPart TS type
    (frontend/src/types/api.ts:266-269) declares four optional AI fields:
    ``clip_name``, ``ai_title``, ``ai_reason`` and ``source``. None of
    these are stored on the ``job_parts`` table; they live in the LLM
    output blob at ``jobs.result_json.segments[*]``.

    Before this commit the FE always saw ``undefined`` for these fields
    and fell back to placeholder labels. This helper performs the
    server-side join keyed by ``part_no`` so the FE receives the
    AI-generated titles + reasons that the LLM emitted.

    The helper is defensive: a malformed result_json or a missing
    segments list silently degrades to the un-enriched parts so the
    endpoint never breaks.
    """
    if not result_json_raw:
        return parts
    try:
        result = json.loads(result_json_raw) if isinstance(result_json_raw, str) else result_json_raw
    except Exception:
        return parts
    if not isinstance(result, dict):
        return parts
    segments = result.get("segments")
    if not isinstance(segments, list) or not segments:
        return parts

    # Build a {part_no: segment} index. The pipeline emits segments in
    # the order the renderer processes them — that is, segments[i] is
    # for part_no = i + 1. The per-segment dict may ALSO carry an
    # explicit "part_no" key on the ranking pass; prefer that when present.
    by_part: dict[int, dict] = {}
    for idx, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        explicit = seg.get("part_no")
        try:
            part_no = int(explicit) if explicit is not None else idx + 1
        except (TypeError, ValueError):
            part_no = idx + 1
        by_part[part_no] = seg

    enriched: list = []
    for p in parts:
        if not isinstance(p, dict):
            enriched.append(p)
            continue
        try:
            part_no = int(p.get("part_no") or 0)
        except (TypeError, ValueError):
            part_no = 0
        seg = by_part.get(part_no)
        if not seg:
            enriched.append(p)
            continue
        # Shallow-merge the 4 documented fields, leaving everything else
        # on the DB row untouched. The DB row wins where it has a value
        # (Sacred Contract #2 spirit — never overwrite a stored truth).
        merged = dict(p)
        for key in _PART_AI_FIELDS:
            if merged.get(key) not in (None, ""):
                continue
            value = seg.get(key)
            if value is None or value == "":
                continue
            merged[key] = value
        enriched.append(merged)
    return enriched


@router.get("/{job_id}/parts")
def api_get_job_parts(job_id: str):
    parts = list_job_parts(job_id)
    # Merge AI-decision metadata (clip_name, ai_title, ai_reason, source)
    # from the job's result_json.segments. Closes audit FINDING-C03.
    try:
        job_row = get_job(job_id)
        result_json_raw = (job_row or {}).get("result_json")
        parts = _enrich_parts_with_segment_ai_fields(parts, result_json_raw)
    except Exception:
        # Never break the parts list because of an enrichment edge case.
        pass
    return {"items": parts}


@router.get("/{job_id}/ai-summary")
def api_get_job_ai_summary(job_id: str):
    """Return structured AI decision data for a job.

    Parses result_json and returns job-level AI reasoning: director plan, story,
    ranking summary, and segment-level context for all evaluated clips (including
    those not selected as final outputs).

    Audit FINDING-BR11 closure (Batch 10C 2026-06-06): the response now
    carries an explicit ``ai_status`` enum plus a human ``status_message``
    so the FE can distinguish four cases and stop rendering an empty card:

        - "ok"           — full ranking + best_clip present, normal display
        - "no_ranking"   — pipeline finished but output_ranking is empty
                           (LLM Call 2 failed, or every part failed QA)
        - "degraded"     — best_clip present but story / director hint missing
        - "no_result"    — result_json itself absent (job is still running or
                           failed before persisting any AI artefacts)

    Backward-compat: the legacy ``available`` boolean is preserved — false
    for "no_result", true for every other case. Existing callers that only
    look at ``available`` are unaffected.
    """
    row = get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    result = _parse_json(row.get("result_json"))
    if not result:
        return {
            "job_id":          job_id,
            "available":       False,
            "ai_status":       "no_result",
            "status_message":  "AI analysis is not available yet — the job has no recorded result data.",
        }

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

    # FINDING-BR11: classify the response so the FE can show a meaningful
    # message instead of an empty card. "no_ranking" is the most common
    # interesting case — the job ran to completion but no part was ranked,
    # usually because LLM Call 2 failed or every part lost QA.
    if not output_ranking and not best_clip:
        ai_status = "no_ranking"
        status_message = (
            "No clips were ranked by the AI. The render completed without "
            "producing an output-ranking — usually because the second LLM "
            "call failed or every part was rejected by quality validation."
        )
    elif best_clip and not story and not ai_director.get("enabled"):
        ai_status = "degraded"
        status_message = (
            "Partial AI analysis available — ranking is present but the "
            "story / director hint is missing."
        )
    else:
        ai_status = "ok"
        status_message = ""

    return {
        "job_id":           job_id,
        "available":        True,
        "ai_status":        ai_status,
        "status_message":   status_message,
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

    Keepalive: sends {"type":"ping"} every _WS_PING_INTERVAL_S seconds when
    no state change occurs.  Prevents proxy/OS from dropping the TCP connection
    during long renders (55-60 min) that have infrequent DB updates.

    T3.1 — Audit 2026-06-08 closure (Batch A V8-C1). The handler now
    multiplexes TWO message types over the same WS:
      - ``{"type":"snapshot", "job":..., "parts":..., "summary":...}``
        — the original DB-snapshot shape (Sacred Contract #6 preserved
        — the snapshot still carries job/parts/summary at the top
        level; the new ``type`` discriminator is additive).
      - ``{"type":"event", "event":{...}}`` — structured events from
        ``_emit_render_event`` bridged via EVENT_BROADCASTER. Pre-T3.1
        these events were trapped in JSONL log files; now they
        stream live alongside the snapshot poll.

    Old FE consumers that don't dispatch on ``type`` ignore event
    messages (their ``isProgressEvent`` guard checks for ``job`` which
    event messages don't carry) and continue to read snapshots.
    """
    from app.features.render.engine.pipeline.render_events import EVENT_BROADCASTER
    await websocket.accept()
    # T3.1 — per-WS event queue + broadcaster subscription. The queue
    # is created in the FastAPI event loop; push from worker threads
    # crosses the boundary via loop.call_soon_threadsafe inside
    # EVENT_BROADCASTER.push.
    event_queue: asyncio.Queue = asyncio.Queue(maxsize=EVENT_BROADCASTER.DEFAULT_QUEUE_SIZE)
    event_loop = asyncio.get_event_loop()
    subscribed = EVENT_BROADCASTER.register(job_id, event_queue, event_loop)
    try:
        last_fp = None
        loop = asyncio.get_event_loop()
        last_send_time = loop.time()
        while True:
            # T3.1 — drain any pending events first. Bounded by the
            # queue cap (default 200) so this loop is O(queue_size)
            # in the worst case. Events fire whenever the broadcaster
            # pushes; in steady-state most iterations drain 0-1
            # events.
            if subscribed:
                while True:
                    try:
                        evt = event_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    try:
                        await websocket.send_json({"type": "event", "event": evt})
                    except Exception:
                        # Send failure — let the outer except handle.
                        raise
            job = get_job(job_id)
            if not job:
                await websocket.send_json({"error": "not_found"})
                break
            parts   = list_job_parts(job_id)
            # T1.4-followup / VW-3 — Audit 2026-06-08 closure (Batch A
            # V8-C2). The /api/jobs/{id}/parts HTTP endpoint at line
            # 459 enriches parts with clip_name / ai_title / ai_reason
            # / source pulled from result_json.segments (FINDING-C03
            # closure). The WS handler must do the same, otherwise FE
            # consumers that only see the WS stream get blank AI
            # metadata even after terminal frame arrives. The
            # enrichment is defensive and a no-op when result_json is
            # absent (mid-render), so the cost during long renders is
            # one defensive None check per tick.
            parts = _enrich_parts_with_segment_ai_fields(
                parts, job.get("result_json")
            )
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
                # T3.1: the snapshot now carries ``type="snapshot"``.
                # Old FE consumers that destructure
                # ``{job, parts, summary}`` still work because those
                # keys are unchanged at the top level.
                await websocket.send_json({
                    "type": "snapshot",
                    "job": job_payload,
                    "parts": parts,
                    "summary": summary,
                })
                last_fp = fp
                last_send_time = loop.time()
            elif loop.time() - last_send_time >= _WS_PING_INTERVAL_S:
                # No state change for a while — send a lightweight ping so the
                # TCP connection is not torn down by proxies or the OS.
                await websocket.send_json({"type": "ping"})
                last_send_time = loop.time()
            # Close WS on any terminal status so the stream doesn't linger.
            # Must match TERMINAL_STATUSES in frontend transport.js.
            if is_terminal:
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("ws_job_progress error job_id=%s: %s", job_id, exc)
    finally:
        # T3.1 — ALWAYS unregister the broadcaster subscription so the
        # broadcaster's subscriber list doesn't leak across WS
        # disconnects (especially on the exception path above).
        # Unregister is idempotent and safe to call when register
        # returned False (subscribe-at-cap case).
        try:
            EVENT_BROADCASTER.unregister(job_id, event_queue)
        except Exception:
            pass


@router.post("/cleanup/logs")
def api_cleanup_logs(keep_last: int = 30, older_than_days: int = 10):
    return prune_job_logs(CHANNELS_DIR, keep_last=keep_last, older_than_days=older_than_days)


# S4.4 — Watchdog extend: grant a running job extra age before the
# 2 h MAX_JOB_AGE_SECONDS watchdog cancels it. Surfaces a clean 404
# when the job isn't active so the FE can decide whether to retry
# (job just finished) or surface the error (already cancelled).
@router.post("/{job_id}/extend")
def api_extend_job_age(job_id: str, extra_seconds: int = 3600) -> dict:
    """Postpone the watchdog auto-cancel deadline for an active job.

    ``extra_seconds`` defaults to 3600 (1 h) — matches the FE advisory
    dialog copy. Negative values clamp to 0. The override is in-memory
    and is cleared when the job terminates, so retrying after a
    completed render returns a 404.

    Returns ``{job_id, granted_seconds, cumulative_override}`` on success.
    """
    from app.jobs.manager import extend_job_age, get_job_age_override
    extra = max(0, int(extra_seconds))
    if not extend_job_age(job_id, extra):
        raise HTTPException(
            status_code=404,
            detail=f"Job {job_id} is not currently running (cannot extend).",
        )
    return {
        "job_id": job_id,
        "granted_seconds": extra,
        "cumulative_override": get_job_age_override(job_id),
    }


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
