# System Architecture

## Overview

AI video render studio — offline-first desktop application.

- **Shell:** Electron (`desktop-shell/`)
- **Backend:** FastAPI + Uvicorn (`backend/`)
- **Frontend:** React 18 + TypeScript + Vite (`frontend/`)
- **Database:** SQLite WAL (`data/app.db`)
- **Render Engine:** FFmpeg subprocess
- **AI:** Google Gemini / OpenAI / Anthropic Claude (provider-selectable)
- **Transcription:** OpenAI Whisper (local, offline)
- **Tracking:** OpenCV (`features/render/engine/motion/crop.py`)

No cloud dependency for core rendering. AI calls are optional — all providers gracefully return `None` on failure and the pipeline falls back to heuristic scoring.

---

## Top-Level Directory Layout

```
D:\tool-render-video\
├── backend/                  FastAPI server + render engine
│   ├── app/                  Application package
│   │   ├── main.py           Entry point — router mounts + startup hooks
│   │   ├── models/           Pydantic schemas (RenderRequest, etc.)
│   │   ├── routes/           Non-render HTTP handlers (jobs, channels, voice, files, feedback, settings)
│   │   ├── features/         All feature modules — canonical code location
│   │   │   ├── render/       Render feature (router, editing, engine/)
│   │   │   │   ├── router.py         POST /api/render/process + preview
│   │   │   │   ├── editing/          Editing API + service
│   │   │   │   ├── engine/           Render engine — all rendering logic
│   │   │   │   │   ├── pipeline/     Orchestration stages (render_pipeline, llm_*, pipeline_*)
│   │   │   │   │   ├── stages/       Per-part workers (part_renderer, part_render_*)
│   │   │   │   │   ├── encoder/      FFmpeg helpers, clip_ops, NVENC semaphore
│   │   │   │   │   ├── audio/        TTS, mixer, cleanup adapters
│   │   │   │   │   ├── subtitle/     Generator, processing, transcription
│   │   │   │   │   ├── overlay/      Text overlay (drawtext)
│   │   │   │   │   ├── motion/       OpenCV subject tracking
│   │   │   │   │   ├── thumbnail/    Thumbnail quality selection
│   │   │   │   │   ├── quality/      Output QA assessment
│   │   │   │   │   └── preview/      FFmpeg probers, session service
│   │   │   │   └── ai/               AI modules — LLM providers, parser, prompts, visibility
│   │   │   └── download/     Download feature (router, engine/)
│   │   ├── core/             Config, stage enums, logging, UI gate
│   │   ├── db/               SQLite connection + migrations + repos
│   │   ├── domain/           Pure dataclasses (RenderPlan, CreatorContext)
│   │   ├── jobs/             Job queue (manager.py) + cancel registry (cancel.py)
│   │   └── services/         Shared utilities (channel_service, maintenance, warmup, db facade)
│   ├── static/               Legacy UI build output (served when STATIC_UI_VERSION=legacy)
│   └── static-v2/            v2 UI build output (served when STATIC_UI_VERSION=v2)
├── frontend/                 React + TypeScript UI (Vite)
│   └── src/
│       ├── features/         Screens (clip-studio, editor, jobs, downloader)
│       ├── api/              HTTP + WebSocket clients
│       └── stores/           Zustand state stores
├── desktop-shell/            Electron host
├── channels/                 Per-channel output storage roots
├── data/                     Runtime: app.db, cache, temp, logs
├── scripts/                  Utility scripts
└── tests/                    Integration test suite
```

---

## Input Sources

**Only two valid inputs to the render pipeline:**

### 1. Local File
- `RenderRequest.source_mode = "local"` (default)
- `RenderRequest.source_video_path` — absolute path to video file on disk
- Validated in `features/render/router.py` before job creation
- Enforcement in `pipeline_source_prep.py:153`: any non-`"local"` source_mode raises `RuntimeError`

### 2. Editor Session
- `RenderRequest.edit_session_id` — non-empty session ID
- Session created by `POST /api/editing/sessions` with a source file
- Session stores: `video_path`, `preview_path`, `duration`, `title`, `work_dir`
- Trim (`edit_trim_in`, `edit_trim_out`) applied via FFmpeg before render
- Session cleanup runs in `finally` block of render pipeline

**Rejected inputs:**
- `source_mode="youtube"` → HTTP 400 "Use standalone Downloader"
- `source_mode="remote"` → HTTP 400 same reason
- `youtube_url` / `youtube_urls` fields exist in schema for backward compat but are ignored by pipeline

The **Download feature** (`features/download/`) is a separate system mounted at `/api/download/`. It downloads video files to disk. Those files are then rendered via the Local File path — it is NOT part of the render pipeline itself.

---

## Router Mounts (main.py)

