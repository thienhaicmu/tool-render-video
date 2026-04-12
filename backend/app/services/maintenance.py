from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


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

