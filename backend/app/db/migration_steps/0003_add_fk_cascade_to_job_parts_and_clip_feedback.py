"""Migration 0003: add FOREIGN KEY ... ON DELETE CASCADE on job_parts.job_id
and clip_feedback.job_id, referencing jobs.job_id.

Audit MT-6 closure (Batch 10L, 2026-06-06): closes FINDING-BR03.
``delete_job`` already cascades atomically inside a single ``db_conn()``
transaction, so orphans don't accrue in normal operation. But the
underlying FK constraint was absent — a future maintenance script that
deletes from ``jobs`` directly (or a partial-write crash) could leave
orphan rows that survive forever.

This migration retrofits the FK on EXISTING databases. New installs
already get the FK via the CREATE TABLE definitions in
``backend/app/db/connection.py:init_db``.

SQLite doesn't support ``ALTER TABLE ADD CONSTRAINT``, so the standard
recipe is the temp-table rename trick:

    1. CREATE TABLE <table>_new (...with FK...)
    2. INSERT INTO <table>_new SELECT * FROM <table>
    3. DROP TABLE <table>
    4. ALTER TABLE <table>_new RENAME TO <table>
    5. Re-create any non-implicit indexes that were on the old table

The audit's MT-6 entry suggests ``PRAGMA foreign_keys=OFF`` around the
copy. We deliberately DON'T do that — the migration runner has already
opened a transaction (``BEGIN``), and SQLite silently ignores PRAGMA
foreign_keys mid-transaction. Instead, the migration first DELETES any
orphan rows defensively — if no orphans, the INSERT-with-FK works
cleanly; if any are found, they're logged and removed before the copy.

Sacred Contract #7: every change inside the runner's single transaction.
A mid-migration crash rolls back to the pre-migration state. The
re-run on next boot starts from scratch (the schema_versions sentinel
row was never committed).

Idempotency: ``PRAGMA foreign_key_list(<table>)`` returns the existing
FKs; if any FK already points to ``jobs``, the table is skipped. This
covers DBs that were manually patched before the runner first ran.
"""
from __future__ import annotations

import logging
import sqlite3


VERSION = 3
NAME = "add_fk_cascade_to_job_parts_and_clip_feedback"

logger = logging.getLogger(__name__)


# Full CREATE-TABLE bodies for the new shape. Identical to the
# definitions in connection.py:init_db so a future schema audit can
# diff them against the live source. Keep in sync if init_db changes.
_NEW_JOB_PARTS_DDL = """
CREATE TABLE job_parts_new_mt6 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    part_no INTEGER NOT NULL,
    part_name TEXT NOT NULL,
    status TEXT NOT NULL,
    progress_percent INTEGER DEFAULT 0,
    start_sec REAL DEFAULT 0,
    end_sec REAL DEFAULT 0,
    duration REAL DEFAULT 0,
    viral_score REAL DEFAULT 0,
    motion_score REAL DEFAULT 0,
    hook_score REAL DEFAULT 0,
    output_file TEXT DEFAULT '',
    message TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, part_no),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
)
"""

_NEW_CLIP_FEEDBACK_DDL = """
CREATE TABLE clip_feedback_new_mt6 (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       TEXT    NOT NULL,
    part_no      INTEGER NOT NULL,
    channel_code TEXT    NOT NULL DEFAULT '',
    goal         TEXT    NOT NULL DEFAULT '',
    rating       INTEGER NOT NULL CHECK(rating IN (-1, 1)),
    hook_type    TEXT    NOT NULL DEFAULT 'none',
    clip_type    TEXT    NOT NULL DEFAULT 'unknown',
    start_sec    REAL    NOT NULL DEFAULT 0.0,
    end_sec      REAL    NOT NULL DEFAULT 0.0,
    duration_sec REAL    NOT NULL DEFAULT 0.0,
    rated_at     TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(job_id, part_no),
    FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
)
"""


