
import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
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


def _default_upload_profiles_root() -> Path:
    return DATABASE_PATH.parent / "upload_profiles"


def normalize_profile_path_value(profile_path: str | None) -> str:
    text = str(profile_path or "").strip()
    if not text:
        return ""
    try:
        path = Path(text).expanduser()
        normalized = path.resolve(strict=False)
    except Exception:
        normalized = Path(text)
    rendered = str(normalized)
    if os.name == "nt":
        return os.path.normcase(os.path.normpath(rendered))
    return os.path.normpath(rendered)


def build_default_upload_profile_path(platform: str, account_key: str) -> str:
    safe_platform = str(platform or "tiktok").strip().lower() or "tiktok"
    safe_key = str(account_key or "default").strip().lower() or "default"
    return str((_default_upload_profiles_root() / safe_platform / safe_key).resolve())


def ensure_upload_account_profile_path_fields(data: dict) -> dict:
    payload = dict(data or {})
    platform = str(payload.get("platform") or "tiktok").strip().lower() or "tiktok"
    account_key = str(payload.get("account_key") or "default").strip().lower() or "default"
    raw_profile = str(payload.get("profile_path") or "").strip()
    if not raw_profile:
        raw_profile = build_default_upload_profile_path(platform, account_key)
    normalized = normalize_profile_path_value(raw_profile)
    Path(normalized).mkdir(parents=True, exist_ok=True)
    payload["platform"] = platform
    payload["account_key"] = account_key
    payload["profile_path"] = normalized
    payload["normalized_profile_path"] = normalized
    payload["profile_lock_state"] = str(payload.get("profile_lock_state") or "idle").strip().lower() or "idle"
    return payload


def _normalize_upload_account_row(row: sqlite3.Row | dict | None):
    if not row:
        return None
    data = dict(row)
    data["proxy_config"] = _json_loads(data.pop("proxy_config_json", "{}"), default={})
    if not isinstance(data["proxy_config"], dict):
        data["proxy_config"] = {}
    data["health_json"] = _json_loads(data.get("health_json"))
    data["metadata_json"] = _json_loads(data.get("metadata_json"))
    data["profile_path"] = ensure_upload_account_profile_path_fields(data).get("profile_path", "")
    data["normalized_profile_path"] = normalize_profile_path_value(data.get("profile_path"))
    data["profile_lock_state"] = str(data.get("profile_lock_state") or "idle").strip().lower() or "idle"
    for key in ("daily_limit", "cooldown_minutes", "today_count"):
        try:
            data[key] = int(data.get(key) or 0)
        except Exception:
            data[key] = 0
    return data


def _normalize_upload_video_row(row: sqlite3.Row | dict | None):
    if not row:
        return None
    data = dict(row)
    data["hashtags"] = _json_loads(data.pop("hashtags_json", "[]"), default=[])
    if not isinstance(data["hashtags"], list):
        data["hashtags"] = []
    data["metadata"] = _json_loads(data.pop("metadata_json", "{}"), default={})
    if not isinstance(data["metadata"], dict):
        data["metadata"] = {}
    try:
        data["duration_sec"] = float(data.get("duration_sec") or 0)
    except Exception:
        data["duration_sec"] = 0
    try:
        data["file_size"] = int(data.get("file_size") or 0)
    except Exception:
        data["file_size"] = 0
    return data


def _normalize_upload_queue_row(row: sqlite3.Row | dict | None):
    if not row:
        return None
    data = dict(row)
    data["hashtags"] = _json_loads(data.pop("hashtags_json", "[]"), default=[])
    if not isinstance(data["hashtags"], list):
        data["hashtags"] = []
    data["metadata"] = _json_loads(data.pop("metadata_json", "{}"), default={})
    if not isinstance(data["metadata"], dict):
        data["metadata"] = {}
    for key in ("priority", "attempt_count", "max_attempts", "part_no"):
        try:
            data[key] = int(data.get(key) or 0)
        except Exception:
            data[key] = 0
    data.setdefault("video_file_name", "")
    data.setdefault("account_display_name", "")
    data.setdefault("account_key", "")
    return data


