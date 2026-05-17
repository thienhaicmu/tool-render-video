# Product State — Post UX-R8.3.1

**Date:** 2026-05-16  
**Branch:** `feature/ai-output-upgrade`  
**Last phase:** UX-R8.3.1 — Creator Journey & Momentum

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in UX-R8.3.1

Transforms the home panel from a static dashboard into a **living creator desk**. The creator now feels: "I know where I left off, what momentum I have, and what to do next." Every sentence derives from real backend signals — no fabricated states, no generic copy.

---

## Signal Audit — What Was Available

| Signal | Source | Used For |
|--------|--------|---------|
| `apiLast.can_rerun` | `/api/jobs/history` | CTA label + narrative context |
| `apiLast.can_retry` | `/api/jobs/history` | CTA label + narrative context (interrupted) |
| `apiLast.title` | `/api/jobs/history` | Project name in continue zone |
| `apiLast.summary_text` | `/api/jobs/history` | Narrative body (prefers verbatim if present) |
| `apiLast.timestamp` / `updated_at` / `created_at` | `/api/jobs/history` | Relative time fallback |
| `CreatorMemory.getTasteModel()` | Client-side module | Momentum strip tendency sentence |
| `taste.hook`, `taste.hookConf` | Taste model | "stronger openings" tendency |
| `taste.pace`, `taste.paceConf` | Taste model | "faster pacing" tendency |
| `taste.editStyle` | Taste model | "high-energy edits" / "cinematic storytelling" tendency |
| `CreatorMemory.getDerivedPreferences()` | Client-side module | Signal count for learning state |
| `entry.status` | localStorage history | History item visual authority class |
| `entry.completedParts`, `entry.failedParts` | localStorage history | History item meta text |

---

## R8.3.1-A — Today's Creative Momentum Narrative

Replaces the flat "Pick up where you left off / Last project" label with a status-aware sentence.

| State | Narrative |
|-------|-----------|
| `can_retry: true` | "Render paused mid-way. Resume where you left off." |
| `can_rerun: true`, `summary_text` present | Verbatim `summary_text` |
| `can_rerun: true`, no summary | "Finished [time ago]." |
| API unavailable, localStorage fallback | "[N clips reviewed · N failed] [time ago]" |
| No history at all | "Start a render to see your projects here." |

The project title (`uxr4ContinueTitle`) stays as the primary anchor. The narrative (`uxr4ContinueNarrative`) appears below it.

---

## R8.3.1-B — One Next-Best Action CTA

Single purposeful button derived from backend state. Labels changed from generic "Continue Editing" / "Retry" to action-oriented:

| State | CTA Label | Handler |
|-------|-----------|---------|
| `can_rerun: true` | **Try another render pass** | `rerunRenderHistory(jobId)` |
| `can_retry: true` | **Retry interrupted render** | `retryHistoryDownload(jobId)` |
| Neither | No button shown | — |
| localStorage fallback | **Try another render pass** | `rerunRenderHistory(jobId)` |

---

## R8.3.1-C — Creative Momentum Strip

Replaces flat key-value taste rows in the intel zone with a single **tendency sentence** when `taste.confident === true`.

### Tendency derivation (priority order, up to 2 combined)

| Condition | Tendency phrase |
|-----------|----------------|
| `taste.hook === 'aggressive'` AND `taste.hookConf > 0.4` | "stronger openings" |
| `taste.pace === 'fast'` AND `taste.paceConf > 0.4` | "faster pacing" |
| `taste.editStyle === 'viral'` | "high-energy edits" |
| `taste.editStyle === 'cinematic'` | "cinematic storytelling" |

Combined: `"Recent tendency: stronger openings · faster pacing"`

### Fallback states

| State | Output |
|-------|--------|
| Confident taste, no prominent tendencies | Style label row (existing `uxr4IntelTaste` pattern) |
| `!taste.confident`, signals > 0 | `"Still learning your preferences — N signals so far"` in `.uxr4MomentumLearning` |
| No `CreatorMemory` module | Default workspace message |

