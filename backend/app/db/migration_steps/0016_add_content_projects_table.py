"""Migration 0016: content_projects table (Content Studio draft persistence).

CU-1 (2026-07-03). Content Studio's ContentPlan previously lived only in the FE
until a render was submitted — closing the tab lost the work. This table gives
each Content Studio project a durable server-side identity (script + plan +
config) that the FE autosaves, so a draft survives reloads and can be reopened.

Purely additive: a new table with all-defaulted columns. No existing table is
dropped, renamed, or column-type-changed. Idempotent (CREATE TABLE IF NOT EXISTS).
"""
VERSION = 16
NAME = "add_content_projects_table"


def up(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS content_projects (
            id           TEXT PRIMARY KEY,
            title        TEXT NOT NULL DEFAULT '',
            script       TEXT NOT NULL DEFAULT '',
            plan_json    TEXT DEFAULT NULL,
            config_json  TEXT DEFAULT NULL,
            status       TEXT NOT NULL DEFAULT 'draft',
            last_job_id  TEXT NOT NULL DEFAULT '',
            created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
            updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_content_projects_updated "
        "ON content_projects(updated_at DESC)"
    )