def _normalize_upload_history_row(row: sqlite3.Row | dict | None):
    if not row:
        return None
    data = dict(row)
    data["adapter_result"] = _json_loads(data.pop("adapter_result_json", "{}"), default={})
    if not isinstance(data["adapter_result"], dict):
        data["adapter_result"] = {}
    data["metadata"] = _json_loads(data.pop("metadata_json", "{}"), default={})
    if not isinstance(data["metadata"], dict):
        data["metadata"] = {}
    try:
        data["attempt_no"] = int(data.get("attempt_no") or 0)
    except Exception:
        data["attempt_no"] = 0
    try:
        data["duration_seconds"] = float(data.get("duration_seconds") or 0)
    except Exception:
        data["duration_seconds"] = 0
    return data


def _normalize_upload_scheduler_state_row(row: sqlite3.Row | dict | None):
    if not row:
        return {
            "state_id": UPLOAD_SCHEDULER_STATE_ID,
            "scheduler_enabled": False,
            "max_concurrent_uploads": 1,
            "tick_interval_seconds": 30,
            "last_tick_at": "",
            "running_count": 0,
            "status": "stopped",
            "metadata": {},
        }
    data = dict(row)
    data["scheduler_enabled"] = bool(int(data.get("scheduler_enabled") or 0))
    try:
        data["max_concurrent_uploads"] = max(1, int(data.get("max_concurrent_uploads") or 1))
    except Exception:
        data["max_concurrent_uploads"] = 1
    try:
        data["tick_interval_seconds"] = max(5, int(data.get("tick_interval_seconds") or 30))
    except Exception:
        data["tick_interval_seconds"] = 30
    try:
        data["running_count"] = max(0, int(data.get("running_count") or 0))
    except Exception:
        data["running_count"] = 0
    data["status"] = str(data.get("status") or "stopped").strip().lower() or "stopped"
    data["metadata"] = _json_loads(data.pop("metadata_json", "{}"), default={})
    return data


def list_upload_account_rows(include_disabled: bool = True):
    conn = get_conn()
    if include_disabled:
        rows = conn.execute(
            """
            SELECT * FROM upload_accounts
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM upload_accounts
            WHERE COALESCE(status, 'active') != 'disabled'
            ORDER BY updated_at DESC, created_at DESC
            """
        ).fetchall()
    conn.close()
    return [enrich_upload_account_runtime_state(_normalize_upload_account_row(r)) for r in rows]


