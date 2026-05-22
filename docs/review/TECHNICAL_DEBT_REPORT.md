# TECHNICAL_DEBT_REPORT.md — Technical Debt Report

## CRITICAL

### C1. render_pipeline.py is a God File
**File**: `backend/app/orchestration/render_pipeline.py`
**Functions affected**: `run_render_pipeline()`, `_render_part()`, `_build_variant_segments()`, `_maybe_cleanup_narration_audio()`, plus 25+ helpers

**Debt**: Every render concern — download, scene detection caching, scoring, transcription, subtitle processing, TTS, audio mixing, FFmpeg cut, FFmpeg encode, QA validation, report generation, thumbnail extraction, AI plan integration — is inlined in one file. Navigation is difficult. Any change touches unrelated code.

**Impact**: Every bug fix, every new render feature, every refactor requires navigating a 5,700+ line file. High regression risk from any change.

**Phase 4B shipped (2026-05-22)**: Post-assembly asset helpers extracted to `orchestration/asset_pipeline.py`; shared logging/event helpers extracted to `orchestration/render_events.py`. `render_pipeline.py` reduced from 6,064 → 5,779 lines.

**Phase 4C shipped (2026-05-22)**: QA/output validation helpers extracted to `orchestration/qa_pipeline.py`. `render_pipeline.py` reduced from 5,779 → 5,510 lines.

**Phase 4D shipped (2026-05-22)**: `_maybe_cleanup_narration_audio` extracted to `orchestration/audio_pipeline.py`; `_event_from_stage`, `_resolve_job_log_dir`, `_render_progress_timer`, `_PROGRESS_TICK_SEC` moved to `orchestration/render_events.py`. `render_pipeline.py` reduced from 5,510 → 5,340 lines.

**Phase 4E.1 shipped (2026-05-22)**: Shared FFmpeg infrastructure extracted from `render_engine.py` to `services/render/ffmpeg_helpers.py`. `render_engine.py` reduced from 1,652 → ~1,210 lines (−442 lines). 28 names re-exported at old location for backward compat.

**Phase 4E.2 shipped (2026-05-22)**: Clip operations extracted from `render_engine.py` to `services/render/clip_ops.py`. `render_engine.py` reduced from ~1,210 → 829 lines (−381 lines). 5 names re-exported at old location for backward compat.

**Phase 4E.3 shipped (2026-05-22)**: `render_base_clip()` extracted from `render_engine.py` to `services/render/base_clip_renderer.py`. `render_engine.py` reduced from 829 → ~619 lines (−210 lines). 1 name re-exported at old location for backward compat.

**Phase 4E.4 shipped (2026-05-22)**: `composite_overlays_on_base_clip()` extracted from `render_engine.py` to `services/render/overlay_compositor.py`. `render_engine.py` reduced from ~619 → ~477 lines (−142 lines). 1 name re-exported at old location for backward compat.

**Phase 4E.5 shipped (2026-05-22)**: `render_part()` and `render_part_smart()` extracted from `render_engine.py` to `services/render/legacy_renderer.py`. `render_engine.py` reduced from ~477 → ~50 lines. `render_engine.py` is now a pure re-export shim with no function bodies. All render logic lives in focused modules under `services/render/`.

---

### C2. Subtitle Display Duration Compressed at Non-1.0 Speeds
**File**: `backend/app/orchestration/render_pipeline.py` — subtitle slicing and ASS burn-in logic
**Functions**: `slice_srt_by_time()` in `subtitle_engine.py` + `render_part_smart()` in `render_engine.py`

**Partially Resolved (2026-05-22)**: Phase 1.5 validation confirmed that the `ass-before-setpts` vf_chain order means subtitle timestamps ARE re-clocked by `setpts=PTS/speed`. A subtitle at source t=10.0s appears at output t=10.0/1.15 = 8.7s — correctly synchronized with the sped-up video and audio.

**Remaining Debt**: Subtitle *display duration* is compressed proportionally to playback speed. A subtitle block authored for 3.0s of screen time is shown for 3.0/1.15 ≈ 2.6s at 1.15x speed. At the default TikTok profile, end-of-clip subtitles have ≈0.4s less reading time per block than intended. This is a legibility concern, not a synchronization error.

**Impact**: Reduced readability at high playback speeds. Text-heavy subtitle blocks are harder to read. Not a synchronization bug — the subtitle text and speech are aligned.

**Resolved on overlay path (Phase 3A/3B, 2026-05-22)**: The overlay path generates `subtitle_output_timeline.ass` with output-second timestamps using `slice_srt_to_output_timeline()`. In `composite_overlays_on_base_clip()`, there is no `setpts` — the base_clip PTS is already output-timeline. Subtitle display duration on the overlay path is NOT compressed; a 3.0s subtitle block shows for exactly 3.0 output seconds.

