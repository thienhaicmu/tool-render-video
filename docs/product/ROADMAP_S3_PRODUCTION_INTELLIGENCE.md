# S3 Production Intelligence Roadmap

Creator-controlled production layer.
AI packages **according to** clip content. AI NEVER overrides creator intent.

Creator always controls: **goal · style · format · clip count · duration preference**

---

## Philosophy

S2 answered: *which clips?*
S3 answers: *how should each clip be packaged?*

S3 is micro-optimization at the clip level.
Same creator settings — better platform-native feel per clip.

AI may: slightly adjust pacing, slightly soften subtitle motion.
AI must not: switch presets, override style, change clip count.

---

## S3.1 — Packaging Intelligence ✅ Complete

**Shipped:** `feat(ai): S3.1 Packaging Intelligence`

**What shipped:**
- New `packaging/clip_packaging_planner.py` — S2-signal-driven per-clip packaging engine:
  - `plan_clip_packaging(segments, subtitle_style, subtitle_emphasis_base, goal)` → `{clip_idx: packaging_dict}`
  - `_derive_clip_packaging(seg, intensity_base)` → packaging dict or `{}` when no signal applies
  - `_clamp_adjacent(target, base, order)` → RC1 adjacent-only enforcement (soft↔balanced, balanced↔strong)
  - `S3_PACKAGING_ENABLED` / `S3_PACKAGING_MIN_SCORE` env gates (RC6 naming)
  - RC4 hard-block: `pro_karaoke`, `minimal` styles → immediate `{}` no-op, no warning
  - RC2 confidence gate: `segment_score >= S3_PACKAGING_MIN_SCORE` (default 60)
  - RC3 explainability: each packaging dict includes `"reason": [...]` signal list
  - Signal table: hook_type → subtitle_intensity target (adjacent-clamped from mode base)
  - Moment table: `payoff / hook_payoff / hook_opener / full_story / explainer / narrative` → 4-dimension hint pack
- `clip_selector._select_diverse()`: S2 context exposed before `_` fields are stripped:
  - `hook_intelligence_type`, `structure_phases`, `moment_type` added to each output dict
- `edit_plan_schema.AIClipPlan`: S2 carry-through fields + packaging slot:
  - `hook_intelligence_type`, `structure_phases`, `moment_type`, `content_type_hint`
  - `packaging_applied: dict` — per-clip packaging guidance on the clip object
  - All 5 new fields included in `to_dict()` `selected_segments` output
- `edit_plan_schema.AIEditPlan`: `clip_packaging: dict` field + `to_dict()` entry
- `ai_director._build_plan()`:
  - S2 fields carried from `selected_raw` into `AIClipPlan` constructor
  - Packaging planner called after `plan.creator_dna_applied` (after all S2 signals are resolved)
  - `plan.clip_packaging` populated; `seg_plan.packaging_applied` attached per clip
  - Try/except guarded — packaging failure appends `packaging_error:…` warning, never raises

**Render pipeline:** NOT modified. RC5 trivially satisfied — packaging is advisory metadata only.

**Files affected:**
- `backend/app/ai/packaging/__init__.py` (new)
- `backend/app/ai/packaging/clip_packaging_planner.py` (new)
- `backend/app/ai/director/clip_selector.py`
- `backend/app/ai/director/edit_plan_schema.py`
- `backend/app/ai/director/ai_director.py`

**Regression guarantees:**
- All packaging imports try/except guarded — zero runtime failures if module missing
- `S3_PACKAGING_ENABLED=0` disables entirely; behavior identical to pre-S3.1
- `packaging={}` produces bit-identical render output (render pipeline untouched)
- `subtitle_style` in `{pro_karaoke, minimal}` → packaging skips entirely, no warning
- `segment_score < 60` → clip skipped (RC2 confidence gate)
- Adjacent-only clamping: `soft→strong` blocked, only `soft→balanced` or `balanced→strong` allowed
- `hook_intelligence_type=none` + `moment_type=unknown` → clip produces `{}` (no packaging)
- No changes to clip count logic, scoring formulas, render pipeline, or external APIs

---

## S3.2 — Retention Prediction ✅ Complete

**Shipped:** `feat(ai): S3.2 Retention Prediction`

