from pathlib import Path
import os

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_APP_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_CHANNELS_DIR = PROJECT_ROOT / "channels"

APP_DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(DEFAULT_APP_DATA_DIR)))
DATABASE_PATH = Path(os.getenv("DATABASE_PATH", APP_DATA_DIR / "app.db"))
REPORTS_DIR = Path(os.getenv("REPORTS_DIR", APP_DATA_DIR / "reports"))
if "CHANNELS_DIR" in os.environ:
    CHANNELS_DIR = Path(os.environ["CHANNELS_DIR"])
else:
    has_project_channels = DEFAULT_CHANNELS_DIR.exists() and any(DEFAULT_CHANNELS_DIR.iterdir())
    CHANNELS_DIR = DEFAULT_CHANNELS_DIR if has_project_channels else (APP_DATA_DIR / "channels")
TEMP_DIR = Path(os.getenv("TEMP_DIR", APP_DATA_DIR / "temp"))
LOGS_DIR  = APP_DATA_DIR / "logs"

for p in [APP_DATA_DIR, REPORTS_DIR, CHANNELS_DIR, TEMP_DIR, LOGS_DIR, DATABASE_PATH.parent]:
    p.mkdir(parents=True, exist_ok=True)
