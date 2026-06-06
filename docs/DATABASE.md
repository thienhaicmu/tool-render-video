# Database

## Overview

Single SQLite database at `data/app.db`. WAL mode enabled. No cloud sync, no replication. Deletion is permanent — there is no recovery path.

Connection module: `backend/app/db/connection.py`

---

## Tables

### jobs

Primary job state table.

```sql
CREATE TABLE jobs (
    job_id           TEXT PRIMARY KEY,
    kind             TEXT NOT NULL,           -- "render" | "download"
    channel_code     TEXT NOT NULL,
    status           TEXT NOT NULL,           -- "queued"|"running"|"completed"|"failed"|"cancelling"
    stage            TEXT DEFAULT '',         -- JobStage enum value
    progress_percent INTEGER DEFAULT 0,
    message          TEXT DEFAULT '',
    payload_json     TEXT,                    -- RenderRequest.model_dump() JSON
    result_json      TEXT,                    -- result blob (see below)
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    priority         INTEGER DEFAULT 0,
    error_kind       TEXT,
    render_plan_json TEXT                     -- RenderPlan JSON (migration 0001)
);
CREATE INDEX idx_jobs_updated ON jobs(updated_at DESC, created_at DESC);
CREATE INDEX idx_jobs_status_kind ON jobs(status, kind);
```

### result_json Structure

Assembled by `pipeline_finalize.py`. Key fields:

```python
{
    "outputs": [str, ...],                 # list of output file paths
    "segments": [...],                     # scored[] list
    "output_ranking": [                    # SACRED CONTRACT #1
        {
            "output_rank_score": float,    # must always be present
            "is_best_output": bool,        # must always be present
            "is_best_clip": bool,          # must always be present
            "output_file": str,
            "output_rank": int,
            "part_no": int,
            ...
        }
    ],
    "best_clip": {...},
    "best_exports": [...],
    "failed_parts": [int, ...],
    "failed_parts_detail": [...],
    "selected_segments_count": int,
    "successful_outputs_count": int,
    "failed_outputs_count": int,
    "is_partial_success": bool,
    "recovery_notes": [str, ...],
    "voice_summary": {...},
    "subtitle_translate_summary": {...},
    # Phase-X removals (kept empty for consumer compat):
    "ai_director": {"enabled": false},
    "story": {},
    "preset_evolution": {},
    "creator_style": {},
    "ai_output_ranking": {"available": false},
    "ai_render_quality_evaluation": {"available": false},
    "ai_ux": {}
}
```

---

### job_parts

Per-clip render state.

```sql
CREATE TABLE job_parts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           TEXT NOT NULL,
    part_no          INTEGER NOT NULL,        -- 1-based clip index
    part_name        TEXT NOT NULL,
    status           TEXT NOT NULL,           -- JobPartStage enum value
    progress_percent INTEGER DEFAULT 0,
    start_sec        REAL DEFAULT 0,
    end_sec          REAL DEFAULT 0,
    duration         REAL DEFAULT 0,
    viral_score      REAL DEFAULT 0,
    motion_score     REAL DEFAULT 0,
    hook_score       REAL DEFAULT 0,
    output_file      TEXT DEFAULT '',
    message          TEXT DEFAULT '',
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, part_no)
);
```

---

### creator_prefs

Singleton table (always exactly 1 row, id=1).

```sql
CREATE TABLE creator_prefs (
    id           INTEGER PRIMARY KEY CHECK (id = 1),
    prefs_json   TEXT DEFAULT '{}',
    updated_at   TEXT DEFAULT CURRENT_TIMESTAMP
);
```

Stores user settings and `creator_context` nested JSON (Sprint 3 CreatorContext).

---

### download_jobs

Download task tracking (separate from render jobs).

