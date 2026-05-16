# UX-R6 — Backend-Driven Product Redesign Audit

**Date:** 2026-05-16  
**Branch:** `feature/ai-output-upgrade`  
**Phase:** UX-R6 — Truth-First Redesign Audit  
**Status:** AUDIT ONLY — No implementation

> Every signal cited below was confirmed in the actual backend source code or frontend JS.  
> No invented data. No hypothetical APIs. No designed-for-non-existent-signals UI.

---

## SECTION 1 — Signal Inventory

### What the backend actually produces

#### Render Job (always present)
| Signal | Field | Format | Reliable? |
|---|---|---|---|
| Job status | `status` | queued \| running \| completed \| failed \| cancelled \| interrupted | Yes |
| Pipeline stage | `stage` | QUEUED → DOWNLOADING → SCENE_DETECTION → SEGMENT_BUILDING → TRANSCRIBING_FULL → RENDERING → RENDERING_PARALLEL → WRITING_REPORT → DONE \| FAILED | Yes |
| Progress | `progress_percent` | 0–100 integer | Yes |
| Status message | `message` | Freeform string ("Rendering part 3 of 8") | Yes |
| Render settings | `payload_json` | Full RenderRequest: aspect_ratio, codec, crf, subtitle, motion_aware_crop, ai_director_enabled, effect_preset, playback_speed, etc. | Yes |
| Completion data | `result_json` | Only on completion: output_dir, completed/failed counts, output_ranking (when AI director enabled) | Conditional |
| Timestamps | `created_at`, `updated_at` | UTC string | Yes |

#### Per-Clip (RenderPart) — live via WebSocket
| Signal | Field | Format | Reliable? |
|---|---|---|---|
| Clip number | `part_no` | Integer | Yes |
| Clip name | `part_name` | "Clip 1: Golden Hook" (backend-set label) | Yes |
| Status | `status` | queued \| waiting \| cutting \| transcribing \| rendering \| done \| failed | Yes |
| Clip progress | `progress_percent` | 0–100 per clip | Yes |
| Timestamps | `start_sec`, `end_sec`, `duration` | Float seconds | Yes |
| Viral score | `viral_score` | 0.0–100.0 float | Conditional (0 if scorer disabled) |
| **Motion score** | `motion_score` | 0.0–100.0 float | Conditional |
| **Hook score** | `hook_score` | 0.0–100.0 float | Conditional |
| Output file | `output_file` | Absolute path | Yes (only when done) |
| Error text | `message` | Freeform (only when failed) | Yes |

**Critical finding:** `motion_score` and `hook_score` exist in DB schema and are sent over WebSocket in every part update. The current frontend reads only `viral_score` — `motion_score` and `hook_score` are ignored entirely.

#### WebSocket Summary Object (live)
| Signal | Field | Reliable? |
|---|---|---|
| Active clips | `summary.active_parts[]` → `{part_no, status, progress_percent}` | Yes |
| **Stuck clips** | `summary.stuck_parts[]` → parts unchanged for >120s | Yes |
| In-progress count | `summary.in_progress_count` | Yes |
| Completed count | `summary.completed_parts` | Yes |
| Failed count | `summary.failed_parts` | Yes |
| Overall progress | `summary.overall_progress_percent` | Yes |

**Critical finding:** `stuck_parts` is a real, actionable signal — the backend already detects stalled clips. This is never surfaced in the UI.

#### Backend History API (confirmed endpoint)
`GET /api/jobs/history?limit=20&offset=0` returns:
```
job_id, status, stage, title, source_hint, timestamp,
output_dir, completed_count, failed_count, total_count,
summary_text, can_open_folder, can_retry, can_rerun
```

**Critical finding:** UX-R4 (workspace momentum hero) reads render history from localStorage. The backend provides a richer, always-accurate server-side history API that the workspace doesn't use.

