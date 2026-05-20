# OQ-3.3 — MediaPipe Pose Eye-Level Anchor
## Premium Framing Composition

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** FRAMING QUALITY ONLY — no tracking rewrite, no crop math rewrite, no render changes

---

## 1. Audit Findings

### Current framing anchor (pre-OQ-3.3)

**File:** `backend/app/services/motion_crop.py`, function `_subject_to_crop_center()`, line 858:

```python
if subject_kind == "body":
    cy = y + h * 0.50
else:
    cy = y + h * 0.34   # ← current face anchor: 34% from top of face box
```

### Problem

`cy = y + h * 0.34` is an approximation. The actual eye line relative to a MediaPipe face
bounding box varies with:

- **Face distance** — close-ups have proportionally taller boxes (includes neck/chin); distant
  faces are tighter (mostly head). Eye position within the box shifts accordingly.
- **Head tilt** — rotated faces shift the eye midpoint within the box.
- **Aspect ratio** — narrow vs wide face boxes.

Result: inconsistent headroom. Forehead often clipped in close-ups; excessive chin room in
medium shots; speaker sits too low in the crop window.

### What premium framing requires

**Rule of thirds:** eyes should land at approximately 1/3 from the top of the crop window.
With a 1440px tall crop:
- Eyes at 33%: 475px of headroom (above) + 965px for body/chin (below)
- This is the broadcast/cinema standard for talking-head composition.

MediaPipe Pose (BlazePose Lite, `model_complexity=0`) provides accurate per-frame
eye landmark positions: `LEFT_EYE (index 2)` and `RIGHT_EYE (index 5)` in normalized
landmark space.

---

## 2. Design

### Eye anchor as a face-box-relative offset

The eye anchor is stored as `eye_anchor_rel: float` — the eye midpoint y as a fraction
of the face box height from its top edge:

```
eye_anchor_rel = (eye_y_src - face_y_src) / face_h_src
```

This is a geometric property of the face (typically 0.25–0.45), not an absolute position.
It remains valid between detection intervals as the face moves — the anchor tracks the
face box naturally.

### Updated `cy` formula

When `eye_anchor_rel` is available:

```python
eye_y = y + h * eye_anchor_rel
cy = eye_y + crop_h * (0.5 - 0.33)   # eyes at 1/3 from crop top
```

`crop_h * (0.5 - 0.33) = crop_h * 0.17`: crop center is 17% of crop height below
the eyes. This satisfies rule-of-thirds exactly.

### Fallback chain (unchanged)

```
Pose available + eye detected + nose in face box → eye_anchor_rel (this phase)
                                                 ↓ else
Pose unavailable OR face box mismatch           → eye_anchor_rel = None
                                                 ↓
                                          existing cy = y + h * 0.34
```

All existing fallbacks are preserved. `_subject_to_crop_center()` signature is fully
backward-compatible (`eye_anchor_rel` defaults to None).

---

## 3. Implementation

### New components

**`_get_mp_pose()`** — lazy singleton:
- `static_image_mode=True` — independent inference per call (no temporal tracking between
  detection intervals)
- `model_complexity=0` — BlazePose Lite, fastest, CPU-safe
- `min_detection_confidence=0.4` — slightly permissive to reduce false negatives
- `POSE_EYE_ANCHOR_ENABLED=0` environment gate for easy disable
- Returns None if mediapipe unavailable (graceful fallback)

**`_get_eye_anchor_rel(frame_bgr_small, face_box_src, detect_scale, det_sy)`** — eye extraction:
- Runs Pose on the detection-interval frame (same `small` frame already available)
- Converts landmarks from small-frame relative → src-frame absolute
- **Validation**: nose landmark must fall within face box (±20% margin) — rejects Pose
  results from background subjects when multiple people are in frame
- Returns eye_rel clamped to `[0.0, 0.65]`, or None on any failure

### `_subject_to_crop_center()` modification

