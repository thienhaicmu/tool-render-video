# RC2.2 — UI Bug Audit

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-19
**Status:** Read-only audit. No code changed.

---

## Index

| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| A | `rc_ai_evolution_feed` no scroll | High | 30 min |
| B | `p28EvolScore` shows 5600% | Critical | 10 min |
| C | `uxr2ThumbScore` shows 5600% | Critical | 10 min |
| D | `uxr1_ai_hero` height/layout | Medium | 20 min |
| E | clipCard hover/play parity | High | 45 min |

---

## A — `rc_ai_evolution_feed` No Scroll

### Severity
High — creator sees a growing list that overflows or gets clipped after 3–4 clips. No scrollbar appears.

### Repro
Run a job with 5+ clips. Watch the evolution feed in the queue panel. After the 4th clip card renders, the feed extends beyond its container with no scroll.

### Root Cause
The evolution feed has no `overflow-y`, no bounded height, and no `flex` participation. It grows to fit all content unconditionally.

The `.rcAiEvolutionList` inner list:

```css
/* v3/runtime.css line 1548 */
.rcAiEvolutionList {
  display: flex;
  flex-direction: column;
  gap: 2px;
  /* NO overflow-y, NO max-height, NO min-height:0 */
}
```

The `.rcAiEvolutionFeed` outer container:

```css
/* v3/runtime.css line 1535 */
.rcAiEvolutionFeed {
  padding: 0 12px 8px;
  /* NO display:flex, NO flex participation, NO overflow */
}
/* v3/runtime.css line 1938 */
.rcAiEvolutionFeed {
  border-left: 2px solid ...;
  /* STILL NO overflow */
}
```

The parent `.rcQueuePanel` has `overflow: hidden` (`v3/runtime.css` line 519), so content that extends past the panel boundary is silently clipped.

### Why It Happens
The feed was designed as a "growing list" without establishing a scroll boundary. The working reference (`rc_part_cards`) explicitly sets `flex: 1; overflow-y: auto; min-height: 0` — the key trio needed in a flex-column layout to enable scroll. The evolution feed is missing all three.

### Comparison: Working Reference vs Broken Feed

| Property | `#rc_part_cards` (works) | `.rcAiEvolutionList` (broken) |
|----------|--------------------------|-------------------------------|
| `flex` | `1` (expands to fill) | not set |
| `overflow-y` | `auto` | not set |
| `min-height` | `0` | not set |
| Scrollbar | defined | none |

