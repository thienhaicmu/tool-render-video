# SCORECARD.md — Architecture Quality Scorecard

Scores are 1–10. Based exclusively on code reviewed during this session. No assumptions.

---

## Summary Table

| # | Category | Score |
|---|----------|-------|
| 1 | Project structure | 5 |
| 2 | Frontend architecture | 5 |
| 3 | Backend architecture | 4 |
| 4 | API contract quality | 7 |
| 5 | Job / queue design | 8 |
| 6 | Render pipeline design | 3 |
| 7 | AI integration | 4 |
| 8 | FFmpeg integration | 7 |
| 9 | Subtitle system | 4 |
| 10 | File / artifact management | 5 |
| 11 | Realtime / progress system | 7 |
| 12 | Error handling | 5 |
| 13 | Test coverage | 2 |
| 14 | Build / package quality | 7 |
| 15 | Maintainability | 3 |
| 16 | Scalability | 4 |
| 17 | Debuggability | 6 |
| 18 | Production readiness | 4 |

**Overall: 5.0 / 10**

---

## Detailed Scores

---

### 1. Project structure — 5/10

**What was scored**: Repository layout, separation of concerns between modules, layering discipline.

**Positive**:
- Clear top-level separation: `backend/`, `desktop-shell/`, `docs/`, `channels/`, `knowledge/`.
- FastAPI router per domain (`render.py`, `jobs.py`, `channels.py`, etc.) — correct. (`upload.py` removed Phase 4F.5C — 8 active routers remain)
- `backend/app/ai/` is a well-organized namespace with 60+ modules arranged by function (analyzers, director, rag, camera, subtitles, etc.).
- `entities/`, `store/`, `api/`, `screens/` split in V2 frontend is appropriate.

**Negative**:
- `backend/app/orchestration/render_pipeline.py` at 290KB obliterates any meaningful separation. The "orchestration" layer is a dumping ground.
- `backend/static/`, `backend/static-v3/`, `backend/static-v4/` coexist with `backend/static-v2/` — dead code with no boundary.
- ~~`backend/app/services/db.py` at 1900 lines~~ — **RESOLVED Phase 4F**: `db.py` is now a 31-line re-export shim; all DB logic extracted to `app/db/`.
- No `core/` domain model — the boundary between route, service, and domain is not enforced anywhere.

---

### 2. Frontend architecture — 5/10

**What was scored**: `backend/static/` — the active default V1 frontend (54 JS files, global state, `setView()` nav).

**Positive**:
- Complete feature set: source prep, render, editor, creator tools, upload, channels, batch queue, review queue — all implemented, none stubbed.
- WebSocket + polling hybrid in `render-ui.js` with `smooth-progress.js` RAF-based animation is a good UX detail — progress bars animate smoothly between coarse server updates.
- Log deduplication (`log-utils.js`, `LOG_DEDUPE_WINDOW_MS=12000`) prevents log panel spam.
- Creator subsystem (DNA, presets, memory, taste, assets, series) is a real implemented feature set, not placeholders.
- Zero runtime npm dependencies — works without a build step, practical for a bundled desktop tool.

**Negative**:
- All state is global: `globals.js` + 20+ `let` declarations per file. No isolation between subsystems. State from one render session bleeds into the next unless `resetRenderSessionUi()` is explicitly called.
- No module system: 54 files loaded as classic `<script>` tags. Every top-level declaration is global. Name collision risk with no module boundary enforcement.
- All views (workspace, render, editor, review, download, history) live in the DOM simultaneously, toggled by `hiddenView` CSS. Editor DOM (waveform, timeline, thumbnail cache) is always present even on the workspace view.
- Editor AI UI (`editor-ai-actions.js`, `editor-agents.js`, `editor-converse.js`) presents AI capabilities the backend does not implement — no LLM calls anywhere.
- No global error boundary — unhandled exceptions in event handlers fail silently.
- V2 (`static-v2/`), V3 (`static-v3/`), V4 (`static-v4/`) ship in every build as dead weight.

