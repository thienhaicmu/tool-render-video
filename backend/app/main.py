
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os
import logging
import threading
from app.services.db import init_db
from app.services.channel_service import ensure_channel
from app.services.maintenance import prune_job_logs, prune_preview_dirs, prune_render_temp_dirs
from app.core.config import APP_DATA_DIR, CHANNELS_DIR, TEMP_DIR
from app.routes.channels import router as channels_router
from app.routes.render import router as render_router
from app.routes.jobs import router as jobs_router
from app.routes.voice import router as voice_router
from app.routes.files import router as files_router
from app.routes.editing import router as editing_router
from app.routes.platform_downloader import router as platform_downloader_router
from app.services.job_manager import recover_pending_render_jobs, shutdown as shutdown_job_manager
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
app.include_router(channels_router)
app.include_router(render_router)
app.include_router(jobs_router)
# Security: POST /api/dev/command executes arbitrary shell commands with no auth.
# Disabled by default. Set ENABLE_DEVTOOLS=1 only in trusted local dev environments.
if os.getenv("ENABLE_DEVTOOLS") == "1":
    from app.routes.devtools import router as devtools_router
    app.include_router(devtools_router)
app.include_router(voice_router)
app.include_router(files_router)
app.include_router(editing_router)
app.include_router(platform_downloader_router)
# Static file mount — path and name vary by UI version so both can coexist safely
if _UI_VERSION == "v2":
    # static-v2 index.html uses relative paths (assets/…) so mount at /assets
    app.mount("/assets", StaticFiles(directory=str(STATIC_DIR / "assets")), name="static_assets")
else:
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
_cleanup_logger = logging.getLogger("app.cleanup")


def _run_periodic_cleanup():
    """Periodic background cleanup: evict stale preview sessions + prune disk dirs."""
    import time as _time
    while True:
        _time.sleep(_CLEANUP_INTERVAL_SEC)
        try:
            from app.routes.render import evict_stale_preview_sessions
            evicted = evict_stale_preview_sessions()
            result_preview = prune_preview_dirs(TEMP_DIR, max_age_hours=6)
            result_render = prune_render_temp_dirs(TEMP_DIR)
            _cleanup_logger.info(
                "periodic cleanup: sessions_evicted=%d preview_removed=%d render_removed=%d",
                evicted,
                result_preview.get("removed", 0),
                result_render.get("removed", 0),
            )
        except Exception as exc:
            _cleanup_logger.warning("periodic cleanup error: %s", exc)


def _groq_health_check_worker():
    from app.core.config import AI_CLOUD_ENABLED, AI_CLOUD_API_KEY, AI_CLOUD_MODEL
    _log = logging.getLogger("app.startup.groq")
    if not AI_CLOUD_ENABLED or not AI_CLOUD_API_KEY:
        return
    try:
        from app.ai.analysis.cloud.groq_provider import GroqProvider
        provider = GroqProvider(api_key=AI_CLOUD_API_KEY, model=AI_CLOUD_MODEL or None)
        result = provider._call_api("ping")
        if result is not None:
            _log.info("groq_health_check_ok model=%s", AI_CLOUD_MODEL or provider.DEFAULT_MODEL)
        else:
            _log.warning(
                "groq_health_check_failed: API returned None — check AI_CLOUD_API_KEY and AI_CLOUD_MODEL"
            )
    except Exception as exc:
        _log.warning("groq_health_check_error: %s — AI cloud features may not work", exc)


def _start_groq_health_check():
    threading.Thread(target=_groq_health_check_worker, daemon=True, name="groq-health").start()


@app.on_event("startup")
def startup():
    _configure_access_log_filter()
    _configure_error_log_filter()
    init_db()
    ensure_channel("k1")
    keep_last = int(os.getenv("LOG_KEEP_LAST", "30"))
    older_days = int(os.getenv("LOG_KEEP_DAYS", "10"))
    prune_job_logs(CHANNELS_DIR, keep_last=keep_last, older_than_days=older_days)
    prune_preview_dirs(TEMP_DIR, max_age_hours=6)
    prune_render_temp_dirs(TEMP_DIR)  # clean leftover render temp dirs from previous run
    # Re-queue any render jobs that were interrupted by a previous server restart
    recover_pending_render_jobs()
    start_warmup()  # pre-download Whisper models + check deps in background
    _start_groq_health_check()  # non-blocking — logs warning if AI_CLOUD_API_KEY invalid
    # Phase 5.2: warm up local knowledge index in background (non-blocking)
    try:
        from app.ai.rag.knowledge_warmup import warmup_knowledge_index
        logging.getLogger("app.startup").info("knowledge_warmup: starting in background thread")
        threading.Thread(
            target=warmup_knowledge_index,
            daemon=True,
            name="knowledge-warmup",
        ).start()
    except Exception as _kw_err:
        logging.getLogger("app.startup").warning("knowledge_warmup: failed to start: %s", _kw_err)
    threading.Thread(target=_run_periodic_cleanup, daemon=True, name="cleanup-loop").start()


@app.get("/api/warmup/status")
def api_warmup_status():
    return warmup_status()


@app.on_event("shutdown")
def shutdown():
    shutdown_job_manager(wait=False)


@app.get("/health")
def health():
    return {"status": "ok", "ui_version": _UI_VERSION}


@app.get("/")
def index():
    return FileResponse(str(INDEX_FILE))
