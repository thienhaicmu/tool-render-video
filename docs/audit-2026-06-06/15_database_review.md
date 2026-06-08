# 15 — Database Review

Targeted analysis of query patterns, index coverage, transaction discipline, and known orphan/leak risks. Phase 1 [03_database_inventory.md](03_database_inventory.md) covered schema; this phase covers behavior.

---

## 1. All query shapes (exhaustive)

Every SQL statement executed by application code (not migrations) lives in `backend/app/db/*_repo.py`. Direct grep:

### `jobs_repo.py`

| Op | Statement | Connection | Notes |
|---|---|---|---|
| upsert | `INSERT INTO jobs … ON CONFLICT(job_id) DO UPDATE …` | `db_conn` (HTTP) | line 12 |
| update | `UPDATE jobs SET stage, progress_percent, message [, status] WHERE job_id = ?` | `_thread_conn` (hot path) | line 36 |
| update | `UPDATE jobs SET error_kind WHERE job_id = ?` | `db_conn` | line 52 |
| update | `UPDATE jobs SET render_plan_json WHERE job_id = ?` | `db_conn` (try/except) | line 61 |
| select | `SELECT render_plan_json FROM jobs WHERE job_id = ?` | `db_conn` (try/except) | line 81 |
| delete | `DELETE FROM job_parts WHERE job_id = ?` + `DELETE FROM jobs WHERE job_id = ?` | `db_conn` (atomic) | line 104 |
| upsert | `INSERT INTO job_parts … ON CONFLICT(job_id, part_no) DO UPDATE …` | `_thread_conn` (hot path) | line 112 |
| select | `SELECT * FROM jobs WHERE job_id = ?` | `db_conn` | line 141 |
| select | `SELECT * FROM jobs ORDER BY created_at DESC` (unbounded!) | `db_conn` | line 147 |
| select | `SELECT * FROM jobs ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?` | `db_conn` | line 153 |
| select | `SELECT * FROM job_parts WHERE job_id IN (…) ORDER BY job_id, part_no ASC` | `db_conn` | line 167 (bulk, N+1 fix) |
| select | `SELECT * FROM job_parts WHERE job_id = ? ORDER BY part_no ASC` | `db_conn` | line 191 |
| update | `UPDATE job_parts SET output_file='' WHERE job_id=? AND part_no=?` | `db_conn` | line 197 |

### `creator_repo.py`

| Op | Statement | Notes |
|---|---|---|
| select | `SELECT prefs_json FROM creator_prefs WHERE id = 1` | line 40 |
| upsert | `INSERT INTO creator_prefs (id=1, prefs_json) … ON CONFLICT DO UPDATE` | line 51 |

### `download_repo.py`

| Op | Statement | Notes |
|---|---|---|
| insert | `INSERT INTO download_jobs …` | line 27 |
| update | `UPDATE download_jobs SET … WHERE id = ?` | line 50 (dynamic columns) |
| select | `SELECT * FROM download_jobs WHERE id = ?` | line 57 |
| select | `SELECT * FROM download_jobs ORDER BY created_at DESC LIMIT ?` | line 65 |
| delete | `DELETE FROM download_jobs WHERE id = ?` | line 73 |

### `feedback_repo.py`

| Op | Statement | Notes |
|---|---|---|
| upsert | `INSERT INTO clip_feedback … ON CONFLICT(job_id, part_no) DO UPDATE` | line 40 |
| select | `SELECT … FROM clip_feedback WHERE job_id = ? AND part_no = ?` | line 72 |
| select | `SELECT … FROM clip_feedback WHERE channel_code = ? [AND goal = ?]` | lines 100, 112 |
| delete | `DELETE FROM clip_feedback WHERE job_id = ? AND part_no = ?` | line 134 |

That's **23 distinct SQL statements**. No JOINs anywhere — all per-table, all keyed by PK or by an indexed column. Good shape for a SQLite app.

---