def get_upload_account_row(account_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM upload_accounts WHERE account_id = ?", (account_id,)).fetchone()
    conn.close()
    return enrich_upload_account_runtime_state(_normalize_upload_account_row(row))


def get_upload_account(account_id: str):
    return get_upload_account_row(account_id)


def _active_profile_conflict_statuses() -> tuple[str, ...]:
    return ("active", "warming")


def find_upload_account_profile_conflict(
    *,
    normalized_profile_path: str,
    exclude_account_id: str = "",
) -> dict | None:
    if not normalized_profile_path:
        return None
    conn = get_conn()
    rows = conn.execute(
        """
        SELECT * FROM upload_accounts
        WHERE COALESCE(status, 'active') IN ('active', 'warming')
        """
    ).fetchall()
    conn.close()
    for row in rows:
        item = _normalize_upload_account_row(row)
        if not item:
            continue
        if exclude_account_id and str(item.get("account_id") or "") == exclude_account_id:
            continue
        if normalize_profile_path_value(item.get("profile_path")) == normalized_profile_path:
            return item
    return None


def list_active_runtime_locks(lock_type: str = "", resource_key: str = ""):
    conn = get_conn()
    clauses = ["active = 1"]
    params: list[Any] = []
    if lock_type:
        clauses.append("lock_type = ?")
        params.append(lock_type)
    if resource_key:
        clauses.append("resource_key = ?")
        params.append(resource_key)
    rows = conn.execute(
        f"""
        SELECT * FROM upload_runtime_locks
        WHERE {' AND '.join(clauses)}
        ORDER BY acquired_at DESC
        """,
        params,
    ).fetchall()
    stale_ids: list[str] = []
    items = []
    now = _utc_now()
    for row in rows:
        data = dict(row)
        try:
            expires_at = datetime.fromisoformat(str(data.get("expires_at") or ""))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
        except Exception:
            expires_at = now
        if expires_at <= now:
            stale_ids.append(str(data.get("lock_id") or ""))
            logger.warning(
                "stale_lock_recovered lock_type=%s resource_key=%s account_id=%s queue_id=%s",
                data.get("lock_type") or "",
                data.get("resource_key") or "",
                data.get("account_id") or "",
                data.get("queue_id") or "",
            )
            continue
        data["metadata"] = _json_loads(data.pop("metadata_json", "{}"), default={})
        items.append(data)
    for lock_id in stale_ids:
        conn.execute(
            """
            UPDATE upload_runtime_locks
            SET active = NULL, released_at = ?
            WHERE lock_id = ?
            """,
            (_utc_now_iso(), lock_id),
        )
    if stale_ids:
        conn.commit()
    conn.close()
    return items


def _set_account_lock_state(account_id: str, state: str):
    if not account_id:
        return
    conn = get_conn()
    conn.execute(
        """
        UPDATE upload_accounts
        SET profile_lock_state = ?, updated_at = CURRENT_TIMESTAMP
        WHERE account_id = ?
        """,
        (state, account_id),
    )
    conn.commit()
    conn.close()


def release_upload_runtime_locks_for_queue(queue_id: str):
    if not queue_id:
        return []
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT * FROM upload_runtime_locks
        WHERE queue_id = ? AND active = 1
        """,
        (queue_id,),
    ).fetchall()
    released: list[dict] = []
    for row in rows:
        data = dict(row)
        cur.execute(
            """
            UPDATE upload_runtime_locks
            SET active = NULL, released_at = ?
            WHERE lock_id = ?
            """,
            (_utc_now_iso(), data["lock_id"]),
        )
        released.append(data)
    conn.commit()
    conn.close()
    for item in released:
        if str(item.get("account_id") or "").strip():
            _set_account_lock_state(str(item.get("account_id") or "").strip(), "idle")
    return released


def acquire_upload_runtime_lock(
    *,
    lock_type: str,
    resource_key: str,
    account_id: str = "",
    queue_id: str = "",
    profile_path: str = "",
    ttl_minutes: int = UPLOAD_PROFILE_LOCK_TTL_MINUTES,
    metadata: dict | None = None,
):
    normalized_key = normalize_profile_path_value(resource_key) if lock_type == "profile_path" else str(resource_key or "").strip()
    if not normalized_key:
        raise ValueError("resource_key is required")
    now = _utc_now()
    expires_at = now + timedelta(minutes=max(1, int(ttl_minutes or UPLOAD_PROFILE_LOCK_TTL_MINUTES)))
    conn = get_conn()
    cur = conn.cursor()
    existing = cur.execute(
        """
        SELECT * FROM upload_runtime_locks
        WHERE lock_type = ? AND resource_key = ? AND active = 1
        ORDER BY acquired_at DESC
        LIMIT 1
        """,
        (lock_type, normalized_key),
    ).fetchone()
    stale_recovered = False
    if existing:
        existing_data = dict(existing)
        try:
            existing_expires = datetime.fromisoformat(str(existing_data.get("expires_at") or ""))
        except Exception:
            existing_expires = now
        if existing_expires.tzinfo is None:
            existing_expires = existing_expires.replace(tzinfo=timezone.utc)
        if existing_expires <= now:
            cur.execute(
                """
                UPDATE upload_runtime_locks
                SET active = NULL, released_at = ?
                WHERE lock_id = ?
                """,
                (_utc_now_iso(), existing_data["lock_id"]),
            )
            stale_recovered = True
            logger.warning(
                "stale_lock_recovered lock_type=%s resource_key=%s account_id=%s queue_id=%s",
                lock_type,
                normalized_key,
                existing_data.get("account_id") or "",
                existing_data.get("queue_id") or "",
            )
        else:
            conn.close()
            return {
                "acquired": False,
                "reason": "busy",
                "lock_type": lock_type,
                "resource_key": normalized_key,
                "existing": existing_data,
                "stale_recovered": False,
            }
    lock_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO upload_runtime_locks (
            lock_id, lock_type, resource_key, account_id, queue_id, profile_path,
            metadata_json, acquired_at, expires_at, released_at, active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', 1)
        """,
        (
            lock_id,
            lock_type,
            normalized_key,
            account_id or "",
            queue_id or "",
            normalize_profile_path_value(profile_path) if profile_path else "",
            _json_dumps(metadata or {}),
            now.isoformat(),
            expires_at.isoformat(),
        ),
    )
    conn.commit()
    conn.close()
    if account_id:
        _set_account_lock_state(account_id, "stale_recovered" if stale_recovered else "locked")
    return {
        "acquired": True,
        "lock_id": lock_id,
        "lock_type": lock_type,
        "resource_key": normalized_key,
        "stale_recovered": stale_recovered,
        "account_id": account_id,
        "queue_id": queue_id,
    }


