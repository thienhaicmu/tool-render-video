# Render Studio — Local AI Video Platform

Auto-render, subtitle, score, and upload short-form videos from YouTube or local files.  
Runs fully on-device. No cloud API required.

---

## What it does

| Step | Feature |
|---|---|
| Source | YouTube (multi-client yt-dlp retry) or local file |
| Editor | Trim, volume, preview before render |
| Render | Scene detection → segment scoring → parallel FFmpeg encode |
| Subtitles | Whisper transcription → SRT → ASS karaoke / bounce |
| Translation | Google Translate per SRT block (vi / en / ja) |
| Voice | Microsoft Edge TTS narration, mixed per part |
| Download | Standalone batch downloader for public videos |
| Upload | Playwright browser automation to TikTok |

---

## Project layout

```
tool-render-video/
├── backend/                  FastAPI application
│   ├── app/
│   │   ├── core/             Config, stage enums
│   │   ├── models/           Pydantic schemas (RenderRequest etc.)
│   │   ├── orchestration/    render_pipeline.py — main render loop
│   │   ├── routes/           HTTP endpoints (render, download, upload, jobs…)
│   │   └── services/         All business logic
│   └── static/               Frontend (single HTML + JS modules + CSS)
│       ├── index.html
│       └── js/
├── desktop-shell/            Electron wrapper
│   ├── main.js               Bootstrap, venv, backend lifecycle
│   └── package.json
├── data/                     Runtime: SQLite, logs, temp, Whisper cache
├── channels/                 Per-channel folder trees
└── docs/                     Full documentation
```

---

## Quick start (development)

```bash
# 1. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 2. Open browser
http://127.0.0.1:8000
```

### Prerequisites

| Tool | Minimum | Install |
|---|---|---|
| Python | 3.11 | python.org |
| ffmpeg + ffprobe | 6.x | `winget install -e --id Gyan.FFmpeg` |
| Node.js | 18+ | Desktop shell only |

---

## Desktop app

```bash
cd desktop-shell
npm install
npm start              # development
npm run dist:win       # build NSIS + portable installer
```

See [docs/DESKTOP_APP.md](docs/DESKTOP_APP.md).

---

## Key environment variables

| Variable | Default | Purpose |
|---|---|---|
| `APP_DATA_DIR` | `./data` | SQLite, logs, temp |
| `CHANNELS_DIR` | `./channels` | Channel output trees |
| `TEMP_DIR` | `./data/temp` | Working + preview files |
| `DATABASE_PATH` | `./data/app.db` | SQLite DB |
| `FFMPEG_BIN` | auto-detect | Override ffmpeg path |
| `FFPROBE_BIN` | auto-detect | Override ffprobe path |
| `YTDLP_PROXY` | — | Explicit proxy for yt-dlp |
| `YTDLP_COOKIEFILE` | — | Cookie file (age-restricted videos) |
| `LOG_KEEP_LAST` | 30 | Job log retention count |
| `LOG_KEEP_DAYS` | 10 | Job log age cutoff |

---

## Documentation index

| File | Contents |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System overview, data flow, component map |
| [docs/RENDER_PIPELINE.md](docs/RENDER_PIPELINE.md) | All render stages, parallelism, resume |
| [docs/DOWNLOAD_SYSTEM.md](docs/DOWNLOAD_SYSTEM.md) | Download tab, yt-dlp retry, proxy fix |
| [docs/VOICE_NARRATION.md](docs/VOICE_NARRATION.md) | Edge TTS, voice sources, audio mix modes |
| [docs/SUBTITLE_TRANSLATION.md](docs/SUBTITLE_TRANSLATION.md) | Whisper → SRT → ASS, translation states |
| [docs/UI_BEHAVIOR.md](docs/UI_BEHAVIOR.md) | View system, editor flow, terminal states |
| [docs/DESKTOP_APP.md](docs/DESKTOP_APP.md) | Electron bootstrap, offline packaging |
| [cowork/README.md](cowork/README.md) | Cowork system entry point — Claude Code workflow rules |
| [cowork/COMMANDS.md](cowork/COMMANDS.md) | Slash commands: /run /test /fix /error /status /log /commit /features |
| [cowork/PROJECT_STATUS.md](cowork/PROJECT_STATUS.md) | Phase stability and safe next tasks |
| [cowork/COWORK_SYSTEM_DEFINITION.md](cowork/COWORK_SYSTEM_DEFINITION.md) | System definition for co-working teams |
| [cowork/HUONG_DAN_SU_DUNG_COWORK.md](cowork/HUONG_DAN_SU_DUNG_COWORK.md) | Hướng dẫn sử dụng (Vietnamese) |
