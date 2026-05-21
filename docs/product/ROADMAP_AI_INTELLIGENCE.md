# AI Intelligence Roadmap — S2 Series

Creator-controlled AI editing layer.
AI edits **according to** creator intent. AI never overrides creator intent.

Creator always controls: **goal · style · format · clip count · duration preference**

---

## Completed Foundation

### S1 — Creator Intent Layer ✅
Smart Defaults, Creator DNA suggestions, Editing Autopilot, AI Managed / Manual Override.

### OQ Stack ✅
- OQ-1: faster-whisper / whisperx, subtitle intelligence, premium styles, motion subtitle engine
- OQ-2: AdaptiveDetector, silence scoring, TransNetV2
- OQ-3: MediaPipe full-range, ByteTrack, eye-level framing
- OQ-4: XTTS hybrid, persona routing, SSML humanizer, ducking, DeepFilterNet
- OQ-5.3: CLIP semantic scoring (OpenCLIP ViT-B-32)

---

## S2 — AI Output Upgrade

### S2.1 — Goal-Aware Hook Intelligence ✅ Complete

**Shipped:** `feat(ai): S2.1 Goal-Aware Hook Intelligence` (commit `6fa833a`)

**What shipped:**
- 9-type EN + VI hook taxonomy: curiosity, surprise, warning, authority, problem, story, contrarian, result_first, challenge
- `detect_hook_type(text)` — dominant hook classification
- `get_opening_window_text(chunks, candidate_start)` — scans the candidate's own opening window (fixes long-form content where hooks appear deep in the source)
- `score_hook_intelligence(text, goal)` — additive bonus [0, +20] with goal-aware multipliers
- `HOOK_INTELLIGENCE_ENABLED` env gate for full rollback
- `goal` field added to all 4 AI modes (viral / podcast / storytelling / education)
- `clip_selector`: hook now scored on candidate opening window, not source video head; goal threaded from mode_config
- `segment_builder`: optional `transcript_blocks` + `goal` params; hook bonus injected into `hook_opening_score`; `hook_intelligence_type` field on segment output

**Files affected:**
- `backend/app/ai/analyzers/hook_analyzer.py`
- `backend/app/ai/config/ai_modes.py`
- `backend/app/ai/director/clip_selector.py`
- `backend/app/services/segment_builder.py`

**Regression guarantees:**
- All new params default to `""` / `None` — zero callers broken
- Bonus is strictly additive, clamped `[0, 100]` — no weight rebalanced
- Transcript absent → bonus = 0.0, behavior identical to before S2.1
- `HOOK_INTELLIGENCE_ENABLED=0` disables entirely

---

### S2.2 — Goal-Aware Best Moment Intelligence ✅ Complete

**Shipped:** `feat(ai): S2.2 Goal-Aware Best Moment Intelligence` (commit `6f1e198`)

**What shipped:**
- New `moment_analyzer.py` — scores the full candidate window (not just the opening hook):
  - `get_window_chunks(chunks, start, end)` — time-range chunk filter
  - `score_best_moment(chunks, start, end, goal)` → [0, +20] additive bonus
  - Three components: peak emotion 60%, goal keyword density 25%, emotion arc 15%
  - Peak emotion uses max across chunks (not aggregate) to avoid saturation on long-form content
  - Goal-aware emotion multipliers: surprise/excitement boosted for viral; warning/curiosity for education; etc.
  - Goal-specific keyword sets per goal type (viral/education/podcast/product/storytelling)
  - `BEST_MOMENT_INTELLIGENCE_ENABLED` env gate for full rollback
- `clip_selector`: `score_best_moment` applied as a **separate** additive bonus after the main formula (not blended into density_s); capped at +5 effective contribution (`moment_raw * 0.25`); annotated in reason string when firing
- `segment_builder`: visual-path best-moment bonus using `peak_scene_quality` vs `avg_scene_quality` and OpenCLIP semantic peak; lightly goal-aware multipliers (1.00–1.15 max, never overrides creator intent); applied outside the v3 formula as bounded additive [0, +15]; `peak_scene_quality` and `best_moment_bonus` fields exposed on segment output

