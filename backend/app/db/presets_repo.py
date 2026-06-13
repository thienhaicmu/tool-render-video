"""presets_repo.py — render_presets table CRUD.

Phase E — Smart Render Presets. Uses db_conn() context manager,
same pattern as assets_repo.py / download_repo.py.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from app.db.connection import _utc_now_iso, db_conn
from app.domain.render_preset import PRESET_ALLOWED_PARAMS, RenderPreset

logger = logging.getLogger("app.db.presets_repo")


def upsert_preset(
    preset_id: str,
    name: str,
    params: dict,
    *,
    description: str = "",
    channel_code: str = "",
    platform: str = "",
    is_builtin: bool = False,
) -> None:
    """Insert or replace a preset row. Used by the seeder for built-ins."""
    safe_params = {k: v for k, v in (params or {}).items() if k in PRESET_ALLOWED_PARAMS}
    params_json = json.dumps(safe_params, sort_keys=True)
    now = _utc_now_iso()
    with db_conn() as conn:
        conn.execute(
            """
            INSERT INTO render_presets
                (preset_id, name, description, channel_code, platform,
                 params_json, is_builtin, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(preset_id) DO UPDATE SET
                name         = excluded.name,
                description  = excluded.description,
                params_json  = excluded.params_json,
                updated_at   = excluded.updated_at
            """,
            (
                preset_id, name, description or "", channel_code or "",
                platform or "", params_json, int(is_builtin), now, now,
            ),
        )
        conn.commit()


def create_preset(
    preset_id: str,
    name: str,
    params: dict,
    *,
    description: str = "",
    channel_code: str = "",
    platform: str = "",
) -> None:
    """Create a new custom preset. is_builtin is always False here."""
    upsert_preset(
        preset_id=preset_id,
        name=name,
        params=params,
        description=description,
        channel_code=channel_code,
        platform=platform,
        is_builtin=False,
    )


def update_preset(preset_id: str, name: str, params: dict, description: str = "") -> bool:
    """Update a custom preset. Returns False if not found or is_builtin."""
    preset = get_preset(preset_id)
    if preset is None:
        return False
    if preset.is_builtin:
        return False
    safe_params = {k: v for k, v in (params or {}).items() if k in PRESET_ALLOWED_PARAMS}
    params_json = json.dumps(safe_params, sort_keys=True)
    with db_conn() as conn:
        conn.execute(
            """
            UPDATE render_presets
            SET name = ?, description = ?, params_json = ?, updated_at = ?
            WHERE preset_id = ?
            """,
            (name, description or "", params_json, _utc_now_iso(), preset_id),
        )
        conn.commit()
    return True


def get_preset(preset_id: str) -> Optional[RenderPreset]:
    with db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM render_presets WHERE preset_id = ?", (preset_id,)
        ).fetchone()
    return RenderPreset.from_row(dict(row)) if row else None


def list_presets(platform: str = "", channel_code: str = "") -> list[RenderPreset]:
    """Return all matching presets — built-ins first, then custom, newest last."""
    with db_conn() as conn:
        if platform and channel_code:
            rows = conn.execute(
                """
                SELECT * FROM render_presets
                WHERE (platform = ? OR platform = '')
                  AND (channel_code = ? OR channel_code = '')
                ORDER BY is_builtin DESC, created_at ASC
                """,
                (platform, channel_code),
            ).fetchall()
        elif platform:
            rows = conn.execute(
                """
                SELECT * FROM render_presets
                WHERE platform = ? OR platform = ''
                ORDER BY is_builtin DESC, created_at ASC
                """,
                (platform,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM render_presets ORDER BY is_builtin DESC, created_at ASC"
            ).fetchall()
    return [RenderPreset.from_row(dict(r)) for r in rows]


def delete_preset(preset_id: str) -> bool:
    """Delete a custom preset. Returns False if not found or is_builtin."""
    preset = get_preset(preset_id)
    if preset is None:
        return False
    if preset.is_builtin:
        return False
    with db_conn() as conn:
        conn.execute("DELETE FROM render_presets WHERE preset_id = ?", (preset_id,))
        conn.commit()
    return True
