# CLAUDE.md — AI Video Render Studio

> ⚠️ **STALE-CONTENT NOTICE (refreshed 2026-06-06 post-Batch 10R):**
> The Phase 1-18 feature-layer migration (commits `cf80766`, `e641a21`)
> + 18 batches of audit closures (Batches 10A–R) have moved or deleted
> several paths this file used to reference. The Sacred Contracts still
> apply; file paths have moved. Highlights:
> - **CRITICAL paths now under `backend/app/features/render/{ai,engine,editing}/`** —
>   `backend/app/orchestration/`, `backend/app/services/render/`,
>   `backend/app/ai/` no longer exist.
> - `render_pipeline.py` is now `backend/app/features/render/engine/pipeline/render_pipeline.py`.
> - `part_renderer.py` is now `backend/app/features/render/engine/stages/part_renderer.py` —
>   path derivation extracted to `stages/segment_metadata.py` (Batch 10P)
>   and three Sacred Contract #5 transitions extracted to
>   `stages/part_db.py` (Batch 10Q).
> - `motion_crop.py` is now `backend/app/features/render/engine/motion/crop.py`.
> - `ffmpeg_helpers.py` is now `backend/app/features/render/engine/encoder/ffmpeg_helpers.py`.
> - **Deleted (do NOT recreate):**
>   `backend/app/services/db.py` (Batch 9 audit A14 closure — use
>   `app/db/connection.py` directly).
>   `backend/app/routes/channels.py` + 6 orphan endpoints (Batch 10H
>   audit FINDING-API05 — see `tests/test_channels_surface_gone.py`).
> - **New surfaces introduced by Batches 10A–R:**
>   `backend/app/models/render_public.py` (`RenderRequestPublic`, 88-field
>   FE-facing slice, now the wire surface for `/api/render/process` —
>   Batch 10N/10O); `backend/app/models/render.py` + `models/jobs.py`
>   (MT-2 split — `models/schemas.py` is a 39-LOC re-export shim);
>   `backend/app/services/dev/` package (MT-1 decomp from
>   `dev_commands.py`); migration `0003_add_fk_cascade_*` for
>   `job_parts` / `clip_feedback` (MT-6); `/api/settings/data-retention`
>   endpoint (MT-7 UI).
>
> The audit catalog is closed end-to-end. For a clean current view,
> prefer reading [docs/audit-2026-06-06/BATCH10_CLOSURE_LEDGER.md](docs/audit-2026-06-06/BATCH10_CLOSURE_LEDGER.md)
> first (3 sections — original + 2 addenda covering Batches 10A–R),
> then drill into [17_system_overview.md](docs/audit-2026-06-06/17_system_overview.md) →
> [18_architecture.md](docs/audit-2026-06-06/18_architecture.md) →
> [19_backend.md](docs/audit-2026-06-06/19_backend.md).

## ⚡ AGENT TEAM PROTOCOL

**All requests route through the agent team. Claude acts as Leader by default.**

| Agent | Role |
|-------|------|
| Leader | Route tasks, enforce gates, manage approval |
| Planner | Analyze + plan — never implements |
| Developer | Implement approved plans only — never expands scope |
| Reviewer | Review + reject on contract violation |
| Git | Commit proposals — never auto-pushes |
| Reporter | Vietnamese summaries at phase end |

### Risk Routing (mandatory)

| Risk | Required Flow |
|------|---------------|
| LOW | Developer directly — bug ≤5 lines, root cause confirmed |
| MEDIUM | Planner → user approval → Developer |
| HIGH | Planner → **explicit** user approval → Developer + focused pytest |
| CRITICAL | Planner → **explicit** user approval → Developer + full pytest suite |
| Unknown | Default to HIGH — do not guess |

### Hard Gates

- Developer does NOT start until user says "go ahead" / "approved" / "do it"
- Reviewer must PASS before Git runs
- Git proposes commit — never auto-pushes without second approval
- No protected file is touched without an approved plan in the conversation

> Agent definitions: `.claude/agents/*.md`

---

## Project Identity

**System:** AI video rendering platform — offline-first desktop application.

**Input:** Local video files or editor sessions. YouTube/platform download is a separate feature (`features/download/`) — downloaded files are then rendered via the local file path. The render pipeline itself only accepts `source_mode="local"` or `edit_session_id`.

**Output:** Short-form vertical videos with platform-optimized subtitles, overlays, and audio. No cloud API required.

**Stack:** FastAPI + Uvicorn + SQLite WAL + FFmpeg + Whisper + OpenCV + yt-dlp + Electron shell.

**Current Priority Order:**
1. Backend stability and correctness — frontend is being rebuilt separately
2. Render correctness — no silent failures, no corrupt output delivered as success
3. Data integrity — `data/app.db` is the sole job state authority
4. API backward compatibility — existing consumers must not break
5. AI safety — one unhandled raise in any AI module crashes the entire render pipeline
6. GPU protection — NVENC semaphore must hold or all concurrent renders fail

**Architecture Philosophy:** Modular monolith with process-isolated workers. Single SQLite database as sole state store. In-process `ThreadPoolExecutor` for job queue. FFmpeg subprocess for render execution. No Redis, no cloud, no external queue.

---

## Runtime Truth

When docs and code conflict: **trust code.** Read the actual file before assuming current state.
Never edit from memory. Never edit based on what a previous session said the file contains.
Current file state may differ from any prior analysis.

---

## Domain Documentation (read before touching these areas)

| Domain | Doc |
|--------|-----|
| Render pipeline stages | `docs/RENDER_PIPELINE.md` |
| System architecture | `docs/ARCHITECTURE.md` |
| Frontend API contract | `docs/FRONTEND_CONTRACT.md` |
| AI/LLM integration | `docs/AI_INTEGRATION.md` |
| Database schema | `docs/DATABASE.md` |
| Environment variables | `docs/CONFIGURATION.md` |

---

## Sacred Contracts — NEVER BREAK

These contracts are embedded in WebSocket consumers, UI parsers, stored job records, and API clients. Breaking any of them silently corrupts the system with no exception thrown. Every violation requires a full audit of all consumers before repair is possible.

---

### Contract 1 — result_json Backward-Compat Aliases

**Rule:** The following three keys MUST exist in every `result_json` blob written by the render pipeline, forever:

```
output_rank_score
is_best_output
is_best_clip
```

