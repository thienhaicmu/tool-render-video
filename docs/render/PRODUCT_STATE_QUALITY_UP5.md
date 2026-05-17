# PRODUCT STATE — QUALITY-UP5: Smart Motion Crop

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): smart motion crop`
**Status:** Shipped

---

## Summary

Two targeted upgrades to the motion crop pipeline:

1. **MediaPipe primary detection** — replaces Haar cascade as the face detection
   layer. More robust to pose angle, partial occlusion, and varied lighting.
   Haar cascade remains as fallback if MediaPipe is unavailable.

2. **Content-type-aware tracking** — interview/tutorial clips get a slower,
   smoother camera. Montage clips get faster, more reactive tracking. Both
   are driven by the same `content_type_hint` already computed by QUALITY-UP2.

---

## Root Cause

The Haar cascade frontal face detector had three known failure modes:

1. **Angle sensitivity.** `haarcascade_frontalface_default.xml` requires
   the face to be within ~30° of frontal. Profile shots, downward angles,
   and tilted heads produce zero detections → camera snaps to frame center.

2. **Lighting fragility.** Low-key lighting, high contrast, and strong
   backlighting all degrade Haar detection quality significantly.

3. **Uniform tracking aggressiveness.** Interview clips (static speaker) and
   montage clips (fast-moving action) received the same detect interval,
   EMA alpha, and pan speed — each wrong for its content type.

---

## Part A — MediaPipe Detection Layer

**File:** `backend/app/services/motion_crop.py`

A lazy singleton pattern loads MediaPipe once per process:

```python
_mp_face_detector = None
_mp_face_detector_initialized = False

def _get_mp_detector():
    ...tries import mediapipe...
    # Returns None if unavailable — no crash, no import error propagation
```

`_detect_mediapipe_faces(frame_bgr_small, scale)` is called inside
`_detect_subjects_in_frame` before the Haar path:

```python
# MediaPipe primary path
if frame_bgr_small is not None:
    mp_boxes = _detect_mediapipe_faces(frame_bgr_small, scale)
    if mp_boxes:
        return mp_boxes, "face"

# Haar cascade fallback
if face_cascade is not None:
    ...existing code...
```

Detection call sites in both `build_subject_path` and `build_subject_path_scene`
now pass `small` (the downscaled BGR frame) as the `frame_bgr_small` parameter.

**Coordinate system** (unchanged from Haar path):
MediaPipe returns relative bounding boxes → converted to absolute `small` frame
coords → divided by `detect_scale` → returned in `_det_frame` coord space →
caller divides by `_det_sx` → source frame coords.

---

## Part B — Confidence-Aware Framing

MediaPipe's `FaceDetection` model filters by `min_detection_confidence=0.5`
at the model level. Detections below 50% confidence are discarded before
returning to the caller. The existing `_filter_subject_candidates` and
`_pick_best_subject` score-based selection then applies on top.

No separate confidence pass is required: MediaPipe's built-in threshold
replaces Haar's `minNeighbors` quality gate.

---

## Part C — Smooth Tracking (Unchanged)

The existing EMA smoothing, Gaussian path smoothing, and velocity limiter
are not changed. MediaPipe provides better detection quality; the smoothing
layer handles the same job.

---

## Part D — Multi-Subject Safety (Unchanged)

`_filter_subject_candidates` and `_pick_best_subject` remain identical.
MediaPipe may return multiple face detections (like Haar); the existing
scoring pipeline (area × center proximity × edge margin × stability) handles
selection.

---

## Part E — Content-Type-Aware Tracking

**File:** `backend/app/services/motion_crop.py`

A parameter table maps content type to tracking multipliers:

| content_type | detect_interval_mul | ema_mul | pan_speed_mul |
|-------------|--------------------|---------|----|
| `interview`  | 2.0× (every 32f) | 0.65× (slower) | 0.70× |
| `commentary` | 1.5× (every 24f) | 0.80× | 0.85× |
| `vlog`       | 1.0× (default)  | 1.00× | 1.00× |
| `tutorial`   | 2.0× (every 32f) | 0.65× | 0.70× |
| `montage`    | 0.5× (every 8f) | 1.30× (faster) | 1.40× |

`_apply_content_type_to_cfg(cfg, content_type)` returns a shallow
`dataclasses.replace()` copy of cfg with the adjusted values:
- `subject_detect_interval` scaled by `detect_interval_mul`
- `ema_alpha_slow/normal/fast` scaled by `ema_mul`
- `max_pan_speed_ratio` scaled by `pan_speed_mul`

Applied at the start of `build_subject_path_scene` (scene path) and
`build_subject_path` (non-scene path). The base config is not mutated.

**Propagation chain:**

```
render_pipeline.py: seg.get("content_type_hint", "vlog")
  → render_part_smart(content_type=...)
    → render_motion_aware_crop(content_type=...)
      → build_motion_path(content_type=...)
        → build_subject_path(content_type=...)
          → build_subject_path_scene(content_type=...)
            → _apply_content_type_to_cfg(cfg, content_type)