def _has_fk_to_jobs(cur: sqlite3.Cursor, table: str) -> bool:
    """True iff ``table`` already has a FK pointing at ``jobs``."""
    try:
        rows = cur.execute(f"PRAGMA foreign_key_list({table})").fetchall()
    except sqlite3.OperationalError:
        # Table doesn't exist — caller skips.
        return False
    # PRAGMA foreign_key_list rows: (id, seq, table, from, to, on_update,
    # on_delete, match). Element 2 is the referenced table.
    return any(str(r[2]).lower() == "jobs" for r in rows)


def _table_exists(cur: sqlite3.Cursor, table: str) -> bool:
    row = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _column_names(cur: sqlite3.Cursor, table: str) -> list[str]:
    """Ordered list of column names — used to build the explicit-column
    INSERT INTO ... SELECT so a stray extra column on either side
    surfaces as a SQL error rather than a silent data loss."""
    rows = cur.execute(f"PRAGMA table_info({table})").fetchall()
    return [str(r[1]) for r in rows]


def _migrate_one(
    cur: sqlite3.Cursor,
    table: str,
    new_ddl: str,
    new_temp_name: str,
    extra_indexes: list[str],
) -> dict:
    """Apply the temp-table FK retrofit to one table. Returns a stats dict."""
    if not _table_exists(cur, table):
        return {"skipped": True, "reason": "table_missing"}
    if _has_fk_to_jobs(cur, table):
        return {"skipped": True, "reason": "fk_already_present"}

    # Defensive orphan sweep so the INSERT-with-FK doesn't trip.
    orphan_count = cur.execute(
        f"SELECT COUNT(*) FROM {table} "
        "WHERE job_id NOT IN (SELECT job_id FROM jobs)"
    ).fetchone()[0]
    if orphan_count:
        logger.warning(
            "0003_add_fk_cascade: table=%s deleting %d orphan row(s) "
            "before FK retrofit", table, orphan_count,
        )
        cur.execute(
            f"DELETE FROM {table} "
            "WHERE job_id NOT IN (SELECT job_id FROM jobs)"
        )

    # Re-use the column names from the OLD table so a stale schema
    # (e.g., a DB missing a new column the new DDL added) still copies
    # cleanly. The new table's defaults fill any gaps.
    old_cols = _column_names(cur, table)
    new_table_post_drop = table  # what the temp will be renamed to

    cur.execute(new_ddl)
    col_list = ", ".join(old_cols)
    cur.execute(
        f"INSERT INTO {new_temp_name} ({col_list}) "
        f"SELECT {col_list} FROM {table}"
    )
    cur.execute(f"DROP TABLE {table}")
    cur.execute(f"ALTER TABLE {new_temp_name} RENAME TO {new_table_post_drop}")

    for idx_sql in extra_indexes:
        cur.execute(idx_sql)

    return {"skipped": False, "orphans_deleted": orphan_count}


def up(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()

    # ── job_parts ────────────────────────────────────────────────────
    # No explicit indexes outside the UNIQUE clause (which is recreated
    # by the new CREATE TABLE).
    jp_stats = _migrate_one(
        cur,
        table="job_parts",
        new_ddl=_NEW_JOB_PARTS_DDL,
        new_temp_name="job_parts_new_mt6",
        extra_indexes=[],
    )
    logger.info("0003_add_fk_cascade: job_parts stats=%s", jp_stats)

    # ── clip_feedback ────────────────────────────────────────────────
    # The idx_feedback_channel index was created in init_db; it gets
    # dropped along with the old table, so we re-create it explicitly.
    cf_stats = _migrate_one(
        cur,
        table="clip_feedback",
        new_ddl=_NEW_CLIP_FEEDBACK_DDL,
        new_temp_name="clip_feedback_new_mt6",
        extra_indexes=[
            "CREATE INDEX IF NOT EXISTS idx_feedback_channel "
            "ON clip_feedback(channel_code, goal)",
        ],
    )
    logger.info("0003_add_fk_cascade: clip_feedback stats=%s", cf_stats)
