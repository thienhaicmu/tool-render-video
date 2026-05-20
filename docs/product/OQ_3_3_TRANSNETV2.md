# OQ-3.3 — TransNetV2 Integration
## Premium Scene Boundary Detection

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** SCENE DETECTION ONLY — no ranking, no render, no clip logic changes

---

## 1. Audit Findings

### Current detector stack (post-OQ-2.1)

```
SceneManager
  ├── ContentDetector(threshold=28.0)    active — hard-cut histogram delta
  └── AdaptiveDetector(adaptive=3.0)     active — relative delta vs rolling avg

Post-SceneManager enrichment:
  _compute_transition_scores()           pixel-delta score per boundary
  _compute_silence_features()            FFmpeg silencedetect per scene (OQ-3.2)
```

**Limitations of heuristic detectors:**

| Cut type | ContentDetector | AdaptiveDetector | TransNetV2 |
|---|---|---|---|
| Hard abrupt cut | ✅ | ✅ | ✅ |
| Gradual fade/dissolve | ❌ | ✅ | ✅ |
| Semantic editorial cut (low pixel change, new scene) | ❌ | ❌ | ✅ |
| Creator pacing boundary (B-roll switch) | ❌ | ❌ | ✅ |
| Jump cut in fast montage | ✅ | ✅ | ✅ |

ContentDetector and AdaptiveDetector both use histogram-based pixel deltas — they are
blind to semantic boundaries where the visual change is subtle (matched lighting, same
background, same color palette) but the editorial intent is a scene change.

TransNetV2 is a 3D convolutional neural network trained on ~1M annotated scene boundaries.
It outputs per-frame transition probabilities and detects cuts that heuristics miss.

---

## 2. TransNetV2 Architecture

**Model:** TransNetV2 (Soucek & Lokoč, 2020)
**Weights:** ~17MB (PyTorch)
**Input:** 25-frame sequences, downsampled to 27×48 px
**Output:** Per-frame transition probability [0, 1]
**Threshold:** 0.5 (default) — tunable via `TRANSNETV2_THRESHOLD`

**VRAM budget on RTX 3060 12GB:**

| Component | VRAM |
|---|---|
| XTTS v2 (when loaded) | ~3.2 GB |
| TransNetV2 inference | ~0.5–1.0 GB |
| Combined peak | ~4.2–4.5 GB |
| Available headroom | ~7.5–7.8 GB |

TransNetV2 inference is sequential (one job at a time). The model instance is created
locally in `_transnetv2_detect()` and released when the function returns.
No VRAM semaphore needed — scene detection is not concurrent with XTTS.

**Speed:**
- CPU: ~40-80 frames/sec → 10-min video in ~40-80s (acceptable; cached for 72h)
- GPU: ~500+ frames/sec → 10-min video in ~4s

Device selection: `TRANSNETV2_DEVICE=auto` (default) → CUDA if available, else CPU.

---

## 3. Integration Architecture (OQ-3.3)

TransNetV2 is **additive only**. It cannot remove existing boundaries from
ContentDetector/AdaptiveDetector. It only adds boundaries that both heuristic
detectors missed.

### Pipeline position

```
detect_scenes():
  1. SceneManager: ContentDetector + AdaptiveDetector → scene_list (FrameTimecode)
  2. _compute_transition_scores()  → per-boundary pixel-delta scores
  3. Build _results: [{start, end, transition_score}, ...]      ← heuristic boundaries
  4. [NEW OQ-3.3] _transnetv2_detect() → tv2_cuts (seconds list)
  5. [NEW OQ-3.3] _merge_transnetv2_cuts() → merged _results    ← +semantic boundaries
  6. _compute_silence_features() → +silence_score per scene     ← unchanged
```

### New function: `_transnetv2_detect(video_path, fps)`

- Imports `transnetv2.TransNetV2` lazily (no module-level import)
- Runs `model.predict_video(video_path)` → per-frame probabilities
- Converts scene tuples to cut timestamps in seconds: `start_frame / fps`
- Returns `[]` on ImportError, RuntimeError, or any failure
- Guarded by `TRANSNETV2_ENABLED=1` env var (default on)
- Logs: `transnetv2_detect_complete cuts=N threshold=T` on success

### New function: `_merge_transnetv2_cuts(base_results, tv2_cuts, video_path, total_duration)`

**Deduplication:** merge within `MIN_MERGE_GAP = 0.5s` — two cuts within 0.5s of each
other are treated as the same boundary (keeps earlier). Prevents near-duplicate scenes.

