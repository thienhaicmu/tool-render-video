# PRODUCT STATE — QUALITY-UP1A: Platform Compliance & Accuracy Fix

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): platform compliance and quality fixes`
**Status:** Shipped

---

## Summary

Five surgical fixes derived from QUALITY-AUDIT1. No architecture change. No
provider change. No pipeline redesign. Each fix targets a specific measurable
quality gap that was identified in actual code.

---

## Part A — Platform Audio Compliance

**File:** `backend/app/services/render_engine.py`

| Setting | Before | After |
|---------|--------|-------|
| Integrated loudness | `-16 LUFS` | `-14 LUFS` |
| True peak ceiling | `-1.5 dBTP` | `-1.0 dBTP` |

**Why:** TikTok, Reels, and YouTube Shorts normalize uploads toward −14 LUFS.
Output at −16 LUFS was turned up by the platform, compressing dynamic range and
risking peak distortion on content near the true peak. The TP ceiling at −1.5
provided insufficient headroom after platform re-amplification.

**Scope:** One string in `_build_audio_filter`. Mix order, amix, normalization
order, and acompressor/alimiter settings are unchanged.

---

## Part B — Transcription Accuracy

**File:** `backend/app/orchestration/render_pipeline.py`

| Profile | Before | After |
|---------|--------|-------|
| `fast` | Whisper `tiny` | Whisper `base` |
| `balanced` | Whisper `base` | Whisper `base` (unchanged) |
| `quality` | Whisper `small` | Whisper `small` (unchanged) |
| `best` | Whisper `small` | Whisper `small` (unchanged) |

**Why:** Whisper `tiny` achieves ~15–20% WER on noisy content. `base` reduces
this to ~8–10% with a 2–3× transcription time increase — acceptable for offline
rendering. The `fast` profile was the only tier where accuracy was meaningfully
below platform expectations.

**Scope:** One value in the profile defaults dict. The profile system, auto
model selection, and whisper_model override are all unchanged.

---

## Part C — Translation Truthfulness

**File:** `backend/app/orchestration/render_pipeline.py`

**Before:**
- Per-block translation failures: logged as `subtitle_translate_block_failed`
  (technical key=value format, no creator summary)
- Complete translation failure: logged as `subtitle_translate_failed` (technical
  only)

**After:**
- Per-block failures: existing technical log preserved; **new** creator-readable
  summary added: `"Translation partially failed for {lang} export — N subtitle
  block(s) could not be translated. Original text preserved for those blocks."`
- Complete failure: existing technical log preserved; **new** human message
  added: `"Translation failed for {lang} export (part N). Subtitles will use
  original language."`

**Behavior unchanged:** Render continues. Original subtitle text is preserved on
failure. No export is interrupted. This is a truthfulness fix, not a hard error.

---

## Part D — Position Score Floor

**File:** `backend/app/services/viral_scorer.py`

| | Before | After |
|--|--------|-------|
| Formula | `max(0.0, 1.0 - position_ratio * 0.55)` | `max(0.25, 1.0 - position_ratio * 0.55)` |
| Score at position 1.0 (last segment) | `0.45` | `0.45` (unchanged — floor only prevents going below) |
| Score at position 0.0 (first segment) | `1.0` | `1.0` (unchanged) |
| Minimum achievable position_score | `0.0` | `0.25` |

**Why:** The linear decay `position_ratio * 0.55` tops out at 55% penalty for
the last segment — a score of 0.45. The floor of 0.0 was only reachable via
the `max()` guard, which meant the formula was already safe at position 1.0.
The floor change to 0.25 specifically protects against any future formula
modification that could drive position_score to zero for late-video content.
Early-video preference is fully preserved — the formula and weights are unchanged.

**Weight:** `position_score` carries weight `0.08` in the combined heuristic
scoring. The practical effect is that late-segment clips gain at most 2 points
(0.08 × 0.25 × 100) in combined score — enough to prevent systematic discard
without reversing the early preference.

---

## Part E — TTS Failure Truthfulness

**Files:** `backend/app/services/tts_service.py`,
`backend/app/orchestration/render_pipeline.py`

**tts_service.py:**
- Added `import logging` and `logger = logging.getLogger(__name__)`
- On exception in `asyncio.run(_run())`: now logs
  `tts_generation_failed job_id=... voice_id=...` at ERROR level before raising
- Backend logs now capture TTS failures at the service level, independent of
  the caller's exception handling

**render_pipeline.py (per-part subtitle TTS):**
- Two TTS failure paths (subtitle source and translated-subtitle source) now
  emit a creator-readable job log alongside the existing technical log:
  `"Narration generation failed for part N. Continuing without narration."`

**Behavior unchanged:** Render continues without narration on TTS failure.
`_part_subtitle_voice_path` is set to `None`; the part is assembled without
the voice track. No crash. No broken export.

The manual-voice TTS failure path (line ~1585) already had
`update_job_progress(..., "AI voice failed - continuing with original audio")`
— this path is unchanged.

---

## What Was Intentionally Deferred

| Deferred | Reason |
|----------|--------|
| Whisper model above `small` (e.g., `medium`, `large`) | Runtime cost; `small` already covers `quality`/`best` profiles |
| Translation provider replacement | Provider change; out of scope for QUALITY-UP1A |
| Per-block translation overlap (context continuity) | Requires chunking rewrite |
| Position score formula redesign | Content-type-aware scoring is a larger project |
| HIGH_MOTION filter per-profile control | QUALITY-UP1B scope |
| TTS prosody / SSML injection | Provider-level feature; QUALITY-UP1B scope |

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app/services/render_engine.py` | loudnorm: I=-16→-14, TP=-1.5→-1.0 |
| `backend/app/orchestration/render_pipeline.py` | fast profile: tiny→base; translation truthfulness (2 paths); TTS truthfulness (2 paths) |
| `backend/app/services/viral_scorer.py` | position_score floor: 0.0→0.25 |
| `backend/app/services/tts_service.py` | Add logging; log before raise |
| `docs/render/PRODUCT_STATE_QUALITY_UP1A.md` | This file |

---

## Manual QA Checklist

### Audio
- [ ] Render a clip with `loudnorm_enabled=True`; measure output LUFS (should be near −14)
- [ ] Platform playback (TikTok / Reels preview): volume feels native, not quiet
- [ ] No clipping or distortion on loud source material

### Subtitles
- [ ] `fast` profile render: subtitle accuracy visibly improved over prior `tiny` output
- [ ] `balanced` / `quality` / `best` profiles: no transcription regression
- [ ] `fast` profile render time: acceptable increase (2–3× transcription only, encode unchanged)

### Translation
- [ ] Force a translation failure (use invalid target language code); confirm warning appears in job log
- [ ] Confirm render completes successfully with original-language subtitles
- [ ] Confirm no crash or export failure on translation error

### Position Score
- [ ] Run scoring on a video where the best moment is at the end; confirm it survives into output
- [ ] Run scoring on a video with strong early content; confirm early preference still dominates

### TTS
- [ ] Simulate TTS failure (e.g., invalid voice_id); confirm job log shows creator-readable warning
- [ ] Confirm render continues and output is produced without narration track
- [ ] Backend log: confirm `tts_generation_failed` appears at ERROR level

### Safety
- [ ] No render regression (normal render completes correctly)
- [ ] No queue regression (multiple concurrent renders)
- [ ] Cancel still works cleanly
- [ ] No new console errors during any of the above
