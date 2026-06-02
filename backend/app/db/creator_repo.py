"""creator_repo.py — singleton creator_prefs row CRUD.

Sprint 5.3 (audit 2026-06-02 P2-D9): migrated from raw get_conn() + manual
close to db_conn() context manager. Same exception-safety guarantee that
jobs_repo.py has had. After Sprint 5.4 db_conn() also auto-commits/
rollbacks, so explicit conn.commit() here is redundant — left in place
for the cleanup pass in a follow-up sprint.
"""
from app.db.connection import (
    _json_dumps,
    _json_loads,
    db_conn,
)


def get_creator_prefs() -> dict:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT prefs_json FROM creator_prefs WHERE id = 1"
        ).fetchone()
    if not row:
        return {}
    return _json_loads(row["prefs_json"], default={})


def upsert_creator_prefs(prefs: dict) -> dict:
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO creator_prefs (id, prefs_json, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                prefs_json = excluded.prefs_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (_json_dumps(prefs),),
        )
        conn.commit()
    return get_creator_prefs()