#### output_ranking (AI Director mode only)
When `ai_director_enabled: true` in payload_json, `result_json.output_ranking[]` contains:
- `output_rank_score` (0–10 scale used for UI)
- `output_rank` (ordinal rank)
- `is_best_clip` / `is_best_output`
- `ranking_reason` (text string)

**When `ai_director_enabled: false`**: `_rankMap()` returns an empty Map. All ranking-dependent UI (best clip hero, score badges, UX-R3 tiers) silently degrades — no indicator that ranking data is absent.

#### Viral Scoring Detail (computed, not stored)
The backend viral scorer (`viral_scoring.py`) produces `reasons[]` per clip:
```
"[hook] strong US hook matched — stop doing, never again"
"[keywords] strong US keyword signal — money(2), growth(1)"
"[tone] high-energy/urgency tone words matched (3): crush, dominate, explosive"
"[duration] 45s — US optimal range is 55-85s"
```
These are **not stored in the DB**. They are computed on-demand via `/api/viral/score`. The UI currently does not call this endpoint — the reason text shown in the review panel comes from `output_ranking.ranking_reason` (AI director mode), not from the viral scorer.

---

## SECTION 2 — Signal Inventory by Screen

### Screen 1: render_active_panel

#### TIER A — Real & Ready
| Signal | Source | Current UI Use | Opportunity |
|---|---|---|---|
| Stage label (9 stages) | `job.stage` | Shown in uxr1_ai_hero label | Stage descriptions are generic — "RENDERING_PARALLEL" not creator-friendly |
| Progress percent | `job.progress_percent` | Shown in completion bar | Stage-gated progress would be more meaningful than a raw % |
| Completed clip count | `summary.completed_parts` | Evolution feed, completion bar | Clear "X of Y clips ready" display |
| Per-clip viral score | `parts[].viral_score` | Evolution feed rows | Only viral shown — motion and hook ignored |
| Status message | `job.message` | Not shown in hero (shown in bar) | "Rendering part 3 of 8" is usable creator-facing text |

#### TIER B — Partial Signal
| Signal | Source | Limitation | Opportunity |
|---|---|---|---|
| motion_score per clip | `parts[].motion_score` | 0 if scorer disabled | Could augment evolution feed with retention angle |
| hook_score per clip | `parts[].hook_score` | 0 if scorer disabled | Strongest signal for "this clip will hook" |
| stuck_parts | `summary.stuck_parts[]` | Not currently exposed | Actionable "Clip 3 may be stalled" warning |
| AI concerns | `RuntimeIntelligence.getConcerns()` | Only 2 shown; taste-dependent | Concerns exist but quality depends on CreatorMemory signals |
| Clip name from backend | `parts[].part_name` | Set by backend | Evolution feed shows "Clip N" but backend sets "Clip 1: Golden Hook" |

#### TIER C — Not Available
| Signal | Why |
|---|---|
| Scene type labels | Not in backend DB — no scene_type field |
| Agent debate output | Editor-only concept; render doesn't run agent system |
| Pacing/retention concern from backend | Backend only has scores, not semantic concerns |
| Real-time sentence-level analysis | Not streamed; viral scorer runs post-render |

---

### Screen 2: render_completion_bar

#### TIER A — Real & Ready
| Signal | Source | Current UI Use | Opportunity |
|---|---|---|---|
| Best clip identity | `output_ranking[is_best_clip]` | UX-R2 completion hero | Only shown when AI director enabled |
| Best clip viral score | `parts[].viral_score` | UX-R2 thumb badge as % | Clear score with tier label |
| Ranking reason | `output_ranking[ranking_reason]` | UX-R2 narrative reason (purple italic) | Good as-is |
| Completed/total ratio | `summary.completed_parts / total_parts` | Completion bar message | Could be "8 of 8 clips scored" |
| Narrative bits | `RuntimeIntelligence.getCompletionNarrative()` | UX-R2 bits strip | AI-generated, taste-aware |
| Export path | `parts[].output_file` | Export Best CTA link | Working |