**Files affected:**
- `backend/app/ai/analyzers/moment_analyzer.py` (new)
- `backend/app/ai/director/clip_selector.py`
- `backend/app/services/segment_builder.py`

**Regression guarantees:**
- All new imports are try/except guarded — zero runtime failures if module missing
- Text path (clip_selector): max +5 effective influence on final score [0, 100]
- Visual path (segment_builder): max +15 bonus before clamp; never mutates formula weights
- `BEST_MOMENT_INTELLIGENCE_ENABLED=0` disables both paths entirely
- Transcript absent → text path returns 0.0 (graceful degradation)
- No changes to viral_scorer, render_pipeline, external APIs, or clip count logic

---

### S2.3 — Structure-Aware Clip Builder ✅ Complete

**Shipped:** `feat(ai): S2.3 Structure-Aware Clip Builder`

**What shipped:**
- New `structure_analyzer.py` — multi-signal confidence detection of three-phase narrative (opening → development → payoff):
  - `analyze_window_structure(chunks, start, end)` — per-chunk confidence combining phrase markers (0.40), position fit (0.35), transition signals (0.25)
  - `score_structure_coherence(chunks, start, end, goal)` → [0, +20] additive bonus; goal-aware bonuses per level (open_only / open_payoff / full)
  - `find_entry_point(all_chunks, current_idx, goal, min_duration, candidate_end)` → (new_idx, delta); only accepts trim when hook quality improves by >= +10 raw delta
  - Phase vocabulary: EN + VI markers for opening, development, payoff phases
  - `_DETECT_THRESHOLD = 0.50` — marker alone maxes at 0.40, preventing keyword-only false positives
  - `STRUCTURE_INTELLIGENCE_ENABLED` env gate for full rollback
- `clip_selector`: micro-trim BEFORE scoring (required change 3: all signals use final window); structure bonus `structure_raw * 0.15` → max +3 effective contribution; annotated in reason string when firing
- `segment_builder`: `structure_type: "none"` field added to visual-path segment output and `_FALLBACK_FIELDS`

**Files affected:**
- `backend/app/ai/analyzers/structure_analyzer.py` (new)
- `backend/app/ai/director/clip_selector.py`
- `backend/app/services/segment_builder.py`

**Regression guarantees:**
- All new imports try/except guarded — zero runtime failures if module missing
- Text path (clip_selector): max +3 effective influence on final score [0, 100]
- Micro-trim only fires when hook quality improvement >= +10 raw delta and result meets min_duration
- `STRUCTURE_INTELLIGENCE_ENABLED=0` disables structure scoring and entry-point trimming entirely
- Transcript absent → all structure signals return 0.0, segment_builder visual path unaffected
- No changes to clip count logic, render pipeline, or external APIs

---

### S2.4 — Diversity Intelligence ✅ Complete

**Shipped:** `feat(ai): S2.4 Diversity Intelligence` (commit `6ea21ea`)

**What shipped:**
- New `diversity_analyzer.py` — goal-aware multi-clip diversity engine:
  - `build_candidate_context(hook_type, phases, position_ratio)` → diversity context dict
  - `compute_diversity_penalty(candidate_ctx, selected_ctxs, goal, top_score, candidate_score, clip_count)` → [0, 15.0] penalty for selection ordering only
  - Three diversity dimensions: hook_type exact/group match, moment archetype (derived from hook + structure phases), temporal zone (early/mid/late)
  - Hook exact-match penalty halved when clips differ in moment_type — avoids over-penalizing clips sharing hook label but differing in content value (required change 1)
  - Temporal penalty fixed 2.5 pts ≈ 0.95× multiplier effect, within 0.90–0.97 target (required change 2)
  - Quality delta gate: diversity only fires when `top_score - candidate_score ≤ 12` — 95-score duplicate always beats 70-score unique (required change 3)
  - Diversity strength scales with clip_count: 2=0.30, 3=0.55, 4=0.70, 5+=1.00 (required change 4)
  - Goal-aware dimension weights: viral → moment_type priority; education/podcast/storytelling → temporal priority; product → hook_type priority
  - `DIVERSITY_INTELLIGENCE_ENABLED` env gate for full rollback
