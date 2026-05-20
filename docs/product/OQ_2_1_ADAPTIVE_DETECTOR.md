# OQ-2.1 — AdaptiveDetector Activation
## Scene Detection Quality Uplift

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** SCENE DETECTION ONLY — no scoring, no ranking, no render logic changes

---

## 1. Audit Findings

### Current detector stack (pre-OQ-2.1)

```
SceneManager
  └── ContentDetector(threshold=28.0)   ← ACTIVE, primary
  └── AdaptiveDetector()                ← PARTIALLY WIRED, effectively dormant
```

**`ContentDetector(threshold=28.0)`** — active, hard-cut detection only.
Fires when the histogram delta between adjacent frames exceeds 28.0.
Reliable for abrupt cuts; blind to gradual transitions and fades.

**`AdaptiveDetector()` (pre-OQ-2.1)**:
```python
if _HAS_ADAPTIVE:
    try:
        scene_manager.add_detector(_AdaptiveDetector())   # no parameters
    except Exception:
        pass                                              # silent failure
```
Three problems:
- **No explicit parameters** — uses PySceneDetect library defaults, which have not been tuned
  against this pipeline's threshold values.
- **Silent failure** — if the constructor or add_detector raises (e.g. API version mismatch),
  it is swallowed completely; no log, no fallback.
- **No activation gate** — no env var to disable or confirm it is running.

---

## 2. AdaptiveDetector Mechanics

AdaptiveDetector computes a rolling average of content-change scores over a sliding window.
A cut fires when the frame's content score exceeds `adaptive_threshold × rolling_average`.

Key difference vs ContentDetector:
- ContentDetector: fires when absolute Δ > fixed threshold.
- AdaptiveDetector: fires when relative Δ > N × local baseline.

This makes AdaptiveDetector sensitive to gradual scene changes that ContentDetector misses:
- Cross-fades (slow visual transition over 10–30 frames)
- Soft cuts (low-contrast scene boundary)
- Fade-in / fade-out

PySceneDetect parameters used:

| Parameter | Default | Our value | Rationale |
|---|---|---|---|
| `adaptive_threshold` | 3.0 | 3.0 | Keep default — 3× local average is a safe trigger |
| `min_content_val` | 15.0 | 15.0 | Keep default — avoids micro-flicker noise |
| `min_scene_len` | 15 frames | (library default) | Prevents sub-0.5s scene fragments |
| `window_width` | 2 | (library default) | 2-frame look-ahead/look-behind |

---

## 3. Duplication Risk Analysis

Both ContentDetector and AdaptiveDetector fire independently.
PySceneDetect's SceneManager merges all cut points from all detectors by enforcing `min_scene_len`
between consecutive cuts — if ContentDetector fires at frame 100 and AdaptiveDetector fires at
frame 101, SceneManager produces ONE cut (the earlier one).

For scene transitions that are abrupt (hard cuts), ContentDetector fires first;
AdaptiveDetector may also fire within a few frames. SceneManager deduplication prevents doubling.

For gradual transitions, ContentDetector does NOT fire; AdaptiveDetector fires alone.
Net effect: AdaptiveDetector adds new boundaries at gradual transitions only.

**Scene explosion guard** — log total scene count after detection so any regression
is immediately visible in logs.

---

## 4. Implementation Changes (OQ-2.1)

### A. Explicit parameters

Replace:
```python
scene_manager.add_detector(_AdaptiveDetector())
```
With:
```python
scene_manager.add_detector(_AdaptiveDetector(
    adaptive_threshold=3.0,
    min_content_val=15.0,
))
```

Both values match PySceneDetect defaults — this is a no-op numerically but makes the
configuration explicit, documentable, and tunable without a library default change.

### B. Replace silent failure with warning log

Replace:
```python
except Exception:
    pass
```
With:
```python
except Exception as _adaptive_exc:
    logger.warning("scene_adaptive_add_failed: %s", _adaptive_exc)
```

### C. Activation gate

Add `SCENE_ADAPTIVE_ENABLED` env var (default `"1"`).
Set to `"0"` to fall back to ContentDetector-only behavior.

### D. Activation logging

Log `scene_adaptive_detector_active` when AdaptiveDetector is successfully added.
Log total scene count at end of `detect_scenes()`.

---

## 5. Compatibility Impact

| Component | Impact |
|---|---|
| Hard-cut scenes | None — ContentDetector(threshold=28) unchanged |
| Gradual transitions | Improved — new boundaries appear at fades/cross-fades |
| `transition_score` | Correct — `_compute_transition_scores()` samples pixel delta at detected boundary, independent of which detector found it |
| `scene_density` | May increase slightly for videos with gradual cuts — correctly reflects true scene rhythm |
| Content-type inference (viral_scorer) | Stable — thresholds span [0.03, 0.18] cuts/s; adding a few gradual boundaries per minute does not shift content type |
| Segment builder | No change — consumes scene list same way |
| Render pipeline | No change — `detect_scenes()` signature unchanged |
| 72h scene cache | Invalidates naturally — new detection run on cache miss |

---

## 6. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Scene explosion (too many scenes) | Low | PySceneDetect min_scene_len deduplication; log total count for monitoring |
| AdaptiveDetector API change in library update | Low | try/except now logs warning instead of silent pass; falls back to ContentDetector-only |
| Content-type misclassification | Negligible | Boundaries added by AdaptiveDetector are real scene changes; density thresholds have wide bands |
| SCENE_ADAPTIVE_ENABLED=0 | None | Reverts to pre-OQ-2.1 ContentDetector-only behavior |

---

## 7. Manual Verification Checklist

```
[ ] Hard-cut video: scene count same as pre-OQ-2.1 (ContentDetector dedup)
[ ] Fade/cross-fade video: new scene boundaries appear at transition midpoints
[ ] Log shows: scene_adaptive_detector_active
[ ] Log shows: scene_count total=N
[ ] SCENE_ADAPTIVE_ENABLED=0: AdaptiveDetector skipped, scene_count unchanged
[ ] AdaptiveDetector unavailable (ImportError): _HAS_ADAPTIVE=False, graceful fallback
[ ] Silent failure fixed: AdaptiveDetector constructor error → warning log, not silent
```

---

## 8. Files Modified

| File | Change |
|---|---|
| `backend/app/services/scene_detector.py` | Add explicit parameters, activation gate, warning log, scene count log |

---

## 9. Commit Hash

`[pending]`

---

## 10. Push Confirmation

`[pending]`
