# BACKEND_REVIEW.md — Backend Architecture Review

## Overview

FastAPI + Uvicorn backend, all Python. Single-machine desktop architecture using SQLite + threading.
No Redis, no Celery, no message broker. Everything runs in one process.

---

## Strengths

### API Architecture

1. **Clean router separation**: 9 routers, each in its own file with clear domain ownership. `render.py`, `jobs.py`, `upload.py`, `channels.py` etc. are all purpose-built.

2. **Job lifecycle design**: The `job_manager.py` priority heap + ThreadPoolExecutor is well-documented and appropriate for a single-machine tool. Priority ordering, FIFO tie-breaking, deduplication, and graceful shutdown are all handled.

3. **Cancel mechanism**: `cancel_registry.py` + thread-local cancel events is clean. Cancel propagates to FFmpeg subprocess kill within ~1s via the polling loop in `_run_ffmpeg_with_retry()`.

4. **Resume / Retry**: Resume skips already-completed parts (reads from DB). Retry re-runs only failed parts. Both are correct.

5. **WebSocket progress**: `ws_job_progress()` fingerprints state before sending — avoids sending on pure timestamp updates. Proper terminal close.

6. **DB write pattern**: Thread-local connections for high-frequency `update_job_progress` / `upsert_job_part` calls. `get_conn()` for everything else. WAL mode for concurrent reads. Good.

7. **Startup recovery**: Marks interrupted jobs correctly (never auto-restarts — correct for a desktop tool).

8. **Security (devtools)**: `ENABLE_DEVTOOLS=1` guard on arbitrary shell command execution. FFmpeg filter allowlist in `quick_process()`. DB file path never exposed to user input.

9. **Cache system**: Scene detection + transcription caching with 72h TTL and mtime-based invalidation is effective.

---

## Weaknesses

### God File: render_pipeline.py

**`backend/app/orchestration/render_pipeline.py` is 290KB / ~7,000+ lines.**

This is the single biggest architectural problem in the project. It contains:
- Download orchestration
- Scene detection caching
- Segment selection logic
- Variant building
- Transcription management
- Per-part render orchestration (subtitle slicing, TTS, audio mix, FFmpeg cut, encode, QA)
- AI edit plan integration
- Creator asset injection (intro/outro/logo)
- Output ranking
- CTA text injection
- Report generation
- Thumbnail extraction
- DB state writes
- Log helpers
- Event emission
- 15+ top-level config dicts (platform profiles, CTA texts, variant subtitle maps, etc.)

**Every change to any render stage requires navigating a 7,000-line file.** This is unsustainable. There is no natural split line between concerns — they are all inlined.

### services/db.py is a God Service

`backend/app/services/db.py` is ~1900 lines containing:
- Schema definition + migrations (init_db)
- Job CRUD
- Job parts CRUD
- Upload accounts CRUD
- Upload queue CRUD
- Upload history CRUD
- Upload scheduler state
- Runtime locks CRUD
- Proxy pool CRUD
- Creator prefs CRUD
- All normalization helpers for every table

This is every data access pattern in the entire app in one file. Adding a new entity requires adding schema, migration, CRUD, and normalization all in this file.

### Fat Route File: render.py

`backend/app/routes/render.py` is ~1400 lines containing:
- Preview session management (in-memory dict + disk fallback)
- Preview video transcoding
- Source preparation (YouTube + local)
- Render job creation
- Batch render coordination
- Local video upload
- FFmpeg quick-process endpoint
- Resumption logic
- Job cancellation
- Media streaming (Range requests)
- Thumbnail serving

The preview session management (`_PREVIEW_SESSIONS`, `_save_session`, `_load_session`, `_cleanup_preview_session`, `evict_stale_preview_sessions`) should be its own service. The `quick_process` endpoint is a complete inline pipeline with no shared code with the main pipeline.

### No Service Layer for AI

The AI subsystem has 60+ modules but no unified service interface. `render_pipeline.py` calls `create_ai_edit_plan()` directly and then manually extracts individual fields from the returned `AIEditPlan` with repeated `getattr()` calls scattered across the file. The AI plan is consumed inline, not through a service contract.

### Shared Module-Level State

- `_render_active_count` and `_render_active_lock` in `render_pipeline.py` track active renders but are accessed from `render.py` via direct import of private names (`_render_active_count`, `_JOB_SEM_VALUE`). This is a leaky abstraction.
- `_PREVIEW_SESSIONS` in `render.py` is module-level dict. No persistence on restart except for the disk JSON fallback.
- `_tv2_model` in `scene_detector.py` — TransNetV2 singleton locked with threading.Lock but never unloaded. On server shutdown, model stays in memory.

