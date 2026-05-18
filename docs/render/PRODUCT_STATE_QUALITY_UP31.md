# PRODUCT STATE — QUALITY-UP31: Series Intelligence

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): series intelligence`
**Status:** Shipped

---

## Summary

Channel consistency phase. Moves from great individual clips to a consistent creator series.

Detects series patterns from render history signals (title similarity, repeated preset, asset pack, time window). Builds a lightweight series fingerprint. Publishes continuity nudges to the steering panel and output trust bar — advisory only, never forced.

**Creator experience:** "My channel feels consistent."

---

## Philosophy

- **Channel consistency, not project management.** No hard projects, no folders, no tagging.
- **Local only.** `creator_series_v1` in localStorage. No backend. No cloud.
- **Soft detection.** Confidence gate prevents nudges from noise or a single divergent render.
- **Gentle only.** Nudges are advisory. Creator choice always wins. No form override.
- **No new dependencies.** Pure JS. Reuses existing: preset · DNA · assets · review queue · steering.
- **No ML.** Weighted counts and EMA over localStorage. Fully inspectable.
- **No creepy language.** "Series style active" not "We detected your series." No scary AI framing.

---

## What Was NOT Built

| Not built | Reason |
|---|---|
| Hard project system | Creator overwhelm. Soft detection is enough. |
| Manual series tagging | No tagging. Signals are inferred automatically. |
| Cloud series memory | Local only. Same philosophy as UP12–UP27. |
| LLM content analysis | No ML. No API calls. Weighted counts only. |
| Thumbnail consistency enforcement | Out of scope. Advisory nudge only. |
| Auto-filling form fields | Creator taste (UP12) + feedback (UP18) already handle defaults. Series is advisory. |
| Backend series model | Frontend only. Series context attached to payload for observability. |

---

## Architecture

### Storage: `creator_series_v1`

```json
{
  "renders": [
    {
      "jobId": "...",
      "name": "Podcast Ep 13",
      "preset_id": "__tutorial_pro",
      "subtitle_style": "story_clean_01",
      "cta_type": "part_2",
      "structure_bias": "story",
      "platform": "youtube_shorts",
      "render_profile": "quality",
      "logo_path": "/path/to/logo.png",
      "intro_path": null,
      "ts": 1748000000000,
      "review_action": "keep"
    }
  ],
  "fingerprint": {
    "confidence": 0.78,
    "series_detected": true,
    "title_prefix": "podcast ep",
    "preset_id": "__tutorial_pro",
    "logo_path": "/path/to/logo.png",
    "subtitle_style": "story_clean_01",
    "cta_type": "part_2",
    "platform": "youtube_shorts",
    "render_profile": "quality",
    "structure_bias": "story",
    "last_seen": 1748000000000,
    "last_computed": 1748000000000,
    "window_size": 8
  }
}
```

Max renders: 50 (FIFO). Time window: 30 days.

---

## Series Detection

### Signal scoring (max 9 points)

| Signal | Points | Condition |
|---|---|---|
| Preset consistency | 2 | Same preset in ≥ 3 recent renders |
| Logo consistency | 2 | Same logo file in ≥ 3 recent renders |
| Intro consistency | 1 | Same intro file in ≥ 3 recent renders |
| Title prefix | 2 | ≥ 3 renders share a common word prefix (e.g. "podcast ep") |
| Platform consistency | 1 | Same platform in ≥ 60% of window renders |
| Review reinforcement | 1 | ≥ 2 keep/favorite actions in window |

```
confidence = min(1.0, signal_score / 9)
series_detected = confidence >= 0.30
```

### Confidence gates

| Gate | Threshold | Effect |
|---|---|---|
| `DETECT_GATE` | 0.35 | Series hint fires in steering panel (cpSeriesHint) |
| `CHIP_GATE` | 0.55 | "Series style" trust chip shows in output trust bar |
| `series_detected` | 0.30 | `series_detected: true` in fingerprint |

### Title prefix algorithm

Normalizes names to lowercase words, strips punctuation. Tries prefix lengths 3→2→1. Returns longest prefix appearing in ≥ 3 renders. Example:
- "Podcast Ep 12", "Podcast Ep 13", "Podcast Ep 14" → prefix "podcast ep"
- "Monday Motivation", "Monday Workout", "Monday Mindset" → prefix "monday"

### Style fingerprint (exponential weighting)

Each style dimension (subtitle_style, cta_type, platform, render_profile, structure_bias) is computed using exponentially weighted counts — newer renders count more (decay α=0.82). Dominant value must:
- Accumulate weight ≥ 0.8 (at least one strong recent signal)
- Beat runner-up by 1.35× (clearly dominant, not noise)

---

## Part A — Series Detection

`CreatorSeries.recordRender(jobId, name, payload)` called when a batch job completes. Extracts style signals from the render payload. Deduplicates by `jobId`. Recomputes fingerprint. Logs `series_confidence` and `series_detected` when applicable.

## Part B — Series Profile (Fingerprint)

Lightweight fingerprint built from windowed render history:
- `title_prefix` — detected series name pattern
- `preset_id` — dominant preset
- `logo_path` — dominant logo file
- `subtitle_style`, `cta_type`, `platform`, `render_profile`, `structure_bias` — weighted style dimensions
- `confidence` — 0.0–1.0

## Part C — Continuity Nudges (Advisory Only)

When `confidence >= DETECT_GATE (0.35)`:
- `cpSeriesHint` text is shown below the preset selector in the editor (same pattern as `cpDnaHint`)
- Example: `Series: "podcast ep"` or `Series style active`

When `confidence >= CHIP_GATE (0.55)`:
- "Series style" chip appears in the output trust bar (same bar as DNA, Platform, Steering chips)

These are purely informational — no form fields are filled, no selections are forced.

## Part D — Review Feedback Loop

`CreatorSeries.recordReviewAction(jobId, action)` called from ReviewQueue:
- `keep` or `favorite` → marks render with review action → next fingerprint recompute counts as reinforcement signal
- `dismiss` → marks render as dismissed (neutral — does not subtract from confidence)

After ≥ 2 keep/favorite actions in the 30-day window: `series_detected` reinforcement signal fires (+1 pt).

## Part E — UI

**Steering panel chip** (`v3ChipSeries`, cyan): "Series" — appears when `cpSeriesHint` is active. Same position as DNA chip.

**Output trust bar chip** (`v3TrustSeries`, cyan): "Series style" or "Series: {prefix}" — appears when `confidence >= 0.55`.

**Hint text** (`cpSeriesHint`): Small italic text below preset selector. Same styling as `cpDnaHint`. Shows when `confidence >= 0.35`.

No "we detected" language. No AI framing. Factual: "Series style active."

## Part F — Local Storage

`creator_series_v1` — lightweight. Only stores:
- Ring buffer of last 50 render signal summaries (no video data, no files, no thumbnails)
- Computed fingerprint (single snapshot)

Not stored: video metadata, timestamps beyond ts, raw payloads, file paths beyond logo/intro.

## Part G — Observability

| Log event | When | Contains |
|---|---|---|
| `series_confidence` | Every render record | `{pct}% window={N}` |
| `series_detected` | When confidence ≥ 0.30 | `prefix="{X}" preset={Y} conf={Z}%` |
| `series_nudge` | When hint text fires in steering panel | hint label |
| `series_suppressed` | Window has renders but conf < DETECT_GATE | `below detect gate ({pct}% < 35%)` |

---

## Files Changed

### New Files

| File | Purpose |
|---|---|
| `backend/static/js/creator-series.js` | `CreatorSeries` IIFE module — full series intelligence |

### Modified Files

| File | Change |
|---|---|
| `backend/static/js/editor-view.js` | `evSyncQsBar()`: series hint update; `v3RefreshSteeringPanel()`: Series chip; payload build: `creator_series`; both init blocks: `CreatorSeries.init()` |
| `backend/static/js/render-ui.js` | Trust bar: `v3TrustSeries` chip when `CreatorSeries.getAppliedChip()` returns non-null |
| `backend/static/js/batch-queue.js` | `_fetchJobStatus`: `CreatorSeries.recordRender()` on `completed` and `completed_with_errors` |
| `backend/static/js/review-queue.js` | `keep()`, `favorite()`, `dismiss()`: `CreatorSeries.recordReviewAction()` |
| `backend/static/index.html` | `cpSeriesHint` div added; `creator-series.js` script tag |
| `backend/static/css/app.css` | `.v3TrustSeries` (output trust bar); `.v3ChipSeries` (steering panel) |

---

## Confidence Thresholds — Design Rationale

| Threshold | Value | Why |
|---|---|---|
| `MIN_RENDERS` | 3 | Minimum data to attempt any detection. 1-2 renders are not a pattern. |
| `DETECT_GATE` | 0.35 | ~3/9 signal score. Requires at least 2 strong signals (preset+logo OR title+platform) before any hint. |
| `CHIP_GATE` | 0.55 | ~5/9 signals. Trust bar chip is more visible — higher bar. |
| `series_detected` | 0.30 | Log-only threshold. Slightly lower than DETECT_GATE so detection is logged before nudges fire. |

---

## Manual QA Checklist

### A — Series detection appears after 3+ similar renders

- [ ] Render 3+ clips with same preset and title prefix (e.g. "Podcast Ep 1", "Podcast Ep 2", "Podcast Ep 3")
- [ ] Log: `series_confidence: 44% window=3` (or similar)
- [ ] Log: `series_detected: prefix="podcast ep" preset=...`
- [ ] Open editor on render 4 — `cpSeriesHint` shows "Series: podcast ep"
- [ ] v3SteeringPanel shows "Series" chip (cyan)

### B — Trust chip appears when confidence ≥ 55%

- [ ] Render 5+ clips with preset + logo consistency (preset=2pts, logo=2pts, platform=1pt → 56%)
- [ ] Render completes — output trust bar shows "Series style" chip (cyan, after DNA)
- [ ] Log: `series_nudge: Series style active`

### C — Different content deactivates series

- [ ] After detecting a podcast series, render a completely different clip with different preset/logo/title
- [ ] `series_confidence` drops
- [ ] If confidence drops below CHIP_GATE → trust chip disappears
- [ ] If confidence drops below DETECT_GATE → hint text disappears

### D — No creepy feeling

- [ ] Text reads "Series style active" or "Series: podcast ep" — not "We detected your series"
- [ ] Chip is small, subtle, cyan — not a banner
- [ ] Creator can ignore completely — no modals, no prompts, no forced changes

### E — No overfit on single-render burst

- [ ] Render one clip with a new preset
- [ ] `series_confidence: 0%` — no series detected (window_size=1)
- [ ] Render two clips with same preset
- [ ] `series_confidence: 0%` — still below MIN_RENDERS=3
- [ ] Third render: `series_confidence: 22%` — detected but below DETECT_GATE; hint suppressed

### F — Review actions reinforce series

- [ ] Render 3+ clips, keep 2 of them via Review Queue
- [ ] Log: `series_confidence` increases by ~11% (1/9 signal points)
- [ ] If confidence crosses CHIP_GATE, trust chip appears on next render

### G — Manual override always wins

- [ ] Series fingerprint suggests `story_clean_01` subtitle
- [ ] Creator manually changes subtitle to `tiktok_bounce_v1`
- [ ] Form respects the manual change (no forced revert)
- [ ] `ctManual` flag prevents CreatorTaste hint from firing
- [ ] Series hint is informational only — no form-fill interference

### H — Series context in payload

- [ ] Submit a render with series active
- [ ] Check payload (dev tools or backend log): `creator_series: { confidence: 0.X, ... }` present
- [ ] Series context is never null when CreatorSeries is loaded

### I — 30-day window eviction

- [ ] Manually set `ts` of old render records to > 30 days ago in localStorage
- [ ] On next `CreatorSeries.init()` or render, those records are excluded from fingerprint
- [ ] Confidence drops accordingly

### J — No regression

- [ ] Normal render flow (editor and batch queue) unchanged
- [ ] History view, download view, review queue unaffected
- [ ] Steering panel, trust bar, preset selector all work normally
- [ ] No console errors with `CreatorSeries` undefined guard (`typeof CreatorSeries !== 'undefined'`)

### K — Observability completeness

- [ ] Render 3 different-title clips with same preset
- [ ] Check event log: `series_confidence`, `series_detected` appear
- [ ] Open editor: `series_nudge` appears in log
- [ ] Render with weak signals (window_size=3, 1 signal only): `series_suppressed` appears
