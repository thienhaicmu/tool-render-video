# PHASE_4F_5_UPLOAD_DOMAIN_REMOVAL_AUDIT.md

**Status**: PHASE 4F.5B SHIPPED — upload_engine.py deleted, channels.py decoupled, frontend /api/upload fetch calls removed
**Date**: 2026-05-22
**Branch**: `restructure/output-timeline-architecture`

---

## 1. Why uploads_repo Extraction Was Cancelled

The original Phase 4F plan called for `uploads_repo.py` (Group C, ~1,200 lines) to be extracted from `services/db.py` in Phase 4F.5. That plan is **cancelled**.

The reason: the upload feature domain has been identified as out of current project scope. Rather than extracting upload code into a new module (which would make it harder to delete later), the goal is to audit whether the upload domain is still actively wired into the running application, and if so, plan its orderly removal.

**uploads_repo.py will NOT be created.**

---

## 2. Audit Scope

All upload-related code across:
- `backend/app/services/db.py` — upload DB functions
- `backend/app/routes/upload.py` — upload API routes
- `backend/app/services/upload_engine.py` — upload execution engine
- `backend/app/routes/channels.py` — channel/profile bootstrap (uses upload_engine)
- `backend/app/main.py` — router registration
- `backend/app/services/dev_commands.py` — QA runner references
- `backend/static/js/upload-manager.js` — frontend upload manager UI
- `backend/static/js/upload-config.js` — frontend upload config UI
- `backend/static/js/upload-engine.js` — frontend upload engine helper
- `backend/static/index.html` — frontend script loading
- `backend/app/db/connection.py` — schema (init_db tables)

---

## 3. Search Commands Run

```
rg "upload_"                                    backend/app
rg "include_router.*upload|upload_router"       backend/app
rg "upload_account|upload_queue|upload_videos"  backend/app
rg "api/upload"                                 backend/static/js
grep "upload-manager|upload-config|upload-engine" backend/static/index.html
grep "CREATE TABLE.*upload"                     backend/app/db/connection.py
wc -l  backend/app/routes/upload.py
wc -l  backend/app/services/upload_engine.py
wc -l  backend/static/js/upload-manager.js
```

---

## 4. Upload DB Functions Inventory (still in services/db.py)

All functions remaining in `services/db.py` after Phases 4F.1–4F.4:

### Group C — Upload Domain (~1,000 lines remaining in services/db.py)

| Function | Lines | Called from |
|---|---|---|
| `_default_upload_profiles_root()` | private | `build_default_upload_profile_path` |
| `normalize_profile_path_value(profile_path)` | public | `routes/upload.py` |
| `build_default_upload_profile_path(platform, key)` | public | `routes/upload.py` |
| `ensure_upload_account_profile_path_fields(data)` | public | upload account CRUD |
| `_normalize_upload_account_row(row)` | private | account CRUD |
| `_normalize_upload_video_row(row)` | private | video CRUD |
| `_normalize_upload_queue_row(row)` | private | queue CRUD |
| `_normalize_upload_history_row(row)` | private | history CRUD |
| `_normalize_upload_scheduler_state_row(row)` | private | scheduler state |
| `_active_profile_conflict_statuses()` | private | runtime locks |
| `list_active_runtime_locks(...)` | public | `routes/upload.py` |
| `_set_account_lock_state(account_id, state)` | private | lock acquire/release |
| `release_upload_runtime_locks_for_queue(queue_id)` | public | `routes/upload.py` |
| `acquire_upload_runtime_lock(...)` | public | `routes/upload.py` |
| `enrich_upload_account_runtime_state(account)` | public | account list |
| `list_upload_account_rows(include_disabled)` | public | `routes/upload.py` |
| `get_upload_account_row(account_id)` | public | `routes/upload.py` |
| `get_upload_account(account_id)` | public | internal |
| `find_upload_account_profile_conflict(...)` | public | `routes/upload.py` |
| `create_upload_account_row(data)` | public | `routes/upload.py` |
| `update_upload_account_row(account_id, changes)` | public | `routes/upload.py` |
| `disable_upload_account_row(account_id)` | public | `routes/upload.py` |
| `get_upload_scheduler_state()` | public | `routes/upload.py` |
| `update_upload_scheduler_state(changes)` | public | `routes/upload.py` |
| `increment_upload_scheduler_running_count(delta)` | public | `routes/upload.py` |
| `create_upload_video_row(data)` | public | `routes/upload.py` |
| `list_upload_video_rows(...)` | public | `routes/upload.py` |
| `get_upload_video_row(video_id)` | public | `routes/upload.py` |
| `get_upload_video(video_id)` | public | internal |
| `update_upload_video_row(video_id, changes)` | public | `routes/upload.py` |
| `disable_upload_video_row(video_id)` | public | `routes/upload.py` |
| `add_upload_queue_item(...)` | public | `routes/upload.py` |
| `list_upload_queue(...)` | public | `routes/upload.py` |
| `get_upload_queue_item(queue_id)` | public | `routes/upload.py` |
| `update_upload_queue_item(queue_id, changes)` | public | `routes/upload.py` |
| `set_upload_queue_last_error(queue_id, error)` | public | `routes/upload.py` |
| `update_upload_queue_status(...)` | public | internal (queue state machine) |
| `mark_upload_queue_uploading(queue_id)` | public | `routes/upload.py` |
| `mark_upload_queue_success(queue_id, result)` | public | `routes/upload.py` |
| `mark_upload_queue_failed(queue_id, error)` | public | `routes/upload.py` |
| `cancel_upload_queue_item(queue_id)` | public | `routes/upload.py` |
| `insert_upload_history(...)` | public | `routes/upload.py` |
| `list_upload_history(queue_id, limit)` | public | `routes/upload.py` |

