"""Schema migration step files.

Each migration is a Python file in this directory named NNNN_description.py
(zero-padded, sortable). The file must define three attributes consumed by
app.db.migrations.discover_migrations():

    VERSION: int    # globally unique, monotonically increasing
    NAME:    str    # short slug
    up(conn):       # callable taking a sqlite3.Connection

Example (commented; this directory ships empty in Sprint 6.B):

    # 0002_add_user_prefs.py
    VERSION = 2
    NAME    = "add_user_prefs"

    def up(conn):
        conn.execute(
            "CREATE TABLE IF NOT EXISTS user_prefs ("
            "  user_id TEXT PRIMARY KEY,"
            "  prefs_json TEXT NOT NULL DEFAULT '{}'"
            ")"
        )

Convention (enforced by CLAUDE.md, not by the runner):
  - Additive only — no DROP, no ALTER RENAME, no column-type changes.
  - Idempotent inside up() — use CREATE TABLE IF NOT EXISTS / CREATE INDEX
    IF NOT EXISTS. The runner already skips applied versions, but defensive
    DDL helps when an operator runs a half-applied migration manually.
  - Self-contained — no imports from app code outside the stdlib + sqlite3.
"""
