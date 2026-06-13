
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os
import logging
import threading
from app.db.connection import init_db
from app.services.channel_service import ensure_channel
from app.services.maintenance import (
    prune_job_logs,
    prune_old_jobs,
    prune_preview_dirs,
    prune_render_cache,
    prune_render_temp_dirs,
    prune_text_overlay_dir,
    prune_xtts_cache,
)
from app.core.config import APP_DATA_DIR, CACHE_DIR, CHANNELS_DIR, TEMP_DIR, LOGS_DIR
from app.core.logging_setup import configure_logging as _configure_logging
# Configure file-based logging before any other module emits a log event.
# Uvicorn's console handlers are not touched — this only adds file handlers.
_configure_logging(LOGS_DIR)
from app.features.render.router import router as render_router
from app.routes.jobs import router as jobs_router
from app.routes.voice import router as voice_router
from app.routes.files import router as files_router
from app.features.render.editing.router import router as editing_router
from app.features.download.router import router as platform_downloader_router
from app.routes.feedback import router as feedback_router
from app.routes.metrics import router as metrics_router
from app.routes.settings import router as settings_router
from app.routes.assets import router as assets_router
from app.routes.presets import router as presets_router
from app.routes.outputs import router as outputs_router
from app.routes.analytics import router as analytics_router
from app.routes.channels_context import router as channels_context_router
from app.routes.batch_render import router as batch_render_router
from app.routes.thumbnails import router as thumbnails_router
from app.routes.storage import router as storage_router
from app.routes.snapshot import router as snapshot_router
from app.routes.prompt_preview import router as prompt_preview_router
from app.routes.job_report import router as job_report_router
from app.routes.job_clone import router as job_clone_router
from app.jobs.manager import recover_pending_render_jobs, shutdown as shutdown_job_manager
from app.services.warmup import start_warmup, get_status as warmup_status
from app.core.ui_gate import resolve_static_directory
from fastapi import Request
from fastapi.responses import Response


class _SuppressNoisyAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        noisy_patterns = (
            'GET /api/jobs/',
            'GET /api/jobs ',
            'GET /api/jobs?',
            'GET /health',
            'WebSocket /api/jobs/',
        )
        return not any(p in msg for p in noisy_patterns)


class _SuppressClientDisconnect(logging.Filter):
    _PHRASES = (
        "client disconnected",
        "connection closed",
        "peer closed connection without sending complete message body",
        "disconnect without closing handshake",
    )
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage().lower()
        return not any(p in msg for p in self._PHRASES)


def _configure_access_log_filter():
    logger = logging.getLogger("uvicorn.access")
    if any(isinstance(f, _SuppressNoisyAccessFilter) for f in logger.filters):
        return
    logger.addFilter(_SuppressNoisyAccessFilter())


def _configure_error_log_filter():
    logger = logging.getLogger("uvicorn.error")
    if any(isinstance(f, _SuppressClientDisconnect) for f in logger.filters):
        return
    logger.addFilter(_SuppressClientDisconnect())

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent

# ── UI activation gate ────────────────────────────────────────────────────────
# Set STATIC_UI_VERSION=v2  to serve backend/static-v2/
# Set STATIC_UI_VERSION=legacy (or leave unset) to serve backend/static/
STATIC_DIR, _UI_VERSION = resolve_static_directory(BACKEND_ROOT)
INDEX_FILE = STATIC_DIR / "index.html"

# ── Redirect all model/cache dirs to a stable location ───────────────────────
# APP_DATA_DIR from config already handles packaged vs dev mode correctly.
_DATA_DIR = APP_DATA_DIR

# Whisper — redirect via env var read by openai-whisper internals
_whisper_cache = _DATA_DIR / "whisper_cache"
_whisper_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(_DATA_DIR / "cache"))

# Torch / HuggingFace — some deps cache here
os.environ.setdefault("TORCH_HOME",           str(_DATA_DIR / "torch"))
os.environ.setdefault("HF_HOME",              str(_DATA_DIR / "huggingface"))
os.environ.setdefault("TRANSFORMERS_CACHE",   str(_DATA_DIR / "huggingface" / "hub"))

# Ollama models — used when starting ollama serve
_ollama_models = _DATA_DIR / "ollama" / "models"
_ollama_models.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("OLLAMA_MODELS", str(_ollama_models))

# Windows TEMP — yt-dlp fallback, some C libs
os.environ.setdefault("TEMP", str(_DATA_DIR / "tmp"))
os.environ.setdefault("TMP",  str(_DATA_DIR / "tmp"))
(_DATA_DIR / "tmp").mkdir(parents=True, exist_ok=True)

