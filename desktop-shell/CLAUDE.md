# AI Context Bootstrap

## Project
- Local short-video platform.
- Backend: FastAPI (`../backend/app`).
- Desktop: Electron (`main.js`, `preload.js`).
- Core tools: ffmpeg/ffprobe, yt-dlp, Whisper, Playwright.

## Runtime Model
- API at `127.0.0.1:8000`.
- Render jobs: threaded queue + SQLite (`data/app.db`).
- Flow: source -> scenes -> segments -> score -> subtitles -> render -> report.
- Upload: Playwright + persistent channel/account profiles.

## Change Policy
- Read minimal files; edit minimal scope.
- Keep contracts stable:
- routes (`../backend/app/routes`)
- schemas (`../backend/app/models/schemas.py`)
- DB job fields (`../backend/app/services/db.py`)
- channel path compatibility (`video_out` + `upload/video_output`).

## Hard Rules
- Keep heavy logic in services.
- Keep Electron isolation enabled.
- Queue long tasks; do not block request handlers.
- Preserve retry/fallback behavior (copy-first cut, NVENC->CPU, motion->standard render).

## Load Order
1. `RULES.md`
2. `STRUCTURE.md`
3. `ARCHITECTURE.md`
4. Only target code files


Only load additional .md files when necessary.
