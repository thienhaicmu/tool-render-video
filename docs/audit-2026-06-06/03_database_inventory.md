# 03 — Database Inventory

Database: SQLite at `data/app.db` (sole job state authority — Sacred Contract #7). No Alembic; migrations are a hand-rolled, additive-only system in [backend/app/db/migration_steps/](../../backend/app/db/migration_steps/) executed by [backend/app/db/migrations.py](../../backend/app/db/migrations.py).

---

## A. Connection model

[backend/app/db/connection.py](../../backend/app/db/connection.py) — 394 LOC.

| Helper | Lines | Purpose |
|---|---|---|
| `_can_write_sqlite(path)` | ~40 | startup writeability probe, sets WAL too |
| `get_conn()` | 101–108 | new `sqlite3.Connection`, row factory + WAL + `SYNCHRONOUS=NORMAL` + `FOREIGN_KEYS=ON` |
| `db_conn()` (ctxmgr) | 111–141 | transactional wrapper — auto-commit on normal exit, rollback on exception, always closes |
| `_thread_conn()` | 150–170 | thread-local persistent connection for render workers (hot-path) |
| `close_thread_conn()` | 173–181 | explicit cleanup of thread-local conn |
| `init_db()` | 202–369 | baseline schema + migration runner invoke |

WAL pragmas confirmed at lines 105-106 (`get_conn`) and 166-167 (`_thread_conn`).

**Sacred Contract #7 / Issue 2 (CLAUDE.md):** the two-pattern surface (`db_conn` + `_thread_conn`) is deliberate, with `_thread_conn` benchmarked ~165× faster per call than `db_conn` for the hot-loop `update_job_progress` writer. Unification is **deferred indefinitely** per `docs/review/SPRINT_7_7_BENCHMARK_PREP_2026-06-05.md` (referenced; not re-verified for this audit).

---

## B. Tables

All `CREATE TABLE` statements live in `connection.py::init_db()` plus the migration steps. No ORM.

### B.1 `jobs` — lines 208–220

| Column | Type | Default | Notes |
|---|---|---|---|
| `job_id` | TEXT | – | **PRIMARY KEY** |
| `kind` | TEXT NOT NULL | – | e.g. `render`, `download` |
| `channel_code` | TEXT NOT NULL | – | |
| `status` | TEXT NOT NULL | – | `queued/running/completed/failed/interrupted/cancelled` |
| `stage` | TEXT | `''` | frozen names: `QUEUED/DOWNLOADING/RENDERING/DONE/FAILED/CANCELLED` |
| `progress_percent` | INTEGER | `0` | |
| `message` | TEXT | `''` | |
| `payload_json` | TEXT | – | serialised `RenderRequest` |
| `result_json` | TEXT | – | output array (see H) |
| `created_at` | TEXT | `CURRENT_TIMESTAMP` | |
| `updated_at` | TEXT | `CURRENT_TIMESTAMP` | |
| `priority` | INTEGER | `0` | |
| `error_kind` | TEXT | – | structured error code for FE |
| `render_plan_json` | TEXT | NULL | added by Migration 0001 |

Indexes:
- `idx_jobs_updated (updated_at DESC, created_at DESC)`
- `idx_jobs_status_kind (status, kind)`

### B.2 `job_parts` — lines 225–244

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | INTEGER | – | PK AUTOINCREMENT |
| `job_id` | TEXT NOT NULL | – | logical FK → `jobs.job_id` (no SQL FK constraint, see I.4) |
| `part_no` | INTEGER NOT NULL | – | |
| `part_name` | TEXT NOT NULL | – | segment label |
| `status` | TEXT NOT NULL | – | frozen: `QUEUED/WAITING/CUTTING/TRANSCRIBING/RENDERING/DONE/FAILED/SKIPPED` |
| `progress_percent` | INTEGER | `0` | |
| `start_sec`, `end_sec`, `duration` | REAL | `0` | |
| `viral_score`, `motion_score`, `hook_score` | REAL | `0` | |
| `output_file` | TEXT | `''` | |
| `message` | TEXT | `''` | |
| `created_at`, `updated_at` | TEXT | `CURRENT_TIMESTAMP` | |
| UNIQUE | – | – | `(job_id, part_no)` |

Indexes: **NONE beyond the UNIQUE constraint.** See I.1.

### B.3 `creator_prefs` — lines 294–301

| Column | Notes |
|---|---|
| `id` | INTEGER PK, `CHECK(id = 1)` — singleton row |
| `prefs_json` | TEXT — JSON blob, contains nested `creator_context` key (Sprint 3) |
| `updated_at` | TEXT |

### B.4 `download_jobs` — lines 305–332

Per-platform downloader job log. Columns: `id (TEXT PK)`, `url`, `platform`, `status`, `progress`, `speed_str`, `eta_str`, `output_path`, `output_dir`, `filename`, `title`, `duration`, `height`, `fps`, `filesize`, `error_msg`, `created_at`, `updated_at`.

Indexes: `idx_dl_jobs_status`, `idx_dl_jobs_created`.

### B.5 `clip_feedback` — lines 335–352

User ratings for AI training. Columns: `id INT AUTOINCREMENT`, `job_id`, `part_no`, `channel_code`, `goal`, `rating CHECK(rating IN (-1, 1))`, `hook_type`, `clip_type`, `start_sec`, `end_sec`, `duration_sec`, `rated_at`. UNIQUE `(job_id, part_no)`.

Indexes: `idx_feedback_channel (channel_code, goal)`.

### B.6 `schema_versions` — [migrations.py:65-72](../../backend/app/db/migrations.py)

`version (INT PK)`, `name`, `applied_at`. Tracks applied migrations.

---

## C. Migration sequence

Runner is invoked from `init_db()` in `connection.py` — `main.py:231` on startup.

| Version | File | Effect |
|---|---|---|
| 0001 | [migration_steps/0001_jobs_add_render_plan_json.py](../../backend/app/db/migration_steps/0001_jobs_add_render_plan_json.py) | `ALTER TABLE jobs ADD COLUMN render_plan_json TEXT DEFAULT NULL` (idempotent via `PRAGMA table_info` guard) |
| 0002 | [migration_steps/0002_jobs_rewrite_groq_to_llm.py](../../backend/app/db/migration_steps/0002_jobs_rewrite_groq_to_llm.py) | Rewrites stored `payload_json`: `groq_analysis_enabled → llm_enabled`, `groq_model → llm_model`, `groq_content_language → llm_language`, `groq_min_quality_score → llm_min_quality`, `groq_selection_strategy → llm_mode`. Preserves existing `llm_*` values. |

**Migration safety:** additive-only (no DROP, no ALTER RENAME). Non-fatal on error (logged WARNING). Baseline schema in `connection.py` runs first; numbered migrations apply incremental changes.

**FINDING-D01 (LOW):** Only 2 migration files exist. Either the codebase is young or schema changes have been merged into the baseline `init_db()` (more likely). Phase 11 should consider establishing a forward-only migration discipline now to avoid baseline drift across machines.

---

## D. Repositories — connection-helper usage

| Repo | Helper used | Notes |
|---|---|---|
| `jobs_repo.py` | `db_conn` (HTTP) + `_thread_conn` (`update_job_progress`, `upsert_job_part` only) | Mixed pattern by design |
| `creator_repo.py` | `db_conn` | |
| `feedback_repo.py` | `db_conn` | |
| `download_repo.py` | `db_conn` (post-Sprint 5.4, commit `9347613`) | |

Public functions (high-level):
- `jobs_repo`: `upsert_job`, `update_job_progress`, `save_error_kind`, `update_render_plan`, `get_render_plan`, `delete_job`, `upsert_job_part`, `get_job`, `list_jobs`, `list_jobs_page`, `list_job_parts`, **`list_job_parts_bulk` (N+1 elimination)**, `clear_part_output`.
- `creator_repo`: `get_creator_prefs`, `upsert_creator_prefs`, `get_creator_context` (nested), `upsert_creator_context` (nested).
- `feedback_repo`: `upsert_clip_feedback`, `get_clip_feedback`, `list_feedback_for_channel`, `delete_clip_feedback`.
- `download_repo`: `create/update/get/list/delete_download_job`.

---

## E. Raw `sqlite3.connect(` callers

Grep across `backend/`:

| File:line | Status |
|---|---|
| `backend/app/db/connection.py:40, 103, 164` | **sanctioned** (`get_conn`, `_thread_conn`, write-probe) |
| `backend/app/features/render/engine/pipeline/db_backup.py:91, 93` | **sanctioned** (atomic `Connection.backup()` snapshot) |
| `backend/app/features/download/engine/cookie_extractor.py:173, 187` | **sanctioned** (read-only Chrome cookies DB) |
| `backend/check_perf.py:26` | **dev script**, imports `DATABASE_PATH` from config — uses same resolved path as runtime, safe per Sub-agent verification |

No leaked raw connections found in business code. Sacred Contract #7 holds.

---

## F. Data integrity rules

| Rule | Mechanism | Enforced at |
|---|---|---|
| `job_id` uniqueness | `PRIMARY KEY` | SQL |
| `job_id` is UUIDv4 | `uuid.uuid4()` at router.py:599 | Python only |
| `(job_id, part_no)` uniqueness | UNIQUE | SQL |
| `clip_feedback.rating ∈ {-1, 1}` | `CHECK` | SQL |
| `creator_prefs.id = 1` (singleton) | `CHECK` | SQL |
| Foreign keys | `PRAGMA foreign_keys = ON` | **enabled but no FK constraints defined** |

---

## G. Job state schema

`jobs.status`, `jobs.stage`, `job_parts.status` are all TEXT — value space is enforced **only** in Python (no `CHECK` constraints). Sacred Contracts #4 and #5 freeze these strings:

- Job stages: `QUEUED → DOWNLOADING → RENDERING → DONE` (+ `FAILED`, `CANCELLED`)
- Per-part: `QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE` (+ `FAILED`, `SKIPPED`)

**FINDING-D02 (MEDIUM):** Status enums live as bare strings in code with no SQL or `enum.Enum` enforcement. A typo on the writer side (`"compleated"`) writes silently and breaks every consumer. Two mitigations would help:
1. Use `enum.StrEnum` (or shared constants) in Python and **assert membership on write**.
2. Add SQL `CHECK(status IN (...))` to the tables — but this conflicts with the additive-only rule unless done via baseline rewrite of new installs.

Phase 8 will recommend.

---

## H. `result_json` shape (Sacred Contract #1)

CLAUDE.md mandates that every entry in `jobs.result_json` carry:
- `output_rank_score`
- `is_best_output`
- `is_best_clip`

Verified:
- **Written** at [features/render/engine/pipeline/pipeline_ranking.py:230, 237-238](../../backend/app/features/render/engine/pipeline/pipeline_ranking.py) (`False` defaults at init).
- **Read** at [routes/jobs.py:415, 419, 434](../../backend/app/routes/jobs.py).
- **Tested** in [backend/tests/test_pipeline_ranking.py:170-175](../../backend/tests/test_pipeline_ranking.py).

Other keys observed in `result_json` entries: `viral_score`, `motion_score`, `hook_score`, `output_score` (legacy alias), `final_score` (legacy alias), `source_title`, `title`, plus user-facing metadata (duration, dimensions, format).

**FINDING-D03 (LOW):** Legacy alias keys `output_score` and `final_score` still read by `routes/jobs.py:415` and `ai_visibility_summary.py:88`. Phase 4 should mark for cleanup, but only after FE consumers verified (Phase 7).

---

## I. Suspicious patterns

### I.1 Missing index on `job_parts.job_id` (HIGH)

[connection.py:225-244](../../backend/app/db/connection.py). The UNIQUE constraint `(job_id, part_no)` provides a composite index that *can* serve prefix lookups on `job_id`, **so this is not a true scan in practice on SQLite** (SQLite uses the leftmost column of a composite index for equality lookups). However, that index is implicitly created and the team may not realise it exists. Phase 8 should confirm with `EXPLAIN QUERY PLAN` against `SELECT … FROM job_parts WHERE job_id = ?`. If SQLite happens to pick a sequential scan because the optimiser hasn't run `ANALYZE`, performance falls off a cliff at scale.

### I.2 No `ANALYZE` ever runs (LOW)

No scheduled `ANALYZE`. With small dev DBs the planner often picks correctly, but on long-running prod-style DBs the planner can degrade. Cost: one statement at startup.

### I.3 No `VACUUM` cadence (LOW)

WAL with `SYNCHRONOUS=NORMAL` lets disk reuse through checkpointing, so a long-running database can grow without ever shrinking. Phase 11 roadmap should add a manual-trigger `/api/dev/db-vacuum` admin command.

### I.4 No SQL-level FK constraints (MED)

`PRAGMA foreign_keys = ON` is set but no `FOREIGN KEY` clauses exist on `job_parts.job_id` or `clip_feedback.job_id`. `delete_job()` does a manual cascade inside `db_conn` (transactional), so orphans should not occur **unless** a process crashes mid-transaction. The cleanup logic is correct; the missing constraint is a defence-in-depth gap.

### I.5 `render_plan_json` never pruned (LOW)

Full RenderPlan JSON kept indefinitely per job. Disk growth is linear with job count. No retention policy. Recommend Phase 11 add per-job retention (e.g., keep RenderPlan only for last N successful + all failed for forensic purposes).

### I.6 N+1 in history list — already fixed (LOW)

`list_jobs_page` originally iterated and called `list_job_parts` per row. Bulk loader `list_job_parts_bulk` ([jobs_repo.py](../../backend/app/db/jobs_repo.py)) replaces this. ✓ Healthy.

---

## J. Backup & cleanup

| Component | Status |
|---|---|
| `db_backup.py` (atomic snapshots via `sqlite3.Connection.backup()`) | ✓ Live, file under [features/render/engine/pipeline/db_backup.py](../../backend/app/features/render/engine/pipeline/db_backup.py). Triggers: per-N-job (default 5) and time-based (≥1h interval). Retention: 10 newest. Failure policy: silent catch (must never crash a render). |
| Scheduled `VACUUM` | None |
| `ANALYZE` | None |
| Old-job auto-prune | None |

---

## K. Summary table

| Concern | State |
|---|---|
| WAL mode | ✓ enabled, both helpers |
| Sacred Contract #7 (only `db/` opens raw conn) | ✓ holds; 4 file:line sites all sanctioned |
| Sacred Contract #1 (result_json keys) | ✓ written, read, tested |
| Frozen state names enforced | Python-side only; no SQL `CHECK` |
| FK constraints | absent; integrity via Python transactions |
| Backup | atomic snapshot, retention 10 |
| Cleanup | manual delete API only |
| Indexes | adequate for current scale (jobs.updated_at, status+kind, download status/created, feedback channel/goal); missing explicit `job_parts.job_id` |
| Migrations applied | 0001, 0002 |

End of 03_database_inventory.md.
