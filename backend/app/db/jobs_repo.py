import logging

from app.db.connection import (
    _json_dumps,
    _thread_conn,
    get_conn,
)

logger = logging.getLogger("app.db")


def upsert_job(job_id: str, kind: str, channel_code: str, status: str,
               payload=None, result=None, stage: str = '', progress_percent: int = 0,
               message: str = '', priority: int = 0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
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
    conn.close()


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


def delete_job(job_id: str) -> None:
    """Permanently delete a job and all its parts from the database."""
    conn = get_conn()
    try:
        conn.execute("DELETE FROM job_parts WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
        conn.commit()
    finally:
        conn.close()


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
    conn = get_conn()
    row = conn.execute('SELECT * FROM jobs WHERE job_id = ?', (job_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_jobs():
    conn = get_conn()
    rows = conn.execute('SELECT * FROM jobs ORDER BY created_at DESC').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def list_jobs_page(limit: int, offset: int) -> list[dict]:
    """Return a page of jobs ordered by updated_at DESC, created_at DESC.

    Executes a single query with SQL-level LIMIT/OFFSET so only the requested
    rows are transferred from SQLite, regardless of total table size.
    """
    conn = get_conn()
    rows = conn.execute(
        'SELECT * FROM jobs ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?',
        (limit, offset),
    ).fetchall()
    conn.close()
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
    conn = get_conn()
    rows = conn.execute(
        f'SELECT * FROM job_parts WHERE job_id IN ({placeholders}) ORDER BY job_id, part_no ASC',
        job_ids,
    ).fetchall()
    conn.close()
    result: dict[str, list[dict]] = {jid: [] for jid in job_ids}
    for r in rows:
        d = dict(r)
        jid = d.get('job_id', '')
        if jid in result:
            result[jid].append(d)
    return result


def list_job_parts(job_id: str):
    conn = get_conn()
    rows = conn.execute('SELECT * FROM job_parts WHERE job_id = ? ORDER BY part_no ASC', (job_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
