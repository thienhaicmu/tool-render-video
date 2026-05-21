# S4 AI Output Upgrade — Production Freeze

**Branch:** `feature/ai-output-upgrade`
**Freeze commit:** `8e7c183` (fix: S4 stabilization mini sprint)
**Freeze date:** 2026-05-21
**Status:** FROZEN — ready for production

---

## A. S4 Summary

S4 is a five-module additive layer that improves visible output quality for
speech-heavy content (podcast, interview, reaction, education, talking-head)
without touching creator controls, clip count, or render engine internals.

All modules are env-gated, independently rollbackable, and fall back gracefully
when their required inputs (transcript, scene data, video frame) are unavailable.

---

## B. Modules Shipped

### S4.1 — Candidate Intelligence V2
**Commit:** `fb4fad5`
**Gate:** `S4_CANDIDATE_INTELLIGENCE_ENABLED`
**File:** `backend/app/services/segment_builder.py`

Snaps selected segment boundaries to natural sentence timestamps from the SRT
transcript. Max nudge ±15% of segment duration. Runs after transcription
(Phase 7) so it works on the first render without a warm cache. Skips any
nudge that would violate `[min_part_sec, max_part_sec]`. Records
`candidate_adjustment_reason`.

### S4.2 — Real Retention Proxy
**Commit:** `b1f4f1e` + stabilization fix `8e7c183`
**Gate:** `S4_RETENTION_PROXY_ENABLED`
**File:** `backend/app/services/viral_scorer.py`

Adjusts `viral_score` by ±15 using 7 multi-signal indicators across two tiers.
Tier-1 signals use pre-computed segment fields (always available). Tier-2
signals require the SRT transcript (skipped gracefully when absent).

**Signals:**
- A `dead_opening`: weak hook + minimal visual energy → penalty up to −6
- B `flat_zone`: static interview with genuine flat pacing (scene_count ≥ 4,
  pacing_accel < 0.05) → penalty up to −4. **Stabilization fix:** scene_count
  guard prevents artifact penalty when pacing_accel = 0.0 due to < 4 scenes.
- C `semantic_density`: high words-per-sec speech → boost up to +5 (tier-2)
- D `payoff_continuation`: strong ending relative to average → boost up to +4
- E `dead_zone`: long spoken segment with heavy silence → penalty up to −4 (tier-2)
- F `healthy_rhythm`: healthy pacing acceleration range → boost up to +3
- G `wps_variance`: healthy within-segment speech variation → boost up to +2 (tier-2)

### S4.3 — Thumbnail Quality Intelligence
**Commit:** `7c6a019`
**Gate:** `S4_THUMBNAIL_QUALITY_ENABLED`
**File:** `backend/app/services/thumbnail_quality.py`

Samples 3 candidate frames around the heuristic thumbnail offset (±1.5s),
scores each with Laplacian variance (sharpness), mean brightness (exposure),
and Haar cascade (face visibility), and selects the highest-quality frame.
Falls back to the original `extract_thumbnail_frame()` call on any failure.
No model downloads — uses OpenCV bundled cascade.

**Note on gate name:** The correct env variable is `S4_THUMBNAIL_QUALITY_ENABLED`.
Any legacy reference to `S4_THUMBNAIL_V2_ENABLED` is incorrect and will silently
leave S4.3 disabled.

### S4.4 — Content Type Intelligence V2
**Commit:** `c734b0c`
**Gate:** `S4_CONTENT_INTELLIGENCE_ENABLED`
**File:** `backend/app/services/viral_scorer.py`

Replaces the single-signal scene-density classifier (4 types) with a
multi-signal classifier (9 types). Gate OFF returns legacy behavior exactly.

**New types:** `high-energy`, `education` (replaces `tutorial`), `reaction`,
`storytelling`, `podcast`. Legacy types `interview`, `commentary`, `vlog`,
`montage` remain as fallbacks.

