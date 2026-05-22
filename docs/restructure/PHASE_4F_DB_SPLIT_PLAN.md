# PHASE_4F_DB_SPLIT_PLAN.md

**Status**: IN PROGRESS (Phase 4F.1–4F.4 SHIPPED, Phase 4F.5 AUDIT COMPLETE, Phase 4F.5A–C SHIPPED — upload router, frontend, engine, channels dependency, DB functions, route file, and platform_repo removed; upload tables remain for 4F.5D)
**Last updated**: 2026-05-22 (post Phase 4F.5C)
**Branch**: `restructure/output-timeline-architecture`

Phase 4F.0 was planning only. Phase 4F.1 has been shipped — see [MIGRATION_HISTORY.md](MIGRATION_HISTORY.md) for details.

---

## 1. Current db.py State

**File**: `backend/app/services/db.py`
**Lines**: 1,886
**Tables owned**: 9 (jobs, job_parts, upload_accounts, upload_queue, upload_videos, upload_history, upload_runtime_locks, upload_scheduler_state, upload_proxy_pool, creator_prefs)
**Public functions**: 55
**Private helpers**: 15
**Module-level globals**: 5 (`_DB_PATH_LOCK`, `_ACTIVE_DB_PATH`, `_tls`, `UPLOAD_PROFILE_LOCK_TTL_MINUTES`, `UPLOAD_SCHEDULER_STATE_ID`)
**Existing test coverage**: **Zero** — no test file imports from `app.services.db`

---

## 2. Why DB Split is High Risk

Compared to the render_engine.py split, db.py presents fundamentally different risks:

| Risk | Reason |
|---|---|
| **Shared mutable state** | `_ACTIVE_DB_PATH` (global, lazy-resolved), `_tls` (thread-local, shared by `update_job_progress` + `upsert_job_part`). Must live in exactly one module. |
| **`init_db()` crosses all domains** | One function creates 9 tables + runs migrations for all. Any partial extraction of `init_db()` risks table creation order. |
| **Thread-local connection cache** | `_thread_conn()` + `close_thread_conn()` + `_tls` are a three-part system. Splitting them across modules breaks the cache. |
| **N+1 intra-domain calls** | `enrich_upload_account_runtime_state()` calls `find_upload_account_profile_conflict()` and `list_active_runtime_locks()`. All three must be co-located or a circular import results. |
| **Row normalization chains** | Upload queue list views (`list_upload_queue`, `get_upload_queue_item`) do LEFT JOINs; row dicts contain computed fields (`video_file_name`, `account_display_name`). Normalization helpers must be co-located with their CRUD callers. |
| **No existing test baseline** | Zero test files exercise `db.py`. Any extraction mistake is silent — behavior change only detectable at runtime. All test files for new modules must be written from scratch. |
| **14 production callers** | `main.py`, 5 route files, 4 orchestration files, 3 service files — all import via `app.services.db`. Any extraction that breaks re-export identity causes a silent behavioral change. |
| **Constant leakage** | `UPLOAD_PROFILE_LOCK_TTL_MINUTES` is imported by `routes/upload.py` as a constant. It must be re-exported from `services/db.py` after extraction. |

---

## 3. Function Inventory by Domain

### Group A — Connection & Schema Foundation (lines 1–499)

**Target module**: `app/db/connection.py`
**Extraction risk**: HIGH (global state, thread-local, startup sequencing)

| Name | Public | Used by |
|---|---|---|
| `_DB_PATH_LOCK` | — | `_resolve_db_path` |
| `_ACTIVE_DB_PATH` | — | `_resolve_db_path` |
| `_tls` | — | `_thread_conn`, `close_thread_conn` |
| `UPLOAD_PROFILE_LOCK_TTL_MINUTES` | ✓ | `acquire_upload_runtime_lock`, `routes/upload.py` |
| `UPLOAD_SCHEDULER_STATE_ID` | ✓ | scheduler functions, `init_db` |
| `_default_fallback_db_path()` | — | `_resolve_db_path` |
| `_force_writable_file(path)` | — | `_can_write_sqlite` |
| `_can_write_sqlite(path)` | — | `_resolve_db_path` |
| `_resolve_db_path()` | — | `get_conn`, `_thread_conn` |
| `get_conn()` | ✓ | ALL groups, 14 callers across app |
| `_thread_conn()` | — | `update_job_progress`, `upsert_job_part` |
| `close_thread_conn()` | ✓ | `render_pipeline.py` |
| `init_db()` | ✓ | `main.py` (startup) |
| `_json_dumps(data)` | — | ALL groups |
| `_json_loads(raw, default)` | — | ALL groups |
| `_utc_now()` | — | locks, proxy pool |
| `_utc_now_iso()` | — | locks, proxy pool, `init_db` |

