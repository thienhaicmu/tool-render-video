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

## Non-Negotiable Constraints (all S3 phases)

- Creator controls: goal, style, format, clip count, duration preference
- AI is additive, never subtractive to creator decisions
- Every new feature has a `*_ENABLED=0` env gate for full rollback
- Transcript absence must degrade gracefully (never failure)
- No external API changes
- No render pipeline failures
- No clip count changes
