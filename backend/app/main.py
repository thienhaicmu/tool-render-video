
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import os
import logging
from app.services.db import init_db
from app.services.channel_service import ensure_channel
from app.services.maintenance import prune_job_logs, prune_preview_dirs
from app.core.config import TEMP_DIR, LOGS_DIR
from app.routes.channels import router as channels_router
from app.routes.render import router as render_router
from app.routes.upload import router as upload_router
from app.routes.jobs import router as jobs_router
from app.routes.devtools import router as devtools_router
from app.services.job_manager import recover_pending_render_jobs, shutdown as shutdown_job_manager
from app.services.warmup import start_warmup, get_status as warmup_status


class _SuppressNoisyAccessFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        noisy_patterns = (
            'GET /api/jobs/',
            'GET /api/jobs ',
            'GET /api/jobs?',
            'GET /health',
            'WebSocket /api/jobs/',
            'WebSocket /api/upload/',
        )
        return not any(p in msg for p in noisy_patterns)


def _configure_access_log_filter():
    logger = logging.getLogger("uvicorn.access")
    if any(isinstance(f, _SuppressNoisyAccessFilter) for f in logger.filters):
        return
    logger.addFilter(_SuppressNoisyAccessFilter())

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
STATIC_DIR = Path("/app/static") if Path("/app/static").exists() else (BACKEND_ROOT / "static")
INDEX_FILE = STATIC_DIR / "index.html"

# ── Redirect all model/cache dirs to project drive (D:) — prevents filling C: ──
_DATA_DIR = PROJECT_ROOT / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)

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
app.include_router(upload_router)
app.include_router(jobs_router)
app.include_router(devtools_router)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup():
    _configure_access_log_filter()
    init_db()
    ensure_channel("k1")
    keep_last = int(os.getenv("LOG_KEEP_LAST", "30"))
    older_days = int(os.getenv("LOG_KEEP_DAYS", "10"))
    prune_job_logs(LOGS_DIR, keep_last=keep_last, older_than_days=older_days)
    prune_preview_dirs(TEMP_DIR, max_age_hours=6)
    # Re-queue any render jobs that were interrupted by a previous server restart
    recover_pending_render_jobs()
    start_warmup()  # pre-download Whisper models + check deps in background


@app.get("/api/warmup/status")
def api_warmup_status():
    return warmup_status()


@app.on_event("shutdown")
def shutdown():
    shutdown_job_manager(wait=False)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def index():
    return FileResponse(str(INDEX_FILE))
