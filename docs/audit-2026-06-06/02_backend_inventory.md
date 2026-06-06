# 02 — Backend Inventory

Branch `feature/ai-workflow-upgrade`. Source of truth: `backend/app/**/*.py`. `backend/.venv/`, `backend/static*/`, and `backend/tests/` are out of scope here (tests covered in Phase 9).

> **Critical pre-finding:** The branch carries a *"Phase 1-18 backend feature-layer migration"* (commits `cf80766` + `e641a21`). The current `CLAUDE.md` (in the repo) still describes the OLD layout (`orchestration/`, `services/render/`, `ai/` at `backend/app/`-level). Those paths are GHOST DIRECTORIES on this branch — code now lives under `backend/app/features/`. Documentation is **misleading** on this branch.

---

## A. Entry point — [backend/app/main.py](../../backend/app/main.py) (369 LOC)

### A.1 Routers mounted

| # | Router | Prefix | Source |
|---|---|---|---|
| 1 | `channels_router` | `/api/channels` | `routes/channels.py` |
| 2 | `render_router` | `/api/render` | `features/render/router.py` |
| 3 | `jobs_router` | `/api/jobs` | `routes/jobs.py` |
| 4 | `devtools_router` | `/api/dev` | `routes/devtools.py` — **conditional, `ENABLE_DEVTOOLS=1` only, loopback-only** ([main.py:133](../../backend/app/main.py)) |
| 5 | `voice_router` | `/api/voice` | `routes/voice.py` (~20 LOC — minimal TTS test) |
| 6 | `files_router` | `/api/files` | `routes/files.py` |
| 7 | `editing_router` | `/api/jobs` | `features/render/editing/router.py` (sub-routes under jobs) |
| 8 | `platform_downloader_router` | `/api/downloader` | `features/download/router.py` |
| 9 | `feedback_router` | `/api/feedback` | `routes/feedback.py` |
| 10 | `metrics_router` | `/api/metrics` | `routes/metrics.py` — Prometheus scrape |
| 11 | `settings_router` | `/api/settings` | `routes/settings.py` |
| (12) | `v2_download_router` | (V2) | `v2.api.routes.download` — **conditional, `ENABLE_V2=1`** |
| (13) | `v2_render_router` | (V2) | `v2.api.routes.render` — same gate |

Evidence: `app.include_router(...)` lines 113–147 of main.py.

### A.2 Static mounts

`STATIC_UI_VERSION` env var selects either `/assets` (v2) or `/static` (legacy). When `backend/static/` doesn't exist, the legacy mount is skipped (Sprint commit `6fae76f`).

### A.3 Startup tasks ([main.py:227 `@app.on_event("startup")`](../../backend/app/main.py))

1. `init_db()` (DB schema + migrations) — main.py:231
2. `_check_db_fallback_at_startup()` — verifies primary DB writable, falls back to LOCALAPPDATA — main.py:232
3. Default channel `"k1"` created — main.py:233
4. Job log prune — main.py:234-236
5. Preview dir prune — main.py:237
6. Render temp dir cleanup — main.py:238
7. **Render cache 72h prune** — main.py:241
8. XTTS cache 30-day prune — main.py:246
9. Text overlay dir 7-day prune — main.py:248
10. `recover_pending_render_jobs()` — marks interrupted jobs — main.py:250
11. `start_warmup()` — main.py:251

**Daemon threads spawned** (lines 254–280):
- Whisper warmup
- Periodic cleanup loop (every `CLEANUP_INTERVAL_SEC`, default 1800s)
- YouTube cookie extraction

### A.4 Shutdown

main.py:333 `@app.on_event("shutdown")`: graceful job manager drain with `SHUTDOWN_TIMEOUT_SEC` (default 30s).

### A.5 Middleware

CSP middleware for v2 UI ([main.py:177-184](../../backend/app/main.py)).

---

## B. Top-level layout under `backend/app/`

```
main.py                              369 LOC
core/        config, logging, stage, ui_gate, devtools_safety
db/          connection.py (394), jobs_repo.py, creator_repo.py, download_repo.py, feedback_repo.py, migrations.py, migration_steps/
domain/      render_plan.py, creator_context.py, manifests.py, timeline.py
features/    download/, render/   (the new home of the world)
jobs/        manager.py, cancel.py
models/      schemas.py             (Pydantic API contracts)
routes/      channels, jobs, feedback, files, settings, voice, metrics, devtools
services/    bin_paths.py, channel_service.py, db.py (49-line facade), maintenance.py, metrics.py, qa_runner.py, warmup.py
ai/          *** EMPTY — only __pycache__ ***
orchestration/  *** EMPTY — only __pycache__ + empty stages/ ***
quality/        *** EMPTY ***
```

