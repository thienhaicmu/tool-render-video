import sqlite3, json, tempfile
from datetime import datetime
from pathlib import Path

conn = sqlite3.connect('../data/app.db')
conn.row_factory = sqlite3.Row
jobs = conn.execute(
    "SELECT job_id, payload_json, created_at, updated_at FROM jobs ORDER BY created_at DESC LIMIT 10"
).fetchall()

print("=== Recent job timings ===")
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
cache = Path(tempfile.gettempdir()) / "render_cache"
if cache.exists():
    files = list(cache.rglob("*"))
    print(f"Transcription cache: {len(files)} entries at {cache}")
else:
    print("Transcription cache: not found")

# App data cache
app_cache = Path("../data/cache")
if app_cache.exists():
    files = list(app_cache.rglob("*"))
    print(f"App data cache: {len(files)} entries at {app_cache}")
else:
    print("App data cache: not found")
