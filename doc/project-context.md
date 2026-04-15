# Project Context

## Stack
- Backend: Python + FastAPI + SQLite.
- Desktop: Electron (Node.js).
- Media pipeline: ffmpeg, Whisper, OpenCV, Playwright.

## Key Folders
- `backend/`
- `desktop-shell/`
- `channels/`
- `data/`

## Important Commands
- `./setup.ps1`
- `./run-backend.ps1`
- `./run-desktop.ps1`
- `./build-backend.bat`
- `./build-desktop.ps1`

## Constraints
- Keep API contracts stable unless task explicitly changes them.
- Keep route handlers thin; use `backend/app/services/` for heavy logic.
- Preserve existing render/upload fallback behavior.

## TODO
- Test command
- Lint/format command
- CI command
