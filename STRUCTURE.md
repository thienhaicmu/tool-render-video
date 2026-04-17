# STRUCTURE.md

## Top Level
- `backend/` — FastAPI + processing services.
- `desktop-shell/` — Electron runtime/packaging.
- `channels/` — per-channel data/config/output.
- `data/` — DB/temp/reports/logs.
- `doc/` — technical docs.
- `cowork/` — AI tool and operator guides.
- Root scripts: setup/run/build (`.ps1`, `.bat`).

## Backend (`backend/app`)
- `main.py` — app bootstrap, log filters, startup hooks.
- `core/config.py` — env/path resolution; creates all required directories on import.
- `core/stage.py` — `JobStage`, `JobPartStage`, `STAGE_TO_EVENT` enums used by pipeline and DB.
- `routes/` — HTTP boundaries only. Validate input, queue jobs, delegate to orchestration.
- `orchestration/` — pipeline logic. `render_pipeline.py` owns `run_render_pipeline()`.
- `services/` — single-domain business logic called by the orchestration layer.

## Route Responsibilities

`routes/render.py` is **not** the pipeline orchestrator. It:
- Validates and rejects bad requests (Types 1 errors)
- Upserts the job record and submits it to the job queue
- Owns preview session storage (`_PREVIEW_SESSIONS`, `_load_session`, `_cleanup_preview_session`)
- Calls `run_render_pipeline()` via the `process_render` wrapper

All render pipeline logic lives in `orchestration/render_pipeline.py`.

## High-Value Services
- `job_manager.py` — render queue + dedup/recovery.
- `db.py` — job/job_part persistence.
- `render_engine.py` — ffmpeg cut/render + NVENC/CPU fallback.
- `subtitle_engine.py` — transcript/subtitle transforms.
- `text_overlay.py` — text layer filter builder + `VALID_FONTS` + `normalize_text_layers`.
- `upload_engine.py` — login/schedule/upload runtime.

## Channel Contract (`channels/<code>`)
- `video_out/` — canonical render output.
- `upload/source|uploaded|failed/` — ingest + upload outcomes.
- `account/upload_settings.json` — channel defaults.
- `account/profiles/<account_key>/account.json` — account runtime profile.
- `hashtag/hashtags.txt` — default tags.
- `logs/` — per-job render logs.

## Data Layout (`data/`)
- `app.db` — SQLite database.
- `temp/preview/{session_id}/` — editor session temp (auto-cleaned, 6h TTL).
- `logs/request.log` — Type 1 request validation errors (JSON lines).
- `logs/app.log` — all pipeline events (JSON lines).
- `logs/error.log` — ERROR/CRITICAL pipeline events only.
- `reports/` — Excel render reports.

## Naming
- Python files: `snake_case.py`.
- Services: `<domain>_service.py` / `<domain>_engine.py`.
- Routes: domain file names.
- Job terminal statuses: `done` / `failed` / `interrupted`.
- Render parts: `<slug>_part_<NNN>.mp4`.