**Critical note on `init_db()`**: `init_db()` creates all 9 tables and contains an internal `_ensure_columns()` helper (local function, not a module-level symbol). It only calls `get_conn()` — no other repo imports. Keeping `init_db()` in `connection.py` is safe and avoids a `schema.py` module. A separate `schema.py` is NOT needed.

**Critical note on `_json_dumps`, `_json_loads`, `_utc_now`, `_utc_now_iso`**: These are private cross-cutting helpers used by every group. They belong in `connection.py`. All repo modules import them from `app.db.connection`. Do NOT create a separate `json_utils.py` or `time_utils.py` — these are small (4 functions) and are not leaking concerns.

---

### Group B — Jobs & Job Parts (lines 1266–1406)

**Target module**: `app/db/jobs_repo.py`
**Extraction risk**: MEDIUM (uses `_thread_conn` which must be imported from `connection.py`)

| Name | Public | Notes |
|---|---|---|
| `upsert_job(...)` | ✓ | Uses `get_conn`, `_json_dumps` |
| `update_job_progress(...)` | ✓ | Uses `_thread_conn` — render hot path |
| `delete_job(job_id)` | ✓ | Uses `get_conn` |
| `upsert_job_part(...)` | ✓ | Uses `_thread_conn` — render hot path |
| `get_job(job_id)` | ✓ | Uses `get_conn` |
| `list_jobs()` | ✓ | Uses `get_conn` |
| `list_jobs_page(limit, offset)` | ✓ | Uses `get_conn` |
| `list_job_parts_bulk(job_ids)` | ✓ | Uses `get_conn` |
| `list_job_parts(job_id)` | ✓ | Uses `get_conn` |

**Callers**: `render_pipeline.py`, `render_events.py`, `qa_pipeline.py`, `routes/render.py`, `routes/download.py`, `routes/jobs.py`, `job_manager.py`, `dev_commands.py`, `maintenance.py`

**Thread-local risk**: `update_job_progress` and `upsert_job_part` both call `_thread_conn()`. After extraction, `jobs_repo.py` imports `_thread_conn` from `app.db.connection`. The `_tls` instance lives in `connection.py` — both functions share the SAME thread-local connection. `close_thread_conn()` (in `connection.py`) correctly closes it. No split risk as long as `_tls` stays in `connection.py`.

---

### Group C — Upload Accounts / Queue / Videos / History / Locks / Scheduler (lines 525–1724)

**Target module**: `app/db/uploads_repo.py`
**Extraction risk**: HIGH (intra-group call chains, profile path normalization, N+1 enrichment)

#### C.1 Profile Path Helpers

| Name | Public | Notes |
|---|---|---|
| `_default_upload_profiles_root()` | — | Uses `DATABASE_PATH` from `app.core.config` |
| `normalize_profile_path_value(profile_path)` | ✓ | OS-specific path normalization |
| `build_default_upload_profile_path(platform, key)` | ✓ | Imported by `routes/upload.py` |
| `ensure_upload_account_profile_path_fields(data)` | ✓ | Calls `normalize_profile_path_value` |

#### C.2 Row Normalizers (all private)

| Name | Notes |
|---|---|
| `_normalize_upload_account_row(row)` | Calls `_json_loads`, `ensure_upload_account_profile_path_fields` |
| `_normalize_upload_video_row(row)` | Calls `_json_loads` |
| `_normalize_upload_queue_row(row)` | Calls `_json_loads` |
| `_normalize_upload_history_row(row)` | Calls `_json_loads` |
| `_normalize_upload_scheduler_state_row(row)` | Calls `_json_loads`, uses `UPLOAD_SCHEDULER_STATE_ID` |

#### C.3 Runtime Locks

| Name | Public | Notes |
|---|---|---|
| `_active_profile_conflict_statuses()` | — | Returns tuple of active status strings |
| `list_active_runtime_locks(...)` | ✓ | Stale-lock recovery inline; calls `_utc_now`, `_json_loads` |
| `_set_account_lock_state(account_id, state)` | — | Called by `acquire_upload_runtime_lock`, `release_upload_runtime_locks_for_queue` |
| `release_upload_runtime_locks_for_queue(queue_id)` | ✓ | Calls `_set_account_lock_state` |
| `acquire_upload_runtime_lock(...)` | ✓ | Calls `_set_account_lock_state`, `normalize_profile_path_value`, `_utc_now` |
| `enrich_upload_account_runtime_state(account)` | ✓ | Calls `find_upload_account_profile_conflict` AND `list_active_runtime_locks` |