**Location:** `backend/app/features/render/engine/pipeline/pipeline_finalize.py` + `pipeline_ranking.py`

**Why it exists:** The history UI and output comparison UI parse `result_json` directly. These field names are hardcoded as string literals in multiple consumers. They predate any schema abstraction. Removing any of them does not throw an exception — the consuming code silently reads `None` or `undefined`, and data disappears from the UI.

**What breaks if violated:** History panel shows empty or missing output entries. AI Director loses its ranking signal for past jobs. Output comparison UI breaks. Cannot be detected by `py_compile`. Requires specific result_json integration tests to catch.

---

### Contract 2 — RenderRequest New Field Defaults

**Rule:** Every new field added to `RenderRequest` in `schemas.py` MUST default to `False` or the most conservative disabled state possible.

**Location:** `backend/app/models/schemas.py`

**Why it exists:** `RenderRequest` is deserialized from stored job records and from API payloads that predate the new field. If a new field defaults to `True` or an active/enabled state, every existing stored job that never explicitly set it will silently activate the new behavior on replay, retry, or history view.

**What breaks if violated:** Jobs replayed from history activate features they were never configured to use. Feature flags auto-enable on application upgrade without user consent or awareness. Behavior changes retroactively for all historical jobs.

---

### Contract 3 — AI Modules Return None on Failure — Never Raise

**Rule:** All modules under `backend/app/ai/**` and `backend/app/features/render/ai/**` MUST catch all exceptions internally and return `None` on failure. Never allow an exception to propagate upward.

**Why it exists:** The render pipeline calls AI modules mid-render. One unhandled exception in any AI module causes the entire render job to abort with no recovery path. `return None` signals the pipeline to use its fallback behavior and continue. A `raise` means the user's job is permanently lost.

**What breaks if violated:** A single AI module exception terminates the active render job mid-flight. Partial output may exist on disk with no recovery path. In a concurrent render context, this can corrupt `job_manager` thread state for other queued jobs.

---

### Contract 4 — Job Stage Transition Names (Frozen)

**Rule:** The following job-level stage names are frozen. Do not rename, reorder, or insert intermediate stages without first updating ALL WebSocket consumers and all UI code that maps these strings.

```
QUEUED → STARTING → RUNNING → ANALYZING → TRANSCRIBING_FULL →
SCENE_DETECTION → SEGMENT_BUILDING → RENDERING → RENDERING_PARALLEL →
WRITING_REPORT → DONE
(terminal: FAILED, CANCELLED)
```

Note: `DOWNLOADING` is retained in the enum for backward compat but not emitted by the render pipeline.

**Location:** `backend/app/core/stage.py` (enum) + `backend/app/features/render/engine/pipeline/render_pipeline.py` (transitions)

**Why it exists:** The frontend WebSocket handler and progress UI map exact stage name strings to progress states and labels. These strings are not shared enums with the frontend — they are string literals matched independently in multiple places.

**What breaks if violated:** Progress UI displays wrong state labels. Stage-based retry logic (`retry on FAILED`, `skip if DONE`) executes on wrong conditions. WebSocket event routing misclassifies events. Job state machine becomes incoherent between backend and frontend.

---

### Contract 5 — Job Part Transition Names (Frozen)

**Rule:** The following per-part status names are frozen. Same enforcement as job stages.

```
QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE
(terminal: FAILED, SKIPPED)
```

**Location:** `backend/app/core/stage.py` (enum) + `backend/app/features/render/engine/stages/part_renderer.py` (transitions)

**Why it exists:** Per-clip progress tracking in the UI depends on exact string matching against these values. The WebSocket event payload carries `parts[]` with these status strings. The UI renders per-clip progress bars, completion indicators, and error states based on them.

**What breaks if violated:** Per-clip progress bars freeze or display incorrect state. Part-level retry logic misidentifies recoverable vs terminal states. Partial success handling breaks — completed clips cannot be distinguished from failed clips.

---

### Contract 6 — `_emit_render_event` Signature (Frozen)

**Rule:** The signature and emitted event shape of `_emit_render_event` in `render_events.py` is frozen. Do not add, remove, or rename parameters. Do not change the event structure without simultaneously updating every call site AND the WebSocket handler in `routes/jobs.py`.

**Location:** `backend/app/features/render/engine/pipeline/render_events.py`

**Why it exists:** `_emit_render_event` is called at every stage boundary across the entire render pipeline (50+ call sites in render_pipeline.py and stage modules). Its output is the raw stream fed into the WebSocket connection consumed by the UI. Every call site must emit a consistent shape. There is no schema validation between the emitter and consumer.

**What breaks if violated:** WebSocket events arrive with missing or extra fields. The UI event handler silently ignores malformed events — no error is thrown. Progress tracking stops updating with no user-visible error. All active renders become opaque. The failure is invisible until the user realizes nothing is moving.

---

### Contract 7 — `data/app.db` Sole Job State Authority

**Rule:** `data/app.db` is the single source of truth for all job state. NEVER delete this file. NEVER write to it with raw `sqlite3.connect()` calls outside the `backend/app/db/` module. NEVER execute DROP, TRUNCATE, or ALTER TABLE RENAME on any column or table.

**Why it exists:** There is no other job state. No Redis, no cloud queue, no in-memory fallback that survives process restart. If `app.db` is deleted or corrupted, all job history is permanently and irrecoverably gone.

**What breaks if violated:** All job history permanently lost. Running jobs have no state record. The `job_manager` startup recovery loop reads `app.db` to resume interrupted jobs — if the file is missing or corrupt, all in-flight jobs are orphaned with no restart path. No alert or warning is surfaced.

---

### Contract 8 — `qa_pipeline.py` Output Validation Never Bypassed

**Rule:** `backend/app/features/render/engine/pipeline/qa_pipeline.py` is the sole output validation gate. NEVER bypass it to make a render "succeed". NEVER catch its exceptions to return a success status. NEVER lower its thresholds to make a specific broken render pass.

**Why it exists:** `qa_pipeline.py` catches: missing output file, output file too small (corrupt/truncated), no video stream present, no audio stream present, zero-duration video. These are real failure modes that occur in production. The entire purpose of this gate is to prevent corrupt videos from being delivered to users marked as successful.

