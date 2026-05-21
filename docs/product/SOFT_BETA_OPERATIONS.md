# S3 Production Intelligence — Soft Beta Operations

**Branch:** `feature/ai-output-upgrade`
**Sprint:** Soft Beta Launch Preparation
**Date:** 2026-05-21
**Status:** ✅ Ready

**CALIBRATION_FROZEN=true** — No threshold changes without a new calibration sprint.

---

## 1. Rollout Checklist

### Pre-launch (complete before any creator render)

- [x] All S3 modules: `S3_*_ENABLED=1` (default)
- [x] `S3_DEBUG_ENABLED=0` (default — never enable in production)
- [x] All frozen defaults applied (see SOFT_BETA_READINESS.md §1)
- [x] `CALIBRATION_FROZEN=true` — no further tuning without sprint approval
- [x] `s3_health_summary` in API response for observability
- [x] Warning severity tiers active (`CRITICAL:`, `WARN:`, `INFO:`)
- [ ] Internal smoke test: 5 renders with `S3_DEBUG_ENABLED=1` — zero `CRITICAL:` warnings
- [ ] Confirm `s3_health_summary` populates correctly in smoke test response
- [ ] Review smoke test `s3_health_summary` for unexpected `clips_processed < clips_attempted`
- [ ] Disable `S3_DEBUG_ENABLED` before first creator render

### Stage 1 → Stage 2 gate (RC3)

All three conditions must be met before exposing to any external creator:

| Requirement | Measurement | Gate |
|-------------|-------------|------|
| No CRITICAL warnings | Count of `CRITICAL:*` in `response.warnings` | **= 0** across 5 consecutive renders |
| Low WARN rate | Count of `WARN:*` in `response.warnings` | **≤ 5%** of warnings per render |
| Consecutive clean renders | Renders with zero CRITICAL warnings | **≥ 5 in a row** |

A "clean render" is defined as: `response.warnings` contains zero strings matching `CRITICAL:*`.

### Stage 2 → Stage 3 gate (RC3)

| Requirement | Measurement | Gate |
|-------------|-------------|------|
| Creator satisfaction | Thumbs-up rate on exported clips | **≥ 7.5 / 10 average** |
| Module error rate | `CRITICAL:*` warnings per 100 renders | **< 5 occurrences** |
| No rollback triggered | No `S3_*_ENABLED=0` emergency action | **True** |

### Stage 3 → Full launch decision (RC3)

| Requirement | Measurement | Gate |
|-------------|-------------|------|
| Stable creator feedback | No sustained negative signal trend | Confirmed over 2-week window |
| Error rate | `CRITICAL:*` rate | **< 2 per 100 renders** |
| S3.5 readiness floor | Clip-level feedback events collected | **≥ 100** (RC4 hard floor) |

---

## 2. Rollback Playbook

### Immediate full rollback (zero downtime, no code deploy)

Set all five gates to `0`:

```
S3_PACKAGING_ENABLED=0
S3_RETENTION_ENABLED=0
S3_THUMBNAIL_ENABLED=0
S3_PLATFORM_INTELLIGENCE_ENABLED=0
STRUCTURE_INTELLIGENCE_ENABLED=0
```

Result: behavior bit-identical to pre-S3.1. Verified in Stabilization RC6.

### Partial rollback by module

Triggered when a specific `CRITICAL:` warning fires repeatedly.

| Warning Observed | Disable | Command |
|-----------------|---------|---------|
| `CRITICAL:packaging_error:*` | S3.1 | `S3_PACKAGING_ENABLED=0` |
| `CRITICAL:retention_prediction_error:*` | S3.2 | `S3_RETENTION_ENABLED=0` |
| `CRITICAL:cover_hint_error:*` | S3.3 | `S3_THUMBNAIL_ENABLED=0` |
| `CRITICAL:platform_adaptation_error:*` | S3.4 | `S3_PLATFORM_INTELLIGENCE_ENABLED=0` |
| `CRITICAL:debug_aggregation_error:*` | Debug | `S3_DEBUG_ENABLED=0` (already default) |

