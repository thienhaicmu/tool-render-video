# Sprint 7.8 — Motion-aware `raw_part` skip + fused cut+motion-crop (Plan)

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-8-motion-aware-fuse` (off main @ `ec66390`)
**Baseline:** 2454 passed / 1 skipped / 0 failed @ Sprint 7.6 FULL merge (PR #15)
**Tier:** HIGH-CRITICAL — Render Edit Protocol applies (touches `motion_crop/` + `base_clip_renderer.py` + `part_cut.py` + `part_render_encode.py`).
**Ship gate:** `FEATURE_RAW_PART_SKIP_MOTION_AWARE=0` default OFF — separate flag from Sprint 7.4 (Sacred Contract #2 spirit preservation).
**Status:** APPROVED 2026-06-05 (architect plan via Agent Team Protocol)

---

## Purpose

Sprint 7.4 shipped the fused cut+render path but explicitly excluded the motion-aware-crop case (`motion_aware_crop=True` stays on the cut→render_part_smart path). Sprint 7.8 closes that gap: when ALL of (Sprint 7.4 predicate fires) AND (NEW flag on) AND (`payload.motion_aware_crop=True`), bypass `cut_video()` AND have `render_motion_aware_crop` pull frames from a source-relative window via `cv2.VideoCapture.set(CAP_PROP_POS_FRAMES, ...)`.

---

## Architecture finding

**Motion-crop seek primitives already exist** in 2 call sites (`path_scene.py:103`, `detection.py:153`). The refactor is small (~200 prod LOC), not big. Sprint 7.8 ships as a single sprint, not 7.8a + 7.8b.

What does NOT yet support a window (the wiring delta):
- `render_motion_aware_crop` main encode loop — reads `cap.read()` linearly.
- `build_subject_path` single-scene fast path — opens cap, reads linearly.
- `_build_motion_path_legacy` — reads linearly.
- `_detect_scene_ranges_in_clip` — scans entire file.
- `_has_subject_in_sample` — samples whole file.
- FFmpeg argv at `render_motion_aware_crop` — `-i input_path` (no `-ss/-t`).

**Caveat (contained):** `cap.set(CAP_PROP_POS_FRAMES, ...)` accuracy depends on keyframe density. Mitigation: forward-skim ≤180 frames (~3s at 60fps) after seek to align. Same `force_accurate_cut` fallback Sprint 7.4 uses for FFmpeg-side seek.

---

## Files touched

| File | Action | LOC |
|---|---|---|
| `backend/app/services/render/base_clip_renderer.py` | modify | ~30 (motion-aware branch in render_part_from_source) |
| `backend/app/services/motion_crop/__init__.py` | modify | ~60 (kwargs + argv + loop bounds + propagation) |
| `backend/app/services/motion_crop/path.py` | modify | ~30 (single-scene seek + bound) |
| `backend/app/services/motion_crop/motion_pixel_diff.py` | modify | ~25 (`_build_motion_path_legacy` + `_detect_scene_ranges_in_clip`) |
| `backend/app/services/motion_crop/detection.py` | modify | ~10 (`_has_subject_in_sample` window) |
| `backend/app/orchestration/stages/part_cut.py` | modify | ~12 (flag mirror + `_skip_active` gate) |
| `backend/app/orchestration/stages/part_render_encode.py` | modify | ~25 (flag mirror + routing change) |
| `backend/app/orchestration/render_pipeline.py` | modify | +5 (master flag read) |
| `backend/app/orchestration/stages/part_renderer.py` | modify | +3 (mirror flag) |
| `backend/app/orchestration/stages/part_render_setup.py` | modify | +3 (mirror flag) |
| `backend/tests/test_motion_aware_fuse.py` | new | ~250 (~30 tests across 9 sections) |

**Total:** ~200 prod LOC + ~250 test LOC = ~450 LOC.

---

## Flag strategy

**Separate flag `FEATURE_RAW_PART_SKIP_MOTION_AWARE`, default OFF.** Both flags required to engage motion-aware fuse: `FEATURE_RAW_PART_SKIP=1` AND `FEATURE_RAW_PART_SKIP_MOTION_AWARE=1`. Preserves Sacred Contract #2 spirit — operators already running 7.4 in production see zero behaviour change after 7.8 deploy until they explicitly opt into the motion-aware case.

`_skip_active` gate update in `part_cut.py`:

```python
_motion_aware_fuse_enabled = (
    _FEATURE_RAW_PART_SKIP_MOTION_AWARE and _payload_motion_aware
)
_skip_active = (
    _skip_predicate_fires
    and _FEATURE_RAW_PART_SKIP
    and (not _payload_motion_aware or _motion_aware_fuse_enabled)
)
```

---

## Detailed change specs

### A. `motion_crop/__init__.py` — `render_motion_aware_crop`

Signature additions (kwargs, all default None/False = pre-7.8 byte-identical):

```python
source_start_sec: float | None = None,
source_duration_sec: float | None = None,
source_seek_force_accurate: bool = False,
```

Behavioural changes:
1. **FFmpeg argv:** when both seek kwargs set, prepend `-ss start -t dur` BEFORE `-i input_path` (input-side fast seek). When `source_seek_force_accurate=True`, place AFTER `-i input_path` (output-side accurate). The stdin (`-f rawvideo -i -`) input is NOT seeked.
2. **OpenCV main loop:** compute `start_frame = int(round(source_start_sec * src_fps))`, `frame_budget = int(round(source_duration_sec * src_fps))`. Issue `cap.set(CAP_PROP_POS_FRAMES, float(start_frame))`. Bound the inner loop with `frames_written < frame_budget`.
3. **Forward-skim alignment (R1 mitigation):** after `cap.set`, read `cap.get(CAP_PROP_POS_FRAMES)`; if mis-aligned, read-and-discard up to 180 frames to align. Log warn if skim > 30.
4. **Scene-aware tracking forced OFF in fuse mode:** when `source_start_sec is not None`, force `scene_aware_tracking=False` at the caller (this function). Single-scene tracking still runs.
5. **Pass-through to `_detect_scene_ranges_in_clip`, `_has_subject_in_sample`, `build_motion_path`, `_build_motion_path_legacy`** — all 4 receive the same kwargs.

### B. `motion_crop/path.py` — `build_subject_path`

Add kwargs. Single-scene fast path (`cap = cv2.VideoCapture(...)`):
- Compute `start_frame`, `frame_budget`. Seek. Bound the `while True:` loop.
- Replace `frame_count` (whole file) with `frame_budget` (window only) at the pad-to-N step.

Multi-scene branch: when source-window mode active, NEVER taken (caller forces `scene_aware_tracking=False`).

### C. `motion_crop/motion_pixel_diff.py`

Add `source_start_sec` / `source_duration_sec` to `_build_motion_path_legacy` and `_detect_scene_ranges_in_clip`. Seek + bound.

### D. `motion_crop/detection.py` — `_has_subject_in_sample`

Add kwargs. When set, compute window total frames, derive step inside window, sample within `range(start_frame, end_frame, step)`. Guard `step = max(1, window_total // max(1, sample_count))`.

### E. `services/render/base_clip_renderer.py` — `render_part_from_source` motion-aware branch

Today (7.4): falls through to `render_part` with seek kwargs. Sprint 7.8 adds motion-aware branch.

**Option A picked:** add `motion_aware_crop: bool = False` + `reframe_mode`, `_motion_cache_key`, `_fallback_flag` kwargs. When `motion_aware_crop=True`, branch to `render_motion_aware_crop(input_path=source_path, source_start_sec=source_start, source_duration_sec=source_duration, ...)`. NVENC semaphore acquired in this branch (4-line acquire pattern from `render_part_smart`).

### F. `stages/part_cut.py` — `_skip_active` gate

Add flag mirror + update gate per Flag strategy section above. Update `raw_part_skip_eligible` debug log to include `FEATURE_RAW_PART_SKIP_MOTION_AWARE` and the `_motion_aware_fuse_enabled` derived bool.

### G. `stages/part_render_encode.py` — `_raw_part_absent` routing

Change the existing 7.4 branch at L313:

```python
# Before (7.4):
if _raw_part_absent and not ctx.payload.motion_aware_crop:
    render_part_from_source(...)
else:
    render_part_smart(...)
```

To:

```python
# Sprint 7.8:
if _raw_part_absent:
    # Both Sprint 7.4 (motion=False) and 7.8 (motion=True) fuse via
    # render_part_from_source. Motion-aware branch is selected by the
    # motion_aware_crop kwarg inside render_part_from_source.
    render_part_from_source(
        ..., existing kwargs ...,
        motion_aware_crop=ctx.payload.motion_aware_crop,
        reframe_mode=ctx.payload.reframe_mode,
        _motion_cache_key=_motion_ck,  # windowed below
        _fallback_flag=_motion_crop_fallback,
    )
else:
    render_part_smart(...)  # unchanged
```

**Windowed cache key:** when `_raw_part_absent and ctx.payload.motion_aware_crop`, append `f"-w{start:.3f}-{dur:.3f}"` suffix to `_motion_ck` at THIS call site (not inside `motion_crop`). Prevents stale-hit collisions across different windows of same source. Pinned by test.

### H. Env flag mirror — 5 sites

Add `_FEATURE_RAW_PART_SKIP_MOTION_AWARE: bool = os.getenv("FEATURE_RAW_PART_SKIP_MOTION_AWARE", "0") == "1"` at:
- `render_pipeline.py` (master)
- `part_cut.py`
- `part_renderer.py`
- `part_render_setup.py`
- `part_render_encode.py`

Pin coherent reads via test (mirroring Sprint 7.4's `TestFlagReadsCoherent`).

---

## Sacred Contracts walk

| # | Contract | Touched? | Disposition |
|---|---|---|---|
| 1 | result_json aliases | No | Unchanged. |
| 2 | RenderRequest additive | **Engaged but compliant** | No new RenderRequest field. New env flag defaults `"0"` → False. Zero behaviour change at default. |
| 3 | AI returns None | No | Motion-crop not in `backend/app/ai/**`. |
| 4 | Job stage frozen | No |
| 5 | Part stage frozen | **Preserved** | `JobPartStage.CUTTING` upsert at `part_cut.py:302` stays unconditional. Skip branch sits AFTER upsert. |
| 6 | `_emit_render_event` signature | No |
| 7 | `data/app.db` sole | No |
| 8 | qa_pipeline never bypassed | **Verified clean** | qa_pipeline reads `final_part` only, never `raw_part`. |

---

## Test plan — `backend/tests/test_motion_aware_fuse.py`

**Section 1 — TestSignatures (5):** kwargs added to `render_motion_aware_crop`, `build_subject_path`, `_build_motion_path_legacy`, `_has_subject_in_sample`, `render_part_from_source`.

**Section 2 — TestBackwardCompat (3):** with seek kwargs None, FFmpeg argv has no `-ss`/`-t` between binary and `-i input_path`; `build_subject_path` does not call `cap.set(CAP_PROP_POS_FRAMES, ...)`; `_has_subject_in_sample` samples full-file range.

**Section 3 — TestSeekWiring (4, mocked OpenCV):** input-side seek default (`-ss N -t M -i source`); output-side with `source_seek_force_accurate=True`; `build_subject_path` calls `cap.set(CAP_PROP_POS_FRAMES, int(start * fps))`; frame budget enforced.

**Section 4 — TestFlagDefaultsOff (3):** Sacred Contract #2 — unset/`"1"`/strict compare.

**Section 5 — TestFlagReadsCoherent (5):** 5-site mirror pin.

**Section 6 — TestSkipActiveTruthTable (8):** expanded from Sprint 7.4's 5 to cover motion_aware × base_flag × motion_aware_flag truth combinations.

**Section 7 — TestProductionSourcePins (4):** `run_cut_stage` references new flag + `_motion_aware_fuse_enabled`; `run_render_encode` passes `motion_aware_crop=ctx.payload.motion_aware_crop`; `render_part_from_source` contains `render_motion_aware_crop` call; motion-aware branch contains `NVENC_SEMAPHORE` acquire.

**Section 8 — TestSacredContractsPreserved (2):** CUTTING upsert appears BEFORE `if _skip_active:`; qa_pipeline.py unchanged.

**Section 9 — TestMotionCacheKeyWindowAware (1):** windowed cache key includes source_start/source_duration markers.

**Net pytest delta target:** +~30 new tests → 2484 total.

---

## Visual review delta (extends Sprint 7.4 table 5 → 8 samples)

| Sample | Config | Purpose |
|---|---|---|
| 6 | RAW_PART_SKIP=1 + MOTION_AWARE=0 + motion_aware=True payload | **7.8 regression pin** — must behave like Sprint 7.4 (motion-aware excluded). Byte-identical to baseline. |
| 7 | RAW_PART_SKIP=1 + MOTION_AWARE=1 + motion_aware=True + subtitle-off | **7.8 active case** — fuse fires. Compare tracking quality vs Sample 1. |
| 8 | RAW_PART_SKIP=1 + MOTION_AWARE=1 + motion_aware=True + bad-first-frame source | **Accuracy fallback** — verify output-side seek + OpenCV forward-skim align. |

---

## Risk register

| ID | Risk | Mitigation |
|---|---|---|
| R1 | OpenCV seek hits nearest keyframe, not exact frame | Forward-skim ≤180 frames after `cap.set`. Bounded. Log warn > 30. |
| R2 | Motion cache key collision across different windows | Cache key MUST include `source_start_sec` + `source_duration_sec`. Pinned by test. |
| R3 | Scene-aware tracking on windowed source: ranges in source coords | Force `scene_aware_tracking=False` in fuse mode. Scene-aware-in-fuse → Sprint 7.9+. |
| R4 | Audio sync at FFmpeg input-side seek (7.4 inherited) | `force_accurate_cut=True` escape hatch. Sample 8 pin. |
| R5 | NVENC double-acquire if `render_motion_aware_crop` grows acquire | Source-pin test: zero `NVENC_SEMAPHORE.acquire` inside that function. |
| R6 | Combined 7.4+7.8 visual review masks 7.8-specific regression | Sample 6 specifically isolates 7.8 changes. |

---

## Rollback

1. **Env flip:** `FEATURE_RAW_PART_SKIP_MOTION_AWARE=0`. Reverts to Sprint 7.4 (motion-aware excluded). Also: `FEATURE_RAW_PART_SKIP=0` reverts entire fuse path.
2. **Git revert:** revert Sprint 7.8 PR. All changes flag-gated default-OFF → mechanical revert. Sprint 7.4 stays intact.

No DB migration, no file-format change, no cleanup of orphan files needed.

---

## What this sprint does NOT do

1. Does NOT change behaviour at default flag values. Pinned by tests.
2. Does NOT change `render_part_smart` signature (Sprint 5.2 freeze preserved).
3. Does NOT modify `qa_pipeline.py`. Sacred Contract #8 untouched.
4. Does NOT modify `RenderRequest` or `schemas.py`. Sacred Contract #2 zero-touch.
5. Does NOT touch `data/app.db` or any DB module. Sacred Contract #7 untouched.
6. Does NOT touch the frozen job/part stage names. Sacred Contracts #4/#5 untouched.
7. Does NOT enable scene-aware tracking under fuse mode. Sprint 7.9+ if needed.
8. Does NOT delete `cut_video`, `raw_part.mp4` orchestration, or `render_part_smart`. All legacy paths remain.
9. Does NOT skip Sprint 7.4's visual review. Combined Sample 1-8 review is one review.
10. Does NOT alter NVENC semaphore semantics. Max 1 acquire per part.

---

## Cross-references

- `docs/review/SPRINT_7_4_RAW_PART_FUSE_2026-06-05.md` — Sprint 7.4 closure
- `docs/review/SPRINT_7_6_FULL_2026-06-05.md` — Sprint 7.6 FULL closure (last merge to main)
- `backend/app/services/render/base_clip_renderer.py` — `render_part_from_source`
- `backend/app/services/motion_crop/__init__.py:359` — `render_motion_aware_crop`
- `backend/app/services/motion_crop/path.py:69` — `build_subject_path`
- `backend/app/orchestration/stages/part_cut.py:320-322` — `_skip_active` gate
- `backend/app/orchestration/stages/part_render_encode.py:300-355` — `_raw_part_absent` routing
- `backend/tests/test_motion_aware_fuse.py` — Sprint 7.8 test suite (new)
