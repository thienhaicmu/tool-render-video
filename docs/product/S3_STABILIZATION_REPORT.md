# S3 Production Intelligence — Stabilization Report

**Branch:** `feature/ai-output-upgrade`
**Sprint:** S3 Stabilization (post S3.4)
**Date:** 2026-05-21
**Status:** ✅ Complete

---

## Purpose

Harden S3.1–S3.4 for production use. No new features. Scope:
- Externalize all critical constants to env vars
- Add unified per-clip explainability (`clip_production_debug`)
- Validate failure modes
- Prove platform differentiation with measured deltas
- Verify `S3_*_ENABLED=0` bit-identical regression for all 4 modules

---

## RC1 — Debug Gate (S3_DEBUG_ENABLED=0 default)

**Status:** ✅ Applied

New module `backend/app/ai/debug/clip_debug_aggregator.py`:
- `S3_DEBUG_ENABLED=0` (default OFF) — guard at function entry, returns `{}` immediately
- `S3_DEBUG_ENABLED=1` enables full per-clip debug in dev/staging only
- `clip_production_debug` field added to `AIEditPlan` + `to_dict()`
- Debug output is advisory metadata only; zero path to selection, retry, ranking, DNA, or render

Production API: `clip_production_debug = {}` when `S3_DEBUG_ENABLED=0`.

---

## RC2 — Goal-Aware Retention Stacking Cap

**Status:** ✅ Applied

**Problem:** `flat_emotion (−10) + dead_zone_risk (−15) + density_falloff (−8) = −33` worst case.
Podcasts and educational content are naturally low-intensity — a −33 penalty conflates
"calm pacing" with "poor content", producing false high-risk labels.

**Solution:** Accumulate emotion-family penalties into `_emotion_penalty_raw`, then apply
`min(_emotion_penalty_raw, _get_emotion_cap(goal))` before subtracting from score.

**Goal-aware caps (externalized, tunable):**

| Goal | Cap | Rationale |
|------|-----|-----------|
| `viral` | 30 | High-energy format — full penalty range appropriate |
| `storytelling` | 26 | Narrative arcs include quiet moments, moderate cap |
| `education` | 22 | Calm pacing is expected — reduce false positives |
| `podcast` | 20 | Low-intensity by design — "calm ≠ boring" |
| _(fallback)_ | 25 | Conservative middle ground |

**Env override:** `S3_RETENTION_MAX_EMOTION_PENALTY` — applies to all goals when set.

**Before:** podcast clip with flat_emotion + dead_zone + density_falloff → score −33.
**After:** same clip → score capped at −20 (podcast cap). No false high-risk label.

---

## RC3 — Signal Dominance Metrics

**Status:** ✅ Applied

`clip_debug_aggregator._compute_dominance()` computes per-clip confidence-proxy weights:

| Module | Base weight |
|--------|-------------|
| retention | 0.35 |
| packaging | 0.25 |
| thumbnail | 0.20 |
| platform  | 0.20 |

Effective weight = base weight × confidence value (where applicable).

**Dominance warning fires when:** any single signal > `S3_DEBUG_DOMINANCE_THRESHOLD` (default 55%)
of total effective weight for a clip. Warning appended to `plan.warnings` and `clip_debug.warnings`
as `dominance_warning:<module>=<pct>`.

**Gated by `S3_DEBUG_ENABLED`** — dominance check only runs in debug mode; never fires in production.

---

## RC4 — Platform Differentiation Proof

**Status:** ✅ Verified

Two benchmark scenarios measured against all four platforms.

### Scenario A: surprise hook, hook_opener moment, `keyword` style (neutral)

| Platform | pacing_hint | opener_emphasis | subtitle_density | visual_polish | confidence |
|----------|-------------|-----------------|------------------|---------------|------------|
| TikTok | `punchy` | `strong` | `compact` | `standard` | 0.90 |
| YouTube Shorts | `standard` | `strong` | `normal` | `standard` | 0.90 |
| Instagram Reels | `standard` | `strong` | `compact` | `standard` | 0.90 |
| Podcast | `calm` | `moderate` | `readable` | `standard` | 0.90 |

