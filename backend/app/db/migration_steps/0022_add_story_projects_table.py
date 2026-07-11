"""
Migration 0022: story_projects table (Story Mode project persistence, SP1).

A "project" persists a Story Studio session — its input config + the edited
StoryPlan v2 — so work survives a reload / app restart. Optional and orthogonal to
render jobs (which keep their own story_plan_json); a one-off render never touches
this table.

Purely additive: a new table with all-defaulted columns. No existing table is
dropped, renamed, or column-type-changed. Idempotent (CREATE TABLE IF NOT EXISTS).
Sacred Contract #7 (additive-only) honoured.
"""
VERSION = 22
NAME = "add_story_projects_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS story_projects (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT '',
            language    TEXT NOT NULL DEFAULT '',
            source      TEXT NOT NULL DEFAULT '',
            config_json TEXT NOT NULL DEFAULT '',
            plan_json   TEXT NOT NULL DEFAULT '',
            status      TEXT NOT NULL DEFAULT 'draft',
            created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_story_projects_updated "
        "ON story_projects(updated_at DESC)"
    )
