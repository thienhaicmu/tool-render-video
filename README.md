# Render Studio — Local AI Video Platform

Auto-render, subtitle, score, and upload short-form videos from YouTube or local files.
Runs fully on-device. No cloud API required.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full technical reference.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Full Render Pipeline](#full-render-pipeline)
3. [Editor Workflow](#editor-workflow)
4. [Multi-Part Rendering](#multi-part-rendering)
5. [Realtime Progress UI](#realtime-progress-ui)
6. [Segment Builder & Viral Scoring](#segment-builder--viral-scoring)
7. [Error Logging System](#error-logging-system)
8. [Configuration Reference](#configuration-reference)
9. [Developer Usage](#developer-usage)
10. [API Reference](#api-reference)
11. [Project Structure](#project-structure)
12. [Environment Variables](#environment-variables)
13. [Troubleshooting](#troubleshooting)

---

## Project Overview

Render Studio is a local desktop platform that takes a long-form YouTube video (or local file) and:

1. Downloads or prepares the video
2. Detects scene boundaries
3. Builds candidate short-form segments using a sliding-window algorithm
4. Scores each segment with a multi-factor viral score
5. Renders the top-N segments as separate short-form videos with optional subtitles, motion-aware crop, color grading, and audio processing
6. Exposes all progress in real time through WebSocket + HTTP polling
7. Optionally uploads finished videos to TikTok via Playwright browser automation

There are two primary paths to start a render:

- **Direct render** — submit a payload directly to `/api/render/process`
- **Editor workflow** — prepare the source first via `/api/render/prepare-source`, edit trim/subtitles/text overlays in the browser UI, then submit

The backend is a **FastAPI** Python server. The UI is a single-file HTML dashboard served from the backend. An **Electron** shell wraps it as a desktop app.

---

## Full Render Pipeline

```
YouTube URL / Local File / Editor Session
        │
        ▼
  ┌─────────────┐
  │  source      │  session reuse (editor path) / yt-dlp / direct path
  └──────┬──────┘
         │  source video
         ▼
  ┌──────────────────┐
  │  scene_detector   │  PySceneDetect — cut boundaries, transition scores
  └────────┬─────────┘
           │  scenes[]
           ▼
  ┌──────────────────────┐
  │  segment_builder      │  sliding-window candidate generation
  │  + viral_scorer       │  viral_score v2 + heuristic scoring
  └──────────┬───────────┘
             │  scored_segments[] (sorted by viral_score)
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
```

All pipeline logic lives in `backend/app/orchestration/render_pipeline.py`.
`routes/render.py` is the HTTP boundary only.

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

## Editor Workflow

The editor flow prepares the source before rendering, so the user can preview and configure the video interactively without triggering a full render job.

**High-level steps:**

```
1. POST /api/render/prepare-source
   → downloads (YouTube) or validates (local) the video
   → stores a session at data/temp/preview/{session_id}/
   → returns: { session_id, title, duration, export_dir }

2. Browser opens editor view
   → preview served from GET /api/render/preview-video/{session_id}
   → user configures trim, volume, subtitle style, text overlays

3. User clicks Render
   → payload includes edit_session_id = session_id
   → output_mode forced to 'manual'; export_dir used as output fallback
   → POST /api/render/process

4. Backend finds session → uses session's video_path (no re-download)
   → session is cleaned up after render completes

If session is not found (server restart, temp expired):
   → job fails immediately with: "Editor session not found — please re-open the editor"
   → never silently re-downloads
```

See [doc/editor-flow.md](doc/editor-flow.md) for the full technical reference.

---

## Multi-Part Rendering

### Adaptive concurrency

Worker count is computed automatically from machine capacity at runtime.

```python
cpu_total = os.cpu_count() or 2
mode = encoder_mode   # "cpu" | "nvenc" | "auto"
heavy = motion_aware_crop or add_subtitle or reup_mode

if mode == "cpu":
    hw_cap = max(1, min(3, cpu_total // 4))
else:
    hw_cap = max(1, min(4, cpu_total // 2))

if heavy:
    hw_cap = max(1, hw_cap // 2)

max_workers = hw_cap if user_req == 0 else max(1, min(user_req, hw_cap))
```

**Reference table:**

| CPU cores | Encoder | Pipeline | max_workers |
|---|---|---|---|
| 4 | CPU | any | 1 |
| 8 | CPU | light | 2 |
| 12 | CPU | light | 3 |
| 4 | NVENC | light | 2 |
| 8 | NVENC | heavy | 2 |
| 8 | NVENC | light | 4 |
| 16 | NVENC | light | 4 |

### `max_parallel_parts` behavior

| Value | Behavior |
|---|---|
| `0` (default) | Fully adaptive |
| `1` | Force serial |
| `2+` | User ceiling — backend uses `min(value, hw_cap)` |

---

## Realtime Progress UI

The browser opens a WebSocket to `/api/jobs/{job_id}/ws` immediately after job submission.
Falls back to HTTP polling at 2500ms if WebSocket is unavailable.

Every 500ms the server pushes:

```json
{
  "job": { "job_id": "...", "status": "running", "stage": "rendering_parallel", "progress_percent": 62 },
  "parts": [ { "part_no": 1, "status": "done" }, { "part_no": 2, "status": "rendering" } ],
  "summary": { "total_parts": 8, "completed_parts": 1, "active_parts": [...] }
}
```

Progress never drifts beyond the latest backend value. Terminal states snap immediately.

---

## Segment Builder & Viral Scoring

### Scene detection

`scene_detector.py` runs PySceneDetect. Each scene gets `start`/`end` timestamps and a `transition_score`.

### Segment building

Sliding-window candidate generation:
1. Normalize scenes
2. Generate candidates by expanding windows from each scene
3. Score every candidate with viral_score v2
4. Select non-overlapping segments (greedy, >45% overlap rejected)
5. Drop segments outside `min_part_sec`/`max_part_sec` bounds

### Viral score v2

```
viral_score = (
    hook_strength × 0.25 + avg_scene_quality × 0.20 + scene_density × 0.15
  + pacing_stability × 0.10 + ending_strength × 0.15 + retention_score × 0.15
) − (weak_open_penalty × 0.5 + overlong_penalty × 0.7 + gap_penalty × 0.3)
```

### Heuristic scorer

| Feature | Weight |
|---|---|
| `scene_density` | 28% |
| `duration_score` | 20% (Gaussian peak at 70s) |
| `starts_at_cut` | 14% |
| `pacing_accel` | 9% |
| `position_score` | 8% |
| Others | 21% |

---

## Error Logging System

Three error types with distinct log destinations:

| Type | When | Logged to | Level |
|---|---|---|---|
| **Type 1 — Request** | HTTPException before pipeline starts (bad payload, invalid paths) | `data/logs/request.log` + `desktop-backend.log` | `WARNING` |
| **Type 2 — Pipeline** | Exception inside `run_render_pipeline` (ffmpeg, Whisper, scene detect) | `data/logs/error.log` + `data/logs/app.log` + `channels/{code}/logs/{job_id}.log` | `ERROR` |
| **Type 3 — System** | Unhandled exception in route function | `desktop-backend.log` | `ERROR` |

**Where to look first:**

```
UI shows "Start render failed"  → data/logs/request.log (Type 1)
Job status = "failed"           → data/logs/error.log or job log (Type 2)
Crash / 500 in any route        → desktop-backend.log (Type 3)
Partial render (some parts ok)  → channels/{code}/logs/{job_id}.log
```

### Log locations

| File | Contents |
|---|---|
| `data/logs/request.log` | Type 1: request validation failures (JSON lines) |
| `data/logs/app.log` | All pipeline events from all jobs (JSON lines) |
| `data/logs/error.log` | ERROR/CRITICAL pipeline events only |
| `channels/{code}/logs/{job_id}.log` | Per-job events for a single render |

### Error codes

| Code | Meaning |
|---|---|
| `RN001` | Generic render error |
| `RN002` | File not found |
| `RN003` | Invalid output path / permission |
| `RN004` | ffmpeg process error |
| `RN005` | Scene detection failed |
| `RN006` | Trim / cut operation failed |

### Reading logs

```bash
# Last 120 lines of job log
GET /api/jobs/{job_id}/logs?lines=120

# View formatted error log (desktop-shell)
cd desktop-shell && npm run logerror

# Tail error log directly
Get-Content data\logs\error.log -Tail 50
```

### Log noise suppression

Two filters are active on startup:
- `_SuppressNoisyAccessFilter` on `uvicorn.access` — suppresses `/api/jobs/` polling and `/health` GET noise
- `_SuppressClientDisconnect` on `uvicorn.error` — suppresses harmless preview video disconnect messages

---

## Configuration Reference

### `max_parallel_parts`

| Value | Meaning |
|---|---|
| `0` | Adaptive (recommended) |
| `1` | Force serial |
| `2–6` | User ceiling |

### Encoder mode

| `encoder_mode` | Behavior |
|---|---|
| `auto` | Tries NVENC first, falls back to CPU libx264/libx265 |
| `nvenc` | Forces NVENC; falls back to CPU if not available |
| `cpu` | Forces CPU encode |

### Heavy pipeline flags

| Flag | Effect |
|---|---|
| `motion_aware_crop: true` | Runs OpenCV optical-flow per part |
| `add_subtitle: true` | Runs Whisper + ASS generation per part |
| `reup_mode: true` | Adds extra filters + audio compressor |

When any of these are active, `hw_cap` is halved.

### Render profiles

| Profile | Preset | CRF | Description |
|---|---|---|---|
| `fast` | faster | 22 | Quick preview |
| `balanced` | slow | 18 | Everyday renders |
| `quality` | slower | 15 | High quality |
| `best` | veryslow | 13 | Final masters |

---

## Developer Usage

### Install and run

```powershell
# Clone and setup
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1

# Backend only (browser UI at http://localhost:8000)
.\run-backend.ps1

# Full desktop app (Electron + backend)
.\run-desktop.ps1
```

### Backend dev server

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
    "output_mode": "manual",
    "output_dir": "C:/data/exports/video_output",
    "render_profile": "balanced",
    "max_parallel_parts": 0,
    "add_subtitle": true,
    "encoder_mode": "auto"
  }'
```

### Debug a render

```powershell
# Enable verbose debug logs
$env:RENDER_DEBUG_LOG = "1"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Syntax-check after editing
cd backend
.venv\Scripts\python.exe -m py_compile app/routes/render.py
.venv\Scripts\python.exe -m py_compile app/orchestration/render_pipeline.py
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web dashboard |
| `GET` | `/health` | Health check |
| `GET` | `/api/warmup/status` | Model warmup status |
| `POST` | `/api/render/prepare-source` | Download/validate source; creates editor session. Returns `session_id`, `title`, `duration`, `export_dir` |
| `GET` | `/api/render/preview-video/{session_id}` | Stream H.264 preview for editor |
| `POST` | `/api/render/process` | Submit render job |
| `POST` | `/api/render/process/batch` | Batch render (multiple YouTube URLs) |
| `POST` | `/api/render/resume/{job_id}` | Resume interrupted job |
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
| `POST` | `/api/upload/login/start` | Start TikTok login |
| `POST` | `/api/upload/schedule` | Run upload plan |
| `WS` | `/api/upload/{run_id}/ws` | Realtime upload progress |

---

## Project Structure

```
render-studio/
├── backend/
│   ├── app/
│   │   ├── main.py                        # FastAPI app, startup hooks, log filters
│   │   ├── core/
│   │   │   ├── config.py                  # Paths, env vars, directory setup
│   │   │   └── stage.py                   # JobStage, JobPartStage, STAGE_TO_EVENT enums
│   │   ├── models/schemas.py              # Pydantic request/response models
│   │   ├── orchestration/
│   │   │   └── render_pipeline.py         # All render pipeline logic (run_render_pipeline)
│   │   ├── routes/
│   │   │   ├── render.py                  # HTTP boundary only — thin wrapper over orchestration
│   │   │   ├── jobs.py                    # Job status, WebSocket, progress summary
│   │   │   ├── upload.py                  # TikTok upload API
│   │   │   ├── channels.py                # Channel CRUD
│   │   │   └── devtools.py                # Dev/maintenance endpoints
│   │   └── services/
│   │       ├── render_engine.py           # ffmpeg pipeline (cut_video, render_part_smart)
│   │       ├── motion_crop.py             # OpenCV optical-flow motion-aware crop
│   │       ├── subtitle_engine.py         # Whisper transcription + ASS subtitle generation
│   │       ├── segment_builder.py         # Sliding-window segment builder + viral_score v2
│   │       ├── viral_scorer.py            # Heuristic + ML-ready viral scoring
│   │       ├── scene_detector.py          # PySceneDetect wrapper
│   │       ├── downloader.py              # yt-dlp YouTube download with retry fallback
│   │       ├── text_overlay.py            # Text layer filter builder + VALID_FONTS
│   │       ├── job_manager.py             # Background ThreadPoolExecutor job queue
│   │       ├── upload_engine.py           # Playwright TikTok upload automation
│   │       ├── report_service.py          # Excel render report writer
│   │       ├── db.py                      # SQLite (jobs, parts, channels)
│   │       ├── warmup.py                  # Startup model preload
│   │       ├── bin_paths.py               # ffmpeg/ffprobe path resolver
│   │       ├── channel_service.py         # Channel folder management
│   │       └── maintenance.py             # Log pruning, preview dir cleanup
│   ├── static/
│   │   └── index.html                     # Single-file web UI dashboard
│   ├── fonts/                             # Bundled subtitle fonts (Bungee, etc.)
│   └── requirements.txt
├── desktop-shell/
│   ├── main.js                            # Electron main process
│   └── package.json
├── channels/                              # Per-channel workspaces (auto-created)
├── data/
│   ├── app.db                             # SQLite database
│   ├── temp/
│   │   └── preview/                       # Editor session temp files (auto-cleaned, max 6h)
│   ├── reports/                           # Excel render reports
│   └── logs/
│       ├── request.log                    # Type 1: request validation errors (JSON lines)
│       ├── app.log                        # All pipeline events (JSON lines)
│       └── error.log                      # ERROR/CRITICAL events only
├── doc/
│   ├── editor-flow.md                     # Editor workflow technical reference
│   ├── project-context.md
│   └── engineering-standards.md
├── cowork/
│   ├── COWORK_SYSTEM_DEFINITION.md        # System definition for AI tools
│   ├── HUONG_DAN_SU_DUNG_COWORK.md        # Vietnamese operator guide
│   └── business-profile.md               # Product and operator profile
└── ARCHITECTURE.md                        # Full technical architecture reference
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
| Whisper slow on first run | Downloading models (~700 MB). Watch `/api/warmup/status`. |
| Electron blank screen | Backend must be running on port 8000 first |
| Parts render sequentially | `max_parallel_parts` was `1`. Send `0` for adaptive. |
| Job fails "Editor session not found" | Session expired or server restarted. Re-open the editor. |
| Preview video won't play | Codec not H.264. Transcode timeout? Check `data/logs/app.log`. |
| TikTok upload fails | Run login first. TikTok selectors change periodically. |
| Port 8000 in use | `$env:PORT=8001` then restart |
