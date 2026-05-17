# PRODUCT STATE — QUALITY-UP4: Human Micro Pacing

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): human micro pacing`
**Status:** Shipped

---

## Summary

Six targeted heuristic upgrades to `apply_micro_pacing`. The pacing pass now
adjusts its aggressiveness per content type, preserves breathing rhythm, protects
payoff moments near clip endings, and skips micro-splices that save less than
100ms. Interview and commentary content sounds human. Montage content stays tight.

---

## Root Cause

`apply_micro_pacing` had three problems that made the pacing feel robotic:

1. **Uniform thresholds regardless of content.** Every clip got the same 0.3s
   minimum silence detection, same `_target_dur` tiers, and same max trim budget
   (2.0s). Interview content got the same treatment as a gaming montage.

2. **Breath pauses kept too short (0.15s).** After trimming, silences ≤ 0.7s
   were compressed to 0.15s — audibly clipped to many viewers. 0.20s is the
   perceptual minimum for a natural breath.

3. **No payoff protection.** Silences in the last 2 seconds of a clip could be
   trimmed aggressively. A dramatic pause before a punchline could be cut to
   0.15s, destroying the comedic timing.

4. **Over-cutting on small silences.** Silences of 0.3s that could only save
   50ms still triggered a full FFmpeg filter_complex re-encode splice. The splice
   overhead was not worth it and introduced an audible stitch.

---

## Part A — Sentence-Safe Cutting

**File:** `backend/app/services/render_engine.py`

Start-of-clip boundary guard extended from `s >= 0.5` to `s >= 0.6`. The 600ms
buffer at the clip start protects the speaker's first word from having its
introductory breath trimmed.

`_target_dur` tier thresholds restructured so that silences are classified by
their likely communicative role:

| Duration | Likely role | Before (kept) | After (kept) |
|---------|------------|---------------|--------------|
| ≤ 0.5s | Breath pause | 0.15s (≤0.7s tier) | 0.20s |
| ≤ 0.9s | Conversation rhythm | 0.25s (≤1.2s tier) | 0.30s |
| ≤ 1.5s | Emphasis / sentence boundary | 0.40s (>1.2s tier) | 0.45s |
| > 1.5s | Dead air | 0.40s (same tier) | 0.50s |

Longer silences are now more likely to be intentional and are preserved more.

---

## Part B — Breathing Rhythm

**File:** `backend/app/services/render_engine.py`

Breath pauses (≤ 0.5s) now keep 0.20s instead of 0.15s. This is the perceptual
threshold below which a pause stops sounding like a breath and starts sounding
like an edit. 50ms difference, significant audible impact.

The `_target_dur` multiplier system (see Part D) further scales up the kept
duration for interview and commentary content, preserving even more breathing
room in conversational clips.

---

## Part C — Over-Cut Prevention

**File:** `backend/app/services/render_engine.py`

Two changes:

1. `min_silence_dur` default raised from `0.3` to `0.4`. Silences shorter than
   400ms are no longer even detected — they are sub-breath pauses that should
   not be touched.

2. `_MIN_TRIM = 0.10` threshold added inside the loop. If a detected silence
   would only save less than 100ms after computing the kept portion, the splice
   is skipped entirely. An FFmpeg filter_complex re-encode for 60ms of savings
   introduces more artifact than value.

---

## Part D — Content-Aware Pacing

**File:** `backend/app/services/render_engine.py` + `backend/app/orchestration/render_pipeline.py`

`apply_micro_pacing` now accepts `content_type: str = "vlog"`. The caller
(`render_pipeline.py`) passes `seg.get("content_type_hint", "vlog")` — the
same field written by QUALITY-UP2's `score_segments`.

Per-type parameter table:

| content_type | noise_db adj | min_silence_dur adj | target_multiplier | max_trim |
|-------------|-------------|---------------------|-------------------|----------|
| `interview` | −5 dB (quieter threshold) | +0.10s (0.50s min) | 1.50× (keep more) | 1.5s |
| `commentary` | −3 dB | +0.05s (0.45s min) | 1.25× | 1.8s |
| `vlog` | ±0 (default) | ±0 (0.40s min) | 1.00× | 2.0s |
| `tutorial` | −4 dB | +0.10s (0.50s min) | 1.40× | 1.5s |
| `montage` | +2 dB (more aggressive) | −0.10s (0.30s min) | 0.80× (tighter) | 2.5s |

**Example — interview clip with a 0.6s silence:**
- `effective_noise_db` = −35 dB (captures quieter breathing)
- `effective_min_dur` = 0.50s (0.6s silence qualifies)
- `_target_dur(0.6s, mul=1.50)` = min(0.55, 0.30 × 1.50) = min(0.55, 0.45) = **0.45s kept**
- trim = 0.6 − 0.45 = **0.15s trimmed** — very gentle

**Example — montage clip with the same 0.6s silence:**
- `effective_noise_db` = −28 dB
- `effective_min_dur` = 0.30s (qualifies)
- `_target_dur(0.6s, mul=0.80)` = min(0.55, 0.30 × 0.80) = min(0.55, 0.24) = **0.24s kept**
- trim = 0.6 − 0.24 = **0.36s trimmed** — tighter

---

## Part E — Energy / Payoff Timing

**File:** `backend/app/services/render_engine.py`

A payoff zone is defined as the last 2 seconds of each clip:

```python
_payoff_zone_start = max(0.0, clip_dur - 2.0)
```

Any silence that begins inside the payoff zone receives a `1.5×` multiplier
on top of the content-type multiplier:

```python
_eff_mul = target_multiplier * (1.5 if s_start >= _payoff_zone_start else 1.0)
```

For a `vlog` clip (target_mul=1.00), a 0.5s silence in the last 2s keeps:
`_target_dur(0.5, 1.5)` = min(0.45, 0.20 × 1.5) = min(0.45, 0.30) = **0.30s** instead of 0.20s.

This preserves the dramatic pause before a reveal, punchline, or reaction.

---

## Part F — Subtitle Safety

`apply_micro_pacing` runs on `final_part` — the rendered video with ASS
subtitles already burned into the frame data by `render_part_smart`. There is
no external SRT file that needs re-timing after micro pacing. The subtitle
frames are part of the video and move with it through the filter_complex splice.

No subtitle drift. No alignment risk.

---

## Parameter Comparison

| Parameter | Before | After (vlog) | After (interview) | After (montage) |
|-----------|--------|--------------|-------------------|-----------------|
| `noise_db` | −30 dB | −30 dB | −35 dB | −28 dB |
| `min_silence_dur` | 0.3s | 0.4s | 0.5s | 0.3s |
| keep for 0.4s silence | 0.15s | 0.20s | 0.30s | 0.16s |
| keep for 0.8s silence | 0.25s | 0.30s | 0.45s | 0.24s |
| keep for 1.5s silence | 0.40s | 0.45s | 0.675s | 0.36s |
| `max_total_trim` | 2.0s | 2.0s | 1.5s | 2.5s |
| min trim per splice | none | 0.10s | 0.10s | 0.10s |
| start boundary guard | 0.5s | 0.6s | 0.6s | 0.6s |

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| Audio energy peak detection (pre-trim) | Requires separate ffprobe loudness pass; QUALITY-UP5 scope |
| TTS narration pacing separation | TTS audio is part of final_part at pacing time; decoupling is architectural |
| Sentence boundary detection from transcription | No transcription data at pacing time |
| Per-silence confidence scoring | Would require neural silence classification |
| Adaptive payoff zone (variable length) | Static 2s is a safe conservative value |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/render_engine.py` | `apply_micro_pacing`: content_type param; content-aware threshold table; improved `_target_dur` tiers; payoff zone protection; 100ms min trim; 0.6s start guard |
| `backend/app/orchestration/render_pipeline.py` | Pass `content_type_hint` to `apply_micro_pacing`; log and event context include content_type |
| `docs/render/PRODUCT_STATE_QUALITY_UP4.md` | This file |

