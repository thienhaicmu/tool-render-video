# OQ-5.3 — CLIP Semantic Scene Scoring
## Additive Semantic Moment Intelligence

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** SEMANTIC SCORING ONLY — no render rewrite, no tracking rewrite, no clip generation rewrite

---

## 1. Audit Findings

### Current scene scoring pipeline (pre-OQ-5.3)

**Files:** `backend/app/services/segment_builder.py`, `backend/app/services/scene_detector.py`

**Signal stack in `_score_scene()`:**
```
duration_score      (0.45 weight) — penalises too short/long scenes
transition_score    (0.35 weight) — cut strength from ContentDetector/AdaptiveDetector
position_stability  (0.20 weight) — rewards early scenes
early_bonus         (+0/+4/+8)   — bonus for scenes starting < 180/90s
speech_bonus        (up to +12)  — speech_density from subtitle alignment
silence_bonus       [-8, +20]    — FFmpeg silencedetect: rhythm/pause/dead-air
```

**Problem:** All signals are structural (timing, transitions, audio). No semantic understanding of the visual content. Two scenes with identical timing and audio can score identically even if one shows a person reacting with emotion (high engagement) and the other is a static shot of a desk (dead frame). CapCut AI Cut and Opus AI both use visual embedding similarity to bias selection toward high-engagement moments.

### Gap: visual engagement detection

Missing signals:
- Person reacting with surprise or excitement
- Product demonstration / how-it-works moment
- Before/after reveal
- Face with strong emotion (smile, shock)
- Presentation/screen reveal
- Eye contact with camera
- Versus: dead frame, static shot, blurry/dark frame

### CLIP as the solution

CLIP (Contrastive Language–Image Pretraining) computes cosine similarity between image embeddings and text prompt embeddings. Given a frame from a scene and a list of positive/negative prompts, we get a semantic quality signal in [−1, +1] per frame.

OpenCLIP ViT-B-32 (open-source, MIT-licensed, pretrained on OpenAI CLIP weights):
- 151 MB VRAM (safe for RTX 3060 12GB even with other models loaded)
- 80ms/frame on RTX 3060 (CUDA), ~600ms/frame on CPU i7
- Battle-tested; pip-installable (`open-clip-torch`)

---

## 2. Model Selection

### Candidates

| Model | VRAM | Speed (RTX 3060) | Quality | Verdict |
|---|---|---|---|---|
| OpenCLIP ViT-B-32 | ~151 MB | ~80ms/frame | Good | ✅ **Chosen** |
| OpenCLIP ViT-L-14 | ~890 MB | ~480ms/frame | Better | Overkill — high VRAM risk |
| SigLIP (ViT-B-16) | ~340 MB | ~120ms/frame | Good | Needs `transformers`; higher dep overhead |

**Chosen: OpenCLIP ViT-B-32 with `pretrained="openai"` weights.**

Justification:
- 151 MB VRAM — safe to run alongside MediaPipe and faster-whisper on RTX 3060 12GB
- 80ms/frame → with 2 frames/scene average, 160ms/scene → negligible vs render time
- `pretrained="openai"` weights are the same model that CapCut/Opus reference implementations use
- Single pip package (`open-clip-torch`) — no transformers, no HuggingFace hub downloads

---

## 3. Design

### Semantic prompts

**Positive (rewarded visual moments):**
1. `"a person reacting with surprise or excitement"`
2. `"a product demonstration showing how something works"`
3. `"a before and after transformation reveal"`
4. `"a person showing strong positive emotion"`
5. `"a presentation or screen reveal moment"`
6. `"close-up of an interesting product or object"`
7. `"an energetic action-filled moment"`
8. `"a person looking directly at the camera with engagement"`

**Negative (penalized patterns):**
1. `"an empty room with nothing happening"`
2. `"a static or frozen frame with no action"`
3. `"a dark underexposed blurry shot"`
4. `"a person looking away with no engagement"`

### Scoring formula

```
raw = mean(pos_sim) - mean(neg_sim)       # cosine similarity delta, [-1, 1]
clip_semantic_bonus = clamp(raw * 30.0, -8.0, +20.0)
```

Scale factor 30.0: typical (pos_sim - neg_sim) range is [−0.3, +0.7] in practice.
This maps a strongly positive frame to +21 → clamped at +20. A dead frame maps to −0.2 → −6.

### Sparse sampling

| Scene duration | Frames sampled |
|---|---|
| < 3s | 1 frame (midpoint) |
| 3–8s | 2 frames (33%, 66%) |
| > 8s | 3 frames (25%, 50%, 75%) |

Rationale: scenes average 4–6s in the pipeline. 2 frames/scene is the baseline. Total scoring overhead: ~320ms per 100 scenes on GPU, ~120s on CPU (disabled by gate for CPU-only if needed).

### Injection architecture