**Note**: These functions are NOT in any `app/db/*.py` module yet — they remain directly in `services/db.py`.

---

## 5. Route / API Usage Findings

### `backend/app/routes/upload.py` — **FULLY ACTIVE**

- **1,502 lines**, **42 API endpoints** under `/api/upload/`
- Registered in `main.py` via `app.include_router(upload_router)` (line 103)
- Imports **all 34** upload DB functions from `app.services.db`
- Also imports **11 functions** from `app.services.upload_engine`
- Also imports from `app.services.channel_service`

**Active endpoint groups**:
| Group | Endpoints | DB functions used |
|---|---|---|
| Proxy management | GET/POST/PATCH/DELETE `/proxies/`, `/proxies/{id}/test` | `list_proxy_pool_rows`, `create/get/update/delete_proxy_pool_row` |
| Account management | GET/POST/PATCH/DELETE `/accounts/`, test-proxy | `list/get/create/update/disable_upload_account_row`, `find_upload_account_profile_conflict` |
| Video library | GET/POST/PATCH/DELETE `/videos/`, `/videos/{channel}` | `list/get/create/update/disable_upload_video_row` |
| Upload queue | GET/POST/PATCH `/queue/`, hold/resume/cancel/run | `list/get/add/update/mark/cancel_upload_queue_item`, `set_upload_queue_last_error`, `insert_upload_history` |
| Upload history | GET `/history`, `/queue/{id}/history` | `list_upload_history` |
| Scheduler | POST/GET `/scheduler/start`, `/stop`, `/status`, `/tick` | `get/update_upload_scheduler_state`, `increment_upload_scheduler_running_count` |
| Legacy schedule | POST `/schedule`, `/schedule/start`, `/schedule/runs/{id}/ws` | `upload_engine.*` |
| Login | POST `/login/start`, `/login/check` | `upload_engine.*` |
| Worker orchestration | POST `/workers/register`, GET `/workers/next-job`, POST `/workers/complete` | `list_upload_queue`, `update_upload_queue_item` |

### `backend/app/routes/channels.py` — **ACTIVE (partial upload coupling)**

Imports from `upload_engine`: `load_upload_settings`, `save_upload_settings`, `ensure_upload_account_profile`, `bootstrap_portable_runtime_for_channel`. These are needed for channel profile bootstrap, which is also used by the render pipeline when setting up channels.

### `backend/app/main.py` — **ACTIVE**

- Line 16: `from app.routes.upload import router as upload_router`
- Line 103: `app.include_router(upload_router)`
- Both lines must be removed to deactivate the upload router.

---

## 6. Frontend / Static Usage Findings

### Loaded in `backend/static/index.html` (lines 1272–1277):
```html
<script src="/static/js/upload-config.js"></script>
<script src="/static/js/upload-manager.js"></script>
<script src="/static/js/upload-engine.js"></script>
```

### File sizes:
| File | Lines | Active API calls to `/api/upload/` |
|---|---|---|
| `upload-manager.js` | 5,397 | 31+ calls (accounts, videos, queue, history, scheduler, proxies) |
| `upload-config.js` | 713 | 2 calls (config/save, videos/{channel}) |
| `upload-engine.js` | 114 | 0 (helper utilities only) |