**Remaining Debt (legacy path only)**: When `FEATURE_OVERLAY_AFTER_BASE_CLIP=0`, `render_part_smart()` is still used and the display duration compression remains. The legacy path is not fixed and is used as the fallback path.

---

### C3. TTS Narration Desync at Non-1.0 Speeds

**Resolved (Phase 0)**:  
`mix_narration_audio()` in `audio_mix_service.py` now accepts `playback_speed: float`
and applies `atempo={speed:.4f}` to the narration track before mixing. The narration
is speed-compensated to match the video playback speed. Speed is clamped to FFmpeg
atempo's range [0.5, 2.0] (a separate concern from the render pipeline's [0.5, 1.5] clamp).

`render_pipeline.py` passes `playback_speed=_get_effective_playback_speed(payload, _target_platform)`
to `mix_narration_audio()` at the call site.

Regression tests added: `TestMixNarrationAudioAtempo` (8 tests) in `test_phase0_hotfixes.py`.

**Historical debt**: TTS narration was generated at natural speaking rate and mixed
without speed compensation. At 1.15x speed the narration ended ~52s into a 60s clip.

---

## HIGH

### H1. db.py is a 1900-Line God Service
**File**: `backend/app/services/db.py`
**Functions**: All of them (schema init, job CRUD, parts CRUD, upload accounts CRUD, upload queue CRUD, upload history CRUD, runtime locks CRUD, scheduler state CRUD, proxy pool CRUD, creator prefs CRUD)

**Debt**: One file owns all database interactions for all domains. Adding any new entity requires adding schema + migration + CRUD + normalization to this file. Zero separation of concerns.

**Impact**: Changes to upload account logic risk breaking render job logic. Hard to test domain logic in isolation.

**Phase 4F.0 planning (2026-05-22)**: DB split strategy defined. Target: `app/db/` with 5 modules (`connection.py`, `jobs_repo.py`, `uploads_repo.py`, `platform_repo.py`, `creator_repo.py`). `services/db.py` remains as backward-compat re-export shim. Plan: `docs/restructure/PHASE_4F_DB_SPLIT_PLAN.md`.

**Phase 4F.1 shipped (2026-05-22)**: `app/db/connection.py` extracted — Group A (connection, schema, thread-local, helpers) moved verbatim. `services/db.py` re-exports all moved symbols. `services/db.py` reduced from ~1,886 → ~1,386 lines (−500 lines). 33 new tests in `test_db_connection.py`.

**Phase 4F.2 shipped (2026-05-22)**: `app/db/jobs_repo.py` extracted — Group B (upsert_job, update_job_progress, delete_job, upsert_job_part, get_job, list_jobs, list_jobs_page, list_job_parts_bulk, list_job_parts) moved verbatim. `services/db.py` re-exports all 9 symbols. `services/db.py` reduced by ~145 additional lines. 35 new tests in `test_jobs_repo.py`.

**Phase 4F.3 shipped (2026-05-22)**: `app/db/creator_repo.py` extracted — Group E (get_creator_prefs, upsert_creator_prefs) moved verbatim. `services/db.py` re-exports both symbols. `services/db.py` reduced by ~25 additional lines (~1,236 lines remaining). 17 new tests in `test_creator_repo.py`.

**Phase 4F.4 shipped (2026-05-22)**: `app/db/platform_repo.py` extracted — Group D (_normalize_proxy_pool_row, list_proxy_pool_rows, get_proxy_pool_row, create_proxy_pool_row, update_proxy_pool_row, delete_proxy_pool_row) moved verbatim. `services/db.py` re-exports all 6 symbols. `services/db.py` reduced by ~130 additional lines (~1,106 lines remaining). 44 new tests in `test_platform_repo.py`.

**Phase 4F.5 audit (2026-05-22)**: Upload domain removal audit completed. Audit found the upload domain is **100% active** (routes registered, frontend loaded, all 43 upload DB functions called by live endpoints). `uploads_repo.py` extraction **cancelled** — upload domain will be deleted directly, not extracted first. Deletion plan in `docs/restructure/PHASE_4F_5_UPLOAD_DOMAIN_REMOVAL_AUDIT.md`. Awaiting user confirmation of 5 questions before proceeding. **No backend code changed in this audit step.**

---

### H2. No Test Coverage for Core Pipeline
**Files**: `backend/app/orchestration/render_pipeline.py`, `backend/app/services/render_engine.py`, `backend/app/services/subtitle_engine.py`

