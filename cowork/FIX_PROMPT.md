# Fix Workflow — Claude Code Protocol

This file defines the mandatory protocol for `/fix` workflows in this repository.

---

## Step-by-Step Protocol

### Step 1 — Orient before touching anything

Read these before writing any code:
- `cowork/COWORK_SYSTEM_DEFINITION.md` — system architecture rules
- `cowork/COMMANDS.md` — what /fix means and what it will not do
- `cowork/PROJECT_STATUS.md` — current safe zones and caution areas

### Step 2 — Gather evidence

Run in order and record results:
```
/status      → confirm backend is alive
/error       → get the structured error summary (error_code, step, exception)
/log error   → see raw error lines
```

Also read directly:
- `data/logs/request.log` — for Type 1 validation errors (rejected before pipeline)
- `data/logs/error.log` — for Type 2 pipeline errors (failed inside run_render_pipeline)
- `channels/<code>/logs/<job_id>.log` — for the specific failed job
- `data/logs/desktop-backend.log` — for Type 3 system/Electron errors

### Step 3 — Locate the minimum change

- Find the exact file and function in the call chain
- Do NOT touch files that are not in the call chain of the bug
- Do NOT refactor while fixing

Call chain reference:
```
routes/ → orchestration/render_pipeline.py → services/ → core/
```

### Step 4 — Implement

Mandatory rules (from RULES.md):
1. Smallest correct change only
2. No scope expansion
3. No unrelated edits
4. Preserve API field names, status enums, and path conventions
5. Keep all fallback paths: NVENC→CPU, WS→polling, copy→reencode
6. Do NOT add pipeline logic to routes — it belongs in orchestration/
7. Do NOT check source_mode before edit_session_id in the pipeline
8. Do NOT silently re-download when edit_session_id is set but session is missing — raise
9. State all assumptions explicitly
10. Do NOT run destructive operations without confirmation

### Step 5 — Verify

Run:
```
/test
```

Or run the targeted import check:
```bash
python -c "from app.routes.render import router; from app.orchestration.render_pipeline import run_render_pipeline; print('imports OK')"
```

### Step 6 — Report

Use [SUMMARY_TEMPLATE.md](SUMMARY_TEMPLATE.md) format.

---

## Risk Levels by File

**Lower risk** — single-domain logic, well-isolated:
- `backend/app/services/subtitle_engine.py`
- `backend/app/services/scene_detector.py`
- `backend/app/services/viral_scorer.py`
- `backend/app/services/report_service.py`
- `backend/app/core/config.py`
- `cowork/` (documentation only)
- `prompts/` (templates only)

**Higher risk** — core pipeline or HTTP boundary:
- `backend/app/orchestration/render_pipeline.py` — the entire render pipeline
- `backend/app/routes/render.py` — HTTP + session management
- `backend/app/services/render_engine.py` — ffmpeg encoding
- `backend/static/js/render-ui.js` — frontend render flow
- `backend/static/js/render-engine.js` — frontend render logic

For higher-risk files: produce a patch plan and get confirmation before applying.

---

## What /fix Will NOT Do

- Refactor code adjacent to the bug
- Add features not stated in the task
- Remove fallback paths (NVENC→CPU, WS→polling, copy→reencode)
- Modify files in a different layer without an explicit reason
- Move pipeline logic into routes
- Run destructive file or database operations
