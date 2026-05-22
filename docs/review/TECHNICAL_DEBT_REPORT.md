# TECHNICAL_DEBT_REPORT.md — Technical Debt Report

## CRITICAL

### C1. render_pipeline.py is a 290KB God File
**File**: `backend/app/orchestration/render_pipeline.py`
**Functions affected**: `run_render_pipeline()`, `_render_part()`, `_build_variant_segments()`, `_maybe_prepend_remotion_hook_intro()`, `_maybe_prepend_asset_intro()`, `_maybe_append_asset_outro()`, `_maybe_apply_asset_logo()`, `_maybe_cleanup_narration_audio()`, plus 30+ helpers

**Debt**: Every render concern — download, scene detection caching, scoring, transcription, subtitle processing, TTS, audio mixing, FFmpeg cut, FFmpeg encode, QA validation, report generation, thumbnail extraction, creator asset injection, AI plan integration — is inlined in one file. Navigation is near-impossible. Any change touches unrelated code. Testing is impractical.

**Impact**: Every bug fix, every new render feature, every refactor requires opening and reading a 7,000+ line file. High regression risk from any change. Onboarding a new contributor is extremely difficult.

---

### C2. Subtitle Timestamps Not Adjusted for Playback Speed
**File**: `backend/app/orchestration/render_pipeline.py` — subtitle slicing and ASS burn-in logic
**Functions**: `slice_srt_by_time()` in `subtitle_engine.py` + `render_part_smart()` in `render_engine.py`

**Debt**: When `playback_speed != 1.0` (which is the default: `1.07` for base + `0.08` for TikTok = 1.15), the video plays back faster but subtitle timestamps remain anchored to the original segment clock. A subtitle at 10.0s displays at 10.0s in the output, but the audio/video at that point has already advanced to ~8.7s (at 1.15x).

**Impact**: Every non-1.0 speed render has subtitle drift proportional to speed deviation. At the default TikTok profile (1.15x speed), a 60s clip has ~8s of accumulated subtitle drift by the end. This is visible and impacts user-perceived quality.

---

### C3. TTS Narration Desync at Non-1.0 Speeds
**File**: `backend/app/orchestration/render_pipeline.py` — TTS + audio mixing section
**Functions**: `generate_narration_audio()` in `tts_service.py`, `mix_narration_audio()` in `audio_mix_service.py`

**Debt**: TTS narration is generated from the transcript at the natural speaking rate. The narration is then mixed with the video at a different playback speed. No atempo compensation is applied to align narration timing with the speed-adjusted video.

**Impact**: When `tts_enabled=True` and `playback_speed != 1.0`, the narration is out of sync with the video. The narration finishes before the video ends (at speed >1.0) or after (at speed <1.0).

---

## HIGH

### H1. db.py is a 1900-Line God Service
**File**: `backend/app/services/db.py`
**Functions**: All of them (schema init, job CRUD, parts CRUD, upload accounts CRUD, upload queue CRUD, upload history CRUD, runtime locks CRUD, scheduler state CRUD, proxy pool CRUD, creator prefs CRUD)

**Debt**: One file owns all database interactions for all domains. Adding any new entity requires adding schema + migration + CRUD + normalization to this file. Zero separation of concerns.

**Impact**: Changes to upload account logic risk breaking render job logic. Hard to test domain logic in isolation.

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

### H6. YouTube Download Has No Timeout
**File**: `backend/app/services/downloader.py` — `download_youtube()`
**Called from**: `render_pipeline.py` (main render path), `routes/render.py` (prepare-source, quick-process)

**Debt**: `download_youtube()` uses yt-dlp subprocess with no timeout parameter. A stalled download (network drop, yt-dlp API change, private video that returns no error) hangs the render job indefinitely.

**Impact**: Render jobs can hang forever at the download stage. The only recovery is manual server restart.

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