#### C.4 Upload Accounts

| Name | Public |
|---|---|
| `list_upload_account_rows(include_disabled)` | ✓ |
| `get_upload_account_row(account_id)` | ✓ |
| `get_upload_account(account_id)` | ✓ |
| `find_upload_account_profile_conflict(...)` | ✓ |
| `create_upload_account_row(data)` | ✓ |
| `update_upload_account_row(account_id, changes)` | ✓ |
| `disable_upload_account_row(account_id)` | ✓ |

#### C.5 Scheduler State

| Name | Public |
|---|---|
| `get_upload_scheduler_state()` | ✓ |
| `update_upload_scheduler_state(changes)` | ✓ |
| `increment_upload_scheduler_running_count(delta)` | ✓ |

#### C.6 Upload Videos

| Name | Public |
|---|---|
| `create_upload_video_row(data)` | ✓ |
| `list_upload_video_rows(...)` | ✓ |
| `get_upload_video_row(video_id)` | ✓ |
| `get_upload_video(video_id)` | ✓ |
| `update_upload_video_row(video_id, changes)` | ✓ |
| `disable_upload_video_row(video_id)` | ✓ |

#### C.7 Upload Queue

| Name | Public | Notes |
|---|---|---|
| `add_upload_queue_item(...)` | ✓ | |
| `list_upload_queue(...)` | ✓ | LEFT JOINs upload_videos + upload_accounts |
| `get_upload_queue_item(queue_id)` | ✓ | LEFT JOINs; called internally by queue mutators |
| `update_upload_queue_item(queue_id, changes)` | ✓ | Calls `get_upload_queue_item` |
| `set_upload_queue_last_error(queue_id, error)` | ✓ | Calls `get_upload_queue_item` |
| `update_upload_queue_status(...)` | ✓ | Calls `get_upload_queue_item` |
| `mark_upload_queue_uploading(queue_id)` | ✓ | Calls `get_upload_queue_item` |
| `mark_upload_queue_success(queue_id, result)` | ✓ | Calls `update_upload_queue_status` |
| `mark_upload_queue_failed(queue_id, error)` | ✓ | Calls `update_upload_queue_status` |
| `cancel_upload_queue_item(queue_id)` | ✓ | |

#### C.8 Upload History

| Name | Public |
|---|---|
| `insert_upload_history(...)` | ✓ |
| `list_upload_history(queue_id, limit)` | ✓ |

**Why uploads_repo.py is one module**: The intra-group call graph is dense:
- `enrich_upload_account_runtime_state` → `find_upload_account_profile_conflict` + `list_active_runtime_locks`
- `list_upload_account_rows` → `enrich_upload_account_runtime_state` → both above
- `acquire_upload_runtime_lock` → `_set_account_lock_state`
- `release_upload_runtime_locks_for_queue` → `_set_account_lock_state`

Splitting these into separate files (e.g., `accounts_repo.py` + `locks_repo.py`) would require mutual imports, which Python allows but creates maintenance overhead. The single `uploads_repo.py` module is ~1,200 lines — large, but internally coherent. A further split is a Phase 4G+ concern, after the initial extraction stabilizes.

---

### Group D — Proxy Pool (lines 1726–1859)

**Target module**: `app/db/platform_repo.py`
**Extraction risk**: LOW (self-contained, no intra-group calls)

| Name | Public | Notes |
|---|---|---|
| `_normalize_proxy_pool_row(row)` | — | Calls `_json_loads` |
| `list_proxy_pool_rows()` | ✓ | |
| `get_proxy_pool_row(proxy_id)` | ✓ | |
| `create_proxy_pool_row(data)` | ✓ | Calls `_utc_now_iso`, `_json_dumps` |
| `update_proxy_pool_row(proxy_id, changes)` | ✓ | Calls `_utc_now_iso`, `_json_dumps` |
| `delete_proxy_pool_row(proxy_id)` | ✓ | |

**Callers**: `routes/upload.py` (all 5 proxy functions)

---

### Group E — Creator Prefs (lines 1861–1886)

**Target module**: `app/db/creator_repo.py`
**Extraction risk**: VERY LOW (25 lines, no dependencies on other groups)

| Name | Public | Notes |
|---|---|---|
| `get_creator_prefs()` | ✓ | Calls `get_conn`, `_json_loads` |
| `upsert_creator_prefs(prefs)` | ✓ | Calls `get_conn`, `_json_dumps` |

**Callers**: `routes/creator.py`

---

## 4. Target DB Module Tree