**What breaks if violated:** Corrupt or incomplete videos are delivered to users with a success status. The failure is invisible until the user attempts to play the file. AI Director training receives false positive quality signals for broken renders. No alert is raised by the system. Trust in render quality is permanently compromised.

---

## Frozen API Contracts

These interfaces are consumed by the Electron frontend, by stored job records deserializing into `RenderRequest`, and by any external API client. Breaking them requires coordinated migration of ALL consumers simultaneously — which in practice means never breaking them.

### REST Endpoints (Frozen)

| Method | Path | Body / Response |
|--------|------|-----------------|
| POST | `/api/render/process` | `RenderRequestPublic` body → job creation response. Wire surface (Batch 10O) — 88 FE-facing fields, `extra='forbid'`. Handler expands to `RenderRequest` server-side to apply validators + fill the 64 BE-only defaults. |
| GET | `/api/jobs/{id}` | Job status poll response |
| GET | `/api/jobs/{id}/ws` | WebSocket upgrade for live progress stream |

**Rules:**
- Do not change these paths — ever
- Do not add required path or query parameters
- Do not remove fields from response payloads
- Additions are allowed; removals never are
- Changing a path requires updating the Electron app, the frontend, and all stored job records simultaneously

**MT-3 Public/Internal surface (since Batch 10O):**
- Wire receives `RenderRequestPublic` (88 fields). A FE field that
  moves to "user-facing" needs adding to BOTH `models/render.py`
  (internal) AND `models/render_public.py:FE_FACING_FIELDS`.
- Replay path (resume / retry / stored payload deserialisation) still
  uses `RenderRequest` with all 152 fields — Sacred Contract #2
  unchanged. Historical job replay is bit-identical.
- Adding a server-derived field to RenderRequest does NOT require
  Public surface changes — by default new RenderRequest fields are
  BE-only and live behind the wire.

### WebSocket Event Shape (Frozen)

Every WebSocket progress event emitted by `_emit_render_event` must conform to this top-level structure:

```json
{
  "job":     { "...job fields..." },
  "parts":   [ { "...part fields..." } ],
  "summary": { "...WsProgressSummary fields..." }
}
```

**Rules:**
- Do not remove any of the three top-level keys
- Do not rename `parts` to `clips`, `segments`, or anything else
- Do not flatten `summary` into the root object
- All three keys must be present in every event emission, even if `parts` is an empty array

### HTTP Polling Fallback (Must Stay Functional)

**Rule:** `GET /api/jobs/{id}` HTTP polling MUST remain a fully functional alternative to WebSocket for all progress data. Do not make any progress-tracking information WebSocket-exclusive.

**Why:** The Electron desktop app operates in environments where WebSocket upgrades may fail. Some network configurations and proxy setups block WebSocket. The polling fallback is the reliability guarantee for offline-first desktop use.

### Backward Compatibility Protocol

If a proposed change affects any frozen contract above:

1. STOP — do not implement
2. Route to Planner
3. Planner must enumerate ALL consumers of the contract (frontend, Electron, stored records, tests)
4. User must explicitly approve a migration plan that covers all consumers
5. Never assume "we'll update the frontend later" — coordinated migration or no migration

---

## Blast Radius Order

Risk order from highest to lowest. Any edit above your assigned risk tier requires an approved plan before the first Edit tool call.

### CRITICAL — Full pytest suite + explicit user approval required before any edit

```
backend/app/features/render/engine/pipeline/render_pipeline.py        # main render orchestrator — owns JobStage state machine
backend/app/features/render/engine/stages/part_renderer.py            # per-part skeleton — owns JobPartStage state machine
backend/app/features/render/engine/stages/part_render_finalize.py     # Sacred Contract #8 qa_pipeline surface
backend/app/features/render/engine/pipeline/qa_pipeline.py            # output validation gate — never bypass
backend/app/features/render/engine/motion/crop.py                     # OpenCV subject tracking skeleton
backend/app/features/render/engine/motion/path.py                     # build_subject_path + build_subject_path_scene
data/app.db                                                            # sole job state — never touch directly
```

> Note: All pipeline logic lives under `backend/app/features/render/engine/`. The old `backend/app/orchestration/` and `backend/app/services/motion_crop*` paths no longer exist.

### HIGH — Planner + explicit user approval + full pytest recommended

```
backend/app/models/schemas.py                                          # 39-LOC re-export shim post-MT-2 (Batch 10I); see models/render.py + models/jobs.py
backend/app/models/render.py                                           # MT-2 split: RenderRequest, RenderRequestStrict, TextLayer*, PrepareSourceRequest, QuickProcessRequest — Sacred Contract #2 surface
backend/app/models/render_public.py                                    # MT-3 wire surface: RenderRequestPublic (88 FE-facing fields, extra=forbid). Wired at /api/render/process (Batch 10O)
backend/app/jobs/manager.py                                            # in-process queue — thread safety and queue semantics
backend/app/features/render/engine/encoder/ffmpeg_helpers.py          # FFmpeg execution + NVENC_SEMAPHORE (defined here)
backend/app/features/render/engine/stages/part_render_encode.py       # FFmpeg encoding — acquires NVENC semaphore
backend/app/features/render/engine/encoder/clip_ops.py                # clip assembly operations
backend/app/db/connection.py                                           # SQLite connection + WAL mode + thread-local. (Batch 9 deleted services/db.py — use connection directly.)
backend/app/core/ui_gate.py                                            # controls which UI is served
backend/app/main.py                                                    # startup sequence + router mounts
backend/app/features/render/engine/pipeline/render_events.py          # _emit_render_event — frozen signature
backend/app/features/render/engine/pipeline/llm_pipeline.py           # Whisper + LLM Call 1
backend/app/features/render/engine/pipeline/llm_stage.py              # segment selection dispatch
backend/app/features/render/ai/llm/__init__.py                        # provider dispatch (select_segments + select_render_plan)
backend/app/features/render/ai/llm/prompts.py                         # prompt templates — format-safety critical
backend/app/features/render/ai/llm/parser.py                          # parse_segment_response + parse_render_plan_response
backend/app/db/jobs_repo.py                                            # jobs + render_plan_json helpers
backend/app/db/creator_repo.py                                         # creator_prefs storage
backend/app/features/render/engine/stages/part_asset_planner.py       # consumes RenderPlan.subtitle_policy
backend/app/features/render/engine/stages/part_render_setup.py        # consumes RenderPlan.camera_strategy
backend/app/features/render/engine/pipeline/pipeline_ranking.py       # output scoring + rank from RenderPlan.clips
```

