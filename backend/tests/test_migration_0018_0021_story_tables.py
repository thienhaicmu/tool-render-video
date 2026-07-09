"""Story-to-Video P0 — migrations 0018-0021 (Story Memory tables) smoke tests.

Pins the additive contract for the Story Mode tables:
1. Each up() creates its table(s); all are idempotent.
2. FK story_series → characters/environments/graph cascades on delete
   (Sacred Contract #7 defence-in-depth; mirrors migration 0003).
3. Tables accept inserts and read them back.
"""
from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

_STEPS = Path(__file__).resolve().parent.parent / "app" / "db" / "migration_steps"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"_mig_{name}", _STEPS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _apply_all(conn: sqlite3.Connection) -> None:
    _load("0018_add_story_series_table").up(conn)
    _load("0019_add_story_characters_table").up(conn)
    _load("0020_add_story_environments_table").up(conn)
    _load("0021_add_story_graph_tables").up(conn)


def _tables(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def test_all_tables_created():
    conn = sqlite3.connect(":memory:")
    _apply_all(conn)
    names = _tables(conn)
    for t in ("story_series", "characters", "environments",
              "relationships", "story_timeline", "chapter_summary"):
        assert t in names, f"missing table {t}"


def test_idempotent():
    conn = sqlite3.connect(":memory:")
    _apply_all(conn)
    _apply_all(conn)  # MUST NOT raise
    assert "characters" in _tables(conn)


def test_fk_cascade_delete_series_removes_children():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    _apply_all(conn)
    conn.execute("INSERT INTO story_series (id, title) VALUES ('s1', 'Series 1')")
    conn.execute("INSERT INTO characters (id, series_id, name) VALUES ('c1', 's1', 'Hero')")
    conn.execute("INSERT INTO environments (id, series_id, name) VALUES ('e1', 's1', 'Hall')")
    conn.execute("INSERT INTO chapter_summary (series_id, chapter_no, rolling_summary) "
                 "VALUES ('s1', 1, 'sum')")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0] == 1

    conn.execute("DELETE FROM story_series WHERE id = 's1'")
    conn.commit()
    assert conn.execute("SELECT COUNT(*) FROM characters").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM environments").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM chapter_summary").fetchone()[0] == 0


def test_insert_round_trip():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _apply_all(conn)
    conn.execute("INSERT INTO story_series (id, title, language) VALUES ('s', 'T', 'vi')")
    conn.execute(
        "INSERT INTO characters (id, series_id, name, canonical_desc, voice_engine, voice_id) "
        "VALUES ('c', 's', 'Hàn Phong', 'áo trắng', 'gemini', 'vi-Wavenet-A')"
    )
    row = conn.execute("SELECT * FROM characters WHERE id='c'").fetchone()
    assert row["name"] == "Hàn Phong"
    assert row["voice_engine"] == "gemini"
    assert row["reference_image_path"] == ""  # defaulted
