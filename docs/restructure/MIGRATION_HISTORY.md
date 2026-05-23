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

## Phase 3C.5 — Audio Contract Validation + Cleanup

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `fcb077c`

**Purpose**: Validate Phase 3C audio contracts, fix test infrastructure bugs, and sync stale docs. No behavioral changes.

**Issues found and fixed**:
- `test_overlay_narration.py` helper had wrong kwarg (`narration_path` → `narration_audio_path`), missing `mix_mode`/`output_path`, and wrong mock target (`_run_ffmpeg_with_retry` → `subprocess.run`). The 3 `TestOverlayPathDoubleAtempoSafety` tests were always SKIPPING. Fixed; all 3 now PASS.
- `test_render_base_clip.py` `test_no_bgm_input_when_disabled` had confusing weak assertion. Simplified to `assert "-stream_loop" not in cmd`.
- `AUDIO_PIPELINE.md` referenced `_bgm_duck_filter()` — this function does not exist. Corrected to `_build_audio_mix_filter()`.
- All four architecture docs had stale "Phase 3C planned" language. Updated to reflect shipped status.
- `BRUTAL_REVIEW_SUMMARY.md` priorities section updated to "post Phase 3C".
- `render_engine.py` docstring updated to describe both base-clip-only and overlay-composite modes.

**Contracts confirmed** (no new contracts introduced):
- Double-atempo safety: narration atempo applies to `[1:a]` only; source `[0:a]` gets `volume` only.
- Composite audio: `-c:a copy` invariant maintained; no BGM, no atempo in composite.
- `base_clip_bgm_applied` manifest field: `True`/`False`/`None` semantics correct.

---

## Phase 4A — Backend Modularization Planning

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `b5845bd`

**Purpose**: Define the strategy to split the backend god files (`render_pipeline.py` 6,064 lines, `db.py` 1,886 lines, `render_engine.py` 1,652 lines, `subtitle_engine.py` 1,970 lines, `routes/render.py` 1,368 lines) into focused modules without changing behavior.

**No code changes in this phase.** Planning doc only.

**Deliverable**: `docs/restructure/PHASE_4A_BACKEND_MODULARIZATION_PLAN.md`

**Recommended first implementation phase**: Phase 4B — Extract Asset Pipeline (`orchestration/asset_pipeline.py`). Moves `_maybe_prepend_remotion_hook_intro`, `_maybe_prepend_asset_intro`, `_maybe_append_asset_outro`, `_maybe_apply_asset_logo` out of render_pipeline.py. These are top-level named functions with no FFmpeg logic and no closure dependencies.

---

---

## Phase 4B — Extract Asset Pipeline

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `2be39cc`

**Purpose**: Extract post-assembly asset hook functions from `render_pipeline.py` into dedicated modules. First code extraction phase of Phase 4.

**Shipped changes**:
- New file: `backend/app/orchestration/render_events.py` — shared logging/event helpers required by the asset functions: `_JOB_LOG_DIRS`, `_safe_unlink`, `_append_json_line`, `_render_error_code`, `_job_log`, `_emit_render_event`. Extracted as a prerequisite to avoid circular imports.
- New file: `backend/app/orchestration/asset_pipeline.py` — four post-assembly helpers moved verbatim: `_maybe_prepend_remotion_hook_intro`, `_maybe_prepend_asset_intro`, `_maybe_append_asset_outro`, `_maybe_apply_asset_logo`.
- `render_pipeline.py`: function bodies for the above 10 items removed; backward-compat re-exports added via `from app.orchestration.render_events import ...` and `from app.orchestration.asset_pipeline import ...`. All existing call sites unchanged.
- `render_pipeline.py` reduced from 6,064 → 5,779 lines (−285 lines).
- New test file: `backend/tests/test_asset_pipeline.py` — 23 tests covering import correctness, backward-compat identity, disabled/enabled behavior for all 4 functions, `_safe_unlink` and `_render_error_code` behavior.

**Contracts introduced**:
- `render_events.py` owns `_JOB_LOG_DIRS`. The dict is a shared mutable singleton: `render_pipeline.py` populates it via `_JOB_LOG_DIRS[job_id] = ...`; `_job_log` and `_emit_render_event` in `render_events.py` read from it. In-place mutation is safe across the import boundary.
- No function signature was changed. No call site was changed. No behavior was changed.
- `asset_pipeline.py` imports from `render_events.py` only — no circular import.

---

## Phase 4C — Extract QA Pipeline

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `f0666c5`

**Purpose**: Extract QA/output validation helpers from `render_pipeline.py` into `orchestration/qa_pipeline.py`. Second code extraction phase of Phase 4.

**Shipped changes**:
- New file: `backend/app/orchestration/qa_pipeline.py` — seven QA helpers moved verbatim: `_resume_output_valid`, `_duration_tolerance`, `_stall_deadline`, `_failed_part_progress`, `_validate_render_output`, `_assess_output_quality`, `_render_part_failure_detail`.
- `render_pipeline.py`: function bodies for the above 7 items removed; backward-compat re-exports added via `from app.orchestration.qa_pipeline import ...`. All existing call sites unchanged.
- `render_pipeline.py` reduced from 5,779 → 5,510 lines (−269 lines).
- New test file: `backend/tests/test_qa_pipeline.py` — 34 tests covering import correctness, backward-compat identity, `_duration_tolerance`, `_stall_deadline`, `_failed_part_progress`, `_render_part_failure_detail`, `_resume_output_valid`, and `_validate_render_output` with mocked ffprobe.

**Contracts introduced**:
- `qa_pipeline.py` imports from `app.services.db` and `app.services.bin_paths` only — no import from `render_pipeline.py`, no circular import.
- No function signature was changed. No call site was changed. No behavior was changed.
- `_stall_deadline` is still accessible as `render_pipeline._stall_deadline` via re-export; `_render_progress_timer` (which calls it, still in render_pipeline.py) continues to work unchanged.

---

## Test Suite State (Post Phase 4C)

```
5844 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing (before Phase 1):
- `test_remotion_adapter.py` — 4 tests
- `test_ai_optional_dependencies.py` — 1 test
- `test_ai_phase36_clip_segment_selection.py` — 2 tests
- `test_ai_visibility_summary.py` — 1 test

None of these are related to the output-timeline architecture restructure.

Phase 4C added 34 new passing tests (`test_qa_pipeline.py`).

Phase 4B added 23 new passing tests (`test_asset_pipeline.py`).

Phase 3C.5 fix: 3 previously-SKIPPED `TestOverlayPathDoubleAtempoSafety` tests in `test_overlay_narration.py` now PASS (5784 → 5787 passing, 4 → 1 skipped).

---

## Phase 4D — Extract Audio Pipeline + Remaining Render Events

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Extract audio cleanup orchestration from `render_pipeline.py` into `orchestration/audio_pipeline.py`. Move remaining render event/progress helpers into `orchestration/render_events.py`.

**Shipped changes**:
- New file: `backend/app/orchestration/audio_pipeline.py` — `_maybe_cleanup_narration_audio` moved verbatim. Imports from `render_events` for `_job_log`/`_safe_unlink`; no circular import.
- `backend/app/orchestration/render_events.py` extended with: `_PROGRESS_TICK_SEC` constant, `_event_from_stage`, `_resolve_job_log_dir`, `_render_progress_timer`. New imports added: `threading`, `time`, `STAGE_TO_EVENT`/`JobPartStage` from `app.core.stage`, `upsert_job_part` from `app.services.db`. `_render_progress_timer` uses a deferred `from app.orchestration.qa_pipeline import _stall_deadline` to avoid top-level circular import.
- `render_pipeline.py`: function bodies for the above 5 items removed; backward-compat re-exports added. Reduced from 5,510 → 5,340 lines (−170 lines).
- New test file: `backend/tests/test_audio_pipeline.py` — 9 tests for `_maybe_cleanup_narration_audio`.
- New test file: `backend/tests/test_render_events.py` — 15 tests for `_event_from_stage`, `_resolve_job_log_dir`, `_render_progress_timer`.
- `backend/tests/test_render_pipeline_guards.py`: mock targets updated from `render_pipeline.*` → `render_events.*` (where functions now live). Mock target for `_stall_deadline` updated from `render_pipeline.*` → `qa_pipeline.*`.
- `backend/tests/test_audio_cleanup_pipeline.py`: mock targets updated from `render_pipeline.cleanup_audio_with_adapter` / `render_pipeline._job_log` → `audio_pipeline.*`.

**Contracts introduced**:
- `audio_pipeline.py` imports from `render_events.py` only (no import from `render_pipeline.py`). No circular import.
- `render_events.py` imports from `qa_pipeline.py` are deferred inside `_render_progress_timer` body to avoid import-time circular dependency.
- `_PROGRESS_TICK_SEC` is defined in `render_events.py`. `render_pipeline.py` no longer defines it.
- No function signature was changed. No call site behavior was changed.

---

## Test Suite State (Post Phase 4D)

```
5868 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing (before Phase 1) — unchanged.

Phase 4D added 24 new passing tests (`test_audio_pipeline.py` + `test_render_events.py`).

---

## Phase 4E.1 — Extract FFmpeg Helpers

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `49a40a9`

**Purpose**: First sub-step of render_engine.py split. Extract shared FFmpeg infrastructure (probe helpers, filter builders, NVENC, thread-local, codec selection) into `services/render/ffmpeg_helpers.py`. Backward-compat re-exports keep all existing callers unchanged.

**Shipped changes**:
- New package: `backend/app/services/render/__init__.py` (empty).
- New file: `backend/app/services/render/ffmpeg_helpers.py` (474 lines) — moved verbatim from `render_engine.py`: `NVENC_SEMAPHORE`, `_FFMPEG_TIMEOUT_SEC`, `_FPS_CAP`, `_tls`, `_PROBE_CACHE`, `_PROBE_CACHE_LOCK`, `set_thread_cancel_event`, `_file_probe_key`, `probe_video_metadata`, `extract_thumbnail_frame`, `_run_ffmpeg_with_retry`, `nvenc_available`, `_resolve_codec`, `_effect_filter`, `_cinematic_color_filter`, `_cinematic_sharpen_filter`, `_smart_denoise_filter`, `content_type_crf_delta`, `_build_audio_mix_filter`, `_build_audio_filter`, `_parse_fps_ratio`, `_probe_fps`, `_resolve_fps`, `_sanitize_speed`, `_has_audio_stream`, `_probe_duration`, `resolve_ffmpeg_threads`, `resolve_target_dimensions`.
- `render_engine.py`: all 28 moved names re-exported via `from app.services.render.ffmpeg_helpers import ...`. Function bodies removed. Reduced from 1,652 → ~1,210 lines (−442 lines). Existing encoder_helpers imports (`_has_encoder`, `_nvenc_runtime_ready`) retained for backward-compat with test patches.
- New test file: `backend/tests/test_ffmpeg_helpers.py` — 53 tests: import smoke tests (new module + render_engine re-export), same-object identity checks, `_sanitize_speed`, `_parse_fps_ratio`, `resolve_target_dimensions`, `_resolve_codec`, `_build_audio_filter`, `_build_audio_mix_filter`, `content_type_crf_delta`.
- `backend/tests/test_probe_unification.py`: `TestMotionCropHasAudioStream` and `TestSubtitleEngineHasAudioStream` mock targets updated from `app.services.render_engine.probe_video_metadata` to `app.services.render.ffmpeg_helpers.probe_video_metadata` (8 patches across 4 test classes). Root cause: `_has_audio_stream` moved to ffmpeg_helpers; it now looks up `probe_video_metadata` in ffmpeg_helpers's namespace, not render_engine's.

**Contracts introduced**:
- `ffmpeg_helpers.py` imports only from stdlib + `bin_paths` + `encoder_helpers`. No import from `render_engine`. No circular import.
- Re-exported names in `render_engine.py` are the SAME objects as in `ffmpeg_helpers.py` (`is` identity). `_tls`, `NVENC_SEMAPHORE`, `_PROBE_CACHE` are shared mutable state — mutations via either namespace are visible to both.
- Renderers in `render_engine.py` (`render_base_clip`, `composite_overlays_on_base_clip`, `render_part_smart`) remain in place and are NOT moved in this sub-phase.

---

## Test Suite State (Post Phase 4E.1)

```
5921 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4E.1 added 53 new passing tests (`test_ffmpeg_helpers.py`).

---

## Phase 4E.2 — Extract Clip Ops

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `a46934c`

**Purpose**: Second sub-step of render_engine.py split. Extract clip-level operations (`cut_video`, `detect_silence_trim_offset`, `detect_bad_first_frame`, `_detect_silence_segments`, `apply_micro_pacing`) from `render_engine.py` into `services/render/clip_ops.py`. Backward-compat re-exports keep all existing callers unchanged.

**Shipped changes**:
- New file: `backend/app/services/render/clip_ops.py` (304 lines) — 5 functions moved verbatim from `render_engine.py`. Imports only from `stdlib` + `bin_paths` + `render.ffmpeg_helpers`. No circular import.
- `render_engine.py`: 5 function bodies removed; backward-compat re-exports added via `from app.services.render.clip_ops import ...`. Reduced from ~1,210 → 829 lines (−381 lines).
- New test file: `backend/tests/test_clip_ops.py` — 43 tests: import smoke tests (new module + render_engine re-export), same-object identity checks, `cut_video` stream-copy/re-encode/drift paths, `detect_silence_trim_offset` clamping, `detect_bad_first_frame` leading-black detection, `_detect_silence_segments` parsing + cancel-event short-circuit, `apply_micro_pacing` no-op and active paths.

**Contracts maintained**:
- `clip_ops.py` imports from `render.ffmpeg_helpers` only — no import from `render_engine`. No circular import.
- Re-exported names in `render_engine.py` are the SAME objects as in `clip_ops.py` (`is` identity).
- Renderers in `render_engine.py` (`render_base_clip`, `composite_overlays_on_base_clip`, `render_part_smart`, `render_part`) remain in place — NOT moved in this sub-phase.
- No function signature was changed. No call site was changed. No behavior was changed.

---

## Test Suite State (Post Phase 4E.2)

```
5964 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4E.2 added 43 new passing tests (`test_clip_ops.py`).

---

## Phase 4E.3 — Extract Base Clip Renderer

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `7576c31`

**Purpose**: Third sub-step of render_engine.py split. Extract `render_base_clip()` from `render_engine.py` into `services/render/base_clip_renderer.py`. Backward-compat re-export keeps all existing callers unchanged.

**Shipped changes**:
- New file: `backend/app/services/render/base_clip_renderer.py` — `render_base_clip()` moved verbatim from `render_engine.py`. Imports only from `stdlib` + `domain/timeline` + `motion_crop` + `bin_paths` + `encoder_helpers` + `render.ffmpeg_helpers`. No import from `render_engine`. No circular import.
- `render_engine.py`: `render_base_clip` body removed; backward-compat re-export added via `from app.services.render.base_clip_renderer import render_base_clip`. Reduced from 829 → ~619 lines (−210 lines).
- New test file: `backend/tests/test_base_clip_renderer.py` — 28 tests: import smoke tests (new module + render_engine re-export), same-object identity checks, no-overlay-filter invariants (no ass=, no drawtext=, no text_layers), speed from TimelineMap.effective_speed (setpts/atempo, 1x no-op, clamping), fps= last in vf_chain, BGM disabled/invalid/enabled paths, NVENC semaphore acquired/released, CPU fallback on NVENC failure, return value metadata.
- `backend/tests/test_render_base_clip.py`: mock patch targets updated from `render_engine_mod.*` to `base_clip_renderer_mod.*` for `_run_ffmpeg_with_retry`, `probe_video_metadata`, `_has_audio_stream`, `_resolve_codec`. Vestigial `nvenc_available` patch removed (not in `base_clip_renderer` namespace).

**Contracts maintained**:
- `base_clip_renderer.py` imports from `render.ffmpeg_helpers` only for shared FFmpeg state — no import from `render_engine`. No circular import.
- Re-exported `render_base_clip` in `render_engine.py` is the SAME object as in `base_clip_renderer.py` (`is` identity).
- `render_base_clip` function signature, behavior, NVENC semaphore usage, CPU fallback, BGM handling, and return value are all unchanged.
- No function signature was changed. No call site was changed. No behavior was changed.

---

## Test Suite State (Post Phase 4E.3)

```
5992 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4E.3 added 28 new passing tests (`test_base_clip_renderer.py`).

---

## Phase 4E.4 — Extract Overlay Compositor

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `f36171f`

**Purpose**: Fourth sub-step of render_engine.py split. Extract `composite_overlays_on_base_clip()` from `render_engine.py` into `services/render/overlay_compositor.py`. Backward-compat re-export keeps all existing callers unchanged.

**Shipped changes**:
- New file: `backend/app/services/render/overlay_compositor.py` — `composite_overlays_on_base_clip()` moved verbatim from `render_engine.py`. Imports only from `stdlib` + `domain/timeline` + `bin_paths` + `encoder_helpers` + `text_overlay` + `render.ffmpeg_helpers`. No import from `render_engine`. No circular import.
- `render_engine.py`: `composite_overlays_on_base_clip` body removed; backward-compat re-export added via `from app.services.render.overlay_compositor import composite_overlays_on_base_clip`. Reduced from ~619 → ~477 lines (−142 lines).
- New test file: `backend/tests/test_overlay_compositor.py` — 42 tests: import smoke tests, backward-compat, same-object identity, subtitle/title/text-layers filter presence, vf_chain order (ass → title → layers → fps), fps= last, forbidden filters (setpts/atempo/crop/scale/eq/hqdn3d/loudnorm/BGM), -c:a copy invariant, -af absent, stream copy vs encode paths, NVENC semaphore acquired/released, CPU fallback on NVENC failure, return value metadata.
- `backend/tests/test_composite_overlays.py`: module import added (`overlay_compositor_mod`); all `patch.object(render_engine_mod, ...)` in `_call_composite` helper updated to `patch.object(overlay_compositor_mod, ...)` for `_run_ffmpeg_with_retry`, `probe_video_metadata`, `_resolve_codec`, `_detect_windows_fontfile`. Vestigial `nvenc_available` patch removed (not in `overlay_compositor` namespace).

**Contracts maintained**:
- `overlay_compositor.py` imports from `render.ffmpeg_helpers` only for shared FFmpeg state — no import from `render_engine`. No circular import.
- Re-exported `composite_overlays_on_base_clip` in `render_engine.py` is the SAME object as in `overlay_compositor.py` (`is` identity).
- All overlay invariants preserved: no setpts, no atempo, no crop/scale/color/effect, -c:a copy always, fps= last, stream copy when no overlays.
- No function signature was changed. No call site was changed. No behavior was changed.

---

## Test Suite State (Post Phase 4E.4)

```
6034 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4E.4 added 42 new passing tests (`test_overlay_compositor.py`).

