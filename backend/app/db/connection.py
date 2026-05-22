
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
UPLOAD_PROFILE_LOCK_TTL_MINUTES = 30
UPLOAD_SCHEDULER_STATE_ID = "main"


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
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_accounts (
            account_id TEXT PRIMARY KEY,
            platform TEXT,
            channel_code TEXT,
            account_key TEXT,
            display_name TEXT DEFAULT '',
            status TEXT DEFAULT 'active',
            profile_path TEXT DEFAULT '',
            proxy_id TEXT DEFAULT '',
            proxy_config_json TEXT DEFAULT '{}',
            daily_limit INTEGER DEFAULT 0,
            cooldown_minutes INTEGER DEFAULT 0,
            today_count INTEGER DEFAULT 0,
            last_upload_at TEXT,
            last_login_check_at TEXT,
            login_state TEXT DEFAULT 'unknown',
            profile_lock_state TEXT DEFAULT 'idle',
            health_json TEXT,
            metadata_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_queue (
            queue_id TEXT PRIMARY KEY,
            video_id TEXT,
            video_path TEXT NOT NULL,
            render_job_id TEXT,
            part_no INTEGER,
            account_id TEXT,
            platform TEXT NOT NULL DEFAULT 'tiktok',
            channel_code TEXT,
            caption TEXT DEFAULT '',
            hashtags_json TEXT DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'pending',
            priority INTEGER DEFAULT 0,
            scheduled_at TEXT DEFAULT '',
            attempt_count INTEGER DEFAULT 0,
            max_attempts INTEGER DEFAULT 3,
            last_error TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            result_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_videos (
            video_id TEXT PRIMARY KEY,
            video_path TEXT NOT NULL,
            file_name TEXT DEFAULT '',
            platform TEXT NOT NULL DEFAULT 'tiktok',
            source_type TEXT NOT NULL DEFAULT 'manual_file',
            status TEXT NOT NULL DEFAULT 'ready',
            caption TEXT DEFAULT '',
            hashtags_json TEXT DEFAULT '[]',
            cover_path TEXT DEFAULT '',
            note TEXT DEFAULT '',
            duration_sec REAL DEFAULT 0,
            file_size INTEGER DEFAULT 0,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_history (
            history_id TEXT PRIMARY KEY,
            queue_id TEXT NOT NULL,
            account_id TEXT,
            video_id TEXT,
            platform TEXT,
            video_path TEXT,
            status TEXT,
            attempt_no INTEGER,
            started_at TEXT,
            finished_at TEXT,
            duration_seconds REAL,
            error TEXT,
            adapter_result_json TEXT DEFAULT '{}',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_runtime_locks (
            lock_id TEXT PRIMARY KEY,
            lock_type TEXT NOT NULL,
            resource_key TEXT NOT NULL,
            account_id TEXT DEFAULT '',
            queue_id TEXT DEFAULT '',
            profile_path TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            acquired_at TEXT DEFAULT CURRENT_TIMESTAMP,
            expires_at TEXT DEFAULT '',
            released_at TEXT DEFAULT '',
            active INTEGER DEFAULT 1,
            UNIQUE(lock_type, resource_key, active)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_scheduler_state (
            state_id TEXT PRIMARY KEY,
            scheduler_enabled INTEGER DEFAULT 0,
            max_concurrent_uploads INTEGER DEFAULT 1,
            tick_interval_seconds INTEGER DEFAULT 30,
            last_tick_at TEXT DEFAULT '',
            running_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'stopped',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS upload_proxy_pool (
            proxy_id TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            type TEXT DEFAULT 'http',
            host TEXT DEFAULT '',
            port INTEGER DEFAULT 0,
            username TEXT DEFAULT '',
            password TEXT DEFAULT '',
            market TEXT DEFAULT '',
            status TEXT DEFAULT 'untested',
            last_tested_at TEXT DEFAULT '',
            last_ok_at TEXT DEFAULT '',
            latency_ms INTEGER DEFAULT 0,
            last_ip TEXT DEFAULT '',
            last_error TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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
    _ensure_columns(
        "upload_accounts",
        {
            "platform": "platform TEXT",
            "channel_code": "channel_code TEXT",
            "account_key": "account_key TEXT",
            "display_name": "display_name TEXT DEFAULT ''",
            "status": "status TEXT DEFAULT 'active'",
            "profile_path": "profile_path TEXT DEFAULT ''",
            "proxy_id": "proxy_id TEXT DEFAULT ''",
            "proxy_config_json": "proxy_config_json TEXT DEFAULT '{}'",
            "daily_limit": "daily_limit INTEGER DEFAULT 0",
            "cooldown_minutes": "cooldown_minutes INTEGER DEFAULT 0",
            "today_count": "today_count INTEGER DEFAULT 0",
            "last_upload_at": "last_upload_at TEXT",
            "last_login_check_at": "last_login_check_at TEXT",
            "login_state": "login_state TEXT DEFAULT 'unknown'",
            "profile_lock_state": "profile_lock_state TEXT DEFAULT 'idle'",
            "health_json": "health_json TEXT",
            "metadata_json": "metadata_json TEXT",
            "created_at": "created_at TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_columns(
        "upload_queue",
        {
            "video_id": "video_id TEXT",
            "video_path": "video_path TEXT NOT NULL DEFAULT ''",
            "render_job_id": "render_job_id TEXT",
            "part_no": "part_no INTEGER",
            "account_id": "account_id TEXT",
            "platform": "platform TEXT NOT NULL DEFAULT 'tiktok'",
            "channel_code": "channel_code TEXT",
            "caption": "caption TEXT DEFAULT ''",
            "hashtags_json": "hashtags_json TEXT DEFAULT '[]'",
            "status": "status TEXT NOT NULL DEFAULT 'pending'",
            "priority": "priority INTEGER DEFAULT 0",
            "scheduled_at": "scheduled_at TEXT DEFAULT ''",
            "attempt_count": "attempt_count INTEGER DEFAULT 0",
            "max_attempts": "max_attempts INTEGER DEFAULT 3",
            "last_error": "last_error TEXT DEFAULT ''",
            "metadata_json": "metadata_json TEXT DEFAULT '{}'",
            "result_json": "result_json TEXT",
            "created_at": "created_at TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_columns(
        "upload_videos",
        {
            "video_path": "video_path TEXT NOT NULL DEFAULT ''",
            "file_name": "file_name TEXT DEFAULT ''",
            "platform": "platform TEXT NOT NULL DEFAULT 'tiktok'",
            "source_type": "source_type TEXT NOT NULL DEFAULT 'manual_file'",
            "status": "status TEXT NOT NULL DEFAULT 'ready'",
            "caption": "caption TEXT DEFAULT ''",
            "hashtags_json": "hashtags_json TEXT DEFAULT '[]'",
            "cover_path": "cover_path TEXT DEFAULT ''",
            "note": "note TEXT DEFAULT ''",
            "duration_sec": "duration_sec REAL DEFAULT 0",
            "file_size": "file_size INTEGER DEFAULT 0",
            "metadata_json": "metadata_json TEXT DEFAULT '{}'",
            "created_at": "created_at TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_columns(
        "upload_history",
        {
            "queue_id": "queue_id TEXT NOT NULL DEFAULT ''",
            "account_id": "account_id TEXT",
            "video_id": "video_id TEXT",
            "platform": "platform TEXT",
            "video_path": "video_path TEXT",
            "status": "status TEXT",
            "attempt_no": "attempt_no INTEGER",
            "started_at": "started_at TEXT",
            "finished_at": "finished_at TEXT",
            "duration_seconds": "duration_seconds REAL",
            "error": "error TEXT",
            "adapter_result_json": "adapter_result_json TEXT DEFAULT '{}'",
            "metadata_json": "metadata_json TEXT DEFAULT '{}'",
            "created_at": "created_at TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    _ensure_columns(
        "upload_runtime_locks",
        {
            "lock_type": "lock_type TEXT NOT NULL DEFAULT ''",
            "resource_key": "resource_key TEXT NOT NULL DEFAULT ''",
            "account_id": "account_id TEXT DEFAULT ''",
            "queue_id": "queue_id TEXT DEFAULT ''",
            "profile_path": "profile_path TEXT DEFAULT ''",
            "metadata_json": "metadata_json TEXT DEFAULT '{}'",
            "acquired_at": "acquired_at TEXT DEFAULT CURRENT_TIMESTAMP",
            "expires_at": "expires_at TEXT DEFAULT ''",
            "released_at": "released_at TEXT DEFAULT ''",
            "active": "active INTEGER DEFAULT 1",
        },
    )
    _ensure_columns(
        "upload_scheduler_state",
        {
            "scheduler_enabled": "scheduler_enabled INTEGER DEFAULT 0",
            "max_concurrent_uploads": "max_concurrent_uploads INTEGER DEFAULT 1",
            "tick_interval_seconds": "tick_interval_seconds INTEGER DEFAULT 30",
            "last_tick_at": "last_tick_at TEXT DEFAULT ''",
            "running_count": "running_count INTEGER DEFAULT 0",
            "status": "status TEXT DEFAULT 'stopped'",
            "metadata_json": "metadata_json TEXT DEFAULT '{}'",
            "created_at": "created_at TEXT DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "updated_at TEXT DEFAULT CURRENT_TIMESTAMP",
        },
    )
    cur.execute(
        """
        INSERT INTO upload_scheduler_state (
            state_id, scheduler_enabled, max_concurrent_uploads, tick_interval_seconds,
            last_tick_at, running_count, status, metadata_json, created_at, updated_at
        )
        VALUES (?, 0, 1, 30, '', 0, 'stopped', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(state_id) DO NOTHING
        """,
        (UPLOAD_SCHEDULER_STATE_ID,),
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
