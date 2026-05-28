
import contextlib
import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from app.core.config import DATABASE_PATH

logger = logging.getLogger("app.db")
_DB_PATH_LOCK = threading.Lock()
_ACTIVE_DB_PATH: Path | None = None


def _default_fallback_db_path() -> Path:
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return base / "tool-render-video" / "data" / "app.db"
    return Path.home() / ".tool-render-video" / "data" / "app.db"


def _force_writable_file(path: Path):
    try:
        if path.exists():
            mode = path.stat().st_mode
            path.chmod(mode | 0o200)
    except Exception:
        pass


def _can_write_sqlite(path: Path) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _force_writable_file(path)
        _force_writable_file(path.with_suffix(path.suffix + "-wal"))
        _force_writable_file(path.with_suffix(path.suffix + "-shm"))
        conn = sqlite3.connect(str(path), timeout=5)
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("CREATE TABLE IF NOT EXISTS __db_write_check (id INTEGER PRIMARY KEY AUTOINCREMENT)")
            conn.execute("INSERT INTO __db_write_check DEFAULT VALUES")
            conn.commit()
            conn.execute("DELETE FROM __db_write_check WHERE id = (SELECT MAX(id) FROM __db_write_check)")
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception:
        return False


def _resolve_db_path() -> Path:
    global _ACTIVE_DB_PATH
    if _ACTIVE_DB_PATH is not None:
        return _ACTIVE_DB_PATH
    with _DB_PATH_LOCK:
        if _ACTIVE_DB_PATH is not None:
            return _ACTIVE_DB_PATH
        primary = Path(DATABASE_PATH)
        if _can_write_sqlite(primary):
            _ACTIVE_DB_PATH = primary
            return _ACTIVE_DB_PATH
        fallback = _default_fallback_db_path()
        if _can_write_sqlite(fallback):
            _ACTIVE_DB_PATH = fallback
            logger.warning(
                "Database path '%s' is not writable; using fallback '%s'.",
                primary,
                fallback,
            )
            return _ACTIVE_DB_PATH
        raise RuntimeError(
            f"No writable SQLite database path available. Tried: {primary} and {fallback}"
        )


def get_conn():
    db_path = _resolve_db_path()
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    conn.execute('PRAGMA foreign_keys=ON;')
    return conn


@contextlib.contextmanager
def db_conn():
    """Context manager for HTTP-path DB access. Always closes the connection on exit."""
    conn = get_conn()
    try:
        yield conn
    finally:
        conn.close()


# Thread-local connection cache — used only by high-frequency render-path writers
# (update_job_progress, upsert_job_part). Each render worker thread holds one
# open connection for the duration of its job instead of open/close per write.
_tls = threading.local()


def _thread_conn() -> sqlite3.Connection:
    """Return this thread's cached DB connection, re-opening if stale."""
    conn = getattr(_tls, 'conn', None)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _tls.conn = None
    db_path = _resolve_db_path()
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA synchronous=NORMAL;')
    conn.execute('PRAGMA foreign_keys=ON;')
    _tls.conn = conn
    return conn


def close_thread_conn() -> None:
    """Explicitly close this thread's cached connection (call from render finally)."""
    conn = getattr(_tls, 'conn', None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
        _tls.conn = None


# Upload tables removed in Phase 4F.5D. Drop them idempotently from any
# existing database file that was created before the upload domain was removed.
_UPLOAD_TABLES = (
    "upload_accounts",
    "upload_queue",
    "upload_videos",
    "upload_history",
    "upload_runtime_locks",
    "upload_scheduler_state",
    "upload_proxy_pool",
)


def _drop_upload_tables(conn: sqlite3.Connection) -> None:
    for table in _UPLOAD_TABLES:
        conn.execute(f"DROP TABLE IF EXISTS {table}")


def init_db():
    conn = get_conn()
    _drop_upload_tables(conn)
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
            "priority": "priority INTEGER DEFAULT 0",
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
    # ── Creator preferences (singleton row, id always = 1) ──────────────────────
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS creator_prefs (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            prefs_json TEXT DEFAULT '{}',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # ── Platform downloader jobs (standalone, not tied to render pipeline) ────
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS download_jobs (
            id          TEXT PRIMARY KEY,
            url         TEXT NOT NULL,
            platform    TEXT DEFAULT '',
            status      TEXT DEFAULT 'queued',
            progress    INTEGER DEFAULT 0,
            speed_str   TEXT DEFAULT '',
            eta_str     TEXT DEFAULT '',
            output_path TEXT DEFAULT '',
            output_dir  TEXT DEFAULT '',
            filename    TEXT DEFAULT '',
            title       TEXT DEFAULT '',
            duration    REAL DEFAULT 0,
            height      INTEGER DEFAULT 0,
            fps         REAL DEFAULT 0,
            filesize    INTEGER DEFAULT 0,
            error_msg   TEXT DEFAULT '',
            created_at  TEXT DEFAULT (datetime('now')),
            updated_at  TEXT DEFAULT (datetime('now'))
        )
        """
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_dl_jobs_status ON download_jobs(status)"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_dl_jobs_created ON download_jobs(created_at DESC)"
    )
    conn.commit()
    conn.close()


def _json_dumps(data: Any) -> str:
    return json.dumps(data or {}, ensure_ascii=False)


def _json_loads(raw: Any, default: Any = None) -> Any:
    if raw is None or raw == "":
        return {} if default is None else default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {} if default is None else default


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()