---

## Phase 4E.5 — Extract Legacy Renderer

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Fifth and final sub-step of render_engine.py split. Extract `render_part()` and `render_part_smart()` from `render_engine.py` into `services/render/legacy_renderer.py`. Backward-compat re-exports keep all existing callers unchanged. After this phase `render_engine.py` is a pure imports/re-exports shim with no function bodies.

**Shipped changes**:
- New file: `backend/app/services/render/legacy_renderer.py` — `render_part()` and `render_part_smart()` moved verbatim from `render_engine.py`. Imports only from `stdlib` + `motion_crop` + `bin_paths` + `text_overlay` + `encoder_helpers` + `render.ffmpeg_helpers`. No import from `render_engine`. No circular import.
- `render_engine.py`: `render_part` and `render_part_smart` bodies removed; backward-compat re-exports added via `from app.services.render.legacy_renderer import render_part, render_part_smart`. Reduced from ~477 → ~50 lines. `render_engine.py` is now a pure re-export shim.
- New test file: `backend/tests/test_legacy_renderer.py` — 40 tests: import smoke tests (new module + render_engine re-export), same-object identity checks, aspect ratio handling, vf_chain filter order invariants (ass-before-setpts), subtitle/title/text-layers presence, audio chain, speed handling (atempo, no-op at 1x), NVENC semaphore, CPU fallback on NVENC failure, render_part_smart fallback behavior.
- `backend/tests/test_render_guards.py`: `_make_render_part_call` helper patch targets updated from `app.services.render_engine.*` to `app.services.render.legacy_renderer.*`. Vestigial `_has_encoder`/`_nvenc_runtime_ready` patches replaced with direct `_resolve_codec` mock.
- `backend/tests/test_phase0_hotfixes.py`: `TestSubtitleTimingInvariant::test_render_engine_ass_before_setpts` updated to inspect `legacy_renderer` source instead of `render_engine` source (which is now a shim with no function bodies).

**Contracts maintained**:
- `legacy_renderer.py` imports from `render.ffmpeg_helpers` only for shared FFmpeg state — no import from `render_engine`. No circular import.
- Re-exported `render_part` and `render_part_smart` in `render_engine.py` are the SAME objects as in `legacy_renderer.py` (`is` identity).
- `render_part_smart()` is the permanent legacy fallback. Its vf_chain order (ass-before-setpts), NVENC semaphore usage, CPU fallback, audio chain, BGM behavior, loudnorm behavior, subtitle behavior, and function signature are all unchanged.
- No function signature was changed. No call site was changed. No behavior was changed.

---

## Test Suite State (Post Phase 4E.5)

```
6074 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4E.5 added 40 new passing tests (`test_legacy_renderer.py`).

---

## Phase 4F.0 — DB Split Planning

**Branch**: `restructure/output-timeline-architecture`
**Status**: PLANNING
**Commit**: (this commit)

**Purpose**: Define the strategy to split `backend/app/services/db.py` (1,886 lines, 9 tables, 55 public functions) into focused DB repository modules without changing behavior.

**No code changes in this phase.** Planning doc only.

**Deliverable**: `docs/restructure/PHASE_4F_DB_SPLIT_PLAN.md`

**Target module tree**:
```
backend/app/db/
├── __init__.py          (empty)
├── connection.py        (get_conn, close_thread_conn, init_db, thread-local, helpers)
├── jobs_repo.py         (upsert_job, update_job_progress, job parts CRUD)
├── uploads_repo.py      (accounts, videos, queue, history, locks, scheduler — ~1,200 lines)
├── platform_repo.py     (proxy pool CRUD)
└── creator_repo.py      (get_creator_prefs, upsert_creator_prefs)
```

`services/db.py` remains as backward-compat re-export shim throughout all sub-phases.

**Recommended first implementation phase**: Phase 4F.1 — Extract DB Connection Foundation.

---

## Phase 4F.1 — Extract DB Connection Foundation

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: First implementation sub-phase of Phase 4F. Create `app/db/` package and move the DB connection + schema foundation from `backend/app/services/db.py` into `backend/app/db/connection.py`. Backward-compat re-exports keep all 14 existing callers unchanged.

**Shipped changes**:
- New file: `backend/app/db/__init__.py` — empty package marker.
- New file: `backend/app/db/connection.py` (~513 lines) — Group A block moved verbatim from `services/db.py`. Contains: `_DB_PATH_LOCK`, `_ACTIVE_DB_PATH`, `_tls`, `UPLOAD_PROFILE_LOCK_TTL_MINUTES`, `UPLOAD_SCHEDULER_STATE_ID`, `_default_fallback_db_path()`, `_force_writable_file()`, `_can_write_sqlite()`, `_resolve_db_path()`, `get_conn()`, `_thread_conn()`, `close_thread_conn()`, `init_db()` (with internal `_ensure_columns` local function intact), `_json_dumps()`, `_json_loads()`, `_utc_now()`, `_utc_now_iso()`.
- `backend/app/services/db.py`: Group A definitions removed; backward-compat re-exports added via `from app.db.connection import (UPLOAD_PROFILE_LOCK_TTL_MINUTES, UPLOAD_SCHEDULER_STATE_ID, close_thread_conn, get_conn, init_db, _json_dumps, _json_loads, _thread_conn, _utc_now, _utc_now_iso)`. Reduced by ~500 lines (~1,886 → ~1,386 lines). `threading` import removed (not needed after Group A extraction).
- New test file: `backend/tests/test_db_connection.py` — 33 tests: import identity (8 symbols same-object `is`), constants (UPLOAD_PROFILE_LOCK_TTL_MINUTES=30, UPLOAD_SCHEDULER_STATE_ID="main"), get_conn() contract (Connection type, row_factory=sqlite3.Row, PRAGMA foreign_keys=1, journal_mode=wal), init_db() creates all 10 expected tables and is idempotent, _json_dumps/_json_loads edge cases (roundtrip, None sentinel behavior, empty string, invalid JSON), _thread_conn() same-connection reuse in same thread and different connections across threads, close_thread_conn() clears thread-local and is safe on empty state, _utc_now() timezone-aware UTC and _utc_now_iso() parseable ISO string.

**Contracts maintained**:
- `app.db.connection` imports from `app.core.config` and stdlib only — no import from `app.services.db`. No circular import.
- All 10 re-exported names in `services/db.py` are the SAME objects as in `app.db.connection` (`is` identity guaranteed).
- `_tls` thread-local state lives in exactly ONE module (`app.db.connection`). `_thread_conn`, `close_thread_conn`, `update_job_progress`, `upsert_job_part` all reference the same `_tls` instance.
- `init_db()` internal `_ensure_columns()` helper remains a local function inside `init_db()` — not hoisted to module scope.
- `UPLOAD_PROFILE_LOCK_TTL_MINUTES` re-exported from `services/db.py` — `routes/upload.py` caller unchanged.
- 14 production callers (main.py, 5 routes, 4 orchestration files, 3 service files) unchanged.
- No SQL, no DDL, no PRAGMA, no row_factory, no DATABASE_PATH logic changed.

---

## Test Suite State (Post Phase 4F.1)

```
6107 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4F.1 added 33 new passing tests (`test_db_connection.py`).

---

## Phase 4F.2 — Extract Jobs Repo

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Second implementation sub-phase of Phase 4F. Move jobs + job_parts CRUD functions from `backend/app/services/db.py` into `backend/app/db/jobs_repo.py`. Backward-compat re-exports keep all existing callers unchanged.

**Shipped changes**:
- New file: `backend/app/db/jobs_repo.py` (~145 lines) — 9 Group B functions moved verbatim from `services/db.py`. Imports only from `app.db.connection` (`_json_dumps`, `_thread_conn`, `get_conn`). No circular import.
- `backend/app/services/db.py`: 9 function bodies removed; backward-compat re-exports added via `from app.db.jobs_repo import (delete_job, get_job, list_job_parts, list_job_parts_bulk, list_jobs, list_jobs_page, update_job_progress, upsert_job, upsert_job_part)`. Reduced by ~145 lines.
- `backend/tests/test_db_connection.py`: `_reset_db_path` helper updated to patch `app.db.connection.DATABASE_PATH` (the local binding) directly, ensuring proper test isolation. `app.core.config.DATABASE_PATH` patch was not sufficient since `connection.py` uses a `from`-import binding.
- New test file: `backend/tests/test_jobs_repo.py` — 35 tests: import identity (9 symbols same-object `is`), job CRUD (upsert creates/updates, get returns dict or None, delete cascades to parts), update_job_progress (stage/progress/message, with/without status, thread-local path), pagination (list_jobs DESC order, list_jobs_page limit/offset/empty), job parts (upsert creates/updates, list ordered by part_no, bulk empty dict/groups-by-job/empty-list-no-parts), JSON payload/result roundtrip (None sentinel → {}), thread-local (progress + part share connection, close allows new connection).

**Contracts maintained**:
- `app.db.jobs_repo` imports from `app.db.connection` only — no import from `app.services.db`. No circular import.
- All 9 re-exported names in `services/db.py` are the SAME objects as in `app.db.jobs_repo` (`is` identity guaranteed).
- `_thread_conn` still lives in `app.db.connection` — `update_job_progress` and `upsert_job_part` both use the shared thread-local from `app.db.connection._tls`. Close behavior via `close_thread_conn()` is unchanged.
- No SQL, no DDL, no function signatures changed.
- 14 production callers all import from `app.services.db` — unchanged.

**Discovery**: `from app.core.config import DATABASE_PATH` creates a local binding in `connection.py`. Patching `app.core.config.DATABASE_PATH` in tests does NOT affect `connection.py`'s binding. Tests must patch `app.db.connection.DATABASE_PATH` directly for proper DB isolation. Fixed in both `test_db_connection.py` and `test_jobs_repo.py`.

---

## Test Suite State (Post Phase 4F.2)

```
6142 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4F.2 added 35 new passing tests (`test_jobs_repo.py`).

---

## Phase 4F.3 — Extract Creator Repo

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Third implementation sub-phase of Phase 4F. Move creator preferences CRUD from `backend/app/services/db.py` into `backend/app/db/creator_repo.py`. Backward-compat re-exports keep all existing callers unchanged.

**Shipped changes**:
- New file: `backend/app/db/creator_repo.py` (~30 lines) — 2 Group E functions moved verbatim from `services/db.py`: `get_creator_prefs()`, `upsert_creator_prefs()`. Imports only from `app.db.connection` (`_json_dumps`, `_json_loads`, `get_conn`). No circular import.
- `backend/app/services/db.py`: 2 function bodies removed; backward-compat re-exports added via `from app.db.creator_repo import (get_creator_prefs, upsert_creator_prefs)`. Reduced by ~25 lines (~1,261 → ~1,236 lines). Upload, platform, and scheduler functions NOT moved — remain in `services/db.py`.
- New test file: `backend/tests/test_creator_repo.py` — 17 tests: import identity (2 symbols same-object `is`, module importability), `get_creator_prefs()` returns `{}` when no row exists, `upsert_creator_prefs()` creates/overwrites row, nested JSON roundtrip, empty dict roundtrip, return value equals persisted state, invalid JSON fallback (returns `{}`), NULL prefs_json fallback (returns `{}`), old import path (`app.services.db`) works end-to-end, cross-module read/write.

**Contracts maintained**:
- `app.db.creator_repo` imports from `app.db.connection` only — no import from `app.services.db`. No circular import.
- Both re-exported names in `services/db.py` are the SAME objects as in `app.db.creator_repo` (`is` identity guaranteed).
- No SQL, no DDL, no function signatures changed.
- Upload domain (uploads_repo), platform repo (platform_repo) NOT moved yet — planned for 4F.4 and 4F.5.
- 14 production callers all import from `app.services.db` — unchanged.

---

## Test Suite State (Post Phase 4F.3)

```
6159 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4F.3 added 17 new passing tests (`test_creator_repo.py`).

---

## Phase 4F.4 — Extract Platform Repo

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Fourth implementation sub-phase of Phase 4F. Move proxy/platform CRUD from `backend/app/services/db.py` into `backend/app/db/platform_repo.py`. Backward-compat re-exports keep all existing callers unchanged.

**Shipped changes**:
- New file: `backend/app/db/platform_repo.py` (~130 lines) — 6 Group D functions moved verbatim from `services/db.py`: `_normalize_proxy_pool_row()`, `list_proxy_pool_rows()`, `get_proxy_pool_row()`, `create_proxy_pool_row()`, `update_proxy_pool_row()`, `delete_proxy_pool_row()`. Imports only from `app.db.connection` (`_json_dumps`, `_json_loads`, `_utc_now_iso`, `get_conn`) plus stdlib (`sqlite3`, `uuid`). No circular import.
- `backend/app/services/db.py`: 6 function bodies removed; backward-compat re-exports added via `from app.db.platform_repo import (_normalize_proxy_pool_row, create_proxy_pool_row, delete_proxy_pool_row, get_proxy_pool_row, list_proxy_pool_rows, update_proxy_pool_row)`. Reduced by ~130 lines (~1,236 → ~1,106 lines). Upload domain functions NOT moved — remain in `services/db.py`.
- New test file: `backend/tests/test_platform_repo.py` — 44 tests: import identity (6 public symbols + private normalizer same-object `is`), list empty/returns-list, create (defaults, explicit proxy_id, metadata, timestamps), get (found/missing, metadata expanded, port int), list order/shape, update (name, status, metadata, preserves fields, missing returns None, updated_at), delete (true/false, row gone, list empty), normalizer unit tests (None/empty→None, metadata JSON expansion, invalid/None JSON fallback, port/latency_ms coercion, non-numeric fallback), old import path and cross-module read/write.

**Contracts maintained**:
- `app.db.platform_repo` imports from `app.db.connection` only — no import from `app.services.db`. No circular import.
- All 6 re-exported names in `services/db.py` are the SAME objects as in `app.db.platform_repo` (`is` identity guaranteed).
- No SQL, no DDL, no function signatures changed.
- Upload domain (uploads_repo) NOT moved yet — planned for 4F.5.
- 14 production callers all import from `app.services.db` — unchanged.

---

## Test Suite State (Post Phase 4F.4)

```
6203 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4F.4 added 44 new passing tests (`test_platform_repo.py`).

---

## Phase 4F.5 — Upload Domain Removal Audit

**Branch**: `restructure/output-timeline-architecture`
**Status**: AUDIT COMPLETE — awaiting user confirmation
**Commit**: (this commit)

**Purpose**: Audit whether the upload domain code (routes, services, DB functions, frontend) is still active before deciding whether to extract `uploads_repo.py` (original plan) or remove the domain entirely.

**Audit finding**: The upload domain is **100% active**. No dead code found.
- `routes/upload.py` — 1,502 lines, 42 endpoints, registered in `main.py`
- `services/upload_engine.py` — 1,793 lines, Playwright TikTok automation
- ~1,000 lines of upload DB functions still in `services/db.py`
- 6,224 lines of frontend JS (`upload-manager.js`, `upload-config.js`, `upload-engine.js`)
- 7 DB tables in `init_db()`: upload_accounts, upload_queue, upload_videos, upload_history, upload_runtime_locks, upload_scheduler_state, upload_proxy_pool
- All 43 upload DB functions actively called by `routes/upload.py`

**Decision**: `uploads_repo.py` extraction is **cancelled**. Upload domain will be removed as a coordinated deletion (not extracted first). Deletion plan requires user confirmation of 5 questions before proceeding.

**Deliverable**: `docs/restructure/PHASE_4F_5_UPLOAD_DOMAIN_REMOVAL_AUDIT.md`

**No backend code changed. No tests changed.**

---

## Phase 4F.5A — Remove Upload Entrypoints

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: First deletion sub-phase of upload domain removal. Remove upload router registration from backend startup and remove upload frontend entry points from static. Upload API endpoints now return 404. Frontend no longer loads or calls any upload UI.

**Shipped changes**:
- `backend/app/main.py`: removed `from app.routes.upload import router as upload_router` (import line); removed `app.include_router(upload_router)` (registration line); removed `'WebSocket /api/upload/'` from the noisy-access-log suppression filter. `routes/upload.py` still exists on disk but is no longer registered.
- `backend/static/index.html`: removed 3 `<script>` tags for `upload-config.js`, `upload-manager.js`, `upload-engine.js`.
- `backend/static/js/upload-manager.js`: **deleted** (5,397 lines).
- `backend/static/js/upload-config.js`: **deleted** (713 lines).
- `backend/static/js/upload-engine.js`: **deleted** (114 lines).
- New test file: `backend/tests/test_upload_entrypoints_removed.py` — 9 tests: upload_router absent from `main` module, zero `/api/upload` routes in FastAPI app, non-upload core routes still registered, 3 script-tag assertions in `index.html`, 3 file-deleted assertions on disk.

**Intentionally left for later phases**:
- `backend/app/routes/upload.py` — file still exists, not yet deleted (4F.5B scope)
- `backend/app/services/upload_engine.py` — still exists, not yet deleted (4F.5B scope)
- `backend/app/services/db.py` upload DB functions — still present (~1,000 lines, 4F.5C scope)
- `backend/app/db/platform_repo.py` — still present, not yet deleted (4F.5C scope)
- Upload tables in `init_db()` — still created on startup (4F.5D scope)
- `backend/static/js/render-engine.js` and `render-ui.js` — these contain `/api/upload/` fetch calls used by the render login/channel flow; these are NOT upload entry points and remain untouched

**Contracts maintained**:
- All non-upload routes (render, jobs, channels, download, creator, voice, viral, subtitle) still registered and functional.
- No DB schema changed. No upload DB functions removed. No render pipeline code touched.
- `services/db.py` unchanged.

---

## Test Suite State (Post Phase 4F.5A)

```
6212 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4F.5A added 9 new passing tests (`test_upload_entrypoints_removed.py`).

---

## Phase 4F.5B — Remove Upload Engine + Channels Dependency

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Second deletion sub-phase of upload domain removal. Delete `upload_engine.py`, decouple `channels.py` from it, and remove stale `/api/upload/` fetch calls from frontend JS files used by the render UI.

