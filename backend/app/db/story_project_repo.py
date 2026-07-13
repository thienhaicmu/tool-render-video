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
    """Return recent LIVE projects (newest first), WITHOUT the heavy config/plan blobs.
    Soft-deleted (trashed) projects are excluded. Empty list on error. Never raises."""
    try:
        _lim = max(1, min(500, int(limit)))
        with db_conn() as conn:
            rows = conn.execute(
                f"SELECT {_LIST_COLS} FROM story_projects "
                "WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT ?",
                (_lim,),
            ).fetchall()
            return [_row(r, _LIST_KEYS) for r in rows]
    except Exception as exc:
        logger.warning("list_projects failed: %s", exc)
        return []


def list_trashed_projects(limit: int = 100) -> list[dict]:
    """Return soft-deleted projects (newest-deleted first). Empty on error. Never raises."""
    try:
        _lim = max(1, min(500, int(limit)))
        with db_conn() as conn:
            rows = conn.execute(
                f"SELECT {_LIST_COLS} FROM story_projects "
                "WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT ?",
                (_lim,),
            ).fetchall()
            return [_row(r, _LIST_KEYS) for r in rows]
    except Exception as exc:
        logger.warning("list_trashed_projects failed: %s", exc)
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
    """SOFT-delete a project (move to trash: set deleted_at). Restorable via
    restore_project; hard-removed via purge_project. Returns True. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute(
                "UPDATE story_projects SET deleted_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
                "WHERE id = ?",
                (project_id,),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_project failed id=%s: %s", project_id, exc)
        return False


def restore_project(project_id: str) -> bool:
    """Restore a soft-deleted project (clear deleted_at). Returns True. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute("UPDATE story_projects SET deleted_at = NULL WHERE id = ?", (project_id,))
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("restore_project failed id=%s: %s", project_id, exc)
        return False


def purge_project(project_id: str) -> bool:
    """HARD-delete a project and all its versions (empty-trash). Returns True. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute("DELETE FROM story_project_versions WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM story_projects WHERE id = ?", (project_id,))
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("purge_project failed id=%s: %s", project_id, exc)
        return False


# ── story_project_versions (version history) ─────────────────────────────────

_VERSION_LIST_KEYS = ("id", "project_id", "label", "created_at")
_VERSION_FULL_KEYS = ("id", "project_id", "label", "plan_json", "config_json", "created_at")


def save_version(project_id: str, *, label: str = "", plan_json: str = "", config_json: str = "") -> str:
    """Snapshot a project's current plan+config as a version. Returns the new version id
    ("" on error / empty project_id). Never raises."""
    import uuid as _uuid
    if not (project_id or "").strip():
        return ""
    vid = _uuid.uuid4().hex
    try:
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO story_project_versions (id, project_id, label, plan_json, config_json) "
                "VALUES (?, ?, ?, ?, ?)",
                (vid, project_id, label, plan_json, config_json),
            )
            conn.commit()
        return vid
    except Exception as exc:
        logger.warning("save_version failed project=%s: %s", project_id, exc)
        return ""


def list_versions(project_id: str, limit: int = 50) -> list[dict]:
    """Return a project's versions (newest first), WITHOUT the heavy blobs. Never raises."""
    try:
        _lim = max(1, min(200, int(limit)))
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT id, project_id, label, created_at FROM story_project_versions "
                "WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, _lim),
            ).fetchall()
            return [_row(r, _VERSION_LIST_KEYS) for r in rows]
    except Exception as exc:
        logger.warning("list_versions failed project=%s: %s", project_id, exc)
        return []


def get_version(version_id: str) -> Optional[dict]:
    """Return one version (incl. plan_json/config_json), or None. Never raises."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT id, project_id, label, plan_json, config_json, created_at "
                "FROM story_project_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
            return _row(row, _VERSION_FULL_KEYS) if row is not None else None
    except Exception as exc:
        logger.warning("get_version failed id=%s: %s", version_id, exc)
        return None


# ── Retention (F-DB1) ─────────────────────────────────────────────────────────

def prune_trashed_projects(max_age_days: int) -> dict:
    """Empty-trash retention: HARD-delete soft-deleted projects whose ``deleted_at`` is
    older than ``max_age_days`` (and their versions). ``max_age_days <= 0`` → disabled
    (no-op). LIVE projects are never touched. Returns ``{pruned, versions}``. Never raises.

    Only ever removes rows the user already trashed — this just auto-empties old trash so
    the authoring store doesn't grow unbounded."""
    if int(max_age_days or 0) <= 0:
        return {"pruned": 0, "versions": 0}
    try:
        with db_conn() as conn:
            cutoff = f"-{int(max_age_days)} days"
            ids = [r[0] if isinstance(r, tuple) else r["id"] for r in conn.execute(
                "SELECT id FROM story_projects WHERE deleted_at IS NOT NULL "
                "AND deleted_at < strftime('%Y-%m-%dT%H:%M:%SZ','now',?)", (cutoff,)).fetchall()]
            vers = 0
            for pid in ids:
                cur = conn.execute("DELETE FROM story_project_versions WHERE project_id = ?", (pid,))
                vers += int(getattr(cur, "rowcount", 0) or 0)
            if ids:
                conn.executemany("DELETE FROM story_projects WHERE id = ?", [(i,) for i in ids])
            conn.commit()
        if ids:
            logger.info("prune_trashed_projects: removed %d trashed project(s) + %d version(s) (>%dd)",
                        len(ids), vers, max_age_days)
        return {"pruned": len(ids), "versions": vers}
    except Exception as exc:
        logger.warning("prune_trashed_projects failed (non-fatal): %s", exc)
        return {"pruned": 0, "versions": 0}
