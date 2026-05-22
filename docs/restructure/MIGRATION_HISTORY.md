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