```sql
CREATE TABLE download_jobs (
    id           TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    platform     TEXT DEFAULT '',
    status       TEXT DEFAULT 'queued',
    progress     INTEGER DEFAULT 0,
    speed_str    TEXT DEFAULT '',
    eta_str      TEXT DEFAULT '',
    output_path  TEXT DEFAULT '',
    output_dir   TEXT DEFAULT '',
    filename     TEXT DEFAULT '',
    title        TEXT DEFAULT '',
    duration     REAL DEFAULT 0,
    height       INTEGER DEFAULT 0,
    fps          REAL DEFAULT 0,
    filesize     INTEGER DEFAULT 0,
    error_msg    TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX idx_dl_jobs_status ON download_jobs(status);
CREATE INDEX idx_dl_jobs_created ON download_jobs(created_at DESC);
```

---

### clip_feedback

User ratings for rendered clips.

```sql
CREATE TABLE clip_feedback (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id       TEXT NOT NULL,
    part_no      INTEGER NOT NULL,
    channel_code TEXT NOT NULL DEFAULT '',
    goal         TEXT NOT NULL DEFAULT '',
    rating       INTEGER NOT NULL CHECK(rating IN (-1, 1)),
    hook_type    TEXT NOT NULL DEFAULT 'none',
    clip_type    TEXT NOT NULL DEFAULT 'unknown',
    start_sec    REAL NOT NULL DEFAULT 0.0,
    end_sec      REAL NOT NULL DEFAULT 0.0,
    duration_sec REAL NOT NULL DEFAULT 0.0,
    rated_at     TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(job_id, part_no)
);
CREATE INDEX idx_feedback_channel ON clip_feedback(channel_code, goal);
```

---

### schema_versions

Migration tracking.

```sql
CREATE TABLE schema_versions (
    version    INTEGER NOT NULL PRIMARY KEY,
    name       TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

---

## Migrations

| File | Version | Change |
|------|---------|--------|
| `0001_jobs_add_render_plan_json.py` | 1 | `ALTER TABLE jobs ADD COLUMN render_plan_json TEXT` |
| `0002_jobs_rewrite_groq_to_llm.py` | 2 | Rewrite `groq_*` fields to `llm_*` in stored `payload_json` |

---

## Connection Model

Two patterns — do not introduce a third.

### `db_conn()` — HTTP request path

```python
@contextlib.contextmanager
def db_conn():
    conn = get_conn()       # new connection
    try:
        yield conn
        conn.commit()       # auto-commit on success
    except Exception:
        conn.rollback()
    finally:
        conn.close()
```

Used by: `jobs_repo.py` (upsert_job, get_job, list_jobs), `creator_repo.py`, `feedback_repo.py`, `download_repo.py`.

### `_thread_conn()` — render hot path only

```python
_tls = threading.local()

def _thread_conn() -> sqlite3.Connection:
    if not hasattr(_tls, 'conn'):
        _tls.conn = get_conn()
    return _tls.conn

def close_thread_conn():
    if hasattr(_tls, 'conn'):
        _tls.conn.close()
        del _tls.conn
```

Used by: `update_job_progress()`, `upsert_job_part()` — high-frequency writes during render.

`close_thread_conn()` called in `finally` block of `render_pipeline.py`.

**Why two patterns:** `db_conn()` is ~165× slower than `_thread_conn()` per call (3,152 μs vs 18.8 μs median, WAL mode). The render progress write rate makes `db_conn()` unacceptable on the hot path. Unification deferred indefinitely — see `docs/review/SPRINT_7_7_BENCHMARK_PREP_2026-06-05.md`.

---

## WAL Mode

Set at connection open time. **Never change journal mode.**

WAL enables concurrent readers while a write is open. Without it, every `update_job_progress` write blocks all HTTP polling responses — progress UI appears frozen during renders.

---

## DB Fallback

If primary `data/app.db` is unwritable, `_resolve_db_path()` falls back to `%LOCALAPPDATA%\tool-render-video\data\app.db`.

- Detected at startup by `_check_db_fallback_at_startup()`
- Logged at `CRITICAL` level
- `DB_FALLBACK_ENGAGED.flag` file written to `APP_DATA_DIR`
- `/health` endpoint returns `"db_fallback_active": true`

This creates a split-DB condition — job state is written to two different files. Recover by fixing permissions on primary path and restarting.
