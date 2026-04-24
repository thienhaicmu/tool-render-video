# Desktop App

## Scope
This document describes the Electron desktop shell behavior for Render Studio:
- `desktop-shell/main.js` lifecycle
- backend bootstrap/start strategy
- offline packaging model
- `backend-bin/render-backend.exe`
- `ffmpeg` external dependency behavior

## Runtime Architecture

Desktop app = Electron shell + local FastAPI backend.

At runtime:
1. Electron process starts.
2. Backend health checked at `http://127.0.0.1:8000/health`.
3. If backend not running, Electron starts backend.
4. BrowserWindow loads `http://127.0.0.1:8000`.

## Main Process Lifecycle (`desktop-shell/main.js`)

## Startup sequence
- `app.whenReady().then(bootstrap)`
- `bootstrap()`:
  1. `healthCheck()`
  2. if unhealthy -> `startBackend()`
  3. `waitBackendReady()` (up to 120s)
  4. `createWindow()`

If startup fails:
- Error dialog shown with backend log path
- app exits

## Window behavior
- Creates `BrowserWindow` (desktop-focused min size)
- Uses `preload.js` with `contextIsolation: true`, `nodeIntegration: false`
- Clears web cache before loading URL to avoid stale frontend bundles

## Shutdown behavior
On `window-all-closed`:
- kills spawned backend process if still running
- quits app on non-macOS

## Backend Start Modes

## Mode A: Offline packaged backend executable
When packaged and file exists:
- path: `backend-bin/render-backend.exe`
- `startBackend()` directly spawns this executable
- skips Python venv/pip bootstrap

## Mode B: Python backend bootstrap (dev / non-offline)
If no packaged backend exe:
- resolve/create venv
- install `backend/requirements.txt`
- install Playwright Chromium
- launch `uvicorn app.main:app --host 127.0.0.1 --port 8000`

Bootstrap state is cached using:
- `data/state/bootstrap-state.json`
- keyed by requirements hash + bootstrap version

## Runtime Environment Paths and Env Vars

Electron sets a dedicated app data root and runtime env:
- `APP_DATA_DIR`
- `DATABASE_PATH`
- `CHANNELS_DIR`
- `TEMP_DIR`
- `HF_HOME`, `TORCH_HOME`, `TRANSFORMERS_CACHE`
- `PLAYWRIGHT_BROWSERS_PATH`
- etc.

This keeps desktop runtime isolated from source tree in packaged mode.

## FFmpeg Dependency Behavior

## Packaged ffmpeg binaries available
If packaged files exist:
- `ffmpeg-bin/ffmpeg.exe`
- `ffmpeg-bin/ffprobe.exe`

Electron injects:
- `FFMPEG_BIN=<packaged ffmpeg.exe>`
- `FFPROBE_BIN=<packaged ffprobe.exe>`

## Packaged ffmpeg binaries not available
- Backend falls back to normal ffmpeg discovery on target machine.
- Offline package may still run, but encode/probe features require ffmpeg availability.

## Build and Packaging

## Standard desktop build
Script: `build-desktop.ps1`

Steps:
1. Build backend executable (`build-backend.bat clean`)
2. Build Electron app (`npm run dist` in `desktop-shell`)

## Offline portable build
Script: `build-offline-exe.ps1`

Steps:
1. Build backend one-file exe via PyInstaller
2. Copy to `desktop-shell/backend-bin/render-backend.exe`
3. Try to copy local `ffmpeg.exe` + `ffprobe.exe` into `desktop-shell/ffmpeg-bin`
4. Build Electron distro (`npm run dist`)

## Electron builder resource model
`desktop-shell/package.json` includes `extraResources`:
- `../backend` -> `backend` (without `.venv`, caches, pyc)
- `backend-bin` -> `backend-bin`
- `ffmpeg-bin` -> `ffmpeg-bin`

## Practical Failure Checklist

- Backend never becomes healthy:
  - check desktop backend log in app data logs folder
  - verify port `8000` availability
- Offline app fails on render/probe:
  - verify `ffmpeg-bin/ffmpeg.exe` and `ffmpeg-bin/ffprobe.exe`
  - otherwise install system ffmpeg
- First run bootstrap very slow:
  - expected when installing Python deps and Playwright Chromium
