# OQ-3.2 — Audio Silence Gap Scoring
## Additive Scene Scoring Signal

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-20
**Phase:** SCORING SIGNAL ONLY — no ranking rewrite, no render logic, no subtitle, no narration

---

## 1. Audit Findings

### Current scoring pipeline (pre-OQ-3.2)

```
detect_scenes()          → [{"start", "end", "transition_score"}]
                              ↓ optional: speech_density via SRT
_score_scene()           → scene_quality
_score_candidate()       → viral_score (v3)
score_segments()         → content_type_hint, final ranking signals
_compute_output_ranking  → composite output_rank_score
```

**Audio signals currently present:**

| Signal | Source | Usage |
|---|---|---|
| `transition_score` [0.1,1.0] | Pixel delta at cut boundary | Per-scene visual cut strength |
| `speech_density` [0,1] | SRT subtitle coverage fraction | Speech richness (only when SRT provided) |
| `speech_density_score` [0,100] | Derived from `speech_density` | Soft reward in `_score_candidate()` |
| `silence_penalty` [0,20] | Fires when `speech_density_score < 20` | Punishes dead-air segments |

**What is missing:**

The existing `silence_penalty` fires only when SRT subtitle data is injected via
`build_segments_from_scenes_with_subtitles()`, which is NOT called in the main pipeline.
The main pipeline calls `build_segments_from_scenes()` (no SRT) — silence_penalty is always 0.

No audio-waveform silence analysis exists anywhere. There is:
- `backend/app/ai/analyzers/silence_analyzer.py` — metadata-only (transcript chunks, no waveform)

The scoring pipeline is entirely visual (transition_score) + layout (duration, position, pacing).
Speech pauses, reaction timing, and breathing gaps are invisible to the scorer.

---

## 2. Problems Identified

| # | Problem | Severity |
|---|---|---|
| P1 | No pre-scene pause detection — natural breath/reaction pauses before a moment carry no weight | MEDIUM |
| P2 | No rhythm pause scoring — interview/podcast moments with good conversational rhythm score same as dead-air scenes | MEDIUM |
| P3 | Dead air undetected without SRT — long silences not penalized in main pipeline | MEDIUM |
| P4 | Hook entry timing blind — silence_penalty only fires with SRT; pre-hook pause not rewarded | MEDIUM |

---

## 3. Implementation Architecture (OQ-3.2)

### A. Silence Feature Extraction

New function `_compute_silence_features(video_path, scenes)` in `scene_detector.py`.

**Method:** FFmpeg `silencedetect` audio filter — no new packages, FFmpeg already required.

```
ffmpeg -hide_banner -i <video> -vn -af "silencedetect=noise=-40dB:d=0.3" -f null -
```

Parameters:
- `noise=-40dB`: threshold for "meaningful silence" (excludes room noise, breath sounds)
- `d=0.3`: minimum silence duration 300ms (natural breath pause floor)
- `-vn`: skip video decode for speed (audio-only pass)

Parses stderr for `silence_start` / `silence_end` lines → list of `(start, end, duration)`.

**Per-scene silence signal components:**

| Component | Condition | Value | Rationale |
|---|---|---|---|
| `pre_pause_bonus` | Silence 0.3–1.5s ending ≤0.5s before scene start | +0 to +8 | Breath/reaction pause before a moment = good hook entry |
| `rhythm_bonus` | 1–3 natural pauses (0.3–1.2s) within scene | +4 to +10 | Conversational rhythm = interview/podcast quality |
| `trailing_bonus` | Scene ends in silence | +4 | Natural cut point |
| `dead_air_penalty` | Total silence > 35% of scene duration | 0 to -8 | Dead air = boring moment |

**Composite `silence_score`:** clamped to `[-8, 20]`

### B. Scene Dict Enrichment

`detect_scenes()` calls `_compute_silence_features()` after `_compute_transition_scores()`.
Each scene dict gains one new field: `"silence_score": float` (default `0.0` on any failure).

### C. Score Integration

Two changes in `segment_builder.py`:

1. `_normalize_scenes()`: copy `silence_score` field into normalized scene dict.
2. `_score_scene()`: add `silence_bonus` additive term (same pattern as existing `speech_bonus`).

```python
silence_bonus = _clamp(float(scene.get("silence_score", 0.0)), -8.0, 20.0)
return (...existing formula...) + silence_bonus
```

This is purely additive — no existing weights or components change.

### D. Opt-out Gate

`SILENCE_SCORING_ENABLED` env var (default `"1"`).
Set to `"0"` to skip silence analysis entirely → silence_score remains 0.0 everywhere → scoring unchanged.

---

## 4. Score Impact Analysis

`_score_scene()` existing formula:
```
scene_quality = duration_score*0.45 + transition_score*0.35 + position_stability*0.20
                + early_bonus [0,8] + speech_bonus [0,12]
```
Max scene_quality ≈ 120.

New `silence_bonus` range: [-8, +20].
Effective influence: **±7-17% of typical scene_quality**.

Scenarios:

| Scenario | silence_score | Effect |
|---|---|---|
| Interview: 2 natural pauses + pre-scene pause | +16 | Scene quality +16 pts → surfaced in ranking |
| Podcast: 1 pause + trailing silence | +12 | Moderate uplift |
| Montage: fast cuts, no pauses | 0 | No change |
| Dead air: 50% silence | -8 | Small penalty (dead air unlikely to be "best moment") |
| Talking-head: good breath rhythm | +8–14 | Rewards natural conversational moments |

---

## 5. Compatibility Impact

| Component | Impact |
|---|---|
| ContentDetector / AdaptiveDetector (OQ-2.1) | None — runs before silence analysis |
| `_compute_transition_scores()` | None — runs before silence analysis |
| 72h scene cache | Valid — silence_score is included in scene dicts, cached with them |
| `speech_density` / SRT path | None — independent signals |
| `silence_penalty` in `_score_candidate()` | None — that path fires on speech_density, not silence_score |
| Render pipeline call sites | None — `detect_scenes()` and `build_segments_from_scenes()` signatures unchanged |
| Viral scorer (viral_scorer.py) | None — consumes segment dicts, silence_score is upstream |
| Output ranking | Indirect — improved scene_quality → improved viral_score → better ranking |

---

## 6. Regression Risks

| Risk | Severity | Mitigation |
|---|---|---|
| FFmpeg silencedetect fails (no audio stream) | Low | try/except returns unmodified scenes; silence_score defaults to 0.0 |
| False positives on noisy room audio | Low | noise=-40dB threshold filters room noise; only meaningful pauses register |
| Score inflation shifting content-type inference | Negligible | silence_score range ±8-20 vs scene_density range 0-100; content-type density thresholds unaffected |
| `SILENCE_SCORING_ENABLED=0` | None | Full revert to pre-OQ-3.2 behavior |
| Slow analysis on long source videos | Low | Audio-only pass (-vn) is very fast (<3s for 60-min video); timeout=90s |

---

## 7. Manual Verification Checklist

```
[ ] Talking-head interview: scenes with breath pauses score higher than previously
[ ] Scene immediately after silence: pre_pause_bonus applied
[ ] Dead-air scene: silence_score negative → viral_score slightly lower
[ ] Pure montage (fast cuts, no pauses): silence_score ≈ 0 → unchanged scoring
[ ] SILENCE_SCORING_ENABLED=0: detect_scenes() returns scenes without silence_score
[ ] FFmpeg unavailable: detect_scenes() returns unmodified scenes, no crash
[ ] Log shows: silence_features_computed scenes=N silence_intervals=M
[ ] Log shows: scene_detection_complete includes silence_data=True/False
```

---

## 8. Files Modified

| File | Change |
|---|---|
| `backend/app/services/scene_detector.py` | Add `_compute_silence_features()`, call from `detect_scenes()` |
| `backend/app/services/segment_builder.py` | `_normalize_scenes()` copies silence_score; `_score_scene()` adds silence_bonus |

---

## 9. Commit Hash

`[pending]`

---

## 10. Push Confirmation

`[pending]`