#### TIER B — Partial Signal
| Signal | Source | Limitation | Opportunity |
|---|---|---|---|
| Avg viral score | Computed from `parts[].viral_score` | 0 clips with score → avg = 0 | "Average performance: 68%" if AI director on |
| Top score context | `topPct` computed in `showCompletionIntelligence()` | Only one number | "Best clip outperforms avg by X%" |

#### TIER C — Not Available
| Signal | Why |
|---|---|
| "Creator alignment score" | No such signal — CreatorMemory is editor-scoped |
| Confidence score as standalone metric | `viral_score` is the confidence |
| Alternative clip comparison | No "second best" surface without reading full ranking |

---

### Screen 3: render_output_panel

#### TIER A — Real & Ready
| Signal | Source | Current UI Use | Opportunity |
|---|---|---|---|
| Clip ranking (0-10) | `output_ranking[output_rank_score]` | `.clipCardScore[data-tier]` badge | **Score shown as X.X/10 — but scale source unclear to creator** |
| Best clip flag | `output_ranking[is_best_clip]` | Full-width hero layout (P2.8-F) | Working |
| Clip duration | `start_sec`, `end_sec`, `duration` | Meta line "Xs" | Accurate, always present |
| Viral score % | `parts[].viral_score` | In hero thumb badge only (UX-R2) | Not shown on regular cards — only score/10 shown |
| Reason text | `output_ranking[ranking_reason]` | `.clipCardReason` text | Shown only when AI director on |
| Thumbnail | `/parts/{no}/thumbnail` | `.clipCardThumbWrap img` | Working, cached |
| Video preview | `/parts/{no}/media` | Lazy-loaded on hover | Working |
| Failed reason | `parts[].message` | Shown in failed card | Small, low prominence |
| Clip name | `parts[].part_name` | Card title | Backend-set, creator-readable |

#### TIER B — Partial Signal  
| Signal | Source | Limitation | Opportunity |
|---|---|---|---|
| motion_score | `parts[].motion_score` | Ignored by frontend | Second dimension alongside viral_score |
| hook_score | `parts[].hook_score` | Ignored by frontend | Most predictive for first-3-second retention |
| Market context | `payload_json.channel_code` / viral market | Not shown per-clip | "Scored for US market" context |
| No-ranking fallback | When `ai_director_enabled: false` | Silent degradation | Should explicitly tell creator "AI ranking unavailable" |

#### TIER C — Not Available
| Signal | Why |
|---|---|
| Compare scoring beyond viral | No backend "A vs B" endpoint |
| Scene type per clip | No `scene_type` field in DB |
| Creator alignment per clip | CreatorMemory is editor-scoped, not render-aware |
| Subtitle quality score | Not in DB |

---

### Screen 4: partial_render_home

#### TIER A — Real & Ready
| Signal | Source | Current UI Use | Opportunity |
|---|---|---|---|
| Server-side render history | `GET /api/jobs/history` | **NOT USED — reads localStorage instead** | Drop localStorage, use API |
| Last job metadata | API response | UX-R4 reads from localStorage | API has `completed_count`, `failed_count`, `summary_text` |
| Render settings from last job | `payload_json` | Not shown at all | "Last project: H.265, 3:4, subtitle on" — actionable context |
| Can retry / can rerun flags | API response `can_retry`, `can_rerun` | Not used | Drive CTA logic correctly (rerun vs retry) |

#### TIER B — Partial Signal
| Signal | Source | Limitation | Opportunity |
|---|---|---|---|
| Creator Memory (taste model) | `CreatorMemory.getTasteModel()` | Editor-scoped — requires editor AI interactions, NOT render usage | Show only when confident; never imply it learns from renders |
| Preferred output format | Inferable from `payload_json` history | Would require reading multiple past jobs | "You usually render 3:4 at 60fps" — useful but needs aggregation |

