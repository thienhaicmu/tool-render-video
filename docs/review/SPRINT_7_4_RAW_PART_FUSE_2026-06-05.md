# Sprint 7.4 — `raw_part` skip + fused cut+render

**Date:** 2026-06-05
**Branch:** `feature/sprint-7-4-raw-part-fuse`
**Baseline:** Pytest 2415 passed / 1 skipped / 0 failed @ `9621f44` (main, post Sprint 7.6 LITE)
**Final pytest:** 2439 passed (+24 new) / 1 skipped / 0 failed
**Source:** `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.4 row + `docs/review/SPRINT_6_O4_RAW_PART_SKIP_PREDICATE_2026-06-05.md` §"Commit 2 deferred plan"
**Tier:** HIGH-CRITICAL — Render Edit Protocol applies (touches `services/render/base_clip_renderer.py` + `stages/part_cut.py` + `stages/part_render_encode.py`).
**Ship gate:** `FEATURE_RAW_PART_SKIP=0` default OFF — operators opt in via env for visual review before any production flip.

## Purpose

Sprint 6 O-4 Commit 1 (`20800ae`) shipped the predicate `_should_skip_raw_part_write` as **telemetry only** with a TODO for Sprint 7.4 to wire the actual cut_video bypass. This commit is that Sprint 7.4 wire.

When ALL of:
1. The predicate fires (`part_subtitle_enabled=False` AND `not (FEATURE_BASE_CLIP_FIRST AND FEATURE_OVERLAY_AFTER_BASE_CLIP)`)
2. `FEATURE_RAW_PART_SKIP=1` (operator opt-in, default OFF — Sacred Contract #2)
3. `payload.motion_aware_crop=False` (Option E scope — Sprint 7.8 will add motion-aware)

then:
- `run_cut_stage` bypasses `cut_video()` — `raw_part.mp4` is never written
- `run_render_encode` detects `raw_part.exists()==False` and routes to `render_part_from_source(source_path, source_start, source_duration, ...)` instead of `render_part_smart(raw_part, ...)`
- The single fused FFmpeg invocation does input-side `-ss/-t` seek + the full encode chain in one pass

## Files touched

### `backend/app/services/render/base_clip_renderer.py`

**Modified `render_part` signature** — added three additive kwargs with defaults that preserve the pre-Sprint-7.4 contract:

```python
def render_part(
    ...existing params...,
    _source_seek_start: float | None = None,
    _source_seek_duration: float | None = None,
    _source_seek_force_accurate: bool = False,
):
```

When both `_source_seek_start` and `_source_seek_duration` are provided, `render_part` prepends `-ss start -t dur` to the FFmpeg input args (input-side seek, fast keyframe behaviour). When `_source_seek_force_accurate=True`, the args are appended after `-i` (output-side seek, frame-accurate but slower). When the kwargs are `None` (default), the input args are exactly `["-i", input_path]` — byte-identical to pre-Sprint-7.4 behaviour. The internal `cmd = [get_ffmpeg_bin(), "-y", *_input_args]` change covers both the NVENC main cmd and the CPU fallback cmd in a single edit.

**NEW `render_part_from_source` function** — thin wrapper around `render_part` that forwards `source_start`/`source_duration` as the seek kwargs. ~70 LOC. Motion-aware branch deliberately delegates back to `render_part` with no motion handling — that path stays on the cut→render_part_smart code path (Sprint 7.8 scope).

`render_part_smart` signature stays UNCHANGED — Sprint 5.2 frozen-signature contract preserved.

### `backend/app/orchestration/render_pipeline.py` (+4 mirror sites)

Added `_FEATURE_RAW_PART_SKIP` env read at the master site (`render_pipeline.py`) and mirror-read at 4 stage modules (`part_cut.py`, `part_renderer.py`, `part_render_setup.py`, `part_render_encode.py`). Same drift-prevention pattern as `FEATURE_BASE_CLIP_FIRST` / `FEATURE_OVERLAY_AFTER_BASE_CLIP`.

Default: `os.getenv("FEATURE_RAW_PART_SKIP", "0") == "1"` → OFF.

### `backend/app/orchestration/stages/part_cut.py`

`run_cut_stage` now computes `_skip_active`:

```python
_skip_predicate_fires = _should_skip_raw_part_write(
    part_subtitle_enabled=_part_subtitle_enabled,
    feature_base_clip_first=_FEATURE_BASE_CLIP_FIRST,
    feature_overlay_after_base_clip=_FEATURE_OVERLAY_AFTER_BASE_CLIP,
)
_payload_motion_aware = bool(getattr(ctx.payload, "motion_aware_crop", False))
_skip_active = (
    _skip_predicate_fires and _FEATURE_RAW_PART_SKIP and not _payload_motion_aware
)
```

When `_skip_active` is True:
- Sprint 6 O-4 `raw_part_skip_eligible` debug log still fires
- NEW `raw_part_skip_active` info log fires
- `cut_video()` is BYPASSED (raw_part never written)
- `_cut_ms = 0`

When `_skip_active` is False:
- Existing `cut_video()` call runs unchanged
- `_cut_ms` measured as before

The cross-stage signal is the file-absence: `raw_part.exists()==False`. No new field on `CutStageResult` needed.

### `backend/app/orchestration/stages/part_render_encode.py`

Added direct import of `render_part_from_source` from `services.render.base_clip_renderer`.

Inside `try: if not _overlay_composite_succeeded:` block, added a new branch:

```python
_raw_part_absent = not raw_part.exists()
...
if _raw_part_absent and not ctx.payload.motion_aware_crop:
    # Sprint 7.4 fused cut+render
    render_part_from_source(
        str(ctx.source_path),
        str(final_part),
        part_timeline.source_start,
        part_timeline.source_end - part_timeline.source_start,
        ...
    )
