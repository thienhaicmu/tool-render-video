# Batch 10 Closure Ledger (2026-06-06)

Append-only audit ledger for the Batch 10 series of closures landed on
`feature/ai-workflow-upgrade` between commits `a5793ef` and `76ce41a`.
Six LOW-tier findings closed plus one FE smoke-test gap plus one DB
retention infrastructure shipment plus one live end-to-end verification.

Replaces the older `docs/review/AUDIT_2026-06-02_followup_*.md` ledger
convention — that folder was archived as part of the Phase 1-18 backend
feature-layer migration (`e641a21`). New closure entries live next to
the audit they close.

---

## Scope

| Dimension | Before Batch 10 | After Batch 10 |
|-----------|-----------------|----------------|
| Branch position | 29 commits ahead of `f3b6858` | 36 commits ahead of `f3b6858` |
| Backend tests   | 575 / 575           | 621 / 621              |
| Frontend tests  | 390 / 390           | 403 / 403              |
| Total           | 965                 | 1024                   |
| Open LOW findings | 6 (BR10-BR15)     | 0                      |
| Audit gap items shipped | —             | DB retention env-gate (ST-12) |

All HIGH and MED audit findings had already been closed in Batches 1–9.
Batch 10 cleared the LOW tier plus the ST-13 FE smoke-test gap and
shipped two pieces of infrastructure (DB lock-acquire histogram + DB
row retention env-gate) that the audit had filed for the medium-term
roadmap (DB09, MT-7).

---

## Closures

### BR10 — `_thread_conn` leak on pre-pipeline thread death

- **Source:** [11_bug_risk_report.md FINDING-BR10](11_bug_risk_report.md)
  (PROBABLE, MED) — restated as ST-14 in [27_future_roadmap.md](27_future_roadmap.md).
- **Risk:** worker thread dies BEFORE `run_render_pipeline` reaches its
  outer try (e.g., during `setup_render_pipeline` or `prepare_output_dir`)
  → the existing `close_thread_conn()` at `render_pipeline.py:1352`
  never runs → cumulative SQLite handle leak on long-lived processes.
- **Fix shipped (`a5793ef`):** belt-and-suspenders `close_thread_conn()`
  in `_common.process_render`'s own `finally`. Idempotent with the
  existing pipeline cleanup. Lives at
  [backend/app/features/render/routers/_common.py](../../backend/app/features/render/routers/_common.py).
- **Tests:** 3 regression tests in
  [tests/test_process_render_thread_conn_safety.py](../../backend/tests/test_process_render_thread_conn_safety.py)
  — pre-pipeline death, happy path, double-fault tolerance.

### DB09 / ST-15 — DB lock-contention not instrumented

- **Source:** [15_database_review.md FINDING-DB09](15_database_review.md)
  (LOW) — restated as ST-15 in the roadmap.
- **Risk:** under concurrent renders, the SQLite write-lock ping-pong
  was invisible to operators — no histogram, no counter, no signal.
- **Fix shipped (`a5793ef`):** new Prometheus histogram
  `db_conn_acquire_seconds{role}` labelling the two production code
  paths (`db_conn` HTTP-path ctxmgr and `_thread_conn` render hot path).
  Cache hits skip observation; first-opens and stale re-opens are
  observed. Lives at
  [backend/app/services/metrics.py](../../backend/app/services/metrics.py)
  and [backend/app/db/connection.py](../../backend/app/db/connection.py).
- **Live evidence (smoke 2026-06-06):**
  ```
  db_conn_acquire_seconds_count{role="db_conn"}      = 18
  db_conn_acquire_seconds_count{role="_thread_conn"} = 4
  ```
- **Tests:** 3 in
  [tests/test_db_conn_acquire_metrics.py](../../backend/tests/test_db_conn_acquire_metrics.py).

### DB05 / MT-7 / ST-12 — DB row retention shipped (env-gated)

- **Source:** [15_database_review.md FINDING-DB05](15_database_review.md)
  + [27_future_roadmap.md MT-7](27_future_roadmap.md). Batch 10 picked
  this up earlier than the roadmap suggested because the same DB-hygiene
  combo was already touching `db_conn` and `_thread_conn`.
- **Risk:** `jobs.render_plan_json` and `result_json` grow indefinitely;
  no auto-prune. Linear disk growth with job count.
