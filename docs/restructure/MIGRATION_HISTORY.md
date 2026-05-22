# MIGRATION_HISTORY.md

**Historical implementation record for the output-timeline architecture restructure.**
**Architecture source of truth lives in** [docs/architecture/](../architecture/).

This document records what changed in each phase, why, and what contracts were introduced.

---

## Phase 0 — Hotfix Sprint

**Commit**: pre-restructure branch  
**Purpose**: Fix immediate production bugs before the restructure.

**Shipped changes**:
- `mix_narration_audio()` in `audio_mix_service.py` now accepts `playback_speed: float` and applies `atempo={speed}` to the narration track before mixing. This fixed TTS narration desync at non-1.0 speeds.
- `socket_timeout: 60` added to yt-dlp options. `cancel_event` passed to download subprocess.
- Regression tests added: `TestMixNarrationAudioAtempo` in `test_phase0_hotfixes.py`.

**Contracts introduced**:
- `mix_narration_audio()` speed compensation is active. TTS narration is speed-adjusted.

**Known risks at time**:
- Subtitle display duration compression still untested and unresolved.

---

## Phase 1 — Output Timeline Architecture Foundation

**Branch**: `restructure/output-timeline-architecture`  
**Status**: SHIPPED  
**Source plan**: [PHASE_1_OUTPUT_TIMELINE_IMPLEMENTATION_PLAN.md](PHASE_1_OUTPUT_TIMELINE_IMPLEMENTATION_PLAN.md)

**Purpose**: Formalize the source↔output timeline conversion as a domain object. Establish per-clip manifest infrastructure.

**Shipped changes**:
- New file: `backend/app/domain/timeline.py` — `TimelineMap` pure dataclass with `source_to_output()`, `output_to_source()`, `to_dict()`, `from_dict()`.
- New file: `backend/app/domain/manifests.py` — `BaseClipManifest` dataclass with all per-clip timing and path fields.
- New file: `backend/app/services/manifest_writer.py` — atomic write/read helpers.
- `render_pipeline.py`: `TimelineMap` created after `_effective_start` finalized; `BaseClipManifest` created immediately after; progressive manifest writes as each stage completes.
- New tests: `test_timeline_map.py` (25 tests), `test_base_clip_manifest.py` (22 tests), `test_manifest_writer.py` (18 tests).

**Contracts introduced**:
- `TimelineMap` is the authoritative source→output coordinate transform.
- Speed clamped `[0.5, 1.5]` at `TimelineMap.__post_init__()`.
- `manifest.json` written to `work_dir/part_N/` for every clip.
- Manifest is write-only in Phase 1 — no pipeline decision reads it back yet.

---

## Phase 1.5 — Timeline Contract Validation

**Branch**: `feature/ai-output-upgrade`  
**Status**: COMPLETE — 1 bug fixed, 0 regressions  
**Source plan**: [PHASE_1_5_TIMELINE_CONTRACT_VALIDATION.md](PHASE_1_5_TIMELINE_CONTRACT_VALIDATION.md)

**Purpose**: Validate that `TimelineMap` accurately models the actual pipeline speed contract before Phase 2 builds on top of it.

**Shipped changes**:
- `backend/app/domain/timeline.py`: `_SPEED_MAX` corrected from `2.0` to `1.5`. The `2.0` value was copied from FFmpeg atempo's filter range by mistake; the pipeline uses `[0.5, 1.5]` consistently.
- `backend/tests/test_timeline_map.py`: 3 clamping tests updated (expected boundary 2.0 → 1.5).

**Contracts introduced**:
- `TimelineMap` speed clamp `[0.5, 1.5]` matches `_get_effective_playback_speed()` and `_sanitize_speed()` exactly.
- `audio_mix_service.py` atempo clamp `[0.5, 2.0]` is a separate concern (FFmpeg filter hardware range).
- The `ass-before-setpts` vf_chain order confirmed correct and intentional. Do NOT reorder.

---

## Phase 2 — Base Clip First Render

**Branch**: `restructure/output-timeline-architecture`  
**Status**: SHIPPED  
**Commit**: referenced in Phase 3 plan  
**Source plan**: [PHASE_2_BASE_CLIP_FIRST_RENDER_PLAN.md](PHASE_2_BASE_CLIP_FIRST_RENDER_PLAN.md)