```
backend/app/db/
├── __init__.py          (empty)
├── connection.py        (~130 lines: get_conn, close_thread_conn, _thread_conn,
│                          _resolve_db_path, _force_writable_file, _can_write_sqlite,
│                          _json_dumps, _json_loads, _utc_now, _utc_now_iso,
│                          init_db, constants, globals)
├── jobs_repo.py         (~140 lines: upsert_job, update_job_progress, delete_job,
│                          upsert_job_part, get_job, list_jobs, list_jobs_page,
│                          list_job_parts, list_job_parts_bulk)
├── uploads_repo.py      (~1,200 lines: ALL upload domain functions — accounts,
│                          videos, queue, history, locks, scheduler, normalization,
│                          profile path helpers, enrich)
├── platform_repo.py     (~130 lines: proxy pool CRUD)
└── creator_repo.py      (~25 lines: get_creator_prefs, upsert_creator_prefs)
```

**What NOT to create**:
- `schema.py` — not needed; `init_db()` only calls `get_conn()` (no other repo imports) and lives safely in `connection.py`
- `json_utils.py` — not needed; 4 small private helpers belong in `connection.py`
- `time_utils.py` — not needed; 2 small private helpers belong in `connection.py`
- `locks_repo.py` — not yet; would require circular imports with `uploads_repo.py`
- `queue_repo.py` — not yet; queue functions call `get_upload_queue_item` internally

---

## 5. Module Responsibility Map

| Module | Owns | Imports from |
|---|---|---|
| `app/db/connection.py` | DB path resolution, connection creation, thread-local cache, JSON/time helpers, schema bootstrap (`init_db`) | `app.core.config`, stdlib only |
| `app/db/jobs_repo.py` | jobs + job_parts CRUD | `app.db.connection` |
| `app/db/uploads_repo.py` | upload accounts, videos, queue, history, locks, scheduler + all row normalizers + profile path helpers | `app.db.connection`, `app.core.config` |
| `app/db/platform_repo.py` | proxy pool CRUD | `app.db.connection` |
| `app/db/creator_repo.py` | creator prefs | `app.db.connection` |
| `app/services/db.py` | backward-compat re-export shim | `app.db.*` |

---

## 6. Dependency Rules

**Allowed**:
```
app.db.jobs_repo        → app.db.connection
app.db.uploads_repo     → app.db.connection
app.db.platform_repo    → app.db.connection
app.db.creator_repo     → app.db.connection
app.services.db         → app.db.*  (re-export shim)
```

**Forbidden**:
```
app.db.*                → app.services.db        (no upward import — circular)
app.db.*                → app.routes.*           (no routes in DB layer)
app.db.*                → app.orchestration.*    (no orchestration in DB layer)
app.db.connection       → any repo module        (connection is the base)
repo modules            → each other             (no inter-repo imports)
```

**Exception — uploads_repo.py intra-calls**:
`enrich_upload_account_runtime_state` calls `find_upload_account_profile_conflict` and `list_active_runtime_locks`. Both are defined in the same file — no import needed. This is NOT an exception to the rule; intra-module calls are plain Python.

---

## 7. Compatibility Strategy

`backend/app/services/db.py` **must remain** as a public compatibility shim throughout all Phase 4F sub-phases.

After each extraction step, `services/db.py` gains re-export lines:
```python
# After Phase 4F.1:
from app.db.connection import (
    get_conn, close_thread_conn, init_db,
    UPLOAD_PROFILE_LOCK_TTL_MINUTES, UPLOAD_SCHEDULER_STATE_ID,
)

# After Phase 4F.2:
from app.db.jobs_repo import (
    upsert_job, update_job_progress, delete_job, upsert_job_part,
    get_job, list_jobs, list_jobs_page, list_job_parts, list_job_parts_bulk,
)
# ... etc
```

**Same-object identity requirement**: All re-exported names MUST be the same Python object (`is` identity). This is guaranteed by `from X import Y` — the name `Y` in `services/db.py` becomes a reference to the same object. No wrapper functions. No property proxies.

**Constant re-export**: `UPLOAD_PROFILE_LOCK_TTL_MINUTES` is imported by `routes/upload.py` as a constant value. Re-exporting an integer works correctly — `from app.services.db import UPLOAD_PROFILE_LOCK_TTL_MINUTES` gets the integer `30`. No identity issue.

**No caller migration required in Phases 4F.1–4F.5**: All existing `from app.services.db import X` imports continue to work without any change. Migration from `app.services.db` to `app.db.*` is a separate optional Phase 4F.6 audit.

---

## 8. Proposed Sub-Phases

