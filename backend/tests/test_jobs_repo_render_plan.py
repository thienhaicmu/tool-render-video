"""
Sprint 2.1 — test the jobs_repo update_render_plan / get_render_plan helpers.

Pins:
- write-then-read round-trip preserves the exact JSON blob
- get_render_plan returns None when job doesn't exist
- get_render_plan returns None when render_plan_json is NULL
- get_render_plan returns None when render_plan_json is empty string
- helpers never raise on DB error (Contract #3 spirit)
- update_render_plan with None clears the field
"""
import sqlite3
import uuid
from pathlib import Path
from unittest import mock

import pytest

from app.db.connection import db_conn, init_db
from app.db.jobs_repo import get_render_plan, update_render_plan, upsert_job


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Point connection.py at a fresh SQLite file under tmp_path so these
    tests don't touch the real data/app.db.

    Pattern lifted from test_db_connection.py: patch both DATABASE_PATH
    (the env-derived constant) and _ACTIVE_DB_PATH (the resolution
    cache) so `_resolve_db_path` re-resolves to the test path. Also
    swap thread-local storage for a clean one to avoid cross-test
    connection bleed.
    """
    import threading

    import app.db.connection as conn
    test_db = tmp_path / "test_app.db"
    monkeypatch.setattr(conn, "DATABASE_PATH", test_db)
    monkeypatch.setattr(conn, "_ACTIVE_DB_PATH", None)
    monkeypatch.setattr(conn, "_tls", threading.local())
    init_db()
    yield test_db


def _new_job(channel: str = "test") -> str:
    job_id = f"job-{uuid.uuid4().hex[:8]}"
    upsert_job(job_id, kind="render", channel_code=channel, status="queued")
    return job_id


class TestRoundTrip:
    def test_write_then_read_preserves_blob(self, isolated_db):
        job_id = _new_job()
        blob = '{"schema_version":1,"clips":[{"start":1.0,"end":2.0}]}'
        update_render_plan(job_id, blob)
        assert get_render_plan(job_id) == blob

    def test_unicode_blob_preserved(self, isolated_db):
        job_id = _new_job()
        blob = '{"creator_context_id":"Khoảnh khắc"}'
        update_render_plan(job_id, blob)
        assert get_render_plan(job_id) == blob

    def test_overwrite_in_place(self, isolated_db):
        job_id = _new_job()
        update_render_plan(job_id, '{"v":1}')
        update_render_plan(job_id, '{"v":2}')
        assert get_render_plan(job_id) == '{"v":2}'


class TestNoneSemantics:
    def test_unknown_job_returns_none(self, isolated_db):
        assert get_render_plan("does-not-exist") is None

    def test_freshly_inserted_job_has_no_plan(self, isolated_db):
        # New job → column defaults to NULL → helper normalises to None.
        job_id = _new_job()
        assert get_render_plan(job_id) is None

    def test_update_with_none_clears_field(self, isolated_db):
        job_id = _new_job()
        update_render_plan(job_id, '{"v":1}')
        assert get_render_plan(job_id) == '{"v":1}'
        update_render_plan(job_id, None)
        assert get_render_plan(job_id) is None

    def test_empty_string_treated_as_none_on_read(self, isolated_db):
        """An empty string is semantically 'no plan' — get_render_plan returns None.

        Production callers normally pass either a real RenderPlan JSON or
        explicit None. Treating empty string as None means callers that
        accidentally pass "" don't get a malformed payload through to
        RenderPlan.from_json(). Round-trip writers should pass None for
        the absent state.
        """
        job_id = _new_job()
        # Directly write an empty string at the DB layer (helper would also
        # work, but this models a stored payload from a buggy caller).
        with db_conn() as conn:
            conn.execute(
                "UPDATE jobs SET render_plan_json = ? WHERE job_id = ?",
                ("", job_id),
            )
            conn.commit()
        assert get_render_plan(job_id) is None


class TestNeverRaises:
    def test_update_swallows_db_error(self, isolated_db, caplog):
        """If the DB connection itself fails, update_render_plan logs a
        warning and returns silently — never raises. The render job
        must keep running even when persistence is broken."""
        with mock.patch("app.db.jobs_repo.db_conn", side_effect=sqlite3.OperationalError("boom")):
            # Must not raise.
            update_render_plan("any-job", '{"v":1}')

    def test_get_swallows_db_error(self, isolated_db):
        with mock.patch("app.db.jobs_repo.db_conn", side_effect=sqlite3.OperationalError("boom")):
            # Must not raise; returns None.
            assert get_render_plan("any-job") is None


class TestEndToEndWithDataclass:
    """Smoke-test the round-trip with the actual RenderPlan dataclass."""

    def test_render_plan_to_db_and_back(self, isolated_db):
        from app.domain.render_plan import (
            AudioPlan,
            CameraStrategy,
            ClipPlan,
            OutputConfig,
            RenderPlan,
            SubtitlePolicy,
        )

        original = RenderPlan(
            clips=[ClipPlan(start=10.0, end=40.0, rank=1, clip_name="hook")],
            subtitle_policy=SubtitlePolicy(style="viral", market="vn"),
            camera_strategy=CameraStrategy(motion_aware_crop=True),
            audio_plan=AudioPlan(voice_enabled=True),
            output_config=OutputConfig(codec="h264_nvenc", crf=22),
            creator_context_id="creator-vn-1",
        )
        job_id = _new_job()
        update_render_plan(job_id, original.to_json())

        raw = get_render_plan(job_id)
        assert raw is not None
        restored = RenderPlan.from_json(raw)
        assert restored == original
