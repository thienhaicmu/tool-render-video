"""
routes/storage.py — Disk Usage & Cleanup endpoints.

Phase L — Disk Usage & Cleanup API.

GET  /api/storage/summary
     Aggregate disk usage across all jobs — total bytes, file count,
     and a per-status breakdown. Uses list_job_parts_bulk() to avoid
     the N+1 pattern.

DELETE /api/jobs/{job_id}/outputs
     Delete all output files for one job and clear the output_file
     column in job_parts via the existing clear_part_output() helper.
     The jobs DB row is NEVER touched (Sacred Contract #7).

POST /api/storage/cleanup
     Batch-delete output files from completed/failed jobs older than
     max_age_days days. Active jobs (running / queued) are excluded
     regardless of the statuses filter.

Blast radius: LOW — new file, no render pipeline changes.
Sacred Contract #7: only output files on disk are deleted;
job DB rows are never removed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.db.jobs_repo import (
    clear_part_output,
    get_job,
    list_job_parts,
    list_job_parts_bulk,
    list_jobs,
    update_part_output_path,
)

logger = logging.getLogger("app.routes.storage")
router = APIRouter(tags=["storage"])

# Statuses that represent active work — never included in cleanup regardless
# of what the caller requests.
_ACTIVE_STATUSES = frozenset({"running", "queued", "cancelling"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _file_size(path: str) -> int:
    """Return file size in bytes, 0 if missing or unreadable."""
    try:
        return Path(path).stat().st_size if path and Path(path).is_file() else 0
    except OSError:
        return 0


def _delete_job_output_files(job_id: str, parts: list[dict]) -> dict:
    """Delete all output files for the given parts list.

    Clears the output_file DB column via clear_part_output() after each
    successful deletion. Returns counts for the caller.
    """
    deleted = 0
    freed = 0
    missing = 0
    for part in parts:
        output_file = str(part.get("output_file") or "").strip()
        if not output_file:
            continue
        p = Path(output_file)
        part_no = int(part.get("part_no") or 0)
        if p.is_file():
            size = _file_size(output_file)
            try:
                p.unlink()
                deleted += 1
                freed += size
            except OSError as exc:
                logger.warning(
                    "storage: failed to delete %s job_id=%s part_no=%d: %s",
                    output_file, job_id, part_no, exc,
                )
                continue
        else:
            missing += 1
        # Clear the DB column whether or not the file existed, to keep DB consistent.
        try:
            clear_part_output(job_id, part_no)
        except Exception as exc:
            logger.warning(
                "storage: clear_part_output failed job_id=%s part_no=%d: %s",
                job_id, part_no, exc,
            )
    return {"deleted_files": deleted, "freed_bytes": freed, "missing_files": missing}


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/api/storage/summary")
def get_storage_summary() -> dict:
    """Aggregate disk usage across all jobs, grouped by job status."""
    jobs = list_jobs()
    if not jobs:
        return {
            "total_bytes": 0,
            "total_files": 0,
            "orphaned_db_refs": 0,
            "by_status": {},
        }

    job_ids = [j["job_id"] for j in jobs]
    parts_by_job = list_job_parts_bulk(job_ids)

    total_bytes = 0
    total_files = 0
    orphaned = 0
    by_status: dict[str, dict] = {}

    for job in jobs:
        status = str(job.get("status") or "unknown")
        parts = parts_by_job.get(job["job_id"], [])
        job_bytes = 0
        job_files = 0

        for part in parts:
            output_file = str(part.get("output_file") or "").strip()
            if not output_file:
                continue
            if Path(output_file).is_file():
                size = _file_size(output_file)
                job_bytes += size
                job_files += 1
            else:
                orphaned += 1

        total_bytes += job_bytes
        total_files += job_files

        bucket = by_status.setdefault(status, {"bytes": 0, "files": 0, "jobs": 0})
        bucket["bytes"] += job_bytes
        bucket["files"] += job_files
        bucket["jobs"] += 1

    return {
        "total_bytes": total_bytes,
        "total_files": total_files,
        "orphaned_db_refs": orphaned,
        "by_status": by_status,
    }


@router.delete("/api/jobs/{job_id}/outputs")
def delete_job_outputs(job_id: str) -> dict:
    """Delete all output files for one job. Never deletes the job DB row."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    parts = list_job_parts(job_id)
    result = _delete_job_output_files(job_id, parts)
    return {"job_id": job_id, **result}


class CleanupRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_age_days: int = Field(30, ge=1, le=365)
    statuses: list[str] = Field(
        default=["completed", "failed"],
        description="Job statuses to include. Active statuses (running/queued) are always excluded.",
    )


@router.post("/api/storage/cleanup")
def cleanup_storage(body: CleanupRequest) -> dict:
    """Delete output files from completed/failed jobs older than max_age_days."""
    # Sanitise requested statuses — never allow active jobs in the cleanup set.
    allowed = {s.strip().lower() for s in body.statuses if s.strip()} - _ACTIVE_STATUSES
    if not allowed:
        raise HTTPException(
            status_code=422,
            detail="statuses must contain at least one non-active status (e.g. 'completed', 'failed')",
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=body.max_age_days)
    cutoff_iso = cutoff.strftime("%Y-%m-%d %H:%M:%S")

    jobs = list_jobs()
    eligible = [
        j for j in jobs
        if str(j.get("status") or "").lower() in allowed
        and str(j.get("updated_at") or "") < cutoff_iso
    ]

    if not eligible:
        return {"jobs_cleaned": 0, "files_deleted": 0, "freed_bytes": 0}

    job_ids = [j["job_id"] for j in eligible]
    parts_by_job = list_job_parts_bulk(job_ids)

    jobs_cleaned = 0
    total_deleted = 0
    total_freed = 0

    for job in eligible:
        jid = job["job_id"]
        parts = parts_by_job.get(jid, [])
        result = _delete_job_output_files(jid, parts)
        if result["deleted_files"] > 0 or result["missing_files"] > 0:
            jobs_cleaned += 1
        total_deleted += result["deleted_files"]
        total_freed += result["freed_bytes"]

    logger.info(
        "storage.cleanup: cleaned %d jobs, deleted %d files, freed %d bytes",
        jobs_cleaned, total_deleted, total_freed,
    )
    return {
        "jobs_cleaned": jobs_cleaned,
        "files_deleted": total_deleted,
        "freed_bytes": total_freed,
    }


# ── Phase T — Output File Archive ─────────────────────────────────────────────

class ArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    archive_dir: str = Field(..., min_length=1, description="Destination directory for archived files")


@router.post("/api/jobs/{job_id}/outputs/archive")
def archive_job_outputs(job_id: str, body: ArchiveRequest) -> dict:
    """Move output files for one job to archive_dir, updating DB paths.

    Unlike DELETE (which removes files), archive preserves the files at a new
    location and updates the output_file column to the new path so job history
    remains accurate. The job DB row is never touched (Sacred Contract #7).
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    archive_path = Path(body.archive_dir.strip())
    try:
        archive_path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create archive directory: {exc}",
        )

    parts = list_job_parts(job_id)
    moved = 0
    skipped = 0
    failed = 0
    results: list[dict] = []

    for part in parts:
        output_file = str(part.get("output_file") or "").strip()
        part_no = int(part.get("part_no") or 0)
        if not output_file:
            continue

        src = Path(output_file)
        if not src.is_file():
            skipped += 1
            results.append({"part_no": part_no, "status": "skipped", "reason": "file_not_found"})
            continue

        dest = archive_path / src.name
        # If dest already exists, append part_no to avoid collision
        if dest.exists():
            dest = archive_path / f"part_{part_no:03d}_{src.name}"

        try:
            src.rename(dest)
            update_part_output_path(job_id, part_no, str(dest))
            moved += 1
            results.append({"part_no": part_no, "status": "moved", "new_path": str(dest)})
        except OSError as exc:
            logger.warning(
                "storage.archive: failed to move %s → %s: %s",
                src, dest, exc,
            )
            failed += 1
            results.append({"part_no": part_no, "status": "failed", "reason": str(exc)})

    logger.info(
        "storage.archive: job_id=%s moved=%d skipped=%d failed=%d archive_dir=%s",
        job_id, moved, skipped, failed, archive_path,
    )
    return {
        "job_id":      job_id,
        "archive_dir": str(archive_path),
        "moved":       moved,
        "skipped":     skipped,
        "failed":      failed,
        "parts":       results,
    }