- **Fix shipped (`a5793ef`):** new `prune_old_jobs(max_age_days)` in
  [backend/app/services/maintenance.py](../../backend/app/services/maintenance.py)
  wired into the periodic cleanup loop in
  [backend/app/main.py](../../backend/app/main.py).
  Gated by `JOB_RETENTION_DAYS` env (default `0` = off — feature is
  opt-in per the desktop offline-first stance). Active jobs (`running`,
  `queued`) are NEVER pruned regardless of age — Sacred Contract 7.
- **Tests:** 6 in
  [tests/test_maintenance_prune_old_jobs.py](../../backend/tests/test_maintenance_prune_old_jobs.py).

### BR12 — Resume disk-truth vs DB-truth invariant

- **Source:** [11_bug_risk_report.md FINDING-BR12](11_bug_risk_report.md)
  (ASSUMPTION, LOW). The audit asked for verification and documentation.
- **Outcome:** **NOT A BUG.** Resume in `part_renderer.py` uses
  `final_part.exists() + ffprobe` (disk truth), NOT the DB `output_file`
  column (which defaults to `''` and may be stale). The audit's worry
  was that an empty-string `output_file` could mislead a future check;
  in practice no resume-skip predicate reads the DB column at all.
- **Closure shipped (`e096cd8`):** code comment explaining the
  disk-truth invariant + 4 AST-based regression guards in
  [tests/test_resume_disk_vs_db_invariant.py](../../backend/tests/test_resume_disk_vs_db_invariant.py)
  that lock the contract — a future refactor that re-introduces a
  `_existing_part_info.get("output_file")` read will fail the test.

### BR13 — Retry semantic for `render_plan_json`

- **Source:** [11_bug_risk_report.md FINDING-BR13](11_bug_risk_report.md)
  (ASSUMPTION, LOW). Audit asked: does retry overwrite the plan or
  reuse it?
- **Outcome:** **NOT A BUG.** Retry semantic is "fresh plan per retry"
  — `retry_failed_parts` enqueues with `resume_from_last=True`; the
  pipeline runs LLM Call 1 + Call 2 again and
  `update_render_plan(job_id, new_plan)` overwrites the stored blob.
  This is the correct behaviour for creator-context updates between
  retries.
- **Closure shipped (`e096cd8`):** docstring on `retry_failed_parts` in
  [backend/app/features/render/routers/lifecycle.py](../../backend/app/features/render/routers/lifecycle.py)
  documenting the semantic + 7 persistence-layer regression tests in
  [tests/test_render_plan_persistence.py](../../backend/tests/test_render_plan_persistence.py)
  that pin overwrite-on-write, NULL-on-clear, last-write-wins, etc.

### BR11 — Empty AI Summary card with no explanation

- **Source:** [11_bug_risk_report.md FINDING-BR11](11_bug_risk_report.md)
  (PROBABLE, LOW). Original audit blamed
  `attach_ai_visibility_summaries` but the FE doesn't actually consume
  its output — the visible bug is in `/api/jobs/{id}/ai-summary` +
  `StepResults.tsx`.
- **Risk:** when result_json is missing, the response is
  `{available: false}` but the FE renders the card based on truthiness
  of the object — empty card with no message.
- **Fix shipped (`18090d6`):**
  - Backend: response now carries `ai_status: "ok" | "no_ranking" |
    "degraded" | "no_result"` + a human `status_message`.
  - Frontend: `StepResults.tsx` hides the card on `no_result` and
    renders a compact warning row with the message on `no_ranking` /
    `degraded`. Backward-compat: `available` boolean preserved.
- **Live evidence (smoke 2026-06-06):**
  ```json
  {
    "available": true,
    "ai_status": "degraded",
    "status_message": "Partial AI analysis available — ranking is present but the story / director hint is missing.",
    "best_part_no": 1,
    "best_score": 75.1
  }
  ```
- **Tests:** 6 in
  [tests/test_jobs_ai_summary_status.py](../../backend/tests/test_jobs_ai_summary_status.py)
  + new `ai_status` type in
  [frontend/src/api/jobs.ts](../../frontend/src/api/jobs.ts).

### TEST09 / ST-13 — FE smoke test gap

- **Source:** [16_test_audit.md TEST09](16_test_audit.md) +
  [27_future_roadmap.md ST-13](27_future_roadmap.md).
- **Risk:** several load-bearing FE surfaces had no smoke tests —
  `RenderSocketClient` reconnect, `DownloaderScreen` paste flow,
  `SettingsScreen` Creator Context form CRUD.
