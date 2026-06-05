# DB Connection Model Audit — Sprint 5.4 (Sub-A)

**Date:** 2026-06-05
**Branch:** `feature/render-engine-upgrade`
**Baseline:** Pytest 2346 passed / 1 skipped / 0 failed @ `9347613` (Sprint 5.4 commit 2)

## Purpose

Close the CLAUDE.md "Issue 2 — Mixed DB Connection Model" item by documenting the post-Sprint-5.4 state, the per-call connection rationale that keeps `_thread_conn` alive, and the precise precondition for the future full unification.

## What changed in Sprint 5.4

| Commit | What |
|---|---|
| `4f5dd80` | Migration 0002 — `jobs.payload_json` `groq_*` → `llm_*` rewrite (separate audit doc). |
| `9347613` | `db/download_repo.py` — 5 sites migrated from raw `get_conn()` + manual close to `db_conn()` ctxmgr. Behaviour identical; exception-safety guarantee added. |
| `<this commit>` | CLAUDE.md fix: helpers live in `app/db/connection.py`, not `services/db.py`. Issue 2 status updated to PARTIALLY RESOLVED. Two audit docs added. |

## Current connection-helper surface

All four sanctioned constructors live in `backend/app/db/connection.py`:

| Helper | Line | Lifecycle | PRAGMAs |
|---|---|---|---|
| `get_conn()` | 101-108 | New `sqlite3.Connection`. Caller must `close()`. `timeout=30`, `row_factory=Row`. | `journal_mode=WAL`, `synchronous=NORMAL`, `foreign_keys=ON` |
| `db_conn()` (ctxmgr) | 111-141 | Wraps `get_conn()`; auto-commit on normal exit, rollback on exception, always closes. | same |
| `_thread_conn()` | 150-170 | Lazy-init `threading.local` cached connection. Health-check via `SELECT 1`, reopens on failure. Never auto-closes — caller must invoke `close_thread_conn()`. | same |
| `sqlite3.connect()` (raw) | sanctioned only inside `db/connection.py` and `services/db_backup.py` (snapshot ops) + `services/cookie_extractor.py` (browser cookie DBs, not `app.db`) | varies | varies |

`services/db.py` is a 50-line re-export facade after the Sprint 6 split — it owns no implementation. CLAUDE.md (Sacred Contract #7 Known Issue) used to claim helpers live there; corrected in this commit.

WAL mode is set on every connection open. Sacred Contract: do not change.

Sanction enforcement: `backend/tests/test_contract_db_sole_authority.py:36-42` walks the import graph and asserts no production file outside `db/connection.py`, `services/db_backup.py`, `services/cookie_extractor.py` calls `sqlite3.connect()` directly.

## Caller inventory (post Sprint 5.4)

### `_thread_conn()` — 2 production callers, both render hot path

| File:Line | Op | Frequency |
|---|---|---|
| `db/jobs_repo.py:37` | `update_job_progress` — `UPDATE jobs SET stage / progress` | Every progress tick (≥ per frame batch) during render |
| `db/jobs_repo.py:116` | `upsert_job_part` — `INSERT OR REPLACE INTO job_parts` | Per part state transition |

Released via `close_thread_conn()` at `orchestration/render_pipeline.py:1248` once the render run completes (success or failure).

### `db_conn()` ctxmgr — all bounded HTTP-path ops

| File | Sites |
|---|---|
| `db/jobs_repo.py` | 15, 53, 71, 90, 106, 142, 148, 159, 177, 192, 199 (every method except `update_job_progress` + `upsert_job_part`) |
| `db/creator_repo.py` | 38, 48 (Sprint 5.3 migration) |
| `db/feedback_repo.py` | 37, 69, 96, 132 (Sprint 5.3 migration) |
| `db/download_repo.py` | 5 sites (Sprint 5.4 commit `9347613`) |

### Raw `get_conn()` — internal infrastructure only

| File:Line | Purpose |
|---|---|
| `db/connection.py:130` | inside `db_conn()` ctxmgr itself |
| `db/connection.py:203` | inside `init_db()` baseline schema setup |
| `backend/check_perf.py` | dev-only perf check script |
| tests | direct connection construction for fixture seeding |

No production HTTP-path file holds a raw `get_conn()` after Sprint 5.4.

## Why `_thread_conn` stays

The original WAL-mode + HTTP-polling design (CLAUDE.md "Database Rules" section) is the load-bearing reason for the thread-local cache:

1. The render thread writes progress updates at high frequency (multiple per second across all parts).
2. The HTTP polling fallback (`GET /api/jobs/{id}` per Frozen API Contracts) is the reliability guarantee for Electron environments where WebSocket upgrades may fail.
3. WAL mode plus a persistent connection means: the writer's transaction does not block readers, and the writer pays the SQLite open cost once per render run instead of per progress tick.

If we replaced `_thread_conn` with `db_conn` (which calls `get_conn` + close on every invocation), every progress tick would re-open + WAL-init the SQLite connection. That cost has not been benchmarked, and the audit ledger has no recorded incidents from the current mixed model — so the conservative call is to leave `_thread_conn` in place until we can measure.

## Decision

**Sub-A scope:** audit doc (this file) + `download_repo` parity migration (commit `9347613`) + CLAUDE.md fix. DEFER full `_thread_conn` → `db_conn` unification.

**Precondition for the future unification (own sprint):**
1. Per-frame progress-write benchmark on a representative render run with WAL on a SATA SSD.
2. Confirm `db_conn()` cost per call is < 1ms (or the cost is amortised by batching progress writes).
3. Audit that no render-thread reuse pattern (e.g. ThreadPoolExecutor) breaks `_thread_conn` reuse semantics if the unification is reversed later.

Until then, additions to either pattern stay subject to CLAUDE.md "Do not add a third model" rule. The contract test guards the raw `sqlite3.connect()` boundary.

## What was OUT of scope this sprint

- `_thread_conn` → `db_conn` migration of the two hot-path callers (deferred per above).
- Renaming `_thread_conn` → `render_thread_conn` for clarity (cosmetic; defer).
- Removing the legacy `conn.commit()` calls inside `db_conn() as conn:` blocks (auto-commit makes them redundant; deferred per `creator_repo.py:5-7` precedent).

## Cross-references

- Sprint 5.4 Planner brief and findings: this conversation's plan stage
- `docs/review/MIGRATION_0002_GROQ_TO_LLM_2026-06-05.md` — sibling Sub-B audit doc
- `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` — Sprint 5.3 precursor audit
- `CLAUDE.md` "Known Issue — Mixed Connection Model" — status updated
- `CLAUDE.md` "Issue 2 — Mixed DB Connection Model" — status updated
- `backend/tests/test_contract_db_sole_authority.py` — boundary enforcement
