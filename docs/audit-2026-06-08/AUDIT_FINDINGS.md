# Audit Findings — Batches A + B

Consolidated forensic findings from Phases 1–15 of the 24-phase audit.
Every claim cites `file:line`. Findings closed by 9-commit sprint are
marked **CLOSED**.

## Phase 1–3 — System Discovery + Execution Graph

### Topology

```
Frontend (Electron + Vite + React + Zustand)
  frontend/src/features/clip-studio/render/RenderWorkflow.tsx
  frontend/src/api/render.ts (submitRender → POST /api/render/process)

REST API (FastAPI) mounted in backend/app/main.py:113-139
  /api/render        — features/render/router.py (7 lifecycle + 4 utility + 4 prepare + 3 read)
  /api/jobs          — routes/jobs.py (15 endpoints + WebSocket)
  /api/jobs/.../parts — features/render/editing/router.py
  /api/downloader    — features/download/router.py (separate feature)
  /api/settings, /api/feedback, /metrics, /api/voice, /api/upload-file

Orchestration
  backend/app/jobs/manager.py:39-216 — ThreadPoolExecutor, MAX_CONCURRENT_JOBS=cpu//2
  backend/app/jobs/cancel.py — in-process threading.Event registry
  Pipeline orchestrator:
    backend/app/features/render/engine/pipeline/render_pipeline.py:298-1402
  Per-part skeleton:
    backend/app/features/render/engine/stages/part_renderer.py:112-291

Database (SQLite WAL, sole authority — Sacred Contract #7)
  Tables: jobs, job_parts (FK CASCADE), creator_prefs, download_jobs,
          clip_feedback (FK CASCADE)
  Indexes: idx_jobs_updated, idx_jobs_status_kind, idx_dl_jobs_*,
           idx_feedback_channel

AI Layer
  features/render/ai/llm/__init__.py:24-68 — dispatch (gemini default)
  features/render/ai/llm/providers/{gemini,openai,claude}.py
  features/render/ai/llm/prompts.py + parser.py
  features/render/ai/visibility/ai_visibility_summary.py
  features/render/ai/context/builder.py — CreatorContext

Render Layer
  engine/pipeline/ (24 helpers — setup, source_prep, llm_pipeline,
    render_loop, ranking, finalize, qa_pipeline, render_events,
    scene_detector, pipeline_cache, etc.)
  engine/stages/ (per-part: part_renderer + part_cut + part_asset_planner +
    part_render_setup/encode/finalize + part_voice_mix + part_done +
    part_db + segment_metadata + viral_scoring)
  engine/encoder/ (ffmpeg_helpers — NVENC_SEMAPHORE, clip_renderer,
    overlay_compositor, clip_ops, encoder_helpers)
  engine/motion/ (crop, path, path_scene, tracker, pixel_diff,
    detection, scoring, trackerless, …)
  engine/audio/ (mixer, tts, tts_xtts, profiles, cleanup_adapters)
  engine/overlay/ (text_overlay)
  engine/subtitle/, preview/, quality/, thumbnail/

Output
  <output_dir>/<stem>_part_NNN.mp4
  Best exports: <output_dir>/best/<stem>_rank_NN.mp4
  result_json with 27 top-level keys (Sacred Contract #1 keys present)
```

### Public surface

- `POST /api/render/process` accepts `RenderRequestPublic` (was 88,
  now **67** fields after T1.4 + follow-up).
- `RenderRequest` itself: 152 fields (64 BE-only before; **85** after).
- Wire-to-internal expansion at
  `features/render/routers/lifecycle.py:51-98` →
  `RenderRequest(**public_payload.model_dump())`.
- Sacred Contract #4 stages (after T2.3 closure): runtime now emits
  every stage in the frozen ordering:
  `QUEUED → STARTING → ANALYZING (T2.3) → DOWNLOADING (back-compat) →
   TRANSCRIBING_FULL → SCENE_DETECTION (T2.3) → SEGMENT_BUILDING →
   RENDERING / RENDERING_PARALLEL → WRITING_REPORT → DONE`.

## Phase 4 — AI Input Forensics

What the LLM ACTUALLY receives (file:line):

- **System prompt** — `prompts.py:46-51` — shared across all 3
  providers; concatenated with `editorial_hint` at `prompts.py:301`.
