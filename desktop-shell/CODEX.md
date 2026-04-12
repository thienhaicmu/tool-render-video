# Codex Context Bootstrap

## Project
- Local short-video platform.
- Backend: FastAPI (`../backend/app`).
- Desktop: Electron (`main.js`, `preload.js`).
- Core tools: ffmpeg/ffprobe, yt-dlp, Whisper, Playwright.

## Runtime
- API: `127.0.0.1:8000`.
- Render jobs: threaded queue + SQLite (`data/app.db`).
- Flow: source -> scenes -> segments -> score -> subtitles -> render -> report.
- Upload: Playwright + persistent channel/account profiles.

## Edit Policy
- Read minimal files; edit minimal scope.
- Keep contracts stable:
- routes: `../backend/app/routes`
- schemas: `../backend/app/models/schemas.py`
- DB fields: `../backend/app/services/db.py`
- channel compatibility: `video_out` + `upload/video_output`

## Hard Rules
- Keep heavy logic in `services/`.
- Keep Electron isolation enabled.
- Queue long tasks; do not block request handlers.
- Preserve fallbacks: copy-cut -> re-encode, NVENC -> CPU, motion render -> standard render.

## Context Load Order
1. `RULES.md`
2. `STRUCTURE.md`
3. `ARCHITECTURE.md`
4. `CODEX.md` or `CLAUDE.md`
5. Only target code files
