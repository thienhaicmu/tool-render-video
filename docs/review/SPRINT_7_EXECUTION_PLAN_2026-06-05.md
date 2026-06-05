# Sprint 7.x Execution Plan

**Date:** 2026-06-05
**Main HEAD at write:** `38859eb` (post Sprint 7.7 prep merge)
**Pytest baseline:** 2423 passed / 1 skipped / 0 failed
**Predecessor doc:** `docs/review/SPRINT_PLAN_2026-06-05.md` (the 8-item scope)
**Companion docs (per-sprint):** see Phase tables for the closure ledger entry each sprint will produce

## Purpose

`SPRINT_PLAN_2026-06-05.md` enumerated the 8-item backlog. This doc is the **execution runbook** — calendar gates, pre-flight checklists, per-phase commit plans, and decision points the user controls. It captures the post-merge reality of the 2026-06-05 session: 4 sprints shipped, 5 gated, with concrete dates for each gate.

This is appended to the audit ledger; it does NOT supersede SPRINT_PLAN_2026-06-05.md, which remains the original scope authority.

## Session shipped (2026-06-05)

| Sprint | PR | Commit | Status |
|---|---|---|---|
| 7.1 Motion crop rename | #7 | `ee08938` (merge) | ✅ Merged |
| 7.3 ASS content cache | #8 | `7967c90` | ✅ Merged |
| 7.6a LLM flag flip | #9 | `ee83c82` | ✅ Merged |
| 7.7 prep (benchmark + defer recommendation) | #10 | `38859eb` | ✅ Merged |

## Calendar at a glance

```
2026-06-05  ▶  Today                  ✅ Sprint 7.1, 7.3, 7.6a, 7.7 prep merged
                                      ✅ CLAUDE.md Issue 2 close (this commit cycle)
            
2026-07-05  ▶  +30d (calendar)        🚀 Sprint 7.2 ready
                                      (FEATURE_BASE_CLIP_VALIDATION_ARTIFACT removal
                                       per SPRINT_6_BASE_CLIP_GATE_2026-06-05.md)
            
2026-07-15  ▶  +40d (release cycle)   🚀 Sprint 7.5 ready (groq_* deletion)
                                      🚀 Sprint 7.6 ready (LLMSegment retire,
                                         telemetry permitting)
            
TBD         ▶  Production data        🚀 Sprint 7.4 (raw_part fuse —
                                         telemetry + 3-5 visual review)
Sprint 7.4 + 30d                      🚀 Sprint 7.8 (motion-aware sub-scope)
            
Indefinite  ▶  No trigger             ⏸  Sprint 7.7 actual (defer per benchmark)
```

---

## Phase 0 — Today (no gates remaining)

### Item A — Close CLAUDE.md Issue 2 (this commit cycle)

**Scope:** Flip CLAUDE.md "Known Active Issues" §"Issue 2 — Mixed DB Connection Model" from `PARTIALLY RESOLVED 2026-06-05 Sprint 5.4` to `RESOLVED-WITH-DEFER 2026-06-05 via Sprint 7.7 prep`. Cite the empirical benchmark in `SPRINT_7_7_BENCHMARK_PREP_2026-06-05.md` as the justification for the indefinite Path A defer.

**Risk:** LOW. Doc-only update. Direct to main.

**Status:** Shipped in the second commit of this execution-plan batch.

### Item B (optional, can defer) — vestigial `render_pipeline.py:99` comment

Sprint 7.6a left a stale "OFF (default)" reference in a different docstring block at line 99 (not the canonical flag block at 127-144 which was updated correctly). Tiny cleanup. **Recommend folding into Sprint 7.6** when LLMSegment + legacy paths are deleted entirely — the comment becomes obsolete by that sprint's scope.

---

## Phase 1 — 2026-07-05 (calendar gate, T+30 days)

### Sprint 7.2 — `FEATURE_BASE_CLIP_VALIDATION_ARTIFACT` removal

**Gate:** 30-day settling period from Sprint 6 P0 HIGH ship (2026-06-05).

**Pre-flight checklist (run on 2026-07-05):**
1. `grep FEATURE_BASE_CLIP_VALIDATION_ARTIFACT=1` across production logs (or per-operator env files).
2. If zero usage observed: **GO**.
3. If non-zero: PAUSE with `docs/review/SPRINT_7_2_PAUSE_<date>.md` documenting the consumer + extending settling window.

