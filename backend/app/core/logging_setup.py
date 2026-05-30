"""
Centralized logging configuration — AI Video Render Studio.

Call configure_logging() once at startup (main.py module level).
All app.* loggers inherit file handlers automatically via Python's
logger hierarchy. Uvicorn's own console handlers are left untouched.

Log files (all under LOGS_DIR = data/logs/):
  app.log      — every INFO+ event from the entire app  (100 MB × 10)
  error.log    — ERROR+ only, with file/line context    ( 20 MB × 10)
  download.log — app.downloader.* subsystem             ( 50 MB ×  5)
  render.log   — app.render.* pipeline                  (100 MB × 10)

Environment variables:
  LOG_LEVEL    — DEBUG | INFO | WARNING | ERROR   (default: INFO)
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

_CONFIGURED = False

# ── Formatters ────────────────────────────────────────────────────────────────

_FMT_STANDARD = logging.Formatter(
    fmt="%(asctime)s  %(levelname)-8s  %(name)-40s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Error formatter: adds file path + line number for fast debugging
_FMT_ERROR = logging.Formatter(
    fmt=(
        "%(asctime)s  %(levelname)-8s  %(name)s\n"
        "  → %(pathname)s:%(lineno)d in %(funcName)s()\n"
        "  %(message)s"
    ),
    datefmt="%Y-%m-%d %H:%M:%S",
)

_LEVEL_MAP: dict[str, int] = {
    "DEBUG":    logging.DEBUG,
    "INFO":     logging.INFO,
    "WARNING":  logging.WARNING,
    "ERROR":    logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _rotating(
    path: Path,
    level: int,
    fmt: logging.Formatter,
    max_mb: int,
    backups: int,
) -> logging.handlers.RotatingFileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(
        str(path),
        maxBytes=max_mb * 1024 * 1024,
        backupCount=backups,
        encoding="utf-8",
        delay=True,   # don't create the file until first write
    )
    h.setLevel(level)
    h.setFormatter(fmt)
    return h


def _attach(logger_name: str, *handlers: logging.Handler) -> None:
    lg = logging.getLogger(logger_name)
    for h in handlers:
        lg.addHandler(h)


# ── Public API ────────────────────────────────────────────────────────────────

def configure_logging(logs_dir: Path) -> None:
    """
    Set up file-based logging for the entire application.

    Safe to call multiple times — subsequent calls are no-ops.
    Does NOT remove Uvicorn's console handlers.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    logs_dir.mkdir(parents=True, exist_ok=True)

    raw_level = os.getenv("LOG_LEVEL", "INFO").upper().strip()
    level = _LEVEL_MAP.get(raw_level, logging.INFO)

    # ── Root "app" logger ─────────────────────────────────────────────────
    # Parent of every app.* logger — sets the floor level and file handlers
    # that all children inherit automatically.
    app_lg = logging.getLogger("app")
    app_lg.setLevel(level)

    # app.log — all events at the configured level
    app_lg.addHandler(_rotating(logs_dir / "app.log",   level,          _FMT_STANDARD, max_mb=100, backups=10))
    # error.log — ERROR and above with full file context
    app_lg.addHandler(_rotating(logs_dir / "error.log", logging.ERROR,  _FMT_ERROR,    max_mb=20,  backups=10))

    # ── Download subsystem — app.downloader.* ─────────────────────────────
    dl_lg = logging.getLogger("app.downloader")
    dl_lg.addHandler(_rotating(logs_dir / "download.log", logging.DEBUG, _FMT_STANDARD, max_mb=50, backups=5))
    # propagate=True (default) — events still reach app.log via "app" parent

    # ── Render pipeline — app.render.* ───────────────────────────────────
    render_lg = logging.getLogger("app.render")
    render_lg.addHandler(_rotating(logs_dir / "render.log", logging.DEBUG, _FMT_STANDARD, max_mb=100, backups=10))

    # ── Suppress noisy third-party libraries ─────────────────────────────
    for noisy in ("httpx", "httpcore", "hpack", "urllib3", "multipart", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    # Announce that file logging is active (appears in both console + app.log)
    logging.getLogger("app.startup").info(
        "logging.configured  level=%s  logs_dir=%s  "
        "files=[app.log, error.log, download.log, render.log]",
        raw_level, logs_dir,
    )