---

### 3. Backend architecture — 4/10

**What was scored**: `backend/app/` — routes, services, orchestration, core layers.

**Positive**:
- 9 routers with clear domain ownership: render, jobs, upload, channels, system, devtools, etc.
- `job_manager.py` priority heap design is documented and appropriate for single-machine desktop use.
- Cancel propagation via `cancel_registry.py` threading.Event + FFmpeg subprocess kill within ~1s is clean.
- WebSocket progress with fingerprinting (`_ws_fingerprint` in `jobs.py`) avoids spurious sends.
- Thread-local SQLite connections for high-frequency writes (`update_job_progress`) is correct.
- WAL mode SQLite for concurrent read/write.
- Startup recovery marks interrupted jobs correctly (no auto-restart — right call for a desktop tool).

**Negative**:
- `render_pipeline.py` at 290KB / 7000+ lines is not a service, not a module, not an orchestrator — it is a monolith inside a monolith. There is no second-biggest file close to it.
- `db.py` at 1900 lines owns every data access pattern across all domains with zero separation.
- `render.py` at 1400 lines mixes preview session state, download orchestration, job creation, batch coordination, media streaming, and thumbnail serving.
- No rate limiting on `/api/render/process` or `/api/render/prepare-source`.
- Batch child hang risk: `_done.wait(timeout=7200)` with no defense against `_ev.set()` never being called.
- No authentication — any process reaching port 8000 can submit jobs, read credentials, stream output files. Undocumented assumption.

---

### 4. API contract quality — 7/10

**What was scored**: FastAPI route definitions, request/response shapes, error handling, HTTP semantics.

**Positive**:
- Pydantic request/response models on all public endpoints.
- Correct HTTP semantics: POST for job creation, DELETE for cancel, GET for streaming with Range support.
- `normalizeApiError()` in frontend handles Pydantic 422 detail arrays — avoids `[object Object]` display.
- WebSocket API has a defined lifecycle: connect → receive progress events → terminal status close.
- `/api/jobs` vs `/api/jobs/history` — two endpoints for different use cases (active vs paginated history) is correct.
- `Range` header support in `stream_render_part_media()` — required for `<video>` seek, implemented correctly.

**Negative**:
- `/api/jobs` (list all jobs) returns ALL rows from DB without pagination — `list_jobs_page()` exists but the active endpoint still uses the unbounded query.
- No versioning (`/api/v1/...`). Not critical for a desktop app but means any API change is a breaking change.
- `quick_process` endpoint is an inline mini-pipeline with its own FFmpeg call — no shared interface with the main pipeline. Two implementations of FFmpeg invocation.

---

### 5. Job / queue design — 8/10

**What was scored**: `backend/app/services/job_manager.py`, job lifecycle state machine, cancel/resume/retry mechanics.

**Positive**:
- Min-heap priority queue with FIFO tie-breaking via monotonic sequence number — correct, deterministic.
- `submit_job()` returns False on duplicate job_id — deduplication without silent overwrite.
- `_mark_job_running()` transitions DB status before dispatch — consistent state.
- Cancel via `cancel_registry.py` threading.Event is propagated to FFmpeg subprocess kill in the render thread poll loop — responsive within ~1s.
- Resume: skips already-completed parts (reads from DB). Retry: re-runs only failed parts. Both are correct and independent.
- Startup recovery: marks queued/running jobs as "interrupted", does not auto-restart — correct behavior for a desktop tool.
- Background scheduler daemon thread for periodic cleanup with proper condition wait.

**Negative**:
- Batch coordinator (`create_render_batch`) bypasses job_manager — uses bare `threading.Thread` instead of `submit_job`. The batch "job" is not tracked in the job manager's heap.
- `_done.wait(timeout=7200)` in batch coordinator is the only guard against a hung child — no escalation, no alert.
- No job result caching — re-running the same URL re-downloads, re-transcribes, re-renders.

---

### 6. Render pipeline design — 3/10

**What was scored**: `backend/app/orchestration/render_pipeline.py`.