def enrich_upload_account_runtime_state(account: dict | None):
    if not account:
        return None
    item = dict(account)
    normalized = normalize_profile_path_value(item.get("profile_path"))
    item["normalized_profile_path"] = normalized
    item["profile_conflict"] = find_upload_account_profile_conflict(
        normalized_profile_path=normalized,
        exclude_account_id=str(item.get("account_id") or ""),
    )
    active_locks = list_active_runtime_locks()
    account_busy = None
    profile_busy = None
    for lock in active_locks:
        if str(lock.get("lock_type") or "") == "account_id" and str(lock.get("resource_key") or "") == str(item.get("account_id") or ""):
            account_busy = lock
        if str(lock.get("lock_type") or "") == "profile_path" and str(lock.get("resource_key") or "") == normalized:
            profile_busy = lock
    item["busy_lock"] = profile_busy or account_busy
    if item["profile_conflict"]:
        item["profile_lock_state"] = "conflict"
    elif item["busy_lock"]:
        item["profile_lock_state"] = "locked"
    else:
        item["profile_lock_state"] = str(item.get("profile_lock_state") or "idle")
    return item


def create_upload_account_row(data: dict):
    prepared = ensure_upload_account_profile_path_fields(data)
    account_id = str(prepared.get("account_id") or uuid.uuid4()).strip() or str(uuid.uuid4())
    payload = {
        "account_id": account_id,
        "platform": prepared["platform"],
        "channel_code": str(prepared.get("channel_code") or "").strip(),
        "account_key": prepared["account_key"],
        "display_name": str(prepared.get("display_name") or "").strip(),
        "status": str(prepared.get("status") or "active").strip().lower(),
        "profile_path": prepared["profile_path"],
        "proxy_id": str(prepared.get("proxy_id") or "").strip(),
        "proxy_config_json": _json_dumps(prepared.get("proxy_config") or {}),
        "daily_limit": int(prepared.get("daily_limit") or 0),
        "cooldown_minutes": int(prepared.get("cooldown_minutes") or 0),
        "today_count": int(prepared.get("today_count") or 0),
        "last_upload_at": prepared.get("last_upload_at"),
        "last_login_check_at": prepared.get("last_login_check_at"),
        "login_state": str(prepared.get("login_state") or "unknown").strip().lower(),
        "profile_lock_state": str(prepared.get("profile_lock_state") or "idle").strip().lower(),
        "health_json": _json_dumps(prepared.get("health_json") or {}),
        "metadata_json": _json_dumps(prepared.get("metadata_json") or {}),
    }
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO upload_accounts (
            account_id, platform, channel_code, account_key, display_name, status,
            profile_path, proxy_id, proxy_config_json, daily_limit, cooldown_minutes, today_count,
            last_upload_at, last_login_check_at, login_state, profile_lock_state, health_json,
            metadata_json, created_at, updated_at
        )
        VALUES (
            :account_id, :platform, :channel_code, :account_key, :display_name, :status,
            :profile_path, :proxy_id, :proxy_config_json, :daily_limit, :cooldown_minutes, :today_count,
            :last_upload_at, :last_login_check_at, :login_state, :profile_lock_state, :health_json,
            :metadata_json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """,
        payload,
    )
    conn.commit()
    row = cur.execute("SELECT * FROM upload_accounts WHERE account_id = ?", (account_id,)).fetchone()
    conn.close()
    return enrich_upload_account_runtime_state(_normalize_upload_account_row(row))


def update_upload_account_row(account_id: str, changes: dict):
    allowed = {
        "platform", "channel_code", "account_key", "display_name", "status",
        "profile_path", "proxy_id", "proxy_config", "daily_limit", "cooldown_minutes", "today_count",
        "last_upload_at", "last_login_check_at", "login_state", "profile_lock_state", "health_json", "metadata_json",
    }
    current = get_upload_account_row(account_id) or {}
    merged = dict(current)
    merged.update(changes or {})
    merged = ensure_upload_account_profile_path_fields(merged)
    values: dict[str, Any] = {}
    for key, value in merged.items():
        if key not in allowed:
            continue
        if key in {"health_json", "metadata_json", "proxy_config"}:
            db_key = "proxy_config_json" if key == "proxy_config" else key
            values[db_key] = _json_dumps(value or {})
        elif key in {"daily_limit", "cooldown_minutes", "today_count"}:
            values[key] = int(value or 0)
        elif value is None and key in {"last_upload_at", "last_login_check_at"}:
            values[key] = None
        else:
            values[key] = str(value or "").strip()
    if not values:
        return get_upload_account_row(account_id)
    assignments = ", ".join([f"{key} = :{key}" for key in values])
    values["account_id"] = account_id
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE upload_accounts
        SET {assignments}, updated_at = CURRENT_TIMESTAMP
        WHERE account_id = :account_id
        """,
        values,
    )
    conn.commit()
    row = cur.execute("SELECT * FROM upload_accounts WHERE account_id = ?", (account_id,)).fetchone()
    conn.close()
    return enrich_upload_account_runtime_state(_normalize_upload_account_row(row))