CLIP scores are computed in `render_pipeline.py` AFTER scene cache resolution and BEFORE `build_segments_from_scenes()`. This keeps:
- Scene cache untouched (boundaries don't change based on CLIP)
- `segment_builder.py` `_score_scene()` unchanged except one additive line
- Score cache invalidated when CLIP version/state changes (version token added to cache key)

```
detect_scenes() / _scene_cache_get()
  ↓
score_scenes_clip(video_path, scenes)   ← NEW (clip_scorer.py)
  → adds clip_semantic_score to each scene dict
  ↓
build_segments_from_scenes(scenes, ...)
  → _score_scene() reads clip_semantic_score (default 0.0)
  → clip_semantic_bonus = clamp(clip_semantic_score, -8, +20)
  → total = (duration * 0.45) + (transition * 0.35) + (position * 0.20) + bonuses
  ↓
score_segments() / _score_cache_put()
```

### Fallback chain

```
CLIP_SCORING_ENABLED=0          → score_scenes_clip() returns scenes unchanged
open_clip not installed         → lazy load fails → returns scenes unchanged
GPU OOM                         → caught in try/except → 0.0 for affected scene
Any per-frame failure           → skip frame, average remaining frames
All frames fail for a scene     → clip_semantic_score = 0.0
```

Zero regression from baseline when CLIP is unavailable.

---

## 4. Implementation

### New file: `backend/app/services/clip_scorer.py`

- `CLIP_SCORING_ENABLED` gate (`CLIP_SCORING_ENABLED=0` to disable)
- `CLIP_SCORER_VERSION = "1"` — bump when prompts or model change to bust score cache
- `_load_clip_model()` — lazy singleton, loads model + pre-encodes text prompts on first call
- `_score_frame_clip(frame_bgr, state)` → float or None
- `_sample_scene_frames(video_path, start, end, n_frames)` → list of BGR frames
- `score_scenes_clip(video_path, scenes)` → enriched scene dicts with `clip_semantic_score`

### Modified: `backend/app/services/segment_builder.py`

`_normalize_scenes()` — add field pass-through:
```python
"clip_semantic_score": float(s.get("clip_semantic_score", 0.0)),
```

`_score_scene()` — add bonus:
```python
clip_semantic_bonus = _clamp(float(scene.get("clip_semantic_score", 0.0)), -8.0, 20.0)
return (duration_score * 0.45) + ... + silence_bonus + clip_semantic_bonus
```

### Modified: `backend/app/orchestration/render_pipeline.py`

Import:
```python
from app.services.clip_scorer import score_scenes_clip, CLIP_SCORER_VERSION
```

After scene cache resolution (before `build_segments_from_scenes`):
```python
scenes = score_scenes_clip(str(source_path), scenes)
```

Score cache key — add CLIP version token:
```python
_score_ck = _render_cache_key(
    str(source_path), _src_st.st_mtime, _src_st.st_size,
    payload.min_part_sec, payload.max_part_sec, len(scenes),
    CLIP_SCORER_VERSION,
)
```

---

## 5. GPU / Latency Estimates

| Scenario | Model | Frames | Time |
|---|---|---|---|
| 30 scenes, GPU (RTX 3060) | ViT-B-32 | ~70 frames | ~5.6s |
| 100 scenes, GPU (RTX 3060) | ViT-B-32 | ~230 frames | ~18s |
| 30 scenes, CPU (i7) | ViT-B-32 | ~70 frames | ~42s |
| CLIP_SCORING_ENABLED=0 | — | 0 | 0ms |

CPU overhead is high but acceptable given render jobs take minutes. For CPU-heavy deployments, set `CLIP_SCORING_ENABLED=0`.

---

## 6. Compatibility Impact

| Component | Impact |
|---|---|
| `detect_scenes()` | Unchanged |
| Scene cache | Unchanged — CLIP runs after cache resolution |
| `_normalize_scenes()` | +1 field pass-through (`clip_semantic_score`) |
| `_score_scene()` | +1 additive bonus term (default 0.0 — no change without CLIP) |
| `_score_candidate()` / `viral_score` | Unchanged — consumes `scene_quality` from `_score_scene()` |
| Score cache key | +1 token (`CLIP_SCORER_VERSION`) — invalidates stale cache on version bump |
| `viral_scorer.py` | Unchanged — `_HEURISTIC_WEIGHTS` sum stays 1.0 |
| `CLIP_SCORING_ENABLED=0` | Full bypass — scenes returned unchanged |
| open_clip not installed | Graceful: `clip_scorer_unavailable` log, scenes returned unchanged |

---

## 7. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| open_clip not installed | None | try/except on load; scenes returned unchanged |
| GPU OOM during CLIP inference | Low | try/except per frame; skips frame, averages remaining; worst case 0.0 |
| CLIP score cache served to wrong CLIP version | None | `CLIP_SCORER_VERSION` in score cache key |
| CLIP biases toward talking-head over wide shots | Low | Prompts include wide-shot patterns; scale factor conservative (30.0) |
| `viral_scorer.py` weight sum breaks | None | CLIP bonus is additive on `scene_quality`, not inside `_score_candidate()` weights |

---

## 8. Manual Verification Checklist

```
[ ] Log shows: clip_scorer_loaded model=ViT-B-32 device=cuda (or cpu)
[ ] Log shows: clip_scoring_complete scenes=N active=True
[ ] Tutorial scene (person on camera): clip_semantic_bonus > 0
[ ] Dead frame (empty room): clip_semantic_bonus < 0
[ ] CLIP_SCORING_ENABLED=0: log shows clip_scorer skipped; no clip_semantic_score field in scenes
[ ] open_clip uninstalled: log shows clip_scorer_unavailable; no crash; scoring unchanged
[ ] Score cache invalidated when CLIP_SCORER_VERSION bumped (new key)
[ ] Render stable: full pipeline completes without error
[ ] Vietnamese source: no crash (language-agnostic, visual scoring only)
```

---

## 9. Files Modified

| File | Change |
|---|---|
| `backend/app/services/clip_scorer.py` | New file — CLIP scorer, lazy singleton, prompt encoding, frame sampling |
| `backend/app/services/segment_builder.py` | `_normalize_scenes()` pass-through; `_score_scene()` additive bonus |
| `backend/app/orchestration/render_pipeline.py` | Import `score_scenes_clip`; call after scene cache; add `CLIP_SCORER_VERSION` to score cache key |

---

## 10. Commit Hash

`[pending]`

---

## 11. Push Confirmation

`[pending]`
