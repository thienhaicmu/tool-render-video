# S3 Production Intelligence — Soft Beta Readiness

**Branch:** `feature/ai-output-upgrade`
**Sprint:** Post-QA Freeze Sprint
**Date:** 2026-05-21
**Status:** ✅ Ready for Soft Beta

**CALIBRATION_FROZEN=true**

---

## Purpose

This document is the single source of truth for S3 soft beta readiness. It locks the
calibration state established across S3.1–S3.4, the Stabilization Sprint, the Benchmark
Calibration Sprint, and the QA Mini Sprint.

No further calibration is permitted without re-opening a sprint with new benchmark data.

---

## 1. Frozen Production Defaults

These values represent the calibrated, QA-validated production state.
All are env-var overridable; defaults below are the frozen baseline.

| Env Var | Frozen Default | Source | Rationale |
|---------|---------------|--------|-----------|
| `S3_RETENTION_BASE_SCORE` | `68` | Calibration Phase A | Raised from 65; realistic baseline for diverse content |
| `S3_RETENTION_DEAD_ZONE_THRESHOLD` | `0.26` | Calibration Phase A | Relaxed from 0.22; calm pacing ≠ dead zone |
| `S3_RETENTION_PROMISE_PENALTY` | `16` | Calibration Phase A | Reduced from 18; less punishing for partial fulfillment |
| `S3_RETENTION_MIN_SCORE` | `45` | Calibration Phase A | Raised from 40; higher-confidence clips only |
| `S3_PLATFORM_CONFIDENCE_MIN` | `0.12` | Calibration Phase A | Raised from 0.10; suppresses near-zero confidence hints |
| `S3_STRUCTURE_DETECT_THRESHOLD` | `0.50` | QA Mini Sprint | 0.42 REJECTED — see rejected assumptions |
| `S3_RETENTION_DEAD_ZONE_MULTIPLIER` | `45.0` | S3 Stabilization | Unchanged; penalty scaling calibrated at launch |
| `S3_RETENTION_ARC_VARIANCE_MIN` | `15.0` | S3 Stabilization | Unchanged; arc detection sensitivity |
| `S3_RETENTION_DENSITY_FALLOFF_RATIO` | `0.60` | S3 Stabilization | Unchanged; second/first half density threshold |
| `S3_RETENTION_HOOK_PENALTY` | _(goal-aware B1)_ | Calibration B1 | viral=20, storytelling=16, education=14, podcast=12 |
| `S3_THUMBNAIL_STRONG_HOOK_NUDGE` | `0.10` | S3 Stabilization | Unchanged; surprise/warning/result_first offset pull |
| `S3_THUMBNAIL_SOFT_HOOK_NUDGE` | `0.08` | S3 Stabilization | Unchanged; story/authority offset push |
| `S3_DEBUG_ENABLED` | `0` | S3 Stabilization | OFF by default — never enabled in production |
| `S3_DEBUG_DOMINANCE_THRESHOLD` | `0.55` | S3 Stabilization | Debug mode only; dominance warning threshold |

**Goal-aware calibration (code-level, not env-var):**

| Parameter | Goal-Aware Values | Module | Sprint |
|-----------|-------------------|--------|--------|
| Hook absence penalty | viral=20, story=16, edu=14, podcast=12 | S3.2 | B1 |
| Dead zone threshold | viral=0.18, story=0.22, edu=0.24, podcast=0.28 (cap ≤0.30) | S3.2 | B3 |
| Emotion stacking cap | viral=30, story=26, edu=22, podcast=20 | S3.2 | Stabilization RC2 |
| Structure bonus | viral: open_only=5, open_payoff=12, full=18 | S2.3 | S2.3 |

---

## 2. Rejected Calibration Assumptions

### 2.1 — Structure threshold 0.42 (REJECTED)

**Assumption:** Lowering `S3_STRUCTURE_DETECT_THRESHOLD` to 0.42 would improve structure detection
for informal/podcast speech with borderline phase confidence.

**Evidence against:**

| Finding | Detail |
|---------|--------|
| False positive confirmed | marker(0.40) + pos(0.00) + nat_start(0.05) = 0.450; detected at 0.42, rejected at 0.50 |
| Trigger is common | Any clip starting with a dev/payoff marker at ratio<0.10 or ratio<0.63 respectively |
| Zero benefit measured | All 5 tested scenarios: delta=+0.00 across structure score |
| Podcast scenarios already pass | #10 (0.53–0.66), #11 (0.61–0.72) — well above both thresholds |
| Root cause mismatch | Weak scenarios fail due to absent opener markers, not strict threshold |

**Status:** PERMANENTLY REJECTED at this confidence level.