### Partial failure investigation (`WARN:partial_*_failure`)

`WARN:partial_packaging_failure:processed=2,attempted=5` means 3 of 5 clips silently degraded
inside the module. This is not a render failure (the clip still renders), but it means S3 output
is missing for those clips.

**Investigation steps:**
1. Enable `S3_DEBUG_ENABLED=1` on the affected creator's next render
2. Inspect `clip_production_debug` in the response for per-clip failure detail
3. Check `s3_health_summary` to confirm which module and clip count
4. If consistently > 50% partial failure on one module: disable that module pending fix

### Playbook sequence

```
1. Observe: CRITICAL:packaging_error:ValueError in response.warnings
2. Action:  Set S3_PACKAGING_ENABLED=0 immediately
3. Confirm: Next render has no packaging_error in warnings
4. Debug:   Reproduce locally with S3_DEBUG_ENABLED=1
5. Fix:     Isolate, fix, verify, re-enable in staging
6. Re-enable: After 5 clean staging renders → re-enable in production
```

---

## 3. Observability Coverage

### Warning matrix — severity tiers (RC2)

| Severity | Pattern | Meaning | Action |
|----------|---------|---------|--------|
| `CRITICAL:` | `CRITICAL:packaging_error:ExceptionType` | S3.1 module crash | Disable `S3_PACKAGING_ENABLED=0` |
| `CRITICAL:` | `CRITICAL:retention_prediction_error:ExceptionType` | S3.2 module crash | Disable `S3_RETENTION_ENABLED=0` |
| `CRITICAL:` | `CRITICAL:cover_hint_error:ExceptionType` | S3.3 module crash | Disable `S3_THUMBNAIL_ENABLED=0` |
| `CRITICAL:` | `CRITICAL:platform_adaptation_error:ExceptionType` | S3.4 module crash | Disable `S3_PLATFORM_INTELLIGENCE_ENABLED=0` |
| `CRITICAL:` | `CRITICAL:debug_aggregation_error:ExceptionType` | Debug module crash (staging only) | `S3_DEBUG_ENABLED=0` |
| `WARN:` | `WARN:partial_packaging_failure:processed=N,attempted=M` | Some clips skipped inside S3.1 | Investigate; see playbook |
| `WARN:` | `WARN:partial_retention_failure:processed=N,attempted=M` | Some clips skipped inside S3.2 | Investigate; see playbook |
| `WARN:` | `WARN:partial_thumbnail_failure:processed=N,attempted=M` | Some clips skipped inside S3.3 | Investigate; see playbook |
| `WARN:` | `WARN:partial_platform_failure:processed=N,attempted=M` | Some clips skipped inside S3.4 | Investigate; see playbook |
| `WARN:` | `WARN:dominance_warning:module=pct%` | Single S3 signal dominates (debug mode only) | Advisory; review signal balance |
| `INFO:` | `INFO:platform_unknown:name` | Unknown platform submitted | Log platform name; add to known list if valid |

**Pre-severity warnings (phases 6–57, not S3-specific):** remain unprefixed. These are unrelated
to S3 observability and are not part of the RC2 scope.

### s3_health_summary — coverage signal (RC1)

Present in every API response under `response.s3_health_summary`:

```json
{
  "packaging":  {"enabled": true,  "clips_attempted": 5, "clips_processed": 5},
  "retention":  {"enabled": true,  "clips_attempted": 5, "clips_processed": 4},
  "thumbnail":  {"enabled": true,  "clips_attempted": 5, "clips_processed": 5},
  "platform":   {"enabled": false}
}
```

Interpretation:
- `enabled: false` → module disabled via env gate; no output expected
- `clips_processed = clips_attempted` → full coverage; all clips received S3 output
- `clips_processed < clips_attempted` → partial degradation; WARN warning also emitted
- `clips_processed = 0`, `enabled: true` → module ran but produced no output (likely CRITICAL also fired)

When `clips_processed = 0` and no CRITICAL warning: the module's score gate (`S3_RETENTION_MIN_SCORE`,
etc.) filtered all clips. This is expected for low-quality input, not a bug.

