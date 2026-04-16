# Business Profile — Render Studio
**Cowork Version**: 2.0 | **Language**: English | **Domain**: AI Video Processing & Social Media Automation

---

## 1. Project Overview

**Product Name**: Render Studio (internal codename: `tool-render-video`)

**Type**: Local AI-powered desktop + web application

**Stack**:
- **Desktop shell**: Electron (`desktop-shell/main.js`) — launches backend, waits for `/health`, opens browser UI
- **Backend**: FastAPI (Python 3.11+) — all business logic, AI processing, job management
- **Database**: SQLite (`data/app.db`) — durable job, channel, and run state
- **AI/ML**: OpenAI Whisper (transcription), OpenCV (scene detection), yt-dlp (YouTube source)
- **Automation**: Playwright + Chromium (TikTok upload automation)
- **Media processing**: ffmpeg 6+ (cut, render, subtitle overlay, volume normalization)

**Deployment**: Local machine (Windows primary, Docker supported). Not a cloud SaaS.

**Entry points**:
- `POST /api/render/process` — trigger a render job
- `POST /api/upload/schedule/start` — trigger an upload run
- WebSocket streams for real-time progress

---

## 2. Domain

**Primary domain**: Short-form video production automation

**Sub-domains**:
1. **Render pipeline** — source resolution (editor/local file/YouTube), optional trim/volume, scene detection, viral scoring, per-segment subtitle generation, ffmpeg rendering, output packaging
2. **Upload automation** — multi-platform social media upload (TikTok via Playwright, YouTube Shorts via API), schedule management, caption management, upload reporting
3. **Job management** — async job queue (ThreadPoolExecutor), status tracking, crash recovery, part-level parallelism
4. **Channel management** — platform credentials, upload presets, scheduling rules per channel

---

## 3. Business Goals

| Priority | Goal | Success Metric |
|---|---|---|
| 1 | Render a batch of short-form videos without manual intervention | Zero manual steps from source → rendered file |
| 2 | Auto-generate subtitles accurate enough for TikTok/YouTube | Whisper accuracy ≥ 90% word accuracy on clear speech |
| 3 | Auto-upload rendered videos on a schedule | Upload success rate ≥ 98% per batch |
| 4 | Detect and rank viral potential before upload | Viral score computed for every segment; top N selected |
| 5 | Recover from crashes without losing completed work | No job permanently stuck in "running" after restart |
| 6 | Support multiple social media platforms without code changes | Channel type is the only differentiator between platforms |

---

## 4. Core Entities

### Job
The primary unit of work in the render pipeline.

| Field | Type | Description |
|---|---|---|
| `job_id` | string | Unique identifier |
| `status` | enum | `queued → running → completed / failed / interrupted` |
| `source_type` | enum | `editor / local / youtube` |
| `source_url` | string | YouTube URL or local file path |
| `created_at` | datetime | Submission time |
| `completed_at` | datetime | Finish time (null if not done) |

**Critical status transitions**:
- `queued → running`: when worker thread picks up the job
- `running → completed`: all parts rendered successfully
- `running → failed`: unrecoverable error
- `running → interrupted`: server crash detected on restart (recovery path)

### JobPart
A segment of a job. One job produces N parts (based on scene detection).

| Field | Type | Description |
|---|---|---|
| `part_id` | string | Unique within job |
| `job_id` | string | Parent job |
| `segment_index` | int | Position in source video |
| `viral_score` | float | 0.0–1.0, computed by scoring model |
| `render_path` | string | Output file path |
| `subtitle_path` | string | SRT/ASS subtitle file path |
| `status` | enum | `pending / rendering / done / failed` |

### Channel
A social media platform destination with credentials and upload settings.

| Field | Type | Description |
|---|---|---|
| `channel_id` | string | Unique identifier |
| `platform` | enum | `tiktok / youtube_shorts` (extensible) |
| `credentials` | json | Platform-specific auth (never logged) |
| `schedule_rules` | json | Upload time windows, frequency limits |
| `caption_template` | string | Default caption with `{{title}}` interpolation |

### UploadRun
A single scheduled upload batch for one channel.

| Field | Type | Description |
|---|---|---|
| `run_id` | string | Unique identifier |
| `channel_id` | string | Target channel |
| `status` | enum | `pending / running / completed / failed` |
| `files` | list | Rendered files to upload in this run |
| `uploaded` | list | Successfully uploaded files |
| `failed` | list | Failed files with error reasons |

### RenderReport
Excel report generated at job completion. Located at `data/<job_id>/render_report.xlsx`.

### UploadReport
Excel report generated at run completion. Located at `data/<run_id>/upload_report.xlsx`.

---

## 5. Expected Outputs

### Per render job
- Rendered video segments (mp4) in `data/<job_id>/parts/`
- Subtitle files (SRT/ASS) per segment in `data/<job_id>/subtitles/`
- `render_report.xlsx` with per-part status, viral score, duration, file size
- Structured log events: `render.job.started`, `render.part.completed`, `render.job.completed`