## 2. Index coverage analysis

Effective indexes:

| Table | Index | Backs |
|---|---|---|
| jobs | `PK(job_id)` | every `WHERE job_id = ?` query |
| jobs | `idx_jobs_updated (updated_at DESC, created_at DESC)` | `list_jobs_page` (line 153) ✓ |
| jobs | `idx_jobs_status_kind (status, kind)` | startup recovery filter `recover_pending_render_jobs` |
| job_parts | `PK(id AUTOINC)` | rarely used |
| job_parts | `UNIQUE(job_id, part_no)` (implicit index) | `WHERE job_id = ?` via leftmost-prefix, `WHERE job_id IN (...)`, ON CONFLICT key for upsert |
| creator_prefs | `PK(id) CHECK(id=1)` | singleton — no scaling concern |
| download_jobs | `PK(id)` | per-id reads/updates |
| download_jobs | `idx_dl_jobs_status (status)` | currently unused — no query filters by status alone |
| download_jobs | `idx_dl_jobs_created (created_at DESC)` | `list_download_jobs ORDER BY created_at DESC LIMIT` ✓ |
| clip_feedback | `PK(id AUTOINC)` | rarely used |
| clip_feedback | `UNIQUE(job_id, part_no)` (implicit) | `WHERE job_id = ? AND part_no = ?` ✓ |
| clip_feedback | `idx_feedback_channel (channel_code, goal)` | `WHERE channel_code = ? [AND goal = ?]` ✓ |

**FINDING-DB01 (CORRECTION to Phase 1 D-I.1):** Phase 1's database inventory flagged a "missing index on `job_parts.job_id`" with HIGH severity. **This was incorrect.** SQLite's UNIQUE composite index on `(job_id, part_no)` serves any equality lookup on `job_id` alone via leftmost-prefix matching — this is documented behavior. No table scan. Index coverage is fine.

I retract that earlier HIGH-severity finding and replace it with: monitor in case the team ever introduces a `LIKE '%foo%'` or non-leftmost lookup that wouldn't be index-served.

**FINDING-DB02 (LOW):** `idx_dl_jobs_status` is currently unused (no query in `download_repo.py` filters by `status` alone). Either drop it OR add a "list active downloads" endpoint that filters by status — Phase 6 noted `/api/downloader/jobs` returns all jobs ordered by created_at with `LIMIT`, no status filter.

---

## 3. Hot path — render progress writes

[jobs_repo.py:36 update_job_progress](../../backend/app/db/jobs_repo.py) uses `_thread_conn` (thread-local persistent connection). [jobs_repo.py:112 upsert_job_part](../../backend/app/db/jobs_repo.py) same.

Pattern:
```python
conn = _thread_conn()
cur = conn.cursor()
cur.execute(...)
conn.commit()
```

This is correct under WAL: each transaction is short (one statement), WAL allows concurrent readers (the WS handler on a separate connection), and `_thread_conn` avoids per-call open/close overhead (the benchmark Phase 1 §A.1 cited from Sprint 7.7 prep showed `_thread_conn` ~165× faster than `db_conn` here).

**FINDING-DB03 (LOW):** Multiple `update_job_progress` callsites fire ~once per 3 s per active part during encode (the progress timer thread cadence per Phase 2). For a 60-min render with 10 parallel parts that's ~6,000 writes per render. WAL handles this. But: if a future change wraps these in `db_conn()` (Phase 1 / Issue 2 trigger), the cost is 6,000 × open+WAL-init+close cycles — measurable user-visible regression. Make sure any future "unify the two connection patterns" sprint runs the same benchmark.

---

## 4. Transaction discipline

`db_conn()` is a context manager that commits on normal exit and rolls back on exception. **Almost every helper inside also calls `conn.commit()` explicitly** ([jobs_repo.py:33, 49, 58, 76, 109, 138, 204](../../backend/app/db/jobs_repo.py); same pattern elsewhere).