else:
    # Existing render_part_smart path (unchanged)
    render_part_smart(...)
```

The else-branch preserves the existing render_part_smart call verbatim. New `_resolved_playback_speed` local pulled out to be reused by both branches.

## Sacred Contracts walk

| Contract | Touched? | Disposition |
|---|---|---|
| #1 result_json aliases | No | unchanged |
| #2 RenderRequest additive (spirit) | **Engaged but compliant** | New env flag `FEATURE_RAW_PART_SKIP` defaults OFF. Zero behaviour change at default. Pinned by test `test_flag_defaults_off`. |
| #3 AI returns None | No | unchanged |
| #4 Job stage frozen | No | unchanged |
| #5 Part stage frozen | **Preserved** | `CUTTING` upsert still unconditional in `run_cut_stage:302`. The skip branch sits AFTER the upsert. Sacred Contract #5 frozen sequence `WAITING → CUTTING → (TRANSCRIBING?) → RENDERING → DONE` holds — `CUTTING` still emits even when cut_video is bypassed. |
| #6 `_emit_render_event` shape | No | signature unchanged. Existing events (`silence_trim_applied`, `first_frame_shift_applied`, `accurate_cut_forced`) still fire from `ctx.source_path` probes (NOT raw_part) — they fire identically whether the skip path is active or not. |
| #7 `data/app.db` | No | unchanged |
| #8 `qa_pipeline` never bypassed | **Verified clean** | qa_pipeline reads only the final `output_path` / `final_part`. Never reads `raw_part`. The skip change cannot affect validation. |

## NVENC Performance Protection

`render_part` already holds the NVENC semaphore inside its `with NVENC_SEMAPHORE:` block. `render_part_from_source` calls `render_part` directly, so the same semaphore acquisition fires once per part — no double-acquire, no leak. Total acquires per part stays at 1 (it was 1 before Sprint 7.4 too — cut_video used stream-copy with no NVENC).

## ROI (per Sprint 6 O-4 Commit 1 audit)

- `raw_part.mp4` ≈ 20–50 MB × 50 parts = **1.0–2.5 GB cumulative** (transient; unlinked in `part_done.py:216`)
- Peak instantaneous (parallel workers=4): ~200 MB
- `cut_video` time: 5–15 s per part
- **Skip-fire scenarios:**
  - `payload.add_subtitle=False` AND `motion_aware_crop=False` AND default base_clip config → 100% of parts skip
  - `add_subtitle=True` + `subtitle_only_viral_high=True` → ~50–70% of parts skip
- **Realistic save on a 50-part subtitle-off + motion-aware-off render:** ~1.5 GB transient + ~12 min wall-time

## Test coverage

`backend/tests/test_render_part_from_source.py` — 24 cases across 7 classes:

1. **TestSignatures** (4) — pin the new `render_part` kwargs + `render_part_from_source` exists + Sprint 5.2 frozen `render_part_smart` signature
2. **TestArgvShape** (4) — input-side seek default, output-side when `force_accurate=True`, source_path used as `-i`, output_path at argv end
3. **TestRenderPartBackwardCompat** (1) — when kwargs are None (default), NO `-ss` or `-t` appears between binary and `-i input_path`
4. **TestRawPartSkipFlag** (3) — Sacred Contract #2: default OFF, ON when `=1`, strict compare rejects `"true"`/`"yes"`/etc.
5. **TestFlagReadsCoherent** (5) — 5-site mirror pin (drift prevention)
6. **TestSkipActiveTruthTable** (5) — `predicate AND flag AND NOT motion_aware` truth table
7. **TestProductionSourcePins** (2) — source-pin that `run_cut_stage` implements `_skip_active` + `run_render_encode` routes to `render_part_from_source`

Net pytest delta: 2415 → 2439 (+24 new).

## What this sprint does NOT do

- Does NOT change behaviour at default (`FEATURE_RAW_PART_SKIP=0`).
- Does NOT add the motion-aware-crop branch (Sprint 7.8 scope).
- Does NOT change `render_part_smart` signature (Sprint 5.2 freeze preserved).
- Does NOT delete `cut_video` or `clip_ops.py` (legacy path stays — runs whenever `_skip_active` is False).
- Does NOT modify `qa_pipeline.py`.

## Ship gate — operator visual review

Before flipping `FEATURE_RAW_PART_SKIP=1` in any production deployment, operators MUST run 3-5 sample renders per Sprint Plan risk register line 302:

| Sample | Config |
|---|---|
| 1 | Baseline (FEATURE_RAW_PART_SKIP=0): default subtitle-off + motion-aware-off render |
| 2 | After flip (FEATURE_RAW_PART_SKIP=1): same input + config → expect byte-equivalent output |
| 3 | Quality check: subtitle-on render → verify cut path unchanged (predicate fires=False) |
| 4 | Boundary check: motion-aware-on render → verify still routes through cut_video (Option E gate) |
| 5 | Recovery: corrupted source render → verify failure mode + error logging |

Verify on Sample 2:
- First-frame quality (no `force_accurate_cut` artifact)
- Audio sync at part boundaries ≤ ±0.35 s
- Duration accuracy vs Sample 1 baseline ≤ ±0.35 s
- No subtitle drift (the skip path requires subtitle off by predicate)
- Cleanup: orphan files / temp dirs

Per the user-approved decision in this session, the operator (= user) runs these 5 samples post-merge of THIS PR and reports back. Any quality regression → revert via env (set `FEATURE_RAW_PART_SKIP=0`) or git revert this commit.

## Cross-references

- `docs/review/SPRINT_PLAN_2026-06-05.md` Sprint 7.4 row
- `docs/review/SPRINT_7_EXECUTION_PLAN_2026-06-05.md` Phase 4
- `docs/review/SPRINT_6_O4_RAW_PART_SKIP_PREDICATE_2026-06-05.md` — Sprint 6 O-4 Commit 1 (telemetry predicate) + Commit 2 plan that this PR implements
- `backend/app/services/render/base_clip_renderer.py` — `render_part` + `render_part_from_source`
- `backend/app/orchestration/render_pipeline.py:116` — `_FEATURE_RAW_PART_SKIP` master read
- `backend/app/orchestration/stages/part_cut.py:303-348` — `_skip_active` truth + bypass
- `backend/app/orchestration/stages/part_render_encode.py:297-360` — `render_part_from_source` routing
- `backend/tests/test_render_part_from_source.py` — 24-case test suite