**Purpose**: Create `render_base_clip()` — an overlay-free video render that produces `base_clip.mp4`. Validate the base clip timing accuracy against `TimelineMap.output_duration`. The base clip is a parallel artifact only; the final output still comes from `render_part_smart()` in Phase 2.

**Shipped changes**:
- `render_engine.py`: new `render_base_clip()` function. Reuses same FFmpeg infrastructure. vf_chain: crop/reframe/effect/color/setpts/fps — NO ass=, NO drawtext=, NO text_layers.
- `manifests.py`: 7 new `base_clip_*` Optional fields added.
- `render_pipeline.py`: `FEATURE_BASE_CLIP_FIRST` env flag (default OFF). Feature-flagged call to `render_base_clip()` with exception-fallback.
- New tests: `test_render_base_clip.py`, additions to `test_base_clip_manifest.py`.

**Contracts introduced**:
- `render_base_clip()` uses `TimelineMap.effective_speed` — NOT re-derived from payload.
- `render_base_clip()` acquires NVENC semaphore (same as `render_part_smart()`).
- When `FEATURE_BASE_CLIP_FIRST=1`, both a base clip AND a final render run per part. The final output is identical to flag-OFF output.
- `base_clip.mp4` is a parallel validation artifact in Phase 2 — NOT an input to the final render.

**Known risks documented for Phase 3**:
- Double-encoding quality loss if Phase 3 feeds base_clip into a lossy second pass.
- Audio double-atempo risk if Phase 3 re-encodes base_clip with audio filters.

---

## Phase 3A — Subtitle Overlay After Base Clip

**Branch**: `restructure/output-timeline-architecture`  
**Status**: SHIPPED  
**Commit**: `8db0295`  
**Source plan**: [PHASE_3_OVERLAY_AFTER_BASE_CLIP_PLAN.md](PHASE_3_OVERLAY_AFTER_BASE_CLIP_PLAN.md) §4–§11

**Purpose**: Wire `base_clip.mp4` into the final render path for the first time. Apply subtitle overlay using `composite_overlays_on_base_clip()`. The overlay composite replaces `render_part_smart()` as the final output producer when both flags are ON.

**Shipped changes**:
- `render_engine.py`: new `composite_overlays_on_base_clip()` function. Accepts `subtitle_ass`. vf_chain: `ass= → fps=`. Audio: `-c:a copy`. Stream copy path when no subtitle.
- `render_pipeline.py`: `FEATURE_OVERLAY_AFTER_BASE_CLIP` env flag (default OFF). Feature-flagged call to composite with fallback to `render_part_smart()`.
- `manifests.py`: `overlay_srt_path`, `overlay_ass_path`, `overlay_rendered_path` fields added.
- `subtitle_engine.py`: `slice_srt_to_output_timeline()` — generates output-timeline ASS for overlay path.
- Tests: `test_composite_overlays.py`, `test_subtitle_output_timeline.py`.

**Contracts introduced**:
- `composite_overlays_on_base_clip()` is overlay-only: no setpts, no atempo, no crop/scale/color.
- The `subtitle_output_timeline.ass` file has output-second timestamps (not source-second).
- Audio is always `-c:a copy` in the composite.
- `render_part_smart()` is the permanent fallback when composite fails.

---

## Phase 3A.5 — Overlay Validation Sprint

**Branch**: `restructure/output-timeline-architecture`  
**Status**: VALIDATED  
**Commit**: `bab429c`

**Purpose**: Validate Phase 3A implementation against real renders and stress cases.

**Shipped changes**: Validation fixtures, edge case tests. No behavioral changes.

**Contracts confirmed**:
- Overlay composite output quality acceptable vs. legacy path.
- Fallback path triggers correctly on composite exception.

---

## Phase 3B — Text Layer Overlay After Base Clip

**Branch**: `restructure/output-timeline-architecture`  
**Status**: SHIPPED  
**Commit**: `0a606ca`  
**Source plan**: [PHASE_3B_TEXT_LAYER_OVERLAY_PLAN.md](PHASE_3B_TEXT_LAYER_OVERLAY_PLAN.md)

**Purpose**: Extend `composite_overlays_on_base_clip()` to support title drawtext and user text_layers overlay. Establish the output-timeline hook timing model.

