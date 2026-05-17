# PRODUCT STATE — QUALITY-UP2: Segment Intelligence Reform

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): segment intelligence reform`
**Status:** Shipped

---

## Summary

Five targeted reforms to clip selection and ranking. The pipeline no longer
optimizes purely for editing density. Interview, commentary, and late-payoff
content survive the selection pass. The output ranking explains itself in
terms creators recognize.

---

## Root Cause

The QUALITY-AUDIT1 report identified two compounding structural problems:

1. **`motion_score = scene_density × 1100`** — measures cut count, not visual
   energy. A talking-head segment with zero cuts scored 0 regardless of content
   quality.
2. **Hard eviction + wrong sort key** — if ≥3 clips hit motion_score ≥ 60,
   all others were discarded. Then the default sort used `(motion_score,
   viral_score)` with motion as the *primary* key, meaning viral_score was a
   tiebreaker at best.

Combined effect: the pipeline consistently selected the clips with the most
scene cuts from the first half of the video, regardless of what was in them.

---

## Part A — Motion Score Reform

**File:** `backend/app/services/viral_scorer.py`

### New `motion_score` formula

**Before:**
```python
motion_score = min(100, int(scene_density * 1100))
```

**After:**
```python
avg_trans_val = features.get("avg_transition_quality", 0.0)
motion_score = min(100, int(scene_density * 660 * max(0.1, avg_trans_val))) if seg_scenes else 0
```

`avg_transition_quality` is the average `transition_score` across all scene
cuts in the segment — already computed by `scene_detector._compute_transition_scores`
as a pixel-diff-based abruptness measure. No new computation required.

**Effect:** A segment scores high on motion only when it has both *frequent*
AND *energetic* cuts. Soft dissolves with many cuts score lower than hard
cuts with fewer. Content with no cuts scores 0 — correct, because
`motion_score` now measures visual energy, not editing volume.

### New `avg_transition_quality` feature in heuristic

**Before:** 10 features, `scene_density` weighted at 0.28.

**After:** 11 features, `avg_transition_quality` added at 0.10,
`scene_density` reduced to 0.18.

| Feature | Before | After | Change |
|---------|--------|-------|--------|
| `scene_density` | 0.28 | 0.18 | −0.10 |
| `n_scenes_norm` | 0.06 | 0.04 | −0.02 |
| `avg_transition_quality` | — | 0.10 | +0.10 NEW |
| `starts_at_cut` | 0.14 | 0.16 | +0.02 |
| `ends_at_cut` | 0.05 | 0.04 | −0.01 |
| `pacing_accel` | 0.09 | 0.07 | −0.02 |
| `duration_score` | 0.20 | 0.20 | — |
| `position_score` | 0.08 | 0.08 | — |
| `scene_quality` | 0.06 | 0.09 | +0.03 |
| `is_first` | 0.02 | 0.02 | — |
| `is_second` | 0.02 | 0.02 | — |
| **Total** | **1.00** | **1.00** | — |

### ML backward-compatibility

`_FEATURE_KEYS` is now an explicit 10-element list (unchanged from before)
rather than `list(_HEURISTIC_WEIGHTS.keys())`. A saved ML model trained on
10-feature vectors will load and predict correctly. The new
`avg_transition_quality` key is used by the heuristic path only.

---

## Part B — HIGH_MOTION Reform

**File:** `backend/app/orchestration/render_pipeline.py`

### Hard eviction replaced with preference boost

**Before:**
```python
high_motion = [s for s in scored if int(s.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE]
if len(high_motion) >= HIGH_MOTION_MIN_KEEP:
    scored = high_motion  # DISCARD all non-qualifying clips
```

**After:**
```python
_high_motion_count = sum(1 for s in scored if int(s.get("motion_score", 0)) >= HIGH_MOTION_MIN_SCORE)
_apply_motion_boost = _high_motion_count >= HIGH_MOTION_MIN_KEEP
# No eviction — all clips remain in pool
```

### Default sort fixed

**Before:** `(motion_score, viral_score)` descending — motion was the **primary**
sort key. Any clip with 0 motion always ranked last, regardless of viral_score.

**After:** `(viral_score + boost, motion_score)` descending — `viral_score`
is primary. High-motion clips receive a gentle +8 point boost when the
high-motion preference is active, but they do not suppress low-motion clips.

**Effect matrix:**

| Content type | Before | After |
|-------------|--------|-------|
| Interview/talking head | Evicted if any montage content present | Competes on viral_score |
| Commentary | Penalized by zero motion_score in sort | Ranks by content quality |
| Vlog | Mixed — survived if little competition | Full pool, viral primary |
| Montage/gaming | Preferred via eviction | Preferred via gentle boost |

---

## Part C — Content Profile Awareness

**File:** `backend/app/services/viral_scorer.py`

Each scored segment now carries a `content_type_hint` field inferred from
scene_density:

| scene_density | content_type_hint |
|--------------|------------------|
| < 0.03 cuts/s | `"interview"` |
| 0.03–0.08 | `"commentary"` |
| 0.08–0.18 | `"vlog"` |
| ≥ 0.18 | `"montage"` |

This field propagates through to `_compute_output_ranking_entry` (via
`components["content_type_hint"]`) and is used by `_output_ranking_reason`
to produce content-type-specific ranking text.

No ML classifier. No model inference. Pure scene statistics.

---

## Part D — Semantic Signals

**File:** `backend/app/services/viral_scorer.py`

Each scored segment now carries a `selection_reason` string — a
human-readable summary of the signals that drove its score:

Examples:
- `"Strong opening hook, High-quality spoken content"` (interview, starts at cut, good scene quality)
- `"Fast-paced editing, Ideal duration"` (montage, high scene_density, duration_score ≥ 0.85)
- `"Strong early position"` (early in video, position_score ≥ 0.85)

The signal is computed from actual feature values, not generated text.
Empty string if no signal is strong enough to name.

---

## Part E — Explainable Ranking

**File:** `backend/app/orchestration/render_pipeline.py`

`_output_ranking_reason()` now produces content-type-aware text:

| Condition | Before | After |
|-----------|--------|-------|
| hook_score ≥ 70, interview content | "Strong hook" | "Strong spoken hook" |
| retention_score ≥ 70, interview | "High retention" | "High engagement energy" |
| speech_density ≥ 60, interview | "Speech-heavy segment" | "Dense spoken content" |
| speech_density < 25, montage | "Low speech density" | "Visual montage" |
| No signals, montage | "Balanced clip signals" | "High-energy montage" |
| No signals, interview | "Balanced clip signals" | "Quality spoken content" |

All reasons are derived from real scores — no fabricated copy.

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| Frame-level optical flow motion energy | Requires video path in scorer; out of scope for this pass |
| Audio energy / speech emphasis detection | Requires pre-processing pass; QUALITY-UP3 scope |
| Content type override from payload | Creator-facing UI change; QUALITY-UP3 scope |
| Combined scoring path (motion boost) | Combined path uses viral_score as 0.80 weight — already content-quality-first |
| Hook language text detection | No transcription at scoring time; text-level signals are QUALITY-UP3 scope |
| HIGH_MOTION_MIN_SCORE threshold recalibration | New motion_score formula changes effective threshold; observe in production before adjusting |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/viral_scorer.py` | New motion_score formula; `avg_transition_quality` feature; `_HEURISTIC_WEIGHTS` rebalanced; `_FEATURE_KEYS` explicit; `content_type_hint`; `selection_reason` |
| `backend/app/orchestration/render_pipeline.py` | HIGH_MOTION eviction → preference boost; sort key fixed to viral_score primary; `_output_ranking_reason` content-type-aware; `content_type_hint` in components |
| `docs/render/PRODUCT_STATE_QUALITY_UP2.md` | This file |

---

## Manual QA Checklist

### Talking-head / Interview
- [ ] A video with zero or minimal scene cuts produces output clips (not empty)
- [ ] Interview clips rank competitively alongside higher-cut clips
- [ ] `content_type_hint` = "interview" visible in scored segment data

### Commentary / Reaction
- [ ] Emotional commentary clips (strong position/hook) survive selection
- [ ] `ranking_reason` shows "Strong spoken hook" or "Dense spoken content" (not generic)

### Tutorial
- [ ] Late-segment payoff clips (high position_ratio) survive due to position_score floor
- [ ] `selection_reason` shows "Strong early position" for early clips

### Montage / Gaming / Sports
- [ ] High-cut-density clips still rank highly (motion boost active)
- [ ] `ranking_reason` shows "High-energy montage" or "Visual montage" where appropriate
- [ ] `_high_motion_count` logged when boost activates

### Ranking quality
- [ ] Job log shows "high_motion_preference: N high-energy clips detected — preference boost applied"
  (no eviction message)
- [ ] No empty output (previously possible if HIGH_MOTION fired on < MIN_KEEP clips)

### Safety
- [ ] Normal render completes without error
- [ ] ML model (if present) still loads and scores correctly (10-feature vector unchanged)
- [ ] No crash on content with zero scene cuts
- [ ] Cancel, resume, and retry unaffected
- [ ] No new backend errors
