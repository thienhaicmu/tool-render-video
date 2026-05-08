# Render System — Full Architecture Audit

> **Living document.** Original audit generated 2026-05-07. Patch notes appended below.
> All findings are grounded in actual file content with exact line references.

---

## Patch Status Log
### 2026-05-08 — AI Productization Phase 27: Safe AI-Assisted Render Mutations

**First phase where bounded AI mutations are applied to AI guidance metadata fields.**

**Implemented:**

- `app/ai/mutations/__init__.py` (new) — package marker; Phase 27 safe mutation package
- `app/ai/mutations/mutation_schema.py` (new) — `VALID_MUTATION_CATEGORIES` frozenset ({subtitle, pacing, camera, creator_style, visual_rhythm}); `AISafeMutation` dataclass (mutation_id, category, confidence, applied, safe, source_recommendation_id, changes, warnings, explanation; `to_dict()` clamps confidence [0,1], caps explanation at 5, coerces invalid category to ""); `AISafeMutationPack` dataclass (available, advisory_mode, mutations, applied_mutation_ids, blocked_mutations, warnings; `to_dict()` caps mutations at 10, caps applied/blocked lists at 20)
- `app/ai/mutations/mutation_safety.py` (new) — `sanitize_mutation_changes(changes) -> dict`; strips forbidden keys and unknown keys, retains only `_ALLOWED_KEYS`, drops None values; `is_mutation_safe(changes) -> bool`; returns False if any forbidden key detected; `apply_safe_mutation(payload, changes) -> dict`; creates a shallow copy of payload (dict or object with `__dict__`), applies only allowed keys, never mutates original; `_ALLOWED_KEYS = {subtitle_density, subtitle_emphasis, camera_behavior, pacing_style, creator_style, visual_rhythm_mode, ai_mode}`; `_FORBIDDEN_KEYS = {playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, bitrate, crf, validation_rules, output_path, render_command, render_segments, segment_order}`; never raises; original payload never mutated in-place
- `app/ai/mutations/mutation_engine.py` (new) — `build_safe_mutations(edit_plan, payload=None, context=None) -> AISafeMutationPack`; reads `execution_recommendations.recommendations` (Phase 25 output); per-category builders: `_build_baseline_mutation()` (always applied), `_build_retention_mutation()` (gate: safe_to_apply + confidence ≥ 0.50), `_build_creator_style_mutation()` (gate: confidence ≥ 0.50; maps to safe camera values via `_STYLE_TO_CAMERA_SAFE`), `_build_subtitle_mutation()` (gate: confidence ≥ 0.40), `_build_visual_rhythm_mutation()` (gate: confidence ≥ 0.35; energetic/moderate → beat_light, calm → beat_none), `_build_pacing_mutation()` (gate: confidence ≥ 0.50); unsafe/low-confidence mutations → `changes={}`, `applied=False`, added to `blocked_mutations`; `advisory_mode=True` when zero mutations applied; emits `ai_safe_mutation_applied`/`ai_safe_mutation_blocked` at INFO, `ai_safe_mutation_skipped` on fallback; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `safe_render_mutations: dict = field(default_factory=dict)` added to `AIEditPlan`; `"safe_render_mutations": dict(self.safe_render_mutations)` in `to_dict()`; backward-compatible; Phase 26 `execution_simulation` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_safe_render_mutations(plan, job_id)` added; runs after Phase 26 (execution simulation); calls `build_safe_mutations(plan, payload=None, context)`; `_append_safe_render_mutations_explainability(plan, pack_dict)` appends: "Safe subtitle density mutation applied" (subtitle), "Visual rhythm guidance safely adjusted" (visual_rhythm), "Creator style mutation applied safely" (creator_style), "Safe pacing mutation applied" (pacing), "Dangerous timing mutations remain blocked" (always); None guard on plan; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_safe_mutations(payload, edit_plan, report)` added; applied mutations → `report["applied"]` as `"safe_mutation:applied({id},{cat}:[changes])"` — FIRST AI-managed mutations to reach the applied list; blocked mutations → `report["skipped"]` as `"safe_mutation:blocked({id},{cat})"` ; emits `ai_safe_mutation_applied`/`ai_safe_mutation_blocked` at INFO; no payload mutation; wired into `apply_ai_render_influence()` after `_report_execution_simulation()`
- `tests/test_ai_phase27_safe_render_mutations.py` (new) — comprehensive test suite covering mutation schema, safety gates, apply_safe_mutation payload invariants, mutation engine, AIEditPlan field, render_influence reporter, safety invariants, and AI Director integration

**Allowed mutation keys and gates:**

| Category | Allowed keys | Confidence gate |
|----------|-------------|-----------------|
| `safe_baseline` | `ai_mode`, `pacing_style` | always applied (conf=1.0) |
| `pacing` | `pacing_style` | ≥ 0.50 + safe_to_apply |
| `creator_style` | `creator_style`, `camera_behavior` | ≥ 0.50 + safe_to_apply |
| `subtitle` | `subtitle_density`, `subtitle_emphasis` | ≥ 0.40 + safe_to_apply |
| `visual_rhythm` | `visual_rhythm_mode` | ≥ 0.35 + safe_to_apply |

**Pacing style canonicalisation:** fast_cuts→fast_hook, fast→fast_hook, retention_optimized→retention_focus, story_driven→story_driven, standard→standard, slow_build→slow_build, medium→standard, slow→slow_build

**Camera behaviour safety mapping:** viral_tiktok/cinematic/storytelling/commentary→dynamic_safe; educational/podcast/product_demo/interview/safe_generic→static

**Visual rhythm safety mapping:** energetic→beat_light, moderate→beat_light, calm→beat_none

**Safety boundaries enforced:**

- Original payload NEVER mutated — `apply_safe_mutation()` always creates a copy
- `_FORBIDDEN_KEYS` (13 keys incl. playback_speed, ffmpeg_args, segment_order, render_segments) always stripped by `sanitize_mutation_changes()`
- Unsafe mutations have `changes={}` and `applied=False` — empty changes reach the report as blocked
- `is_mutation_safe()` returns False if any forbidden key detected in changes
- `advisory_mode=True` set on pack when zero mutations are applied
- Applied mutations only affect AI guidance metadata fields — never FFmpeg commands, timings, or render payload execution fields
- Applied mutations appear in `report["applied"]` — but only as AI metadata, no payload object mutation occurs in `_report_safe_mutations`
- No FFmpeg commands altered. No subtitle timing rewrite. No segment reorder. No playback_speed mutation.
- Never blocks render — all Phase 27 code wrapped in try/except in AI Director and engine
- Deterministic — same edit_plan always produces same mutation pack
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- FFmpeg command mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Render structure mutation
- Render queue mutation
- Autonomous rendering
- Executor override
- Output validation mutation

**Architecture notes:**

- Phase 27 is the FIRST phase where mutations appear in `report["applied"]` (all prior phases added to `report["skipped"]`)
- Mutations are proposed and validated at AI Director time (when edit_plan is built); no payload is needed because changes target AI guidance metadata fields only
- `apply_safe_mutation(payload, changes) -> dict` is available for downstream use when a payload dict copy is needed; it is not called in the main reporting path to preserve the "no payload mutation" invariant in render_influence

**Verification:**

- Phase 27 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 26: Execution Simulation Layer Foundation

**Implemented:**

- `app/ai/simulation/__init__.py` (new) — package marker; Phase 26 simulation package
- `app/ai/simulation/simulation_schema.py` (new) — `VALID_SAFETY_LEVELS` frozenset ({safe, caution, blocked}); `AIExecutionSimulation` dataclass (simulation_id, recommendation_id, label, estimated_retention_gain, estimated_story_gain, estimated_subtitle_clarity_gain, estimated_pacing_gain, confidence, safety_level, advisory_only always True, warnings, explanation; `to_dict()` hardcodes advisory_only=True, clamps confidence [0,1], clamps all gains [-100,100], caps explanation at 5, coerces invalid safety_level to "safe"); `AISimulationPack` dataclass (available, mode always "simulation_only", simulations, recommended_simulation_id, warnings; `to_dict()` hardcodes mode="simulation_only", caps simulations at 10)
- `app/ai/simulation/simulation_scoring.py` (new) — `score_simulation(simulation, edit_plan=None) -> dict`; weighted gain blend (retention×0.35 + story×0.25 + subtitle×0.20 + pacing×0.20) centered at 50; safety penalties: caution −15, blocked −50; low-confidence (<0.40) dampening toward 50; returns {"overall_score":0-100, "confidence":0-1, "reasons":[], "warnings":[]}; deterministic; never raises
- `app/ai/simulation/execution_simulator.py` (new) — `simulate_execution_recommendations(edit_plan, context) -> AISimulationPack`; primary path reads `execution_recommendations.recommendations` (Phase 25 output) and simulates each by category (retention, creator_style, subtitle, visual_rhythm, pacing, safe_baseline); supplemental direct-metadata path fills gaps: `_simulate_retention()` (gain: 18/10/4 for score <40/<70/≥70), `_simulate_subtitle()` (gain: 12/6/3 for compact/normal/other + 3 bonus for emphasis), `_simulate_visual_rhythm()` (pacing: 10/7/5 for >120/>80/≤80 bpm), `_simulate_story_pacing()` (story_driven/fast_cuts/standard), `_simulate_creator_style()` (retention=confidence×8, pacing=confidence×10); `_select_recommended()`: scores via `score_simulation()`, picks best non-baseline only if it beats baseline by >2 pts; `sim_safe_baseline` always present; emits `ai_execution_simulation_created` at INFO, `ai_execution_simulation_fallback` on error; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `execution_simulation: dict = field(default_factory=dict)` added to `AIEditPlan`; `"execution_simulation": dict(self.execution_simulation)` in `to_dict()`; backward-compatible; Phase 25 `execution_recommendations` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_execution_simulation(plan, job_id)` added; runs after Phase 25 (execution recommendations) so simulation reads full recommendation context; calls `simulate_execution_recommendations(plan, context)`; `_append_execution_simulation_explainability(plan, pack_dict)` appends: "Execution simulation estimated retention improvement (+X.Y)" or "Execution simulation prepared (advisory metadata only)", "Subtitle clarity simulation available" (when present), "Simulation remains advisory-only"; None guard on plan; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_execution_simulation(payload, edit_plan, report)` added; checks `edit_plan.execution_simulation`, adds `"execution_simulation:deferred_phase26(count=...,recommended=...)"` to report["skipped"]; no payload mutation; wired into `apply_ai_render_influence()` after `_report_execution_recommendations()`
- `tests/test_ai_phase26_execution_simulation.py` (new) — comprehensive test suite covering simulation schema, scoring, simulator builder, AIEditPlan field, render_influence reporter, safety invariants, and AI Director integration

**Simulation gain model:**

| Simulation | Retention | Story | Subtitle | Pacing | Source |
|------------|-----------|-------|----------|--------|--------|
| retention_pacing (fast_cuts) | +18 (low) / +10 (mid) | — | — | +8 | retention.score |
| creator_style | confidence×8 | — | — | confidence×10 | creator_style_adaptation |
| compact_subtitle | — | — | +12/+6/+3 | — | subtitle_execution.density |
| visual_rhythm (energetic) | +6 | — | — | +10 | beat_visual_execution.bpm |
| story_pacing (story_driven) | — | (100-score)×0.15 | — | +8 | story_optimization |
| safe_baseline | 0 | 0 | 0 | 0 | always present |

**Scoring formula:** `overall = clamp(50 + Σ(gain×weight) − safety_penalty − low_conf_dampening, 0, 100)`

**Safety penalties:** safe: −0, caution: −15, blocked: −50

**Recommendation selection:** best non-baseline simulation selected only when `score > baseline_score + 2.0`; otherwise `sim_safe_baseline` is recommended

**Safety boundaries enforced:**

- `advisory_only` always True — hardcoded in `AIExecutionSimulation.to_dict()`
- `mode` always "simulation_only" — hardcoded in `AISimulationPack.to_dict()`
- Simulations contain no `recommended_settings` — no forbidden key exposure
- Blocked simulations penalized −50 pts in scoring (prefer safe/caution)
- safe_baseline always available as stable neutral reference
- No FFmpeg commands altered
- No payload mutation — simulator reads edit_plan, never writes render payload
- No subtitle timing rewrite, no segment reorder, no playback_speed mutation
- No autonomous execution of any simulation result
- Never blocks render — all Phase 26 code wrapped in try/except in AI Director and simulator
- Deterministic — same edit_plan always produces same simulation pack
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Actual execution apply
- Autonomous rendering
- FFmpeg mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Payload mutation
- Executor override
- Output duplication

**Architecture notes:**

- Phase 26 runs after Phase 25 (execution recommendations) so simulations can reference recommendation-backed metadata for higher fidelity estimates
- Supplemental direct-metadata simulators fire for any gain category not already covered by a recommendation-backed simulation (no duplicates)
- `score_simulation()` is pure — same simulation object always returns same score regardless of edit_plan context

**Verification:**

- Phase 26 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 25: Safe Execution Recommendation Layer

**Implemented:**

- `app/ai/execution/__init__.py` (new) — package marker; Phase 25 execution package
- `app/ai/execution/execution_schema.py` (new) — `VALID_CATEGORIES` frozenset ({subtitle, pacing, camera, creator_style, retention, visual_rhythm, safe_baseline}); `AIExecutionRecommendation` dataclass (recommendation_id, label, category, confidence, safe_to_apply, advisory_only always True, recommended_settings, blocked_settings, warnings, explanation; `to_dict()` hardcodes advisory_only=True, clamps confidence [0,1], caps explanation at 5, coerces invalid category to "safe_baseline"); `AIExecutionPack` dataclass (available, mode always "advisory", recommendations, recommended_pack_id, warnings; `to_dict()` hardcodes mode="advisory", caps recommendations at 10)
- `app/ai/execution/execution_safety.py` (new) — `sanitize_execution_settings(settings) -> dict`; strips all forbidden keys, retains only `_ALLOWED_KEYS`; `is_execution_recommendation_safe(recommendation, context) -> bool`; checks recommended_settings for forbidden keys; `_ALLOWED_KEYS = {subtitle_density, subtitle_emphasis, camera_behavior, pacing_style, creator_style, visual_rhythm_mode, hook_density, target_duration_hint, ai_mode}`; `_FORBIDDEN_KEYS = {playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, bitrate, crf, validation_rules, output_path, render_command}`; never raises; no payload mutation
- `app/ai/execution/execution_recommendation.py` (new) — `build_execution_recommendations(edit_plan, context) -> AIExecutionPack`; reads: creator_style_adaptation, retention, subtitle_execution, beat_visual_execution, story_optimization; safe_baseline always built first; `_build_creator_style_recommendation()`: maps Phase 23 style_id to camera_behavior + pacing_style; safe_to_apply=True only when confidence ≥ 0.50; `_build_retention_recommendation()`: fast_cuts/high-hook for score<40, retention_optimized/medium for score<70, standard/low otherwise; `_build_visual_rhythm_recommendation()`: energetic(>120bpm)/moderate(>80bpm)/calm; `_build_story_pacing_recommendation()`: story_driven for three_act/hero_journey, fast_cuts for montage/highlight; `_select_recommended()`: max by confidence×100 + category bonus (retention+15, creator_style+10, pacing+8, subtitle+6, visual_rhythm+4) minus 20 if not safe_to_apply; all settings sanitized via `sanitize_execution_settings()` before attachment; emits `ai_execution_recommendations_created` at INFO, `ai_execution_recommendation_fallback` on error; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `execution_recommendations: dict = field(default_factory=dict)` added to `AIEditPlan`; `"execution_recommendations": dict(self.execution_recommendations)` in `to_dict()`; backward-compatible; Phase 24 `render_decision_preview` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_execution_recommendations(plan, job_id)` added; runs after Phase 24 (render decision preview); calls `build_execution_recommendations(plan, context)`; `_append_execution_recommendations_explainability(plan, pack_dict)` appends: "AI execution recommendation pack prepared", "Retention-oriented pacing recommendation available" / "Creator-style execution recommendation available" / "Story-driven pacing recommendation available", "Autonomous execution remains blocked"; None guard on plan; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_execution_recommendations(payload, edit_plan, report)` added; checks `edit_plan.execution_recommendations`, adds `"execution_recommendations:deferred_phase25(count=...,recommended=...)"` to report["skipped"]; no payload mutation; wired into `apply_ai_render_influence()` after `_report_render_decision_preview()`
- `tests/test_ai_phase25_execution_recommendation.py` (new) — comprehensive test suite covering execution schema, safety gates, recommendation builder, AIEditPlan field, render_influence reporter, safety invariants, and AI Director integration

**Recommendation categories and scoring:**

| Category | Bonus | Source |
|----------|-------|--------|
| `retention` | +15 | retention.overall_retention_score |
| `creator_style` | +10 | creator_style_adaptation.primary_style |
| `pacing` | +8 | story_optimization.flow_type |
| `subtitle` | +6 | subtitle_execution.density |
| `visual_rhythm` | +4 | beat_visual_execution.bpm |
| `safe_baseline` | 0 | always present |

**Retention pacing thresholds:**

| Score range | Pacing style | Hook density |
|-------------|-------------|--------------|
| < 40 | fast_cuts | high |
| 40–69 | retention_optimized | medium |
| ≥ 70 | standard | low |

**Safety boundaries enforced:**

- `advisory_only` always True — hardcoded in `AIExecutionRecommendation.to_dict()`
- `mode` always "advisory" — hardcoded in `AIExecutionPack.to_dict()`
- `_FORBIDDEN_KEYS` (playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, bitrate, crf, validation_rules, output_path, render_command) always stripped by `sanitize_execution_settings()`
- `is_execution_recommendation_safe()` returns False if any forbidden key detected
- safe_baseline always available as stable fallback
- No FFmpeg commands altered
- No payload mutation — builder reads edit_plan, never writes render payload
- No subtitle timing rewrite
- No segment reorder
- No playback_speed mutation
- No autonomous execution of any recommendation
- Never blocks render — all Phase 25 code wrapped in try/except in AI Director and builder
- Deterministic — same edit_plan always produces same recommendations
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Autonomous execution of recommendations
- Direct render mutation
- FFmpeg filter chain mutation
- Playback_speed mutation
- Subtitle timing rewrite
- Segment reorder
- Payload mutation
- Automatic execution apply
- Render executor override

**Architecture notes:**

- Phase 25 runs after Phase 24 (render decision preview) so all prior AI phase outputs are available
- safe_baseline recommendation always scored at confidence=1.0 but with 0 category bonus, so a high-confidence retention/style recommendation will be selected as recommended_pack_id instead
- `_ALLOWED_KEYS` whitelist is the authoritative list of settings the recommendation layer can suggest
- Creator style → camera behavior mapping mirrors Phase 23 adaptation hints for consistency

**Verification:**

- Phase 25 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 24: AI Render Decision Preview Foundation

**Implemented:**

- `app/ai/preview/__init__.py` (new) — package marker; Phase 24 preview package
- `app/ai/preview/preview_schema.py` (new) — `VALID_SAFETY_STATUSES` frozenset ({safe, caution, blocked, unavailable}); `AIRenderDecisionPreview` dataclass (available, mode, selected_variant_id, creator_style, decision_summary, recommended_actions, blocked_actions, safety_status, confidence, warnings, explanation; `to_dict()` hardcodes mode="advisory", clamps confidence [0,1], caps recommended_actions at 10, explanation at 8, coerces invalid safety_status to "safe"); `AIPreviewSafetyReport` dataclass (safe_to_preview, safe_to_execute always False, blocked_reasons, advisory_only always True, warnings; `to_dict()` hardcodes safe_to_execute=False and advisory_only=True)
- `app/ai/preview/decision_preview.py` (new) — `build_render_decision_preview(edit_plan, context) -> dict`; aggregates variant_selection, creator_style_adaptation, retention, story_optimization, subtitle_execution, timing_mutation metadata into a single advisory summary; `_BLOCKED_ACTIONS = [autonomous_rendering_of_selected_variant, ffmpeg_filter_chain_mutation, timing_mutation_application, subtitle_timing_rewrite, playback_speed_mutation, segment_reorder]` always included; `_determine_safety_status()`: unavailable when no variant metadata, caution when ret_score<40 or variant_confidence<0.30, safe otherwise; `_compute_overall_confidence()`: weighted blend of variant_confidence, style_confidence, ret_score/100, narrative_score/100; result always includes `safety_report` sub-dict; emits `ai_render_decision_preview_created` at INFO, `ai_render_decision_preview_fallback` on error; deterministic; never raises
- `app/ai/director/edit_plan_schema.py` (updated) — `render_decision_preview: dict = field(default_factory=dict)` added to `AIEditPlan`; `"render_decision_preview": dict(self.render_decision_preview)` in `to_dict()`; backward-compatible
- `app/ai/director/ai_director.py` (updated) — `_attach_render_decision_preview(plan, job_id)` added; runs after Phase 22 (variant selection) to aggregate all prior phase outputs; calls `build_render_decision_preview(plan, context)`; `_append_render_decision_preview_explainability(plan, preview_dict)` appends: "AI render decision preview prepared", "Selected advisory variant summarized", "Autonomous render actions remain blocked"; wrapped in try/except; never blocks render
- `app/ai/director/render_influence.py` (updated) — `_report_render_decision_preview(payload, edit_plan, report)` added; checks `edit_plan.render_decision_preview`, adds `"render_decision_preview:deferred_phase24(status=...,confidence=...,selected_variant=...)"` to report["skipped"]; no payload mutation; wired into `apply_ai_render_influence()` after `_report_variant_selection()`
- `tests/test_ai_phase24_render_decision_preview.py` (new) — comprehensive test suite covering preview schema, decision_preview builder, blocked actions constant, AIEditPlan field, render_influence reporter, safety invariants, and AI Director integration

**Safety boundaries enforced:**

- `safe_to_execute` always False — hardcoded in both `AIPreviewSafetyReport.to_dict()` and the constant
- `advisory_only` always True — hardcoded in `AIPreviewSafetyReport.to_dict()`
- `mode` always "advisory" — hardcoded in `AIRenderDecisionPreview.to_dict()`
- `_BLOCKED_ACTIONS` always present in every preview result regardless of metadata
- `phase24_advisory_only_mode` always in `safety_report.blocked_reasons`
- No FFmpeg commands altered
- No payload mutation — preview reads all prior phase metadata, never writes render payload
- No subtitle timing rewrite
- No segment reorder
- No playback_speed mutation
- No autonomous rendering of any variant
- Never blocks render — all Phase 24 code wrapped in try/except in AI Director and decision_preview
- Deterministic — same edit_plan always produces same preview
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Autonomous rendering based on selected variant
- FFmpeg filter chain mutation
- Timing mutation application
- Subtitle timing rewrite
- Playback_speed mutation
- Segment reorder
- Any payload mutation