app = FastAPI(title="YT TikTok Desktop Local Platform")
app.include_router(render_router)
app.include_router(jobs_router)
# Security: POST /api/dev/command executes arbitrary shell commands with no auth.
# Disabled by default. Set ENABLE_DEVTOOLS=1 only in trusted local dev environments.
# Hard-block: refuses to mount unless uvicorn is bound to a loopback host
# (fail closed — see app/core/devtools_safety.py).
if os.getenv("ENABLE_DEVTOOLS") == "1":
    from app.core.devtools_safety import (
        assert_devtools_safe,
        detect_uvicorn_bind_host,
    )
    _devtools_host = detect_uvicorn_bind_host()
    assert_devtools_safe(_devtools_host)
    logging.getLogger("app.security").warning(
        "DEVTOOLS ENABLED on loopback host %s — POST /api/dev/command executes "
        "arbitrary shell commands without authentication. Disable in production.",
        _devtools_host,
    )
    from app.routes.devtools import router as devtools_router
    app.include_router(devtools_router)
app.include_router(voice_router)
app.include_router(files_router)
app.include_router(editing_router)
app.include_router(platform_downloader_router)
app.include_router(feedback_router)
app.include_router(metrics_router)  # Sprint 6.C: Prometheus /metrics endpoint
app.include_router(settings_router)  # Sprint 3-FE: /api/settings/creator-context
app.include_router(assets_router)   # Phase C: Asset Library
app.include_router(presets_router)  # Phase E: Smart Render Presets
app.include_router(outputs_router)   # Phase F: Multi-Output Compare & Export
app.include_router(analytics_router) # Phase G: Analytics Dashboard API
app.include_router(channels_context_router) # Phase I: Per-Channel Creator Context
app.include_router(batch_render_router)    # Phase K: Batch Render from Asset Library
app.include_router(thumbnails_router)      # Phase J: Output Thumbnail API
app.include_router(storage_router)         # Phase L: Disk Usage & Cleanup
app.include_router(snapshot_router)        # Phase P: Job Snapshot
app.include_router(prompt_preview_router)  # Phase R: LLM Prompt Preview
app.include_router(job_report_router)      # Phase S: Job Export Report
app.include_router(job_clone_router)       # Phase M: Job Clone / Re-render
# v2 API routes — disabled by setting ENABLE_V2=0
if os.getenv("ENABLE_V2", "1") != "0":
    try:
        from v2.api.routes.download import router as v2_download_router
        from v2.api.routes.render import router as v2_render_router
        app.include_router(v2_download_router)
        app.include_router(v2_render_router)
    except Exception as _v2_err:  # noqa: BLE001
        logging.getLogger("app.main").warning("v2 routes failed to load: %s", _v2_err)
# Static file mount — path and name vary by UI version so both can coexist safely
if _UI_VERSION == "v2":
    # static-v2 index.html uses relative paths (assets/…) so mount at /assets
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="static_assets")
elif STATIC_DIR.is_dir():
    # Legacy index.html references /static/… absolute paths
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ── CSP middleware for v2 UI ──────────────────────────────────────────────────
# Applied only when STATIC_UI_VERSION=v2 to avoid breaking the legacy UI.
# Allows same-origin scripts/styles, WebSocket connections, and blob/data URIs
# for video/audio media. Inline styles are permitted for the React runtime.
_CSP_V2 = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "img-src 'self' data: blob: https://img.youtube.com; "
    "media-src 'self' blob:; "
    "connect-src 'self' ws://127.0.0.1:8000 ws://localhost:8000; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "frame-ancestors 'none';"
)

_UI_PATHS_V2 = frozenset({"/", "/index.html"})


@app.middleware("http")
async def _csp_middleware(request: Request, call_next):
    response = await call_next(request)
    if _UI_VERSION == "v2" and request.url.path in _UI_PATHS_V2:
        response.headers["Content-Security-Policy"] = _CSP_V2
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
    return response


_CLEANUP_INTERVAL_SEC: int = int(os.getenv("CLEANUP_INTERVAL_SEC", "1800"))  # default 30 min
# Audit FINDING-DB05 / MT-7 / ST-12 (Batch 10A 2026-06-06): env-gated row
# retention for completed/failed jobs. 0 = disabled (default). Set to e.g.
# 90 to evict any non-active job whose ``updated_at`` is more than 90 days
# old. Active rows (running/queued) are never touched regardless of age.
_JOB_RETENTION_DAYS: int = int(os.getenv("JOB_RETENTION_DAYS", "0"))
_cleanup_logger = logging.getLogger("app.cleanup")