**What shipped:**
- New `analyzers/retention_predictor.py` — per-clip retention likelihood engine:
  - `predict_clip_retention(selected_raw, chunks, goal)` → `{clip_idx: retention_dict}`
  - `_predict_one(seg, all_chunks, goal)` — per-clip scoring from S2 carry-through signals
  - `_get_window_chunks()` — re-slices full transcript by clip start/end (same logic as moment_analyzer)
  - `_compute_emotion_scores()` — per-chunk emotion intensity via existing emotion_analyzer
  - `_compute_dead_zone_ratio()` — RC4: contiguous flat zone detection, fires at ≥22% threshold
  - `_compute_density_falloff()` — second_half_avg / first_half_avg density ratio
  - `S3_RETENTION_ENABLED` / `S3_RETENTION_MIN_SCORE` env gates (RC6 naming)
  - Six retention factors: `hook_weakness`, `payoff_absence`, `unfulfilled_hook_promise`, `flat_emotion`, `dead_zone_risk`, `structural_gap`, `density_falloff`
  - RC1 architectural constraint documented in module docstring and function docstring
  - RC2: `prediction_confidence` field [0, 1] — reflects signal depth, not prediction certainty
  - RC3: hook→payoff coherence penalty: −18 for promise hooks (result_first/challenge/surprise/warning/authority), −12 for generic opening-only
  - RC4: dead-zone only fires at ≥22% clip flat ratio, requires ≥3 consecutive flat chunks
  - RC5: `retention_explanation: {strengths, risks}` explainability per clip
- `edit_plan_schema.AIClipPlan`: `retention_prediction: dict` field + `to_dict()` entry
- `edit_plan_schema.AIEditPlan`: `clip_retention_prediction: dict` field + `to_dict()` entry
- `ai_director._build_plan()`:
  - Try-import guard at module level
  - Called after S3.1 packaging (after all S2 signals resolved)
  - `plan.clip_retention_prediction` populated; `seg_plan.retention_prediction` attached per clip
  - Try/except guarded — prediction failure appends `retention_prediction_error:…`, never raises

**Distinct from Phase 16 retention (plan.retention):**
- Phase 16: whole-video analysis using story + pacing + subtitle context
- S3.2: per-clip window analysis using S2 signals + transcript chunks

**Files affected:**
- `backend/app/ai/analyzers/retention_predictor.py` (new)
- `backend/app/ai/director/edit_plan_schema.py`
- `backend/app/ai/director/ai_director.py`

**Regression guarantees:**
- RC1 hard-enforced: `retention_score` has zero path back to clip_selector, segment_builder, retry_analyzer, diversity_analyzer, or dna_engine
- All imports try/except guarded — zero runtime failures if module missing
- `S3_RETENTION_ENABLED=0` → returns `{}`, plan unchanged, bit-identical behavior (RC6)
- Scene fallback clips (no transcript): `retention_available=False`, `prediction_confidence=0.15`, no risk flags
- `emotion_analyzer` unavailable → empty emotion scores, dead-zone/arc/flat paths skipped gracefully
- No changes to clip count logic, scoring formulas, selection, render pipeline, or external APIs

---

## S3.3 — Thumbnail/Cover Intelligence ✅ Complete

**Shipped:** `feat(ai): S3.3 Thumbnail/Cover Intelligence` — commit `82a2615`

**What shipped:**
- New `thumbnail/cover_hint_planner.py` — S2-signal-driven per-clip frame hint engine:
  - `plan_cover_hints(selected_raw, retention_predictions, goal, packaging_applied)` → `{clip_idx: cover_hint_dict}`
  - `_hint_one(seg, retention, pkg_for_clip)` → hint dict or null-ratio dict
  - `S3_THUMBNAIL_ENABLED` / `S3_THUMBNAIL_MIN_SCORE` env gates (RC1 naming)
  - RC2 confidence gate: `segment_score >= S3_THUMBNAIL_MIN_SCORE` (default 40); weak clips → null hint
  - RC3: `packaging_applied[idx]` non-empty (S3.1 crop metadata) → +0.08 confidence bonus; no new CV
  - RC4 `thumbnail_risks` list: `late_payoff`, `low_face_presence`, `weak_expression`, `low_signal`, `scene_fallback`
  - RC6 `preferred_offset_ratio`: clamped `[0.05, 0.90]` of clip duration; `None` when no signals
  - Moment-type → offset range table: payoff / hook_payoff / hook_opener / full_story / explainer / narrative
  - Hook-type → offset nudge table: surprise/warning/result_first (−0.10) · story/authority (+0.08)
  - Confidence accumulation: base (0.20) + hook (0.20) + moment (0.25) + retention (0.15) + structure (0.10) + crop meta (0.08)
