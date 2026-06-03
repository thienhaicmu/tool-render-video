# Audit 2026-06-02 — Track D Audit Pass D2: Test Coverage Gaps

Seventh append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## Why this audit

Track C C1 + C2 just closed two silent-failure bugs that lived 6+ days
each (`srt_path` typo in `part_done.py`, missing `_mv_score_part`
import in `part_render_finalize.py`). Both bugs had the same shape:

1. Function call inside a `try / except: pass` block.
2. Call site had zero behavioral test coverage.
3. The exception was silently swallowed.
4. Nobody noticed for days because the broader test suite passed —
   the function under the try block was tested in isolation, just not
   *called* in any test.

D2 audits the rest of the codebase for the same pattern: identify
behavioral surfaces inside `try / except: pass` blocks that have no
test exercising the call site. Each gap is a future-C1/C2 risk.

## Audit methodology

Read-only analysis. No code edits. Steps:

1. Enumerate the 22 new modules created in Sprint 6.D.
2. For each, count direct test consumers (`grep -r "from app.X import" tests/`).
3. For each, count indirect coverage via re-export shims through the
   parent god file (`render_pipeline.py`, `motion_crop.py`, `part_renderer.py`).
4. Scan all orchestration + motion_crop files for `try / except: pass`
   patterns.
5. Manually classify each except-pass block as HIGH / MEDIUM / LOW
   risk based on whether the swallowed call has external side effects.

## Finding 1 — Direct test coverage of new Sprint 6.D modules

20 of 22 modules have **zero direct test imports**. The 2 with direct
tests are exactly the two ones with regression guards added in Track C.

| Module | Direct test files |
|---|---|
| `orchestration/pipeline_setup.py` | 0 |
| `orchestration/pipeline_source_prep.py` | 0 |
| `orchestration/pipeline_narration.py` | 0 |
| `orchestration/pipeline_finalize.py` | 0 |
| `services/motion_crop_cache.py` | 0 |
| `services/motion_crop_config.py` | 0 |
| `services/motion_crop_utils.py` | 0 |
| `services/motion_crop_tracker.py` | 0 |
| `services/motion_crop_detection.py` | 0 |
| `services/motion_crop_scoring.py` | 0 |
| `services/motion_crop_trackerless.py` | 0 |
| `services/motion_crop_legacy.py` | 0 |
| `services/motion_crop_path.py` | 0 |
| `stages/part_render_context.py` | 0 |
| `stages/part_asset_planner.py` | 0 |
| `stages/part_cut.py` | 0 |
| `stages/part_render_setup.py` | 0 |
| `stages/part_render_encode.py` | 0 |
| `stages/part_voice_mix.py` | 0 |
| `stages/part_render_finalize.py` | **1** (Track C C2 guard) |
| `stages/part_done.py` | **1** (Track C C1 guard) |

## Finding 2 — Indirect coverage via re-export shims

Most motion_crop_*.py modules have *function-level* tests through the
parent module's re-export shims (test_probe_unification.py,
test_motion_crop_guards.py exercise extracted helpers). render_pipeline
similarly has 7 test files using its re-export shims for asset / audio
/ qa / event helpers.

What's missing is **call-site coverage** — no test invokes the actual
extracted entry point (e.g., `run_cut_stage`, `run_render_preflight`,
`run_render_encode`, `prepare_part_assets`, etc.) with realistic
inputs and verifies the resulting state mutations. This is the gap
that produced C1 and C2 — the extracted functions had unit tests for
their dependencies but no test exercising the orchestrator path.

| Parent module | Test files |
|---|---|
| `app.services.motion_crop` | 4 (`test_encoder_helpers`, `test_motion_crop_guards`, `test_probe_unification`, `test_render_audit_p0_fixes`) |
| `app.orchestration.render_pipeline` | 7 (asset_pipeline, audio_cleanup_pipeline, audio_pipeline, qa_pipeline, remotion_adapter, render_events, render_pipeline_guards) |
| `app.orchestration.stages.part_renderer` | **0** |

