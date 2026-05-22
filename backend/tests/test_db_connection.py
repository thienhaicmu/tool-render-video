"""
Tests for app.db.connection — Phase 4F.1 extraction.

Covers:
- Import identity (services.db re-exports same objects as app.db.connection)
- Constants
- get_conn() contract (Connection type, row_factory, PRAGMAs)
- init_db() creates all expected tables, is idempotent
- _json_dumps / _json_loads edge cases
- _thread_conn() reuses connection within same thread
- close_thread_conn() closes and clears thread-local connection
- _utc_now() / _utc_now_iso() contracts

Test isolation: every test that touches the DB uses a tmp_path fixture and
patches app.db.connection._ACTIVE_DB_PATH = None to force re-resolution.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_db_path(monkeypatch, db_path):
    """Force connection.py to use db_path instead of the real DATABASE_PATH."""
    import app.db.connection as conn
    monkeypatch.setattr(conn, "_ACTIVE_DB_PATH", None)
    monkeypatch.setattr("app.core.config.DATABASE_PATH", db_path)


# ---------------------------------------------------------------------------
# Import identity — services.db re-exports same objects
# ---------------------------------------------------------------------------

class TestImportIdentity:
    NAMES = [
        "get_conn",
        "close_thread_conn",
        "init_db",
        "_thread_conn",
        "_json_dumps",
        "_json_loads",
        "_utc_now",
        "_utc_now_iso",
    ]

    def _both(self, name):
        import app.db.connection as conn_mod
        import app.services.db as db_mod
        return getattr(conn_mod, name), getattr(db_mod, name)

    def test_get_conn_same_object(self):
        a, b = self._both("get_conn")
        assert a is b

    def test_close_thread_conn_same_object(self):
        a, b = self._both("close_thread_conn")
        assert a is b

    def test_init_db_same_object(self):
        a, b = self._both("init_db")
        assert a is b

    def test_thread_conn_same_object(self):
        a, b = self._both("_thread_conn")
        assert a is b

    def test_json_dumps_same_object(self):
        a, b = self._both("_json_dumps")
        assert a is b

    def test_json_loads_same_object(self):
        a, b = self._both("_json_loads")
        assert a is b

    def test_utc_now_same_object(self):
        a, b = self._both("_utc_now")
        assert a is b

    def test_utc_now_iso_same_object(self):
        a, b = self._both("_utc_now_iso")
        assert a is b


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    def test_upload_profile_lock_ttl_minutes(self):
        from app.db.connection import UPLOAD_PROFILE_LOCK_TTL_MINUTES
        assert UPLOAD_PROFILE_LOCK_TTL_MINUTES == 30

    def test_upload_scheduler_state_id(self):
        from app.db.connection import UPLOAD_SCHEDULER_STATE_ID
        assert UPLOAD_SCHEDULER_STATE_ID == "main"

    def test_constants_re_exported_from_services_db(self):
        from app.services.db import UPLOAD_PROFILE_LOCK_TTL_MINUTES, UPLOAD_SCHEDULER_STATE_ID
        assert UPLOAD_PROFILE_LOCK_TTL_MINUTES == 30
        assert UPLOAD_SCHEDULER_STATE_ID == "main"


# ---------------------------------------------------------------------------
# get_conn()
# ---------------------------------------------------------------------------

class TestGetConn:
    def test_returns_sqlite_connection(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn
        conn = get_conn()
        try:
            assert isinstance(conn, sqlite3.Connection)
        finally:
            conn.close()

    def test_row_factory_is_sqlite_row(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn
        conn = get_conn()
        try:
            assert conn.row_factory is sqlite3.Row
        finally:
            conn.close()

    def test_foreign_keys_pragma_on(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn
        conn = get_conn()
        try:
            cur = conn.execute("PRAGMA foreign_keys")
            row = cur.fetchone()
            assert row[0] == 1
        finally:
            conn.close()

    def test_wal_journal_mode(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn
        conn = get_conn()
        try:
            cur = conn.execute("PRAGMA journal_mode")
            row = cur.fetchone()
            assert row[0] == "wal"
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# init_db()
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "jobs",
    "job_parts",
    "upload_accounts",
    "upload_queue",
    "upload_videos",
    "upload_history",
    "upload_runtime_locks",
    "upload_scheduler_state",
    "upload_proxy_pool",
    "creator_prefs",
}


class TestInitDb:
    def _get_tables(self, conn):
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in cur.fetchall()}

    def test_creates_all_expected_tables(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            tables = self._get_tables(conn)
            missing = EXPECTED_TABLES - tables
            assert not missing, f"Missing tables: {missing}"
        finally:
            conn.close()

    def test_idempotent_second_call_does_not_raise(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import init_db
        init_db()
        init_db()  # must not raise

    def test_tables_accessible_after_init(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        from app.db.connection import get_conn, init_db
        init_db()
        conn = get_conn()
        try:
            conn.execute("SELECT COUNT(*) FROM jobs").fetchone()
            conn.execute("SELECT COUNT(*) FROM upload_accounts").fetchone()
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# _json_dumps / _json_loads
# ---------------------------------------------------------------------------

class TestJsonHelpers:
    def test_roundtrip_dict(self):
        from app.db.connection import _json_dumps, _json_loads
        data = {"key": "value", "num": 42}
        assert _json_loads(_json_dumps(data)) == data

    def test_roundtrip_list(self):
        from app.db.connection import _json_dumps, _json_loads
        data = [1, 2, 3]
        assert _json_loads(_json_dumps(data)) == data

    def test_dumps_none_returns_empty_object_json(self):
        from app.db.connection import _json_dumps
        # None is treated as {} sentinel — returns serialized empty object
        assert _json_dumps(None) == "{}"

    def test_loads_none_returns_default(self):
        from app.db.connection import _json_loads
        assert _json_loads(None, default={}) == {}

    def test_loads_empty_string_returns_default(self):
        from app.db.connection import _json_loads
        assert _json_loads("", default=[]) == []

    def test_loads_invalid_json_returns_default(self):
        from app.db.connection import _json_loads
        assert _json_loads("not-valid-json", default={"fallback": True}) == {"fallback": True}

    def test_loads_invalid_json_default_none_returns_empty_dict(self):
        from app.db.connection import _json_loads
        # default=None is the sentinel meaning "use {} as fallback"
        result = _json_loads("!!bad", default=None)
        assert result == {}

    def test_dumps_nested_structure(self):
        from app.db.connection import _json_dumps, _json_loads
        data = {"a": {"b": [1, 2]}, "c": None}
        assert _json_loads(_json_dumps(data)) == data


# ---------------------------------------------------------------------------
# _thread_conn()
# ---------------------------------------------------------------------------

class TestThreadConn:
    def test_same_thread_reuses_connection(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        import app.db.connection as conn_mod
        monkeypatch.setattr(conn_mod, "_tls", threading.local())
        from app.db.connection import _thread_conn, close_thread_conn
        try:
            c1 = _thread_conn()
            c2 = _thread_conn()
            assert c1 is c2
        finally:
            close_thread_conn()

    def test_different_threads_get_different_connections(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        import app.db.connection as conn_mod
        monkeypatch.setattr(conn_mod, "_tls", threading.local())
        from app.db.connection import _thread_conn, close_thread_conn

        results = {}

        def worker(tid):
            results[tid] = _thread_conn()
            close_thread_conn()

        t1 = threading.Thread(target=worker, args=("t1",))
        t2 = threading.Thread(target=worker, args=("t2",))
        t1.start(); t1.join()
        t2.start(); t2.join()

        assert results["t1"] is not results["t2"]


# ---------------------------------------------------------------------------
# close_thread_conn()
# ---------------------------------------------------------------------------

class TestCloseThreadConn:
    def test_close_clears_thread_local(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        import app.db.connection as conn_mod
        monkeypatch.setattr(conn_mod, "_tls", threading.local())
        from app.db.connection import _thread_conn, close_thread_conn

        c1 = _thread_conn()
        close_thread_conn()
        c2 = _thread_conn()
        # After close, a new connection must be opened
        assert c1 is not c2

    def test_close_on_empty_does_not_raise(self, tmp_path, monkeypatch):
        db_file = tmp_path / "test.db"
        _reset_db_path(monkeypatch, db_file)
        import app.db.connection as conn_mod
        monkeypatch.setattr(conn_mod, "_tls", threading.local())
        from app.db.connection import close_thread_conn
        close_thread_conn()  # no connection open — must not raise


# ---------------------------------------------------------------------------
# _utc_now() / _utc_now_iso()
# ---------------------------------------------------------------------------

class TestUtcHelpers:
    def test_utc_now_returns_timezone_aware_datetime(self):
        from app.db.connection import _utc_now
        dt = _utc_now()
        assert isinstance(dt, datetime)
        assert dt.tzinfo is not None
        assert dt.tzinfo == timezone.utc

    def test_utc_now_iso_returns_string(self):
        from app.db.connection import _utc_now_iso
        s = _utc_now_iso()
        assert isinstance(s, str)
        assert len(s) > 0

    def test_utc_now_iso_is_parseable(self):
        from app.db.connection import _utc_now_iso
        s = _utc_now_iso()
        # Must be parseable as ISO 8601
        dt = datetime.fromisoformat(s)
        assert dt is not None
