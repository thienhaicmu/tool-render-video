from __future__ import annotations

from typing import Any

from app.db.connection import get_conn, _utc_now_iso


def create_download_job(
    job_id: str,
    url: str,
    platform: str,
    output_dir: str,
) -> None:
    conn = get_conn()
    try:
        conn.execute(
            """
            INSERT INTO download_jobs (id, url, platform, output_dir, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'queued', ?, ?)
            """,
            (job_id, url, platform, output_dir, _utc_now_iso(), _utc_now_iso()),
        )
        conn.commit()
    finally:
        conn.close()


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
    conn = get_conn()
    try:
        conn.execute(f"UPDATE download_jobs SET {cols} WHERE id = ?", vals)
        conn.commit()
    finally:
        conn.close()


def get_download_job(job_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM download_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_download_jobs(limit: int = 100) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM download_jobs ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def delete_download_job(job_id: str) -> None:
    conn = get_conn()
    try:
        conn.execute("DELETE FROM download_jobs WHERE id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()