### MEDIUM — Planner + focused pytest required

```
backend/app/features/render/router.py                                       # preserve validation, legacy coercion, resume/retry
backend/app/routes/jobs.py                                                  # preserve WS shape, polling, job history
backend/app/features/render/editing/router.py                               # editing API — trim, rerender, export
backend/app/features/render/engine/audio/tts.py                             # TTS synthesis
backend/app/features/render/engine/pipeline/pipeline_segment_selection.py  # segment selection, variant logic, CTA
backend/app/features/render/engine/pipeline/pipeline_config.py             # render pipeline config helpers
backend/app/features/render/engine/pipeline/pipeline_render_loop.py        # parallel part dispatch (ThreadPoolExecutor)
backend/app/features/render/engine/audio/mixer.py                          # audio pipeline
backend/app/features/render/engine/pipeline/scene_detector.py              # scene boundary detection
```

### LOW — Edit freely, no planner required

```
backend/app/routes/voice.py
backend/app/routes/feedback.py
backend/app/routes/settings.py                      # Sprint 3-FE CreatorContext API + MT-7-UI data-retention (Batch 10R)
backend/app/core/config.py                          # env vars and data paths only
backend/knowledge/**                                # add only — never delete existing entries
backend/app/domain/render_plan.py                   # pure dataclass — defensive (de)serialisation, no I/O
backend/app/domain/creator_context.py               # pure dataclass — defensive, no I/O
backend/app/services/dev/                           # MT-1 decomp of dev_commands.py — 6 sub-modules (_shared/log/bug/registry/autofix/router) behind a re-export shim
backend/app/features/render/engine/stages/segment_metadata.py  # MT-4 phase A: build_part_paths pure helper (Batch 10P)
backend/app/features/render/engine/stages/part_db.py           # MT-4 phase B: 3 Sacred Contract #5 facade methods (Batch 10Q)
```

> Removed in Batch 10H (audit FINDING-API05): `backend/app/routes/channels.py`
> + 6 orphan `/api/channels/*` endpoints + `ChannelCreate` /
> `ChannelInfo` schemas. `ensure_channel()` survives in
> `services/channel_service.py` (still called by render_pipeline +
> main.py startup). Regression guard: `tests/test_channels_surface_gone.py`.

> Note: Render router: `backend/app/features/render/router.py` (mounted at `/api/render/`). Editing router: `backend/app/features/render/editing/router.py`. Downloader router: `backend/app/features/download/router.py` (mounted at `/api/download/`). All three are mounted in `main.py`.

> Note: Job queue: `backend/app/jobs/manager.py`. Cancel registry: `backend/app/jobs/cancel.py`. These replaced `services/job_manager.py` and `services/cancel_registry.py`.

> Note: `build_render_plan()` was deleted. Any code referencing it is stale.

> RenderPlan contract: see `docs/AI_INTEGRATION.md`. Configuration reference: `docs/CONFIGURATION.md`.

---

## Critical Warnings

### ⛔ render_pipeline.py + part_renderer.py — Pipeline Orchestrators

`backend/app/features/render/engine/pipeline/render_pipeline.py` is the main render orchestrator. Stage logic is distributed across pipeline modules: `pipeline_setup.py`, `pipeline_source_prep.py`, `pipeline_narration.py`, `pipeline_render_loop.py`, `pipeline_segment_selection.py`, `pipeline_ranking.py`, `pipeline_cache.py`, `pipeline_config.py`, `pipeline_finalize.py`. Per-part rendering is orchestrated by `stages/part_renderer.py`, which delegates to 8 stage helpers: `part_render_context.py`, `part_asset_planner.py`, `part_cut.py`, `part_render_setup.py`, `part_render_encode.py`, `part_voice_mix.py`, `part_render_finalize.py`, `part_done.py`. Both files remain CRITICAL tier because they own the frozen `JobStage` and `JobPartStage` state-machine transitions. A change in either can silently affect all render paths.

- Full pytest is **required** — not optional — for any change to either file
- A Planner analysis with an explicit per-file change list is required before any edit
- Explicit user approval is required — "I think it's fine" is not approval
- Run pytest BEFORE your edit to establish a baseline, then AFTER to verify no regression
- A 3-line change in one stage can silently affect rendering behavior for all video types and all platforms
- Never make "while I'm here" improvements — one change per approved plan

### ⛔ devtools.py — Unauthenticated Shell Execution Route

`backend/app/routes/devtools.py` exposes a shell command execution endpoint protected only by checking for the `ENABLE_DEVTOOLS=1` environment variable. There is no authentication. There is no rate limiting.

- **NEVER** make it easier to enable (do not add a UI toggle, do not default to enabled)
- **NEVER** enable it in any production deployment
- **NEVER** add new endpoints or capabilities to `devtools.py`
- **NEVER** lower or remove the `ENABLE_DEVTOOLS=1` requirement
- Any change to `devtools.py` requires explicit HIGH-risk user approval

### ⛔ AI modules — Canonical Location is `features/render/ai/`

The legacy `ai/director/ai_director.py` monolith was removed in Phase G. The `app/ai/` shim layer was removed in the Phase 1-18 feature-layer migration. All imports must go directly to the canonical path — there is no shim.

- **Canonical:** `backend/app/features/render/ai/llm/` — providers (gemini, openai, claude), parser, prompts, dispatcher
- **Observability:** `backend/app/features/render/ai/visibility/` — AI visibility summaries

The AI safety rule applies absolutely: any unhandled exception in any AI module kills an active render job. Every public function MUST catch all exceptions and return `None`. Lazy-import optional deps (`torch`, `openai`, `google-genai`, `anthropic`) via try/except so missing AI extras never break startup.

### ⛔ data/app.db — No Backup, No Recovery

This is an offline-first desktop application. There is no cloud sync, no replication, no automatic backup. `data/app.db` is the only copy of all job state on the user's machine. Corruption or deletion is permanent. There is no recovery path.

### ⛔ .claude/settings.json — Security (PARTIALLY RESOLVED 2026-06-02)

`.claude/settings.json` is tracked in git and currently contains `defaultMode: "default"` (NOT `bypassPermissions` as older docs warned). It holds a ~380-entry Bash/PowerShell allowlist — no secrets, no bypass.