**Architecture notes:**

- Phase 24 runs after Phase 22 (variant selection) so it can aggregate all prior AI phase outputs into a unified advisory summary
- Reads from: variants, variant_selection, creator_style_adaptation, retention, story_optimization, subtitle_execution, timing_mutation, explainability
- Advisory mode is a permanent constraint in Phase 24 — not a configurable parameter
- `_BLOCKED_ACTIONS` is a module-level constant to prevent accidental omission

**Verification:**

- Phase 24 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

---

### 2026-05-08 — AI Productization Phase 23: Creator Style Adaptation Foundation

**Implemented:**

- `app/ai/styles/style_schema.py` (updated, Phase 23 additions) — `DetectedStyleProfile` dataclass added (style_id, label, confidence, pacing_style, subtitle_style, camera_style, energy_level, hook_density, explanation, warnings; `to_dict()` coerces invalid style_id to `safe_generic`); `CreatorStyleSet` dataclass added (detected, primary_style, styles, fallback_used, warnings; `to_dict()` caps styles at 5); `VALID_P23_STYLES` frozenset added ({viral_tiktok, cinematic, educational, podcast, product_demo, storytelling, commentary, interview, safe_generic}); Phase 14 classes unchanged (backward compatible)
- `app/ai/styles/style_classifier.py` (updated, Phase 23 additions) — `detect_creator_styles(edit_plan, context) -> CreatorStyleSet` added; reads Phase 14 `creator_style.dominant_style` and maps to Phase 23 ID via `_P14_TO_P23` dict; derives secondary style candidates from pacing/retention/story metadata; `safe_generic` fallback when p14 dominant=unknown or confidence<20; emits `ai_creator_style_detected` at INFO, `ai_creator_style_fallback` when fallback; deterministic; never raises; Phase 14 `classify_creator_style()` unchanged
- `app/ai/styles/style_adapter.py` (new) — `build_style_adaptation(style_profile, edit_plan, context) -> dict`; maps Phase 23 style_id to advisory hint dict ({subtitle_density, subtitle_style, pacing_hint, camera_hint, hook_density_hint, visual_rhythm_hint, preset_hint}); safety gate strips any key not in `_SAFE_HINT_KEYS` and any key in `_FORBIDDEN_HINT_KEYS`; context-aware adjustments: low retention score raises hook_density from low→medium; compact subtitle execution lowers subtitle_density from high→medium; emits `ai_creator_style_adaptation_applied` at INFO; deterministic; never raises; never mutates payload
- `app/ai/styles/style_scoring.py` (new) — `score_style_fit(style_profile, variant, edit_plan) -> dict`; returns {style_fit_score 0-100, confidence 0-1, reasons, warnings}; per-style × per-purpose fit score table (`_STYLE_PURPOSE_FIT`); low confidence (<0.30) dampens score toward neutral 60; safe_generic always returns stable 58-65 range; deterministic; never raises; no ML models; no external APIs
- `app/ai/variants/variant_selector.py` (updated, Phase 23 additions) — `_compute_style_bonuses(scored, edit_plan) -> dict` added; reads `edit_plan.creator_style_adaptation` (detected + confidence ≥ 0.20); calls `score_style_fit()` for each variant; applies bonus = (fit_score − 60) / 100 × 16 (range −8 to +8) to sort key only; original score dict unchanged (confidence math unaffected); `_sort_key` updated to include bonus; never raises; all prior Phase 22 logic preserved
- `app/ai/director/edit_plan_schema.py` (updated) — `creator_style_adaptation: dict = field(default_factory=dict)` added to `AIEditPlan`; `"creator_style_adaptation": dict(self.creator_style_adaptation)` in `to_dict()`; backward-compatible; Phase 14 `creator_style` field unchanged
- `app/ai/director/ai_director.py` (updated) — `_attach_creator_style_adaptation(plan, job_id)` added; runs between Phase 20 and Phase 21 so style adaptation is available when variant selector executes; calls `detect_creator_styles(plan)` + `build_style_adaptation(primary_profile, plan)`; stores compact {detected, primary_style, confidence, adaptation, fallback_used, warnings}; `_append_creator_style_adaptation_explainability(plan, style_set, adaptation_result)` appends: "Creator style classified as viral TikTok", "Fast pacing adaptation suggested", "Creator style: safe generic fallback used", etc.; wrapped in try/except; never blocks render; Phase 14 `_attach_creator_style()` call preserved
- `tests/test_ai_phase23_creator_style.py` (new) — comprehensive test suite covering style schema, detect_creator_styles, build_style_adaptation, score_style_fit, AIEditPlan field, AI Director integration, variant selector style-fit bonus, and all safety boundaries

**Supported Phase 23 style IDs:**

| ID | Label | Pacing | Subtitle | Camera | Hook Density |
|----|-------|--------|----------|--------|--------------|
| `viral_tiktok` | Viral TikTok | fast | punch | fast_follow | high |
| `cinematic` | Cinematic | slow_build | minimal | slow_reveal | low |
| `educational` | Educational | medium | bold | static | medium |
| `podcast` | Podcast | medium | clean | static | low |
| `product_demo` | Product Demo | medium | overlay | static | medium |
| `storytelling` | Storytelling | slow_build | minimal | pan | medium |
| `commentary` | Commentary | fast | bold | reaction | high |
| `interview` | Interview | slow | clean | static | low |
| `safe_generic` | Generic | default | default | auto | medium |

**Phase 14 → Phase 23 mapping:**

| Phase 14 | Phase 23 |
|----------|----------|
| podcast_viral | viral_tiktok |
| high_energy_reaction | commentary |
| storytelling_cinematic | cinematic |
| documentary_clean | podcast |
| educational_focus | educational |
| anime_edit | viral_tiktok |
| gameplay_highlight | commentary |
| motivation_short | viral_tiktok |
| interview_clip | interview |
| calm_minimal | safe_generic |

**Verification:**

- Phase 23 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- Adaptation output contains only advisory hint keys (subtitle_density, pacing_hint, camera_hint, etc.)
- `_FORBIDDEN_HINT_KEYS` (playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, crf, bitrate, output_path, validation_rules) always stripped
- No FFmpeg commands altered
- No payload mutation — style detection and adaptation read edit_plan, never write render payload
- No subtitle timing rewrite
- No segment reorder
- No playback_speed mutation
- Style-fit bonus applied to sort key only — base scores unchanged, confidence gate unaffected
- Never blocks render — all Phase 23 code wrapped in try/except in AI Director
- Deterministic — same edit_plan always produces same style detection result
- No internet, no API keys, no GPU required

**Intentionally still blocked:**

- Autonomous rendering based on detected style
- Creator-style auto-editing (FFmpeg filter chains)
- playback_speed mutation
- subtitle timing rewrite
- segment reorder
- payload mutation
- automatic export selection

**Architecture notes:**

- Phase 23 runs after Phase 20 (story optimization) and before Phase 21 (variant planning) so the style adaptation is available when the variant selector executes in Phase 22
- Phase 14 `creator_style` dict (dominant_style, confidence, etc.) preserved untouched; Phase 23 adds `creator_style_adaptation` as a separate field
- Style-fit bonus in variant selector: max ±8 pts on sort key — cannot override safety gates or high-risk penalties
- `safe_generic` always available as stable fallback with neutral score range (58-65)

**Integrated systems:**

- Creator Style Classification (Phase 14) — dominant_style mapped to Phase 23 ID
- Retention Intelligence (Phase 16) — low retention score raises hook_density hint
- Story Optimization (Phase 20) — narrative flow feeds secondary style signal
- Variant Selector (Phase 22) — style-fit bonus applied per variant
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 22: AI Best Variant Selector Foundation

**Implemented:**

- `app/ai/variants/variant_selector.py` (new) — `select_best_variant(variant_set, edit_plan, context) -> dict`; returns {selected_variant_id, selection_confidence, selection_reasons, rejected_variants, fallback_used}; accepts `AIVariantSet`, serialised dict, or any object with `variants` attribute; scores all candidates via `score_variant()`; sort key: (−score, purpose_priority, risk_priority); skips `risk="high"` variants when any safe option exists; confidence gate: if selection_confidence < 0.50 and non-baseline selected, falls back to `safe_baseline`; emits `ai_variant_selected` at INFO, `ai_variant_selector_fallback` on fallback, `ai_variant_selection_skipped` when no variants; deterministic; never raises; never renders; never mutates payload
- `app/ai/variants/variant_scoring.py` (updated, Phase 22 additions) — `_RISK_PENALTIES["high"]` raised 30→40 for stronger selection pressure; `_BASELINE_FLOOR = 58.0` guarantees `safe_baseline` always scores ≥ 58; `normalized_score` field added to return dict (score / 100.0); `expected_gain` baseline shifted to `_BASELINE_FLOOR`; backward-compatible (all Phase 21 callers still receive `score`, `expected_gain`, `reasons`, `warnings`)
- `app/ai/director/edit_plan_schema.py` — `variant_selection: dict = field(default_factory=dict)` added to `AIEditPlan`; `"variant_selection": dict(self.variant_selection)` in `to_dict()`; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_variant_selection(plan, job_id)` added; runs only when `ai_variant_planning_enabled=True` AND `plan.variants.get("available")`; stores compact {selected_variant_id, selection_confidence, selection_reasons, fallback_used, rejected_count}; `_append_variant_selection_explainability(plan, selection)` appends: "AI selected retention-focused variant", "Safe baseline retained due to low confidence", "Creator-style variant scored highest", etc.; all wrapped in try/except; never block render; Phase 22 runs after Phase 21 in `_build_plan`
- `app/ai/director/render_influence.py` — `_report_variant_selection(payload, edit_plan, report)` added; reports selection as deferred in Phase 22; compact `report["skipped"]` entry with selected/confidence/fallback/rejected; no variant rendered, no payload mutated, no FFmpeg altered; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase21_variant_rendering.py` — `test_returns_dict_with_expected_keys` updated from strict set equality to `issubset` to accommodate new `normalized_score` field (non-breaking backward compatibility fix)
- `tests/test_ai_phase22_best_variant_selector.py` (new) — 48 tests covering selector core behaviour, confidence fallback, priority heuristics, scoring normalization, AIEditPlan field, AI Director integration, render influence defer, and all safety boundaries

**Verification:**

