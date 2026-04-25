> **DEPRECATED — root copy.**
> The authoritative version of this file is [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
> This copy is kept for backward compatibility with any external links.

# ARCHITECTURE.md

Architecture V2 — current state as of 2026-04.

---

## Layer Model

The backend has three distinct layers. Each layer has a single responsibility and a strict dependency direction.

```
┌──────────────────────────────────────────────────┐
│  HTTP Layer  (backend/app/routes/)                │
│  thin handlers — validate, queue, respond         │
└────────────────────┬─────────────────────────────┘
                     │ calls
┌────────────────────▼─────────────────────────────┐
│  Orchestration Layer  (backend/app/orchestration/)│
│  run_render_pipeline() — all pipeline logic       │
└────────────────────┬─────────────────────────────┘
                     │ calls
┌────────────────────▼─────────────────────────────┐
│  Services Layer  (backend/app/services/)           │
│  downloader, scene_detector, render_engine, ...   │
└──────────────────────────────────────────────────┘
```

**Dependency direction:** routes → orchestration → services → core.
Nothing in services imports from routes or orchestration.

---

## Components

### Electron shell (`desktop-shell/main.js`)
Spawns the FastAPI backend process on startup, waits for `/health` to respond, then opens a `BrowserWindow` pointed at `http://127.0.0.1:8000`.

### FastAPI app (`backend/app/main.py`)
- Mounts all routers
- Runs startup hooks: init DB, ensure default channel, prune old logs and preview dirs, recover interrupted jobs, start Whisper warmup
- Installs two log filters:
  - `_SuppressNoisyAccessFilter` on `uvicorn.access` — drops `/api/jobs/` polling and `/health` lines
  - `_SuppressClientDisconnect` on `uvicorn.error` — drops harmless preview video disconnect messages

### HTTP Layer (`backend/app/routes/`)

| File | Role |
|---|---|
| `render.py` | Validate input, queue job, delegate to `run_render_pipeline`. Also owns `prepare-source` and session management. |
| `jobs.py` | Job status, WebSocket progress stream, log tail |
| `upload.py` | TikTok upload API |
| `channels.py` | Channel CRUD |
| `devtools.py` | Dev/maintenance endpoints |

`render.py` is **not** the pipeline orchestrator. `process_render()` is a 6-line wrapper:

```python
def process_render(job_id, payload, resume_mode=False):
    run_render_pipeline(
        job_id=job_id, payload=payload, resume_mode=resume_mode,
        load_session_fn=_load_session,
        cleanup_session_fn=_cleanup_preview_session,
    )
```

Session management (`_load_session`, `_cleanup_preview_session`, `_PREVIEW_SESSIONS`) lives in `render.py` and is passed as callbacks so `orchestration/render_pipeline.py` does not import from `routes/`.

### Orchestration Layer (`backend/app/orchestration/render_pipeline.py`)

Contains all render pipeline logic: `run_render_pipeline()` and all helper functions.

Signature:
```python
def run_render_pipeline(
    job_id: str,
    payload: RenderRequest,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
):
```

Pipeline steps in order:
1. Validate effective channel and output path
2. Check `edit_session_id` → load session or raise if not found
3. Resolve source (session / local / YouTube download)
4. Optional trim/volume
5. Scene detection
6. Segment building + viral scoring
7. Full-video transcription (if subtitles enabled)
8. Per-part: cut → transcribe slice → render
9. Write `render_report.xlsx`
10. Finalize job status

### Services Layer (`backend/app/services/`)

| Service | Responsibility |
|---|---|
| `downloader.py` | yt-dlp download with multi-client retry fallback |
| `scene_detector.py` | PySceneDetect wrapper |
| `segment_builder.py` | Sliding-window segment building + viral_score v2 |
| `viral_scorer.py` | Heuristic scoring + feedback recording |
| `render_engine.py` | ffmpeg cut + full encode + NVENC/CPU fallback |
| `subtitle_engine.py` | Whisper transcription + ASS subtitle generation |
| `motion_crop.py` | OpenCV optical-flow motion-aware crop |
| `text_overlay.py` | Text layer filter builder + `VALID_FONTS` + `normalize_text_layers` |
| `job_manager.py` | ThreadPoolExecutor queue with dedup and restart recovery |
| `db.py` | SQLite — jobs, job_parts, channels |
| `upload_engine.py` | Playwright TikTok upload automation |
| `report_service.py` | Excel report writer |
| `warmup.py` | Background Whisper model preload on startup |
| `channel_service.py` | Channel folder structure management |
| `maintenance.py` | Log pruning, preview temp cleanup |
| `bin_paths.py` | ffmpeg/ffprobe binary path resolution |

---

## Core (`backend/app/core/`)

### `core/config.py`
Resolves all runtime paths from environment variables with safe defaults.
Creates required directories on import.

Key paths:
- `APP_DATA_DIR` — root of all runtime data
- `CHANNELS_DIR` — per-channel workspaces
- `TEMP_DIR` — temp render and preview files
- `LOGS_DIR` — structured log files
- `REQUEST_LOG` — `data/logs/request.log` (Type 1 errors)

### `core/stage.py`
Defines the stage enumerations used by the pipeline and the DB.

```python
class JobStage(str, Enum):
    QUEUED, STARTING, RUNNING, DOWNLOADING, SCENE_DETECTION,
    SEGMENT_BUILDING, TRANSCRIBING_FULL, RENDERING,
    RENDERING_PARALLEL, WRITING_REPORT, DONE, FAILED

class JobPartStage(str, Enum):
    QUEUED, CUTTING, TRANSCRIBING, RENDERING, DONE, FAILED

STAGE_TO_EVENT: dict[str, str]  # maps JobStage → structured event name
```

---

## Render Flow (Detailed)

```
POST /api/render/process
        │
        ▼
_validate_render_source(payload)
  ├─ if edit_session_id present → _validate_output_dir only (source bypass)
  └─ else → validate source_mode, youtube_url/local_path, output_dir leaf name

_validate_text_layers_or_400(payload)

upsert_job(queued)
submit_job(job_id, process_render, ...)
        │
        ▼ (background thread)
process_render() → run_render_pipeline(load_session_fn, cleanup_session_fn)
        │
        ▼
resolve source
  ├─ edit_session_id set → load_session_fn(id)
  │     found   → source = sess["video_path"]  (no download)
  │     missing → raise RuntimeError (job fails, no re-download)
  ├─ source_mode == "local" → use source_video_path directly
  └─ source_mode == "youtube" → download_youtube()

scene detection → segment building → viral scoring
        │
        ▼
full-video Whisper transcription (if add_subtitle)
        │
        ▼
ThreadPoolExecutor (adaptive workers)
  per part: cut_video → slice_srt → render_part_smart
        │
        ▼
write render_report.xlsx
cleanup_session_fn(edit_session_id)
upsert_job(done)
```

---

## Session Lifecycle (Editor Flow)

Sessions are created by `POST /api/render/prepare-source` and consumed by the render pipeline.

```
prepare-source
  → work_dir = data/temp/preview/{session_id}/
  → downloads/validates source
  → transcodes preview to H.264 (duration-aware timeout: min(3600, 120 + 2×duration))
  → _save_session: writes to _PREVIEW_SESSIONS (in-memory) + work_dir/session.json (disk)
  → returns { session_id, title, duration, export_dir: work_dir/"exports" }

_load_session(session_id)
  → check _PREVIEW_SESSIONS first (fast path)
  → fallback to data/temp/preview/{session_id}/session.json (survives server restart)
  → validates video_path still exists on disk

_cleanup_preview_session(session_id)
  → removes from _PREVIEW_SESSIONS
  → deletes data/temp/preview/{session_id}/ tree

Automatic cleanup:
  → startup: prune_preview_dirs(max_age_hours=6) removes stale session dirs
```

**Session expiry rule:** If `edit_session_id` is set in the payload but the session cannot be loaded, the pipeline raises `RuntimeError` immediately. The job fails with a clear message. There is no silent re-download.

---

## Input Validation

`_validate_render_source` in `render.py` has two paths:

**Session path** (when `edit_session_id` is non-empty):
- Validates `output_mode` is `"channel"` or `"manual"`
- Validates `output_dir` leaf name is `"video_output"` or `"video_out"`
- Skips all source_mode / URL / path validation (session supplies the source)

**Normal path** (no session):
- All of the above
- Validates `source_mode` is `"youtube"` or `"local"`
- Validates URL or local path is present
- If `output_mode == "channel"`, validates channel folder is in `output_dir`

---

## Stage Tracking

Every pipeline stage transition calls `_set_stage(stage, progress_pct, message)` which:
1. Calls `upsert_job(stage=...)` to write the new stage to SQLite
2. Calls `_emit_render_event(event=STAGE_TO_EVENT[stage], ...)` to write to structured logs

This means job stage, progress percent, and log events are always consistent.

---

## Error Classification

| Type | Source | Log destination | Level |
|---|---|---|---|
| **Type 1 — Request** | `HTTPException` raised before pipeline starts | `data/logs/request.log` (JSON line via `_emit_request_event`) + `desktop-backend.log` | WARNING |
| **Type 2 — Pipeline** | Exception inside `run_render_pipeline` | `data/logs/error.log` + `data/logs/app.log` + `channels/{code}/logs/{job_id}.log` | ERROR |
| **Type 3 — System** | Unhandled exception in a route function | `desktop-backend.log` (FastAPI default handler) | ERROR |

Type 2 errors use structured JSON lines with `error_code`, `step`, `exception`, and `traceback`.
Type 1 errors use structured JSON lines with `route`, `status_code`, and `detail`.

### Error codes (Type 2)

| Code | Meaning |
|---|---|
| `RN001` | Generic render error |
| `RN002` | File not found |
| `RN003` | Invalid output path / permission |
| `RN004` | ffmpeg process error |
| `RN005` | Scene detection failed |
| `RN006` | Trim / cut operation failed |

---

## text_layers Contract

Text layers are submitted as a JSON array in `RenderRequest.text_layers`.

Each layer is validated by `normalize_text_layers` in `services/text_overlay.py`:

| Field | Type | Constraint |
|---|---|---|
| `id` | str | required |
| `text` | str | non-empty |
| `font_family` | str | must be in `VALID_FONTS` (14 values) |
| `font_size` | int | 12–160 |
| `color` | str | hex `#RRGGBB` or `#RRGGBBAA` |
| `position` | str | one of 7 preset positions |
| `alignment` | str | `"left"` / `"center"` / `"right"` |
| `x_percent` | float | 0–100 |
| `y_percent` | float | 0–100 |
| `outline` | object | `{enabled, thickness}` |
| `shadow` | object | `{enabled, offset_x, offset_y}` |
| `background` | object | `{enabled, color, padding}` |
| `start_time` | float | ≥ 0 |
| `end_time` | float | ≥ 0 (0 = full duration) |

The frontend normalizes `outline`/`shadow`/`background` to objects before submission so Pydantic never receives flat values.

---

## Queue / Worker Model

- The job queue is an in-process `ThreadPoolExecutor` managed by `job_manager.py`
- One thread per job at the job level (a single job runs one pipeline at a time)
- Within a job, parts render in parallel up to `adaptive hw_cap` workers
- On server restart, `recover_pending_render_jobs()` re-queues any `queued` or `running` jobs found in the DB as `interrupted`

---

## Storage

| Location | Durable? | Contents |
|---|---|---|
| `data/app.db` | Yes | Jobs, job_parts, channels |
| `channels/{code}/` | Yes | Output videos, logs, channel config |
| `data/logs/` | Yes | Structured log files |
| `data/reports/` | Yes | Excel render reports |
| `data/temp/preview/` | No (6h TTL) | Editor session temp dirs |
| `_PREVIEW_SESSIONS` (in-memory) | No | Fast session lookup cache |
