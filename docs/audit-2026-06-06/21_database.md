# 21 — Database Reference

Rebuilt from code on 2026-06-06. Deep audit in [03_database_inventory.md](03_database_inventory.md) and [15_database_review.md](15_database_review.md).

## Engine

SQLite at `data/app.db`. WAL mode + `SYNCHRONOUS=NORMAL` + `FOREIGN_KEYS=ON`. Connection helpers in [backend/app/db/connection.py](../../backend/app/db/connection.py):

- `db_conn()` — ctxmgr for HTTP path. Commits on exit, rolls back on exception.
- `_thread_conn()` — thread-local persistent connection for render hot path. ~165× faster per call (benchmark, Phase 1).
- `init_db()` — schema bootstrap + migration runner.
- DB fallback path probe at startup (Primary `data/app.db` → `LOCALAPPDATA` fallback if not writable).

## Tables

| Table | Purpose | Key columns |
|---|---|---|
| `jobs` | render + download jobs | job_id (PK), kind, channel_code, status, stage, progress_percent, payload_json, result_json, render_plan_json, error_kind, priority |
| `job_parts` | per-clip state | id (PK), job_id, part_no (UNIQUE compound), status, viral_score, motion_score, hook_score, output_file |
| `creator_prefs` | singleton brand context | id=1 (CHECK), prefs_json (nested `creator_context`) |
| `download_jobs` | platform downloader | id (PK), url, platform, status, output_path, filename, title, duration, height, fps, filesize |
| `clip_feedback` | user ratings | id, job_id, part_no (UNIQUE compound), rating (`CHECK in (-1,1)`), hook_type, clip_type, channel_code, goal |
| `schema_versions` | migration log | version (PK), name, applied_at |

## Indexes

| Table | Index | Backs |
|---|---|---|
| jobs | `idx_jobs_updated (updated_at DESC, created_at DESC)` | history paginated list |
| jobs | `idx_jobs_status_kind (status, kind)` | startup recovery filter |
| job_parts | `UNIQUE(job_id, part_no)` (implicit composite index) | per-job lookups via leftmost-prefix |
| download_jobs | `idx_dl_jobs_status` | currently UNUSED (Phase 8 DB02) |
| download_jobs | `idx_dl_jobs_created (created_at DESC)` | list ordered |
| clip_feedback | `idx_feedback_channel (channel_code, goal)` | channel summary |
| clip_feedback | `UNIQUE(job_id, part_no)` (implicit) | per-clip rating |

## Migrations

| Version | File | Effect |
|---|---|---|
| 0001 | `migration_steps/0001_jobs_add_render_plan_json.py` | additive column |
| 0002 | `migration_steps/0002_jobs_rewrite_groq_to_llm.py` | data rewrite (groq_* → llm_*) |

Strictly additive. Idempotent. Non-fatal on error (logged WARNING). Order-of-ops verified safe even under crash mid-loop (Phase 8 DB07).

## Integrity rules

| Rule | Where enforced |
|---|---|
| `job_id` UUIDv4 format | Python only (router.py:599) |
| stage / status enums | Python only — NO `CHECK(status IN (…))` (Phase 4 BR05) |
| FK from `job_parts.job_id` → `jobs.job_id` | Python only — no SQL FK (Phase 4 BR03) |
| FK from `clip_feedback.job_id` → `jobs.job_id` | Python only |
| `rating ∈ {-1, 1}` | SQL CHECK ✓ |
| `creator_prefs.id = 1` | SQL CHECK ✓ |

## Sacred Contract #1 keys

Every entry in `jobs.result_json` carries:
- `output_rank_score`
- `is_best_output`
- `is_best_clip`

Written at [pipeline_ranking.py:230, 237-238](../../backend/app/features/render/engine/pipeline/pipeline_ranking.py). Tested at [tests/test_pipeline_ranking.py:170-175](../../backend/tests/test_pipeline_ranking.py).

## Backup

[features/render/engine/pipeline/db_backup.py](../../backend/app/features/render/engine/pipeline/db_backup.py) uses `sqlite3.Connection.backup()` for atomic snapshots. Retention: 10 newest. Trigger: per-N-job (default 5) + time-based (≥ 1 h).

No `VACUUM`, no `ANALYZE`, no row-age pruning.

End of 21_database.md.
