"""
Migration 0023: story project versions + soft-delete (SP3+).

Two additive changes to the Story project store (migration 0022):
  1. story_project_versions — named snapshots of a project's plan so the user can
     revert to an earlier version (version-history).
  2. story_projects.deleted_at — soft-delete (trash / restore); NULL = live.

Purely additive: a new table + a new nullable column with a NULL default. No DROP,
no RENAME, no type change. Idempotent (IF NOT EXISTS; the column add is PRAGMA-guarded).
Sacred Contract #7 (additive-only) honoured.
"""
VERSION = 23
NAME = "story_project_versions_and_soft_delete"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_project_versions (
            id          TEXT PRIMARY KEY,
            project_id  TEXT NOT NULL,
            label       TEXT NOT NULL DEFAULT '',
            plan_json   TEXT NOT NULL DEFAULT '',
            config_json TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_project_versions_project "
        "ON story_project_versions(project_id, created_at DESC)"
    )
    # Soft-delete column — add only if missing (idempotent).
    cols = {r[1] for r in conn.execute("PRAGMA table_info(story_projects)").fetchall()}
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE story_projects ADD COLUMN deleted_at TEXT DEFAULT NULL")