**Debt**: The render pipeline — the most critical code in the project — has zero test coverage. The 80+ test files in `backend/tests/` all test AI subsystem schema validators. No integration tests for FFmpeg invocation, subtitle slicing, audio mixing, or output validation.

**Impact**: Any regression in render quality, subtitle correctness, or FFmpeg command generation is only discovered by running a real render job.

---

### H3. RAG Memory Not Connected to Production Render
**File**: `backend/app/orchestration/render_pipeline.py` — call to `create_ai_edit_plan()`
**Line**: ~1550 (approximate — the context dict build)

**Debt**: `create_ai_edit_plan()` accepts a `memory_store` context key for RAG retrieval of prior render decisions. `render_pipeline.py` does not pass this key. The entire RAG infrastructure (vector store, SQLite memory, embeddings, retriever) is built and tested but effectively unused in production renders.

**Impact**: The AI system has no memory of prior renders. Creator preference learning is siloed in the adaptive profile JSON files, not in the RAG system. Work done on Phases 3–5 (memory phases) is not active.

---

### H4. FAISS Vector Index Not Persisted
**File**: `backend/app/ai/rag/vector_store.py` — `LocalVectorStore`

**Debt**: The in-memory vector store is rebuilt from scratch on every server restart. The `SQLiteStore` (`sqlite_store.py`) persists the raw text and metadata, but the vector embeddings are not saved to disk. Rebuilding from SQLite requires re-embedding all entries on startup — no code does this.

**Impact**: RAG retrieval on the first render after a server restart has no vector index. The system falls back to cosine search over empty entries (no results).

---

### H5. V2/V3/V4 Frontends Ship But Are Not the Default
**Directories**: `backend/static-v2/`, `backend/static-v3/`, `backend/static-v4/`

**Debt**: The active default frontend is `backend/static/` (V1). `static-v2/` is opt-in via `STATIC_UI_VERSION=v2` and does not have feature parity with V1 (missing the full editor, creator tools, review queue). `static-v3/` and `static-v4/` are partial UI iterations that serve no active route. All three ship in every Electron build.

**Impact**: Package bloat. `static-v3/` and `static-v4/` add confusion about which UI is canonical. `static-v2/` creates a second surface to maintain for any API contract change.

---

### H6. YouTube Download Hang Risk (Partially Resolved)
**File**: `backend/app/services/downloader.py` — `download_youtube()`
**Called from**: `render_pipeline.py` (main render path), `routes/render.py` (prepare-source, quick-process)

**Partially Resolved (Phase 0)**: `socket_timeout: 60` added to yt-dlp options, and `cancel_event` is now passed from `render_pipeline.py` so user cancel propagates to the download subprocess. The 60s socket timeout mitigates the most common stall scenario (network drop, hung connection).

**Remaining Debt**: yt-dlp's `socket_timeout` applies to individual socket operations, not total download time. A very slow download that keeps making progress can still run indefinitely. A total wall-clock timeout per download session is not yet implemented.

---

### H7. Preview Session Memory Loss on Server Restart
**File**: `backend/app/routes/render.py` — `_PREVIEW_SESSIONS` dict
**Lines**: 74–141

**Debt**: Preview sessions are stored in a module-level dict. On server restart, the in-memory dict is lost. Disk fallback (`session.json`) works only if: (a) the file exists, (b) the session directory was not cleaned, (c) the `video_path` still exists. In the packaged app, server restarts are common (crash, update).

**Impact**: Users lose their prepared source session on server restart and must re-prepare (re-download YouTube video).

---

## MEDIUM

### M1. Module-Level Mutable State in Screens
**File**: `backend/static-v2/assets/js/screens/create.js` — lines 30–40
**Variables**: `_phase`, `_srcMode`, `_url`, `_filePath`, `_outputDir`, `_error`, `_session`, `_activePreset`, `_advOpen`, `_generating`

**Debt**: Screen state is stored as module-level variables. Navigation away and back does not reset state unless explicitly handled. The current code resets most vars in `mount()` but `_error` retention on error states and `_session` retention across navigations is incomplete.

---

### M2. Batch Child Wait Has 7200s Hard Ceiling
**File**: `backend/app/routes/render.py` — `_run_batch()` function, line ~749
**Code**: `_done.wait(timeout=7200)`

**Debt**: If a child render job gets stuck (FFmpeg hung past `_FFMPEG_TIMEOUT_SEC`), the `_child_fn` finally block may not call `_done.set()` in some edge cases. The batch coordinator then waits the full 7200s before moving to the next URL.

---