`.claude/settings.local.json` does NOT currently exist in the repo. Older docs warning about a tracked `bypassPermissions` mode are obsolete.

**Still applies:** Never reintroduce `defaultMode: "bypassPermissions"` to a tracked settings file. Local overrides belong in `.claude/settings.local.json` (which should remain gitignored). Periodically prune the allowlist — the current list contains entries for paths that no longer exist (`backend/static/`, `backend/static-v3/`).

---

## Performance Protections

These constants and code paths protect hardware resources. They are not performance optimizations — they are system failure prevention mechanisms.

### NVENC_MAX_SESSIONS

**Location:** `backend/app/features/render/engine/encoder/ffmpeg_helpers.py:27-28` (`NVENC_SEMAPHORE = threading.Semaphore(_NVENC_SEM_VALUE)`, default value 3, env override `NVENC_MAX_SESSIONS`). Acquired in `stages/part_render_encode.py` at NVENC encode call sites.

**What it does:** Limits the number of simultaneous NVENC GPU hardware encoder sessions.

**Why it must not be raised:** NVENC has a hardware-enforced session limit, typically 3–5 on consumer GPUs. When the limit is exceeded, NVIDIA does not gracefully fail the over-limit session — it fails ALL active sessions. Every render currently encoding fails simultaneously with a generic FFmpeg error that does not mention the NVENC limit as the cause.

**What breaks if raised beyond hardware limit:** All concurrent renders fail simultaneously with opaque FFmpeg errors. No warning before failure. Recovery requires restarting all affected jobs. The failure mode is non-obvious and hard to diagnose.

**Known gap:** Other FFmpeg call sites (`encoder/clip_ops.py`, `motion/crop.py`, `audio/mixer.py`, `preview/ffmpeg_probers.py`) do NOT acquire `NVENC_SEMAPHORE`. If any of those paths invoke an NVENC codec, the session limit can be silently exceeded.

**Rule:** Never change `NVENC_MAX_SESSIONS` without an explicit user request that includes documented reasoning and knowledge of the target hardware class.

### MAX_CONCURRENT_JOBS and MAX_RENDER_JOBS

**Location:** `backend/app/core/config.py` or `backend/app/jobs/manager.py`.

**Why they must not be changed casually:** These values cap CPU and memory consumption for a desktop application that runs alongside other software. Increasing these values without accounting for the hardware profile can make the machine unresponsive during render, causing the user to force-quit the application and orphan active jobs.

**Rule:** Only change with explicit user request that includes hardware context and reasoning.

### FFmpeg Path Helpers — Mandatory Usage

**Rule:** Always use these helper functions when constructing FFmpeg command arguments. Never concatenate raw path strings directly into FFmpeg arguments.

```python
safe_filter_path(path)    # escapes path for use inside FFmpeg filter graph arguments
get_ffmpeg_bin()          # returns platform-correct FFmpeg binary path
get_ffprobe_bin()         # returns platform-correct ffprobe binary path
```

**Why they exist:** Windows paths containing spaces, parentheses, backslashes, or other special characters cause FFmpeg to misparse filter graph arguments. The failure is silent — FFmpeg either drops the filter or produces output without the affected processing stage (e.g., subtitles missing, audio missing). Raw path concatenation has caused production render failures.

**What breaks without them:** FFmpeg receives malformed filter arguments and fails silently or partially. Rendered output is missing audio, subtitles, or overlay elements. FFmpeg's error output is generic and does not identify the path as the cause. Debugging takes significant time.

---

## Render Edit Protocol

Mandatory flow before any edit to `render_pipeline.py` or any CRITICAL-tier render file. Do not skip steps. Do not reorder steps.

```
Step 1 — Read docs/RENDER_PIPELINE.md
         Understand the exact stage you are touching and its dependencies.

Step 2 — Read docs/ARCHITECTURE.md
         Understand the system-level call chain into and out of the stage.

Step 3 — Planner produces written analysis
         Must name: exact files to change, line ranges, risk tier, test strategy, rollback plan.

Step 4 — Explicit user approval
         Wait for: "approved", "go ahead", "do it". Not implicit. Not "sounds good".

Step 5 — Run full pytest BEFORE any edit
         Record the exact pass/fail count as your baseline. Write it down.

Step 6 — Read the actual file at current state
         Not from memory. Not from a prior session. The file may have changed.

Step 7 — Make the minimal edit
         Use Edit tool (surgical diff). Never use Write tool (full file rewrite) on render files.
         Change only what the approved plan specifies. Do not touch adjacent code.

Step 8 — Run full pytest AFTER the edit
         Compare against Step 5 baseline. Any regression = STOP.

Step 9 — If regression detected
         Do NOT attempt to fix the regression in the same session.
         Report the regression with the exact failing test name and diff.
         The baseline test suite is the ground truth.
         Attempting to fix an ununderstood regression creates new hidden failures.
```

---

## Render Never-Do List

### Never bypass qa_pipeline.py

```python
# FORBIDDEN — marking render successful to avoid showing failure:
result["status"] = "success"  # render actually failed

# FORBIDDEN — swallowing validation exception:
try:
    qa_pipeline.validate(output_path)
except Exception:
    pass  # pretend it succeeded

# FORBIDDEN — lowering thresholds for a specific broken render:
MIN_OUTPUT_FILE_SIZE = 100  # was 1_000_000, changed "temporarily"
```

**Consequence:** Corrupt or empty videos are delivered to users marked as successful. The failure is invisible until the user plays the file. AI Director receives false positive training signal. User trust is permanently damaged.

---

### Never Remove Partial-Success Handling

Renders where 8 of 10 clips succeed are partial successes. They must remain visible in the UI as partial, with the successful clips accessible. Do not convert partial successes into failures or into full successes.

**Consequence:** The user loses access to the 8 clips that rendered correctly. The job appears as fully failed, but output was produced and exists on disk. User must restart the entire job to recover clips that already finished.

---

### Never Change `_emit_render_event` Without Updating All Consumers

`_emit_render_event` is called at every stage transition across the entire pipeline. The WebSocket handler in `routes/jobs.py` parses its exact output shape. If the emitter shape changes at the source but the consumer is not updated simultaneously, events are silently dropped.

