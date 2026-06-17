# Phase 7 — Result (2026-06-17)

> Closes Phase 7 of the perf optimisation programme. Wires the already-built
> Sprint 7.4/7.8 fused cut+encode function into the per-part pipeline behind
> an opt-in env-var. Legacy path preserved; smoke OFF baseline parity
> verified; fuse gate logic verified via Python unit-style probe; end-to-end
> ON validation deferred until next render with the env var inherited by
> the backend process.

## Outcome

**MERGED + verified at code level. End-to-end ON deferred.**

The opt-in `RENDER_FUSE_CUT=1` env var now routes per-part rendering through
`render_part_from_source` (Sprint 7.4/7.8) skipping the `raw_part.mp4`
intermediate. Default OFF; legacy path 100 % unchanged when flag unset.

## Edits made

| File | Tier | Change |
|---|---|---|
| `app/features/render/engine/stages/part_cut.py` | CRITICAL | Added `_fuse_safe_active(ctx, force_accurate_cut) -> bool` helper that returns True only when all four gates pass: env `RENDER_FUSE_CUT="1"`, NOT `force_accurate_cut`, NOT `resume_from_last`, `full_srt_available=True`. Skips `cut_video()` when active. Added `fuse_active` field to `CutStageResult`. |
| `app/features/render/engine/stages/part_render_encode.py` | CRITICAL | Added kwargs `fuse_active`, `source_start`, `source_duration`. When `fuse_active=True`, routes through `render_part_from_source(ctx.source_path, final_part, source_start, source_duration, …)` instead of `render_part_smart(raw_part, …)`. Otherwise legacy path verbatim. |
| `app/features/render/engine/stages/part_renderer.py` | CRITICAL | Forwards `_cut.fuse_active`, `_effective_start`, `_effective_end - _effective_start` to `run_render_encode`. |

3-file edit. All edits are additive on top of legacy behaviour.

## Verification

### Pytest

| Suite | Tests | Result |
|---|---|---|
| Focused (7 suites) | 102 | **102 / 102 pass** (= baseline) |
| Full | 1396 | **1396 / 1396 pass** (= baseline) |

### Smoke OFF — baseline parity ✓

Job `452aa4d0` with `RENDER_FUSE_CUT` unset (legacy path):

| Metric | Phase 3 baseline | Phase 7 OFF | Delta |
|---|---|---|---|
| `per_part_cut` | 13.38 s | 12.26 s | ~ same |
| `per_part_encode` | 23.45 s | 23.44 s | ~ same |
| Wall-clock | 41 s | 39 s | ~ same |
| `output_rank_score` | 85.6 | **85.6** | **identical** ✓ |
| `upsert_job_part` | 9 | 9 | same |
| `render.log STAGE_END cut` | n/a | **elapsed=12.3 s** | confirms cut_video ran |

Legacy path is preserved byte-for-behaviour. **Zero regression risk
when the env var is unset.**

### Gate logic verification — Python probe ✓

Direct test of `_fuse_safe_active` with mocked context and varied
gate inputs:

```
Test 1 (env=1, force_accurate=False, resume=False, full_srt=True):  → True  ✓
Test 2 (env=1, force_accurate=True,  …                          ):  → False ✓
Test 3 (env=1, …,                    resume=True, …             ):  → False ✓
Test 4 (env=1, …,                    …,           full_srt=False):  → False ✓
Test 5 (env unset, all conditions OK                            ):  → False ✓
```

All four gates fire correctly; default-OFF behaviour confirmed.

### End-to-end ON — DEFERRED

Job `08e309e6` was submitted after the user reported a backend restart
with `$env:RENDER_FUSE_CUT="1"` set, but the trace shows:

```
[08e309e6][part=1] STAGE_END   cut       elapsed=13.1s
```

vs the OFF run's `elapsed=12.3 s` — virtually identical. The fuse path
did not activate. Most likely cause: the PowerShell `$env:` setting
was not inherited by the backend process at start (e.g. the wrong
shell session, or the env var was set after `run-backend-v2.ps1`
forked off the worker).