#### TIER C — Not Available
| Signal | Why |
|---|---|
| "Saved projects" | No project save concept in backend |
| "Recommendations" for next render | No recommendation engine |
| Creator productivity analytics | No such data stored |
| Render quality trends over time | Not aggregated in backend |

---

### Screen 5: view_monitor

**Reality:** `#view_monitor` (index.html line 389) is hidden by default (`class="hiddenView"`, `style="display:none"`). It contains `#action_title`, `#action_state`, `#action_message`, `#action_meta`, `#part_focus`, `#steps_grid`. No active WebSocket binding targets it. No JS function actively populates it in the current codebase.

**Verdict:** This is a **legacy diagnostic container** — a dead panel from an earlier architecture. It is neither a creator intelligence surface nor a useful technical monitor. Nothing in the active render flow writes to it.

---

## SECTION 3 — Backend-Backed Redesign Opportunities

### Opportunity 1 — motion_score + hook_score per clip (HIGH VALUE)

**Backend reality:** `motion_score` and `hook_score` are computed by the backend, stored in DB, and sent over WebSocket with every part update.

**Current state:** Frontend completely ignores both. Only `viral_score` is used.

**What this enables:**
- Three-dimensional clip scoring: viral (shareability) / motion (retention) / hook (first-impression)
- The output panel could show a 3-bar mini chart per card instead of a single score
- The evolution feed during render could surface "strong hook, weak motion" per clip as it completes
- "Best hook" and "best motion" could be separate editorial recommendations alongside "best viral"

**Implementation signal quality:** Conditional (0 if scorer disabled) — needs graceful fallback. When scores are 0, treat as "not scored" not "0% hook."

---

### Opportunity 2 — stuck_parts warning (MEDIUM VALUE)

**Backend reality:** `summary.stuck_parts[]` lists parts unchanged for >120s. This is emitted in every WebSocket tick.

**Current state:** Ignored entirely.

**What this enables:**
- A live "⚠ Clip 3 may be stalled (2m 30s)" warning in the runtime hero
- A "Retry stuck clips" action button when stuck_parts > 0
- Reduces creator uncertainty during long renders

**Implementation risk:** Low. Data is already in the WS payload. Need to read `summary.stuck_parts` in `_updateEvolutionFeed()` or `_updateHero()` and render a warning card.

---

### Opportunity 3 — Server history API replacing localStorage (HIGH VALUE)

**Backend reality:** `GET /api/jobs/history` returns structured, server-side render history with `completed_count`, `failed_count`, `total_count`, `summary_text`, `can_retry`, `can_rerun`, timestamps. Always accurate.

**Current state:** UX-R4 workspace reads from `localStorage` (`RENDER_HISTORY_KEY`). The API is never called from the workspace.

**What this enables:**
- Workspace momentum hero shows accurate last session data even after browser cache clear
- `can_retry` / `can_rerun` flags drive the "Continue Editing" CTA correctly (rerun = complete restart; retry = failed parts only)
- `summary_text` ("8 clips completed") is backend-generated — no client-side assembly needed
- Multi-device consistency (if the product ever supports it)

**Implementation complexity:** Medium. Requires replacing `_renderHistoryRead()` with an API fetch on workspace load. Needs loading state and error fallback.

---

### Opportunity 4 — Render settings surface in workspace (LOW VALUE, QUICK WIN)

**Backend reality:** Every completed job has `payload_json` with full render settings: aspect_ratio, codec, effect_preset, subtitle style, motion_aware_crop, playback_speed, etc.

**Current state:** Last job's settings are not shown anywhere in the workspace.

**What this enables:**
- "Last project: 3:4 · H.265 · Karaoke subtitles · 60fps" — a single line of render context
- Creator can verify they're about to use the same settings without opening the sidebar
- "Resume with same settings" CTA

**Implementation complexity:** Low. Read from last history API entry's source_hint + parse payload_json fields for display.