- Phase 22 tests pass (48 tests)
- Full suite passes (1402 tests, zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- No variant is ever rendered by the selector — metadata only
- `risk="high"` variants skipped from selection whenever any safe option exists
- Confidence gate < 0.50 → always falls back to `safe_baseline`
- `safe_baseline` guaranteed floor score (≥ 58) — selector always has a stable fallback
- No payload mutation — selector reads variant metadata, never writes to render payload
- No segment start/end timing changes
- No playback_speed changes
- No FFmpeg command changes
- No subtitle timing changes
- No automatic rendering of selected variant
- Never blocks render — all Phase 22 code wrapped in try/except in AI Director
- Deterministic — same input always produces same selected_variant_id

**Selection heuristics (priority order):**
1. Highest `score_variant()` score (base + confidence boost + safety gate + context boost − risk penalty)
2. Tiebreak: purpose_priority (retention → hook → story → subtitle → creator_style → pacing → safe_baseline)
3. Tiebreak: risk_priority (low → medium → high)
4. Confidence gate fallback: score < 50 → safe_baseline returned instead

**Intentionally still blocked:**

- Autonomous rendering of selected variant
- Multi-variant execution queue
- Auto-export best variant
- UI auto-selection
- Timing mutation application
- FFmpeg mutation
- Payload mutation

**Architecture notes:**

- Selector operates on Phase 21 `AIVariantSet` or its serialised dict form — no extra analysis
- `_report_variant_selection` in render_influence records plan as "deferred_phase22" — safe pass-through for future execution phase
- Phase 22 runs after Phase 21 in `_build_plan`; if Phase 21 produced no variants, Phase 22 is skipped
- `normalized_score` in scoring is additive — existing callers are unaffected

**Integrated systems:**

- Variant Planning (Phase 21) — AIVariantSet is the selector's input
- Variant Scoring (Phase 21/22) — `score_variant()` drives ranking
- Retention Intelligence (Phase 16) — context boost for low retention score
- Story Optimization (Phase 20) — context boost for weak_hook / low narrative_score
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 21: Safe Autonomous Variant Rendering Foundation

**Implemented:**

- `app/ai/variants/__init__.py` (new) — package marker
- `app/ai/variants/variant_schema.py` (new) — `AIVariantPlan` dataclass (variant_id, label, purpose, confidence, risk, suggested_changes, expected_gain, safe_to_render, warnings); `AIVariantSet` dataclass (available, mode, variants capped at 5, recommended_variant_id, warnings); `VALID_PURPOSES` = {safe_baseline, retention, hook, subtitle, pacing, story, creator_style}; `VALID_RISKS` = {low, medium, high}; `clamp_variant_count(value) -> int` clamps to [1, 5]; no Pydantic, no heavy deps
- `app/ai/variants/variant_safety.py` (new) — `sanitize_variant_changes(changes) -> dict` strips all forbidden keys; `is_variant_safe(variant, context) -> bool`; gates: risk != "high", no forbidden keys in suggested_changes, non-empty variant_id; `ALLOWED_CHANGE_KEYS` = {subtitle_density, subtitle_emphasis, camera_behavior, pacing_style, target_duration_hint, creator_style, ai_mode}; `FORBIDDEN_CHANGE_KEYS` = {playback_speed, segment_start, segment_end, subtitle_timing, ffmpeg_args, codec, crf, bitrate, validation_rules, output_path}; never raises
- `app/ai/variants/variant_scoring.py` (new) — `score_variant(variant, edit_plan, context) -> dict`; returns {score 0-100, expected_gain 0-100, reasons, warnings}; base scores per purpose; risk penalty (high=-30, medium=-8); confidence boost (up to +15); safety gate modifier (+5 safe, -20 unsafe); context boosts from edit_plan retention/story/subtitle metadata; deterministic; never raises
- `app/ai/variants/variant_generator.py` (new) — `generate_variant_plans(edit_plan, context, count=3) -> AIVariantSet`; always includes safe_baseline; factories: retention (low retention score), hook (weak_hook issue), subtitle (subtitle_execution available), pacing (non-fast current pacing), story (low narrative_score), creator_style (dominant_style classified); sanitizes + safety-gates + scores all candidates; recommends highest expected_gain safe variant; mode always "advisory"; max 5 variants; never raises; never enqueues render; never mutates payload or edit_plan; emits `ai_variant_plans_generated` at INFO
- `app/models/schemas.py` — `ai_variant_planning_enabled: bool = False` and `ai_variant_count: int = 3` added after ai_timing_mutation_enabled; backward-compatible defaults
- `app/ai/director/edit_plan_schema.py` — `variants: dict = field(default_factory=dict)` added to `AIEditPlan`; `"variants": dict(self.variants)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_variant_plans(plan, count, job_id)` added; runs only when `ai_variant_planning_enabled=True`; calls `generate_variant_plans(plan, ...)` with clamped count; `_append_variant_explainability(plan, variant_set)` appends: "AI variant planning prepared safe A/B options", "Retention-focused variant suggested", "Compact subtitle variant available", "Hook-strengthening variant prepared"; all helpers wrapped in try/except; never block render; Phase 21 runs after Phase 20 in `_build_plan`
- `app/ai/director/render_influence.py` — `_report_variant_plans(payload, edit_plan, report)` added; reports variant planning as deferred in Phase 21; adds compact entry to `report["skipped"]` with mode/variants/safe/recommended counts; no extra render jobs enqueued, no payload mutated, no FFmpeg commands altered; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase21_variant_rendering.py` (new) — 73 tests covering schema defaults, to_dict(), valid purposes/risks, count clamping, variant safety, forbidden key stripping, scoring, generator invariants, request flags, AIEditPlan field, AI Director integration, render influence defer, and all safety boundaries

**Verification:**

- Phase 21 tests pass (73 tests)
- Full suite passes (1354 tests, zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- `FORBIDDEN_CHANGE_KEYS` always stripped from `suggested_changes` before storage
- `high` risk variants never receive `safe_to_render=True` from safety gate
- `mode` always `"advisory"` — variants are metadata only
- No extra render jobs enqueued — generator is pure metadata computation
- No payload mutation — generator reads edit_plan, never writes to payload
- No segment start/end timing changes
- No playback_speed changes
- No FFmpeg command changes
- No subtitle timing changes
- No segment reordering
- No automatic rendering of any variant
- Never blocks render — all Phase 21 code wrapped in try/except in AI Director
- Deterministic heuristics only — no cloud AI, no API keys, no GPU
- `ai_variant_planning_enabled` defaults to `False` — zero behavior change for existing requests

**Intentionally still blocked:**

- Actual multi-variant rendering
- Variant queue execution
- AI best variant selector with autonomous rendering
- UI variant selection
- Auto-export best variant
- Timing mutation application
- FFmpeg mutation
- Payload mutation

**Architecture notes:**

- Variant generator builds on all prior Phase 11–20 metadata — no new analysis
- Factory priority: baseline → retention → hook → subtitle → pacing → story → creator_style
- All candidates sanitized via `sanitize_variant_changes()` before scoring
- `_report_variant_plans` in render_influence records the plan as "deferred_phase21" — safe pass-through for future phases
- `clamp_variant_count` enforces [1, 5] regardless of request value

**Integrated systems:**

- Retention Intelligence (Phase 16) — low retention_score triggers retention variant
- Story Optimization (Phase 20) — weak_hook issue triggers hook variant; low narrative_score triggers story variant
- Subtitle Execution (Phase 17) — available subtitle_execution triggers subtitle variant
- Creator Style (Phase 14) — dominant_style triggers creator_style variant
- Pacing Intelligence (Phase 4) — non-fast pacing_style triggers pacing variant
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 20: Story-driven Edit Optimization Foundation

**Implemented:**

- `app/ai/story_optimization/__init__.py` (new) — package marker
- `app/ai/story_optimization/story_optimization_schema.py` (new) — `StoryOptimizationIssue` dataclass (start, end, issue_type, severity, reason, suggested_action, confidence, safe_to_auto_apply always False in to_dict(), metadata); `StoryOptimizationPlan` dataclass (available, narrative_score, flow_type, issues capped at 10, recommendations capped at 8, warnings); `VALID_ISSUE_TYPES` = {weak_hook, missing_setup, long_setup, weak_build_up, missing_climax, weak_payoff, abrupt_outro, unclear_arc, retention_risk, unknown}; `VALID_SEVERITIES` = {low, medium, high}; `VALID_FLOW_TYPES` = {hook_to_climax, linear, flat, unknown}; no Pydantic, no heavy deps
- `app/ai/story_optimization/hook_optimizer.py` (new) — `analyze_hook_quality(story_context, retention_context, transcript_chunks) -> list[StoryOptimizationIssue]`; gates: hook segment presence, weak_hook retention risk, retention_risk score > 0.5; severity: high (no hook), medium (retention risk), low (mildly elevated score); no text rewriting; never raises; safe_to_auto_apply always False
- `app/ai/story_optimization/payoff_analyzer.py` (new) — `analyze_payoff_quality(story_context, retention_context) -> list[StoryOptimizationIssue]`; detects missing payoff (high severity), unclear_payoff retention risk, abrupt_ending, pacing_decay in payoff region, elevated payoff retention_risk; never raises; advisory only
- `app/ai/story_optimization/arc_optimizer.py` (new) — `analyze_story_arc(story_context, pacing_context, retention_context) -> dict`; returns {flow_type, narrative_score, issues, warnings}; flow classification: hook_to_climax (hook + climax present), linear (≥3 segments + linear flow), flat (≤1 segment or flat arc), unknown; base score from segment presence weights (hook=20, setup=10, build_up=15, climax=25, payoff=15, outro=5); bonus for full arc (+10-20); energy modifier (±5); retention risk deduction (-2 per risk); 60/40 blend with story retention_score when available; issues: weak_hook (no hook), missing_climax, weak_build_up (hook→climax without build-up), unclear_arc (flat), long_setup (setup > 1.5× climax+build_up duration); no segment reorder; never raises; emits `ai_story_arc_analyzed` at INFO
- `app/ai/story_optimization/story_recommender.py` (new) — `build_story_optimization_plan(story_context, retention_context, pacing_context, transcript_chunks) -> StoryOptimizationPlan`; combines hook + payoff + arc analyses; deduplicates issues by issue_type; issue-driven recommendations from map + flow-type recommendation; max 10 issues, max 8 recommendations; all safe_to_auto_apply=False enforced; never raises; emits `ai_story_optimization_generated` + `ai_story_optimization_issues_detected` at INFO
- `app/ai/director/edit_plan_schema.py` — `story_optimization: dict = field(default_factory=dict)` added to `AIEditPlan`; `"story_optimization": dict(self.story_optimization)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_story_optimization(plan, chunks, pacing_ctx, job_id)` added; called after Phase 19 in `_build_plan`; pulls story/retention context from plan; `_append_story_optimization_explainability(plan, opt_plan)` appends: "Strong hook-to-climax flow detected" (hook_to_climax), "Story arc can be tightened" (long_setup/weak_build_up), "Payoff clarity may improve retention" (weak_payoff/abrupt_outro), "Opening hook may need strengthening" (weak_hook), "Narrative arc needs clearer structure" (unclear_arc/missing_climax); all helpers wrapped in try/except; never block render
- `app/ai/director/render_influence.py` — `_report_story_optimization(payload, edit_plan, report)` added; reports story optimization as deferred in Phase 20; adds compact entry to `report["skipped"]` with flow/score/issue/recommendation counts; no segment ordering changed, no timing changed, no subtitle rewritten, no FFmpeg commands altered; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase20_story_optimization.py` (new) — 69 tests covering schema defaults, to_dict(), valid types/severities, hook optimizer, payoff analyzer, arc optimizer, story recommender, render influence defer, AI Director integration, and all safety boundaries

**Verification:**

- Phase 20 tests pass (69 tests)
- Full suite passes (1281 tests, zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- `safe_to_auto_apply` structurally False in `StoryOptimizationIssue.to_dict()` — cannot be overridden regardless of stored value
- No segment start/end timing changes — story optimization is metadata-only in Phase 20
- No playback_speed changes
- No FFmpeg command changes
- No subtitle timing changes
- No automatic segment reordering
- No transcript text rewriting
- Never blocks render — all Phase 20 code wrapped in try/except in AI Director
- Deterministic heuristics only — no cloud AI, no API keys, no GPU

**Not yet implemented (intentionally blocked):**

- Automatic segment reordering
- Story-aware timing execution
- Autonomous narrative editing
- AI-generated hook rewriting
- Render-time story mutation

**Known limitations:**

- Advisory only — all issues have safe_to_auto_apply=False
- Deterministic heuristics only — no ML models
- No segment/timing mutation
- No subtitle rewrite
- No autonomous editing

**Architecture notes:**

- Story optimization builds on existing Phase 12 story structure, Phase 16 retention risks, and Phase 4 pacing — no new analysis
- Arc scoring blends structural segment presence (60%) with Phase 12 retention_score (40%) for stability
- `_report_story_optimization` in render_influence records the plan as "deferred_phase20" — safe pass-through for future phases
- Phase 20 runs after Phase 19 (timing mutation) in the AI Director `_build_plan` sequence
- Issues are deduplicated by issue_type before capping at 10

**Integrated systems:**

- Story Intelligence (Phase 12) — segments, dominant_arc, narrative_flow, retention_score drive arc classification
- Retention Intelligence (Phase 16) — risk_regions drive hook/payoff issue detection
- Pacing Intelligence (Phase 4) — energy_level biases narrative score up/down
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 19: Retention-driven Timing Mutation Foundation

**Implemented:**

- `app/ai/timing/__init__.py` (new) — package marker
- `app/ai/timing/timing_schema.py` (new) — `TimingMutationCandidate` dataclass (start, end, action, confidence, reason, risk_category, max_trim_seconds clamped [0, 1.5], safe_to_apply, warnings); `TimingMutationPlan` dataclass (available, mode, candidates capped at 10, estimated_retention_gain, warnings); `VALID_ACTIONS` = {tighten_setup, trim_silence, shorten_outro, hold_hook, no_change, none}; `_MAX_TRIM_SECONDS = 1.5`, `_MIN_CONFIDENCE = 0.70`, `_MIN_REGION_DURATION = 3.0`, `_MAX_CANDIDATES = 10`; no Pydantic, no heavy deps
- `app/ai/timing/timing_safety.py` (new) — `clamp_trim_seconds(value, max_value=1.5) -> float`; `is_candidate_safe(candidate, context=None) -> bool`; gates: confidence ≥ 0.70, action not in {no_change, none, hold_hook}, region duration ≥ 3.0 s, start ≥ 0, max_trim_seconds ≤ 1.5; never raises
- `app/ai/timing/timing_analyzer.py` (new) — `analyze_timing_candidates(retention_context, story_context, pacing_context, transcript_chunks) -> list[TimingMutationCandidate]`; risk-to-action map: long_setup→tighten_setup, silence_gap→trim_silence, pacing_decay (last 25%)→shorten_outro, weak_hook→hold_hook (max_trim=0, advisory only), unclear_payoff→no_change (max_trim=0); confidence derived from severity + pacing energy boost; max_trim per category: long_setup=1.0, silence_gap=0.8, pacing_decay=1.5; never trim more than 25% of region; max 10 candidates; safe_to_apply always False from analyzer; never raises; emits `ai_timing_candidates_analyzed` at INFO
- `app/ai/timing/timing_recommender.py` (new) — `build_timing_mutation_plan(..., enabled=False) -> TimingMutationPlan`; enabled=False → mode='advisory', all safe_to_apply=False; enabled=True → runs is_candidate_safe gate; estimated_retention_gain computed from safe candidates (confidence × trim_ratio × 0.05 cap); never raises; emits `ai_timing_mutation_plan_generated` at INFO
- `app/models/schemas.py` — `ai_timing_mutation_enabled: bool = False` added after ai_beat_transition_enabled; backward-compatible default preserves existing behavior
- `app/ai/director/edit_plan_schema.py` — `timing_mutation: dict = field(default_factory=dict)` added to `AIEditPlan`; `"timing_mutation": dict(self.timing_mutation)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_timing_mutation(plan, chunks, pacing_ctx, enabled, job_id)` added; called after Phase 18 in `_build_plan`; pulls retention/story context from plan; `_append_timing_mutation_explainability(plan, timing_plan)` appends: "Retention risk: setup pacing candidate identified" (tighten_setup), "Retention risk: silence gap trim candidate identified" (trim_silence), "Retention risk: outro pacing decay candidate identified" (shorten_outro), "Timing mutation plan advisory-only (no segments changed)" (advisory mode), "Timing mutation plan ready (N safe candidates, est. gain=X%)" (enabled mode); all helpers wrapped in try/except; never block render
- `app/ai/director/render_influence.py` — `_report_timing_mutation(payload, edit_plan, report)` added; reports timing mutation as deferred in Phase 19; adds compact entry to `report["skipped"]` with mode/candidate/safe/gain counts; no segment start/end changed, no playback_speed changed, no FFmpeg commands altered; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase19_timing_mutation.py` (new) — 63 tests covering schema defaults, to_dict(), valid actions, safety gates, analyzer heuristics, recommender modes, render influence defer, AI Director integration, and all safety boundaries

**Verification:**

- Phase 19 tests pass (63 tests)
- Full suite passes (1212 tests, zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- `max_trim_seconds` hard cap: 1.5 s — no AI-proposed trim exceeds this
- `hold_hook` in `_ADVISORY_ONLY_ACTIONS` — can never receive safe_to_apply=True
- `no_change` and `none` in `_ADVISORY_ONLY_ACTIONS` — advisory-only actions always blocked
- `confidence` gate: ≥ 0.70 — low-confidence candidates always blocked
- `region duration` gate: ≥ 3.0 s — micro-regions always blocked
- `start ≥ 0` gate — hook region start never trimmed below zero
- `enabled=False` default — advisory-only mode; no segment timing changed until explicitly opted in
- No segment start/end timing changes — timing mutation is metadata-only in Phase 19
- No playback_speed changes
- No FFmpeg command changes
- No subtitle timing changes
- Never blocks render — all Phase 19 code wrapped in try/except in AI Director
- Deterministic heuristics only — no cloud AI, no API keys, no GPU

**Architecture notes:**

- Timing candidates are derived from retention risk regions (Phase 16) — no new audio analysis
- `pacing_decay` rule only applies to the last 25% of content to prevent erroneous mid-video trim proposals
- `hold_hook` produces advisory-only candidates with max_trim=0 — signals the hook needs strengthening, not cutting
- `_report_timing_mutation` in render_influence records the plan as "deferred_phase19" — safe pass-through for future phases
- Phase 19 runs after Phase 18 (beat visual execution) in the AI Director `_build_plan` sequence
- estimated_retention_gain is bounded (confidence × trim_ratio × 0.05 per candidate, sum capped at 1.0)

**Integrated systems:**

- Retention Intelligence (Phase 16) — risk_regions drive all candidate generation
- Story Intelligence (Phase 12) — story segments available for future region refinement
- Pacing Intelligence (Phase 4) — energy_level and total_duration used for confidence boosts and last-quarter check
- Explainability (Phase 6) — compact lines appended to summary_lines

### 2026-05-08 — AI Productization Phase 18: Beat-synced Visual Execution Foundation

**Implemented:**

- `app/ai/visuals/__init__.py` (new) — package marker
- `app/ai/visuals/beat_visual_schema.py` (new) — `BeatPulseRegion` dataclass (start, end, pulse_strength clamped [0, 0.15], pulse_style, beat_count, warnings); `TransitionHint` dataclass (start, end, transition_style, confidence, reason, safe_to_apply always False in to_dict()); `BeatVisualExecutionPlan` dataclass (available, execution_mode="metadata_only", bpm, pulse_regions capped at 12, transition_hints capped at 10, warnings); `VALID_PULSE_STYLES` = {none, soft_pulse, punch_pulse, cinematic_pulse}; `VALID_TRANSITION_STYLES` = {none, soft_cut, beat_pulse, energy_pop, cinematic_push}; `_MAX_PULSE_STRENGTH = 0.15`, `_BPM_MIN = 60.0`, `_BPM_MAX = 190.0`, `_MIN_BEAT_COUNT = 4`; no Pydantic, no heavy deps
- `app/ai/visuals/beat_pulse.py` (new) — `build_beat_pulse_regions(pacing_context, beat_execution_context, story_context, retention_context) -> list[BeatPulseRegion]`; gate checks: beat_available required, BPM must be [60, 190], beat_count ≥ 4; style selection: dominant_arc in {tension_release, emotional_peak, curiosity_build, setup_payoff} → cinematic_pulse; energy ≥ 0.7 + fast pacing or bpm ≥ 120 → punch_pulse; energy < 0.3 → soft_pulse; per-story-segment regions with boost for hook/climax/tension/build_up; retention risk overlap softens pulse × 0.5; fallback single region when no story segments; max 12 regions; never raises; emits `ai_beat_pulse_regions_generated` at INFO
- `app/ai/visuals/transition_planner.py` (new) — `build_transition_hints(pacing_context, story_context, retention_context, creator_style_context) -> list[TransitionHint]`; advisory-only; safe_to_apply structurally False; segment-pair transition map: hook→build_up=beat_pulse, build_up→climax=cinematic_push, climax→payoff=energy_pop, etc.; hype creator styles (anime_edit, high_energy_reaction, gameplay_highlight, podcast_viral) → energy_pop override; calm styles (documentary_clean, calm_minimal, interview_clip) → soft_cut override; fast pacing + beat + bpm in range → beat_pulse fallback; arc fallback mapping; max 10 hints; never raises; emits `ai_transition_hints_generated` at INFO
- `app/ai/visuals/visual_execution.py` (new) — `build_beat_visual_execution_plan(...) -> BeatVisualExecutionPlan`; orchestrates pulse regions + transition hints; execution_mode always "metadata_only"; availability requires beat_available + valid bpm + beat_count ≥ 4; never raises; emits `ai_beat_visual_execution_generated` at INFO
- `app/ai/director/edit_plan_schema.py` — `beat_visual_execution: dict = field(default_factory=dict)` added to `AIEditPlan`; `"beat_visual_execution": dict(self.beat_visual_execution)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_beat_visual_execution(plan, pacing_ctx, job_id)` added; called after Phase 17 in `_build_plan`; pulls beat_execution/story/retention/creator_style context from plan; `_append_beat_visual_explainability(plan, visual_plan)` appends: "Beat pulse visual rhythm planned" (punch_pulse regions), "Cinematic visual rhythm planned" (cinematic_pulse regions), "High-energy visual transition hints detected" (energy_pop/cinematic_push/beat_pulse hints), "Visual beat execution remains metadata-only"; all helpers wrapped in try/except; never block render
- `app/ai/director/render_influence.py` — `_report_beat_visual_execution(payload, edit_plan, report)` added; reports beat visual execution as deferred in Phase 18; adds compact entry to `report["skipped"]` with bpm/pulse_regions/transition_hints counts; no FFmpeg commands altered, no timing changed, no visual effects applied; called inside `apply_ai_render_influence` try block
- `tests/test_ai_phase18_beat_visual_execution.py` (new) — 80+ tests covering schema defaults, to_dict(), pulse planner gates, energy/arc style mapping, density softening, transition advisory, render influence defer, AI Director integration, and all safety boundaries

**Verification:**

- Phase 18 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- `pulse_strength` hard cap: 0.15 — matches Phase 11 beat_execution constraint
- `safe_to_apply` structurally False in `TransitionHint.to_dict()` — cannot be overridden
- `execution_mode` always "metadata_only" — planner never sets anything else
- BPM gate: [60.0, 190.0] — outside range → empty regions returned
- beat_count gate: ≥ 4 — below threshold → empty regions returned
- No FFmpeg command changes — beat visual plan is metadata only
- No clip start/end timing changes
- No subtitle timing changes
- No playback_speed changes
- No output validation/status rule changes
- No librosa at runtime — all metadata sourced from existing pacing/beat context
- Never blocks render — all Phase 18 code wrapped in try/except in AI Director
- Deterministic heuristics only — no cloud AI, no API keys, no GPU

**Architecture notes:**

- Beat visual execution builds on existing Phase 11 beat metadata (`plan.beat_execution`) and Phase 4 pacing context — no new audio analysis
- Pulse regions are derived from story segment boundaries (Phase 12) — no new timing introduced
- Transition hints are advisory boundaries between adjacent story segments — no cut mutation
- `_report_beat_visual_execution` in render_influence records the plan as "deferred_phase18" — safe pass-through for future phases
- Phase 18 runs after Phase 17 (subtitle execution) in the AI Director `_build_plan` sequence

**Integrated systems:**

- Beat/Pacing Intelligence (Phase 4/11) — beat_available, bpm, beat_count, energy_level, pacing_style drive all gates
- Story Intelligence (Phase 12) — story segments provide region boundaries; dominant_arc informs pulse/transition style
- Retention Intelligence (Phase 16) — risk_regions soften pulse in overlap zones
- Creator Style Intelligence (Phase 14) — dominant_style biases transition hint style
- Explainability (Phase 6) — compact lines appended to summary_lines

**What Beat Visual Execution can do now:**

- Generate compact beat pulse regions from BPM/energy/story segment metadata
- Classify pulse style per region: punch_pulse (high energy), cinematic_pulse (cinematic arc), soft_pulse (low energy)
- Soften pulse in retention risk overlap zones
- Generate advisory transition hints for adjacent story segment pairs
- Map creator style and story arc to specific transition styles
- Expose compact `"beat_visual_execution"` key in render result_json
- Report beat visual execution as safely deferred in render_influence
- Append advisory explainability lines to AI summary

**Not yet implemented:**

- Actual FFmpeg beat pulse visual effect
- Actual beat-synced transitions in rendered output
- Timeline-driven transition editor
- Autonomous timing mutation
- Playback speed mutation
- per-frame visual beat synchronization

**Known limitations:**

- Metadata-first execution only — no visual output change in Phase 18
- Advisory transition hints only — `safe_to_apply` always False
- No FFmpeg visual mutation
- No clip timing mutation
- No subtitle timing mutation
- Pulse regions derived from story segment boundaries — not from precise audio beat timestamps

> Phase 18 extends the AI system from subtitle execution intelligence toward beat-synced visual rhythm planning, enabling energy-aware pulse regions and advisory transition hints while preserving complete render stability and safety.

---

### 2026-05-08 — AI Productization Phase 17: Dynamic Subtitle Execution Foundation

**Implemented:**

- `app/ai/subtitles/__init__.py` (new) — package marker
- `app/ai/subtitles/subtitle_execution_schema.py` (new) — `SubtitleExecutionHint` dataclass (emphasis_strength, density_mode, emotion_style, beat_sync_strength, keyword_focus, warnings); `SubtitleExecutionRegion` dataclass (start, end, style, emphasis, emotion, beat_strength, metadata); `SubtitleExecutionPlan` dataclass (available, regions capped at 20, global_hint, warnings); `VALID_DENSITY_MODES` = {compact, normal, expressive}; `VALID_EMOTION_STYLES` = {neutral, hype, dramatic, calm, emotional, punch}; all have `to_dict()` methods; no Pydantic, no heavy deps
- `app/ai/subtitles/subtitle_emphasis.py` (new) — `build_subtitle_emphasis(transcript_chunks, pacing_context, emotion_context, retention_context) -> dict`; deterministic only; never raises; `_detect_hook_strength()` scores hook keyword density in early chunks (ratios → 0.85/0.6/0.3/0.1); `_extract_keyword_focus()` extracts keyword_focus list from early chunks; emotion contribution: urgency/excitement/surprise/hype → +0.3–0.5; energy_level > 0.7 → +0.25 emphasis +0.3 beat_sync; beat_available + bpm ≥ 120 → +0.2–0.4 beat_sync; weak_hook retention risk → +0.1 emphasis; all values clamped [0, 1]; emits `ai_subtitle_emphasis_generated` at INFO
- `app/ai/subtitles/subtitle_density.py` (new) — `analyze_subtitle_density(transcript_chunks, pacing_context, story_context) -> dict`; deterministic only; never raises; overload detection: avg_words > 6.0 or max_words > 12 → compact + overload_detected; pacing fast/dynamic → compact; slow_build/slow → expressive; avg_words < 3.0 → expressive; story arc curiosity_build/tension_release/front_loaded → compact; emits `ai_subtitle_density_detected` at INFO
- `app/ai/subtitles/subtitle_emotion.py` (new) — `detect_subtitle_emotion_style(emotion_context, story_context, creator_style_context) -> dict`; deterministic only; never raises; maps emotion → style via `_EMOTION_STYLE_MAP`; maps pacing_style → style via `_PACING_STYLE_MAP`; maps dominant_arc → style via `_ARC_STYLE_MAP`; maps creator_style → style via `_CREATOR_STYLE_MAP`; confidence = top_score × 0.8 + gap × 0.4, clamped [0, 1]; supported mappings: hype/fast pacing → punch/hype; cinematic/tension arc → dramatic; calm/slow → calm; emotional arc → emotional
- `app/ai/subtitles/subtitle_execution.py` (new) — `build_subtitle_execution_plan(...) -> SubtitleExecutionPlan`; orchestrates emphasis + density + emotion; builds temporal regions from transcript chunks (max 20); chunk score > 0.7 → hook style + +0.15 emphasis; story hook/climax segment bounds → style annotation; all region emphasis and beat_strength values clamped [0, 1]; never raises; emits `ai_subtitle_execution_generated` at INFO
- `app/ai/director/edit_plan_schema.py` — `subtitle_execution: dict = field(default_factory=dict)` added to `AIEditPlan`; `"subtitle_execution": dict(self.subtitle_execution)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_subtitle_execution(plan, chunks, pacing_ctx, job_id)` added; called after Phase 16 in `_build_plan`; builds execution plan from story/retention/creator_style context; stores `execution_plan.to_dict()` on `plan.subtitle_execution`; `_append_subtitle_execution_explainability(plan, execution_plan)` appends: "Dynamic subtitle emphasis enabled" (emphasis > 0.3), "Emotion-aware subtitle execution detected" (non-neutral emotion), "Compact subtitle density recommended" (density == compact), "Beat-aware subtitle emphasis enabled" (beat_sync > 0.3); both helpers never raise; wrapped in try/except
- `app/services/subtitle_engine.py` — `apply_subtitle_execution_hints(blocks, subtitle_execution) -> dict` added; safely reads global_hint fields (emphasis_strength, emotion_style, density_mode, keyword_focus); validates and clamps all values; returns `{applied: True, ...}` on success, `{applied: False, ...}` on missing/unavailable metadata; never mutates subtitle blocks timing or text; never raises; emits `subtitle_execution_hints_applied` at INFO
- `tests/test_ai_phase17_dynamic_subtitles.py` (new) — 78+ tests covering all schema, emphasis, density, emotion, execution planner, AIEditPlan field, subtitle engine hints, AI Director integration, and safety boundary requirements

**Verification:**

- Phase 17 tests pass
- Full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**

- No transcript text mutation in any code path
- No subtitle timing mutation — start/end never altered
- No SRT segmentation rewrite
- No playback_speed mutation
- No FFmpeg command changes
- No autonomous subtitle rewriting
- All emphasis/beat_sync values structurally clamped to [0.0, 1.0]
- Density mode validated against frozenset before use
- Emotion style validated against frozenset before use
- Max 20 execution regions — no unbounded output
- Never blocks render pipeline — all subtitle execution errors are caught and recorded as warnings
- Deterministic heuristics only — no cloud AI, no API keys, no external inference, no GPU
- `apply_subtitle_execution_hints` is read-only — returns hints dict, never mutates blocks

**Architecture notes:**

- Subtitle execution intelligence is metadata-first: the plan is built and stored in `result_json["subtitle_execution"]` but does not yet alter ASS generation architecture, karaoke timing, or FFmpeg commands
- `build_subtitle_execution_plan` combines emphasis + density + emotion sub-systems into a single plan object
- All three sub-systems (emphasis, density, emotion) are independently callable and fallback-safe
- Regions are built from transcript chunk boundaries — no new timing introduced
- `apply_subtitle_execution_hints` in subtitle_engine.py is a safe read interface for downstream render steps
- Phase 17 runs after Phase 16 (retention intelligence) in the AI Director `_build_plan` sequence

**Integrated systems:**

- Story Intelligence (Phase 12) — story segments used for region style annotation (hook/climax)
- Retention Intelligence (Phase 16) — risk_regions used for emphasis boost on hook risk
- Creator Style Intelligence (Phase 14) — dominant_style used for emotion style hint
- Beat/Pacing Intelligence (Phase 4) — energy_level, bpm, beat_available drive emphasis and beat_sync
- Explainability (Phase 6) — compact lines appended to summary_lines

**What Dynamic Subtitle Execution can do now:**

- Detect hook keyword density and translate to emphasis strength
- Map pacing/emotion/story signals to subtitle emotion styles (neutral/hype/dramatic/calm/emotional/punch)
- Detect overloaded subtitle density regions and recommend compact/expressive modes
- Build temporal execution regions (max 20) with per-region style, emphasis, and beat_strength hints
- Annotate hook and climax regions from story intelligence
- Boost emphasis when retention hook risk is detected
- Expose compact `"subtitle_execution"` key in render result_json with global_hint + regions
- Append advisory explainability lines to AI summary

**Not yet implemented:**

- Subtitle timing mutation
- Autonomous subtitle rewriting
- Adaptive subtitle segmentation
- Beat-synced karaoke timing mutation
- AI-generated subtitle text
- Adaptive ASS style switching from execution hints

**Known limitations:**

- Metadata-first execution — execution plan is advisory; does not yet alter ASS generation, karaoke logic, or FFmpeg subtitle burn
- Bounded subtitle influence only — no timing, no text, no segmentation changes
- No transcript rewriting — subtitle text is read-only throughout
- No autonomous subtitle generation — all subtitle content originates from Whisper transcription
- Emphasis hints are informational — not yet wired to per-block ASS style overrides

> Phase 17 extends the AI system from retention intelligence toward dynamic subtitle execution planning, enabling emotion-aware, beat-aware, and density-aware subtitle metadata while preserving complete subtitle timing stability and render safety.

---

### 2026-05-08 — AI Productization Phase 16: Retention Intelligence Foundation

**Implemented:**

* `app/ai/retention/__init__.py` (new) — package marker
* `app/ai/retention/retention_schema.py` (new) — retention risk dataclasses and compact retention analysis schema; deterministic only; no external deps
* `app/ai/retention/dropoff_detector.py` (new) — heuristic viewer drop-off risk analysis using transcript pacing, silence gaps, subtitle density, hook strength, and story transitions
* `app/ai/retention/retention_analyzer.py` (new) — retention scoring pipeline combining story structure, pacing energy, subtitle readability, and narrative progression into compact retention analysis
* `app/ai/retention/retention_recommender.py` (new) — advisory-only retention recommendations; never mutates render timing, segments, subtitles, playback speed, or FFmpeg commands
* `app/ai/director/edit_plan_schema.py` — `retention: dict = field(default_factory=dict)` added to `AIEditPlan`; included in `to_dict()` output
* `app/ai/director/ai_director.py` — Retention Intelligence block added after Story Intelligence and Creator Style Intelligence; compact retention analysis attached to `plan.retention`; explainability integration added with safe fallback guards
* `tests/test_ai_phase16_retention_intelligence.py` (new) — retention analysis, drop-off detection, explainability, advisory recommendation, schema, and AI Director integration coverage

**Detection categories:**

* `weak_hook`
* `long_setup`
* `low_energy`
* `silence_gap`
* `subtitle_overload`
* `story_drop`
* `unclear_payoff`
* `pacing_decay`

**Verification:**

* 91/91 Phase 16 tests pass
* 959/959 full suite passes (zero regressions)
* `git diff --check` clean

**Safety boundaries enforced:**

* Deterministic heuristics only — no cloud AI, no API keys, no external inference
* Metadata-first execution only
* Advisory-only recommendations
* No segment timing mutation
* No automatic cuts
* No subtitle timing mutation
* No playback_speed mutation
* No FFmpeg command mutation
* Never blocks render pipeline execution
* Never raises on malformed transcript or missing AI context

**Architecture notes:**

* Retention analysis operates entirely on existing AI metadata and transcript context
* No real viewer analytics required
* Retention intelligence is explainability-focused in Phase 16
* Retention recommendations remain advisory metadata only
* Compatible with all prior AI phases and safe fallback execution
* Integrated after Story Intelligence and Creator Style Intelligence inside AI Director

**Integrated systems:**

* Story Intelligence
* Beat/Pacing Intelligence
* Explainability
* Timeline Intelligence
* Smart Preset Evolution
* Creator Style Intelligence
* External Knowledge Learning

**What Retention Intelligence can do now:**

* Detect likely viewer drop-off regions
* Estimate retention pacing quality
* Detect weak hooks and long setup regions
* Identify subtitle overload risk
* Identify pacing decay and story-energy collapse
* Generate advisory retention recommendations
* Append retention insight lines to explainability summaries
* Expose compact `"retention"` metadata in render result_json

**Not yet implemented:**

* Retention-driven timing mutation
* Automatic silence removal
* Autonomous edit optimization
* Viewer analytics integration
* Retention-based subtitle rewriting
* Beat-synced retention execution

**Known limitations:**

* No real viewer analytics integration
* Heuristic scoring only
* No autonomous editing
* No automatic pacing mutation
* Recommendations remain advisory only
* Retention analysis does not yet alter rendered output

> Phase 16 extends the AI system from story understanding toward viewer-retention-aware editing analysis while preserving stable render execution.

### 2026-05-08 — AI Productization Phase 15: External Knowledge Learning Foundation

**Implemented:**
- `app/ai/knowledge/__init__.py` (new) — empty package marker
- `app/ai/knowledge/knowledge_schema.py` (new) — `ExternalKnowledgeItem` dataclass (id, source_type, text, market, platform, style, topic, tags, confidence 0-1, metadata); `KnowledgeSearchResult` dataclass (id, score, text, metadata) with `to_dict()` that caps text at 500 chars; `VALID_SOURCE_TYPES` frozenset = {manual_note, trend_summary, style_pattern, hook_pattern, subtitle_pattern, pacing_pattern, market_pattern}; no Pydantic, no heavy deps
- `app/ai/knowledge/knowledge_ingest.py` (new) — `parse_knowledge_json(data) -> list[ExternalKnowledgeItem]`; never raises; validates each item for required id/source_type/text fields and valid source_type membership; skips malformed items with debug logging; confidence clamped to [0, 1]; tags normalized to list[str]; emits `ai_external_knowledge_loaded count=N skipped=M` at INFO; `ingest_knowledge_file(path: str) -> dict` reads local JSON file only, returns `{loaded, skipped, items, warnings}`; returns file_not_found warning if path missing; never raises on corrupt JSON
- `app/ai/knowledge/knowledge_store.py` (new) — `LocalKnowledgeStore` with in-memory `_items: list[ExternalKnowledgeItem]` and parallel `_vectors: list[Optional[list[float]]]`; `add_item(item) -> bool` tries to embed text via existing `app.ai.rag.embeddings.embed_text`, stores vector or None if unavailable; `add_items(items) -> int` returns count of successful adds; `search(query, top_k=5, filters=None) -> list[KnowledgeSearchResult]` uses vector cosine search if query embeds successfully (items without vectors get 0.0), falls back to keyword token-overlap scoring otherwise; `_apply_filters` passes items with None field through (market-agnostic items included regardless of filter); `_keyword_score` = (matched_tokens / total_tokens) × (0.5 + confidence × 0.5); `_build_result` sets metadata with source_type, market, platform, style, topic, tags, confidence; never raises
- `app/ai/knowledge/knowledge_retriever.py` (new) — `retrieve_external_knowledge(query, context=None, top_k=5) -> dict`; never raises; expects `context["knowledge_store"]` as `LocalKnowledgeStore`; builds field filters from `context["market"]` and `context["style"]`; returns `{available: False, results: [], warnings: ["no_knowledge_store"]}` when store absent; returns `{available: False, ..., warnings: ["knowledge_store_empty"]}` when count=0; on matches: returns `{available: True, results: [KnowledgeSearchResult.to_dict(), ...], warnings: []}`; emits `ai_external_knowledge_matched count=N top_score=X.XXX` at INFO; emits debug on skip
- `app/ai/director/edit_plan_schema.py` — `external_knowledge: dict = field(default_factory=dict)` added to `AIEditPlan`; `"external_knowledge": dict(self.external_knowledge)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_external_knowledge(plan, chunks, pacing_ctx, context, mode, job_id)` added; checks `context.get("knowledge_store")`; if absent sets `available=False`; builds query from mode + market + transcript excerpt (first 5 chunks, max 200 chars); extracts style_hint from `plan.creator_style["dominant_style"]` if Phase 14 already ran; calls `retrieve_external_knowledge` with `{knowledge_store, market, style}` context; stores compact summary via `_build_knowledge_summary` on `plan.external_knowledge`; `_build_knowledge_summary(result)` → `{available, matched_items, top_matches: [{source_type, market, style, score, text[:300]}]}`; `_append_knowledge_explainability(plan, result)` appends "External curated knowledge matched this edit style" and "Market-specific hook guidance identified" (when hook_pattern result present) with dedup guard; Phase 15 block added after Phase 14 in `_build_plan`; all helpers never raise; emits `ai_external_knowledge_matched` / `ai_external_knowledge_skipped` logs
- `tests/test_ai_phase15_external_knowledge.py` (new) — 79 tests covering: schema defaults and to_dict() for both dataclasses, VALID_SOURCE_TYPES completeness, ingest (valid JSON, malformed items skipped, missing id/text/source_type skipped, invalid source_type skipped, empty list, non-dict input, confidence clamping, tags normalization, file_not_found warning, loaded count, items in result, corrupt JSON fallback), store (empty count, add_item returns True, count increases, add_items count, invalid type returns False, search empty returns empty, returns KnowledgeSearchResult list, keyword search finds matching item, top_k respected, score field present, never raises on garbage query, market filter excludes non-matching, None market passes through, metadata has source_type/market/style, empty/None add_items), retriever (never raises on None/empty args, available False without store, required keys present, available True with populated store, results is list, top_k respected, empty store returns False, market filter passed through, warnings is list), AIEditPlan field (has field, defaults {}, in to_dict, value propagated), AI Director integration (sets dict, available False without store, never raises on empty chunks/None context/garbage store, available True with populated store, top_matches present and capped at 5, build_knowledge_summary available False/True, text capped at 300, explainability append never raises, line added on results, hook pattern adds market line, no duplicate lines, style_hint from creator_style), no external dependencies (no API key, no GPU, no internet, no real rendering, safe imports, works without sentence_transformers, no copyrighted names, never raises on broken store)

**Verification:**
- 79/79 Phase 15 tests pass
- 868/868 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- Local curated JSON files only — no network access, no web scraping, no cloud APIs in any code path
- Advisory metadata only — `external_knowledge` dict in result_json never mutates render commands, subtitles, timing, or segments
- `available=False` returned whenever store is absent, empty, or broken — render pipeline continues unaffected
- No API keys required — knowledge store uses existing optional embedding layer (`sentence-transformers`) with keyword fallback
- `_apply_filters` never blocks items with None fields — market-agnostic knowledge items always pass through
- Never raises in any code path — all knowledge failures are caught and recorded as warnings
- No copyrighted creator names, trend dumps, or scraped content permitted in schema or logic

**Architecture notes:**
- External knowledge is context-injected — `LocalKnowledgeStore` is passed via `context["knowledge_store"]`, not a global singleton
- Vector search uses existing `app.ai.rag.embeddings.embed_text` — no new model dependency
- Keyword fallback is deterministic and works without any AI library installed
- In-memory only in Phase 15 — no SQLite persistence, no disk writes from the knowledge layer
- Phase 15 runs after Phase 14 (creator style); style_hint from `plan.creator_style` is used to filter results

**Integrated systems:**
- AI Director — Phase 15 block attached in `_build_plan` after Phase 14
- Creator Style Intelligence — style_hint extracted from `plan.creator_style["dominant_style"]` for query filtering
- Explainability — `_append_knowledge_explainability` adds up to 2 advisory lines to summary
- Existing embedding layer (`app.ai.rag.embeddings`) — reused for optional vector search

**What External Knowledge Learning can do now:**
- Ingest curated local JSON knowledge files (manual notes, trend summaries, style/hook/pacing/market patterns)
- Store items in memory with optional embedding vectors for semantic search
- Fall back to keyword token-overlap search when embeddings are unavailable
- Filter search results by market and style from the render context
- Attach compact `"external_knowledge"` key to render result_json with matched_items count and top 5 matches
- Append advisory lines to AI explainability summary when knowledge matches edit style
- Identify market-specific hook guidance from matched hook_pattern knowledge items

**Not yet implemented:**
- Online trend ingestion
- Automatic web crawling or social platform API integrations
- Knowledge persistence UI
- Auto-application of external knowledge to render settings
- Knowledge confidence calibration
- Per-market knowledge version management

**Known limitations:**
- Local curated JSON only — no internet access, no autonomous trend ingestion
- Advisory metadata only — no effect on rendered output
- In-memory only — knowledge is lost when process restarts unless store is re-populated
- No autonomous training — all knowledge must be manually curated
- Keyword search is token-overlap only; no TF-IDF, no BM25 weighting

> Phase 15 extends the AI system with a safe, local, auditable external knowledge layer, allowing curated editing/trend knowledge to inform AI recommendations without requiring internet access, cloud APIs, or autonomous training.

---

### 2026-05-08 — AI Productization Phase 14: Creator Style Intelligence

**Implemented:**
- `app/ai/styles/style_schema.py` (new) — `CreatorStyleProfile` dataclass (style_id, display_name, pacing_style, subtitle_style, camera_behavior, hook_style, story_arc_style, energy_level, notes); `StyleClassification` dataclass (available, dominant_style, confidence 0-100, secondary_styles list capped at 3, matched_traits list capped at 6, warnings); `StyleRecommendation` dataclass (recommended_style, confidence 0-100, suggested_adjustments dict, reasons list capped at 5, warnings); all have `to_dict()` methods; no Pydantic, no heavy deps
- `app/ai/styles/style_profiles.py` (new) — 10 creator archetypes in `_PROFILES` dict: `podcast_viral` (fast pacing, punch subtitle, fast_follow camera, urgency hook, high energy), `high_energy_reaction` (fast pacing, punch subtitle, dramatic_push camera, surprise hook, very_high energy), `storytelling_cinematic` (slow_build pacing, minimal subtitle, slow_reveal camera, curiosity hook, medium energy), `documentary_clean` (slow pacing, clean subtitle, static camera, informational hook, low energy), `educational_focus` (medium pacing, bold subtitle, static camera, question hook, medium energy), `anime_edit` (fast pacing, bold subtitle, dramatic_push camera, dramatic hook, very_high energy), `gameplay_highlight` (fast pacing, overlay subtitle, fast_follow camera, reaction hook, high energy), `motivation_short` (medium_fast pacing, bold subtitle, slow_reveal camera, urgency hook, high energy), `interview_clip` (slow pacing, clean subtitle, static camera, question hook, low energy), `calm_minimal` (slow pacing, minimal subtitle, static camera, story hook, very_low energy); `STYLE_IDS` frozenset; `STYLE_DURATION_HINTS` dict (motivation_short/anime_edit=30s, high_energy_reaction=45s, podcast_viral/gameplay_highlight/calm_minimal=60s, etc.); `get_profile(style_id)` and `get_all_profiles()` helpers; no copyrighted creator names anywhere
- `app/ai/styles/style_classifier.py` (new) — `classify_creator_style(transcript_context, pacing_context, emotion_context, story_context, memory_context) -> StyleClassification`; never raises; deterministic rule-based scoring only; `_build_signals()` aggregates all inputs into flat signal dict; `_score_style(style_id, signals) -> (float, list[str])` applies per-archetype rules (energy_level, pacing_style, emotion, bpm, narrative_flow, dominant_arc, chunk_count); confidence formula: base = min(75, best_score), clarity bonus = min(25, gap×0.8) where gap is spread between 1st and 2nd scores; emits `ai_creator_style_classified` at INFO
- `app/ai/styles/style_recommender.py` (new) — `recommend_style_adjustments(classification, current_context=None) -> StyleRecommendation`; never raises; advisory only; `_SAFE_ADJUSTMENT_FIELDS = frozenset({subtitle_style, pacing_style, camera_behavior, hook_style, target_duration_hint})`; `_UNSAFE_FIELDS = frozenset({playback_speed, segment_start, segment_end, timing, codec, bitrate, fps, resolution, ffmpeg, output_format})` — safety gate strips all unsafe keys before returning; loads profile via `get_profile(dominant)`, builds adjustments from profile fields; adds `target_duration_hint` from `STYLE_DURATION_HINTS`; reasons (max 5): archetype display name detected, pacing style identified, energy level match, matched signals, high-confidence match; emits `ai_creator_style_recommended` at INFO
- `app/ai/director/edit_plan_schema.py` — `creator_style: dict = field(default_factory=dict)` added to `AIEditPlan`; `"creator_style": dict(self.creator_style)` added to `to_dict()` output; backward-compatible
- `app/ai/director/ai_director.py` — `_attach_creator_style(plan, chunks, pacing_ctx, job_id)` added; builds `transcript_ctx = {"text": joined first 15 chunks, "chunk_count": len(chunks)}`; passes `story_ctx = dict(plan.story)` for story context; calls `classify_creator_style` then `recommend_style_adjustments`; stores `{**classification.to_dict(), "recommendation": recommendation.to_dict()}` on `plan.creator_style`; `_append_style_explainability(plan, classification)` maps each style_id to a human-readable line via `_STYLE_LINES` dict, appends with dedup guard; Phase 14 block added after Phase 13 in `_build_plan`; both helpers never raise
- `app/orchestration/render_pipeline.py` — `"creator_style": _ai_edit_plan.creator_style if _ai_edit_plan is not None else {}` added to `_result_payload` dict
- `tests/test_ai_phase14_creator_styles.py` (new) — 74 tests covering: schema defaults and to_dict() for all three dataclasses, caps (traits at 6, secondary_styles at 3, reasons at 5), profiles (all 10 archetypes present, required fields, no copyrighted creator names in display_names or notes, duration hints positive, get_all_profiles returns copy), classifier safety (never raises on None/garbage/empty inputs, dominant_style always string, valid style_id or "unknown", confidence in 0-100, available=True with signals), high-urgency classification (high energy + fast pacing → podcast_viral or high_energy_reaction, urgency emotion favors podcast_viral, very_high energy + bpm → reaction or anime, matched_traits nonempty for strong signals), calm classification (calm pacing → documentary or calm_minimal, very_low energy → calm_minimal, neutral/low energy not podcast), cinematic classification (narrative arc → cinematic, setup_payoff arc favors cinematic, curiosity + structured flow not high-energy), recommender safety (never raises on None/unavailable/unknown, no playback_speed/timing/ffmpeg suggestions, reasons ≤5, confidence 0-100, only safe adjustment fields, no copyrighted creators in reasons, advisory only no mutation), recommender suggestions (returns StyleRecommendation, recommended_style matches dominant, adjustments nonempty for known style, reasons nonempty, target_duration_hint present), AIEditPlan field (has field, defaults to {}, in to_dict), AI Director integration (sets creator_style dict, never raises on empty chunks or None pacing, includes recommendation key, explainability append never raises, line added for known style, no duplicate lines, never raises on missing explainability), result JSON compactness (classification to_dict compact, recommendation to_dict compact, full dict has recommendation key), no external dependencies (no API key, no GPU, no external models, no real rendering, safe imports, no network calls)

**Verification:**
- 74/74 Phase 14 tests pass
- 789/789 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- `_UNSAFE_FIELDS` frozenset prevents playback_speed, timing, codec, bitrate, fps, resolution, ffmpeg, output_format from ever appearing in suggested_adjustments
- `_SAFE_ADJUSTMENT_FIELDS` whitelist ensures only subtitle_style, pacing_style, camera_behavior, hook_style, target_duration_hint can be returned
- Advisory only — `recommend_style_adjustments` returns recommendations only; nothing auto-applied
- No copyrighted creator names in any profile display_name, notes field, reason string, or log message
- Classification is archetype-based only — no imitation of any real creator
- Deterministic rule-based scoring only — no ML model, no external inference
- Never raises in any code path — all style intelligence failures caught and recorded as warnings
- No external API calls, no GPU, no optional AI libraries required

**Architecture notes:**
- Creator styles are archetype-based only — no copyrighted creator replication
- Deterministic classification only — heuristic rule scoring, no model inference
- Metadata-first execution — `creator_style` dict in result_json is advisory, no render command mutation
- Advisory-only recommendations — suggestions must be explicitly applied by downstream logic or user
- No timing mutation — style intelligence never alters clip boundaries, segment order, or playback speed
- No render command mutation — FFmpeg commands are never modified by style intelligence

**Integrated systems:**
- AI Director — Phase 14 block attached in `_build_plan` after Phase 13
- Story Intelligence — `story_ctx` passed to classifier for narrative_flow and dominant_arc signals
- Beat/Pacing Intelligence — `pacing_context` passed for energy_level, bpm, pacing_style signals
- Smart Preset Evolution — runs before style intelligence; style complements preset recommendations
- Explainability — `_append_style_explainability` appends human-readable archetype line to summary
- Timeline Intelligence — transcript chunks passed for text density and hook keyword scoring

**What Creator Style Intelligence can do now:**
- Classify editing content into one of 10 creator archetypes from combined signals
- Score each archetype using energy, pacing, emotion, BPM, narrative arc, and text signals
- Compute confidence from score spread (narrow competition → lower confidence)
- Recommend safe style-compatible subtitle_style, pacing_style, camera_behavior, hook_style
- Suggest advisory target_duration_hint from archetype-specific duration hints
- Expose compact `"creator_style"` key in render result_json with classification + recommendation
- Append human-readable archetype detection line to AI explainability summary

**Not yet implemented:**
- Creator-specific fine tuning
- Autonomous creator adaptation
- Online creator learning
- Creator A/B testing
- Creator-style render mutation

**Known limitations:**
- No copyrighted creator imitation — archetypes are generic editing style categories only
- No external creator scraping — all profiles are statically defined
- No automatic preset mutation — recommendations remain advisory
- Recommendations remain advisory — no effect on rendered output
- Confidence is heuristic (not calibrated to actual user satisfaction or creator intent)
- All 10 archetypes are fixed; no user-defined custom archetypes in Phase 14

> Phase 14 extends the AI system from generic editing intelligence toward creator-style-aware editing archetypes while preserving render stability and fallback-safe execution.

---

### 2026-05-08 — AI Productization Phase 13: Smart Preset Evolution

**Implemented:**
- `app/ai/presets/preset_schema.py` (new) — `PresetPerformanceSample` dataclass (preset, ai_mode, market, score, duration, subtitle_tone, camera_behavior, pacing_style, story_arc, status, metadata); `PresetRecommendation` dataclass (recommended_preset, confidence 0-100, reasons list capped at 5, suggested_adjustments dict, warnings); `PresetEvolutionReport` dataclass (available, market, ai_mode, best_samples list capped at 5, recommendation, warnings); all have `to_dict()` methods; no Pydantic, no heavy deps
- `app/ai/presets/preset_analyzer.py` (new) — `analyze_preset_performance(memories, context=None) -> PresetEvolutionReport`; never raises; accepts list of memory result dicts (from retriever) or MemorySearchResult-like objects; parses each into `PresetPerformanceSample` with `_parse_sample()` — handles dict with "metadata" key, direct attributes, or both; relevance scoring: status weight (completed=1.0, completed_with_errors=0.7, failed=0.2), market match +0.25, mode match +0.25, output score ÷ 100 × 0.30; sorts by relevance, separates usable from failed; confidence formula: base = min(60, usable×12), penalty for <3 samples, failure rate penalty up to −25, market+mode match bonus up to +20; returns `PresetEvolutionReport` with `recommendation=None` (filled by recommender); emits `ai_preset_evolution_generated` log at INFO
- `app/ai/presets/preset_recommender.py` (new) — `recommend_preset(report, current_context=None) -> PresetRecommendation`; never raises; advisory only — never mutates payload; dominant pattern extraction via `Counter.most_common(1)` across best_samples for subtitle_tone, camera_behavior, pacing_style; `target_duration_hint` from median duration of high-score (≥60) samples; `ai_mode_hint` from most common mode; `_UNSAFE_FIELDS` safety gate strips playback_speed, codec, bitrate, fps, resolution, output_format, validation, ffmpeg, timing before returning; reasons list (max 5): market match, mode match, subtitle tone learning, camera behavior pattern, pacing style correlation; confidence: base = min(50, n×15), high-score bonus up to +20, context match bonus up to +20
- `app/ai/director/edit_plan_schema.py` — `preset_evolution: dict = field(default_factory=dict)` added to `AIEditPlan`; `"preset_evolution": dict(self.preset_evolution)` added to `to_dict()` output; backward-compatible (all existing tests pass)
- `app/ai/director/ai_director.py` — `_attach_preset_evolution(plan, memory_ctx, mode, context, job_id)` added; called after `_attach_story_intelligence` inside `_build_plan`; extracts memories from `memory_ctx.get("results", [])`; builds `preset_context = {"market": market, "mode": mode}`; calls `analyze_preset_performance` then `recommend_preset`; attaches recommendation to report; stores `report.to_dict()` on `plan.preset_evolution`; when no memories available sets `{"available": False, "warnings": ["no_memory_available_for_preset_analysis"]}`; `_append_preset_explainability(plan, report)` appends ("Preset recommendation based on similar successful renders", "Subtitle tone suggestion learned from prior high-score outputs") when confidence ≥ 30.0; dedup guard prevents duplicate lines; both helpers never raise
- `app/orchestration/render_pipeline.py` — `"preset_evolution": _ai_edit_plan.preset_evolution if _ai_edit_plan is not None else {}` added to `_result_payload` dict
- `tests/test_ai_phase13_preset_evolution.py` (new) — 63 tests covering: schema defaults and to_dict() for all three dataclasses, reasons/best_samples caps, analyzer safety (empty/None/garbage inputs never raise, empty/None → available=False, malformed entries skipped, all-failed → available=False), high-score completed samples (produce available report, populate best_samples, cap at 5, completed_with_errors usable), failed samples (warn in report, mixed still works, all-failed gives no usable), market/mode relevance (same market rank higher, same mode rank higher, market/mode stored in report), recommender safety (never raises, unavailable report → confidence 0, None context safe, playback_speed/codec/ffmpeg/timing never suggested, reasons ≤5, confidence 0-100, only allowed adjustment fields), recommender suggestions (subtitle_tone from dominant samples, camera_behavior from dominant, reasons nonempty, all keys in to_dict), AIEditPlan preset_evolution field (has field, defaults to {}, in to_dict), AI Director with no memory (sets available=False, never raises on garbage, works with real memories), explainability integration (appends safely, never raises on missing/None explainability or report, no duplicate lines), result JSON compactness (best_samples ≤5, all keys present, recommendation in output, no raw memory text), no external dependencies (no API key, no GPU, no real rendering, no torch, no sentence_transformers, safe imports)

**Verification:**
- 63/63 Phase 13 tests pass
- 715/715 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- `_UNSAFE_FIELDS` frozenset prevents playback_speed, codec, bitrate, fps, resolution, output_format, validation, ffmpeg, timing from ever appearing in suggested_adjustments
- Advisory only — `recommend_preset` returns recommendations only; nothing auto-applied
- No preset is silently overwritten — `preset_evolution` is metadata only, not wired to payload mutation
- All-failed memories → `available=False`, no recommendation generated
- Empty/missing memory context → `available=False`, warning recorded, render continues
- Never raises in any code path — all preset evolution failures are caught and recorded as warnings
- No external API calls, no GPU, no optional AI libraries required

**What Preset Evolution can do now:**
- Parse historical render memories (from RAG retriever results) into structured performance samples
- Score each sample by market/mode relevance + output score + status weight
- Identify high-performing patterns: dominant subtitle_tone, camera_behavior, pacing_style
- Recommend preset name from most-common preset in best samples
- Suggest safe adjustments: subtitle_tone, camera_behavior, pacing_style, target_duration_hint, ai_mode_hint
- Include confidence score (0-100) and up to 5 human-readable reasons
- Expose compact `"preset_evolution"` key in render result_json
- Append advisory lines to AI explainability summary

**Not yet implemented:**
- Auto-applying evolved presets (explicitly deferred)
- UI preset recommendation controls
- A/B preset testing
- Online learning or feedback loops
- Autonomous preset mutation
- Per-market preset version branching

**Known limitations:**
- Advisory only — no effect on rendered output
- Deterministic heuristics only — no ML, no semantic understanding of preset quality
- Quality depends entirely on the richness of stored render memories; sparse memory → low confidence
- Confidence formula is heuristic (not calibrated to actual user satisfaction)
- Does not change user-selected preset automatically under any circumstance

---

### 2026-05-08 — AI Productization Phase 12: Story Intelligence Foundation

**Implemented:**
- `app/ai/story/story_schema.py` (new) — `StorySegment` dataclass (start, end, segment_type, confidence, emotion, retention_risk, notes); `StoryAnalysis` dataclass (available, narrative_flow, segments, dominant_arc, retention_score, warnings); both have `to_dict()` methods; `VALID_SEGMENT_TYPES` frozenset (`hook`, `setup`, `build_up`, `tension`, `climax`, `payoff`, `outro`, `unknown`); `to_dict()` caps segments at 12 to prevent giant result dumps
- `app/ai/story/story_analyzer.py` (new) — `analyze_story_structure(transcript_chunks, pacing_context=None, emotion_context=None, memory_context=None) -> StoryAnalysis`; never raises; deterministic heuristics only — no ML, no external APIs, no audio loading; divides video into 5 temporal phases (early 0-20%, middle 20-50%, peak 50-75%, late 75-90%, outro 90-100%); classifies each phase using: hook keyword density scoring from transcript text, per-phase energy modulation from `pacing_context.energy_level`, and pacing_style; `_classify_phase` maps (phase_name, text_score, energy_score) → segment_type; computes `dominant_arc` (curiosity_build, setup_payoff, tension_release, emotional_peak, linear_build, front_loaded, informational), `narrative_flow` (hook_to_climax, hook_to_payoff, linear_build, front_loaded, flat), and `retention_score` (0-100, duration-weighted by segment type and confidence); emits `ai_story_analysis_generated` log at INFO with flow/arc/retention/segment count
- `app/ai/story/retention.py` (new) — `estimate_retention(segment, context=None) -> dict` returning `{score:int 0-100, risk:float 0-1, reasons:list[str], warnings:list[str]}`; deterministic only, no ML; per-type score/risk adjustments (hook +20/-0.20, outro -20/+0.25, climax +22/-0.22, etc.); confidence modifier (< 0.30 → −10 score, +0.10 risk); emotion modifier (`curiosity/urgency/surprise/excitement` → +8 score; `sadness/boredom/calm` → −8 score); incorporates `segment.retention_risk` from analyzer via averaging; never raises on garbage input
- `app/ai/director/edit_plan_schema.py` — `story: dict = field(default_factory=dict)` added to `AIEditPlan`; `"story": dict(self.story)` added to `to_dict()` output; backward-compatible (all existing tests pass)
- `app/ai/director/ai_director.py` — `_attach_story_intelligence(plan, chunks, pacing_ctx, memory_ctx, job_id)` added; called after `_attach_explainability` inside `_build_plan`; calls `analyze_story_structure` with transcript chunks and pacing context dict; stores `story.to_dict()` on `plan.story`; `_append_story_explainability(plan, story)` appends compact lines to `plan.explainability.summary.summary_lines` ("Strong opening hook detected", "Narrative climax identified", "Narrative tension peak identified", "Narrative build-up identified", "Retention pacing weakened near ending"); both helpers wrapped in try/except — never block rendering
- `app/orchestration/render_pipeline.py` — `"story": _ai_edit_plan.story if _ai_edit_plan is not None else {}` added to `_result_payload` dict alongside `ai_director`/`ai_render_influence`/`ai_beat_execution`
- `tests/test_ai_phase12_story_intelligence.py` (new) — 61 tests covering: StorySegment/StoryAnalysis schema defaults and to_dict(), VALID_SEGMENT_TYPES, segment cap at 12, analyzer safety (empty/None/garbage inputs never raise, empty → available=False, valid → available=True, no invalid segment types), hook detection (hook keywords in early position → hook segment, neutral text → no hook), build-up detection (rising energy → build_up, low energy → no build_up), climax detection (high intensity → tension or climax), retention risk (all required keys, hook > outro score, outro > hook risk, low confidence increases risk, score/risk clamped 0-100/0-1, never raises on garbage, curiosity emotion reduces risk), AIEditPlan story field (has field, in to_dict(), defaults to {}), result JSON compactness (≤12 segments, all required keys, valid segment types, strings for arc/flow), explainability integration (appends safely, hook line added, never raises on missing/garbage explainability or summary), no external dependencies (no API key, no GPU, no real rendering, no librosa, no torch, safe imports), narrative flow and arc (hook_to_climax on hook+tension, retention_score 0-100, nonempty strings, segments produced, timing non-negative, retention_risk in range)

**Verification:**
- 61/61 Phase 12 tests pass
- 652/652 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- No transcript mutations — story analyzer reads chunks read-only
- No segment timing mutations — start/end never altered
- No subtitle timing mutations
- No playback_speed mutations
- No FFmpeg command changes
- No external API calls, no GPU, no ML models, no audio loading
- Deterministic only — same inputs always produce same story classification
- Story analysis failure never blocks render — wrapped in try/except
- Result JSON limited to 12 segments maximum (no transcript dumps)
- All segment types validated against `VALID_SEGMENT_TYPES` frozenset

**What Story Intelligence can do now:**
- Detect opening hook segments from keyword-dense early transcript text
- Classify narrative build-up phases from rising energy context
- Identify tension/climax regions from peak energy signals
- Estimate per-segment viewer dropout risk deterministically
- Compute overall retention score (0-100, duration-weighted)
- Determine dominant narrative arc (curiosity_build, tension_release, etc.)
- Determine narrative flow shape (hook_to_climax, linear_build, flat, etc.)
- Append compact narrative insight lines to existing AI explainability summary
- Expose compact `"story"` key in render result_json

**Not yet implemented:**
- Story-aware render retiming (Phase 13+)
- Autonomous narrative editing
- Retention-driven cut mutation
- Story-driven subtitle timing or emphasis
- Full emotional arc execution via FFmpeg
- Per-chunk audio-based energy analysis (currently uses whole-video energy_level from pacing context)

**Known limitations:**
- Story classification is positional + keyword-heuristic only — relies on transcript text keyword density and pacing energy_level from beat analysis
- No semantic understanding of narrative meaning — "build_up" is energy-based, not plot-based
- Energy is a single global value from pacing_context, not per-segment audio energy
- Metadata-first: story segments in result_json are advisory only, no effect on rendered output in Phase 12

---

### 2026-05-08 — AI Productization Phase 11: Beat-aware Render Execution

**Implemented:**
- `app/models/schemas.py` — Three new opt-in fields added to `RenderRequest` AI Director section: `ai_beat_execution_enabled: bool = False`, `ai_beat_pulse_enabled: bool = True`, `ai_beat_transition_enabled: bool = False`; all default-false/safe so existing requests are unaffected
- `app/ai/director/edit_plan_schema.py` — `AIBeatExecutionPlan` dataclass added (enabled, beat_available, bpm, beat_count, pulse_strength, suggested_transition_style, execution_mode="metadata_only", warnings); `beat_execution: dict` field added to `AIEditPlan`; `to_dict()` updated to include `"beat_execution"` key
- `app/ai/director/beat_execution.py` (new) — `build_beat_execution_plan(edit_plan, payload, context=None) -> dict`; never raises; never mutates payload, timing, or subtitles; BPM gate: [60.0, 190.0]; beat_count gate: ≥4; pulse_strength clamped to ≤0.15 (energy_level * 0.20); transition style: "metadata_only" if transition disabled, "beat_pulse" if fast/dynamic + BPM ≥ 120 + pulse enabled, else "soft_cut"; execution_mode always "metadata_only" in Phase 11; all metadata sourced from `edit_plan.pacing` — no librosa, no audio models
- `app/ai/director/render_influence.py` — `_apply_pacing_influence` upgraded from report-only to Phase 11 integration: when `ai_beat_execution_enabled=True` AND `pacing.beat_available=True`, calls `build_beat_execution_plan`, stores result on `edit_plan.beat_execution`, records applied or skipped entry; when disabled, records `beat_execution_disabled` in skipped; `_update_explainability` extended to append beat status line (`"Beat-aware execution planned safely"` or `"Beat execution skipped: <reason>"`) after the AI render influence line; deduplication guard prevents duplicates
- `app/orchestration/render_pipeline.py` — AI Beat Execution block inserted after the Phase 10 influence block: `_ai_beat_report` initialized to `{"enabled": False}`; if `ai_beat_execution_enabled=True` and plan exists, checks `edit_plan.beat_execution` cache (populated by influence module if both were enabled together), otherwise calls `build_beat_execution_plan` directly; logs `ai_beat_execution_planned` at INFO with bpm/count/enabled, or `ai_beat_execution_skipped` at DEBUG; `"ai_beat_execution": _ai_beat_report` added to `_result_payload` dict
- `tests/test_ai_phase11_beat_execution.py` (new) — 52 tests covering: schema defaults (AIBeatExecutionPlan, AIEditPlan.beat_execution, RenderRequest fields), disabled behavior (no pacing, beat unavailable, bpm None, None/garbage inputs), BPM validation (< 60 skip, = 60 accept, > 190 skip, = 190 accept, 0 skip, negative skip), beat count validation (< 4 skip, = 4 accept, 0 skip, stored in report), pulse strength bounds (high energy capped at 0.15, zero energy = 0.0, None energy defaults, never negative), transition style logic (disabled → metadata_only, fast+120bpm+pulse → beat_pulse, fast+120bpm+no pulse → soft_cut, dynamic+125bpm → beat_pulse, slow style → soft_cut, fast+low bpm → soft_cut), safety no-mutations (playback_speed unchanged, non-default speed unchanged, segment start/end unchanged, execution_mode always metadata_only), report shape (all 10 keys present, lists, applied entry on success, bpm stored), integration with render_influence (beat planned when enabled, stored on plan, disabled skips + notes, explainability beat line added), no external dependencies (no API key, no librosa, no torch, no GPU, no file I/O)

**Verification:**
- 52/52 Phase 11 tests pass
- 591/591 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- `execution_mode` structurally locked to "metadata_only" — no timing changes possible in Phase 11
- `pulse_strength` hard cap: 0.15
- BPM must be in [60.0, 190.0] or entire beat plan is skipped
- `beat_count` must be ≥ 4 or plan is skipped
- `playback_speed` — structurally never touched
- Segment `start`, `end`, `score` — structurally never touched
- Subtitle timing, text, emphasis — structurally never touched
- No librosa, no audio model loading — all beat metadata from `edit_plan.pacing` only
- Beat execution block is opt-in: `ai_beat_execution_enabled=False` by default

**Not yet implemented:**
- Beat-synced FFmpeg cut timing (Phase 12+)
- Real-time pulse visual effect in video output
- UI toggle for `ai_beat_execution_enabled`
- Subtitle emphasis driven by beat timing
- Full camera behavior execution (AI zoom/push rendered via FFmpeg)

**Known limitations:**
- Phase 11 beat execution is metadata-only: the plan is built and stored in result_json but does not yet alter any FFmpeg command or clip boundary
- `pulse_strength` and `suggested_transition_style` are advisory fields for downstream phases; no visual difference in rendered output in Phase 11

---

### 2026-05-08 — AI Productization Phase 10: Safe Render Influence

**Implemented:**
- `app/models/schemas.py` — `ai_render_influence_enabled: bool = False` added to `RenderRequest`; opt-in only; defaults to False so all existing requests behave identically to before; placed in the AI Director section with other AI flags
- `app/ai/director/render_influence.py` (new) — `apply_ai_render_influence(payload, edit_plan, context=None) -> tuple[object, dict]`; `clamp_ai_influence(value, min, max, default) -> float`; never raises; mutates payload in-place (required: pipeline reads payload fields directly throughout); returns same payload object plus influence_report
- `render_influence.py` — Camera influence: activates `motion_aware_crop=True` only when `camera.behavior` is in `{"fast_follow", "dramatic_push", "slow_reveal"}` AND payload already has `motion_aware_crop=True` OR `reframe_mode` is in `{"motion", "subject", "face"}` — the safety gate prevents force-enabling motion crop on static renders; `zoom_strength` clamped to ≤1.18, `follow_strength` clamped to ≤0.85
- `render_influence.py` — Subtitle influence: enables `highlight_per_word=True` only when `subtitle.highlight_keywords=True` AND `add_subtitle=True` on payload; never alters subtitle text, timing, ASS formatting, or market subtitle policy
- `render_influence.py` — Pacing influence: report-only in Phase 10; pacing_style and energy_level recorded in skipped list with `beat_sync_deferred=phase11` annotation; no clip duration or cut timing changes
- `render_influence.py` — Memory influence: report-only in Phase 10; memory context result count recorded in skipped list; no render settings altered based on memory
- `render_influence.py` — Explainability update: appends compact status line (`"AI render influence applied safely (N adjustments)"` or `"AI render influence enabled (no adjustments needed)"`) to `edit_plan.explainability.summary.summary_lines` if it exists; deduplication guard prevents duplicate lines; cosmetic-only, never raises on missing explainability
- `app/orchestration/render_pipeline.py` — AI Render Influence block inserted after AI Director plan creation (line ~1695) and before per-part loop; `_ai_influence_report` initialized to `{"enabled": False}`; only invoked when `_ai_edit_plan is not None` AND `ai_render_influence_enabled=True`; outer try/except ensures any module-level crash still leaves render running with the original payload; logs `ai_render_influence_applied` at INFO or `ai_render_influence_module_failed` at WARNING; `ai_render_influence` key added to `_result_payload` dict alongside `ai_director`
- `tests/test_ai_phase10_render_influence.py` (new) — 53 tests covering: schema defaults/backward-compat, module import safety, None plan/payload/corrupt plan never raises, `clamp_ai_influence` bounds, zoom/follow clamped values in applied report, `playback_speed` never touched, segment `start`/`end`/`score` never touched, subtitle timing/text fields never touched, influence report shape (`enabled/applied/skipped/warnings`), camera gate (only when motion_aware_crop or motion reframe), subtitle gate (only when add_subtitle=True), pacing/memory always skipped (report-only), explainability line append + dedup guard, fallback on corrupt plan fields, no API key, no GPU, no real video

**Verification:**
- 53/53 Phase 10 tests pass
- 539/539 full suite passes (zero regressions)
- `git diff --check` clean

**Safety boundaries enforced:**
- `zoom_strength` hard cap: 1.18 (AI plan values above this are clamped)
- `follow_strength` hard cap: 0.85
- `motion_aware_crop` only enabled if payload already permits motion-aware render
- `highlight_per_word` only enabled if `add_subtitle=True`
- `playback_speed` — structurally never touched
- Segment `start`, `end`, `score` — structurally never touched
- Subtitle timing, text, ASS logic — structurally never touched
- Output validation fields — structurally never touched
- Pacing cuts — deferred (Phase 11)
- Memory-driven render changes — deferred (Phase 11)

**Not yet implemented:**
- Beat-synced cuts (Phase 11)
- Render-time subtitle emphasis override
- Full camera behavior execution (AI zoom/push rendered via FFmpeg)
- UI toggle for `ai_render_influence_enabled`
- Autonomous editing

**Known limitations:**
- AI influence is intentionally conservative in Phase 10
- Camera influence activates `motion_aware_crop` but does not pass AI zoom/follow values into the FFmpeg motion crop pass (those are payload-level fields not yet linked to AI values)
- Pacing style observation does not yet alter cut timing or segment ordering
- Memory context is observed but not applied to render settings until Phase 11

---

### 2026-05-08 — AI Productization Phase 9: Packaging + Performance Stabilization

**Implemented:**
- `app/ai/diagnostics.py` (new) — `get_ai_runtime_diagnostics() -> dict`; returns `{dependencies, startup_safe, embedding_available, vector_store, memory, warnings}`; uses dependency detectors only — never loads models, never triggers embeddings, never raises; `embedding_available` checks library presence via `importlib.util.find_spec`, not model load; `memory.db_path` is sanitized to filename only (no full path exposed)
- `app/ai/rag/sqlite_store.py` — three new methods on `SQLiteMemoryStore`:
  - `health() -> dict` — checks DB file existence and row count without requiring `initialize()`; returns `{sqlite_available, count, warnings}`; never raises
  - `vacuum() -> bool` — opens connection with `isolation_level=None` (autocommit) to run `VACUUM` legally; returns `True` on success, `False` on any failure; requires `_ready=True`
  - `prune(max_rows=5000) -> int` — deletes oldest memories and their matching embeddings in a single transaction (embeddings deleted first for FK consistency); returns rows deleted; never raises; never blocks rendering
- `app/ai/rag/vector_store.py` — `health() -> dict` on `LocalVectorStore`; returns `{count, faiss_available, fallback_mode, warnings}`; uses `has_faiss()` detector, not FAISS import; never raises even on corrupted internal state
- `app/ai/rag/memory_store.py` — two new methods on `LocalMemoryStore`:
  - `get_memory_health() -> dict` — aggregates vector store + SQLite health; returns `{vector_count, sqlite_count, faiss_available, fallback_mode, sqlite_available, hydrated, warnings}`; never raises
  - `compact_memory(max_rows=5000) -> dict` — calls `prune()` then `vacuum()` if rows were deleted; returns `{pruned, vacuumed, message}`; never raises
- `app/routes/render.py` — `GET /api/render/ai-diagnostics` endpoint; read-only, no auth changes, matches existing `/queue-status` style; delegates to `get_ai_runtime_diagnostics()`; returns `{startup_safe, error}` fallback on any failure; no model loading, no embedding computation
- `tests/test_ai_phase9_packaging_performance.py` (new) — 39 tests covering: diagnostics import safety, `get_ai_runtime_diagnostics()` shape/behavior, dependency key presence, embedding lazy-load verification (reload-based sentinel check), `embed_text`/`embed_texts` None-safety, vector store `health()` in fallback mode, SQLite `health()`/`vacuum()`/`prune()` on temp DBs, embedding-memory FK consistency after prune, memory store health/compact, API key independence, GPU independence, model-load guard

**Verification:**
- 39/39 Phase 9 tests pass
- 486/486 full suite passes (zero regressions)
- `git diff --check` clean (LF→CRLF warnings are Windows `core.autocrlf` only)

**Constraints preserved:**
- No optional AI lib made mandatory
- No heavy import at module level (sentence-transformers/faiss/torch/mediapipe/faster-whisper never imported at startup)
- No render pipeline modified
- No render engine modified
- No DB schema changed
- No Electron packaging config changed
- No cloud dependencies added
- No background services added
- All diagnostics are read-only — zero side effects on render behavior

**Not yet implemented:**
- Full Electron packaging validation (installer size, bundle audit)
- Real startup profiling (time-to-first-render measurement)
- GPU/CPU model selection UI
- Render-time AI influence (Phase 10+)
- Memory compaction scheduled job (currently manual call only)

**Known limitations:**
- Diagnostics are lightweight snapshots — they do not benchmark model inference speed
- Optional AI libraries remain user-installed (`requirements-ai.txt`)
- Memory compaction is SQLite-only; in-memory vector store is not pruned (only rebuilds on app restart)
- `vacuum()` requires the store to be initialized (`_ready=True`); safe to call at any time otherwise (returns False)

---

### 2026-05-08 — AI Director Phase 8: Timeline Intelligence UI

**Implemented:**
- `index.html` — `#evAiOverlayLayer` div added inside `#evTimelineBarWrap` (after `#evTimelineLayers`); `#evAiTimelineLegend` div added after the `evTimeline` block, inside `view_editor`; both hidden by default; `aria-hidden="true"` set; no existing IDs or DOM structure changed
- `editor-view.js` — `aiPlan: null` added to `_ev` state object; reset to `null` in both `openEditorView()` and `openEditorView_withSession()` on session open; `_evSetDuration()` now calls `_evRenderAiTimeline()` after updating trim UI so overlay redraws whenever duration changes
- `editor-view.js` — `_evSetAiPlan(plan)` public setter: stores plan in `_ev.aiPlan` and triggers `_evRenderAiTimeline()`; `_evRenderAiTimeline()` builds absolute-positioned segment bars from `plan.selected_segments[].{start,end,score}`; segments with `score ≥ 0.7` get hook class (amber); populates legend with AI Clip / Hook chips and energy+emotion badge; clears overlay and hides legend when plan is absent, disabled, or duration is zero
- `render-ui.js` — `renderAiInsights()` calls `if (typeof _evSetAiPlan === 'function') _evSetAiPlan(aiDir)` immediately after the panel becomes visible, so the editor timeline overlay is populated whenever a completed render's AI plan is shown
- `app.css` — ~80 lines of Phase 8 styles appended at end; `.evAiOverlayLayer` (absolute, `bottom:12px`, `height:6px`, `pointer-events:none`, `z-index:2`); `.evAiSegBar` (blue clip bars, `rgba(99,179,237,.50)`); `.evAiSegBarHook` (amber hook bars with subtle glow, `rgba(251,191,36,.72)`); `.evAiTimelineLegend` (flex row, dark bg, `border-top`); `.evAiLegendItem`/`.evAiLegendHook` with `::before` color chips; `.evAiLegendEnergy` with `data-energy` color variants (high=green, mid=amber, low=blue)

**Visible behavior:**
- Editor timeline shows no overlay by default (clean, no regression)
- After a render completes with AI Director enabled, switching to editor view reveals colored segment bars overlaid on the timeline: blue for standard AI clips, amber/gold for high-score hook segments
- Legend row appears below the timeline showing clip/hook chip legend and a right-aligned energy+emotion summary badge (color-coded by energy tier)
- Hovering a segment bar shows a tooltip with start/end times and score
- Overlay is fully static — no per-frame updates; `pointer-events: none` throughout so seek and trim interactions are completely unaffected
- On editor re-open (`openEditorView*`), overlay and legend are cleared

**Constraints preserved:**
- No canvas, no SVG libraries, no chart dependencies
- No new API endpoints
- No WebSocket or render queue logic changed
- No existing CSS classes or editor DOM modified (additions only)
- `_evOnTimeUpdate()` untouched — no per-frame overlay work
- Overlay does not appear until a completed render provides AI metadata

**Not yet implemented:**
- Interactive AI controls (user-adjustable confidence thresholds)
- Beat-sync render execution triggered from UI
- Story intelligence UI
- Real-time pacing visualization during active render

---

### 2026-05-08 — AI Director Phase 7: Insights UI

**Implemented:**
- `index.html` — `#ai_insights_panel` div added inside `#render_active_panel`, after the dominant render card (`rdCard`); includes `#ai_conf_badge` (confidence badge) and `#ai_insights_body` (dynamic content); starts hidden (`hiddenView`); no existing IDs or layout changed
- `render-ui.js` — `renderAiInsights(job)` called at end of `updateRenderMainState()`; `resetAiInsightsPanel()` called from `resetRenderSessionUi()`; panel hides cleanly when `ai_director` is absent or `enabled=false`; all text content safely escaped via existing `esc()` helper
- `render-ui.js` — `renderAiInsights(job)` builds 6 sections: ① summary headline + bullets (max 5), ② confidence bars (Semantic/Pacing/Memory via CSS `--ai-bar-pct`), ③ pacing + camera cards in 2-col grid (behavior/BPM/emotion/energy/zoom), ④ subtitle card (tone/emphasis/density/beat-aware/emotion-aware), ⑤ memory card (only when `memory_context.results` is non-empty), ⑥ warning pills from `ai_summary.warnings`
- `render-ui.js` — `_aiBarLevel(pct)` maps 0-39→low, 40-69→mid, 70+→high; `_aiEnergyLabel(level)` maps float energy to High/Moderate/Low; `_aiBarRowHtml(label, pct)` generates CSS-only bar row HTML
- `app.css` — ~150 lines of new AI Insights styles appended at end; classes: `.aiInsightsPanel`, `.aiInHeader`, `.aiInLabel`, `.aiInConfBadge` (color-coded by level data attribute), `.aiInBody`, `.aiHeadline`, `.aiSummaryList/.aiSummaryItem`, `.aiConfGrid/.aiBarRow/.aiBar/.aiBarFill` (CSS custom property `--ai-bar-pct`), `.aiInsightGrid/.aiInsightCard/.aiInsightCardBadge` (color variants: default/green/amber), `.aiMemCard`, `.aiWarnPill`; no existing CSS classes modified

**Visible behavior:**
- AI Insights panel is hidden during active rendering (no `result_json.ai_director` yet)
- Panel appears after render completes if `ai_director_enabled=true` in request
- Confidence badge color-codes: green ≥70, amber 40–69, red <40
- Bar fills are pure CSS (no canvas, no SVG libraries, no chart deps)
- Pacing/camera/subtitle cards use compact badge layout with color semantics (green=positive, amber=caution, default=neutral)
- Memory card appears only when past render results were retrieved
- Warnings shown as amber pills below the main content
- Panel hides completely if no AI metadata — existing render card layout unchanged

**Constraints preserved:**
- No existing IDs, classes, or render flow modified (only additions)
- No React, Vue, or chart library added
- No WebSocket logic changed
- No backend API changes
- No render queue logic changed
- 447/447 backend tests still passing after changes
- `git diff --check` clean

**Not yet implemented:**
- Timeline AI overlays (per-clip reasoning markers)
- Interactive AI controls (user-adjustable confidence thresholds)
- Beat-sync render execution triggered from UI
- Story intelligence UI
- Real-time pacing visualization during active render

**Known limitations:**
- AI Insights only visible after render completion (result_json not set during active render)
- Compact visualization only — no detailed breakdown modals
- No timeline overlays yet

---

### 2026-05-08 — AI Director Phase 6: Explainability Foundation

**Implemented:**
- `app/ai/explainability/` package (new) — deterministic, rule-based, no external deps, never raises
- `reason_builder.py` (new) — four public functions: `build_clip_reasons`, `build_camera_reasons`, `build_subtitle_reasons`, `build_pacing_reasons`; each returns up to 5 deduplicated human-readable strings; explanations derived from existing plan data only — no hallucination; all functions wrapped in `try/except` returning `[]` on failure
- `confidence.py` (new) — `calculate_ai_confidence(edit_plan) -> dict`; returns `{overall, clip_selection, semantic, memory, pacing, camera, subtitle, warnings}` (all 0–100); weighted overall score (clip×0.30, semantic×0.20, memory×0.15, pacing×0.20, camera×0.075, subtitle×0.075); graceful degradation: semantic≤40 when embeddings unavailable, memory≤30 when RAG error, clip=20 when no segments; never raises
- `summary.py` (new) — `build_ai_summary(edit_plan, confidence) -> dict`; returns `{headline, summary_lines≤6, strengths≤6, warnings, confidence}`; headline reflects overall quality (Strong/Solid/Basic), energy level, emotion, and mode label; warnings derived from plan warnings + confidence warnings; never raises
- `AIEditPlan` expanded — two new fields: `explainability: dict = {}` and `confidence: dict = {}`; `to_dict()` updated with: `explainability` (full reasons + summary), `confidence` (full scores), `ai_summary` (compact headline/lines/strengths/warnings without nested confidence), `ai_confidence` (compact overall/semantic/memory/pacing subset for result_json)
- `ai_director.py` upgraded — `_attach_explainability(plan, job_id)` helper called at end of `_build_plan()`; guarded by local try/except so explainability crash can never block plan return; logs `ai_explainability_generated` and `ai_confidence_generated` at INFO level; explainability error appended to `plan.warnings` as `"explainability_error:*"` when it does fail

**Tests added:**
- `backend/tests/test_ai_explainability_phase6.py` — 64 tests covering reason builder imports/determinism/deduplication/content, confidence imports/structure/degradation rules (semantic≤40 on embeddings_unavailable, memory≤30 on rag_error, clip=20 on no segments), summary structure/compactness/headline quality signals, schema new fields and to_dict keys, AI Director integration (plan has explainability+confidence after creation, to_dict includes ai_summary/ai_confidence, crash isolation via monkeypatch, JSON serialization), constraint checks (no API key, no GPU, no cloud), Phase 1–5 regression

**Phase 6 design constraints preserved:**
- No cloud API calls, no API keys
- No ML models, no GPU
- No LLM reasoning — all explanations are deterministic from existing plan data
- No changes to render_pipeline.py, render_engine.py, subtitle_engine.py, motion_crop.py
- Explainability is observation-only metadata — render output unchanged
- All prior Phase 1–5 tests pass without modification (383 → 447 total)

**How it works:**
- `reason_builder` maps plan fields (behavior, emotion, BPM, scores, flags) to human-readable strings via rule lookups — same inputs always produce same outputs
- `confidence` scores each dimension from available evidence (segments, warnings, memory results, beat data) with explicit floor values when data is absent
- `summary` derives headline quality ("Strong/Solid/Basic") from overall confidence and combines emotion+energy+mode into a natural-language label
- All data flows into `to_dict()` → `result_json["ai_director"]["ai_summary"]` and `["ai_confidence"]` automatically, with no render_pipeline.py changes needed

**Not yet implemented:**
- Explainability UI — no frontend exposure yet
- Timeline AI overlays showing per-clip reasoning
- Interactive AI insights panel
- Story intelligence layer
- Render-time AI overrides based on confidence

**Known limitations:**
- Explanations are rule-based string mappings — intentionally compact, no natural language generation
- Confidence scores are heuristic (weighted rules), not calibrated probabilities
- `ai_summary` and `ai_confidence` appear inside `result_json["ai_director"]`, not at result_json top level

---

### 2026-05-08 — AI Director Phase 5: Camera + Subtitle Intelligence

**Implemented:**
- `camera_planner.py` (new) — deterministic, rule-based camera behavior planning; no external deps; never raises; priority rules: `clean_subtitle`→disabled, emotion(`surprise`/`urgency`)→`dramatic_push`, fast pacing/high energy(`>0.75`)→`fast_follow`, `storytelling`/`slow_build`→`slow_reveal`, default→mode config; all paths set `subtitle_safe=True`, `zoom_strength`, `follow_strength`, and `reason` string
- `subtitle_planner.py` (new) — deterministic, rule-based subtitle behavior planning; no external deps; never raises; mode-based base config: viral_tiktok=hype/punch/4words, podcast=clean/keyword/6words, storytelling=story/soft/6words, clean_subtitle=clean/none/7words; beat-aware override: if `beat_available AND pacing_style=="fast"` → `density="compact"`; emotion-aware override: if emotion in `{curiosity, surprise, urgency}` → `highlight_keywords=True`; all paths return `reason` string
- `AICameraPlan` expanded — new fields: `zoom_strength` (float, default 1.0), `follow_strength` (float, default 0.5), `motion_energy` (Optional[float]), `reason` (str); `to_dict()` updated
- `AISubtitlePlan` expanded — new fields: `emphasis_style` (str, default "none"), `density` (str, default "normal"), `beat_aware` (bool), `emotion_aware` (bool), `reason` (str); `to_dict()` updated
- `ai_modes.py` upgraded — each mode now has `subtitle_emphasis_style`, `subtitle_density`, `camera_zoom_strength` (viral_tiktok=punch/compact/1.12, podcast=keyword/normal/1.05, storytelling=soft/normal/1.05, clean_subtitle=none/comfortable/1.0)
- `ai_director.py` upgraded — imports `plan_camera_behavior`, `plan_subtitle_behavior`; builds `pacing_ctx` and `transcript_ctx` dicts from pacing plan output; injects `mode_name` into `mode_config_with_name`; calls `_safe_camera_plan()` and `_safe_subtitle_plan()` wrappers that catch all exceptions and return bare plan objects with warning entries (`camera_planner_error:*`, `subtitle_planner_error:*`)

**Tests added:**
- `backend/tests/test_ai_director_phase5_camera_subtitle.py` — 51 tests covering camera planner behaviors (fast_follow, dramatic_push, slow_reveal, none, subtitle_safe invariant, zoom/follow strengths, reason strings, crash safety), subtitle planner (per-mode defaults, beat_aware/emotion_aware overrides, reason strings, crash safety), schema expansion (new fields on both plan types, to_dict completeness), AI Director integration (expanded plans in output, planner crash fallbacks via monkeypatch on `ai_director` module namespace), ai_modes Phase 5 fields, and Phase 1–4 regression guards

**Phase 5 design constraints preserved:**
- No changes to `motion_crop.py` or `subtitle_engine.py` — plans are metadata only
- No camera/subtitle behavior forced into actual render output
- All camera/subtitle data is observation/planning metadata
- All prior Phase 1–4 tests pass without modification (332 → 383 total)

**Not yet implemented:**
- Applying `zoom_strength` to FFmpeg `motion_crop` parameters
- Applying `emphasis_style`/`density` to subtitle engine rendering
- UI controls exposing camera/subtitle intelligence settings
- Memory-context-informed camera/subtitle overrides (RAG feedback loop)

**Known limitations:**
- Camera and subtitle plans are planning hints only; render output is identical to pre-Phase-5
- `motion_energy` field is reserved but not yet populated

---

### 2026-05-08 — AI Director Phase 4: Beat + Emotion Pacing Foundation

**Implemented:**
- `beat_analyzer.py` upgraded — adds `energy` dict (`mean`, `peak`, `curve` ≤64 points) to all return paths; handles `None` audio_path with `"no_audio_path"` warning; full return shape guaranteed regardless of librosa availability
- `emotion_analyzer.py` (new) — rule-based keyword matching across 5 emotion categories (`urgency`, `surprise`, `curiosity`, `excitement`, `warning`); `analyze_text_emotion(text)` for single strings; `analyze_pacing_emotion(chunks)` for transcript-level aggregation; returns `{dominant, score, signals, warnings}`; no external deps; never raises
- `AIPacingPlan` dataclass (new, `edit_plan_schema.py`) — `beat_available`, `bpm`, `beat_count`, `energy_level`, `pacing_style`, `emotion`, `emotion_score`, `suggested_cut_style`, `warnings`; `to_dict()` is compact (no beat arrays, no energy curve)
- `AIEditPlan.pacing` field added — default `AIPacingPlan()` (safe for all existing code and tests)
- `ai_modes.py` upgraded — each mode now has `pacing_style`, `prefer_beat_sync`, `emotion_bias` (viral_tiktok=fast/True/curiosity, podcast_shorts=medium/False/clarity, storytelling=slow_build/False/curiosity, clean_subtitle=stable/False/neutral)
- `ai_director.py` upgraded — `_build_pacing_plan()` runs emotion analysis on transcript chunks; attempts beat analysis if `audio_path`/`source_path`/`video_path` in context; `_suggest_cut_style()` maps BPM→fast_cut/medium_cut/slow_cut or falls back to `pacing_style`; pacing warnings include `"beat_analysis_unavailable"` when no path provided
- `render_pipeline.py` — `source_path` added to `_ai_context` dict (one line, no behavior change)

**Tests added:**
- `backend/tests/test_ai_director_phase4_pacing.py` — 45 tests covering beat analyzer safety, emotion detection, pacing plan schema, mode config, AI Director integration, cut style logic, safety/regression guards

**Phase 4 design constraints preserved:**
- Beat analysis is observation-only; no FFmpeg command changes
- `analyze_beats()` never called at import time
- All pacing data is plan metadata only; existing render output unchanged
- All prior Phase 1–3 tests pass without modification (332 total)

**Not yet implemented:**
- Actual beat-synced cut timestamps in render commands
- Beat-synced zoom/pulse rendering effects
- Emotion-driven camera behavior
- Subtitle emphasis by beat
- UI controls for pacing/beat settings
- Librosa energy used to weight clip selection (Phase 5 candidate)

**Known limitations:**
- Beat quality depends on optional librosa — degrades to `beat_available=False` when absent
- Emotion detection is keyword-only; no ML models
- `pacing_style` influences cut style label only, not actual cuts yet

---

### 2026-05-08 — AI Director Phase 3: Persistent Learning Memory

**Implemented:**
- `SQLiteMemoryStore` (`rag/sqlite_store.py`) — stdlib `sqlite3` only, no ORM; auto-creates `ai_memory.db` under `APP_DATA_DIR` (packaging-safe, same dir as `app.db`); tables: `render_memories`, `embeddings`; methods: `initialize()`, `add_memory()`, `search_memories()`, `count()`, `load_vectors()`; all methods return safe defaults on any failure
- `write_render_memory()` (`rag/memory_writer.py`) — summarizes render result JSON into compact human-readable text; embeds if sentence-transformers available; persists to SQLite; falls back to text-only write if embeddings unavailable; never raises; never blocks rendering
- `LocalMemoryStore` upgraded (`rag/memory_store.py`) — integrates `SQLiteMemoryStore`; `initialize_with_sqlite()` attaches persistence + hydrates in-memory vector store from stored vectors; `add_render_memory()` writes to both SQLite and in-memory; `search_recent()` returns recent memories as text-only fallback (score=0.5)
- `initialize_memory_system(db_path=None)` factory — creates and hydrates a `LocalMemoryStore` in one call; always returns usable store
- `retrieve_ai_context()` upgraded (`rag/retriever.py`) — text-only fallback path: when embeddings unavailable but store has SQLite records, returns recent memories with `"text_only_fallback"` warning instead of empty; behavior unchanged when `memory_store=None` (preserves Phase 2 test compatibility)
- Render pipeline integration (`render_pipeline.py`) — after `upsert_job()`, calls `write_render_memory()` when `ai_director_enabled=True` or a plan was created; wrapped in bare `try/except`; zero impact on render result or job state

**Tests added:**
- `backend/tests/test_ai_director_phase3_memory.py` — 37 tests covering SQLite CRUD, persist/reload, vector round-trip, memory writer, text summary, retriever contract, AI Director end-to-end, safety guarantees, Phase 1/2 regression guard

**Persistence design:**
- DB path: `APP_DATA_DIR / "ai_memory.db"` (resolves to `%APPDATA%\RenderVideoTool\data\ai_memory.db` in packaged mode; `<project>/data/ai_memory.db` in dev)
- Memories stored without vectors still counted and returned via `search_recent()`
- Memories with vectors loaded on `initialize_with_sqlite()` for semantic search in next session
- No ORM, no migration system — only `CREATE TABLE IF NOT EXISTS`

**Not stored:**
- Raw filesystem paths, usernames, proxy credentials, API keys
- Full FFmpeg tracebacks (failure memories store compact summary only)

**Not yet implemented:**
- Beat-aware editing
- Emotion/story pacing
- Camera planner
- Subtitle planner
- UI AI memory controls
- Distributed/cloud vector DB

**Known limitations:**
- Retrieval quality depends on optional sentence-transformers
- Memory score influence intentionally capped at +5
- No cross-device sync
- Session hydration loads ≤500 most-recent vectors (prevents RAM growth)

---

### 2026-05-08 — AI Director Phase 2: Semantic Hook + Local RAG Memory

**Implemented:**
- `RenderMemory` / `MemorySearchResult` dataclasses (`rag/memory_schema.py`) — plain Python, no heavy deps
- `LocalMemoryStore` (`rag/memory_store.py`) — session-scoped in-memory store; `add_render_memory()` / `search_similar()` / `count()`; silently degrades when sentence-transformers absent
- `retrieve_ai_context()` (`rag/retriever.py`) — stable `{enabled, available, results, warnings}` contract; never raises; handles missing deps, missing store, empty store, and search errors independently
- `AIEditPlan.memory_context` field added (`edit_plan_schema.py`); `to_dict()` includes it
- `select_ai_segments()` extended with `memory_context` param (`clip_selector.py`); `_apply_memory_bonus()` adds up to +5 score to top segment when RAG hits score > 0.7; annotates reason with `rag_match`
- `create_ai_edit_plan()` RAG integration (`ai_director.py`): when `ai_use_rag_memory=True`, builds query from mode/market/duration/first-chunk text, calls retriever, attaches result to plan; errors append `rag:` warning prefix and do not crash the plan
- `_build_rag_query()` helper constructs a concise retrieval query for the memory store

**Tests added:**
- `backend/tests/test_ai_director_phase2_rag.py` — 25 tests covering schema, store, retriever contract, plan field, clip bonus, and end-to-end director RAG; all library-optional (pass without sentence-transformers / faiss)

**Constraints preserved:**
- `ai_use_rag_memory=False` default → `memory_context={}` on plan, zero regression risk
- All Phase 1 test_ai_director_phase1.py (24 tests) still pass without modification
- No SQLite persistence in Phase 2 — memory is session-scoped only

**Not yet implemented:**
- Persistent cross-session memory (SQLite / file-based)
- Market-specific retrieval weighting
- Auto-storage of completed renders into memory store
- Beat-aware editing, emotion/story pacing, render segment override

---

### 2026-05-08 — AI Director Phase 1

**Implemented:**
- `AIEditPlan` schema (`edit_plan_schema.py`) — dataclass, no heavy deps, `to_dict()` included
- Transcript normalization (`transcript_analyzer.py`) — accepts list[dict], list[obj], SRT string, plain text; returns [] on any failure
- Silence scoring (`silence_analyzer.py`) — gap-ratio penalty from transcript timing only; no FFmpeg
- Hook scoring (`hook_analyzer.py`) — rule-based always; optional 40% semantic upgrade via sentence-transformers (lazy-loaded)
- Clip selection (`clip_selector.py`) — window scoring with hook + density + duration fit + silence penalty; deduplicates overlapping windows; scene fallback
- AI mode configs (`ai_modes.py`) — `viral_tiktok`, `podcast_shorts`, `storytelling`, `clean_subtitle`
- AI Director orchestrator (`ai_director.py`) — `create_ai_edit_plan(request, context)`: returns `None` on disabled/failure, never raises
- `RenderRequest` AI fields — `ai_director_enabled=False` (all defaults preserve old behavior)
- Pipeline integration — optional call in `render_pipeline.py` after transcription; plan attached to `_result_payload["ai_director"]`; old pipeline runs unchanged when disabled

**Tests added:**
- `backend/tests/test_ai_director_phase1.py` — 24 tests; no GPU, no API keys, no video rendering

**Not yet implemented in Phase 1:**
- RAG memory retrieval (infrastructure exists in `rag/`)
- Beat-aware editing (librosa available but not connected)
- Emotion/story pacing analysis
- Aggressive render segment override (plan is observation-only)
- Semantic similarity across render history
- Market-specific clip preference learning

### 2026-05-08 — P0 Render Foundation Fixes

**Fixed:**
- 16:9 render dimension branch: `resolve_target_dimensions("16:9")` now returns `(1920, 1080)`. The original `else` fallback producing 1080×1440 has been replaced by an explicit `elif "16:9"` branch, extracted into the public helper `resolve_target_dimensions()` in `render_engine.py`.
- `motion_crop._codec_flags()` CPU paths: libx264 and libx265 now include `-maxrate 20M -bufsize 40M` via delegation to the unified `encoder_helpers.codec_extra_flags()`. NVENC path intentionally keeps unconstrained VBR (pipe-latency constraint).
- Body subject crop center formula: `_subject_to_crop_center()` body branch now uses `cy = y + h * 0.50` (mid-body). Face branch retains `cy = y + h * 0.34`.

**Also fixed in same patch (P0-P1 encoder unification):**
- 12 duplicated encoder helpers consolidated into `app/services/encoder_helpers.py`. Both `render_engine.py` and `motion_crop.py` now import from this single source of truth.
- `ffprobe_video_info()` in `motion_crop.py` now wraps `render_engine.probe_video_metadata()` — no uncached subprocess.
- `has_audio_stream()` in `motion_crop.py` now wraps `render_engine._has_audio_stream()`.

**Tests added:**
- `backend/tests/test_render_audit_p0_fixes.py` — 18 focused regression tests (no FFmpeg, no GPU)
- `backend/tests/test_render_guards.py` — dimension selector unit + integration tests
- `backend/tests/test_motion_crop_guards.py` — codec flags + body center guard tests
- `backend/tests/test_probe_unification.py` — probe consolidation guard

**Items intentionally deferred:**
- Smoke test (real render end-to-end): still P0 priority, not yet added.
- `_run_with_retry` stderr capture in `subtitle_engine.py`: P0, deferred.
- BGM filter duplication in `render_part()`: P3, deferred.
- Stall detection in progress timer: P2, deferred.

---

## A. Executive Summary

**Overall render system rating: 6.5 / 10**

The render system is architecturally sound and shows genuine production thinking: NVENC semaphore design, probe caching, retry logic, structured output validation with blackdetect, a progress subsystem with heartbeat threading, and market-aware viral scoring. However, three years of accretion have left a split-module duplication problem that has **already caused a real codec flag divergence** between `render_engine.py` and `motion_crop.py`, a silent 16:9 dimension bug, a body-crop formula that was never finished, and zero automated tests.

### Top 5 Risks

| # | Risk | Severity | Status |
|---|------|----------|--------|
| 1 | `motion_crop._codec_flags()` missing `-maxrate 20M -bufsize 40M` → unbounded bitrate when motion-aware crop is active | HIGH | **Fixed 2026-05-08** — CPU paths delegate to `encoder_helpers.codec_extra_flags()` |
| 2 | `render_part()` aspect_ratio `"16:9"` falls to `else` branch → 1080×1440 portrait output instead of 1920×1080 landscape | HIGH | **Fixed 2026-05-08** — explicit `elif "16:9"` branch in `resolve_target_dimensions()` |
| 3 | Face vs body crop center formula identical (`cy = y + h * 0.34`) for both branches in `_subject_to_crop_center()` — body subjects framed wrong | MEDIUM | **Fixed 2026-05-08** — body branch now `cy = y + h * 0.50` |
| 4 | Zero test suite — every regression is invisible, no smoke test for the entire pipeline | MEDIUM | **Partial** — focused regression tests added; smoke test (real render) still missing |
| 5 | `_run_with_retry()` in `subtitle_engine.py` does not capture stderr → FFmpeg errors during audio extraction are silently discarded | MEDIUM | Open |

### Top 5 Upgrade Priorities

1. ~~**P0 — Fix 16:9 dimension bug**~~ — **Done 2026-05-08.** `resolve_target_dimensions()` in `render_engine.py` now handles all four ratios explicitly.
2. ~~**P0 — Fix `motion_crop._codec_flags()` divergence**~~ — **Done 2026-05-08.** CPU paths unified through `encoder_helpers.codec_extra_flags()`.
3. ~~**P0 — Fix body crop center formula**~~ — **Done 2026-05-08.** Body branch uses `h * 0.50` in `_subject_to_crop_center()`.
4. ~~**P1 — Consolidate duplicate encoder helpers**~~ — **Done 2026-05-08.** `app/services/encoder_helpers.py` is the single source; both `render_engine.py` and `motion_crop.py` import from it.
5. **P0 — Add smoke test suite** — Still open. 10 s reference clip: cut → subtitle → render → validate dimensions + duration. Focused unit regression tests added, but end-to-end smoke test not yet written.

---

## B. Feature Health Matrix

| Feature | Status | Evidence | Main Issue | Upgrade | Priority |
|---------|--------|----------|------------|---------|----------|
| Pipeline Orchestration | Acceptable | `render_pipeline.py:872–1718` | `_process_one_part` closure is ~400 lines inside `run_render_pipeline` | Extract to top-level `_render_one_part(ctx)` | P2 |
| FFmpeg Encode (`render_part`) | Good | `render_engine.py` | **Fixed 2026-05-08** — `resolve_target_dimensions()` handles all aspect ratios correctly | — | Done |
| FFmpeg Encode (motion crop path) | Good | `motion_crop.py` | **Fixed 2026-05-08** — CPU codec flags unified via `encoder_helpers.codec_extra_flags()` | — | Done |
| Codec / GPU Detection | Good | `app/services/encoder_helpers.py` | **Fixed 2026-05-08** — 12 helpers extracted and unified; both files import from single source | — | Done |
| Output Validation | Good | `render_pipeline.py:591–823` | Duration tolerance 15% is generous for clips < 15s | Tighten for short clips | P2 |
| Frame Extraction / Preview | Acceptable | `render.py:184–296`, `render_engine.py:45–117`, `motion_crop.py:244–280` | 3 separate probe implementations; `motion_crop.ffprobe_video_info()` not cached | Unify to single cached `probe_video_metadata()` | P1 |
| Motion Crop / Subject Track | Acceptable | `motion_crop.py` | **Fixed 2026-05-08** — body `cy = h*0.50`; face retains `h*0.34` | — | Done |
| Subtitle Transcription | Good | `subtitle_engine.py:263–`, `render_pipeline.py:1515–1597` | One-time full transcription with heartbeat thread; correct design | — | — |
| SRT Slicing / ASS Conversion | Acceptable | `subtitle_engine.py:147–196` | `apply_playback_speed=False` is intentional; subtitles burned before `setpts` | Document explicitly | P3 |
| Voice / TTS Mix | Needs Inspection | `tts_service.py`, `audio_mix_service.py` | Files outside review scope; timeout and failure visibility unclear | Separate targeted review | P1 |
| Viral Scoring | Acceptable | `viral_scoring.py:1–743`, `render_pipeline.py:52–134` | Missing score defaults to 50 — masks real zero-score content | Differentiate absent vs neutral | P2 |
| Output Ranking | Acceptable | `render_pipeline.py:184–236` | `is_best_clip` init to `False`; `continuity_score` in `ranking_components` but weight=0 | Confirm best-clip pass runs | P1 |
| Render Queue / Progress | Acceptable | `render_pipeline.py:316–361` | No stall detection; parks at 85% when duration unknown | Add wall-clock stall threshold | P2 |
| Frontend Render Payload | Acceptable | `schemas.py`, `render-ui.js` | `retry_count` unbounded; `whisper_model` resolves silently | Add schema bounds; expose in UI | P2 |
| Test Coverage | **Partial** | `backend/tests/` (9 test files, 200+ tests) | Focused unit tests exist; end-to-end smoke test still missing | Add smoke test | P0 |

---

## C. Deep Findings

### 1. Render Pipeline Architecture

**What exists:**
`run_render_pipeline()` at `render_pipeline.py:872` is a single function orchestrating: download → scene detect → segment build → subtitle → per-part FFmpeg render → ranking → finalization. Parts run in `ThreadPoolExecutor` with `JOB_SEMAPHORE` (default 2, env `MAX_RENDER_JOBS`) at line 248.

**What is good:**
- `_set_stage()` at line 954 keeps DB progress consistent on every state transition
- `_render_progress_timer()` at line 316 uses `stop_event.wait()` — wakes immediately on job completion, never drifts
- `resume_from_last` logic at line 1630 skips already-done parts
- `_emit_render_event()` at line 418 writes to 3 targets simultaneously: job log, app.log, error.log
- `_render_error_code()` at line 401 classifies failure patterns into typed codes (RN001–RN006, VOICE001)

**What is weak/risky:**
- `_process_one_part` is an inner closure of ~400 lines (lines 1618–2100+). Closures this large capture too many outer-scope variables (`effective_channel`, `job_id`, `output_dir`, `source`, all payload fields), making unit testing impossible and refactors unsafe.
- `_probe_video_duration()` at line 515 spawns a fresh `ffprobe` subprocess. The cached `probe_video_metadata()` from `render_engine.py` is never used here — redundant subprocess call.
- If `ensure_channel()` at line 905 raises (filesystem permission), the job never reaches `upsert_job()` — DB shows `STARTING` forever.
- No stall detection: if FFmpeg hangs silently, the progress timer increments to 99% and never fails the job.

**Evidence:**
```python
# render_pipeline.py:515–527 — redundant probe, ignoring render_engine cache
def _probe_video_duration(video_path: Path) -> int:
    cmd = [get_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration", ...]
    try:
        r = subprocess.run(cmd, ...)
        return max(0, int(float((r.stdout or "0").strip() or 0)))
    except Exception:
        return 0
```

**Recommended upgrade:**
- Extract `_process_one_part` to a module-level `_render_one_part(ctx: PartRenderContext)` dataclass
- Replace `_probe_video_duration()` calls with `probe_video_metadata(path)["duration"]`
- Add wall-clock stall timeout to progress timer

**Files affected:** `render_pipeline.py`, `render_engine.py`
**Risk: MEDIUM**

---

### 2. FFmpeg Render Quality

**What exists:**
`render_part()` at `render_engine.py:798` builds a VF chain:
`scale+crop → zoom → canvas pad → [denoise] → effect → cinematic color → sharpen → format=yuv420p → fade → ass subtitle → title drawtext → text layers → setpts/speed → fps`

**Critical bug — 16:9 aspect ratio:**
```python
# render_engine.py:839-844 (original — BUG)
if aspect_ratio == "1:1":
    target_w, target_h = 1080, 1080
elif aspect_ratio == "9:16":
    target_w, target_h = 1080, 1920
else:  # "3:4", "4:5" AND "16:9" fall here — BUG
    target_w, target_h = 1080, 1440
```
`"16:9"` is a valid schema value but produces 1080×1440 (portrait 3:4). Correct would be 1920×1080.

> **Status Update — Fixed 2026-05-08:** The inline if/elif block was replaced by `resolve_target_dimensions(aspect_ratio)` — a standalone helper with explicit branches for all four ratios. `render_part()` now calls `target_w, target_h = resolve_target_dimensions(aspect_ratio)`. Regression guard: `tests/test_render_audit_p0_fixes.py::TestAspectRatioDimensions`.

**What is good:**
- NVENC semaphore scoped with `with` at line 983 — releases before CPU fallback
- CPU fallback at lines 992–1028 cleanly reconstructs the full command
- `hqdn3d` denoiser gated on `veryslow/slower` only
- `_cinematic_color_filter()` and `_cinematic_sharpen_filter()` skip sources below 480p at lines 314–327
- BT.709 color metadata applied: `-colorspace`, `-color_primaries`, `-color_trc`
- `force_accurate_cut` at `cut_video():461` handles keyframe-boundary inaccuracy

**What is weak/risky:**
- BGM filter_complex build (lines 945–967) is copy-pasted verbatim for the CPU fallback path at lines 1001–1027. Any mixing logic change must be made in both places.
- `title_text` escaping at line 901 handles `\\`, `:`, `'` but not `%` or `{` — could corrupt `drawtext` filter on edge inputs.
- No `-shortest` guard on the video/BGM amix `duration=first` path when source has no audio.

**Files affected:** `render_engine.py`
**Risk: HIGH (16:9 bug), LOW–MEDIUM (others)**

---

### 3. Frame Extraction / Preview / Thumbnail

**Are there 2 separate frame extraction features? Yes — 3 probe functions and 2 blackdetect passes.**

#### Feature 1: Editor Preview Transcode
- **File:** `render.py:184–296` — `_probe_preview_profile()`, `_is_browser_safe_preview()`, `_ensure_h264_preview()`
- **Purpose:** Convert any source to browser-safe H.264 for the Chromium editor preview
- **Method:** Fresh ffprobe per call → transcode at `crf=28 veryfast` if needed
- **Cache:** Single `preview_h264.mp4` per session dir (existence check at line 242)
- **Status:** Correct and purpose-specific; keep as-is

#### Feature 2: Cached General Probe (shared service)
- **File:** `render_engine.py:45–117` — `probe_video_metadata()`
- **Purpose:** `{duration, fps, has_audio, has_video, width, height}` for all pipeline stages
- **Method:** One ffprobe JSON call, cached by `(abspath, mtime_ns, size_bytes)` at line 32
- **Status:** The authoritative implementation; should be the single source of truth

#### Feature 3: Motion Crop Direct Probe (should be eliminated)
- **File:** `motion_crop.py:244–280` — `ffprobe_video_info()`
- **Purpose:** Get `(width, height, fps)` for crop coordinate calculation
- **Method:** Direct `subprocess.run(ffprobe ...)`, **NOT cached**
- **Problem:** Duplicates `probe_video_metadata()` work; issues a new subprocess every call

#### Blackdetect — 2 separate passes (both intentional):
- **Source blackdetect:** `render_engine.detect_bad_first_frame():576` — scans clip start in source, returns seconds to skip
- **Output blackdetect:** `render_pipeline._assess_output_quality():735` — scans first 0.5s of rendered output for validation
- These serve different purposes and should both be kept.

#### `has_audio_stream` — three implementations:
| Location | Method | Cached? |
|----------|--------|---------|
| `subtitle_engine.py:246` | raw subprocess | No |
| `motion_crop.py:283` | raw subprocess | No |
| `render_engine.py:407` (`_has_audio_stream`) | wraps `probe_video_metadata()` | Yes |

#### Which to keep / refactor:
- `_ensure_h264_preview()` — **KEEP AS-IS** (different purpose: transcode not metadata)
- `probe_video_metadata()` — **KEEP AND EXPAND** as the shared service
- `ffprobe_video_info()` in motion_crop — **REFACTOR** to wrap `probe_video_metadata()`
- `has_audio_stream()` in subtitle_engine and motion_crop — **REPLACE** with `render_engine._has_audio_stream()`

#### Shared service proposal:
```python
# motion_crop.py — replace ffprobe_video_info() body:
from app.services.render_engine import probe_video_metadata

def ffprobe_video_info(video_path: str):
    meta = probe_video_metadata(video_path)
    fps = meta["fps"] if meta["fps"] > 0 else 30.0
    return meta["width"], meta["height"], fps
```
4-line change. Zero API contract change. Eliminates redundant subprocesses.

**UI/API impact:** None. `ffprobe_video_info()` is only called internally within `motion_crop.py`.

**Files affected:** `motion_crop.py`, `subtitle_engine.py`, `render_engine.py`
**Risk: MEDIUM**

---

### 4. Motion Crop / Auto Reframe

**What exists:**
`render_motion_aware_crop()` in `motion_crop.py` uses OpenCV Haar cascades for face/body detection at 16-frame intervals (`subject_detect_interval=16` at config line 40), with EMA smoothing and velocity-limited Gaussian temporal smoothing. Config in `MotionCropConfig` at line 27.

**Critical bug — body crop center formula:**
```python
# motion_crop.py:748-751 (original — BUG)
if subject_kind == "body":
    cy = y + h * 0.34     # BUG: same as face — should be 0.50 for mid-body
else:
    cy = y + h * 0.34     # face: upper bias (correct for forehead/nose focus)
```
Both branches were identical. A detected body was framed as if it were a face — crop centers on upper chest/shoulder instead of visual mid-body. Clearly an unfinished refactor.

> **Status Update — Fixed 2026-05-08:** Body branch now uses `cy = y + h * 0.50`. Face branch retains `cy = y + h * 0.34`. Regression guard: `tests/test_render_audit_p0_fixes.py::TestBodyCropCenterFormula`.

**Codec flag divergence:**
```python
# motion_crop.py:178-183 (original — MISSING maxrate/bufsize)
return ["-crf", str(video_crf), "-profile:v", "high", "-level:v", "5.1",
        "-tune", "film", "-x264-params", x264p]

# render_engine.py:251-257 — CORRECT
return ["-crf", ..., "-maxrate", "20M", "-bufsize", "40M",
        "-profile:v", "high", ...]
```
Same divergence existed for libx265 (motion_crop.py:162–169 vs render_engine.py:235–242).

> **Status Update — Fixed 2026-05-08:** Both the 12-function encoder helper duplication and the codec flag divergence were resolved by extracting all shared encoder logic into `app/services/encoder_helpers.py`. `motion_crop._codec_flags()` now delegates CPU paths to `encoder_helpers.codec_extra_flags()` which includes `-maxrate 20M -bufsize 40M` for libx264 and libx265. NVENC path in `motion_crop` intentionally keeps unconstrained VBR (raw-pipe latency constraint — see comment in `_codec_flags()`). Regression guard: `tests/test_render_audit_p0_fixes.py::TestMotionCropCodecFlags`.

**Duplicated encoder helpers (all 6 must be in sync):**
| Function | render_engine.py | motion_crop.py |
|----------|-----------------|----------------|
| `_ffmpeg_encoders_text()` | line 142 | line 91 |
| `_has_encoder()` | line 152 | line 101 |
| `_nvenc_runtime_ready()` | line 156 | line 105 |
| `_resolve_codec()` / `_resolve_encoder()` | line 200 | line 129 |
| `_map_preset_for_encoder()` | line 260 | line 142 |
| `_codec_extra_flags()` / `_codec_flags()` | line 218 | line 154 |
| `_reup_video_filters()` | line 295 | line 186 |
| `_reup_audio_filter()` | line 304 | line 194 |
| `_safe_filter_path()` | line 412 | line 203 |
| `_detect_windows_fontfile()` | line 416 | line 207 |
| `_detect_windows_fonts_dir()` | line 432 | line 219 |
| `_get_custom_fonts_dir()` | line 442 | line 227 |

**What is good:**
- Velocity limiter (`max_pan_speed_ratio=0.010`) prevents jitter at `_apply_velocity_limiter()`
- Gaussian temporal smoothing (`window=45` frames) gives cinematic panning
- Scene-cut detection resets tracking state at `scene_aware_tracking=True`
- `lost_subject_hold_frames=45` prevents snap-to-center on momentary face loss
- `motion_fallback=True` gracefully degrades to pixel-diff mode
- `render_part_smart()` at `render_engine.py:1114` catches all exceptions and falls back to standard `render_part()`
- NVENC semaphore pre-acquired at `render_engine.py:1077–1079` before passing to `render_motion_aware_crop` — no double-acquire risk

**What is weak/risky:**
- `ffprobe_video_info()` issues uncached subprocess
- Codec flags diverged (missing maxrate/bufsize)
- `subject_padding=0.55` not exposed in schema; users cannot control zoom level

**Files affected:** `motion_crop.py`, `render_engine.py`
**Risk: HIGH (codec flags, body formula)**

---

### 5. Subtitle Feature

**What exists:**
Full pipeline at `render_pipeline.py:1515–1597`:
Whisper transcription (full video once) → `slice_srt_by_time()` per part → optional translation → optional hook text injection → `srt_to_ass_bounce()` or `srt_to_ass_karaoke()` → burn via `ass` FFmpeg filter.

**What is good:**
- Transcription is done **once** on the full source, then sliced per part — correct and efficient
- Heartbeat thread at line 1539 emits progress every 12s during Whisper — prevents UI stall
- `_MODEL_TRANSCRIBE_LOCKS` at `subtitle_engine.py:16` serializes concurrent Whisper calls per model — GPU-safe
- `slice_srt_by_time()` at line 147 correctly handles overlap-clipping and zero-rebasing
- `apply_playback_speed=False` at `render_pipeline.py:1750` is **correct by design**: subtitles are burned into pixels before `setpts` runs, so they automatically ride the frame through the speed change

**What is weak/risky:**
- `_run_with_retry()` at `subtitle_engine.py:211` uses bare `subprocess.run(command, check=True)` with no `capture_output`. FFmpeg errors during audio extraction are silently discarded.
- If the full SRT write fails (disk full, permissions), `full_srt_available` becomes `False` and all parts silently render without subtitles — only a WARNING is emitted.
- `_apply_subtitle_edits_to_srt()` at pipeline line 254 matches blocks by index + 0.5s timestamp tolerance. After translation, block indices can shift and edits apply to wrong blocks.
- Karaoke fallback to bounce when segment-level SRT is detected is silent — no log, no UI warning.

**Evidence:**
```python
# subtitle_engine.py:211-220 — stderr silently discarded on failure
def _run_with_retry(command: list[str], retries: int = 2, wait_sec: float = 0.8):
    attempt = 0
    while True:
        attempt += 1
        try:
            return subprocess.run(command, check=True)  # no capture_output!
        except Exception:
            if attempt > retries:
                raise
            time.sleep(wait_sec * attempt)
```

**Files affected:** `subtitle_engine.py`, `render_pipeline.py`
**Risk: MEDIUM**

---

### 6. Voice / Audio Feature

**Evidence available from imports only:**
```python
# render_pipeline.py:35-36
from app.services.tts_service import generate_narration_mp3
from app.services.audio_mix_service import mix_narration_audio
```
`voice_enabled`, `voice_language`, `voice_gender`, `voice_source` are in the schema.
`voice_source: "subtitle" | "translated_subtitle" | "manual"` routes to different narration text.

**Needs Inspection:** Full behavior of timeout, per-part failure isolation, audio sync, and error visibility requires reading `tts_service.py` and `audio_mix_service.py`. These were not in the review scope.

**Risk: UNKNOWN — P1 for separate targeted review**

---

### 7. Output Ranking / Market Viral

**What exists:**
Two-layer scoring:
1. `viral_scoring.score_part_for_market()` — market-specific component scores
2. `_compute_output_ranking_entry()` at `render_pipeline.py:184` — 6-component weighted combine

```python
# render_pipeline.py:197-204
raw_score = (
    segment_viral_score * 0.35
    + hook_score * 0.20
    + retention_score * 0.20
    + speech_density_score * 0.10
    + market_score * 0.10
    + duration_fit_score * 0.05
)
```

**What is good:**
- Ranking weights are explicit and documented
- `_output_ranking_reason()` at line 154 generates human-readable explanation strings
- `_first_score()` at line 147 has multi-name alias fallback for legacy field names
- `resolve_combined_score_weights()` at line 52 always normalizes to sum=1.0

**What is weak/risky:**
- `_score_component()` at line 137 returns `default=50.0` when a score is `None`. A part with **no** hook score (genuinely 0) is treated identically to a part with a **neutral** score (50). Failed scoring is indistinguishable from absent scoring.
- `is_best_clip: False` and `is_best_output: False` initialized at line 219 — never set to `True` inside this function. The auto_best_export pass must run after ranking. If the job fails before that pass, all clips report `is_best_clip=False`.
- `continuity_score` appears in `ranking_components` at line 213 but has **weight 0** in the raw_score formula. It influences reason strings but not the score — misleading.
- Duration scoring Gaussian curves (US 70±18s, EU 95±25s, JP 50±15s) are hardcoded; no UI to adjust per campaign.

**Files affected:** `render_pipeline.py`, `viral_scoring.py`
**Risk: MEDIUM**

---

### 8. Render Queue / Progress / Logs

**What exists:**
Per-job DB progress via `upsert_job_part()`, background `_render_progress_timer` at `render_pipeline.py:316`, and `_emit_render_event()` writing structured JSON to 3 log destinations.

**Progress timer design:**
```python
# render_pipeline.py:338-343
while not stop_event.wait(timeout=_PROGRESS_TICK_SEC):   # 3.0s
    elapsed = time.monotonic() - encode_start
    if expected_duration > 0:
        progress = min(99, 70 + int(30 * elapsed / expected_duration))
    else:
        progress = 85  # parks here forever when duration unknown
```

**What is good:**
- `stop_event.wait()` pattern wakes immediately on completion — no polling lag
- Progress clamped at 99%; caller always writes authoritative 100% after success
- Log entries include `error_code`, `traceback`, `duration_ms`, `step` — machine-parseable
- `_render_active_count` at line 251 tracks active render count

**What is weak/risky:**
- No stall detection. If FFmpeg hangs, progress parks at 85% (unknown duration) or interpolates to 99% and stays there. Job never auto-fails.
- `_render_active_count` is maintained but never exposed via the API — UI cannot see queue depth.
- Error codes RN001–RN006 and VOICE001 have no user-facing documentation.
- Heartbeat during transcription ticks every 12s; during render the timer ticks every 3s — inconsistent granularity.

**Files affected:** `render_pipeline.py`
**Risk: MEDIUM**

---

### 9. Frontend Render Payload

**Confirmed consumed fields from `schemas.py` and `render_pipeline.py`:**

| Field | Consumed at | Notes |
|-------|------------|-------|
| `render_profile` | pipeline:487 | `fast/balanced/quality/best` |
| `video_preset` / `video_crf` | pipeline:500–509 | override profile defaults |
| `motion_aware_crop` / `reframe_mode` | render_part_smart | |
| `add_subtitle` / `subtitle_style` | pipeline:1501, 1744 | |
| `subtitle_viral_min_score` | pipeline:1492 | gates subtitle per part |
| `hook_apply_enabled` / `hook_applied_text` | pipeline:898–903 | market viral hook |
| `text_layers` | pipeline:1000 | validated at entry |
| `resume_from_last` | pipeline:1602 | skip done parts |
| `playback_speed` | render_engine:911 | clamped 0.5–1.5 |
| `reup_mode` / `reup_bgm_*` | render_engine:931 | |

**What is weak/risky:**
- `retry_count` at pipeline line 950 is clamped `max(0, min(5, int(payload.retry_count)))` but the schema has no declared bounds — client can send arbitrary values.
- `whisper_model` defaults to `"auto"` resolving silently per profile. Users never see which model is running.
- `part_order="viral"` + `subtitle_only_viral_high=True` can silently render low-ranked parts without subtitles — no UI warning.
- `render_output_subdir` required in channel mode is enforced at runtime (`RuntimeError` at pipeline line 906), not at request validation.
- `edit_session_id` bypass at `render.py:132–134` skips all source validation; stale session returns confusing error instead of clean 404.

**Files affected:** `schemas.py`, `render.py`, `render_pipeline.py`
**Risk: LOW–MEDIUM**

---

### 10. Tests / QA Coverage

**Existing tests:** Zero. The `tests/` directory does not exist.

**Critical missing regression cases:**

| Test | Guards |
|------|--------|
| `cut_video` duration tolerance | stream-copy vs re-encode fallback path |
| 16:9 aspect ratio output dimensions | silent wrong-dimension render |
| Motion crop fallback when no face/body | `motion_fallback=True` path |
| Subtitle slicing at `playback_speed=1.5` | burn-in timing correctness |
| NVENC semaphore release on encode failure | no GPU deadlock |
| Output validation rejects empty file | `RN001` code fires |
| Karaoke with segment-level SRT | silent fallback to bounce |
| BGM mix with silent source | `amix`/`shortest` edge case |
| 16:9 render post-fix regression | confirms fix |
| Resume from last skips done parts | `resume_from_last=True` |

---

## D. Frame Extraction Special Review

See Section C.3 above for full analysis.

**Summary:**

| | Feature 1 | Feature 2 | Feature 3 |
|---|-----------|-----------|-----------|
| **Name** | Editor Preview Transcode | Cached General Probe | Motion Crop Probe |
| **File** | `render.py:184` | `render_engine.py:45` | `motion_crop.py:244` |
| **Function** | `_ensure_h264_preview()` | `probe_video_metadata()` | `ffprobe_video_info()` |
| **Cached?** | Yes (file on disk) | Yes (in-process dict) | **No** |
| **Purpose** | Browser-safe preview | All metadata | Width/height/fps |
| **Action** | Keep as-is | Keep and expand | Refactor to wrap Feature 2 |

**Shared service:** `render_engine.probe_video_metadata()` — already exists, just needs to be imported by `motion_crop.py` and `subtitle_engine.py`.

---

## E. Recommended Upgrade Roadmap

### P0 — Bug / Risk Fixes

| Item | File | Location | Change |
|------|------|----------|--------|
| Fix 16:9 render dimensions | `render_engine.py` | 839–844 | Add `elif aspect_ratio == "16:9": target_w, target_h = 1920, 1080` |
| Add maxrate/bufsize to motion_crop codec flags | `motion_crop.py` | 154–183 | Mirror `render_engine._codec_extra_flags()` maxrate/bufsize for both libx264 and libx265 |
| Fix body crop center formula | `motion_crop.py` | 748–751 | Change body branch to `cy = y + h * 0.50` |
| Fix `_run_with_retry` stderr capture | `subtitle_engine.py` | 211–220 | Add `capture_output=True`, propagate stderr on raise |
| Add smoke test: cut → render → validate | new `tests/test_smoke.py` | — | 10s reference clip, assert correct dims, >10KB, non-zero duration |

### P1 — Output Quality

| Item | File | Action |
|------|------|--------|
| Replace `motion_crop.ffprobe_video_info()` | `motion_crop.py:244` | Wrap `probe_video_metadata()` |
| Replace `has_audio_stream()` duplicates | `motion_crop.py:283`, `subtitle_engine.py:246` | Import `_has_audio_stream` from `render_engine.py` |
| Consolidate 12 duplicate encoder helpers | `motion_crop.py:91–238` | Extract to `app/services/encoder_helpers.py` |
| Review Voice / TTS service | `tts_service.py`, `audio_mix_service.py` | Confirm timeout, per-part isolation, failure visibility |
| Confirm `is_best_clip` pass runs before final write | `render_pipeline.py` | Find auto_best_export pass; add assertion or log |
| Replace `_probe_video_duration()` in pipeline | `render_pipeline.py:515` | Use `probe_video_metadata()["duration"]` |

### P2 — Product UX

| Item | Action |
|------|--------|
| Expose active Whisper model in progress UI | Surface `tuned["whisper_model"]` in progress event |
| Add stall detection to progress timer | Wall-clock check: if elapsed > max(120, expected_duration × 10), fail the part |
| Warn when `part_order=viral` + `subtitle_only_viral_high` silences parts | Emit `subtitle_skipped_viral_gate` WARNING event |
| Show score breakdown in part card | `ranking_components` already in part record; just render in UI |
| Make `render_output_subdir` schema-validated in channel mode | Add Pydantic validator in `RenderRequest` |
| Add stall-suspected event at `progress=85` for unknown-duration jobs | Emit WARNING after 5 min at 85% |

### P3 — Performance / Scale

| Item | Action |
|------|--------|
| Reduce BGM filter duplication | Extract `_build_bgm_filter_complex()` helper; used in both GPU and CPU paths in `render_part()` |
| Cache subtitle slice by (start, end, speed) | Skip re-slicing when SRT slice already exists at same params |
| Profile Whisper on large sources | Evaluate `faster-whisper` or `whisper.cpp` for 2–4× speedup |
| Expose `subject_padding` via schema | Add `motion_crop_subject_padding: float = 0.55` to `RenderRequest` |

---

## F. Do Not Touch List

These systems are correctly designed and must not be changed unless a specific defect is confirmed:

1. **`probe_video_metadata()` + `_PROBE_CACHE`** — `render_engine.py:45–117` — Caching strategy is correct; do not rewrite
2. **`_run_ffmpeg_with_retry()`** — `render_engine.py:120–139` — Retry + stderr capture is clean; do not change signature
3. **`_render_progress_timer()`** — `render_pipeline.py:316–361` — `stop_event.wait()` pattern is correct; do not convert to `time.sleep()`
4. **`slice_srt_by_time()` with `apply_playback_speed=False`** — `render_pipeline.py:1750` — The burn-in-before-setpts design is intentional and correct; changing it will break subtitle sync
5. **`NVENC_SEMAPHORE` scoping** — `render_engine.py:24`, `render_part_smart:1077–1112` — Pre-acquire before `render_motion_aware_crop` is correct; do not add a second acquire inside motion_crop
6. **`_validate_render_output()` + `_assess_output_quality()`** — `render_pipeline.py:591–823` — Solid two-phase validation; do not collapse
7. **`_apply_subtitle_edits_to_srt()`** — `render_pipeline.py:254–313` — The 0.5s tolerance guard and silent-skip design is intentional defensive behavior

---

## G. Patch Prompts

### Patch Prompt 1 — Fix Frame Extraction Duplication

```
You are patching motion_crop.py and subtitle_engine.py to eliminate private ffprobe
subprocesses in favour of the shared cached probe in render_engine.py.

Context:
- motion_crop.py:244–280 defines ffprobe_video_info() — fresh subprocess, not cached
- motion_crop.py:283–292 defines has_audio_stream() — fresh subprocess, not cached
- subtitle_engine.py:246–260 defines has_audio_stream() — fresh subprocess, not cached
- render_engine.py:45–117 defines probe_video_metadata() — one subprocess, cached by
  (abspath, mtime_ns, size_bytes); render_engine._has_audio_stream() wraps it

Tasks:
1. In motion_crop.py, add at the top:
     from app.services.render_engine import probe_video_metadata, _has_audio_stream
2. Replace ffprobe_video_info() body (lines 244–280) with:
     def ffprobe_video_info(video_path: str):
         meta = probe_video_metadata(video_path)
         fps = meta["fps"] if meta["fps"] > 0 else 30.0
         return meta["width"], meta["height"], fps
3. Replace motion_crop.has_audio_stream() (lines 283–292) with:
     has_audio_stream = _has_audio_stream
4. In subtitle_engine.py, replace has_audio_stream() (lines 246–260) similarly:
     from app.services.render_engine import _has_audio_stream as has_audio_stream
5. Render a test clip with motion_aware_crop=True and confirm no double ffprobe
   subprocess appears in the debug log.

Do not modify render_engine.probe_video_metadata().
Do not change any function signatures visible outside these files.
```

---

### Patch Prompt 2 — Fix Render Output Validation

```
You are strengthening render output validation in render_pipeline.py and adding
stall detection to the progress timer.

Current problems:
- _validate_render_output() uses 15% duration tolerance for all clips — too loose for
  short clips (e.g., 10s clip allows ±1.5s error).
- _render_progress_timer() parks at 85% forever when expected_duration is unknown and
  never fails a stalled job.
- _assess_output_quality() computes score_penalty but never acts on it.

Tasks:
1. In _validate_render_output() at line 680:
   Replace: tolerance = max(1.0, expected_duration * 0.15)
   With:    tolerance = max(0.5, min(expected_duration * 0.15, 3.0))
   (tightens for short clips, caps at 3.0s for long clips)

2. In _render_progress_timer() at line 316, add a stall guard:
   After the loop starts, compute:
     stall_deadline = encode_start + max(120.0, (expected_duration or 60.0) * 10)
   Inside the while loop, check:
     if time.monotonic() > stall_deadline:
         try:
             upsert_job_part(..., status=JobPartStage.FAILED, ...,
                             message="Render stall detected: wall-clock timeout exceeded")
             _emit_render_event(..., event="render.stall_detected", level="WARNING", ...)
         except Exception:
             pass
         stop_event.set()
         break

3. In the _process_one_part caller of _assess_output_quality(), after receiving the
   quality_result dict, if quality_result["score_penalty"] > 20:
     log a WARNING via _emit_render_event with the warnings list

Do not change _validate_render_output() signature.
Do not remove any existing checks.
```

---

### Patch Prompt 3 — Fix Motion Crop Quality

```
You are fixing two bugs in motion_crop.py and adding the missing codec bitrate flags.

Bug 1 — Body crop center formula (line 748–751):
  Both face and body branches compute cy = y + h * 0.34.
  For a detected body subject, the crop should center at mid-body, not near the top.
  Fix:
    if subject_kind == "body":
        cy = y + h * 0.50    # mid-body center
    else:
        cy = y + h * 0.34    # face: slight upward bias for forehead

Bug 2 — Missing bitrate cap for libx265 (motion_crop.py:162–169):
  Current:
    return ["-crf", str(video_crf), "-tag:v", "hvc1", "-x265-params", x265p]
  Fix: add "-maxrate", "20M", "-bufsize", "40M" before "-tag:v":
    return ["-crf", str(video_crf), "-maxrate", "20M", "-bufsize", "40M",
            "-tag:v", "hvc1", "-x265-params", x265p]

Bug 3 — Missing bitrate cap for libx264 (motion_crop.py:178–183):
  Current:
    return ["-crf", str(video_crf), "-profile:v", "high", ...]
  Fix: add "-maxrate", "20M", "-bufsize", "40M":
    return ["-crf", str(video_crf), "-maxrate", "20M", "-bufsize", "40M",
            "-profile:v", "high", "-level:v", "5.1", "-tune", "film",
            "-x264-params", x264p]

After fixing, verify by rendering a high-motion clip with motion_aware_crop=True
and checking the output file size is consistent with standard render_part() output.
Do not change MotionCropConfig or any function visible outside motion_crop.py.
```

---

### Patch Prompt 4 — Fix Subtitle Robustness

```
You are fixing subtitle reliability issues in subtitle_engine.py and render_pipeline.py.

Fix 1 — Capture stderr in _run_with_retry (subtitle_engine.py:211–220):
  Current:
    return subprocess.run(command, check=True)
  Replace with:
    result = subprocess.run(command, check=True, capture_output=True, text=True)
  On CalledProcessError, re-raise with context:
    except subprocess.CalledProcessError as exc:
        if attempt > retries:
            stderr_tail = (exc.stderr or "")[-1000:].strip()
            raise RuntimeError(
                f"FFmpeg failed (exit={exc.returncode})"
                + (f": {stderr_tail}" if stderr_tail else "")
            ) from exc

Fix 2 — Log karaoke→bounce fallback:
  In srt_to_ass_karaoke(), when it falls back to bounce because word-level timing
  is missing, add before the fallback return:
    logger.warning("srt_to_ass_karaoke: segment-level SRT detected; falling back to bounce style")

Fix 3 — Warn on subtitle_edits misalignment after translation (render_pipeline.py):
  After translate_srt_file() succeeds (around line 1812) and _sub_edits is non-empty:
    if _sub_edits:
        _emit_render_event(..., event="subtitle_edits_may_misalign", level="WARNING",
            message="subtitle_edits applied after translation; index alignment is best-effort")

Do not change the public signatures of srt_to_ass_bounce() or srt_to_ass_karaoke().
Do not alter the apply_playback_speed=False design — it is intentional.
```

---

### Patch Prompt 5 — Improve Render Queue / Progress UI

```
You are adding stall visibility and queue depth to the render progress system.

Backend changes (render_pipeline.py):

1. Add a new GET endpoint to render.py at /api/render/queue-status:
   @router.get("/queue-status")
   def queue_status():
       from app.orchestration.render_pipeline import _render_active_count, _JOB_SEM_VALUE
       with _render_active_lock:
           active = _render_active_count[0]
       return {"active_renders": active, "max_renders": _JOB_SEM_VALUE}

2. In _render_progress_timer (render_pipeline.py:316), when expected_duration <= 0
   and time.monotonic() - encode_start > 300:
     emit a WARNING event with event="render.stall_suspected":
       _emit_render_event(..., event="render.stall_suspected", level="WARNING",
           message=f"Render has been running {elapsed:.0f}s with unknown duration")
   Emit at most once per job (use a local flag inside the timer).

3. After _assess_output_quality() returns, if quality_warnings is non-empty, include
   them in the final upsert_job_part() call so the UI can display them per-part.

Frontend changes (render-ui.js or render-engine.js):

4. Poll /api/render/queue-status every 10s when an active render is detected.
   Display "X of Y render slots active" in the status bar.
   Stop polling when no renders are active.

5. When a part record includes quality_warnings, show a yellow badge "⚠ Quality" on
   the part card with a tooltip listing the warning strings.

Do not add polling when no render job is active.
Do not change the _render_progress_timer stop_event pattern.
```

---

# H. AI Architecture Direction

## Current AI Capabilities

The current render system already contains multiple AI-assisted or AI-like systems:

### Existing AI Features
- Whisper subtitle transcription
- Subtitle translation pipeline
- Motion-aware crop
- Subject tracking
- EMA camera smoothing
- Scene-aware tracking reset
- Viral scoring
- Market-aware subtitle tone
- Hook scoring (heuristic-based)
- Ranking system
- Multi-market presets
- Smart fallback handling

### Current Strengths
- Strong render backbone
- Strong subtitle rendering pipeline
- Structured render events/logging
- Render validation system
- Motion smoothing stability
- Multi-market architecture
- Queue and progress infrastructure
- Electron-compatible architecture
- Offline-first rendering flow

---

## AI Phase Status

### AI Director Phase 1 — 2026-05-08

**Implemented:**
- AI Edit Plan schema (`AIClipPlan`, `AISubtitlePlan`, `AICameraPlan`, `AIEditPlan`)
- Transcript normalization — multi-format, fallback-safe
- Silence scoring from transcript gap analysis
- Rule-based hook scoring + optional semantic scoring (sentence-transformers, lazy-loaded)
- Clip selection foundation — hook + density + duration fit + silence penalty
- AI mode configs: `viral_tiktok`, `podcast_shorts`, `storytelling`, `clean_subtitle`
- Render pipeline integration — safe attachment to `result_json`, observation-only
- 24 unit tests — no GPU, no API keys

**Not yet implemented:**
- RAG memory retrieval and cross-render learning
- Beat-aware editing (librosa pipe)
- Emotion pacing and story structure analysis
- Aggressive render override (plan influences but does not yet replace segment selection)
- Market-specific learning

**Known limitations in Phase 1:**
- Clip selector samples transcript at `len(chunks) // 12` intervals — may miss short high-value windows in very long transcripts
- Silence penalty uses transcript gap data only — does not detect actual audio silence not reflected in transcript timing
- Semantic hook scoring requires sentence-transformers; unavailable in default packaging
- AI plan is attached to `result_json` for logging but does not yet drive render segment ordering

---

## Missing AI Capabilities

The system currently lacks higher-level semantic and planning intelligence.

### Missing Semantic AI
- Semantic hook understanding
- Context-aware clip understanding
- Emotion understanding
- Semantic pacing analysis

### Missing Editing Intelligence
- AI edit planning
- Story structure analysis
- Narrative pacing
- Dynamic camera behavior planning
- Dynamic subtitle emphasis

### Missing Learning Systems
- RAG memory
- Similar successful output retrieval
- Render memory persistence
- Cross-render learning
- Market-specific learning

### Missing Audio Intelligence
- Beat-aware editing
- BPM-aware pacing
- Music-aware transitions
- Emotion-aware rhythm planning

---

## AI Upgrade Principles

The AI system must follow these architectural rules:

### Principle 1 — AI Creates Plans
AI modules generate:
- edit plans
- recommendations
- scores
- behaviors

AI modules do NOT directly render video.

### Principle 2 — Existing Pipeline Remains Executor
The existing render pipeline remains:
- authoritative
- stable
- fallback-safe

AI layers must remain optional.

### Principle 3 — Local AI First
Prefer:
- local inference
- offline AI
- free/open-source AI

Avoid:
- mandatory cloud APIs
- mandatory subscriptions
- cloud-dependent rendering

### Principle 4 — Incremental Upgrades
AI features must:
- integrate gradually
- preserve compatibility
- avoid rewrite-style refactors

### Principle 5 — Fallback Safety
If any AI system fails:
- render pipeline must continue
- existing render behavior must remain functional

---

# I. AI Dependency Strategy

## Approved Optional AI Libraries

| Library | Purpose |
|---|---|
| faster-whisper | Subtitle transcription |
| sentence-transformers | Semantic understanding |
| faiss-cpu | RAG memory retrieval |
| librosa | Beat/BPM analysis |
| mediapipe | Face/body tracking |

---

## Dependency Rules

### All AI Dependencies Must Be Optional

Rules:
- no hard imports at startup
- no mandatory GPU
- no mandatory CUDA
- no mandatory API keys
- no cloud lock-in

### Required Import Pattern

Correct:

```python
try:
    from sentence_transformers import SentenceTransformer
except Exception:
    SentenceTransformer = None

*End of audit. No code was modified. All file:line references are based on direct reads performed during this session.*
