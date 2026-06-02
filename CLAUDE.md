# CLAUDE.md — AI Video Render Studio

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

**Input:** YouTube URLs or local video files.

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
| Frontend API contract | `docs/FRONTEND_CONTRACT_PACKET_V1.md` |
| Subtitle/translation | `docs/SUBTITLE_TRANSLATION.md` |
| Voice narration | `docs/VOICE_NARRATION.md` |
| Electron desktop | `docs/DESKTOP_APP.md` |

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

**Location:** `backend/app/orchestration/render_pipeline.py`

**Why it exists:** The history UI, output viewer, and AI Director training pipeline all parse `result_json` directly. These field names are hardcoded as string literals in multiple consumers. They predate any schema abstraction. Removing any of them does not throw an exception — the consuming code silently reads `None` or `undefined`, and data disappears from the UI.

**What breaks if violated:** History panel shows empty or missing output entries. AI Director loses its ranking signal for past jobs. Output comparison UI breaks. Cannot be detected by `py_compile`. Requires specific result_json integration tests to catch.

---

### Contract 2 — RenderRequest New Field Defaults

**Rule:** Every new field added to `RenderRequest` in `schemas.py` MUST default to `False` or the most conservative disabled state possible.

**Location:** `backend/app/models/schemas.py`

**Why it exists:** `RenderRequest` is deserialized from stored job records and from API payloads that predate the new field. If a new field defaults to `True` or an active/enabled state, every existing stored job that never explicitly set it will silently activate the new behavior on replay, retry, or history view.

**What breaks if violated:** Jobs replayed from history activate features they were never configured to use. Feature flags auto-enable on application upgrade without user consent or awareness. Behavior changes retroactively for all historical jobs.

---

### Contract 3 — AI Modules Return None on Failure — Never Raise

**Rule:** All modules under `backend/app/ai/**` MUST catch all exceptions internally and return `None` on failure. Never allow an exception to propagate upward.

**Why it exists:** The render pipeline calls AI modules mid-render. One unhandled exception in any AI module causes the entire render job to abort with no recovery path. `return None` signals the pipeline to use its fallback behavior and continue. A `raise` means the user's job is permanently lost.

**What breaks if violated:** A single AI module exception terminates the active render job mid-flight. Partial output may exist on disk with no recovery path. In a concurrent render context, this can corrupt `job_manager` thread state for other queued jobs.

---

### Contract 4 — Job Stage Transition Names (Frozen)

**Rule:** The following job-level stage names are frozen. Do not rename, reorder, or insert intermediate stages without first updating ALL WebSocket consumers and all UI code that maps these strings.

```
QUEUED → DOWNLOADING → RENDERING → DONE
(terminal: FAILED, CANCELLED)
```

**Location:** `backend/app/orchestration/render_pipeline.py`

**Why it exists:** The frontend WebSocket handler and progress UI map exact stage name strings to progress states, colors, labels, and conditional logic (e.g., "skip DOWNLOADING if already DONE"). These strings are not enum constants shared with the frontend — they are string literals embedded independently in multiple places.

**What breaks if violated:** Progress UI displays wrong state labels. Stage-based retry logic (`retry on FAILED`, `skip if DONE`) executes on wrong conditions. WebSocket event routing misclassifies events. Job state machine becomes incoherent between backend and frontend.

---

### Contract 5 — Job Part Transition Names (Frozen)

**Rule:** The following per-part status names are frozen. Same enforcement as job stages.

```
QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE
(terminal: FAILED, SKIPPED)
```

**Location:** `backend/app/orchestration/render_pipeline.py`

**Why it exists:** Per-clip progress tracking in the UI depends on exact string matching against these values. The WebSocket event payload carries `parts[]` with these status strings. The UI renders per-clip progress bars, completion indicators, and error states based on them.

**What breaks if violated:** Per-clip progress bars freeze or display incorrect state. Part-level retry logic misidentifies recoverable vs terminal states. Partial success handling breaks — completed clips cannot be distinguished from failed clips.

---

### Contract 6 — `_emit_render_event` Signature (Frozen)

**Rule:** The signature and emitted event shape of `_emit_render_event` in `render_pipeline.py` is frozen. Do not add, remove, or rename parameters. Do not change the event structure without simultaneously updating every call site in `render_pipeline.py` AND the WebSocket handler in `routes/jobs.py`.

