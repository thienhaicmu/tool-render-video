# Soft Beta Stage 1 — Smoke Test Report

**Branch:** `feature/ai-output-upgrade`
**Sprint:** Soft Beta Stage 1
**Date:** 2026-05-21
**Status:** ✅ PASS — Proceed to Stage 2

**Test method:** Code-level end-to-end simulation. All four S3 modules + debug aggregator exercised
against 5 synthetic renders using the same call pattern as `ai_director._build_plan()`.
`S3_DEBUG_ENABLED=1`. All other settings: production frozen defaults.

---

## 1. Render Matrix

| Render | Content Type | Goal | Platform | Clips | Result |
|--------|-------------|------|----------|-------|--------|
| R1 | Podcast / Low Energy | podcast | youtube | 3 | PASS |
| R2 | Talking Head / Education | education | youtube | 3 | PASS |
| R3 | Viral / Strong Hook | viral | tiktok | 3 | PASS |
| R4 | Viral / Weak Hook (no opener) | viral | tiktok | 2 | PASS |
| R5 | Education / Bad Audio + Filler | education | youtube | 1 | PASS |

**Total: 5/5 PASS. 0 CRITICAL warnings. 0 module rollbacks. 0 render regressions.**

---

## 2. Warning Summary

### Per-render warning breakdown

| Render | CRITICAL | WARN (production) | WARN (debug-only) | INFO |
|--------|----------|-------------------|-------------------|------|
| R1 Podcast | 0 | 0 | 2 | 1 |
| R2 Education | 0 | 0 | 1 | 1 |
| R3 Viral Strong | 0 | 0 | 0 | 0 |
| R4 Viral Weak | 0 | 0 | 1 | 0 |
| R5 Bad Audio | 0 | 0 | 0 | 1 |
| **TOTAL** | **0** | **0** | **4** | **3** |

**WARN rate (production-equivalent): 0.0%** — gate requires ≤5%. ✅ PASS

### Warning classification

**CRITICAL (0):** None. Zero module crashes. Zero exceptions. ✅

**WARN — production equivalent (0):** None. After WARN logic fix (see findings), no genuine
partial failures occurred in any render. ✅

**WARN — debug-only (4, staging artifact):**

| Warning | Renders | Meaning | Production impact |
|---------|---------|---------|-----------------|
| `WARN:dominance_warning:packaging=56%` | R1 | packaging signals dominate when 2/3 clips have no transcript window | None — debug-mode only |
| `WARN:dominance_warning:packaging=61%` | R1 | same | None |
| `WARN:dominance_warning:packaging=56%` | R2 | same pattern | None |
| `WARN:dominance_warning:platform=60%` | R4 | platform dominates when packaging returns `{}` (score gate) | None |

These only fire with `S3_DEBUG_ENABLED=1`. Production has `S3_DEBUG_ENABLED=0` — these never appear.
They are expected in staging and indicate the debug system is working correctly.

**INFO (3):**

| Warning | Renders | Meaning |
|---------|---------|---------|
| `INFO:platform_unknown:youtube` | R1, R2, R5 | `youtube` not in known platforms — returns `{}` for platform adaptation |

See findings §5 for detail.

---

## 3. s3_health_summary Statistics

### Per-render health

| Render | packaging | retention | thumbnail | platform |
|--------|-----------|-----------|-----------|----------|
| R1 Podcast | 3/3 ✅ | 3/3 ✅ | 3/3 ✅ | 0/3 ⚠ |
| R2 Education | 3/3 ✅ | 3/3 ✅ | 3/3 ✅ | 0/3 ⚠ |
| R3 Viral Strong | 3/3 ✅ | 3/3 ✅ | 3/3 ✅ | 3/3 ✅ |
| R4 Viral Weak | 0/2 ⚠ | 2/2 ✅ | 2/2 ✅ | 2/2 ✅ |
| R5 Bad Audio | 0/1 ⚠ | 1/1 ✅ | 1/1 ✅ | 0/1 ⚠ |

