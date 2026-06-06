# 08 — Architecture Review

Independent architectural assessment based on Phase 1–2 evidence + dedicated Phase 3 scan. Source code only.

> LOC numbers in this doc were measured by `wc -l` against the working tree on 2026-06-06. Where they disagreed with the sub-agent's numbers, the measured values are kept.

---

## 1. Top-25 LOC distribution (backend)

| Rank | File | LOC | Tier |
|---|---|---|---|
| 1 | `services/dev_commands.py` | **1542** | CLI/devtools utility — god file |
| 2 | `features/render/engine/pipeline/render_pipeline.py` | **1357** | render orchestrator — god by design |
| 3 | `features/render/router.py` | **1195** | god controller (15+ endpoints) |
| 4 | `features/render/engine/encoder/clip_renderer.py` | 905 | FFmpeg encode core |
| 5 | `models/schemas.py` | 892 | Pydantic surface |
| 6 | `features/render/engine/stages/part_asset_planner.py` | 883 | per-part asset prep |
| 7 | `routes/jobs.py` | 806 | jobs/WS controller |
| 8 | `features/render/engine/motion/crop.py` | 803 | motion crop skeleton |
| 9 | `features/download/engine/downloader.py` | 776 | yt-dlp wrapper + per-platform logic |
| 10 | `features/render/engine/stages/viral_scoring.py` | 742 | scoring algorithms |
| 11 | `features/render/engine/subtitle/transcription/adapters.py` | 694 | Whisper provider variants |
| 12 | `features/render/engine/encoder/ffmpeg_helpers.py` | 647 | FFmpeg helpers + NVENC semaphore |
| 13 | `features/render/engine/stages/part_render_finalize.py` | 639 | finalize stage |
| 14 | `features/render/engine/motion/path_scene.py` | 592 | per-scene motion path builder |
| 15 | `features/render/engine/quality/assessor.py` | 582 | quality assessment |
| 16 | `services/qa_runner.py` | 554 | local QA runner |
| 17 | `features/render/engine/subtitle/processing/readability.py` | 544 | subtitle readability rules |
| 18 | `features/render/engine/overlay/text_overlay.py` | 506 | text overlay generator |
| 19 | `routes/channels.py` | 475 | channels CRUD |
| 20 | `features/render/ai/llm/parser.py` | 458 | LLM response parsing |
| 21 | `features/render/engine/subtitle/generator/ass.py` | 457 | ASS subtitle writer |
| 22 | `services/warmup.py` | 456 | startup warmup |
| 23 | `features/render/engine/stages/part_render_encode.py` | 450 | per-part encode dispatcher |
| 24 | `features/render/engine/pipeline/llm_pipeline.py` | 448 | mandatory LLM pre-render |
| 25 | `features/render/ai/llm/prompts.py` | 423 | LLM prompt templates |

**Counted >800 LOC: 8 files.** Total backend (`backend/app/**.py` ex-pycache): **40,146 LOC**.

## Top-15 LOC distribution (frontend)

| Rank | File | LOC | Tier |
|---|---|---|---|
| 1 | `types/openapi-generated.ts` | 4091 | generated — skip |
| 2 | `features/clip-studio/render/steps/StepConfigure.tsx` | **944** | god component |
| 3 | `features/clip-studio/render/steps/StepResults.tsx` | 786 | results god component |
| 4 | `features/clip-studio/download/DownloadTab.tsx` | 647 | download tab |
| 5 | `features/clip-studio/render/RenderWorkflow.tsx` | 566 | step orchestrator |
| 6 | `features/downloader/DownloaderScreen.tsx` | 456 | sidebar downloader |
| 7 | `features/settings/SettingsScreen.tsx` | 455 | creator-context form |
| 8 | `features/clip-studio/render/steps/StepRendering.tsx` | 447 | progress screen |
| 9 | `features/clip-studio/history/HistoryTab.tsx` | 447 | history tab |
| 10 | `types/api.ts` | 419 | hand-written API types |
| 11 | `features/jobs/JobDetailDrawer.tsx` | 411 | drawer |
| 12 | `i18n/translations.ts` | 359 | translations |
| 13 | `features/editor/EditorMetadataPanel.tsx` | 324 | editor panel |
| 14 | `layouts/Sidebar.tsx` | 319 | sidebar |
| 15 | `features/jobs/HistoryScreen.tsx` | 272 | history root |