**Consequence:** Progress UI freezes mid-render with no error shown. User cannot distinguish between "render is running slowly" and "progress reporting is broken". All concurrent renders become opaque. Must restart the backend to recover.

---

### Never Remove Resume/Retry Behavior

`render_pipeline.py` contains logic to resume interrupted jobs and retry failed stages. This exists because render jobs on a desktop machine take 20–60 minutes and system interruptions (sleep, crash, network drop) are routine.

**Consequence:** Any interruption requires restarting the entire job from scratch. Up to 60 minutes of compute work lost per interruption. The application becomes unreliable for long renders. This is a regression that directly degrades the user's trust in the tool.

---

### Never Skip Source Cleanup on Failure Paths

When a render fails at any stage, the cleanup path (deleting downloaded source files, temp segments, partial outputs) must still execute. Failure paths must not silently skip cleanup.

**Consequence:** Each failed render leaves orphaned files consuming disk space. The accumulation is invisible — no counter, no alert. The machine runs out of disk space during a future render with no clear cause. The user sees a generic disk space error with no indication of where the space went.

---

## Database Rules

### SQLite Additive-Only Migrations

**Rule:** Every schema change to `data/app.db` must be strictly additive:

| Allowed | Forbidden |
|---------|-----------|
| New table with all-nullable or defaulted columns | DROP TABLE |
| New column with a DEFAULT value | DROP COLUMN |
| New index | RENAME COLUMN |
| | ALTER TABLE RENAME |
| | Changing column type |

**Why:** This is an offline desktop application. There is no migration rollback path. A destructive migration executes on the user's machine and permanently destroys data. New columns with defaults allow all existing rows and all existing application code to continue reading the database without modification or crash.

### WAL Mode Must Not Change

**Rule:** SQLite WAL (Write-Ahead Logging) mode is set at startup in the DB connection module. Do not change the journal mode under any circumstances.

**Why:** WAL mode enables concurrent readers while a write transaction is open. The render pipeline executes high-frequency progress writes (`update_job_progress`) while the frontend simultaneously polls for job state via HTTP. Without WAL, every progress write blocks all readers, causing the progress polling loop to stall for the duration of each write. The UI appears frozen during active renders.

**What breaks if changed:** Journal mode `DELETE` (SQLite default) causes reader-writer blocking. Progress updates cause the HTTP polling response to stall. The frontend shows frozen progress during active renders. Performance degrades proportionally to render frequency.

### No Direct Writes Outside the db/ Module

**Rule:** Never access `data/app.db` using a raw `sqlite3.connect()` call outside of `backend/app/db/`. All database access must go through the established connection module. (Batch 9 deleted the `backend/app/services/db.py` re-export facade — older docs that named it as a sanctioned access path are obsolete.)

**Why:** The connection module sets WAL mode, registers row factories, and manages thread-local connection state for the render thread. Bypassing it creates connections without WAL mode, without row factories, and in incompatible isolation levels — all of which corrupt the consistency guarantees the pipeline depends on.

### Known Issue — Mixed Connection Model (Sprint 5.4 partial closure)

Helpers live in `backend/app/db/connection.py`:

- `db_conn()` ctxmgr — HTTP path / bounded ops. Auto-commit on normal exit, rollback on exception. Used by `jobs_repo.py`, `creator_repo.py`, `feedback_repo.py`, `download_repo.py` (`download_repo` migrated to `db_conn()` in Sprint 5.4, commit `9347613`).
- `_thread_conn()` — render hot path only. Thread-local persistent connection used by `update_job_progress()` and `upsert_job_part()` in `db/jobs_repo.py`. Released via `close_thread_conn()` at end of `render_pipeline.py` AND belt-and-suspenders in `routers/_common.process_render`'s finally (Batch 10A, audit BR10 closure — covers worker-thread death before the pipeline's own cleanup runs).

Sprint 5.4 ruling: the `_thread_conn` → `db_conn` unification stays DEFERRED. Empirical benchmark shows `db_conn` is ~165× slower per call (3,152 μs vs 18.8 μs median, WAL mode). The two-pattern surface is steady state. See `docs/DATABASE.md` for the full decision record.

Do not add callers that introduce a third model (raw `sqlite3.connect()` outside the sanctioned sites in `connection.py`, `features/render/engine/pipeline/db_backup.py`, and `features/download/engine/cookie_extractor.py`). Enforced by `tests/test_contract_db_sole_authority.py`.

---

## AI Module Rules

### Optional Dependencies in `requirements-ai.txt` Only

**Rule:** Any package that is optional for AI inference (PyTorch, transformers, CUDA bindings, ML model loaders) goes exclusively in `requirements-ai.txt`. Never add optional AI packages to `requirements.txt`.

**Why:** The system must install and run correctly for users who do not have GPU hardware, who have not installed the AI dependency set, or who are running in a reduced-capability mode. The base `requirements.txt` install must produce a working render system — AI features degrade gracefully, they do not block the installation.

### AI Modules Must Not Fail at Import Time

**Rule:** Every module under `backend/app/features/render/ai/**` must import successfully even when optional dependencies are absent. Use lazy imports with availability flags.

```python
# Correct pattern:
try:
    import torch
    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False

def run_model(input_data):
    if not _TORCH_AVAILABLE:
        return None
    ...

# Forbidden pattern:
import torch  # crashes entire FastAPI startup if torch not installed
```

**What breaks if violated:** The entire FastAPI application fails to start. Every render is impossible — not just AI-enhanced ones. The user cannot use the tool at all, and the error message (`ModuleNotFoundError: No module named 'torch'`) does not clearly indicate that it is an optional dependency.

### AI Modules Must Return None on Failure

This is repeated here as implementation guidance. Every method in every `backend/app/features/render/ai/**` module:

```python
# Correct pattern:
def analyze(self, input_data):
    try:
        return self._run_inference(input_data)
    except Exception:
        return None  # caller uses fallback behavior

# Forbidden pattern — propagates exception upward:
def analyze(self, input_data):
    return self._run_inference(input_data)  # unhandled exception kills the render job
```

The render pipeline handles `None` returns from AI modules with fallback behavior. There is no fallback for an exception.

---

## Audit Ledger

Architecture audits live in dated folders under `docs/`. The current
canonical audit is `docs/audit-2026-06-06/`. The older `docs/review/`
folder was archived during the Phase 1-18 feature-layer migration
(commit `e641a21`) — its files are recoverable from git history but
the directory no longer exists on the working tree. `docs/archive/**`
likewise holds frozen historical artifacts.

