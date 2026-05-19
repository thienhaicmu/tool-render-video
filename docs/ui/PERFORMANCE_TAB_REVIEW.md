# Performance Tab Review — `setInspectorTab('performance')`

**Date:** 2026-05-19
**Type:** Product / Creator Value Review
**Question:** Does this tab help creators make better render decisions, or is it interesting-but-useless telemetry?
**Verdict up front:** The tab is structurally misnamed. It is an export/settings panel that carries one buried diagnostic feature. Most of what is inside is high-value; it just needs to be organized and labeled honestly.

---

## 1. Inventory

The Performance tab contains six distinct surface groups, rendered in DOM order:

### 1A — Quick Start Preset
**File/lines:** [index.html:953](../../backend/static/index.html#L953)

Four preset cards in a 2×2 grid: TikTok/Reels, Podcast Clip, Clean Business, High Quality. One-click applies a full render configuration. Has a sub-label "You can still customize everything."

Backed by `evApplyPreset(name)` which writes to the render state.

### 1B — Market & Target
**File/lines:** [index.html:993](../../backend/static/index.html#L993)

- Target Market selector: US / EU / JP
- Market Tone selector: Clean / Bold / Karaoke
- Three checkboxes: Auto Best Clips, Keyword Highlight, Auto Best Export
- Hook Quality card (`#mvHookCard`) — shows hook_text_score, strength tier, first issue, suggestion
- "Analyze Market" button → POST `/api/viral/score/all` → compares US/EU/JP viral scores
- AI Strategy panel (`#aiux_strategy_panel`) — appears after analysis

The hook quality card is populated by `_mvAnalyzeHook()` ([editor-view.js:3068](../../backend/static/js/editor-view.js#L3068)) — a **pure rule-based JS function** with no backend call.

### 1C — Output Settings
**File/lines:** [index.html:1036](../../backend/static/index.html#L1036)

The largest section. Contains:
- Creator Presets bar (save/load named configs)
- DNA consistency hints
- Steering panel (active keep/avoid clip decisions)
- Quick Strategy Bar: Platform pills (YouTube/TikTok/Reels), Variant toggle, Subtitle pills (Off/Clean/Viral/Karaoke), CTA toggle, Structure bias (Hook/Balanced/Story)
- Advanced (collapsed): Aspect ratio, Output profile (Fast/Balanced/Quality/Best), Min/Max clip duration, Max clips, Expert preset dropdown, CTA config, Title overlay, Subtitle emphasis
- Creator Assets (collapsed within Advanced): Logo, Intro, Outro, Music profile, Brand subtitle

### 1D — Batch Queue
**File/lines:** [index.html:1236](../../backend/static/index.html#L1236)

A drag-and-drop zone for queuing multiple video files for sequential batch processing. Shows a drop target, "Queue All" button, file list after selection.

### 1E — Render Settings (collapsed group, auto-opens on tab activate)
**File/lines:** [index.html:1555](../../backend/static/index.html#L1555)

- Device: Auto (GPU) / CPU only / GPU force
- FPS: 30 / 60
- Transform: None / Slightly Different / Strong Transform
- Reframe Mode: Fast Center Crop / Motion Tracking / Subject Tracking

Auto-expanded via `evSetInspGroupOpen('performance', true)` when the tab is activated ([editor-view.js:2525](../../backend/static/js/editor-view.js#L2525)).

### 1F — Advanced Debug (collapsed group, NOT auto-opened)
**File/lines:** [index.html:1601](../../backend/static/index.html#L1601)

Runtime Diagnostics grid (8 cells, 2 columns):
- FPS (from `PlaybackRuntime.getDiag()`)
- Dropped (dropped frame count)
- TL nodes (all DOM children of `#evTLInner`)
- Clips DOM (`.evTLClip` count)
- Subs DOM (`.evTLSub` count)
- Thumb cache (from `ThumbnailCache._cacheSize()`)
- Wave cache (from `EditorWaveform._cacheSize()`)
- Hover vids (`.clipCard.is-preview-playing` count)

Action buttons: Clear thumbs, Clear waves, Dev overlay.

Quality Controls (checkboxes):
- Hover video previews
- Timeline filmstrip
- Waveform lane

Heavy timeline warning (`edPerfWarning`) fires when `tlNodes > 2000 || clipsDom > 150 || subsDom > 300` — shows amber banner and colors the relevant cells.

Polling engine: `EditorPerformanceRuntime` ([editor-performance-runtime.js](../../backend/static/js/editor-performance-runtime.js)) polls at 1200ms interval when tab is active.

---

## 2. Creator Value Test

| Surface | Actionable? | Decision unlocked | If removed |
|---------|-------------|------------------|------------|
| Quick Start Preset | **A — Actionable** | "I don't know settings, let me pick TikTok" | Creators manually configure each knob — friction goes up for new users |
| Platform pills | **A — Actionable** | Changes reframe, FPS defaults, platform profile for the render | Creators have to navigate to hidden selects |
| Subtitle pills | **A — Actionable** | Visual style of subtitles | Creative choice removed |
| Structure bias pills | **A — Actionable** | Weights clip selection toward hook-heavy vs story-heavy | No hook/story balance control |
| Market selector | **A — Actionable** | Affects viral scoring weights, subtitle tone | Scoring defaults to US always |
| Analyze Market button | **A — Actionable** | Shows which market the content fits — creator can target accordingly | No multi-market comparison |
| Hook Quality card (tier only) | **B — Explanatory** | Tells creator if their hook is "Weak" and why | Creator doesn't know the hook is hurting them |
| Hook Score as a number | **C — Decorative** | A 78 vs 82 means nothing to a creator | Nothing lost |
| Creator Presets | **A — Actionable** | Save and reload full configurations across sessions | Every session starts from scratch |
| Steering panel | **A — Actionable** | Shows what keep/avoid decisions are active, lets creator reset | No way to see accumulated clip guidance |
| Render Settings group | **A — Actionable** | GPU/CPU selection prevents render failures on some hardware | No hardware fallback |
| Transform / Reframe Mode | **A — Actionable** | Controls AI reframing quality and render time | No visual differentiation between clips |
| Quality toggles (filmstrip etc.) | **A — Actionable** | Disable heavy features if editor is slow | No way to diagnose or fix editor lag |
| Heavy timeline warning | **B — Explanatory** | Surfaces the cause of lag contextually | Creator has laggy editor with no explanation |
| FPS / Dropped (playback) | **B — Explanatory** (marginal) | Confirms whether editor is dropping frames | Creator can't confirm lag source |
| TL nodes / Clips DOM / Subs DOM | **C — Decorative** | A creator reads "TL nodes: 1847" and gains nothing | Nothing lost |
| Thumb cache / Wave cache sizes | **C — Decorative** | Numbers without context. Cache buttons below are actionable; the numbers are not | Nothing lost |
| Hover vids count | **C — Decorative** | Shows how many cards are in hover-preview state. Irrelevant to any creator decision | Nothing lost |
| Batch Queue | **A — Actionable** | Power users can queue multiple source files for sequential processing | Must re-setup each run manually |
| Dev overlay button | **C — Decorative** | Dispatches Ctrl+Shift+D — developer-only debug overlay. Meaningless to a creator | Nothing |

---

## 3. Actionable vs Decorative Breakdown

### ACTIONABLE (keep, possibly surface better)
1. Quick Start Presets
2. All Quick Strategy Bar pills (Platform, Variant, Subtitle, CTA, Structure)
3. Market & Target controls
4. Analyze Market
5. Creator Presets (save/load)
6. Steering panel
7. Render Settings group (Device, FPS, Transform, Reframe)
8. Quality toggles (hover preview, filmstrip, waveform)
9. Batch Queue
10. Cache clear buttons

### EXPLANATORY (keep as-is or improve labels)
1. Hook Quality card — strong/weak tier + one-line issue is good. The number is redundant.
2. Heavy timeline warning — the warning text and amber highlight are correct and honest
3. FPS / Dropped — useful context if the creator is actively editing and experiencing lag

### DECORATIVE (remove or demote)
1. Hook Score number (the tier is sufficient)
2. TL nodes count
3. Clips DOM count
4. Subs DOM count
5. Thumb cache / Wave cache raw sizes (the clear buttons are the value, not the numbers)
6. Hover vids count
7. Dev overlay button

---

## 4. Signal Quality Audit

### Hook Text Score (0–100)
**Source:** `_mvAnalyzeHook()` at [editor-view.js:3068](../../backend/static/js/editor-view.js#L3068) — pure rule-based JS, no backend call.

The function awards points for: strong action verbs, question patterns, emotion words, curiosity phrases, specificity, length range. Each has a fixed integer weight. Score is capped at 100.

**Signal quality: WEAK PRECISION.** The difference between 74 and 81 is one extra emotion word. Presenting this as a number implies calibrated measurement. It isn't — it's a checklist with weights. The tier labels (`strong` / `medium` / `weak`) are the honest output. The number overclaims.

**Duplicate definition problem:** There are TWO different `_mvAnalyzeHook` function definitions in [editor-view.js](../../backend/static/js/editor-view.js) — one at line 3068 (local heuristic) and one at line 3393 (wraps `mvGenerateHookVariants`). The second shadows the first in the call stack. The caller at line 3147 reaches the second. This means the hook quality card is actually showing the score of the best AI-generated variant, not of the original text. This is a silent accuracy problem — the displayed score may not match the creator's actual hook.

### Market Viral Score (0–100 per market)
**Source:** POST `/api/viral/score/all` → `viral_scoring.py` → integer 0–100 per market.

This is backend-scored with a rule-based formula (see `viral_scoring.py:701`). The formula uses keywords, readability, hook patterns, market-specific weights.

**Signal quality: MODERATE.** The directional comparison (US: 71, EU: 24, JP: 21) is meaningful — a large spread tells the creator "this content is US-native, don't target JP." A small spread (US: 54, EU: 49, JP: 48) should mean "content is market-neutral" but will look like random noise to a creator. Numbers without a confidence range or spread interpretation are semi-honest.

The tier labels (`hot` / `warm` / `normal` / `weak`) from `get_tier()` in `viral_scoring.py` are the honest layer. The raw number adds false precision.

### Render FPS / Dropped Frames
**Source:** `PlaybackRuntime.getDiag()` — measures actual playback frame intervals in real-time.

**Signal quality: GOOD.** These are genuine measurements. The limitation is context: they only update during active playback, and "—" (no playback active) is the most common state a creator will see.

### Timeline / DOM Counts
**Source:** `document.querySelectorAll('*')` on `#evTLInner`, `.evTLClip`, `.evTLSub`.

**Signal quality: GOOD FOR DEVELOPER, MEANINGLESS FOR CREATOR.** These are accurate counts. The warning thresholds (>2000 nodes, >150 clips, >300 subs) are calibrated. The numbers themselves have zero creator interpretability.

### Cache Sizes
**Source:** `ThumbnailCache._cacheSize()`, `EditorWaveform._cacheSize()` — return internal size estimates.

**Signal quality: APPROXIMATE.** Useful for gauging memory pressure before clearing. A creator looking at "Thumb cache: 24MB" gains nothing actionable unless they already know what "Thumb cache" is. The cache clear buttons are the value here.

---

## 5. Trust Review

### Where trust is earned
1. **Heavy timeline warning** — fires on threshold crossing only, shows a specific repair action ("consider reducing clip count or disabling filmstrip/waveform"). Honest and earned.
2. **Quality toggle checkboxes** — direct cause-and-effect. Toggle off filmstrip → filmstrip disappears. No ambiguity.
3. **Platform pills** — creator picks TikTok, system configures for TikTok. Transparent.
4. **Market Analysis** — the comparison across US/EU/JP is transparent about what it's doing ("Analyze Market" button, explicit scores shown). Creator understands it's a scoring preview.

### Where false confidence is created

**Issue 1 — Hook Score as number**
`hook_text_score: 83` reads like a calibrated AI measurement. It is word pattern matching. A creator might decline to change a weak hook because "it's already 83" — missing that the metric has no calibration.

Severity: Medium. Creator impact: Could prevent useful hook iteration.

**Issue 2 — Duplicate `_mvAnalyzeHook` functions**
The hook score displayed in the card may come from the best AI-generated variant rather than the creator's actual hook text. If the creator has NOT applied any AI hook suggestion, the displayed score might reflect a suggestion they didn't choose. This creates a silent accuracy gap.

Severity: High. Creator impact: Hook quality feedback may be for the wrong text. Creator optimizes against a phantom.

**Issue 3 — Market viral numbers without spread context**
`US: 71` with no confidence range. On low-quality or ambiguous subtitle text, the scores are unreliable but displayed with the same precision as high-quality analysis.

Severity: Low. The directional comparison still holds. Creator rarely acts on the absolute number.

**Issue 4 — Advanced Debug metrics visible to creator**
"TL nodes: 1847" in a styled metrics grid creates an impression that this is meaningful to the creator. It is not. The risk is that a creator sees low numbers (TL nodes: 347) and feels reassured about editor performance — when the actual bottleneck might be something else entirely (e.g., unrelated CSS repaint).

Severity: Low. Most creators never open "Advanced Debug."

---

## 6. RC2 Creator Reality Check

**C1 (power user, experienced):**
Would open Performance tab intentionally. Would use:
- Market & Target + Analyze Market (high value)
- Platform/Subtitle/Variant pills (daily use)
- Creator Presets (saves time)
- Render Settings (GPU/CPU selection when a job fails)

Would NOT use: Advanced Debug (doesn't know it's there; if they found it, would read the FPS and ignore TL nodes).

Would be confused by: The tab name "Performance" when they want "Export" settings.

**C2 (typical creator, weekly user):**
Would use Quick Start Preset (first few sessions). After that: Platform pills, Subtitle style, occasionally Market analysis. Would skip Batch Queue, never open Advanced Debug. Would not understand hook score number but might trust it.

Highest risk: Hook score false confidence. If the rule-based hook scorer gives 79 to a weak hook because it contains strong verbs, this creator stops iterating on the hook.

**C3 (first-time user):**
Clicks "TikTok / Reels" preset. Satisfied. Exits tab. Never returns unless things break.

Sees "Performance" tab label in the future and thinks it will show analytics about their videos' performance on social media. Is disappointed.

**Would they skip entirely?**
All three personas would skip the Advanced Debug section. C2 and C3 would skip Market & Target on first use (it looks intimidating — 🌍 with market codes and an Analyze button). The Steering Panel is invisible to anyone who hasn't used keep/avoid clip decisions (it's hidden by default).

---

## 7. Runtime Cost

### Polling — `EditorPerformanceRuntime._startPoll()`
**Interval:** 1200ms  
**Active only when:** Performance tab is open (`onTabActivate` / `onTabDeactivate` guard)  
**Cost per tick:**
1. `document.getElementById('evTLInner').querySelectorAll('*').length` — **expensive**. This is a full DOM subtree traversal. On a project with 100 clips × 12 timeline elements each = 1200 nodes, this forces a layout query every 1.2 seconds. On 200 clips: ~2400 nodes queried.
2. `document.querySelectorAll('.evTLClip')` — global class scan, O(total DOM)
3. `document.querySelectorAll('.evTLSub')` — same
4. `document.querySelectorAll('.clipCard.is-preview-playing')` — same

Then a DOM write pass (8 textContent updates).

**The irony:** The performance monitoring tab introduces measurable performance overhead. The `querySelectorAll('*')` is the worst offender — it touches every node in the timeline subtree, forces layout flush, and runs 50 times per minute.

**Severity:** Medium. The guard (`_isActive`) prevents it from running in the background. But a creator who leaves the Performance tab open while editing gets continuous polling overhead.

### Memory
The poll does not accumulate memory (no arrays, no cache). The `_quality` flags object is tiny. Not a concern.

### DOM writes
8 `textContent` updates per poll. Cheap individually, but they trigger MutationObserver callbacks if any are listening. Negligible.

### Market Analysis
POST `/api/viral/score/all` is a one-shot request on button press. Not polling. No concern.

### Hook quality update
`mvUpdateHookQuality()` calls `_mvAnalyzeHook()` which is pure JS string processing. Runs on subtitle change and tab switch. O(text length) — fast.

---

## 8. Per-Issue Findings

### Issue P1 — Tab name misleads creators
**Severity:** Medium  
**Creator impact:** Creators opening "Performance" expect analytics (how are my clips doing?) or speed diagnostics (why is the editor slow?). They find export settings. This creates disorientation and reduces tab discoverability.  
**Minimal fix:** Rename tab from "Performance" to "Export" or "Output". Update `data-active-insp-title` and the tab button label in HTML/CSS. No logic change needed.  
**Risk:** Low. Tab name change is cosmetic. No functional dependency on the name.

### Issue P2 — Hook Score number overclaims signal quality
**Severity:** Medium  
**Creator impact:** "Hook Score: 83" from rule-based pattern matching looks authoritative. Creator may stop iterating on a weak hook that scores high on word patterns.  
**Minimal fix:** Remove the raw number from `#mvHookScore` display or show it de-emphasized (smaller, lighter color). The strength tier (Strong/Medium/Weak) + one-line issue + suggestion is the honest layer. The number can remain for tooltip/developers only.  
**Risk:** Low. The tier and issue text are already rendered. Removing/de-emphasizing the number is a CSS or template change.

### Issue P3 — Duplicate `_mvAnalyzeHook` function definitions
**Severity:** High  
**Creator impact:** The second definition (line 3393) shadows the first (line 3068). The hook quality card may score the best AI variant, not the creator's actual hook. Creator sees "Strong" for text they didn't write.  
**Minimal fix:** Identify which definition is intentional. The first (line 3068) is the direct rule analyzer. The second (line 3393) wraps `mvGenerateHookVariants`. If the hook card should score the original text, the call at line 3147 should explicitly use the first definition (via a renamed function or by checking whether variants have been applied).  
**Risk:** Medium. Changing which function `mvUpdateHookQuality` calls may change the displayed score. Needs regression test on the hook card output.

### Issue P4 — Advanced Debug metrics have no creator value
**Severity:** Low (hidden by default)  
**Creator impact:** TL nodes, Clips DOM, Subs DOM, Hover vids are developer metrics with zero creator interpretability. They add visual noise and create an "analytics dashboard" feeling that undermines trust in the real metrics.  
**Minimal fix:** Remove TL nodes, Clips DOM, Subs DOM, Hover vids from the displayed grid. Keep FPS, Dropped, Thumb cache, Wave cache (these have marginal creator relevance — at least "Thumb cache" hints at memory). Move the quality toggles ABOVE the metrics grid so they're the first thing seen in Advanced Debug.  
**Risk:** Low. No functional dependency on these cells being visible. The warning system reads the raw values internally regardless of display.

### Issue P5 — `querySelectorAll('*')` polling is expensive
**Severity:** Medium  
**Creator impact:** A creator keeping the Performance tab open while editing a large project will experience 50+ full DOM traversals per minute on the timeline subtree. On 150+ clips, this creates measurable jank on a mid-range machine.  
**Minimal fix:** Cache the previous `tlNodes` count. Only run `querySelectorAll('*')` if a delta is detected (e.g., observe the timeline container with a MutationObserver counter instead of polling). Or: raise the poll interval to 5000ms (5 seconds) — the diagnostics don't need sub-second precision.  
**Risk:** Low. Poll interval is a single constant in [editor-performance-runtime.js:25](../../backend/static/js/editor-performance-runtime.js#L25). Warning fires on threshold; a 5s interval still catches the warning quickly enough for any meaningful action.

### Issue P6 — Quality toggles buried inside Advanced Debug (collapsed)
**Severity:** High  
**Creator impact:** The three quality toggles (Hover preview, Timeline filmstrip, Waveform lane) are the ONLY directly actionable performance controls — the reason a creator would actually need a "Performance" tab. They are hidden inside "Advanced Debug" > "Quality Controls", three clicks from the surface. A creator who experiences editor lag has no path to these controls.  
**Minimal fix:** Move quality toggles OUT of Advanced Debug into their own visible section, either:
- A "Quality Controls" section directly in the Performance tab (not collapsed), or
- Added to the Render Settings group as a second block

Keep the raw metrics inside Advanced Debug for developers.  
**Risk:** Low. The toggles are independent of the metrics grid. Moving them is a DOM restructure with no logic change.

### Issue P7 — Dev overlay button exposed to creators
**Severity:** Low  
**Creator impact:** "Dev overlay" button dispatches `Ctrl+Shift+D`. A curious creator pressing it gets a developer debug overlay they don't understand and can't turn off without pressing it again. Minor UX confusion.  
**Minimal fix:** Move Dev overlay button behind a `data-dev-only` attribute and hide it in production, or move it entirely outside the standard UI flow (keyboard shortcut only).  
**Risk:** Minimal.

### Issue P8 — Heavy timeline warning unreachable in normal flow
**Severity:** Medium  
**Creator impact:** The `edPerfWarning` CSS is the ONLY proactive diagnostic feature — it tells a creator their timeline is heavy and what to do. But it fires inside "Advanced Debug" (collapsed), so it never reaches a creator's attention even when their editor is struggling.  
**Minimal fix:** When `edPerfWarning` fires, also surface a visible indicator outside the collapsed group — a small amber chip in the Render Settings group header, or an inline banner above the Quality toggles (once moved, see Issue P6).  
**Risk:** Low. An external indicator reading from the same `section.classList.contains('edPerfWarning')` check requires no change to the existing warning logic.

---

## 9. Summary Verdicts

### KEEP (as-is or minor label tweaks)
- Quick Start Presets — high value, immediately actionable
- Quick Strategy Bar pills (Platform, Subtitle, Variant, CTA, Structure) — excellent creator UX
- Market & Target + Analyze Market — real decision support
- Creator Presets bar — power user value
- Steering panel — critical for iterative render workflows
- Render Settings group (Device, FPS, Transform, Reframe)
- Cache clear buttons
- Heavy timeline warning logic (improve visibility — Issue P8)
- Market tier labels (`hot` / `warm` / `normal` / `weak`)

### IMPROVE
1. **Tab name** → "Export" (Issue P1) — zero risk, immediate clarity gain
2. **Hook score** → show tier only, remove or de-emphasize number (Issue P2)
3. **Duplicate `_mvAnalyzeHook`** → resolve which definition owns the hook card (Issue P3) — important correctness fix
4. **Quality toggles** → move above diagnostics to a visible location (Issue P6) — the most creator-facing fix
5. **Heavy timeline warning** → surface outside the collapsed group (Issue P8)
6. **Poll interval** → raise from 1200ms to 5000ms (Issue P5) — reduces jank with no loss of usefulness

### REMOVE / DEMOTE TO DEVELOPER-ONLY
1. TL nodes, Clips DOM, Subs DOM, Hover vids metrics (Issue P4)
2. Dev overlay button from default UI (Issue P7)
3. Hook score raw number (Issue P2, partial)

---

## What "Editor Intelligence" Would Look Like

The tab should answer three questions a creator actually asks:

**1. "What should I render this as?"**
→ Quick Start Presets + Platform pills + Subtitle/Variant/CTA/Structure. Already here. Already good.

**2. "Will this content work on [platform/market]?"**
→ Market Analysis + Hook Quality (tier, not number). Mostly here. Needs signal honesty improvement.

**3. "Why is my editor slow and how do I fix it?"**
→ Quality toggles with a contextual warning when thresholds are crossed. Currently buried. Needs surfacing.

Metrics like "TL nodes: 1847" answer a fourth question ("What is the editor's internal state?") that only a developer asks. Removing them from the creator-facing view would make the tab feel like editorial intelligence rather than a server monitoring dashboard.

---

*Product review only — no code changed.*