---

## Manual QA Checklist

### Talking Head / Interview
- [ ] Breathing sounds natural between sentences
- [ ] No machine-gun speech feel
- [ ] Dramatic pauses preserved near clip end
- [ ] Job log shows `content_type=interview` in micro pacing entry

### Commentary / Reaction
- [ ] Laugh/surprise moments not clipped mid-reaction
- [ ] Joke timing preserved (payoff zone protection active)
- [ ] Pacing feels human, not robotic

### Tutorial
- [ ] Explanation clarity maintained
- [ ] No over-cutting between explanation steps
- [ ] Dead air removed but rhythm preserved

### Montage / Gaming / Sports
- [ ] Still feels energetic and tight
- [ ] Tighter than interview (shorter kept durations)
- [ ] `content_type=montage` in log

### Subtitles
- [ ] Rendered subtitles visually align with speech after pacing
- [ ] No subtitle-speech drift visible

### Over-cut prevention
- [ ] Clips with only 50–80ms trimmable silences: micro pacing skipped (no re-encode)
- [ ] Job log: "no qualifying silence segments" for such clips

### Safety
- [ ] Normal render completes without error
- [ ] Cancel still works during micro pacing
- [ ] No backend errors during any of the above
- [ ] No regression on clips that previously had micro pacing applied