The append-only rule still applies to whichever folder is current.
For `audit-2026-06-06/` specifically:

1. NEW findings or follow-up closures go in NEW files (e.g.
   `BATCH10_CLOSURE_LEDGER.md`, `SMOKE_TEST_2026-06-06_BATCH10R.md`).
2. Existing files in the audit folder are NEVER edited in place —
   the closure ledger uses append-only addenda at the bottom (see
   the 3-section structure of `BATCH10_CLOSURE_LEDGER.md` for the
   pattern).
3. If a finding relates to a prior file, reference it by filename in
   the new file's body.
4. Never delete files from any audit folder.

**Why:** the audit folder is the history of architectural knowledge
at specific points in time. Editing existing files rewrites history.
Future auditors must be able to read what was known at each point in
time and trace what changed. Mutating historical records destroys the
audit trail.

---

## ⛔ render-flow.html — Prototype Only, Never "Done" Until Ported

`render-flow.html` is a standalone visual prototype. It is **NOT** the real UI.

**Rule:** Any design change made in `render-flow.html` is NOT done until the same change is implemented in the real files:

| Real file | Role |
|-----------|------|
| `frontend/src/features/clip-studio/render/RenderWorkflow.tsx` | All rendering/results screen logic and JSX |
| `frontend/src/features/clip-studio/render/RenderWorkflow.css` | All rendering/results screen styles |

**Enforcement:**
- Never report a UI task as complete after editing `render-flow.html` only
- Always port prototype changes to `RenderWorkflow.tsx` + `RenderWorkflow.css` before marking done
- `render-flow.html` may be used to sketch/prototype, but the real implementation is the only source of truth
- When comparing "what the screen should look like," read the prototype for design intent, then implement in `RenderWorkflow.tsx`

---

## Quick Commands

```powershell
# Activate backend venv (PowerShell, from repo root)
cd D:\tool-render-video\backend
.\.venv\Scripts\Activate.ps1

# Start backend with v2 UI
.\run-backend-v2.ps1

# Start Electron desktop app
.\run-desktop-v2.ps1

# Syntax-check a changed Python file (run after every Python edit)
python -m py_compile app\features\render\engine\pipeline\render_pipeline.py

# Run a focused test suite
python -m pytest tests\test_render_guards.py -v --tb=short

# Run full test suite (required for CRITICAL/HIGH tier changes)
python -m pytest

# Check git status cleanly
git status --short

# Verify which .claude/ files are tracked in git (they ARE tracked — not gitignored)
git ls-files .claude/
```

### Safe Git Staging (Mandatory)

```powershell
# Stage explicit file paths only:
git add backend/app/features/render/router.py
git add backend/app/models/schemas.py

# FORBIDDEN — stages secrets, build artifacts, unreviewed files:
git add .
git add *
git add -A
```

---

## Agent Compatibility

### Leader Agent Behavior

Route ALL render-related requests through Planner before any implementation. Use these shortcuts for risk classification:

```
render_pipeline.py mentioned    → CRITICAL tier → Planner required, full pytest required
part_renderer.py mentioned      → CRITICAL tier → same as render_pipeline.py
motion/crop.py mentioned        → CRITICAL tier → same as render_pipeline.py
features/render/ai/** mentioned → HIGH tier → AI safety rule (return None, never raise) is absolute
qa_pipeline.py mentioned        → CRITICAL tier → never bypass contract is absolute
schemas.py field change         → HIGH tier → additive-only verification first
API route path mentioned        → HIGH tier → check Frozen API Contracts section first
database schema mentioned       → HIGH tier → additive-only rule applies
NVENC or MAX_* constants        → HIGH tier → Performance Protections section applies
devtools.py mentioned           → HIGH tier → security danger, explicit approval required
features/render/router.py       → MEDIUM tier → Planner + focused pytest
features/render/editing/        → MEDIUM tier → Planner + focused pytest
routes/jobs.py edit             → MEDIUM tier → Planner + focused pytest
routes/*.py edit (non-job)      → LOW tier → edit freely, no planner required
config.py edit                  → LOW tier → env vars only, direct to Developer
```

Do not allow Developer to start on MEDIUM+ risk without an approved plan present in the conversation.

### Developer Agent Behavior

Before touching any file:

1. Read the actual file at current state — prior-session assumptions are invalid
2. Check Blast Radius Order — confirm the risk tier of every file in the plan
3. CRITICAL or HIGH tier: confirm an approved plan is present in the conversation before the first Edit call
4. Use Edit tool (surgical diff) for all edits on existing files — never Write tool for full rewrites
5. Change only what the approved plan specifies — no adjacent improvements
6. Run `py_compile` after every Python file change
7. Run `pytest` before declaring any task complete

For `render_pipeline.py` specifically: follow the Render Edit Protocol section exactly, in order, without skipping steps.

### Reviewer Agent Behavior

Check auto-reject conditions first. Reject immediately on the first violation found — no discussion needed.

**Auto-Reject (immediate, no negotiation):**

| Condition | Reason |
|-----------|--------|
| CRITICAL or HIGH tier file edited without approved plan visible in conversation | Safety gate violation |
| `output_rank_score`, `is_best_output`, or `is_best_clip` absent from result_json writes | Breaks UI backward compatibility |
| Any API route path changed | Breaks existing API consumers |
| Any AI module under `backend/app/features/render/ai/**` can `raise` instead of `return None` | Pipeline crash on any failure |
| `qa_pipeline.py` validation bypassed, caught, or threshold lowered | Corrupt renders delivered as success |
| `git add .`, `git add *`, or `git add -A` proposed | Stages unreviewed or sensitive files |
| Stage or part transition name changed without documented WS consumer audit | Silent UI breakage |

**Review Checklist (all must pass before PASS verdict):**