- **Closure shipped (`4a5c29d`):** 3 new Vitest files, 13 tests total:
  - [tests/render-socket-client.test.ts](../../frontend/tests/render-socket-client.test.ts) — mocks
    global WebSocket, drives reconnect state machine (7 tests).
  - [tests/downloader-screen-paste.test.tsx](../../frontend/tests/downloader-screen-paste.test.tsx) — paste
    flow, validation, batch submission (3 tests).
  - [tests/settings-creator-context-form.test.tsx](../../frontend/tests/settings-creator-context-form.test.tsx) — form
    hydration, save success, save failure (3 tests).
- **Deferred from audit's list:** RenderWorkflow step nav (heavy
  hook/store coupling, low ROI without refactor) and history pagination
  (already covered by `job-list-pagination.test.tsx`).

### BR15 — Whisper model never unloaded

- **Source:** [11_bug_risk_report.md FINDING-BR15](11_bug_risk_report.md)
  (CONFIRMED, LOW).
- **Risk:** plain-dict caches at `whisper.py:_MODEL_CACHE` and
  `adapters.py:_FW_MODEL_CACHE` — mixing `tiny` (preview) and
  `large-v3` (render) keeps both resident, multi-GB RAM held without
  upper bound.
- **Fix shipped (`36aa662`):** both caches converted to `OrderedDict`
  LRU with cap 2 (configurable via `WHISPER_MODEL_CACHE_MAX` and
  `FW_MODEL_CACHE_MAX`). MRU touch on hit, evict LRU on insert past
  cap. Defensive `_release_*_model` helpers drop refs + best-effort
  CUDA cleanup. Two new public helpers
  `unload_all_whisper_models` / `unload_all_fw_models` for future
  shutdown / maintenance use.
- **Tests:** 10 in
  [tests/test_whisper_model_lru.py](../../backend/tests/test_whisper_model_lru.py).

### BR14 — `prune_render_cache` vs concurrent cache write race

- **Source:** [11_bug_risk_report.md FINDING-BR14](11_bug_risk_report.md)
  (PROBABLE, LOW).
- **Risk:** the 4 cache writers in
  [pipeline_cache.py](../../backend/app/features/render/engine/pipeline/pipeline_cache.py)
  used raw `Path.write_text` / `shutil.copy2`. The periodic prune
  (every 30 min) could observe a partially-written file and unlink it
  — writer's flush then fails (Windows: sharing violation) or writes
  into orphaned inode (POSIX).
- **Fix shipped (`1327275`):**
  - Two new helpers `_atomic_write_text` and `_atomic_copy2` stage
    bytes into a `.tmp` sidecar and `os.replace` into place (atomic
    on every supported platform).
  - All four `_*_cache_put` paths route through them.
  - Belt-and-suspenders: `prune_render_cache` now skips `.tmp` files
    entirely.
- **Live evidence (smoke 2026-06-06):** zero `.tmp` orphans across the
  4 cache subdirs after a full render.
- **Tests:** 7 in
  [tests/test_pipeline_cache_atomic_write.py](../../backend/tests/test_pipeline_cache_atomic_write.py).

---

## Live verification (smoke 2026-06-06)

A 25-second end-to-end render against the same baseline video as the
earlier 2026-06-06 smoke test confirmed every closure that touches a
runtime code path.

Full report: [SMOKE_TEST_2026-06-06_BATCH10.md](SMOKE_TEST_2026-06-06_BATCH10.md).
Driver: [backend/scripts/smoke_test_2026-06-06_batch10.py](../../backend/scripts/smoke_test_2026-06-06_batch10.py).

Job `0eb3fc98-0164-421d-ba48-3c922fd1e778` reached terminal status
`completed` in 25 s wall-clock (Whisper cache hit from baseline smoke).
Output: 1 clip, 41 MB MP4, `viral_score=85`, `output_rank_score=75.1`,
`failed_parts=[]`.

Sacred Contracts spot-checked live: #1 (result_json keys),
#4 / #5 (stage and part status names), #7 (DB sole authority),
#8 (qa_pipeline not bypassed) — all green.

---

## Commits (batch ordering)

