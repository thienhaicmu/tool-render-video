"""check_perf.py — dev-only perf snapshot of recent render jobs + cache size.

Audit 2026-06-02 P3-D7: previously used a hardcoded `sqlite3.connect('../data/app.db')`
which bypassed the connection module's fallback-path resolution. If the
primary DB path was unwritable and the runtime had fallen back to
LOCALAPPDATA, this script would silently read a stale empty DB.

Now imports DATABASE_PATH from app.core.config — same path the live
runtime uses, including fallback resolution. Also drops the obsolete
tempfile.gettempdir() / 'render_cache' check (cache root moved to
APP_DATA_DIR/cache in Sprint 4.4).
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Make `app.core.config` importable when run from repo root or backend/.
_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.config import CACHE_DIR, DATABASE_PATH  # noqa: E402

conn = sqlite3.connect(str(DATABASE_PATH))
conn.row_factory = sqlite3.Row
jobs = conn.execute(
    "SELECT job_id, payload_json, created_at, updated_at FROM jobs ORDER BY created_at DESC LIMIT 10"
).fetchall()

print(f"=== Recent job timings (db: {DATABASE_PATH}) ===")
for j in jobs:
    try:
        c = datetime.fromisoformat(str(j["created_at"]).replace("Z", ""))
        u = datetime.fromisoformat(str(j["updated_at"]).replace("Z", ""))
        secs = (u - c).total_seconds()
        p = json.loads(j["payload_json"] or "{}")
        whisper  = p.get("whisper_model", "?")
        profile  = p.get("render_profile", "?")
        subtitle = p.get("add_subtitle", False)
        motion   = p.get("motion_aware_crop", False)
        ai_dir   = p.get("ai_director_enabled", False)
        min_sec  = p.get("min_part_sec", "?")
        max_sec  = p.get("max_part_sec", "?")
        src = str(p.get("source_video_path") or p.get("youtube_url", ""))[-40:]
        print(f"  {secs:5.0f}s | {profile} whisper={whisper} sub={subtitle} motion={motion} ai={ai_dir} clip={min_sec}-{max_sec}s")
        print(f"         src: {src}")
    except Exception as e:
        print(f"  error: {e}")

conn.close()

print()
if CACHE_DIR.exists():
    files = list(CACHE_DIR.rglob("*"))
    print(f"App data cache: {len(files)} entries at {CACHE_DIR}")
else:
    print(f"App data cache: not found at {CACHE_DIR}")