**Positive**:
- The pipeline does produce correct output for the happy path (the tool works).
- Scene/transcription 72h caching with mtime-based invalidation is sound.
- `_auto_frame_skip()` in scene detector auto-tunes based on source FPS — smart.
- Variant rendering (aggressive/balanced/story) uses different score weight formulas — legitimate differentiation.
- `_emit_render_event()` for progress/status broadcast is consistent.

**Negative**:
- 290KB / 7000+ lines in a single file. Every render concern is inlined. Navigation is near-impossible. Testing is impractical.
- **Critical correctness bug**: subtitle timestamps sliced from source clock but burned into speed-adjusted video. At default TikTok profile (1.15x), accumulated drift at 60s = ~8s. Not fixed.
- **Critical correctness bug**: TTS narration generated at natural speed, mixed into sped-up video. At 1.15x speed, narration overruns or underruns video. No atempo compensation.
- Scene cache stored in system temp dir (`tempfile.gettempdir()`) — vulnerable to OS cleanup tools.
- No disk space validation before render start.
- No minimum segment pool size validation — degenerate pool (1 scene) proceeds silently.
- Black frame detection runs after full encode, not before — wastes encode time on re-render.
- The ±20% output duration QA tolerance is too wide — real quality regressions pass.
- No audio stream presence check in output QA — muted video passes.

---

### 7. AI integration — 4/10

**What was scored**: `backend/app/ai/` — all 60+ modules, the director, RAG, knowledge system, quality gates.

**Positive**:
- Graceful degradation pattern is correct: every AI module wrapped in try/except with fallback, `create_ai_edit_plan()` returns None on failure, render always completes.
- `LocalVectorStore` falls back from FAISS to pure Python cosine similarity — correct dependency isolation.
- SQLite memory store in `ai/rag/sqlite_store.py` persists raw text and metadata across restarts.
- Knowledge packs in `backend/knowledge/` are explicit, auditable, version-controlled JSON files — platform-specific tuning is real and meaningful.
- Schema validation via dataclasses on AI plan components — prevents malformed plan assembly.

**Negative**:
- **No external AI provider used anywhere.** Zero calls to any LLM API. The "AI" branding is a naming artifact.
- `create_ai_edit_plan()` is not called with `memory_store` by `render_pipeline.py` — the entire RAG subsystem (vector store, SQLite memory, embeddings, retriever) is built, tested, and completely inactive in production.
- FAISS vector index is in-memory only — lost on every server restart. No rebuild from SQLite on startup.
- Knowledge packs loaded per-render with no module-level caching — repeated I/O.
- `except ImportError` pattern used for optional AI imports will silently swallow non-import bugs (syntax errors, attribute errors at import time) — modules with bugs appear "unavailable" instead of crashing.
- Viral ML scorer requires 30+ feedback records and manual `train_model()` call — no UI trigger. In practice always heuristic.
- "Emotion analysis" is keyword scoring. "Retention prediction" is a weighted alias for scene quality score. "Creator DNA" reads a JSON file. The module names are aspirational, not descriptive.

---

### 8. FFmpeg integration — 7/10

**What was scored**: `backend/app/services/render_engine.py` — filter chain construction, subprocess management, NVENC, error handling.

**Positive**:
- `_run_ffmpeg_with_retry()`: Popen + communicate thread + 1s poll loop for cancel/timeout is well-structured. Cancel propagates within ~1s.
- NVENC auto-detect with lru_cache — one probe per process lifetime, not per render.
- `_NVENC_SEM_VALUE=3` semaphore limits concurrent NVENC sessions — prevents GPU memory exhaustion.
- `_build_audio_filter()`: loudnorm + sidechain compression chain is correct for ducking BGM under narration.
- `detect_bad_first_frame()` + 0.1s retry — catches the common black-frame-on-scene-cut problem.
- `probe_video_metadata()` with (abspath, mtime_ns, size) cache — avoids repeated ffprobe calls.
- Hardware acceleration fallback: NVENC → libx264 with correct parameter translation.