- `clip_selector`: `_deduplicate()` replaced with `_select_diverse()` — greedy per-round O(n²) selection with diversity-adjusted comparison scores; hook_type + phases stored on candidates for context; original scores never mutated in output
- `segment_builder`: `_select_non_overlapping()` extended with `goal` + `total_duration` params; diversity-adjusted ordering using `hook_intelligence_type` (already computed by S2.1); `diversity_penalty` field added to output
- `clip_segment_selector` (Phase 36): greedy per-round selection replaces single-pass greedy; story-segment reason labels mapped to hook_type proxies (hook→story, climax→surprise, payoff→result_first); diversity context tracked per accepted plan

**Files affected:**
- `backend/app/ai/analyzers/diversity_analyzer.py` (new)
- `backend/app/ai/director/clip_selector.py`
- `backend/app/services/segment_builder.py`
- `backend/app/ai/clips/clip_segment_selector.py`

**Regression guarantees:**
- All imports try/except guarded — zero runtime failures if module missing
- Diversity penalty affects selection ordering ONLY — output scores are always original pre-penalty values
- `clip_count = 1` → no-op (count_strength = 0.0)
- `top_score - score > 12` → no penalty (quality gate); high-quality duplicate always beats mediocre unique
- `DIVERSITY_INTELLIGENCE_ENABLED=0` disables entirely across all three selection paths
- Transcript absent → hook_type = "none", moment_type = "unknown", graceful degradation to temporal-only diversity
- No changes to scoring formulas, render pipeline, external APIs, or clip count logic

---

### S2.5 — Retry Intelligence ✅ Complete

**Shipped:** `feat(ai): S2.5 Retry Intelligence`

**What shipped:**
- New `retry_analyzer.py` — single bounded retry engine:
  - `evaluate_selection_confidence(selected_raw)` → float [0, 100] — mirrors `_clip_confidence()` logic on raw selection dicts before plan assembly
  - `should_retry(confidence, clip_count)` → bool — fires only when confidence < 60; clip_count accepted for API consistency
  - `build_retry_config(mode_config, selected_raw, goal, clip_count)` → dict — returns fresh mode_config copy with conservative bounded weight shifts (max multiplier 1.20)
  - Weakness signals detected from reason annotations: `weak_hook` (no "hook=N"), `weak_moment` (no "moment=N"), `weak_structure` (no "structure=N"), `low_diversity` (2+ clips, score spread < 5pts, no structure variety)
  - Strategy shifts: weak_hook → `hook_weight *= 1.15`; weak_moment → `retry_moment_scale = 1.15`; weak_structure → `retry_structure_scale = 1.10`; low_diversity → `retry_diversity_scale = 1.10`
  - clip_count = 1 uses 0.5× aggressiveness on all adjustments
  - `RETRY_INTELLIGENCE_ENABLED` env gate for full rollback
- `clip_selector`: reads `retry_moment_scale`, `retry_structure_scale`, `retry_diversity_scale` from mode_config (default 1.0 = no change); applies to moment bonus, structure bonus, and diversity penalty respectively
- `ai_director._build_plan()`: retry attached post-selection before plan assembly; evaluates first-pass confidence; triggers single retry if below threshold; replaces result only when improvement ≥ +8 confidence; annotates `warnings` with `retry_improved:N` or `retry_no_improvement`; skipped entirely when no transcript (chunks empty)

