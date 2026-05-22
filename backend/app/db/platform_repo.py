import sqlite3
import uuid

from app.db.connection import (
    _json_dumps,
    _json_loads,
    _utc_now_iso,
    get_conn,
)


def _normalize_proxy_pool_row(row: sqlite3.Row | dict | None):
    if not row:
        return None
    data = dict(row)
    data["metadata"] = _json_loads(data.pop("metadata_json", "{}"), default={})
    try:
        data["port"] = int(data.get("port") or 0)
    except Exception:
        data["port"] = 0
    try:
        data["latency_ms"] = int(data.get("latency_ms") or 0)
    except Exception:
        data["latency_ms"] = 0
    return data


def list_proxy_pool_rows():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM upload_proxy_pool ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [_normalize_proxy_pool_row(r) for r in rows]


def get_proxy_pool_row(proxy_id: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM upload_proxy_pool WHERE proxy_id = ?", (proxy_id,)
    ).fetchone()
    conn.close()
    return _normalize_proxy_pool_row(row)


def create_proxy_pool_row(data: dict):
    proxy_id = str(data.get("proxy_id") or uuid.uuid4())
    now = _utc_now_iso()
    conn = get_conn()
    conn.execute(
        """
        INSERT INTO upload_proxy_pool (
            proxy_id, name, type, host, port, username, password,
            market, status, last_tested_at, last_ok_at, latency_ms,
            last_ip, last_error, notes, metadata_json, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            proxy_id,
            str(data.get("name") or ""),
            str(data.get("type") or "http"),
            str(data.get("host") or ""),
            int(data.get("port") or 0),
            str(data.get("username") or ""),
            str(data.get("password") or ""),
            str(data.get("market") or ""),
            "untested",
            "",
            "",
            0,
            "",
            "",
            str(data.get("notes") or ""),
            _json_dumps(data.get("metadata") or {}),
            now,
            now,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM upload_proxy_pool WHERE proxy_id = ?", (proxy_id,)).fetchone()
    conn.close()
    return _normalize_proxy_pool_row(row)


def update_proxy_pool_row(proxy_id: str, changes: dict):
    allowed = {
        "name", "type", "host", "port", "username", "password", "market",
        "status", "last_tested_at", "last_ok_at", "latency_ms", "last_ip",
        "last_error", "notes", "metadata_json",
    }
    now = _utc_now_iso()
    conn = get_conn()
    current = conn.execute("SELECT * FROM upload_proxy_pool WHERE proxy_id = ?", (proxy_id,)).fetchone()
    if not current:
        conn.close()
        return None
    merged = dict(current)
    for k, v in changes.items():
        if k in allowed:
            merged[k] = v
    if "metadata" in changes:
        merged["metadata_json"] = _json_dumps(changes["metadata"])
    conn.execute(
        """
        UPDATE upload_proxy_pool SET
            name=?, type=?, host=?, port=?, username=?, password=?,
            market=?, status=?, last_tested_at=?, last_ok_at=?,
            latency_ms=?, last_ip=?, last_error=?, notes=?, metadata_json=?, updated_at=?
        WHERE proxy_id=?
        """,
        (
            str(merged.get("name") or ""),
            str(merged.get("type") or "http"),
            str(merged.get("host") or ""),
            int(merged.get("port") or 0),
            str(merged.get("username") or ""),
            str(merged.get("password") or ""),
            str(merged.get("market") or ""),
            str(merged.get("status") or "untested"),
            str(merged.get("last_tested_at") or ""),
            str(merged.get("last_ok_at") or ""),
            int(merged.get("latency_ms") or 0),
            str(merged.get("last_ip") or ""),
            str(merged.get("last_error") or ""),
            str(merged.get("notes") or ""),
            str(merged.get("metadata_json") or "{}"),
            now,
            proxy_id,
        ),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM upload_proxy_pool WHERE proxy_id = ?", (proxy_id,)).fetchone()
    conn.close()
    return _normalize_proxy_pool_row(row)


def delete_proxy_pool_row(proxy_id: str) -> bool:
    conn = get_conn()
    cur = conn.execute("DELETE FROM upload_proxy_pool WHERE proxy_id = ?", (proxy_id,))
    conn.commit()
    conn.close()
    return cur.rowcount > 0
