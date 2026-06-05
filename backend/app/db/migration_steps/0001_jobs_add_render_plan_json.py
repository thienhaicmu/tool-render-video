"""
Migration 0001: jobs.render_plan_json — add nullable column for RenderPlan blob.

Sprint 2.1 (RenderPlan skeleton): introduces a persisted RenderPlan JSON
payload per job. The column is additive, NULL-by-default, and never
read by code that predates this migration — backward-compat is
guaranteed both for stored payloads and for in-flight jobs that finish
without ever writing a plan.

Sacred Contract #2 honoured: the field defaults to NULL (the most
conservative disabled state). Sacred Contract #7 honoured: this is an
additive ALTER TABLE — no DROP, no RENAME, no type change. Idempotent
under repeated runs: the runner records `schema_versions(version=1)`,
and the body itself uses PRAGMA table_info to skip if the column
already exists (covers DBs that were patched manually before the
runner first ran).
"""
from __future__ import annotations

import sqlite3


VERSION = 1
NAME = "jobs_add_render_plan_json"


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(jobs)")
    existing = {row[1] for row in cur.fetchall()}
    if "render_plan_json" not in existing:
        cur.execute("ALTER TABLE jobs ADD COLUMN render_plan_json TEXT DEFAULT NULL")