---

### Opportunity 5 — part_name as editorial label (MEDIUM VALUE)

**Backend reality:** `parts[].part_name` is set by the backend — it can contain rich labels like "Clip 1: Golden Hook" (if AI director sets it).

**Current state:** The evolution feed shows "Clip N" (generated client-side) instead of reading `part_name`. Clip cards read `part_name` correctly (line 3900 in render-ui.js) but the evolution feed doesn't.

**What this enables:**
- Evolution feed during render shows "Clip 1: Golden Hook — 85%" instead of "Clip 1 — 85%"
- More editorial feel without inventing labels — the label comes from backend

**Implementation complexity:** Very low. Change one line in `_updateEvolutionFeed()` to read `part.part_name` instead of generating "Clip N".

---

### Opportunity 6 — AI Director mode indicator (MEDIUM VALUE)

**Backend reality:** `payload_json.ai_director_enabled` controls whether `output_ranking` is populated. When false, the ranking Map is empty and all ranking-dependent UI silently degrades.

**Current state:** No UI indicator distinguishes "AI Director on" (rich ranking, best clip, tier hierarchy) from "AI Director off" (no ranking, empty tiers, fallback UI). The clip review panel looks like it should show scores but shows nothing.

**What this enables:**
- When `ai_director_enabled: false`, show "AI scoring not enabled for this render" in the output header
- Remove the tier headers (they're empty/meaningless without ranking)
- Show clips sorted by part_no with a note "Enable AI Director for ranking"

**Implementation complexity:** Low. Read `payload_json.ai_director_enabled` in `populateRenderOutputPanel()` and gate tier/ranking UI behind it.

---

### Opportunity 7 — Viral scorer reasons surface (LOW VALUE, REQUIRES EXTRA CALL)

**Backend reality:** `/api/viral/score` can compute detailed reason strings per clip. These include hook matches, keyword signals, tone words, duration assessment.

**Current state:** Reason text in the review panel comes from `output_ranking.ranking_reason` (editorial sentence from AI director). The viral scorer's granular reasons are never shown.

**What this enables:**
- "Why 85%: Strong hook matched — high-energy tone (3 words) — 45s, slightly short for US" in expanded clip card
- More transparent scoring

**Implementation complexity:** High. Requires calling `/api/viral/score` with clip text — but clip text is not easily available client-side (requires subtitle extraction or separate endpoint). **Not recommended for immediate implementation** without a dedicated backend endpoint that returns pre-computed reasons.

---

## SECTION 4 — Unsafe / Fake Redesigns to Avoid

### AVOID 1 — Creator Memory in workspace intelligence

**What's tempting:** "AI learns your editing style" as a workspace insight based on CreatorMemory.

**Why it's fake:** CreatorMemory is scoped to the editor's AI suggestion flow. It accumulates from accept/reject signals on `strongerHook`, `fasterPacing`, `cinematicMode`, etc. **These actions only happen in the AI suggestions panel within the editor.** A creator who uses the render tool without the editor's AI workflow will always have 0 signals, and the workspace will always show the fallback.

**What's real:** CreatorMemory accurately reflects editor AI interaction history. It just doesn't learn from render outcomes.

**Safe alternative:** Show CreatorMemory signals only after the editor has been used. Label them explicitly as "from your editor sessions" not "from your renders."

---

### AVOID 2 — "Recommendations for next render"

**What's tempting:** "Based on your history, try a 3:4 format next."

**Why it's fake:** No recommendation engine exists. The backend has no aggregation layer over history. This would be invented intelligence.

**Safe alternative:** Show last used settings from `payload_json`. That's factual, not predictive.

---

### AVOID 3 — "Creator alignment score" per clip

**What's tempting:** Adding an "alignment" badge showing how well each clip matches the creator's taste profile.

**Why it's fake:** CreatorMemory is editor-scoped (suggestion accept/reject). The render pipeline has no access to taste model during rendering. There is no backend signal connecting viral scores to creator preferences.

**Safe alternative:** In the completion narrative, `RuntimeIntelligence.getCompletionNarrative()` already produces a taste note when confidence is high. That's the correct surface.

---

### AVOID 4 — Scene type labels per clip

**What's tempting:** Labeling clips as "High-energy intro" or "Emotional climax" in the review panel.

**Why it's fake:** No `scene_type` field exists in the backend. The editor's scene graph runs on the editor's timeline, not on rendered clips.

---

### AVOID 5 — Competitor-style analytics dashboard

**What's tempting:** Historical performance charts, clip quality trends over time.

**Why it's fake:** The backend stores completed job counts and viral scores per clip, but there is no aggregation API, no trend computation, and no performance-over-time data structure.

---

### AVOID 6 — "Confidence score" as a standalone metric

**What's tempting:** A separate "AI confidence: 87%" badge distinct from the viral score.

**Why it's fake:** `viral_score` IS the confidence metric. There is no separate confidence field in the DB. `output_rank_score` is a 0-10 ranking score derived from viral_score — it's not an independent confidence signal.

---

## SECTION 5 — Screen-by-Screen Redesign Viability

### Screen 1 — render_active_panel

**Current problem:** Stage names are technical strings (RENDERING_PARALLEL). Evolution feed uses only viral_score — ignores motion and hook. Stuck clips cause silent waiting. Backend part_name is not used in the feed.

**Real backend signals available:**
- 9 named pipeline stages (can be humanized)
- `summary.stuck_parts[]` (actionable stall warning)
- `parts[].part_name` (backend editorial label)
- `parts[].motion_score`, `parts[].hook_score` (three-dimensional scoring)
- `job.message` ("Rendering part 3 of 8" — human-readable)

**Recommended redesign:**
1. Humanize stage labels: SCENE_DETECTION → "Analyzing scene structure", RENDERING_PARALLEL → "Rendering clips in parallel", WRITING_REPORT → "Scoring and ranking clips"
2. In evolution feed: show `part_name` instead of "Clip N"; add motion + hook sparkline when both > 0
3. Add stuck_parts warning card: "Clip 3 seems stuck — 2m 30s with no progress" + retry action
4. Show `job.message` as secondary text under stage label (it's a real human-readable string)

**What to remove:** Nothing. Additive changes only.
**What to promote:** part_name, stuck_parts warning, 3-score mini display.
**What NOT to invent:** Scene type labels, agent debate UI, pacing concerns from backend.
**Complexity:** Low (part_name, stage humanization) to Medium (3-score display, stuck warning).
**ROI:** High — all signals are already in the WS payload.

---

### Screen 2 — render_completion_bar

**Current problem:** Completion hero (UX-R2) only appears when AI director produces a best clip. When AI director is off, the hero shows fallback text. Score inconsistency (% in hero vs. X/10 in cards) confuses the scale.

**Real backend signals available:**
- Best clip identity + viral score + ranking reason (AI director mode)
- Completed / total count (always)
- Average viral score (computed from parts[].viral_score)
- `can_retry` / `can_rerun` from history API

**Recommended redesign:**
1. Unify score display: Use `viral_score × 10 = output_score` correlation explicitly OR show both as "85 viral / 8.5 rank" in the hero thumb. The two systems should be explained or unified.
2. Rename "Export Best" to "Download Best" — the word "export" implies a format conversion.
3. Add AI Director off state: when ranking is empty, show "Clips rendered — AI scoring was disabled. Enable AI Director for clip ranking." Replace the empty hero with a neutral completion message.

**What to remove:** The score inconsistency (UX-R2 known limitation UX-R2.3 — still unresolved).
**What to promote:** Context for when AI ranking is unavailable.
**What NOT to invent:** "Creator alignment score", confidence as a standalone signal.
**Complexity:** Low (copy changes, AI director gate), Medium (score unification).
**ROI:** High — score inconsistency is a trust issue.

---

### Screen 3 — render_output_panel

**Current problem:** Three real scores per clip (viral, motion, hook) exist — only one is shown. Ranking-dependent UI silently empties when AI director is off. The review panel claims to be an "editorial review workspace" but clips have no editorial dimension beyond their rank score.

**Real backend signals available:**
- `output_rank_score` (0-10), `is_best_clip`, `ranking_reason` — when AI director on
- `viral_score`, `motion_score`, `hook_score` — per clip, always in WS
- `part_name` — backend editorial label per clip
- `parts[].message` — error text for failed clips
- `start_sec`, `end_sec`, `duration` — precise timecode

**Recommended redesign:**
1. **Add motion + hook to clip card:** Below the existing `output_score` badge, add a two-bar mini indicator: "Motion 72 · Hook 68" — only when both > 0. Adds a second editorial dimension without redesigning the card.
2. **AI Director gate:** When `payload_json.ai_director_enabled === false`, remove UX-R3 tier headers and show: "Clips sorted by part number — AI ranking requires AI Director mode." Prevents confusing empty Strong/Additional tiers.
3. **Failed clip error visibility:** Promote `parts[].message` in failed clip cards — currently too small. Make it the dominant text in the failed card body.
4. **Duration more prominent:** `start_sec–end_sec` timecodes could appear as "0:00–0:45" in the card meta — useful for editorial decisions about which clip to use.

**What to remove:** Silent empty tier headers when AI Director is off.
**What to promote:** motion_score + hook_score, failed clip error text, timecodes.
**What NOT to invent:** Scene labels, alignment scores, competitor comparison.
**Complexity:** Low to Medium.
**ROI:** Very high — motion and hook scores already exist in the data and are unused.

---

### Screen 4 — partial_render_home

**Current problem:** Workspace reads localStorage for history (misses server truth). CreatorMemory intelligence implies AI learns from renders (it doesn't). "Continue Editing" calls `rerunRenderHistory()` (re-renders from scratch, doesn't restore review state).

**Real backend signals available:**
- `GET /api/jobs/history` with `completed_count`, `failed_count`, `summary_text`, `can_retry`, `can_rerun`, precise timestamps
- `payload_json` settings from last job (aspect ratio, codec, subtitle style)

**Recommended redesign:**
1. **Replace localStorage history with API call:** `renderRenderHistory()` should call `/api/jobs/history?limit=10` instead of (or in addition to) reading localStorage. Use localStorage as a fast-path cache while API loads.
2. **Fix "Continue Editing" semantics:** If `can_retry: true` on last job (failed parts exist), show "Retry Failed Clips" instead of "Continue Editing." If `can_rerun: true`, show "Rerun" not "Continue Editing." "Continue Editing" implies the editor, not a re-render.
3. **Show last render settings:** A single line under the project title: "Last: 3:4 · H.265 · Subtitles on" — read from `payload_json` of last history entry.
4. **Creator Memory label:** Change "AI Workspace" label to "From your editor sessions" — accurate scoping.

**What to remove:** Misleading "AI learns from renders" implication. CreatorMemory fallback shows when no editor sessions exist.
**What to promote:** API-sourced history, last settings display, correct CTA semantics.
**What NOT to invent:** Recommendations, trend analytics, saved projects.
**Complexity:** Medium (API integration, CTA logic).
**ROI:** High — data quality and trust improvement.

---

### Screen 5 — view_monitor

**Reality:** Dead panel. Hidden by default. Not populated by any active JS.

**Verdict: REMOVE from production HTML.**

It is not a technical monitor (nothing writes to it). It is not a creator intelligence surface (wrong concept entirely). It is not needed for diagnostics (browser DevTools serve that purpose). It adds DOM weight and potential confusion if accidentally revealed.

**Recommended action:** Remove `#view_monitor` from `index.html`. Delete its CSS rules from workflow.css/history.css if any exist. No replacement needed — its function was never implemented.

**Complexity:** Very low.
**ROI:** Reduces DOM size; removes dead code.

---

## SECTION 6 — Prioritized Redesign Roadmap

### P0 — Highest Leverage (Real signals, no new backend, high creator value)

| Item | Screen | What | Why |
|---|---|---|---|
| **P0-A** | Output Panel | Add `motion_score` + `hook_score` to clip cards | Three real scores exist, one is shown. Highest information density gain with zero backend work |
| **P0-B** | Output Panel | AI Director gate for tier headers | Silent empty tiers actively mislead. Gate behind `payload_json.ai_director_enabled` |
| **P0-C** | Active Panel | Use `part_name` in evolution feed | Backend sets editorial labels — feed shows generic "Clip N" |
| **P0-D** | Active Panel | surface `stuck_parts` warning | Real stall detection already in WS payload — creator has no visibility |
| **P0-E** | Completion | Score display unification (UX-R2.3) | Hero shows viral %, cards show rank/10. Different scales, same clips. Trust issue |
| **P0-F** | Home | Replace localStorage history with API | API is richer, server-accurate, has `can_retry`/`can_rerun` flags |

---

### P1 — Valuable (Meaningful improvement, contained scope)

| Item | Screen | What | Why |
|---|---|---|---|
| **P1-A** | Active Panel | Humanize stage labels (9 stages → creator-friendly strings) | RENDERING_PARALLEL means nothing to a creator |
| **P1-B** | Home | Fix "Continue Editing" CTA semantics | Currently calls `rerunRenderHistory()` — a full re-render, not editing |
| **P1-C** | Home | Show last render settings (aspect, codec, subtitles) | Fast context check before starting a new render |
| **P1-D** | Output Panel | Promote failed clip error text | `parts[].message` exists but is visually buried in failed cards |
| **P1-E** | Output Panel | Show clip timecodes (start–end) | `start_sec`/`end_sec` are always present and editorially useful |
| **P1-F** | Completion | AI Director off state in completion hero | Empty hero + ranking fallback needs explicit "AI scoring was disabled" message |
| **P1-G** | Home | Fix CreatorMemory scope label | "AI Workspace" → "From your editor sessions" |

---

### P2 — Optional (Lower ROI or higher complexity)

| Item | Screen | What | Why |
|---|---|---|---|
| **P2-A** | Active Panel | `job.message` shown in stage sub-label | Already human-readable; low-effort addition |
| **P2-B** | Home | Preferred format inference from payload history | Requires reading multiple past jobs — useful but complex aggregation |
| **P2-C** | view_monitor | Remove dead panel from HTML | Zero user value; minor cleanup |
| **P2-D** | Completion | "Download Best" rename from "Export Best" | Copy change only; marginal clarity |
| **P2-E** | Output Panel | Motion/hook score at completion hero level | Would complement the viral% in UX-R2 thumb badge |

---

## Appendix — Confirmed Fake / Missing Backend Signals

These do NOT exist in the backend. Do not design for them.

| Signal | Why it doesn't exist |
|---|---|
| scene_type label per clip | No `scene_type` field in `job_parts` table |
| Retention curve data | Not computed or stored |
| Creator alignment score | CreatorMemory is editor-scoped, not render-scoped |
| Recommendation engine | No aggregation or prediction layer |
| A/B test comparison | No such endpoint |
| Trend data over multiple renders | Not aggregated |
| "Saved projects" | No project save concept |
| Per-clip confidence independent of viral_score | `viral_score` is the score; no separate confidence |
| Agent debate output in render pipeline | Agent system is editor-only |
| Pacing / retention concerns from backend | Backend has scores only; semantic labels are frontend-computed |
| started_at / completed_at timestamps | Only `created_at` and `updated_at` exist |