- `thumbnail/__init__.py` (new) — package marker
- `edit_plan_schema.AIClipPlan`: `cover_hint: dict` field + `to_dict()` entry
- `edit_plan_schema.AIEditPlan`: `clip_cover_hints: dict` field + `to_dict()` entry
- `ai_director._build_plan()`:
  - Try-import guard at module level (`_COVER_AVAILABLE`, `_COVER_ENABLED`)
  - S3.3 block after S3.2 — `plan.clip_cover_hints` populated; `seg_plan.cover_hint` attached per clip
  - `packaging_applied=plan.clip_packaging` passed to planner (RC3 crop meta)
  - Try/except guarded — failure appends `cover_hint_error:…` warning, never raises
- `render_pipeline._select_cover_frame_time()`:
  - New `cover_hint_ratio: float | None = None` kwarg (backward-compatible, default None = exact no-op)
  - RC6: hint appended as one extra candidate only; deduplicated against existing 5 candidates
  - UP15 scoring logic untouched — hint is one more option, not an override
- `render_pipeline` UP15 call site:
  - Looks up `_ai_edit_plan.clip_cover_hints.get(idx - 1)` before calling `_select_cover_frame_time`
  - Whole lookup in try/except — failure leaves `cover_hint_ratio=None` (exact no-op)

**Files affected:**
- `backend/app/ai/thumbnail/__init__.py` (new)
- `backend/app/ai/thumbnail/cover_hint_planner.py` (new)
- `backend/app/ai/director/edit_plan_schema.py`
- `backend/app/ai/director/ai_director.py`
- `backend/app/orchestration/render_pipeline.py`

**Regression guarantees:**
- `S3_THUMBNAIL_ENABLED=0` → `{}` returned → `clip_cover_hints={}`, all `cover_hint={}` → `cover_hint_ratio=None` at UP15 → bit-identical to pre-S3.3
- `cover_hint_planner` import fails → `_COVER_AVAILABLE=False` → S3.3 block skipped entirely
- Per-clip hint failure → try/except swallows; other clips unaffected; `cover_hint_error:…` appended
- `cover_hint_ratio=None` → no extra candidate added; `_select_cover_frame_time` unchanged
- `preferred_offset_ratio=None` (weak clip / no signals) → `cover_hint_ratio=None` at UP15 → no-op
- UP15 hint lookup failure (try/except) → `_cover_hint_ratio=None` → UP15 runs exactly as today
- `packaging_applied={}` (S3.1 disabled) → RC3 bonus never fires; confidence slightly lower, no functional change
- `segment_score < 40` → null hint; UP15 runs unchanged for that clip
- No changes to clip count, scoring, selection, diversity, DNA, render engine, or external APIs
- `cover_hint` advisory only — has zero import path back to clip_selector, retry_analyzer, diversity_analyzer, or dna_engine

---

## S3.4 — Platform Intelligence ✅ Complete

**Shipped:** `feat(ai): S3.4 Platform Intelligence`