| Phase | Goal | Risk | Lines extracted |
|---|---|---|---|
| **4F.1** ✓ | Extract DB connection foundation to `connection.py` | HIGH | ~130 |
| **4F.2** ✓ | Extract jobs repo to `jobs_repo.py` | MEDIUM | ~140 |
| **4F.3** ✓ | Extract creator repo to `creator_repo.py` | VERY LOW | ~25 |
| **4F.4** ✓ | Extract platform repo to `platform_repo.py` | LOW | ~130 |
| ~~**4F.5**~~ | ~~Extract uploads repo to `uploads_repo.py`~~ | ~~HIGH~~ | ~~CANCELLED — upload domain being removed instead; see PHASE_4F_5_UPLOAD_DOMAIN_REMOVAL_AUDIT.md~~ |
| **4F.6** | Import migration audit (callers optionally migrated) | LOW | 0 |
| **4F.7** | Deprecation cleanup planning (no code deleted) | — | 0 |

**Why 4F.3 (creator) before 4F.4 (platform) before 4F.5 (uploads)**:
Extract smallest and simplest first to prove the extraction pattern + test harness before tackling the large uploads domain. Creator prefs (25 lines, 2 functions) is the ideal smoke test for the re-export pattern and the temp-SQLite test fixture.

---

## 9. Phase 4F.1 Implementation Scope

**Goal**: Create `app/db/__init__.py` and `app/db/connection.py`. Move all connection + helper + schema code verbatim. Add re-exports in `services/db.py`.

**Files to create**:
- `backend/app/db/__init__.py` (empty)
- `backend/app/db/connection.py` (verbatim from db.py lines 1–499 + helper functions)

**What moves to `connection.py`**:
```
_DB_PATH_LOCK, _ACTIVE_DB_PATH, _tls
UPLOAD_PROFILE_LOCK_TTL_MINUTES, UPLOAD_SCHEDULER_STATE_ID
_default_fallback_db_path()
_force_writable_file(path)
_can_write_sqlite(path)
_resolve_db_path()
get_conn()
_thread_conn()
close_thread_conn()
init_db()
_json_dumps(data)
_json_loads(raw, default)
_utc_now()
_utc_now_iso()
```

**Imports `connection.py` needs**:
```python
import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from app.core.config import DATABASE_PATH
```

**What `services/db.py` re-exports after 4F.1**:
```python
from app.db.connection import (
    get_conn,
    close_thread_conn,
    init_db,
    UPLOAD_PROFILE_LOCK_TTL_MINUTES,
    UPLOAD_SCHEDULER_STATE_ID,
)
```

**What remains in `services/db.py` (function bodies, not yet moved)**:
All repository functions from Group B, C, D, E. They still use `get_conn()` and helpers directly — since `services/db.py` re-exports `get_conn` from `connection.py`, and these functions are still inside `services/db.py`, they call the local re-exported name. This works correctly.

**Test file to create**: `backend/tests/test_db_connection.py`

---

## 10. Connection Foundation Risk Analysis

### 10.1 `_ACTIVE_DB_PATH` global

`_ACTIVE_DB_PATH` is module-level `None`, lazily populated by `_resolve_db_path()` under `_DB_PATH_LOCK`. If this global lives in `connection.py`, all modules that import `get_conn` (which calls `_resolve_db_path`) share the SAME resolved path. This is correct.

**Risk**: If any code tried to reset `_ACTIVE_DB_PATH` from outside (e.g., tests), it would need to import the variable from `connection.py` and mutate it. Current tests don't do this, but future test isolation may require it. Note this in test strategy: use `monkeypatch` or `tmp_path` at the `connection.py` level, not `services/db.py`.

### 10.2 `_tls` thread-local

`_tls = threading.local()` must exist as ONE instance shared by `_thread_conn()`, `close_thread_conn()`, `update_job_progress()`, and `upsert_job_part()`. After Phase 4F.2, `jobs_repo.py` imports `_thread_conn` from `connection.py`. The `_tls` instance is in `connection.py`. `close_thread_conn()` (also in `connection.py`) closes the connection set by `_thread_conn()`. Correct.

**Risk**: Do NOT copy `_tls = threading.local()` into `jobs_repo.py`. One global instance only.

### 10.3 `init_db()` startup sequence

`main.py` calls `init_db()` at startup. After Phase 4F.1, `services/db.py` re-exports `init_db` from `connection.py`. `main.py` continues to import from `services/db.py` — unchanged. The same `init_db` object runs.

`init_db()` contains a local function `_ensure_columns(table, required)` that is only visible inside the body of `init_db()`. This is fine — it's not a module-level symbol and doesn't need to be exported.

### 10.4 SQLite WAL mode + PRAGMA sequence

Both `get_conn()` and `_thread_conn()` set:
```
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;
```
These must be preserved verbatim. WAL mode enables concurrent reads during writes — critical for parallel render jobs.

