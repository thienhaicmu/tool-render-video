# S4 AI Output Upgrade — Roadmap

Lightweight, no-model-download quality improvements targeting visible output
quality for speech-heavy content: podcast, interview, reaction, education,
talking-head.

AI may: nudge segment boundaries, adjust ranking, improve thumbnail frame,
classify content type more accurately.
AI must not: change clip count, override creator controls, download models,
call external APIs.

---

## Philosophy

S3 answered: *how should each clip be packaged?*
S4 answers: *are the cuts themselves natural?*

S4 operates on signals already computed by S2/S3 (scene data, SRT transcript,
transition quality) and applies lightweight post-processing passes. No new
inference, no new models, no new compute budget.

---

## S4.1 — Candidate Intelligence V2 ✅ COMPLETE

**Shipped:** `feat(ai): S4.1 Candidate Intelligence V2` (commit `fb4fad5`)
**Gate:** `S4_CANDIDATE_INTELLIGENCE_ENABLED`

Transcript-aware boundary refinement. Snaps segment start/end to natural
sentence timestamps from SRT within ±15% of segment duration.
Works on first render (applied after Phase 7 transcription, no cache warm needed).

**Files:** `backend/app/services/segment_builder.py` (+3 functions)
**Pipeline:** `backend/app/orchestration/render_pipeline.py` (gate block after transcription)

---

## S4.2 — Real Retention Proxy ✅ COMPLETE

**Shipped:** `feat(ai): S4.2 Real Retention Proxy` (commit `b1f4f1e`)
**Stabilized:** `fix(ai): S4 stabilization mini sprint` (commit `8e7c183`)
**Gate:** `S4_RETENTION_PROXY_ENABLED`

Multi-signal retention estimation. Applies bounded ±15 adjustment to
`viral_score` using 7 signals across two tiers. Tier-1 always active;
tier-2 requires SRT transcript (skipped gracefully when absent).

**Stabilization fix:** `flat_zone` signal guarded with `scene_count >= 4`
to prevent false penalty on segments with < 4 scene cuts (data artifact).

**Files:** `backend/app/services/viral_scorer.py` (+3 functions)
**Pipeline:** gate block after S4.1, before AI Director

---

## S4.3 — Thumbnail Quality Intelligence ✅ COMPLETE

**Shipped:** `feat(ai): S4.3 Thumbnail Quality Intelligence` (commit `7c6a019`)
**Gate:** `S4_THUMBNAIL_QUALITY_ENABLED`

Quality-scored cover frame selection. Samples 3 frames ±1.5s around heuristic
offset. Scores each with Laplacian sharpness + brightness exposure + Haar face
detection. Selects highest-quality frame. Falls back to original heuristic frame
on any failure. No model downloads (bundled OpenCV cascade).

**Files:** `backend/app/services/thumbnail_quality.py` (new, 208 lines)
**Pipeline:** gate block at UP15 cover frame step

**Gate name note:** `S4_THUMBNAIL_QUALITY_ENABLED` (not `S4_THUMBNAIL_V2_ENABLED`).

---

## S4.4 — Content Type Intelligence V2 ✅ COMPLETE

**Shipped:** `feat(ai): S4.4 Content Type Intelligence V2` (commit `c734b0c`)
**Gate:** `S4_CONTENT_INTELLIGENCE_ENABLED`

Nine-type multi-signal content classifier replacing the legacy 4-bucket
scene-density-only classifier. Gate OFF = legacy behavior exactly.

New types: `high-energy`, `education` (replaces `tutorial`), `reaction`,
`storytelling`, `podcast`. Existing: `interview`, `commentary`, `vlog`,
`montage`.

**Files:** `backend/app/services/viral_scorer.py` (+1 function `_classify_content_type_v2`)

---

## S4.5 — Speaker-aware Cuts ✅ COMPLETE

**Shipped:** `feat(ai): S4.5 Speaker-aware Cuts` (commit `a6c7fe0`)
**Stabilized:** `fix(ai): S4 stabilization mini sprint` (commit `8e7c183`)
**Gate:** `S4_SPEAKER_AWARE_CUTS_ENABLED`

Pause-gap preference for natural cut timing. Snaps segment boundaries to
midpoints of silence gaps (≥ 0.50s) and pause-adjacent utterance endpoints.
Asymmetric nudge: end ±10% × content_weight (primary), start ±5% × content_weight
(conservative — opening handled by `detect_silence_trim_offset`).

Content weights: podcast=1.0, interview=1.0, reaction=0.9 … high-energy=0.0.

**Stabilization fix:** utterance endpoints only collected when followed by a
gap ≥ `_S45_MIN_PAUSE_SEC` (0.50s). Non-pause block ends excluded.

**Files:** `backend/app/services/segment_builder.py` (+2 functions)
**Pipeline:** gate block after S4.2, before AI Director

---

## S4 Stabilization Sprint ✅ COMPLETE

**Shipped:** `fix(ai): S4 stabilization mini sprint` (commit `8e7c183`)

Two targeted fixes from the QA audit:
1. S4.5 utterance endpoint filter — prevents false speaker-aware snaps on rapid speech
2. S4.2 flat_zone guard — prevents false penalty on segments with < 4 scene cuts

---

## S4 Production Freeze Sprint ✅ COMPLETE

**Freeze commit:** `8e7c183`
**Freeze date:** 2026-05-21
**Document:** `docs/product/S4_PRODUCTION_FREEZE.md`

Final verification: 72/72 checks passed. 5/5 content profiles stable.
Rollback paths verified bit-identical.

**Recommendation: SHIP FULL S4**

All five modules ON in production:
```
S4_CANDIDATE_INTELLIGENCE_ENABLED=1
S4_RETENTION_PROXY_ENABLED=1
S4_THUMBNAIL_QUALITY_ENABLED=1
S4_CONTENT_INTELLIGENCE_ENABLED=1
S4_SPEAKER_AWARE_CUTS_ENABLED=1
```

---

## S4 Execution Summary

| Module | Commit | Status | Gate |
|---|---|---|---|
| S4.1 Candidate Intelligence V2 | `fb4fad5` | ✅ COMPLETE | `S4_CANDIDATE_INTELLIGENCE_ENABLED` |
| S4.2 Real Retention Proxy | `b1f4f1e` | ✅ COMPLETE | `S4_RETENTION_PROXY_ENABLED` |
| S4.3 Thumbnail Quality Intelligence | `7c6a019` | ✅ COMPLETE | `S4_THUMBNAIL_QUALITY_ENABLED` |
| S4.4 Content Type Intelligence V2 | `c734b0c` | ✅ COMPLETE | `S4_CONTENT_INTELLIGENCE_ENABLED` |
| S4.5 Speaker-aware Cuts | `a6c7fe0` | ✅ COMPLETE | `S4_SPEAKER_AWARE_CUTS_ENABLED` |
| S4 Stabilization Sprint | `8e7c183` | ✅ COMPLETE | — |
| S4 Production Freeze | `8e7c183` | ✅ COMPLETE | — |