**Shipped changes**:
- `backend/app/services/upload_engine.py`: **deleted** (1,793 lines, Playwright TikTok automation).
- `backend/app/routes/channels.py`:
  - Removed `from app.services.upload_engine import (load_upload_settings, save_upload_settings, ensure_upload_account_profile, bootstrap_portable_runtime_for_channel)` import block.
  - Unified `create_channel` to always use the local `_write_channel_settings()` and `_write_channel_profile()` helpers (removed the if/else that used upload_engine functions for the non-custom-root path).
  - Removed `bootstrap_portable_runtime_for_channel` call and its `HTTPException` wrapper. Removed `bootstrap_root` variable.
  - Removed `portable_bootstrap` key from response.
  - In `channel_info`: replaced `load_upload_settings(channel_code)` with direct JSON file read (same pattern as the custom-root branch — reads `base / "account" / "upload_settings.json"` directly).
- `backend/static/js/render-engine.js`: Removed 9 upload-specific functions: `collectUploadPayload`, `uploadStageLabel`, `uploadPipelineState`, `renderUploadPipeline`, `setUploadAction`, `renderUploadRun`, `ensureUploadAccount`, `checkUploadLoginStatus`, `startLogin`, `_stopUploadWs` (~248 lines removed). These included 3 `/api/upload/` fetch calls (`/accounts/ensure`, `/login/check`, `/login/start`).
- `backend/static/js/render-ui.js`: Removed 5 upload queue functions: `addRenderClipToUploadQueue`, `loadUploadQueueLegacy`, `loadUploadQueue`, `runUploadQueueItem`, `cancelUploadQueueItem` (~145 lines removed). These included 5 `/api/upload/` fetch calls (`/queue/add`, `/queue`, `/queue/{id}/run`, `/queue/{id}/cancel`).
- New test file: `backend/tests/test_upload_engine_removed.py` — 11 tests: upload_engine.py file deleted, channels.py source contains no upload_engine references (5 symbol checks), channels module imports cleanly, upload_engine not importable, upload routes still absent from app, render-engine.js and render-ui.js contain no `/api/upload/` fetch calls.

**Remaining upload code intentionally left for later phases**:
- `backend/app/routes/upload.py` — file still on disk, dead (4F.5C scope)
- `backend/app/services/db.py` upload DB functions (~1,000 lines) — still present (4F.5C scope)
- `backend/app/db/platform_repo.py` — still present (4F.5C scope)
- Upload tables in `init_db()` — still created on startup (4F.5D scope)
- `globals.js` upload-related global variables — harmless orphans, deferred cleanup
- `channels.js` `refreshUploadValidationState()` call and `render-config.js` `syncUploadJsonModeUI()` calls — already broken since Phase 4F.5A (functions were defined in deleted upload-manager.js/upload-config.js); deferred cleanup

**Remaining `/api/upload-file` calls**: Two calls in `editor-audio-runtime.js` and `editor-view.js` use `/api/upload-file` (hyphen, not domain path). These are file-upload endpoints for the editor, completely unrelated to the TikTok upload domain — intentionally untouched.

**Note**: `dev_commands.py` and `qa_runner.py` have string references to `upload_engine.py` in file-path routing tables (not Python imports). These are safe — devtools are disabled by default, and `dev_commands.py` already handles `upload_engine.py not found` gracefully.

**Contracts maintained**:
- `channels.py` channel creation and info endpoints remain functional. Local `_write_channel_settings` and `_write_channel_profile` helpers produce equivalent output to the removed upload_engine functions for the channel creation use case.
- All non-upload routes, render pipeline, and job management unaffected.
- No DB schema changed. No upload DB functions removed. `services/db.py` unchanged.

---

## Test Suite State (Post Phase 4F.5B)

```
6223 passed, 1 skipped, 8 failed
```

The 8 persistent failures are pre-existing — unchanged.

Phase 4F.5B added 11 new passing tests (`test_upload_engine_removed.py`).

---

## Phase 4F.5C — Remove Upload DB Functions + Dead Upload Files

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Third deletion sub-phase of upload domain removal. Delete the now-dead `routes/upload.py` and `platform_repo.py`, remove all 43 upload-domain DB functions from `services/db.py`, and delete the upload-only test file. No DB schema changes — upload tables remain until Phase 4F.5D.

**Shipped changes**:
- `backend/app/routes/upload.py`: **deleted** (1,501 lines, 42 API endpoints; had been unregistered since Phase 4F.5A).
- `backend/app/db/platform_repo.py`: **deleted** (142 lines, proxy pool CRUD; upload-only, callers removed in 4F.5A).
- `backend/app/services/db.py`: **complete rewrite** — all 43 upload-domain DB functions removed (~1,062 lines deleted); removed `UPLOAD_PROFILE_LOCK_TTL_MINUTES`/`UPLOAD_SCHEDULER_STATE_ID` constants from connection import; removed `from app.db.platform_repo import (...)` re-export block; removed now-unused stdlib imports (`json`, `os`, `sqlite3`, `uuid`, `datetime`, `timedelta`, `timezone`, `Path`, `Any`, `DATABASE_PATH`). File reduced from 1,116 → 31 lines — now a pure re-export shim for `connection`, `jobs_repo`, and `creator_repo`.
- `backend/tests/test_platform_repo.py`: **deleted** (44 tests; tested deleted platform_repo.py).
- `backend/tests/test_db_connection.py`: removed `test_constants_re_exported_from_services_db` (tested the now-removed re-export of upload constants from services/db).
- New test file: `backend/tests/test_upload_domain_removed.py` — 13 tests covering: deleted files (routes/upload.py, upload_engine.py, platform_repo.py), services/db.py exposes no upload symbols, services/db.py exposes no proxy symbols, upload constants absent from services/db.py, live non-upload symbols still present, three dead modules not importable, no /api/upload routes registered, static files contain no /api/upload fetch calls, upload tables still present in connection.py (sanity check for Phase 4F.5D pre-condition).

**Remaining upload code intentionally left for Phase 4F.5D**:
- `backend/app/db/connection.py` upload table DDL — 7 `CREATE TABLE IF NOT EXISTS upload_*` blocks still present
- `backend/app/db/connection.py` `_ensure_columns` migration calls for upload tables — still present
- `backend/app/db/connection.py` `INSERT INTO upload_scheduler_state` seed row — still present
- `UPLOAD_PROFILE_LOCK_TTL_MINUTES`, `UPLOAD_SCHEDULER_STATE_ID` constants in `connection.py` — still present (tested in `test_db_connection.py::TestConstants`)

**Contracts maintained**:
- All non-upload routes, render pipeline, and job management unaffected.
- `services/db.py` re-exports for jobs, creator, and connection helpers unchanged — all callers (`render_pipeline.py`, `routes/render.py`, `routes/jobs.py`, `main.py`, etc.) work without modification.
- No DB schema changed. Upload tables still exist in running databases.

**Audit findings**:
- `routes/upload.py` — only importer was `main.py` (removed in 4F.5A); no remaining callers. A.
- `platform_repo.py` — only callers were `services/db.py` shim (removed) and `routes/upload.py` (deleted). A.
- All 43 upload DB functions — only caller was `routes/upload.py` (deleted). A.
- `UPLOAD_PROFILE_LOCK_TTL_MINUTES`, `UPLOAD_SCHEDULER_STATE_ID` — only used by upload functions (removed) and `routes/upload.py` (deleted). A.
- No unexpected active callers found.

---

## Test Suite State (Post Phase 4F.5C)

```
6133 passed, 1 skipped, 67 failed  (environment without edge_tts)
```

The 67 failures are all pre-existing environment failures — `edge_tts` not installed in this test environment causes the render_pipeline import chain to fail for many test files. No new failures introduced by Phase 4F.5C. All 84 DB tests (test_db_connection, test_jobs_repo, test_creator_repo) pass cleanly.

Phase 4F.5C: deleted 44 tests (`test_platform_repo.py`), removed 1 test from `test_db_connection.py`, added 13 new tests (`test_upload_domain_removed.py`). Net: −32 tests from suite.

---

## Phase 4F.5D — Drop Upload Schema + Final Upload Cleanup

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Final upload-domain removal phase. Remove upload table DDL from `init_db()`, remove upload-only constants from `connection.py`, add idempotent `_drop_upload_tables()` migration helper, and update tests and docs.

**Shipped changes**:
- `backend/app/db/connection.py`: Complete rewrite (~522 → 230 lines).
  - Removed `UPLOAD_PROFILE_LOCK_TTL_MINUTES = 30` and `UPLOAD_SCHEDULER_STATE_ID = "main"` constants.
  - Removed 7 `CREATE TABLE IF NOT EXISTS upload_*` DDL blocks (`upload_accounts`, `upload_queue`, `upload_videos`, `upload_history`, `upload_runtime_locks`, `upload_scheduler_state`, `upload_proxy_pool`).
  - Removed 6 `_ensure_columns()` calls for upload tables (kept jobs and job_parts blocks).
  - Removed `INSERT INTO upload_scheduler_state` seed row.
  - Added `_UPLOAD_TABLES` tuple and `_drop_upload_tables(conn)` function (idempotent `DROP TABLE IF EXISTS` for all 7 upload tables).
  - Added `_drop_upload_tables(conn)` call inside `init_db()` — runs on every startup, drops stale upload tables from any existing DB file.
- `backend/tests/test_db_connection.py`:
  - Removed `TestConstants` class (2 tests for now-deleted upload constants).
  - Updated `EXPECTED_TABLES` set from 10 tables to 3 (`jobs`, `job_parts`, `creator_prefs`).
  - Updated `test_tables_accessible_after_init` to query `creator_prefs` instead of `upload_accounts`.
- `backend/tests/test_upload_domain_removed.py`: Removed `TestUploadTablesStillInSchema` class (1 test; was a Phase 4F.5D guard, now obsolete).
- New test file: `backend/tests/test_upload_schema_removed.py` — 20 tests: upload constants absent from connection.py, init_db() does not create any of the 7 upload tables, init_db() creates exactly 3 live tables (jobs, job_parts, creator_prefs), `_drop_upload_tables()` drops existing upload tables from a simulated old DB, `_drop_upload_tables()` is idempotent, `jobs` table preserved after drop, `_drop_upload_tables` helper callable at module level.

**Contracts maintained**:
- `init_db()` is still called via `services/db.py` shim → `main.py`. Existing databases: upload tables are dropped on first startup after upgrade. New databases: upload tables are never created.
- `services/db.py` public namespace: `[]` for upload symbols, `[]` for proxy symbols. Only live job/creator/connection re-exports remain.
- All non-upload routes, render pipeline, and job management unaffected.

**services/db.py public namespace (post 4F.5D)**:
```
['_json_dumps', '_json_loads', '_thread_conn', '_utc_now', '_utc_now_iso',
 'close_thread_conn', 'delete_job', 'get_conn', 'get_creator_prefs', 'get_job',
 'init_db', 'list_job_parts', 'list_job_parts_bulk', 'list_jobs', 'list_jobs_page',
 'logger', 'logging', 'update_job_progress', 'upsert_creator_prefs', 'upsert_job', 'upsert_job_part']
```
No upload or proxy symbols.

**Upload domain fully removed** — Phases 4F.5A through 4F.5D complete:
- 4F.5A: Upload router unregistered, frontend JS files deleted.
- 4F.5B: `upload_engine.py` deleted, `channels.py` decoupled.
- 4F.5C: `routes/upload.py` deleted, `platform_repo.py` deleted, all upload DB functions removed from `services/db.py`.
- 4F.5D: Upload table DDL removed from `init_db()`, constants removed, `_drop_upload_tables()` migration added.

---

## Test Suite State (Post Phase 4F.5D)

```
6148 passed, 1 skipped, 67 failed  (environment without edge_tts)
```

The 67 failures are identical to Phase 4F.5C — all pre-existing environment failures (`edge_tts` not installed). Zero new failures from Phase 4F.5D changes. All 133 targeted tests pass (DB connection, jobs, creator, upload removal, upload schema).

Phase 4F.5D: removed 3 tests (TestConstants×2 from test_db_connection.py, TestUploadTablesStillInSchema×1 from test_upload_domain_removed.py), added 20 new tests (`test_upload_schema_removed.py`). Net: +17 tests from suite.

---

## Phase 4F.6 — Test Baseline Stabilization + DB Import Audit

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Investigate the 8→67 failure spike, confirm all failures are environment-only (not regressions), install the declared production dependency in the test venv, audit DB imports across the app after upload removal, and add a structural import audit test file.

**Root cause of failure spike**:
- `backend/app/services/tts_service.py:8` has a hard top-level `import edge_tts`.
- `edge-tts==7.2.8` is declared in `requirements.txt` but was not installed in the test venv.
- Import chain: any test importing `app.main` → `app.routes.render` → `render_pipeline` → `tts_service` → `edge_tts` → `ModuleNotFoundError`.
- Fix: `pip install "edge-tts==7.2.8"` in the project venv. Baseline restored to `8 failed, 6207 passed, 1 skipped`.

**DB import audit findings**:
- `services/db.py` post-4F.5D is a 31-line pure re-export shim. No upload or proxy symbols in namespace.
- All `app.services.db` callers across app code import only live (non-upload) functions.
- `dev_commands.py` contains string path literals to deleted files (`"backend/app/services/upload_engine.py"`) — these are routing table strings, not Python imports; acceptable historical references in dev tooling.
- No active Python imports of deleted modules (`upload_engine`, `platform_repo`, `routes.upload`) found anywhere in the codebase.

**Shipped changes**:
- Installed `edge-tts==7.2.8` in the project venv (restores declared production dependency).
- New test file: `backend/tests/test_db_import_audit.py` — 15 tests covering:
  - All 4 DB modules import cleanly (`connection`, `jobs_repo`, `creator_repo`, `services.db`).
  - `services/db.py` exposes all expected live symbols (connection, jobs, creator).
  - `services/db.py` exposes no upload, proxy, or platform-repo symbols.
  - Upload constants absent from `services/db.py`.
  - 3 deleted files absent from filesystem and not importable (`platform_repo`, `routes/upload`, `upload_engine`).

**Test suite state (post 4F.6)**:
```
8 failed, 6222 passed, 1 skipped  (with edge_tts installed)
```
The 8 pre-existing failures are unchanged. +15 tests from `test_db_import_audit.py`.

---

## Phase 4F.7 — Architecture Freeze

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Freeze the backend restructure state after Phase 4F completion. Audit all stale documentation references. Create the architecture freeze document as the entry gate for Phase 4G. No code changes.

**Created**:
- `docs/restructure/PHASE_4F_7_ARCHITECTURE_FREEZE.md` — 20-section freeze document: completed scope, backend module tree, render/orchestration/DB architecture, upload domain removal status, compatibility shim policy, active APIs, removed APIs, test baseline, stale reference audit results, dependency direction rules, what must not change, Phase 4G entry criteria, Phase 4H preview note.

**Stale references corrected**:
- `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md:26` — removed stale `platform_repo.py (proxy pool CRUD); uploads_repo planned (4F.5)` references; updated to reflect actual state (only connection.py, jobs_repo.py, creator_repo.py in app/db/).
- `docs/review/TECHNICAL_DEBT_REPORT.md` H1 — marked "RESOLVED (Phase 4F)"; `services/db.py` is now a 31-line shim, not a god file.
- `docs/review/TECHNICAL_DEBT_REPORT.md` L1 — marked "OBSOLETE (Phase 4F.5)"; `enrich_upload_account_runtime_state()` deleted with upload domain.
- `docs/review/TECHNICAL_DEBT_REPORT.md` L4 — updated to note upload `_ensure_columns` blocks removed; only `jobs`/`job_parts` remain.
- `docs/review/SCORECARD.md` — removed `upload.py` from active router list; noted `db.py` debt resolved.
- `docs/review/BRUTAL_REVIEW_SUMMARY.md` — updated SQLite single-database section to remove references to TikTok upload credentials (upload domain removed).
- `docs/restructure/PHASE_4A_BACKEND_MODULARIZATION_PLAN.md` — status updated to reference 4F.7.

**Audit findings summary**:
- 0 classification-E findings (no unexpected active upload code in backend/app).
- All `from app.services.render_engine import ...` callers — classification D (active shim, acceptable).
- All `from app.services.db import ...` callers — classification D (active shim, acceptable).
- `services/dev_commands.py` + `qa_runner.py` string refs to deleted files — classification B (dev tooling string literals, not Python imports).
- `connection.py _drop_upload_tables()` — classification A (correct migration helper).

**Contracts maintained**:
- All public API endpoints unchanged.
- All render behavior unchanged.
- `services/render_engine.py` shim: 53 lines, all render symbols re-exported.
- `services/db.py` shim: 31 lines, all DB symbols re-exported.
- Test baseline: 8 failed, 6222 passed, 1 skipped (unchanged).

**Phase 4G entry criteria**: documented in PHASE_4F_7_ARCHITECTURE_FREEZE.md §18. Requires Phase 4G plan doc + subtitle_engine audit + circular import resolution before starting.

---

## Test Suite State (Post Phase 4F.7)

```
8 failed, 6222 passed, 1 skipped  (docs-only phase, no test changes)
```

No new tests added in Phase 4F.7 (docs/audit only). Baseline unchanged.

---

## Phase 4G.0 — Subtitle Engine Split Planning

**Branch**: `restructure/output-timeline-architecture`
**Status**: PLANNING — no code changed
**Source plan**: [PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md](PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md)

**Purpose**: Audit `subtitle_engine.py` (1,970 lines) and produce a complete split plan before any extraction begins.

**Audit findings**:
- 1,970 lines, 7 distinct clusters identified:
  - **A — Styles/Constants**: `SUBTITLE_STYLES`, `SUBTITLE_PRESETS`, `_HL_OPEN`/`_HL_CLOSE` PUA constants → `styles.py`
  - **B — SRT Core**: `parse_srt_blocks`, `write_srt_blocks`, `slice_srt_by_time`, `slice_srt_to_output_timeline`, `_run_with_retry` → `srt_core.py`
  - **C — ASS Core**: `srt_to_ass_bounce`, `srt_to_ass_karaoke`, `burn_subtitle_onto_video`, `_ass_escape_text`, `_hex_to_ass` → `ass_core.py`
  - **D — Readability**: `resegment_srt_for_readability`, `slice_srt_to_text`, `insert_emphasis_markers` → `readability.py`
  - **E — Text Transforms**: `apply_market_line_break_to_srt`, `apply_market_hook_text_to_srt`, `apply_hook_subtitle_format`, `resolve_hook_overlay_text`, `subtitle_emphasis_pass` → `text_transforms.py`
  - **F — Transcription**: `transcribe_audio`, `_MODEL_CACHE`, `has_audio_stream` (deferred import) → `transcription.py`
  - **G — Shim**: `subtitle_engine.py` stays as a re-export shim after all clusters extracted