### `/api/upload/` calls found in `upload-manager.js`:
- `GET/POST /api/upload/accounts`
- `PATCH/DELETE /api/upload/accounts/{id}`
- `POST /api/upload/accounts/{id}/test-proxy`
- `GET /api/upload/videos`
- `POST /api/upload/videos/add`
- `PATCH/DELETE /api/upload/videos/{id}`
- `GET/POST /api/upload/queue`
- `PATCH /api/upload/queue/{id}`
- `POST /api/upload/queue/{id}/run`, `/hold`, `/resume`, `/cancel`
- `GET /api/upload/history`
- `GET /api/upload/queue/{id}/history`
- `GET/POST/POST /api/upload/scheduler/status`, `/start`, `/stop`
- `POST /api/upload/queue/retry-failed`
- `GET/POST/PATCH/DELETE /api/upload/proxies/{id}`
- `POST /api/upload/proxies/{id}/test`

---

## 7. Service / Orchestration Usage Findings

### `backend/app/services/upload_engine.py` — **ACTIVE** (1,793 lines)
- Playwright-based TikTok upload automation
- Used directly by `routes/upload.py` (11 imports) and `routes/channels.py` (4 imports)
- Contains: `upload_schedule`, `login_with_persistent_profile`, `check_login_with_persistent_profile`, `upload_one_video`, `execute_upload_run`, `create_upload_run`, `get_upload_run`, `list_upload_accounts`, `list_ranked_videos`, `load_channel_config`, `ensure_upload_account_profile`, `save_upload_settings`, `load_upload_settings`, `_resolve_video_input_dir`

### `backend/app/services/dev_commands.py` — **INCIDENTAL**
- References `upload_engine.py` and `routes/upload.py` as string file paths in QA runner routing tables (not imports). References are documentation/routing metadata inside the dev AI command system, not active callers.

### `backend/app/routes/channels.py` — **COUPLED** (partial)
- `load_upload_settings`, `save_upload_settings`, `ensure_upload_account_profile`, `bootstrap_portable_runtime_for_channel` are imported from `upload_engine`. These functions bootstrap the `account/upload_settings.json` and profile directory structure that channel setup depends on. The channel bootstrap path is used both by upload and by the render pipeline's channel selection.
- **Risk**: Removing `upload_engine.py` without auditing what `channels.py` still needs will break channel bootstrap.

### `backend/app/db/platform_repo.py` (Phase 4F.4) — **NOTE**
- The proxy pool CRUD functions were already extracted to `platform_repo.py` in Phase 4F.4.
- `routes/upload.py` imports `list_proxy_pool_rows`, `get_proxy_pool_row`, etc. from `app.services.db` (which re-exports from `platform_repo`). These ARE still active callers.
- **The proxy pool is part of the upload domain.** If the upload domain is removed, `platform_repo.py` becomes unused too, and can be removed in the same sweep.

---

## 8. Docs-Only References

The following docs reference the upload domain but are not code callers:
- `docs/restructure/PHASE_4F_DB_SPLIT_PLAN.md` — Group C, D descriptions and planned uploads_repo
- `docs/restructure/PHASE_4A_BACKEND_MODULARIZATION_PLAN.md` — original god-file audit
- `docs/review/TECHNICAL_DEBT_REPORT.md` — H1 (db.py god file) tracks progress

---

## 9. Active vs Dead Classification Table