**Files affected:**
- `backend/app/ai/analyzers/retry_analyzer.py` (new)
- `backend/app/ai/director/clip_selector.py`
- `backend/app/ai/director/ai_director.py`

**Regression guarantees:**
- All retry imports try/except guarded — zero runtime failures if module missing
- Maximum 1 retry, bounded by `should_retry()` returning False on second call (no recursion)
- Retry skipped when transcript absent (chunks empty) — scene fallback path unchanged
- All weight adjustments capped at ×1.20 — never subtracts weight, never disables a dimension
- `RETRY_INTELLIGENCE_ENABLED=0` disables entirely; no path change for existing renders
- Improvement threshold gate: retry result kept only when confidence improves ≥ +8; otherwise original selected_raw preserved
- No changes to clip count logic, render pipeline, camera/subtitle planners, or external APIs

---

### S2.6 — Creator DNA Editing Memory ✅ Complete

**Shipped:** `feat(ai): S2.6 Creator DNA Editing Memory`

**What shipped:**
- New `creator_dna/dna_engine.py` — frontend DNA signal consumer:
  - `apply_creator_dna(mode_config, creator_dna, goal)` → `(evolved_dict, report)` — returns evolved mode_config copy and per-dimension explainability report; never mutates original
  - `_DNA_MIN_CONFIDENCE = 0.55` — dimension must reach this confidence before any influence fires (avoids premature personalization from insufficient behavior history)
  - `suppressed_signals` hard-block: if frontend gated a signal, backend absolutely does not apply it — no soft ignore
  - Influence table: `hook_forward` → `hook_weight ×(1+strength×0.10)` max +10%; `clean_visual` → `speech_density_weight ×(1-strength×0.05)` + `silence_penalty_weight ×(1+strength×0.05)`; `narrative_structure` → `retry_structure_scale ×(1+strength×0.08)` max +8%
  - All adjustments bounded: `[original × 0.90, original × 1.15]`
  - Structured explainability report per applied dimension: `{dimension: {"confidence": float, "effect": "+N%"}}`
  - `CREATOR_DNA_ENABLED` env gate for full rollback
- `ai_director._build_plan()`: DNA blend applied immediately after `get_mode_config()` — correct order: DNA → mode_config → pass 1 → retry evaluation → retry (S2.5 retry sees DNA-adjusted weights naturally)
  - No backend learning: frontend snapshot always wins; decay is natural (new snapshot on next request replaces previous preferences without any backend state)
  - `plan.creator_dna_applied` populated with structured report for downstream explainability
- `edit_plan_schema.AIEditPlan`: `creator_dna_applied` field added (default `{}`) + included in `to_dict()`

**Files affected:**
- `backend/app/ai/creator_dna/dna_engine.py` (new)
- `backend/app/ai/creator_dna/__init__.py` (new)
- `backend/app/ai/director/ai_director.py`
- `backend/app/ai/director/edit_plan_schema.py`

**Regression guarantees:**
- All imports try/except guarded — zero runtime failures if module missing
- `creator_dna` absent or empty → `dna_report = {}`, `mode_config` unchanged, behavior identical to pre-S2.6
- `CREATOR_DNA_ENABLED=0` disables entirely; no path change for existing renders
- No changes to S2.1–S2.5 scorer files, clip_selector scoring formulas, segment_builder, render pipeline, or external APIs
- Confidence below 0.55 → dimension skipped; suppressed signal → dimension hard-blocked
- No clip count changes caused by DNA bias
- `creator_dna_applied: {}` on plan when DNA does not fire — always a safe empty dict

---

## Non-Negotiable Constraints (all S2 phases)

- Creator controls: goal, style, format, clip count, duration preference
- AI is additive, never subtractive to creator decisions
- Every signal is bounded and clamped — no unbounded score inflation
- Every new feature has a `*_ENABLED=0` env gate for full rollback
- Transcript absence must degrade gracefully to 0 bonus (never failure)
- No external API changes
- No render pipeline failures
- No clip count changes caused by scoring changes
