# PRODUCT STATE — QUALITY-UP10B: Quality Multiplier Fixes

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): quality multiplier fixes`
**Status:** Shipped

---

## Summary

Four surgical fixes derived from QUALITY-UP10A's code-level validation audit.
No new models. No pipeline reorder. No architecture change. No new dependencies.

Each fix targets a systemic failure that silently neutralised multiple previous quality
upgrades (UP1A through UP8) for large categories of creator content.

---

## Part A — Feature Activation Integrity

**File:** `backend/app/models/schemas.py`

### Problem

Two of the highest-impact quality improvements from the UP1A–UP8 chain were gated behind
opt-in flags that defaulted to `False`. Any render that did not explicitly pass these flags
received none of the improvement.

| Flag | Before | After | Dormant upgrade |
|------|--------|-------|-----------------|
| `loudnorm_enabled` | `False` | `True` | UP1A Part A — -14 LUFS audio compliance |
| `remotion_hook_intro` | `False` | `True` | UP8 — 4 intro personalities |

### Effect

**loudnorm_enabled = True:**
Every render now applies the full audio polish chain:
`highpass(80Hz) → loudnorm(-14 LUFS) → acompressor(ratio=2) → alimiter(limit=0.95)`

This is the -14 LUFS platform compliance fix that was shipped in UP1A but never activated
by default. Renders previously shipped at source loudness; platforms (TikTok, Reels,
YouTube Shorts) would re-amplify, compressing dynamic range and risking distortion.

**remotion_hook_intro = True:**
Every render now generates an intro clip (when `hook_apply_enabled` is set).
The four UP8 personalities (`viral_pop`, `clean_creator`, `story_cinematic`,
`gaming_energy`) are now active. Before this fix, the old hardcoded intro had been
removed by UP8 but the new personalities were never enabled — creators received no
intro at all.

### Override safety

Creators or integrations that explicitly pass `loudnorm_enabled=False` or
`remotion_hook_intro=False` in the render payload retain full opt-out capability.
The change only affects renders that relied on the schema default.

### Scope

One file. Two boolean defaults. Zero logic changes.

---

## Part B — Tutorial Content Type Recovery

**File:** `backend/app/services/viral_scorer.py`

### Problem

`score_segments()` inferred only 4 content types from scene density alone. The type
`"tutorial"` was never produced, despite being listed in every downstream quality table
(UP4 pacing, UP5 motion crop, UP6 subtitle, UP7 TTS, UP8 intro).

Tutorial content (screen recordings, explainer videos, screen+facecam) typically had
scene density in the 0.08–0.18 range → classified as `"vlog"` → received:
- `story` subtitle preset instead of `clean`
- `story_cinematic` intro instead of `clean_creator`
- Vlog pacing (2.0s max trim) instead of tutorial pacing (1.5s max trim)
- `+0%` TTS rate instead of `-8%` (deliberate)
- Vlog motion crop (1.0× tracking speed) instead of tutorial (2.0× interval, slower/smoother)

All five systems simultaneously wrong. Every previous quality upgrade degraded for
tutorial creators.

### Fix: Weighted tutorial likelihood heuristic

A second-pass classification added after the 4-bucket density assignment.
No new models. No Whisper rerun. Uses signals already computed in `extract_features()`.

**Signal 1 — Steady editing rhythm** (`pacing_accel`, weight 0.40):
`pacing_accel` measures whether cut density accelerates across the clip. Tutorial content
has uniform, deliberate pacing (low acceleration). Commentary and reaction content tends
to build toward a punchline (higher acceleration).

`_steady = max(0.0, 1.0 - features["pacing_accel"] / 0.40)`

At `pacing_accel = 0.0` (perfectly uniform): `_steady = 1.0`
At `pacing_accel = 0.40` (moderate acceleration): `_steady = 0.0`

**Signal 2 — Sharp/hard cuts** (`avg_transition_quality`, weight 0.60):
`avg_transition_quality` is the average pixel-delta magnitude at each scene cut boundary,
normalised to [0.1, 1.0]. Screen recordings produce highly abrupt cuts (UI state changes
produce maximum pixel delta). Natural vlog/commentary cuts are softer.

`_sharp = min(1.0, avg_trans_val / 0.65)`

At `avg_trans_val = 0.65` (hard cut threshold): `_sharp = 1.0`
At `avg_trans_val = 0.30` (soft cut): `_sharp = 0.46`

**Combined likelihood:**

```python
_tutorial_likelihood = 0.60 * _sharp + 0.40 * _steady
```

**Thresholds:**
- Within `"vlog"` bucket (density 0.08–0.18): fires when `likelihood >= 0.70`
- Within `"commentary"` bucket (density 0.03–0.08): fires when `likelihood >= 0.75` (more conservative)

**Guard:** requires `len(seg_scenes) >= 3` — minimum cuts needed for a meaningful
transition quality signal. Segments with fewer than 3 cuts are too sparse to classify reliably.

**Does NOT fire in:**
- `"interview"` bucket (< 0.03 density) — not enough cuts to compute transition quality
- `"montage"` bucket (≥ 0.18 density) — too fast-paced to be tutorial

### Selection reason update

`selection_reason` now emits `"Steady instructional pacing"` for tutorial segments
instead of falling through to the montage/vlog logic.

### speech_density_score honesty

The existing `speech_density_score` formula (`min(100, 45 + len(seg_scenes) * 3)`) was
a scene-count proxy — it measured cut frequency, not speech content.

This is now a two-path computation:

1. **Real speech data path:** If the segment builder computed a real `speech_density_score`
   via `build_segments_from_scenes_with_subtitles()` (SRT coverage ratio × 100), that value
   is used directly. This path fires on re-renders when prior transcription output is available.

2. **Proxy fallback:** When no real speech data exists (first renders, no SRT available),
   the existing scene-count formula is preserved unchanged. No regression.

```python
_real_speech = float(seg.get("speech_density_score", 0.0))
_speech_density_score = int(_real_speech) if _real_speech > 0 else min(100, 45 + len(seg_scenes) * 3)
```

### Downstream effect of tutorial classification

Once `content_type_hint = "tutorial"` is inferred, every quality system unlocks correctly:

| System | Before (vlog default) | After (tutorial) |
|--------|-----------------------|-----------------|
| Subtitle preset (UP6) | `story` | `clean` |
| Intro preset (UP8) | `story_cinematic` | `clean_creator` |
| Micro pacing (UP4) | db=±0, mul=1.0, max=2.0s | db=−4, mul=1.40, max=1.5s |
| Motion crop (UP5) | 1.0× interval, 1.00× EMA | 2.0× interval, 0.65× EMA |
| TTS rate (UP7) | `+0%` | `−8%` |
| TTS pause style (UP7) | `normal` | `deliberate` |
| Story arc build order (UP3) | chronological (same) | chronological (correct) |

All downstream unlocks are zero-code changes — every system was already wired for
`"tutorial"`. The fix is purely the inference gate.

### Observability

Debug log on tutorial inference:
```
content_type_hint=tutorial inferred seg=[12.3,82.1] scene_density=0.112
avg_tq=0.78 pacing_accel=0.08 likelihood=0.75
```

---

## Part C — Manual Voice Content Type

**File:** `backend/app/orchestration/render_pipeline.py`

### Problem

The manual voice TTS path (`voice_source == "manual"`) fired at line 1604 with a
hardcoded `content_type="vlog"`. This was before segment scoring, so `content_type_hint`
from the scored segments was not yet available.

Tutorial creators writing a script got a +0% rate and `normal` pause style instead of
-8% rate and `deliberate` pauses. Commentary creators got neutral instead of +10%/light.

### Fix

Derive content type from `payload.subtitle_style` — the best creator-intent signal
available before segment scoring runs.

```python
_manual_voice_ct = {
    "viral":  "commentary",
    "clean":  "tutorial",
    "story":  "vlog",
    "gaming": "montage",
}.get((payload.subtitle_style or "").strip().lower(), "vlog")
```

**Mapping logic:** The subtitle style was chosen by the creator (or auto-defaulted from
their last render's content type). It is the strongest available proxy for content intent
at this point in the pipeline. The UP6 content→style mapping is simply reversed.

| Creator chose subtitle | Inferred voice content_type | TTS rate | Pause style |
|------------------------|----------------------------|----------|-------------|
| `viral` | `commentary` | `+10%` | `light` |
| `clean` | `tutorial` | `−8%` | `deliberate` |
| `story` | `vlog` | `+0%` | `normal` |
| `gaming` | `montage` | `+12%` | `light` |
| (unset / other) | `vlog` | `+0%` | `normal` |

### Override safety

If the creator explicitly set `voice_rate` to a non-default value (`!= "+0%"`),
`_effective_rate_for()` in `tts_service.py` honours the creator's rate exactly.
The content-type nudge only fires on the default `+0%` rate. Override path is unchanged.

### Scope

One inference block and one parameter change at the manual voice call site.
No pipeline reorder. No new dependencies.

---

## Part D — Ranking Reason: Tutorial Support

**File:** `backend/app/orchestration/render_pipeline.py`

### Problem

`_output_ranking_reason()` checked for `content_type in ("interview", "commentary", "podcast")`
in two places, and `content_type in ("interview", "commentary")` in the fallback.
Tutorial was not included — clips correctly inferred as tutorial would receive generic
reasons (`"Balanced clip signals"`) instead of content-aware ones.

### Fix

Added `"tutorial"` to all spoken-content checks in `_output_ranking_reason`:

| Condition | Before | After |
|-----------|--------|-------|
| hook_score ≥ 70, spoken types | `"Strong spoken hook"` for interview/commentary/podcast | + tutorial |
| retention_score ≥ 70, interview | `"High engagement energy"` | + tutorial |
| speech_density ≥ 60, spoken types | `"Dense spoken content"` | + tutorial |
| fallback, spoken types | `"Quality spoken content"` for interview/commentary | + tutorial |

---

## Parameter Comparison

| Scenario | Before UP10B | After UP10B |
|----------|-------------|-------------|
| Tutorial (screen recording) | content_type=vlog, story subtitle, story intro, vlog TTS | content_type=tutorial, clean subtitle, clean_creator intro, -8% TTS |
| Tutorial (talking-head explainer) | content_type=commentary, viral subtitle, viral_pop intro, +10% TTS | content_type=tutorial, clean subtitle, clean_creator intro, -8% TTS |
| Commentary (tight edits) | No change | No change — stays commentary |
| Vlog (natural cuts) | No change | No change — tutorial threshold not met for soft cuts |
| Montage/gaming | No change | No change — density ≥0.18 → montage |
| Interview/podcast | No change | No change — density <0.03 → interview |
| Audio on any render | Source loudness (loudnorm dormant) | -14 LUFS applied by default |
| Intro on any render | No intro (remotion_hook_intro dormant) | Content-type intro by default |
| Manual voice on tutorial | +0% vlog rate | -8% deliberate rate when subtitle_style=clean |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| "gaming" as inferable type | Gaming maps to montage which gets identical treatment (gaming_energy intro, gaming subtitle) — no practical gap |
| "story" as inferable type | Story maps to vlog which gets near-identical treatment (story subtitle, story_cinematic intro) — +3% rate difference is below perceptual threshold |
| Tutorial detection via audio/speech signal | Would require pre-scoring Whisper pass; visual signals are sufficient for screen recording detection |
| Per-clip adaptive re-detection of tutorial | Current per-segment inference is sufficient; no batch reclassification needed |
| Narration re-generation when content_type becomes known post-scoring | Manual voice fires before scoring; deferring the TTS call requires pipeline reorder. Subtitle-style proxy is sufficient. |
| speech_density_score formula replacement | Proxy formula kept as fallback when SRT data unavailable; this is correct behaviour for first renders |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/models/schemas.py` | `loudnorm_enabled: bool = True`, `remotion_hook_intro: bool = True` |
| `backend/app/services/viral_scorer.py` | Tutorial likelihood heuristic; `selection_reason` tutorial branch; `speech_density_score` real-data path |
| `backend/app/orchestration/render_pipeline.py` | Manual voice content_type from subtitle_style; `_output_ranking_reason` tutorial support |
| `docs/render/PRODUCT_STATE_QUALITY_UP10B.md` | This file |