**Exact file/line:**
- Broken: [backend/static/css/v3/runtime.css:1548](../../backend/static/css/v3/runtime.css#L1548)
- Reference (working): [backend/static/css/v3/runtime.css:875](../../backend/static/css/v3/runtime.css#L875)

### Minimal Safe Fix

In `v3/runtime.css`, add to `.rcAiEvolutionFeed` and `.rcAiEvolutionList`:

```css
/* Line ~1535: make the feed a flex column with a bounded height */
.rcAiEvolutionFeed {
  display: flex;
  flex-direction: column;
  min-height: 0;
  max-height: 300px; /* or clamp(180px, 30vh, 320px) for responsive */
}

/* Line ~1548: make the list scroll when content exceeds the feed */
.rcAiEvolutionList {
  overflow-y: auto;
  min-height: 0;
  scrollbar-width: thin;
  scrollbar-color: rgba(255,255,255,.09) transparent;
}
.rcAiEvolutionList::-webkit-scrollbar       { width: 4px; }
.rcAiEvolutionList::-webkit-scrollbar-thumb { background: rgba(255,255,255,.1); border-radius: 2px; }
```

### Risk
Low. The feed already caps content at 6 items in JS (`render-ui.js:5471`), so the scroll boundary will rarely be hit in normal use. A fixed `max-height` is simpler than a dynamic one; increase it if designers want more visible.

---

## B — `p28EvolScore` Shows 5600% Instead of 56%

### Severity
Critical — visible to creator on every completed clip in the evolution feed. Destroys trust in AI scoring.

### Repro
Run any job. As clips complete, the evolution feed shows scores like `5600%`, `7200%` where `56%`, `72%` are expected.

### Root Cause
Double multiplication. The backend emits `viral_score` as a **0–100 integer**. The frontend treats it as a **0–1 fraction** and multiplies by 100 again.

**Backend scale — confirmed in three places:**

```python
# app/services/viral_scorer.py line 131
"""Weighted linear combination of features → score in [0, 100]."""
return round(min(100.0, max(0.0, raw * 100.0)), 1)

# app/services/viral_scorer.py line 332
"viral_score": int(viral_score)   # 0–100 integer stored on segment

# app/services/viral_scoring.py line 701
viral_score = int(round(max(0.0, min(100.0, composite))))  # documented 0–100
```

**Frontend double-multiply:**

```javascript
// render-ui.js line 5423
const rawSc = p.viral_score != null ? Number(p.viral_score) : null;
const pct   = rawSc !== null ? Math.round(rawSc * 100) : null;
//  56 (from backend) * 100 = 5600 ← BUG
```

**Value flow:**
```
backend: viral_score = 56  (0–100 int)
  ↓  WebSocket / REST part payload
JS: rawSc = 56
  ↓  * 100  (wrong — backend is NOT 0–1)
pct = 5600
  ↓  render
DOM: <span class="p28EvolScore">5600%</span>
```

**Exact file/line:**
- [backend/static/js/render-ui.js:5422-5423](../../backend/static/js/render-ui.js#L5422)

### Minimal Safe Fix

```javascript
// render-ui.js line 5423 — remove * 100
const pct = rawSc !== null ? Math.round(rawSc) : null;
```

### Risk
Low. The backend scale is unambiguous and documented. All three backend sources agree on 0–100. The only change is removing one `* 100` multiplication.

---

## C — `uxr2ThumbScore` Shows 5600% Instead of 56%

### Severity
Critical — visible on the completion hero thumbnail (the most prominent UI element after a render finishes). Equivalent damage to trust as Bug B.

### Repro
Complete any job with a best clip. The completion hero thumbnail badge shows `5600%` instead of `56%`.

### Root Cause
Same double-multiply pattern as Bug B, applied in two additional locations: the `bestViralPct` used for the hero thumb badge, and `topPct` used throughout the completion summary card.

**Double-multiply #1 — hero thumb badge:**

```javascript
// render-ui.js line 5628
const bestViralPct = Math.round(Number(bestPart.viral_score || 0) * 100) || topPct;
// viral_score = 56 → 56 * 100 = 5600
```

**Double-multiply #2 — topPct (shared throughout completion summary):**

```javascript
// render-ui.js line 5720–5724
const scores   = completed.map(p => Number(p.viral_score || 0));
const topScore = Math.max(...scores);          // 56
const topPct   = Math.round(topScore * 100);  // 5600 ← BUG
```

`topPct` is then used at:
- Line 5724: `topTier` classification threshold (wrong — `5600 >= 70` passes, tier always "high")
- Line 5747: "Top Clip" score in the completion card: `5600%`
- Lines 5772–5773: narrative bits: "Best clip 5600% — strong hook"
- Line 5786: passed as fallback to `_showCompletionHero`

**Exact files/lines:**
- [backend/static/js/render-ui.js:5628](../../backend/static/js/render-ui.js#L5628)
- [backend/static/js/render-ui.js:5724](../../backend/static/js/render-ui.js#L5724)

### Minimal Safe Fix

```javascript
// render-ui.js line 5628 — remove * 100
const bestViralPct = Math.round(Number(bestPart.viral_score || 0)) || topPct;

// render-ui.js line 5724 — remove * 100
const topPct = Math.round(topScore);
```

### Risk
Low — same as Bug B. Removing the erroneous `* 100`.

> **Note:** Bugs B and C share the same root cause. The single source of truth for display formatting should be: `Math.round(Number(part.viral_score || 0))` with no multiplication. The backend is the authority: `viral_score` is always 0–100.

---

## D — `uxr1_ai_hero` Height / Layout Issue

### Severity
Medium — when concern items stack up (stall warnings, editorial concerns), the hero grows unbounded, compressing the queue panel below. The queue may become too small to use or disappear entirely.

### Repro
Run a job on a source with low-quality content that triggers multiple concern items. Watch `#uxr1_ai_hero` grow. The `.rcQueuePanel` queue grid shrinks to near-zero height.

### Root Cause
`.uxr1AiHero` has `flex-shrink: 0` (will not yield space to siblings) and no `max-height`. It is a direct flex child of `.renderActivePanel`, which gives its **only** flexible child — `.renderRuntimeMount` — `flex: 1; min-height: 0`. When the hero grows, the mount must absorb the loss.

**Flex chain:**

```
.renderActivePanel (flex column, overflow:hidden)
  ├── .uxr1AiHero           (flex-shrink:0, NO max-height)  ← grows freely
  ├── .rdCard               (flex-shrink:0)
  ├── .aiInsightsPanel      (flex-shrink:0)
  └── .renderRuntimeMount   (flex:1, min-height:0)          ← absorbs loss
        └── .rcBottom
              └── .rcQueuePanel  ← starved when hero is too tall
```

**`flex-shrink: 0` with no upper bound is the trigger.** The hero can consume 100% of the panel height if enough concerns are injected (each `uxr1ConcernItem` adds ~36px).

**Exact files/lines:**
- [backend/static/css/v3/runtime.css:2279](../../backend/static/css/v3/runtime.css#L2279) — `.uxr1AiHero { flex-shrink: 0; ... }` — missing `max-height`
- [backend/static/css/v3/runtime.css:34](../../backend/static/css/v3/runtime.css#L34) — `.renderRuntimeMount { flex: 1; min-height: 0; }` — correct but starved by hero growth
- [backend/static/index.html:493](../../backend/static/index.html#L493) — hero is immediate child of `#render_active_panel`

### Why It Happens
The hero was originally a one-or-two-line element (stage label + message). When UX-R7/R8 added concern items and stall warnings, no height cap was applied. The `flex-shrink: 0` rule prevents the hero from collapsing when space is tight — the right choice for a status strip but dangerous when content can stack vertically.

### Minimal Safe Fix

In `v3/runtime.css`, cap the hero height and allow internal scroll for overflow content:

```css
/* ~line 2279 — add max-height and allow inner scroll */
.uxr1AiHero {
  max-height: 220px;    /* tune based on design; ~5 concern items fit */
  overflow: hidden;     /* already set; confirm it clips correctly */
}

/* OR: cap only the concerns sub-region, not the entire hero */
#uxr1_concerns {
  max-height: 110px;
  overflow-y: auto;
  scrollbar-width: none;
}
```

The concerns-only approach is more surgical — it preserves the hero stage label/icon at full size and only limits the expandable concern list.

### Risk
Low. Capping at 220px leaves room for 2–3 concern items visible, which is the typical maximum. If a concern item needs to be visible, the creator can still see it in the evolution feed.

---

## E — clipCard Hover/Play Parity vs `uxr2HeroThumb`

### Severity
High — two categories of clips cannot be previewed in a way the UI implies they should be:
1. `isSkipped` cards with an output file cannot be previewed at all.
2. `isBestClip` hover-play is functional but has invisible coupling gaps vs. the completion hero.

### Repro

**For isSkipped:** Run a job with `resume_from_last` enabled. Some parts are skipped (already rendered). The skipped clip cards show a `—` placeholder — no thumbnail, no hover preview, no Preview button. If the creator wants to review a skipped clip, there is no UI affordance.

**For isBestClip:** The best clip card in the output grid has hover-play (works), but it opens in `centerPreviewClip` automatically after 900ms (UX-R3-F). If the creator dismisses the auto-preview and then tries to hover the card, the IntersectionObserver gate may prevent video replay if the card is not registered as intersecting (e.g., after scroll).

### Root Cause A — `isSkipped` Has No Video Element

The thumbnail HTML builder at **[render-ui.js:4455–4458](../../backend/static/js/render-ui.js#L4455)**:

```javascript
const thumbHtml = isDone && hasFile && jobId
  ? `<img class="clipCardThumbImg" ...> <video class="clipCardThumbVid" data-src="..." ...></video>`
  : `<div class="clipCardThumbPlaceholder">${isFailed ? '✗' : isSkipped ? '—' : '⋯'}</div>`;
```

`isSkipped` means `st === 'skipped'` → `isDone = false` → always renders placeholder, no `<video>`.

The click handler is also gated the same way at **[render-ui.js:4459–4461](../../backend/static/js/render-ui.js#L4459)**:
```javascript
const thumbAttrs = (isDone && hasFile && jobId) ? ` data-previewable="true" onclick="..."` : '';
```

And the Preview button at **[render-ui.js:4462–4464](../../backend/static/js/render-ui.js#L4462)**:
```javascript
const previewBtn = (!isFailed && !isSkipped && hasFile && jobId) ? `<button ...>Preview</button>` : '';
```

`isSkipped` is an explicit exclusion from the preview button.

`_bindCardHoverPreviews` at **[render-ui.js:4640](../../backend/static/js/render-ui.js#L4640)** early-returns when no `.clipCardThumbVid` is found:
```javascript
const vid = card.querySelector('.clipCardThumbVid');
if (!thumbWrap || !vid) return;
```

**Three independent guards all block preview for `isSkipped`.** None of them check if the skipped clip has an `output_file` that is available for playback.

### Root Cause B — `isBestClip` Hover Uses a Different (More Complex) Path Than `uxr2HeroThumb`

**`uxr2HeroThumb` (works cleanly):**
```javascript
// render-ui.js line 5636–5644
thumbEl.onmouseenter = function () {
  if (!vidEl.src && vidEl.dataset.src) vidEl.src = vidEl.dataset.src;
  vidEl.classList.add('uxr2VidActive');
  vidEl.play().catch(function () {});
};
thumbEl.onmouseleave = function () {
  vidEl.classList.remove('uxr2VidActive');
  vidEl.pause();
};
```
- Direct property assignment (`onmouseenter`) — cannot accumulate
- No IntersectionObserver gate
- Class applied directly to the `<video>` element
- Works immediately; no observer setup delay

**`clipCard.isBestClip` hover (via `_bindCardHoverPreviews`):**
```javascript
// render-ui.js line 4643–4655
thumbWrap.onmouseenter = () => {
  if (vid._cardInView === false) return;  // IntersectionObserver gate ← can silently no-op
  if (_cardHoverActiveVid === vid) return;
  _stopCardHoverVideo();
  if (!vid.getAttribute('src') && vid.dataset.src) vid.src = vid.dataset.src;
  _cardHoverActiveVid = vid;
  vid.play().catch(() => {});
  card.classList.add('is-preview-playing'); // class on card, not video
};
```
- IntersectionObserver gate: `vid._cardInView` is `undefined` on first hover (fine), but `false` after scroll-out. If the creator scrolls, scrolls back, and hovers — `_cardInView` may still be `false` until the observer re-fires.
- `_cardHoverActiveVid` global: one active video at a time. If `uxr2HeroThumb` is playing (it uses a separate `onmouseenter` on a different element), `_cardHoverActiveVid` is still `null` — so no conflict there. But if any other clip card is hovering, the best clip hover is blocked until `_stopCardHoverVideo()` clears it.
- CSS visibility uses `is-preview-playing` on the parent `card` element → `.clipCard.is-preview-playing .clipCardThumbVid { opacity: 1 }` ([editor-engine.css:557](../../backend/static/css/v3/editor-engine.css#L557)).

**Coupling check:** `uxr2HeroThumb` playback uses `thumbEl.onmouseenter` (direct property on `#uxr2_hero_thumb`). It is entirely independent of `_cardHoverActiveVid` and `_cardHoverObserver`. It is safe to reuse the same pattern (direct `onmouseenter`/`onmouseleave` + `.uxr2VidActive` class) for `isSkipped` cards. There is no coupling risk.

### Minimal Parity Plan

**For `isSkipped` with `hasFile = true`:**
Change the `thumbHtml` guard to:
```javascript
// render-ui.js ~line 4455
const canPreview = (isDone || isSkipped) && hasFile && jobId;
const thumbHtml = canPreview
  ? `<img class="clipCardThumbImg" ...> <video class="clipCardThumbVid" data-src="..." ...></video>`
  : `<div class="clipCardThumbPlaceholder">...</div>`;
```
And update `thumbAttrs` and `previewBtn` to use `canPreview` instead of `isDone`.

**For `isBestClip` hover parity:**
No fix strictly needed — hover-play is working. Optionally, the `uxr2HeroThumb` pattern (direct `onmouseenter` on the wrap, `.uxr2VidActive` on the video) could replace the `_bindCardHoverPreviews` path for the single best clip card to eliminate the observer gate. This is an enhancement, not a bug fix.

### Risk
- `isSkipped` fix: Medium. The only risk is loading a video src for a file that was rendered in a prior session and may have moved. The lazy `data-src` pattern already handles missing files gracefully (`video.play().catch(() => {})`). The thumbnail endpoint returning 404 is already handled by `onerror` on the `<img>`.
- `isBestClip` parity: Low. The current behavior is functional. Any change to hover logic risks regressions on the existing IntersectionObserver setup.

---

## Pre-Fix Checklist

Before any code changes:

- [ ] Confirm backend `viral_score` range on a real job log (should be 0–100 integers like `56`, `72`, not `0.56`, `0.72`)
- [ ] Confirm `isSkipped` clips do have `output_file` populated in the parts payload (check WS message)
- [ ] Measure `uxr1_ai_hero` height with 4 concerns active before choosing a `max-height` value
- [ ] Verify `rc_ai_evolution_feed` is inserted into DOM BEFORE or AFTER `rc_part_cards` and confirm the flex order is correct after the scroll fix

---

## Single Source of Truth for Score Formatting

All `viral_score` values in the frontend must be treated as **0–100 integers** emitted by the backend. Display format: `Math.round(Number(part.viral_score || 0)) + '%'`. No multiplication.

Places that currently apply `* 100` and must be corrected:

| File | Line | Expression | Fix |
|------|------|-----------|-----|
| render-ui.js | 5423 | `Math.round(rawSc * 100)` | `Math.round(rawSc)` |
| render-ui.js | 5628 | `Math.round(...viral_score... * 100)` | remove `* 100` |
| render-ui.js | 5724 | `Math.round(topScore * 100)` | `Math.round(topScore)` |

`topPct` is derived from `viral_score` values, so fixing line 5724 also fixes the downstream uses at lines 5726, 5731, 5747, 5772, 5773, 5786.

---

*Audit only — no code changed. All line numbers reference `feature/ai-output-upgrade` as of 2026-05-19.*