Total `frontend/src/**` (`.ts` + `.tsx`, ex-generated): **~14,000 LOC**.

---

## 2. God files (backend)

### 2.1 `services/dev_commands.py` — 1542 LOC — **FINDING-A01 (HIGH)**

Distinct responsibilities (read at top of file + grep):
1. CLI command dispatcher
2. Feature registry builder
3. Git status/blame/log parser
4. Error log classifier
5. Bug-class inference from stacktraces
6. Auto-fix orchestrator (≥6 strategies)
7. Test runner wrapper
8. Status aggregation
9. Slack / HTTP webhook integration

This is a workshop's worth of dev tooling collapsed into one file. It is **not reachable from the rest of the app** (no production import path), so blast radius is low — but it's the largest file in the codebase and the hardest to evolve. Recommend split into `services/dev/{router,feature_registry,log_analyzer,bug_classifier,autofix,…}.py`.

### 2.2 `features/render/engine/pipeline/render_pipeline.py` — 1357 LOC — **FINDING-A02 (HIGH)**

After Sprint 6.D this was reported at 1,103 LOC. It has grown **+254 lines** (+23 %) in subsequent sprints (mostly Sprint 7.x feature flags + RenderPlan plumbing). Owns:

1. `JobStage` state machine
2. Feature-flag dispatch (4 active flags + 2 retired)
3. Source-prep dispatch
4. Optional pre-narration TTS
5. Mandatory LLM call
6. Optional RenderPlan emission + persistence
7. Subtitle gating
8. Render loop dispatch
9. AI visibility summary attachment
10. Finalize coordination
11. Error / cancel paths

This file remains CRITICAL tier because it owns the per-job state machine. Splitting further requires an orchestrator-pattern refactor (state machine class) — not a verbatim move. Acceptable for now; flag for revisit in Phase 11.

### 2.3 `features/render/router.py` — 1195 LOC — **FINDING-A03 (HIGH)**

15+ endpoints in one file:

```
queue-status, cache/clear, ai/diagnostics, prepare-source,
prepare-source/{id}/cancel, preview-video, preview-transcript,
process, upload, quick-process, resume, retry, {job_id}/cancel,
{job_id}, {job_id}/part/{n}/media, {job_id}/part/{n}/thumbnail,
subtitle-preview
```

Recommend split into 4 routers: `prepare/`, `render/` (process/resume/retry/cancel/get), `preview/` (media/thumbnail/subtitle), `utility/` (cache, diagnostics). All bundled under the same `/api/render` prefix.

### 2.4 `models/schemas.py` — 892 LOC — **FINDING-A04 (MED)**

Mixes:
- domain request models (RenderRequest, PrepareSourceRequest, QuickProcessRequest)
- per-feature models (Channel*, Feedback*, Upload*)
- vestigial upload-related models (UploadAccount*, UploadVideo*, ProxyPool*) — see §6 (dead code).

Split into `models/{render,channels,upload,download,feedback}.py` and re-export from `models/__init__.py`.

### 2.5 `features/render/engine/motion/crop.py` — 803 LOC

Per CLAUDE.md, motion crop was decomposed in Sprint 6.D-3.x (skeleton + `motion_path.py` builder). The skeleton kept the public surface (`build_subject_path`, `render_motion_aware_crop`) and the OpenCV-tracking state machine. 803 LOC is **within target** (≤ 800 was the goal; ≤ 800 LOC is the bar) — barely over. Acceptable, **monitor**.

### 2.6 `features/render/engine/stages/part_asset_planner.py` — 883 LOC