def _run_periodic_cleanup():
    """Periodic background cleanup: evict stale preview sessions + prune disk dirs."""
    import time as _time
    while True:
        _time.sleep(_CLEANUP_INTERVAL_SEC)
        try:
            from app.features.render.router import evict_stale_preview_sessions
            evicted = evict_stale_preview_sessions()
            result_preview = prune_preview_dirs(TEMP_DIR, max_age_hours=6)
            result_render = prune_render_temp_dirs(TEMP_DIR)
            # Sprint 6 P0: bound long-running caches that previously had no TTL.
            result_xtts = prune_xtts_cache(TEMP_DIR, max_age_days=30)
            from app.services.text_overlay import get_text_overlay_temp_dir
            result_overlay = prune_text_overlay_dir(get_text_overlay_temp_dir(), max_age_days=7)
            # Sprint 6 P1 (closure of CLAUDE.md Issue 3): render cache prune
            # was startup-only since Sprint 5.2 — long-running servers never
            # tripped the 72h TTL on sources that are never re-accessed.
            # Now runs on every periodic tick as well. 72h TTL matches
            # _RENDER_CACHE_TTL_SEC in pipeline_cache.py.
            result_cache = prune_render_cache(CACHE_DIR, max_age_hours=72)
            # Audit FINDING-DB05 / MT-7: DB row retention.
            # Batch 10R (MT-7 UI): the Settings screen can now persist
            # ``job_retention_days`` in creator_prefs. Each cleanup tick
            # reads the DB-stored value first; falls back to the
            # ``JOB_RETENTION_DAYS`` env var when the user hasn't
            # configured anything via the UI (first boot / scripted
            # deployment). Either way, 0 = retention disabled.
            try:
                from app.db.creator_repo import get_job_retention_days
                _db_days = get_job_retention_days()
            except Exception as _exc:  # pragma: no cover — repo helper is defensive
                _db_days = None
                _cleanup_logger.warning("data_retention read failed: %s", _exc)
            _retention_days = _db_days if _db_days is not None else _JOB_RETENTION_DAYS
            result_jobs = prune_old_jobs(_retention_days)
            _cleanup_logger.info(
                "periodic cleanup: sessions_evicted=%d preview_removed=%d render_removed=%d "
                "xtts_removed=%d overlay_removed=%d cache_removed=%d cache_freed_mb=%.1f "
                "jobs_pruned=%d parts_pruned=%d",
                evicted,
                result_preview.get("removed", 0),
                result_render.get("removed", 0),
                result_xtts.get("removed", 0),
                result_overlay.get("removed", 0),
                result_cache.get("removed", 0),
                result_cache.get("freed_bytes", 0) / (1024 * 1024),
                result_jobs.get("removed_jobs", 0),
                result_jobs.get("removed_parts", 0),
            )
        except Exception as exc:
            _cleanup_logger.warning("periodic cleanup error: %s", exc)



@app.on_event("startup")
def startup():
    _configure_access_log_filter()
    _configure_error_log_filter()
    init_db()
    _check_db_fallback_at_startup()
    # Phase E: seed built-in render presets (idempotent — safe on every restart).
    try:
        from app.services.preset_seeder import seed_builtin_presets
        seed_builtin_presets()
    except Exception as _se:
        logging.getLogger("app.startup").warning("preset_seeder import failed: %s", _se)
    ensure_channel("k1")
    keep_last = int(os.getenv("LOG_KEEP_LAST", "30"))
    older_days = int(os.getenv("LOG_KEEP_DAYS", "10"))
    prune_job_logs(CHANNELS_DIR, keep_last=keep_last, older_than_days=older_days)
    prune_preview_dirs(TEMP_DIR, max_age_hours=6)
    prune_render_temp_dirs(TEMP_DIR)  # clean leftover render temp dirs from previous run
    # Sprint 5.2: bound render-cache disk growth. TTL 72h matches
    # _RENDER_CACHE_TTL_SEC in pipeline_cache.py.
    prune_render_cache(CACHE_DIR, max_age_hours=72)
    # Sprint 6 P0 (audit 2026-06-04 S-5 + S-7): two caches with no TTL
    # previously — XTTS synthesis cache and text_overlay drawtext files.
    # Same scheduler tick handles them periodically; startup prune
    # catches anything that accumulated between restarts.
    prune_xtts_cache(TEMP_DIR, max_age_days=30)
    # Phase 1-18 feature-layer migration moved text_overlay to
    # features/render/engine/overlay/text_overlay.py. The old import path
    # `app.services.text_overlay` no longer exists; using the new location.
    from app.features.render.engine.overlay.text_overlay import get_text_overlay_temp_dir
    prune_text_overlay_dir(get_text_overlay_temp_dir(), max_age_days=7)
    # Re-queue any render jobs that were interrupted by a previous server restart
    recover_pending_render_jobs()
    start_warmup()  # pre-download Whisper models + check deps in background
    # Pre-load Whisper model into RAM so first job doesn't pay the 5-15s load cost.
    # Uses WARMUP_WHISPER_MODEL env var (default "small" = balanced preset).
    def _whisper_model_warmup():
        try:
            _wm = os.getenv("WARMUP_WHISPER_MODEL", "small")
            from app.features.render.engine.subtitle.transcription.adapters import warmup_fw_model
            ok = warmup_fw_model(_wm)
            logging.getLogger("app.startup").info(
                "whisper_warmup: model=%s loaded=%s", _wm, ok
            )
        except Exception as _ww_err:
            logging.getLogger("app.startup").debug("whisper_warmup: skipped — %s", _ww_err)
    threading.Thread(target=_whisper_model_warmup, daemon=True, name="whisper-warmup").start()
    # RAG knowledge warmup removed in Phase G — RAG/AI Director removed.
    threading.Thread(target=_run_periodic_cleanup, daemon=True, name="cleanup-loop").start()
    # Auto-extract Chrome cookies for YouTube auth (non-blocking — best-effort)
    def _cookie_warmup():
        try:
            from app.core.config import COOKIES_DIR
            from app.features.download.engine.cookie_extractor import extract_youtube_cookies
            out = COOKIES_DIR / "youtube_cookies.txt"
            ok = extract_youtube_cookies(out)
            if ok:
                logging.getLogger("app.startup").info("cookie_warmup: YouTube cookies extracted → %s", out)
            else:
                logging.getLogger("app.startup").debug("cookie_warmup: no Chrome profile found, skipping")
        except Exception as _ce:
            logging.getLogger("app.startup").debug("cookie_warmup: skipped — %s", _ce)
    threading.Thread(target=_cookie_warmup, daemon=True, name="cookie-warmup").start()


