# Backend Rules

## API Contracts — Frozen

| Contract | File | Must stay intact |
|----------|------|-----------------|
| Route paths | `routes/render.py`, `routes/jobs.py` | `/api/render/process`, `/api/jobs/{id}`, `/api/jobs/{id}/ws` |
| WebSocket event shape | `routes/jobs.py` | `{ job, parts[], summary: WsProgressSummary }` |
| HTTP polling fallback | `routes/jobs.py` | Must work when WebSocket unavailable |
| RenderRequest field defaults | `schemas.py` | New fields: always default `False`/disabled |

## Risk Tiers

### LOW — Edit freely
- `backend/app/routes/voice.py`
- `backend/app/routes/channels.py`
- `backend/app/routes/download.py`
- `backend/app/core/config.py` (env vars + data paths)
- `backend/knowledge/**` (add only)

### MEDIUM — Plan first, focused pytest
- `backend/app/routes/render.py` — preserve validation, legacy coercion, resume/retry
- `backend/app/routes/jobs.py` — preserve WS shape, polling, history
- `backend/app/routes/editing.py`
- `backend/app/services/tts_service.py`, `audio_mix_service.py`
- `backend/app/orchestration/asset_pipeline.py`, `audio_pipeline.py`
- `backend/app/services/scene_detector.py`, `segment_builder.py`

### HIGH — Plan + explicit user approval + full pytest recommended
- `backend/app/models/schemas.py` — additive only, never rename/remove fields
- `backend/app/services/db.py` — no schema drops, no destructive migrations
- `backend/app/services/job_manager.py` — queue semantics, thread safety
- `backend/app/core/ui_gate.py` — controls which UI is served
- `backend/app/main.py` — startup + mount points

## AI Import Rule

Optional AI dependencies go in `requirements-ai.txt` only.
Never add import-time optional deps to main runtime (`requirements.txt` path).
AI modules must never fail at import time due to optional dep absence.

## DEVTOOLS Danger

`backend/app/routes/devtools.py` requires `ENABLE_DEVTOOLS=1`.
This is an unauthenticated shell execution route.
Never enable in production. Never make it easier to enable.

## Database Rules

- `data/app.db` — sole job state authority, NEVER delete
- `data/ai_memory.db` — AI learning store, MEDIUM risk
- SQLite migrations: additive only (new columns with defaults), never drop
- WAL mode is set — do not change journal mode