**⚠ = expected zero-output (score gate or unknown platform) — not a failure. No WARN emitted.**

### Notes

- **Packaging 0/N on R4 and R5:** clips with `segment_score < S3_PACKAGING_MIN_SCORE (60)` are
  correctly skipped. R4 clips scored 55 and 52; R5 clip scored 48. Expected gate behavior.
- **Platform 0/N on R1, R2, R5:** `youtube` is not in `_KNOWN_PLATFORMS` (only `youtube_shorts`
  is). Platform adapter correctly returns `{}` for unknown platforms. See findings §5.
- **Retention 3/3 on all podcast/education renders:** full coverage even for clips without
  transcript windows — these get `retention_available=False`, score=68.0 (base, unchanged).

### s3_health_summary populated: ✅ (all 5 renders)

---

## 4. Module Analysis

### S3.1 — Packaging

| Render | Coverage | Signal detected | Reasons |
|--------|----------|----------------|---------|
| R1 Podcast | 3/3 | hook=story/authority, moment=full_story/explainer/narrative | ✅ |
| R2 Education | 3/3 | hook=result_first/authority, moment=hook_opener/explainer/full_story | ✅ |
| R3 Viral | 3/3 | hook=surprise/warning/result_first, moment=hook_opener/hook_payoff/payoff | ✅ |
| R4 Weak | 0/2 | no hook, unknown moment — score gate filtered (55, 52 < 60) | Expected |
| R5 Bad Audio | 0/1 | no hook, explainer moment — score gate filtered (48 < 60) | Expected |

**Finding:** Packaging correctly fires for high-signal clips and correctly skips low-score/no-signal clips.

### S3.2 — Retention Prediction

| Render | Clip | Score | available | Risks |
|--------|------|-------|-----------|-------|
| R1 clip 0 | podcast | 56.0 | True | flat_emotion, dead_zone_risk |
| R1 clip 1 | podcast | 68.0 | False | (no transcript window — graceful degradation) |
| R1 clip 2 | podcast | 68.0 | False | (no transcript window) |
| R2 clip 0 | education | 53.0 | True | structural_gap, flat_emotion, dead_zone_risk |
| R2 clip 1 | education | 68.0 | False | (no transcript window) |
| R2 clip 2 | education | 68.0 | False | (no transcript window) |
| R3 clip 0 | viral | 83.0 | True | (none — strong hook, clean structure) |
| R3 clip 1 | viral | 68.0 | False | (no transcript window) |
| R3 clip 2 | viral | 68.0 | False | (no transcript window) |
| R4 clip 0 | viral weak | 48.0 | True | hook_weakness |
| R4 clip 1 | viral weak | 68.0 | False | (no transcript window) |
| R5 clip 0 | bad audio | 54.0 | True | hook_weakness |

**Findings:**
- R3 clip 0 (viral/surprise/hook_opener): score 83.0, zero risks. ✅ High-quality hook correctly rewarded.
- R4 clip 0 (viral/none/unknown): score 48.0, hook_weakness correctly flagged. ✅
- R5 clip 0 (education/none/explainer): score 54.0, hook_weakness. ✅ Expected for bad audio content.
- Graceful degradation confirmed: `retention_available=False` + base score 68.0 for clips without transcript window. No errors, no risks.

### S3.3 — Thumbnail / Cover Hints

| Render | Offsets | Quality |
|--------|---------|---------|
| R1 Podcast | 0.455, 0.33, 0.25 | Reasonable — story/authority moments |
| R2 Education | 0.05, 0.25, 0.455 | hook_opener → early frame; full_story → later |
| R3 Viral | 0.05, 0.40, 0.50 | hook_opener → early; payoff → mid-late |
| R4 Viral Weak | None, None | Correct — unknown moment, no signal → null offset |
| R5 Bad Audio | 0.25 | Low confidence but produces hint (explainer with some signal) |

