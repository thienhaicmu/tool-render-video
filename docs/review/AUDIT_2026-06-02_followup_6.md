# Audit 2026-06-02 — Track C Bug Fix C2: missing _mv_score_part import

Sixth append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## What this closes

The missing `_mv_score_part` import at
`stages/part_render_finalize.py:361` (formerly preserved verbatim
through Sprint 6.D-2.5c per the no-while-I-am-here convention, see
`AUDIT_2026-06-02_followup_4.md` "Known-bug preservation" section).

## Git archaeology

Investigation traced the bug to a specific commit:

| Date | Commit | Event |
|---|---|---|
| 2026-04-27 | `c58813e` "big update add market viral" | Feature INTRODUCED working in monolithic `render_pipeline.py`. Author wrote the complete pipeline: import + per-part call + seg field assignments + `market_viral_scored` WS emit. |
| 2026-04-27 → 2026-05-28 | — | Feature **live for 31 days**, producing real `mv_viral_*` data and emitting `market_viral_scored` per part. |
| **2026-05-28** | `765616d` "Phase A-1..A-4 — decompose render_pipeline.py monolith" | **Refactor regression.** Extracted `process_one_part` to `stages/part_renderer.py`. The call site was copied. The `from app.services.viral_scoring import score_part_for_market as _mv_score_part` line was NOT copied. Python module-scoped imports mean the call now raises NameError caught by surrounding `try/except: pass`. |
| 2026-05-28 → 2026-06-03 | various | Bug was a silent no-op for **6 days**. Zero test coverage explains why nobody noticed (`grep "mv_viral_score" backend/tests/` returns nothing). |
| 2026-06-03 | `26d380d` (Sprint 6.D-2.5c) | Moved the buggy call to `stages/part_render_finalize.py`. Bug preserved by convention. |
| 2026-06-03 | `7a4f899` (Track B) | Removed the vestigial `_mv_score_part` import from `render_pipeline.py` (it had been orphaned since Phase A — sitting unused in the wrong module). |
| 2026-06-03 | THIS commit | Restored import + added 2 regression-guard tests + this ledger entry. |

**Diagnosis: refactor regression, not deliberate disable.** The Phase A
commit message states "All frozen contracts intact. Baseline maintained"
— author intent was behavioral preservation. The market viral feature
was deliberately authored to work and ran in production for 31 days
before the accidental break.

## The fix

```python
# Added to stages/part_render_finalize.py imports:
from app.services.viral_scoring import score_part_for_market as _mv_score_part
```

Plus a module-docstring update replacing the "Known-bug preservation"
note with the fix history record.

## Behavioral consequences (RESTORATION of previously-active behavior)

Each surface returns to its 2026-04-27 → 2026-05-28 behavior:

| Surface | Pre-fix (broken) | Post-fix (restored) |
|---|---|---|
| `_mv_score_part(text, dur, market)` per part | NameError caught | Actual `score_part_for_market` call, ~few-ms latency |
| `seg["mv_viral_score"]` | never set | 0–100 integer |
| `seg["mv_viral_tier"]` | never set | "hot" / "warm" / "normal" / "weak" |
| `seg["mv_viral_market"]` | never set | "US" / "EU" / "JP" |
| `seg["mv_viral_reasons"]` | never set | list of reason strings |
| `market_viral_scored` WS event | never emits | emits per part |
| `result_json["market_viral_parts"]` | empty list (filter `if "mv_viral_score" in _s` excludes all) | populated list with full per-part scoring data |
| `pipeline_ranking.market_score` | falls back to 50.0 default | uses real `mv_viral_score` (0–100) |
| **Output ranking → best-clip selection** | uses 50.0 weight | uses real market scores — may reorder |

## Risk

**MEDIUM**, downgraded from initial HIGH after archaeology.

Original assessment was HIGH because of the output-ranking impact.
After archaeology, the assessment drops to MEDIUM:

- The fix RESTORES the previously-working behavior. The 50.0 default
  was a fallback for the broken state, not the intended design.
- Zero frontend consumers depend on the absence (grep
  `frontend/src/ market_viral` returns nothing).
- WS handlers typically ignore unknown event names — the new
  `market_viral_scored` events won't break the frontend monitor.
- The "best clip" reordering impact is bounded by `combined_weights`
  configuration; default weights treat all signals as comparable.

## Test coverage

Added in the same commit as the fix:

`tests/test_market_viral_call_site.py::TestMarketViralCallSiteActivation`:

1. `test_mv_score_part_is_invoked_when_srt_exists`
   Asserts `_mv_score_part` is called when an SRT file exists, and
   that the returned `mv_viral_*` fields land on the `seg` dict.

2. `test_mv_score_part_skipped_when_srt_missing_keeps_no_op`
   Asserts `_mv_score_part` is still called even when SRT is missing
   (with empty text) — proves the import resolution path is robust.

If the import is ever lost again (e.g., during a future refactor),
both tests will fail because `mock_score.called` would stay False.

This closes the test-coverage gap that allowed the 6-day silent
regression to escape notice.

## Pytest

Before fix: 2078 passed, 1 skipped.
After fix + tests: 2080 passed, 1 skipped, 0 failed.
No baseline regression.

## References

- Code change: `backend/app/orchestration/stages/part_render_finalize.py` —
  one new import line + docstring update.
- Test added: `backend/tests/test_market_viral_call_site.py` —
  new file with 2 regression-guard tests.
- Audit root: `docs/review/AUDIT_2026-06-02.md`.
- Sister bug C1 fix: `docs/review/AUDIT_2026-06-02_followup_5.md`.
- Sprint 6.D closure: `docs/review/AUDIT_2026-06-02_followup_4.md`.
- Original feature commit: `c58813e` (2026-04-27).
- Refactor regression commit: `765616d` (2026-05-28).

## Status

**Bug C2: CLOSED.** Track C closed in full (both C1 and C2 fixed).
The two pre-Sprint-6.D "known-bugs" identified in
`AUDIT_2026-06-02_followup_4.md` are no longer outstanding.

## Operational note

The first render run after this commit will produce visibly different
behavior compared to the previous 6 days:

- New `market_viral_scored` WebSocket events in the per-part stream
  (frontend monitor will ignore them gracefully).
- New populated `market_viral_parts` array in `result_json`.
- Output ranking may select a different "best clip" if multiple clips
  had similar viral scores but different market viral scores.

If any of those changes is unexpected to the user, the fix can be
reverted by removing the new import line. The two regression tests
would then fail loudly, providing an obvious revert marker.
