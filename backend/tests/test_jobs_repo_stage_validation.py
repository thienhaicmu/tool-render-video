"""Tests for the stage/status validation guard in jobs_repo (audit BR05/C06).

Sacred Contracts #4 and #5 freeze the job-stage and per-part status
strings. Until Batch 3 the writers passed raw strings with no check —
a typo silently corrupted every consumer.

These tests pin two properties:
1. Writes with valid stage/status values produce no warning.
2. Writes with unknown stage/status values produce a WARN log (but DO
   NOT raise — the contract is non-fatal so a live render is never
   killed by a typo). The log lets ops/devs catch the drift in CI logs.

The repo functions are tested via monkey-patching the DB connection so
no real SQLite write happens.
"""
from __future__ import annotations

import logging

import pytest

from app.core.stage import JobPartStage, JobStage
from app.db import jobs_repo


class _FakeConn:
    """Minimal stand-in for sqlite3.Connection used by jobs_repo."""

    def __init__(self):
        self.calls: list[tuple] = []

    def execute(self, sql: str, params=()):
        self.calls.append((sql, params))
        return self

    def commit(self):
        pass

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_db(monkeypatch):
    conn = _FakeConn()

    class _CM:
        def __enter__(self_inner):
            return conn

        def __exit__(self_inner, *exc):
            return False

    monkeypatch.setattr(jobs_repo, "db_conn", lambda: _CM())
    monkeypatch.setattr(jobs_repo, "_thread_conn", lambda: conn)
    return conn


# ---------------------------------------------------------------------------
# upsert_job
# ---------------------------------------------------------------------------

def test_upsert_job_known_status_no_warning(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.upsert_job(
        job_id="j1", kind="render", channel_code="k1",
        status="queued", stage="queued",
    )
    # No warnings from jobs_repo.
    warnings = [r for r in caplog.records if r.name == "app.db" and r.levelname == "WARNING"]
    assert warnings == []


def test_upsert_job_unknown_status_warns(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.upsert_job(
        job_id="j1", kind="render", channel_code="k1",
        status="compleated",  # typo — Sacred Contract violation
        stage="rendering",
    )
    msgs = [r.getMessage() for r in caplog.records if r.name == "app.db"]
    assert any("unknown status" in m and "compleated" in m for m in msgs), msgs


def test_upsert_job_unknown_stage_warns(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.upsert_job(
        job_id="j1", kind="render", channel_code="k1",
        status="running", stage="renderring",  # typo
    )
    msgs = [r.getMessage() for r in caplog.records if r.name == "app.db"]
    assert any("unknown stage" in m and "renderring" in m for m in msgs), msgs


def test_upsert_job_accepts_enum_member(fake_db, caplog):
    """Passing the enum member itself (not a string) must work — the repo
    normalises to the enum's .value before persisting.
    """
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.upsert_job(
        job_id="j1", kind="render", channel_code="k1",
        status="running", stage=JobStage.RENDERING,
    )
    warnings = [r for r in caplog.records if r.name == "app.db" and r.levelname == "WARNING"]
    assert warnings == []
    # The persisted stage value is the string, not the enum repr.
    assert fake_db.calls, "no SQL executed"
    _, params = fake_db.calls[-1]
    assert "rendering" in params


def test_upsert_job_empty_stage_silent(fake_db, caplog):
    """The default stage='' is a valid no-op — must not warn."""
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.upsert_job(
        job_id="j1", kind="render", channel_code="k1", status="queued",
    )
    warnings = [r for r in caplog.records if r.name == "app.db" and r.levelname == "WARNING"]
    assert warnings == []


# ---------------------------------------------------------------------------
# update_job_progress
# ---------------------------------------------------------------------------

def test_update_job_progress_unknown_stage_warns(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.update_job_progress(
        job_id="j1", stage="foo_stage", progress_percent=10,
    )
    msgs = [r.getMessage() for r in caplog.records if r.name == "app.db"]
    assert any("unknown stage" in m and "foo_stage" in m for m in msgs)


def test_update_job_progress_with_enum_no_warning(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.update_job_progress(
        job_id="j1",
        stage=JobStage.RENDERING,
        progress_percent=50,
        status="running",
    )
    warnings = [r for r in caplog.records if r.name == "app.db" and r.levelname == "WARNING"]
    assert warnings == []


def test_update_job_progress_unknown_status_warns(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.update_job_progress(
        job_id="j1",
        stage="rendering",
        progress_percent=10,
        status="finsihed",  # typo
    )
    msgs = [r.getMessage() for r in caplog.records if r.name == "app.db"]
    assert any("unknown status" in m and "finsihed" in m for m in msgs)


# ---------------------------------------------------------------------------
# upsert_job_part
# ---------------------------------------------------------------------------

def test_upsert_job_part_known_status_no_warning(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.upsert_job_part(
        job_id="j1", part_no=1, part_name="seg-1", status="rendering",
    )
    warnings = [r for r in caplog.records if r.name == "app.db" and r.levelname == "WARNING"]
    assert warnings == []


def test_upsert_job_part_unknown_status_warns(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.upsert_job_part(
        job_id="j1", part_no=1, part_name="seg-1", status="cuttng",  # typo
    )
    msgs = [r.getMessage() for r in caplog.records if r.name == "app.db"]
    assert any("unknown part_status" in m and "cuttng" in m for m in msgs)


def test_upsert_job_part_accepts_enum_member(fake_db, caplog):
    caplog.set_level(logging.WARNING, logger="app.db")
    jobs_repo.upsert_job_part(
        job_id="j1", part_no=1, part_name="seg-1",
        status=JobPartStage.RENDERING,
    )
    warnings = [r for r in caplog.records if r.name == "app.db" and r.levelname == "WARNING"]
    assert warnings == []


# ---------------------------------------------------------------------------
# Contract — guard must be non-fatal
# ---------------------------------------------------------------------------

def test_unknown_value_does_not_raise(fake_db, caplog):
    """Sacred Contract #2 + spirit of #3 — the validation guard must
    never escalate to an exception. A typo is a warning, not a crash.
    A live render in flight must complete even if a writer slipped in
    an unknown stage value.
    """
    caplog.set_level(logging.WARNING, logger="app.db")
    # No raise expected.
    jobs_repo.upsert_job(
        job_id="j1", kind="render", channel_code="k1",
        status="bogus_status", stage="bogus_stage",
    )
    jobs_repo.update_job_progress(
        job_id="j1", stage="bogus_stage2", progress_percent=1, status="bogus_status2",
    )
    jobs_repo.upsert_job_part(
        job_id="j1", part_no=1, part_name="seg", status="bogus_part_status",
    )