```
a5793ef  feat(db):       Batch 10A — _thread_conn leak-safe, db_conn metrics, env-gated job prune
e096cd8  docs(render):   Batch 10B — pin resume + retry invariants (BR12, BR13)
18090d6  feat(ai-summary): Batch 10C — explicit ai_status, hide empty card (BR11)
4a5c29d  test(frontend): Batch 10D — FE smoke coverage (ST-13 / TEST09)
36aa662  feat(whisper):  Batch 10E — LRU eviction for both model caches (BR15)
1327275  fix(cache):     Batch 10F — atomic-rename cache writes + tmp-aware prune (BR14)
76ce41a  docs(smoke):    Batch 10G — driver + live-evidence smoke report for 10A-F
```

---

## Not closed / deferred

- **MT-1** (`services/dev_commands.py` 1542-LOC decomposition) — out of
  scope; 3–6 month effort per the audit roadmap.
- **MT-2** (`models/schemas.py` split) — same.
- **MT-3** through **MT-7** — see [27_future_roadmap.md](27_future_roadmap.md).
- **Audit "investigation needed"** items beyond BR12 / BR13 — none remain.
- The FE `RenderWorkflow` step-navigation test from ST-13's wishlist —
  deferred because the component has heavy hook/store coupling that
  would require an extraction pass to test cheaply. Manual smoke
  covers it adequately for now.

---

## Branch position recommendation

`feature/ai-workflow-upgrade` is now 36 commits ahead of `f3b6858`
(which itself was the merge base from the previous cycle, not `main`).
A merge plan back to `main` is outside the scope of this ledger; this
ledger records what was done and leaves the merge decision to the
next conversation.

When that merge plan is drafted, this ledger plus
[SMOKE_TEST_2026-06-06_BATCH10.md](SMOKE_TEST_2026-06-06_BATCH10.md)
together form the "what changed and why it's safe" appendix.

---

# Addendum — Batches 10H through 10M (2026-06-06)

Six follow-on closures landed on `feature/ai-workflow-upgrade` after
the original ledger entry. The branch is now **44 commits ahead** of
`f3b6858`. BE: 680 / 680. FE: 403 / 403. The original
"Not closed / deferred" section above is now partly stale — MT-1, MT-2,
MT-5, MT-6 have all closed; the addendum below records what shipped.

## Scope delta (vs original entry)

| Dimension | Original entry (Batch 10G) | Addendum (Batch 10M) |
|-----------|---------------------------|----------------------|
| Branch position    | 36 ahead of `f3b6858` | 44 ahead |
| Backend tests      | 621 / 621             | 680 / 680 |
| Frontend tests     | 403 / 403             | 403 / 403 |
| Total              | 1024                  | 1083 |
| Open audit MT items | MT-1 through MT-7    | MT-3, MT-4, MT-7-UI, MT-9 only |

## Closures

### FINDING-API05 — orphan `/api/channels/*` surface (Batch 10H)

- **Source:** [13_api_catalog.md](13_api_catalog.md), [11_bug_risk_report.md](11_bug_risk_report.md). MED.
- **Risk:** 6 endpoints with zero FE callers since the Phase 4F.5A
  upload-pipeline retirement. The audit's two options were "delete"
  or "build a management screen"; no product owner stepped forward
  for the second.
- **Fix shipped (`f611cda`):**
  - Deleted `backend/app/routes/channels.py` (475 LOC, 6 endpoints).
  - Removed the `channels_router` import + `include_router` mount
    from `main.py`.
  - Removed `ChannelCreate` / `ChannelInfo` from
    `app/models/schemas.py` and `list_channels()` from
    `services/channel_service.py` — both were only consumed by the
    deleted route.
  - `ensure_channel()` survived because render_pipeline + main.py
    startup still call it for the default `k1` channel folder.
- **Regression guard:** 4 tests in
  [tests/test_channels_surface_gone.py](../../backend/tests/test_channels_surface_gone.py).

### MT-2 — schemas.py decomposition (Batch 10I)

- **Source:** [27_future_roadmap.md MT-2](27_future_roadmap.md). 3–6
  month tier in the audit roadmap; closed earlier in practice.
- **Risk:** 570-LOC monolith hosting render, jobs, and (formerly)
  channel schemas. Hard to scan; small risk of accidental cross-domain
  coupling on future additions.
- **Fix shipped (`acf5452`):** split by domain:
  - `app/models/render.py`  — `PrepareSourceRequest`, `QuickProcessRequest`,
    `TextLayer*` helpers, `RenderRequest`, `RenderRequestStrict`.
  - `app/models/jobs.py`    — `JobStatusResponse`.
  - `app/models/schemas.py` — 39-LOC re-export shim, identity-preserving.
  - Sacred Contract #2 preserved by construction: every field,
    default, validator, and ConfigDict survives the move byte-for-byte.