- [ ] API payload and response fields preserved — additive changes only, no removals
- [ ] `RenderRequest` new fields default to `False` or disabled equivalent
- [ ] Job stage enum values in `core/stage.py` unchanged — especially: QUEUED, RUNNING, ANALYZING, RENDERING, DONE, FAILED, CANCELLED
- [ ] Job part names unchanged: `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE`
- [ ] WebSocket event shape preserved: top-level `job`, `parts[]`, `summary` all present
- [ ] HTTP polling fallback still functional — no progress data made WebSocket-exclusive
- [ ] `result_json` parseable by consumers: `output_rank_score`, `is_best_output`, `is_best_clip` present
- [ ] Output validation still catches: missing file, file too small, no video stream, no audio stream, zero duration
- [ ] Subtitle and voice code paths no-op cleanly when those features are disabled
- [ ] AI module changes bounded: no import-time failures on missing optional deps, no unhandled raises
- [ ] Any behavior or specification change is reflected in a new file under the current audit folder (`docs/audit-2026-06-06/` as of 2026-06-06)

**Overengineering Flags (stop, escalate to Planner for rescoping):**

- Three or more files changed when one was expected
- A new abstraction layer added for a single use case
- A helper function created for a function called once
- Existing working code refactored while fixing an unrelated bug

### QA Agent Behavior

Before marking any render-touching task complete:

1. Run `python -m pytest` (full suite) — not just the focused test
2. Verify `py_compile` passes on every changed Python file
3. If `render_pipeline.py` was changed: confirm the total test count matches the pre-edit baseline
4. If `schemas.py` was changed: confirm no existing field was removed or renamed
5. If `routes/*.py` was changed: confirm all three frozen route paths are unchanged
6. If `qa_pipeline.py` was changed: confirm no validation threshold was lowered and no exception path was added that returns success

---

## Known Active Issues (Investigation Required Before Touching)

### Issue 1 — Frontend Build Pipeline (RESOLVED 2026-06-02)

`vite.config.ts:13` now declares `build.outDir = '../backend/static-v2'` with `emptyOutDir: true`.
`ui_gate.py:53-58` serves from `backend/static-v2/` when `STATIC_UI_VERSION=v2`.
Running `npm run build` updates the live served UI correctly.

Caveat: `emptyOutDir: true` will wipe `backend/static-v2/` on every build — do not place hand-authored assets there.

### Issue 2 — Mixed DB Connection Model (DEFERRED INDEFINITELY)

Two connection patterns are steady state (see `docs/DATABASE.md`):
- `db_conn()` — HTTP path, auto-commit context manager
- `_thread_conn()` — render hot path only, thread-local cached connection

`db_conn` is ~165× slower per call (3,152 μs vs 18.8 μs). Unification deferred indefinitely.

Do not add callers that introduce a third pattern (raw `sqlite3.connect()` outside `connection.py`, `features/render/engine/pipeline/db_backup.py`, and `features/download/engine/cookie_extractor.py`). Enforced by `tests/test_contract_db_sole_authority.py`.

**Observability addition (Batch 10A, audit DB09 closure / ST-15):** every
acquire of either connection emits to the
`db_conn_acquire_seconds` Prometheus histogram with `role={db_conn|_thread_conn}`.
`_thread_conn` cache hits are skipped — only first-opens and stale
re-opens observe. See `/metrics` for live data.

### Issue 3 — Cache Location (RESOLVED)

Cache root: `APP_DATA_DIR/cache`. Pruned at startup (`main.py`) and every 30 minutes (`_run_periodic_cleanup`). TTL 72h for render cache, 30d for XTTS, 7d for text overlay. Subdir-agnostic walker — new cache subdirs are automatically pruned.

**Atomic-write addition (Batch 10F, audit BR14 closure):** the 4
`_*_cache_put` helpers in `pipeline_cache.py` now stage bytes in a
`.tmp` sidecar and `os.replace` into place. `prune_render_cache` skips
`.tmp` files entirely. Concurrent prune vs Whisper-cache-write can no
longer truncate the target.

### Issue 4 — Pipeline Files (CURRENT STATE)

Current locations (all under `backend/app/features/render/engine/`):
- `pipeline/render_pipeline.py` — main orchestrator
- `stages/part_renderer.py` — per-part skeleton (~260 LOC), delegates
  to 8 stage helpers + the two MT-4 extracts: `segment_metadata.py`
  (path derivation — Batch 10P) and `part_db.py` (3 Sacred Contract #5
  transitions — Batch 10Q)
- `motion/crop.py` — OpenCV tracking skeleton
- `motion/path.py` — `build_subject_path`; `motion/path_scene.py` — `build_subject_path_scene`

All CRITICAL tier — own state machines despite refactor.

### Issue 5 — FFmpeg Layer (CURRENT STATE)

Real FFmpeg execution: `features/render/engine/encoder/ffmpeg_helpers.py` (NVENC semaphore defined here) + `stages/part_render_encode.py` (acquires semaphore).

Clip assembly: `features/render/engine/encoder/clip_ops.py`. Overlay: `features/render/engine/overlay/text_overlay.py`. Audio: `features/render/engine/audio/mixer.py`.

### Issue 6 — DB FK + cascade on job_parts / clip_feedback (RESOLVED — Batch 10L)

`data/app.db` now enforces `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE`
on `job_parts` and `clip_feedback`. Fresh DBs get the constraint via
`init_db`; existing DBs are retrofitted by migration
`0003_add_fk_cascade_to_job_parts_and_clip_feedback.py` (defensive
orphan cleanup + temp-table-rename recipe). `delete_job` was already
atomic via `db_conn` transaction; this closes the defence-in-depth
gap the audit flagged as BR03.

### Issue 7 — Whisper model LRU (RESOLVED — Batch 10E)

Both `_MODEL_CACHE` (OpenAI whisper) and `_FW_MODEL_CACHE` (faster-whisper)
are now `OrderedDict` LRU caches with cap 2 (configurable via
`WHISPER_MODEL_CACHE_MAX` / `FW_MODEL_CACHE_MAX`). Mixing `tiny`
(preview) + `large-v3` (render) no longer pins multi-GB of model
weights forever.

### Issue 8 — DB row retention via Settings UI (RESOLVED — Batch 10A backend + 10R UI)

`prune_old_jobs(max_age_days)` runs on every periodic cleanup tick.
The cleanup loop reads the value from `creator_prefs.prefs_json`
nested key `data_retention.job_retention_days` (Settings screen UI in
Batch 10R) and falls back to the `JOB_RETENTION_DAYS` env var when
the UI value isn't configured. 0 = retention disabled (the default).
Active jobs (`status IN ('running', 'queued')`) are NEVER pruned
regardless of age — Sacred Contract #7.
