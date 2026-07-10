"""
story_repo.py — Story Mode cross-chapter memory persistence (Story-to-Video P0).

Durable server-side identity for a story series and its canonical characters /
environments / graph, so a character drawn in chapter 1 stays consistent in
chapter 186 (Character DB) and a later chapter can ground on earlier ones
(chapter_summary). Tables: story_series, characters, environments,
relationships, story_timeline, chapter_summary (migrations 0018-0021).

All access goes through ``db_conn`` (HTTP path, auto-commit) — the sanctioned
connection helper the other repos use (Sacred Contract #7). Every function is
defensive: logs and returns a safe default on any DB error (never crashes a
request / render). A one-off chapter uses an empty series_id and never touches
these tables.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.db.connection import db_conn

logger = logging.getLogger("app.db.story")


# ── story_series ─────────────────────────────────────────────────────────────

def upsert_series(
    series_id: str,
    *,
    title: str = "",
    language: str = "",
    art_style: str = "",
    world_setting: str = "",
) -> bool:
    """Create or update a story series. Returns True on success. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO story_series
                    (id, title, language, art_style, world_setting, updated_at)
                VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    language=excluded.language,
                    art_style=excluded.art_style,
                    world_setting=excluded.world_setting,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                """,
                (series_id, title, language, art_style, world_setting),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_series failed id=%s: %s", series_id, exc)
        return False


def _series_row(row: Any) -> dict:
    keys = ("id", "title", "language", "art_style", "world_setting", "created_at", "updated_at")
    return dict(zip(keys, row)) if isinstance(row, tuple) else {k: row[k] for k in keys}


def get_series(series_id: str) -> Optional[dict]:
    """Return the series dict, or None if missing / on error. Never raises."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT id, title, language, art_style, world_setting, created_at, updated_at "
                "FROM story_series WHERE id = ?",
                (series_id,),
            ).fetchone()
            return _series_row(row) if row is not None else None
    except Exception as exc:
        logger.warning("get_series failed id=%s: %s", series_id, exc)
        return None


def list_series(limit: int = 50) -> list[dict]:
    """Return recent series (newest first). Empty list on error. Never raises."""
    try:
        _lim = max(1, min(200, int(limit)))
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT id, title, language, art_style, world_setting, created_at, updated_at "
                "FROM story_series ORDER BY updated_at DESC LIMIT ?",
                (_lim,),
            ).fetchall()
            return [_series_row(r) for r in rows]
    except Exception as exc:
        logger.warning("list_series failed: %s", exc)
        return []


def delete_series(series_id: str) -> bool:
    """Delete a series (FK ON DELETE CASCADE removes its characters/environments/
    graph). Returns True on success. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute("DELETE FROM story_series WHERE id = ?", (series_id,))
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("delete_series failed id=%s: %s", series_id, exc)
        return False


# ── characters ───────────────────────────────────────────────────────────────

def upsert_character(
    char_id: str,
    *,
    series_id: str = "",
    name: str = "",
    canonical_desc: str = "",
    reference_image_path: str = "",
    voice_engine: str = "",
    voice_id: str = "",
    age: str = "",
    gender: str = "",
) -> bool:
    """Create or update a canonical character. Returns True on success. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO characters
                    (id, series_id, name, canonical_desc, reference_image_path,
                     voice_engine, voice_id, age, gender, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    series_id=excluded.series_id,
                    name=excluded.name,
                    canonical_desc=excluded.canonical_desc,
                    reference_image_path=excluded.reference_image_path,
                    voice_engine=excluded.voice_engine,
                    voice_id=excluded.voice_id,
                    age=excluded.age,
                    gender=excluded.gender,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                """,
                (char_id, series_id, name, canonical_desc, reference_image_path,
                 voice_engine, voice_id, age, gender),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_character failed id=%s: %s", char_id, exc)
        return False


def _character_row(row: Any) -> dict:
    keys = ("id", "series_id", "name", "canonical_desc", "reference_image_path",
            "voice_engine", "voice_id", "age", "gender", "created_at", "updated_at")
    return dict(zip(keys, row)) if isinstance(row, tuple) else {k: row[k] for k in keys}


_CHARACTER_COLS = ("id, series_id, name, canonical_desc, reference_image_path, "
                   "voice_engine, voice_id, age, gender, created_at, updated_at")


def list_characters(series_id: str) -> list[dict]:
    """Return all canonical characters for a series. Empty list on error / empty
    series_id. Never raises."""
    if not (series_id or "").strip():
        return []
    try:
        with db_conn() as conn:
            rows = conn.execute(
                f"SELECT {_CHARACTER_COLS} FROM characters WHERE series_id = ? ORDER BY name",
                (series_id,),
            ).fetchall()
            return [_character_row(r) for r in rows]
    except Exception as exc:
        logger.warning("list_characters failed series=%s: %s", series_id, exc)
        return []


def get_character(char_id: str) -> Optional[dict]:
    """Return one character dict, or None. Never raises."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                f"SELECT {_CHARACTER_COLS} FROM characters WHERE id = ?",
                (char_id,),
            ).fetchone()
            return _character_row(row) if row is not None else None
    except Exception as exc:
        logger.warning("get_character failed id=%s: %s", char_id, exc)
        return None


