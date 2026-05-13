# Desktop App

## Desktop App Role

**Stability marker: Experimental / needs verification**

The desktop app is an Electron shell around the local FastAPI backend. It is not a separate backend architecture.

Primary file:

- `desktop-shell/main.js`

The desktop shell provides:

- startup orchestration
- splash window
- single-instance behavior
- backend health check
- backend spawn/bootstrap
- packaged runtime paths
- folder picker and shell IPC
- FFmpeg path injection when packaged binaries exist

Packaged behavior should be verified on target machines before being documented as fully stable.

## Startup Flow

**Stability marker: Semi-stable implementation**

Current startup behavior:

```text
Electron app starts
  -> acquire single-instance lock
  -> create splash window
  -> health check http://127.0.0.1:8000/health
  -> if unhealthy, start backend
  -> wait for backend readiness
  -> clear web cache
  -> create BrowserWindow
  -> load http://127.0.0.1:8000 with cache-busting query
```

If backend startup fails, the desktop app should show an error with log path context and exit cleanly.

## Dev Mode

**Stability marker: Semi-stable implementation**

In dev mode, the shell can use the source-tree backend and a Python virtual environment under `backend/.venv`.

Typical backend command is Uvicorn running `app.main:app` on `127.0.0.1:8000`.

Dev mode expects Python dependencies to be installable from `backend/requirements.txt`.

## Packaged Mode

**Stability marker: Experimental / needs verification**

Packaged mode uses Electron resources and app user data directories instead of assuming the source tree is writable.

Runtime data is moved under Electron's app data area where possible:

- database
- channels
- temp
- logs
- model/cache directories
- Playwright browser path

Do not hardcode source-tree paths into packaged-only behavior.

## Backend Startup Strategy

**Stability marker: Semi-stable implementation**

Backend startup order:

1. If already healthy on localhost, reuse it.
2. If packaged backend executable exists, spawn it.
3. Otherwise bootstrap/use Python environment and launch Uvicorn.

Startup waits for `/health` for a bounded period.

### What must not break: backend startup

- Health check before spawn.
- Wait-for-ready loop.
- Backend log capture.
- Port `8000` assumption unless changed everywhere.
- Clean shutdown of spawned backend process.

## backend-bin Behavior

**Stability marker: Experimental / needs verification**

Packaged offline builds may include:

```text
desktop-shell/backend-bin/render-backend.exe
```

When present, Electron can spawn this executable directly and skip Python/venv bootstrap.

This path is packaging-sensitive and should be verified after build changes.

## Python Dependency Bootstrap

**Stability marker: Semi-stable implementation**

When no packaged backend executable is used, Electron can create/use a virtual environment, install backend requirements, and install Playwright Chromium.

Bootstrap state is cached using requirements hash and a bootstrap version so first run can be slower than later runs.

Preserve the existing warning: first run may be slow due to dependency installation and browser download.

## ffmpeg-bin Behavior

**Stability marker: Semi-stable implementation**

Packaged builds may include:

```text
desktop-shell/ffmpeg-bin/ffmpeg.exe
desktop-shell/ffmpeg-bin/ffprobe.exe
```

When present, Electron injects:

- `FFMPEG_BIN`
- `FFPROBE_BIN`

If packaged binaries are missing, the backend falls back to normal FFmpeg discovery. Rendering/probing can fail on machines without system FFmpeg.

### What must not break: FFmpeg desktop behavior

- Preserve packaged binary detection.
- Preserve environment injection.
- Preserve fallback to system discovery.
- Preserve clear failure diagnostics when FFmpeg is missing.

## Runtime Environment Paths

**Stability marker: Stable contract**

The desktop shell sets environment variables for local runtime isolation. These include app data, database, reports, channels, temp, model/cache folders, Playwright browsers, and FFmpeg/ffprobe when available.

These paths are part of desktop portability. Do not casually redirect them back to the source tree in packaged mode.

## Health Checks and Warmup

**Stability marker: Semi-stable implementation**

The backend exposes:

- `/health`
- `/api/warmup/status`

The desktop shell depends on `/health` before loading the app. Warmup is backend-managed and can prepare heavy dependencies such as model/cache resources.

## Electron IPC Surface

**Stability marker: Stable contract**

The preload/IPC surface is used by the static frontend for desktop-only capabilities such as folder picking and opening paths.

Do not remove IPC handlers without checking frontend calls.

Known capabilities include:

- folder picker
- path existence checks
- shell open path
- browser profile open behavior

## Known Packaging Risks

**Stability marker: Experimental / needs verification**

Preserve these warnings:

- Packaged backend executable may not include every runtime dependency.
- FFmpeg binaries may be missing from the package.
- Playwright browser install/cache can fail or be slow.
- Model caches can be large.
- Antivirus or Windows permissions can block spawned executables.
- Port `8000` may already be occupied.
- Packaged startup must be tested separately from dev startup.

## What Should Not Be Documented

**Stability marker: Stable contract**

- Do not claim packaged builds are fully verified unless tested.
- Do not document private local paths as universal.
- Do not promise offline behavior when runtime dependencies are absent.
- Do not expose signing/distribution assumptions not present in the repo.

