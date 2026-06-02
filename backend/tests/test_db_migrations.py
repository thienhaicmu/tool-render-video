"""test_db_migrations.py — Sprint 6.B.

Verifies the schema migration runner:
- empty steps directory: no error, no migrations applied
- single migration recorded in schema_versions on apply
- already-applied migrations are skipped on a re-run
- multiple migrations run in VERSION order
- malformed migration files raise a clear MigrationError
- migration failure rolls back; later migrations don't apply
- schema_versions table is created automatically if missing
- discover_migrations rejects duplicate VERSION values
- run_pending_migrations on a fresh DB starts at zero

Audit reference: Sprint 6 long-term — Sprint 6.B follow-up to Contract 7
work (schema lifecycle hardening).
"""
from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path

import pytest

from app.db.migrations import (
    MigrationError,
    applied_versions,
    discover_migrations,
    run_pending_migrations,
)


# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def conn(tmp_path) -> sqlite3.Connection:
    """Return a fresh sqlite3 connection bound to a tmp-path DB."""
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(str(db_path))
    yield c
    c.close()


def _write_migration(
    steps_dir: Path,
    filename: str,
    version: int,
    name: str,
    body: str = "pass",
) -> Path:
    """Drop a migration .py file into steps_dir with VERSION/NAME/up()."""
    steps_dir.mkdir(parents=True, exist_ok=True)
    path = steps_dir / filename
    path.write_text(
        textwrap.dedent(f"""
        VERSION = {version}
        NAME = "{name}"

        def up(conn):
            {body}
        """).strip() + "\n",
        encoding="utf-8",
    )
    return path


# ── applied_versions ─────────────────────────────────────────────────────────


class TestAppliedVersions:
    def test_creates_schema_versions_table(self, conn):
        result = applied_versions(conn)
        assert result == set()
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "schema_versions" in tables

    def test_returns_recorded_versions(self, conn):
        applied_versions(conn)  # ensure table exists
        conn.execute("INSERT INTO schema_versions (version, name) VALUES (1, 'init')")
        conn.execute("INSERT INTO schema_versions (version, name) VALUES (3, 'add_col')")
        conn.commit()
        assert applied_versions(conn) == {1, 3}


# ── discover_migrations ───────────────────────────────────────────────────────


class TestDiscoverMigrations:
    def test_empty_dir_returns_empty(self, tmp_path):
        assert discover_migrations(tmp_path) == []

    def test_missing_dir_returns_empty(self, tmp_path):
        assert discover_migrations(tmp_path / "does-not-exist") == []

    def test_loads_single_migration(self, tmp_path):
        _write_migration(tmp_path, "0001_initial.py", 1, "initial")
        migs = discover_migrations(tmp_path)
        assert len(migs) == 1
        assert migs[0].version == 1
        assert migs[0].name == "initial"
        assert callable(migs[0].up)

    def test_sorts_by_version_ascending(self, tmp_path):
        _write_migration(tmp_path, "0003_third.py", 3, "third")
        _write_migration(tmp_path, "0001_first.py", 1, "first")
        _write_migration(tmp_path, "0002_second.py", 2, "second")
        migs = discover_migrations(tmp_path)
        assert [m.version for m in migs] == [1, 2, 3]

    def test_ignores_files_starting_with_underscore(self, tmp_path):
        _write_migration(tmp_path, "0001_real.py", 1, "real")
        # An __init__.py that doesn't follow the convention
        (tmp_path / "__init__.py").write_text("# package marker\n", encoding="utf-8")
        migs = discover_migrations(tmp_path)
        assert [m.version for m in migs] == [1]

    def test_missing_attribute_raises_clear_error(self, tmp_path):
        path = tmp_path / "0001_bad.py"
        path.write_text("VERSION = 1\nNAME = 'bad'\n", encoding="utf-8")  # no up()
        with pytest.raises(MigrationError, match="missing required attribute 'up'"):
            discover_migrations(tmp_path)

    def test_non_int_version_raises(self, tmp_path):
        path = tmp_path / "0001_bad.py"
        path.write_text("VERSION = 'one'\nNAME = 'bad'\ndef up(c): pass\n", encoding="utf-8")
        with pytest.raises(MigrationError, match="VERSION must be int"):
            discover_migrations(tmp_path)

    def test_duplicate_version_raises(self, tmp_path):
        _write_migration(tmp_path, "0001_a.py", 1, "a")
        _write_migration(tmp_path, "0001b_dup.py", 1, "b")
        with pytest.raises(MigrationError, match="duplicate VERSION=1"):
            discover_migrations(tmp_path)


# ── run_pending_migrations ────────────────────────────────────────────────────


class TestRunPendingMigrations:
    def test_empty_dir_returns_zero_applied(self, conn, tmp_path):
        result = run_pending_migrations(conn, steps_dir=tmp_path)
        assert result["applied"] == []
        assert result["skipped"] == []
        assert result["available"] == 0

    def test_applies_and_records_single_migration(self, conn, tmp_path):
        _write_migration(
            tmp_path, "0001_add_foo.py", 1, "add_foo",
            body="conn.execute('CREATE TABLE foo (id INTEGER PRIMARY KEY)')",
        )
        result = run_pending_migrations(conn, steps_dir=tmp_path)
        assert result["applied"] == [1]
        assert result["skipped"] == []
        # Table was created
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "foo" in tables
        # schema_versions has the row
        rows = conn.execute(
            "SELECT version, name FROM schema_versions"
        ).fetchall()
        assert (1, "add_foo") in [(r[0], r[1]) for r in rows]

    def test_re_run_skips_already_applied(self, conn, tmp_path):
        _write_migration(tmp_path, "0001_init.py", 1, "init",
                         body="conn.execute('CREATE TABLE bar (id INTEGER)')")
        first = run_pending_migrations(conn, steps_dir=tmp_path)
        assert first["applied"] == [1]
        second = run_pending_migrations(conn, steps_dir=tmp_path)
        assert second["applied"] == []
        assert second["skipped"] == [1]

    def test_runs_multiple_in_version_order(self, conn, tmp_path):
        _write_migration(tmp_path, "0002_b.py", 2, "b",
                         body="conn.execute('CREATE TABLE t2 (id INTEGER)')")
        _write_migration(tmp_path, "0001_a.py", 1, "a",
                         body="conn.execute('CREATE TABLE t1 (id INTEGER)')")
        _write_migration(tmp_path, "0003_c.py", 3, "c",
                         body="conn.execute('CREATE TABLE t3 (id INTEGER)')")
        result = run_pending_migrations(conn, steps_dir=tmp_path)
        assert result["applied"] == [1, 2, 3]

    def test_failure_rolls_back_and_raises(self, conn, tmp_path):
        _write_migration(tmp_path, "0001_good.py", 1, "good",
                         body="conn.execute('CREATE TABLE ok (id INTEGER)')")
        # Write the failing migration directly (multi-line body via the
        # dedent template is fiddly; bypass the helper for this one case).
        (tmp_path / "0002_bad.py").write_text(
            "VERSION = 2\n"
            "NAME = \"bad\"\n"
            "\n"
            "def up(conn):\n"
            "    conn.execute('CREATE TABLE will_fail (id INTEGER)')\n"
            "    raise RuntimeError('boom')\n",
            encoding="utf-8",
        )
        with pytest.raises(MigrationError, match="0002_bad failed"):
            run_pending_migrations(conn, steps_dir=tmp_path)
        # The good migration applied + recorded
        assert applied_versions(conn) == {1}
        # The bad migration's CREATE TABLE was rolled back
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        assert "ok" in tables
        assert "will_fail" not in tables
