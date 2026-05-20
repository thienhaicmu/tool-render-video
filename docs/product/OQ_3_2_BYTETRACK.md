# OQ-3.2 — ByteTrack Subject Tracking
## Premium Crop Stability

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** TRACKING ONLY — no crop math, no smoothing, no render, no detector changes

---

## 1. Audit Findings

### Current subject persistence logic (pre-OQ-3.2)

**File:** `backend/app/services/motion_crop.py`

**Detection + tracking loop:**
```
Every N frames (default N=16):
  MediaPipe FaceDetection → detected box (ground truth)
  → tracker.init(frame, box)  ← reinitialize OpenCV tracker

Every frame (between detections):
  tracker.update(frame) → raw_box  ← KCF/CSRT/MOSSE per-pixel update

When subject lost (tracker fails or no detection):
  subject = None
  → fall to last_subject (STATIC box — exact pixels from last good detection)
```

### Problems identified

| # | Problem | Root cause |
|---|---|---|
| P1 | Face jump at re-detection | MediaPipe detected box at frame N is unvalidated against tracker position from frame N-1 — if face moved while tracker coasted/drifted, there's an instantaneous crop jump |
| P2 | Stale position during 533ms gap | At 30fps + 16-frame interval, `last_subject` holds the exact same (x,y,w,h) for up to 16 frames even when the subject is moving |
| P3 | OpenCV tracker drift accepted unchecked | KCF/CSRT accumulate error over many frames; no validation against expected position |
| P4 | No velocity extrapolation | When tracker fails, static `last_subject` doesn't predict where the subject moved |

### Current hold mechanism
```python
elif last_subject is not None:
    # Hold last known subject position (subject momentarily occluded)
    cx, cy = _subject_to_crop_center(last_subject, ...)
```
`last_subject` is the EXACT box from the last detection or tracker update. It never moves
during the hold period, creating visually stale crops when the subject has moved.

---

## 2. ByteTrack-Inspired Design

**ByteTrack** (Zhang et al., 2022) uses Kalman filter + IoU matching for inter-frame
subject continuity. For this single-subject use case, the key components are:

1. **Kalman velocity state** — predicts where the subject is each frame based on observed motion
2. **IoU validation** — rejects detection/tracker updates that are too far from predicted position (likely drift or false detection)
3. **Coasting** — when subject is momentarily occluded, the Kalman prediction smoothly extrapolates position rather than freezing

### `_ByteTrackSubject` class

State: `(cx, cy, w, h, vx, vy)` — center position + size + velocity.

**`predict()`** — advance state by one frame:
- `cx += vx`, `cy += vy`
- velocity decays by 0.90× (gentle damping prevents runaway prediction)
- increments `coast` counter

**`update(box, gain)`** — update from measurement:
- if `coast ≥ 3` AND `IoU(predicted, detected) < 0.10` → reject (return False = likely different subject or drifted detector)
- velocity: `vx = (det_cx - cx) × gain` (observed displacement scaled by gain)
- position: lerp toward detected center at `gain`
- size: slow update (0.10 gain) to avoid jumps
- resets `coast = 0`

**`is_alive(max_coast)`** — True when `coast ≤ max_coast` (uses existing `cfg.lost_subject_hold_frames = 45`)

**`get_subject()`** — returns current predicted `(x, y, w, h)` box

### Update gains

| Source | Gain | Rationale |
|---|---|---|
| MediaPipe detection | 0.55 | Ground truth — strong anchor |
| OpenCV tracker (per-frame) | 0.20 | Fine motion — moderate influence, prediction dominant |

---

## 3. Integration Architecture (OQ-3.2)

**Additive layer** — ByteTrack runs on top of existing detection + OpenCV tracker.
No existing code is removed. The OpenCV tracker still runs. MediaPipe still runs.
ByteTrack is inserted as a validation and prediction layer.

### Loop changes (4 insertion points)

**Before loop** — initialization:
```python
_btrack: Optional[_ByteTrackSubject] = None
```

**Top of each iteration** — predict + alive check:
```python
if _btrack is not None:
    _btrack.predict()
    if not _btrack.is_alive(cfg.lost_subject_hold_frames):
        _btrack = None
```

**Step 1 (OpenCV tracker update)** — validate and smooth:
```python
if _btrack is not None and subject is not None:
    if _btrack.update(subject, gain=0.20):
        subject = _btrack.get_subject()   # smoothed position
    else:
        tracking = False                   # tracker drifted — force re-detect
```

**After detection confirmed (Step 2)** — update/create track:
```python
if _btrack is not None:
    if not _btrack.update(best, gain=0.55):
        _btrack = _ByteTrackSubject(best)  # new track (subject changed)
else:
    _btrack = _ByteTrackSubject(best)      # first detection
```

**Step 3 (crop center)** — ByteTrack prediction fills the hold gap:
```python
# subject is not None  →  existing (unchanged)
# _btrack alive        →  NEW: velocity-predicted position (replaces static hold)
# last_subject         →  existing fallback (unchanged)
# default center       →  existing fallback (unchanged)
```

---

## 4. Compatibility Impact

| Component | Impact |
|---|---|
| `_create_tracker()` / OpenCV KCF/CSRT/MOSSE | Unchanged — still runs every frame |
| `_detect_subjects_in_frame()` | Unchanged — still runs every N frames |
| `_detect_mediapipe_faces()` (OQ-4.1) | Unchanged — MediaPipe still primary detector |
| `last_subject` static hold | Preserved as final fallback after ByteTrack coast expires |
| `motion_fallback` → legacy pixel-diff | Unchanged — still fires when `subjects_found_total == 0` |
| `trackerless_*` path (no OpenCV tracker) | Unchanged — ByteTrack updates happen regardless of tracker availability |
| `_subject_to_crop_center()` | Unchanged — consumes (x,y,w,h) same as before |
| Gaussian smoothing + velocity limiter | Unchanged — consumes raw_centers same as before |
| `MotionCropConfig` | No new fields — uses existing `lost_subject_hold_frames=45` |
| Render pipeline call sites | Unchanged — `build_subject_path()` signature unchanged |

---

## 5. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| ByteTrack rejects valid re-detection (IoU < 0.10 false rejection) | Low | Rejection only active after ≥3 coast frames; IoU 0.10 is very permissive for typical face movement |
| Velocity extrapolation moves crop off-frame | Low | `_subject_to_crop_center()` already clamps to frame bounds |
| Kalman drift over many coasting frames (45+) | Low | `is_alive(hold_frames=45)` expires track; falls to `last_subject` then default center |
| Performance overhead | Negligible | Pure Python math, no GPU, O(1) per frame |

---

## 6. Manual Verification Checklist

```
[ ] Static talking-head: crop center stable, no extra motion from prediction
[ ] Slow movement: crop follows smoothly, no jump at re-detection
[ ] Fast movement: prediction catches up within 2-3 frames
[ ] Subject occlusion (2s): coast holds predicted position, not static freeze
[ ] Subject reappears after occlusion: smooth re-lock without jump
[ ] No subject (motionless B-roll): legacy pixel-diff fallback still fires
[ ] Wide shot (OQ-4.1 full-range): ByteTrack correctly tracks small face
[ ] Render stable: full pipeline completes without error
```

---

## 7. Files Modified

| File | Change |
|---|---|
| `backend/app/services/motion_crop.py` | Add `_iou_xywh()`, `_ByteTrackSubject` class, wire into `build_subject_path()` and `build_subject_path_scene()` |

---

## 8. Commit Hash

`[pending]`

---

## 9. Push Confirmation

`[pending]`
