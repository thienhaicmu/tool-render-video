"""Phase 4F.5D: verify upload schema removed from init_db() and _drop_upload_tables() works."""
import sqlite3
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = BACKEND_ROOT / "app"

_UPLOAD_TABLES = (
    "upload_accounts",
    "upload_queue",
    "upload_videos",
    "upload_history",
    "upload_runtime_locks",
    "upload_scheduler_state",
    "upload_proxy_pool",
)
_LIVE_TABLES = ("jobs", "job_parts", "creator_prefs")


def _reset_db_path(monkeypatch, db_path):
    import app.db.connection as conn_mod
    monkeypatch.setattr(conn_mod, "DATABASE_PATH", db_path)
    monkeypatch.setattr(conn_mod, "_ACTIVE_DB_PATH", None)


def _get_tables(conn) -> set:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )
    return {row[0] for row in cur.fetchall()}


# ── Upload constants removed from connection.py ───────────────────────────────

class TestUploadConstantsRemoved:
    def test_upload_profile_lock_ttl_minutes_not_in_connection(self):
        import app.db.connection as conn_mod
        assert not hasattr(conn_mod, "UPLOAD_PROFILE_LOCK_TTL_MINUTES"), (
            "UPLOAD_PROFILE_LOCK_TTL_MINUTES still present in connection.py — "
            "should be removed in Phase 4F.5D"
        )

    def test_upload_scheduler_state_id_not_in_connection(self):
        import app.db.connection as conn_mod
        assert not hasattr(conn_mod, "UPLOAD_SCHEDULER_STATE_ID"), (
            "UPLOAD_SCHEDULER_STATE_ID still present in connection.py — "
            "should be removed in Phase 4F.5D"
        )


# ── init_db() no longer creates upload tables ─────────────────────────────────

class TestInitDbNoUploadTables:
    def test_upload_accounts_not_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            tables = _get_tables(conn)
            assert "upload_accounts" not in tables
        finally:
            conn.close()

    def test_upload_queue_not_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "upload_queue" not in _get_tables(conn)
        finally:
            conn.close()

    def test_upload_videos_not_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "upload_videos" not in _get_tables(conn)
        finally:
            conn.close()

    def test_upload_history_not_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "upload_history" not in _get_tables(conn)
        finally:
            conn.close()

    def test_upload_runtime_locks_not_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "upload_runtime_locks" not in _get_tables(conn)
        finally:
            conn.close()

    def test_upload_scheduler_state_not_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "upload_scheduler_state" not in _get_tables(conn)
        finally:
            conn.close()

    def test_upload_proxy_pool_not_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "upload_proxy_pool" not in _get_tables(conn)
        finally:
            conn.close()

    def test_no_upload_tables_at_all(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            tables = _get_tables(conn)
            upload_present = [t for t in _UPLOAD_TABLES if t in tables]
            assert upload_present == [], (
                f"init_db() still created upload table(s): {upload_present}"
            )
        finally:
            conn.close()


# ── init_db() still creates live tables ───────────────────────────────────────

class TestInitDbLiveTablesPresent:
    def test_jobs_still_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "jobs" in _get_tables(conn)
        finally:
            conn.close()

    def test_job_parts_still_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "job_parts" in _get_tables(conn)
        finally:
            conn.close()

    def test_creator_prefs_still_created(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "creator_prefs" in _get_tables(conn)
        finally:
            conn.close()

    def test_exactly_four_live_tables(self, tmp_path, monkeypatch):
        _reset_db_path(monkeypatch, tmp_path / "test.db")
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            tables = _get_tables(conn)
            # Exclude the write-check helper table if present
            real_tables = {t for t in tables if t != "__db_write_check"}
            assert real_tables == {
                "jobs", "job_parts", "creator_prefs", "download_jobs", "clip_feedback",
            }, (
                f"Unexpected tables after init_db(): {real_tables}"
            )
        finally:
            conn.close()


# ── _drop_upload_tables() drops existing upload tables and is idempotent ──────

class TestDropUploadTables:
    def _make_old_db(self, db_path: Path):
        """Create a DB file that simulates an old install with all upload tables.

        The `jobs` table here mirrors the day-1 core columns (job_id, kind,
        channel_code, status, created_at, updated_at) — anything narrower is
        not representative of any real install. _ensure_columns(jobs, …) will
        still add the later-added columns (stage, payload_json, …) during
        init_db().
        """
        conn = sqlite3.connect(str(db_path))
        for table in _UPLOAD_TABLES:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY)"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL DEFAULT '',
                channel_code TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT '',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
        conn.close()

    def test_drops_all_upload_tables_from_existing_db(self, tmp_path, monkeypatch):
        db_file = tmp_path / "old.db"
        self._make_old_db(db_file)
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            tables = _get_tables(conn)
            upload_present = [t for t in _UPLOAD_TABLES if t in tables]
            assert upload_present == [], (
                f"_drop_upload_tables() did not remove: {upload_present}"
            )
        finally:
            conn.close()

    def test_jobs_preserved_after_drop(self, tmp_path, monkeypatch):
        db_file = tmp_path / "old.db"
        self._make_old_db(db_file)
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            assert "jobs" in _get_tables(conn)
        finally:
            conn.close()

    def test_drop_upload_tables_idempotent(self, tmp_path, monkeypatch):
        db_file = tmp_path / "fresh.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn, _drop_upload_tables, init_db
        init_db()
        conn = get_conn()
        try:
            # Calling again on a DB that never had upload tables must not raise
            _drop_upload_tables(conn)
            _drop_upload_tables(conn)
        finally:
            conn.close()

    def test_drop_upload_tables_helper_exists(self):
        import app.db.connection as conn_mod
        assert hasattr(conn_mod, "_drop_upload_tables"), (
            "_drop_upload_tables helper not found in connection.py"
        )
        assert callable(conn_mod._drop_upload_tables)
