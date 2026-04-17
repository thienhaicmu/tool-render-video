# Render Studio — System Definition for AI Tools

This document is the authoritative context file for AI tools (Claude, Copilot, etc.) working in this repository. Read this before making any code changes.

---

## What This System Does

Render Studio is a local desktop application that:
1. Takes a YouTube URL or local video file
2. Detects scene boundaries and builds short-form video segments
3. Scores segments by viral potential
4. Renders the top-N segments with subtitles, motion-aware crop, color grading, and text overlays
5. Optionally uploads finished videos to TikTok

Everything runs on the local machine. No cloud API is required except optional Ollama for captions.

---

## Architecture (V2 — current)

Three-layer model with strict dependency direction:

```
routes/  →  orchestration/  →  services/  →  core/
```

| Layer | Location | Role |
|---|---|---|
| HTTP | `backend/app/routes/` | Validate input, queue jobs, respond. No pipeline logic. |
| Orchestration | `backend/app/orchestration/render_pipeline.py` | All render pipeline steps. `run_render_pipeline()` |
| Services | `backend/app/services/` | Single-domain logic: download, render, subtitle, score, upload |
| Core | `backend/app/core/` | Config (paths) + Stage enums |

**Critical rule:** All render pipeline logic lives in `orchestration/render_pipeline.py`. `routes/render.py` is an HTTP boundary. Do not add pipeline logic to routes.

---

## Key Files

| File | Role |
|---|---|
| `backend/app/main.py` | FastAPI app, startup hooks, log filters |
| `backend/app/core/config.py` | All runtime paths resolved from env vars |
| `backend/app/core/stage.py` | `JobStage`, `JobPartStage`, `STAGE_TO_EVENT` enums |
| `backend/app/models/schemas.py` | Pydantic models for all API requests |
| `backend/app/orchestration/render_pipeline.py` | `run_render_pipeline()` — the entire render pipeline |
| `backend/app/routes/render.py` | HTTP wrapper + session management for editor flow |
| `backend/app/services/text_overlay.py` | `VALID_FONTS`, `normalize_text_layers`, drawtext filter builder |
| `backend/app/services/downloader.py` | yt-dlp with multi-client retry fallback |
| `backend/app/services/render_engine.py` | ffmpeg cut + encode + NVENC/CPU fallback |
| `backend/app/services/job_manager.py` | In-process job queue with restart recovery |
| `backend/app/services/db.py` | SQLite for jobs, job_parts, channels |
| `backend/static/index.html` | Entire frontend (single file) |

---

## Editor → Render Flow (Most Complex Workflow)

This is where most bugs and misunderstandings occur. Read carefully.

### Step 1: Prepare source
```
POST /api/render/prepare-source
→ downloads or validates the source
→ creates session at data/temp/preview/{session_id}/
→ returns { session_id, title, duration, export_dir }
```

### Step 2: Editor UI
- Frontend stores `sessionId` and `exportDir` in `_ev`
- User configures trim, subtitle, text layers
- `edit_session_id` is set on the payload before submit

### Step 3: Submit render
```
POST /api/render/process (with edit_session_id set)
→ _validate_render_source: only validates output_dir; skips source_mode/URL validation
→ pipeline: load_session_fn(edit_session_id) → use sess["video_path"] → no download
```

### Session missing behavior
If `edit_session_id` is set but the session cannot be found:
- `run_render_pipeline` raises `RuntimeError` immediately
- Job fails with: "Editor session not found — please re-open the editor"
- **Never** silently re-downloads. This is a hard rule.

### Output dir for editor flow
```
1. Use payload.output_dir (from main form) if non-empty
2. Else use _ev.exportDir (= data/temp/preview/{session_id}/exports)
3. Else show error, abort
4. Append /video_output if leaf not already "video_output" or "video_out"
5. Force output_mode='manual', channel_code='', render_output_subdir=''
```

For full details see [editor-flow.md](../doc/editor-flow.md).

---

## Error Classification

| Type | Source | Log |
|---|---|---|
| Type 1 — Request | HTTPException before pipeline | `data/logs/request.log` + `desktop-backend.log` |
| Type 2 — Pipeline | Exception inside `run_render_pipeline` | `data/logs/error.log` + `data/logs/app.log` + `channels/{code}/logs/{job_id}.log` |
| Type 3 — System | Unhandled route exception | `desktop-backend.log` |

```
UI shows "Start render failed"  →  data/logs/request.log  (Type 1)
Job status = "failed"           →  data/logs/error.log    (Type 2)
Server 500 with no job created  →  desktop-backend.log    (Type 3)
```

---

## text_layers Contract

- Max 8 layers per job
- `font_family` must be in `VALID_FONTS` (14 values in `text_overlay.py`)
- `outline`, `shadow`, `background` must be objects (not flat values)
- Frontend normalizers `_toOutline`/`_toShadow`/`_toBg` ensure this before submission
- `evTxtFont` UI options must always match `VALID_FONTS` (currently 12 of 14)
- `x_percent` and `y_percent` are the authoritative position fields — never remove or simplify them

---

## Stage System

All pipeline stage transitions use `JobStage` from `core/stage.py`:

```
queued → starting → downloading → scene_detection → segment_building
      → transcribing_full → rendering / rendering_parallel → writing_report → done
                                                                            → failed
```

`STAGE_TO_EVENT` maps each stage to a structured event name for log emission.

---

## Logging

Three log files are written during normal operation:
- `data/logs/request.log` — Type 1 validation rejections
- `data/logs/app.log` — all pipeline events (JSON lines)
- `data/logs/error.log` — ERROR/CRITICAL only

Two uvicorn log filters are active:
- `_SuppressNoisyAccessFilter` on `uvicorn.access` — drops `/api/jobs/` and `/health` polling
- `_SuppressClientDisconnect` on `uvicorn.error` — drops harmless video disconnect messages

---

## What Is Stable vs. Fragile

**Stable (safe to rely on):**
- SQLite job/part persistence
- Channel folder structure
- `run_render_pipeline` callback interface
- `VALID_FONTS` set
- Session in-memory + disk fallback

**Fragile (external dependencies):**
- YouTube format availability (yt-dlp fallback list may need updating)
- TikTok upload UI selectors (Playwright selectors drift)
- NVENC availability (depends on GPU driver state)

---

## Rules AI Tools Must Follow

1. **No pipeline logic in routes.** `routes/render.py` is HTTP-only. Pipeline logic → `orchestration/render_pipeline.py`.
2. **Session check before source_mode dispatch.** Check `edit_session_id` first in the pipeline; dispatch to download only if no session.
3. **Never silent re-download.** If `edit_session_id` is set and session is missing, raise — do not fall back to downloading.
4. **Do not break x/y positioning.** `x_percent` and `y_percent` in text layers are exact. Do not simplify or remove them.
5. **Session callbacks are parameters, not imports.** `load_session_fn` and `cleanup_session_fn` are passed to `run_render_pipeline`. `orchestration/` must not import from `routes/`.
6. **Smallest correct change.** Do not refactor code adjacent to the task. Do not add features not requested.
7. **Verify after changes.** Run `python -c "from app.routes.render import router; from app.orchestration.render_pipeline import run_render_pipeline"` to confirm imports are clean.
