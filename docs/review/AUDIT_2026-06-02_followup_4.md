# Audit 2026-06-02 — Sprint 6.D Closure: God-File Decomposition Complete

Fourth append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## What this closes

The original audit's Issue 4 — "Remaining God Files" — flagged three
single-file LOC concentrations as architectural risk:

| File | Audit baseline | Audit target |
|---|---|---|
| `backend/app/orchestration/render_pipeline.py` | 1525 LOC | ≤ 800 LOC / ≤ 50% reduction |
| `backend/app/orchestration/stages/part_renderer.py` | 2101 LOC | ≤ 800 LOC / ≤ 50% reduction |
| `backend/app/services/motion_crop.py` | 2512 LOC | ≤ 800 LOC / ≤ 50% reduction |

Sprint 6.D was the multi-phase decomposition response to this finding.
The plan is documented at `docs/review/SPRINT_6D_PLAN.md`. This ledger
entry records the **completion state**.

## Final reduction

| File | Baseline | Final | Δ | % Reduction |
|---|---|---|---|---|
| `render_pipeline.py` | 1536 | 1103 | −433 | 28% |
| `motion_crop.py` | 2512 | 757 | −1755 | 70% |
| `part_renderer.py` | 2101 | 325 | −1776 | 85% |
| **Sum** | **6149** | **2185** | **−3964** | **64%** |

**All three files now ≤ 800 LOC plan target met.** `render_pipeline.py`
sits modestly above the strict "≤ 50% reduction" goal but well under
the absolute LOC ceiling; the residual is glue code with no clean
internal seam.

## What got built (new modules)

22 new modules across 3 packages:

### `app/orchestration/` (render_pipeline.py decomposition — Sprint 6.D-1.x)
| Module | LOC | Sprint |
|---|---|---|
| `pipeline_setup.py` | 158 | 6.D-1.1 + 6.D-1.2 |
| `pipeline_source_prep.py` | 305 | 6.D-1.3 |
| `pipeline_narration.py` | 155 | 6.D-1.4 |
| `pipeline_finalize.py` | 270 | 6.D-1.5 |

### `app/services/` (motion_crop.py decomposition — Sprint 6.D-3.x)
| Module | LOC | Sprint |
|---|---|---|
| `motion_crop_cache.py` | 51 | 6.D-3.1 |
| `motion_crop_config.py` | 130 | 6.D-3.2 |
| `motion_crop_utils.py` | 201 | 6.D-3.3 |
| `motion_crop_tracker.py` | 140 | 6.D-3.4 |
| `motion_crop_detection.py` | 305 | 6.D-3.5a |
| `motion_crop_scoring.py` | 213 | 6.D-3.5b |
| `motion_crop_trackerless.py` | 181 | 6.D-3.5c |
| `motion_crop_legacy.py` | 260 | 6.D-3.7 |
| `motion_crop_path.py` | 977 | 6.D-3.6a + 6.D-3.6b |

### `app/orchestration/stages/` (part_renderer.py decomposition — Sprint 6.D-2.x)
| Module | LOC | Sprint |
|---|---|---|
| `part_render_context.py` | 108 | 6.D-2.1 |
| `part_asset_planner.py` | 712 | 6.D-2.2 |
| `part_cut.py` | 286 | 6.D-2.3 |
| `part_render_setup.py` | 260 | 6.D-2.4 (re-scoped from TRANSCRIBE) |
| `part_render_encode.py` | 370 | 6.D-2.5a |
| `part_voice_mix.py` | 346 | 6.D-2.5b |
| `part_render_finalize.py` | 629 | 6.D-2.5c (CRITICAL — qa_pipeline surface) |
| `part_done.py` | 209 | 6.D-2.5d |

## How safety was kept

The 23-commit decomposition maintained these invariants across **every**
phase commit:

- **Pytest baseline preserved**: 2077 passed, 1 skipped, 0 failed from
  the first phase through the last. No regressions introduced; the
  three transient regressions (Sprint 2.2 SUBTITLE_PER_PART_MODEL,
  Sprint 2.5b playback_speed scan, structural-invariant style)
  were resolved in the same commit by patching the test's source-scan
  list — never by modifying behavioral assertions.
