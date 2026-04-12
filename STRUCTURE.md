# STRUCTURE.md

## Top Level
- `backend/`: FastAPI + processing services.
- `desktop-shell/`: Electron runtime/packaging.
- `channels/`: per-channel data/config/output.
- `data/`: DB/temp/reports/cache.
- Root scripts: setup/run/build (`.ps1`, `.bat`).

## Backend (`backend/app`)
- `main.py`: app bootstrap.
- `core/config.py`: env/path resolution.
- `routes/`: API/WS boundaries.
- `services/`: business logic.

## High-Value Services
- `job_manager.py`: render queue + dedupe/recovery.
- `db.py`: job/job_part persistence.
- `render_engine.py`: ffmpeg cut/render + fallback.
- `subtitle_engine.py`: transcript/subtitle transforms.
- `upload_engine.py`: login/schedule/upload runtime.

## Channel Contract (`channels/<code>`)
- `video_out/`: canonical render output.
- `upload/source|uploaded|failed/`: ingest + upload outcomes.
- `account/upload_settings.json`: channel defaults.
- `account/profiles/<account_key>/account.json`: account runtime profile.
- `hashtag/hashtags.txt`: default tags.
- `logs/render|upload/`: runtime logs.

## Naming
- Python files: `snake_case.py`.
- Services: `<domain>_service.py` / `<domain>_engine.py`.
- Routes: domain file names.
- Job terminal statuses: `completed|failed|interrupted`.
- Render parts: `<slug>_part_<NNN>.mp4`.