| Symbol / File | Classification | Reason |
|---|---|---|
| All 43 upload DB functions in `services/db.py` | **A — ACTIVE** | Called by `routes/upload.py` (live registered route) |
| `routes/upload.py` (all 42 endpoints) | **A — ACTIVE** | Registered in `main.py`, called by frontend |
| `services/upload_engine.py` | **A — ACTIVE** | Imported by `routes/upload.py` and `routes/channels.py` |
| `static/js/upload-manager.js` | **A — ACTIVE** | Loaded in `index.html`, calls `/api/upload/` |
| `static/js/upload-config.js` | **A — ACTIVE** | Loaded in `index.html`, calls `/api/upload/` |
| `static/js/upload-engine.js` | **A — ACTIVE** | Loaded in `index.html` (helper, no direct API calls) |
| `app/db/platform_repo.py` | **A — ACTIVE** (via shim) | proxy pool is used by `routes/upload.py` |
| `upload_accounts` DB table | **A — ACTIVE** | Created in `init_db()`, used by account CRUD |
| `upload_queue` DB table | **A — ACTIVE** | Created in `init_db()`, used by queue CRUD |
| `upload_videos` DB table | **A — ACTIVE** | Created in `init_db()`, used by video CRUD |
| `upload_history` DB table | **A — ACTIVE** | Created in `init_db()`, used by history CRUD |
| `upload_runtime_locks` DB table | **A — ACTIVE** | Created in `init_db()`, used by lock acquire/release |
| `upload_scheduler_state` DB table | **A — ACTIVE** | Created in `init_db()`, seeded on startup |
| `upload_proxy_pool` DB table | **A — ACTIVE** | Created in `init_db()`, used by proxy pool CRUD |
| Upload references in `dev_commands.py` | **C — DOCS/HISTORICAL** | String paths in routing tables only, not live imports |
| `channels.py` upload_engine imports | **A — ACTIVE** (coupled) | Channel bootstrap depends on upload_engine settings functions |

**Conclusion: There is NO dead upload code. Everything is wired and active.**

---

## 10. Safe Removal Candidates

No symbol is purely dead. However, the following items can be removed **as a coordinated set** once the user confirms the upload domain removal decision:

| Item | Removal Phase | Pre-condition |
|---|---|---|
| `main.py` lines 16, 103 (upload_router import + include) | 4F.5A | Frontend upload removed or acceptable to break |
| `routes/upload.py` | 4F.5A | After main.py change |
| `static/js/upload-manager.js`, `upload-config.js`, `upload-engine.js` | 4F.5A | Simultaneously with route removal |
| upload script tags in `index.html` | 4F.5A | Simultaneously with route removal |
| `services/upload_engine.py` | 4F.5B | After confirming `channels.py` audit (see §11) |
| All upload DB functions in `services/db.py` (Group C) | 4F.5C | After routes and engine removed |
| Upload tables in `init_db()` (connection.py) | 4F.5D | LAST — only after data confirmed irrelevant |
| `app/db/platform_repo.py` | 4F.5C or 4F.5D | After proxy pool callers confirmed gone |

---

## 11. Items Requiring User Confirmation

### CONFIRM-1: Upload domain removal is definitive
> **Question**: Is the upload domain (TikTok publishing, queue management, scheduler, login) being permanently removed from this project? Or is it being deferred/paused?

### CONFIRM-2: channels.py upload_engine coupling
> `routes/channels.py` imports `load_upload_settings`, `save_upload_settings`, `ensure_upload_account_profile`, `bootstrap_portable_runtime_for_channel` from `upload_engine.py`. These functions manage the `account/upload_settings.json` and profile directories that channels use.
> **Question**: Should channel bootstrap (`channels.py`) be refactored to no longer depend on upload_engine? Or will channels.py also be removed/simplified?

### CONFIRM-3: Proxy pool (platform_repo.py)
> `platform_repo.py` (extracted in 4F.4) contains proxy pool CRUD which is exclusively used by `routes/upload.py`. If the upload domain is removed, `platform_repo.py` becomes dead code too.
> **Question**: Should `platform_repo.py` be deleted in the same sweep, or kept for possible future reuse?

### CONFIRM-4: DB table preservation
> Removing upload tables from `init_db()` is the highest-risk step. If any user has existing data in `upload_accounts`, `upload_queue`, `upload_videos`, etc., that data will be lost on next startup.
> **Question**: Is there existing production data in upload tables that needs to be preserved (migrated/exported) before table removal? Or are these tables always empty in practice?

### CONFIRM-5: upload_scheduler_state seed row
> `init_db()` seeds an `upload_scheduler_state` row on startup. Removing this seed is safe only after the scheduler route/loop is gone.

---

## 12. Recommended Deletion / Deprecation Phases

If user confirms removal (CONFIRM-1 = yes), the recommended order:

### Phase 4F.5A — Remove upload router + frontend (LOW RISK for render pipeline)
**Files to delete/modify**:
- `backend/app/main.py` — remove lines 16 and 103 (upload_router import + include)
- `backend/app/routes/upload.py` — delete file
- `backend/static/js/upload-manager.js` — delete file
- `backend/static/js/upload-config.js` — delete file
- `backend/static/js/upload-engine.js` — delete file
- `backend/static/index.html` — remove 3 `<script>` tags

**Effect**: Upload API endpoints return 404. Frontend upload UI disappears. Render pipeline is unaffected.

