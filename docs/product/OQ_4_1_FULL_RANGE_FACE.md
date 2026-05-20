# OQ-4.1 — MediaPipe Full-Range Face Detection
## Reframe Quality Uplift

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** REFRAME QUALITY ONLY — no crop logic, no smoothing, no tracking, no render changes

---

## 1. Audit Findings

### Current MediaPipe configuration (pre-OQ-4.1)

**File:** `backend/app/services/motion_crop.py`, function `_get_mp_detector()`, line 87:

```python
_mp_face_detector = mp.solutions.face_detection.FaceDetection(
    model_selection=0,           # short-range model (≤2m), fastest CPU inference
    min_detection_confidence=0.5,
)
```

`model_selection=0` is the **short-range** MediaPipe model — optimized for faces within
approximately 2 meters of the camera. It is the fastest model and works well for
close-up talking-head shots (typical phone-held vlog distance).

### Problem

`model_selection=0` misses faces in:
- Wide shots (speaker 3–5m from camera)
- Small faces (zoomed-out B-roll with subject in frame)
- Multiple speakers where secondary speakers are farther back
- Podcast/interview setups filmed across a table

When MediaPipe returns no detections, the pipeline falls through to:
1. Haar cascade face detection (less accurate, more false positives)
2. Body detection (looser bounding box → imprecise crop center)
3. Legacy pixel-diff motion tracking (no subject awareness)
4. Frame center fallback

Each fallback tier produces worse framing than a true face detection. The root fix is
ensuring MediaPipe detects the face in the first place.

---

## 2. MediaPipe model_selection Values

| Value | Name | Detection range | Use case |
|---|---|---|---|
| `0` | Short-range | ≤ ~2m | Close-up vlog, selfie, handheld |
| `1` | Full-range | ≤ ~5m | Wide shots, interview across table, podcast, any fixed camera setup |

Both models:
- Return identical output format (`relative_bounding_box`)
- Have identical API (no signature change)
- Load as lazy singleton (initialized once, reused)

Full-range model performance:
- Slightly higher CPU cost per inference (marginally larger model, ~same latency at 0.30× frame scale)
- Same confidence threshold interface (`min_detection_confidence=0.5`)
- Better recall on small/distant faces at cost of negligible precision reduction

---

## 3. Implementation (OQ-4.1)

**Single change in `_get_mp_detector()`:**

```python
# Before:
model_selection=0,   # short-range model (≤2m)

# After:
model_selection=1,   # full-range model (≤5m) — detects wide shots and small faces
```

Also update the `logger.info` string from `model=short_range` to `model=full_range`.

**No other changes.** The entire crop logic, smoothing, velocity limiting, fallback
chain, scene tracking, and render pipeline are identical.

---

## 4. Compatibility Impact

| Component | Impact |
|---|---|
| `_detect_mediapipe_faces()` — detection function | None — same input/output format |
| `_detect_subjects_in_frame()` — detection hierarchy | None — only primary detection path improved |
| Haar cascade fallback | Reached less often — full-range model detects more faces |
| Body detection fallback | Reached less often — face detected where body was the best option before |
| Legacy pixel-diff fallback | Reached less often — fewer "no subject detected" cases |
| `_subject_to_crop_center()` | None — consumes (x,y,w,h) same as before |
| Gaussian smoothing | None — consumes crop centers same as before |
| Velocity limiter | None — unchanged |
| `render_motion_aware_crop()` | None — signature unchanged |
| Render pipeline call sites | None — all caller code unchanged |
| MotionCropConfig | None — no new fields |

---

## 5. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Full-range model detects faces in background of busy shots | Low | `_detect_subjects_in_frame()` picks the largest face with center preference — same selection logic as before |
| Confidence threshold (0.5) produces false positives with full-range | Low | Full-range model has similar precision to short-range at ≥0.5 confidence; lower confidence thresholds are where precision diverges |
| CPU overhead on mobile/low-spec servers | Negligible | Frame analysis already runs at 0.30× scale; full-range model is marginally larger |
| Close-up shots regress | None | Full-range model detects ≤2m faces with equal or better confidence than short-range |

---

## 6. Manual Verification Checklist

```
[ ] Log shows: mediapipe_face_detection_loaded model=full_range confidence_threshold=0.5
[ ] Wide-shot video (speaker 3-4m away): face detected, crop centers on speaker
[ ] Close-up talking-head (pre-OQ-4.1 baseline): face still detected, crop unchanged
[ ] Interview across table: both speakers detected when visible
[ ] MediaPipe unavailable: graceful Haar fallback unchanged (log: mediapipe_unavailable)
[ ] Render stable: full pipeline completes without error
```

---

## 7. Files Modified

| File | Change |
|---|---|
| `backend/app/services/motion_crop.py` | `model_selection=0` → `model_selection=1`; log string updated |

---

## 8. Commit Hash

`[pending]`

---

## 9. Push Confirmation

`[pending]`