### Per upload run
- Upload receipts per platform (TikTok post URL, YouTube video ID)
- `upload_report.xlsx` with per-file status, platform, timestamp, URL
- Files moved from pending to `channels/<channel_id>/uploaded/` or `channels/<channel_id>/failed/`
- Structured log events: `upload.run.started`, `upload.file.completed`, `upload.run.completed`

### Per cowork pipeline run
- `artifacts/<task_id>/<run_id>/final-summary.md` — human-readable engineering task report
- All pipeline artifacts (see COWORK_SYSTEM_DEFINITION.md §11)

---

## 6. Business Rules

### Render pipeline rules

1. **Source resolution is mandatory before rendering.** A job cannot enter `running` state without a resolved source path. YouTube sources must be downloaded via yt-dlp first.

2. **Scene detection drives segmentation.** Segments are defined by scene change detection (OpenCV). Minimum segment duration: 15 seconds. Maximum: 60 seconds for short-form output.

3. **Viral scoring is computed before render.** Only segments with `viral_score ≥ threshold` (configurable, default 0.6) proceed to full render. Lower-scored segments are saved as metadata but not rendered by default.

4. **Subtitle generation is per-part, not per-job.** Each `JobPart` has its own subtitle file. Subtitle generation uses Whisper; language is auto-detected.

5. **Render has a fallback.** If primary render fails, the pipeline retries with a simplified ffmpeg command (no effects, no overlay). If fallback also fails, the part status is set to `failed` and the job continues with remaining parts.

6. **Job recovery on restart.** On startup, all jobs in `queued` or `running` state are set to `interrupted`. The UI notifies the user. Manual re-trigger is required (automatic retry of interrupted jobs is not allowed without user confirmation).

### Upload pipeline rules

7. **Login check before upload.** Every upload run starts with a platform login verification. If login fails, the run is aborted with status `failed` and a clear error message.

8. **Dry-run mode is always available.** Upload can be executed in dry-run mode: all steps run except the actual upload API call. Used for testing schedule and caption configuration.

9. **Files are moved after upload.** Successfully uploaded files are moved to `channels/<channel_id>/uploaded/`. Failed files are moved to `channels/<channel_id>/failed/` with an error log entry.

10. **Caption must not exceed platform limit.** TikTok: 2200 characters. YouTube: 5000 characters. If caption exceeds limit, it is truncated with a trailing `...` and a warning is logged.

11. **Upload schedule respects rate limits.** No more than 3 uploads per hour per channel. No uploads between 2:00–6:00 AM local time (default; configurable per channel).

### Security rules

12. **Credentials are never stored in plain text in source files.** Platform credentials are stored in the SQLite database, encrypted at the application layer. Never log credential fields.

13. **YouTube source downloads require explicit user consent.** The user must acknowledge that downloading from YouTube complies with the platform's terms of service.

14. **API keys are read from environment variables only.** Never accept API keys via the API endpoint body or query parameters.

---

## 7. Acceptance Criteria

These are domain-specific acceptance criteria patterns. Append project-specific values when creating tasks.

### For bugfix tasks

```
- [ ] The reported error condition no longer occurs under the same input conditions
- [ ] Existing behavior for all other input conditions is unchanged (regression-free)
- [ ] The fix is covered by a test that would have caught the original bug
- [ ] A structured log event is emitted when the error condition is detected and handled
- [ ] No new dependency is added
```

### For render pipeline tasks

```
- [ ] Job status transitions are correct: queued → running → completed/failed/interrupted
- [ ] Interrupted jobs are detectable on server restart and not automatically re-triggered
- [ ] Per-part status is tracked independently; one part failing does not fail the whole job
- [ ] RenderReport is generated and contains accurate per-part data
- [ ] ffmpeg command is logged at DEBUG level before execution
```

### For upload pipeline tasks

```
- [ ] Upload dry-run mode works without making any real API calls
- [ ] Files are moved to uploaded/ or failed/ directories after run completion
- [ ] UploadReport is generated with per-file status and timestamps
- [ ] Login verification runs before first upload attempt in every run
- [ ] Caption length is validated before upload; truncation is logged as a warning
```

### For schema/data model tasks

```
- [ ] New fields are added with default values; no existing row is broken
- [ ] Migration script is provided if column addition requires backfill
- [ ] SQLite schema is reflected in the Pydantic model
- [ ] additionalProperties: false is maintained on affected JSON schemas
```

---

## 8. Terminology Rules

These rules are mandatory. AI must use exact terms — no synonyms, no paraphrasing.

