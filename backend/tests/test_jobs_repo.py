"""
Tests for app.db.jobs_repo — Phase 4F.2 extraction.

Covers:
- Import identity (services.db re-exports same objects as app.db.jobs_repo)
- Job CRUD: upsert_job, get_job, delete_job (with cascade to job_parts)
- Progress: update_job_progress (with/without status, thread-local path)
- Pagination: list_jobs ordering, list_jobs_page limit/offset
- Job parts: upsert_job_part, list_job_parts, list_job_parts_bulk
- JSON payload/result roundtrip
- Thread-local: update_job_progress + upsert_job_part share _thread_conn;
  close_thread_conn clears it

Test isolation: every test patching DB state uses tmp_path + resets
app.db.connection._ACTIVE_DB_PATH = None to avoid touching production DB.
"""

import threading

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_db(monkeypatch, db_path):
    import app.db.connection as conn
    # Patch the local binding inside connection.py (from-import creates a local name)
    monkeypatch.setattr(conn, "DATABASE_PATH", db_path)
    monkeypatch.setattr(conn, "_ACTIVE_DB_PATH", None)
    conn.init_db()


# ---------------------------------------------------------------------------
# Import identity — services.db re-exports same objects
# ---------------------------------------------------------------------------

class TestImportIdentity:
    NAMES = [
        "upsert_job",
        "update_job_progress",
        "delete_job",
        "upsert_job_part",
        "get_job",
        "list_jobs",
        "list_jobs_page",
        "list_job_parts_bulk",
        "list_job_parts",
    ]

    def _both(self, name):
        import app.db.jobs_repo as repo
        import app.services.db as db_mod
        return getattr(repo, name), getattr(db_mod, name)

    def test_upsert_job_same_object(self):
        a, b = self._both("upsert_job")
        assert a is b

    def test_update_job_progress_same_object(self):
        a, b = self._both("update_job_progress")
        assert a is b

    def test_delete_job_same_object(self):
        a, b = self._both("delete_job")
        assert a is b

    def test_upsert_job_part_same_object(self):
        a, b = self._both("upsert_job_part")
        assert a is b

    def test_get_job_same_object(self):
        a, b = self._both("get_job")
        assert a is b

    def test_list_jobs_same_object(self):
        a, b = self._both("list_jobs")
        assert a is b

    def test_list_jobs_page_same_object(self):
        a, b = self._both("list_jobs_page")
        assert a is b

    def test_list_job_parts_bulk_same_object(self):
        a, b = self._both("list_job_parts_bulk")
        assert a is b

    def test_list_job_parts_same_object(self):
        a, b = self._both("list_job_parts")
        assert a is b


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------

