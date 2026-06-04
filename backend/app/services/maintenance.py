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
    from app.services.db import get_job
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
    {removed, kept} for visibility in the startup log.
    """
    if not cache_dir.exists():
        return {"removed": 0, "kept": 0}
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    removed = kept = 0
    for subdir in cache_dir.iterdir():
        if not subdir.is_dir():
            continue
        try:
            for f in subdir.iterdir():
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
        except Exception:
            pass
    if removed:
        logger.info(
            "maintenance: pruned %d stale render cache files (>%dh old) from %s",
            removed, max_age_hours, cache_dir,
        )
    return {"removed": removed, "kept": kept}


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

