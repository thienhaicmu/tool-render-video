"""Online SQLite snapshot + retention for data/app.db.

Sprint 6.A (Sacred Contract 7 follow-up). CLAUDE.md §"data/app.db — No Backup,
No Recovery" warned that the offline desktop app had no copy of job state
beyond the live DB. This module closes that gap with cheap point-in-time
snapshots taken by the render pipeline + a CLI for manual use.

Mechanism: sqlite3.Connection.backup(target) — Python's native binding to
SQLite's online backup API. With WAL mode the snapshot is atomic and does
NOT block live readers/writers.

Triggers, in priority order:
  1. CLI: `python -m app.services.db_backup --snapshot`
  2. After every Nth completed render job (DB_BACKUP_EVERY_N_JOBS, default 5)
  3. Time-based: skip if a snapshot was taken less than
     DB_BACKUP_MIN_INTERVAL_SEC ago (default 1h)

Retention: keep newest DB_BACKUP_KEEP_LAST snapshots (default 10).

Failure policy: backup must NEVER fail a render job. The single call site in
render_pipeline.py wraps maybe_snapshot_after_job() in try/except: pass.
"""
from __future__ import annotations

import datetime
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path

from app.core.config import APP_DATA_DIR
from app.db.connection import get_active_db_path

logger = logging.getLogger(__name__)


# ── Configuration (env-tunable) ──────────────────────────────────────────────

# Default backup root. DB_BACKUP_DIR env var overrides — power users can point
# at a separate volume for real DR. Both must be writable by the app process.
BACKUP_DIR: Path = Path(
    os.getenv("DB_BACKUP_DIR", str(APP_DATA_DIR / "backups"))
)

# How many snapshots to keep after each prune. Older ones are unlinked.
BACKUP_KEEP_LAST: int = max(1, int(os.getenv("DB_BACKUP_KEEP_LAST", "10")))

# Snapshot every Nth completed render. Lower = more snapshots, more disk.
BACKUP_EVERY_N_JOBS: int = max(1, int(os.getenv("DB_BACKUP_EVERY_N_JOBS", "5")))

# Minimum wallclock seconds between snapshots, even if the N-job trigger fires
# more often. Bounds disk I/O on bursty workloads.
BACKUP_MIN_INTERVAL_SEC: int = max(0, int(os.getenv("DB_BACKUP_MIN_INTERVAL_SEC", str(60 * 60))))


# ── Internal state — guarded by _job_counter_lock ────────────────────────────

_job_counter_lock = threading.Lock()
_job_counter: int = 0
_last_backup_at: float = 0.0  # monotonic seconds; 0 means "never"
# Guards against piling up snapshot threads: the finalize call site fires this
# in a daemon thread, and a hung/slow backup leaves _last_backup_at stale, so
# the time-trigger would otherwise re-fire on every later render. Only one
# snapshot runs at a time.
_snapshot_in_progress: bool = False


# ── Snapshot ─────────────────────────────────────────────────────────────────


def snapshot_db(target_dir: Path | None = None) -> Path | None:
    """Take an atomic online backup of the live SQLite file.

    Uses sqlite3.Connection.backup() which iterates pages while honoring WAL
    so concurrent writers are not blocked. The destination is a complete,
    self-contained SQLite file at `target_dir/app-YYYYMMDD-HHMMSS.db`.

    Returns the destination Path on success, or None on any failure (logged
    at WARNING level; never raises).
    """
    out_dir = target_dir if target_dir is not None else BACKUP_DIR
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        src_path = get_active_db_path()
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
        dest = out_dir / f"app-{ts}.db"
        # If a snapshot collided on the same second, fall through with a suffix
        # so we don't overwrite a previous backup. Rare; only happens under
        # manual rapid-fire CLI use.
        suffix = 0
        while dest.exists():
            suffix += 1
            dest = out_dir / f"app-{ts}-{suffix}.db"
        src = sqlite3.connect(str(src_path))
        try:
            dst = sqlite3.connect(str(dest))
            try:
                src.backup(dst)
            finally:
                dst.close()
        finally:
            src.close()
        logger.info(
            "db_backup: snapshot %s → %s (%d bytes)",
            src_path, dest, dest.stat().st_size,
        )
        # Sprint 6.C: success counter (lazy import keeps this module
        # decoupled from the metrics layer's optional dep).
        try:
            from app.services.metrics import DB_BACKUPS_TOTAL
            DB_BACKUPS_TOTAL.labels(result="success").inc()
        except Exception:
            pass
        return dest
    except Exception as exc:
        logger.warning("db_backup: snapshot failed: %s", exc)
        try:
            from app.services.metrics import DB_BACKUPS_TOTAL
            DB_BACKUPS_TOTAL.labels(result="failure").inc()
        except Exception:
            pass
        return None