### 10.5 `row_factory = sqlite3.Row`

Both `get_conn()` and `_thread_conn()` set `conn.row_factory = sqlite3.Row`. All CRUD functions do `dict(row)` or `dict(r)` on query results. This must be preserved. If `row_factory` is removed or changed, all `dict(row)` calls break silently (they return empty dicts because `sqlite3.Row` supports `dict(row)` but a plain tuple does not).

### 10.6 DATABASE_PATH import

`connection.py` imports `DATABASE_PATH` from `app.core.config`. This is a `pathlib.Path`. Used by `_resolve_db_path()` and `_default_upload_profiles_root()`. The second helper actually lives in `uploads_repo.py` territory — but it's defined at line ~526 of `db.py`. Resolution: `_default_upload_profiles_root()` moves to `uploads_repo.py` in Phase 4F.5, importing `DATABASE_PATH` from `app.core.config` directly. `connection.py` imports `DATABASE_PATH` only for `_resolve_db_path()`.

---

## 11. Repository Extraction Order

Recommended sub-phase order justification:

**Phase 4F.1 — Connection first** (prerequisite):
Nothing else can be extracted without `connection.py` existing. The shared state (`_tls`, `_ACTIVE_DB_PATH`) must be in place before any repo imports it.

**Phase 4F.2 — Jobs second** (critical path):
The render pipeline's hot path (`update_job_progress`, `upsert_job_part`) is highest traffic. Extract and test early to validate `_thread_conn` behavior. If the thread-local pattern works here, Phase 4F.5 is de-risked.

**Phase 4F.3 — Creator third** (simplest, proves pattern):
Only 2 functions, no dependencies, no row normalizers, no intra-calls. Validates that the re-export shim pattern works end-to-end with a trivial example before the complex uploads domain.

**Phase 4F.4 — Platform fourth** (low risk):
5 proxy functions, self-contained. Validates CRUD pattern without the complexity of enrich/lock chains.

**Phase 4F.5 — Uploads last** (most complex):
~1,200 lines. Extract after all other modules are proven. The `enrich_upload_account_runtime_state` N+1 calls and lock chain must be moved as a single unit without splitting.

---

## 12. Public API Stability Rules

The following must remain true throughout all Phase 4F sub-phases:

1. **Function signatures unchanged**: No parameter added, removed, or renamed.
2. **Return shapes unchanged**: `dict(row)` structure, JSON column expansion (e.g., `proxy_config` vs `proxy_config_json`), normalization behavior.
3. **Constant values unchanged**: `UPLOAD_PROFILE_LOCK_TTL_MINUTES = 30`, `UPLOAD_SCHEDULER_STATE_ID = "main"`.
4. **`get_conn()` returns `sqlite3.Connection` with `row_factory = sqlite3.Row`**: This is an implicit contract relied on by every CRUD function.
5. **`init_db()` creates all 9 tables in the same order**: `init_db()` is idempotent (`CREATE TABLE IF NOT EXISTS`). Table creation order must not change.
6. **`_ensure_columns()` migration runs for all tables**: The migration helper inside `init_db()` must continue to run for all 9 tables. Do not silently drop migration calls.
7. **`close_thread_conn()` closes the same thread-local connection** used by `update_job_progress` + `upsert_job_part`.
8. **`services/db.py` public namespace is a superset of current namespace**: Every name currently importable from `app.services.db` must remain importable after all phases.

---

## 13. SQLite Schema / Migration Rules

**MUST NOT change during Phase 4F**:
- Table names
- Column names, types, or defaults
- `UNIQUE` constraints
- `PRIMARY KEY` declarations
- `ON CONFLICT` clauses in INSERT statements
- `CHECK` constraint in `creator_prefs` (`id = 1`)
- The `INSERT INTO upload_scheduler_state ... ON CONFLICT DO NOTHING` seed row
- `_ensure_columns()` migration calls and their column DDL strings

**Schema is owned by `init_db()`** in `connection.py`. No repo module should contain DDL (`CREATE TABLE`, `ALTER TABLE`). Only `connection.py` may modify schema at startup.

**Foreign keys**: `PRAGMA foreign_keys=ON` is set in both `get_conn()` and `_thread_conn()`. The `job_parts.job_id` → `jobs.job_id` relationship is soft-enforced. Do not break this.

---

## 14. Testing Strategy

### Test files to create (all new — no existing db tests)