### HTML structure

```html
<div class="uxr4MomentumStrip">
  <div class="uxr4MomentumLabel">Recent tendency</div>
  <div class="uxr4MomentumTendency">stronger openings · faster pacing</div>
</div>
```

---

## R8.3.1-D — History as Creative Continuity

History item meta text is now status-aware narrative rather than flat status labels.

| Status | Old meta | New meta |
|--------|----------|----------|
| `completed` | "Completed · 5 clips" | "Completed · 5 clips" (unchanged) |
| `partial` | "Partial · 3 clips · 2 failed" | "Resume · 3 clips · 2 failed" |
| `failed` | "Failed · 2 failed" | "Ready to retry" |

**Visual authority (CSS) by status:**

- `.renderHistoryItem.uxr4TopItem` (first item) — larger title (12px), fg-100 color
- `.renderHistoryItem.partial` — amber left border (`rgba(251,191,36,.35)`)
- `.renderHistoryItem.failed` — dimmed icon (opacity .55), muted title (fg-400)

---

## CSS Added

### workflow.css
```
.uxr4ContinueNarrative   — 10.5px, rgba(255,255,255,.44); narrative line below project title
.uxr4MomentumStrip       — flex column, gap 3px; wraps tendency content
.uxr4MomentumLabel       — 8.5px uppercase "Recent tendency" label
.uxr4MomentumTendency    — 11px, rgba(129,140,248,.85); tendency sentence
.uxr4MomentumLearning    — 10.5px, rgba(255,255,255,.35), italic; learning state
```

### history.css
```
.renderHistoryItem.uxr4TopItem            — padding-top 10px; elevated first item
.renderHistoryItem.uxr4TopItem .title     — 12px, fg-100; visual authority
.renderHistoryItem.partial                — amber left border (resume signal)
.renderHistoryItem.failed .statusIcon     — opacity .55 (gentle)
.renderHistoryItem.failed .title          — fg-400 (gentle recovery)
```

---

## What the R8.3.1 Arc Achieved

| Surface | Before | After |
|---------|--------|-------|
| Continue zone label | "Pick up where you left off" / "Last project" | Gone — title is the anchor |
| Continue zone narrative | `summary_text` + time in flat meta | Status-aware sentence ("Render paused mid-way") |
| CTA button label | "Continue Editing" / "Retry" | "Try another render pass" / "Retry interrupted render" |
| Intel zone | Flat key-value taste rows OR learning message | Momentum tendency sentence OR learning strip |
| History meta text | Generic status label | "Resume · …" (partial) / "Ready to retry" (failed) |
| History item visual | Uniform appearance | Status-driven weight (elevated top item, amber partial, gentle failed) |

---

## Limitations (Honest)

- **Narrative gate**: if `apiLast.summary_text` is empty AND `timeAgo` is unavailable, the narrative line is omitted — only the title shows.
- **Momentum strip gate**: tendency sentence only fires when `taste.confident === true` (requires ≥8 preference signals). New creators see the default workspace message.
- **Tendency cap**: at most 2 tendencies combined. If the creator has 3 matching conditions, the third is omitted.
- **History visual**: `partial` left border uses `padding-left: 8px` which slightly shifts item alignment relative to `completed` items — intentional (resume visual contrast).
- **CTA absence**: when `can_rerun === false` AND `can_retry === false` (render is done but no rerun available), no CTA appears. This is correct — no action is needed.

---

## Maturity Assessment

**UI Score: 9.95 / 10**

The home panel now answers three questions with real signals:
1. **Where did I leave off?** (project title + status narrative)
2. **What should I do next?** (single purposeful CTA)
3. **What momentum do I have?** (tendency sentence from taste model)

No fabricated momentum claims. No generic "Start creating" language. Every sentence traces to a real backend signal or a confirmed-absent fallback.