| Correct Term | Do NOT use | Notes |
|---|---|---|
| `job` | task, request, render_task | The primary work unit in the render pipeline |
| `job_part` / `part` | segment, chunk, clip | A rendered segment within a job |
| `upload_run` / `run` | upload_job, upload_task, batch | A scheduled upload execution |
| `channel` | account, platform_account, destination | A social media platform connection |
| `viral_score` | popularity_score, engagement_score | The computed ranking metric per part |
| `interrupted` | crashed, stopped, aborted | Job status after server crash recovery |
| `scene_detect` | split, cut_detect, frame_analysis | OpenCV scene change detection step |
| `render_report` | output_report, job_report | The Excel file produced per job |
| `upload_report` | upload_log, run_report | The Excel file produced per upload run |
| `caption` | description, text, post_text | The text that accompanies a social media post |
| `subtitle` | captions (for video overlay), transcript | The SRT/ASS overlay file on the video itself |
| `dry_run` | test_mode, simulation, preview | Upload run without real API calls |
| `executor_mode` | run_mode, mode | Cowork pipeline execution mode |
| `task_pack` | prompt_pack, task_file | The markdown file sent to Claude CLI |

**Platform name capitalization:**
- `TikTok` (not tiktok, Tiktok)
- `YouTube` (not Youtube, youtube)
- `YouTube Shorts` (not YT Shorts, youtube shorts)
- `Whisper` (not whisper, OpenAI Whisper — unless citing the library)

---

## 9. Constraints

### Hard constraints (AI must never violate)

1. **Do not touch `backend/.venv/`** — Python virtual environment; managed by pip, never by AI
2. **Do not modify `data/app.db` directly** — SQLite database; all changes must go through migration scripts or Pydantic models
3. **Do not change ffmpeg command structure** without understanding the full render pipeline in `backend/app/services/render_pipeline.py`
4. **Do not remove Playwright browser automation** for TikTok — there is no public TikTok API for video upload; Playwright is the only viable path
5. **Do not add `async` to functions in the Electron main process** without verifying Electron's IPC event loop compatibility
6. **Do not change the job status machine** (the 5 states: `queued / running / completed / failed / interrupted`) without updating all downstream consumers: UI polling, report generation, startup recovery

### Scope constraints by task type

| Task type | Always in scope | Always out of scope |
|---|---|---|
| `bugfix` | The specific file containing the bug | Other services, frontend, database schema |
| `feature` | Files explicitly named in task | Existing working adapters (e.g. don't touch TikTok when adding YouTube) |
| `refactor` | Declared module only | Any route handler or API contract |
| `performance` | The bottleneck identified in profiling | Correctness changes unrelated to performance |
| `infra` | Docker, setup scripts, config files | Application logic |

---

## 10. Risks

### High-probability risks

| Risk | Category | Mitigation |
|---|---|---|
| ffmpeg command change breaks all renders | Regression | Never change ffmpeg args without a before/after test render |
| Playwright selector breaks after TikTok UI update | External dependency | Always check selector in `upload_service.py` before assuming it works |
| Whisper model not loaded; subtitle generation silently skipped | Silent failure | Always verify `whisper.load_model()` response before calling `.transcribe()` |
| SQLite WAL lock under concurrent workers | Concurrency | Use the existing `job_manager` lock pattern; do not introduce new raw DB connections in threads |
| Large YouTube source (> 1 hour) causing OOM during download | Resource | yt-dlp size limits should be checked before download; stream-download is preferred |

### Low-probability but high-impact risks

| Risk | Category | Mitigation |
|---|---|---|
| yt-dlp format change causes all YouTube downloads to fail | External dependency | Pin yt-dlp version in requirements.txt; test before upgrading |
| Electron main process crash on Windows path with spaces | Platform-specific | Always quote all file paths in Electron IPC and shell invocations |
| Whisper GPU memory exhaustion on long batches | Resource | Use `fp16=False` on CPU; enforce max batch size per worker |
| TikTok account flagged for automation | Policy | Use human-like delays in Playwright upload; never upload > 3 videos/hour |

---

## 11. Assumptions

The following assumptions were made based on codebase analysis. If any are incorrect, update this document and the corresponding `docs/` files.

1. **ASSUMPTION**: The primary target OS is Windows 11. The setup scripts (`setup.ps1`, `run-desktop.ps1`) use PowerShell. Docker is a secondary deployment path.

2. **ASSUMPTION**: Whisper model size is `base` or `small` by default. The `large` model is not used in production due to RAM constraints on typical developer machines (8–16GB).

3. **ASSUMPTION**: The SQLite database does not need multi-process write access. All writes go through the single FastAPI process. If this changes, WAL mode must be enabled and all write paths must be reviewed.

4. **ASSUMPTION**: YouTube Shorts upload uses the YouTube Data API v3 (not Playwright) since YouTube has a public API. If credentials for the API are unavailable, Playwright automation is the fallback.

5. **ASSUMPTION**: The `viral_score` model is a heuristic function (not a trained ML model). Replacing it with a real ML model is a future task outside current scope.

6. **ASSUMPTION**: The Electron shell does not process video itself; it is purely a UI host. All compute happens in the FastAPI backend process.

7. **ASSUMPTION**: `claude-cowork-v2/` is a sibling directory to the main project source, not embedded within it. The cowork pipeline operates on the main project by having Claude CLI invoke with the main project as working directory.