**Execution:**
- Single commit, ½d
- Branch: `feature/sprint-7-2-validation-flag-removal`
- Delete env reads at 4 sites:
  - `backend/app/orchestration/render_pipeline.py:123`
  - `backend/app/orchestration/stages/part_renderer.py:27`
  - `backend/app/orchestration/stages/part_render_setup.py:92`
  - `backend/app/orchestration/stages/part_render_encode.py:108`
- Tighten gate at `part_render_encode.py:153` from `if FIRST AND (OVERLAY OR VALIDATION):` to `if FIRST AND OVERLAY:` (drop the VALIDATION clause)
- Update CLAUDE.md Performance Protections + Blast Radius Order references (line refs only)
- Delete 4 test cases from `tests/test_part_render_encode_base_clip_gate.py` that exercise the VALIDATION flag truth-table rows
- Audit doc `docs/review/SPRINT_7_2_VALIDATION_FLAG_REMOVAL_2026-07-05.md`

**Test plan:**
- Pytest baseline before edit: expect 2423/1/0 (or whatever it is on 2026-07-05)
- After edit: expect baseline - 4 cases (the truth-table rows for VALIDATION flag)
- Verify gate truth table still covers the remaining 4 default cases

---

## Phase 2 — ~2026-07-15 (release cycle gate, T+40 days)

### Sprint 7.5 — `groq_*` field deletion

**Gate:** Migration 0002 has run on every production DB. Conservative estimate: 40 days after PR #6 ship (2026-06-05 → 2026-07-15).

**Pre-flight checklist:**
1. Operators run on every production DB:
   ```sql
   SELECT COUNT(*) AS legacy_rows FROM jobs WHERE
     payload_json LIKE '%groq_analysis_enabled%' OR
     payload_json LIKE '%groq_model%' OR
     payload_json LIKE '%groq_content_language%' OR
     payload_json LIKE '%groq_min_quality_score%' OR
     payload_json LIKE '%groq_selection_strategy%';
   ```
2. Must return 0 across ALL production DBs.
3. If non-zero: PAUSE — investigate why migration 0002 didn't run (orphaned DB? Skipped startup?).

**Execution:**
- 2 commits, 1d total
- Branch: `feature/sprint-7-5-groq-deletion`
- Commit 1 (backend):
  - Delete 5 `groq_*` fields from `RenderRequest` at `schemas.py:364-379`: `groq_analysis_enabled`, `groq_model`, `groq_content_language`, `groq_min_quality_score`, `groq_selection_strategy`
  - **Preserve** `groq_only_mode` + `groq_api_key` (no llm_* equivalent — Migration 0002 design)
  - Delete `_coerce_groq_to_llm` validator at `schemas.py:466-482`
  - Update `tests/test_migration_0002_groq_to_llm.py::test_replay_parity_with_validator` — currently references the deleted field names; update to verify direct `llm_*` deserialization
- Commit 2 (frontend):
  - Run `npm run gen:types` → `frontend/src/types/openapi-generated.ts` auto-cleans
  - Verify zero hand-written component references via grep across `frontend/src/`
- CLAUDE.md Sacred Contract #2 entry update (document the controlled-removal justification: migration eliminated the read-side dependency)
- Audit doc `docs/review/SPRINT_7_5_GROQ_DELETION_2026-07-15.md`

**Test plan:**
- Pytest baseline before
- After: expect minor delta (~5 cases that reference the deleted fields)
- Smoke render with a stored job from before Sprint 7.5 — verify no schema error on replay (the `extra="ignore"` pin from Sprint 5.3 catches the silently-dropped `groq_*` keys gracefully)

---

## Phase 3 — After 1 release of 7.6a clean (~2026-07-15)

### Sprint 7.6 — `LLMSegment` retire