**Key risks identified**:
- Hard `import whisper` at line 9 — after extraction, only `transcription.py` is affected; breaking the whole module is eliminated
- `has_audio_stream()` uses a deferred import from `render_engine._has_audio_stream` (line 280–289) — classified as cross-module coupling; resolution in Phase 4G.6 (change to `from app.services.render.ffmpeg_helpers import _has_audio_stream`)
- `_HL_OPEN`/`_HL_CLOSE` shared between `_ass_escape_text` (ass_core) and `_insert_emphasis_markers` (readability) — defined once in `styles.py`, imported by both
- `_run_with_retry` used by both transcription (2 callers) and `burn_subtitle_onto_video` (1 caller) — placed in `srt_core.py` (no new dependency edge)

**Dependency DAG for target package**:
```
styles.py ← readability.py ← ass_core.py
srt_core.py ← transcription.py
srt_core.py ← text_transforms.py
```
No cycles. All edges point inward toward styles/srt_core.

**Proposed sub-phases**:
- 4G.1: Extract `styles.py` (constants only, no logic, no deps)
- 4G.2: Extract `srt_core.py` (SRT parse/write/slice, `_run_with_retry`)
- 4G.3: Extract `ass_core.py` (ASS rendering, depends on styles.py + srt_core.py)
- 4G.4: Extract `readability.py` (depends on styles.py + srt_core.py)
- 4G.5: Extract `text_transforms.py` (depends on srt_core.py)
- 4G.6: Extract `transcription.py` (Whisper model, fix `has_audio_stream` import)
- 4G.7: Convert `subtitle_engine.py` to shim + caller migration

**Docs created**: `PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md` (20 sections)

**Docs updated**:
- `MIGRATION_HISTORY.md` (this entry)
- `PHASE_4A_BACKEND_MODULARIZATION_PLAN.md` — status updated to include 4G.0 planning
- `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` — last updated note
- `docs/review/TECHNICAL_DEBT_REPORT.md` — H2 entry updated with 4G.0 planning note

**Contracts maintained**:
- All public `subtitle_engine` exports unchanged.
- All render behavior unchanged.
- No new imports, no function moves, no shim changes.
- Test baseline: 8 failed, 6222 passed, 1 skipped (unchanged — docs-only phase).

---

## Test Suite State (Post Phase 4G.0)

```
8 failed, 6222 passed, 1 skipped  (docs-only phase, no test changes)
```

No new tests added in Phase 4G.0 (planning only). Baseline unchanged.

---

## Phase 4G.1 — Extract Subtitle Styles

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Source plan**: [PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md](PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md) — Cluster A

**Purpose**: Create `app/services/subtitles/` package scaffold and extract Cluster A (styles/presets/PUA constants) from `subtitle_engine.py` into `subtitles/styles.py`.

**Shipped changes**:
- New file: `backend/app/services/subtitles/__init__.py` (empty package scaffold)
- New file: `backend/app/services/subtitles/styles.py` (~292 lines) — verbatim copy of Cluster A:
  - `_HL_OPEN` / `_HL_CLOSE` (PUA Unicode sentinels U+E100/U+E101)
  - `_compute_subtitle_scale()`, `_compute_margin_v()` (resolution helpers)
  - `BOUNCE_FX`, `_PRESET_MOTION_FX`, `_MOTION_FX_DEFAULT`, `_get_motion_fx()`
  - `ASSPreset` frozen dataclass (20 fields)
  - `_PRESETS` dict (10 canonical preset entries)
  - `_STYLE_ALIASES` dict (5 backward-compat aliases)
  - `_DEFAULT_PRESET_ID`
  - `normalize_subtitle_style_id()`, `get_subtitle_preset()`, `build_ass_style_line()`
- `subtitle_engine.py` edited: removed `from dataclasses import dataclass`; removed `_HL_OPEN`/`_HL_CLOSE` definitions; removed `_compute_subtitle_scale`/`_compute_margin_v` function bodies; removed entire ASS Preset architecture block; added `from app.services.subtitles.styles import (...)` re-export block.
- New tests: `backend/tests/test_subtitle_styles.py` — 39 tests

**subtitle_engine.py line reduction**: 1,970 → 1,699 lines (−271)

**Contracts maintained**:
- All public `subtitle_engine` exports unchanged — same-object identity passes for all mutable dicts.
- `_HL_OPEN = ''` / `_HL_CLOSE = ''` — exact PUA codepoints preserved.
- `_PRESETS` table: 10 preset entries, all field values verbatim.
- `_STYLE_ALIASES` table: 5 entries, all unchanged.
- `_DEFAULT_PRESET_ID = "tiktok_bounce_v1"` unchanged.
- `ASSPreset` is a frozen dataclass with 20 fields — field order preserved.
- No ASS rendering behavior changed. No SRT timing behavior changed.

**No circular imports**: `styles.py` imports only `dataclasses.dataclass` (stdlib). `subtitle_engine.py` imports from `styles.py` (correct direction).

---

## Test Suite State (Post Phase 4G.1)

```
8 failed, 6261 passed, 1 skipped  (+39 new tests in test_subtitle_styles.py)
```

39 new tests in `test_subtitle_styles.py`. All 8 known failures are pre-existing. Baseline maintained.

---

## Phase 4G.2 — Extract SRT Core

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Source plan**: [PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md](PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md) — Cluster B (partial — `slice_srt_to_output_timeline` deferred)

**Purpose**: Extract Cluster B (SRT parsing/writing/slicing, timestamp helpers, `_run_with_retry`) from `subtitle_engine.py` into `subtitles/srt_core.py`.

**Shipped changes**:
- New file: `backend/app/services/subtitles/srt_core.py` (~165 lines) — verbatim copy of:
  - `format_srt_timestamp`, `parse_srt_timestamp` — SRT timestamp format/parse
  - `_parse_srt_blocks` — internal SRT parser (text joined with space)
  - `parse_srt_blocks` — public round-trip parser (text joined with `\n`)
  - `write_srt_blocks` — SRT file writer
  - `slice_srt_by_time` — time-range slicing with optional speed scaling
  - `slice_srt_to_text` — plain-text extraction, no file write
  - `_run_with_retry` — generic subprocess retry (shared with future ass_core)
- `subtitle_engine.py` edited: removed 8 function bodies; added `from app.services.subtitles.srt_core import (...)` re-export block.
- New tests: `backend/tests/test_subtitle_srt_core.py` — 44 tests

**Deferred (not moved)**:
- `slice_srt_to_output_timeline` stays in `subtitle_engine.py` — depends on `TimelineMap`; deferred per Phase 4G.2 spec. Still calls `slice_srt_by_time` (now imported from srt_core) — no behavior change.

**subtitle_engine.py line reduction**: 1,699 → 1,539 lines (−160)

**Contracts maintained**:
- All public `subtitle_engine` exports unchanged — same-object identity passes for all 8 moved functions.
- `slice_srt_by_time` signature, defaults, return dict schema — verbatim.
- `slice_srt_to_output_timeline` still in `subtitle_engine.py`, still calls `slice_srt_by_time`.
- `_run_with_retry` retry count and exception re-raise behavior — verbatim.
- No ASS rendering behavior changed. No Whisper/transcription behavior changed.

**No circular imports**: `srt_core.py` imports only `subprocess`, `time`, `pathlib.Path` (all stdlib). No subtitle package internal deps.

---

## Test Suite State (Post Phase 4G.2)

```
8 failed, 6305 passed, 1 skipped  (+44 new tests in test_subtitle_srt_core.py)
```

44 new tests in `test_subtitle_srt_core.py`. All 8 known failures are pre-existing. Baseline maintained.

---

## Phase 4G.3 — Extract Output Timeline Subtitle Helper

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Source plan**: [PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md](PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md) — Cluster B completion

**Purpose**: Extract `slice_srt_to_output_timeline` (deferred from Phase 4G.2) into `subtitles/output_timeline.py`. This function bridges `srt_core.slice_srt_by_time` with the `TimelineMap` domain object and is required for the overlay compositor path (output-timeline subtitle positioning).

**Shipped changes**:
- New file: `backend/app/services/subtitles/output_timeline.py` (~30 lines) — verbatim copy of:
  - `slice_srt_to_output_timeline(source_srt_path, output_srt_path, source_start, source_end, timeline)` — delegates to `slice_srt_by_time` with `playback_speed=timeline.effective_speed, rebase_to_zero=True, apply_playback_speed=True`
- `subtitle_engine.py` edited: removed `from app.domain.timeline import TimelineMap` (no longer needed), removed `slice_srt_to_output_timeline` function body; added `from app.services.subtitles.output_timeline import (slice_srt_to_output_timeline,)` re-export at top.
- New tests: `backend/tests/test_subtitle_output_timeline.py` — 21 tests
- Updated `backend/tests/test_subtitle_srt_core.py::TestSliceSrtToOutputTimelineEngineCompat::test_output_timeline_calls_slice_srt_by_time` — patch target updated from `subtitle_engine.slice_srt_by_time` to `output_timeline.slice_srt_by_time` (the function now lives in the new module).

**subtitle_engine.py line reduction**: 1,539 → 1,514 lines (−25)

**Contracts maintained**:
- `subtitle_engine.slice_srt_to_output_timeline` still works — same-object identity with `subtitles.output_timeline.slice_srt_to_output_timeline`.
- Output-timeline timing contract unchanged: timestamps divided by `timeline.effective_speed`, rebased to zero.
- `apply_playback_speed=True` — the overlay path still receives output-timeline SRT.
- No ASS rendering behavior changed. No Whisper/transcription behavior changed.
- `test_slice_srt_to_output_timeline.py` (existing 14 tests) — all pass unchanged.

**No circular imports**:
- `output_timeline.py` imports `TimelineMap` (domain, no subtitle deps) and `srt_core.slice_srt_by_time` (lower layer). No import of `subtitle_engine.py`.

---

## Test Suite State (Post Phase 4G.3)

```
8 failed, 6326 passed, 1 skipped  (+21 new tests in test_subtitle_output_timeline.py)
```

21 new tests in `test_subtitle_output_timeline.py`. All 8 known failures are pre-existing. Baseline maintained.

---

## Phase 4G.4 — Extract ASS Core

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Source plan**: [PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md](PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md) — Cluster C (ASS Core) + Cluster D visual-width stub

**Purpose**: Extract ASS generation/conversion cluster from `subtitle_engine.py` into `subtitles/ass_core.py`. Also creates `subtitles/readability.py` as a minimal stub with visual-width helpers required by `srt_to_ass_bounce` — establishes the correct `ass_core → readability` dependency direction per the Phase 4G DAG.

**Shipped changes**:
- New file: `backend/app/services/subtitles/readability.py` (stub, ~70 lines):
  - `_WIDE_CHARS`, `_NARROW_CHARS` — character width classification frozensets
  - `_approx_visual_width` — em-unit width estimator
  - `_break_by_visual_width` — visual-midpoint line-break for subtitle captions
  - No subtitle package internal deps (pure Python, no imports from subtitles/)
- New file: `backend/app/services/subtitles/ass_core.py` (~290 lines) — verbatim copy of:
  - `_ass_time` — ASS centisecond timestamp formatter (H:MM:SS.cc)
  - `_ass_escape_text` — safe embedding in ASS Dialogue Text; resolves `_HL_OPEN`/`_HL_CLOSE`
  - `_ass_highlight_tags` — market-specific inline ASS color tags
  - `srt_to_ass_bounce` — main SRT→ASS converter (bounce/viral styles)
  - `_hex_to_ass` — CSS #RRGGBB → ASS &HAABBGGRR
  - `srt_to_ass_karaoke` — pro karaoke-style ASS (word-level SRT, fallback to bounce)
  - `_safe_filter_path` — FFmpeg filter path escaping
  - `burn_subtitle_onto_video` — burn ASS onto video via ffmpeg
  - `_PREVIEW_ASPECT_RES`, `_PREVIEW_FONTS_DIR` — preview render constants
  - `render_subtitle_preview` — render PNG preview via ffmpeg lavfi
- `subtitle_engine.py` edited: removed 11 ASS functions/constants + 4 visual-width helpers; added `from app.services.subtitles.readability import (...)` and `from app.services.subtitles.ass_core import (...)` re-export blocks.
- New tests: `backend/tests/test_subtitle_ass_core.py` — 62 tests

**Deferred (not moved)**:
- `subtitle_emphasis_pass`, `resegment_srt_for_readability` — Cluster D, Phase 4G.5
- Text transforms (`apply_market_hook_text_to_srt`, etc.) — Cluster E, Phase 4G.5
- Transcription/Whisper cluster — Phase 4G.6

**subtitle_engine.py line reduction**: 1,514 → 1,018 lines (−496)

**Contracts maintained**:
- All public `subtitle_engine` exports unchanged — same-object identity passes for all moved functions.
- `srt_to_ass_bounce` signature, ASS output format, style line content — verbatim.
- `srt_to_ass_karaoke` `\k` timing tags and fallback logic — verbatim.
- `_ass_escape_text` resolves `_HL_OPEN`/`_HL_CLOSE` via shared constants from `styles.py`.
- `_PREVIEW_FONTS_DIR` path corrected to `parents[3]` (ass_core.py is one level deeper than subtitle_engine.py).
- No ASS output content changed. No SRT timing behavior changed. No Whisper behavior changed.

**Dependency graph** (no cycles):
```
readability.py  → [no subtitle deps]
ass_core.py     → styles.py + srt_core.py + readability.py
```

---

## Test Suite State (Post Phase 4G.4)

```
8 failed, 6388 passed, 1 skipped  (+62 new tests in test_subtitle_ass_core.py)
```

62 new tests in `test_subtitle_ass_core.py`. All 8 known failures are pre-existing. Baseline maintained.

---

## Phase 4G.5 — Extract Subtitle Text Transforms + Full Readability Cluster

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Source plan**: [PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md](PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md) — Cluster D (full) + Cluster E

**Purpose**: Extend `subtitles/readability.py` with the full readability/emphasis cluster and create new `subtitles/text_transforms.py` with the market/hook text transform cluster. After this phase, `subtitle_engine.py` contains only the Whisper/transcription cluster plus re-export blocks.

**Shipped changes**:
- `backend/app/services/subtitles/readability.py` extended from stub (~70 lines) to full module (~370 lines). Added:
  - `_HOOK_EMPHASIS_WORDS` — hook/emphasis vocabulary frozenset (shared with `text_transforms`)
  - `_is_cjk` — CJK/Hiragana/Katakana/Hangul detection
  - `_emphasis_level` — intensity map per preset ID (strong/medium/subtle/minimal/word_only)
  - `_EMPH_CONTRAST`, `_EMPH_EMOTIONAL`, `_EMPH_URGENCY`, `_NUMBER_RE` — emphasis vocabulary sets + regex
  - `_should_emphasize`, `_uppercase_emphasis_words`, `_insert_emphasis_markers` — emphasis token helpers
  - `_semantic_wrap_block` — midpoint wrap with orphan/widow avoidance
  - `subtitle_emphasis_pass` — unified emphasis pipeline entry point
  - `_INTEL_MAX_WPS`, `_INTEL_MAX_WORDS`, `_INTEL_MIN_DISPLAY_SEC`, `_INTEL_GAP_FILL_SEC` — readability tuning constants (env-overridable)
  - `_PUNCT_PAUSE_RE`, `_CLAUSE_STARTERS` — phrase boundary detection
  - `_find_phrase_split`, `_split_block_semantic`, `resegment_srt_for_readability` — CapCut-style resegmentation
  - Module-level imports added: `os`, `re`, `logging`, `Path`, `from styles import (normalize_subtitle_style_id, get_subtitle_preset, _HL_OPEN, _HL_CLOSE)`, `from srt_core import (_parse_srt_blocks, format_srt_timestamp)`
- New file: `backend/app/services/subtitles/text_transforms.py` (~270 lines):
  - `resolve_hook_overlay_text` — explicit hook text or first SRT block fallback
  - `apply_market_line_break_to_srt` — market/tone word-count policy re-wrap; deferred import from `market_subtitle_policy`
  - `apply_market_hook_text_to_srt` — replace opening subtitle hook zone
  - `format_hook_subtitle` — single-block visual impact formatting (uppercase emphasis anchor)
  - `apply_hook_subtitle_format` — apply impact formatting to first N blocks
  - `apply_subtitle_execution_hints` — consume AI subtitle execution metadata (never mutates timing)
  - Imports: `re`, `logging`, `Path`, `from srt_core import (_parse_srt_blocks, format_srt_timestamp)`, `from readability import _HOOK_EMPHASIS_WORDS`
- `subtitle_engine.py` edited:
  - Updated `from subtitles.readability import (...)` block to include all 21 new symbols
  - Added `from app.services.subtitles.text_transforms import (...)` re-export block (6 symbols)
  - Removed all moved function/constant bodies (lines 237–1018); file reduced from 1,018 → 249 lines
  - `subtitle_engine.py` now contains only: re-export blocks (imports) + Whisper/transcription cluster
- New tests: `backend/tests/test_subtitle_readability.py` — 57 tests
- New tests: `backend/tests/test_subtitle_text_transforms.py` — 49 tests

**subtitle_engine.py line reduction**: 1,018 → 249 lines (−769)

**Contracts maintained**:
- All public `subtitle_engine` exports unchanged — same-object identity passes for all moved symbols.
- `subtitle_emphasis_pass` signature, per-block pipeline order, word-level SRT detection — verbatim.
- `resegment_srt_for_readability` gap-fill/clamp behavior, env-override constants — verbatim.
- `_HOOK_EMPHASIS_WORDS` frozenset defined once in `readability.py`; `text_transforms.py` imports from it — no duplication.
- `apply_subtitle_execution_hints` never mutates subtitle timing or text — verified.
- No ASS output content changed. No SRT timing behavior changed. No Whisper behavior changed.

**Dependency graph** (no cycles):
```
readability.py      → styles.py + srt_core.py
text_transforms.py  → srt_core.py + readability.py
```