**What shipped:**
- New `platform/platform_adapter.py` — S2-signal × platform cross-reference engine:
  - `plan_platform_adaptation(selected_raw, platform_render_strategy, goal, target_platform, subtitle_style)` → `{clip_idx: adaptation_dict}`
  - `_adapt_one(seg, platform, subtitle_style, strategy_ctx)` → adaptation dict
  - `_step(current, delta, order)` — adjacent-only intensity shifts on ordered scales
  - `_clamp_for_style(target, subtitle_style, order)` — RC3 conflict suppression (conservative → mid-scale cap)
  - `S3_PLATFORM_INTELLIGENCE_ENABLED` / `S3_PLATFORM_MIN_SCORE` env gates
  - RC1 confidence gate: `segment_score >= S3_PLATFORM_MIN_SCORE` (default 40); weak clips → null hints
  - RC2 confidence bounded: `max(0.10, min(0.90, conf))` — heuristic only, never certainty=1.0
  - RC3 platform conflict suppression: `_CONSERVATIVE_STYLES` (`{minimal, clean, soft}`) capped at mid-scale; `_AGGRESSIVE_STYLES` allow full platform target
  - RC4 `platform_reason` list: `["platform=tiktok", "moment=hook_opener", "hook=surprise", "retention=low", "style_clamped=clean"]`
  - RC5 exact no-op: `S3_PLATFORM_INTELLIGENCE_ENABLED=0` → `{}`
  - RC6 future consumer guard: docstring + comments enforce advisory-only architectural constraint
  - Four output hints per clip: `pacing_hint`, `opener_emphasis`, `subtitle_density_hint`, `visual_polish_hint`
  - Per-platform default tables: TikTok (punchy/strong/compact/standard), Shorts (standard/moderate/normal/standard), Reels (standard/moderate/compact/high), Podcast (calm/calm/readable/standard)
  - Per-clip signal modulation: payoff moment → +1 pacing step; soft hook → −1 pacing & opener step; strong hook → +1 opener step; Reels full_story/narrative → +1 polish step
  - `platform_risks` list: `hook_too_slow`, `payoff_unclear`, `subtitle_crowded`, `style_conflict`, `low_signal`
  - Unknown platform → `{}` immediately (no partial hints)
- `platform/__init__.py` (new) — package marker
- `edit_plan_schema.AIClipPlan`: `platform_adaptation: dict` + `to_dict()` entry
- `edit_plan_schema.AIEditPlan`: `clip_platform_adaptation: dict` + `to_dict()` entry
- `ai_director._build_plan()`:
  - Try-import guard at module level (`_PLATFORM_ADAPT_AVAILABLE`, `_PLATFORM_ADAPT_ENABLED`)
  - S3.4 block after S3.3 — enriches `selected_raw` with `retention_prediction` per clip before calling adapter
  - `plan.clip_platform_adaptation` populated; `seg_plan.platform_adaptation` attached per clip
  - `platform_render_strategy=plan.platform_render_strategy` passed (Phase 55E output)
  - `subtitle_style` from request passed for RC3 conflict suppression
  - Try/except guarded — failure appends `platform_adaptation_error:…` warning, never raises

**Distinct from UP14 (_PLATFORM_PROFILES in render_pipeline.py):**
- UP14: per-job flat nudges (speed_delta, sub_bias) applied at render time — not signal-aware
- S3.4: per-clip, signal-aware advisory hints at plan assembly — UP14 unchanged

**Distinct from Phase 55A–57 (platform knowledge retrieval):**
- Phases 55A–57: job-level platform knowledge contexts (advisory metadata)
- S3.4: per-clip cross-reference layer using Phase 55E output × S2 signals

**Files affected:**
- `backend/app/ai/platform/__init__.py` (new)
- `backend/app/ai/platform/platform_adapter.py` (new)
- `backend/app/ai/director/edit_plan_schema.py`
- `backend/app/ai/director/ai_director.py`

**Regression guarantees:**
- `S3_PLATFORM_INTELLIGENCE_ENABLED=0` → `{}` → `clip_platform_adaptation={}`, all `platform_adaptation={}` → bit-identical to pre-S3.4
- `platform_adapter` import fails → `_PLATFORM_ADAPT_AVAILABLE=False` → block skipped entirely
- Per-clip failure → try/except swallows; `platform_adaptation_error:…` appended; other clips unaffected
- Unknown/empty platform → `{}` immediately; no partial hints emitted
- `render_pipeline.py` not modified — UP14 `_PLATFORM_PROFILES` unchanged
- `render_engine.py` not modified — zero render changes
- Creator `subtitle_style` enforced via RC3 — conservative styles capped at mid-scale
- `platform_adaptation` advisory only — zero import path back to clip_selector, retry_analyzer, diversity_analyzer, dna_engine
- No changes to clip count, scoring, selection, render architecture, or external APIs

---

## S3 Stabilization Sprint ✅ Complete

**Shipped:** `feat(ai): S3 Stabilization Sprint`

