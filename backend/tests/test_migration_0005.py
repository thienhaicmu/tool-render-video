"""Sprint I-B — migration 0005 smoke tests (creator_prefs_channel table).

1. Table created with expected columns.
2. up() is idempotent (safe to run twice).
3. Row can be inserted and read back (basic round-trip).
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_STEP_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "db" / "migration_steps"
    / "0005_add_creator_prefs_channel_table.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("_mig_0005", _STEP_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _apply_migration(conn):
    _load_migration().up(conn)


def test_migration_creates_table():
    conn = sqlite3.connect(":memory:")
    _apply_migration(conn)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='creator_prefs_channel'"
    ).fetchone()
    assert row is not None, "creator_prefs_channel table not found"


def test_migration_is_idempotent():
    conn = sqlite3.connect(":memory:")
    _apply_migration(conn)
    _apply_migration(conn)  # must not raise


def test_migration_row_roundtrip():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _apply_migration(conn)
    conn.execute(
        "INSERT INTO creator_prefs_channel (channel_code, prefs_json) VALUES (?, ?)",
        ("vn", '{"creator_context": {"channel_name": "VN"}}'),
    )
    row = conn.execute(
        "SELECT prefs_json FROM creator_prefs_channel WHERE channel_code = 'vn'"
    ).fetchone()
    assert row is not None
    import json
    data = json.loads(row["prefs_json"])
    assert data["creator_context"]["channel_name"] == "VN"