**Transition scores for new boundaries:** existing boundaries retain their pixel-delta
scores; new TransNetV2 boundaries get scores from `_compute_transition_score_at_sec()`
(same pixel-delta method, seconds-based seeking).

**Scene explosion guard:** if merged count > `base_count × 4` (or > 50 absolute),
the merge is aborted and base_results returned unchanged with a warning log.

**Minimum scene length:** 0.5s after merge (prevents sub-second fragments).

### New function: `_compute_transition_score_at_sec(video_path, cut_sec)`

Like existing `_compute_transition_scores()` but takes seconds instead of FrameTimecode.
Used exclusively for TransNetV2-added boundaries.

---

## 4. Configuration

| Env var | Default | Effect |
|---|---|---|
| `TRANSNETV2_ENABLED` | `"1"` | Set `"0"` to disable completely |
| `TRANSNETV2_THRESHOLD` | `"0.5"` | Cut probability threshold [0.0, 1.0] |

Device is auto-detected via `torch.cuda.is_available()` — no separate env var needed.

---

## 5. Scene Cache Implications

The 72h scene cache in `render_pipeline.py` caches the output of `detect_scenes()`.
TransNetV2 results are included in that output — once computed, results are cached and
not rerun until the cache expires or the source file changes (keyed to path + mtime + size).

On first run per video: full detection time (ContentDetector + AdaptiveDetector + TransNetV2).
On subsequent runs (cache hit): zero detection time.

---

## 6. Compatibility Impact

| Component | Impact |
|---|---|
| ContentDetector(28.0) | None — unchanged |
| AdaptiveDetector(3.0) | None — unchanged |
| `_compute_transition_scores()` | None — runs before TransNetV2 merge |
| `_compute_silence_features()` | None — runs after merge, sees merged scene list |
| `_normalize_scenes()` in segment_builder | None — consumes dict format, same as before |
| `_score_scene()` | None — silence_score/speech_density fields still present |
| `score_segments()` in viral_scorer | None — consumes segment dicts |
| `detect_scenes()` signature | None — unchanged externally |
| 72h scene cache | Valid — TransNetV2 boundaries included in cached output |
| Render pipeline | None — `detect_scenes()` return format unchanged |
| `TRANSNETV2_ENABLED=0` | Full revert — ContentDetector+AdaptiveDetector only |
| `transnetv2` not installed | Graceful fallback — `_HAS_TRANSNETV2=False`, no error |

---

## 7. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Scene explosion from TransNetV2 false positives | Low | Explosion guard: >4× base count → abort merge, warning log |
| TransNetV2 semantic cuts shift scene_density for content-type inference | Low | Only adds missed boundaries; density thresholds have wide bands [0.03,0.18] |
| VRAM exhaustion on RTX 3060 when XTTS also loaded | Low | Scene detection runs before XTTS (separate pipeline stages); TransNetV2 ~1GB vs 12GB total |
| TransNetV2 ImportError | None | `_HAS_TRANSNETV2=False` path continues with ContentDetector+Adaptive |
| CPU TransNetV2 latency | Acceptable | 72h cache amortizes 40-80s CPU cost; GPU reduces to ~4s |

---

## 8. Manual Verification Checklist

```
[ ] transnetv2 not installed: _HAS_TRANSNETV2=False, scene detection unchanged
[ ] TRANSNETV2_ENABLED=0: detect_scenes() behavior identical to pre-OQ-3.3
[ ] Hard-cut video: same boundaries as ContentDetector (TransNetV2 agrees, deduped)
[ ] Editorial cut video: new boundaries detected that ContentDetector missed
[ ] Log shows: transnetv2_detect_complete cuts=N threshold=0.50
[ ] Log shows: transnetv2_merge_complete base=N merged=M new_boundaries=K
[ ] Log shows: scene_enrichment_complete silence_data=True (unchanged from OQ-3.2)
[ ] Explosion guard: simulated 5x scene count → reverts to base, warning logged
[ ] VRAM: RTX 3060 handles TransNetV2 + XTTS without OOM
[ ] Render stable: full pipeline runs to completion with TransNetV2 active
```

---

## 9. Files Modified

| File | Change |
|---|---|
| `backend/app/services/scene_detector.py` | Add `_HAS_TRANSNETV2`, `_compute_transition_score_at_sec()`, `_transnetv2_detect()`, `_merge_transnetv2_cuts()`; wire into `detect_scenes()` |

---

## 10. Commit Hash

`[pending]`

---

## 11. Push Confirmation

`[pending]`