def disable_upload_account_row(account_id: str):
    return update_upload_account_row(account_id, {"status": "disabled"})


def get_upload_scheduler_state():
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM upload_scheduler_state WHERE state_id = ?",
        (UPLOAD_SCHEDULER_STATE_ID,),
    ).fetchone()
    conn.close()
    return _normalize_upload_scheduler_state_row(row)


def update_upload_scheduler_state(changes: dict | None = None):
    allowed = {
        "scheduler_enabled",
        "max_concurrent_uploads",
        "tick_interval_seconds",
        "last_tick_at",
        "running_count",
        "status",
        "metadata",
    }
    values: dict[str, Any] = {}
    for key, value in (changes or {}).items():
        if key not in allowed:
            continue
        if key == "scheduler_enabled":
            values[key] = 1 if value else 0
        elif key in {"max_concurrent_uploads", "tick_interval_seconds", "running_count"}:
            minimum = 1 if key in {"max_concurrent_uploads", "tick_interval_seconds"} else 0
            values[key] = max(minimum, int(value or 0))
        elif key == "metadata":
            values["metadata_json"] = _json_dumps(value or {})
        else:
            values[key] = str(value or "").strip()
    if not values:
        return get_upload_scheduler_state()
    assignments = ", ".join([f"{key} = :{key}" for key in values])
    values["state_id"] = UPLOAD_SCHEDULER_STATE_ID
    conn = get_conn()
    conn.execute(
        f"""
        UPDATE upload_scheduler_state
        SET {assignments}, updated_at = CURRENT_TIMESTAMP
        WHERE state_id = :state_id
        """,
        values,
    )
    conn.commit()
    conn.close()
    return get_upload_scheduler_state()