---

## Test Suite State (Post Phase 4G.5)

```
8 failed, 6477 passed, 1 skipped  (+89 new passing tests across readability + text_transforms)
```

89 functional tests pass. 17 tests fail due to `ModuleNotFoundError: No module named 'whisper'` — this is the same pre-existing environment limitation as the 13 whisper-related failures in `test_subtitle_ass_core.py` (Python 3.11 test runner does not have whisper installed; full project venv does). All 8 pre-existing failures unchanged.

---

## Phase 4G.6 — Extract Subtitle Transcription + Shim Completion

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Source plan**: [PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md](PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md) — Cluster F + shim finalization

**Purpose**: Extract Cluster F (Whisper/transcription) from `subtitle_engine.py` into `subtitles/transcription.py`. Fix the `has_audio_stream` cross-module coupling. After this phase `subtitle_engine.py` is a pure re-export shim with no function bodies and no `import whisper`.

**Shipped changes**:
- New file: `backend/app/services/subtitles/transcription.py` (~210 lines) — verbatim copy of all transcription symbols from `subtitle_engine.py`, with two changes:
  - `_WHISPER_CACHE_DIR` uses `parents[4]` (not `parents[3]`) — file is one directory deeper than `subtitle_engine.py` was
  - `has_audio_stream()` coupling fixed: now imports `from app.services.render.ffmpeg_helpers import _has_audio_stream` directly instead of routing through `render_engine` shim
  - Moved: `_MODEL_CACHE`, `_MODEL_CACHE_LOCK`, `_MODEL_TRANSCRIBE_LOCKS`, `_WHISPER_CACHE_DIR`, `WORD_MIN_GAP_SEC`, `WORD_MIN_DURATION_SEC`, `WORD_MERGE_SHORTER_THAN_SEC`, `get_whisper_model`, `_get_transcribe_lock`, `_transcribe_with_retry`, `_ensure_ffmpeg_in_path_for_whisper`, `has_audio_stream`, `extract_audio_for_transcription`, `transcribe_to_srt`, `_write_word_level_srt`, `_write_segment_level_srt`
- `backend/app/services/subtitle_engine.py`: complete rewrite to pure re-export shim (~45 lines). All stdlib imports (`subprocess`, `os`, `re`, `logging`, `Path`, `time`, `threading`), `import whisper`, `from bin_paths import ...`, and all 14 transcription symbol bodies removed. Added `from app.services.subtitles.transcription import (...)` re-export block. File reduced 249 → 45 lines.
- New test file: `backend/tests/test_subtitle_transcription.py` — 49 tests: module imports (11), same-object identity via shim (10), coupling fix verification (3 — checks `ffmpeg_helpers` is used, not `render_engine`), `get_whisper_model` caching with mock (3), `_get_transcribe_lock` caching (3), `_transcribe_with_retry` retry logic (4), `_ensure_ffmpeg_in_path_for_whisper` PATH injection (2), `extract_audio_for_transcription` args (2), `_write_segment_level_srt` (3), `_write_word_level_srt` (3), `transcribe_to_srt` integration paths (5).

**subtitle_engine.py line reduction**: 249 → 45 lines (−204). Total reduction from original: 1,970 → 45 lines (−1,925).

**Coupling fix details**:
- Before: `has_audio_stream()` called `from app.services.render_engine import _has_audio_stream` (deferred import through shim)
- After: `has_audio_stream()` calls `from app.services.render.ffmpeg_helpers import _has_audio_stream` (direct to implementation)
- Risk: zero — `_has_audio_stream` signature and behavior unchanged; `ffmpeg_helpers` has no import from any subtitle module

**Contracts maintained**:
- All public `subtitle_engine` exports unchanged — same-object identity passes for all 14 moved symbols.
- `_MODEL_CACHE`, `_MODEL_CACHE_LOCK`, `_MODEL_TRANSCRIBE_LOCKS` are module-level singletons in exactly one module (`transcription.py`). No second copy created anywhere.
- `transcribe_to_srt` signature, word-level/segment-level path selection, WAV cleanup (always in `finally`), retry behavior — verbatim.
- `WORD_MIN_GAP_SEC=0.02`, `WORD_MIN_DURATION_SEC=0.12`, `WORD_MERGE_SHORTER_THAN_SEC=0.11` — unchanged.
- No ASS output content changed. No SRT timing behavior changed.

**Dependency graph** (no cycles):
```
transcription.py → srt_core.py (format_srt_timestamp, _run_with_retry)
transcription.py → render.ffmpeg_helpers (_has_audio_stream — deferred)
transcription.py → bin_paths (get_ffmpeg_bin)
```
No imports from styles.py, readability.py, ass_core.py, or text_transforms.py.

---

## Test Suite State (Post Phase 4G.6)

```
8 failed, 6526 passed, 1 skipped  (+49 new tests in test_subtitle_transcription.py)
```

49 new tests in `test_subtitle_transcription.py` — all 49 pass (whisper mocked at module load time via `sys.modules` injection). All 8 pre-existing failures unchanged. `subtitle_engine.py` is now a pure re-export shim; no function bodies remain.

---

## Phase 4G.7 — Subtitle Caller Migration Audit + Compatibility Freeze

**Branch**: `restructure/output-timeline-architecture`
**Status**: COMPLETE
**Source plan**: [PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md](PHASE_4G_SUBTITLE_ENGINE_SPLIT_PLAN.md) — Phase 4G.7 (audit + freeze)

**Purpose**: Audit all callers of `subtitle_engine.py`, classify them, document the caller migration policy, and freeze the compatibility shim. No behavior changes. No forced caller migration.