**What shipped:**
- `backend/app/ai/analyzers/retention_predictor.py`:
  - All 8 threshold/penalty constants externalized to env vars (`S3_RETENTION_BASE_SCORE`, `S3_RETENTION_DEAD_ZONE_THRESHOLD`, `S3_RETENTION_DEAD_ZONE_MULTIPLIER`, `S3_RETENTION_ARC_VARIANCE_MIN`, `S3_RETENTION_DENSITY_FALLOFF_RATIO`, `S3_RETENTION_HOOK_PENALTY`, `S3_RETENTION_PROMISE_PENALTY`, `S3_RETENTION_GENERIC_PENALTY`)
  - RC2: Goal-aware emotion stacking cap — flat_emotion + dead_zone + density_falloff accumulated into `_emotion_penalty_raw`, capped at `_get_emotion_cap(goal)` (viral=30, storytelling=26, education=22, podcast=20, fallback=25)
  - `S3_RETENTION_MAX_EMOTION_PENALTY` env override applies to all goals
- `backend/app/ai/thumbnail/cover_hint_planner.py`:
  - `_HOOK_OFFSET_NUDGE` values externalized to `S3_THUMBNAIL_STRONG_HOOK_NUDGE` / `S3_THUMBNAIL_SOFT_HOOK_NUDGE`
  - Removed dead `low_face_presence` risk (`content_type_hint` always `""` in selected_raw — structural dead code)
- `backend/app/ai/platform/platform_adapter.py`:
  - All 6 confidence constants externalized to env vars (`S3_PLATFORM_CONF_BASE/PLATFORM/STRATEGY/MOMENT/HOOK/RETENTION`)
  - `S3_PLATFORM_CONFIDENCE_MIN` env var (RC2 floor)
- `backend/app/ai/debug/__init__.py` (new) — package marker
- `backend/app/ai/debug/clip_debug_aggregator.py` (new):
  - `S3_DEBUG_ENABLED=0` default — hard gate, returns `{}` immediately in production
  - `aggregate_clip_debug()` — S3.1–S3.4 per-clip signal aggregation
  - `_compute_dominance()` — RC3 signal balance check, fires warning when any signal > `S3_DEBUG_DOMINANCE_THRESHOLD` (55%)
  - Per-module summarisers: `_summarise_packaging`, `_summarise_retention`, `_summarise_thumbnail`, `_summarise_platform`
- `backend/app/ai/director/edit_plan_schema.py`: `clip_production_debug: dict` + `to_dict()` entry
- `backend/app/ai/director/ai_director.py`:
  - Debug aggregator try-import + execution block after S3.4
  - RC5: Rate-limited unknown platform warning in S3.4 block (max 1 `platform_unknown:X` per render)
  - Imports `_KNOWN_PLATFORMS` from `platform_adapter` for RC5 gate
- `docs/product/S3_STABILIZATION_REPORT.md` (new): RC4 platform differentiation benchmark, RC3 dominance analysis, QA matrix, failure mode table, threshold inventory

**Regression guarantees:**
- `S3_DEBUG_ENABLED=0` (default) → `{}` → `clip_production_debug={}` → no debug in production API
- All S3 modules still individually rollback-able via `S3_*_ENABLED=0`
- No changes to clip count, scoring, selection, diversity, DNA, render pipeline, or external APIs
- Dead-risk removal (`low_face_presence`) has zero behavior impact (risk was structurally dead)

---

## Creator Benchmark Sprint ✅ Complete

**Shipped:** `feat(ai): Creator Benchmark Calibration Sprint` — commit `69f32ac`

**What shipped:**
- 20-scenario benchmark matrix, 10 QA dimensions each (see `docs/product/CREATOR_BENCHMARK_REPORT.md`)
- Phase A: 5 env-var calibrations (no code changes)
- Phase B code calibrations:
  - B1: Goal-aware hook absence penalty (viral=20, storytelling=16, education=14, podcast=12)
  - B2: Externalized `_DETECT_THRESHOLD` to `S3_STRUCTURE_DETECT_THRESHOLD` env var
  - B3: Goal-aware dead zone threshold (viral=0.18, storytelling=0.22, education=0.24, podcast=0.28, hard cap ≤0.30)
