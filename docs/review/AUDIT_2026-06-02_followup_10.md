# Audit 2026-06-02 — Track D P2 Action Items: stage + pipeline smoke tests

Tenth append-only ledger entry to `docs/review/AUDIT_2026-06-02.md`.

Date: 2026-06-03

## What this closes

Track D P2 action items from the audit ledger
(`docs/review/AUDIT_2026-06-02_followup_7.md`):

- 5 stage helper smoke tests (originally listed as "8 commits" — 3 of
  those 8 stages were already covered by Track C / P0 / P1 work).
- 4 orchestration pipeline helper smoke tests.

Total: 9 modules → 9 new test files → 34 new tests in one bundled
commit. P2 backlog from followup_7 now empty.

## Audit gap closed

Per followup_7 Finding 1, 20 of 22 Sprint 6.D modules had zero direct
test imports. After this batch:

| Module | Coverage source |
|---|---|
| `stages/part_done.py` | Track C C1 + Track D T1 |
| `stages/part_render_finalize.py` | Track C C2 + Track D T2 + Contract #8 |
| `stages/part_asset_planner.py` | Track D T3 |
| `stages/part_render_context.py` | **P2 smoke (this commit)** |
| `stages/part_cut.py` | **P2 smoke (this commit)** |
| `stages/part_render_setup.py` | **P2 smoke (this commit)** |
| `stages/part_render_encode.py` | **P2 smoke (this commit)** |
| `stages/part_voice_mix.py` | **P2 smoke (this commit)** |
| `orchestration/pipeline_setup.py` | **P2 smoke (this commit)** |
| `orchestration/pipeline_source_prep.py` | **P2 smoke (this commit)** |
| `orchestration/pipeline_narration.py` | **P2 smoke (this commit)** |
| `orchestration/pipeline_finalize.py` | **P2 smoke (this commit)** |

12 of 22 Sprint 6.D modules now have direct test imports. The
remaining 10 are `motion_crop_*.py` modules + `part_renderer.py`
skeleton, all of which have indirect coverage via re-export shims
or are thin orchestrators (`part_renderer.py` delegates everything
to the 8 stages helpers).

## What was added

9 test files, all in `backend/tests/`:

| File | Tests | Module under test |
|---|---|---|
| `test_smoke_part_render_context.py` | 3 | `PartRenderContext` dataclass |
| `test_smoke_part_cut.py` | 4 | `run_cut_stage` + `CutStageResult` |
| `test_smoke_part_render_setup.py` | 4 | `run_render_preflight` + `RenderPreflightResult` |
| `test_smoke_part_render_encode.py` | 4 | `run_render_encode` + `RenderEncodeResult` |
| `test_smoke_part_voice_mix.py` | 3 | `run_part_voice_mix` |
| `test_smoke_pipeline_setup.py` | 4 | `setup_render_pipeline` + `PipelineSetupResult` |
| `test_smoke_pipeline_source_prep.py` | 3 | `prepare_render_source` + `SourcePrepResult` |
| `test_smoke_pipeline_narration.py` | 4 | `run_manual_voice_tts` |
| `test_smoke_pipeline_finalize.py` | 5 | `run_render_finalize` + `FinalizeContext` |

Total: 34 tests.

## Coverage shape

Each smoke test asserts the high-value refactor-regression surfaces:

1. **Signature integrity** — `inspect.signature(fn)` against a frozen
   set of expected param names. Catches kwarg renames that pytest
   collection would NOT catch (callers bind by name, so the rename
   is silent at import time).
2. **Dataclass field integrity** — `dataclasses.fields(cls)` against
   a frozen set of expected field names. Catches field renames that
   silently strand callers (callers alias each field back to a local
   variable; a rename leaves the alias unbound).
3. **Return-type annotation** — string-compared since modules use
   `from __future__ import annotations`. Catches accidental
   annotation drift during refactors.
4. **Kw-only enforcement** — for the 2 pipeline functions that use
   `*` to force keyword-only args. Catches accidental removal of
   the `*` (which would make positional binding legal and freeze
   param order).
5. **Behavioral skip-path probes** — for the 3 functions with
   conditional execution (voice_mix, manual_voice_tts, setup). One
   happy-path invocation that asserts the early-return / normalization
   logic is intact.

## Why string comparison for annotations

The Sprint 6.D modules use `from __future__ import annotations`, which
makes annotations stored as strings rather than resolved types. The
test author originally used `is` comparison against the actual class,
got 8 failures, and converted to string comparison. This is the
documented Python 3.7+ pattern when modules opt into PEP 563.

Trade-off: string comparison cannot catch a typo'd annotation that
refers to a non-existent class. The mitigation is that `inspect.signature`
still resolves the parameter shape — a typo'd class reference would
show up as the typo string, not the corrected one.

## Sacred Contracts honored

These tests do not touch any Sacred Contract surface. They are
inspection-only against the public API. No production code modified.

## Pytest

Before this batch: 2108 passed, 1 skipped (after followup_9).
After this batch: **2142 passed, 1 skipped**, 0 failed.

Net +34 tests, 0 regressions.

## Risk

**LOW.** Pure introspection tests. No FFmpeg, no DB, no file I/O
beyond a few tmp_path probes in the behavioral skip-path tests.
Fastest section of the test suite (~3 seconds for all 34).

## Remaining work from followup_7

P3 — open:
- Contract #2 RenderRequest default audit (1 commit) — verify every
  new field added to `schemas.py::RenderRequest` defaults to False
  or disabled-equivalent.
- Contract #7 import-graph test (1 commit) — static analysis that no
  module outside `app/db/` or `services/db.py` calls
  `sqlite3.connect()`.
- Sacred Contract #3 audit of `backend/app/ai/**` (broader scope,
  D5 candidate from followup_7).

Code-shape recommendations — open, HIGH risk gated:
- Refactor `except: pass` blocks to `except: log + emit_warning`
  pattern.
- Add `_run_or_warn(block_name, fn)` helper in `render_events.py`
  for consistent silent-failure-with-signal handling.

## References

- Audit root: `docs/review/AUDIT_2026-06-02.md`.
- D2 audit findings: `docs/review/AUDIT_2026-06-02_followup_7.md`.
- P0 closure (T1+T2): `docs/review/AUDIT_2026-06-02_followup_8.md`.
- P1 closure (T3 + Contracts #1/#6/#8): `docs/review/AUDIT_2026-06-02_followup_9.md`.
- Sprint 6.D closure: `docs/review/AUDIT_2026-06-02_followup_4.md`.

## Status

**Track D P2: CLOSED.** All 5 uncovered stages/* helpers + 4
orchestration pipeline_*.py helpers now have direct call-site /
signature smoke tests. The audit's Finding 1 gap (20 modules with
zero direct test imports) is reduced to 10, and the remaining 10
all have indirect coverage paths.

Track D P3 + code-shape recommendations remain open.
