
import json
import sqlite3
from typing import Any
from app.core.config import DATABASE_PATH


def get_conn():
    conn = sqlite3.connect(DATABASE_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    conn.execute('PRAGMA foreign_keys=ON;')
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            channel_code TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT DEFAULT '',
            progress_percent INTEGER DEFAULT 0,
            message TEXT DEFAULT '',
            payload_json TEXT,
            result_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS job_parts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            part_no INTEGER NOT NULL,
            part_name TEXT NOT NULL,
            status TEXT NOT NULL,
            progress_percent INTEGER DEFAULT 0,
            start_sec REAL DEFAULT 0,
            end_sec REAL DEFAULT 0,
            duration REAL DEFAULT 0,
            viral_score REAL DEFAULT 0,
            motion_score REAL DEFAULT 0,
            hook_score REAL DEFAULT 0,
            output_file TEXT DEFAULT '',
            message TEXT DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(job_id, part_no)
        )
        """
    )
    # Lightweight schema migration for existing local DBs created by old versions.
    def _ensure_columns(table: str, required: dict[str, str]):
        existing_rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in existing_rows}
        for col, ddl in required.items():
            if col not in existing:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    _ensure_columns(
        "jobs",
        {
            "stage": "stage TEXT DEFAULT ''",
            "progress_percent": "progress_percent INTEGER DEFAULT 0",
            "message": "message TEXT DEFAULT ''",
            "payload_json": "payload_json TEXT",
            "result_json": "result_json TEXT",
            "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_columns(
        "job_parts",
        {
            "progress_percent": "progress_percent INTEGER DEFAULT 0",
            "start_sec": "start_sec REAL DEFAULT 0",
            "end_sec": "end_sec REAL DEFAULT 0",
            "duration": "duration REAL DEFAULT 0",
            "viral_score": "viral_score REAL DEFAULT 0",
            "motion_score": "motion_score REAL DEFAULT 0",
            "hook_score": "hook_score REAL DEFAULT 0",
            "output_file": "output_file TEXT DEFAULT ''",
            "message": "message TEXT DEFAULT ''",
            "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    conn.commit()
    conn.close()


def _json_dumps(data: Any) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def upsert_job(job_id: str, kind: str, channel_code: str, status: str,
               payload=None, result=None, stage: str = '', progress_percent: int = 0,
               message: str = ''):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO jobs (job_id, kind, channel_code, status, stage, progress_percent, message, payload_json, result_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
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
        (job_id, kind, channel_code, status, stage, progress_percent, message, _json_dumps(payload), _json_dumps(result))
    )
    conn.commit()
    conn.close()


def update_job_progress(job_id: str, stage: str, progress_percent: int, message: str = '', status: str | None = None):
    conn = get_conn()
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
    conn.close()


def upsert_job_part(job_id: str, part_no: int, part_name: str, status: str,
                    progress_percent: int = 0, start_sec: float = 0, end_sec: float = 0,
                    duration: float = 0, viral_score: float = 0, motion_score: float = 0,
                    hook_score: float = 0, output_file: str = '', message: str = ''):
    conn = get_conn()
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
    conn.close()


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


def list_job_parts(job_id: str):
    conn = get_conn()
    rows = conn.execute('SELECT * FROM job_parts WHERE job_id = ? ORDER BY part_no ASC', (job_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]
