# Backend Context

## Stack

- **Framework**: FastAPI (Python 3.11+)
- **ASGI Server**: Uvicorn
- **Database**: SQLite with WAL mode
- **Job Queue**: Python ThreadPoolExecutor
- **Key Libraries**: yt-dlp, openai-whisper, pydantic v2

## File Layout

```
backend/app/
├── main.py              # FastAPI app, startup hooks, static file serving
├── core/
│   └── config.py        # CHANNELS_DIR, TEMP_DIR, DATABASE_PATH constants
├── models/
│   └── schemas.py       # Pydantic request/response models
├── routes/
│   ├── channels.py      # Channel CRUD
│   ├── render.py        # Render pipeline entry + preview session management
│   ├── upload.py        # Upload job submission
│   └── jobs.py          # Job status HTTP + WebSocket
└── services/
    ├── db.py            # SQLite helpers: get_job, update_job_progress, upsert_job_part
    ├── job_manager.py   # ThreadPoolExecutor, submit_job, recover_pending_render_jobs
    ├── render_engine.py # Full render pipeline: download → detect → segment → transcribe → render
    ├── downloader.py    # yt-dlp wrapper with ios client + bestvideo+bestaudio strategy
    ├── upload_engine.py # Playwright-based TikTok upload
    ├── bin_paths.py     # ffmpeg/ffprobe discovery
    ├── warmup.py        # Background model pre-download
    └── maintenance.py   # Log pruning, preview session cleanup
```

## Render Pipeline Stages

Each stage must call `update_job_progress(job_id, stage=..., percent=..., message=...)` at start and end.

Stage sequence:
1. `downloading` — yt-dlp download
2. `scene_detection` — ffmpeg scene filter
3. `segment_building` — ffmpeg trim per segment
4. `transcribing_full` — Whisper transcription
5. `rendering` / `rendering_parallel` — ffmpeg encode per clip
6. `writing_report` — JSON report file
7. `done`

## Database Schema

```sql
CREATE TABLE jobs (
  job_id TEXT PRIMARY KEY,
  channel_code TEXT,
  status TEXT,           -- queued|running|completed|failed|interrupted
  stage TEXT,
  progress_percent REAL,
  message TEXT,
  created_at TEXT,
  updated_at TEXT,
  payload TEXT           -- JSON blob of RenderRequest
);

CREATE TABLE job_parts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id TEXT,
  part_index INTEGER,
  part_name TEXT,
  status TEXT,           -- pending|running|done|failed
  progress_percent REAL,
  message TEXT,
  updated_at TEXT
);
```

## Critical Rules

1. Never block the request thread with pipeline work — always use `job_manager.submit_job()`
2. Always use `update_job_progress()` at every stage transition
3. SQLite WAL mode is required — do not change journal mode
4. NVENC fallback to CPU is mandatory — do not remove the fallback chain
5. Preview sessions expire in 6 hours — always call `_cleanup_preview_session()` in finally blocks