def increment_upload_scheduler_running_count(delta: int):
    conn = get_conn()
    row = conn.execute(
        "SELECT running_count FROM upload_scheduler_state WHERE state_id = ?",
        (UPLOAD_SCHEDULER_STATE_ID,),
    ).fetchone()
    current = 0
    if row:
        try:
            current = max(0, int(row["running_count"] or 0))
        except Exception:
            current = 0
    next_value = max(0, current + int(delta or 0))
    conn.execute(
        """
        UPDATE upload_scheduler_state
        SET running_count = ?, updated_at = CURRENT_TIMESTAMP
        WHERE state_id = ?
        """,
        (next_value, UPLOAD_SCHEDULER_STATE_ID),
    )
    conn.commit()
    conn.close()
    return get_upload_scheduler_state()


def create_upload_video_row(data: dict):
    video_id = str(data.get("video_id") or uuid.uuid4()).strip() or str(uuid.uuid4())
    payload = {
        "video_id": video_id,
        "video_path": str(data.get("video_path") or "").strip(),
        "file_name": str(data.get("file_name") or "").strip(),
        "platform": str(data.get("platform") or "tiktok").strip().lower() or "tiktok",
        "source_type": str(data.get("source_type") or "manual_file").strip().lower(),
        "status": str(data.get("status") or "ready").strip().lower(),
        "caption": str(data.get("caption") or "").strip(),
        "hashtags_json": json.dumps(data.get("hashtags") or [], ensure_ascii=False),
        "cover_path": str(data.get("cover_path") or "").strip(),
        "note": str(data.get("note") or "").strip(),
        "duration_sec": float(data.get("duration_sec") or 0),
        "file_size": int(data.get("file_size") or 0),
        "metadata_json": _json_dumps(data.get("metadata") or {}),
    }
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO upload_videos (
            video_id, video_path, file_name, platform, source_type, status,
            caption, hashtags_json, cover_path, note, duration_sec, file_size,
            metadata_json, created_at, updated_at
        )
        VALUES (
            :video_id, :video_path, :file_name, :platform, :source_type, :status,
            :caption, :hashtags_json, :cover_path, :note, :duration_sec, :file_size,
            :metadata_json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """,
        payload,
    )
    conn.commit()
    row = cur.execute("SELECT * FROM upload_videos WHERE video_id = ?", (video_id,)).fetchone()
    conn.close()
    return _normalize_upload_video_row(row)


def list_upload_video_rows(
    *,
    platform: str = "",
    status: str = "",
    source_type: str = "",
    limit: int = 100,
):
    safe_limit = max(1, min(int(limit or 100), 500))
    clauses = []
    params: list[Any] = []
    if platform:
        clauses.append("platform = ?")
        params.append(platform)
    if status:
        clauses.append("status = ?")
        params.append(status)
    if source_type:
        clauses.append("source_type = ?")
        params.append(source_type)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT * FROM upload_videos
        {where}
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()
    conn.close()
    return [_normalize_upload_video_row(r) for r in rows]


def get_upload_video_row(video_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM upload_videos WHERE video_id = ?", (video_id,)).fetchone()
    conn.close()
    return _normalize_upload_video_row(row)


def get_upload_video(video_id: str):
    return get_upload_video_row(video_id)


def update_upload_video_row(video_id: str, changes: dict):
    allowed = {"caption", "hashtags", "cover_path", "note", "status", "metadata"}
    values: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in allowed:
            continue
        if key == "hashtags":
            values["hashtags_json"] = json.dumps(value or [], ensure_ascii=False)
        elif key == "metadata":
            values["metadata_json"] = _json_dumps(value or {})
        else:
            values[key] = str(value or "").strip()
    if not values:
        return get_upload_video_row(video_id)
    assignments = ", ".join([f"{key} = :{key}" for key in values])
    values["video_id"] = video_id
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE upload_videos
        SET {assignments}, updated_at = CURRENT_TIMESTAMP
        WHERE video_id = :video_id
        """,
        values,
    )
    conn.commit()
    row = cur.execute("SELECT * FROM upload_videos WHERE video_id = ?", (video_id,)).fetchone()
    conn.close()
    return _normalize_upload_video_row(row)


def disable_upload_video_row(video_id: str):
    return update_upload_video_row(video_id, {"status": "disabled"})


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


