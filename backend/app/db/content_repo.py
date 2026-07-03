"""
content_repo.py — Content Studio project (draft) persistence (CU-1).

A ``content_projects`` row is the durable server-side identity of a Content
Studio project: script + the (editable) ContentPlan JSON + the studio config +
status. The FE autosaves it so a draft survives reloads and can be reopened.

All access goes through ``db_conn`` (HTTP path, auto-commit) — the same
sanctioned connection helper the other repos use. Every function is defensive:
it logs and returns a safe default on any DB error (never crashes a request).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.db.connection import db_conn

logger = logging.getLogger("app.db.content")


def upsert_content_project(
    project_id: str,
    *,
    title: str = "",
    script: str = "",
    plan_json: Optional[str] = None,
    config_json: Optional[str] = None,
    status: str = "draft",
    last_job_id: str = "",
) -> bool:
    """Create or update a content project (autosave). Returns True on success.
    Never raises."""
    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO content_projects
                    (id, title, script, plan_json, config_json, status, last_job_id, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    script=excluded.script,
                    plan_json=excluded.plan_json,
                    config_json=excluded.config_json,
                    status=excluded.status,
                    last_job_id=excluded.last_job_id,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                """,
                (project_id, title, script, plan_json, config_json, status, last_job_id),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_content_project failed id=%s: %s", project_id, exc)
        return False


def _row_to_dict(row: Any) -> dict:
    keys = ("id", "title", "script", "plan_json", "config_json", "status",
            "last_job_id", "created_at", "updated_at")
    if isinstance(row, tuple):
        return dict(zip(keys, row))
    return {k: row[k] for k in keys}


def get_content_project(project_id: str) -> Optional[dict]:
    """Return the project dict, or None if missing / on error. Never raises."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT id, title, script, plan_json, config_json, status, "
                "last_job_id, created_at, updated_at FROM content_projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            return _row_to_dict(row) if row is not None else None
    except Exception as exc:
        logger.warning("get_content_project failed id=%s: %s", project_id, exc)
        return None


def list_content_projects(limit: int = 50) -> list[dict]:
    """Return recent projects (newest first). Empty list on error. Never raises."""
    try:
        _lim = max(1, min(200, int(limit)))
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT id, title, script, plan_json, config_json, status, "
                "last_job_id, created_at, updated_at FROM content_projects "
                "ORDER BY updated_at DESC LIMIT ?",
                (_lim,),
            ).fetchall()
            return [_row_to_dict(r) for r in rows]
    except Exception as exc:
        logger.warning("list_content_projects failed: %s", exc)
        return []


def delete_content_project(project_id: str) -> bool:
    """Delete a project. Returns True on success. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute("DELETE FROM content_projects WHERE id = ?", (project_id,))
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_content_project failed id=%s: %s", project_id, exc)
        return False
