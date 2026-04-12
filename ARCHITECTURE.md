# ARCHITECTURE.md

## Components
- Electron: `desktop-shell/main.js` -> start backend, wait `/health`, open UI.
- FastAPI: `backend/app/main.py` -> startup hooks + route mount.
- Routes: `render.py`, `jobs.py`, `upload.py`, `channels.py`.
- Services: queue, DB, media pipeline, upload automation.
- Storage: SQLite (`data/app.db`), files (`channels/*`, `data/*`).

## Render Flow
1. `POST /api/render/process` validate input.
2. Upsert job `queued`.
3. Submit to `job_manager` thread pool.
4. Resolve source (editor/local/youtube).
5. Optional trim/volume.
6. Scene detect -> segment build -> viral score.
7. Transcript/subtitle generation (conditional per part).
8. Per part: cut -> render -> fallback -> persist `job_parts`.
9. Write `render_report.xlsx`.
10. Finalize job status; stream via HTTP/WS.

## Upload Flow
1. Login/check via `/api/upload/login/*`.
2. `POST /api/upload/schedule/start` create run.
3. Background task executes upload.
4. Resolve files + schedule + captions.
5. Per file: upload/dry-run; move to `uploaded` or `failed`.
6. Write `upload_report.xlsx`.
7. Stream run state via WS.

## Queue/Worker
- Render queue: in-process `ThreadPoolExecutor` (`max_workers=4`), dedupe by `job_id`.
- Startup recovery: `queued/running` -> `interrupted`.
- Part parallelism: bounded by pipeline/encoder mode.
- Upload runs: in-memory run state + lock.

## Durability
- Durable: DB rows, output files, reports, logs.
- Ephemeral: preview sessions, in-memory upload run cache.