def add_upload_queue_item(
    *,
    video_path: str,
    video_id: str = '',
    render_job_id: str = '',
    part_no: int = 0,
    channel_code: str = '',
    account_id: str = '',
    platform: str = 'tiktok',
    caption: str = '',
    hashtags: list[str] | None = None,
    scheduled_at: str = '',
    priority: int = 0,
    status: str | None = None,
    metadata: dict | None = None,
):
    queue_id = str(uuid.uuid4())
    final_status = status or ('scheduled' if str(scheduled_at or '').strip() else 'pending')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO upload_queue (
            queue_id, video_id, video_path, render_job_id, part_no, account_id, platform,
            channel_code, caption, hashtags_json, status, priority, scheduled_at,
            attempt_count, max_attempts, last_error, metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 3, '', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """,
        (
            queue_id,
            video_id or None,
            video_path,
            render_job_id,
            int(part_no or 0),
            account_id or None,
            platform or 'tiktok',
            channel_code,
            caption or '',
            json.dumps(hashtags or [], ensure_ascii=False),
            final_status,
            int(priority or 0),
            str(scheduled_at or '').strip(),
            _json_dumps(metadata or {}),
        ),
    )
    conn.commit()
    row = cur.execute('SELECT * FROM upload_queue WHERE queue_id = ?', (queue_id,)).fetchone()
    conn.close()
    return _normalize_upload_queue_row(row)


def list_upload_queue(limit: int = 100, status: str = '', account_id: str = '', platform: str = ''):
    safe_limit = max(1, min(int(limit or 100), 500))
    clauses = []
    params: list[Any] = []
    if status:
        clauses.append("q.status = ?")
        params.append(status)
    if account_id:
        clauses.append("q.account_id = ?")
        params.append(account_id)
    if platform:
        clauses.append("q.platform = ?")
        params.append(platform)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    conn = get_conn()
    rows = conn.execute(
        f"""
        SELECT
            q.*,
            COALESCE(v.file_name, '') AS video_file_name,
            COALESCE(a.display_name, '') AS account_display_name,
            COALESCE(a.account_key, '') AS account_key
        FROM upload_queue q
        LEFT JOIN upload_videos v ON v.video_id = q.video_id
        LEFT JOIN upload_accounts a ON a.account_id = q.account_id
        {where}
        ORDER BY q.priority DESC, q.created_at DESC
        LIMIT ?
        """,
        (*params, safe_limit),
    ).fetchall()
    conn.close()
    return [_normalize_upload_queue_row(r) for r in rows]


def get_upload_queue_item(queue_id: str):
    conn = get_conn()
    row = conn.execute(
        """
        SELECT
            q.*,
            COALESCE(v.file_name, '') AS video_file_name,
            COALESCE(a.display_name, '') AS account_display_name,
            COALESCE(a.account_key, '') AS account_key
        FROM upload_queue q
        LEFT JOIN upload_videos v ON v.video_id = q.video_id
        LEFT JOIN upload_accounts a ON a.account_id = q.account_id
        WHERE q.queue_id = ?
        """,
        (queue_id,),
    ).fetchone()
    conn.close()
    return _normalize_upload_queue_row(row)


def update_upload_queue_item(queue_id: str, changes: dict):
    allowed = {"account_id", "caption", "hashtags", "priority", "scheduled_at", "status"}
    values: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in allowed:
            continue
        if key == "hashtags":
            values["hashtags_json"] = json.dumps(value or [], ensure_ascii=False)
        elif key == "priority":
            values[key] = int(value or 0)
        else:
            values[key] = str(value or "").strip()
    if "scheduled_at" in values and "status" not in values:
        current = get_upload_queue_item(queue_id)
        if current and current.get("status") in {"pending", "scheduled"}:
            values["status"] = "scheduled" if values["scheduled_at"] else "pending"
    if not values:
        return get_upload_queue_item(queue_id)
    assignments = ", ".join([f"{key} = :{key}" for key in values])
    values["queue_id"] = queue_id
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE upload_queue
        SET {assignments}, updated_at = CURRENT_TIMESTAMP
        WHERE queue_id = :queue_id
        """,
        values,
    )
    conn.commit()
    conn.close()
    return get_upload_queue_item(queue_id)