**Negative**:
- No `-r` forcing in output filter chains — may produce VFR output from VFR inputs, incompatible with some platforms.
- No B-frame suppression for TikTok compatibility (`-bf 0` not enforced).
- No codec validation at input stage — unsupported codec discovered at encode time, not at ffprobe validation.
- Black frame detection runs post-encode — wastes encode time.
- `_FFMPEG_TIMEOUT_SEC=3600` per FFmpeg call — a hung FFmpeg holds a job thread for an hour before detection.
- Source video already in target aspect ratio triggers unnecessary crop+scale (no "already correct" detection).

---

### 9. Subtitle system — 4/10

**What was scored**: `backend/app/services/subtitle_engine.py` (frozen pure re-export shim post Phase 4G.7; all logic in `app/services/subtitles/` 7-module package with 388 unit tests), `slice_srt_by_time()`, ASS conversion, playback speed interaction.

**Positive**:
- `parse_srt_blocks()` / `write_srt_blocks()` round-trip SRT editing is correct.
- `WORD_MIN_DURATION_SEC=0.12`, `WORD_MERGE_SHORTER_THAN_SEC=0.11` guards in ASS converter prevent zero-duration events.
- Per-model Whisper transcription lock prevents VRAM contention.
- Transcription 72h cache avoids re-running Whisper on the same source.
- Bounce/karaoke subtitle styles are implemented and selectable.
- `_get_transcribe_lock()` per model name is correct — one lock per resource, not a global lock.

**Negative**:
- **Critical correctness bug**: `slice_srt_by_time()` subtracts `start_sec` from timestamps but does NOT divide by `playback_speed`. When `playback_speed=1.15`, a subtitle at 10.0s in the source appears at 10.0s in the output but the video frame at 10.0s has already advanced to ~11.5s of source content — subtitle is 1.5s behind by the 10s mark, 8s behind by the 60s mark.
- Whisper runs synchronously on the render thread. For a 1-hour video on CPU Whisper medium, this is 10–20 min of blocking.
- `_get_transcribe_lock()` with `MAX_CONCURRENT_JOBS=2` means the second concurrent render's transcription silently waits behind the first with no user feedback.
- Model cold start (`get_whisper_model()`) holds `_MODEL_CACHE_LOCK` during load (30–60s on first use) — all concurrent callers block silently.
- Transcription cache misses on re-download (new yt-dlp session to different work_dir) — same URL, different path = full re-transcription.
- No SRT-level guard for very short word-level segments (<0.1s) before ASS conversion — the ASS converter guards it but the SRT slice step does not.

---

### 10. File / artifact management — 5/10

**What was scored**: temp file lifecycle, output paths, cache management, cleanup strategy.

**Positive**:
- `finally: _safe_unlink(path)` pattern used consistently for intermediates (`cut.mp4`, `.hook_intro.mp4`, `.with_intro.mp4`, `.cleaned.mp3`).
- 30-minute periodic cleanup thread in `main.py` as safety net for leaked intermediates.
- `evict_stale_preview_sessions()` daemon thread for preview session cleanup.
- Output paths are user-configured and validated by `ffprobe` after render.
- 72h cache TTL with (path, mtime_ns, size) key is correct invalidation logic.

**Negative**:
- Scene cache in `tempfile.gettempdir()` (C:\Windows\Temp) — vulnerable to OS cleanup tools, moves on machine-specific temp paths.
- Temp files named generically (`cut.mp4`, `.hook_intro.mp4`) — if two concurrent renders work in the same directory, names could collide. Work dirs are per-job but the pattern is fragile.
- On Windows, locked files fail `_safe_unlink()` silently — the `finally` block does not raise, so temp files can leak permanently (the 30min cleanup thread catches them only by age).
- No MD5/SHA checksum stored for output files — no integrity check after delivery (network copy, disk write).
- Disk space not checked before render start — a full disk produces a 0-byte output after a full encode pass.
- `_PREVIEW_SESSIONS` module-level dict lost on server restart — disk fallback (`session.json`) is fragile (path must still exist, video_path must still exist).