**Why it exists:** `_emit_render_event` is called at every stage boundary across the entire render pipeline (render_pipeline.py + stages/part_renderer.py). Its output is the raw stream fed into the WebSocket connection consumed by the UI. Every call site must emit a consistent shape. There is no schema validation between the emitter and consumer.

**What breaks if violated:** WebSocket events arrive with missing or extra fields. The UI event handler silently ignores malformed events — no error is thrown. Progress tracking stops updating with no user-visible error. All active renders become opaque. The failure is invisible until the user realizes nothing is moving.

---

### Contract 7 — `data/app.db` Sole Job State Authority

**Rule:** `data/app.db` is the single source of truth for all job state. NEVER delete this file. NEVER write to it with raw `sqlite3.connect()` calls outside the `backend/app/db/` module. NEVER execute DROP, TRUNCATE, or ALTER TABLE RENAME on any column or table.

**Why it exists:** There is no other job state. No Redis, no cloud queue, no in-memory fallback that survives process restart. If `app.db` is deleted or corrupted, all job history is permanently and irrecoverably gone.

**What breaks if violated:** All job history permanently lost. Running jobs have no state record. The `job_manager` startup recovery loop reads `app.db` to resume interrupted jobs — if the file is missing or corrupt, all in-flight jobs are orphaned with no restart path. No alert or warning is surfaced.

---

### Contract 8 — `qa_pipeline.py` Output Validation Never Bypassed

**Rule:** `backend/app/orchestration/qa_pipeline.py` is the sole output validation gate. NEVER bypass it to make a render "succeed". NEVER catch its exceptions to return a success status. NEVER lower its thresholds to make a specific broken render pass.

**Why it exists:** `qa_pipeline.py` catches: missing output file, output file too small (corrupt/truncated), no video stream present, no audio stream present, zero-duration video. These are real failure modes that occur in production. The entire purpose of this gate is to prevent corrupt videos from being delivered to users marked as successful.

**What breaks if violated:** Corrupt or incomplete videos are delivered to users with a success status. The failure is invisible until the user attempts to play the file. AI Director training receives false positive quality signals for broken renders. No alert is raised by the system. Trust in render quality is permanently compromised.

---

## Frozen API Contracts

These interfaces are consumed by the Electron frontend, by stored job records deserializing into `RenderRequest`, and by any external API client. Breaking them requires coordinated migration of ALL consumers simultaneously — which in practice means never breaking them.

### REST Endpoints (Frozen)

| Method | Path | Body / Response |
|--------|------|-----------------|
| POST | `/api/render/process` | `RenderRequest` body → job creation response |
| GET | `/api/jobs/{id}` | Job status poll response |
| GET | `/api/jobs/{id}/ws` | WebSocket upgrade for live progress stream |

