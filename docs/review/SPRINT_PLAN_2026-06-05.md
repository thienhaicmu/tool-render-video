# SPRINT PLAN — Post-Merge Cleanup & Deferred Items Cycle

**Date:** 2026-06-05
**Branch baseline:** `main` @ `9b67da5` (post-merge of PR #6)
**Pytest baseline:** **2397 passed / 1 skipped / 0 failed** — verified on merged main
**Predecessor plan:** `docs/review/SPRINT_PLAN_2026-06-04.md` (CLOSED — all 6 sprints shipped, all P0/P1 items resolved or deferred with audit docs)
**Meta-finding rule:** Per `docs/review/SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md` — **index from `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` empirical rankings, NOT from pre-audit predictions.** Original SPRINT_PLAN §253-261 "Dự đoán P0" had a 1/4 validation rate; this plan is constructed from concrete artifacts (audit docs, code state, time-gated commitments) only.

---

## Context

The Sprint 1-6 migration roadmap closed on 2026-06-05 via PR #6 merge (commit `9b67da5`). The merge brought 47 commits to main, 16 sprint tags, 12 audit ledger entries, 2 DB migrations applied (`schema_versions` rows 1 + 2 confirmed live on production DB). Backend smoke test passed (`/api/jobs` 200, `/api/downloader/jobs` 200, migration 0002 verified bit-identical with `_coerce_groq_to_llm` semantics — 7 stored rows correctly preserved `groq_only_mode`, 0 rows retained the 5 mapped `groq_*` keys).

This plan covers what remains: a backlog of items that were either (a) explicitly deferred during Sprint 1-6, (b) calendar-gated for a settling period, or (c) parked as separate scoping targets from audit docs.

**It does NOT introduce new optimisation predictions.** Every item below cites its source audit doc.

---

## Decision points for the user

| Question | Default recommendation |
|---|---|
| Branch strategy for new work | New feature branch `feature/cleanup-cycle` (substantive work); direct-to-main only for renames + calendar-gated removals |
| Sprint numbering convention | `Sprint 7.x` (continues Sprint 6 numbering) |
| Approval gate | Same as Sprint 1-6 — explicit user "go ahead" per sprint, Planner cycle for HIGH/CRITICAL |
| Audit-doc-per-sprint discipline | Continue — every sprint ships a closure doc under `docs/review/` |
| Calendar-gated items | Set GitHub issues with due dates so they don't get forgotten |

---

## Backlog inventory (source-cited)

| # | Item | Source audit doc | Risk tier | Gate type |
|---|---|---|---|---|
| 1 | Rename `motion_crop/legacy.py` → `motion_pixel_diff.py` | `DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §4 + Sprint 5.3 audit | LOW | None — ready to ship |
| 2 | Remove `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` flag | `SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` §"Deprecation timeline" | LOW | Calendar — **2026-07-05** (30-day settling from 2026-06-05) |
| 3 | N.1 Content-addressable ASS cache | `SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` §"Adjacent follow-up targets" + `SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md` §"Parked items" | MEDIUM | None — ready to scope |
| 4 | Sprint 6 O-4 Commit 2 — actual `raw_part` fuse | `SPRINT_6_O4_RAW_PART_SKIP_PREDICATE_2026-06-05.md` §"Commit 2 deferred plan" | CRITICAL | Data — telemetry fire-rate + manual visual review 3-5 samples |
| 5 | Sprint 6 O-4 motion-aware-crop sub-scope | Same doc §"Approved scope" | CRITICAL | Sequence — gated on item 4 |
| 6 | Delete `groq_*` schema alias fields + `_coerce_groq_to_llm` validator | `DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §1 + `MIGRATION_0002_GROQ_TO_LLM_2026-06-05.md` §"What this migration does NOT do" | HIGH | Release cycle — ≥ 1 production release after Migration 0002 |
| 7 | Retire `LLMSegment` + legacy `select_segments` + `_to_scored_dict` | `DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §3 | HIGH | Decision — flip `LLM_EMIT_RENDER_PLAN=1` default; ship for one release |
| 8 | Mixed DB connection unification (`_thread_conn` → `db_conn`) | `DB_CONNECTION_AUDIT_2026-06-05.md` §"Decision" | HIGH | Data — per-frame progress-write benchmark (3 explicit preconditions) |

**8 items.** No "Dự đoán P0" entries — every item has a concrete audit reference.

---

## Recommended Sprint 7.x roadmap

| Sprint | Item | Risk | Effort | Gate |
|---|---|---|---|---|
| **7.1** | Motion crop rename | LOW | ½d | None — GO immediately |
| **7.2** | Validation artifact flag removal | LOW | ½d | Calendar: 2026-07-05 |
| **7.3** | N.1 ASS content-addressable cache | MEDIUM | 1-2d | None — Planner cycle ready |
| **7.4** | Sprint 6 O-4 Commit 2 (raw_part fuse) | CRITICAL | 2-3d | Telemetry data + visual review |
| **7.5** | groq_* field + validator deletion | HIGH | 1d | Release cycle elapsed |
| **7.6** | LLMSegment retire | HIGH | 2-3d | Flag default flip decision |
| **7.7** | DB connection unification | HIGH | 1-2d | Per-frame benchmark |
| **7.8** | Sprint 6 O-4 motion-aware sub-scope | CRITICAL | 2d | After 7.4 settles |
| **Total** | 8 sprints | mixed | ~12d active + gates | net -800 LOC + reduced flag surface |

Order rationale: ship LOW-risk + no-gate items first to build momentum and let the calendar-gated work settle. Save CRITICAL-tier work for when telemetry justifies the visual-review cost.

---

## Sprint 7.1 — Motion crop rename (LOW)

**Source:** `DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §4 — *"the 'legacy' name in the SPRINT_PLAN recap was a misclassification. Recommend a future rename to `motion_pixel_diff.py`."*

**Scope:**
- Rename `backend/app/services/motion_crop/legacy.py` → `motion_pixel_diff.py`
- Update 5 import sites: `motion_crop/__init__.py:89-93`, `motion_crop/__init__.py:349, 443, 467`, `motion_crop/path.py:64,387`
- Audit doc `docs/review/SPRINT_7_1_MOTION_RENAME_2026-06-05.md` (closure record)

**Sacred Contract walk:** Pure rename — touches NO contract surface. Sacred Contract #5 (frozen stage names) unaffected. Sacred Contract #8 unaffected (qa_pipeline never references motion_crop internals).

**Tests:** Existing `tests/test_motion_crop_*.py` must continue to pass. Add source-pin assertion that `motion_pixel_diff` exists.

**Commit count:** 1 commit (rename + import updates + audit doc).

**Branch:** Could go direct to main given LOW risk + pure rename, OR `feature/cleanup-7-1`. Recommend direct-to-main if user agrees.

---

## Sprint 7.2 — Validation artifact flag removal (LOW, calendar-gated)

**Source:** `SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` §"Deprecation timeline" — *"`FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` is a transitional opt-in. Scheduled for removal 2026-07-05 (30-day settling period)."*

**Gate:** Calendar — **2026-07-05** (30 days from Sprint 6 P0 HIGH ship date 2026-06-05). If between now and then a consumer surfaces, pause the removal with a follow-up audit doc.

**Scope:**
- Delete `_FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` env reads from 4 sites: `render_pipeline.py`, `part_renderer.py`, `part_render_setup.py`, `part_render_encode.py`
- Simplify gate at `part_render_encode.py` from `if first AND (overlay OR validation):` to `if first AND overlay:`
- Update CLAUDE.md Performance Protections + Blast Radius Order entries
- Audit doc `docs/review/SPRINT_7_2_VALIDATION_FLAG_REMOVAL_<DATE>.md`

**Pre-gate check:** Grep all production logs (if accessible) for `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT=1` usage. If zero usage observed in the 30-day window, removal is safe.

**Sacred Contract walk:** Sacred Contract #2 implication — removing the opt-in is a behavior change for the (possibly empty) set of users who relied on it. The doc commits to this on the original ship date.

**Tests:** Update `tests/test_part_render_encode_base_clip_gate.py` — remove the `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` cases (4 tests).

**Commit count:** 1 commit.

**Branch:** Direct to main (LOW + calendar-gated, no surprises).

---

## Sprint 7.3 — N.1 ASS content-addressable cache (MEDIUM)

**Source:** `SPRINT_6_P1_INLINE_ASS_DEFER_2026-06-05.md` §"N.1 Content-addressable ASS cache"

**Scope:**
- Hash produced ASS body (SHA-256 of UTF-8 bytes)
- Lookup/write at `cache/ass/{sha256}.ass`
- Eliminate re-writes on re-renders of identical source+style
- Pure-additive next to W-2 in `part_asset_planner.py:597-623`
- TTL = same 72h as render cache (covered by Sprint 6 P1 `prune_render_cache`)

**Sacred Contract walk:** #1-8 all clean. New cache path under existing `APP_DATA_DIR/cache/` subtree — Sacred Contract #7 cross-subtree protection holds.

**Tests:**
- Hash determinism (same input → same path)
- Cache hit short-circuits the `srt_to_ass_*` call
- Cache miss writes the ASS file
- Integration with `prune_render_cache` (subdir-agnostic walk picks up `cache/ass/`)

**ROI honest estimate:** Zero on first render. ms-class on cache-hit re-renders. Real benefit: re-render workflows (subtitle style A/B testing, sub language switches) avoid re-running `srt_to_ass_bounce`. Audit row O-6 ranked this MEDIUM.

**Commit count:** 2 commits (cache helper + test integration).

**Branch:** `feature/cleanup-7-3-ass-cache` (substantive work, fresh branch).

---

## Sprint 7.4 — Sprint 6 O-4 Commit 2 raw_part fuse (CRITICAL)

**Source:** `SPRINT_6_O4_RAW_PART_SKIP_PREDICATE_2026-06-05.md` §"Commit 2 deferred plan"

**Gate (TWO conditions, BOTH required):**
1. **Telemetry data:** grep `raw_part_skip_eligible` from production render logs. Minimum 50 sample parts across at least 3 unique source videos. Predicate fire-rate ≥ 30% justifies the ship.
2. **Manual visual review:** 3-5 sample renders per Sprint Plan risk register line 302. Cover: (a) first-frame quality without `force_accurate_cut`, (b) audio sync at part boundaries, (c) duration accuracy ±0.35s vs current, (d) subtitle-disabled + base_clip-disabled config (the default skip case), (e) control render with `FEATURE_RAW_PART_SKIP=0`.

**Scope (per Sprint 6 O-4 audit Commit 2 plan):**
- NEW `render_part_from_source(source_path, start, dur, ...)` helper in `services/render/base_clip_renderer.py` (additive — `render_part_smart` signature stays frozen)
- Gate `cut_video()` call in `run_cut_stage` on `FEATURE_RAW_PART_SKIP and skip_predicate(...)`
- Replace Commit 1 telemetry log with actual skip + log marking the skip happened
- New env flag `FEATURE_RAW_PART_SKIP=0` default OFF, 30-day settling
- Mirror env reads at 5 sites
- 3-5 visual review samples archived
- Audit doc `docs/review/SPRINT_7_4_RAW_PART_FUSE_<DATE>.md`

**ROI per Commit 1 audit:** ~1.5 GB transient + ~12 min wall-time / 50-part subtitle-off render.

**Sacred Contract walk:** Most sensitive — #5 CUTTING upsert MUST stay unconditional even when `cut_video` bypassed; #6 events from `ctx.source_path` probes (`silence_trim_applied`, etc.) continue firing; #8 qa_pipeline reads `final_part` only (unaffected).

**Render Edit Protocol:** 9 steps mandatory. Step 5 baseline must match Step 8 plus the new test cases.

**Commit count:** Single combined commit (predicate wire + helper + flag + tests) to keep the gate atomic.

**Branch:** `feature/sprint-7-4-raw-part-fuse`.

---

## Sprint 7.5 — groq_* field + validator deletion (HIGH, release-gated)

**Source:** `DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §1 + `MIGRATION_0002_GROQ_TO_LLM_2026-06-05.md` §"What this migration does NOT do"

**Gate:** Migration 0002 must have run on every production DB. Operationally: wait for ≥ 1 production release cycle after this main branch is deployed. **Earliest safe ship: depends on release cadence.** Conservative: wait until 2026-07-15 (40 days after migration ships).

**Scope:**
- Delete 5 `groq_*` fields from `RenderRequest` in `schemas.py:364-379`: `groq_analysis_enabled`, `groq_model`, `groq_content_language`, `groq_min_quality_score`, `groq_selection_strategy`
- KEEP `groq_only_mode` + `groq_api_key` (no llm_* equivalent — Migration 0002 design)
- Delete `_coerce_groq_to_llm` validator at `schemas.py:466-482`
- Trigger frontend openapi-typescript regen → auto-cleanup `frontend/src/types/openapi-generated.ts`
- Update CLAUDE.md Sacred Contract #2 entry (additive-only is preserved because deletion happens AFTER all stored payloads were migrated)
- Audit doc `docs/review/SPRINT_7_5_GROQ_DELETION_<DATE>.md`

**Pre-gate verification:**
```sql
SELECT COUNT(*) FROM jobs WHERE
  payload_json LIKE '%groq_analysis_enabled%' OR
  payload_json LIKE '%groq_model%' OR
  payload_json LIKE '%groq_content_language%' OR
  payload_json LIKE '%groq_min_quality_score%' OR
  payload_json LIKE '%groq_selection_strategy%';
```
Must return 0 (migration 0002 deleted these keys).

**Sacred Contract walk:** #2 (additive) is the head-on contract. Argument: this is a controlled removal AFTER a migration eliminated the read-side dependency. Not a silent drop. Document the safety logic in the audit doc.

**Tests:**
- Existing `test_migration_0002_groq_to_llm.py::test_replay_parity_with_validator` will fail (it references `groq_*` field names) → update to verify direct `llm_*` deserialization
- Frontend regen + verify no production component references the 5 deleted types

**Commit count:** 2 commits (backend deletion + frontend regen).

**Branch:** `feature/sprint-7-5-groq-deletion`.

---

## Sprint 7.6 — LLMSegment retire (HIGH, decision-gated)

**Source:** `DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §3

**Gate:** Flip `LLM_EMIT_RENDER_PLAN=1` default ON, ship for one release. Without this, the legacy `select_segments` path is the production code path and `LLMSegment` is load-bearing.

**Scope (after flag flip):**
- Delete legacy `select_segments` from 4 providers: `claude_provider.py`, `gemini_provider.py`, `openai_provider.py`, dispatcher `__init__.py`
- Delete `LLMSegment` dataclass + `GroqSegment` alias from `parser.py:35, 55`
- Delete `_to_scored_dict` consumer from `llm_stage.py:263`
- Delete `_dict_to_segment` from `parser.py:213` + `parse_segment_response` from `parser.py:71`
- Update CLAUDE.md HIGH-tier entries
- Audit doc `docs/review/SPRINT_7_6_LLMSEGMENT_RETIRE_<DATE>.md`

**Pre-gate decision:** User explicitly approves the `LLM_EMIT_RENDER_PLAN=1` default flip. This is a separate small sprint preceding Sprint 7.6 itself.

**Sacred Contract walk:** #3 AI safety — every deletion happens in modules under `backend/app/ai/**`. Existing exception-handling must remain. New code path (RenderPlan-only) was extensively tested in Sprint 4. Audit doc cites the test coverage.

**Tests:**
- Update anti-import pins at `test_render_pipeline_llm_emit_flag.py:124` and `test_render_pipeline_render_plan_wiring.py:139` to reflect new state
- Delete obsolete tests that exercise the legacy `select_segments` path
- Add new integration test that asserts RenderPlan-only path produces the same final output

**Commit count:** 3-4 commits split by file group (providers / parser / consumer / docs).

**Branch:** `feature/sprint-7-6-llmsegment-retire`.

---

## Sprint 7.7 — DB connection unification (HIGH, benchmark-gated)

**Source:** `DB_CONNECTION_AUDIT_2026-06-05.md` §"Decision" — three explicit preconditions:
1. Per-frame progress-write benchmark on representative render run (WAL + SATA SSD).
2. Confirm `db_conn()` cost per call is < 1ms OR cost amortised by batching.
3. Audit that no render-thread reuse pattern (ThreadPoolExecutor) breaks `_thread_conn` reuse semantics.

**Scope (after benchmark passes):**
- Migrate `update_job_progress` + `upsert_job_part` in `db/jobs_repo.py:37, 116` from `_thread_conn()` to `db_conn()` ctxmgr
- Delete `_thread_conn` + `close_thread_conn` helpers from `connection.py:150-170`
- Update CLAUDE.md "Issue 2 — Mixed DB Connection Model" entry to RESOLVED
- Update CLAUDE.md "Performance Protections" section
- Audit doc `docs/review/SPRINT_7_7_DB_UNIFY_<DATE>.md`

**Pre-gate benchmark plan:**
- Run a representative 50-part render with `update_job_progress` instrumented for per-call latency
- Compare current `_thread_conn` vs proposed `db_conn` via env-flag toggle
- Measure: median + p95 latency; total render wall-time delta
- Pass criteria: db_conn p95 < 5ms; total wall-time delta < 1%

**Sacred Contract walk:** #7 (sole DB authority — preserved). Performance Protections section (WAL + polling concern — explicitly addressed by benchmark).

**Tests:**
- Update `tests/test_db_connection.py` to delete `_thread_conn` cases
- Add stress test for parallel-render `db_conn` calls

**Commit count:** 2-3 commits split by impl + test + doc.

**Branch:** `feature/sprint-7-7-db-unify`.

---

## Sprint 7.8 — Sprint 6 O-4 motion-aware-crop sub-scope (CRITICAL)

**Source:** `SPRINT_6_O4_RAW_PART_SKIP_PREDICATE_2026-06-05.md` §"Approved scope" — *"Motion-aware-crop=True deferred. Motion-aware branch could be added in a future Commit 3 once Commit 2 settles."*

**Gate:** Sprint 7.4 has shipped + 30-day settling on `FEATURE_RAW_PART_SKIP`.

**Scope:**
- Extend `render_part_from_source` (from Sprint 7.4) to handle the motion-aware branch
- Plumb `-ss/-t` through `render_motion_aware_crop` in `services/motion_crop/__init__.py:351-724`
- Add the motion-aware case to the predicate truth-table
- 3 additional visual review samples (motion-tracking continuity at part boundaries)
- Audit doc

**Risk:** This is the highest-risk item in the backlog. Motion tracking quality is user-visible and Subject identity carryover across cut boundaries was a known tricky area in Sprint 6.D-3.6b. Defer until Sprint 7.4 has stabilised in production.

**Commit count:** TBD per Planner cycle.

**Branch:** TBD.

---

## Cross-sprint protocol

Same as `SPRINT_PLAN_2026-06-04.md` line 270-280:

| File touched | Protocol |
|---|---|
| `render_pipeline.py`, `stages/part_renderer.py`, `part_render_finalize.py`, `motion_crop/__init__.py`, `motion_crop/path.py` + `path_scene.py`, `qa_pipeline.py` | Render Edit Protocol 9 bước, full pytest |
| `schemas.py` | Sacred Contract #2 — Sprint 7.5 deletion only AFTER release-gated verification |
| `routes/*.py` | Frozen API contracts — additive only |
| Database migrations | Additive only, NEVER DROP/RENAME |
| `data/app.db` | NEVER touch directly |

Each substantive sprint ships an audit-ledger entry under `docs/review/SPRINT_7_X_*.md`.

---

## Calendar gates (commit to dates)

| Date | Gate | Sprint |
|---|---|---|
| 2026-07-05 | 30-day settling on `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` complete | 7.2 ready to ship |
| 2026-07-15 (estimate) | ≥1 production release cycle after migration 0002 | 7.5 ready to scope |
| TBD | Sprint 7.4 visual review samples collected | 7.4 ready to ship |
| Sprint 7.4 + 30d | `FEATURE_RAW_PART_SKIP` settled | 7.8 ready to scope |

Set GitHub issues with `due:` dates for the calendar items so they don't slip.

---

## Rollback gate (unchanged)

Nếu bất kỳ sprint nào pytest delta > 0:
1. STOP
2. Revert PR cuối
3. Không fix trong cùng session
4. Tạo `docs/review/REGRESSION_*.md`
5. Plan riêng để fix

---

## Risk register (per sprint)

| Sprint | Risk | Tier | Mitigation |
|---|---|---|---|
| 7.1 | Import-graph drift after rename | LOW | Existing import tests catch missing modules |
| 7.2 | Hidden consumer of validation artifact | LOW | Pre-gate log grep; pause if non-zero usage |
| 7.3 | Cache collision on hash truncation | MEDIUM | Use full SHA-256, not truncated |
| 7.4 | Visual quality regression at part boundaries | CRITICAL | Manual sample review 3-5 renders + Sacred Contract walk |
| 7.5 | Stored payload still has `groq_*` keys (migration didn't run) | HIGH | Pre-gate SQL verification |
| 7.6 | Premature flag flip breaks user workflows | HIGH | Single-release waiting period after flip |
| 7.7 | DB benchmark methodology flawed | HIGH | A/B env-flag toggle; multiple sample runs |
| 7.8 | Motion-tracking continuity broken | CRITICAL | Visual review + Sprint 6.D-3.6b warmup_center logic verification |

---

## Approval log

| Date | Sprint | Approver | Status |
|---|---|---|---|
| 2026-06-05 | Sprint 7 cycle scope | (this doc, awaiting user approval) | pending |
| | Sprint 7.1 | | (awaiting) |
| | Sprint 7.2 | | (calendar 2026-07-05) |
| | Sprint 7.3 | | (awaiting) |
| | Sprint 7.4 | | (telemetry + visual review) |
| | Sprint 7.5 | | (release cycle gate) |
| | Sprint 7.6 | | (flag flip decision) |
| | Sprint 7.7 | | (benchmark gate) |
| | Sprint 7.8 | | (post 7.4 settled) |

---

## What this plan does NOT include

- **New optimisation predictions.** Per the meta-finding rule, no "Dự đoán" entries.
- **Re-opening of items closed in Sprint 1-6.** Whisper-skip, Inline ASS, TTS pipe are permanently DEFERRED per their audit docs — no FFmpeg architectural change has emerged that would warrant revisiting.
- **Periodic audit refresh.** `docs/review/TEMP_FILE_AUDIT_2026-06-04.md` should be re-run after Sprint 7.4 ships (the optimisation landscape will shift). That's a future planning artifact, not in this plan.
- **CLAUDE.md known issues 1, 3, 4, 5.** All RESOLVED or CLOSED per their notes. Only Issue 2 (DB connection model — Sprint 7.7) has remaining residual.

---

## Cross-references

- Predecessor: `docs/review/SPRINT_PLAN_2026-06-04.md` (CLOSED)
- Meta-finding: `docs/review/SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md`
- Per-item source audits cited per row in §"Backlog inventory" above
- Empirical audit: `docs/review/TEMP_FILE_AUDIT_2026-06-04.md`
- Sacred Contracts: `CLAUDE.md` §"Sacred Contracts — NEVER BREAK"
- Render Edit Protocol: `CLAUDE.md` §"Render Edit Protocol"
- Merge closure: PR #6, commit `9b67da5`