---

### 11. Realtime / progress system — 7/10

**What was scored**: `backend/app/routes/jobs.py` WebSocket, `transport.js`, `_ws_fingerprint`, progress updates.

**Positive**:
- `_ws_fingerprint()` in `jobs.py` checks (status, stage, progress_percent, message, parts tuple, completed_parts, failed_parts, stuck_parts count) — avoids sending on pure timestamp updates. Correct and efficient.
- WebSocket + 3s polling hybrid in `transport.js` — WS primary, degrades gracefully. One final poll 600ms after WS terminal signal is a smart hedge.
- `_compute_progress_summary()` detects stuck_parts (>120s since last update) — backend knows when a part is hung.
- Terminal status detection in `transport.js` correct: completed, completed_with_errors, failed, interrupted.
- Progress events emitted via `_emit_render_event()` at all meaningful pipeline stage transitions.

**Negative**:
- No estimated time remaining shown anywhere — users see progress percent only.
- Stuck part detection exists in the backend (`stuck_parts` in summary) but not prominently surfaced in the frontend UI — users see a frozen bar with no explanation.
- Scene detection stage shows `scene_detection` but `progress_percent` does not advance — the bar appears frozen for 1–5min on long videos.
- Whisper transcription stage similarly shows no sub-progress — can be 10–20min of apparent hang.
- Batch render has a `batch_id` but no separate batch-level progress UI — multi-URL renders are opaque.
- WebSocket reconnect is not implemented in `transport.js` — if the server restarts mid-render (crash, update), polling takes over but shows stale state.

---

### 12. Error handling — 5/10

**What was scored**: Render error propagation, AI fallbacks, API error responses, frontend error display.

**Positive**:
- `render_pipeline.py` catches errors, logs via `_emit_render_event()`, and re-raises — consistent pattern.
- `create_ai_edit_plan()` returns None on any AI failure — render never blocked by AI errors.
- `quick_process()` cleans up work_dir in `finally` with `shutil.rmtree(ignore_errors=True)`.
- `normalizeApiError()` in frontend handles both string and Pydantic 422 array detail fields.
- `_safe_unlink()` does not raise on failure — temp file cleanup is non-fatal.
- FFmpeg error: stderr captured and included in the error event for debugging.

**Negative**:
- `except ImportError` for optional AI imports also catches `ImportError` raised by bugs inside imported modules (missing attribute at import time, circular imports) — modules with real bugs appear silently unavailable.
- `screens/create.js` `_error` is module-level — persists across navigation if not explicitly cleared.
- No global error boundary in the frontend — unhandled exceptions in event handlers fail silently.
- `normalizeApiError()` is inconsistently applied — some screens set `_error` correctly, others let exceptions propagate to console only.
- FFmpeg timeout at 3600s — a hung FFmpeg holds a job thread for an hour with no user notification until timeout triggers.
- No audio stream presence check in output QA — muted video passes validation.
- No subtitle burn-in check — a failed ASS event causes FFmpeg to skip the subtitle silently; the output passes QA.

---

### 13. Test coverage — 2/10

**What was scored**: `backend/tests/` — all 80+ test files.

**Positive**:
- 80+ test files exist — the project is not entirely untested.
- AI schema validator tests are complete and correct for their scope.
- Optional AI dependency mocking is correctly set up — tests don't require FAISS/sentence-transformers installed.

**Negative**:
- The 80+ tests cover **only AI schema validators** — `dataclass` shape checks, Pydantic model validations, and a few heuristic scoring edge cases.
- Zero test coverage for: `render_pipeline.py`, `render_engine.py`, `subtitle_engine.py`, `scene_detector.py`, `job_manager.py`, `db.py`, `downloader.py`, `audio_mix_service.py`, `tts_service.py`.
- No FFmpeg integration tests. No subtitle sync tests. No audio mix tests. No job lifecycle tests. No DB schema migration tests.
- The subtitle display duration compression (C2) and TTS desync bug (C3) were not caught by tests at time of audit. C3 is now covered by `TestMixNarrationAudioAtempo`; C2 is addressed on the overlay path via `test_composite_overlays.py` assertions.
- No end-to-end test for the render pipeline — all regressions are discovered by running real render jobs.
- No CI configuration visible — tests presumably run manually only.

