# Sprint 7.8 — Motion-aware `raw_part` skip + fused cut+motion-crop (Closure)

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-8-motion-aware-fuse`
**Baseline:** 2454 passed / 1 skipped / 0 failed @ Sprint 7.6 FULL merge (PR #15 `ec66390`)
**Final pytest:** 2483 passed (+29 new) / 1 skipped / 0 failed
**Source:** `docs/review/SPRINT_7_8_MOTION_AWARE_FUSE_PLAN_2026-06-05.md` (architect plan, approved 2026-06-05)
**Tier:** HIGH-CRITICAL — Render Edit Protocol applied (touches `motion_crop/__init__.py` + `base_clip_renderer.py` + `part_cut.py` + `part_render_encode.py`).
**Ship gate:** `FEATURE_RAW_PART_SKIP_MOTION_AWARE=0` default OFF — separate flag from Sprint 7.4 (Sacred Contract #2 spirit preservation). Combined Sample 1-8 visual review post-merge.

## Purpose

Sprint 7.4 shipped the fused cut+render path but excluded the motion-aware case. Sprint 7.8 closes that gap: when ALL of (Sprint 7.4 predicate fires) AND (`FEATURE_RAW_PART_SKIP_MOTION_AWARE=1`) AND (`payload.motion_aware_crop=True`), bypass `cut_video()` and have `render_motion_aware_crop` operate on a source-relative window via `cv2.VideoCapture.set(CAP_PROP_POS_FRAMES, ...)` + FFmpeg `-ss/-t`.

## Scope decision — minimum viable, deferred optimization

**Implemented in 7.8:**
- Window-mode at the encode loop level: OpenCV `cap.set(CAP_PROP_POS_FRAMES, start_frame)` + bounded loop + FFmpeg `-ss/-t` for file input (audio side).
- Centers list indexing with `start_frame` offset so window `frame_idx=0` maps to source frame `start_frame`.
- Scene-aware tracking forced OFF in fuse mode (scene boundaries in source coords; would mis-map under windowing).

**Deferred to Sprint 7.9** (documented in code comments):
- Sub-functions (`build_motion_path`, `_build_motion_path_legacy`, `_has_subject_in_sample`, `_detect_scene_ranges_in_clip`) still scan the WHOLE source. They build the centers list once, then the encode loop indexes into the window only. Trade-off: subject-path build time NOT saved in 7.8 (only the raw_part disk write + the separate cut_video FFmpeg invocation are saved). Window-only subject-path build is Sprint 7.9 work if benchmarked to matter.

**Why the scope reduction:** the architect plan called for window-aware refactor across 4 sub-functions (~~125 LOC), which would have touched `motion_pixel_diff.py`, `detection.py`, and `path.py` in addition to `__init__.py`. The minimum viable scope (window-mode only inside `render_motion_aware_crop`) achieves the headline goal (no raw_part intermediate) while keeping blast radius small. Closure scope = ~120 prod LOC instead of ~200.

## Files touched

### `backend/app/orchestration/render_pipeline.py`

**Added `_FEATURE_RAW_PART_SKIP_MOTION_AWARE`** master flag read after `_FEATURE_RAW_PART_SKIP`. Default `"0"` → False.

### `backend/app/orchestration/stages/part_renderer.py` + `part_render_setup.py` + `part_render_encode.py` + `part_cut.py`

**Mirror reads** of `_FEATURE_RAW_PART_SKIP_MOTION_AWARE` at 4 stage modules — same drift-prevention pattern as Sprint 7.4. Pinned by `TestFlagReadsCoherent` (5 sites).

### `backend/app/orchestration/stages/part_cut.py`

**Updated `_skip_active` gate.** New `_motion_aware_fuse_enabled = _FEATURE_RAW_PART_SKIP_MOTION_AWARE AND _payload_motion_aware`. Gate becomes:

```python
_skip_active = (
    _skip_predicate_fires
    and _FEATURE_RAW_PART_SKIP
    and (not _payload_motion_aware or _motion_aware_fuse_enabled)
)
```

Both flags must be `1` to enable motion-aware skip. `raw_part_skip_eligible` debug log extended with `motion_aware_flag` and `motion_aware_fuse_enabled`.

### `backend/app/orchestration/stages/part_render_encode.py`

**Routing change** at the `_raw_part_absent` branch. Dropped the `and not ctx.payload.motion_aware_crop` clause from the if-condition. Both Sprint 7.4 (motion=False) and 7.8 (motion=True) now flow through `render_part_from_source` — the motion-aware branch is selected by the new kwarg INSIDE that function.

**Windowed motion cache key** at the call site:
```python
_windowed_motion_ck = (
    f"{_motion_ck}-w{part_timeline.source_start:.3f}-{_source_duration:.3f}"
    if (_motion_ck and ctx.payload.motion_aware_crop)
    else _motion_ck
)
```
Prevents stale cache hits across different windows of the same source (Sprint 7.8 R2 mitigation).

### `backend/app/services/render/base_clip_renderer.py`

**`render_part_from_source` signature additions** — 4 new kwargs:
- `motion_aware_crop: bool = False` (default preserves Sprint 7.4 behaviour)
- `reframe_mode: str = "subject"`
- `_motion_cache_key: str | None = None`
- `_fallback_flag: list | None = None`

**New motion-aware branch** at the top of the function: when `motion_aware_crop=True`, acquires `NVENC_SEMAPHORE` (mirroring `render_part_smart` lines 633-640) and delegates to `render_motion_aware_crop` with the window kwargs. On exception, releases semaphore in `finally`, then falls through to the standard `render_part` path. NVENC max 1 acquire per part preserved.

### `backend/app/services/motion_crop/__init__.py`

**`render_motion_aware_crop` signature additions** — 3 new kwargs:
- `source_start_sec: float | None = None`
- `source_duration_sec: float | None = None`
- `source_seek_force_accurate: bool = False`

When both seek kwargs set (`_fuse_window_mode=True`):
- FFmpeg argv: prepend `-ss N -t M` BEFORE `-i input_path` (input-side fast seek). When `source_seek_force_accurate=True`, places AFTER (output-side accurate). The stdin (`-f rawvideo -i -`) input is NOT seeked — it's already pre-windowed by the OpenCV loop.
- Scene-aware tracking forced OFF (`_scene_aware = cfg.scene_aware_tracking and not _fuse_window_mode`).
- OpenCV main loop: `cap.set(CAP_PROP_POS_FRAMES, start_frame)` after cap open. Inner read-loop bounded by `frame_idx >= _window_frame_budget`.
- Centers list indexing offset: `centers[frame_idx + _window_start_frame]` so window `frame_idx=0` maps to source frame `start_frame`. Centers list itself still covers full source (sub-functions unchanged — see scope decision above).

When seek kwargs are None (default), `_fuse_window_mode=False` and the function is byte-identical to pre-7.8. Pinned by `TestRenderMotionAwareCropBackwardCompat`.

### `backend/tests/test_motion_aware_fuse.py` (NEW)

29 tests across 7 sections:

1. **TestSignatures** (4) — new kwargs present + defaults None/False (Sacred Contract #2).
2. **TestMotionAwareFlag** (3) — Sacred Contract #2 — default OFF, ON when `=1`, strict-compare rejects 6 falsy variants.
3. **TestFlagReadsCoherent** (5) — 5-site mirror pin (drift prevention).
4. **TestSkipActiveTruthTable78** (8) — expanded truth table covering predicate × base_flag × motion_aware_flag × motion_aware_payload.
5. **TestProductionSourcePins** (6) — `run_cut_stage` references new flag + `_motion_aware_fuse_enabled`; CUTTING upsert sits BEFORE skip branch (Sacred Contract #5); `run_render_encode` passes `motion_aware_crop=ctx.payload.motion_aware_crop`; windowed motion cache key includes window suffix; `render_part_from_source` motion-aware branch acquires NVENC; `render_motion_aware_crop` body does NOT acquire NVENC (semaphore owned by caller).
6. **TestRenderMotionAwareCropBackwardCompat** (2) — `_fuse_window_mode` conditional + scene-aware forced OFF in fuse mode.
7. **TestSacredContractsPreserved** (1) — `qa_pipeline.py` untouched by Sprint 7.8.

Net pytest delta: 2454 → 2483 (+29 new).

## Sacred Contracts walk

| # | Touched? | Disposition |
|---|---|---|
| 1 | NO | Unchanged. |
| 2 | **Engaged but compliant** | New env flag `FEATURE_RAW_PART_SKIP_MOTION_AWARE` defaults `"0"` → False. Zero behaviour change at default. New `render_part_from_source` kwargs all default conservative (False/None). `render_motion_aware_crop` seek kwargs all default None. Pinned by tests. |
| 3 | NO | Motion-crop not in `backend/app/ai/**`. |
| 4 | NO | No job stage transitions touched. |
| 5 | **Preserved** | `JobPartStage.CUTTING` upsert at `part_cut.py:302` stays unconditional. Skip branch sits AFTER upsert. Pinned by `test_part_cut_cutting_upsert_before_skip_branch`. |
| 6 | NO | No new event signatures. Existing events fire identically. |
| 7 | NO | Zero DB writes added. |
| 8 | **Verified clean** | qa_pipeline reads `final_part` only. Sprint 7.8 produces the same final_part output. Pinned by `test_qa_pipeline_unchanged_by_sprint_7_8`. |

## NVENC Performance Protection

`render_motion_aware_crop` does NOT internally acquire `NVENC_SEMAPHORE` — verified by source-pin test `test_render_motion_aware_crop_does_not_acquire_nvenc`. Acquisition happens one level up in `render_part_from_source`'s new motion-aware branch (4-line acquire pattern from `render_part_smart`). **Max 1 acquire per part preserved.**

## Visual review delta (extends Sprint 7.4's 5-sample table to 8)

| Sample | Config | Purpose |
|---|---|---|
| 6 | `FEATURE_RAW_PART_SKIP=1` + `FEATURE_RAW_PART_SKIP_MOTION_AWARE=0` + `motion_aware_crop=True` | **7.8 regression pin** — must behave like Sprint 7.4 (motion-aware excluded). Expect byte-identical to baseline. |
| 7 | `FEATURE_RAW_PART_SKIP=1` + `FEATURE_RAW_PART_SKIP_MOTION_AWARE=1` + `motion_aware_crop=True` + subtitle-off | **7.8 active case** — fuse fires. Compare subject-tracking vs Sample 1. Specifically check: subject-lock at first 60 frames; eye-anchor placement consistency; no scene-aware regression (warmup_center inactive in fuse mode). |
| 8 | RAW_PART_SKIP=1 + MOTION_AWARE=1 + bad-first-frame source (force_accurate_cut=True path) | **Accuracy fallback** — verify output-side seek produces clean first frame. |

## Risk register

| ID | Risk | Mitigation |
|---|---|---|
| R1 | OpenCV seek hits nearest keyframe, not exact frame | `force_accurate_cut=True` operator escape. Sample 8 pin. **Forward-skim alignment NOT implemented in this commit** — left for Sprint 7.9 if Sample 7 shows misalignment. |
| R2 | Motion cache key collision across different windows | Windowed cache key at `part_render_encode` call site includes `source_start_sec` + `source_duration_sec` suffix. Pinned by `test_part_render_encode_windowed_cache_key_includes_window`. |
| R3 | Scene-aware tracking on windowed source: ranges in source coords | Force `_scene_aware=False` when fuse mode. Pinned by `test_scene_aware_forced_off_in_fuse_mode`. |
| R4 | Audio sync at FFmpeg input-side seek | Same `force_accurate_cut=True` escape Sprint 7.4 uses. Inherited. |
| R5 | NVENC double-acquire if `render_motion_aware_crop` grows acquire | Source-pin test `test_render_motion_aware_crop_does_not_acquire_nvenc` regression pin. |
| R6 | Sprint 7.4+7.8 combined visual review masks 7.8-specific regression | Sample 6 specifically isolates 7.8 changes (regression pin). |
| R7 | Sub-function full-source scan defeats fuse mode performance benefit | Documented in code + closure doc. Sprint 7.9 deferred work. Sprint 7.8 still saves the raw_part write + the separate cut_video FFmpeg invocation — partial but valid speedup. |

## Rollback

1. **Env flip:** `FEATURE_RAW_PART_SKIP_MOTION_AWARE=0`. Reverts to Sprint 7.4 (motion-aware excluded). Also: `FEATURE_RAW_PART_SKIP=0` reverts entire fuse path including 7.4.
2. **Git revert:** revert Sprint 7.8 PR. All changes flag-gated default-OFF → mechanical revert. Sprint 7.4 stays intact.

No DB migration, no file-format change, no cleanup of orphan files needed.

## What this sprint does NOT do

1. Does NOT change behaviour at default flag values. Pinned by tests.
2. Does NOT change `render_part_smart` signature (Sprint 5.2 freeze preserved).
3. Does NOT modify `qa_pipeline.py`. Sacred Contract #8 untouched.
4. Does NOT modify `RenderRequest` or `schemas.py`. Sacred Contract #2 zero-touch.
5. Does NOT touch `data/app.db` or any DB module. Sacred Contract #7 untouched.
6. Does NOT touch frozen job/part stage names.
7. Does NOT implement window-only sub-function scans (deferred to Sprint 7.9).
8. Does NOT implement forward-skim alignment for keyframe-edge sources (deferred to Sprint 7.9 if Sample 7 shows misalignment).
9. Does NOT enable scene-aware tracking under fuse mode (scene_aware_tracking=False forced).
10. Does NOT delete `cut_video`, `raw_part.mp4` orchestration, `render_part_smart`. All legacy paths remain.
11. Does NOT skip Sprint 7.4's visual review. Combined Sample 1-8 review is one review.
12. Does NOT alter NVENC semaphore semantics. Max 1 acquire per part.

## Cross-references

- `docs/review/SPRINT_7_8_MOTION_AWARE_FUSE_PLAN_2026-06-05.md` — architect plan
- `docs/review/SPRINT_7_4_RAW_PART_FUSE_2026-06-05.md` — Sprint 7.4 closure
- `docs/review/SPRINT_7_6_FULL_2026-06-05.md` — last merge to main (PR #15)
- `backend/app/services/render/base_clip_renderer.py:750-880` — `render_part_from_source` + motion-aware branch
- `backend/app/services/motion_crop/__init__.py:359-400` — `render_motion_aware_crop` + seek kwargs
- `backend/app/services/motion_crop/__init__.py:574-595` — FFmpeg argv with window
- `backend/app/services/motion_crop/__init__.py:644-674` — OpenCV loop with seek + bound
- `backend/app/orchestration/stages/part_cut.py:319-340` — `_skip_active` gate
- `backend/app/orchestration/stages/part_render_encode.py:310-365` — `_raw_part_absent` routing
- `backend/tests/test_motion_aware_fuse.py` — 29-case test suite (new)