| Test file | Tests | What it exercises |
|---|---|---|
| `test_db_connection.py` | ~25 | `get_conn` thread isolation, `_thread_conn` caching + stale recovery, `close_thread_conn`, `init_db` table creation, `_json_dumps`/`_json_loads` edge cases, `_utc_now` timezone correctness |
| `test_jobs_repo.py` | ~30 | Job CRUD full lifecycle, `update_job_progress` thread-local path, `list_jobs_page` pagination, `list_job_parts_bulk` N job batching, delete cascades to job_parts |
| `test_uploads_repo.py` | ~50 | Account CRUD, profile path normalization, lock acquire/release/stale-recovery, scheduler state toggle, queue full lifecycle (pending→uploading→success/failed), history insert+list, video CRUD |
| `test_platform_repo.py` | ~15 | Proxy CRUD, `_normalize_proxy_pool_row` field coercion |
| `test_creator_repo.py` | ~10 | Prefs roundtrip, missing prefs returns `{}`, invalid JSON fallback |
| `test_db_compat_exports.py` | ~20 | Every public name importable from `app.services.db`; same-object identity for all functions; constants have expected values |

### Test isolation pattern (REQUIRED for all db test files)

```python
import sqlite3
import pytest
from pathlib import Path

@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Provide an isolated temp SQLite DB for each test."""
    db_file = tmp_path / "test.db"
    import app.db.connection as conn_mod
    monkeypatch.setattr(conn_mod, "_ACTIVE_DB_PATH", None)  # reset cache
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    # Reinitialize the resolved path
    from app.db.connection import init_db
    init_db()
    yield db_file
    # cleanup: tmp_path fixture handles file deletion
```

### Key behavioral invariants to assert

| Invariant | Test assertion |
|---|---|
| `get_conn()` sets `row_factory = sqlite3.Row` | `assert conn.row_factory == sqlite3.Row` |
| `dict(row)` works on query results | `row = conn.execute("SELECT 1 AS x").fetchone(); assert dict(row) == {"x": 1}` |
| `_json_loads(None)` returns `{}` | `assert _json_loads(None) == {}` |
| `_json_loads("")` returns `{}` | `assert _json_loads("") == {}` |
| `_json_loads("{invalid}")` returns `{}` | — |
| `_json_loads('[]', default=[])` returns `[]` | — |
| Thread-local conn is reused across calls | same connection object returned on second call |
| Stale lock recovery in `list_active_runtime_locks` | expired lock in DB → returned items excludes it, DB row updated to `active=NULL` |
| `init_db()` is idempotent | second call does not raise |
| `list_jobs_page(2, 0)` returns at most 2 rows | — |
| `list_job_parts_bulk([])` returns `{}` | — |

---

## 15. Mock/Patch Migration Strategy

### Current state: zero test patches target `app.services.db`

No test file currently patches any symbol in `app.services.db`. The existing tests mock upstream callers (e.g., `render_pipeline_mod`, `qa_pipeline_mod`) rather than DB functions directly.

### After extraction: new test files patch `app.db.*` directly

New module test files (e.g., `test_jobs_repo.py`) should test the real functions against a temp SQLite database — not mock `get_conn`. This produces meaningful tests that catch actual SQL bugs.

### If route tests are added in future

If future tests for `routes/jobs.py`, `routes/upload.py` etc. need to mock DB calls:
- Patch at the **route module's imported name**, e.g., `patch("app.routes.jobs.list_jobs", ...)`.
- Do NOT patch at `app.services.db.list_jobs` if `routes/jobs.py` does `from app.services.db import list_jobs` — patch the name in the route's namespace.
- After optional Phase 4F.6 migration, if `routes/jobs.py` imports from `app.db.jobs_repo` directly, patch there.

### `test_db_compat_exports.py` — identity checks

```python
def test_get_conn_identity():
    from app.services.db import get_conn as old
    from app.db.connection import get_conn as new
    assert old is new

def test_upsert_job_identity():
    from app.services.db import upsert_job as old
    from app.db.jobs_repo import upsert_job as new
    assert old is new
```

These identity checks are the guard that the shim is a true re-export and not a wrapper.

---

## 16. Docs Sync Strategy

### Create (this phase):
- `docs/restructure/PHASE_4F_DB_SPLIT_PLAN.md` ← this document

### Update after each sub-phase:
- `docs/restructure/MIGRATION_HISTORY.md` — add Phase 4F.N entry when SHIPPED
- `docs/restructure/PHASE_4A_BACKEND_MODULARIZATION_PLAN.md` — mark sub-phases SHIPPED
- `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` — add `app/db/` tree entry after 4F.1

### Do NOT update yet (only update when code ships):
- `docs/review/TECHNICAL_DEBT_REPORT.md` — update H1 row (db.py god file) only after 4F.5 completes

### Truthfulness rule:
Never mark a phase SHIPPED until its tests pass in the full suite. Never update MIGRATION_HISTORY until the commit is made.

