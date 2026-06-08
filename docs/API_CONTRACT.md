# API Contract & Sacred Contracts

## Frozen REST Endpoints

Do not change these paths, add required parameters, or remove response fields.

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/render/process` | Submit render job |
| GET | `/api/jobs/{id}` | Poll job status |
| GET | `/api/jobs/{id}/ws` | WebSocket live progress stream |
| GET | `/health` | Health + DB path check |
| GET | `/` | Serve frontend index.html |

---

## Sacred Contracts

### Contract 1 — result_json Backward-Compat Keys

Every `result_json` blob written by the pipeline **must** contain these three keys:

```
output_rank_score
is_best_output
is_best_clip
```

**Location:** `pipeline_ranking.py:_compute_output_ranking_entry()`, `pipeline_finalize.py`

Removing any of these causes the history UI and output comparison UI to silently show empty data.

---

### Contract 2 — RenderRequest New Field Defaults

Every new field added to `RenderRequest` in `models/schemas.py` must default to `False` or the most conservative disabled state.

`model_config = ConfigDict(extra="ignore")` ensures unknown fields in stored payloads are silently dropped.

---

### Contract 3 — AI Modules Return None, Never Raise

All modules under `features/render/ai/**` and `ai/**` must catch all exceptions and return `None`. See [AI_INTEGRATION.md](AI_INTEGRATION.md).

---

### Contract 4 — Job Stage Names (Frozen)

`JobStage` enum in `core/stage.py`. Do not rename or remove values without updating all WebSocket consumers and frontend state machines.

```
QUEUED → STARTING → RUNNING → ANALYZING → TRANSCRIBING_FULL →
SCENE_DETECTION → SEGMENT_BUILDING → RENDERING → RENDERING_PARALLEL →
WRITING_REPORT → DONE
(terminal: FAILED, CANCELLED)
```

---

### Contract 5 — Job Part Stage Names (Frozen)

`JobPartStage` enum in `core/stage.py`. Same enforcement as Contract 4.

```
QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE
(terminal: FAILED, SKIPPED)
```

---

### Contract 6 — `_emit_render_event` Signature (Frozen)

Defined in `features/render/engine/pipeline/render_events.py`.

```python
def _emit_render_event(
    *,
    channel_code: str,
    job_id: str,
    event: str,
    level: str,
    message: str,
    step: str,
    context: dict | None = None,
    exception: Exception | None = None,
    traceback_text: str = "",
    duration_ms: int | None = None,
    error_code: str = "",
):
```

50+ call sites across the pipeline use keyword args. Any signature change must update all call sites and the WebSocket handler in `routes/jobs.py` simultaneously.

---

### Contract 7 — `data/app.db` Sole Job State Authority

- Never delete `data/app.db`
- Never write to it with raw `sqlite3.connect()` outside `backend/app/db/`
- Never execute DROP, TRUNCATE, or ALTER TABLE RENAME
- All access through `db/connection.py` (sets WAL mode, row factories, thread-local state)

Fallback path to `%LOCALAPPDATA%` is detected at startup and surfaced via `/health` endpoint `db_fallback_active` field.

---

### Contract 8 — `qa_pipeline.py` Output Validation Never Bypassed

`features/render/engine/pipeline/qa_pipeline.py` is the sole output validation gate.

Never:
- Bypass it to make a render "succeed"
- Catch its exceptions to return success
- Lower its thresholds for a specific broken render

It catches: missing output file, file too small, no video stream, no audio stream, zero-duration video.

---

## WebSocket Event Shape (Frozen)

Every event emitted by `_emit_render_event` must have these three top-level keys:

```json
{
  "job":     { "...job fields..." },
  "parts":   [ { "...part fields..." } ],
  "summary": { "...WsProgressSummary fields..." }
}
```

- Never remove any of the three top-level keys
- Never rename `parts` to `clips` or `segments`
- Never flatten `summary` into root
- All three keys present in every emission, even if `parts` is `[]`

---

## HTTP Polling Fallback

`GET /api/jobs/{id}` HTTP polling must remain a fully functional alternative to WebSocket. No progress-tracking data may be made WebSocket-exclusive. Required for Electron environments where WebSocket upgrades may fail.

---

## Database Migration Rules

Schema changes must be strictly additive:

| Allowed | Forbidden |
|---------|-----------|
| New table with nullable / defaulted columns | DROP TABLE |
| New column with DEFAULT value | DROP COLUMN |
| New index | RENAME COLUMN |
| | ALTER TABLE RENAME |
| | Changing column type |

WAL mode must not change. SQLite WAL enables concurrent reads during writes, required for the render progress polling pattern.

---

## FFmpeg Path Helpers (Mandatory)

Always use these when building FFmpeg commands:

```python
safe_filter_path(path)    # escapes path for FFmpeg filter graph args
get_ffmpeg_bin()          # platform-correct FFmpeg binary
get_ffprobe_bin()         # platform-correct ffprobe binary
```

Never concatenate raw path strings into FFmpeg arguments. Windows paths with spaces, parentheses, or backslashes cause silent misparse.

---

## NVENC Semaphore

`NVENC_SEMAPHORE` in `features/render/engine/encoder/ffmpeg_helpers.py:27-28`.

- Default max: 3 sessions (`NVENC_MAX_SESSIONS` env var)
- Consumer GPU NVENC limit: 3-5 sessions hardware-enforced
- Exceeding limit fails ALL active sessions simultaneously with generic FFmpeg error

Do not raise `NVENC_MAX_SESSIONS` without documenting target hardware class.

Acquired at three call sites in `stages/part_render_encode.py`. Other FFmpeg callers (`clip_ops.py`, `motion_crop.py`, `audio_mix_service.py`) do NOT acquire it — known gap.