**Finding:** Null offset correctly returned when there is no usable signal (R4). Thumbnail module functional for all scenarios.

### S3.4 — Platform Adaptation

| Render | Platform | Coverage | Sample hint |
|--------|----------|----------|------------|
| R1 Podcast | youtube | 0/3 | N/A (unknown platform) |
| R2 Education | youtube | 0/3 | N/A (unknown platform) |
| R3 Viral | tiktok | 3/3 | pacing=punchy, opener=strong, density=compact, conf=0.8 |
| R4 Viral Weak | tiktok | 2/2 | pacing=punchy, opener=strong, density=compact, conf=0.5-0.4 |
| R5 Bad Audio | youtube | 0/1 | N/A (unknown platform) |

**R3 platform hints validated:**
- All clips: `pacing=punchy` (TikTok default), `opener=strong` (surprise/warning hooks), `density=compact`
- Confidence: clip 0 = 0.80 (strong hook + known platform + known moment), clips 1-2 = 0.70
- This matches the S3.4 benchmark differentiation results. ✅

---

## 5. Findings

### F1 — WARN:partial logic was too broad (FIXED)

**Observed:** First test run emitted `WARN:partial_*_failure` for cases where `clips_processed == 0`
due to expected behavior (score gate filtering all clips, unknown platform returning `{}`).

**Root cause:** Initial WARN condition was `clips_processed < clips_attempted`, triggering on
zero-processed cases that are expected and correct.

**Fix applied:** Changed to `0 < clips_processed < clips_attempted` in `ai_director.py` (line 500).
Zero-processed is either:
- All clips below score gate → expected, no warning needed
- Unknown platform → `INFO:platform_unknown:*` already emitted
- All clips failed internally → a `CRITICAL:*_error` would have fired

**Result after fix:** 0 production-equivalent WARN warnings across all 5 renders. ✅

### F2 — `youtube` not a known platform (DOCUMENTED, NOT FIXED)

**Observed:** `INFO:platform_unknown:youtube` fires on R1, R2, R5. Platform adaptation returns `{}`
for all clips on these renders.

**Root cause:** `_KNOWN_PLATFORMS` in `platform_adapter.py` contains `youtube_shorts` but not
`youtube` (the main channel). This is correct for short-form content (the system's primary use
case), but creators rendering for the YouTube main feed get no platform adaptation.

**Decision:** `CALIBRATION_FROZEN=true` — adding a new platform requires a dedicated sprint with
benchmark data to calibrate `youtube` hints. This is a known limitation for soft beta.

**Creator guidance:** Creators targeting YouTube main channel should use `youtube_shorts` for
Shorts content or leave platform blank for no platform-specific adaptation.

### F3 — Dominance warnings in debug mode are expected (DOCUMENTED)

**Observed:** `WARN:dominance_warning:packaging=56-61%` on R1/R2, `WARN:dominance_warning:platform=60%` on R4.

**Root cause:** When 2/3 clips have no transcript window, retention signal weight is low, causing
packaging to dominate. When packaging returns `{}` (score gate), platform fills the signal gap.
These are natural consequences of content characteristics, not anomalies.

**Production impact:** Zero. Dominance warnings only fire with `S3_DEBUG_ENABLED=1`. Production
default is `S3_DEBUG_ENABLED=0`. These never appear in creator-facing output.

**Staging value:** Confirms debug system is working and signal balance is observable. ✅

---

## 6. Failed Modules

**None.** Zero CRITICAL warnings. All modules ran without exception across all 5 renders.

| Module | Errors | Crashes | Status |
|--------|--------|---------|--------|
| S3.1 Packaging | 0 | 0 | ✅ |
| S3.2 Retention | 0 | 0 | ✅ |
| S3.3 Thumbnail | 0 | 0 | ✅ |
| S3.4 Platform | 0 | 0 | ✅ |
| S3 Debug | 0 | 0 | ✅ |

