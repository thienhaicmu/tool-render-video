# Log Usage — Diagnosing Errors

This file tells Claude Code exactly where to look for each error type.

---

## Quick Lookup: Symptom → Log

| Symptom | Error Type | First log to read |
|---|---|---|
| UI shows "Start render failed" | Type 1 — Request | `data/logs/request.log` |
| Job status = "failed" | Type 2 — Pipeline | `data/logs/error.log` + per-job log |
| Server returns 500, no job created | Type 3 — System | `data/logs/desktop-backend.log` |
| Electron window does not open | Bootstrap/Electron | `data/logs/desktop-backend.log` |
| Render stuck on a stage | Type 2 | `data/logs/app.log` (trace) + per-job log |
| Subtitle wrong timing | Type 2 | per-job log + `data/logs/app.log` |

---

## Log Files

### `data/logs/request.log`
**Type 1 errors.** Validation rejections before the pipeline starts.
Format: JSON lines with `route`, `status_code`, `detail`.

```powershell
Get-Content data\logs\request.log -Tail 50
```

When to read: UI shows a red validation message immediately on submit (before any job is created).

---

### `data/logs/error.log`
**Type 2 errors.** Pipeline failures inside `run_render_pipeline`.
Format: JSON lines with `error_code`, `step`, `exception`, `traceback`.

```powershell
Get-Content data\logs\error.log -Tail 50
```

When to read: A job was created but finished with status `failed`.

---

### `data/logs/app.log`
**All pipeline events.** Full trace of every stage transition, progress update, and event.
Use this to trace the sequence of events leading up to a failure.

```powershell
Get-Content data\logs\app.log -Tail 100
```

---

### `channels/<code>/logs/<job_id>.log`
**Per-job log.** Most detailed log for a single render job.
Read this first when debugging a specific job failure.

```powershell
Get-Content channels\<channel_code>\logs\<job_id>.log
```

Or via API:
```bash
GET http://localhost:8000/api/jobs/{job_id}/logs?lines=200
```

---

### `data/logs/desktop-backend.log`
**System and Electron log.** Catches:
- Unhandled exceptions in route functions (Type 3)
- Electron bootstrap errors (backend did not start)
- uvicorn startup errors

```powershell
Get-Content data\logs\desktop-backend.log -Tail 100
```

---

## Structured Error Codes (Type 2)

| Code | Meaning |
|---|---|
| `RN001` | Generic render error |
| `RN002` | File not found |
| `RN003` | Invalid output path or permission denied |
| `RN004` | ffmpeg process error |
| `RN005` | Scene detection failed |
| `RN006` | Trim or cut operation failed |

---

## Via claude-cowork-v2 Scripts

```bash
# Capture an error for the bug-ranking system
npm run capture-error -- \
  --component render_engine \
  --action render \
  --error-name RuntimeError \
  --message "description of the error"

# List all recorded errors ranked by priority
npm run log_error -- --list

# Get fix prompt for the highest-priority error
npm run log_error

# Send fix prompt to Claude automatically
npm run log_error:run
```

Scripts live in: `claude-cowork-v2/scripts/`

---

## Debug Mode (Verbose Logging)

Enable verbose debug logging for the next backend run:

```powershell
$env:RENDER_DEBUG_LOG = "1"
.\run-backend.ps1
```

This emits additional per-frame and per-segment detail in the per-job log.

---

## Standard Debug Sequence

```
1. /status            → confirm backend is alive
2. /error             → get highest-priority error (code + step + message)
3. Read per-job log   → channels/<code>/logs/<job_id>.log
4. Read error.log     → data/logs/error.log (last 50 lines)
5. Read app.log       → data/logs/app.log (last 100 lines) for event trace
6. /fix               → apply patch or get plan
7. /test              → verify after patch
```