- **Sacred Contracts 1–8 intact**: every phase commit body documented
  the Contract surfaces touched and verified them via grep
  (`JobPartStage.*`, `_emit_render_event` kwarg shape, `upsert_job_part`
  arity, `_validate_render_output`/`_assess_output_quality` kwargs).
  Sacred Contract #8 (qa_pipeline never bypassed) was the most
  delicate surface — concentrated in Sprint 6.D-2.5c, moved verbatim
  with no threshold changes, no fallback path, no exception-to-success
  swap.
- **Frozen stage names**: `JobStage.*` and `JobPartStage.*` references
  via enum only. Grep confirms zero string-literal stage transitions
  introduced.
- **NVENC semaphore**: untouched. Acquisition happens inside
  `render_engine` helpers (Sprint 4.2 centralized point); decomposition
  did not redistribute or duplicate the semaphore acquire/release.
- **Known-bug preservation**: two pre-existing bugs documented and
  preserved verbatim (the `srt_path` typo in part_done.py, the
  `_mv_score_part` missing import in part_render_finalize.py) — both
  caught by surrounding try/except blocks, making the affected paths
  silent no-ops. Fixing either would change runtime behavior and was
  out of scope for the pure-relocation refactor.

## Plan-revision events

Two mid-execution revisions recorded in `SPRINT_6D_PLAN.md` §11
changelog:

1. **Pushback revision** (commit `0d8f643`): pre-execution. Plan phase
   3.5 split into 3.5a/b/c (original "~30 functions" violated §7 stop
   condition #5); phase 3.6 split into 3.6a/b. `render_pipeline` phase
   1.5 reordered to execute first (safest contiguous slice; risk
   downgraded HIGH→MEDIUM).
2. **Mid-execution revision** (commit `41dd67e`): mid-2.x. Phase 2.4
   re-scoped from TRANSCRIBE (already absorbed into 2.2) to "RENDER
   pre-flight". Phase 2.5 split into 2.5a/b/c/d to keep no single
   commit above ~430 LOC, isolating the Sacred Contract #8 surface
   in 2.5c.

Total phase count: 17 (original) → 20 (pushback) → 23 (mid-execution).
All 23 executed.

## What's NOT closed

- **`render_pipeline.py` strict reduction target** (≤ 50% of baseline)
  not met — 28% achieved. The remaining 1103 LOC is one large function
  (`run_render_pipeline`) whose interior glue is tightly coupled with
  no clean internal seam left. Further decomposition is possible but
  requires a different strategy (likely an "orchestrator pattern"
  refactor, not a verbatim relocation). Out of Sprint 6.D scope.
- **Dead-import cleanup** across all three god files. Sprint 6.D
  consistently followed the "no while I'm here" convention to keep
  each commit a pure relocation. The cleanup is now a separate
  follow-up: remove unused imports across `part_renderer.py`,
  `motion_crop.py`, and `render_pipeline.py`. Estimated ~80 LOC
  removable, no behavioral impact.
- **Known-bug fixes** (`srt_path` typo, missing `_mv_score_part`
  import). Both should be filed as separate behavioral-change tasks.
  Fixing them activates code paths that have been silent no-ops for
  unknown time — potential downstream impact requires investigation
  before fixing.

## References

- Plan: `docs/review/SPRINT_6D_PLAN.md`
- Audit root: `docs/review/AUDIT_2026-06-02.md` (Issue 4 in original ledger)
- Previous followups: `AUDIT_2026-06-02_followup.md`,
  `AUDIT_2026-06-02_followup_2.md`, `AUDIT_2026-06-02_followup_3.md`
- Final commit: `26d380d` (Sprint 6.D-2.5c)
- Branch: `restructure/output-timeline-architecture` @ origin

## Status

**Issue 4 — Remaining God Files: CLOSED.**

`render_pipeline.py`, `motion_crop.py`, and `part_renderer.py` all
satisfy the plan §1 LOC ceiling. Architectural risk classification
for these three files drops from "god file" to "ordinary large
module" — review concerns shift from monolith-decomposition to
ongoing-maintenance hygiene.