### Missing Rate Limiting

- No rate limiting on `/api/render/process`. A bad client can submit unlimited parallel render requests (each creates a job in the DB, each gets queued).
- No limit on `/api/render/prepare-source`. A bad actor can initiate unlimited YouTube downloads.

### Thread Safety in Batch

The batch render in `render.py` (`create_render_batch`) uses a bare `threading.Thread` (not job_manager) for the coordinator, then submits child jobs via `submit_job`. The coordinator waits on a per-child `threading.Event` with a 7200s timeout. If the child's `_ev.set()` is called before `_done.wait()`, everything is fine. But if the child fails catastrophically and `_done` is never set due to a bug in `_child_fn`, the coordinator hangs for 2 hours.

### Temp File Risk

Multiple places create intermediate files (`cut.mp4`, `.hook_intro.mp4`, `.with_intro.mp4`, `.cleaned.mp3`, etc.) that must be cleaned up by `finally: _safe_unlink(...)`. If the `finally` block is reached but the unlink fails (permissions, locked file on Windows), the temp file leaks. The background cleanup thread at 30min intervals is a safety net but relies on age-based deletion, not tracking.

### Error Handling Inconsistency

- `render_pipeline.py`: most errors are caught, logged via `_emit_render_event()`, and re-raised. Good.
- `render.py` `quick_process()`: FFmpeg errors raise `HTTPException(500)` but the work_dir cleanup in `finally` uses `shutil.rmtree(ignore_errors=True)` — good.
- AI module imports: wrapped in `try/except ImportError` with no-op fallbacks — graceful degradation, but if an AI module raises a non-ImportError at import time (syntax error, circular import), it silently swallows it as an ImportError match.

### No Authentication / Authorization

There is no authentication layer. Any process that can reach port 8000 can:
- Submit render jobs
- Read all job history
- Access all output files via media streaming
- Manage upload accounts (TikTok credentials)
- Execute arbitrary shell commands (if ENABLE_DEVTOOLS=1)

This is designed for single-user local use but is documented nowhere explicitly.

### Test Coverage Reality

80+ test files for AI modules but they are unit tests that:
- Mock all optional AI dependencies (sentence-transformers, faiss-cpu, etc.)
- Test the AI schema/schema validators, not real AI behavior
- Never test render_pipeline.py, render_engine.py, or the FFmpeg integration

The core pipeline (the most critical code) has zero tests.

---

## Architecture Problems

| Problem | File | Severity |
|---------|------|----------|
| God file render_pipeline.py (290KB) | `app/orchestration/render_pipeline.py` | Critical |
| God service db.py (1900 lines) | `app/services/db.py` | High |
| Fat route render.py (1400 lines) | `app/routes/render.py` | High |
| No service layer for AI integration | `render_pipeline.py` + `ai/director/` | High |
| Module-level shared state for preview sessions | `routes/render.py:74` | Medium |
| No rate limiting on render/download | `routes/render.py` | Medium |
| Batch child hang risk (7200s wait) | `routes/render.py:749` | Medium |
| V2/V3/V4 static ship but are not the default | `static-v2/`, `static-v3/`, `static-v4/` | Medium |
| Temp file leak risk on Windows locks | `render_pipeline.py` throughout | Medium |
| No authentication | `main.py` | Low (desktop-only) |

---

## Production Risks

1. **Single SQLite database**: All job state, upload accounts (TikTok credentials), and render history in one file. No backup strategy. Corruption = total data loss.

2. **Thread-local DB connections**: If a render thread throws without calling `close_thread_conn()`, the connection leaks. The `finally` at the end of `run_render_pipeline` calls it, but the call site is in `process_render` in `render.py`, not in the pipeline itself.

3. **FFmpeg subprocess on Windows**: `subprocess.Popen` with `stdout/stderr=PIPE` + manual communicate thread. If the communicate thread crashes, `_done` is never set, and the main loop runs until `_FFMPEG_TIMEOUT_SEC` (default 3600s). This would stall the job worker for an hour.

4. **No disk space checking**: Render pipeline never checks available disk before starting. A full disk causes FFmpeg to produce a 0-byte output file, which triggers "Output file empty" error after all processing is done — no early warning.