# ── environments ─────────────────────────────────────────────────────────────

def upsert_environment(
    env_id: str,
    *,
    series_id: str = "",
    name: str = "",
    canonical_desc: str = "",
    reference_image_path: str = "",
) -> bool:
    """Create or update a canonical environment. Returns True on success. Never raises."""
    try:
        with db_conn() as conn:
            conn.execute(
                """
                INSERT INTO environments
                    (id, series_id, name, canonical_desc, reference_image_path, updated_at)
                VALUES (?, ?, ?, ?, ?, strftime('%Y-%m-%dT%H:%M:%SZ','now'))
                ON CONFLICT(id) DO UPDATE SET
                    series_id=excluded.series_id,
                    name=excluded.name,
                    canonical_desc=excluded.canonical_desc,
                    reference_image_path=excluded.reference_image_path,
                    updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now')
                """,
                (env_id, series_id, name, canonical_desc, reference_image_path),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("upsert_environment failed id=%s: %s", env_id, exc)
        return False


def _environment_row(row: Any) -> dict:
    keys = ("id", "series_id", "name", "canonical_desc", "reference_image_path",
            "created_at", "updated_at")
    return dict(zip(keys, row)) if isinstance(row, tuple) else {k: row[k] for k in keys}


def list_environments(series_id: str) -> list[dict]:
    """Return all canonical environments for a series. Empty on error / empty
    series_id. Never raises."""
    if not (series_id or "").strip():
        return []
    try:
        with db_conn() as conn:
            rows = conn.execute(
                "SELECT id, series_id, name, canonical_desc, reference_image_path, "
                "created_at, updated_at FROM environments WHERE series_id = ? ORDER BY name",
                (series_id,),
            ).fetchall()
            return [_environment_row(r) for r in rows]
    except Exception as exc:
        logger.warning("list_environments failed series=%s: %s", series_id, exc)
        return []


def get_environment(env_id: str) -> Optional[dict]:
    """Return one environment dict, or None. Never raises."""
    try:
        with db_conn() as conn:
            row = conn.execute(
                "SELECT id, series_id, name, canonical_desc, reference_image_path, "
                "created_at, updated_at FROM environments WHERE id = ?",
                (env_id,),
            ).fetchone()
            return _environment_row(row) if row is not None else None
    except Exception as exc:
        logger.warning("get_environment failed id=%s: %s", env_id, exc)
        return None


# ── chapter_summary (rolling cross-chapter memory) ───────────────────────────

def add_chapter_summary(series_id: str, chapter_no: int, rolling_summary: str) -> bool:
    """Append a chapter's rolling summary. Returns True on success. Never raises."""
    if not (series_id or "").strip():
        return False
    try:
        with db_conn() as conn:
            conn.execute(
                "INSERT INTO chapter_summary (series_id, chapter_no, rolling_summary) "
                "VALUES (?, ?, ?)",
                (series_id, int(chapter_no or 0), rolling_summary or ""),
            )
            conn.commit()
        return True
    except Exception as exc:
        logger.warning("add_chapter_summary failed series=%s ch=%s: %s", series_id, chapter_no, exc)
        return False


def list_chapter_summaries(series_id: str, before_chapter: Optional[int] = None) -> list[dict]:
    """Return prior chapter summaries for a series (oldest first), optionally only
    chapters strictly before ``before_chapter`` (cross-reference context for the
    current chapter). Empty on error / empty series_id. Never raises."""
    if not (series_id or "").strip():
        return []
    try:
        with db_conn() as conn:
            if before_chapter is not None:
                rows = conn.execute(
                    "SELECT chapter_no, rolling_summary, created_at FROM chapter_summary "
                    "WHERE series_id = ? AND chapter_no < ? ORDER BY chapter_no ASC",
                    (series_id, int(before_chapter)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT chapter_no, rolling_summary, created_at FROM chapter_summary "
                    "WHERE series_id = ? ORDER BY chapter_no ASC",
                    (series_id,),
                ).fetchall()
            keys = ("chapter_no", "rolling_summary", "created_at")
            return [dict(zip(keys, r)) if isinstance(r, tuple) else {k: r[k] for k in keys}
                    for r in rows]
    except Exception as exc:
        logger.warning("list_chapter_summaries failed series=%s: %s", series_id, exc)
        return []
