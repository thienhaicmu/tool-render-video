import os
import sys
from pathlib import Path

# Tests that import via 'from backend.app.xxx import yyy' require the repo
# root (D:\tool-render-video) to be on sys.path.  This conftest ensures it
# is added before any test module is collected.
_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/ -> backend/ -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ── Session data-dir isolation (MUST run before app.core.config is imported) ──
# Without this the whole test suite uses the REAL desktop data dir: every test
# that exercises the pipeline writes job rows, render.log lines and channel
# folders into data/ + channels/ alongside the user's real renders ("chung
# đụng"). The render.log file handler in particular binds to its path at
# setup_logging() time, so a per-test monkeypatch of LOGS_DIR can't redirect it
# — only setting the env BEFORE config import does. We point APP_DATA_DIR (and
# CHANNELS_DIR, which otherwise resolves to the real ./channels because that
# folder exists) at a throwaway, git-ignored sandbox under tests/.
_TEST_SANDBOX = Path(__file__).resolve().parent / ".pytest-data"
os.environ.setdefault("APP_DATA_DIR", str(_TEST_SANDBOX))
os.environ.setdefault("CHANNELS_DIR", str(_TEST_SANDBOX / "channels"))