**Key deltas:**
- TikTok vs Shorts: pacing `punchy` vs `standard` (1 step)
- TikTok vs Podcast: pacing `punchy` vs `calm` (2 steps), opener `strong` vs `moderate`
- Reels vs Shorts: density `compact` vs `normal`

### Scenario B: story hook, full_story moment, `clean` style (conservative RC3 clamping)

| Platform | pacing_hint | opener_emphasis | subtitle_density | visual_polish | confidence |
|----------|-------------|-----------------|------------------|---------------|------------|
| TikTok | `standard`* | `moderate`* | `normal`* | `standard` | 0.90 |
| YouTube Shorts | `calm` | `calm` | `normal` | `standard` | 0.90 |
| Instagram Reels | `calm` | `calm` | `normal` | `smooth`† | 0.90 |
| Podcast | `calm` | `calm` | `readable` | `standard` | 0.90 |

`*` = RC3 clamped (clean style prevents TikTok from reaching aggressive end of scale)
`†` = Reels-exclusive: `full_story` on Reels triggers +1 polish step (`standard→smooth`)

**Key deltas:**
- Reels vs Shorts: `smooth` vs `standard` visual polish — unique Reels signal
- TikTok vs Shorts/Reels: RC3 clamping means clean-style TikTok is `standard` pacing (not `punchy`)
- Podcast vs all others: `readable` density (others: `normal` or `compact`)

**Conclusion:** TikTok ≠ Shorts ≠ Reels ≠ Podcast. Differentiation proven across both neutral and conservative-style scenarios.

---

## RC5 — Unknown Platform Warning Rate-Limiting

**Status:** ✅ Applied

`ai_director._build_plan()` S3.4 block:
- If `target_platform` is non-empty but not in `_KNOWN_PLATFORMS`, appends
  `platform_unknown:<name>` to `plan.warnings` — **at most once per render**.
- Guard: `if _unknown_warn not in plan.warnings` prevents duplicate appends.
- Empty `target_platform` (platform not set) → warning suppressed entirely.
- `plan_platform_adaptation()` still returns `{}` immediately for unknown platforms (no change).

---

## RC6 — Hard No-Op Guarantee

**Status:** ✅ Verified

All four S3 modules:

| Module | Env gate | Behavior at 0 |
|--------|----------|---------------|
| S3.1 Packaging | `S3_PACKAGING_ENABLED=0` | `{}` → `clip_packaging={}`, no packaging applied |
| S3.2 Retention | `S3_RETENTION_ENABLED=0` | `{}` → `clip_retention_prediction={}` |
| S3.3 Thumbnail | `S3_THUMBNAIL_ENABLED=0` | `{}` → `clip_cover_hints={}`, `cover_hint_ratio=None` at UP15 |
| S3.4 Platform | `S3_PLATFORM_INTELLIGENCE_ENABLED=0` | `{}` → `clip_platform_adaptation={}` |
| S3 Debug | `S3_DEBUG_ENABLED=0` | `{}` → `clip_production_debug={}` |

RC6 hard requirement: "if no usable signals exist, must remain bit-identical, NO fake defaults."

- `hook_intelligence_type=none` + `moment_type=unknown` → packaging `{}`, thumbnail null hint
- Unknown platform → `{}` immediately (no partial hints emitted)
- No transcript window → `retention_available=False`, score `65.0` (unchanged base), no risk flags
- Import failure for any module → try/except guard → `{}`, warning appended, plan continues

---

## Threshold Externalization Summary

All critical thresholds now configurable via env vars (no code changes required for calibration):