---

### 14. Build / package quality — 7/10

**What was scored**: `desktop-shell/package.json`, Electron builder config, Python bundling, FFmpeg bundling.

**Positive**:
- Electron + electron-builder + NSIS + portable targets — professional Windows desktop build chain.
- FFmpeg bundled in `desktop-shell/ffmpeg-bin/` — no dependency on system FFmpeg. Correct for a desktop tool.
- PyInstaller backend bundle in `desktop-shell/backend-bin/` — Python runtime packaged, no Python install required.
- `sys.frozen` detection in `config.py` correctly splits dev vs packaged data paths (`data/` vs `%APPDATA%/RenderVideoTool/data`).
- Bootstrap state JSON (`data/state/bootstrap-state.json`) with version guard — controlled startup state.
- Python probe order in `desktop-shell/main.js` (`py -3.11`, `py -3`, `python`, `python3`) — reasonable fallback chain for dev mode.

**Negative**:
- Dead frontend code (`static/`, `static-v3/`, `static-v4/`) ships in every Electron package — unnecessary payload.
- No `extraResources` exclusion for test files (`backend/tests/`) — test suite ships with the packaged app.
- `STATIC_UI_VERSION` env var toggle ships in packaged app — configuration leak.
- No signing configuration visible in `package.json` — Windows SmartScreen warnings for unsigned installs.
- No auto-update mechanism visible — users must manually install new versions.

---

### 15. Maintainability — 3/10

**What was scored**: Code navigability, modularity, naming, ability to make a change without understanding the whole file.

**Positive**:
- `ai/` namespace is modular — each analyzer is its own file. Adding a new heuristic analyzer does not require touching existing files.
- `knowledge/` JSON files are auditable and can be edited without touching Python code.
- Router files have clear domain ownership — adding a new API endpoint in the correct router is straightforward.
- `create-store.js` store pattern is consistent across all frontend stores.

**Negative**:
- `render_pipeline.py` at 290KB makes every render change high-risk. Any fix touches unrelated code. Merge conflicts are guaranteed in team development.
- `db.py` at 1900 lines — adding a new entity requires editing the same file as all other entities.
- `render.py` at 1400 lines — preview session logic, download orchestration, and media streaming all in one route file.
- 15+ top-level config dicts inlined in `render_pipeline.py` (`_PLATFORM_PROFILES`, `_CTA_TEXTS`, `_VARIANT_AGGRESSIVE_SUB`, `_PLAY_RES_Y_MAP`, etc.) — platform-specific configuration is buried in a 7000-line file.
- Module-level state (`_render_active_count`, `_PREVIEW_SESSIONS`) accessed from other modules via direct import of private names — leaky abstraction.
- AI modules named as if they implement real AI (ai_director, emotion_analyzer, retention_predictor) while implementing heuristics — the gap between name and behavior is a maintainability hazard.
- V1/V3/V4 dead frontend code forces every frontend developer to determine whether their change applies to one version, two versions, or all.

---

### 16. Scalability — 4/10

**What was scored**: Ability to handle more users, more jobs, larger videos, concurrent requests.

**Positive**:
- `MAX_CONCURRENT_JOBS` is configurable — defaults to `cpu_count() // 2`, which is reasonable for CPU-bound work.
- ThreadPoolExecutor with priority heap — correct for a single-machine task queue.
- NVENC semaphore (`_NVENC_SEM_VALUE=3`) limits GPU resource contention — good.
- Paginated job history endpoint (`list_jobs_page`) — correct pattern, just not used by the active jobs endpoint.