- Benchmark results: BASELINE 7.09/10 → AFTER 7.13/10 (incremental improvement; QA needed for launch)
- Launch readiness: "Creator QA Needed (7.0–8.0)"

**Calibration only. No new features. No S3.5. No S4. No render changes.**

---

## Creator QA Mini Sprint ✅ Complete

**Shipped:** `feat(ai): Creator QA Mini Sprint — KEEP 0.50 threshold decision` — commit `6d834c4`

**What shipped:**
- Validated `S3_STRUCTURE_DETECT_THRESHOLD=0.42` against 5 weakest benchmark scenarios
- False positive mathematically confirmed: marker at ratio=0 + nat_start → c=0.450, detected at 0.42, not at 0.50
- All tested podcast scenarios (#10, #11) already exceed 0.50 (confidence 0.53–0.72) — lowering threshold gives zero benefit
- Weak scenarios (#8, #15, #20) fail due to missing opener markers, not strict threshold — threshold tuning cannot fix structural absence
- **Decision: KEEP 0.50** for all goals
- Goal-aware threshold infrastructure added to `structure_analyzer.py` (`_GOAL_DETECT_THRESHOLDS={}`, `_get_detect_threshold()`); empty dict → no behavior change
- Deliverable: `docs/product/CREATOR_QA_MINI_REPORT.md`

**Threshold decision is final. Calibration state locked in Post-QA Freeze Sprint.**

---

## Post-QA Freeze Sprint ✅ Complete

**Shipped:** `feat(ai): Post-QA Freeze Sprint — calibration locked, soft beta ready` — commit `8153f44`

**What shipped:**
- `CALIBRATION_FROZEN=true` — no further threshold tuning without new benchmark data
- Locked production defaults: `S3_RETENTION_BASE_SCORE=68`, `S3_RETENTION_DEAD_ZONE_THRESHOLD=0.26`, `S3_RETENTION_PROMISE_PENALTY=16`, `S3_RETENTION_MIN_SCORE=45`, `S3_PLATFORM_CONFIDENCE_MIN=0.12`, `S3_STRUCTURE_DETECT_THRESHOLD=0.50`
- Rejected assumption permanently documented: threshold 0.42 rejected; false-positive proof in `CREATOR_QA_MINI_REPORT.md §10`
- `docs/product/SOFT_BETA_READINESS.md` (new): frozen defaults, rejected assumptions, launch checklist, known limitations, monitoring signals, exit criteria
- `docs/product/CREATOR_QA_MINI_REPORT.md`: Section 10 added (freeze note, locked defaults, rejected assumption record)

---

## Soft Beta Launch Preparation ✅ Complete

**Shipped:** `feat(ai): Soft Beta Launch Preparation — RC1–RC4 observability` — commit `d8aee34`

**What shipped:**
- RC1: `s3_health_summary` — per-module `clips_attempted / clips_processed` in every API response
- RC2: Warning severity tiers — `CRITICAL:` (module crash), `WARN:` (partial failure), `INFO:` (platform unknown)
- RC3: Measurable stage gates documented in `docs/product/SOFT_BETA_OPERATIONS.md`
- RC4: S3.5 hard floor — 100 clip-level feedback events before any learning hypothesis
- Deliverable: `docs/product/SOFT_BETA_OPERATIONS.md`

---

## Soft Beta Stage 1 🚧 In Progress

**Goal:** Internal smoke test. Validate S3 runs safely in production-like conditions.

**Scope:**
- 5 synthetic renders: podcast, education, viral (strong), viral (weak hook), bad audio
- `S3_DEBUG_ENABLED=1`, all other settings production defaults
- Pass gates: 0 CRITICAL, ≤5% WARN, health populated, 0 rollbacks, 0 regressions
- Deliverable: `docs/product/SOFT_BETA_STAGE1_REPORT.md`

**No new features. No S3.5. No calibration changes. No render changes.**

---

## Non-Negotiable Constraints (all S3 phases)

- Creator controls: goal, style, format, clip count, duration preference
- AI is additive, never subtractive to creator decisions
- Every new feature has a `*_ENABLED=0` env gate for full rollback
- Transcript absence must degrade gracefully (never failure)
- No external API changes
- No render pipeline failures
- No clip count changes
