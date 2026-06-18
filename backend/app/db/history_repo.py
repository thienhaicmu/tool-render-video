"""History/reset helpers — clear job + download + asset history in one
transaction while preserving settings, presets, and migration state.

Additive-only per the DB rules: uses ``DELETE FROM`` (never DROP/TRUNCATE)
through the sanctioned ``db_conn`` context manager, so schema and WAL mode
are untouched. ``schema_versions``, ``creator_prefs``,
``creator_prefs_channel``, ``render_presets`` are NEVER cleared.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("app.db")

# History/runtime tables cleared by clear_history(). Order is child→parent so
# the delete works even if FK enforcement is on. Tables absent from a given DB
# are skipped. NOT listed (deliberately preserved): schema_versions,
# creator_prefs, creator_prefs_channel, render_presets.
_HISTORY_TABLES = (
    "clip_feedback",
    "job_parts",
    "render_ab_scores",
    "platform_metrics",
    "assets",
    "download_jobs",
    "jobs",
)


def clear_history(*, preserve_active: bool = True) -> dict:
    """Delete all job/download/asset history rows.

    When ``preserve_active`` is True (default), render jobs still
    ``running``/``queued`` and downloads still ``queued``/``downloading`` are
    kept (and their ``job_parts``) so an in-flight job is never orphaned —
    Sacred Contract #7. Returns a ``{table: rows_deleted}`` dict. Never
    raises; rolls back the whole transaction on any error and returns
    ``{}``.
    """
    try:
        from app.db.connection import db_conn
        counts: dict[str, int] = {}
        with db_conn() as conn:
            existing = {
                r[0] if isinstance(r, tuple) else r["name"]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            active_jobs: list[str] = []
            if preserve_active and "jobs" in existing:
                active_jobs = [
                    r[0] if isinstance(r, tuple) else r["job_id"]
                    for r in conn.execute(
                        "SELECT job_id FROM jobs WHERE status IN ('running','queued')"
                    ).fetchall()
                ]

            keep_ph = ",".join("?" * len(active_jobs)) if active_jobs else ""

            for table in _HISTORY_TABLES:
                if table not in existing:
                    continue
                if table in ("jobs", "job_parts") and active_jobs:
                    sql = f"DELETE FROM {table} WHERE job_id NOT IN ({keep_ph})"
                    params: tuple = tuple(active_jobs)
                elif table == "download_jobs" and preserve_active:
                    sql = "DELETE FROM download_jobs WHERE status NOT IN ('queued','downloading')"
                    params = ()
                else:
                    sql = f"DELETE FROM {table}"
                    params = ()
                counts[table] = conn.execute(sql, params).rowcount or 0
            conn.commit()
    except Exception as exc:
        logger.warning("clear_history failed (non-fatal): %s", exc)
        return {}

    total = sum(counts.values())
    logger.info(
        "clear_history: deleted %d rows across %d tables (preserve_active=%s) %s",
        total, len(counts), preserve_active, counts,
    )
    return counts
