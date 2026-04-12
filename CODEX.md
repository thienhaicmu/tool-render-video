# CODEX.md

Codex bootstrap for this repo.

## Load Order
1. `CODEX.md`
2. `RULES.md`
3. `STRUCTURE.md`
4. `ARCHITECTURE.md` (only for flow/queue changes)
5. `PROMPTS.md` (only for AI-content tasks)

## System
- Stack: FastAPI (Python) + Electron (Node.js).
- Product: long video -> segments -> subtitles -> short clips -> optional TikTok upload.
- Core tools: `ffmpeg`, Whisper, Playwright, SQLite.

## Critical Paths
- API entry: `backend/app/main.py`
- Render orchestration: `backend/app/routes/render.py`
- Queue: `backend/app/services/job_manager.py`
- Render engine: `backend/app/services/render_engine.py`
- Upload engine: `backend/app/services/upload_engine.py`
- Desktop bootstrap: `desktop-shell/main.js`

## Working Rules
- Read minimal files; edit minimal scope.
- Keep routes thin; put logic in `services/`.
- Preserve contracts: API fields, status enums, channel paths.
- Preserve fallbacks: copy->reencode, NVENC->CPU, motion->standard.
- Always include verification steps.

## Performance
- Optimize end-to-end job time first.
- Never block request thread with full pipeline work.
- Bound parallelism by device/workload.
- Reuse probes/artifacts when settings/input are unchanged.
- Log stage duration + failure cause.
