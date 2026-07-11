"""
story_project_repo.py — Story Studio project persistence (SP1).

A durable store for a Story Studio session (input config + edited StoryPlan v2) so
work survives a reload / app restart. Orthogonal to render jobs — a render never
depends on this table; it only backs the FE "Projects" list / autosave.

All access goes through ``db_conn`` (HTTP path, auto-commit) — the sanctioned
connection helper (Sacred Contract #7). Every function is defensive: logs and
returns a safe default on any DB error (never crashes a request).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.db.connection import db_conn

logger = logging.getLogger("app.db.story_project")

_LIST_COLS = "id, name, language, source, status, created_at, updated_at"
_FULL_COLS = ("id, name, language, source, config_json, plan_json, status, "
              "created_at, updated_at")


def upsert_project(
    project_id: str,
    *,
    name: str = "",
    language: str = "",
    source: str = "",
    config_json: str = "",
    plan_json: str = "",
    status: str = "draft",
) -> bool:
    """Create or update a story project. Returns True on success. Never raises."""
    if not (project_id or "").strip():
        return False
    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO story_projects
                    (id, name, language, source, config_json, plan_json, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    language=excluded.language,
                    source=excluded.source,
                    config_json=excluded.config_json,
                    plan_json=excluded.plan_json,
                    status=excluded.status,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                """,
                (project_id, name, language, source, config_json, plan_json, status),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_project failed id=%s: %s", project_id, exc)
        return False


def _row(row: Any, keys: "tuple[str, ...]") -> dict:
    return dict(zip(keys, row)) if isinstance(row, tuple) else {k: row[k] for k in keys}


_LIST_KEYS = ("id", "name", "language", "source", "status", "created_at", "updated_at")
_FULL_KEYS = ("id", "name", "language", "source", "config_json", "plan_json", "status",
              "created_at", "updated_at")


def list_projects(limit: int = 100) -> list[dict]:
    """Return recent projects (newest first), WITHOUT the heavy config/plan blobs.
    Empty list on error. Never raises."""
    try:
        _lim = max(1, min(500, int(limit)))
        with db_conn() as conn:
            rows = conn.execute(
                f"SELECT {_LIST_COLS} FROM story_projects ORDER BY updated_at DESC LIMIT ?",
                (_lim,),
            ).fetchall()
            return [_row(r, _LIST_KEYS) for r in rows]
    except Exception as exc:
        logger.warning("list_projects failed: %s", exc)
        return []


def get_project(project_id: str) -> Optional[dict]:
    """Return the full project dict (incl. config_json/plan_json), or None. Never raises."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                f"SELECT {_FULL_COLS} FROM story_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            return _row(row, _FULL_KEYS) if row is not None else None
    except Exception as exc:
        logger.warning("get_project failed id=%s: %s", project_id, exc)
        return None


def delete_project(project_id: str) -> bool:
    """Delete a project. Returns True on success. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute("DELETE FROM story_projects WHERE id = ?", (project_id,))
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_project failed id=%s: %s", project_id, exc)
        return False
