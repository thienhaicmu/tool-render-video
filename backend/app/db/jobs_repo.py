import logging

from app.db.connection import (
    _json_dumps,
    _thread_conn,
    db_conn,
)

logger = logging.getLogger("app.db")


def upsert_job(job_id: str, kind: str, channel_code: str, status: str,
               payload=None, result=None, stage: str = '', progress_percent: int = 0,
               message: str = '', priority: int = 0):
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO jobs (job_id, kind, channel_code, status, stage, progress_percent, message, payload_json, result_json, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                kind=excluded.kind,
                channel_code=excluded.channel_code,
                status=excluded.status,
                stage=excluded.stage,
                progress_percent=excluded.progress_percent,
                message=excluded.message,
                payload_json=excluded.payload_json,
                result_json=excluded.result_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (job_id, kind, channel_code, status, stage, progress_percent, message, _json_dumps(payload), _json_dumps(result), priority)
        )
        conn.commit()


def update_job_progress(job_id: str, stage: str, progress_percent: int, message: str = '', status: str | None = None):
    conn = _thread_conn()
    cur = conn.cursor()
    if status:
        cur.execute(
            'UPDATE jobs SET stage = ?, progress_percent = ?, message = ?, status = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?',
            (stage, progress_percent, message, status, job_id),
        )
    else:
        cur.execute(
            'UPDATE jobs SET stage = ?, progress_percent = ?, message = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?',
            (stage, progress_percent, message, job_id),
        )
    conn.commit()


def save_error_kind(job_id: str, kind: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "UPDATE jobs SET error_kind = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
            (kind, job_id),
        )
        conn.commit()


def update_render_plan(job_id: str, plan_json: str | None) -> None:
    """Persist the RenderPlan JSON blob for a job (Sprint 2.1).

    `plan_json` is expected to be the output of `RenderPlan.to_json()` or
    None when the plan should be cleared. The column is nullable —
    passing None is a valid 'no plan present' state and is preserved
    verbatim. Never raises; logs a warning and returns on DB error so
    a failure to persist does not crash a live render.
    """
    try:
        with db_conn() as conn:
            conn.execute(
                "UPDATE jobs SET render_plan_json = ?, updated_at = CURRENT_TIMESTAMP WHERE job_id = ?",
                (plan_json, job_id),
            )
            conn.commit()
    except Exception as exc:
        logger.warning("update_render_plan failed for job_id=%s: %s", job_id, exc)


def get_render_plan(job_id: str) -> str | None:
    """Return the raw RenderPlan JSON blob for a job, or None when the row
    has no plan (NULL column) or the job doesn't exist.

    The caller is expected to feed the result to
    `RenderPlan.from_json(...)` which is itself defensive — so any
    malformed payload becomes None there, not here. Never raises.
    """
    try:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT render_plan_json FROM jobs WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            value = row[0] if isinstance(row, tuple) else row["render_plan_json"]
            return value if isinstance(value, str) and value else None
    except Exception as exc:
        logger.warning("get_render_plan failed for job_id=%s: %s", job_id, exc)
        return None


def delete_job(job_id: str) -> None:
    """Permanently delete a job and all its parts from the database."""
    with db_conn() as conn:
        conn.execute("DELETE FROM job_parts WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.commit()


def upsert_job_part(job_id: str, part_no: int, part_name: str, status: str,
                    progress_percent: int = 0, start_sec: float = 0, end_sec: float = 0,
                    duration: float = 0, viral_score: float = 0, motion_score: float = 0,
                    hook_score: float = 0, output_file: str = '', message: str = ''):
    conn = _thread_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO job_parts (job_id, part_no, part_name, status, progress_percent, start_sec, end_sec, duration, viral_score, motion_score, hook_score, output_file, message, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(job_id, part_no) DO UPDATE SET
            part_name=excluded.part_name,
            status=excluded.status,
            progress_percent=excluded.progress_percent,
            start_sec=excluded.start_sec,
            end_sec=excluded.end_sec,
            duration=excluded.duration,
            viral_score=excluded.viral_score,
            motion_score=excluded.motion_score,
            hook_score=excluded.hook_score,
            output_file=excluded.output_file,
            message=excluded.message,
            updated_at=CURRENT_TIMESTAMP
        """,
        (job_id, part_no, part_name, status, progress_percent, start_sec, end_sec, duration, viral_score, motion_score, hook_score, output_file, message)
    )
    conn.commit()


def get_job(job_id: str):
    with db_conn() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs():
    with db_conn() as conn:
        rows = conn.execute('SELECT * FROM jobs ORDER BY created_at DESC').fetchall()
        return [dict(r) for r in rows]


def list_jobs_page(limit: int, offset: int) -> list[dict]:
    """Return a page of jobs ordered by updated_at DESC, created_at DESC.

    Executes a single query with SQL-level LIMIT/OFFSET so only the requested
    rows are transferred from SQLite, regardless of total table size.
    """
    with db_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM jobs ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?',
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def list_job_parts_bulk(job_ids: list[str]) -> dict[str, list[dict]]:
    """Fetch parts for multiple jobs in a single query, keyed by job_id.

    Replaces N individual list_job_parts() calls with one IN (...) query,
    eliminating the N+1 problem in the history endpoint.
    Returns an empty list for any job_id that has no parts.
    """
    if not job_ids:
        return {}
    placeholders = ','.join('?' * len(job_ids))
    with db_conn() as conn:
        rows = conn.execute(
            f'SELECT * FROM job_parts WHERE job_id IN ({placeholders}) ORDER BY job_id, part_no ASC',
            job_ids,
        ).fetchall()
        result: dict[str, list[dict]] = {jid: [] for jid in job_ids}
        for r in rows:
            d = dict(r)
            jid = d.get('job_id', '')
            if jid in result:
                result[jid].append(d)
        return result


def list_job_parts(job_id: str):
    with db_conn() as conn:
        rows = conn.execute('SELECT * FROM job_parts WHERE job_id = ? ORDER BY part_no ASC', (job_id,)).fetchall()
        return [dict(r) for r in rows]


def clear_part_output(job_id: str, part_no: int) -> None:
    """Clear output_file for a single part (file deleted by caller)."""
    with db_conn() as conn:
        conn.execute(
            "UPDATE job_parts SET output_file='', updated_at=CURRENT_TIMESTAMP WHERE job_id=? AND part_no=?",
            (job_id, part_no),
        )
        conn.commit()