- **User prompt slots** (`prompts.py:58-232` + `:259-325`):
  - `{language}` — from `payload.llm_language` (`render_pipeline.py:582`)
  - `{output_count}` — from `payload.output_count` (`:576`)
  - `{min_sec}` / `{max_sec}` — from `payload.min_part_sec` /
    `max_part_sec` (`llm_pipeline.py:322-323`)
  - `{srt_content}` — Whisper SRT, converted to seconds-format,
    truncated by provider-specific cap (Gemini 60K / Claude 50K /
    OpenAI 30K)
  - `{editorial_section}` — from `_build_editorial_hint`
    (`llm_stage.py:49-91`)
  - `{target_duration_section}` — **NEW after T2.4**. Renders an
    explicit "TARGET TOTAL DURATION" paragraph when
    `payload.target_duration > 0`; suppressed (back-compat) when 0.

### Field audit table (post all closures)

| User-facing intent | Reaches LLM? | How |
|--------------------|--------------|-----|
| `creator_style` | Indirect — via `CreatorContext.brand_voice` from creator_prefs |
| `target_platform` | Post-LLM only; not in prompt — applied at `pipeline_segment_selection.py:25-51` |
| `target_market` (request) | NO — `ai_target_market` not in prompt |
| `target_audience` (creator_prefs) | YES — `creator_context.py:148-150` |
| `audience_type` | n/a — no model field |
| `content_goal` | n/a — no model field |
| `hook_strength` | YES — `_HOOK_HINTS` advisory at `llm_stage.py:27-37` |
| `clip_count` | YES — as `output_count` |
| `min_duration` / `max_duration` | YES — as `min_part_sec` / `max_part_sec` |
| `video_type` | YES — `_VIDEO_TYPE_HINTS` advisory at `llm_stage.py:39-46` |
| **`target_duration`** | **YES — T2.4 (commit 7f57475)** as soft total-duration target |

### Provider runtime params

| | Gemini | OpenAI | Claude |
|---|---|---|---|
| Default model | `gemini-2.5-flash` (env override) | `gpt-4o-mini` (hardcoded) | `claude-haiku-4-5-20251001` (hardcoded) |
| Temperature | 0.2 | 0.2 | 0.2 |
| Max output | 16384 | 4096 | 4096 |
| JSON mode | `application/json` MIME | `{"type":"json_object"}` | None — prompt obedience |
| Cache | 72h content-addressable | same | same |
| Retry | shared `call_with_retry` 2 attempts | same | same |

API keys are STRIPPED from client payloads at `models/render.py:388-404`
and resolved from server env via `llm_stage._resolve_api_key:94-129`.

## Phase 5 — AI Output Forensics

### Parser (`features/render/ai/llm/parser.py`)

- Three accepted shapes: native (`{clips: [...], subtitle_policy,
  camera_strategy, audio_plan, overlays}`), wrapped
  (`{render_plan: {…}}`), legacy `{segments: [...]}`.
- Robust against: malformed JSON (4-strategy extractor — raw / fenced
  / first `{}` / first `[]`), prose-wrapped JSON, fields in wrong
  order, extra fields (filtered by `_filter_dataclass`).
- Per-clip validation: duration in `[min_sec, max_sec]`, `start >= 0`,
  `end <= video_duration + 1.0`, score clamped to `[0, 1]`, clip_name
  sanitised.