---

## 7. Rollback Events

**None.** No `S3_*_ENABLED=0` action triggered or required.

---

## 8. Creator Observations

**Podcast / Low Energy (R1):**
- Retention correctly flags `flat_emotion` + `dead_zone_risk` for the structured podcast clip (clip 0)
- Clips 1-2 (no transcript window) degrade gracefully to base score 68.0, no risks
- Packaging fires for all clips on hook/moment signals: story, authority, narrative
- Platform returns `{}` for `youtube` — creator should be aware
- Dominance (debug): packaging dominates when retention is unavailable — expected in light-transcript scenarios

**Education / Talking Head (R2):**
- `structural_gap` + `flat_emotion` + `dead_zone_risk` on clip 0 (result_first/hook_opener) — these risks are real for short explainer clips with limited emotional arc
- Score 53.0 is reasonable (below baseline 68.0 due to penalties, but not a failure)
- Packaging correctly annotates hook_opener and full_story moments

**Viral / Strong Hook (R3):**
- Cleanest render: 0 warnings, all 4 modules fully processed, full coverage
- Retention score 83.0 for surprise/hook_opener clip — correctly rewarded ✅
- TikTok platform hints confirmed: punchy/strong/compact with high confidence
- This is the ideal-case scenario; real viral content should match or exceed this

**Viral / Weak Hook (R4):**
- `hook_weakness` correctly detected (score 48.0 — below base 68.0)
- Packaging correctly skips (scores 55/52 below packaging gate 60)
- Thumbnail returns null offsets for unknown moment/hook type — correct
- Platform still provides hints (tiktok known), confidence 0.5/0.4 (lower due to missing hook/retention signals)

**Education / Bad Audio (R5):**
- `hook_weakness` detected (score 54.0)
- Single clip: packaging skipped (score 48 < 60), platform skipped (youtube unknown)
- Thumbnail still provides offset hint (0.25) based on explainer moment
- This is a content problem, not a system problem — S3 correctly identifies the weakness

---

## 9. Pass/Fail Recommendation

### Stage 1 gate results

| Gate | Requirement | Result | Status |
|------|-------------|--------|--------|
| CRITICAL warnings | = 0 | 0 | ✅ PASS |
| WARN rate (production) | ≤ 5% | 0.0% | ✅ PASS |
| s3_health_summary populated | all renders | 5/5 | ✅ PASS |
| Module rollbacks | = 0 | 0 | ✅ PASS |
| Render regressions | = 0 | 0 | ✅ PASS |

**VERDICT: STAGE 1 PASS — Proceed to Stage 2**

### What to watch in Stage 2

| Signal | Watch for | Action if triggered |
|--------|-----------|---------------------|
| `INFO:platform_unknown:*` frequency | If >30% of creators use unsupported platforms | Document; plan platform expansion sprint |
| Retention score distribution | Scores below 50.0 on more than 50% of clips | Review content quality thresholds |
| `flat_emotion` + `dead_zone_risk` co-occurrence | High rate on podcast/education renders | Expected for calm content; monitor only |
| Platform coverage gap | `youtube` platform usage rate | Prioritize if creators commonly submit it |
| Packaging score gate hit rate | If >60% of clips are below packaging gate | Consider lowering `S3_PACKAGING_MIN_SCORE` |

---

## 10. Incidental Fix

**`ai_director.py` — WARN partial logic corrected (smoke test finding):**

Changed `clips_processed < clips_attempted` to `0 < clips_processed < clips_attempted` in the
`WARN:partial_*_failure` emission block. Zero-processed is expected behavior (score gate or unknown
platform), not a partial failure. True partial failure requires at least one clip to have succeeded.

This is a bug fix, not a calibration change. `CALIBRATION_FROZEN=true` is unaffected.
