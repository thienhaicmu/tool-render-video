"""download_repo.py — download_jobs table CRUD.

Sprint 5.4 (Sub-A): migrated from raw get_conn() + manual close to
db_conn() context manager. Matches the Sprint 5.3 precedent set by
creator_repo.py and feedback_repo.py — same exception-safety guarantee
that jobs_repo.py has had. db_conn() also auto-commits/rolls back on
exit, so explicit conn.commit() calls here are redundant; left in
place for the cleanup pass in a follow-up sprint (same disposition as
creator_repo.py).
"""
from __future__ import annotations

from typing import Any

from app.db.connection import _utc_now_iso, db_conn


def create_download_job(
    job_id: str,
    url: str,
    platform: str,
    output_dir: str,
) -> None:
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO download_jobs (id, url, platform, output_dir, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'queued', ?, ?)
            """,
            (job_id, url, platform, output_dir, _utc_now_iso(), _utc_now_iso()),
        )
        conn.commit()


def update_download_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    allowed = {
        "status", "progress", "speed_str", "eta_str",
        "output_path", "filename", "title",
        "duration", "height", "fps", "filesize", "error_msg",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _utc_now_iso()
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [job_id]
    with db_conn() as conn:
        conn.execute(f"UPDATE download_jobs SET {cols} WHERE id = ?", vals)
        conn.commit()


def get_download_job(job_id: str) -> dict | None:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM download_jobs WHERE id = ?", (job_id,)
        ).fetchone()
    return dict(row) if row else None


def list_download_jobs(limit: int = 100) -> list[dict]:
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM download_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_download_job(job_id: str) -> None:
    with db_conn() as conn:
        conn.execute("DELETE FROM download_jobs WHERE id = ?", (job_id,))
        conn.commit()


def find_active_job_for_url(url: str) -> dict | None:
    """Return an existing queued/downloading job for this URL, or None."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM download_jobs WHERE url = ? AND status IN ('queued', 'downloading') LIMIT 1",
            (url,),
        ).fetchone()
    return dict(row) if row else None


def complete_download_job(job_id: str, **fields: Any) -> bool:
    """Set status='done' only if currently 'downloading' (race-safe). Returns True if applied."""
    allowed = {"output_path", "filename", "title", "duration", "height", "fps", "filesize"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    updates["status"] = "done"
    updates["updated_at"] = _utc_now_iso()
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [job_id]
    with db_conn() as conn:
        cur = conn.execute(
            f"UPDATE download_jobs SET {cols} WHERE id = ? AND status = 'downloading'",
            vals,
        )
        conn.commit()
    return cur.rowcount > 0
