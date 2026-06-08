# 18 — Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│  Electron desktop shell (desktop-shell/)                               │
│  - bootstrap python venv, install Chromium, spawn backend              │
│  - preload bridge (8 IPC methods) exposed to renderer                  │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │  loads
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│  React SPA (frontend/src/)                                             │
│  - Zustand stores (uiStore, renderStore, qualityStore, editorStore)    │
│  - Panel-based routing (no URL router)                                 │
│  - 7 feature folders: clip-studio (primary), jobs, progress,           │
│    downloader, editor, quality, settings                               │
│  - WS client (RenderSocketClient) for live render progress             │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │  HTTP + WS over localhost
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│  FastAPI app (backend/app/main.py)                                     │
│  - 11 mounted routers (13 with V2)                                     │
│  - 70 endpoints total (36 USED, 24 UNCALLED, 2 WS, 2 deprecated)       │
│  - 3 daemon startup threads (Whisper warmup, cleanup loop, cookies)    │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
                  ┌────────────────┴────────────────┐
                  │                                 │
                  ▼                                 ▼
       ┌──────────────────────┐         ┌─────────────────────────┐
       │  Job manager         │         │  Routes (read-mostly)   │
       │  - priority heap     │         │  - /api/jobs/{id}       │
       │  - ThreadPoolExecutor│         │  - WS /api/jobs/{id}/ws │
       │  - cancel registry   │         │  - /api/jobs/history    │
       └──────────┬───────────┘         │  - /api/settings/...    │
                  │                     │  - /api/feedback/...    │
                  ▼                     └────────────┬────────────┘
       ┌─────────────────────┐                       │
       │  Worker thread      │                       │
       │  - _thread_conn DB  │                       │
       │  - run_render_pipe  │                       │
       └──────────┬──────────┘                       │
                  │                                  │
                  ▼                                  ▼
       ┌─────────────────────────────────────────────────────────────┐
       │  SQLite (data/app.db) — WAL, single file, sole authority    │
       │  Tables: jobs, job_parts, creator_prefs, download_jobs,     │
       │          clip_feedback, schema_versions                     │
       └─────────────────────────────────────────────────────────────┘

       Render pipeline (features/render/engine/pipeline/):

       run_render_pipeline()
         ├─ setup
         ├─ source_prep (local file or editor session)
         ├─ optional manual narration TTS
         ├─ llm_pipeline       ── mandatory; Whisper → LLM → segments
         ├─ optional RenderPlan emission (LLM Call 2)
         ├─ subtitle gating
         ├─ render_loop (per-part, ThreadPoolExecutor)
         │   └─ part_renderer
         │       ├─ asset_planner (SRT slice + ASS + camera strategy)
         │       ├─ part_cut       (or fused skip per Sprint 7.4/7.8)
         │       ├─ part_render_setup (encode params + progress timer)
         │       ├─ part_render_encode (FFmpeg + NVENC semaphore)
         │       ├─ part_voice_mix   (edge-tts or XTTS + mix)
         │       ├─ part_render_finalize (Sacred #8 qa_pipeline gate)
         │       └─ part_done
         └─ pipeline_finalize (result.json + Sacred #1 keys + best-export)
```

## Module layering (clean / breakdown)

| Layer | Allowed dependencies | Status |
|---|---|---|
| `domain/` | stdlib only | ✓ leaf — no reverse imports |
| `db/` | `domain/` | ✓ |
| `core/` | `domain/` | ✓ |
| `services/` (non-feature) | `db/`, `core/` | ⚠ leak: `services/maintenance.py`, `services/warmup.py` know render details (Phase 3 A15/A16) |
| `features/render/`, `features/download/` | everything above + each other | ⚠ cross-feature imports (Phase 3 A08) |
| `jobs/` | `db/`, `domain/`, `features/render/` (via callable submission) | ✓ |
| `routes/` + `features/*/router.py` | everything | ✓ |
| `main.py` | wires all of the above | ✓ |

## Threading model

- 1 main asyncio event loop (FastAPI/uvicorn).
- 1 scheduler daemon thread (`jobs/manager.py::_scheduler_loop`).
- 1 cleanup loop daemon ([main.py:266](../../backend/app/main.py)).
- 1 Whisper warmup daemon ([main.py:264](../../backend/app/main.py)).
- 1 cookie-extraction daemon ([main.py:280](../../backend/app/main.py)).
- N worker threads inside ThreadPoolExecutor (N = `MAX_CONCURRENT_JOBS`, default `cpu_count // 2`).
- Inside each worker: progress timer thread per active encode (3 s cadence).
- Async asyncio.run for edge-tts inside each worker (Phase 4 BR08).

WAL DB serialises all writes via SQLite's per-DB write lock; readers go concurrent.

## Persistence boundary

| Concern | Where |
|---|---|
| Job state | `data/app.db` (SQLite WAL) |
| In-flight LLM responses | not persisted (Phase 6 AI06) |
| Whisper transcripts | `cache/transcription/{hash}.srt` (72 h TTL) |
| Scene detect | `cache/scene_detect/{hash}.json` (72 h TTL) |
| Motion path | `cache/motion_paths/` (72 h TTL) |
| ASS content | `cache/ass/` (content-addressable) |
| Per-job logs | `data/logs/job-{job_id}/` (pruned at startup + every 30 min) |
| Backups | `data/backups/app.db.snap-*` (retention 10) |

End of 18_architecture.md.
