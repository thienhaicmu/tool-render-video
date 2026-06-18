from __future__ import annotations

import logging
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("app.maintenance")

# Matches standard UUID4 format used for job_id values.
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)
_ACTIVE_STATUSES = frozenset({"running", "queued"})


def prune_preview_dirs(temp_dir: Path, max_age_hours: int = 6):
    """Remove stale preview session dirs older than max_age_hours."""
    preview_root = temp_dir / "preview"
    if not preview_root.exists():
        return {"removed": 0, "kept": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    removed = kept = 0
    for d in preview_root.iterdir():
        if not d.is_dir():
            continue
        try:
            mtime = datetime.fromtimestamp(d.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
                logger.info("maintenance: removed stale preview dir %s (age > %dh)", d.name, max_age_hours)
                removed += 1
            else:
                kept += 1
        except Exception:
            pass
    return {"removed": removed, "kept": kept}


def prune_render_temp_dirs(temp_dir: Path) -> dict:
    """Remove render temp dirs for non-active jobs.

    Scans TEMP_DIR for UUID-named subdirectories (one per job). Skips dirs for
    jobs that are still running or queued. Deletes dirs for finished, failed,
    cancelled, or orphaned jobs (not found in DB).

    Directories whose names are NOT UUID-format (e.g. preview/, downloads/, tmp/)
    are always left untouched.
    """
    from app.db.jobs_repo import get_job
    removed = kept = skipped = 0
    if not temp_dir.exists():
        return {"removed": removed, "kept": kept, "skipped": skipped}
    for d in temp_dir.iterdir():
        if not d.is_dir():
            continue
        if not _UUID_RE.match(d.name):
            skipped += 1
            continue
        job = get_job(d.name)
        if job and str(job.get("status") or "").lower() in _ACTIVE_STATUSES:
            kept += 1  # active job — never touch its work dir
            continue
        try:
            shutil.rmtree(d, ignore_errors=True)
            logger.info("maintenance: removed render temp dir job_id=%s", d.name)
            removed += 1
        except Exception as exc:
            logger.warning("maintenance: failed to remove render temp dir job_id=%s: %s", d.name, exc)
            kept += 1
    return {"removed": removed, "kept": kept, "skipped": skipped}


def prune_render_cache(cache_dir: Path, max_age_hours: int = 72) -> dict:
    """Remove cache files older than max_age_hours from cache_dir and its subdirs.

    Sprint 5.2 (audit 2026-06-02 P2-D2): pipeline_cache.py only evicts entries
    on read access. Sources that are never re-accessed (most one-off renders)
    accumulate forever. This prune walks every subdirectory of the cache root
    (scene_detect, transcription, segment_scores, plus any future addition)
    and removes individual files older than the deadline.

    Per-file try/except so one bad file doesn't abort the whole prune. Per-
    subdir try/except so an unreadable subdir doesn't kill the loop. Returns
    {removed, kept, freed_bytes} for visibility in the startup + periodic log.

    Sprint 6 P1 (this commit): added freed_bytes to the return dict + log
    line. Size is read before unlink so the metric reflects what was
    actually freed rather than relying on a post-hoc stat (which would
    fail after unlink).
    """
    if not cache_dir.exists():
        return {"removed": 0, "kept": 0, "freed_bytes": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    removed = kept = 0
    freed_bytes = 0
    for subdir in cache_dir.iterdir():
        if not subdir.is_dir():
            continue
        try:
            for f in subdir.iterdir():
                if not f.is_file():
                    continue
                # Audit FINDING-BR14 closure (Batch 10F 2026-06-06):
                # never touch a ".tmp" sidecar. pipeline_cache writes
                # atomically via "<key>.json.tmp" → os.replace into the
                # final name; deleting the tmp file mid-write makes the
                # writer's flush either fail (Windows sharing violation)
                # or write into an orphaned inode (POSIX). The tmp file
                # is by definition fresh, so we'd never legitimately
                # match the cutoff anyway — this is belt-and-suspenders.
                if f.suffix == ".tmp":
                    continue
                try:
                    st = f.stat()
                    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
                    if mtime < cutoff:
                        # Capture size BEFORE unlink — once the file is gone
                        # we can't stat() it any more.
                        size = st.st_size
                        f.unlink(missing_ok=True)
                        removed += 1
                        freed_bytes += size
                    else:
                        kept += 1
                except Exception:
                    pass
        except Exception:
            pass
    if removed:
        logger.info(
            "maintenance: pruned %d stale render cache files (>%dh old, freed=%.1f MB) from %s",
            removed, max_age_hours, freed_bytes / (1024 * 1024), cache_dir,
        )
    return {"removed": removed, "kept": kept, "freed_bytes": freed_bytes}


def clear_all_cache(cache_dir: Path) -> dict:
    """Remove ALL cache files (every subdir, any age) — the 'clear cache'
    side of the reset/clear-history feature. Mirrors prune_render_cache's
    defensive per-file/per-subdir try/except and skips ``.tmp`` sidecars so a
    concurrent atomic cache write isn't corrupted. Returns
    {removed, freed_bytes}. Never raises."""
    if not cache_dir.exists():
        return {"removed": 0, "freed_bytes": 0}
    removed = 0
    freed_bytes = 0
    for subdir in cache_dir.iterdir():
        if not subdir.is_dir():
            continue
        try:
            for f in subdir.iterdir():
                if not f.is_file() or f.suffix == ".tmp":
                    continue
                try:
                    size = f.stat().st_size
                    f.unlink(missing_ok=True)
                    removed += 1
                    freed_bytes += size
                except Exception:
                    pass
        except Exception:
            pass
    logger.info(
        "maintenance: cleared %d cache files (freed=%.1f MB) from %s",
        removed, freed_bytes / (1024 * 1024), cache_dir,
    )
    return {"removed": removed, "freed_bytes": freed_bytes}


def prune_xtts_cache(temp_dir: Path, max_age_days: int = 30) -> dict:
    """Remove stale XTTS synthesis cache MP3 files older than max_age_days.

    Sprint 6 P0-1 (per docs/review/TEMP_FILE_AUDIT_2026-06-04.md S-5):
    services/tts_xtts_adapter.py:161 maintains a hash-keyed MP3 cache at
    `TEMP_DIR/xtts_cache/` with no eviction. Identical synthesis is
    rare in practice (text + language + gender + content_type), so the
    cache grows unbounded — ~40-50 MB per unique synthesis × cumulative
    usage. This prune runs in the same scheduler tick as
    prune_render_cache, on a longer TTL (30d default) since hits do save
    real GPU time.

    Per-file try/except so one bad file doesn't abort. Returns
    {removed, kept} for startup-log visibility. Idempotent if the dir
    doesn't exist yet.
    """
    cache_root = temp_dir / "xtts_cache"
    if not cache_root.exists():
        return {"removed": 0, "kept": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    removed = kept = 0
    try:
        for f in cache_root.iterdir():
            if not f.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    f.unlink(missing_ok=True)
                    removed += 1
                else:
                    kept += 1
            except Exception:
                pass
    except Exception as exc:
        logger.warning("maintenance: failed to scan xtts_cache: %s", exc)
    if removed:
        logger.info(
            "maintenance: pruned %d stale xtts_cache files (>%dd old) from %s",
            removed, max_age_days, cache_root,
        )
    return {"removed": removed, "kept": kept}


def prune_text_overlay_dir(overlay_dir: Path, max_age_days: int = 7) -> dict:
    """Remove stale text-overlay drawtext txt files older than max_age_days.

    Sprint 6 P0-2 (per docs/review/TEMP_FILE_AUDIT_2026-06-04.md S-7):
    services/text_overlay.py:_write_textfile_for_drawtext writes one
    deterministic-named txt file per layer per render under
    `data/temp/text_overlays/` (or fallback tmpdir) and never cleans up.
    Hash-keyed names mean files repeat across renders of the same
    overlay config — useful for FFmpeg drawtext but a leak otherwise.

    7-day TTL keeps the cache useful for users who re-render the same
    overlay config across a few days while preventing long-term
    accumulation. Returns {removed, kept}.
    """
    if not overlay_dir.exists():
        return {"removed": 0, "kept": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    removed = kept = 0
    try:
        for f in overlay_dir.iterdir():
            if not f.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    f.unlink(missing_ok=True)
                    removed += 1
                else:
                    kept += 1
            except Exception:
                pass
    except Exception as exc:
        logger.warning("maintenance: failed to scan text_overlay dir: %s", exc)
    if removed:
        logger.info(
            "maintenance: pruned %d stale text_overlay files (>%dd old) from %s",
            removed, max_age_days, overlay_dir,
        )
    return {"removed": removed, "kept": kept}


# Job statuses that are safe to prune. Active states are excluded so a
# pathological clock skew or paused job can never be deleted out from under
# the render thread. "interrupted" is included because the recovery loop in
# main.py marks it back to running on startup if recoverable — older
# interrupted rows past the retention window are dead.
_PRUNABLE_JOB_STATUSES = (
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
    "interrupted",
)


def prune_old_jobs(max_age_days: int) -> dict:
    """Audit FINDING-DB05 / MT-7 / ST-12 closure (Batch 10A 2026-06-06).

    Delete completed/failed/cancelled jobs (plus their job_parts rows) whose
    ``updated_at`` is older than ``max_age_days``. ENV-gated via
    ``JOB_RETENTION_DAYS`` (default 0 = disabled) in the caller — this
    function itself just runs the prune when given a positive window.

    Why ``updated_at`` not ``created_at``: ``updated_at`` reflects the last
    state transition. A failed-then-resumed job keeps its row fresh and
    won't be pruned until N days after its FINAL state.

    Defensive: returns ``{removed_jobs, removed_parts}`` on success, the
    same dict shape with zeros on any error (and a WARN log). Never raises.

    Active job rows (``status IN ('running', 'queued')``) are NEVER touched
    regardless of age — the WHERE clause restricts deletion to the
    terminal-status set in ``_PRUNABLE_JOB_STATUSES``.
    """
    if not isinstance(max_age_days, int) or max_age_days <= 0:
        return {"removed_jobs": 0, "removed_parts": 0}

    placeholders = ",".join("?" * len(_PRUNABLE_JOB_STATUSES))
    cutoff_sql = f"datetime('now', '-{int(max_age_days)} days')"

    try:
        # Imported lazily so test collection doesn't open a connection.
        from app.db.connection import db_conn
        with db_conn() as conn:
            # Collect the doomed job_ids first so we can count the parts
            # we're about to delete (SQLite's DELETE doesn't return changes
            # for the joined-table case).
            doomed = conn.execute(
                f"""
                SELECT job_id FROM jobs
                 WHERE status IN ({placeholders})
                   AND updated_at < {cutoff_sql}
                """,
                _PRUNABLE_JOB_STATUSES,
            ).fetchall()
            if not doomed:
                return {"removed_jobs": 0, "removed_parts": 0}
            ids = [row[0] if isinstance(row, tuple) else row["job_id"] for row in doomed]
            ph = ",".join("?" * len(ids))
            parts_cur = conn.execute(
                f"DELETE FROM job_parts WHERE job_id IN ({ph})", ids
            )
            removed_parts = parts_cur.rowcount or 0
            jobs_cur = conn.execute(
                f"DELETE FROM jobs WHERE job_id IN ({ph})", ids
            )
            removed_jobs = jobs_cur.rowcount or 0
            # Commit explicitly so the ctxmgr's commit-on-exit doesn't
            # also fire a no-op transaction; harmless either way.
            conn.commit()
    except Exception as exc:
        logger.warning("prune_old_jobs failed (non-fatal): %s", exc)
        return {"removed_jobs": 0, "removed_parts": 0}

    if removed_jobs:
        logger.info(
            "maintenance: pruned %d completed/failed jobs (>%dd old) + %d job_parts",
            removed_jobs, max_age_days, removed_parts,
        )
    return {"removed_jobs": removed_jobs, "removed_parts": removed_parts}


def prune_job_logs(channels_dir: Path, keep_last: int = 30, older_than_days: int = 10):
    keep_last = max(1, int(keep_last or 30))
    older_than_days = max(1, int(older_than_days or 10))
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

    removed = 0
    scanned = 0
    channels = 0

    if not channels_dir.exists():
        return {"channels": 0, "scanned": 0, "removed": 0, "keep_last": keep_last, "older_than_days": older_than_days}

    for channel_dir in channels_dir.iterdir():
        if not channel_dir.is_dir():
            continue
        log_dir = channel_dir / "logs"
        if not log_dir.exists():
            continue
        channels += 1
        files = [p for p in log_dir.glob("*.log") if p.is_file()]
        files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        scanned += len(files)

        for idx, f in enumerate(files):
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            should_delete = idx >= keep_last or mtime < cutoff
            if not should_delete:
                continue
            try:
                f.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass

    return {
        "channels": channels,
        "scanned": scanned,
        "removed": removed,
        "keep_last": keep_last,
        "older_than_days": older_than_days,
    }

