"""
Migration 0026: characters.asset_slug — GĐ3 identity lock (library asset per character).

A series character that resolved to a library asset (e.g. geeme_042) must keep that
EXACT asset in every later chapter — same face across chapter 1 and chapter 186. The
resolver (character_resolver.py) treats a persisted asset_slug as MATCHED_EXACT and
never re-assigns it; persist_series_memory writes it after a successful render.

Additive, defaults to '' (= no lock, resolver assigns fresh) — pre-migration rows and
code are unaffected. Sacred Contract #7 honoured (ALTER ADD COLUMN only). Idempotent:
PRAGMA table_info skip + the runner's schema_versions record.
"""
from __future__ import annotations

import sqlite3

VERSION = 26
NAME = "characters_add_asset_slug"


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(characters)")
    existing = {row[1] for row in cur.fetchall()}
    if "asset_slug" not in existing:
        cur.execute("ALTER TABLE characters ADD COLUMN asset_slug TEXT NOT NULL DEFAULT ''")