- Truncate to top-`output_count` by score DESC; rank reassigned 1..N
  (AI's rank field overridden).

### Vision-field audit (user's `{segment, score, title, reason, hook_type, ranking{viral, hook, retention, audience_fit}}`)

| Field | Verdict |
|-------|---------|
| `segment` | PARTIAL — flat `start`/`end` on `ClipPlan`, not nested |
| `score` | PRESENT |
| `title` | PRESENT but DISPLAY ONLY (`render_pipeline.py:267` → `seg["ai_title"]` → `/api/jobs/{id}/parts`) |
| `reason` | PRESENT but DISPLAY ONLY |
| `hook_type` | PRESENT; biases CTA type at `part_asset_planner.py:633-641` |
| `ranking.viral_score`, `.hook_score`, `.retention_score` | PARTIAL — present FLAT on `ClipPlan`, not nested |
| **`ranking.audience_fit`** | **MISSING entirely** — zero grep hits anywhere |

### Sacred Contract #3 audit (returns None never raise)

Verified at every exit from `ai/llm/**`:
- Provider boundary: `gemini.py:78-92`, `openai.py:56-70`,
  `claude.py:62-76` — outer try/except → None
- Parser boundary: `parser.py:102, 159-161`
- Retry wrapper: `retry.py:194-199`
- Orchestrator outer try: `render_pipeline.py:530, 647-653`
- `llm_pipeline.py` IS allowed to `raise LLMPipelineError` because it
  sits OUTSIDE `ai/**` (orchestration tier).

✅ Contract intact.

### Bug — closed by T1.5

`prompts.py:248,295` referenced undefined `MAX_SRT_CHARS`. Call site
`render_pipeline.py:545` invoked `check_srt_truncation` without
`max_srt_chars=` → `NameError` swallowed by outer try/except as
"AI emission failed". Effect: transcript-truncation WS warning never
fired for ANY provider. **Closed by T1.5 (commit b4a5052).**

## Phase 6–7 — Render Input + AI → Render Mapping

### Vision-field consumer status

| Field | Status | Severity |
|-------|--------|----------|
| `target_platform` | ✅ READ in 8 sites | OK |
| `output_count` | ✅ READ → LLM cap | OK |
| `min_part_sec`/`max_part_sec` | ✅ READ → LLM bounds | OK |
| `hook_strength` | ⚠️ ADVISORY only — soft hint in prompt | OK |
| `video_type` | ⚠️ ADVISORY only — soft hint | OK |
| **`target_duration`** | **✅ READ — T2.4 wires to LLM (commit 7f57475)** | OK |
| `energy_style` | ❌ Removed from wire (T1.4) | CLOSED |
| `output_language` | ❌ Removed from wire (T1.4) | CLOSED |
| `narration_style` | ❌ Removed from wire (T1.4) | CLOSED |
| `target_market` (`ai_target_market`) | ⚠️ READ but gated by `combined_scoring_enabled` (default False) | MEDIUM (strategic) |
| Phase-G zombie flags (11 in Public) | ❌ Removed from wire (T1.4 + follow-up) | CLOSED |
| UP26 4 fields | ❌ Removed from wire (T1.4) | CLOSED (strategic LLM wire deferred) |
| `playback_speed` | ✅ READ — default `1.07` always applied | **HIGH** (deferred V8-A7) |

### RenderPlan field consumer status (after T2.4)

Consumed:
- `clips[i].start/.end/.score/.clip_name` — drives FFmpeg + filenames
- `clips[i].hook_type` — biases CTA type
- `clips[i].content_type` — drives CRF, subtitle bias, CTA library
- `clips[i].subtitle_style` — per-clip subtitle override
- `clips[i].viral_score/.hook_score/.retention_score` — ranking
- `clips[i].speech_density/.duration_fit` — ranking weights
- `clips[i].cover_offset_ratio` — cover-frame hint
- `subtitle_policy.style/.market/.emphasis_pass` — subtitle policy
- `camera_strategy.reframe_mode` — only this field; tracker dead
- `audio_plan.voice_provider` + `.cta_audio` (misnamed — text only)
- `overlays[kind=hook]` — first hook overlay only (hard-coded styling)

**Display only (never rendered into video):**
- `clips[i].title`, `clips[i].reason` — flow to `result_json[segments].ai_title/ai_reason` → exposed via HTTP + WS (T1.4-followup / VW-3) but never appear as on-screen text.

**Dead (documented deferral):**
- `camera_strategy.motion_aware_crop` — `part_render_setup.py:113-122`
  explicit deferral
- `camera_strategy.tracker` — same
- `audio_plan.voice_enabled` / `.bgm_enabled` — `part_voice_mix.py:104-108`
  documented bool-ambiguity blocker

**Silently dropped:**
- `overlays[kind=cta]` — `render_pipeline.py:679,684` loop only matches `"hook"`

### Sacred Contract #1 keys

`output_rank_score`, `is_best_output`, `is_best_clip` present at
`pipeline_ranking.py:225-247` + `render_pipeline.py:1167-1206` +
`pipeline_finalize.py:130`. ✅

## Phase 8 — Workflow Violations

### A) User chose X → AI doesn't use X

| ID | Title | Severity | Status |
|----|-------|----------|--------|
| V8-A1 | `target_duration` validated then ignored | HIGH | ✅ Closed (T2.4) |
| V8-A7 | `playback_speed=1.07` silent default | HIGH | ⏳ Deferred |
| V8-A8 | `motion_aware_crop` AI value discarded | MEDIUM | Documented |
| V8-A12 | `clip_lock`/`clip_exclude` never reach LLM | HIGH | ⏳ Strategic |
| V8-A6 | `hook_strength` + `video_type` advisory only | MEDIUM | Documented |

### B) FE sends X → BE ignores

| ID | Title | Status |
|----|-------|--------|
| V8-B5 | FE sends Phase-G zombies as `true` | ✅ Closed (T1.4) |
| V8-B1 | FE never sets `playback_speed` (default sneaks) | Deferred (V8-A7) |
| V8-B7 | BE emits 22 result_json keys FE doesn't read | Documented |
| V8-B8 | Structured event detail trapped (V8-C1 follow) | ⏳ Deferred (T3.1) |

### C) BE returns X → FE doesn't read

| ID | Title | Sev | Status |
|----|-------|-----|--------|
| V8-C1 | `_emit_render_event` JSONL never reaches FE WS | **CRITICAL** | ⏳ Deferred (T3.1) |
| V8-C2 | clip_name / ai_title / ai_reason declared FE type, BE never persists | HIGH | ✅ Closed (VW-3 + FINDING-C03) |

### D) AI decides X → Render overrides X

| ID | Title | Status |
|----|-------|--------|
| V8-D1 | Local ranking recomputes via 6-weight rubric, overrides AI overall score | ⏳ Strategic |
| V8-D2 | AI rank fragile — duplicate/gap forces silent legacy sort | Documented |
| V8-D4 | motion_aware_crop / voice_enabled / bgm_enabled deferred | Documented |

## Phase 9 — False Success Hunt

### A) Backend says completed but output is wrong

| ID | Title | Sev | Status |
|----|-------|-----|--------|
| V9-A1 | Resume-skip bypasses full `_validate_render_output` | HIGH | ✅ Closed (T1.2) |
| V9-A4 | Auto-best-export copies outputs without re-validation | LOW | Documented |

### B) FE shows success but render failed

| ID | Title | Status |
|----|-------|--------|
| V9-B1 | FE fires success toast on `{completed, completed_with_errors, partial}` without result-content check | Documented |

### C) AI failed but pipeline continued

| ID | Title | Sev | Status |
|----|-------|-----|--------|
| V9-C1+C2+D2 | `select_render_plan` returns None → empty scored → 0 outputs → status="completed" + success toast | **CRITICAL** | ✅ Closed (T1.1) |

### E) WS fails but UI shows success

| ID | Title | Sev | Status |
|----|-------|-----|--------|
| V9-E1 | FE has NO HTTP polling fallback | HIGH | ✅ Closed (T1.3) |
| V9-E2 | `RenderSocketClient.onclose` retries WS only, never falls back | MEDIUM | Closed by T1.3 wider design |

### F) Cancel signal lost

| ID | Title | Sev | Status |
|----|-------|-----|--------|
| V9-F2 | Whisper uninterruptible | HIGH | ✅ Closed (T2.1) |
| V9-F3 | OpenCV motion crop uninterruptible | HIGH | ✅ Closed (T2.2) |
| V9-F5 | cancel_registry in-process — restart loses signal | MEDIUM | ⏳ Strategic |

### G) Resume/retry semantics

| ID | Title | Sev | Status |
|----|-------|-----|--------|
| V9-G1 | Resume reuses old QA check (cross-ref V9-A1) | HIGH | ✅ Closed (T1.2) |
| V9-G2 | Retry skips done parts without re-validating (cross-ref V9-A1) | HIGH | Inherits T1.2 closure |

## Phase 10 — State Machine Forensics

### Enum

`JobStage`: QUEUED, STARTING, RUNNING, ANALYZING, DOWNLOADING,
SCENE_DETECTION, SEGMENT_BUILDING, TRANSCRIBING_FULL, RENDERING,
RENDERING_PARALLEL, WRITING_REPORT, DONE, FAILED, CANCELLED.

### Post-T2.3 written-stage status (B-10-A closure)

| Stage | Written? | Where |
|-------|----------|-------|
| QUEUED | ✅ | `_common.py:240, 264` |
| STARTING | ✅ | `render_pipeline.py:431` |
| RUNNING (as stage) | ⚠️ — used as STATUS string not as stage value | `manager.py:86` |
| **ANALYZING** | **✅ (T2.3 closure)** | `pipeline_source_prep.py:96` |
| DOWNLOADING | ✅ (back-compat) | `pipeline_source_prep.py:97` |
| TRANSCRIBING_FULL | ✅ | `llm_pipeline.py:128, 225` |
| **SCENE_DETECTION** | **✅ (T2.3 closure)** | `llm_pipeline.py:~290` |
| SEGMENT_BUILDING | ✅ | `llm_pipeline.py:293` |
| RENDERING / RENDERING_PARALLEL | ✅ | `pipeline_render_loop.py:88, 166, 230` |
| WRITING_REPORT | ✅ | `render_pipeline.py:1087` |
| DONE | ✅ | `pipeline_finalize.py:223` |
| FAILED | ✅ | `render_pipeline.py:1381` |
| CANCELLED | ✅ | `_common.py:184-186` |

### Sticky issues

- B-10-B: synthetic `"partial"` status — ✅ **Closed by T3.2** (now
  returns canonical `"completed_with_errors"`).
- `interrupted` is NOT in `_TERMINAL_STATUSES` — server-restart leaves
  jobs in `interrupted` with WS poll continuing. Documented; not a bug
  because user explicitly clicks Resume.

## Phase 11 — Frontend Audit

### Closed by 9-commit sprint

- T1.3 — HTTP polling fallback wired in `useRenderSocket.ts` after WS
  reconnect exhaustion (5s polling of `GET /api/jobs/{id}` +
  `/parts`). Closes V9-E1.
- T1.4 + follow-up — 21 dead fields removed from `RenderRequest`
  TypeScript interface + `buildPayload`. Closes V8-B5, UP26, UP27,
  v2 dead.
- VW-3 — WS handler enriches parts with AI metadata via
  `_enrich_parts_with_segment_ai_fields`. Closes V8-C2.

### Documented gaps (not closed)

- FE labels in `StepConfigure.tsx:567, 607, 886` still display the
  removed field names — UI form widgets cleanup is a follow-up.
- FE only reads `result_json.output_ranking` (`api/jobs.ts:103-114`)
  and `best_clip` — 22 of 27 BE-emitted `result_json` keys invisible.
- Backend comment `routes/jobs.py:778` says "Frontend falls back to
  HTTP polling if this endpoint fails" — was a lie pre-T1.3; now true.

## Phase 12 — Backend Audit

### Routes (60+ endpoints, all mounted)

7 lifecycle + 4 utility + 4 prepare + 3 read + 15 jobs + 3 editing +
12 downloader + 4 settings + 4 feedback + 1 voice + 1 files + 1
metrics + 1 devtools (gated by `ENABLE_DEVTOOLS=1` + loopback assert).

### God-module candidates

| File | LOC | Status |
|------|-----|--------|
| `render_pipeline.py` | 1402 | CRITICAL tier (accepted — 8 helpers extracted) |
| `part_asset_planner.py` | 953 | God module (subtitle + viral + RenderPlan policy + CTA) |
| `routes/jobs.py` | 935 | God module (15 endpoints + WS + history normaliser) |
| `clip_renderer.py` | 905 | Encoder layer — appropriate |
| `motion/crop.py` | 803 | CRITICAL tier — expected |

### Anti-pattern hunt

| Pattern | Found |
|---------|-------|
| `sqlite3.connect(` outside sanctioned sites | NONE (Sacred Contract #7 ✅) |
| Bare except outside AI tier | Defensive only |
| Unbounded retries | NONE (retry.py capped at 2) |
| Hard-coded model IDs | OpenAI + Claude hardcode default; Gemini reads env (asymmetric) |
| NVENC_SEMAPHORE acquire on all FFmpeg call sites | Gaps exist (B-12-A): `motion/crop.py`, `audio/mixer.py`, `preview/ffmpeg_probers.py`, `encoder/clip_ops.py` ⏳ Strategic |

## Phase 13 — Database Audit

### Tables

`jobs`, `job_parts` (FK CASCADE per Batch 10L), `creator_prefs`
(singleton), `download_jobs` (standalone, no FK), `clip_feedback`
(FK CASCADE).

### Indexes

`idx_jobs_updated (updated_at DESC, created_at DESC)`,
`idx_jobs_status_kind (status, kind)`, `idx_dl_jobs_status`,
`idx_dl_jobs_created`, `idx_feedback_channel (channel_code, goal)`.

**Missing (mitigated)**: `job_parts(job_id)` (mitigated by
`UNIQUE(job_id, part_no)` implicit index).

### Sacred Contract #7 verification

`grep sqlite3.connect(` → 7 hits, ALL sanctioned:
- `db/connection.py:56, 119, 196`
- `features/download/engine/cookie_extractor.py:173, 187`
- `features/render/engine/pipeline/db_backup.py:91, 93`

✅ Contract intact.

### WAL mode

`PRAGMA journal_mode=WAL` set on both `get_conn` (`connection.py:121`)
and `_thread_conn` (`connection.py:198`). ✅

### Retention prune

`services/maintenance.py:239` `prune_old_jobs` restricts deletion to
`_PRUNABLE_JOB_STATUSES` (terminal set), uses belt-and-suspenders
explicit DELETE on `job_parts` before `jobs` (covers pre-migration-0003
DBs without CASCADE).

### Dead column flag

`jobs.render_plan_json` — written by `update_render_plan` but never
read on resume/retry. Documented as forensic only; not a runtime bug.

## Phase 14 — Legacy / Dead Code

### YouTube / yt-dlp surface outside `features/download/`

| File:line | Status | Action |
|-----------|--------|--------|
| `routes/jobs.py:103, 108` | Legacy-only — runs on STORED rows with no `source_mode` | KEEP defensively |
| `models/render.py:100-101` `youtube_url`, `youtube_urls` | DEAD on render path (validator rejects non-local) | KEEP (Sacred Contract #2) |
| `models/render_public.py:54` `youtube_url` in `FE_FACING_FIELDS` | KEPT for legacy-job inference | OK |
| `render_pipeline.py:1360, 1372` | Error-log context only | LOW priority cleanup |
| `core/tracing.py:16` | Docstring example | Update docstring |

### Phase-G zombie fields

27 `ai_*` fields in `RenderRequest` gated by `ctx.ai_edit_plan` which
is hardcoded `None` at `render_pipeline.py:931`. T1.4 removed 11 from
the Public surface; **the remaining 16 stay in `RenderRequest` for
Sacred Contract #2 replay safety** but never reach the wire.

## Phase 15 — Test Audit

### 782 tests across 57+ files (after VW-1 closures)

#### Test value classes

- **HIGH VALUE (Sacred Contract guards):**
  - `test_sacred_contract_3_ai_return_none.py`
  - `test_sacred_contract_6_ws_shape.py`
  - `test_sacred_contract_8_qa_thresholds.py`
  - `test_render_pipeline_contract.py` (AST contract — JobStage enum
    use, `_emit_render_event` kwarg, STAGE_TO_EVENT coverage)
  - `test_render_request_public_surface.py` (Python ↔ TS parity)
  - `test_resume_disk_vs_db_invariant.py` (resume disk-truth choice)
  - `test_render_pipeline_integration.py` (3 happy-path 2-part renders)
  - `test_e2e_ffmpeg_render.py` (the only true E2E with FFmpeg)
  - `test_jobs_repo_stage_validation.py` (status/stage WARN validators)
  - `test_part_db_transitions.py` (Sacred Contract #5)
  - `test_nvenc_semaphore_guard.py` (NVENC contract)

#### New tests landed in this sprint (VW-1, commit f2b035f)

- `test_false_success_zero_outputs.py` (2 tests) — T1.1 guard
- `test_resume_runs_full_qa.py` (5 tests) — T1.2 guard (behavioural +
  structural)
- `test_render_request_public_no_dead_fields.py` (4 tests) — T1.4
  guard (caught 2 more dead fields: `max_export_parts`, `part_order`)

#### Sprint 4 — still missing

| Test | Guards | Effort |
|------|--------|--------|
| `test_cancel_interrupts_whisper.py` | T2.1 — Whisper cancel UX | 4h |
| `test_cancel_interrupts_motion_crop.py` | T2.2 — OpenCV cancel | 4h |
| `test_stages_analyzing_scene_detection_emitted.py` | T2.3 — Sacred Contract #4 frozen-stage runtime emission | 4h |
| FE: `useRenderSocket.test.ts` | T1.3 — polling fallback activates | 4h |
| FE: `render-workflow-payload.test.ts` | T1.4 — buildPayload no dead fields | 2h |
