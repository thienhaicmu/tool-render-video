# Render Studio — Local AI Video Platform

Auto-render, subtitle, score, and upload short-form videos from YouTube or local files.  
Runs fully on-device. No cloud API required.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Full Render Pipeline](#full-render-pipeline)
3. [Multi-Part Rendering](#multi-part-rendering)
4. [Realtime Progress UI](#realtime-progress-ui)
5. [Segment Builder & Viral Scoring](#segment-builder--viral-scoring)
6. [Error Logging System](#error-logging-system)
7. [Configuration Reference](#configuration-reference)
8. [Developer Usage](#developer-usage)
9. [API Reference](#api-reference)
10. [Project Structure](#project-structure)
11. [Environment Variables](#environment-variables)
12. [Troubleshooting](#troubleshooting)
13. [Future Improvements](#future-improvements)

---

## Project Overview

Render Studio is a local desktop platform that takes a long-form YouTube video (or local file) and:

1. Downloads the video
2. Detects scene boundaries
3. Builds candidate short-form segments using a sliding-window algorithm
4. Scores each segment with a multi-factor viral score
5. Renders the top-N segments as separate short-form videos with optional subtitles, motion-aware crop, color grading, and audio processing
6. Exposes all progress in real time through WebSocket + HTTP polling
7. Optionally uploads finished videos to TikTok via Playwright browser automation

The backend is a **FastAPI** Python server. The UI is a single-file HTML dashboard served from the backend. An optional **Electron** shell wraps it as a desktop app.

---

## Full Render Pipeline

```
YouTube URL / Local File
        │
        ▼
  ┌─────────────┐
  │  downloader  │  yt-dlp (YouTube) or direct path (local)
  └──────┬──────┘
         │  source video
         ▼
  ┌──────────────────┐
  │  scene_detector   │  PySceneDetect — finds cut boundaries, transition scores
  └────────┬─────────┘
           │  scenes[]
           ▼
  ┌──────────────────────┐
  │  segment_builder      │  sliding-window candidate generation
  │  + viral_scorer       │  viral_score v2 + heuristic/ML scoring
  └──────────┬───────────┘
             │  scored_segments[] (sorted by viral_score)
             │  → top-N selected, high-motion filter applied
             │
             ▼
  ┌───────────────────────────────────────────┐
  │  ThreadPoolExecutor (adaptive max_workers) │
  │                                           │
  │  Part 1 ──► cut_video ──► subtitle ──► render_part_smart  ──► part_001.mp4
  │  Part 2 ──► cut_video ──► subtitle ──► render_part_smart  ──► part_002.mp4
  │  Part N ──► cut_video ──► subtitle ──► render_part_smart  ──► part_N.mp4
  └──────────────────────────┬────────────────┘
                             │
                             ▼
                    output_dir / *.mp4
                    render_report.xlsx
                             │
                             ▼
              ┌──────────────────────────────┐
              │  WebSocket / HTTP Polling     │
              │  /api/jobs/{id}/ws            │
              │  → job status + parts[]       │
              │  → summary (active_parts,     │
              │     overall_progress, etc.)   │
              └──────────────┬───────────────┘
                             │
                             ▼
                     Browser UI (index.html)
                     Live Part Tracking panel
                     Smooth progress bars
```

### Per-part stages

| Stage | Description |
|---|---|
| `queued` | Scheduled, not yet started |
| `cutting` | `ffmpeg` stream-copy to isolate raw segment |
| `transcribing` | Whisper slice from pre-built full-SRT |
| `rendering` | `ffmpeg` full encode: crop, color, subtitle, speed, codec |
| `done` | Final `.mp4` written to output dir |
| `failed` | Error — see job log |

---

## Multi-Part Rendering

### Adaptive concurrency

Worker count is computed automatically from machine capacity at runtime — no manual tuning required.

```python
# render.py — process_render()

cpu_total = os.cpu_count() or 2
mode = encoder_mode   # "cpu" | "nvenc" | "auto"
heavy = motion_aware_crop or add_subtitle or reup_mode

# Hardware cap
if mode == "cpu":
    hw_cap = max(1, min(3, cpu_total // 4))   # 1 per 4 cores, max 3
else:                                          # nvenc / auto
    hw_cap = max(1, min(4, cpu_total // 2))   # 1 per 2 cores, max 4

# Heavy pipeline halves the cap (motion crop is CPU-intensive per part)
if heavy:
    hw_cap = max(1, hw_cap // 2)

# max_parallel_parts == 0  → fully adaptive (use hw_cap)
# max_parallel_parts >= 1  → user ceiling, capped by hw_cap
max_workers = hw_cap if user_req == 0 else max(1, min(user_req, hw_cap))
```

**Reference table (typical machines):**

| CPU cores | Encoder | Pipeline | max_workers |
|---|---|---|---|
| 4 | CPU | any | 1 |
| 8 | CPU | light | 2 |
| 12 | CPU | light | 3 |
| 4 | NVENC | light | 2 |
| 8 | NVENC | heavy | 2 |
| 8 | NVENC | light | 4 |
| 16 | NVENC | light | 4 |

### Execution model

When `max_workers > 1`, all part futures are **submitted before any result is awaited**:

```python
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    for idx, seg in enumerate(scored, start=1):
        future_map[executor.submit(_process_one_part, idx, seg)] = idx

    for future in as_completed(future_map):   # harvest as each finishes
        result = future.result()
```

This is true parallelism — parts execute simultaneously up to `max_workers`.  
When `max_workers == 1`, a sequential `for` loop is used (no executor overhead).

### Shared state safety

- Per-part files are uniquely named (`slug_part_001_raw.mp4`, etc.) — no file collisions
- `full_srt` is written once before the part loop and read-only during parallel phase
- `upsert_job_part` DB writes serialize at SQLite level (progress-only, never blocking render)

### `max_parallel_parts` behavior

| Value | Behavior |
|---|---|
| `0` (default) | Fully adaptive — backend selects based on CPU + pipeline |
| `1` | Force serial — exactly 1 worker regardless of hardware |
| `2+` | User ceiling — backend uses `min(user_value, hw_cap)` |

Set in the editor UI or in the API payload field `max_parallel_parts`.

---

## Realtime Progress UI

### Transport

The browser opens a WebSocket to `/api/jobs/{job_id}/ws` immediately after a job is submitted.  
If the WebSocket fails (proxy, firewall), it falls back gracefully to HTTP polling at 2500ms intervals.

```
Browser
  │
  ├─ WebSocket /api/jobs/{id}/ws        (preferred, 500ms tick)
  │    ↓ JSON: { job, parts[], summary }
  │
  └─ HTTP GET /api/jobs/{id}            (fallback polling, 2500ms)
     HTTP GET /api/jobs/{id}/parts
```

### WebSocket payload

Every 500ms the server pushes:

```json
{
  "job": {
    "job_id": "...",
    "status": "running",
    "stage": "rendering_parallel",
    "progress_percent": 62,
    "message": "Processed 3/8 parts"
  },
  "parts": [
    { "part_no": 1, "status": "done",       "progress_percent": 100, ... },
    { "part_no": 2, "status": "rendering",  "progress_percent": 70,  ... },
    { "part_no": 3, "status": "cutting",    "progress_percent": 10,  ... },
    { "part_no": 4, "status": "queued",     "progress_percent": 0,   ... }
  ],
  "summary": {
    "total_parts": 8,
    "completed_parts": 1,
    "failed_parts": 0,
    "pending_parts": 5,
    "processing_parts": 2,
    "active_parts": [
      { "part_no": 2, "status": "rendering", "progress_percent": 70 },
      { "part_no": 3, "status": "cutting",   "progress_percent": 10 }
    ],
    "overall_progress_percent": 27.5,
    "parts_percent": 27.5,
    "current_part": 2,
    "current_stage": "rendering"
  }
}
```

### Multiple active parts

When `processing_parts > 1`, the **Live Part Tracking** panel shows:

- An **Active Parts Bar** at the top with one chip per concurrent part (color-coded by stage)
- A `"N parallel"` badge when multiple parts are rendering simultaneously
- Per-part progress cards with animated fill bars (stage-colored: amber=cutting, purple=transcribing, blue→green=rendering)
- A pulsing glow on all active cards

### Smooth progress interpolation

Backend remains the source of truth. The UI animates toward backend values:

```js
// _partTarget[partNo] = backend value (updated every WS tick)
// _partDisplay[partNo] = visually displayed value (eased toward target)

function _easeToward(current, target, maxStep) {
  const diff = target - current;
  const step = Math.min(maxStep, Math.max(0.3, diff * 0.08));
  return Math.min(target, current + step);
}

// requestAnimationFrame loop eases display toward target
// Done/failed parts snap to final value immediately
// Job-level bar eases at 1.5%/frame, part bars at 2%/frame
```

Progress never drifts beyond the latest backend value. Terminal states (done/failed) snap immediately.

### Job-level overall progress

The job-level `%` bar is derived from parts aggregate during the rendering stage:

```
overall % = 30 + (parts_mean_percent / 100) × 60   [clamped to 30–90]
```

Pre-render stages (download, scene detect, segment build) occupy 0–30%.  
Report writing occupies 90–100%.

---

## Segment Builder & Viral Scoring

### Scene detection

`scene_detector.py` runs PySceneDetect on the source video. Each scene gets:
- `start` / `end` timestamps
- `transition_score` — strength of the cut (used in segment quality)

### Segment building (`segment_builder.py`)

Uses a **sliding-window candidate generation** algorithm:

1. **Normalize scenes** — sort, clamp to video duration, fill gaps
2. **Score each scene** — `scene_quality` from duration fit, transition strength, position bonus
3. **Generate candidates** — for every scene as a start point, expand the window until `max_part_sec` is exceeded; emit a candidate at each step where duration ≥ `min_part_sec`
4. **Score every candidate** — compute `viral_score v2` (see below)
5. **Select non-overlapping** — greedy selection by score, reject candidates with > 45% overlap with an already-selected segment
6. **Enforce hard bounds** — drop segments below `min_part_sec`, clamp above `max_part_sec`
7. **Fallback** — if nothing passes, emit one segment covering `[0, max_part_sec]`

**`min_part_sec` / `max_part_sec`** (defaults: 70s / 180s) are hard boundaries.  
The algorithm never produces a segment outside this range.

### Viral score v2 (`segment_builder.py` — `_score_candidate`)

```
viral_score = (
    hook_strength     × 0.25   # quality of the first scene
  + avg_scene_quality × 0.20   # mean quality across all scenes in window
  + scene_density     × 0.15   # cuts/sec (pacing)
  + pacing_stability  × 0.10   # low standard deviation in scene durations
  + ending_strength   × 0.15   # quality of the last scene
  + retention_score   × 0.15   # pacing_stability × 0.6 + gap-free × 0.4
) − (
    weak_open_penalty × 0.5    # hook_strength < 40
  + overlong_penalty  × 0.7    # segment exceeds max_len
  + gap_penalty       × 0.3    # timeline gaps inside segment
)
```

All sub-scores are in `[0, 100]`. Final `viral_score` is clamped to `[0, 100]`.

### Heuristic scorer (`viral_scorer.py`)

After segment building, `score_segments()` re-scores each segment with a **position-aware heuristic** optimized for TikTok content patterns:

| Feature | Weight | Notes |
|---|---|---|
| `scene_density` | 28% | Fast pacing matters most |
| `duration_score` | 20% | Gaussian peak at 70s, σ=20s |
| `starts_at_cut` | 14% | Strong hook = starts at a cut boundary |
| `pacing_accel` | 9% | Scene cuts accelerating toward the end |
| `position_score` | 8% | Earlier segments slightly favored |
| `n_scenes_norm` | 6% | Scene count |
| `scene_quality` | 6% | Visual quality signal |
| `ends_at_cut` | 5% | Clean ending |
| `is_first` | 2% | First segment bonus |
| `is_second` | 2% | Second segment bonus |

### ML scorer (optional)

If enough real performance feedback is recorded (≥30 samples), a Ridge regression model is trained and replaces the heuristic:

```python
from app.services.viral_scorer import record_feedback, train_model

# After a video is posted and metrics are available:
record_feedback(segment._features, views=145000, likes=8200)

# Once 30+ records exist:
status = train_model()   # trains sklearn Ridge on views/likes proxy target
```

Model is persisted at `data/viral_model.pkl` and auto-loaded on restart.

---

## Error Logging System

All render events are written to structured log files.

### Log locations

| File | Contents | Purpose |
|---|---|---|
| `channels/{code}/logs/{job_id}.log` | Per-job structured JSON events | Trace a single render from start to finish |
| `data/logs/app.log` | All events from all jobs | Full audit trail across all channels |
| `data/logs/error.log` | `ERROR` / `CRITICAL` events only | Quick error triage without noise |

Each log entry is a JSON line:

```json
{
  "timestamp": "2025-04-16T10:32:01Z",
  "level": "ERROR",
  "event": "render.ffmpeg.error",
  "module": "render",
  "message": "ffmpeg encode failed on part 3",
  "job_id": "abc123",
  "step": "rendering",
  "error_code": "RN004",
  "context": { "part_no": 3 },
  "exception": "CalledProcessError: ...",
  "traceback": "..."
}
```

### Error codes

| Code | Meaning |
|---|---|
| `RN001` | Generic render error |
| `RN002` | File not found |
| `RN003` | Invalid output path / permission |
| `RN004` | ffmpeg process error |
| `RN005` | Scene detection failed |
| `RN006` | Trim / cut operation failed |

### Reading logs via API

```bash
# Last 120 lines of job log
GET /api/jobs/{job_id}/logs?lines=120

# Response: { job_id, log_file, items: [...lines] }
```

### Debugging a failed job

```bash
# 1. Get job detail
curl http://localhost:8000/api/jobs/{job_id}

# 2. Read log
curl "http://localhost:8000/api/jobs/{job_id}/logs?lines=200"

# 3. View formatted error log (desktop-shell)
cd desktop-shell && npm run logerror

# 4. Tail error log directly
Get-Content data\logs\error.log -Tail 50
```

---

## Configuration Reference

### `max_parallel_parts`

Controls how many parts render simultaneously within a single job.

| Value | Meaning |
|---|---|
| `0` | Adaptive — backend auto-selects based on CPU + pipeline (recommended) |
| `1` | Force serial — safe on any machine |
| `2–6` | User ceiling — backend uses `min(value, hw_cap)` |

Set via API payload or editor UI. Default: `0` (adaptive).

### Encoder mode

| `encoder_mode` | Behavior |
|---|---|
| `auto` | Tries NVENC first, falls back to CPU libx264/libx265 |
| `nvenc` | Forces NVENC; falls back to CPU if not available |
| `cpu` | Forces CPU encode (libx264/libx265) |

Affects both render quality settings and `hw_cap` for parallel workers.

### Heavy pipeline flags

These flags lower the adaptive worker cap:

| Flag | Effect |
|---|---|
| `motion_aware_crop: true` | Runs OpenCV optical-flow analysis per part (CPU heavy) |
| `add_subtitle: true` | Runs Whisper + ASS generation per part |
| `reup_mode: true` | Adds extra video filters + audio compressor |

When any of these are active, `hw_cap` is halved to avoid CPU saturation.

### Render profiles

| Profile | Preset | CRF | Whisper | Description |
|---|---|---|---|---|
| `fast` | faster | 22 | tiny | Quick preview |
| `balanced` | slow | 18 | base | Everyday renders |
| `quality` | slower | 15 | small | High quality |
| `best` | veryslow | 13 | small | Final masters |

---

## Developer Usage

### Install and run

```powershell
# Clone
git clone <repo-url> render-studio
cd render-studio

# One-click setup (venv, pip, playwright, node)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1

# Run backend only (browser UI at http://localhost:8000)
.\run-backend.ps1

# Run full desktop app (Electron + backend)
.\run-desktop.ps1
```

### Backend dev server (hot-reload)

```powershell
cd backend
.venv\Scripts\activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Trigger a render job

```bash
curl -X POST http://localhost:8000/api/render/process \
  -H "Content-Type: application/json" \
  -d '{
    "source_mode": "youtube",
    "youtube_url": "https://youtube.com/watch?v=EXAMPLE",
    "channel_code": "T1",
    "output_dir": "C:/data/channels/T1/upload/video_output",
    "render_output_subdir": "upload/video_output",
    "render_profile": "balanced",
    "max_parallel_parts": 0,
    "add_subtitle": true,
    "motion_aware_crop": true,
    "encoder_mode": "auto",
    "max_export_parts": 5
  }'
```

### Observe realtime progress

```bash
# WebSocket (preferred)
wscat -c ws://localhost:8000/api/jobs/{job_id}/ws

# HTTP polling
watch -n 2 "curl -s http://localhost:8000/api/jobs/{job_id}/parts | python -m json.tool"

# Job log tail
curl "http://localhost:8000/api/jobs/{job_id}/logs?lines=50"
```

### Debug a render

```powershell
# Enable verbose debug logs
$env:RENDER_DEBUG_LOG = "1"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Syntax-check services after editing
cd backend
.venv\Scripts\python.exe -m py_compile app/routes/render.py
.venv\Scripts\python.exe -m py_compile app/services/render_engine.py
.venv\Scripts\python.exe -m py_compile app/services/segment_builder.py

# Confirm ffmpeg is accessible
.venv\Scripts\python.exe -c "from app.services.bin_paths import get_ffmpeg_bin; print(get_ffmpeg_bin())"
```

### Build distributable

```powershell
# Backend exe only
.\build-backend.bat

# Full desktop app (Electron + backend exe)
.\build-desktop.ps1

# Offline portable (no Python required)
.\build-offline-exe.ps1
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web dashboard |
| `GET` | `/health` | Health check |
| `GET` | `/api/warmup/status` | Model warmup status |
| `POST` | `/api/render/prepare-source` | Download / validate source, open editor |
| `POST` | `/api/render/process` | Submit render job |
| `POST` | `/api/render/process/batch` | Batch render (multiple YouTube URLs) |
| `POST` | `/api/render/resume/{job_id}` | Resume interrupted job |
| `GET` | `/api/render/preview-video/{session_id}` | Stream H.264 preview for editor |
| `POST` | `/api/render/upload-local` | Upload local video from browser |
| `POST` | `/api/render/download-health` | Check YouTube URL health |
| `POST` | `/api/render/quick-process` | One-shot download + transcode |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/{job_id}` | Job detail |
| `GET` | `/api/jobs/{job_id}/parts` | Job parts detail |
| `GET` | `/api/jobs/{job_id}/logs` | Job log tail |
| `WS` | `/api/jobs/{job_id}/ws` | Realtime job progress stream |
| `GET` | `/api/channels` | List channels |
| `POST` | `/api/channels` | Create channel |
| `POST` | `/api/upload/login/start` | Start TikTok login (browser) |
| `POST` | `/api/upload/schedule` | Run upload plan |
| `WS` | `/api/upload/{run_id}/ws` | Realtime upload progress |

---

## Project Structure

```
render-studio/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI app + startup
│   │   ├── core/config.py            # Paths, env vars
│   │   ├── models/schemas.py         # Pydantic request/response models
│   │   ├── routes/
│   │   │   ├── render.py             # Render API + process_render orchestrator
│   │   │   ├── jobs.py               # Job status, WebSocket, progress summary
│   │   │   ├── upload.py             # TikTok upload API
│   │   │   ├── channels.py           # Channel CRUD
│   │   │   └── devtools.py           # Dev/maintenance endpoints
│   │   └── services/
│   │       ├── render_engine.py      # ffmpeg pipeline (cut_video, render_part_smart)
│   │       ├── motion_crop.py        # OpenCV optical-flow motion-aware crop
│   │       ├── subtitle_engine.py    # Whisper transcription + ASS subtitle generation
│   │       ├── segment_builder.py    # Sliding-window segment builder + viral_score v2
│   │       ├── viral_scorer.py       # Heuristic + ML viral scoring + feedback loop
│   │       ├── scene_detector.py     # PySceneDetect wrapper
│   │       ├── downloader.py         # yt-dlp YouTube download
│   │       ├── job_manager.py        # Background ThreadPoolExecutor job queue
│   │       ├── upload_engine.py      # Playwright TikTok upload automation
│   │       ├── caption_engine.py     # AI caption (Ollama / Claude / template)
│   │       ├── report_service.py     # Excel render report writer
│   │       ├── db.py                 # SQLite (jobs, parts, channels)
│   │       ├── warmup.py             # Startup model preload
│   │       ├── bin_paths.py          # ffmpeg/ffprobe path resolver
│   │       ├── channel_service.py    # Channel folder management
│   │       ├── text_overlay.py       # Custom text layer filter builder
│   │       └── maintenance.py        # Log pruning
│   ├── static/
│   │   └── index.html                # Single-file web UI dashboard
│   ├── fonts/                        # Bundled subtitle fonts (Bungee, etc.)
│   ├── run_backend_server.py         # uvicorn entry point
│   └── requirements.txt
├── desktop-shell/
│   ├── main.js                       # Electron main process
│   └── package.json
├── channels/                         # Per-channel workspaces (auto-created)
├── data/
│   ├── app.db                        # SQLite database
│   ├── temp/                         # Temp render files (auto-cleaned)
│   ├── reports/                      # Excel render reports
│   ├── logs/
│   │   ├── app.log                   # All structured events (JSON lines)
│   │   └── error.log                 # Error/critical events only
│   ├── viral_feedback.jsonl          # ML training data (views/likes)
│   └── viral_model.pkl               # Trained Ridge model (if present)
├── setup.ps1
├── run-backend.ps1
├── run-desktop.ps1
├── build-backend.bat
├── build-desktop.ps1
└── build-offline-exe.ps1
```

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8000` | Server port |
| `FFMPEG_BIN` | auto-detect | Path to `ffmpeg.exe` |
| `FFPROBE_BIN` | auto-detect | Path to `ffprobe.exe` |
| `APP_DATA_DIR` | `./data` | Database + temp + reports root |
| `DATABASE_PATH` | `./data/app.db` | SQLite database file |
| `CHANNELS_DIR` | `./channels` | Channel workspaces root |
| `TEMP_DIR` | `./data/temp` | Temp render files |
| `REPORTS_DIR` | `./data/reports` | Excel reports output |
| `RENDER_DEBUG_LOG` | `0` | Set to `1` to enable verbose render debug logging |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API for captions |
| `OLLAMA_MODEL` | `llama3.2:3b` | Ollama model name |
| `LOG_KEEP_LAST` | `30` | Keep N latest log files per channel |
| `LOG_KEEP_DAYS` | `10` | Delete logs older than N days |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ffmpeg not found` | `winget install -e --id Gyan.FFmpeg` or set `FFMPEG_BIN` |
| `ModuleNotFoundError` | `cd backend && .venv\Scripts\pip install -r requirements.txt` |
| Whisper slow on first run | Normal — downloading models (~700 MB). Watch warmup endpoint. |
| Electron blank screen | Backend must be running on port 8000 first |
| Parts render sequentially | `max_parallel_parts` was `1`. Send `0` to enable adaptive mode. |
| Only one active part shown | UI uses `active_parts[]` array — check browser console for WS data. |
| TikTok upload fails | Run login first. TikTok selectors change periodically. |
| `.exe` closes immediately | Run from terminal: `cd backend\dist && render-backend.exe` |
| Build fails (antivirus) | Add `backend\dist\` to AV exclusion list |
| Port 8000 in use | `$env:PORT=8001` then restart |

---

## Future Improvements

- **Data-driven viral scoring** — collect real TikTok views/likes via `record_feedback()` and run `train_model()` to replace the heuristic with a Ridge regression model trained on your actual audience data.
- **GPU acceleration** — motion-aware crop currently runs on CPU (OpenCV). A CUDA-backed optical flow pass would reduce per-part processing time significantly on NVENC machines.
- **Distributed rendering** — the job queue (`job_manager.py`) is single-machine. A Celery + Redis backend would allow distributing parts across multiple machines while keeping the same API surface.
- **Part-level retry** — currently a failed part marks itself `failed` and the job continues. Per-part automatic retry with back-off would improve reliability on flaky ffmpeg environments.
- **Subtitle language detection** — Whisper already supports `language=auto`. Exposing per-segment language detection in the UI would enable multilingual channels.
