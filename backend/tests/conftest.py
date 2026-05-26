import sys
from pathlib import Path

# Tests that import via 'from backend.app.xxx import yyy' require the repo
# root (D:\tool-render-video) to be on sys.path.  This conftest ensures it
# is added before any test module is collected.
_REPO_ROOT = Path(__file__).resolve().parents[2]  # tests/ -> backend/ -> repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
