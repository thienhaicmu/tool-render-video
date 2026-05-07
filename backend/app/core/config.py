import sys
from pathlib import Path
import os


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
REQUEST_LOG = LOGS_DIR / "request.log"   # Type 1: request/validation errors

for p in [APP_DATA_DIR, REPORTS_DIR, CHANNELS_DIR, TEMP_DIR, LOGS_DIR, DATABASE_PATH.parent]:
    p.mkdir(parents=True, exist_ok=True)