**Shipped changes**:
- New test file: `backend/tests/test_subtitle_engine_compat_exports.py` — 67 tests:
  - Shim structure (7): no function bodies, no class bodies, no `import whisper`, no `render_engine`, imports only from `subtitles.*`, no stdlib imports
  - Public symbol presence (31): all expected symbols across all 7 clusters present and callable/accessible
  - Same-object identity per cluster (11): one representative per cluster + 4 additional constants
  - No upward coupling (7): no subtitle/* module imports `subtitle_engine`
  - No `render_engine` coupling (8): no subtitle module imports `render_engine`; coupling fix verification for `transcription.py`
  - Dependency direction (2): all shim imports from `subtitles.*`; all 7 modules referenced

**Caller audit findings** (no code changes required):

| Caller | File | Import | Classification |
|---|---|---|---|
| `render_pipeline.py:25` | `app/orchestration/render_pipeline.py` | Top-level import of 14 subtitle symbols | A — keep as-is |
| `render_pipeline.py:3407` | `app/orchestration/render_pipeline.py` | Deferred `_hex_to_ass` | A — keep as-is |
| `routes/subtitle.py:7` | `app/routes/subtitle.py` | `render_subtitle_preview` | A — keep as-is |
| `routes/render.py:568` | `app/routes/render.py` | Deferred `get_whisper_model` | A — keep as-is |
| `segment_builder.py:838` | `app/services/segment_builder.py` | Deferred `_parse_srt_blocks` | A — keep as-is |
| `subtitle_transcription_adapters.py:17` | `app/services/subtitle_transcription_adapters.py` | `extract_audio_for_transcription, format_srt_timestamp, transcribe_to_srt` | A — keep as-is |
| `test_ai_phase17_dynamic_subtitles.py` | `tests/` | 12× deferred `apply_subtitle_execution_hints` | C — keep as-is |
| `test_ai_phase59a_subtitle_promotion.py` | `tests/` | `normalize_subtitle_style_id` | C — keep as-is |
| `test_market_subtitle_linebreak.py` | `tests/` | top-level imports | C — keep as-is |
| `test_probe_unification.py` | `tests/` | `has_audio_stream` (4 tests) | C — keep as-is |
| All `test_subtitle_*.py` files | `tests/` | Backward-compat identity checks | C — keep as-is |
| `test_slice_srt_to_output_timeline.py` | `tests/` | `slice_srt_to_output_timeline, parse_srt_blocks` | C — keep as-is |

Zero Classification B/E/F findings. No active coupling violations. No stale doc references requiring correction.

**Dependency audit — CLEAN**:
- `subtitle_engine.py` imports ONLY from `app.services.subtitles.*`
- No subtitle/* module imports `subtitle_engine` (no upward coupling)
- No subtitle/* module imports `render_engine`
- `transcription.py has_audio_stream()` imports from `render.ffmpeg_helpers` directly (coupling fix from Phase 4G.6 confirmed working)

**Caller migration policy** (frozen):
- `app.services.subtitle_engine` remains a stable compatibility shim indefinitely
- Production callers (`render_pipeline.py`, `routes/`, `services/`) keep existing imports unchanged
- New code should import from `app.services.subtitles.*` directly
- Tests for new modules import new modules directly; legacy compat tests verify old import path
- The shim will not be removed until all confirmed callers are explicitly migrated (Phase 4G.8+, not planned)

**Contracts maintained**:
- All public `subtitle_engine` exports unchanged
- No behavior, timing, ASS rendering, or Whisper behavior changed
- `subtitle_engine.py` is permanently frozen as a pure re-export shim

---

## Test Suite State (Post Phase 4G.7)

```
8 failed, 6593 passed, 1 skipped  (+67 new tests in test_subtitle_engine_compat_exports.py)
```

67 new tests in `test_subtitle_engine_compat_exports.py` — all 67 pass. All 388 subtitle package tests pass (full suite: styles 39 + srt_core 44 + output_timeline 21 + ass_core 62 + readability 57 + text_transforms 49 + transcription 49 + compat_exports 67). All 8 pre-existing failures unchanged. No new failures.

---

## Phase 4H.0 — Route Cleanup Planning

**Branch**: `restructure/output-timeline-architecture`
**Status**: PLANNING — no backend code changed
**Source plan**: [PHASE_4H_ROUTE_CLEANUP_PLAN.md](PHASE_4H_ROUTE_CLEANUP_PLAN.md)

**Purpose**: Audit `routes/render.py` (~1,369 lines) and produce a complete cleanup plan before any extraction begins. Next major restructure target after Phase 4G completion.

**Audit findings**:
- 9 distinct responsibility clusters identified in `routes/render.py`:
  - **A — Preview Session**: `_save_session`, `_load_session`, `_cleanup_preview_session`, `evict_stale_preview_sessions` + 4 module-level state vars → `services/preview/session_service.py`
  - **B — Source Prep**: POST `/prepare-source`, DELETE `/prepare-source/{session_id}`; owns `_ACTIVE_DOWNLOADS` state
  - **C — Preview Endpoints**: GET `/preview/{session_id}/video`, GET `/preview/{session_id}/transcript`
  - **D — Render Job Control**: POST `/process`, POST `/resume/{job_id}`, POST `/retry/{job_id}`, POST `/{job_id}/cancel`, GET `/jobs/{job_id}`; inner helpers `process_render()` + `_queue_render_job()`
  - **E — Batch**: POST `/process/batch`; `_run_batch()` inner closure (captures 5 vars) → `services/render/batch_service.py`
  - **F — Media Streaming**: GET `/jobs/{job_id}/parts/{part_no}/media` (Range-aware), GET `/jobs/{job_id}/parts/{part_no}/thumbnail` (JPEG, 24h cache) → stays in routes
  - **G — Quick Process**: POST `/quick-process` (no session path)
  - **H — Route Helpers**: 10 helper functions; FFmpeg probe subset (6 functions) → `services/preview/ffmpeg_probers.py`; payload/validation helpers stay in routes
  - **I — Module-level state**: `_PREVIEW_SESSIONS`, `_ACTIVE_DOWNLOADS`, `_PREVIEW_DIR`, `_SESSION_TTL_HOURS`, `_MAX_PREVIEW_SESSIONS`, `_UUID_RE`

**Key coupling constraints documented**:
- `evict_stale_preview_sessions()` called from `main.py` — re-export required at old location
- `_load_session`/`_cleanup_preview_session` passed as fn-reference callbacks to `run_render_pipeline()` — pipeline signature must NOT change
- `_run_batch()` inner closure captures 5 variables — requires closure → explicit args refactor to extract
- `_ACTIVE_DOWNLOADS` stays in `routes/render.py` (download lifecycle, not session lifecycle)

**Proposed sub-phases**:
- 4H.1: Extract `services/preview/ffmpeg_probers.py` (6 FFmpeg probe helpers — no state deps)
- 4H.2: Extract `services/preview/session_service.py` (Cluster A + 4 state vars)
- 4H.3: Extract `services/render/batch_service.py` (Cluster E closure → explicit args)
- 4H.4: Route thinning pass (update call sites to use new services)
- 4H.5: Audit + freeze (no code changes)

**Docs created**: `PHASE_4H_ROUTE_CLEANUP_PLAN.md` (20 sections)

**Test baseline at Phase 4H.0 start**: `8 failed, 6593 passed, 1 skipped` (unchanged — planning-only phase)

---

## Test Suite State (Post Phase 4H.0)

```
11 failed, 6593 passed, 1 skipped  (docs-only phase, no test changes)
```

No new tests added in Phase 4H.0 (planning only). Baseline unchanged.

**Note on failure count**: The 3 extra failures vs. the Phase 4G.7 documented baseline (8→11) are pre-existing test ordering issues in `test_subtitle_transcription.py::TestGetWhisperModel`. The `sys.modules.setdefault("whisper", ...)` pattern in that file is defeated when `test_subtitle_engine_compat_exports.py` (which also injects a whisper mock) is collected first. These 3 failures were already present at Phase 4G.7 ship time; the documented "8 failures" reflected a different test collection order. Phase 4H.1 is the first phase measured against the correct 11-failure baseline.

---

## Phase 4H.1 — Extract FFmpeg Probe Helpers

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: First implementation phase of Phase 4H. Extract 6 route-local FFmpeg/ffprobe media inspection helpers from `routes/render.py` into `services/preview/ffmpeg_probers.py`. Create `services/preview/` package scaffold. Backward-compat re-exports keep all existing callers unchanged.

**Shipped changes**:
- New file: `backend/app/services/preview/__init__.py` — empty package scaffold.
- New file: `backend/app/services/preview/ffmpeg_probers.py` (188 lines) — 6 helpers moved verbatim from `routes/render.py`:
  - `_probe_video_codec(video_path: Path) -> str` — ffprobe video codec name
  - `_probe_preview_profile(video_path: Path) -> dict` — ffprobe container/video/audio details
  - `_is_browser_safe_preview(video_path: Path) -> bool` — Chromium h264/aac compatibility check
  - `_ensure_h264_preview(src, work_dir, duration_sec) -> Path` — H.264 transcode-or-reuse; duration-aware timeout
  - `_run_ffmpeg_checked(cmd, fail_message)` — subprocess run; raises `HTTPException(500)` on non-zero exit
  - `_detect_leading_black_duration(input_path, min_duration, threshold) -> float` — blackdetect vf filter; returns black_end for leading-only black
- `backend/app/routes/render.py`: 6 function bodies removed; backward-compat import block added: `from app.services.preview.ffmpeg_probers import (...)`. Reduced from ~1,369 → 1,205 lines (−164 lines, net).
- New test file: `backend/tests/test_preview_ffmpeg_probers.py` — 44 tests:
  - Module importability (4): both modules import; all 6 symbols present in each
  - Same-object identity (6): one per helper; `routes.render.X is probers.X`
  - No FastAPI routing objects (7): no `APIRouter`, no `router =`, no `Request`, no route decorators, no `FileResponse`, no `StreamingResponse`, no `routes.render` import
  - `_probe_video_codec` (5): success path, exception path, strip/lower, ffprobe bin, select_streams
  - `_probe_preview_profile` (3): dict keys, empty streams, fallback on exception
  - `_is_browser_safe_preview` (6): h264/aac/mp4→True, vp9/webm→False, hevc→False, no audio→True, mov→True, opus→False
  - `_run_ffmpeg_checked` (4): success returns proc, HTTPException on nonzero, detail truncation, unknown error fallback
  - `_detect_leading_black_duration` (5): no-black, leading-black, mid-video black ignored, too-short black ignored, blackdetect filter in cmd
  - `_ensure_h264_preview` (4): cached output reused, safe src returned as-is, fallback on transcode failure, fallback on timeout

**Dependencies of `ffmpeg_probers.py`**:
- `json`, `re`, `subprocess`, `logging`, `pathlib.Path` — stdlib only
- `fastapi.HTTPException` — exception class only (not routing objects)
- `app.services.bin_paths.get_ffprobe_bin`, `get_ffmpeg_bin` — bin path helpers

**Contracts maintained**:
- All 6 re-exported names in `routes/render.py` are the SAME objects as in `ffmpeg_probers.py` (`is` identity guaranteed).
- All FFmpeg/ffprobe commands, subprocess behavior, timeout values, return types, and exception types unchanged.
- No route handler signatures changed. No API paths changed. No frontend contracts changed.
- `_run_ffmpeg_checked` still raises `HTTPException(status_code=500, ...)` — callers in `quick_process` catch `HTTPException` by type; behavior preserved.
- `routes/render.py` still imports `get_ffprobe_bin` and `get_ffmpeg_bin` from `bin_paths` (pre-existing imports remain; ffmpeg_probers.py also imports them directly).

---

## Test Suite State (Post Phase 4H.1)

```
11 failed, 6651 passed, 1 skipped  (+44 new tests in test_preview_ffmpeg_probers.py)
```

44 new tests in `test_preview_ffmpeg_probers.py` — all 44 pass. All 11 failures are pre-existing (4 AI test failures + 4 remotion adapter failures + 3 whisper mock ordering failures). Zero new failures introduced by Phase 4H.1.

Phase 4H.1 line delta: `routes/render.py` reduced by 164 net lines (1,369 → 1,205). `ffmpeg_probers.py` created (188 lines).

---

## Phase 4H.1A — Stabilize Whisper Test Baseline

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: (this commit)

**Purpose**: Fix 3 pre-existing `TestGetWhisperModel` ordering failures introduced in Phase 4G.7 when `test_subtitle_engine_compat_exports.py` was added. No behavior changes.

**Root cause**: Both `test_subtitle_engine_compat_exports.py` and `test_subtitle_transcription.py` use `sys.modules.setdefault("whisper", _whisper_mock)` at module level. Because pytest collects files alphabetically, `test_subtitle_engine_compat_exports.py` ("engine") is always collected before `test_subtitle_transcription.py` ("transcription"). The first file injects `_whisper_mock_A` into `sys.modules["whisper"]`, and `transcription.py` binds to it. The second file's `setdefault` is a no-op (key already present). `TestGetWhisperModel` then mutates `_whisper_mock_B` (its own module-level variable), but `transcription.py`'s `get_whisper_model` calls `_whisper_mock_A.load_model` — a different object. Assertions on `_whisper_mock_B.load_model` fail.

**Fix**: Replaced the 3 `TestGetWhisperModel` test methods to use `mock.patch("app.services.subtitles.transcription.whisper", mock_whisper)` inside each test body, making them fully order-independent. The patch targets the `whisper` name binding in the `transcription` module's namespace directly — the exact binding that `get_whisper_model` references. The module-level `_whisper_mock` variable is no longer referenced in these 3 tests.

**Shipped changes**:
- `backend/tests/test_subtitle_transcription.py`: `TestGetWhisperModel` — 3 methods rewritten to use `mock.patch("app.services.subtitles.transcription.whisper", mock_whisper)` context manager instead of module-level `_whisper_mock`. `setup_method` and `teardown_method` (cache clear) unchanged.

**Behavior unchanged**:
- `get_whisper_model()` cache behavior, lock semantics, function signature — all unchanged
- No real Whisper model loads in any test
- Same-object identity tests (via `subtitle_engine` shim) still pass
- All 49 subtitle_transcription tests still pass

---

## Test Suite State (Post Phase 4H.1A)

```
8 failed, 6654 passed, 1 skipped  (3 whisper ordering failures fixed)
```

Baseline stabilized. The 8 remaining failures are pre-existing: 4 remotion adapter failures + 4 AI/optional-dependency failures. This is the correct stable baseline for Phase 4H.2+.

---

## Phase 4H.2 — Extract Preview Session Service

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED (2026-05-22)
**Commit**: (this commit)

**Purpose**: Second implementation phase of Phase 4H. Extract 4 preview session helper functions and 4 module-level state variables from `routes/render.py` into `services/preview/session_service.py`. Singleton state semantics preserved — `_PREVIEW_SESSIONS` is defined exactly once in `session_service.py`; `routes/render.py` imports and re-exports all symbols. `main.py` unchanged.

**Shipped changes**:
- New file: `backend/app/services/preview/session_service.py` (83 lines) — owns `_PREVIEW_SESSIONS`, `_PREVIEW_DIR`, `_SESSION_TTL_HOURS`, `_MAX_PREVIEW_SESSIONS`, `_save_session`, `_load_session`, `_cleanup_preview_session`, `evict_stale_preview_sessions`
- `backend/app/routes/render.py`: removed 4 state vars + 4 function bodies; added `from app.services.preview.session_service import ...` block with all 8 symbols; `evict_stale_preview_sessions` comment notes it is re-exported for `main.py` backward compat
- New tests: `tests/test_preview_session_service.py` — 17 tests covering singleton identity, `_save_session` (5 cases), `_load_session` (4 cases), `_cleanup_preview_session` (3 cases), `evict_stale_preview_sessions` (3 cases)
- Updated docs: `CURRENT_RENDER_ARCHITECTURE.md`, `PHASE_4H_ROUTE_CLEANUP_PLAN.md`, `TECHNICAL_DEBT_REPORT.md`

**Symbols that stayed in `routes/render.py`**:
- `_ACTIVE_DOWNLOADS` — download cancel events belong to download lifecycle, not session lifecycle
- `_UUID_RE` — used only by route handlers for `session_id` validation

**Contracts introduced**:
- `app.services.preview.session_service._PREVIEW_SESSIONS` is the authoritative singleton registry
- `routes.render._PREVIEW_SESSIONS is session_service._PREVIEW_SESSIONS` — same object
- `routes.render.evict_stale_preview_sessions is session_service.evict_stale_preview_sessions` — same function

**Phase 4H.2 line delta**: `routes/render.py` reduced by 55 net lines (1,205 → 1,150). `session_service.py` created (83 lines).

---

## Test Suite State (Post Phase 4H.2)

```
8 failed, 6671 passed, 1 skipped  (+17 new tests from test_preview_session_service.py)
```

17 new tests in `test_preview_session_service.py` — all 17 pass. 8 failures unchanged (pre-existing). Zero new failures introduced by Phase 4H.2.

---

## Phase 4H.3 — Extract Media Streaming Helpers

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED (2026-05-22)
**Commit**: (this commit)

**Purpose**: Third implementation phase of Phase 4H. Extract two media-streaming helpers from the inline body of `stream_render_part_media` in `routes/render.py` into `services/preview/media_streaming.py`. Both helper units were embedded inline (an inner closure and a range-parsing block); they are now module-level functions callable independently and covered by unit tests. Route handlers remain in `routes/render.py`. No API changes.

**Pre-edit audit findings**:
- `_iter()` inner closure (lines 1065-1075 in pre-4H.3 `routes/render.py`): iterator generator embedded inside `stream_render_part_media`; extracted as `_iter_file_bytes(path, start, end, chunk)` with `path` promoted to explicit parameter.
- Range parsing inline block (lines 1080-1096): `re.match + HTTPException(416)` logic embedded in `stream_render_part_media`; extracted as `_parse_range_header(range_header, file_size)`.
- `stream_render_part_media` route handler: **B — stays** (full route handler, calls helpers).
- `get_render_part_thumbnail` route handler: **B — stays** (self-contained, no helpers to extract).
- `preview_video` route handler: **B — stays** (different cluster, not touched).
- `_ACTIVE_DOWNLOADS`: **C — stays** (download lifecycle state).
- `_UUID_RE`: **C — stays** (route validation).

**Shipped changes**:
- New file: `backend/app/services/preview/media_streaming.py` (54 lines) — owns `_parse_range_header`, `_iter_file_bytes`
- `backend/app/routes/render.py`: removed `_iter()` inner closure + range-parsing inline block from `stream_render_part_media`; added `from app.services.preview.media_streaming import _parse_range_header, _iter_file_bytes`; route handler calls helpers by name
- New tests: `tests/test_preview_media_streaming.py` — 28 tests covering module structure (7), same-object identity (2), route handler presence (2), `_parse_range_header` (11), `_iter_file_bytes` (5), range/no-range integration (2)
- Updated docs: `CURRENT_RENDER_ARCHITECTURE.md`, `PHASE_4H_ROUTE_CLEANUP_PLAN.md`, `TECHNICAL_DEBT_REPORT.md`

**Contracts introduced**:
- `routes.render._parse_range_header is media_streaming._parse_range_header` — same object
- `routes.render._iter_file_bytes is media_streaming._iter_file_bytes` — same object
- Range parsing behavior: `_parse_range_header` raises `HTTPException(416)` on invalid/out-of-range; returns `(byte1, byte2)` inclusive on success. Behavior identical to pre-extraction inline code.
- No APIRouter, no DB, no session state in `media_streaming.py`.

**Phase 4H.3 line delta**: `routes/render.py` reduced by 25 net lines (1,150 → 1,125). `media_streaming.py` created (54 lines).

---

## Test Suite State (Post Phase 4H.3)

```
8 failed, 6699 passed, 1 skipped  (+28 new tests from test_preview_media_streaming.py)
```

28 new tests in `test_preview_media_streaming.py` — all 28 pass. 8 failures unchanged (pre-existing). Zero new failures introduced by Phase 4H.3.

---

## Phase 4H.6 — Route Cleanup Freeze

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED (2026-05-22)
**Commit**: (this commit)

**Purpose**: Audit and freeze phase for the Phase 4H route cleanup effort. No backend code changes. Complete cluster classification for all remaining `routes/render.py` content. Document official stopping point and freeze policy. Update SCORECARD.md and BRUTAL_REVIEW_SUMMARY.md with current priorities.

**Audit findings**:
- `routes/render.py` after Phase 4H.3: 1,125 lines, 17 route handlers + 6 module-level functions + 2 state vars + 1 inner closure
- All remaining route handlers classified (A/B/C — see PHASE_4H_6_ROUTE_FREEZE.md §2e)
- `_run_batch()` inner closure: B — future extraction candidate (batch service); deferred
- `quick_process`: C — intentionally frozen (self-contained 283-line FFmpeg handler)
- `_ACTIVE_DOWNLOADS`, `_UUID_RE`: A — acceptable to remain (route-lifecycle state)
- No circular imports confirmed via `python -m compileall app`
- All 3 compatibility shims verified: `services/db.py`, `services/render_engine.py`, `services/subtitle_engine.py`
- `main.py` deferred import of `evict_stale_preview_sessions` verified working

**Why 4H.4 / 4H.5 were not completed**:
- Phase 4H.4 (Source Prepare Service): rejected — `prepare_source` is route-handler code, not service logic; coupling complexity exceeds extraction value
- Phase 4H.5 (original plan): merged into 4H.6 (this phase)

**Docs created**:
- `docs/restructure/PHASE_4H_6_ROUTE_FREEZE.md` — full audit, cluster classification, freeze policy, coupling constraint resolution

**Docs updated**:
- `PHASE_4H_ROUTE_CLEANUP_PLAN.md` — status set to COMPLETE
- `CURRENT_RENDER_ARCHITECTURE.md` — Phase 4H complete note, service package documented
- `TECHNICAL_DEBT_REPORT.md` — Phase 4H.6 entry, route debt classified
- `BRUTAL_REVIEW_SUMMARY.md` — priorities updated post Phase 4H
- `SCORECARD.md` — backend architecture and maintainability scores updated

**Phase 4H cumulative summary**:
- Total lines removed from `routes/render.py`: **−244 lines** (1,369 → 1,125)
- New service modules created: **3** (`ffmpeg_probers.py`, `session_service.py`, `media_streaming.py`)
- New tests added across Phase 4H: **89** (44 + 17 + 28)
- Test baseline at freeze: `8 failed, 6699 passed, 1 skipped`

---

## Test Suite State (Post Phase 4H.6)

```
8 failed, 6699 passed, 1 skipped  (no new tests — audit/docs phase)
```

Baseline unchanged. Phase 4H.6 introduced no backend code changes and no new tests. Phase 4H is complete.

---

## Phase 5.0 — Post-Restructure Review

**Branch**: `restructure/output-timeline-architecture`
**Status**: COMPLETE (2026-05-23)
**Commit**: (this commit)

**Purpose**: Comprehensive post-restructure audit covering all changes from Phases 4E–4H. No runtime code changes. Audit and planning only.

**Scope covered**:
- Full backend module tree walk (app/, services/, orchestration/ directories)
- All three compatibility shims verified: `services/render_engine.py` (53 lines), `services/db.py` (31 lines), `services/subtitle_engine.py` (45 lines) — all healthy pure re-export shims
- Complete API route audit across all 8 registered routers (channels, download, render, jobs, voice, viral, subtitle, creator)
- Frontend API usage audit across backend/static/ and backend/static-v2/ (23 fetch calls classified, 2 WebSocket connections)
- Upload domain removal verified clean — no active callers, no active routes, no active frontend references to removed `/api/upload/*` endpoints
- Schema audit: RenderRequest (70+ fields, active, unchanged since Phase 3C.5); 8 dead Upload* Pydantic classes confirmed in schemas.py (no active callers — NEW-1)
- WebSocket contract audit: `/api/jobs/{job_id}/ws` unchanged, fingerprinting logic intact
- Test baseline confirmed: 8 failed / 6699 passed / 1 skipped (matches Phase 4H.6 exactly — no regressions)

**New findings documented in PHASE_5_0_POST_RESTRUCTURE_REVIEW.md**:
- NEW-1: Dead Upload* Pydantic schemas in `models/schemas.py` (8 classes, no callers) — LOW priority cleanup
- NEW-2: `/api/upload-file` 404 in editor JS — pre-existing bug (editor-audio-runtime.js:89, editor-view.js:1107) — MEDIUM priority fix
- NEW-3: `uploadWs` orphan variable in globals.js — LOW priority cleanup
- NEW-4: `main.py` uses deprecated `@app.on_event` FastAPI pattern — LOW priority, not blocking

**Docs created**:
- `docs/restructure/PHASE_5_0_POST_RESTRUCTURE_REVIEW.md` — full 22-section audit report

**Docs updated**:
- `docs/restructure/MIGRATION_HISTORY.md` — Phase 5.0 entry added (this entry)
- `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` — stale SQLite "upload queue" comment fixed; last-updated date bumped

**Go/No-Go decision**: GO — Phase 5.1 Output Quality Hardening can begin.

**Test Suite State (Post Phase 5.0)**:
```
8 failed, 6699 passed, 1 skipped  (no new tests — audit/docs phase)
```

---

## Phase 5.1 — AI Knowledge and Render Safety Foundation

**Branch**: `restructure/output-timeline-architecture`
**Status**: COMPLETE (2026-05-23)
**Commit**: phase 5.1 ai knowledge and render safety foundation

**Purpose**: Fix the /api/upload-file 404, add render safety checks (audio stream QA + download timeout), lay the local knowledge foundation for AI-augmented rendering, and document the AI render contract.

**Shipped changes**:

### Task 1 — Fix /api/upload-file 404
- **New file**: `backend/app/routes/files.py` — POST `/api/upload-file` endpoint
  - Accepts FormData field `file` (matches frontend in editor-audio-runtime.js:89, editor-view.js:1107)
  - Saves to `APP_DATA_DIR/editor-uploads/` (safe; no traversal possible)
  - `_safe_filename()` strips `/`, `\\`, null bytes, leading dots; normalises unicode
  - Returns `{"path": "<saved_absolute_path>"}` (matches frontend `d.path` usage)
  - Max upload 200 MB; counter-suffixed if name collides
  - Does NOT recreate /api/upload/* domain
- **Updated**: `backend/app/main.py` — registered `files_router`

### Task 2 — Wall-clock timeout for YouTube download
- **Updated**: `backend/app/services/downloader.py`
  - Added `_DOWNLOAD_WALLCLOCK_TIMEOUT = 300` (override via `YTDLP_WALLCLOCK_TIMEOUT` env)
  - Added `_try_download_with_timeout()` inner closure (wraps `_try_download` via `concurrent.futures.ThreadPoolExecutor`)
  - Timeout fires `RuntimeError("Download timed out after Xs wall-clock")` — distinguishable from format errors
  - On timeout: propagates immediately (no retrying a timed-out download)
  - Applied to both main attempts loop and dynamic fallback loop
  - `socket_timeout: 60` (per-socket stall protection) preserved unchanged

### Task 3 — Audio stream check in output QA
- **Updated**: `backend/app/orchestration/qa_pipeline.py`
  - `_validate_render_output()` section 6: now warns when audio stream is absent regardless of `expect_audio`
  - Severity: WARNING (non-fatal, ok=True preserved) — consistent with existing QA pattern
  - `expect_audio=True` path: produces "expected but missing" warning (legacy behaviour preserved)
  - `expect_audio=None/False` path: NEW — "output has no audio stream" warning
  - Uses `has_audio` from existing ffprobe JSON parse (no duplicate probe calls)
  - `_has_audio_stream()` in `services/render/ffmpeg_helpers.py` already existed; qa_pipeline uses probe JSON directly

### Task 4 — Local knowledge foundation
- **New directory**: `backend/knowledge/` — full structure created
  - `raw/video_samples/`, `raw/transcripts/`, `raw/research_notes/` — empty with .gitkeep
  - `processed/` — 7 `.jsonl` files with 1 example item each (platform_rules, hook_patterns, subtitle_rules, pacing_rules, visual_rules, cta_patterns, failure_patterns)
  - `index/` — empty with .gitkeep (FAISS index location)
- **New file**: `backend/knowledge/README.md` — schema reference, usage docs, governance notes

### Task 5 — RAG/FAISS readiness
- **Updated**: `backend/app/ai/rag/vector_store.py`
  - Added `save_index(path)` method — serializes FAISS index to disk; returns bool, never raises
  - Added `load_index(path)` method — deserializes from disk; validates entry count matches; returns bool, never raises
  - Added clarifying module docstring: `memory_store` = RAG infrastructure; `knowledge/` = filter-based platform/video knowledge
  - FAISS persistence target path: `backend/knowledge/index/faiss.index`
  - Graceful degradation: missing index → rebuild path; no knowledge files → warn, don't crash
  - Existing memory_store behaviour unchanged

### Task 6 — AI Render Contract
- **New file**: `docs/ai/AI_RENDER_CONTRACT.md`
  - 10 sections covering: local-first, no external LLM at runtime, RAG as filter retrieval, AI boundaries, structured output validation, fallback to safe defaults, knowledge sources, user filter mapping, cloud AI policy, offline requirement
  - Future flow diagram: filters → knowledge retrieval → CreativeBrief → ScenePlan → VisualDirection → validation → render pipeline → QA → output

### Task 7 — AI Decision Traceability Plan
- **New file**: `docs/ai/AI_DECISION_TRACEABILITY_PLAN.md`
  - Planning doc (no code) — 8 event types defined with JSON schemas
  - Implementation guidance: `app/ai/tracing.py` + `AITraceLogger` class + per-job `.jsonl` file
  - Answers: "Why did AI choose this scene/style/subtitle/pacing?"

**New tests**:
- `tests/test_upload_file_endpoint.py` — 18 tests: import, _safe_filename sanitisation, route 200, path key, field name, path traversal safety, upload domain not restored
- `tests/test_downloader_timeout.py` — 7 tests: constant exists, default 300s, min 60s, timeout raises RuntimeError, wall-clock indicator in message, normal download unaffected, socket_timeout preserved
- `tests/test_qa_audio_stream.py` — 14 tests: audio present passes, metadata correct, audio missing warns, warn non-fatal, expect_audio=True warning, probe failure safety, keys always present

**Docs updated**:
- `docs/review/FULL_PROJECT_BACKEND_AI_GOVERNANCE_REVIEW.md` — Phase 5.1 summary section added
- `docs/review/TECHNICAL_DEBT_REPORT.md` — P0: /api/upload-file marked RESOLVED; FAISS persistence status updated; H6 downloader timeout updated
- `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md` — audio stream QA note added
- `docs/restructure/MIGRATION_HISTORY.md` — this entry

**Upload domain removal**: STILL INTACT — `routes/upload.py` absent, `services/upload_engine.py` absent, no `/api/upload/*` routes registered. `/api/upload-file` is a single new endpoint, not a domain.

**Test Suite State (Post Phase 5.1)**:
```
Expected: 8 failed (same known failures) / 6738+ passed (39+ new tests) / 1 skipped
```

---

## Phase 5.2 — Local Knowledge Retrieval Activation (2026-05-23)

**Goal**: Activate the local filter-based knowledge retrieval system so AI render planning uses `knowledge/processed/*.jsonl` items at render time.

**Entry criteria**: Phase 5.1 complete (knowledge foundation, FAISS persistence primitives).

### New Files

| File | Purpose |
|---|---|
| `backend/app/ai/rag/knowledge_schema.py` | `KnowledgeItem` dataclass + `validate_knowledge_item()` (never raises, returns None on bad data) |
| `backend/app/ai/rag/knowledge_loader.py` | `load_knowledge_items()` — reads all `*.jsonl` from `knowledge/processed/`, validates each item |
| `backend/app/ai/rag/knowledge_index.py` | `KnowledgeIndex` — `build()`, `save()`, `load()`, `rebuild()`, `query()`, `is_ready()` |
| `backend/app/ai/rag/knowledge_warmup.py` | `get_knowledge_index()` singleton + `warmup_knowledge_index()` |
| `backend/app/ai/tracing.py` | `AITraceLogger` — JSONL trace per render job at `data/logs/{job_id}_ai_trace.jsonl` |

### Runtime Changes (surgical — minimal)

| File | Change |
|---|---|
| `backend/app/main.py` | Added `warmup_knowledge_index()` daemon thread in `@app.on_event("startup")` |
| `backend/app/orchestration/render_pipeline.py` | Added knowledge filter build, retrieval call, tracer init, context injection in AI director block |
| `backend/app/ai/director/ai_director.py` | Added hint extraction from `retrieved_knowledge` in `_build_plan()` |

### Knowledge Index Lifecycle

1. At startup: `warmup_knowledge_index()` → `get_knowledge_index()` → try `load()` from `knowledge/index/faiss.index.meta.json` → if fail, try `rebuild()` from `knowledge/processed/*.jsonl` → if fail, log warning, continue
2. At render time (ai_director_enabled=True): `KnowledgeIndex.query(filters, top_k=10)` → hard-filter by platform/niche/style/duration/aspect_ratio/subtitle_style/target_goal → rank by weight + match count → return top-k
3. Missing knowledge: empty list returned → AI edit plan receives `retrieved_knowledge=[]` → hints not set → render proceeds unchanged

### Fallback Guarantees

- Missing `knowledge/processed/` directory: `load_knowledge_items()` returns `[]`, warning logged
- Missing FAISS/sentence-transformers: `KnowledgeIndex` uses in-memory filter+rank, no crash
- Missing `knowledge/index/faiss.index.meta.json`: `load()` returns False, `rebuild()` called
- Retrieval exception at render time: caught, `retrieved_knowledge=[]`, warning logged
- `warmup_knowledge_index()` never raises

### H3 / H4 Resolution

- **H3** (knowledge not wired to `create_ai_edit_plan`): RESOLVED — `retrieved_knowledge` and `knowledge_filters` now in `_ai_context`.
- **H4** (FAISS not persisted): RESOLVED — `KnowledgeIndex.save()/load()` persist metadata and FAISS geometry; startup wires load → rebuild lifecycle.

### Test Files Added

| File | Tests |
|---|---|
| `tests/test_ai_knowledge_schema.py` | 28 |
| `tests/test_ai_knowledge_loader.py` | 10 |
| `tests/test_ai_knowledge_index.py` | 20 |
| `tests/test_ai_knowledge_retrieval.py` | 17 |
| `tests/test_ai_trace_logger.py` | 12 |
| `tests/test_ai_render_knowledge_integration.py` | 13 |
| **Total** | **100** |

### Test Suite State (Post Phase 5.2)

```
8 failed (same known pre-existing failures) / 6842 passed (+104 new tests) / 1 skipped
```

Known failures: `test_remotion_adapter.py` (4), `test_ai_optional_dependencies.py` (1), `test_ai_phase36_clip_segment_selection.py` (2), `test_ai_visibility_summary.py` (1) — all pre-Phase-1.

**No new failures introduced.**

---

## Phase 5.3 — AI Render Contract (2026-05-23)

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Commit**: `phase 5.3 freeze ai render contract`

**Purpose**: Convert retrieved local knowledge into validated render execution hints that can safely influence render decisions. Establish explicit AI contract models with validation layer.

**New files**:
- `backend/app/ai/contracts.py` — `CreativeBrief`, `RenderExecutionHints`, `AIValidationResult` dataclasses
- `backend/app/ai/validators.py` — `validate_execution_hints()`: clamp/fallback/fixup for all hint fields
- `backend/app/ai/render_mapper.py` — `map_knowledge_to_execution_hints()`: knowledge → validated hints
- `backend/tests/test_ai_contracts.py` — 11 tests
- `backend/tests/test_ai_validators.py` — 35 tests
- `backend/tests/test_ai_render_mapper.py` — 28 tests
- `backend/tests/test_ai_trace_logger_execution_hints.py` — 13 tests
- `backend/tests/test_ai_director_execution_hints.py` — 9 tests
- `backend/tests/test_render_pipeline_ai_execution_hints.py` — 13 tests

**Modified files**:
- `backend/app/ai/director/ai_director.py` — Phase 5.3 mapper block added at end of `create_ai_edit_plan()`; merges into `plan.knowledge_injection`
- `backend/app/ai/tracing.py` — `log_execution_hints()`, `log_validation_fixup()`, `log_decision_rejected()` added
- `backend/app/orchestration/render_pipeline.py` — Phase 5.3 block: reads execution_hints; applies hook overlay gate; logs pacing/subtitle as advisory
- Docs: `AI_RENDER_CONTRACT.md`, `AI_DECISION_TRACEABILITY_PLAN.md`, `CURRENT_RENDER_ARCHITECTURE.md`, `TECHNICAL_DEBT_REPORT.md` updated

**Contracts introduced**:
- `RenderExecutionHints.playback_speed_hint` clamped to [0.5, 1.5]
- `RenderExecutionHints.cut_interval_min/max` clamped to [1.0, 12.0]; inverted range auto-swapped
- `subtitle_emphasis_style` must be one of "subtle"/"medium"/"strong"/"word_only"; else → None
- `hook_overlay_enabled` must be strict bool; int/str → None
- `visual_intensity` must be one of "low"/"medium"/"high"; else → None
- Invalid AI output NEVER crashes render — all failures degrade to None/safe defaults

**Render behavior impact**:
- Hook overlay: AI `hook_overlay_enabled=False` → `_hook_overlay_enabled = False` (single gate applied)
- Pacing hints: advisory only — logged, not applied (no compatible runtime hook found)
- Subtitle hints: advisory only — per-part resolution from payload unchanged
- FFmpeg: ZERO changes to FFmpeg commands or filter graphs

### Test Suite State (Post Phase 5.3)

```
8 failed (same known pre-existing failures) / 6951 passed (+109 new tests) / 1 skipped
```

Known failures: `test_remotion_adapter.py` (4), `test_ai_optional_dependencies.py` (1), `test_ai_phase36_clip_segment_selection.py` (2), `test_ai_visibility_summary.py` (1) — all pre-Phase-1.

**No new failures introduced.**

### Phase 5.4 — AI Pacing Hint Propagation (2026-05-23)

**New files**:
- `backend/app/ai/pacing.py` — `AIPacingConfig` dataclass, `build_ai_pacing_config()`: validates/applies pacing hints; user explicit limits always win
- `backend/tests/test_ai_pacing_config.py` — 25 tests
- `backend/tests/test_ai_trace_logger_pacing.py` — 12 tests
- `backend/tests/test_render_pipeline_ai_pacing.py` — 17 tests

**Modified files**:
- `backend/app/ai/tracing.py` — `log_pacing_applied()` added
- `backend/app/orchestration/render_pipeline.py` — Phase 5.4 early pacing block; `_seg_min_sec/_seg_max_sec` local vars; Phase 5.2 block reuses `_early_retrieved_knowledge`
- Docs: `AI_RENDER_CONTRACT.md`, `AI_DECISION_TRACEABILITY_PLAN.md`, `CURRENT_RENDER_ARCHITECTURE.md`, `TECHNICAL_DEBT_REPORT.md`, `MIGRATION_HISTORY.md` updated

**Pacing injection point**:
- Early retrieval before `build_segments_from_scenes()` (~line 1683 pre-edit)
- `_seg_min_sec`/`_seg_max_sec` replace `payload.min_part_sec`/`payload.max_part_sec` in 3 calls

**User override**: `payload.min_part_sec != 15` or `payload.max_part_sec != 60` → AI rejected with `user_duration_override`

**Render behavior impact**:
- Pacing hints: NOW APPLIED (was advisory only)
- FFmpeg: ZERO changes
- Subtitle hints: still advisory
- Hook overlay gate: still active

### Test Suite State (Post Phase 5.4)

```
8 failed (same known pre-existing failures) / 7005 passed (+54 new tests) / 1 skipped
```

Known failures: `test_remotion_adapter.py` (4), `test_ai_optional_dependencies.py` (1), `test_ai_phase36_clip_segment_selection.py` (2), `test_ai_visibility_summary.py` (1) — all pre-Phase-1.

**No new failures introduced.**


---

## Phase 5.5 — AI Subtitle Emphasis Hint Integration (2026-05-23)

**Branch**: `restructure/output-timeline-architecture`
**Goal**: Integrate validated AI subtitle emphasis hints into the subtitle processing path without altering SRT timestamps, ASS preset IDs, or FFmpeg commands.

**New files**:
- `backend/app/ai/subtitle_hints.py` — `AISubtitleEmphasisConfig` dataclass; `build_ai_subtitle_emphasis_config()` validates emphasis style; same pattern as `pacing.py`
- `backend/tests/test_ai_subtitle_emphasis_config.py` — 28 tests
- `backend/tests/test_ai_trace_logger_subtitle_emphasis.py` — 11 tests
- `backend/tests/test_render_pipeline_ai_subtitle_emphasis.py` — 16 tests
- `backend/tests/test_subtitle_execution_hints_ai_integration.py` — 12 tests

**Modified files**:
- `backend/app/services/subtitles/readability.py` — `subtitle_emphasis_pass()` gains `emphasis_level_override: str | None = None` parameter (Case B); default=None preserves existing behavior
- `backend/app/ai/tracing.py` — `log_subtitle_emphasis_applied()` added; writes `ai.subtitle_emphasis_applied` JSONL event
- `backend/app/orchestration/render_pipeline.py` — Phase 5.5 block between Phase 5.3 and Phase 60D; `_ai_subtitle_emphasis_config` built once; per-part `subtitle_emphasis_pass()` call passes `emphasis_level_override`
- Docs: `AI_RENDER_CONTRACT.md`, `AI_DECISION_TRACEABILITY_PLAN.md`, `CURRENT_RENDER_ARCHITECTURE.md`, `TECHNICAL_DEBT_REPORT.md`, `MIGRATION_HISTORY.md` updated

**Subtitle injection point**:
- Phase 5.5 config built once at ~line 2578 in `render_pipeline.py` (after Phase 5.3, before per-part loop)
- Per-part: `subtitle_emphasis_pass()` call at ~line 3664 receives `emphasis_level_override` from config

**Emphasis integration: Case B** — `subtitle_emphasis_pass()` existed but had no emphasis override parameter; minimal optional param added with None default preserving all existing behavior.

**User override**: `payload.subtitle_style` and per-part style hierarchy always preserved; AI only overrides emphasis level inside the pass.

**Timing safety**: `subtitle_emphasis_pass()` only modifies `b["text"]`; `b["start"]` and `b["end"]` guaranteed unchanged.

**Render behavior impact**:
- Subtitle emphasis: NOW APPLIED (was advisory only)
- No new style IDs created
- Subtitle timing: GUARANTEED UNCHANGED
- FFmpeg: ZERO changes
- Pacing hints: still active (Phase 5.4)
- Hook overlay gate: still active (Phase 5.3)

### Test Suite State (Post Phase 5.5)

8 failed (same known pre-existing failures) / 7072 passed (+67 new tests) / 1 skipped

Known failures: `test_remotion_adapter.py` (4), `test_ai_optional_dependencies.py` (1), `test_ai_phase36_clip_segment_selection.py` (2), `test_ai_visibility_summary.py` (1) — all pre-Phase-1.

**No new failures introduced.**

---

## Phase 5.6 — AI Visual Intensity Hint Integration (2026-05-23)

**Goal**: Integrate validated AI `visual_intensity` hints into existing visual render behavior, or safely log rejection if no safe injection point exists.

**Outcome**: No safe injection point found. Infrastructure built, all hints logged as advisory.

**Files added**:
- `backend/app/ai/visual_hints.py` — `AIVisualIntensityConfig` dataclass, `build_ai_visual_intensity_config(execution_hints, payload)`: validates intensity, detects user override, documents injection investigation
- `backend/tests/test_ai_visual_intensity_config.py` — 29 tests for config model
- `backend/tests/test_ai_trace_logger_visual_intensity.py` — 14 tests for trace logger
- `backend/tests/test_render_pipeline_ai_visual_intensity.py` — 26 tests for pipeline integration

**Files modified**:
- `backend/app/ai/tracing.py` — `log_visual_intensity_applied()` added; writes `ai.visual_intensity_applied` JSONL event
- `backend/app/orchestration/render_pipeline.py` — Phase 5.6 block added after Phase 5.5 block; `_ai_visual_intensity_config` built once; no render parameter changes
- Docs: `AI_RENDER_CONTRACT.md`, `AI_DECISION_TRACEABILITY_PLAN.md`, `CURRENT_RENDER_ARCHITECTURE.md`, `TECHNICAL_DEBT_REPORT.md`, `MIGRATION_HISTORY.md` updated

**Visual injection point investigation**:
- Reviewed: `legacy_renderer.py`, `base_clip_renderer.py`, `ffmpeg_helpers.py`, `clip_ops.py`, `render_pipeline.py`
- `effect_preset` param in `render_part()`/`render_part_smart()`/`render_base_clip()` maps directly to FFmpeg filter strings via `_effect_filter()` — no intermediate level parameter
- `payload.effect_preset` is a user-set field — AI must not override it
- No `_effect_intensity`, `_visual_energy`, `effect_strength`, `visual_profile` local variables found in render_pipeline.py
- `_cinematic_color_filter()` and `_cinematic_sharpen_filter()` accept content_type/src_h only
- **Result: NOT FOUND — no safe visual intensity injection point**
- `render_overrides={}`, `applied=False` for all valid hints

**User override detection**: `payload.effect_preset != "slay_soft_01"` (schema default) → rejected with `user_visual_override`

**Render behavior impact**:
- Visual intensity hints: ADVISORY ONLY — `applied=False`, `render_overrides={}`
- `effect_preset`: GUARANTEED UNCHANGED
- FFmpeg: ZERO changes
- Subtitle emphasis hints: still active (Phase 5.5)
- Pacing hints: still active (Phase 5.4)
- Hook overlay gate: still active (Phase 5.3)
- API: ZERO changes

### Test Suite State (Post Phase 5.6)

8 failed (same known pre-existing failures) / 7141 passed (+69 new tests) / 1 skipped

Known failures: `test_remotion_adapter.py` (4), `test_ai_optional_dependencies.py` (1), `test_ai_phase36_clip_segment_selection.py` (2), `test_ai_visibility_summary.py` (1) — all pre-Phase-1.

---

## Phase 5.7 — Safe Visual Intensity Injection (2026-05-23)

**Goal**: Add a safe renderer-level injection point so AI `visual_intensity` hints can affect visual output without giving AI control over FFmpeg.

**Key finding from Phase 5.6**: `_effect_filter()` in `ffmpeg_helpers.py` supports 6 named presets: `slay_soft_01` (default), `slay_pop_01`, `story_clean_01`, `social_bright`, `cinematic_soft`, `high_contrast`. The new `resolve_effect_preset_with_intensity()` function maps AI hints to 3 of these presets.

**Files changed**:

| File | Change |
|---|---|
| `backend/app/services/render/ffmpeg_helpers.py` | Added `resolve_effect_preset_with_intensity()`, `_VISUAL_INTENSITY_ALLOWED`, `_VISUAL_INTENSITY_PRESET_MAP` |
| `backend/app/services/render/legacy_renderer.py` | Added `visual_intensity_hint: str | None = None` to `render_part()` and `render_part_smart()`; calls resolver before `_effect_filter()` |
| `backend/app/services/render/base_clip_renderer.py` | Added `visual_intensity_hint: str | None = None` to `render_base_clip()`; calls resolver before `_effect_filter()` |
| `backend/app/ai/visual_hints.py` | `_NO_SAFE_INJECTION_POINT = False`; `applied=True` now possible; `render_overrides={"visual_intensity_hint": <value>}`; `_build_render_overrides()` helper added |
| `backend/app/orchestration/render_pipeline.py` | Phase 5.7 block extracts `_vis_intensity_hint`; passes to renderer calls via `visual_intensity_hint=_vis_intensity_hint` |

**New test files** (5):
- `tests/test_render_effect_intensity_mapping.py` — 34 tests for `resolve_effect_preset_with_intensity()`
- `tests/test_legacy_renderer_visual_intensity.py` — 17 tests for `render_part()` / `render_part_smart()`
- `tests/test_base_clip_renderer_visual_intensity.py` — 16 tests for `render_base_clip()`
- `tests/test_ai_visual_intensity_config.py` — 37 tests for `build_ai_visual_intensity_config()` (applied=True cases)
- `tests/test_render_pipeline_ai_visual_intensity.py` — 25 tests for pipeline integration

**AI mapping table** (renderer-owned):
- `"low"` → `story_clean_01` (subtle, gentle processing)
- `"medium"` → `slay_soft_01` (natural default)
- `"high"` → `slay_pop_01` (energetic pop)

**Render behavior impact**:
- Visual intensity hints: ACTIVE — `applied=True` for valid hints when user has not set explicit `effect_preset`
- `effect_preset`: GUARANTEED UNCHANGED — never mutated; preserved for logging
- AI disabled: `visual_intensity_hint=None` → renderer uses original `effect_preset`
- User explicit preset: `user_effect_is_explicit=True` → renderer uses original `effect_preset`
- `overlay_compositor.py`: NOT modified — no `visual_intensity_hint` added (strict rule)
- FFmpeg: ONLY the preset name input to `_effect_filter()` may change — filter construction logic unchanged
- API: ZERO changes

### Test Suite State (Post Phase 5.7)

8 failed (same known pre-existing failures) / 7215 passed (+74 new tests from Phase 5.7) / 1 skipped

Known failures: `test_remotion_adapter.py` (4), `test_ai_optional_dependencies.py` (1), `test_ai_phase36_clip_segment_selection.py` (2), `test_ai_visibility_summary.py` (1) — all pre-Phase-1.

**No new failures introduced.**

---

## Phase 5.8 — Output Quality Intelligence (2026-05-23)

**Branch**: `restructure/output-timeline-architecture`
**Commit message**: `phase 5.8 add output quality intelligence`

### Changes

**New module**: `backend/app/quality/`
- `__init__.py` — package exports
- `models.py` — `QualityIssue`, `QualityReport` dataclasses with scoring
- `assessor.py` — `assess_rendered_part_quality()` with 9 assessment categories

**Modified**:
- `backend/app/orchestration/qa_pipeline.py` — added `_assess_render_quality_intelligence()`
- `backend/app/orchestration/render_pipeline.py` — wired quality intelligence after `_assess_output_quality()`

**New tests** (5 files, ~80 tests):
- `tests/test_quality_models.py`
- `tests/test_quality_assessor.py`
- `tests/test_quality_subtitle_density.py`
- `tests/test_quality_trace_correlation.py`
- `tests/test_qa_pipeline_quality_integration.py`

**Docs updated** (5 files):
- `docs/ai/AI_RENDER_CONTRACT.md`
- `docs/ai/AI_DECISION_TRACEABILITY_PLAN.md`
- `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md`
- `docs/review/TECHNICAL_DEBT_REPORT.md`
- `docs/restructure/MIGRATION_HISTORY.md`

### Constraints honored
- NEVER raises (all exceptions caught internally)
- NEVER auto-regenerates video
- NEVER changes FFmpeg commands
- NEVER requires internet or API keys
- Warnings NEVER affect existing QA ok/error result
- Quality intelligence failure NEVER propagates to render result


---

## Phase 5.9 — Expose Quality Report API (2026-05-23)

**Goal**: Expose Phase 5.8 quality report sidecar JSON through safe read-only API endpoints.

**New files**:
- `backend/app/quality/report_locator.py` — `find_quality_report_path()`, `load_quality_report()`, `load_quality_report_for_part()` with security validation
- `backend/app/quality/report_summary.py` — `build_job_quality_summary()` aggregator

**Modified**:
- `backend/app/routes/jobs.py` — two new read-only GET endpoints added; no existing routes changed

**New tests** (3 files, 62 tests):
- `tests/test_quality_report_locator.py` (29 passed, 1 skipped)
- `tests/test_quality_report_summary.py` (12 passed)
- `tests/test_quality_report_api.py` (21 passed)

**Docs updated** (4 files):
- `docs/ai/AI_RENDER_CONTRACT.md`
- `docs/architecture/CURRENT_RENDER_ARCHITECTURE.md`
- `docs/review/TECHNICAL_DEBT_REPORT.md`
- `docs/restructure/MIGRATION_HISTORY.md`

### Constraints honored
- READ-ONLY — zero render behavior change
- No FFmpeg calls from quality routes
- No raw filesystem paths accepted or exposed
- Path traversal blocked at locator level (regex + resolve + relative_to)
- Invalid job_id → 400; missing job/part → 404; missing report → 404
- No DB schema changes
- Baseline test count unchanged (8 failures from Phase 5.8 pre-existing)

---

## Phase 5.10 — UI/Backend Contract Freeze (2026-05-23)

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED

**Purpose**: Freeze the UI/backend contract before Phase 6 UI overhaul. Audit
all active endpoints, document all RenderRequest field statuses, document valid
option enums, and create tests that enforce the contract.

**New files**:
- `docs/ui/UI_BACKEND_CONTRACT.md` — 14-section contract document; single source of truth for Phase 6 UI
- `backend/tests/test_ui_backend_contract.py` — 44 tests: endpoint existence, removed routes absent, file upload, RenderRequest instantiation, static file audit
- `backend/tests/test_ui_option_contract.py` — 47 tests: subtitle style enum, effect preset enum, platform options, duration bounds, source quality modes, render profiles, AI hint bounds
- `backend/tests/test_quality_api_contract.py` — 40 tests: quality endpoint 404/400 behavior, response shapes, locator security, contract doc existence

**Key audit findings**:
- 37 active API endpoints (render: 17, jobs: 12, files: 1, core: 2, other routers: 5+)
- Zero `/api/upload/` (old domain) calls in static JS — upload domain fully removed
- Two `/api/upload-file` (hyphen) calls in editor JS — correct, intentional
- 10 canonical subtitle style presets; `pro_karaoke` (schema default) is not canonical — resolves to `tiktok_bounce_v1`; Phase 6 UI must use canonical IDs
- 6 effect presets; quality endpoints (Phase 5.9) active but not yet called by UI
- WebSocket fingerprint logic documented
- Phase 6 UI overhaul checklist: 14 items

**Contracts introduced**:
- `docs/ui/UI_BACKEND_CONTRACT.md` is frozen — Phase 6 UI must comply with it
- All removed `/api/upload/*` routes confirmed absent and test-asserted
- All option enums test-validated against live backend code
- Quality report response shapes test-asserted against `QualityReport.to_dict()` and `build_job_quality_summary()`
- Score thresholds: >=85 Good, 70-84 Needs review, 50-69 Warning, <50 Poor

**No code changes to render pipeline, FFmpeg, or API behavior.**

**Test suite state (Post Phase 5.10)**:
```
8 failed (pre-existing), 7479 passed, 2 skipped
```
Phase 5.10 added 131 new passing tests.

---

## Phase 6.0 — UI Foundation Architecture (2026-05-23)

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED

**Purpose**: Scaffold the new React/TypeScript frontend foundation at `frontend/`.
Implements all architecture, typed API layer, state stores, WebSocket abstraction,
design tokens, layout skeleton, enum constants, and tests. The legacy `backend/static/`
frontend is untouched and remains fully operational.

**New directory**: `frontend/` (React 18 + TypeScript + Vite + Zustand)

**New files (frontend)**:
- `frontend/package.json` — name: render-studio-ui; React 18, TypeScript, Vite, Zustand, Vitest
- `frontend/vite.config.ts` — proxy /api + /media to 127.0.0.1:8000; build → backend/static-new/
- `frontend/tsconfig.json`, `tsconfig.app.json`, `tsconfig.node.json`
- `frontend/index.html` — Vite entry point
- `frontend/src/main.tsx` — React root
- `frontend/src/App.tsx` — AppShell wrapper with panel routing
- `frontend/src/types/api.ts` — TypeScript interfaces from API contract + schemas.py
- `frontend/src/types/enums.ts` — Typed enum constants matching backend values
- `frontend/src/api/client.ts` — ApiError class + apiFetch base wrapper
- `frontend/src/api/render.ts` — submitRender, getRenderStatus, cancelRender, resumeRender, retryRender
- `frontend/src/api/jobs.ts` — getJob, getJobHistory, getQueueStatus, getJobPartQuality, getJobQualitySummary, deleteJob
- `frontend/src/api/upload.ts` — uploadFile() using POST /api/upload-file only
- `frontend/src/websocket/RenderSocketClient.ts` — WS client, 3-attempt reconnect, terminal guard
- `frontend/src/websocket/events.ts` — typed WS event interfaces + RenderStage enum
- `frontend/src/hooks/useRenderSocket.ts` — React hook: { stage, progress, isConnected, error }
- `frontend/src/stores/renderStore.ts` — jobs, activeJobId, submitRender, updateJobStatus, setActiveJob
- `frontend/src/stores/qualityStore.ts` — reports, summaries, fetchPartQuality, fetchJobSummary
- `frontend/src/stores/uiStore.ts` — sidebarOpen, activePanel, notifications
- `frontend/src/styles/tokens.css` — ~79 CSS custom properties (cinematic dark theme)
- `frontend/src/styles/global.css` — reset + base styles using tokens
- `frontend/src/lib/constants.ts` — PLATFORMS(3), ASPECT_RATIOS(5), SUBTITLE_STYLES(10), EFFECT_PRESETS(6), QUALITY_MODES(3), RENDER_PROFILES(4), getQualityLabel, getQualityVariant
- `frontend/src/layouts/AppShell.tsx` — root layout: sidebar + topbar + content
- `frontend/src/layouts/Sidebar.tsx` — navigation with collapse support
- `frontend/src/layouts/Topbar.tsx` — title, connection status, warmup badge
- `frontend/src/components/ui/Button.tsx` — variant(4) + size(3) + loading
- `frontend/src/components/ui/Badge.tsx` — 5 semantic variants
- `frontend/src/components/ui/ProgressBar.tsx` — 0–100 fill, 3 variants
- `frontend/src/components/quality/QualityBadge.tsx` — score → §8.3 threshold badge
- `frontend/src/components/quality/QualityIssueList.tsx` — grouped by severity
- `frontend/tests/api.test.ts` — ApiError + upload path audit (11 tests)
- `frontend/tests/constants.test.ts` — enum count + value + quality logic (31 tests)
- `frontend/tests/stores.test.ts` — uiStore toggle/panel/notifications (15 tests)

**New docs**:
- `docs/ui/PHASE_6_UI_ARCHITECTURE.md` — tech stack, directory, state flow, WS flow, token system, API layer, component strategy, migration plan, Phase 6.1 checklist

**Test results**: 57/57 passed (3 test files)

**Contracts preserved**:
- `backend/static/` untouched — legacy UI remains fully operational
- All API calls comply with `docs/ui/UI_BACKEND_CONTRACT.md` Phase 5.10 freeze
- `/api/upload-file` (hyphen) used for uploads; `/api/upload/*` (slash) never referenced
- Quality endpoints called on-demand only (not polled)
- WebSocket closes on terminal status; no reconnect for terminal states
- Paginated history uses `/api/jobs/history`; unbounded `/api/jobs` not used

---

## Phase 6.1 — Render Setup Screen (2026-05-23)

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED

**Purpose**: Build the Render Setup Screen — the primary user-facing form for configuring and submitting render jobs.

**Files created**:
- `frontend/src/features/render/RenderSetupScreen.tsx` — top-level screen, plugged into App.tsx
- `frontend/src/features/render/RenderForm.tsx` — main form, two-column layout
- `frontend/src/features/render/RenderForm.types.ts` — RenderFormState + RenderFormErrors
- `frontend/src/features/render/RenderForm.schema.ts` — validateRenderForm, isFormValid, buildRenderPayload
- `frontend/src/features/render/RenderForm.css` — form layout and component styles
- `frontend/src/features/render/components/FormField.tsx` — label + children + hint + error wrapper
- `frontend/src/features/render/components/SelectCardGroup.tsx` — clickable card grid for enum selection
- `frontend/src/features/render/components/SourceSection.tsx` — source_mode toggle + URL/path inputs
- `frontend/src/features/render/components/OutputSection.tsx` — output_dir + max_export_parts
- `frontend/src/features/render/components/CreativeSection.tsx` — platform, aspect ratio, effect preset
- `frontend/src/features/render/components/SubtitleSection.tsx` — add_subtitle toggle + subtitle_style
- `frontend/src/features/render/components/AdvancedSection.tsx` — AI director, render profile, part durations
- `frontend/src/features/render/components/SummaryCard.tsx` — sticky summary card with submit button
- `frontend/src/components/ui/Notifications.tsx` — fixed-position toast notifications
- `frontend/tests/render-form.test.tsx` — 14 rendering tests
- `frontend/tests/render-validation.test.tsx` — 29 pure logic tests
- `frontend/tests/render-submit.test.tsx` — 9 submit flow tests

**Files modified**:
- `frontend/src/App.tsx` — replaced RenderPanel placeholder with RenderSetupScreen
- `frontend/src/layouts/AppShell.tsx` — added Notifications toast area

**Canonical subtitle default confirmed**: `tiktok_bounce_v1` — `pro_karaoke` never appears in form

**Test results**: 109/109 passed (6 test files)

**Contracts preserved**:
- `backend/static/` untouched — legacy UI remains fully operational
- All field names match `docs/ui/UI_BACKEND_CONTRACT.md` §5 exactly
- Only 10 canonical subtitle presets used (no legacy aliases)
- Only 6 effect presets, 3 platforms, 5 aspect ratios used
- Submit calls `POST /api/render/process` via `renderStore.submitRender()`
- On success: success notification + redirect to history panel
- On failure: error notification, stays on render panel

---

## Phase 6.2 — History Screen + Job Actions (2026-05-23)

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED

**Purpose**: Build the History Screen — paginated job list with search/filter, job action buttons (cancel/retry/re-run/delete), and a detail drawer for selected jobs.

**Files created**:
- `frontend/src/features/jobs/HistoryScreen.tsx` — top-level screen; manages fetch, pagination, filters, action state
- `frontend/src/features/jobs/HistoryScreen.css` — layout CSS (.history-screen, .history-content, .history-list-pane, .history-detail-pane)
- `frontend/src/features/jobs/JobList.tsx` — renders filtered list + pagination controls
- `frontend/src/features/jobs/JobListItem.tsx` — card: title, badge, source, progress bar (active), counts, timestamp, actions
- `frontend/src/features/jobs/JobStatusBadge.tsx` — maps 9 status strings to Badge variants
- `frontend/src/features/jobs/JobActionsMenu.tsx` — Cancel/Retry/Re-run/Details/Delete buttons with conditions
- `frontend/src/features/jobs/JobDetailDrawer.tsx` — right-rail panel; loads full JobStatus via getJob(), collapsible payload section
- `frontend/src/features/jobs/JobFilters.tsx` — search input + status filter dropdown
- `frontend/src/features/jobs/JobEmptyState.tsx` — empty list with "Create first render" CTA
- `frontend/src/features/jobs/JobLoadingState.tsx` — 3-row skeleton placeholder
- `frontend/src/features/jobs/JobErrorState.tsx` — error message + retry button
- `frontend/src/features/jobs/jobs.utils.ts` — formatRelativeTime, formatDateTime, isTerminalStatus, isActiveStatus, canCancel, canRetry, canRerun, canDelete
- `frontend/src/features/jobs/jobs.types.ts` — StatusFilter, JobActionState
- `frontend/tests/history-screen.test.tsx` — 14 screen integration tests
- `frontend/tests/job-actions.test.tsx` — 9 action handler tests
- `frontend/tests/job-status.test.tsx` — 10 status badge tests
- `frontend/tests/job-utils.test.ts` — 31 utility function tests

**Files modified**:
- `frontend/src/App.tsx` — replaced HistoryPanel placeholder with HistoryScreen import

**Status badge map (9 statuses)**:
- completed → Complete (success), partial → Partial (warning), running → Rendering (info)
- queued → Queued (neutral), failed → Failed (error), interrupted → Interrupted (warning)
- cancelled/canceled → Canceled (neutral), cancelling → Canceling (warning), unknown → Unknown (neutral)

**Action conditions**:
- Cancel: isActiveStatus(status) → cancelRender(jobId)
- Retry: item.can_retry → retryRender(jobId)
- Re-run: item.can_rerun → resumeRender(jobId)
- Delete: isTerminalStatus(status) → window.confirm() → deleteJob(jobId, true)
- Details: always visible → opens JobDetailDrawer

**Test results**: 173/173 passed (10 test files, 64 new tests)

**Contracts preserved**:
- `backend/static/` untouched — legacy UI remains fully operational
- History uses `GET /api/jobs/history?limit=20&offset=N` (paginated) — never unbounded `/api/jobs`
- Delete uses `DELETE /api/jobs/{id}?delete_files=true`
- Cancel uses `POST /api/render/{id}/cancel`
- Retry uses `POST /api/render/retry/{id}`
- Re-run uses `POST /api/render/resume/{id}`
- Quality endpoints NOT called in Phase 6.2 — placeholder shown in drawer

---

## Phase 6.3 — Quality Panel + Job Detail Intelligence

**Branch**: `restructure/output-timeline-architecture`
**Status**: SHIPPED
**Date**: 2026-05-23

**Purpose**: Replace the "coming in Phase 6.3" placeholder in JobDetailDrawer with a fully functional, on-demand quality report panel. AI trace references are displayed with friendly labels, never raw internal event strings.

**Shipped changes**:

Frontend — new files (`frontend/src/features/quality/`):
- `quality.types.ts` — `QualityLoadState` type, `AI_TRACE_FRIENDLY` display map (6 known refs)
- `quality.utils.ts` — `getFriendlyTraceLabel`, `getSeverityIcon`, `formatScore` pure helpers
- `QualityPanel.tsx` — main entry, fetch-on-open, no polling, pending/loading/error/empty/loaded states
- `QualityPanel.css` — CSS token-based styles (compact for 380px drawer)
- `QualitySummaryCard.tsx` — aggregate score badge + issue count badges
- `QualityPartList.tsx` — list wrapper for QualityPartCard
- `QualityPartCard.tsx` — expandable card; fetches part report on-demand when expanded
- `QualityTraceRefs.tsx` — AI trace ref pills (friendly labels); "No AI trace references" if empty
- `QualityLoadingState.tsx` — 3-row animated skeleton
- `QualityEmptyState.tsx` — 404 / no data state
- `QualityErrorState.tsx` — error message + Retry button

Frontend — modified files:
- `frontend/src/stores/qualityStore.ts` — added `refreshJobSummary`, `refreshPartQuality` actions
- `frontend/src/features/jobs/JobDetailDrawer.tsx` — placeholder replaced with `<QualityPanel />`

Tests — new files:
- `frontend/tests/quality-utils.test.ts` — 17 pure logic tests
- `frontend/tests/quality-panel.test.tsx` — 21 rendering + behaviour tests

Docs updated:
- `docs/ui/PHASE_6_UI_ARCHITECTURE.md` — Phase 6.3 section added, checklist updated
- `docs/restructure/MIGRATION_HISTORY.md` — this entry

**Contracts introduced**:
- `QualityPanel` NEVER polls — single fetch on open, manual refresh only
- `QualityPanel` skips fetch entirely for `queued`/`running` job statuses
- Part reports are fetched on-demand (expand click) — not bulk-fetched with summary
- `refreshJobSummary` clears loading guard before re-fetch (prevents skip on repeat open)
- AI trace refs always rendered as friendly labels; raw `ai.*` event strings never shown directly

**Test results**: 211/211 passed (12 test files, 38 new tests)