**Rules:**
- Do not change these paths — ever
- Do not add required path or query parameters
- Do not remove fields from response payloads
- Additions are allowed; removals never are
- Changing a path requires updating the Electron app, the frontend, and all stored job records simultaneously

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
backend/app/orchestration/render_pipeline.py        # 1,525 lines — main orchestrator (refactored from 5,816-line monolith)
backend/app/orchestration/stages/part_renderer.py   # 2,101 lines — per-part rendering: cut→TTS→subtitle→FFmpeg
backend/app/orchestration/qa_pipeline.py            # 385 lines — output validation gate — never bypass
backend/app/services/motion_crop.py                 # 2,512 lines — OpenCV subject tracking
data/app.db                                         # sole job state — never touch directly
```

> Note: `backend/app/ai/director/ai_director.py` was removed in Phase G (RAG/AI Director retirement, see `main.py:238`). Historic references in older docs/agent definitions can be ignored — the file does not exist.

### HIGH — Planner + explicit user approval + full pytest recommended

```
backend/app/models/schemas.py                       # Pydantic API contracts — additive only, never rename
backend/app/services/job_manager.py                 # in-process queue — thread safety and queue semantics
backend/app/services/render/ffmpeg_helpers.py       # 564 lines — real FFmpeg execution layer + NVENC_SEMAPHORE
backend/app/services/render/legacy_renderer.py      # 491 lines — render_part() core + render_part_smart() wrapper
backend/app/services/render/clip_ops.py             # 401 lines — clip assembly operations
backend/app/services/subtitle_engine.py             # 46-line facade — real impl in services/subtitles/
backend/app/services/db.py                          # DB connection + WAL mode setup
backend/app/core/ui_gate.py                         # controls which UI is served
backend/app/main.py                                 # startup sequence + router mounts
backend/app/orchestration/asset_pipeline.py         # asset injection stage
backend/app/orchestration/render_events.py          # event error classification
backend/app/orchestration/groq_only_pipeline.py     # Groq-only pre-render path
backend/app/orchestration/parallel_analysis.py      # concurrent scene detect + Whisper threads
```

> ⚠️ CORRECTION — `render_engine.py` is 53 lines and is a thin facade. It is NOT the real FFmpeg execution layer.
> The genuinely dangerous files are `services/render/ffmpeg_helpers.py` (564 lines), `legacy_renderer.py` (491 lines), and `clip_ops.py` (401 lines).
> The NVENC semaphore lives at `services/render/ffmpeg_helpers.py:27-28` — NOT in `render_engine.py`.
> Any documentation or agent definition that lists `render_engine.py` as the primary FFmpeg risk file is protecting the wrong file.

### MEDIUM — Planner + focused pytest required

```
backend/app/routes/render.py                        # preserve validation, legacy coercion, resume/retry
backend/app/routes/jobs.py                          # preserve WS shape, polling, job history
backend/app/routes/editing.py
backend/app/services/tts_service.py
backend/app/services/audio_mix_service.py
backend/app/orchestration/audio_pipeline.py
backend/app/orchestration/pipeline_segment_selection.py  # segment selection, variant logic, CTA, output naming
backend/app/orchestration/pipeline_subtitle_utils.py     # subtitle utils used by render pipeline
backend/app/orchestration/pipeline_config.py             # render pipeline config helpers
backend/app/orchestration/pipeline_ranking.py            # output scoring and best-clip selection
backend/app/orchestration/pipeline_render_loop.py   # parallel part dispatch (ThreadPoolExecutor)
backend/app/services/scene_detector.py
backend/app/services/segment_builder.py             # clip boundary builder
```

### LOW — Edit freely, no planner required

```
backend/app/routes/voice.py
backend/app/routes/channels.py
backend/app/routes/feedback.py
backend/app/core/config.py                          # env vars and data paths only
backend/knowledge/**                                # add only — never delete existing entries
```

> Note: `routes/download.py` does NOT exist — downloader endpoints live at `backend/app/features/downloader/router.py`, loaded via shim `routes/platform_downloader.py`. Edits there are MEDIUM tier (preserve WS shape + job semantics).

---

## Critical Warnings

### ⛔ render_pipeline.py + part_renderer.py — Refactored Dual Monolith

`backend/app/orchestration/render_pipeline.py` (1,525 lines) is the main render orchestrator. It was refactored from a 5,816-line monolith — stage logic now lives in separate modules (`pipeline_render_loop.py`, `pipeline_segment_selection.py`, `pipeline_ranking.py`, `pipeline_cache.py`, `pipeline_config.py`, `pipeline_subtitle_utils.py`, `groq_only_pipeline.py`, `parallel_analysis.py`) and per-part rendering lives in `stages/part_renderer.py` (2,101 lines). Both files are CRITICAL tier. A change in either can silently affect all render paths.

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

### ⛔ AI modules — Distributed Across `backend/app/ai/**`

The legacy `ai/director/ai_director.py` monolith was removed in Phase G (RAG/AI Director retirement — see `main.py:238`). Current AI orchestration is distributed across:

- `backend/app/ai/analysis/` — hybrid analyzer + local/cloud providers (Groq, OpenAI)
- `backend/app/ai/analysis/groq/` — Groq-only pipeline client + prompts
- `backend/app/ai/llm/` — Claude / Gemini / OpenAI LLM providers
- `backend/app/ai/visibility/`, `ai/tracing.py`, `ai/diagnostics.py`, `ai/dependencies.py`

The AI safety rule still applies absolutely: any unhandled exception in `backend/app/ai/**` will kill an active render job. Every public entry point in every AI module MUST catch all exceptions and return `None`. Lazy-import optional deps (`torch`, `groq`, `openai`, `google-genai`) via try/except so missing AI extras never break startup.

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

**Location:** Semaphore defined at `backend/app/services/render/ffmpeg_helpers.py:27-28` (`NVENC_SEMAPHORE = threading.Semaphore(_NVENC_SEM_VALUE)`, default value 3, env override `NVENC_MAX_SESSIONS`). Acquired around every NVENC encode in `services/render/legacy_renderer.py:266`, `base_clip_renderer.py:92,224`, `overlay_compositor.py:133`. `services/render_engine.py` only re-exports the symbol — it is a 53-line facade and does NOT own the semaphore.

**What it does:** Limits the number of simultaneous NVENC GPU hardware encoder sessions.

**Why it must not be raised:** NVENC has a hardware-enforced session limit, typically 3–5 on consumer GPUs. When the limit is exceeded, NVIDIA does not gracefully fail the over-limit session — it fails ALL active sessions. Every render currently encoding fails simultaneously with a generic FFmpeg error that does not mention the NVENC limit as the cause.

**What breaks if raised beyond hardware limit:** All concurrent renders fail simultaneously with opaque FFmpeg errors. No warning before failure. Recovery requires restarting all affected jobs. The failure mode is non-obvious and hard to diagnose.

**Known gap (audit 2026-06-02):** The semaphore is acquired only at `base_clip_renderer.py:92` and `legacy_renderer.py:266`. Other FFmpeg call sites (`clip_ops.py`, `motion_crop.py`, `audio_mix_service.py`, `preview/ffmpeg_probers.py`) call FFmpeg without acquiring `NVENC_SEMAPHORE` — if any of those paths happen to invoke an NVENC codec, the limit can be silently exceeded. Future fix: centralize acquire/release inside `_run_ffmpeg_with_retry`, conditioned on argv containing `*_nvenc`.

**Rule:** Never change `NVENC_MAX_SESSIONS` without an explicit user request that includes documented reasoning and knowledge of the target hardware class.

### MAX_CONCURRENT_JOBS and MAX_RENDER_JOBS

**Location:** `backend/app/core/config.py` or `backend/app/services/job_manager.py`.

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

**Rule:** Never access `data/app.db` using a raw `sqlite3.connect()` call outside of `backend/app/db/` or `backend/app/services/db.py`. All database access must go through the established connection module.

**Why:** The connection module sets WAL mode, registers row factories, and manages thread-local connection state for the render thread. Bypassing it creates connections without WAL mode, without row factories, and in incompatible isolation levels — all of which corrupt the consistency guarantees the pipeline depends on.

### Known Issue — Mixed Connection Model (Do Not Worsen)

`upsert_job()` uses `get_conn()` — a new connection per call, manually closed.
`update_job_progress()` uses `_thread_conn()` — a thread-local persistent connection.

Both models coexist in `backend/app/services/db.py` and `backend/app/db/jobs_repo.py`. This is an inconsistency. Do not add new callers that introduce a third model. Do not silently switch one model to the other without a full audit of all callers and their transaction semantics. Unifying this is future architecture work requiring a dedicated plan.

---

## AI Module Rules

### Optional Dependencies in `requirements-ai.txt` Only

**Rule:** Any package that is optional for AI inference (PyTorch, transformers, CUDA bindings, ML model loaders) goes exclusively in `requirements-ai.txt`. Never add optional AI packages to `requirements.txt`.

**Why:** The system must install and run correctly for users who do not have GPU hardware, who have not installed the AI dependency set, or who are running in a reduced-capability mode. The base `requirements.txt` install must produce a working render system — AI features degrade gracefully, they do not block the installation.

### AI Modules Must Not Fail at Import Time

**Rule:** Every module under `backend/app/ai/**` must import successfully even when optional dependencies are absent. Use lazy imports with availability flags.

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

This is repeated here as implementation guidance. Every method in every `backend/app/ai/**` module:

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

`docs/review/**` is an append-only audit ledger. It records architectural findings, decisions, and audits over the lifetime of the project. It is READ-ONLY for all agents.

### Correct Process for New Findings

1. Create a **new** file: `docs/review/TOPIC_YYYY-MM-DD.md`
2. If the finding relates to a prior finding, reference the prior file by filename in the new file body
3. Explain what changed, what was found, and why in the new file
4. Never edit any existing file in `docs/review/`
5. Never delete any file in `docs/review/`

`docs/archive/**` follows identical rules — read-only, append-only, never edit existing files.

**Why:** `docs/review/` is the audit history of architectural knowledge at specific points in time. Editing existing files rewrites history. Future auditors must be able to read what was known at each point in time and trace what changed. Mutating historical records destroys the audit trail.

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
python -m py_compile app\orchestration\render_pipeline.py

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
git add backend/app/routes/render.py
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
motion_crop.py mentioned        → CRITICAL tier → same as render_pipeline.py
backend/app/ai/** mentioned     → HIGH tier → AI safety rule (return None, never raise) is absolute
qa_pipeline.py mentioned        → CRITICAL tier → never bypass contract is absolute
schemas.py field change         → HIGH tier → additive-only verification first
API route path mentioned        → HIGH tier → check Frozen API Contracts section first
database schema mentioned       → HIGH tier → additive-only rule applies
NVENC or MAX_* constants        → HIGH tier → Performance Protections section applies
devtools.py mentioned           → HIGH tier → security danger, explicit approval required
routes/*.py edit                → MEDIUM tier → Planner + focused pytest
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
| Any AI module under `backend/app/ai/**` can `raise` instead of `return None` | Pipeline crash on any failure |
| `qa_pipeline.py` validation bypassed, caught, or threshold lowered | Corrupt renders delivered as success |
| `git add .`, `git add *`, or `git add -A` proposed | Stages unreviewed or sensitive files |
| Stage or part transition name changed without documented WS consumer audit | Silent UI breakage |

**Review Checklist (all must pass before PASS verdict):**

- [ ] API payload and response fields preserved — additive changes only, no removals
- [ ] `RenderRequest` new fields default to `False` or disabled equivalent
- [ ] Job stage names unchanged: `QUEUED → DOWNLOADING → RENDERING → DONE`
- [ ] Job part names unchanged: `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE`
- [ ] WebSocket event shape preserved: top-level `job`, `parts[]`, `summary` all present
- [ ] HTTP polling fallback still functional — no progress data made WebSocket-exclusive
- [ ] `result_json` parseable by consumers: `output_rank_score`, `is_best_output`, `is_best_clip` present
- [ ] Output validation still catches: missing file, file too small, no video stream, no audio stream, zero duration
- [ ] Subtitle and voice code paths no-op cleanly when those features are disabled
- [ ] AI module changes bounded: no import-time failures on missing optional deps, no unhandled raises
- [ ] Any behavior or specification change is reflected in a new `docs/review/` file

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

### Issue 2 — Mixed DB Connection Model

`upsert_job()` calls `get_conn()` (new connection + manual close per call).
`update_job_progress()` calls `_thread_conn()` (thread-local persistent connection).
Both exist in the same module. Do not add callers of a third model.
Unifying these is future architectural work — requires a dedicated plan and full caller audit.

### Issue 3 — Cache Location (PARTIALLY RESOLVED 2026-06-02)

Cache root has been moved to `APP_DATA_DIR/cache` (see `pipeline_cache.py:29,45,59,77,86,99` and `services/motion_crop.py:26,41`). The `POST /api/render/cache/clear` endpoint targets the new path.

**Remaining gap:** `services/maintenance.py` still does NOT prune `APP_DATA_DIR/cache`. TTL (`_RENDER_CACHE_TTL_SEC = 72h`) is only enforced lazily on `_cache_get` reads — caches for sources never re-accessed accumulate forever. Fix: add a `prune_render_cache(cache_dir, max_age_hours=72)` call into the existing maintenance scheduler.

### Issue 4 — Remaining God Files

`render_pipeline.py` is now 1,525 lines (was 5,816 before Phase A-F refactors). `stages/part_renderer.py` is 2,101 lines. `services/motion_crop.py` is 2,512 lines. All three must be treated with full-pytest caution on every change.

`ai/director/ai_director.py` was removed in Phase G — no longer applicable.

Further decomposition of `render_pipeline.py`, `part_renderer.py`, or `motion_crop.py` is future architecture work — requires a dedicated multi-phase plan. Do not start decomposition without an approved plan. Do not make partial decompositions.

### Issue 5 — render_engine.py Is a Facade (Documentation Drift)

`render_engine.py` is 53 lines — a thin dispatch facade. It is NOT the real FFmpeg execution layer.
The dangerous files are `services/render/ffmpeg_helpers.py`, `services/render/legacy_renderer.py`, `services/render/clip_ops.py`.
Any legacy documentation listing `render_engine.py` as CRITICAL is protecting the wrong file.
The real FFmpeg files carry HIGH blast radius and must be treated accordingly.
