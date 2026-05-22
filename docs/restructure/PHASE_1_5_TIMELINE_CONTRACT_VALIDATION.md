# Phase 1.5 — Timeline Contract Validation

**Date**: 2026-05-22  
**Branch**: feature/ai-output-upgrade  
**Status**: COMPLETE — 1 bug fixed, 0 regressions, 5638 tests pass

---

## Purpose

Validate that Phase 1's `TimelineMap` domain object accurately represents the
actual render pipeline speed contract before Phase 2 builds on top of it.
"TimelineMap must match existing behavior, not redefine it."

---

## 1. Speed Clamp Consistency Audit

### 1.1 Render pipeline speed clamp: [0.5, 1.5]

Grepped all speed clamp patterns across `backend/app/`:

| Location | Expression | Clamp |
|---|---|---|
| `render_pipeline.py` — `_get_effective_playback_speed()` | `max(0.5, min(1.5, payload.playback_speed + platform_delta))` | [0.5, 1.5] |
| `render_engine.py:452` — `_sanitize_speed()` | `max(0.5, min(1.5, v))` | [0.5, 1.5] |
| `motion_crop.py:551` | `max(0.5, min(1.5, speed))` | [0.5, 1.5] |
| `subtitle_engine.py:160` | `max(0.5, min(1.5, speed))` | [0.5, 1.5] |
| `render_pipeline.py:4222` | `max(0.5, min(1.5, ...))` | [0.5, 1.5] |
| `render_pipeline.py:4360` | `max(0.5, min(1.5, ...))` | [0.5, 1.5] |

**Conclusion**: Every render-path speed sanitizer uses [0.5, 1.5]. This is the canonical pipeline speed range.

### 1.2 audio_mix_service.py: [0.5, 2.0] — intentionally different

`audio_mix_service.py` clamps narration atempo to [0.5, 2.0]. This is **correct and separate**: it reflects FFmpeg's atempo filter's own hardware constraint, not the pipeline's playback speed range. The narration atempo is a post-process step that can exceed the video speed range in principle.

### 1.3 Bug found: TimelineMap._SPEED_MAX = 2.0 (incorrect)

Phase 1's `timeline.py` set `_SPEED_MAX = 2.0`, copying the FFmpeg atempo
range by mistake. Because `TimelineMap` is a *video timeline* model (not an
audio filter model), its clamp must match the render pipeline, not FFmpeg atempo.

**Fix applied**:

```python
# Before (incorrect):
# FFmpeg atempo filter is clamped to [0.5, 2.0].
_SPEED_MAX = 2.0

# After (correct):
# Matches _get_effective_playback_speed() and _sanitize_speed() in the render pipeline,
# both of which clamp to [0.5, 1.5].  audio_mix_service uses [0.5, 2.0] separately
# because that is FFmpeg atempo's own filter range — that is a different concern.
_SPEED_MAX = 1.5
```

**Files changed**:
- `backend/app/domain/timeline.py`: `_SPEED_MAX` constant + module-level comment + docstring
- `backend/tests/test_timeline_map.py`: 3 clamping tests updated (expected value was 2.0, now 1.5)

---

## 2. FFmpeg Filter Chain Order Validation

Confirmed in `backend/app/services/render_engine.py`:

```
ass='{ass_safe}'          (line ~988-990)  ← subtitle filter, SOURCE timestamps
setpts=PTS/{speed:.4f}    (line ~1007)     ← re-clocks frames to output speed
fps={target_fps}           (line ~1013)    ← normalizes frame rate
```

**Order is correct and unchanged.** The `ass` filter applies subtitle timestamps
in source-clip time before `setpts` re-clocks the frames. This is the implicit
contract that keeps subtitles correctly aligned at any playback speed.

**Conclusion**: No change required. Do NOT reorder this chain.

---

## 3. Manifest Lifecycle Validation

Verified Phase 1 integration points in `render_pipeline.py`:

| Stage | Manifest field written | When |
|---|---|---|
| Timeline creation | initial manifest (all metadata) | After `_effective_start` finalized |
| `cut_video()` | `cut_path` | After cut completes |
| SRT generation | `srt_path` | Before resegmentation block |
| ASS generation | `ass_path` | Inside `if needs_ass:` block |
| Narration | `narration_path` | At `_final_voice_path` convergence |
| `render_part_smart()` | `rendered_path` | After render finally block |

All writes go through `write_manifest()` which:
- Is atomic (`.tmp` → `os.replace()`)
- Never raises (logs warning on failure, returns `None`)
- Creates parent directory if absent

**Conclusion**: Manifest lifecycle is correct. Write-only in Phase 1 (no read-back into pipeline decisions).

---

## 4. API / Frontend / Schema Isolation

Ran `git diff HEAD~1 -- backend/app/models/schemas.py backend/static/ backend/app/routes/ backend/app/services/db.py`:

**Result: empty diff.** Phase 1 introduced zero changes to API schema, frontend,
routes, or database.

---

## 5. Test Results

### Phase 1 domain tests (65 tests)
```
tests/test_timeline_map.py        25 passed
tests/test_base_clip_manifest.py  22 passed
tests/test_manifest_writer.py     18 passed
Total: 65 passed in 0.26s
```

### Full suite (post-fix)
```
5638 passed, 1 skipped, 8 failed
```

The 8 failures are **pre-existing** (verified against stashed baseline before Phase 1):
- `test_ai_optional_dependencies.py::test_get_ai_dependency_status_keys`
- `test_ai_phase36_clip_segment_selection.py::TestClipSegmentSelector::test_invalid_timing_rejected`
- `test_ai_phase36_clip_segment_selection.py::TestClipSegmentSelector::test_negative_timing_rejected`
- `test_ai_visibility_summary.py::test_badges_generated_from_real_scores`
- `test_remotion_adapter.py::test_render_request_default_remotion_hook_intro_false`
- `test_remotion_adapter.py::test_generate_hook_intro_returns_path_when_ffmpeg_creates_file`
- `test_remotion_adapter.py::test_generate_hook_intro_uses_fallback_headline_rotation`
- `test_remotion_adapter.py::test_remotion_success_replaces_clip_with_concatenated_output`

**Zero new failures introduced by Phase 1 or Phase 1.5.**

---

## 6. Summary of Changes

| File | Change |
|---|---|
| `backend/app/domain/timeline.py` | `_SPEED_MAX` 2.0 → 1.5; comment + docstring corrected |
| `backend/tests/test_timeline_map.py` | 3 clamping tests: expected max boundary 2.0 → 1.5 |
| `docs/restructure/PHASE_1_5_TIMELINE_CONTRACT_VALIDATION.md` | This document |

---

## 7. Phase 2 Readiness

TimelineMap now accurately models the actual render pipeline speed contract.
The speed range `[0.5, 1.5]` is consistent across:
- `_get_effective_playback_speed()` (where speed enters the pipeline)
- `_sanitize_speed()` in render_engine.py (where speed enters FFmpeg)
- `TimelineMap.__post_init__()` (where speed enters the timeline model)

Phase 2 can safely read `manifest.rendered_path` and `manifest.timeline` to
derive output timing without needing to re-derive speed from raw payload fields.