**Re-evaluation condition:** New benchmark data showing ≥3 scenarios with verified true-positive phase
confidence in [0.42, 0.50) that are not reachable via the false-positive path (i.e., the marker
appears at a valid position within the phase's active range, not at ratio=0).

### 2.2 — Universal emotion penalty cap (DEFERRED, not rejected)

**Assumption considered (not tested):** A single flat emotion penalty cap across all goals.

**Reason not pursued:** Goal-aware caps (viral=30, storytelling=26, education=22, podcast=20) already
implement this with appropriate differentiation. A universal cap would collapse goal-specific behavior.
No new testing needed; the existing goal-aware implementation is the correct approach.

---

## 3. Soft Beta Launch Checklist

### 3.1 Render Stability

- [x] `render_pipeline.py` not modified in S3.1–S3.4, Stabilization, Calibration, or QA sprints
- [x] `render_engine.py` not modified in any S3 sprint
- [x] S3.3 cover hint: one extra candidate added via existing mechanism — UP15 scoring logic untouched
- [x] All S3 outputs are advisory metadata only — zero render path feedback
- [x] Per-clip exception in any S3 module → try/except swallows → render continues unaffected

### 3.2 Creator Override Integrity

- [x] Creator controls (goal, style, format, clip count, duration) never overridden by S3
- [x] `pro_karaoke` / `minimal` styles → S3.1 packaging immediate no-op (`{}`)
- [x] Conservative styles (`clean`, `soft`) → S3.4 platform signals capped at mid-scale (RC3)
- [x] No clip count changes from any S3 module
- [x] No scoring/selection changes from S3.2–S3.4 (advisory only, zero path to clip_selector)
- [x] S2.3 structure scoring feeds clip_selector — but `_GOAL_DETECT_THRESHOLDS={}` means behavior is unchanged from pre-QA sprint

### 3.3 Rollback Verification

All S3 modules individually rollback-able via env var:

| Module | Rollback Gate | Behavior at 0 |
|--------|--------------|---------------|
| S3.1 Packaging | `S3_PACKAGING_ENABLED=0` | `{}` → no packaging applied |
| S3.2 Retention | `S3_RETENTION_ENABLED=0` | `{}` → no retention prediction |
| S3.3 Thumbnail | `S3_THUMBNAIL_ENABLED=0` | `{}` → `cover_hint_ratio=None` at UP15 |
| S3.4 Platform | `S3_PLATFORM_INTELLIGENCE_ENABLED=0` | `{}` → no platform adaptation |
| S2.3 Structure | `STRUCTURE_INTELLIGENCE_ENABLED=0` | `0.0` → no structure bonus |
| S3 Debug | `S3_DEBUG_ENABLED=0` | `{}` → no debug output (default) |

`S3_*_ENABLED=0` for all modules → behavior bit-identical to pre-S3.1. Verified in S3 Stabilization RC6.

### 3.4 Env Defaults Frozen

- [x] All frozen defaults documented in Section 1 above
- [x] `S3_DEBUG_ENABLED=0` — debug is OFF by default; never enabled in production
- [x] `CALIBRATION_FROZEN=true` — no further tuning without sprint approval
- [x] `S3_STRUCTURE_DETECT_THRESHOLD=0.50` — 0.42 rejected (Section 2.1)

### 3.5 Debug Off by Default

- [x] `S3_DEBUG_ENABLED` defaults to `"0"` in `clip_debug_aggregator.py`
- [x] `aggregate_clip_debug()` returns `{}` immediately when `S3_DEBUG_ENABLED=0`
- [x] `clip_production_debug={}` in all production API responses
- [x] Dominance warnings only fire in debug mode — never reach production `plan.warnings`

### 3.6 S3_*_ENABLED Rollback Verified

- [x] Each module has try/except import guard — import failure → module silently skipped
- [x] Each module has per-clip try/except — clip-level failure → warning appended, other clips unaffected
- [x] All `S3_*_ENABLED=0` paths verified bit-identical in S3 Stabilization RC6
- [x] Unknown platform → `{}` immediately, one `platform_unknown:<name>` warning max (RC5)

---

## 4. Known Limitations (not blockers)

These are documented weaknesses that are acceptable for soft beta. They do not block launch.

| # | Limitation | Impact | Path to Resolution |
|---|-----------|--------|-------------------|
| 1 | B-roll clips (#8) get no structure bonus | score_structure=0.0 | Requires clip-level content detection upstream (S4 scope) |
| 2 | Missing opener marker (#15, #20) = 0 structure score | Cannot recover structureless clips | Upstream clip selection improvement (S4 scope) |
| 3 | Average benchmark score 7.13/10 (target ≥8.0) | Below full-launch target | Acceptable for soft beta; requires S4 features to close gap |
| 4 | Vietnamese-only clips may miss some phase markers | Partial structure detection | Marker vocabulary can be extended without threshold change |
| 5 | No real-time per-clip debug in production | Debug requires `S3_DEBUG_ENABLED=1` | By design — debug is opt-in for staging only |

---

## 5. Soft Beta Scope Definition

**What soft beta means for S3:**
- S3.1–S3.4 + all calibration applied to real creator renders
- `S3_DEBUG_ENABLED=0` (production default)
- All `S3_*_ENABLED=1` (all modules active)
- Frozen defaults from Section 1 applied
- No further tuning; monitor outcomes

**Monitoring signals to watch:**
- `packaging_error:*` warnings in plan output → packaging module instability
- `retention_prediction_error:*` → retention predictor failure
- `platform_unknown:*` → unknown platforms being submitted
- Cover hint confidence distribution → `preferred_offset_ratio` hit rate

**Exit criteria for soft beta → full launch:**
- Zero S3-originated render failures across N renders (N = product decision)
- Creator satisfaction feedback ≥ 8.0 on tracked renders
- No `S3_*_ENABLED=0` emergency rollbacks triggered

---

## 6. Sprint History Summary

| Sprint | Commit | Outcome |
|--------|--------|---------|
| S3.1 Packaging Intelligence | — | ✅ |
| S3.2 Retention Prediction | — | ✅ |
| S3.3 Thumbnail/Cover Intelligence | `82a2615` | ✅ |
| S3.4 Platform Intelligence | — | ✅ |
| S3 Stabilization Sprint | `aee7f99` | ✅ RC1–RC6 hardened |
| Creator Benchmark Sprint | `69f32ac` | ✅ 7.09→7.13; B1/B2/B3 calibrated |
| Creator QA Mini Sprint | `6d834c4` | ✅ KEEP 0.50; 0.42 rejected |
| Post-QA Freeze Sprint | _(this commit)_ | ✅ Calibration locked |