New optional parameter: `eye_anchor_rel: Optional[float] = None`

```python
if eye_anchor_rel is not None and subject_kind != "body":
    eye_y = y + h * eye_anchor_rel
    cy = eye_y + crop_h * (0.5 - _EYE_CROP_THIRDS)   # _EYE_CROP_THIRDS = 0.33
elif subject_kind == "body":
    cy = y + h * 0.50
else:
    cy = y + h * 0.34   # unchanged fallback
```

The `subject_ratio` large-face blend (`cy * 0.70 + frame_h * 0.42 * 0.30`) is skipped when
eye anchor is active — the eye position is already accurate; blending toward frame center
would degrade it.

### Loop wiring (both build_subject_path and build_subject_path_scene)

| Where | Change |
|---|---|
| Before loop | `_last_eye_rel: Optional[float] = None` |
| After detection confirmed | `_last_eye_rel = _get_eye_anchor_rel(small, best/locked_subject, detect_scale, _det_sy)` |
| Step 3 `_subject_to_crop_center()` calls | `eye_anchor_rel=_last_eye_rel` |

`_last_eye_rel` is cached across detection intervals — valid because it is a geometric
ratio (not an absolute position) that tracks the face box correctly.

---

## 4. Compatibility Impact

| Component | Impact |
|---|---|
| `_subject_to_crop_center()` | New optional param, None default — all existing call sites unaffected |
| Face detection / MediaPipe face model | Unchanged — separate model, no interaction |
| ByteTrack tracking (OQ-3.2) | Unchanged — `get_subject()` returns same (x,y,w,h); eye anchor applied in Step 3 independently |
| OpenCV tracker | Unchanged |
| Gaussian smoothing | Unchanged — consumes raw_centers same format |
| Velocity limiter | Unchanged |
| `render_motion_aware_crop()` | Unchanged — signature unchanged |
| Render pipeline | Unchanged |
| `MotionCropConfig` | No new fields |
| Multi-person frames | Safe — nose validation ensures anchor matches selected subject |

---

## 5. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Pose detects wrong person in multi-person frame | Low | Nose-in-face-box validation rejects mismatched results; falls back to `y + h * 0.34` |
| Pose fails on close-up (face fills frame, no body visible) | Low | Returns None → fallback to existing formula; no regression from baseline |
| `eye_anchor_rel` outside expected range | None | Clamped to `[0.0, 0.65]`; out-of-range returns None |
| Pose model load failure | None | Lazy singleton catches exception; `_mp_pose_detector = None`; all calls return None |
| `POSE_EYE_ANCHOR_ENABLED=0` disables it | Intended | Hard gate for easy rollback; face detection unchanged |
| Subject-ratio adjustments interact with eye anchor | None | `cy` ratio adjustments skipped when eye anchor active |

---

## 6. Manual Verification Checklist

```
[ ] Log shows: mediapipe_pose_loaded model_complexity=0 eye_anchor=enabled
[ ] Talking-head close-up: eyes at approximately 1/3 from crop top (not forehead-clipped)
[ ] Medium shot: good headroom, no chin-heavy framing
[ ] Wide shot: Pose may return None — fallback formula, no regression
[ ] Multiple people in frame: anchor matches selected speaker, not background subject
[ ] POSE_EYE_ANCHOR_ENABLED=0: eye anchor disabled, cy = y + h * 0.34 (unchanged baseline)
[ ] MediaPipe unavailable: graceful fallback (log: mediapipe_pose_unavailable), no crash
[ ] Render stable: full pipeline completes without error
```

---

## 7. Files Modified

| File | Change |
|---|---|
| `backend/app/services/motion_crop.py` | Add `_get_mp_pose()`, `_get_eye_anchor_rel()`, `eye_anchor_rel` param in `_subject_to_crop_center()`, wire `_last_eye_rel` into both tracking loops |

---

## 8. Commit Hash

`[pending]`

---

## 9. Push Confirmation

`[pending]`
