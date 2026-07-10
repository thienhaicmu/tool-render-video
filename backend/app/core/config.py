import random
import sys
from pathlib import Path
import os

# Load .env from project root — must run before any os.getenv() call.
# override=False: real environment variables always win over .env values.
try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)
except Exception:
    pass


def _default_app_data_dir() -> Path:
    """Return a stable data directory that survives PyInstaller packaging.

    In packaged mode __file__-relative paths resolve inside the temp extraction
    bundle, which changes on every launch and gets deleted on shutdown.  Use
    %APPDATA%\\RenderVideoTool\\data so the path is persistent and writable.
    """
    if getattr(sys, "frozen", False):
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            return Path(appdata) / "RenderVideoTool" / "data"
        return Path.home() / ".render-video-tool" / "data"
    return Path(__file__).resolve().parents[3] / "data"


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_APP_DATA_DIR = _default_app_data_dir()
DEFAULT_CHANNELS_DIR = PROJECT_ROOT / "channels"

APP_DATA_DIR    = Path(os.getenv("APP_DATA_DIR",    str(DEFAULT_APP_DATA_DIR)))
DATABASE_PATH   = Path(os.getenv("DATABASE_PATH",   str(APP_DATA_DIR / "app.db")))
REPORTS_DIR     = Path(os.getenv("REPORTS_DIR",     str(APP_DATA_DIR / "reports")))
if "CHANNELS_DIR" in os.environ:
    CHANNELS_DIR = Path(os.environ["CHANNELS_DIR"])
else:
    has_project_channels = DEFAULT_CHANNELS_DIR.exists() and any(DEFAULT_CHANNELS_DIR.iterdir())
    CHANNELS_DIR = DEFAULT_CHANNELS_DIR if has_project_channels else (APP_DATA_DIR / "channels")
TEMP_DIR    = Path(os.getenv("TEMP_DIR",    str(APP_DATA_DIR / "temp")))
LOGS_DIR    = APP_DATA_DIR / "logs"
COOKIES_DIR = APP_DATA_DIR / "cookies"
# Nguồn chân lý duy nhất cho thư mục gốc cache render — dùng bởi
# pipeline_cache.py, motion/crop.py và helper prune trong maintenance.
CACHE_DIR   = APP_DATA_DIR / "cache"
REQUEST_LOG = LOGS_DIR / "request.log"   # Type 1: request/validation errors
# Thư mục gốc thư viện BGM của NGƯỜI DÙNG: {BGM_DIR}/{mood}/*.mp3
# (hoặc .wav/.m4a/.ogg/.flac). Ưu tiên cao nhất — người dùng ghi đè nhạc riêng.
BGM_DIR     = APP_DATA_DIR / "bgm"
# Thư viện BGM ĐÓNG GÓI theo repo (assets/bgm/{mood}/*.mp3) — nạp sẵn bởi
# backend/scripts/fetch_free_bgm.py và commit vào project để KHỎI tải lại. Dùng
# làm fallback khi BGM_DIR của người dùng chưa có nhạc cho mood đó. Ghi công CC-BY
# ở assets/bgm/ATTRIBUTION.txt.
BUNDLED_BGM_DIR = PROJECT_ROOT / "assets" / "bgm"

for p in [APP_DATA_DIR, REPORTS_DIR, CHANNELS_DIR, TEMP_DIR, LOGS_DIR, COOKIES_DIR, CACHE_DIR, BGM_DIR, DATABASE_PATH.parent]:
    p.mkdir(parents=True, exist_ok=True)


_BGM_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}


def _pick_bgm_file(mood: str) -> "str | None":
    """Return a random BGM file path for the requested mood, or None.

    Scan priority (first non-empty dir wins): user's ``BGM_DIR/{mood}`` →
    bundled ``BUNDLED_BGM_DIR/{mood}`` → user's ``BGM_DIR/default`` → bundled
    ``BUNDLED_BGM_DIR/default``. So a specific mood (even the repo-bundled one)
    beats a generic default, while the user's own files always win their tier.
    Returns None when no directory contains audio. Never raises.
    """
    try:
        m = (mood or "").strip().lower()
        dirs: list[Path] = []
        if m and m != "default":
            dirs += [BGM_DIR / m, BUNDLED_BGM_DIR / m]
        dirs += [BGM_DIR / "default", BUNDLED_BGM_DIR / "default"]
        for d in dirs:
            if d.is_dir():
                candidates = [f for f in d.iterdir()
                              if f.is_file() and f.suffix.lower() in _BGM_AUDIO_EXTS]
                if candidates:
                    return str(random.choice(candidates))
        return None
    except Exception:
        return None

# AI Cloud Analyzer — server-side defaults read from environment / .env
# These are fallbacks used when RenderRequest does not supply ai_cloud_api_key.
AI_CLOUD_ENABLED  : bool = os.getenv("AI_CLOUD_ENABLED", "0") == "1"
AI_CLOUD_PROVIDER : str  = os.getenv("AI_CLOUD_PROVIDER", "gemini")
AI_CLOUD_API_KEY  : str  = os.getenv("AI_CLOUD_API_KEY", "")
AI_CLOUD_MODEL    : str  = os.getenv("AI_CLOUD_MODEL", "")

# Server-wide default LLM provider for NEW jobs.
# Supported: "gemini" | "openai" | "claude".
AI_PROVIDER_DEFAULT  : str  = os.getenv("AI_PROVIDER_DEFAULT", "gemini").strip().lower()

# Per-provider API keys (server env fallback). Resolved in llm_stage._resolve_api_key
# AFTER payload-level keys. Empty = no fallback for that provider.
GEMINI_API_KEY       : str  = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY       : str  = os.getenv("OPENAI_API_KEY", "")
CLAUDE_API_KEY       : str  = os.getenv("CLAUDE_API_KEY", "")

# Gemini key POOL for quota rotation. Comma-separated in GEMINI_API_KEYS; each
# free-tier key is ~20 requests/day, so a pool multiplies daily headroom. The
# rotation logic lives in app/features/render/ai/llm/key_pool.py. When
# GEMINI_API_KEYS is empty the pool falls back to [GEMINI_API_KEY] (single-key
# behaviour unchanged). GEMINI_API_KEY (if unset) defaults to the first pool key.
GEMINI_API_KEYS      : "list[str]" = [
    k.strip() for k in os.getenv("GEMINI_API_KEYS", "").split(",") if k.strip()
]
if not GEMINI_API_KEY and GEMINI_API_KEYS:
    GEMINI_API_KEY = GEMINI_API_KEYS[0]

# SQLite connection timeout in seconds. Desktop renders on slow SSD/NAS may
# need a larger value. The startup write-check uses timeout=5 (uncontended)
# and is intentionally excluded from this setting.
DB_TIMEOUT           : int  = int(os.getenv("DB_TIMEOUT", "30"))

# Whisper / transcription tuning (see adapters.py + pipeline_cache.py):
#   WHISPER_BATCH_SIZE          — WhisperX batch_size override. Default: 8 (CUDA) / 4 (CPU).
#   WHISPER_CONTENT_HASH_CACHE  — Set to "1" to enable sha256-keyed transcription result cache
#                                 that survives re-downloads to different paths (default: off).
#   WHISPER_MODEL_CACHE_MAX     — Max OpenAI-whisper models in LRU cache (default: 2).
#   FW_MODEL_CACHE_MAX          — Max faster-whisper models in LRU cache (default: 2).
