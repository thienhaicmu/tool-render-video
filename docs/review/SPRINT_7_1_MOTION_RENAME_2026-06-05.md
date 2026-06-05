# Sprint 7.1 — Motion crop rename `legacy.py` → `motion_pixel_diff.py`

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-1-motion-rename` (Sprint 7 cycle first commit)
**Baseline:** Pytest 2397 passed / 1 skipped / 0 failed @ `5578f0c` (main, Sprint 7.x plan commit)
**Final pytest:** 2397 passed / 1 skipped / 0 failed (rename = zero behaviour change)
**Source:** `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §4 — *"the 'legacy' name in the SPRINT_PLAN recap was a misclassification… Recommend a future rename to `motion_pixel_diff.py`."*

## Purpose

The module name `motion_crop/legacy.py` has misled at least two audit cycles into investigating it as dead code. It is NOT dead — three live render-path callers depend on it for the pixel-diff fallback when subject tracking cannot find or hold a lock. Renaming to `motion_pixel_diff.py` describes the module's actual behaviour and prevents the same misclassification from recurring.

## Scope (pure rename, additive only)

`git mv backend/app/services/motion_crop/legacy.py backend/app/services/motion_crop/motion_pixel_diff.py`

Plus:
- 2 production import updates (`motion_crop/__init__.py:89`, `motion_crop/path.py:64`)
- 1 docstring header refresh on `motion_pixel_diff.py` (now cites Sprint 7.1 + the misclassification rationale)
- 2 comment refreshes inside `motion_crop/__init__.py` (lines 88, 321 — adapt the historical Sprint 6.D-3.7 notes to point at the new filename)
- Symbol names UNCHANGED: `detect_motion_center`, `_build_motion_path_legacy`, `_detect_scene_ranges_in_clip`. Renaming the `_legacy` suffix on the function name would force a wider blast radius (callers grep for it) — out of scope this sprint.

## Caller audit (pre-rename)

| File:line | Import |
|---|---|
| `motion_crop/__init__.py:89-93` | re-export tuple of 3 symbols |
| `motion_crop/path.py:64` | `_build_motion_path_legacy` |

**Zero tests import `motion_crop.legacy`** — confirmed by grep across `backend/tests/`. No backward-compat shim required.

## Sacred Contract walk

| Contract | Touched? | Disposition |
|---|---|---|
| #1 result_json aliases | No | unchanged |
| #2 RenderRequest additive | No | unchanged |
| #3 AI returns None | No | unchanged (module is not under `backend/app/ai/**`) |
| #4 Job stage frozen | No | unchanged |
| #5 Part stage frozen | No | unchanged |
| #6 `_emit_render_event` shape | No | unchanged — no events emitted from this module |
| #7 `data/app.db` | No | unchanged |
| #8 `qa_pipeline` | No | unchanged — qa never references motion_crop internals |
| NVENC Performance Protection | No | unchanged — this module does no FFmpeg encode |

## Test coverage

The 3 symbols are exercised through:
- `backend/tests/test_motion_crop_guards.py` (subject-tracker fallback paths)
- `backend/tests/test_probe_unification.py` (motion-path probe flow)
- `backend/tests/test_render_audit_p0_fixes.py` (P0 motion regression suite)

All three test modules import via the `app.services.motion_crop` re-export surface — they do NOT import `motion_crop.legacy` or `motion_crop.motion_pixel_diff` directly. **Zero test changes required.** Verified: 52 passed in 1.71s post-rename on the three modules above.

Full pytest: 2397 passed / 1 skipped / 0 failed — identical to baseline.

## What this sprint does NOT do

- Does NOT rename the `_build_motion_path_legacy` function. Renaming the function would touch every caller's grep target + the `_legacy` suffix appears in audit docs as a stable identifier. Save for a future sprint if anyone wants the consistency cleanup.
- Does NOT update historical audit docs (`AUDIT_2026-06-02_followup_4.md`, `SPRINT_6D_PLAN.md`, etc.) that mention `motion_crop_legacy`. Those are time-stamped records of past state — editing them rewrites history.
- Does NOT add a backward-compat shim at `motion_crop/legacy.py`. The grep confirmed zero external callers; the shim would just be a future cleanup target.

## Cross-references

- `docs/review/DEAD_CODE_PURGE_BLOCKERS_2026-06-05.md` §4 — scoped this rename
- `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.1 row — committed scope
- `backend/app/services/motion_crop/motion_pixel_diff.py` (new path)
- `backend/app/services/motion_crop/__init__.py:88-95, 321-324` — updated comment + import
- `backend/app/services/motion_crop/path.py:64` — updated import

## Sprint 7.1 commit chain

1. Rename + import updates + audit doc — single commit on `feature/sprint-7-1-motion-rename`.
2. PR + merge to main.