| Prefix | Module | Source |
|--------|--------|--------|
| `/api/channels` | channels_router | `routes/channels.py` |
| `/api/render` | render_router | `features/render/router.py` |
| `/api/jobs` | jobs_router | `routes/jobs.py` |
| `/api/voice` | voice_router | `routes/voice.py` |
| `/api/files` | files_router | `routes/files.py` |
| `/api/editing` | editing_router | `features/render/editing/router.py` |
| `/api/download` | platform_downloader_router | `features/download/router.py` |
| `/api/feedback` | feedback_router | `routes/feedback.py` |
| `/metrics` | metrics_router | `routes/metrics.py` (Prometheus) |
| `/api/settings` | settings_router | `routes/settings.py` |
| `/api/dev/command` | devtools_router | `routes/devtools.py` (ENABLE_DEVTOOLS=1 only) |

**Static file mounts:**
- Legacy UI: `/static` → `backend/static/`
- v2 UI: `/assets` → `backend/static-v2/assets/` (when `STATIC_UI_VERSION=v2`)

**v2 API routes** (`ENABLE_V2=1`, default ON): Import attempted from `v2.api.routes.*` — directory does not exist in current codebase, import silently fails.

---

## Key Subsystem Connections

```
User (Electron / Browser)
        │
        ▼
   Electron shell (desktop-shell/)
        │  IPC / HTTP to localhost:8000
        ▼
   FastAPI (backend/app/main.py)
        │
        ├── features/render/router.py → POST /api/render/process
        │       └── jobs/manager.py → ThreadPoolExecutor
        │               └── features/render/engine/pipeline/render_pipeline.py
        │                       ├── pipeline_source_prep.py   (source validation)
        │                       ├── llm_pipeline.py           (Whisper + LLM Call 1)
        │                       ├── render_pipeline.py        (LLM Call 2 → RenderPlan)
        │                       ├── pipeline_render_loop.py   (parallel part dispatch)
        │                       │       └── stages/part_renderer.py (per-part worker)
        │                       │               ├── part_cut.py
        │                       │               ├── part_render_setup.py
        │                       │               ├── part_render_encode.py  (FFmpeg)
        │                       │               ├── part_voice_mix.py
        │                       │               └── part_done.py
        │                       └── pipeline_finalize.py      (result_json assembly)
        │
        ├── routes/jobs.py → GET /api/jobs/{id}/ws (WebSocket)
        │       └── Streams render_events.py events to UI
        │
        └── features/download/router.py → POST /api/download/batch
                └── features/download/service.py
                        └── adapters/ (youtube, tiktok, instagram, ...)
```

---

## AI Module Architecture

### Canonical Location
`backend/app/features/render/ai/llm/` — all LLM logic lives here. There is no shim layer — all imports must reference this path directly.

### Providers
Three interchangeable providers — same interface, same Sacred Contract #3 (never raise):

| Provider | Default Model | Max SRT | Env Key |
|----------|--------------|---------|---------|
| Gemini | gemini-2.0-flash | 60,000 chars | `GEMINI_API_KEY` |
| OpenAI | gpt-4o-mini | 30,000 chars | `OPENAI_API_KEY` |
| Claude | claude-3-5-sonnet-20241022 | 50,000 chars | `CLAUDE_API_KEY` |

Selected via `RenderRequest.ai_provider` or `AI_PROVIDER_DEFAULT` env var.

---

## Concurrency Model

- **Job queue:** `jobs/manager.py` — `ThreadPoolExecutor` with `MAX_CONCURRENT_JOBS` workers
- **Part-level parallelism:** `pipeline_render_loop.py` — inner `ThreadPoolExecutor` with `MAX_RENDER_JOBS` workers per job
- **GPU encoding:** `NVENC_SEMAPHORE` (max 3 sessions, in `features/render/engine/encoder/ffmpeg_helpers.py`)
- **DB writes on render thread:** `_thread_conn()` — cached thread-local SQLite connection, released in `finally` block
- **DB writes on HTTP thread:** `db_conn()` context manager — new connection per request, auto-commit

---

## Startup Sequence (main.py)

1. Configure file-based logging (`core/logging_setup.py`)
2. Mount all routers
3. `@app.on_event("startup")`:
   - `init_db()` — create tables + run migrations
   - `_check_db_fallback_at_startup()` — detect split-DB condition
   - `ensure_channel("k1")` — create default channel
   - Prune stale preview dirs, render temp dirs, render cache (72h TTL), XTTS cache (30d), text overlay (7d)
   - `recover_pending_render_jobs()` — re-queue interrupted jobs
   - `start_warmup()` — pre-download Whisper models
   - `_whisper_model_warmup()` thread — load Whisper into RAM
   - `_run_periodic_cleanup()` thread — 30-min cleanup loop
   - `_cookie_warmup()` thread — extract Chrome cookies for yt-dlp

---

## Frontend Screens

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | App.tsx | Root |
| `/editor` | EditorScreen.tsx | Trim + preview + text overlay |
| `/render` | RenderWorkflow.tsx | Configure + monitor + results |
| `/history` | HistoryScreen.tsx | Job list + filtering |
| `/downloader` | DownloaderScreen.tsx | Multi-URL batch download |
| `/quality` | QualityPanel.tsx | Output quality report |
| `/settings` | SettingsScreen.tsx | User preferences |
