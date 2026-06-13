"""assets_repo.py — assets table CRUD.

Phase C — Asset Library. Uses db_conn() context manager (HTTP path,
auto-commit on normal exit, rollback on exception). Follows the same
pattern as download_repo.py / creator_repo.py.

Deduplication contract: upsert_asset() treats `file_path` as the
deduplication key — if a row with the same file_path already exists
the existing asset_id is returned and no data is overwritten. This
prevents double-registration when a user re-downloads the same video
or renders a file that was already enriched.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.db.connection import _utc_now_iso, db_conn
from app.domain.asset import Asset

logger = logging.getLogger("app.db.assets_repo")


def upsert_asset(asset_id: str, file_path: str, original_url: str = "", title: str = "") -> str:
    """Insert a new asset row or return the existing asset_id for this file_path.

    Returns the asset_id that should be used — either the newly created one
    or the pre-existing one for the same file_path.
    """
    with db_conn() as conn:
        row = conn.execute(
            "SELECT asset_id FROM assets WHERE file_path = ?", (file_path,)
        ).fetchone()
        if row:
            return str(row["asset_id"])
        conn.execute(
            """
            INSERT INTO assets (asset_id, file_path, original_url, title, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (asset_id, file_path, original_url or "", title or "", _utc_now_iso()),
        )
        conn.commit()
    return asset_id


def update_asset_enrichment(
    asset_id: str,
    duration_sec: float = 0.0,
    width: int = 0,
    height: int = 0,
    fps: float = 0.0,
    file_size_bytes: int = 0,
    language: str = "",
    content_type: str = "",
    transcription_cache_path: Optional[str] = None,
    thumbnail_path: Optional[str] = None,
) -> None:
    """Write enrichment fields after ffprobe / Whisper / thumbnail pass."""
    with db_conn() as conn:
        conn.execute(
            """
            UPDATE assets SET
                duration_sec             = ?,
                width                    = ?,
                height                   = ?,
                fps                      = ?,
                file_size_bytes          = ?,
                language                 = ?,
                content_type             = ?,
                transcription_cache_path = ?,
                thumbnail_path           = ?,
                enriched_at              = ?
            WHERE asset_id = ?
            """,
            (
                duration_sec, width, height, fps, file_size_bytes,
                language or "", content_type or "",
                transcription_cache_path, thumbnail_path,
                _utc_now_iso(),
                asset_id,
            ),
        )
        conn.commit()


def get_asset(asset_id: str) -> Optional[Asset]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
        ).fetchone()
    return Asset.from_row(dict(row)) if row else None


def get_asset_by_path(file_path: str) -> Optional[Asset]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM assets WHERE file_path = ?", (file_path,)
        ).fetchone()
    return Asset.from_row(dict(row)) if row else None


def list_assets(
    limit: int = 100,
    offset: int = 0,
    *,
    content_type: str = "",
    language: str = "",
    min_duration: float = 0.0,
    max_duration: float = 0.0,
    q: str = "",
) -> list[Asset]:
    """Return assets matching the optional filter params, newest first.

    Phase Q: content_type, language, min_duration, max_duration, q (title LIKE search).
    All filters are optional; omitting them returns all assets (original behaviour).
    """
    where: list[str] = []
    params: list = []

    if content_type.strip():
        where.append("content_type = ?")
        params.append(content_type.strip())

    if language.strip():
        where.append("language = ?")
        params.append(language.strip())

    if min_duration > 0:
        where.append("duration_sec >= ?")
        params.append(min_duration)

    if max_duration > 0:
        where.append("duration_sec <= ?")
        params.append(max_duration)

    if q.strip():
        where.append("title LIKE ?")
        params.append(f"%{q.strip()}%")

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.extend([limit, offset])

    with db_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM assets {where_sql} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params,
        ).fetchall()
    return [Asset.from_row(dict(r)) for r in rows]


def delete_asset(asset_id: str) -> None:
    with db_conn() as conn:
        conn.execute("DELETE FROM assets WHERE asset_id = ?", (asset_id,))
        conn.commit()
