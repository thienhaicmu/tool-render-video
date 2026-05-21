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

### S2.4 — Diversity Intelligence ⬜ Planned

---

### S2.5 — Retry Intelligence ⬜ Planned

---

### S2.6 — Creator DNA Editing Memory ⬜ Planned

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