---

## Manual QA Checklist

### Part A — Feature activation

- [ ] Normal render (no explicit flags): job log shows `loudnorm_applied=True`
- [ ] Normal render with hook enabled: intro generated (log `hook_intro_requested`)
- [ ] Render with `loudnorm_enabled=False` in payload: loudnorm skipped (log absent)
- [ ] Render with `remotion_hook_intro=False` in payload: no intro generated
- [ ] Audio output: -14 LUFS on rendered clip (measure with ffprobe or audacity)
- [ ] Intro present on commentary render: `viral_pop` preset visible

### Part B — Tutorial classification

- [ ] Screen recording tutorial: log shows `content_type_hint=tutorial`
- [ ] Tutorial subtitle preset: `clean` (thin outline, no bounce, minimal)
- [ ] Tutorial intro preset: `clean_creator` (slow fade, thin divider, editorial)
- [ ] Tutorial pacing: breathing preserved, no over-cutting
- [ ] Tutorial motion crop: log shows slower tracking interval
- [ ] Tutorial TTS (subtitle): log shows `rate=-8% pause_style=deliberate`
- [ ] Commentary creator (tight edits, high transition quality): stays `commentary`
- [ ] Vlog (soft natural cuts): stays `vlog` — tutorial threshold not met
- [ ] Montage: stays `montage` — density gate prevents tutorial classification
- [ ] Interview/podcast: stays `interview`

### Part C — Manual voice content type

- [ ] Tutorial creator with `subtitle_style=clean`: TTS log shows `content_type=tutorial rate=-8%`
- [ ] Commentary creator with `subtitle_style=viral`: TTS log shows `content_type=commentary rate=+10%`
- [ ] Creator with explicit `voice_rate="+5%"`: rate respected exactly (override wins)
- [ ] No subtitle style set: falls back to `vlog` content type (unchanged from before)

### Part D — Ranking reason

- [ ] Tutorial clip with strong hook: ranking_reason includes `"Strong spoken hook"`
- [ ] Tutorial clip with no strong signals: ranking_reason includes `"Quality spoken content"`
- [ ] Montage clip: ranking_reason unchanged — `"High-energy montage"` still fires

### Safety

- [ ] Normal render completes without errors
- [ ] Cancel still works during all phases
- [ ] Resume still works for interrupted renders
- [ ] No regression on commentary, vlog, montage, interview content types
- [ ] No backend errors in queue or concurrent renders
