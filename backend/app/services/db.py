
import json
import logging
import os
import sqlite3
import threading
import uuid
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
            daily_limit INTEGER DEFAULT 0,
            cooldown_minutes INTEGER DEFAULT 0,
            today_count INTEGER DEFAULT 0,
            last_upload_at TEXT,
            last_login_check_at TEXT,
            login_state TEXT DEFAULT 'unknown',
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
            "daily_limit": "daily_limit INTEGER DEFAULT 0",
            "cooldown_minutes": "cooldown_minutes INTEGER DEFAULT 0",
            "today_count": "today_count INTEGER DEFAULT 0",
            "last_upload_at": "last_upload_at TEXT",
            "last_login_check_at": "last_login_check_at TEXT",
            "login_state": "login_state TEXT DEFAULT 'unknown'",
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


def _normalize_upload_account_row(row: sqlite3.Row | dict | None):
    if not row:
        return None
    data = dict(row)
    data["health_json"] = _json_loads(data.get("health_json"))
    data["metadata_json"] = _json_loads(data.get("metadata_json"))
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
    return [_normalize_upload_account_row(r) for r in rows]


def get_upload_account_row(account_id: str):
    conn = get_conn()
    row = conn.execute("SELECT * FROM upload_accounts WHERE account_id = ?", (account_id,)).fetchone()
    conn.close()
    return _normalize_upload_account_row(row)


def create_upload_account_row(data: dict):
    account_id = str(data.get("account_id") or uuid.uuid4()).strip() or str(uuid.uuid4())
    payload = {
        "account_id": account_id,
        "platform": str(data.get("platform") or "tiktok").strip().lower() or "tiktok",
        "channel_code": str(data.get("channel_code") or "").strip(),
        "account_key": str(data.get("account_key") or "default").strip() or "default",
        "display_name": str(data.get("display_name") or "").strip(),
        "status": str(data.get("status") or "active").strip().lower(),
        "profile_path": str(data.get("profile_path") or "").strip(),
        "proxy_id": str(data.get("proxy_id") or "").strip(),
        "daily_limit": int(data.get("daily_limit") or 0),
        "cooldown_minutes": int(data.get("cooldown_minutes") or 0),
        "today_count": int(data.get("today_count") or 0),
        "last_upload_at": data.get("last_upload_at"),
        "last_login_check_at": data.get("last_login_check_at"),
        "login_state": str(data.get("login_state") or "unknown").strip().lower(),
        "health_json": _json_dumps(data.get("health_json") or {}),
        "metadata_json": _json_dumps(data.get("metadata_json") or {}),
    }
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO upload_accounts (
            account_id, platform, channel_code, account_key, display_name, status,
            profile_path, proxy_id, daily_limit, cooldown_minutes, today_count,
            last_upload_at, last_login_check_at, login_state, health_json,
            metadata_json, created_at, updated_at
        )
        VALUES (
            :account_id, :platform, :channel_code, :account_key, :display_name, :status,
            :profile_path, :proxy_id, :daily_limit, :cooldown_minutes, :today_count,
            :last_upload_at, :last_login_check_at, :login_state, :health_json,
            :metadata_json, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
        """,
        payload,
    )
    conn.commit()
    row = cur.execute("SELECT * FROM upload_accounts WHERE account_id = ?", (account_id,)).fetchone()
    conn.close()
    return _normalize_upload_account_row(row)


def update_upload_account_row(account_id: str, changes: dict):
    allowed = {
        "platform", "channel_code", "account_key", "display_name", "status",
        "profile_path", "proxy_id", "daily_limit", "cooldown_minutes", "today_count",
        "last_upload_at", "last_login_check_at", "login_state", "health_json", "metadata_json",
    }
    values: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in allowed:
            continue
        if key in {"health_json", "metadata_json"}:
            values[key] = _json_dumps(value or {})
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
    return _normalize_upload_account_row(row)


def disable_upload_account_row(account_id: str):
    return update_upload_account_row(account_id, {"status": "disabled"})


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
            updated_at = CURRENT_TIMESTAMP
        WHERE queue_id = ? AND status IN ('pending', 'scheduled', 'failed')
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
    return update_upload_queue_status(queue_id, 'failed', last_error=error or 'Upload failed', attempt_count_delta=1)


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