**Gate:** ≥ 1 production release cycle of `LLM_EMIT_RENDER_PLAN=1` default (from PR #9 ship date 2026-06-05) running clean. Telemetry criterion: `render.plan.ai_fallback` ratio < 20% across production renders.

**Pre-flight checklist:**
1. Operators count `render.plan.ai_emitted` vs `render.plan.ai_fallback` events from logs/DB
2. If `ai_fallback / (ai_emitted + ai_fallback) > 20%`: PAUSE with `docs/review/SPRINT_7_6_PAUSE_<date>.md` documenting the failure modes
3. If healthy ratio: **GO**

**Execution:**
- 3-4 commits split by file group, 2-3d total
- Branch: `feature/sprint-7-6-llmsegment-retire`
- Commit 1: Delete `LLMSegment` + `GroqSegment` alias from `parser.py:35, 55`, plus `_dict_to_segment` at `:213` + `parse_segment_response` at `:71`
- Commit 2: Delete `select_segments` from 4 providers:
  - `backend/app/ai/llm/claude_provider.py`
  - `backend/app/ai/llm/gemini_provider.py`
  - `backend/app/ai/llm/openai_provider.py`
  - `backend/app/ai/llm/__init__.py` (dispatcher)
- Commit 3: Delete `_to_scored_dict` consumer from `llm_stage.py:263` + the upstream `select_segments` call in `llm_stage.run_llm_segment_selection`
- Commit 4: Update anti-import pins at `tests/test_render_pipeline_llm_emit_flag.py:124` + `test_render_pipeline_render_plan_wiring.py:139`; fix vestigial `render_pipeline.py:99` comment from Sprint 7.6a (now consistent with deleted code)
- Update CLAUDE.md HIGH-tier Blast Radius Order entries
- Audit doc `docs/review/SPRINT_7_6_LLMSEGMENT_RETIRE_<date>.md`

**Test plan:**
- Pytest baseline before
- After: significant test churn expected (multiple tests reference `LLMSegment`, `GroqSegment`, `select_segments` directly)
- Render-engine integration test on RenderPlan-only path
- Smoke test: render with no AI key configured → expect graceful fallback (renders without RenderPlan, output unchanged)

---

## Phase 4 — Production telemetry data collected

### Sprint 7.4 — `raw_part` fuse (CRITICAL — Render Edit Protocol)

**Gate (BOTH required):**
1. **Telemetry data:** grep `raw_part_skip_eligible part=N predicate=true` from production render logs. Minimum 50 sample parts across 3+ unique source videos. Predicate fire-rate ≥ 30% justifies ship cost.
2. **Manual visual review:** 3-5 sample renders per Sprint Plan risk register line 302:
   - First-frame quality without `force_accurate_cut`
   - Audio sync at part boundaries
   - Duration accuracy ±0.35s vs current behaviour
   - Subtitle-disabled + base_clip-disabled config (the default skip case)
   - Control render with `FEATURE_RAW_PART_SKIP=0`

**Execution:**
- Single combined commit (predicate wire + helper + flag + tests must be atomic for the gate), 2-3d
- Branch: `feature/sprint-7-4-raw-part-fuse`
- NEW `render_part_from_source(source_path, start, dur, ...)` helper in `services/render/base_clip_renderer.py` (additive — `render_part_smart` signature stays frozen per Sprint 5.2 merge)
- Gate `cut_video()` in `run_cut_stage` on `FEATURE_RAW_PART_SKIP and skip_predicate(...)`
- Replace Sprint 6 O-4 Commit 1 telemetry log with actual skip + a different log marking the skip happened
- New env flag `FEATURE_RAW_PART_SKIP=0` default OFF, 30-day settling window
- Mirror env reads at 5 sites (same drift-prevention pattern as `FEATURE_BASE_CLIP_FIRST`)
- Archive 3-5 visual review samples (screenshots/durations attached to PR)
- Audit doc `docs/review/SPRINT_7_4_RAW_PART_FUSE_<date>.md` with Render Edit Protocol 9 steps trail

**ROI (per Sprint 6 O-4 Commit 1 audit):** ~1.5 GB transient + ~12 min wall-time / 50-part subtitle-off render.

### Sprint 7.8 — `raw_part` motion-aware sub-scope (CRITICAL)

**Gate:** Sprint 7.4 shipped + 30-day settling on `FEATURE_RAW_PART_SKIP`.

**Execution:**
- Extend `render_part_from_source` (from Sprint 7.4) to handle the motion-aware branch
- Plumb `-ss/-t` through `render_motion_aware_crop` in `services/motion_crop/__init__.py:351-724`
- Add motion-aware case to the predicate truth-table
- 3 additional visual review samples (motion-tracking continuity at part boundaries)
- Audit doc

**Risk:** Highest in backlog. Motion tracking quality + subject identity carryover across cut boundaries is the tricky area (Sprint 6.D-3.6b warmup_center logic). Defer aggressively until Sprint 7.4 has settled.

---

## Phase 5 — Indefinite defer

### Sprint 7.7 actual — DB connection unification

**Status:** **DEFERRED INDEFINITELY** per `SPRINT_7_7_BENCHMARK_PREP_2026-06-05.md` empirical findings.

**Benchmark conclusion:** `db_conn` is ~165x slower per call than `_thread_conn` (3,152 us vs 18.8 us median on dev hardware). The 1:1 helper swap fails Sprint 7.7 criterion 2 (wall-time delta < 1%) by ~12,000%. CLAUDE.md Issue 2 status updated to RESOLVED-WITH-DEFER citing this audit.

**Re-open triggers (any one):**
- Connection-pool dependency added (e.g. `sqlalchemy`).
- SQLite migrated to a server-mode database.
- Write rate drops 100x at source (Sprint 7.7 Path C).
- Render thread pool migration breaks `_thread_conn` reuse semantics.

**If re-opened:** fresh Planner cycle citing `SPRINT_7_7_BENCHMARK_PREP_2026-06-05.md` + collect new benchmark numbers + present three forward paths (A defer / B batching / C rate-limit-and-unify).

---

## Decision points (user controls)

| Date | Decision |
|---|---|
| 2026-06-05 (today) | Ship Phase 0 items? (CLAUDE.md Issue 2 close — recommended) |
| 2026-07-05 | Operators check production logs for VALIDATION flag usage → GO/PAUSE on Sprint 7.2 |
| 2026-07-15 | Operators verify migration 0002 ran on prod DBs → GO/PAUSE on Sprint 7.5 |
| ~2026-07-15 | Operators check `render.plan.ai_fallback` ratio → GO/PAUSE on Sprint 7.6 |
| TBD | User collects production `raw_part_skip_eligible` telemetry → schedule Sprint 7.4 |
| Sprint 7.4 + 30d | User schedules Sprint 7.8 motion-aware sub-scope |
| External trigger | User re-opens Sprint 7.7 actual via new Planner cycle |

---

## Per-sprint pre-flight commands

Standard sequence per sprint (mirrors PR #6-10 pattern):

```powershell
# P1 — read-only verification
cd D:\tool-render-video
git fetch --all --tags --prune
git log --oneline origin/main..main          # expect empty
git log --oneline main..origin/main          # expect empty
git status --short                            # expect clean
git checkout -b feature/sprint-7-X-<name>

# P2 — pytest baseline
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest -q --tb=no                  # record baseline pass count

# P3 — implementation per the per-sprint plan above

# P4 — pytest verify
python -m pytest -q --tb=line                # delta should match audit doc projection

# P5 — commit + push + PR
git add <explicit-files-only>                # NEVER git add . per CLAUDE.md
git commit -m "..."
git push -u origin feature/sprint-7-X-<name>

# P6 — open PR via GitHub web UI (gh CLI not installed)
# Title + body per the per-sprint plan
# Merge via "Create a merge commit" (NOT squash, NOT rebase)

# P7 — local sync
git fetch origin
git checkout main && git pull --ff-only origin main
python -m pytest -q                          # verify on merged main
git branch -d feature/sprint-7-X-<name>      # safe delete
```

---

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-05.md` — original 8-item backlog scope (predecessor)
- `docs/review/SPRINT_PLAN_2026-06-04.md` — Sprint 1-6 plan (grandparent, CLOSED)
- `docs/review/SPRINT_6_P1_AUDIT_CYCLE_SUMMARY_2026-06-05.md` — meta-finding rule (index from audit, not predictions)
- `docs/review/SPRINT_7_7_BENCHMARK_PREP_2026-06-05.md` — empirical justification for 7.7 indefinite defer
- `docs/review/SPRINT_7_1_MOTION_RENAME_2026-06-05.md` — Sprint 7.1 closure
- `docs/review/SPRINT_7_3_ASS_CONTENT_CACHE_2026-06-05.md` — Sprint 7.3 closure
- `docs/review/SPRINT_7_6a_LLM_FLAG_FLIP_2026-06-05.md` — Sprint 7.6a closure
- `docs/review/SPRINT_6_BASE_CLIP_GATE_2026-06-05.md` — Sprint 7.2 trigger (30-day settling source)
- `docs/review/MIGRATION_0002_GROQ_TO_LLM_2026-06-05.md` — Sprint 7.5 trigger (migration design)
- `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §1, §3 — Sprint 7.5 + 7.6 prerequisites
- `docs/review/SPRINT_6_O4_RAW_PART_SKIP_PREDICATE_2026-06-05.md` — Sprint 7.4 + 7.8 prior art
- `CLAUDE.md` "Known Active Issues" §"Issue 2" — updated this commit cycle

## What this doc does NOT do

- Does NOT supersede `SPRINT_PLAN_2026-06-05.md` (the original 8-item scope). This is execution runbook only.
- Does NOT ship code (Phase 0 ships in a sibling commit; per-phase code ships when calendar/data gates open).
- Does NOT commit to specific dates beyond Phase 1 (2026-07-05). Phase 2+ dates are estimates that depend on actual production release cadence.
- Does NOT re-litigate any closed deferral (Sprint 6 P1 Whisper/Inline-ASS/TTS — those stay closed).