### Known observability gaps (documented, not blocking)

| Gap | Impact | Status |
|-----|--------|--------|
| Per-clip inner-loop exceptions silently degrade to `{}` | `WARN:partial_*` fires but specific clip reason unknown | Mitigated by `s3_health_summary`; detailed debug via `S3_DEBUG_ENABLED=1` |
| Retention risk distribution not in plan.warnings | Cannot tell what % of clips have `hook_weakness` without parsing all clip data | Monitor via `selected_segments[i].retention_prediction.retention_explanation.risks` |
| No null-hint rate for S3.3 | Cannot tell how often thumbnail hint falls back to null | Count `clip_cover_hints[i].preferred_offset_ratio == null` per render |
| Debug dominance only in staging | Signal imbalance invisible in production | Acceptable for soft beta; enable `S3_DEBUG_ENABLED=1` to investigate if WARN fires |

---

## 4. Creator Feedback Loop Design

**Design only. No S3.5 implementation. No learning system. No code.**

### Implicit signals (no creator action required)

Observable from existing render + export data:

| Signal | What it means | How to collect |
|--------|---------------|---------------|
| Manual clip delete after export | Creator rejected this clip | Log delete event + original clip index + `retention_prediction` for that clip |
| Manual clip re-order | Creator preferred different sequence | Log final order vs AI-suggested order |
| Re-render triggered | Creator dissatisfied with overall output | Log re-render count per session |
| Subtitle style override | Creator changed from AI suggestion | Log original style vs final style |
| Thumbnail frame scrub override | Creator picked a different cover frame | Log offset delta from `preferred_offset_ratio` |
| Platform change before render | Creator changed platform after seeing plan | Log platform switch event |
| Clip duration trim | Creator shortened/lengthened clip | Log trim delta vs original duration |

### Explicit signals (lightweight creator action)

| Signal | UI touchpoint | What it tells us |
|--------|--------------|-----------------|
| Thumbs up/down per clip | Per-clip in export preview | Clip-level satisfaction ground truth |
| "Skip this clip" | One-tap in preview | Strong rejection signal |
| "More like this" | One-tap on a clip | Positive reinforcement |
| Re-render reason (category) | Re-render dialog | Categorized dissatisfaction root cause |

### What NOT to collect

- Real-time learning or model updates from feedback
- Automatic threshold adjustment based on creator behavior
- Personalized models per creator
- Any feedback path back to clip selection or scoring (advisory-only architecture must be preserved)

---

## 5. S3.5 Readiness Requirements (RC4)

**Hard floor: minimum 100 clip-level feedback events before any learning hypothesis.**

This is a non-negotiable gate. Building a learning system from < 100 events produces
overfit hypotheses that damage calibration. The 100-event floor is the minimum for any
statistically meaningful signal — not a target for launch, a prerequisite for analysis.

| Requirement | Status | Notes |
|-------------|--------|-------|
| Clip identity stability (UUID per clip) | ❌ Not implemented | Required for attribution |
| Feedback storage (append-only log) | ❌ Not implemented | `{render_id, clip_id, signal_type, ts}` |
| Signal attribution to S3 output | ❌ Not implemented | `retention_prediction` must be stored with render record |
| **100 clip-level feedback events** | ❌ Not met | **RC4 hard floor — no S3.5 until met** |
| Baseline volume for calibration | ❌ Not met | Need ≥100 events before any hypothesis |

**These are pre-conditions for a future S3.5 sprint, not items for this sprint.**

No S3.5 work begins until all five requirements above are ✅.

---

## 6. Known Creator Limitations (Soft Beta)

These limitations are expected behaviors of the current calibrated system. They are documented
here so creator-facing support can set accurate expectations. None require a hotfix. Each has a
documented path to resolution in a future sprint.

### L1 — YouTube main feed not supported

**What happens:** Creators who set platform to `youtube` (the main channel, not Shorts) receive
`INFO:platform_unknown:youtube` in the API response and no platform-specific packaging hints.
S3.1, S3.2, and S3.3 run normally. Only S3.4 platform adaptation is absent.

