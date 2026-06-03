# Audit 2026-06-02 — Track D P0 Action Items T1 + T2 Closure

Eighth append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## What this closes

Two P0 action items from the Track D / D2 audit ledger
(`docs/review/AUDIT_2026-06-02_followup_7.md`):

- **T1** — Regression-guard tests for **H2** (cover frame extraction
  block at `stages/part_done.py:142-208`).
- **T2** — Regression-guard tests for **H4** (combined score block at
  `stages/part_render_finalize.py:396-461`).

Both blocks were flagged in followup_7 as HIGH-risk silent-failure
surfaces: wrapped in `try / except: pass`, mutating `seg`, emitting
WS events, and entirely without call-site test coverage. The pattern
that produced Track C bug C2 (refactor regression silently swallowed
for 6 days, traced to commit `765616d` Phase A on 2026-05-28) is the
exact pattern these two blocks were vulnerable to.

## Why test-only — not behavior changes

Both blocks are believed to be functioning today. The audit (followup_7)
did NOT find a bug in either. The audit found:

- The blocks have side effects that downstream code depends on
  (`seg["cover_file"]`, `seg["cover_frame_offset"]`,
  `seg["combined_weights"]`, `seg["combined_score"]`,
  `cover_frame_selected`, `adaptive_score_weights_resolved`,
  `combined_score_computed` WS events, and the cover JPG file on disk).
- The `except: pass` would silently swallow any future regression
  (e.g., a lost import after refactoring, a renamed attribute on `ctx`).
- Zero existing tests would catch the silent failure.

These tests close the coverage gap — they do NOT change runtime
behavior.

## What was added

| File | Purpose | Tests |
|---|---|---|
| `backend/tests/test_part_done_cover_frame.py` | T1: regression guard for the cover frame extraction side effects | 3 |
| `backend/tests/test_part_render_finalize_combined_score.py` | T2: regression guard for the combined score block side effects | 3 |

### T1 — `test_part_done_cover_frame.py`

Three test methods under `TestCoverFrameExtractionActivation`:

1. `test_cover_jpg_written_and_seg_fields_set` — happy path:
   - asserts `_select_cover_frame_time` invoked
   - asserts `extract_thumbnail_frame` invoked with the final video path
   - asserts the cover JPG file is written to the expected location
   - asserts `seg["cover_file"]` and `seg["cover_frame_offset"]` set
   - asserts `cover_frame_selected` WS event emitted with correct context

2. `test_variant_type_uses_variant_naming` — variant path:
   - asserts the cover file uses the `{stem}_{variant_type}_cover.jpg`
     naming pattern when `variant_type` is set (NOT the
     `{stem}_part_{idx:03d}_cover.jpg` default).

3. `test_extract_thumbnail_returns_none_skips_file_write` — corrupt
   video / no-readable-frame path:
   - asserts JPG file is NOT written when `extract_thumbnail_frame`
     returns None
   - asserts seg fields are NOT set
   - asserts `cover_frame_selected` event is NOT emitted (intended
     behavior — no exception raised, just a clean no-op)

### T2 — `test_part_render_finalize_combined_score.py`

Three test methods under `TestCombinedScoreBlockActivation`:

1. `test_combined_score_populated_when_block_runs_clean` — happy path:
   - asserts `resolve_combined_score_weights` invoked with the expected
     kwargs (`target_market`, `has_market_score`, `has_hook_score`,
     `duration`, `adaptive_enabled`)
   - asserts `seg["combined_weights"]` set to the resolved dict
   - asserts `seg["combined_score"]` equals weighted-sum arithmetic
     (viral=80*0.5 + market=70*0.3 + hook=60*0.2 = 73.0)
   - asserts BOTH `adaptive_score_weights_resolved` and
     `combined_score_computed` WS events emitted
   - asserts event context carries the expected scoring fields

2. `test_combined_score_clamped_to_100_when_weights_overshoot` —
   upper clamp:
   - constructs weights summing to 1.5
   - asserts result is clamped to 100.0 (NOT 150.0).
   - guards against the `min(100.0, _cs_raw)` arithmetic regressing.