@app.get("/api/warmup/status")
def api_warmup_status():
    return warmup_status()


def _check_db_fallback_at_startup() -> None:
    """Sprint 4.4 — surface DB fallback engagement at startup.

    Sacred Contract 7 says `data/app.db` is the sole job state authority.
    `_resolve_db_path()` will silently fall back to LOCALAPPDATA when the
    configured primary path is unwritable. This check writes a marker file
    and logs at CRITICAL so operators can detect the split-DB condition.
    """
    try:
        from app.db.connection import is_fallback_active, get_active_db_path
        if not is_fallback_active():
            # Remove stale flag from a previous fallback session
            try:
                flag = APP_DATA_DIR / "DB_FALLBACK_ENGAGED.flag"
                if flag.exists():
                    flag.unlink()
            except Exception:
                pass
            return
        active = get_active_db_path()
        from app.core.config import DATABASE_PATH as _PRIMARY
        log = logging.getLogger("app.startup")
        log.critical(
            "DB_FALLBACK_ENGAGED — primary path %s is not writable; "
            "data is being written to fallback %s. Sacred Contract 7 erosion: "
            "job state is now split across two app.db files. Investigate the "
            "primary path's permissions and restart the app to recover.",
            _PRIMARY, active,
        )
        try:
            flag = APP_DATA_DIR / "DB_FALLBACK_ENGAGED.flag"
            flag.write_text(
                f"timestamp={threading.current_thread().name}\n"
                f"primary={_PRIMARY}\nactive={active}\n",
                encoding="utf-8",
            )
        except Exception as exc:
            log.warning("DB_FALLBACK_ENGAGED.flag write failed: %s", exc)
    except Exception as exc:
        # Never raise from a startup hook — fall through and let the app boot
        logging.getLogger("app.startup").warning(
            "_check_db_fallback_at_startup failed: %s", exc,
        )


@app.on_event("shutdown")
def shutdown():
    # Sprint 4.1: bounded graceful shutdown. Default 30s gives FFmpeg time
    # to wrap up a short clip; longer renders are signaled cancel and
    # abandoned past the deadline. Override via SHUTDOWN_TIMEOUT_SEC.
    timeout = float(os.getenv("SHUTDOWN_TIMEOUT_SEC", "30"))
    shutdown_job_manager(wait=True, timeout=timeout)


@app.get("/health")
def health():
    """Health endpoint — adds DB-path visibility (Sprint 4.4).

    db_path is the currently-active SQLite path (after fallback resolution).
    db_fallback_active=True signals that data is being written to the
    LOCALAPPDATA fallback instead of the configured primary path. Clients
    (frontend, Electron, monitoring) can surface this to the operator.
    """
    db_path = ""
    db_fallback_active = False
    try:
        from app.db.connection import get_active_db_path, is_fallback_active
        db_path = str(get_active_db_path())
        db_fallback_active = is_fallback_active()
    except Exception:
        pass
    return {
        "status": "ok",
        "ui_version": _UI_VERSION,
        "db_path": db_path,
        "db_fallback_active": db_fallback_active,
    }


@app.get("/")
def index():
    return FileResponse(str(INDEX_FILE))