**Root cause:** `_KNOWN_PLATFORMS` contains `youtube_shorts` but not `youtube`. Main-channel
content has a different pacing and duration profile that requires separate calibration data.

**Creator guidance:** For YouTube Shorts → use `youtube_shorts`. For YouTube main feed → leave
platform blank; all other S3 modules run fully. Platform adaptation will not be applied.

**Resolution:** Future platform expansion sprint with YouTube main-channel calibration data.
Requires `CALIBRATION_FROZEN=false` authorization.

### L2 — Weak source material degrades gracefully, not silently

**What happens:** Clips with `segment_score < 45` are excluded from retention prediction (S3.2
score gate). Clips with `segment_score < 60` receive no packaging guidance (S3.1 packaging gate).
These clips still render normally — S3 simply has no output for them.

**Visible signal:** `s3_health_summary.packaging.clips_processed < clips_attempted` when some
clips are below the packaging gate. No WARN is emitted (zero-processed is expected behavior).

**Creator guidance:** S3 output is most useful for clips with high selection scores. Clips that
the AI selected with lower confidence naturally receive less S3 enrichment. This is by design.

**Resolution:** Not a bug. If creators want more S3 coverage, `S3_PACKAGING_MIN_SCORE` and
`S3_RETENTION_MIN_SCORE` can be lowered — but this risks noise on low-quality clips. Requires
a calibration sprint to evaluate the trade-off.

### L3 — Bad audio lowers retention confidence

**What happens:** Clips with heavily fragmented speech (high filler words, low speech density,
broken sentence structure) receive lower retention scores. The `hook_weakness` risk is correctly
flagged when no clear opener signal is detected. Retention `prediction_confidence` is lower for
these clips.

**Visible signal:** `retention_explanation.risks: ["hook_weakness"]` with `retention_score` in
the 48–58 range.

**Creator guidance:** This is the system working correctly — poor audio quality genuinely reduces
retention likelihood. The risk flag is informational; the creator can still use the clip.

**Resolution:** Not a bug. Future improvement (S4 scope): audio quality signal to weight
confidence rather than penalize score directly.

### L4 — No opener → conservative packaging (expected)

**What happens:** Clips with `hook_intelligence_type = none` and `moment_type = unknown` receive
`packaging = {}` (no packaging guidance). This is the score-gate and signal-gate working together.

**Visible signal:** `packaging_applied: {}` in `selected_segments` for those clips.
`s3_health_summary.packaging.clips_processed` will be lower than `clips_attempted`.

**Creator guidance:** The AI cannot improve packaging for clips it cannot read. A clip with no
detected hook type is likely mid-content — packaging guidance would be speculative. The render
still proceeds with the creator's chosen style.

**Resolution:** Not a bug. Improving hook detection coverage (S2 scope) would increase packaging
coverage downstream.

---

## 7. Configuration Reference

### Production-safe configuration

```
# S3 modules — all enabled by default
S3_PACKAGING_ENABLED=1
S3_RETENTION_ENABLED=1
S3_THUMBNAIL_ENABLED=1
S3_PLATFORM_INTELLIGENCE_ENABLED=1
STRUCTURE_INTELLIGENCE_ENABLED=1

# Debug — OFF in production
S3_DEBUG_ENABLED=0

# Frozen calibration defaults
S3_RETENTION_BASE_SCORE=68
S3_RETENTION_DEAD_ZONE_THRESHOLD=0.26
S3_RETENTION_PROMISE_PENALTY=16
S3_RETENTION_MIN_SCORE=45
S3_PLATFORM_CONFIDENCE_MIN=0.12
S3_STRUCTURE_DETECT_THRESHOLD=0.50
```

### Staging/investigation configuration

```
# Enable debug for per-clip signal inspection
S3_DEBUG_ENABLED=1

# All other settings identical to production
```

### Emergency rollback configuration

```
S3_PACKAGING_ENABLED=0
S3_RETENTION_ENABLED=0
S3_THUMBNAIL_ENABLED=0
S3_PLATFORM_INTELLIGENCE_ENABLED=0
STRUCTURE_INTELLIGENCE_ENABLED=0
```