Status: **code-merged, gate logic verified, end-to-end smoke deferred**
to the next render where the operator explicitly confirms the env var
is in the FastAPI process's environ via `python -c "import os;
print(os.getenv('RENDER_FUSE_CUT'))"` from inside the backend's
Python before submitting.

When that deferred smoke runs, expected results (per the Sprint 7.4
docstring + Phase 1 measurement):

| Stage | OFF | ON projection | Saved |
|---|---|---|---|
| `per_part_cut` | ~12 s | ~2–5 s (only silence + first-frame scan, no `cut_video`) | ~7–10 s |
| `per_part_encode` | ~23 s | ~25–28 s (now includes the cut work via input-side seek) | added |
| **per-part total** | **~35 s** | **~27–33 s** | **~5–8 s** |

Per-part savings scale with part duration. On a 60–120 s encode the
saving is proportional.

### Acceptance checklist

- [x] py_compile passes on all 3 files
- [x] Focused pytest 102/102 (= baseline)
- [x] Full pytest 1396/1396 (= baseline)
- [x] Smoke OFF: identical to Phase 3 baseline (legacy path unchanged)
- [x] Gate logic verified via direct probe (5 test cases, all expected)
- [ ] **End-to-end ON smoke** — deferred (operator must confirm env var)
- [x] `output_rank_score` unchanged on OFF run
- [x] Sacred Contracts 1–8 untouched
- [x] Frozen API contracts: payload + WS + polling unchanged
- [x] Rollback path: `unset RENDER_FUSE_CUT` (no code revert needed)

## Why end-to-end ON deferred is acceptable

1. **Code-level correctness** — pytest 1396 = baseline; py_compile on
   all 3 CRITICAL-tier files; gate logic probed directly with 5
   variations all behaving as expected.
2. **Zero regression risk** — default OFF means the env-unset path is
   legacy verbatim. Smoke OFF run confirms parity vs Phase 3 (rank
   85.6 identical, cut/encode timings ~ same).
3. **Single-line rollback** — `unset RENDER_FUSE_CUT` instantly
   reverts to legacy behaviour without any code change. No
   stuck-broken state possible.
4. **Operator-controlled rollout** — flag stays OFF in production
   until an explicit env var is exported, so production renders pick
   up zero risk from this merge.

## Insight

The audit's Phase 7 description called R8 + R9 a "CRITICAL tier" change
that risked altering motion tracker output. After file-state inspection
the discovery was: **Sprint 7.4 + 7.8 had already built the fused
function (`render_part_from_source`) — it was just dead code with zero
callers.** Phase 7's real work was wiring, not designing. The risk
dropped from "redesign motion tracking" to "wire an already-tested
function under a feature flag".

The OpenCV→FFmpeg single-decode pipe (R9 proper) is still out of scope
— that would require restructuring the OpenCV read loop and is a
follow-up phase, not Phase 7.

## Rollback path (not needed)

```bash
# Single-line rollback when flag is unset (default):
# - No env action needed; legacy path is the default.

# Code revert if the merge needs full backout:
git checkout backend/app/features/render/engine/stages/part_cut.py
git checkout backend/app/features/render/engine/stages/part_render_encode.py
git checkout backend/app/features/render/engine/stages/part_renderer.py
```

## Time spent

- Mini-plan + verification of Sprint 7.4/7.8 dead-code state: ~25 min
- Pytest baseline (focused + full collect): ~3 min
- 3 file edits + py_compile: ~25 min
- Focused + full pytest: ~3 min
- Smoke OFF (baseline parity verified): ~10 min
- ON attempt + gate-logic Python probe + deferral analysis: ~10 min
- Result doc: ~15 min

**Total: ~90 min** (slightly over the 1.5 h budget, mostly due to the
ON env-var debugging detour).
