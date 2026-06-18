"""Best-effort yt-dlp auto-updater.

YouTube routinely breaks older yt-dlp releases ("Requested format is not
available" / "no longer supported"). To keep the download feature working
without a manual ``pip install -U``, this runs a throttled, non-blocking
``pip install -U yt-dlp`` in the background at startup.

Design constraints (offline-first desktop app):
  - Never blocks startup — caller runs it in a daemon thread.
  - Never raises — every failure path is swallowed and logged at debug.
  - Throttled via a marker file so we hit PyPI at most once per interval.
  - Disable with ``YTDLP_AUTO_UPDATE=0``.
  - The upgrade takes effect on the NEXT process start (yt-dlp is already
    imported in the current one).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("app.downloader.autoupdate")

# Re-check at most once per this window (seconds). 12h keeps it fresh without
# hammering PyPI on every restart.
_UPDATE_INTERVAL_SEC = 12 * 3600


def _marker_path() -> Path:
    from app.core.config import APP_DATA_DIR
    return APP_DATA_DIR / ".ytdlp_update_check"


def _due(marker: Path) -> bool:
    try:
        if not marker.is_file():
            return True
        return (time.time() - marker.stat().st_mtime) >= _UPDATE_INTERVAL_SEC
    except Exception:
        return True


def _touch(marker: Path) -> None:
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(str(int(time.time())), encoding="utf-8")
    except Exception:
        pass


def update_ytdlp_now() -> bool:
    """Run ``pip install -U yt-dlp`` once. Returns True on a clean exit.
    Best-effort: returns False (never raises) on any failure or when pip is
    unavailable (e.g. a frozen build)."""
    try:
        cmd = [sys.executable, "-m", "pip", "install", "-U", "--disable-pip-version-check", "yt-dlp"]
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
        if proc.returncode == 0:
            logger.info("ytdlp_auto_update: yt-dlp is up to date / upgraded")
            return True
        logger.debug("ytdlp_auto_update: pip exit=%s err=%s", proc.returncode, (proc.stderr or "")[:200])
        return False
    except Exception as exc:
        logger.debug("ytdlp_auto_update: skipped — %s", exc)
        return False


def maybe_update_ytdlp() -> None:
    """Throttled, env-gated entry point for the startup background thread."""
    if (os.getenv("YTDLP_AUTO_UPDATE", "1") or "1").strip() not in ("1", "true", "yes", "on"):
        logger.debug("ytdlp_auto_update: disabled via YTDLP_AUTO_UPDATE")
        return
    marker = _marker_path()
    if not _due(marker):
        return
    # Touch BEFORE the attempt so a slow/looping failure can't trigger
    # back-to-back pip runs across rapid restarts.
    _touch(marker)
    update_ytdlp_now()