Plans per-part assets (SRT slice, ASS conversion, camera strategy, asset filenames). This file is doing a lot of "what should be in this clip" logic. Phase 4 (duplication) should check if camera strategy logic overlaps RenderPlan parsing.

---

## 3. God controllers (FE)

### 3.1 `StepConfigure.tsx` — 944 LOC — **FINDING-A05 (HIGH)**

50+ form fields, nested `SubtitleDemo` / `SubtitlePreview` components inside, FFmpeg preview fetching, AI provider testing, file/dir pickers, validation. Single `useState` shape holds the entire config.

Recommend: split into `ConfigForm` (state + handlers), `ConfigTabs` (UI), `PreviewPanel` (FFmpeg subtitle preview), `AiTestPanel` (provider test).

### 3.2 `StepResults.tsx` — 786 LOC — **FINDING-A06 (MED)**

Results grid + AI summary card + quality panel + per-clip actions (trim/rerender/export/delete/rate). Likely subdivisible into `ResultsGrid`, `BestPick`, `AiSummary`, `PerClipActions`, `QualityPanel`.

### 3.3 `RenderWorkflow.tsx` — 566 LOC — **FINDING-A07 (LOW)**

Orchestrates 3 steps + WS lifecycle + restore-state. The "container" pattern is justifying its size, but the `handleStartRender` payload assembly (~60 LOC) and the WS handler setup could move into hooks.

---

## 4. Cross-cutting violations

### 4.1 Circular / asymmetric dependencies

**FINDING-A08 (MED) — `download` ↔ `render` coupling.** Not actually circular, but:

- `features/download/router.py:111` imports `dl_job_start`, `dl_job_done`, `dl_job_fail` from `app.features.render.engine.pipeline.workflow_trace`.
- `features/render/router.py:25` imports `slugify` from `app.features.download.engine.downloader`.
- `features/render/engine/pipeline/pipeline_source_prep.py:46` imports the same `slugify`.

These are **wrong direction** dependencies: a downloader knowing about render's telemetry, render knowing about downloader's slug builder.

Recommend: move `slugify` → `app/core/naming.py`; move workflow trace types → `app/core/tracing.py`.

**FINDING-A09 (CLEAN) — `ai/**` does not back-import from `engine/**`.** Verified. Only `domain/` types and shared services flow back.

**FINDING-A10 (CLEAN) — `domain/` is a true leaf.** No reverse imports.

### 4.2 Hidden coupling

**FINDING-A11 (MED) — global `NVENC_SEMAPHORE`.** Module-level `threading.Semaphore` in `encoder/ffmpeg_helpers.py:27-28`. Acquired implicitly by 3 sites (Phase 1 FINDING). All metrics in `services/metrics.py` read its internal value too. There is no DI seam, so test isolation requires monkey-patching the module global. Combined with FINDING-R01 (only 3 acquire sites — risk other paths invoke NVENC without acquiring), this is the highest-risk global in the system.

**FINDING-A12 (MED) — `_PREVIEW_SESSIONS` singleton.** Dict + `OrderedDict` cache + `Lock` in `engine/preview/session_service.py:18`. Re-exported and mutated from `features/render/router.py:46-49` preview handlers. Phase 11 should encapsulate mutations behind module-level functions only.

**FINDING-A13 (MED) — thread-local cancel events.** `_tls = threading.local()` in `ffmpeg_helpers.py:39`. `set_thread_cancel_event(ev)` stores per thread. `_run_ffmpeg_with_retry()` reads `_tls.cancel_event` without `getattr(.., None)` defence. If a code path skips `set_thread_cancel_event`, an unhelpful `AttributeError` is raised inside FFmpeg loop and caught by outer try — silent cancel failure. Add a default guard.

### 4.3 Side effects at import time

Acceptable level only:
- `core/config.py` runs `load_dotenv()` + creates app dirs (`mkdir(…, exist_ok=True)`).
- `main.py` configures logging.

No file I/O or network calls at import. ✓

### 4.4 Facade chains

