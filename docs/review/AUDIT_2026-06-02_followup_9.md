# Audit 2026-06-02 — Track D P1 Action Items T3 + Contract Conformance

Ninth append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## What this closes

Four P1 action items from the Track D / D2 audit ledger
(`docs/review/AUDIT_2026-06-02_followup_7.md`):

- **T3** — regression-guard tests for **H5** (market line-break block
  at `stages/part_asset_planner.py:358-363`).
- **Contract #1 conformance** — frozen `result_json` keys.
- **Contract #6 conformance** — `_emit_render_event` signature +
  log-shape schema.
- **Contract #8 conformance** — `qa_pipeline` validation gate is
  unbypassable.

Followup_8 closed the P0 items (T1 + T2). This closes the P1 items.

## What was added

Four test files, four commits:

| Commit | File | Tests |
|---|---|---|
| `799e40c` | `backend/tests/test_part_asset_planner_market_line_break.py` | 3 |
| `3669caf` | `backend/tests/test_contract_result_json_keys.py` | 7 |
| `1bca412` | `backend/tests/test_contract_emit_render_event_shape.py` | 6 |
| (this commit) | `backend/tests/test_contract_qa_pipeline_unbypassed.py` | 6 |

Net +22 tests, 0 production code changes.

## Why test-only

Like the followup_8 P0 work, this is preventive coverage. The audit
(followup_7) did not find a live bug in any of these surfaces — it
found that they would fail silently if a future refactor broke them.

Each test guards a specific failure mode that has historically slipped
through code review (Track C C1 + C2 demonstrated the pattern: a lost
import inside a try/except: pass block, undetected for 6 days).

## Test breakdown

### T3 — `test_part_asset_planner_market_line_break.py`

Three tests under `TestMarketLineBreakActivation`:

1. `test_apply_market_line_break_invoked_when_mv_cfg_set` — happy path:
   `apply_market_line_break_to_srt(srt_path, mv_cfg)` invoked.
2. `test_skipped_when_mv_cfg_falsy` — intentional fallthrough:
   `mv_cfg={}` short-circuits the if-guard, helper NOT called.
3. `test_silent_swallow_when_helper_raises` — safety-net guard:
   helper raises → `prepare_part_assets` continues without
   propagating (the try/except: pass is the design).

### Contract #1 — `test_contract_result_json_keys.py`

Seven tests under `TestResultJsonContractKeys`, asserting the three
frozen backward-compat aliases (`output_rank_score`, `is_best_output`,
`is_best_clip`) are present + type-correct on every code path through
`_compute_output_ranking_entry`:

1. `test_keys_present_on_minimal_seg` — bare seg.
2. `test_keys_present_on_full_seg` — every score populated.
3. `test_keys_present_when_all_scores_missing` — empty seg.
4. `test_output_rank_score_is_numeric` — type + range guard.
5. `test_is_best_flags_are_boolean` — type + default-False guard.
6. `test_output_rank_score_matches_output_score` — alias invariant
   (output_rank_score == output_score at every score value).
7. `test_keys_present_with_payload_hook_score_override` — override path.

### Contract #6 — `test_contract_emit_render_event_shape.py`

Six tests in two layers.

**Signature layer (3 tests, `TestEmitRenderEventSignature`):**

1. `test_all_frozen_kwargs_present` — all 11 frozen kwargs exist
   (channel_code, job_id, event, level, message, step, context,
   exception, traceback_text, duration_ms, error_code).
2. `test_all_params_are_keyword_only` — `*` separator preserved.
3. `test_required_kwargs_have_no_defaults` — 6 load-bearing kwargs
   must be supplied by every caller.

**Log-shape layer (3 tests, `TestEmitRenderEventLogShape`):**

4. `test_log_entry_contains_all_frozen_top_level_keys` — every emit
   writes a log line containing all 12 frozen top-level keys
   (timestamp, level, event, module, message, job_id, step,
   error_code, context, exception, traceback, duration_ms).
5. `test_log_entry_context_kwarg_lands_as_dict` — context kwarg
   survives verbatim.
6. `test_log_entry_with_error_level_sets_error_code` — ERROR-level
   events auto-populate error_code (drives the WS failure UI).

### Contract #8 — `test_contract_qa_pipeline_unbypassed.py`

Six tests under `TestQaPipelineSurfaceUnbypassed`:

1. `test_validate_render_output_exists_in_qa_pipeline` — signature
   integrity (output_path, expected_duration, expect_audio).
2. `test_assess_output_quality_exists_in_qa_pipeline` — signature
   integrity (output_path, expect_subtitle, subtitle_file,
   expect_hook, hook_applied).
3. `test_finalize_imports_validate_render_output` — the finalize
   module has `_validate_render_output` and `_assess_output_quality`
   bound at module level. Without these, the call site at line 485
   would raise NameError caught silently (Track C C2 pattern).
4. `test_validate_render_output_call_site_not_wrapped_in_try` —
   source-text scan: no enclosing try/except at the same indent
   level around the validation call. A wrapping try would let the
   subsequent `raise RuntimeError` be caught silently.
5. `test_finalize_raises_runtime_error_on_validate_failure` —
   behavioral: when `_validate_render_output` returns `ok=False`,
   `run_part_finalize` raises `RuntimeError("output_validation_failed[...]")`.
6. `test_finalize_invokes_validate_on_happy_path` — positive case:
   the validation gate runs unconditionally on every render success
   path. Guards against future "skip validation if flag X" branches.

## Sacred Contracts honored

These tests **assert** Sacred Contracts — they don't modify them. All
six SaCs in scope:

- **#1** — Contract #1 tests directly assert the 3 frozen keys.
- **#6** — Contract #6 tests directly assert the frozen signature +
  log shape.
- **#8** — Contract #8 tests directly assert the validation gate is
  unbypassable.
- Track D P0 work (followup_8) already covered the C1/C2 surface
  pattern via T1+T2 + Track C bug fixes.

T3 production code unchanged — only the test surrounding it.

## Pytest

Before this batch (after followup_8): 2086 passed, 1 skipped.
After this batch: **2108 passed, 1 skipped**, 0 failed.

Net +22 tests (T3=3, Contract #1=7, Contract #6=6, Contract #8=6).

```
backend/tests/test_part_asset_planner_market_line_break.py ........ 3 passed
backend/tests/test_contract_result_json_keys.py ................... 7 passed
backend/tests/test_contract_emit_render_event_shape.py ............ 6 passed
backend/tests/test_contract_qa_pipeline_unbypassed.py .............. 6 passed
```

## Risk

**LOW.** Test-only additions across 4 separate commits. Each test
file is independently runnable. No production code modified.

## Remaining work from followup_7

### P2 — Stage helper smoke tests (open)

8 commits, 1 per `stages/part_*.py` module. Each smoke test asserts
the helper's call signature + at least one key state mutation. Lower
ROI per commit than the Contract conformance tests just added.

### P2 — Pipeline_*.py orchestration helpers (open)

4 commits, 1 per `orchestration/pipeline_*.py` helper. Same pattern
as the stages smokes.

### P3 — Lower-priority audit follow-ups (open)

- Contract #2 RenderRequest default audit (1 commit).
- Contract #7 import-graph test (1 commit, static analysis).
- Sacred Contract #3 audit of `backend/app/ai/**` (broader scope,
  D5 candidate per followup_7).

### Code-shape recommendations (deferred)

From followup_7 Finding 6:
- Refactor `except: pass` blocks to `except: log + emit_warning`
  pattern.
- Add `_run_or_warn(block_name, fn)` helper in `render_events.py`
  for consistent silent-failure-with-signal handling.

These are HIGH risk (touching CRITICAL-tier files in the orchestrator
and stages) and require explicit user approval + Planner analysis
before any edit.

## References

- Audit root: `docs/review/AUDIT_2026-06-02.md`.
- D2 audit findings: `docs/review/AUDIT_2026-06-02_followup_7.md`.
- P0 closure (T1+T2): `docs/review/AUDIT_2026-06-02_followup_8.md`.
- Sister fix C1: `docs/review/AUDIT_2026-06-02_followup_5.md`.
- Sister fix C2: `docs/review/AUDIT_2026-06-02_followup_6.md`.
- Sprint 6.D closure: `docs/review/AUDIT_2026-06-02_followup_4.md`.

## Status

**Track D P1: CLOSED.** T3 + 3 Sacred Contract conformance tests
are live, green, and indexed. The audit's three highest-value
Contract gaps (#1, #6, #8) now have direct conformance tests that
fail loudly if a future refactor breaks the contract.

Track D P2 (stage + pipeline smoke tests) remains open. P3 + code-
shape recommendations also open.