**FINDING-B01 (MEDIUM):** Three ghost directories exist with zero `.py` files:
- `backend/app/ai/` — has empty `analysis/`, `context/`, `llm/`, `visibility/` subdirs (only `__pycache__`)
- `backend/app/orchestration/` — has empty `stages/`
- `backend/app/quality/` — empty

CLAUDE.md still treats `backend/app/orchestration/render_pipeline.py` as the primary CRITICAL file. That file does not exist on this branch. The real file is `backend/app/features/render/engine/pipeline/render_pipeline.py` (1357 LOC — up 28% from the 1,103 LOC claimed in CLAUDE.md). **Stale doc + ghost dirs together create a confusing trap for any new agent.** Cleanup recommended in Phase 11.

---

## C. Feature modules

### C.1 `features/download/`

[backend/app/features/download/](../../backend/app/features/download/)

| File | Purpose |
|---|---|
| `router.py` | `APIRouter(prefix="/api/downloader")` |
| `service.py` | high-level orchestration |
| `engine/engine.py`, `downloader.py`, `platform_detect.py`, `file_naming.py`, `tiktok_handler.py`, `cookie_extractor.py` | core download flow |
| `adapters/{youtube,tiktok,instagram,facebook,douyin,generic}.py` | platform-specific yt-dlp wrappers |

### C.2 `features/render/`

The largest feature. Subdirectories:

```
features/render/
├── router.py                      # /api/render mount
├── ai/                            # LLM + content analysis (was backend/app/ai/)
├── editing/                       # trim/rerender/export
├── engine/
│   ├── audio/                     # mixer, tts (edge), tts_xtts
│   ├── encoder/                   # ffmpeg_helpers, clip_renderer, clip_ops, overlay_compositor, encoder_helpers
│   ├── motion/                    # detection, crop, cache, path, tracker, trackerless, scoring, utils, pixel_diff, config
│   ├── overlay/                   # text_overlay
│   ├── pipeline/                  # render orchestrator + stages + QA + caching (see D)
│   ├── preview/                   # session_service, media_streaming, ffmpeg_probers
│   ├── quality/                   # assessor, models, report_locator, report_summary
│   ├── stages/                    # part_* per-clip stages (was backend/app/orchestration/stages/)
│   ├── subtitle/                  # transcription/, generator/, processing/, translation_service
│   └── thumbnail/                 # thumbnail_quality
```

### C.3 Render pipeline orchestrator

[backend/app/features/render/engine/pipeline/render_pipeline.py](../../backend/app/features/render/engine/pipeline/render_pipeline.py) — 1357 LOC, **CRITICAL tier**. Owns:

- `JobStage` transitions: `QUEUED → DOWNLOADING → RENDERING → DONE` (`+ FAILED/CANCELLED` terminals)
- Feature flags (verified at top of file):
  - `_FEATURE_RAW_PART_SKIP` (Sprint 7.4, default OFF) — fused cut+render
  - `_FEATURE_RAW_PART_SKIP_MOTION_AWARE` (Sprint 7.8, default OFF)
  - `_FEATURE_BASE_CLIP_FIRST` (default OFF)
  - `_FEATURE_OVERLAY_AFTER_BASE_CLIP` (default OFF)
- Mandatory LLM pre-render (Phase F1) — HARD-FAIL if LLM unavailable

Pipeline stage modules in same dir:

| File | Role |
|---|---|
| `pipeline_setup.py` | dir prep, profile resolution |
| `pipeline_source_prep.py` | download/local source handling |
| `llm_pipeline.py`, `llm_stage.py` | LLM segment selection |
| `parallel_analysis.py` | concurrent scene detect + Whisper |
| `asset_pipeline.py` | logos/intros/outros |
| `pipeline_render_loop.py` | ThreadPoolExecutor parallel part dispatch |
| `pipeline_segment_selection.py`, `pipeline_ranking.py` | clip choice + ranking |
| `pipeline_subtitle_utils.py`, `pipeline_config.py`, `pipeline_cache.py` | helpers |
| `pipeline_finalize.py` | aggregate outputs |
| `qa_pipeline.py` | output validation gate (Sacred Contract #8) |
| `render_events.py` | WS event emission |
| `db_backup.py` | atomic SQLite snapshots |
| `report_service.py`, `render_output.py`, `workflow_trace.py` | side artifacts |

Per-part stages in [features/render/engine/stages/](../../backend/app/features/render/engine/stages/):
`part_renderer.py` (skeleton), `part_render_context.py`, `part_asset_planner.py`, `part_cut.py`, `part_render_setup.py`, `part_render_encode.py`, `part_voice_mix.py`, `part_render_finalize.py`, `part_done.py`, `manifest_writer.py`, `viral_scoring.py`.

---

## D. Routes

### D.1 Legacy `routes/`

| File | URL prefix | Notes |
|---|---|---|
| channels.py | `/api/channels` | list/create/get |
| jobs.py | `/api/jobs` | status, parts, WS progress, history |
| feedback.py | `/api/feedback` | clip +1/-1 ratings |
| files.py | `/api/files` | list/download |
| settings.py | `/api/settings` | creator-context |
| voice.py | `/api/voice` | TTS test (~20 LOC) |
| metrics.py | `/api/metrics` | Prometheus (~34 LOC) |
| devtools.py | `/api/dev` | **SHELL EXEC, env-gated** |

### D.2 Feature `router.py`

| File | URL prefix | Notes |
|---|---|---|
| `features/render/router.py` | `/api/render` | `process`, `prepare-source`, `resume`, `retry`, `cancel`, `preview-video`, `preview-transcript`, `test-cloud-ai` |
| `features/render/editing/router.py` | `/api/jobs` | trim/rerender/export under `parts/{partNo}/` |
| `features/download/router.py` | `/api/downloader` | start, batch, WS progress, cancel |

**FINDING-B02 (LOW):** Editing routes are mounted under `/api/jobs/` (not `/api/render/`) because they operate on a stored job. Documentation-wise this is non-obvious — a new developer would search `routes/jobs.py` first and miss them. Phase 7 + 10 should call out.

---

## E. Services & repositories

### E.1 `services/`

| File | Purpose |
|---|---|
| `bin_paths.py` | FFmpeg/ffprobe path resolution, `get_ffmpeg_bin`, `get_ffprobe_bin`, `ensure_ffmpeg_available` |
| `channel_service.py` | channel directory setup |
| `maintenance.py` | `prune_job_logs`, `prune_preview_dirs`, `prune_render_temp_dirs`, `prune_xtts_cache`, `prune_text_overlay_dir`, `prune_render_cache` |
| `metrics.py` | Prometheus gauges (`JOB_QUEUE_ACTIVE`, `JOB_QUEUE_PENDING`) |
| `warmup.py` | startup warmup tasks |
| `qa_runner.py` | tiny QA helper (~40 LOC) |
| `db.py` | **49-line re-export facade**: `from app.db.connection import *; from app.db.jobs_repo import *; ...` |

**FINDING-B03 (LOW):** `services/db.py` is a backward-compat shim, not dead code. Still imported by `features/render/editing/editing_service.py` and others. Keep until callers are migrated.

### E.2 `db/` repositories

| File | Tables | Connection helper | Highlights |
|---|---|---|---|
| `jobs_repo.py` | jobs, job_parts | `db_conn` (HTTP) + `_thread_conn` (render hot path) | `upsert_job`, `update_job_progress`, `save_error_kind`, `update_render_plan`, `get_render_plan`, `delete_job`, `upsert_job_part`, `list_jobs_page`, `list_job_parts`, `list_job_parts_bulk` |
| `creator_repo.py` | creator_prefs (singleton) | `db_conn` | `get/upsert_creator_prefs`, `get/upsert_creator_context` (nested JSON) |
| `feedback_repo.py` | clip_feedback | `db_conn` | basic CRUD |
| `download_repo.py` | download_jobs | `db_conn` (migrated Sprint 5.4) | CRUD |

See `03_database_inventory.md` for schema detail.

---

## F. AI pipeline

[backend/app/features/render/ai/](../../backend/app/features/render/ai/) — ~60 files.

| Submodule | Files | Role |
|---|---|---|
| `analysis/` | `hybrid.py`, `local.py`, `cloud/{openai_provider,base,response_parser,prompt_builder}.py`, `contract.py`, `signals.py`, `merger.py` | local heuristics + cloud LLM content analysis |
| `llm/` | `providers/{claude,openai,gemini}.py`, `parser.py`, `prompts.py` | provider abstraction + prompts + parser |
| `context/` | `builder.py` | CreatorContext signal builder |
| `visibility/` | `ai_visibility_summary.py` | AI decision tracing → FE |
| root | `dependencies.py`, `diagnostics.py`, `tracing.py` | optional-import gates, lazy loading |

Call chain (representative):

```
pipeline_render_loop.run_render_loop()
  → llm_pipeline.run_llm_pre_render()
    → llm_stage.run_llm_segment_selection()
      → analysis/hybrid.run_content_analysis()
        → llm/providers/claude.select_segments() / openai / gemini
        → llm/parser.parse_segment_response()
```

Default LLM provider: Claude (`claude-haiku-4-5-20251001`) — verify in Phase 5.

**Sacred Contract #3 status:** Every provider file under `llm/providers/` should catch all exceptions and return `None`. Phase 4 (bug risk) will verify.

---

## G. Background jobs & queues

### G.1 Job manager — [backend/app/jobs/manager.py](../../backend/app/jobs/manager.py) (~350 LOC)

- Priority min-heap (higher int = higher priority, FIFO within tier).
- Scheduler thread drains heap into a `ThreadPoolExecutor`.
- `MAX_CONCURRENT_JOBS` default = `cpu_count // 2` (env override).
- Thread-local DB connection cache per worker (the `_thread_conn` model — see Phase 8).

### G.2 Cancel registry — [backend/app/jobs/cancel.py](../../backend/app/jobs/cancel.py) (~86 LOC)

- One `threading.Event` per job_id.
- Jobs poll `cancel_event.is_set()` at safe checkpoints.
- `cancel_all_active()` triggered on shutdown.

### G.3 Schedulers (all threading-based, no APScheduler/asyncio loops)

| Loop | Cadence | Spawned at |
|---|---|---|
| Periodic cleanup (preview, render temp, XTTS, text overlay, render cache) | 1800s | main.py:266 |
| Whisper warmup | once | main.py:264 |
| YouTube cookie extraction | once | main.py:280 |

---

## H. Models — Pydantic [backend/app/models/schemas.py](../../backend/app/models/schemas.py) (~1000 LOC)

Key request models:

- `RenderRequest` (lines 111–398) — main render payload; `model_config = ConfigDict(extra="ignore")` (line 117). Sacred Contract #2: new fields **must default to False / disabled**.
- `PrepareSourceRequest`
- `QuickProcessRequest`
- `DownloadBatchRequest`
- `TextLayerConfig`
- `TrimRequest`, `RerenderRequest`, `ExportRequest`

**FINDING-B04 (LOW):** `extra="ignore"` on `RenderRequest` is correct for backward compat replay but silently drops typo'd field names from the FE. Phase 7 should diff actual FE payload keys against accepted model fields.

---

## I. Notable dead / facade / sentinel surface

| Item | Status | Recommendation |
|---|---|---|
| `backend/app/ai/`, `backend/app/orchestration/`, `backend/app/quality/` | Ghost dirs (no `.py`) | Delete (Phase 11) |
| `services/db.py` | Live facade (49 LOC) | Keep until callers migrate |
| `services/__pycache__/motion_crop_legacy.cpython-311.pyc` | Compiled cache with no source | Delete |
| `routes/voice.py` (~20 LOC) | TTS test stub | Phase 5 will verify if reachable from FE |
| V2 routers (`ENABLE_V2=1`) | Off by default | Phase 5 — verify what V2 even is |
| `features/render/engine/pipeline/remotion_adapter.py` | Present in tree | Phase 5 — Remotion isn't in `requirements.txt`; verify usage |

---

## J. Surprises / observations

**FINDING-B05 (HIGH):** Mandatory LLM in render path. `llm_pipeline.py::run_llm_pre_render()` raises `LLMPipelineError` if no provider succeeds — there is no fallback to the legacy heuristic scene selector (removed in Phase F1). This contradicts CLAUDE.md Sacred Contract #3 ("AI modules must return None on failure — never raise"): the *modules* return None, but the *pipeline orchestrator* raises and kills the job. Important: this is a deliberate architecture choice but it should be documented in Phase 10 docs — currently it's only in commit messages.

**FINDING-B06 (MEDIUM):** Two routers register under `/api/jobs` (`routes/jobs.py` + `features/render/editing/router.py`). FastAPI allows this but route ordering matters. Confirm no path collisions in Phase 6.

**FINDING-B07 (LOW):** `render_pipeline.py` grew from 1,103 → 1,357 LOC (+254 lines) since Sprint 6.D closed. Phase 4 will look at what crept back in.

**FINDING-B08 (LOW):** Editing router lives under `features/render/editing/` but mounts at `/api/jobs/...`. Phase 10 documentation should explain this naming gap (it's an editing operation on a job-part, not a render).

---

## K. Stats

| Metric | Value |
|---|---|
| Python files under `backend/app/**` (non-test, non-pycache) | ~180 |
| Top-level dirs in `backend/app/` | 11 (3 ghost) |
| Mounted routers | 11 main + 2 V2 (conditional) |
| Distinct router prefixes | 8 |
| Render engine submodules | 12 |
| Active env-gated feature flags | 4 (all OFF by default) |
| Daemon threads at startup | 3 |
| SQLite tables | 5 active + 1 `schema_versions` |

End of 02_backend_inventory.md.