**Type conditions:**
- `high-energy`: density ≥ 0.20/s AND avg_transition_quality ≥ 0.55 AND pacing_accel ≥ 0.30
- `education`: density 0.03–0.18/s, n_scenes ≥ 3, steady rhythm + sharp cuts
- `reaction`: density 0.03–0.10/s AND starts_at_cut ≥ 0.5 AND avg_tq ≥ 0.50
- `storytelling`: density 0.06–0.18/s AND pacing_accel < 0.20 AND avg_tq < 0.45
- `podcast`: density < 0.05/s AND real SRT speech_density_score > 55

### S4.5 — Speaker-aware Cuts
**Commit:** `a6c7fe0` + stabilization fix `8e7c183`
**Gate:** `S4_SPEAKER_AWARE_CUTS_ENABLED`
**File:** `backend/app/services/segment_builder.py`

Snaps segment boundaries to natural pause midpoints and pause-adjacent
utterance endpoints. Complements S4.1 (which uses sentence timestamps) by
targeting silence gaps ≥ 0.50s between consecutive SRT blocks.

**Asymmetric nudge windows (RC3/RC4):**
- End boundary: ±10% of duration × content-type weight (primary target)
- Start boundary: ±5% of duration × content-type weight (conservative —
  `detect_silence_trim_offset` already handles opening cleanup)

**Content weights:** podcast=1.0, interview=1.0, reaction=0.9, storytelling=0.7,
education=0.6, commentary=0.5, tutorial=0.4, vlog=0.3, montage=0.10,
high-energy=0.0 (intentional fast cuts, never adjusted).

**Stabilization fix:** Utterance endpoints are only collected when the following
gap is ≥ `_S45_MIN_PAUSE_SEC` (0.50s). Tight-gap block ends no longer added.

---

## C. Production Defaults

| Env Var | Value | Status |
|---|---|---|
| `S4_CANDIDATE_INTELLIGENCE_ENABLED` | `1` | ON |
| `S4_RETENTION_PROXY_ENABLED` | `1` | ON |
| `S4_THUMBNAIL_QUALITY_ENABLED` | `1` | ON |
| `S4_CONTENT_INTELLIGENCE_ENABLED` | `1` | ON |
| `S4_SPEAKER_AWARE_CUTS_ENABLED` | `1` | ON |

All five modules are recommended ON. The two stabilization fixes (S4.2
flat_zone guard, S4.5 endpoint filter) resolved the blockers identified in
the QA audit. No module has an open blocker.

---

## D. Rollback Playbook

Every module is independently rollbackable via a single env toggle.
Rollback takes effect on the next render — no restart required if env is
read at request time.

### Instant per-module rollback

| Symptom | Action | Effect |
|---|---|---|
| Segment boundaries shift unexpectedly | `S4_CANDIDATE_INTELLIGENCE_ENABLED=0` | Returns to raw scene boundaries |
| Viral scores change unexpectedly | `S4_RETENTION_PROXY_ENABLED=0` | Returns to pre-S4.2 viral scores |
| Thumbnail quality regresses | `S4_THUMBNAIL_QUALITY_ENABLED=0` | Returns to single heuristic frame |
| Content type labels change | `S4_CONTENT_INTELLIGENCE_ENABLED=0` | Returns to 4-bucket legacy classifier |
| Cut timing shifts unexpectedly | `S4_SPEAKER_AWARE_CUTS_ENABLED=0` | Returns to S4.1-only boundaries |
| Full S4 rollback | All five vars = `0` | Bit-identical to pre-S4 baseline |

### Full rollback to pre-S4 baseline

```
S4_CANDIDATE_INTELLIGENCE_ENABLED=0
S4_RETENTION_PROXY_ENABLED=0
S4_THUMBNAIL_QUALITY_ENABLED=0
S4_CONTENT_INTELLIGENCE_ENABLED=0
S4_SPEAKER_AWARE_CUTS_ENABLED=0
```

Verified: with all five vars = `0`, module chain output is bit-identical
to the `f45b10e` pre-S4 baseline commit.

---

## E. Known Limitations

### 1. No production render comparison data
S4 features have never been enabled in production (0/116 historical jobs
had any S4 flag set). The production freeze recommendation is based on:
- Unit and integration verification (72/72 checks passed)
- Code audit of each module
- Synthetic profile smoke testing across 5 content types

