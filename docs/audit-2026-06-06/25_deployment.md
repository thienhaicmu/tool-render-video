# 25 — Deployment

Rebuilt from code on 2026-06-06. Single deployment target: **Electron desktop application running on the user's PC**. No cloud, no container, no remote infrastructure.

## Components shipped

| Component | Where in the installer |
|---|---|
| Electron main + preload | `desktop-shell/main.js`, `preload.js`, packaged via electron-builder |
| Frontend SPA build | `backend/static-v2/` (Vite outDir) |
| Backend Python source | bundled in `backend/` |
| Backend binary | `backend-bin/render-backend.exe` (PyInstaller build path; see `build-offline-exe.ps1`) |
| FFmpeg + ffprobe | `ffmpeg-bin/{ffmpeg.exe, ffprobe.exe}` |
| Python venv | created at first run inside `{userData}/data/.venv/` (dev) or `backend/.venv/` (packaged) |
| Chromium (via Playwright) | downloaded at first run, `{userData}/data/playwright/` |

## First-run bootstrap

[desktop-shell/main.js:189+](../../desktop-shell/main.js):

1. Detect Python 3.11+ (probes `py -3.11`, `python3`, etc.).
2. Create venv at `{userData}/data/.venv` (or `backend/.venv` for dev).
3. `pip install -r backend/requirements.txt`.
4. `python -m playwright install chromium`.
5. Persist bootstrap state to `{userData}/data/state/bootstrap-state.json` with hash check.

## Steady-state launch

1. Electron spawns backend (`render-backend.exe` packaged, else venv Python) listening on `127.0.0.1:8000`.
2. Logs to `{userData}/data/logs/desktop-backend.log`.
3. `PLAYWRIGHT_BROWSERS_PATH` env var passed.
4. Polls `http://127.0.0.1:8000/health` until ready, then opens the main window.

## Environment variables

Backend reads ([backend/app/core/config.py](../../backend/app/core/config.py)):

| Var | Default | Purpose |
|---|---|---|
| `APP_DATA_DIR` | platform-dependent | DB + cache + logs root |
| `STATIC_UI_VERSION` | `v2` | which UI to serve |
| `ENABLE_DEVTOOLS` | (unset) | enables `/api/dev/command` shell exec |
| `ENABLE_V2` | (unset) | enables V2 routers |
| `MAX_CONCURRENT_JOBS` | `cpu_count // 2` | render queue cap |
| `NVENC_MAX_SESSIONS` | `3` | NVENC semaphore size |
| `CLEANUP_INTERVAL_SEC` | `1800` | periodic cleanup cadence |
| `SHUTDOWN_TIMEOUT_SEC` | `30` | graceful drain timeout |
| `LLM_WHISPER_MODEL` | `base` | Whisper model size for LLM pre-render |
| `LLM_EMIT_RENDER_PLAN` | `1` | toggle Call-2 RenderPlan emission |
| `FEATURE_BASE_CLIP_FIRST` | `0` | render flag |
| `FEATURE_OVERLAY_AFTER_BASE_CLIP` | `0` | render flag |
| `FEATURE_RAW_PART_SKIP` | `0` | render flag (Sprint 7.4) |
| `FEATURE_RAW_PART_SKIP_MOTION_AWARE` | `0` | render flag (Sprint 7.8) |
| `GEMINI_API_KEY` / `OPENAI_API_KEY` / `CLAUDE_API_KEY` | (unset) | server-side LLM credentials |

(See `.env.example` at repo root for the canonical list — but trust the code: env reads happen at module load.)

## Update path

There is no automatic updater visible in `desktop-shell/main.js`. Updates ship as a new installer; the user reinstalls. Re-running the installer:

- Preserves `{userData}/data/` (DB, caches, logs).
- Rebuilds the venv only if the hash check in `bootstrap-state.json` changes.

## Disk layout (user side)

```
{userData}/data/
├── app.db                       # SQLite WAL — sole job state
├── .venv/                       # Python venv (when packaged path)
├── backups/                     # app.db snapshots (retention 10)
├── cache/
│   ├── transcription/           # Whisper SRT cache (72 h)
│   ├── scene_detect/            # PySceneDetect output cache (72 h)
│   ├── motion_paths/            # subject path cache (72 h)
│   └── ass/                     # ASS subtitle cache (content-addressable)
├── logs/
│   ├── desktop-backend.log
│   └── job-{job_id}/            # per-job event log files
├── playwright/                  # Chromium downloaded for cookies/automation
└── state/bootstrap-state.json
```

Output videos go where the user picked them (RenderRequest `output_dir`), not under `{userData}`.

## Docker

`backend/Dockerfile` exists. Not used in the desktop product. Likely a CI artifact for headless testing. Not investigated this audit.

## Build scripts

| Script | What it does |
|---|---|
| `build-backend.bat` | (untested in audit) |
| `build-desktop.ps1` | Electron build |
| `build-offline-exe.ps1` | PyInstaller backend → `render-backend.exe` |
| `run-backend-v2.ps1`, `run-desktop-v2.ps1` | dev runners |

End of 25_deployment.md.
