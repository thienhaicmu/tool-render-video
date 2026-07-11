"""
Migration 0025: story_assets.description — rich text for AI library-pick.

The AI plan chooses library assets by slug (library-pick); a short natural-language
``description`` (from a ``{file}.json`` sidecar ``desc`` key) lets it disambiguate
similar assets in build_library_catalog. Additive, defaults to '' — the catalog falls
back to slug-derived tokens when empty, so pre-migration rows and code are unaffected.

Named ``description`` (not ``desc`` — a SQL reserved word). Sacred Contract #2 (defaults
to '' = no behaviour change) and #7 (additive ALTER TABLE, no DROP/RENAME/type-change).
Idempotent: PRAGMA table_info skip + the runner's schema_versions record.
"""
from __future__ import annotations

import sqlite3


VERSION = 25
NAME = "add_description_to_story_assets"


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(story_assets)")
    existing = {row[1] for row in cur.fetchall()}
    if "description" not in existing:
        cur.execute("ALTER TABLE story_assets ADD COLUMN description TEXT NOT NULL DEFAULT ''")