def set_upload_queue_last_error(queue_id: str, error: str):
    conn = get_conn()
    conn.execute(
        """
        UPDATE upload_queue
        SET last_error = ?, updated_at = CURRENT_TIMESTAMP
        WHERE queue_id = ?
        """,
        (str(error or "").strip(), queue_id),
    )
    conn.commit()
    conn.close()
    return get_upload_queue_item(queue_id)


def update_upload_queue_status(
    queue_id: str,
    status: str,
    last_error: str | None = None,
    attempt_count_delta: int = 0,
    result: dict | None = None,
):
    allowed = {'pending', 'scheduled', 'uploading', 'success', 'failed', 'held', 'cancelled'}
    if status not in allowed:
        raise ValueError(f"invalid upload queue status: {status}")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE upload_queue
        SET status = ?,
            last_error = CASE WHEN ? IS NULL THEN last_error ELSE ? END,
            attempt_count = attempt_count + ?,
            result_json = CASE WHEN ? IS NULL THEN result_json ELSE ? END,
            updated_at = CURRENT_TIMESTAMP
        WHERE queue_id = ?
        """,
        (
            status,
            last_error,
            last_error,
            int(attempt_count_delta or 0),
            None if result is None else _json_dumps(result),
            None if result is None else _json_dumps(result),
            queue_id,
        ),
    )
    conn.commit()
    conn.close()
    return get_upload_queue_item(queue_id)


def mark_upload_queue_uploading(queue_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE upload_queue
        SET status = 'uploading',
            last_error = '',
            attempt_count = attempt_count + 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE queue_id = ? AND status IN ('pending', 'scheduled', 'failed', 'held')
        """,
        (queue_id,),
    )
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return get_upload_queue_item(queue_id), changed > 0


def mark_upload_queue_success(queue_id: str, result: dict | None = None):
    return update_upload_queue_status(queue_id, 'success', last_error='', result=result or {})


def mark_upload_queue_failed(queue_id: str, error: str):
    return update_upload_queue_status(queue_id, 'failed', last_error=error or 'Upload failed', attempt_count_delta=0)


def cancel_upload_queue_item(queue_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE upload_queue
        SET status = 'cancelled',
            updated_at = CURRENT_TIMESTAMP
        WHERE queue_id = ? AND status IN ('pending', 'scheduled', 'held', 'failed')
        """,
        (queue_id,),
    )
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return get_upload_queue_item(queue_id), changed > 0


def insert_upload_history(
    *,
    queue_id: str,
    account_id: str = '',
    video_id: str = '',
    platform: str = '',
    video_path: str = '',
    status: str,
    attempt_no: int = 0,
    started_at: str = '',
    finished_at: str = '',
    duration_seconds: float = 0,
    error: str = '',
    adapter_result: dict | None = None,
    metadata: dict | None = None,
):
    history_id = str(uuid.uuid4())
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO upload_history (
            history_id, queue_id, account_id, video_id, platform, video_path,
            status, attempt_no, started_at, finished_at, duration_seconds,
            error, adapter_result_json, metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (
            history_id,
            queue_id,
            account_id or None,
            video_id or None,
            platform or '',
            video_path or '',
            status,
            int(attempt_no or 0),
            started_at or '',
            finished_at or '',
            float(duration_seconds or 0),
            error or '',
            _json_dumps(adapter_result or {}),
            _json_dumps(metadata or {}),
        ),
    )
    conn.commit()
    row = cur.execute("SELECT * FROM upload_history WHERE history_id = ?", (history_id,)).fetchone()
    conn.close()
    return _normalize_upload_history_row(row)


def list_upload_history(queue_id: str | None = None, limit: int = 50):
    safe_limit = max(1, min(int(limit or 50), 500))
    conn = get_conn()
    if queue_id:
        rows = conn.execute(
            """
            SELECT * FROM upload_history
            WHERE queue_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (queue_id, safe_limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM upload_history
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    conn.close()
    return [_normalize_upload_history_row(r) for r in rows]