**Negative**:
- Single SQLite database as the sole persistent store for everything — WAL mode helps with concurrent reads but SQLite has hard limits for write throughput at scale.
- `/api/jobs` fetches ALL rows — one heavy user with 1000 jobs causes full table scan on every job list request.
- Whisper transcription lock per model — with MAX_CONCURRENT_JOBS=2, only one render transcribes at a time. Effectively serial transcription regardless of job count.
- No horizontal scaling possible — all state is process-local or SQLite-local. Cannot run two backend instances.
- No disk space management — no quota, no cleanup policy, a user who renders 100 videos will accumulate output files indefinitely.
- YouTube download has no timeout — one stalled download blocks a worker thread indefinitely, reducing effective concurrency.

---

### 17. Debuggability — 6/10

**What was scored**: Logging, error reporting, event emission, ability to diagnose a failed render.

**Positive**:
- `_emit_render_event()` logs to DB and broadcasts via WebSocket — progress and errors are visible in real-time.
- FFmpeg stderr captured and included in render event `message` field — FFmpeg errors are surfaced to the user.
- `stuck_parts` detection (>120s since last update) in `_compute_progress_summary()` — identifies hung render stages.
- Render events stored in DB (`job_parts` table with `log` field) — post-mortem debugging via job history.
- Stage-level progress (`scene_detection`, `transcribing_full`, `cutting`, `rendering`, etc.) — narrows where a failure occurred.
- TransNetV2 singleton double-checked lock logged on first load.

**Negative**:
- Scene detection, Whisper transcription, and Whisper model load show no sub-progress — during these stages (which can be 10–30min), the log shows only the entry stage event with no heartbeat.
- `except ImportError` silent swallow for AI modules — a bug in an AI module at import time appears as "feature unavailable" not "error in module X at line Y".
- No structured logging format — log messages are ad-hoc f-strings; grepping for a specific job's events across log files is not systematic.
- Scene cache in system temp dir — cache misses are silent and expensive, no cache hit/miss logging visible.
- No request ID correlation between frontend WS messages and backend render events.
- AI plan generation failure is logged as a single warning line (`ai_director_failed job_id=X: exc`) with no plan-component-level detail.

---

### 18. Production readiness — 4/10

**What was scored**: Resilience, data safety, failure recovery, and fitness for real-world use.

**Positive**:
- Single-user desktop tool — authentication absence is an acceptable design decision (though undocumented).
- Startup recovery marks interrupted jobs without auto-restart — correct desktop behavior.
- Output QA validation (duration + file size) catches the most common FFmpeg failures.
- Cancel mechanism works within ~1s via threading.Event + subprocess kill.
- Resume and retry mechanics are correct and tested in practice.
- The tool ships with bundled FFmpeg, bundled Python — eliminates most "dependency hell" issues for end users.

**Negative**:
- **Subtitle display duration compression** at non-1.0 speeds: subtitle blocks show for ≈13% less time at 1.15x. This is a legibility concern, not synchronization drift — subtitles ARE in sync with sped-up speech. **Resolved on overlay path (Phase 3A/3B)**: output-timeline ASS eliminates compression when `FEATURE_OVERLAY_AFTER_BASE_CLIP=1`. Legacy path still has compressed display duration.
- **TTS desync** — **Resolved (Phase 0)**: `mix_narration_audio()` applies `atempo=speed` compensation. Narration is synced to video at any speed. Covered by `TestMixNarrationAudioAtempo` regression tests.
- YouTube download has no timeout — render jobs can hang indefinitely at the download stage. The only recovery is manual server restart.
- Single SQLite database with no backup strategy — corruption = total data loss including TikTok credentials.
- No disk space check before render — full disk discovered only after a full encode pass.
- RAG system built and inactive — creator preference learning is advertised but not operational.
- V1 dead frontend code ships — larger package, more security surface, more confusion.
- Output QA tolerance of ±20% — real quality failures (missing audio, subtitle burn-in failure) pass validation.
- No codec compliance validation — B-frames in output may fail TikTok upload validation upstream.