class TestJobCrud:
    def test_upsert_job_creates_row(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, get_job
        upsert_job("job1", "render", "ch1", "queued")
        row = get_job("job1")
        assert row is not None
        assert row["job_id"] == "job1"
        assert row["kind"] == "render"
        assert row["status"] == "queued"

    def test_upsert_job_updates_existing_row(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, get_job
        upsert_job("job1", "render", "ch1", "queued")
        upsert_job("job1", "render", "ch1", "processing", stage="encode", progress_percent=50)
        row = get_job("job1")
        assert row["status"] == "processing"
        assert row["stage"] == "encode"
        assert row["progress_percent"] == 50

    def test_get_job_returns_expected_fields(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, get_job
        upsert_job("job2", "upload", "ch2", "done", stage="finish", priority=5)
        row = get_job("job2")
        assert row["kind"] == "upload"
        assert row["channel_code"] == "ch2"
        assert row["priority"] == 5

    def test_get_job_missing_returns_none(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import get_job
        assert get_job("nonexistent_job") is None

    def test_delete_job_removes_job(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, delete_job, get_job
        upsert_job("job3", "render", "ch1", "queued")
        delete_job("job3")
        assert get_job("job3") is None

    def test_delete_job_cascades_to_parts(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, upsert_job_part, delete_job, list_job_parts
        from app.db.connection import close_thread_conn
        upsert_job("job4", "render", "ch1", "queued")
        upsert_job_part("job4", 1, "part_1", "done")
        upsert_job_part("job4", 2, "part_2", "done")
        close_thread_conn()
        delete_job("job4")
        assert list_job_parts("job4") == []

    def test_delete_job_nonexistent_does_not_raise(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import delete_job
        delete_job("never_created")  # must not raise


# ---------------------------------------------------------------------------
# update_job_progress
# ---------------------------------------------------------------------------

class TestUpdateJobProgress:
    def test_updates_stage_progress_message(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, update_job_progress, get_job
        from app.db.connection import close_thread_conn
        upsert_job("job5", "render", "ch1", "queued")
        update_job_progress("job5", "encode", 42, message="halfway")
        close_thread_conn()
        row = get_job("job5")
        assert row["stage"] == "encode"
        assert row["progress_percent"] == 42
        assert row["message"] == "halfway"

    def test_updates_status_when_provided(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, update_job_progress, get_job
        from app.db.connection import close_thread_conn
        upsert_job("job6", "render", "ch1", "queued")
        update_job_progress("job6", "done", 100, status="completed")
        close_thread_conn()
        row = get_job("job6")
        assert row["status"] == "completed"

    def test_does_not_change_status_when_none(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, update_job_progress, get_job
        from app.db.connection import close_thread_conn
        upsert_job("job7", "render", "ch1", "processing")
        update_job_progress("job7", "encode", 10)
        close_thread_conn()
        row = get_job("job7")
        assert row["status"] == "processing"

    def test_uses_thread_local_connection(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        import app.db.connection as conn_mod
        monkeypatch.setattr(conn_mod, "_tls", threading.local())
        from app.db.jobs_repo import upsert_job, update_job_progress
        from app.db.connection import _thread_conn, close_thread_conn
        upsert_job("job8", "render", "ch1", "queued")
        update_job_progress("job8", "start", 1)
        # The thread_conn should be open now
        c1 = _thread_conn()
        update_job_progress("job8", "mid", 50)
        c2 = _thread_conn()
        assert c1 is c2, "update_job_progress must reuse the same thread-local connection"
        close_thread_conn()


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class TestPagination:
    def test_list_jobs_returns_all_in_created_desc_order(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, list_jobs
        from app.db.connection import get_conn
        upsert_job("j_old", "render", "ch1", "done")
        upsert_job("j_new", "render", "ch1", "queued")
        # Force j_old to a clearly earlier timestamp so ORDER BY created_at DESC is deterministic
        conn = get_conn()
        conn.execute("UPDATE jobs SET created_at = '2000-01-01 00:00:00' WHERE job_id = 'j_old'")
        conn.commit()
        conn.close()
        rows = list_jobs()
        ids = [r["job_id"] for r in rows]
        assert "j_new" in ids
        assert "j_old" in ids
        assert ids.index("j_new") < ids.index("j_old"), "list_jobs must order by created_at DESC"

    def test_list_jobs_page_limit(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, list_jobs_page
        for i in range(5):
            upsert_job(f"pg_job_{i}", "render", "ch1", "queued")
        rows = list_jobs_page(limit=3, offset=0)
        assert len(rows) == 3

    def test_list_jobs_page_offset(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, list_jobs_page
        for i in range(5):
            upsert_job(f"off_job_{i}", "render", "ch1", "queued")
        page0 = list_jobs_page(limit=3, offset=0)
        page1 = list_jobs_page(limit=3, offset=3)
        ids0 = {r["job_id"] for r in page0}
        ids1 = {r["job_id"] for r in page1}
        assert ids0.isdisjoint(ids1), "pages must not overlap"

    def test_list_jobs_page_empty_beyond_end(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, list_jobs_page
        upsert_job("only_job", "render", "ch1", "queued")
        rows = list_jobs_page(limit=10, offset=999)
        assert rows == []


# ---------------------------------------------------------------------------
# Job Parts
# ---------------------------------------------------------------------------

class TestJobParts:
    def test_upsert_job_part_creates_part(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, upsert_job_part, list_job_parts
        from app.db.connection import close_thread_conn
        upsert_job("jpart1", "render", "ch1", "processing")
        upsert_job_part("jpart1", 1, "clip_1", "done", start_sec=0.0, end_sec=10.0)
        close_thread_conn()
        parts = list_job_parts("jpart1")
        assert len(parts) == 1
        assert parts[0]["part_no"] == 1
        assert parts[0]["part_name"] == "clip_1"

    def test_upsert_job_part_updates_same_part(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, upsert_job_part, list_job_parts
        from app.db.connection import close_thread_conn
        upsert_job("jpart2", "render", "ch1", "processing")
        upsert_job_part("jpart2", 1, "clip_1", "processing", progress_percent=10)
        upsert_job_part("jpart2", 1, "clip_1", "done", progress_percent=100)
        close_thread_conn()
        parts = list_job_parts("jpart2")
        assert len(parts) == 1
        assert parts[0]["status"] == "done"
        assert parts[0]["progress_percent"] == 100

    def test_list_job_parts_ordered_by_part_no(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, upsert_job_part, list_job_parts
        from app.db.connection import close_thread_conn
        upsert_job("jpart3", "render", "ch1", "processing")
        upsert_job_part("jpart3", 3, "clip_3", "done")
        upsert_job_part("jpart3", 1, "clip_1", "done")
        upsert_job_part("jpart3", 2, "clip_2", "done")
        close_thread_conn()
        parts = list_job_parts("jpart3")
        assert [p["part_no"] for p in parts] == [1, 2, 3]

    def test_list_job_parts_bulk_empty_returns_empty_dict(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import list_job_parts_bulk
        assert list_job_parts_bulk([]) == {}

    def test_list_job_parts_bulk_groups_by_job_id(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, upsert_job_part, list_job_parts_bulk
        from app.db.connection import close_thread_conn
        upsert_job("bulk_j1", "render", "ch1", "done")
        upsert_job("bulk_j2", "render", "ch1", "done")
        upsert_job_part("bulk_j1", 1, "part_a", "done")
        upsert_job_part("bulk_j1", 2, "part_b", "done")
        upsert_job_part("bulk_j2", 1, "part_c", "done")
        close_thread_conn()
        result = list_job_parts_bulk(["bulk_j1", "bulk_j2"])
        assert len(result["bulk_j1"]) == 2
        assert len(result["bulk_j2"]) == 1

    def test_list_job_parts_bulk_returns_empty_list_for_no_parts(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, list_job_parts_bulk
        upsert_job("empty_j", "render", "ch1", "done")
        result = list_job_parts_bulk(["empty_j"])
        assert result["empty_j"] == []


# ---------------------------------------------------------------------------
# JSON payload / result roundtrip
# ---------------------------------------------------------------------------

class TestJsonFields:
    def test_payload_roundtrips_through_upsert_get(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, get_job
        import json
        payload = {"platform": "tiktok", "count": 3}
        upsert_job("jp_json1", "render", "ch1", "queued", payload=payload)
        row = get_job("jp_json1")
        assert row is not None
        stored = json.loads(row["payload_json"])
        assert stored == payload

    def test_result_roundtrips_through_upsert_get(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, get_job
        import json
        result = {"files": ["a.mp4", "b.mp4"]}
        upsert_job("jp_json2", "render", "ch1", "done", result=result)
        row = get_job("jp_json2")
        stored = json.loads(row["result_json"])
        assert stored == result

    def test_none_payload_stores_empty_object(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        from app.db.jobs_repo import upsert_job, get_job
        import json
        upsert_job("jp_json3", "render", "ch1", "queued", payload=None)
        row = get_job("jp_json3")
        stored = json.loads(row["payload_json"])
        assert stored == {}


# ---------------------------------------------------------------------------
# Thread-local: update_job_progress + upsert_job_part share connection
# ---------------------------------------------------------------------------

class TestThreadLocal:
    def test_update_progress_and_upsert_part_share_conn(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        import app.db.connection as conn_mod
        monkeypatch.setattr(conn_mod, "_tls", threading.local())
        from app.db.jobs_repo import upsert_job, update_job_progress, upsert_job_part
        from app.db.connection import _thread_conn, close_thread_conn
        upsert_job("tl_job", "render", "ch1", "queued")
        update_job_progress("tl_job", "start", 0)
        c1 = _thread_conn()
        upsert_job_part("tl_job", 1, "clip_1", "processing")
        c2 = _thread_conn()
        assert c1 is c2, "update_job_progress and upsert_job_part must share _thread_conn"
        close_thread_conn()

    def test_close_thread_conn_allows_new_connection(self, tmp_path, monkeypatch):
        _setup_db(monkeypatch, tmp_path / "test.db")
        import app.db.connection as conn_mod
        monkeypatch.setattr(conn_mod, "_tls", threading.local())
        from app.db.jobs_repo import upsert_job, update_job_progress
        from app.db.connection import _thread_conn, close_thread_conn
        upsert_job("tl_job2", "render", "ch1", "queued")
        update_job_progress("tl_job2", "start", 0)
        c1 = _thread_conn()
        close_thread_conn()
        update_job_progress("tl_job2", "end", 100)
        c2 = _thread_conn()
        assert c1 is not c2, "after close_thread_conn, a new connection must be opened"
        close_thread_conn()
