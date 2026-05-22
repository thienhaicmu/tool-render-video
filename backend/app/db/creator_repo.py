from app.db.connection import (
    _json_dumps,
    _json_loads,
    get_conn,
)


def get_creator_prefs() -> dict:
    conn = get_conn()
    row = conn.execute("SELECT prefs_json FROM creator_prefs WHERE id = 1").fetchone()
    conn.close()
    if not row:
        return {}
    return _json_loads(row["prefs_json"], default={})


def upsert_creator_prefs(prefs: dict) -> dict:
    conn = get_conn()
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
    conn.close()
    return get_creator_prefs()
