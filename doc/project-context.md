# Project Context

## Stack
- Backend: Python + FastAPI + SQLite.
- Orchestration: `backend/app/orchestration/render_pipeline.py` — all render pipeline logic.
- Desktop: Electron (Node.js) — wraps the FastAPI backend as a native app.
- Media pipeline: ffmpeg, Whisper (OpenAI), OpenCV, PySceneDetect.
- Upload automation: Playwright.

## Architecture V2 (current)
The backend uses a 3-layer model:
1. `routes/` — HTTP boundary only. Thin handlers. No pipeline logic.
2. `orchestration/` — pipeline orchestration. `run_render_pipeline()` owns all render steps.
3. `services/` — single-domain logic (downloader, renderer, subtitle engine, etc.).

See [ARCHITECTURE.md](../ARCHITECTURE.md) for the full reference.

## Key Folders
- `backend/app/orchestration/` — render pipeline logic
- `backend/app/core/` — `config.py` (paths) + `stage.py` (enums)
- `backend/app/routes/` — HTTP handlers
- `backend/app/services/` — domain services
- `backend/static/` — single-file web UI (`index.html`)
- `channels/` — per-channel workspaces
- `data/` — DB, temp, logs, reports
- `cowork/` — AI tool and operator guides
- `doc/` — technical documentation

## Important Commands
- `./setup.ps1` — one-click environment setup
- `./run-backend.ps1` — start backend only
- `./run-desktop.ps1` — start full desktop app
- `./build-backend.bat` — build backend exe
- `./build-desktop.ps1` — build full desktop installer

## Constraints
- Keep API contracts stable unless a task explicitly changes them.
- Keep route handlers thin; pipeline logic must live in `orchestration/`.
- Preserve render/upload fallback behavior (NVENC→CPU, copy→reencode, etc.).
- `edit_session_id` must be checked before `source_mode` dispatch in the pipeline.
- Never silently re-download when `edit_session_id` is present but session is missing — fail the job with a clear message.
- Session callbacks are passed from `routes/render.py` to `run_render_pipeline` to avoid circular imports.
