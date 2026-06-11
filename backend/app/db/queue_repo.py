"""queue_repo.py — acquisition_queue table CRUD.

Follows the same db_conn() context-manager pattern as download_repo.py.
AcquisitionScheduler is the only caller that mutates status; this module
is a dumb data accessor with an allowlist to prevent arbitrary injection.
"""
from __future__ import annotations

from typing import Any

from app.db.connection import _utc_now_iso, db_conn

_UPDATABLE_FIELDS = frozenset({
    "status",
    "download_job_id",
    "asset_id",
    "retry_count",
    "error_msg",
    "started_at",
    "completed_at",
})


def enqueue(
    queue_id: str,
    url: str,
    platform: str = "",
    quality: str = "best",
    priority: int = 5,
    output_dir: str = "",
    max_retries: int = 3,
) -> None:
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO acquisition_queue
                (queue_id, url, platform, quality, priority, output_dir,
                 max_retries, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?)
            """,
            (queue_id, url, platform, quality, priority, output_dir,
             max_retries, _utc_now_iso(), _utc_now_iso()),
        )
        conn.commit()


def get_next_queued() -> dict | None:
    """Return the highest-priority (lowest number) pending item, FIFO within same priority."""
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM acquisition_queue WHERE status = 'queued' "
            "ORDER BY priority ASC, created_at ASC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_queue_item(queue_id: str) -> dict | None:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM acquisition_queue WHERE queue_id = ?", (queue_id,)
        ).fetchone()
    return dict(row) if row else None


def update_queue_item(queue_id: str, **fields: Any) -> None:
    updates = {k: v for k, v in fields.items() if k in _UPDATABLE_FIELDS}
    if not updates:
        return
    updates["updated_at"] = _utc_now_iso()
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [queue_id]
    with db_conn() as conn:
        conn.execute(
            f"UPDATE acquisition_queue SET {cols} WHERE queue_id = ?", vals
        )
        conn.commit()


def list_queue(status: str | None = None, limit: int = 100) -> list[dict]:
    with db_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM acquisition_queue WHERE status = ? "
                "ORDER BY priority ASC, created_at ASC LIMIT ?",
                (status, min(limit, 500)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM acquisition_queue "
                "ORDER BY priority ASC, created_at ASC LIMIT ?",
                (min(limit, 500),),
            ).fetchall()
    return [dict(r) for r in rows]


def count_running() -> int:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM acquisition_queue WHERE status = 'running'"
        ).fetchone()
    return row[0] if row else 0


def delete_queue_item(queue_id: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "DELETE FROM acquisition_queue WHERE queue_id = ?", (queue_id,)
        )
        conn.commit()