### M3. Knowledge Packs Loaded Per-Render
**File**: `backend/app/ai/knowledge/knowledge_pack_loader.py`

**Debt**: Knowledge pack JSON files are opened and parsed on every render that uses AI planning. For the 20+ knowledge JSON files, this is unnecessary repeated I/O.

---

### M4. No Disk Space Check Before Render
**File**: `backend/app/orchestration/render_pipeline.py` — start of `run_render_pipeline()`

**Debt**: No disk space validation before starting. A full disk causes FFmpeg to produce a 0-byte output after a full encode pass. The QA check catches it, but the time for the full encode is wasted.

---

### M5. Scene Detection Progress Not Reported
**File**: `backend/app/services/scene_detector.py` — `detect_scenes()`

**Debt**: Scene detection on a 1-hour video takes 1–5 minutes. During this time, the job stage is `scene_detection` but `progress_percent` does not advance. The progress bar appears frozen.

---

### M6. V3/V4 Static Fragments Ship But Are Not Wired
**Directories**: `backend/static-v3/`, `backend/static-v4/`

**Debt**: Incomplete UI iterations that ship in the package but serve no active route. They add confusion and package size.

---

### M7. Optional AI Imports Use Broad Exception Swallow
**File**: All AI module `__init__` blocks (e.g. `ai/director/ai_director.py` lines 25–115)
**Pattern**: `try: from app.ai.X import Y; _AVAILABLE = True; except ImportError: _AVAILABLE = False`

**Debt**: `except ImportError` catches `ModuleNotFoundError` but will also catch any `ImportError` raised by a bug inside the imported module (e.g. referencing a missing attribute at import time). A bug in an AI module silently makes it appear as "optional and unavailable."

---

### M8. Whisper Model Lock Blocks All Concurrent Transcriptions
**File**: `backend/app/services/subtitle_engine.py` — `_get_transcribe_lock()`

**Debt**: One lock per Whisper model name. With `MAX_CONCURRENT_JOBS=2` and two renders both using Whisper base, the second render's transcription step blocks behind the first. Both jobs are counted as "running" but one is effectively waiting. Users see a stalled render with no explanation.

---

### M9. `list_jobs()` Returns All Jobs Without Pagination
**File**: `backend/app/services/db.py` — `list_jobs()`
**Called from**: `routes/jobs.py` `api_list_jobs()`

**Debt**: `GET /api/jobs` fetches ALL jobs from the database. For long-running apps with hundreds of jobs, this query materializes the full table. `list_jobs_page()` exists and is used by the history endpoint, but the raw `/api/jobs` endpoint still uses the unbounded query.

---

## LOW

### L1. `enrich_upload_account_runtime_state()` is N+1 on Lock List
**File**: `backend/app/services/db.py` — `enrich_upload_account_runtime_state()`
**Function calls**: `list_active_runtime_locks()` called once per account

**Debt**: `list_upload_account_rows()` calls `enrich_upload_account_runtime_state()` per row, which calls `list_active_runtime_locks()` per row. For 10 accounts, this is 10 separate lock queries.

---

### L2. Scene Cache Uses System Temp Dir
**File**: `backend/app/orchestration/render_pipeline.py` — `_scene_cache_get()` / `_scene_cache_put()`
**Path**: `tempfile.gettempdir() / "render_cache" / "scene_detect" / ...`

**Debt**: Cache goes to the system temp dir (C:\Windows\Temp on Windows), not the project data dir. System cleanup tools can delete this cache unexpectedly, causing expensive scene re-detection.

---

### L3. `_PREVIEW_SESSIONS` LRU Eviction Uses Submit Time
**File**: `backend/app/routes/render.py` — `_save_session()` line 85
**Code**: `oldest = min(_PREVIEW_SESSIONS, key=lambda k: _PREVIEW_SESSIONS[k].get("created_at", 0))`

**Debt**: Eviction is by creation time, not by last access. An old but actively used session can be evicted in favor of a newer one.

---

### L4. SQLite Schema Migrations Use ALTER TABLE Per-Column
**File**: `backend/app/services/db.py` — `_ensure_columns()`

**Debt**: Schema migration is done by checking column existence and running `ALTER TABLE ADD COLUMN`. For new tables needing many new columns (e.g. adding 5 columns to `upload_accounts`), this runs 5 separate ALTER TABLE statements on every startup. Harmless but not idiomatic.

---

### L5. No Content Integrity for Output Files
**File**: `backend/app/orchestration/render_pipeline.py` — `_validate_render_output()`

**Debt**: Output validation checks duration and size. No MD5/SHA checksum of output files stored to DB. No way to verify file integrity after delivery (e.g. network copy corruption, partial disk write).