def prune_snapshots(
    target_dir: Path | None = None,
    keep_last: int | None = None,
) -> int:
    """Delete snapshot files beyond the newest `keep_last`. Returns deleted count.

    Newest-first sort by mtime. Files that don't match the `app-*.db` glob
    (e.g. operator notes, README) are left alone.
    """
    out_dir = target_dir if target_dir is not None else BACKUP_DIR
    keep = keep_last if keep_last is not None else BACKUP_KEEP_LAST
    try:
        if not out_dir.exists():
            return 0
        snaps = sorted(
            out_dir.glob("app-*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        to_remove = snaps[keep:]
        removed = 0
        for p in to_remove:
            try:
                p.unlink()
                removed += 1
            except Exception:
                pass
        if removed:
            logger.info("db_backup: pruned %d old snapshot(s) from %s", removed, out_dir)
        return removed
    except Exception as exc:
        logger.warning("db_backup: prune failed: %s", exc)
        return 0


def maybe_snapshot_after_job() -> Path | None:
    """Trigger snapshot if N-job or time-since-last interval fires.

    Called once per completed render at render_pipeline.py finalize. The single
    call site is wrapped in `try/except: pass` so any failure here cannot
    propagate. Returns the snapshot path (if taken) or None.
    """
    global _job_counter, _last_backup_at, _snapshot_in_progress
    with _job_counter_lock:
        _job_counter += 1
        n = _job_counter
        last = _last_backup_at
        in_progress = _snapshot_in_progress

    # A previous snapshot is still running (slow/hung backup) — don't stack
    # another one. Returning here keeps the daemon-thread call site from
    # spawning a new sqlite connection pair on every subsequent render.
    if in_progress:
        return None

    elapsed = float("inf") if last <= 0 else (time.monotonic() - last)
    n_trigger = (n % BACKUP_EVERY_N_JOBS) == 0
    time_trigger = elapsed >= BACKUP_MIN_INTERVAL_SEC

    if not (n_trigger or time_trigger):
        return None

    with _job_counter_lock:
        _snapshot_in_progress = True
    try:
        snap = snapshot_db()
    finally:
        with _job_counter_lock:
            _snapshot_in_progress = False
    if snap is not None:
        with _job_counter_lock:
            _last_backup_at = time.monotonic()
        prune_snapshots()
    return snap


def list_snapshots(target_dir: Path | None = None) -> list[tuple[Path, int, datetime.datetime]]:
    """Return [(path, size_bytes, mtime), ...] newest-first."""
    out_dir = target_dir if target_dir is not None else BACKUP_DIR
    if not out_dir.exists():
        return []
    snaps = sorted(
        out_dir.glob("app-*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    result: list[tuple[Path, int, datetime.datetime]] = []
    for p in snaps:
        try:
            st = p.stat()
            mt = datetime.datetime.fromtimestamp(st.st_mtime)
            result.append((p, st.st_size, mt))
        except Exception:
            pass
    return result


# ── CLI ──────────────────────────────────────────────────────────────────────


def _reset_state_for_tests() -> None:
    """Test helper — reset module-level trigger state. Not part of the public API."""
    global _job_counter, _last_backup_at, _snapshot_in_progress
    with _job_counter_lock:
        _job_counter = 0
        _last_backup_at = 0.0
        _snapshot_in_progress = False


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", action="store_true", help="Take a snapshot now")
    ap.add_argument("--list",     action="store_true", help="List existing snapshots")
    ap.add_argument("--prune",    action="store_true", help="Apply retention policy now")
    args = ap.parse_args()

    if args.snapshot:
        path = snapshot_db()
        print(f"snapshot: {path}" if path else "snapshot: failed")
        return 0 if path else 1
    if args.list:
        snaps = list_snapshots()
        if not snaps:
            print(f"(no snapshots in {BACKUP_DIR})")
            return 0
        for p, sz, mt in snaps:
            print(f"{p.name}\t{sz} bytes\t{mt.isoformat()}")
        return 0
    if args.prune:
        n = prune_snapshots()
        print(f"pruned {n} snapshot(s)")
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
