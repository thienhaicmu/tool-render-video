"""catalog_repo.py — asset_catalog table CRUD.

Follows the same db_conn() context-manager pattern as download_repo.py.
All mutations go through explicit allowlists to prevent arbitrary field
injection. CatalogService owns the state-machine logic; this module is
a dumb data accessor.
"""
from __future__ import annotations

from typing import Any

from app.db.connection import _utc_now_iso, db_conn

_UPDATABLE_FIELDS = frozenset({
    "status",
    "storage_tier",
    "storage_path",
    "filename",
    "filesize",
    "title",
    "duration",
    "height",
    "fps",
    "thumbnail_url",
    "error_msg",
    "download_job_id",
    "meta_json",
    "expires_at",
    "archived_at",
    "deleted_at",
})


def create_asset(
    asset_id: str,
    dedup_key: str,
    url: str,
    platform: str = "",
    quality: str = "best",
) -> None:
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO asset_catalog
                (asset_id, dedup_key, url, platform, quality, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (asset_id, dedup_key, url, platform, quality, _utc_now_iso(), _utc_now_iso()),
        )
        conn.commit()


def get_asset_by_id(asset_id: str) -> dict | None:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM asset_catalog WHERE asset_id = ?", (asset_id,)
        ).fetchone()
    return dict(row) if row else None


def get_asset_by_dedup_key(dedup_key: str) -> dict | None:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM asset_catalog WHERE dedup_key = ?", (dedup_key,)
        ).fetchone()
    return dict(row) if row else None


def update_asset(asset_id: str, **fields: Any) -> None:
    updates = {k: v for k, v in fields.items() if k in _UPDATABLE_FIELDS}
    if not updates:
        return
    updates["updated_at"] = _utc_now_iso()
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [asset_id]
    with db_conn() as conn:
        conn.execute(f"UPDATE asset_catalog SET {cols} WHERE asset_id = ?", vals)
        conn.commit()


def increment_ref_count(asset_id: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "UPDATE asset_catalog SET ref_count = ref_count + 1, updated_at = ? "
            "WHERE asset_id = ?",
            (_utc_now_iso(), asset_id),
        )
        conn.commit()


def decrement_ref_count(asset_id: str) -> None:
    with db_conn() as conn:
        conn.execute(
            "UPDATE asset_catalog SET ref_count = MAX(0, ref_count - 1), updated_at = ? "
            "WHERE asset_id = ?",
            (_utc_now_iso(), asset_id),
        )
        conn.commit()


def list_assets(status: str | None = None, limit: int = 100) -> list[dict]:
    with db_conn() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM asset_catalog WHERE status = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (status, min(limit, 500)),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM asset_catalog ORDER BY created_at DESC LIMIT ?",
                (min(limit, 500),),
            ).fetchall()
    return [dict(r) for r in rows]


def get_expired_assets(max_age_days: int) -> list[dict]:
    """Return assets whose expires_at is set and in the past."""
    if max_age_days <= 0:
        return []
    with db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM asset_catalog "
            "WHERE expires_at IS NOT NULL "
            f"AND expires_at < datetime('now', '-{max_age_days} days') "
            "AND status NOT IN ('deleted')"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_asset_record(asset_id: str) -> None:
    with db_conn() as conn:
        conn.execute("DELETE FROM asset_catalog WHERE asset_id = ?", (asset_id,))
        conn.commit()
