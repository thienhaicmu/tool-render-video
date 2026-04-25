# Structure

## Top-Level
- `backend/`: FastAPI + media pipeline.
- `desktop-shell/`: Electron shell + packaging.
- `channels/`: per-channel runtime workspaces.
- `data/`: shared DB/temp/reports/caches.
- `tool-render-pro-v1/`: separate UI/tool workspace.

## Backend Map (`backend/app`)
- `main.py`: app boot, router wiring, startup/shutdown hooks.
- `core/config.py`: env/path resolution.
- `models/schemas.py`: API payload contracts.
- `routes/`: API boundaries (`render`, `upload`, `jobs`, `channels`).
- `services/`: business logic and pipeline execution.

## Desktop Map (`desktop-shell`)
- `main.js`: backend bootstrap + window lifecycle.
- `preload.js`: minimal safe IPC bridge.
- `backend-bin/`: packaged backend exe.
- `build/`: icons.
- `dist/`: build output.

## Channel Contract (`channels/<code>`)
- `video_out/`: primary upload input.
- `upload/source|queue|uploaded|failed|archive|logs/`: upload lifecycle.
- `account/upload_settings.json`: channel defaults.
- `account/profiles/<account_key>/account.json`: account profile.
- `hashtag/hashtags.txt`: hashtag defaults.
- `logs/render|upload/`: runtime logs.

## Naming
- Python files: `snake_case.py`.
- Routes: domain-based.
- Services: `<domain>_engine.py` / `<domain>_service.py`.
- Status set: `queued|running|completed|failed|interrupted`.
- Output part: `<slug>_part_<NNN>.mp4`.