Subjective creator preference data (mid-sentence rate, abrupt ending rate,
blind A/B scores) requires actual renders with S4 enabled. This data does
not yet exist.

### 2. S4.2 signals fire on synthetic data at low rate
In synthetic smoke tests, S4.2 adjusted 0/5 profiles because synthetic
segments have neutral feature values. In production with real SRT transcripts
and real scene cuts, tier-2 signals (C, E, G) will fire when the
`transcript_blocks` argument is populated.

### 3. S4.3 requires frame-accurate video extraction
S4.3 calls `extract_thumbnail_frame()` up to 3 times per part. On very slow
disk systems, this may add 1–3s of latency per part. Frame extraction is
already a standard render step — this is an incremental increase only.

### 4. S4.4 + S4.2 interaction
When both gates are ON, S4.4 may reclassify a segment from "interview" to
"podcast" (when real SRT speech_density_score > 55). This causes S4.2
`flat_zone` and `dead_zone` signals to skip for that segment (those signals
check `ctype in ("interview", "commentary")`). This is correct behavior —
a speech-dense podcast segment should not be penalized for low visual pacing.

### 5. S4.5 combined nudge with S4.1
S4.1 (±15% of duration) and S4.5 (±5–10% of duration) both adjust start/end.
They run sequentially (S4.1 first, S4.5 second). No combined cap exists.
For a 90s segment with podcast weight=1.0: S4.1 can shift start up to ±13.5s,
S4.5 can then shift it up to ±4.5s more. Combined ±18s maximum theoretical
shift. In practice, both must find a qualifying candidate within their
respective windows — double-snap is unlikely unless dense transcript.

---

## F. Monitoring Recommendations

### Observability fields (already on segment output)

| Field | Module | Watch for |
|---|---|---|
| `candidate_adjustment_reason` | S4.1 | Rate of snaps per render; should be > 0% for SRT-enabled jobs |
| `retention_adjustment_reason` | S4.2 | `flat_zone` should fire rarely (< 10% of segments) |
| `cut_adjustment_reason` | S4.5 | Rate of snaps; `pause_boundary`, `sentence_completion`, `reaction_completion` |
| `content_type_hint` | S4.4 | Distribution of types; `interview` should decrease, `podcast` may appear |
| `thumbnail_quality_reason` | S4.3 | `sharp_frame`, `good_exposure`, `good_face_visibility` |

### Suggested render log queries (per job)

```
s4_boundary_refinement segments=N adjusted=K    # S4.1: K/N adjusted
s4_retention_proxy segments=N adjusted=K        # S4.2: K/N adjusted
s4_natural_cuts segments=N adjusted=K           # S4.5: K/N adjusted
```

### Alert conditions

- `flat_zone` fires on > 30% of segments in a job → investigate scene_count distribution
- Any S4 exception logged at WARN or above → check module fallback path
- Render latency increase > 5s per part → check S4.3 frame extraction (disk I/O)
- Clip count changes → **critical** — S4 must never change clip count (RC6)

---

## G. Final Recommendation

### SHIP FULL S4

All five modules are recommended for production with all gates ON.

**Evidence:**
- 72/72 verification checks passed (STEP 4)
- 5/5 content profiles processed without exception (STEP 5)
- All rollback paths verified bit-identical to pre-S4 baseline
- Both QA audit blockers resolved (stabilization sprint `8e7c183`)
- Zero clip count changes across all test configurations
- Module chain latency: negligible (< 1ms per render for S4.1/2/4/5)
- S4.3 adds ≤ 3 frame extractions per part (incremental, not new operation)

**Caveats:**
- Creator preference data from real renders does not yet exist
- First production renders with S4 ON should be monitored via the
  observability fields listed in Section F
- If any module shows unexpected behavior: single env toggle rollback,
  no deployment required

**Recommended monitoring window:** first 20 production renders with S4 ON.
Check `retention_adjustment_reason` and `cut_adjustment_reason` distributions.
If `flat_zone` fires on > 30% of segments, disable S4.2 immediately and
investigate.