- **Regression guard:** 8 tests in
  [tests/test_schemas_split_re_export.py](../../backend/tests/test_schemas_split_re_export.py)
  — re-export identity, no shim back-deps, field count pin (152),
  validator behaviour preserved, API-key stripping still fires.

### MT-1 — dev_commands.py decomposition (Batch 10J)

- **Source:** [27_future_roadmap.md MT-1](27_future_roadmap.md). The
  audit's biggest split target. 3–6 month tier; closed in one session
  via a coarse-grained boundary split.
- **Fix shipped (`ba548b4`):** the 1542-LOC monolith became the
  `app.services.dev` package (7 files, ~250 LOC average):
  - `_shared.py` (94)   — bottom-layer utilities.
  - `log.py` (385)      — `/log` + discovery / parsing / classification.
  - `bug.py` (307)      — bug classification + `/error` + `_LAST_ERROR` state
    with `get_last_error` / `set_last_error` accessors.
  - `registry.py` (276) — fix feature registry + target parsing.
  - `autofix.py` (430)  — `/fix` + autofix machinery.
  - `router.py` (236)   — dispatcher + simple commands.
  - `__init__.py` (15)  — re-export.
  - `dev_commands.py` (22) — re-export shim. `routes/devtools.py`
    keeps its existing `from app.services.dev_commands import …` line.
- **Design call:** `bug.py ↔ autofix.py` has a logical loop
  (`_choose_error` needs `_infer_code_targets`; `_cmd_fix` needs
  `_choose_error`). Resolved with lazy imports inside each function
  body — the package loads cleanly, runtime calls work.
- **Regression guard:** 23 tests in
  [tests/test_dev_commands_split.py](../../backend/tests/test_dev_commands_split.py)
  — shim identity, every sub-module loads, dispatcher routes each of
  the 8 prefixes correctly, pure-function behaviour pinned.

### MT-5 — render-pipeline integration test (Batch 10K)

- **Source:** [27_future_roadmap.md MT-5](27_future_roadmap.md). The
  audit's TEST02 finding explicitly punted on this because the
  orchestrator calls 15+ heavy dependencies.
- **Fix shipped (`bb13467`):** 3 integration tests at the coarsest
  safe boundary — six pipeline helper mocks (`prepare_render_source`,
  `run_manual_voice_tts`, `run_llm_pre_render`,
  `_llm_select_render_plan`, `run_render_loop`, `run_render_finalize`)
  let everything else run for real against a tmp SQLite database.
