# Render Studio — Local AI Video Platform

Auto render, subtitle, score, and upload short-form videos from YouTube or local files.

---

## Requirements

| Tool | Version | Note |
|------|---------|------|
| Python | 3.11+ | [python.org](https://www.python.org/downloads/) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org/) |
| ffmpeg | 6+ | `winget install -e --id Gyan.FFmpeg` |
| Git | any | [git-scm.com](https://git-scm.com/) |

---

## Quick Start

### 1. Clone and Setup

```powershell
git clone <repo-url> pc_video_platform_full
cd pc_video_platform_full

# Auto-install everything (venv, pip deps, playwright, node_modules)
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

What `setup.ps1` does:
- Creates `backend/.venv` with Python 3.11+
- Installs `backend/requirements.txt` (FastAPI, Whisper, OpenCV, yt-dlp, etc.)
- Installs Playwright Chromium browser (for TikTok upload)
- Installs `desktop-shell/node_modules` (Electron)

### 2. Run the App

**Option A — Desktop app (Electron + Backend):**
```powershell
.\run-desktop.ps1
```

**Option B — Backend only (browser UI):**
```powershell
.\run-backend.ps1
```
Then open: http://localhost:8000

**Option C — Manual start (separate terminals):**
```powershell
# Terminal 1: Backend
cd backend
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# Terminal 2: Desktop shell (optional)
cd desktop-shell
npm start
```

**Option D — Docker:**
```powershell
docker compose up -d --build
```

---

## Build Portable EXE

### Backend only (.exe)

```powershell
.\build-backend.bat            # Build normally
.\build-backend.bat clean      # Clean old artifacts first
.\build-backend.bat debug      # Build with debug output
```

Output: `backend\dist\render-backend.exe`

Run the built exe:
```powershell
cd backend\dist
.\render-backend.exe
# Open http://localhost:8000
```

### Full Desktop app (Electron + Backend .exe)

```powershell
.\build-desktop.ps1
```

Output: `desktop-shell\dist\` (portable .exe)

### Offline portable (bundle everything)

```powershell
.\build-offline-exe.ps1
```

Packages backend .exe into Electron app for distribution without Python.

---

## Common Commands

### Backend development

```powershell
# Activate venv
cd backend
.venv\Scripts\activate

# Install new dependency
pip install <package>
pip freeze > requirements.txt

# Run server with hot-reload
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Syntax check all services
python -m py_compile app/services/render_engine.py
python -m py_compile app/services/motion_crop.py
python -m py_compile app/services/subtitle_engine.py

# Check ffmpeg is available
python -c "from app.services.bin_paths import get_ffmpeg_bin; print(get_ffmpeg_bin())"
```

### Channel management

```powershell
# Create channel via API
curl -X POST http://localhost:8000/api/channels -H "Content-Type: application/json" -d "{\"channel_code\": \"my_channel\"}"

# List channels
curl http://localhost:8000/api/channels
```

### Render jobs

```powershell
# Start render from YouTube URL
curl -X POST http://localhost:8000/api/render/process ^
  -H "Content-Type: application/json" ^
  -d "{\"source_mode\": \"youtube\", \"youtube_url\": \"https://youtube.com/watch?v=xxx\", \"channel_code\": \"T1\", \"render_profile\": \"balanced\"}"

# Check job status
curl http://localhost:8000/api/jobs
curl http://localhost:8000/api/jobs/<job_id>
curl http://localhost:8000/api/jobs/<job_id>/parts

# Resume failed job
curl -X POST http://localhost:8000/api/render/resume/<job_id>
```

### Upload to TikTok

```powershell
# Step 1: Login (opens browser for manual login)
curl -X POST http://localhost:8000/api/upload/login/start ^
  -H "Content-Type: application/json" ^
  -d "{\"channel_code\": \"T1\", \"account_key\": \"default\"}"

# Step 2: Schedule upload
curl -X POST http://localhost:8000/api/upload/schedule ^
  -H "Content-Type: application/json" ^
  -d "{\"channel_code\": \"T1\", \"dry_run\": true, \"max_items\": 2}"
```

### Cleanup and maintenance

```powershell
# Clean temp render files
curl -X POST http://localhost:8000/api/jobs/cleanup ^
  -H "Content-Type: application/json" ^
  -d "{\"keep_last\": 30, \"older_than_days\": 10}"

# Clean __pycache__ manually
Get-ChildItem -Path backend\app -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force

# Clean old build artifacts
Remove-Item -Recurse -Force backend\build, backend\dist -ErrorAction SilentlyContinue
```

### Playwright (TikTok upload browser)

```powershell
cd backend
.venv\Scripts\python.exe -m playwright install chromium    # Install browser
.venv\Scripts\python.exe -m playwright install-deps        # Install system deps
```

---

## Project Structure

```
pc_video_platform_full/
  backend/
    app/
      main.py                   # FastAPI app entry point
      core/config.py            # Paths, env config
      models/schemas.py         # Pydantic request/response models
      routes/
        render.py               # Render API endpoints
        upload.py               # Upload API endpoints
        jobs.py                 # Job status + WebSocket
        channels.py             # Channel CRUD
      services/
        render_engine.py        # ffmpeg render pipeline
        motion_crop.py          # OpenCV motion-aware crop
        subtitle_engine.py      # Whisper transcribe + ASS subtitle
        downloader.py           # yt-dlp download
        scene_detector.py       # scenedetect scene split
        segment_builder.py      # Smart segment builder
        viral_scorer.py         # Viral score heuristic
        upload_engine.py        # Playwright TikTok upload
        caption_engine.py       # AI caption (Ollama/Claude/template)
        report_service.py       # Excel report writer
        job_manager.py          # Background job queue
        warmup.py               # Startup model preload
        db.py                   # SQLite operations
        bin_paths.py            # ffmpeg/ffprobe path resolver
        channel_service.py      # Channel folder management
        maintenance.py          # Log cleanup
    static/                     # Web UI (index.html, favicon, icons)
    fonts/                      # Bungee-Regular.ttf (subtitle font)
    run_backend_server.py       # uvicorn entry point
    requirements.txt
  desktop-shell/
    main.js                     # Electron main process
    package.json
    build/                      # App icons (icon.ico, icon.png)
  channels/                     # Channel workspaces (per-channel data)
  data/
    app.db                      # SQLite database
    temp/                       # Temp render files (auto-cleaned)
    reports/                    # Excel reports
  setup.ps1                     # One-click install
  run-backend.ps1               # Start backend server
  run-desktop.ps1               # Start Electron desktop app
  build-backend.bat             # Build backend .exe (PyInstaller)
  build-desktop.ps1             # Build full desktop app
  build-offline-exe.ps1         # Build offline portable
  FEATURES_SUMMARY.md           # Full feature list
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web dashboard |
| `GET` | `/health` | Health check |
| `GET` | `/api/warmup/status` | Model loading status |
| `GET` | `/api/channels` | List channels |
| `POST` | `/api/channels` | Create channel |
| `GET` | `/api/channels/{code}` | Channel detail |
| `POST` | `/api/render/process` | Start render job |
| `POST` | `/api/render/process/batch` | Batch render (multi-URL) |
| `POST` | `/api/render/resume/{job_id}` | Resume failed job |
| `POST` | `/api/render/upload-local` | Upload local video file |
| `POST` | `/api/render/download-health` | Check YouTube URL health |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/jobs/{job_id}` | Job detail |
| `GET` | `/api/jobs/{job_id}/parts` | Job parts detail |
| `WS` | `/api/jobs/{job_id}/ws` | Realtime job progress |
| `POST` | `/api/upload/login/start` | Start TikTok login |
| `POST` | `/api/upload/schedule` | Run upload plan |
| `WS` | `/api/upload/{run_id}/ws` | Realtime upload progress |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HOST` | `127.0.0.1` | Server bind address |
| `PORT` | `8000` | Server port |
| `FFMPEG_BIN` | auto-detect | Path to ffmpeg.exe |
| `FFPROBE_BIN` | auto-detect | Path to ffprobe.exe |
| `APP_DATA_DIR` | `./data` | Database + temp + reports root |
| `DATABASE_PATH` | `./data/app.db` | SQLite database file |
| `CHANNELS_DIR` | `./channels` | Channel workspaces root |
| `TEMP_DIR` | `./data/temp` | Temp render files |
| `REPORTS_DIR` | `./data/reports` | Excel reports output |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API URL |
| `OLLAMA_MODEL` | `llama3.2:3b` | Ollama model for captions |
| `LOG_KEEP_LAST` | `30` | Keep N latest logs per channel |
| `LOG_KEEP_DAYS` | `10` | Delete logs older than N days |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ffmpeg not found` | `winget install -e --id Gyan.FFmpeg` or set `FFMPEG_BIN` env |
| `ModuleNotFoundError` | `cd backend && .venv\Scripts\pip install -r requirements.txt` |
| Whisper slow on first run | Normal — downloads models (~700MB). Wait for warmup. |
| Electron blank screen | Backend must be running on port 8000 first |
| TikTok upload fails | Run login first. Selectors may change with TikTok updates. |
| `.exe` closes immediately | Run from cmd to see error: `cd backend\dist && render-backend.exe` |
| Build fails (antivirus) | Add `backend\dist\` to AV exclusion list |
| Port 8000 in use | Set env: `$env:PORT=8001` then run again |