| File | LOC | Status |
|---|---|---|
| `services/db.py` | 49 | live re-export facade — 18 callers; remove only after migrating callers (Phase 11) |
| `routes/voice.py` | 19 | thin TTS test router — acceptable |
| `features/render/engine/pipeline/render_output.py` | ~15 | dataclass only — inline into pipeline_config.py |
| `features/render/engine/pipeline/report_service.py` | ~15 | one-function module — fold into `services/reporting.py` |

**FINDING-A14 (LOW):** Phase 11 roadmap should batch the 2 micro-modules + start migrating callers off `services/db.py`.

### 4.5 Feature leakage

**FINDING-A15 (MED) — `services/maintenance.py` knows render details.** Calls `prune_render_cache`, `prune_render_temp_dirs`, `prune_xtts_cache`. Should be `features/render/services/maintenance.py` with `services/maintenance.py` orchestrating per-feature cleanup hooks.

**FINDING-A16 (MED) — `services/warmup.py` loads render-specific models.** Whisper + XTTS warmup. Same recommendation.

**FINDING-A17 (CLEAN) — FE `api/` does not import from `features/`.** Verified.

### 4.6 Duplicate logic

Spot-checked:

- **`RenderRequest` validation scattered** — 3 helpers in `features/render/router.py` (`_validate_output_dir`, `_validate_render_source`, `_validate_text_layers_or_400`) + downstream re-validation in `pipeline_setup.py`. Single `RenderRequestValidator` would deduplicate (FINDING-A18, MED).
- **FFmpeg argv builders** — each call site builds its own filter chain. No shared `FFmpegBuilder`. Risk: filter graphs drift (FINDING-A19, MED).
- **Path naming** — `slugify`, output-path stems duplicated across `part_renderer.py`, `part_done.py`, `downloader.py`. Recommend `app/core/naming.py` (already mentioned in FINDING-A08).

### 4.7 Mixed responsibilities — 3 picks

**FINDING-A20 (HIGH):** `stages/part_renderer.py::process_one_part` mixes parsing + DB writes + event emission + stage orchestration in one function. Recommend split: `SegmentMetadata` (parse), `PartDB` (writes), `PartEvents` (log), `PartOrchestrator` (delegate to stage helpers).

**FINDING-A21 (HIGH):** `features/render/router.py::prepare_source` mixes input validation + work-dir creation + 7 event emissions + ffprobe + preview-session persistence in one endpoint. Split as in §3.

**FINDING-A22 (MED):** `stages/part_render_finalize.py::run_part_finalize` mixes micro-pacing + asset overlay + viral scoring + QA validation + quality assessment + 12 event emits. Already the Sacred Contract #8 surface; splitting needs care.

---

## 5. Dead code

Beyond ghost dirs from Phase 1:

**FINDING-A23 (LOW):** Models defined in `schemas.py` with zero callers:
- `DownloadBatchRequest`
- `UploadAccount*`, `UploadVideo*`, `ProxyPool*` (a whole upload feature whose router was deleted Phase 4F.5A)

Recommend delete. (Tracked in Phase 4 dead_code_report.)

**FINDING-A24 (LOW):** `_pycache_` files for `motion_crop_legacy.cpython-311.pyc` survive without source. Clean once `git clean -fdx` is run; safer to add `data/` patterns to gitignore.

---

## 6. Seven-dimension scores

Scale: 1 (terrible) to 10 (excellent).