---

## 17. Risk Checklist

Before each sub-phase implementation:

- [ ] `connection.py` module-level globals are not duplicated in repo modules
- [ ] `_tls` instance lives in exactly one module (`connection.py`)
- [ ] `init_db()` migration calls not silently dropped
- [ ] Re-exported names pass `is` identity check vs new module
- [ ] Constants (`UPLOAD_PROFILE_LOCK_TTL_MINUTES`, `UPLOAD_SCHEDULER_STATE_ID`) re-exported from `services/db.py`
- [ ] No `def` wrapper stubs shadowing re-exports in `services/db.py`
- [ ] `_default_upload_profiles_root()` stays with `uploads_repo.py` (uses `DATABASE_PATH`)
- [ ] No repo module imports from `services/db.py` (one-way dependency only)
- [ ] Full test suite passes with 0 new failures after each sub-phase
- [ ] `UPLOAD_SCHEDULER_STATE_ID` is accessible from both `uploads_repo.py` and via `services/db.py` re-export

---

## 18. What Must NOT Change

Throughout all Phase 4F sub-phases:

**DO NOT change**:
- Any function signature in `db.py`
- Any return value shape (dict keys, JSON expansion, normalization behavior)
- Any SQL query (SELECT, INSERT, UPDATE, DELETE statements)
- Any schema DDL in `init_db()`
- Any `_ensure_columns()` migration call or column DDL string
- `row_factory = sqlite3.Row` in both `get_conn()` and `_thread_conn()`
- PRAGMA settings (WAL, synchronous=NORMAL, foreign_keys=ON)
- The `UPLOAD_SCHEDULER_STATE_ID = "main"` seed insert behavior
- `enrich_upload_account_runtime_state()` N+1 behavior (pre-existing debt, fix separately)
- `services/db.py` existence and its public namespace
- `app.core.config.DATABASE_PATH` usage

**DO NOT do**:
- Combine or merge functions
- Add caching or connection pooling
- Change `get_conn()` to return a context manager
- Add `async`/`await`
- Change the SQLite file path resolution logic
- Add new tables or columns
- Fix bugs in the upload lock TTL logic
- Fix the N+1 enrichment in `enrich_upload_account_runtime_state`
- Change JSON column expansion behavior (e.g., `proxy_config_json` → `proxy_config`)

---

## 19. Phase 4F.1 Prompt Recommendation

When implementing Phase 4F.1, the prompt should specify:

**Goal**: Create `app/db/__init__.py` and `app/db/connection.py`. Move connection + helper + schema bootstrap verbatim. Add re-exports in `services/db.py`.

**STRICT RULES**:
- DO NOT modify any function bodies — verbatim copy only
- DO NOT change any SQL or PRAGMA statements
- DO NOT change `row_factory = sqlite3.Row`
- DO NOT move any repository functions (Groups B, C, D, E stay in `services/db.py` for now)
- DO NOT remove the original definitions from `services/db.py` until they are replaced by re-exports from the new module
- DO NOT create `schema.py`, `json_utils.py`, or `time_utils.py`
- The `_ensure_columns` local function inside `init_db()` is NOT a module-level symbol — do not hoist it

**Files to create**:
1. `backend/app/db/__init__.py` — empty
2. `backend/app/db/connection.py` — verbatim copy of connection/helper/schema block

**Files to modify**:
1. `backend/app/services/db.py` — add 5 re-export lines at top (after existing imports)

**Test file to create**:
1. `backend/tests/test_db_connection.py` — ~25 tests

**Validation**: `python -m pytest tests/test_db_connection.py -v` + full suite (0 new failures).

**Commit**: `"phase 4f1 extract db connection foundation"`

---

## 20. Definition of Done

Phase 4F planning is done when:

- [x] Every `db.py` function is categorized into Group A/B/C/D/E
- [x] Target module tree is defined (`app/db/` with 5 modules)
- [x] Extraction order is justified (4F.1→4F.2→4F.3→4F.4→4F.5)
- [x] `get_conn`/`init_db` risk is explicitly analyzed (sections 9, 10)
- [x] Thread-local connection risk is explicitly analyzed (section 10.2)
- [x] `enrich_upload_account_runtime_state` intra-dependency is documented (sections 3, 11)
- [x] Compatibility shim strategy is clear (section 7)
- [x] Test strategy covers all DB domains (section 14)
- [x] Mock/patch strategy is documented (section 15)
- [x] 14 production callers are inventoried (section 2)
- [x] No backend code changed
- [x] Docs updated truthfully (Planning only — no SHIPPED claims)

Phase 4F.1 implementation is ready to begin.