3. `test_combined_score_uses_viral_when_market_score_missing` —
   fallback path:
   - forces `_mv_score_part` to raise (so seg["mv_viral_score"] stays
     unset)
   - asserts `resolve_combined_score_weights` still called with
     `has_market_score=False`
   - asserts the block falls back to using `viral_score` in the market
     slot (per the `_cs_mv = float(_cs_mv_raw) if _cs_mv_raw is not
     None else _cs_viral` line at line 401)

## Sacred Contracts honored

These tests do not touch any Sacred Contract surface. They are
mock-heavy unit tests around `run_part_done` (T1) and
`run_part_finalize` (T2):

- No edits to the production code under test.
- All `qa_pipeline` calls (`_validate_render_output`,
  `_assess_output_quality`) are mocked to return clean results
  — the tests assert the OUTER blocks' side effects, not the
  qa_pipeline integrations themselves (those have their own
  coverage at `tests/test_qa_pipeline_*.py`).
- No new behaviors, no new emit shapes — the tests assert the
  existing emit shape and the existing seg-dict shape.

## Pytest

Before T1 + T2: 2080 passed, 1 skipped (after followup_5 + followup_6).
After T1 + T2:  **2086 passed, 1 skipped**, 0 failed.

```
tests/test_part_done_cover_frame.py::TestCoverFrameExtractionActivation::test_cover_jpg_written_and_seg_fields_set PASSED
tests/test_part_done_cover_frame.py::TestCoverFrameExtractionActivation::test_variant_type_uses_variant_naming PASSED
tests/test_part_done_cover_frame.py::TestCoverFrameExtractionActivation::test_extract_thumbnail_returns_none_skips_file_write PASSED
tests/test_part_render_finalize_combined_score.py::TestCombinedScoreBlockActivation::test_combined_score_populated_when_block_runs_clean PASSED
tests/test_part_render_finalize_combined_score.py::TestCombinedScoreBlockActivation::test_combined_score_clamped_to_100_when_weights_overshoot PASSED
tests/test_part_render_finalize_combined_score.py::TestCombinedScoreBlockActivation::test_combined_score_uses_viral_when_market_score_missing PASSED
```

Net +6 tests, +0 regressions.

## Risk

**LOW.** Test-only additions. No production code modified.

## Remaining P0/P1/P2 work from followup_7

P0 — both items closed.

P1 — still open (not in scope for this commit):
- P1-T3: regression guard for **H1** (asset overrides hydration in
  `stages/part_setup.py`)
- P1-T4: regression guard for **H3** (subtitle ASS rebuild in
  `stages/part_subtitle.py`)
- P1-T5: regression guard for **H5** (per-part voice-mix block in
  `stages/part_voice_mix.py`)
- P1-T6: regression guard for **H6** (orphan-file cleanup in
  `stages/part_done.py`)

P2 — code-shape recommendations, deferred:
- Refactor the `except: pass` blocks to `except: log + emit_warning`
  pattern.
- Add a `_run_or_warn(block_name, fn)` helper in `render_events.py`
  for consistent silent-failure-with-signal handling.

## References

- Audit root: `docs/review/AUDIT_2026-06-02.md`.
- Findings doc: `docs/review/AUDIT_2026-06-02_followup_7.md` (H2 + H4
  listed under "HIGH-risk silent-fail surfaces").
- Sister bug fixes that motivated this coverage push:
  `docs/review/AUDIT_2026-06-02_followup_5.md` (C1) and
  `docs/review/AUDIT_2026-06-02_followup_6.md` (C2).
- Sprint 6.D closure: `docs/review/AUDIT_2026-06-02_followup_4.md`.

## Status

**Track D P0: CLOSED.** Both T1 and T2 regression-guard tests are
live, green, and indexed. The two HIGH-risk silent-failure surfaces
identified in followup_7 now have call-site activation tests that
will fail loudly if a future refactor breaks the import resolution
path or the side-effect chain.

Track D P1 (H1, H3, H5, H6 coverage) remains open for a future pass.