| Dimension | Score | Why |
|---|---|---|
| **Scalability** | **4** | Single SQLite + single FastAPI process + single in-proc `ThreadPoolExecutor`. WAL helps reads, but the design is *offline-first desktop*; horizontal scaling would need a major rewrite (drop Sacred Contract #7). NVENC semaphore correctly caps GPU. MAX_CONCURRENT_JOBS + JOB_SEMAPHORE form a reasonable backpressure trio. For the design intent (single user, single host), 6/10; for "could this serve 100 concurrent users", 1/10. **Average 4.** |
| **Maintainability** | **5** | 8 god files, 18 importers of `services/db.py`, three ghost dirs, stale CLAUDE.md actively misleading. Counterweights: per-feature folders, per-stage modules, Sprint 6.D + feature-layer migration show ongoing investment, 22 commits on this branch addressing technical debt. Weighted **5**. |
| **Readability** | **6** | Module names self-describing. Stage helpers reasonably small. BUT god files (1357, 1195 LOC) contain 200+ LOC functions with no internal sub-section comments. Sacred Contracts referenced by number (#1..#8) but no canonical list. Feature-flag matrix opaque. Tests provide little reading documentation. **6**. |
| **Extensibility** | **6** | New LLM provider = one file. New subtitle style = one file. BUT: new render stage = touch part_renderer skeleton + new stage file + JobPartStage string (frozen by contract but not enum-checked) + DB stage column + FE label map. New AI score signal = touch parser, ranking weights, visibility summary, FE renderer. The hot paths are pluggable; cross-cutting concerns are sticky. **6**. |
| **Testability** | **4** | 17 test files for ~180 backend modules + 0 FE tests despite Vitest dependency. God files mostly untested (and hard to test given module globals + threading + filesystem deps). Sacred Contract #1 has a contract test (`test_pipeline_ranking.py:170-175`) — exemplary. No integration test for a full render flow; no FE test of the WS event handler. **4**. |
| **Reliability** | **6** | Sacred Contracts honored (#1, #3, #6, #8 verified). QA gate solid. WAL + db_backup. BUT: no SQL FK constraints, status enums are text (typo → silent corruption), LLM mandatory hard-fail = single API key kills job, no LLM retry, NVENC semaphore not centralized. Resume-from-last is real. **6**. |
| **Observability** | **7** | Prometheus metrics for NVENC, FFmpeg duration, job queue. Per-job log files. WS event stream (poll-based but functional). AI visibility summary surfaced to FE. AGAINST: event log not piped to FE (S02), no distributed trace IDs, no per-error aggregation dashboard. For a desktop app, this is excellent. **7**. |

**Overall weighted: (4+5+6+6+4+6+7)/7 = 5.4 / 10.**

This is a mid-grade architecture with strong intent and consistent contracts, undermined by accumulated complexity (god files) and an under-invested test surface (Phase 9 will confirm).

---

## 7. Top 10 architecture-level actions (sorted by ROI)

1. **Centralize NVENC semaphore inside `_run_ffmpeg_with_retry`** conditioned on `_argv_uses_nvenc(command)`. Closes FINDING-R01 + A11. (Sprint-scale.)
2. **Promote job/part stage enums to `enum.StrEnum`** and add `CHECK(status IN (…))` SQL constraints on `jobs.status`, `jobs.stage`, `job_parts.status`. Closes FINDING-D02. (Sprint.)
3. **Move `slugify` and `workflow_trace` to `app/core/`** to fix cross-feature coupling (FINDING-A08). (Day.)
4. **Split `features/render/router.py`** into 4 sub-routers. Closes FINDING-A03, A21. (Sprint.)
5. **Wrap LLM provider calls in 2-attempt retry with `Retry-After` honor** (FINDING-AI05). (Day.)
6. **Cache LLM responses keyed `(provider, model, srt_hash, params_hash)`** (FINDING-AI06). (Sprint.)
7. **Decide LLM-mandatory policy:** either accept the trade-off and ship a clear FE error code + settings hint, or restore a legacy heuristic fallback (FINDING-AI07 / S07). (Tech decision + sprint.)
8. **Audit `services/db.py` callers** and migrate them to direct `app.db.*` imports, then delete the facade (FINDING-A14). Lowers blast radius by ~18 files. (Sprint.)
9. **Delete ghost dirs `backend/app/{ai,orchestration,quality}/`** and remove stale guidance from CLAUDE.md (FINDING-B01). (Hour.)
10. **Pull render-specific maintenance + warmup into `features/render/services/`** (FINDING-A15, A16) so `services/` remains feature-agnostic. (Day.)

End of 08_architecture_review.md.