```

---

## Part F — Failure Safety

Three layers of graceful degradation:

1. **MediaPipe import fails** — `_get_mp_detector()` catches any exception
   and sets `_mp_face_detector = None`. Logged at INFO level. Haar runs
   unchanged.

2. **MediaPipe inference fails per-frame** — `_detect_mediapipe_faces` wraps
   `detector.process()` in try/except. Returns `[]` on error (logged at DEBUG).
   Haar path runs as fallback.

3. **No subject found at all** — existing `motion_fallback` path to legacy
   pixel-diff tracking is unchanged.

No render crash. No broken export. No missing frames.

---

## Parameter Comparison

| Parameter | Before | After (vlog) | After (interview) | After (montage) |
|-----------|--------|--------------|-------------------|-----------------|
| Face detector | Haar frontal | MediaPipe (Haar fallback) | MediaPipe | MediaPipe |
| `subject_detect_interval` | 16 | 16 | 32 | 8 |
| `ema_alpha_slow` | 0.08 | 0.08 | 0.052 | 0.104 |
| `ema_alpha_normal` | 0.18 | 0.18 | 0.117 | 0.234 |
| `ema_alpha_fast` | 0.25 | 0.25 | 0.163 | 0.325 |
| `max_pan_speed_ratio` | 0.010 | 0.010 | 0.007 | 0.014 |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| MediaPipe pose/body landmark tracking | `face_detection` sufficient; pose adds GPU pressure |
| Full-range MediaPipe model (model_selection=1) | model_selection=0 (short-range) sufficient for typical clip distances |
| Per-detection confidence score in subject scoring | MediaPipe's `min_detection_confidence=0.5` is a sufficient pre-filter |
| Adaptive `min_detection_confidence` per content_type | Static 0.5 threshold is safe; montage may benefit from lower — QUALITY-UP6 scope |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/motion_crop.py` | `_get_mp_detector`, `_detect_mediapipe_faces`, `_CONTENT_TYPE_TRACKING`, `_apply_content_type_to_cfg`; `_detect_subjects_in_frame` MediaPipe primary path; detect call sites pass `small`; `content_type` param chain through all tracking functions |
| `backend/app/services/render_engine.py` | `render_part_smart` accepts `content_type`, passes to `render_motion_aware_crop` |
| `backend/app/orchestration/render_pipeline.py` | Pass `content_type=seg.get("content_type_hint", "vlog")` to `render_part_smart` |
| `docs/render/PRODUCT_STATE_QUALITY_UP5.md` | This file |

---

## Manual QA Checklist

### MediaPipe available (pip install mediapipe)
- [ ] Log shows `mediapipe_face_detection_loaded model=short_range` on first render
- [ ] Talking-head clips: face tracked through partial occlusion (hand covers face)
- [ ] Profile/angled shots: face tracked where Haar previously failed
- [ ] Low-light clips: detection more stable than before

### MediaPipe unavailable (no mediapipe package)
- [ ] Log shows `mediapipe_unavailable fallback=haar`
- [ ] Render completes normally (Haar runs as before)
- [ ] No ImportError, no crash, no missing frames

### Content-type tracking
- [ ] Job log: interview clip `subject_detect_interval=32` in motion crop config
- [ ] Job log: montage clip `subject_detect_interval=8`
- [ ] Interview: camera movement visibly smoother/slower
- [ ] Montage: camera movement visibly more reactive

### Multi-subject safety
- [ ] Two-person interview: camera stays on primary speaker (score-based selection)
- [ ] Subject switch is smooth (existing confirm-frames logic unchanged)

### Safety
- [ ] Normal render completes without error
- [ ] Cancel still works during motion crop
- [ ] No regression on clips that previously had subject tracking
- [ ] No backend errors during any of the above
