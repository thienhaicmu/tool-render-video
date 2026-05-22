# PHASE_4H_ROUTE_CLEANUP_PLAN.md

**Planning document for routes/render.py cleanup.**
**Status**: IN PROGRESS — Phase 4H.1 + 4H.2 shipped (2026-05-22); Phase 4H.3–4H.5 pending.
**Created**: 2026-05-22

---

## 1. Current `routes/render.py` State

**File**: `backend/app/routes/render.py`
**Line count**: ~1,369 lines (post Phase 4F upload removal; no render routes deleted)
**Prefix**: `APIRouter(prefix="/api/render")`

The file mixes at least 9 distinct responsibility clusters: preview session state management, source preparation, preview video/transcript endpoints, render job lifecycle control, batch orchestration, media streaming, one-shot quick process, route-local FFmpeg helpers, and module-level mutable state. No cluster has been extracted to a service module. Every concern has grown in-place over the project's lifetime.

The file is not a god-file-scale problem (1,369 lines vs. `render_pipeline.py`'s 5,510+), but it is the next-largest file in the routes layer and contains non-route logic that has no business being in a route module.

**Known coupling constraints discovered during audit (see §14)**:
- `evict_stale_preview_sessions()` is called from `main.py` — any extraction must keep this symbol importable from the new location or update `main.py`.
- `process_render()` passes `_load_session` and `_cleanup_preview_session` as function references to `run_render_pipeline()` — preview session is coupled to the render pipeline signature.
- `_run_batch()` is an inner closure capturing `batch_id, child_job_ids, urls, effective_channel, payload` — tight coupling makes batch extraction harder.

---

## 2. Cluster A — Preview Session State/Service

**Type**: State management + helper functions  
**Where in file**: Top of module, lines ~50–180

**Functions**:
| Function | Signature | What it does |
|---|---|---|
| `_save_session` | `(session_id: str, data: dict) -> None` | Serializes session dict to JSON file on disk |
| `_load_session` | `(session_id: str) -> dict \| None` | Deserializes session JSON from disk; returns None if missing |
| `_cleanup_preview_session` | `(session_id: str) -> None` | Deletes session JSON + associated preview directory |
| `evict_stale_preview_sessions` | `() -> None` | Scans in-memory registry, evicts sessions older than `_SESSION_TTL_HOURS`; **called from main.py** |

**Module-level state owned by Cluster A** (see §10 for full inventory):
- `_PREVIEW_SESSIONS: dict[str, dict]` — in-memory registry of active sessions
- `_PREVIEW_DIR: Path` — base directory for preview temp files
- `_SESSION_TTL_HOURS: int = 6`
- `_MAX_PREVIEW_SESSIONS: int = 200`

**Coupling**: `_load_session` and `_cleanup_preview_session` are passed as function references to `run_render_pipeline()` from `process_render()` in Cluster D. Extraction to a service must preserve function-reference passability (or change the pipeline signature — out of Phase 4H scope).

**Extraction target**: `backend/app/services/preview/session_service.py`

---

## 3. Cluster B — Source Preparation

**Type**: Routes + download orchestration  
**Where in file**: ~lines 180–450

**Routes**:
| Method | Path | Handler | Description |
|---|---|---|---|
| POST | `/prepare-source` | `prepare_source` | Download or validate source video; create preview session; start transcription; return `session_id` |
| DELETE | `/prepare-source/{session_id}` | `cancel_prepare_source` | Signal cancel event for in-progress download; cleanup session |

**Module-level state owned by Cluster B**:
- `_ACTIVE_DOWNLOADS: dict[str, threading.Event]` — cancel events for active downloads, keyed by `session_id`

**Key internal behavior**:
- `prepare_source` calls `_validate_render_source()` (Cluster H), `_ensure_h264_preview()` (Cluster H), and `_save_session()` (Cluster A)
- Download uses `yt-dlp` via `download_youtube()` — cancel event stored in `_ACTIVE_DOWNLOADS`
- Session data written includes source path, transcript, preview profile metadata

**Extraction target**: Route handlers stay in `routes/render.py`; download/prepare logic may be extracted to `services/preview/source_prep.py` in a future sub-phase.

---

## 4. Cluster C — Preview Endpoints

**Type**: Read-only routes  
**Where in file**: ~lines 450–570

**Routes**:
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | `/preview/{session_id}/video` | `preview_video` | Stream preview video from `_PREVIEW_DIR`; uses Cluster H `_is_browser_safe_preview` |
| GET | `/preview/{session_id}/transcript` | `preview_transcript` | Return transcript from loaded session dict |

**Dependencies**: Both handlers call `_load_session()` (Cluster A). `preview_video` calls `_is_browser_safe_preview()` (Cluster H) and returns a `FileResponse`.

**Extraction target**: Routes stay in `routes/render.py`. No service extraction needed for these two thin handlers.

---

## 5. Cluster D — Render Job Control

**Type**: Routes + internal orchestration helpers  
**Where in file**: ~lines 570–1255

**Routes**:
| Method | Path | Handler | Description |
|---|---|---|---|
| POST | `/process` | `create_render_job` | Main render entry point; calls `process_render()` |
| POST | `/resume/{job_id}` | `resume_render_job` | Resume an interrupted job; re-queues via `job_manager` |
| POST | `/retry/{job_id}` | `retry_failed_parts` | Retry failed parts; re-queues via `job_manager` |
| POST | `/{job_id}/cancel` | `cancel_render_job` | Signal cancel; calls `cancel_registry.request_cancel()` |
| GET | `/jobs/{job_id}` | `get_render_job` | Return job row from DB |

**Internal helpers** (not routes):
| Function | Role |
|---|---|
| `process_render(session_id, payload, bg_tasks, request)` | Session validation, payload coercion, source resolution, calls `_queue_render_job` |
| `_queue_render_job(payload, source_path, job_id, bg_tasks)` | Calls `job_manager.submit_job(run_render_pipeline, ...)` |

**Key coupling**:
- `process_render()` passes `_load_session` and `_cleanup_preview_session` as fn args to `run_render_pipeline()` — preview session lifecycle is coupled to render pipeline callback signature
- `create_render_job` calls `process_render()` which is inlined (not a route handler itself)

**Extraction target**: Route handlers stay in `routes/render.py`. `process_render()` and `_queue_render_job()` could move to a service layer in a later sub-phase, but the callback coupling complicates this.

---

## 6. Cluster E — Batch Orchestration

**Type**: Route + inner closure  
**Where in file**: ~lines 850–1050

**Routes**:
| Method | Path | Handler | Description |
|---|---|---|---|
| POST | `/process/batch` | `create_render_batch` | Create batch; spawn background thread running `_run_batch()` |

**`_run_batch()` closure** (defined inside `create_render_batch`):
- Captures: `batch_id`, `child_job_ids`, `urls`, `effective_channel`, `payload`
- Runs in a bare `threading.Thread` (outside `job_manager`)
- 7200s blocking wait per child job (`job.join(timeout=7200)`)
- No batch-level cancel event
- No batch-level resume after crash

**Known debt** (documented in BRUTAL_REVIEW_SUMMARY.md §Under-Engineered):
- No batch-level progress UI
- No batch-level cancel — individual child cancels work, but batch thread cannot be stopped
- No batch resume if server restarts mid-batch
- The `_run_batch()` inner closure captures 5 variables, making it harder to extract to a standalone service

**Extraction target**: `_run_batch()` logic could move to `services/render/batch_service.py` but requires closure → explicit args refactor. This is Phase 4H.4 scope.

---

## 7. Cluster F — Media Streaming

**Type**: Routes — self-contained  
**Where in file**: ~lines 1256–1369

**Routes**:
| Method | Path | Handler | Description |
|---|---|---|---|
| GET | `/jobs/{job_id}/parts/{part_no}/media` | `stream_render_part_media` | HTTP Range-aware streaming; path resolved from DB (no path traversal) |
| GET | `/jobs/{job_id}/parts/{part_no}/thumbnail` | `get_render_part_thumbnail` | JPEG thumbnail via `extract_thumbnail_frame`; path from DB; 24h browser cache |

**Security note** (per existing docstrings): File paths are resolved from `job_parts` DB records, never from user-supplied input. No path-traversal risk.

**Dependencies**:
- `stream_render_part_media`: `list_job_parts()` (DB), `re.match()` (stdlib), `StreamingResponse` (FastAPI)
- `get_render_part_thumbnail`: `list_job_parts()` (DB), `extract_thumbnail_frame()` (from `render_engine` shim)

**Note**: `get_render_part_thumbnail` imports `from app.services.render_engine import extract_thumbnail_frame` — a deferred import at function body. This routes through the `render_engine` shim. Phase 4H does NOT change this import — shim is stable.

**Extraction target**: Both routes stay in `routes/render.py`. They are thin (30–40 lines each), self-contained, and have no internal state. No extraction needed.

---

## 8. Cluster G — Quick Process

**Type**: Route — one-shot render  
**Where in file**: ~lines 1100–1200

**Route**:
| Method | Path | Handler | Description |
|---|---|---|---|
| POST | `/quick-process` | `quick_process` | One-shot render with no preview session; validates source, queues job, returns `job_id` |

**Key difference from Cluster D**: `quick_process` does NOT create a preview session. It validates the source directly, coerces the payload via `_coerce_legacy_channel_payload()` (Cluster H), and queues via `_queue_render_job()` (Cluster D helper).

**Extraction target**: Route stays in `routes/render.py`. No extraction needed.

---

## 9. Cluster H — Route-Local Helpers

**Type**: Module-level helper functions (not routes)  
**Where in file**: Scattered — defined near first use

**Functions**:
| Function | Signature | Used by |
|---|---|---|
| `_emit_request_event` | `(event_type: str, payload: dict) -> None` | D (`process_render`) |
| `_validate_output_dir` | `(output_dir: str) -> Path` | D, G |
| `_coerce_legacy_channel_payload` | `(payload: dict) -> dict` | D, G |
| `_validate_render_source` | `(session: dict, payload: dict) -> tuple` | D |
| `_probe_video_codec` | `(path: str) -> str` | B |
| `_probe_preview_profile` | `(path: str) -> dict` | B |
| `_is_browser_safe_preview` | `(codec: str, audio_codec: str) -> bool` | B, C |
| `_ensure_h264_preview` | `(source_path: str, dest_path: str) -> None` | B |
| `_run_ffmpeg_checked` | `(cmd: list, desc: str) -> None` | H helpers |
| `_detect_leading_black_duration` | `(path: str) -> float` | B |
| `upload_local_video` | POST `/upload-local` | standalone |
| `download_health` | POST `/download-health` | standalone |

**FFmpeg probe subset** (`_probe_video_codec`, `_probe_preview_profile`, `_is_browser_safe_preview`, `_ensure_h264_preview`, `_run_ffmpeg_checked`, `_detect_leading_black_duration`): These 6 functions are route-local FFmpeg helpers with no dependencies on session state. They depend only on `bin_paths.get_ffmpeg_bin()` and stdlib. They are the cleanest extraction candidate.

**Extraction target for FFmpeg probe helpers**: `backend/app/services/preview/ffmpeg_probers.py`  
**Extraction target for payload/validation helpers**: May stay in `routes/render.py` or move to a shared util — lower priority.

---

## 10. Cluster I — Module-Level State Inventory

All module-level mutable state in `routes/render.py`:

| Variable | Type | Owner Cluster | Description |
|---|---|---|---|
| `_PREVIEW_SESSIONS` | `dict[str, dict]` | A | In-memory session registry; keyed by `session_id` (UUID) |
| `_ACTIVE_DOWNLOADS` | `dict[str, threading.Event]` | B | Cancel events for active yt-dlp downloads; keyed by `session_id` |
| `_PREVIEW_DIR` | `Path` | A | Base directory for preview temp files; set from `tempfile.mkdtemp()` at import time |
| `_SESSION_TTL_HOURS` | `int = 6` | A | Session expiry constant |
| `_MAX_PREVIEW_SESSIONS` | `int = 200` | A | Max concurrent session limit |
| `_UUID_RE` | `re.Pattern` | A | UUID validation regex (used in session_id validation) |

**State ownership rules**:
- `_PREVIEW_SESSIONS` and `_PREVIEW_DIR` are tightly coupled — both must live in the same module to avoid cross-module state aliasing
- `_ACTIVE_DOWNLOADS` is used ONLY in Cluster B (`prepare_source` + `cancel_prepare_source`) — could travel with those functions
- If Cluster A is extracted to `services/preview/session_service.py`, all 4 A-owned variables must move with it

---

## 11. Target Module Tree

After all planned sub-phases complete:

```
backend/app/
├── routes/
│   └── render.py                        (slimmed — route definitions only, ~500–700 lines target)
├── services/
│   ├── preview/
│   │   ├── __init__.py
│   │   ├── session_service.py           (Cluster A: _save_session, _load_session,
│   │   │                                  _cleanup_preview_session, evict_stale_preview_sessions,
│   │   │                                  _PREVIEW_SESSIONS, _PREVIEW_DIR, _SESSION_TTL_HOURS,
│   │   │                                  _MAX_PREVIEW_SESSIONS, _UUID_RE)
│   │   └── ffmpeg_probers.py            (Cluster H FFmpeg subset: _probe_video_codec,
│   │                                      _probe_preview_profile, _is_browser_safe_preview,
│   │                                      _ensure_h264_preview, _run_ffmpeg_checked,
│   │                                      _detect_leading_black_duration)
│   └── render/
│       └── batch_service.py             (Cluster E: _run_batch logic extracted from closure)
```

**NOT extracted** (stay in `routes/render.py`):
- All route handler functions (Clusters B, C, D, F, G)
- Cluster H payload/validation helpers (`_emit_request_event`, `_validate_output_dir`, `_coerce_legacy_channel_payload`, `_validate_render_source`)
- `upload_local_video`, `download_health` endpoints
- `process_render()`, `_queue_render_job()` internal orchestration helpers

**Backward-compat re-exports**: `routes/render.py` re-exports `evict_stale_preview_sessions` from `services/preview/session_service.py` so that `main.py`'s existing import continues to work with zero changes.

---

## 12. Sub-Phase Ordering Rationale

Extraction order is bottom-up (dependencies before dependents):

| Sub-phase | Target | Rationale |
|---|---|---|
| **4H.1** | Extract `services/preview/ffmpeg_probers.py` (Cluster H FFmpeg subset) | No deps on session state; pure FFmpeg helpers; lowest risk; enables clean extraction of Cluster A next |
| **4H.2** | Extract `services/preview/session_service.py` (Cluster A + owned module state) | Depends on no other extracted module; once out, Cluster B/C can import from service |
| **4H.3** | Extract `services/render/batch_service.py` (Cluster E `_run_batch` logic) | Independent of preview session; closure → explicit args refactor contained to 2 functions |
| **4H.4** | Route thinning pass (Clusters B/C/D imports updated to use new services) | After 4H.1 and 4H.2 ship; `routes/render.py` call sites updated to import from new modules |
| **4H.5** | Audit + freeze (no code changes) | Verify no circular imports; update all docs; baseline test count |

**Why Cluster D (render job control) is NOT extracted**: `process_render()` passes `_load_session` and `_cleanup_preview_session` as function-reference args to `run_render_pipeline()`. Extracting these to a service without changing the pipeline's callback signature is complex and risky. The render pipeline signature change is out of Phase 4H scope. Cluster D routes are thin enough as-is; they can remain in `routes/render.py`.

**Why Cluster F (media streaming) is NOT extracted**: Both endpoints are under 40 lines each. They are purely data retrieval + streaming with no state. The `extract_thumbnail_frame` import routes through the `render_engine` shim (which is frozen). No complexity to extract here.

---

## 13. API Invariants — Routes Must Not Change

The following API surface is frozen. No sub-phase may change any route path, method, request body shape, or response shape.

| Method | Path | Frozen contract |
|---|---|---|
| POST | `/api/render/prepare-source` | Returns `{session_id: str, ...}` |
| DELETE | `/api/render/prepare-source/{session_id}` | Returns `{cancelled: bool}` |
| GET | `/api/render/preview/{session_id}/video` | Returns `FileResponse` (video/mp4) |
| GET | `/api/render/preview/{session_id}/transcript` | Returns transcript dict |
| POST | `/api/render/process` | Returns `{job_id: str, ...}` |
| POST | `/api/render/process/batch` | Returns `{batch_id: str, job_ids: [...]}` |
| POST | `/api/render/resume/{job_id}` | Returns `{job_id: str, status: str}` |
| POST | `/api/render/retry/{job_id}` | Returns `{job_id: str, ...}` |
| POST | `/api/render/{job_id}/cancel` | Returns `{job_id: str, status: "cancelling"}` |
| GET | `/api/render/jobs/{job_id}` | Returns job row dict |
| GET | `/api/render/jobs/{job_id}/parts/{part_no}/media` | Returns `StreamingResponse` (video/mp4, Range-aware) |
| GET | `/api/render/jobs/{job_id}/parts/{part_no}/thumbnail` | Returns `Response` (image/jpeg) |
| POST | `/api/render/quick-process` | Returns `{job_id: str, ...}` |
| POST | `/api/render/upload-local` | Returns upload result |
| POST | `/api/render/download-health` | Returns health dict |

**The frontend JavaScript calls these URLs by hardcoded string.** Any path change breaks the frontend without a coordinated JS update.

---

## 14. Key Coupling Constraints

These are the hard dependencies that make extraction non-trivial:

### C1 — `evict_stale_preview_sessions` called from `main.py`
`backend/app/main.py` calls `from app.routes.render import evict_stale_preview_sessions` and schedules it via `BackgroundTasks` or startup hook. If this function moves to `services/preview/session_service.py`:
- `routes/render.py` must re-export it: `from app.services.preview.session_service import evict_stale_preview_sessions`
- OR `main.py` must be updated to import from the new location
- **Plan**: re-export at old location; `main.py` unchanged.

### C2 — `_load_session` / `_cleanup_preview_session` passed as callbacks to `run_render_pipeline`
In `process_render()`:
```python
run_render_pipeline(
    ...,
    load_session_fn=_load_session,
    cleanup_session_fn=_cleanup_preview_session,
)
```
If these functions move to `session_service.py`, `routes/render.py` must import them and pass them by reference. The `run_render_pipeline()` signature does NOT change. The callback contract is preserved as long as both functions remain callable with the same signature.

### C3 — `_run_batch()` is an inner closure
`_run_batch()` is defined inside `create_render_batch()` and captures `batch_id`, `child_job_ids`, `urls`, `effective_channel`, `payload` from the enclosing scope. Extraction to `batch_service.py` requires converting these captured variables to explicit function parameters. The logic itself is self-contained.

### C4 — `_ACTIVE_DOWNLOADS` state shared between `prepare_source` and `cancel_prepare_source`
Both handlers read/write `_ACTIVE_DOWNLOADS`. If session_service is extracted without `_ACTIVE_DOWNLOADS`, these two handlers would still need access to the dict. Options:
- Move `_ACTIVE_DOWNLOADS` to `session_service.py` alongside other session state
- Keep `_ACTIVE_DOWNLOADS` in `routes/render.py` (download-specific, not session-specific)
- **Plan**: keep `_ACTIVE_DOWNLOADS` in `routes/render.py` — it belongs to download lifecycle, not session lifecycle.

### C5 — `_probe_video_codec` / `_probe_preview_profile` call `_run_ffmpeg_checked`
The FFmpeg probe helpers depend on `_run_ffmpeg_checked`. All 6 FFmpeg probe functions travel together to `ffmpeg_probers.py` — no split within the subset.

---

## 15. Migration Risk Matrix

| Sub-phase | Risk | Mitigation |
|---|---|---|
| 4H.1 (ffmpeg_probers) | Low — pure functions, no state | Same-object identity tests; no callers outside `routes/render.py` |
| 4H.2 (session_service) | Medium — module-level dict state | Verify `_PREVIEW_SESSIONS` singleton: only ONE instance in process; test `evict` via re-export; verify `main.py` caller unchanged |
| 4H.3 (batch_service) | Medium — closure → explicit args | Test batch job creation; no batch cancel test currently exists |
| 4H.4 (route thinning) | Low — import updates only | No behavior change; grep all callers before and after |
| 4H.5 (audit + freeze) | None — docs only | Circular import check; test baseline count |

**Highest risk point**: Extracting `_PREVIEW_SESSIONS` (a module-level dict). If `routes/render.py` keeps a separate binding (e.g. `from session_service import _PREVIEW_SESSIONS` creates an alias, not the same dict), the session eviction loop and the session load/save functions would operate on different dicts. This MUST be prevented — all session state access must go through the module that owns the dict.

---

## 16. Test Strategy

### 4H.1 (ffmpeg_probers)
- `test_preview_ffmpeg_probers.py`
- Import identity: `routes.render._probe_video_codec is preview.ffmpeg_probers._probe_video_codec` (same-object after re-export)
- `_is_browser_safe_preview()` unit tests: (h264,aac)→True, (vp9,opus)→False, (hevc,aac)→False
- `_run_ffmpeg_checked()` raises on non-zero exit, passes on zero
- `_detect_leading_black_duration()` returns float ≥ 0.0

### 4H.2 (session_service)
- `test_preview_session_service.py`
- `_save_session` / `_load_session` roundtrip
- `_load_session` returns None for missing session
- `_cleanup_preview_session` deletes file; safe on already-missing
- `evict_stale_preview_sessions` removes sessions older than TTL; keeps recent sessions
- `evict_stale_preview_sessions` importable from `routes.render` (re-export contract)
- Module-level state singleton: only one `_PREVIEW_SESSIONS` dict in process

### 4H.3 (batch_service)
- `test_render_batch_service.py`
- `_run_batch` logic with mocked `run_render_pipeline` and `job_manager`
- Batch completes when all child jobs finish
- Child job IDs correct count

### General
- After each sub-phase: run full test suite, confirm pre-existing 8-failure baseline is unchanged
- No new failures introduced

---

## 17. Feature Flag Impact

Phase 4H does not touch `render_pipeline.py`, `render_engine.py`, or any module controlled by:
- `FEATURE_BASE_CLIP_FIRST`
- `FEATURE_OVERLAY_AFTER_BASE_CLIP`

No render behavior changes in any sub-phase. Feature flags are unaffected.

---

## 18. Rollback Strategy

Each sub-phase is an independent extraction. Rollback procedure if a sub-phase introduces a regression:

1. `git revert <commit>` — single commit per sub-phase
2. Run test suite to confirm baseline restored
3. Document reason for revert in MIGRATION_HISTORY.md

**4H.2 rollback risk**: If `_PREVIEW_SESSIONS` aliasing bug occurs (two dict instances), sessions will appear empty after `evict_stale_preview_sessions` runs. Symptom: all active sessions evicted on next call. Diagnosis: check `id(_PREVIEW_SESSIONS)` in both modules. Fix: ensure all code reaches the dict through the owning module.

---

## 19. Open Questions

1. **Should `_ACTIVE_DOWNLOADS` move to `session_service.py`?**
   - It is download-lifecycle state, not session-lifecycle state.
   - Current plan: keep in `routes/render.py`. This leaves one download-specific dict in the route module, which is acceptable.
   - If `prepare_source` is ever extracted to a service, `_ACTIVE_DOWNLOADS` should travel with it.

2. **Should `process_render()` / `_queue_render_job()` be extracted?**
   - These are orchestration helpers currently inlined in the route module.
   - Extraction requires understanding the `_load_session`/`_cleanup_preview_session` callback contract.
   - **Current plan**: out of Phase 4H scope. Leave in `routes/render.py` for now.

3. **Should Cluster F (`stream_render_part_media`, `get_render_part_thumbnail`) move to a separate router?**
   - Both are read-only media endpoints with no state dependency.
   - A `routes/render_media.py` could separate media serving from job management.
   - **Current plan**: out of Phase 4H scope. The gain does not justify the routing change risk.

4. **Is the `_run_batch()` bare-thread approach worth fixing in Phase 4H?**
   - The batch's use of a bare `threading.Thread` with a 7200s blocking wait is documented debt (BRUTAL_REVIEW_SUMMARY.md §Under-Engineered).
   - **Current plan**: Phase 4H.3 extracts the closure to `batch_service.py` without changing the threading model. The threading debt is separate work.

---

## 20. Definition of Done

Phase 4H is complete when ALL of the following are true:

- [ ] `services/preview/__init__.py` exists (empty)
- [ ] `services/preview/ffmpeg_probers.py` exists with the 6 FFmpeg probe helpers (Phase 4H.1)
- [ ] `services/preview/session_service.py` exists with all 4 Cluster A functions + 4 owned state variables (Phase 4H.2)
- [ ] `services/render/batch_service.py` exists with `_run_batch` logic converted from closure to explicit args (Phase 4H.3)
- [ ] `routes/render.py` re-exports `evict_stale_preview_sessions` from `session_service.py` so `main.py` import is unchanged (Phase 4H.2)
- [ ] `routes/render.py` re-exports all moved Cluster H FFmpeg helpers (Phase 4H.1)
- [ ] All API paths/methods/response shapes are unchanged (verified by manual contract check)
- [ ] `main.py` caller of `evict_stale_preview_sessions` is unchanged (import path unchanged)
- [ ] No circular imports (`ffmpeg_probers` → no route imports; `session_service` → no route imports)
- [ ] Test suite passes at or above Phase 4G.7 baseline: `8 failed, 6593+ passed, 1 skipped`
- [ ] New tests exist for `ffmpeg_probers.py` (Phase 4H.1) and `session_service.py` (Phase 4H.2)
- [ ] `docs/restructure/MIGRATION_HISTORY.md` — Phase 4H.0–4H.5 entries added
- [ ] `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` — `services/preview/` block added
- [ ] `docs/review/TECHNICAL_DEBT_REPORT.md` — `routes/render.py` entry added under HIGH
- [ ] `docs/review/BRUTAL_REVIEW_SUMMARY.md` — current priority list updated