**Validates**: All remaining tests still pass with 8 pre-existing failures only.

### Phase 4F.5B — Remove upload_engine service + channels.py decoupling
**Pre-condition**: CONFIRM-2 answered. If `channels.py` still needs upload_engine functions, those functions must be extracted/inlined into `channels.py` or a new `channel_profile_service.py` before `upload_engine.py` is deleted.

**Files to delete/modify**:
- `backend/app/services/upload_engine.py` — delete file (after channels.py decoupled)
- `backend/app/routes/channels.py` — remove `upload_engine` imports, replace with inlined logic or new module

### Phase 4F.5C — Remove upload DB functions from services/db.py
**Files to modify**:
- `backend/app/services/db.py` — delete all 43 upload Group C function bodies
- Remove `from app.db.platform_repo import ...` re-exports if platform_repo is also being removed
- `backend/app/db/platform_repo.py` — delete file (if CONFIRM-3 = delete)
- `backend/tests/test_platform_repo.py` — delete file (if platform_repo deleted)

**Effect**: `services/db.py` drops from ~1,106 lines to ~80 lines (essentially only the re-export shim header).

### Phase 4F.5D — Remove upload tables from init_db() (HIGHEST RISK)
**Pre-condition**: CONFIRM-4 answered. Data preservation decision made.

**Files to modify**:
- `backend/app/db/connection.py` — remove 7 `CREATE TABLE IF NOT EXISTS upload_*` blocks from `init_db()`, remove `_ensure_columns` migration calls for upload tables, remove `INSERT INTO upload_scheduler_state` seed row

**Effect**: On next startup, upload tables no longer exist in new DBs. **Existing DB files are unaffected** (SQLite doesn't drop tables on restart — old tables simply become orphaned).

---

## 13. What Must NOT Be Removed Yet

Until user confirms each phase:

- `backend/app/routes/upload.py` — ACTIVE, must not be deleted
- `backend/app/services/upload_engine.py` — ACTIVE, must not be deleted
- `backend/app/main.py` upload router registration — ACTIVE
- All upload DB functions in `services/db.py` — ACTIVE, must not be deleted
- Upload tables in `init_db()` — must not be dropped
- `backend/app/db/platform_repo.py` — re-exported by shim, callers exist
- Frontend upload JS files — ACTIVE, served to browser

---

## 14. Test Strategy for Removal

### Phase 4F.5A test validation
After removing `routes/upload.py` + frontend:
1. Compile check: `python -m compileall app`
2. Full test suite must pass with same 8 pre-existing failures only
3. Confirm no tests import from `routes.upload` (currently zero)
4. Manual verify: render pipeline unaffected (render jobs still work)

### Phase 4F.5B test validation
After removing `upload_engine.py` + channels.py decoupling:
1. Verify `channels.py` still compiles and channel tests pass
2. `test_asset_pipeline.py` and other orchestration tests unaffected

### Phase 4F.5C test validation
After removing upload DB functions:
1. `test_db_compat_exports.py` (if it exists) — verify only non-upload names remain
2. Full suite still 8 pre-existing failures only
3. Optionally: delete `test_platform_repo.py` + `platform_repo.py` if proxy pool removed

### Phase 4F.5D test validation
After removing upload tables from init_db():
1. `test_db_connection.py::TestInitDb::test_creates_all_expected_tables` — **MUST be updated** (currently expects 10 tables including uploads; after removal expects 3 tables: jobs, job_parts, creator_prefs)
2. Full suite must still pass with same baseline

---

## 15. Final Recommendation

**The upload domain is 100% active. There is no dead code to safely delete without a coordinated removal.**

The upload domain spans:
- 1 route file (1,502 lines, 42 endpoints)
- 1 service file (1,793 lines, Playwright automation)
- ~1,000 lines of DB functions in services/db.py
- 6,224 lines of frontend JS
- 7 DB tables in init_db()
- 1 extracted repo module (platform_repo.py)

**Recommended next action**: User should confirm the 5 questions in §11. Once confirmed, Phase 4F.5A (route + frontend removal) is the natural starting point and has zero impact on the render pipeline.

**If removal is confirmed, the services/db.py upload functions should be deleted directly** (not extracted to uploads_repo.py first). Extracting to uploads_repo.py would be pure churn — the module would exist for one commit before being deleted.

**Phase 4F.5A can proceed immediately** once confirmation is received. It is a mechanical deletion with no behavior changes to the render pipeline.
