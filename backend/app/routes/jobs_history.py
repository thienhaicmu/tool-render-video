"""History-list normalisation helpers — Strategic-7 extract (Audit 2026-06-08).

Pure-move from ``routes/jobs.py``. The helpers form a self-contained group
that converts a raw ``jobs`` table row (plus its ``job_parts``) into the
shape consumed by the ``/api/jobs/history`` endpoint and the FE history UI.

Nothing in this module touches request/response state or the WebSocket
surface — they are deterministic transforms over dicts.

``jobs.py`` re-imports these names so existing callers (and the legacy
public surface of ``routes.jobs``) keep working without change.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.db.jobs_repo import list_job_parts


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
        # T3.2 -- Audit 2026-06-08 closure (Batch B B-10-B). Pre-T3.2 the
        # history endpoint synthesized a "partial" status here, but
        # nothing in app.db ever wrote it: jobs_repo._VALID_JOB_STATUSES
        # only enumerates {queued, running, completed,
        # completed_with_errors, failed, interrupted, cancelled}, and
        # pipeline_finalize writes "completed_with_errors" for this
        # exact case. The WS handler and the single-job /api/jobs/{id}
        # endpoint surfaced the canonical "completed_with_errors"
        # while the history list surfaced "partial" -- same DB row,
        # two different wire strings. FE supported both because of
        # this asymmetry; now the wire is unified on the canonical
        # status name.
        return "completed_with_errors", f"{completed} clips completed, {failed} failed"
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
        # T2 visibility (audit 2026-06-15): expose job-level progress_percent
        # and the latest progress message so History rows + cs-shell topbar
        # badge can render a live progress bar / ETA without making a
        # second round-trip per row.
        "progress_percent": int(row.get("progress_percent") or 0),
        "message": str(row.get("message") or ""),
    }


__all__ = [
    "_parse_json",
    "_to_iso_utc",
    "_safe_file_name",
    "_truncate_text",
    "_render_title_and_hint",
    "_download_title_and_hint",
    "_parts_counts",
    "_render_status_and_summary",
    "_download_status_and_summary",
    "_history_output_dir",
    "_normalize_history_item",
]