**FINDING-DB04 (LOW):** Redundant `conn.commit()` calls inside `db_conn()` ctxmgr. The ctxmgr will commit on exit — the explicit `conn.commit()` is a no-op once the implicit commit ran. Not a bug; harmless. But it muddles the model: "is the ctxmgr the boundary or is `commit()` the boundary?". A future maintainer who removes the ctxmgr `commit` (thinking "the helper already does it") would lose data; a future maintainer who removes the helper `commit` (thinking "the ctxmgr does it") sees no behavior change. Asymmetric reversibility. Pick one pattern.

`_thread_conn()` is a raw connection — autocommit OFF (SQLite default). Hot-path writers explicitly call `conn.commit()` per statement. ✓ correct.

---

## 5. Atomic deletes (transaction safety)

[jobs_repo.py:104 delete_job](../../backend/app/db/jobs_repo.py):
```python
with db_conn() as conn:
    conn.execute("DELETE FROM job_parts WHERE job_id = ?", (job_id,))
    conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))
    conn.commit()
```

Both deletes happen inside one `db_conn()` ctxmgr → one transaction → atomic. ✓ (Phase 4 BR03 already confirmed.)

But the FK constraint is absent — so if a maintenance script (e.g., a future BI export) ever deletes from `jobs` directly without going through this helper, orphan `job_parts` rows survive. Defensive recommendation: add explicit `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE` to the next baseline rewrite of `job_parts`. Same for `clip_feedback.job_id`.

---

## 6. `SELECT *` and read column-projection

Every read query uses `SELECT *`. For 5–15 column tables this is fine; the cost is the marshalling per row, not the wire bytes.

**FINDING-DB05 (LOW):** if `result_json` ever becomes large (Phase 1 noted "no pruning"), `SELECT *` will start pulling MBs per row even when the caller only wanted `status`. Today the only "list" query that returns many rows is `list_jobs_page(limit, offset)` — already bounded. Acceptable for now.

Also note: `payload_json` and `render_plan_json` are unbounded TEXT columns that `SELECT *` pulls every time. Targeted column projection would be a meaningful improvement if any list-style endpoint ever takes off.

---

## 7. Unbounded query still exposed

[jobs_repo.py:147 list_jobs()](../../backend/app/db/jobs_repo.py): `SELECT * FROM jobs ORDER BY created_at DESC` — no LIMIT.

Phase 6 noted the FE explicitly *bans* this (`jobs.ts:184` documents the ban). But the helper is still exported and used by:

- ~~routes/jobs.py `GET /api/jobs`~~ (deprecated, returns the unbounded list)
- Possibly maintenance scripts (Phase 11 should grep). 

**FINDING-DB06 (MED):** as long as `list_jobs()` is reachable, a future bug or careless test will load the entire jobs table into memory. Either rename to `_dangerous_list_jobs_all()` to make the risk obvious, OR delete it and migrate the deprecated route to use `list_jobs_page(limit=10_000, offset=0)` with an explicit cap.

---

## 8. Migration tooling

Two migration steps applied (Phase 1 §C). Both are additive and idempotent:
- 0001 — `ALTER TABLE jobs ADD COLUMN render_plan_json` (guarded by PRAGMA table_info)
- 0002 — payload rewrite (Python-side JSON rewrite of stored rows, not a schema change)

The runner ([db/migrations.py](../../backend/app/db/migrations.py)) inserts into `schema_versions` after applying. On error it logs WARNING and continues — Phase 1 noted "non-fatal on error". Note that means: a partially-applied migration produces an inconsistent DB and the app boots happily — no startup gate.

**FINDING-DB07 (MED):** migration runner does not gate startup on migration success. If 0002's Python rewrite half-finishes (e.g., process killed mid-loop), some rows keep `groq_*` keys and others get rewritten. The next boot will retry and complete — but **only if** 0002 hasn't yet inserted itself into `schema_versions`. If it inserted before the loop completed, never retried. Need to verify the order:

Reading [migration_steps/0002_jobs_rewrite_groq_to_llm.py:90-122](../../backend/app/db/migration_steps/0002_jobs_rewrite_groq_to_llm.py): the loop iterates rows, writes each individually. The schema_versions insert happens *after* the loop (at [migrations.py:165](../../backend/app/db/migrations.py)) — so a crash mid-loop leaves 0002 unmarked and **gets retried** on next boot. ✓ safe.

Documenting for future maintainers: any *non-idempotent* migration step (e.g., a destructive ALTER) would NOT be safe under this model. Stay strictly additive.

---

## 9. Backup + cleanup

[features/render/engine/pipeline/db_backup.py](../../backend/app/features/render/engine/pipeline/db_backup.py): uses `sqlite3.Connection.backup()` API. Atomic. Retention 10 newest. Failure mode: silent-catch (per Sacred Contract — backup must never crash a render).

No scheduled `VACUUM`, no `ANALYZE`. WAL with `SYNCHRONOUS=NORMAL` recovers disk via checkpoints implicitly. For SQLite at the expected scale (single-user, ≤ 100k rows lifetime), `ANALYZE` is overkill.

**FINDING-DB08 (LOW):** add a one-shot `ANALYZE` at the end of `init_db()` so the planner has stats on first run. ~1 ms cost; nothing to lose.

---

## 10. Concurrency model summary

| Concern | Status |
|---|---|
| WAL mode | ✓ enabled in both `get_conn` and `_thread_conn` (Phase 1 §A) |
| WAL allows concurrent reads while a write transaction is open | ✓ — render thread writes via `_thread_conn`, WS handler polls via separate connections |
| Single writer constraint of SQLite | OK because all writes go through `_thread_conn` (render thread) or `db_conn` (HTTP handler) — both serialize via SQLite's per-DB write lock |
| Per-frame writer holding lock too long | NO — each `update_job_progress` is one statement + commit (~ms) |
| Lock contention measured? | NO — no benchmarks under load |

**FINDING-DB09 (LOW):** under stress (e.g., 4 concurrent renders all writing progress + 1 WS client polling), the SQLite write lock could ping-pong. WAL helps but doesn't eliminate. Recommend: instrument with a Prometheus counter on `db_conn` acquisition time (Phase 1 noted Prometheus is already integrated).

---

## 11. Summary

| # | Severity | Topic | Status |
|---|---|---|---|
| DB01 | n/a | Phase 1 "missing index" claim retracted | ✓ correct via leftmost-prefix |
| DB02 | LOW | `idx_dl_jobs_status` unused | drop or wire a status filter |
| DB03 | LOW | hot-path writer count | acceptable; document for future "unify" sprint |
| DB04 | LOW | redundant `conn.commit()` inside ctxmgr | cosmetic |
| DB05 | LOW | `SELECT *` reads pull unbounded TEXT cols | safe today; revisit if list endpoints grow |
| DB06 | MED | `list_jobs()` unbounded helper still exposed | rename or delete |
| DB07 | (MED reviewed → LOW) | migration runner not gating startup | verified safe via order-of-ops |
| DB08 | LOW | no `ANALYZE` ever runs | add to `init_db` finalizer |
| DB09 | LOW | no lock-contention instrumentation | add Prometheus histogram |

**No new HIGH or CRITICAL findings.** The DB layer is the most mature part of the system. The earlier Phase 1 "missing index" alarm is corrected here.

Cross-references:
- FK absence (Phase 4 BR03) — still recommended for next baseline rewrite.
- Status enums as TEXT (Phase 4 BR05) — still recommended as `enum.StrEnum` + SQL `CHECK`.
- `_thread_conn` vs `db_conn` two-pattern surface (Phase 1 §A.1, Issue 2 in CLAUDE.md) — defer per benchmark; this audit confirms the trade-off is sound.

End of 15_database_review.md.