**Shipped changes**:
- `render_engine.py`: `composite_overlays_on_base_clip()` extended with `text_layers` and `title_text` params. New vf_chain order: `ass → drawtext=title → drawtext=layers → fps=`. Stream copy guard updated to check all three overlay types.
- `render_pipeline.py`: `_part_text_layers_overlay` variable (separate from legacy `_part_text_layers`). Hook layer built with `end_time=1.5` (output seconds — no speed factor). Composite call updated to pass `text_layers` and `title_text`.
- `manifests.py`: `overlay_text_layers_applied: Optional[int]` field added.
- New test file: `test_overlay_text_layer_timing.py` (17 tests — timing model invariants).
- `test_composite_overlays.py`: +35 tests across 4 new classes.
- `test_base_clip_manifest.py`: +4 tests for `overlay_text_layers_applied`.

**Contracts introduced**:
- Hook `end_time` in overlay path is `1.5` output seconds (constant, no speed multiplication).
- Hook `end_time` in legacy path is `round(min(2.5, 1.5 × speed), 3)` source-clip seconds (unchanged).
- User text_layer `start_time`/`end_time` passed through AS-IS in both paths (output/perceived seconds).
- Title `enable='lt(t,3)'` is identical in both paths (correct on both; semantics differ slightly but effect is same).
- `_part_text_layers` (legacy) and `_part_text_layers_overlay` (overlay) are kept as separate variables.

---

## Phase 3C — Audio Ownership for Overlay Path

**Branch**: `restructure/output-timeline-architecture`  
**Status**: SHIPPED  
**Source plan**: [PHASE_3C_AUDIO_OWNERSHIP_PLAN.md](PHASE_3C_AUDIO_OWNERSHIP_PLAN.md)

**Audit findings**:
- TTS narration mixing **already operated on the overlay path** — `mix_narration_audio()` is called on `final_part` after the render/composite. No narration implementation gap.
- BGM (`reup_bgm_*`) was the sole missing audio feature on the overlay path. It was baked into `render_part_smart()` only; `render_base_clip()` had no BGM parameters.

**Shipped changes**:
- `manifests.py`: `base_clip_bgm_applied: Optional[bool]` field added. `to_dict()` and `from_dict()` updated with backward compatibility.
- `render_engine.py`: `render_base_clip()` extended with `reup_bgm_enable`, `reup_bgm_path`, `reup_bgm_gain` params. When BGM is enabled and path is valid, uses `filter_complex` (same pattern as `_render_part()`), reusing `_build_audio_mix_filter()` helper. Both NVENC and CPU fallback paths updated via shared `_build_base_clip_cmd()` closure.
- `render_pipeline.py`: BGM params passed to `render_base_clip()` call site via `getattr(payload, ...)`. `_part_manifest.base_clip_bgm_applied` set after successful base clip render.
- New file: `backend/tests/test_overlay_narration.py` — narration interface, double-atempo safety, atempo clamp, overlay path narration flow.
- `test_render_base_clip.py`: `TestRenderBaseClipBgm` class (7 tests).
- `test_composite_overlays.py`: `TestCompositeAudioInvariantsPhase3C` class (6 tests).
- `test_base_clip_manifest.py`: `TestBaseClipManifestBgmApplied` class (6 tests).

**Contracts introduced**:
- `render_base_clip()` owns BGM. BGM baked into `base_clip.mp4`.
- `composite_overlays_on_base_clip()` audio stays `-c:a copy` — BGM flows through stream copy unchanged.
- `mix_narration_audio()` is called on composite output unchanged. No double-atempo.
- atempo applied exactly once per audio stream invariant maintained.
- `base_clip_bgm_applied: True` = BGM mixed; `False` = disabled/invalid path; `None` = base clip not rendered.

---

## Test Suite State (Post Phase 3C)

```
5784 passed, 4 skipped, 8 failed
```

The 8 persistent failures are pre-existing (before Phase 1):
- `test_remotion_adapter.py` — 4 tests
- `test_ai_optional_dependencies.py` — 1 test
- `test_ai_phase36_clip_segment_selection.py` — 2 tests
- `test_ai_visibility_summary.py` — 1 test

None of these are related to the output-timeline architecture restructure.