### retention_predictor.py
| Env var | Default | Description |
|---------|---------|-------------|
| `S3_RETENTION_BASE_SCORE` | `65.0` | Base score before adjustments |
| `S3_RETENTION_DEAD_ZONE_THRESHOLD` | `0.22` | Flat fraction threshold |
| `S3_RETENTION_DEAD_ZONE_MULTIPLIER` | `45.0` | Dead-zone penalty scaling |
| `S3_RETENTION_ARC_VARIANCE_MIN` | `15.0` | Minimum variance for arc detection |
| `S3_RETENTION_DENSITY_FALLOFF_RATIO` | `0.60` | Second/first half density threshold |
| `S3_RETENTION_HOOK_PENALTY` | `20.0` | Hook absence penalty |
| `S3_RETENTION_PROMISE_PENALTY` | `18.0` | Unfulfilled promise-hook penalty |
| `S3_RETENTION_GENERIC_PENALTY` | `12.0` | Generic payoff-absence penalty |
| `S3_RETENTION_MAX_EMOTION_PENALTY` | _(unset)_ | Override all goal caps |

### cover_hint_planner.py
| Env var | Default | Description |
|---------|---------|-------------|
| `S3_THUMBNAIL_STRONG_HOOK_NUDGE` | `0.10` | Surprise/warning/result_first offset pull |
| `S3_THUMBNAIL_SOFT_HOOK_NUDGE` | `0.08` | Story/authority offset push |

### platform_adapter.py
| Env var | Default | Description |
|---------|---------|-------------|
| `S3_PLATFORM_CONF_BASE` | `0.20` | Base confidence |
| `S3_PLATFORM_CONF_PLATFORM` | `0.20` | Platform-known contribution |
| `S3_PLATFORM_CONF_STRATEGY` | `0.15` | Strategy-available contribution |
| `S3_PLATFORM_CONF_MOMENT` | `0.20` | Moment-known contribution |
| `S3_PLATFORM_CONF_HOOK` | `0.10` | Hook-known contribution |
| `S3_PLATFORM_CONF_RETENTION` | `0.10` | Retention-available contribution |
| `S3_PLATFORM_CONFIDENCE_MIN` | `0.10` | Confidence floor (RC2) |

### clip_debug_aggregator.py
| Env var | Default | Description |
|---------|---------|-------------|
| `S3_DEBUG_ENABLED` | `0` | Enable debug aggregation (default OFF) |
| `S3_DEBUG_DOMINANCE_THRESHOLD` | `0.55` | Signal dominance warning threshold |

---

## Failure Mode Validation

| Scenario | Module | Expected behavior | Status |
|----------|--------|-------------------|--------|
| No transcript window | S3.2 | `retention_available=False`, confidence=0.15, no risks | ✅ |
| `score < threshold` | S3.2/S3.3/S3.4 | Null hints, `retention_available` unchanged | ✅ |
| `emotion_analyzer` import fails | S3.2 | `[]` emotion scores, emotion block skipped | ✅ |
| `silence_analyzer` import fails | S3.2 | `density_falloff=None`, density block skipped | ✅ |
| Unknown platform | S3.4 | `{}` returned, 1 warning appended (rate-limited) | ✅ |
| Empty `target_platform` | S3.4 | `{}` returned, no warning | ✅ |
| `pro_karaoke`/`minimal` style | S3.1 | Immediate `{}` no-op, no warning | ✅ |
| `segment_score < 60` | S3.1 | Clip skipped (RC2 confidence gate) | ✅ |
| All `S3_*_ENABLED=0` | All | `{}` returned, plan unchanged, bit-identical render | ✅ |
| Per-clip exception in any module | All | Try/except swallows, warning appended, other clips unaffected | ✅ |
| Debug module import fails | S3 Debug | `_DEBUG_AVAILABLE=False`, block skipped entirely | ✅ |

---

## Dead Risk Removal

**`low_face_presence` in `cover_hint_planner.py`** — removed.

Audit finding: `content_type_hint` is always `""` on `selected_raw` dicts (the field is only
populated on `AIClipPlan` objects, not on the raw segment dicts passed to S3.3). The risk
`low_face_presence` could never fire. Removed to prevent misleading debug output.

---

## Regression Guarantees

- `S3_*_ENABLED=0` for all modules → behavior bit-identical to pre-S3.1
- No changes to clip count, scoring, selection, diversity, DNA, or render pipeline
- `render_pipeline.py` and `render_engine.py` not modified in this sprint
- All S3 outputs are advisory metadata only — zero feedback path to selection or render
- Try/except guards at import level AND per-clip level — no runtime failures if any module missing
