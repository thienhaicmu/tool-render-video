"""Admin / diagnostics endpoints (audit FINDING-A03 utility bucket).

All four endpoints are read-mostly and have no FE callers today (per
Phase 6 audit FINDING-API07). They are kept so a future Settings /
Maintenance UI can wire them up; deleting them now would require an
explicit product decision.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter

router = APIRouter(tags=["render"])
logger = logging.getLogger("app.render")


@router.get("/queue-status")
def get_queue_status():
    """Read-only — returns active render count and max concurrent slots."""
    from app.features.render.engine.pipeline.render_pipeline import (
        _JOB_SEM_VALUE,
        _render_active_count,
        _render_active_lock,
    )
    with _render_active_lock:
        active = _render_active_count[0]
    return {"active_renders": active, "max_renders": _JOB_SEM_VALUE}


@router.get("/system-info")
def get_system_info():
    """Read-only system snapshot for the Settings screen.

    Returns cache sizes, job counts, and runtime config. Never mutates state.
    """
    from app.core.config import APP_DATA_DIR, DATABASE_PATH
    from app.db.jobs_repo import list_jobs
    def _dir_size_mb(path: Path) -> float:
        try:
            total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            return round(total / 1_048_576, 1)
        except Exception:
            return 0.0

    def _file_size_mb(path: Path) -> float:
        try:
            return round(path.stat().st_size / 1_048_576, 1) if path.exists() else 0.0
        except Exception:
            return 0.0

    cache_dir = APP_DATA_DIR / "cache"
    cache_subdirs: dict[str, float] = {}
    if cache_dir.exists():
        for sub in cache_dir.iterdir():
            if sub.is_dir():
                cache_subdirs[sub.name] = _dir_size_mb(sub)

    try:
        jobs = list_jobs()
        total_jobs     = len(jobs)
        completed_jobs = sum(1 for j in jobs if j.get("status") in ("completed", "completed_with_errors"))
        failed_jobs    = sum(1 for j in jobs if j.get("status") == "failed")
        active_jobs    = sum(1 for j in jobs if j.get("status") in ("running", "queued", "cancelling"))
    except Exception:
        total_jobs = completed_jobs = failed_jobs = active_jobs = 0

    return {
        "cache": {
            "total_mb":   round(sum(cache_subdirs.values()), 1),
            "subdirs":    cache_subdirs,
            "cache_dir":  str(cache_dir),
        },
        "database": {
            "path":    str(DATABASE_PATH),
            "size_mb": _file_size_mb(DATABASE_PATH),
        },
        "jobs": {
            "total":     total_jobs,
            "completed": completed_jobs,
            "failed":    failed_jobs,
            "active":    active_jobs,
        },
    }


@router.post("/cache/clear")
def clear_render_cache():
    """Delete all files under APP_DATA_DIR/cache. Non-destructive to job records."""
    from app.core.config import APP_DATA_DIR
    cache_dir = APP_DATA_DIR / "cache"
    deleted = 0
    freed_mb = 0.0
    if cache_dir.exists():
        for f in cache_dir.rglob("*"):
            if f.is_file():
                try:
                    freed_mb += f.stat().st_size / 1_048_576
                    f.unlink()
                    deleted += 1
                except Exception:
                    pass
    return {"deleted_files": deleted, "freed_mb": round(freed_mb, 1)}


@router.get("/ai-diagnostics")
def get_ai_diagnostics():
    """Read-only AI runtime diagnostics.

    Returns dependency availability, embedding readiness, vector store mode,
    and SQLite memory health. Never loads models. Never triggers embeddings.
    """
    try:
        from app.features.render.ai.diagnostics import get_ai_runtime_diagnostics
        return get_ai_runtime_diagnostics()
    except Exception as exc:
        logger.debug("ai_diagnostics_endpoint_error: %s", exc)
        return {"startup_safe": True, "error": "diagnostics_unavailable"}