- **Asserts:**
  - 2-part ranking with the 3 Sacred Contract #1 keys on every entry
  - Top entry wins `output_rank=1` + `is_best_clip=True`
  - Direct sqlite read shows 2 `job_parts` rows persisted
  - Every `_emit_render_event` call uses kwargs only with
    `channel_code` / `job_id` / `event` / `step` at minimum
    (Sacred Contract #6)
- **Two shape gotchas documented for future maintainers:**
  - `output_mode="channel"` requires `render_output_subdir` — use
    `"manual"` for fake-source tests.
  - `run_render_loop.rows` is a list of LISTS (10-column shape), not
    dicts; orchestrator sorts by `int(x[3])` (part_no).
- **Regression guard:**
  [tests/test_render_pipeline_integration.py](../../backend/tests/test_render_pipeline_integration.py).

### FINDING-BR03 / MT-6 — FK + cascade on job_parts + clip_feedback (Batch 10L)

- **Source:** [11_bug_risk_report.md FINDING-BR03](11_bug_risk_report.md)
  + [15_database_review.md](15_database_review.md). Defense-in-depth
  gap; `delete_job` was already atomic via `db_conn` transaction, but
  a future maintenance script bypassing the helper could leave orphan
  rows.
- **Fix shipped (`4726955`):**
  - `init_db` baseline DDL now defines both child tables with
    `FOREIGN KEY (job_id) REFERENCES jobs(job_id) ON DELETE CASCADE` —
    new databases get the constraint directly.
  - Migration `0003_add_fk_cascade_to_job_parts_and_clip_feedback.py`
    retrofits existing DBs via the SQLite temp-table-rename recipe.
  - Defensive orphan cleanup before the FK-enforced INSERT so the
    migration runs cleanly even on a DB that had bypassed
    `delete_job` historically.
  - `idx_feedback_channel` re-created after the table rename.
  - Skipped `PRAGMA foreign_keys=OFF` because the migration runner
    has already opened a transaction (SQLite silently ignores PRAGMA
    mid-tx); the orphan-cleanup step makes the PRAGMA dance
    unnecessary.
- **Regression guard:** 6 tests in
  [tests/test_migration_0003_fk_cascade.py](../../backend/tests/test_migration_0003_fk_cascade.py).
  Includes a positive test that `DELETE FROM jobs` actually cascades
  to both child tables after migration.

### Stale-paths cleanup in dev/qa lookups (Batch 10M)

- **Source:** carry-over from Batch 10H / 10J — the dev-tools lookup
  tables referenced modules that no longer exist (deleted in Phase
  1-18, Phase 4F.5A, Batch 9, Batch 10H).
- **Why this matters:** every `/fix` category whose lookup pointed at
  a deleted file returned an empty list — the command was silently
  useless for roughly 60% of its routes. The lookups WERE static
  strings, so they never crashed; the failure mode was "no
  suggestion" without any error.
- **Fix shipped (`8788395`):**
  - `services/dev/registry.py`: dropped the entire upload / login /
    proxy / profile / scheduler domain trees. Render domain remains
    and now points at the feature-layer paths.
  - `services/dev/autofix.py`: rewrote 6 lookup tables; deleted
    `_apply_upload_selector_wait_autofix` (which patched the
    deleted `services/upload_engine.py`); folded the
    `upload_selector_wait` branch in `_cmd_fix` into the generic
    planned-fix path.
  - `services/dev/bug.py`: `_likely_functions_for_targets` now matches
    feature-layer paths (`features/render/router.py`,
    `engine/pipeline/render_pipeline.py`) instead of the pre-migration
    `routes/render.py` / `services/render_engine.py`.
  - `services/qa_runner.py`: reduced `_default_patch_targets` from 9
    dead-subsystem categories to 3 live ones; fallback now points
    at `services/dev/router.py` (post-MT-1) instead of the retired
    `services/dev_commands.py` monolith.
- **Net deletion:** ~166 lines of dead lookup tables removed.
- **Regression guard:** 16 tests in
  [tests/test_dev_paths_live.py](../../backend/tests/test_dev_paths_live.py):
  every path returned by every lookup table must exist on disk; a
  source-grep guard scans 7 files for 9 known-deleted paths outside
  comments / docstrings; the deleted
  `_apply_upload_selector_wait_autofix` helper is prevented from
  silently returning.

## Commits (addendum ordering)

```
f611cda  chore(channels):    Batch 10H — delete orphan /api/channels surface (API05)
acf5452  refactor(schemas):  Batch 10I — MT-2 split schemas.py by domain (additive)
b0d7917  fix(test):          flaky test_submit_job_increments_pending_count (1-liner)
ba548b4  refactor(dev):      Batch 10J — MT-1 decompose dev_commands.py into 6 sub-modules
bb13467  test(pipeline):     Batch 10K — MT-5 render-pipeline integration test
4726955  feat(db):           Batch 10L — MT-6 FK+cascade on job_parts and clip_feedback (BR03)
8788395  chore(dev):         Batch 10M — purge stale paths from dev-tools lookup tables
```

## Updated audit status

| Audit MT item | Status as of Batch 10M |
|---------------|------------------------|
| MT-1 dev_commands decomp | **CLOSED** (Batch 10J) |
| MT-2 schemas.py split    | **CLOSED** (Batch 10I) |
| MT-3 RenderRequest split | OPEN — HIGH-risk per CLAUDE.md, needs explicit Sacred Contract review session |
| MT-4 process_one_part extraction | OPEN — CRITICAL tier, needs planner |
| MT-5 pipeline integration test | **CLOSED** (Batch 10K) |
| MT-6 FK + cascade        | **CLOSED** (Batch 10L) |
| MT-7 DB row retention    | Backend **CLOSED** (Batch 10A as ST-12); UI toggle still open |
| MT-8 JobPart fields cleanup | Already closed in Batch 8 (C03) |
| MT-9 WS push redesign    | OPEN — LT-scale per audit |

The branch is in good shape for a merge plan. Of the open audit roadmap
items, only MT-3 / MT-4 carry blast-radius concerns that justify a
dedicated review session before implementation; MT-7-UI and MT-9 can
be picked up at leisure.
