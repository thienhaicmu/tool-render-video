"""Tests for the db_backup hardening (2026-06-18).

The opportunistic snapshot is now fired off the render worker thread, and
maybe_snapshot_after_job() guards against stacking snapshots when a previous
one is still running (a hung/slow sqlite backup would otherwise re-fire on the
time trigger every subsequent render and pile up daemon threads).
"""
from __future__ import annotations

import pytest

from app.features.render.engine.pipeline import db_backup


@pytest.fixture(autouse=True)
def _reset():
    db_backup._reset_state_for_tests()
    yield
    db_backup._reset_state_for_tests()


@pytest.fixture
def _isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "backup-src.db"
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", db_path)
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db
    init_db()
    yield db_path


def test_maybe_snapshot_skips_when_in_progress(monkeypatch):
    called = {"n": 0}
    monkeypatch.setattr(db_backup, "snapshot_db", lambda *a, **k: called.__setitem__("n", called["n"] + 1))
    # Simulate a snapshot already running.
    db_backup._snapshot_in_progress = True
    assert db_backup.maybe_snapshot_after_job() is None
    assert called["n"] == 0  # snapshot_db never invoked


def test_maybe_snapshot_takes_one_and_clears_flag(_isolated_db, tmp_path, monkeypatch):
    monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path / "backups")
    # First call time-triggers (last_backup_at == 0 → elapsed == inf).
    snap = db_backup.maybe_snapshot_after_job()
    assert snap is not None and snap.exists()
    # The in-progress flag must be reset so future renders can snapshot again.
    assert db_backup._snapshot_in_progress is False


def test_maybe_snapshot_clears_flag_even_if_backup_fails(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("backup blew up")
    monkeypatch.setattr(db_backup, "snapshot_db", _boom)
    # snapshot_db raising must not leave the guard stuck True (would wedge all
    # future snapshots). maybe_snapshot lets the exception propagate, but the
    # finally clears the flag.
    with pytest.raises(RuntimeError):
        db_backup.maybe_snapshot_after_job()
    assert db_backup._snapshot_in_progress is False
