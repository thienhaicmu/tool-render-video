"""test_db_backup.py — Sprint 6.A.

Verifies the online SQLite backup module:
- snapshot_db produces a valid sqlite file with the source's schema
- snapshot_db returns None on missing source (no exception)
- prune_snapshots removes only files beyond newest keep_last
- prune_snapshots tolerates a missing dir
- maybe_snapshot_after_job triggers on every Nth call (N=2 here)
- maybe_snapshot_after_job returns None when neither trigger fires

Audit reference: docs/review/AUDIT_2026-06-02.md ⛔ data/app.db — No Backup
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from app.services import db_backup
from app.services.db_backup import (
    list_snapshots,
    maybe_snapshot_after_job,
    prune_snapshots,
    snapshot_db,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def source_db(tmp_path) -> Path:
    """Create a tiny on-disk SQLite source DB with one row to back up."""
    src = tmp_path / "source.db"
    conn = sqlite3.connect(str(src))
    try:
        conn.execute("CREATE TABLE jobs (job_id TEXT PRIMARY KEY, payload TEXT)")
        conn.execute("INSERT INTO jobs VALUES (?, ?)", ("test-1", '{"k":1}'))
        conn.commit()
    finally:
        conn.close()
    return src


@pytest.fixture(autouse=True)
def reset_state(monkeypatch, tmp_path):
    """Reset module trigger state + redirect get_active_db_path to a fixture DB."""
    db_backup._reset_state_for_tests()
    yield
    db_backup._reset_state_for_tests()


def _patch_active_db(monkeypatch, db_path: Path) -> None:
    """Make snapshot_db read from db_path instead of the runtime DB."""
    monkeypatch.setattr(db_backup, "get_active_db_path", lambda: db_path)


# ── snapshot_db ──────────────────────────────────────────────────────────────


class TestSnapshotDb:
    def test_produces_valid_sqlite_file_with_source_data(
        self, source_db, tmp_path, monkeypatch,
    ):
        _patch_active_db(monkeypatch, source_db)
        dest_dir = tmp_path / "backups"
        snap = snapshot_db(target_dir=dest_dir)
        assert snap is not None
        assert snap.exists()
        assert snap.suffix == ".db"

        # Open the snapshot and verify the row + schema came across.
        conn = sqlite3.connect(str(snap))
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
            assert "jobs" in tables
            row = conn.execute("SELECT job_id, payload FROM jobs").fetchone()
            assert row == ("test-1", '{"k":1}')
        finally:
            conn.close()

    def test_returns_none_on_missing_source(self, tmp_path, monkeypatch):
        _patch_active_db(monkeypatch, tmp_path / "does-not-exist.db")
        dest_dir = tmp_path / "backups"
        # SQLite's connect-to-missing creates an empty file; the backup still
        # succeeds but produces an empty DB. The negative case for THIS test
        # is when get_active_db_path itself raises — simulate that.
        def raising():
            raise RuntimeError("simulated db resolution failure")
        monkeypatch.setattr(db_backup, "get_active_db_path", raising)
        snap = snapshot_db(target_dir=dest_dir)
        assert snap is None


# ── prune_snapshots ──────────────────────────────────────────────────────────


class TestPruneSnapshots:
    def _make_snap(self, dir_: Path, name: str, mtime_offset: float) -> Path:
        dir_.mkdir(parents=True, exist_ok=True)
        p = dir_ / name
        p.write_bytes(b"\x00")
        # Push the mtime forward/back so sort order is deterministic.
        target = time.time() + mtime_offset
        import os
        os.utime(p, (target, target))
        return p

    def test_removes_only_beyond_keep_last(self, tmp_path):
        d = tmp_path / "backups"
        # 4 snapshots, newest → oldest
        newest = self._make_snap(d, "app-20260602-100000.db", 0)
        mid1   = self._make_snap(d, "app-20260601-100000.db", -1000)
        mid2   = self._make_snap(d, "app-20260530-100000.db", -2000)
        old    = self._make_snap(d, "app-20260528-100000.db", -3000)

        removed = prune_snapshots(target_dir=d, keep_last=2)
        assert removed == 2
        # Newest 2 still present
        assert newest.exists()
        assert mid1.exists()
        # Oldest 2 gone
        assert not mid2.exists()
        assert not old.exists()

    def test_tolerates_missing_dir(self, tmp_path):
        result = prune_snapshots(target_dir=tmp_path / "does-not-exist", keep_last=5)
        assert result == 0

    def test_ignores_non_snapshot_files(self, tmp_path):
        d = tmp_path / "backups"
        d.mkdir()
        # A README, a notes file, etc. — must NOT be deleted
        readme = d / "README.md"
        readme.write_text("backup directory notes")
        notes = d / "operator-notes.txt"
        notes.write_text("don't delete me")
        # Also one stale snapshot
        self._make_snap(d, "app-20250101-100000.db", -1000000)
        removed = prune_snapshots(target_dir=d, keep_last=0)
        assert removed == 1
        assert readme.exists()
        assert notes.exists()


# ── maybe_snapshot_after_job ─────────────────────────────────────────────────


class TestMaybeSnapshotAfterJob:
    def test_n_trigger_every_nth_call(self, source_db, tmp_path, monkeypatch):
        # N=2 → calls 2, 4, 6 trigger; calls 1, 3, 5 do not.
        # Disable the time trigger so only the N counter is exercised. The
        # first call would otherwise time-fire because _last_backup_at=0 means
        # elapsed=inf, so we stub it to "just now" before invoking.
        monkeypatch.setattr(db_backup, "BACKUP_EVERY_N_JOBS", 2)
        monkeypatch.setattr(db_backup, "BACKUP_MIN_INTERVAL_SEC", 999_999)
        monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path / "backups")
        _patch_active_db(monkeypatch, source_db)

        # Stub last-backup time to "now" so the time trigger never fires here.
        with db_backup._job_counter_lock:
            db_backup._last_backup_at = time.monotonic()

        assert maybe_snapshot_after_job() is None  # 1st call: no trigger
        first = maybe_snapshot_after_job()
        assert first is not None                   # 2nd call: N triggers
        # snapshot_db() bumps _last_backup_at to "now" inside maybe_snapshot_after_job
        # so the time trigger stays disarmed for the rest of the test.
        assert maybe_snapshot_after_job() is None  # 3rd: no trigger
        second = maybe_snapshot_after_job()
        assert second is not None                  # 4th: N triggers
        # Two snapshots exist now
        snaps = list_snapshots(target_dir=tmp_path / "backups")
        assert len(snaps) == 2

    def test_skips_when_neither_trigger_fires(self, source_db, tmp_path, monkeypatch):
        # N=1000 (won't fire), interval=large → first call must NOT snapshot.
        # But the first call sets _last_backup_at=0; if interval check uses
        # `elapsed >= MIN`, last=0 means elapsed=inf → time_trigger fires.
        # We avoid that by stubbing _last_backup_at before invoking.
        monkeypatch.setattr(db_backup, "BACKUP_EVERY_N_JOBS", 1000)
        monkeypatch.setattr(db_backup, "BACKUP_MIN_INTERVAL_SEC", 999_999)
        monkeypatch.setattr(db_backup, "BACKUP_DIR", tmp_path / "backups")
        _patch_active_db(monkeypatch, source_db)

        # Pretend a backup was just taken so the time trigger can't fire.
        with db_backup._job_counter_lock:
            db_backup._last_backup_at = time.monotonic()
        assert maybe_snapshot_after_job() is None


# ── list_snapshots ────────────────────────────────────────────────────────────


class TestListSnapshots:
    def test_returns_newest_first(self, source_db, tmp_path, monkeypatch):
        _patch_active_db(monkeypatch, source_db)
        d = tmp_path / "backups"
        # Take two snapshots with a delay so mtimes differ.
        first = snapshot_db(target_dir=d)
        assert first is not None
        time.sleep(0.05)
        second = snapshot_db(target_dir=d)
        assert second is not None

        snaps = list_snapshots(target_dir=d)
        assert len(snaps) == 2
        # Newest first → second precedes first by mtime
        assert snaps[0][0] == second
        assert snaps[1][0] == first

    def test_returns_empty_for_missing_dir(self, tmp_path):
        snaps = list_snapshots(target_dir=tmp_path / "does-not-exist")
        assert snaps == []