The third row is the standout — `part_renderer` (and all 8 stages/*
helpers it delegates to) has zero call-site test coverage from any
direction.

## Finding 3 — Silent-failure surfaces (except-pass blocks)

30 `try / except: pass` patterns identified across orchestration +
motion_crop. Classified by risk:

### HIGH risk — silent-fail surfaces matching the C1/C2 shape

These wrap calls with external side effects (DB writes, file writes,
WS emits, output ranking signals). Each is a potential refactor
regression hiding spot.

| # | Location | What's wrapped | Status |
|---|---|---|---|
| **H1** | `stages/part_done.py:139` | `_assess_render_quality_intelligence(...)` | ✅ Tested (Track C C1 guard) |
| **H2** | `stages/part_done.py:151` | Cover frame: `_select_cover_frame_time` + `extract_thumbnail_frame` + `_cover_path.write_bytes` | ⚠️ **Gap** — no call-site test |
| **H3** | `stages/part_render_finalize.py:393` | `_mv_score_part` + `seg["mv_viral_*"]` assignments + `market_viral_scored` emit | ✅ Tested (Track C C2 guard) |
| **H4** | `stages/part_render_finalize.py:460` | `resolve_combined_score_weights` + `combined_score` computation + `adaptive_score_weights_resolved` + `combined_score_computed` emits | ⚠️ **Gap** — no call-site test |
| **H5** | `stages/part_asset_planner.py:362` | `apply_market_line_break_to_srt(...)` | ⚠️ **Gap** — no call-site test |
| **H6** | `stages/part_asset_planner.py:561` | SRT block parsing for debug logging | ⚠️ Low impact (debug only) |

**Action items for future Track-C-style fix sessions:**
- T1 (HIGH): regression-guard test for H2 (cover frame extraction).
  Tests should mock `extract_thumbnail_frame` and assert it's called
  + the resulting `seg["cover_file"]` lands.
- T2 (HIGH): regression-guard test for H4 (combined score).
  Tests should mock `resolve_combined_score_weights`, supply an SRT
  + market context, and assert `seg["combined_score"]` is set.
- T3 (MEDIUM): regression-guard test for H5 (market line break).
  Lower priority — failure here is silent but not behavior-critical
  (line breaks are cosmetic for the subtitle pass).

### MEDIUM risk — intentional safety wrappers

These wrap calls where failure must NOT propagate (per Sacred
Contracts or operational safety). The except-pass is the design.

| # | Location | What's wrapped | Why intentional |
|---|---|---|---|
| M1 | `orchestration/pipeline_finalize.py:232` | `maybe_snapshot_after_job()` (Sprint 6.A backup) | Backup failure must NOT kill render. Sacred Contract 7 follow-up. |
| M2 | `orchestration/render_pipeline.py:1056` | `cleanup_session_fn(edit_session_id)` | Cleanup is best-effort; failure must not affect render outcome. |

**No action needed.** Documented intent.

### LOW risk — observability fail-safes

These wrap tracing / logging calls. By design, tracing must never
break the system being traced.

| # | Location | Count | Purpose |
|---|---|---|---|
| L1 | `orchestration/workflow_trace.py` | 7 | Trace-line writing fail-safes |
| L2 | `orchestration/render_events.py` | 5 | Event-emission fail-safes |
| L3 | `orchestration/pipeline_cache.py` | 3 | Cache I/O fail-safes |
| L4 | `orchestration/pipeline_segment_selection.py` | 1 | Helper fail-safe |
| L5 | `orchestration/pipeline_subtitle_utils.py` | 1 | Helper fail-safe |
| L6 | `orchestration/qa_pipeline.py` | 1 | qa_pipeline internal fail-safe |
| L7 | `services/motion_crop.py` | 3 | Subprocess cleanup fail-safes |
| L8 | `services/motion_crop_cache.py` | 1 | Cache I/O fail-safe |

**No action needed.** All are documented design decisions in their
modules. Adding tests would add no value — the design IS to swallow
exceptions.

## Finding 4 — Sacred Contract test coverage map

For each Sacred Contract (CLAUDE.md §"Sacred Contracts"), I checked
whether a dedicated test asserts the contract holds.

| Contract | Test coverage | Notes |
|---|---|---|
| **#1** `result_json` backward-compat aliases (`output_rank_score`, `is_best_output`, `is_best_clip`) | ⚠️ Partial — `_compute_output_ranking_entry` is tested in isolation; no end-to-end "render → result_json has all 3 keys" test | Action: add a contract-conformance test |
| **#2** `RenderRequest` new field defaults | ⚠️ Indirect — `schemas.py` model tests run, but no test that NEW fields default to False/disabled | Action: add a schema-default assertion test |
| **#3** AI modules return None on failure | ⚠️ Partial — `test_qa_pipeline_quality_integration.py` tests the `_assess_render_quality_intelligence` return-None path; other AI modules (under `backend/app/ai/**`) not audited | Bigger audit needed (D5 candidate) |
| **#4** Job stage transition names frozen | ✅ Implicit via `JobStage` enum + `STAGE_TO_EVENT` mapping table; rename would break import | Strong static guarantee |
| **#5** Job part transition names frozen | ✅ Same — `JobPartStage` enum + frozen string literal absence | Strong static guarantee |
| **#6** `_emit_render_event` signature frozen | ⚠️ No signature contract test. 28+ call sites in part_render_finalize, part_render_encode, etc. — kwargs are checked manually per move. | Action: add a "every emit kwarg shape" test |
| **#7** `app.db` sole job state authority | ⚠️ No direct contract test. `tests/test_jobs_repo.py` tests connection but not "only this module writes" | Action: add an import-graph test (no `sqlite3.connect()` calls outside `app/db/` or `services/db.py`) |
| **#8** `qa_pipeline` never bypassed | ⚠️ No "every render path runs validation" test. `_validate_render_output` is tested in isolation, not as an unbypassable gate. | Action: add an integration test that asserts validation is invoked on every render success path |

## Finding 5 — Priority-ranked action items

If/when the user wants to address these gaps, recommended order:

| Priority | Action | Effort | Why |
|---|---|---|---|
| **P0** | T1 (cover frame regression test, H2) | 1 small commit | Same shape as C1/C2 — refactor-regression-prone |
| **P0** | T2 (combined score regression test, H4) | 1 small commit | Same shape as C1/C2 — refactor-regression-prone |
| **P1** | Contract #1 conformance test (result_json keys) | 1 commit | Single-purpose test, catches future result_json key drift |
| **P1** | Contract #6 emit-shape test | 1 commit | Catches future `_emit_render_event` kwarg changes |
| **P1** | Contract #8 validation-gate test | 1 commit | High-value: guarantees Sprint 6.D-2.5c's qa_pipeline surface stays unbypassed |
| **P2** | Stage helper smoke-tests | 8 commits, 1 per stages/* | Per-helper happy-path test asserting call signatures + key state mutations |
| **P2** | Pipeline_*.py orchestration helpers | 4 commits | Same as P2, for orchestration/pipeline_*.py |
| **P3** | Contract #2 RenderRequest default audit | 1 commit | Lower urgency — Pydantic catches type errors at deserialize time |
| **P3** | Contract #7 import-graph test | 1 commit | Static analysis test that no module outside `app/db/` calls `sqlite3.connect()` |

## Finding 6 — Pattern recognition for future audits

Three rules of thumb emerged from this audit:

1. **Any `try / except: pass` block wrapping a call with side effects
   is a future-C1/C2 risk.** Side effects = WS emit, DB write, file
   write, mutation of shared state (like `seg` dict). The block needs
   a behavioral test asserting the side effect actually happens.

2. **Extracted helpers without direct test imports are refactor-fragile.**
   The parent module's re-export tests catch import-path drift but
   miss call-site drift (e.g., missing import in extracted module
   that calls a re-exported symbol).

3. **Sacred Contracts need their own conformance tests.** Implicit
   coverage via "the function is tested in isolation" is insufficient
   — the Contract is about how callers WIRE to the function, not how
   the function behaves in isolation.

## Pytest

Audit is read-only. Pytest baseline unchanged: 2080 passed, 1 skipped.

## References

- Audit root: `docs/review/AUDIT_2026-06-02.md`.
- Sprint 6.D closure: `docs/review/AUDIT_2026-06-02_followup_4.md`.
- Track C C1 fix: `docs/review/AUDIT_2026-06-02_followup_5.md`.
- Track C C2 fix: `docs/review/AUDIT_2026-06-02_followup_6.md`.

## Status

**D2 audit: COMPLETE.** No code changes — pure findings document.

Outstanding action items recorded for future Track-C-style sessions.
The 2 P0 items (T1 cover frame test, T2 combined score test) are
direct follow-ups to Track C and should be the first picked up.
