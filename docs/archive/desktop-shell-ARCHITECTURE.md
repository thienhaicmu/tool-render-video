# Architecture

## Components
- Electron shell: boot backend, wait `/health`, open app window.
- FastAPI app: routes + startup hooks + static UI.
- Services: render/upload/scoring/subtitle/channel/db.
- Storage:
- SQLite: `jobs`, `job_parts`
- Files: `channels/`, `data/temp`, `data/reports`, logs.

## Route Responsibilities
- `render.py`: validate -> queue -> execute pipeline -> persist progress/result.
- `jobs.py`: query jobs/parts/logs + WS progress stream.
- `upload.py`: login/config/video listing + async upload run orchestration.
- `channels.py`: channel folder/config/profile bootstrap.

## Render Flow
1. `POST /api/render/process` -> validate -> create queued job.
2. Worker resolves source (editor session/local/yt-dlp), optional trim/volume.
3. Detect scenes -> build segments -> score/rank.
4. Generate subtitles (optional), slice per segment.
5. For each part: cut -> render -> update `job_parts`.
6. Append `render_report.xlsx`, mark job `completed|failed`.

## Upload Flow
1. Login check/start (`/api/upload/login/*`).
2. `POST /api/upload/schedule/start` creates `run_id`.
3. Background task runs `upload_schedule`.
4. Per file: build caption -> dry-run or upload -> move to `uploaded/` or `failed/`.
5. Append `upload_report.xlsx`; stream state via upload WS endpoint.

## Queue / Worker
- Render: ThreadPoolExecutor (`max_workers=4`), dedupe by `job_id`, startup stale-job recovery -> `interrupted`.
- Upload: in-memory run state + lock, executed via FastAPI background task.
- Render part-level parallelism is capped by encoder/pipeline cost.

## Reliability Rules
- Keep progress state writes continuous (`jobs` + `job_parts`).
- Preserve fallbacks:
- cut copy -> re-encode
- motion render -> standard render
- NVENC -> CPU
- Durable: DB/files. Non-durable: upload run memory + preview sessions.
