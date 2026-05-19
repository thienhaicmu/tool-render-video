# Phase 74 — RC Polish & Consistency Plan
**Post-73.3 Quality Floor | V1 RC Final Polish**
**Status:** PLANNING — not yet implemented
**Branch target:** feature/ai-output-upgrade
**Date:** 2026-05-19

---

## Executive Summary

Phase 73.3 is complete. The quality floor stops weak clips from reaching the creator's review queue. The remaining "beta feeling" is not capability — it is consistency. Creators do not lose trust because a feature is missing; they lose trust when the tool behaves differently than expected, uses inconsistent language, or shows evidence that something was not finished.

This phase addresses five grounded, code-verified issues that produce that beta feeling. Each fix is small, deterministic, and safe. No ranking changes. No new systems. No workflow changes.

**The five problems this phase fixes:**

1. `_arrivalTriggered` is never reset — the arrival animation/notification only fires on the first render of a session. Every subsequent render in the same browser session receives no arrival signal. This is a silent regression that makes rerenders feel dead. (**P0 — functional**)

2. Toast messages across review-queue.js and render-ui.js use mixed capitalization, mixed punctuation patterns, and mixed tone — the same "retry failed" condition produces two different message formats depending on which branch is hit. (**P0 — trust**)

3. The Words tab `▸ Advanced` disclosure arrow does not visually toggle to `▾` when expanded. Phase 63 identified this as deferred micro-fix FP-1. After six phases it remains. (**P0 — finish what was started**)

4. Silent `catch (_) {}` blocks in network/API call paths mean that when something fails, the creator sees no feedback and the developer sees no trace. Phase 71 addressed localStorage catches with `console.warn`; the same treatment is needed for fetch/API failure paths. (**P1 — debugging and trust**)

5. ReviewQueue action buttons show single-character labels (K, ★, D, ↻) with keyboard shortcuts only in title attributes. First-time creators do not hover — they see unlabeled symbol buttons on their completed clips and do not know what they do. (**P1 — discoverability**)

---

## RC Polish Audit

### Finding P0-1 — `_arrivalTriggered` never reset (render-ui.js line ~5826)

The arrival animation path has a guard: `if (!_arrivalTriggered)`. When the first clip arrives, `_arrivalTriggered = true` is set. This variable is never reset in `resetRenderSessionUi()` or `clearRenderOutputPanel()`.

**Effect:** After the first render completes in a browser session, starting a second render and waiting for results produces no arrival animation, no "first clip ready" signal, none of the animated feedback that makes the tool feel alive. The creator sees clips appear, but the panel feels inert. On a rerender (the most common second-render case), this means the tool appears to have regressed — it felt lively on first use and dead on second use.

**Fix:** Add `_arrivalTriggered = false;` to `resetRenderSessionUi()` and/or `clearRenderOutputPanel()`. One line.

**Risk:** None. This restores the intended behavior on every render, not just the first.

---

### Finding P0-2 — Toast message inconsistency (review-queue.js, render-ui.js)

A full audit of every `showToast` call finds three conflicting patterns used for the same message categories:

**Pattern A** (terse noun phrase): `'Kept'`, `'Added to Favorites'`
**Pattern B** (em-dash with action hint): `'Dismissed — undo in Dismissed section'`, `'No settings stored — open Create to start a new render'`, `'Retry error — check connection'`
**Pattern C** (colon with error detail): `'Retry failed: ${err}'`

The same retry failure surface uses both Pattern B and Pattern C depending on which branch fires:

```javascript
// Pattern C (line ~100):
_showToast(`Retry failed: ${err}`, 'error');

// Pattern B (line ~109):
_showToast('Retry error — check connection', 'error');
```

Additional inconsistencies:
- `'Restored to Ready to Review'` (7 words) vs `'Kept'` (1 word) — same category of state-change confirmation
- `'Retrying… check Review when complete'` uses `…` but other info toasts use plain `.`
- Some error toasts are lowercase-initial; some are title-case; some are sentence-case

**Proposed standard:**
- **Success:** Terse verb/noun phrase, title case, no trailing punctuation. `'Kept'`, `'Added to Favorites'`, `'Dismissed'`, `'Restored'`
- **Error:** `'[Action] failed — [brief actionable hint]'` using em-dash, sentence-case after the em-dash. `'Retry failed — check connection'`
- **Info/progress:** Complete phrase, sentence case, no trailing period unless needed. `'Retrying — check Review when complete'`

**Risk:** Strings only. No logic changes.

---

### Finding P0-3 — Words tab `▸ Advanced` arrow does not toggle (index.html)

Phase 63 wrapped the Words tab advanced controls in a `<details>` element. The `▸` character in the summary is static — when the `<details>` opens, `▸` stays `▸`. The browser renders `<details open>` but the arrow text does not change.

This is the most visible evidence of "unfinished" in the editor. A creator opens the section, sees `▸` still pointing right, and either thinks it didn't open or that the arrow is decoration.

**Fix:** CSS `details[open] > summary .advToggleArrow { content: '▾'; }` or a `toggle` event listener that swaps the character. The `<summary>` element already renders the `▸` as a text node — either approach works.

**Risk:** None. Pure visual fix.

---

### Finding P1-1 — Empty catches on fetch/API paths (render-ui.js, render-config.js)

Phase 71 addressed localStorage failure catches with `console.warn`. The same treatment is missing from fetch/API error paths.

Key silent-failure catches in network paths (not localStorage, where silent is intentional):

| File | Line range | Path | What is lost |
|---|---|---|---|
| render-ui.js | ~176 | `_loadQueueStatus` | Queue status silently fails; no badge update |
| render-ui.js | ~3986 | `populateRenderOutputPanel` | Render output panel silently fails to populate |
| render-ui.js | ~5013 | render status handling | Status transition error silently swallowed |
| render-config.js | ~290 | `syncUploadSourceDirByChannel` | Channel sync failure deliberately silent (comment: "convenience") |

The localStorage catches (`_renderHistoryRead`, `_renderHistoryWrite`, `_renderHistoryPayload`, etc.) are intentionally silent and should remain so — localStorage is best-effort. The distinction is: **fetch/API failures should log**; **localStorage failures should stay silent**.

**Fix:** Replace `catch (_) {}` with `catch (err) { console.warn('[context]', err); }` on fetch-path catches only. Does not change any visible behavior. Aids debugging in production.

**Risk:** Very low. Behavior unchanged for creator. Developer gets trace.

---

### Finding P1-2 — ReviewQueue buttons are unlabeled symbols (review-queue.js)

Current card action buttons in `_cardHtml()`:

```html
<button class="rqBtn rqBtnKeep"    title="Keep  K">K</button>
<button class="rqBtn rqBtnFav"     title="Favorite  F">&#9733;</button>
<button class="rqBtn rqBtnDismiss" title="Dismiss  D">D</button>
<button class="rqBtn rqBtnRetry"   title="Retry  R">&#8635;</button>
<button class="rqBtn rqBtnOpen"    title="Open Folder">&#128193;</button>
```

A creator who has never used the tool sees: `K`, `★`, `D`, `↻`, `📁`. The keyboard shortcut hint in `title` only appears on hover (and not on touch). "K" and "D" are single letters with no inherent meaning.

**Fix:** Add short visible text labels below or alongside the symbol. Options:

Option A — Stack: symbol on top, label below (`Keep`, `Fav`, `Dismiss`, `Retry`, `Open`)
Option B — Inline: symbol + short label (`★ Fav`, `K Keep`, `D Dismiss`)
Option C — Label only on hover-capable devices, always visible on first use (CSS `@media (hover: none)`)

Recommended: Option A (stack) — consistent with common card UI pattern, fits the existing `rqBtn` sizing, and works on both mouse and touch without media query complexity.

**Risk:** Low. Template change only. Keyboard shortcuts remain identical.

---

## Consistency Audit

### Same action, different outcome: second render arrival

Covered in P0-1 above. Functionally consistent API; visually inconsistent presentation depending on whether creator has rendered before in this session.

### Same error type, different message format

Covered in P0-2 above. `retry()` uses colon-format on API error, em-dash-format on network error.

### "Advanced" disclosure: same interaction pattern, different visual feedback

`<details>` elements elsewhere in the UI (Market section, Presets section — collapsed by Phase 64) use the browser's native `▶`/`▼` triangle. The Words tab Advanced uses a text character `▸` that was manually added and does not respond to `[open]` state. Same interaction, different visual contract.

### Button text: ReviewQueue vs clip card Keep/Avoid

Clip card Keep button (render view) has full text: "Keep". Clip card Avoid button has full text: "Avoid". ReviewQueue cards have "K" and "D". A creator who uses both views sees inconsistent labeling for equivalent actions. The ReviewQueue labels should match the clip card register.

---

## Micro UX Improvements

### Better wording

| Current | Proposed | Location |
|---|---|---|
| `'Retry error — check connection'` | `'Retry failed — check connection'` | review-queue.js |
| `'Restored to Ready to Review'` | `'Restored'` | review-queue.js |
| `'Retrying… check Review when complete'` | `'Retrying — check Review when done'` | review-queue.js |
| `'Dismissed — undo in Dismissed section'` | `'Dismissed — tap Undo to restore'` | review-queue.js |

`'Dismissed — undo in Dismissed section'` tells the creator WHERE undo is, which is useful — but the phrase "in Dismissed section" assumes the creator can see the section name. "tap Undo to restore" describes the action available, which is more immediate.

### Loading and disabled state clarity

`rc_open_output_btn` (Open Output Folder button) is disabled on init and re-enabled in at least four separate code locations. The enable check at one location uses a fragile regex `/not set|no output/i.test()` on the text content of a nearby element. A centralized enable function `_syncOpenOutputBtn()` would be safer and more predictable. This is P2 — the button works, the mechanism is just fragile.

### Focus consistency

ReviewQueue `_focusNextCard` uses `setTimeout(0)` to defer focus after `_refreshView()` re-renders the DOM. This is correct (DOM must settle). Using `requestAnimationFrame` instead of `setTimeout(0)` more accurately expresses "after next paint" and is more reliable on slow repaints. Low-impact improvement.

---

## Trust Improvements

### What currently causes micro trust loss

| Observation | Creator interpretation | Real cause |
|---|---|---|
| Second render: panel fills with clips but no animated "arrived" signal | "Did something go wrong? It just appeared." | `_arrivalTriggered` never reset |
| ReviewQueue K/D buttons | "What do these do?" | Single-character labels with no visible text |
| `▸ Advanced` stays `▸` after click | "Did it open? The arrow didn't change." | Static text character, no open-state variant |
| `'Retry error — check connection'` for one error, `'Retry failed: ${err}'` for another | "The tool is inconsistent" | Two different error branches, no shared format |
| "Restored to Ready to Review" vs "Kept" | Register mismatch: one is a sentence, one is a word | No toast standard enforced |

### What should never surprise the creator

- Starting a second render should feel identical to starting the first
- Every completed action should produce a confirmation in the same register
- Every expandable section should visually confirm it expanded
- Every button should say what it does in plain language

---

## Priority Matrix

| ID | Fix | Impact | Effort | Risk | Priority |
|---|---|---|---|---|---|
| 74.1 | `_arrivalTriggered` reset on session clear | High (functional regression) | Minimal (1–2 lines) | Very Low | **P0** |
| 74.2 | Toast message normalization | High (trust every session) | Low (strings only) | Very Low | **P0** |
| 74.3 | Words tab `▸ Advanced` arrow toggle | Medium (finish line from Phase 63) | Minimal (CSS only) | None | **P0** |
| 74.4 | `console.warn` on fetch/API catches | Low (dev-facing, no creator change) | Low (~8 targeted lines) | None | **P1** |
| 74.5 | ReviewQueue button labels visible | Medium (discoverability) | Low (template change) | Very Low | **P1** |
| 74.6 | `rc_open_output_btn` centralize enable | Low (internal fragility) | Low (~15 lines) | Low | **P2** |
| 74.7 | `requestAnimationFrame` for focus defer | Very Low (correctness) | Minimal (1 line) | None | **P2** |

---

## Commit Plan

### Commit 74.1 — Fix `_arrivalTriggered` never reset (P0)

**File:** `backend/static/js/render-ui.js`
**Change:** Add `_arrivalTriggered = false;` inside `resetRenderSessionUi()` and `clearRenderOutputPanel()`. Verify which function is the canonical session-clear entry point and add to both defensively.
**Why safe:** Restores intended behavior. The variable was clearly intended to be per-render, not per-session. Adding the reset makes behavior match expectation.
**Test:** Start render → wait for arrival → clear/reset session → start second render → verify arrival fires again.

---

### Commit 74.2 — Toast message normalization (P0)

**File:** `backend/static/js/review-queue.js`
**Changes:**
- `'Retry error — check connection'` → `'Retry failed — check connection'` (align with error pattern)
- `'Restored to Ready to Review'` → `'Restored'` (terse, matches 'Kept' register)
- `'Dismissed — undo in Dismissed section'` → `'Dismissed — tap Undo to restore'` (action-oriented)
- `'Retrying… check Review when complete'` → `'Retrying — check Review when done'` (consistent separator)

**Standard applied:**
- Success confirmations: terse noun/verb phrase, title case, no punctuation
- Error messages: `'[Action] failed — [brief hint]'`
- Info/state messages: `'[State] — [what creator can do next]'`

**Why safe:** Strings only. All toast types and severities unchanged.
**Test:** Trigger each state (keep, dismiss, retry success, retry fail, undismiss) — verify messages match standard.

---

### Commit 74.3 — Words tab Advanced arrow toggle (P0)

**File:** `backend/static/index.html` (or the CSS/JS file that owns the Words tab template — verify before editing)
**Change:** Make the `▸` toggle to `▾` when `<details>` is open. Two viable approaches:
- CSS: `details.advSection[open] > summary .advArrow::before { content: '▾'; }` (preferred — no JS)
- JS fallback: `toggle` event listener on `<details>` element that swaps textContent of the arrow span

**Why safe:** Pure visual. No behavior changes. The `<details>` open/close mechanism already works correctly.
**Test:** Open Words tab → click Advanced → verify arrow toggles from `▸` to `▾`. Click again → verify it toggles back.

---

### Commit 74.4 — `console.warn` on fetch/API silent catches (P1)

**File:** `backend/static/js/render-ui.js`, `backend/static/js/render-config.js`
**Target catches:** Network/fetch/API paths only. localStorage catches intentionally stay silent.

Targeted replacements (fetch/API paths, not localStorage):
- `_loadQueueStatus` catch: add `console.warn('[render-ui] queue status load failed', err)`
- `populateRenderOutputPanel` catch: add `console.warn('[render-ui] populate output panel failed', err)`
- Render status handling catch (~line 5013): add `console.warn('[render-ui] status transition error', err)`

**NOT changed:** All `_renderHistoryRead`, `_renderHistoryWrite`, `_renderHistoryPayload`, `_renderHistoryTitle`, `_renderHistoryStatus` catches remain silent (localStorage is best-effort by design).

**Why safe:** No behavior change for creator. `console.warn` does not affect render flow, toast display, or UI state. Purely developer-facing.
**Test:** Simulate network failure → verify `console.warn` appears in DevTools with context. Normal render → verify no new console noise.

---

### Commit 74.5 — ReviewQueue action button labels (P1)

**File:** `backend/static/js/review-queue.js` — `_cardHtml()` function
**Change:** Add visible text label to each action button. Proposed stack layout (symbol + label):

```html
<button class="rqBtn rqBtnKeep"    title="Keep  K">
  <span class="rqBtnIcon">K</span>
  <span class="rqBtnLabel">Keep</span>
</button>
<button class="rqBtn rqBtnFav"     title="Favorite  F">
  <span class="rqBtnIcon">&#9733;</span>
  <span class="rqBtnLabel">Fav</span>
</button>
<button class="rqBtn rqBtnDismiss" title="Dismiss  D">
  <span class="rqBtnIcon">D</span>
  <span class="rqBtnLabel">Dismiss</span>
</button>
<button class="rqBtn rqBtnRetry"   title="Retry  R">
  <span class="rqBtnIcon">&#8635;</span>
  <span class="rqBtnLabel">Retry</span>
</button>
<button class="rqBtn rqBtnOpen"    title="Open Folder">
  <span class="rqBtnIcon">&#128193;</span>
  <span class="rqBtnLabel">Open</span>
</button>
```

CSS: `rqBtnIcon` and `rqBtnLabel` styled as stacked flex column. `rqBtnLabel` at ~9px, muted color. This keeps the button compact while adding legibility.

**Why safe:** Template and CSS only. All click handlers, keyboard shortcuts, and `data-rq-jobid` attributes unchanged.
**Test:** Open Review tab → verify each button shows symbol above label. Keyboard K/F/D/R still triggers correct action.

---

### Commit 74.6 — Centralize `rc_open_output_btn` enable logic (P2)

**File:** `backend/static/js/render-ui.js`
**Change:** Extract the scattered enable/disable logic into a single `_syncOpenOutputBtn()` function. Call from each location that currently sets `.disabled` directly. Replace the fragile regex content-check with a proper state variable check (`selectedRenderOutputDir` or equivalent).
**Why:** Currently enabled/disabled in 4 locations using `/not set|no output/i.test(element.textContent)` — this breaks silently if the text ever changes.
**Why safe:** Functionally equivalent. The button behavior does not change.
**Test:** Render completes with output path → button enabled. Clear session → button disabled. Rerender → button re-enables.

---

### Commit 74.7 — `requestAnimationFrame` for focus defer in ReviewQueue (P2)

**File:** `backend/static/js/review-queue.js` — `_focusNextCard()` function
**Change:** Replace `setTimeout(function() { ... }, 0)` with `requestAnimationFrame(function() { ... })`.
**Why:** `rAF` fires after the next browser paint, which is the correct moment to focus an element that was just created by `_refreshView()`'s innerHTML rewrite. `setTimeout(0)` fires at the end of the microtask queue, which is usually before paint — technically incorrect timing.
**Why safe:** The behavior difference is imperceptible in practice. The fix is semantically correct and makes the intent explicit.
**Test:** Dismiss a ReviewQueue item → verify focus moves to next card reliably.

---

## Definition of Done

- [ ] Second render in the same session fires arrival animation/signal identically to the first render
- [ ] All ReviewQueue toast messages follow the defined pattern (success = terse title case; error = `'X failed — hint'`; info = `'State — action hint'`)
- [ ] Words tab `▸ Advanced` toggles to `▾` when opened, back to `▸` when closed
- [ ] No regressions in render flow, scoring, review actions, or keyboard shortcuts from Phases 63–73
- [ ] Phase 72 K/A/D shortcuts still work on clip cards; ReviewQueue K/F/D/R still work
- [ ] P1: `console.warn` appears in DevTools for fetch/API failures (not localStorage failures)
- [ ] P1: ReviewQueue action buttons show visible text labels; keyboard shortcuts unchanged
- [ ] Phase 73.3 quality floor unaffected (render_pipeline.py not touched in this phase)
- [ ] Zero new localStorage keys, zero new API endpoints, zero ranking changes

---

## Appendix — Deferred (Not in Phase 74)

| Item | Reason deferred |
|---|---|
| Platform → duration auto-link | Requires dirty flag infrastructure not yet built |
| Arrow key navigation in render view | Tab/Shift+Tab sufficient for V1 |
| Rerender keyboard shortcut | Too consequential for single-key trigger |
| `evMinPart` / `evMaxPart` default change (73.1) | Pending separate commit |
| `evMaxExportParts` default change (73.2) | Pending separate commit |
| Narrow-spread advisory note (73.4) | P1 optional, pending 73.1/73.2 |
| `_rcUserIsScrolling` not reset | Not creator-visible; defer |
| Batch cancel / child process kill | Backend orchestration scope |

---

## Code Locations

| Symbol | File | Line | Note |
|---|---|---|---|
| `_arrivalTriggered` | render-ui.js | ~5826 | Set to `true` on arrival; never reset |
| `resetRenderSessionUi()` | render-ui.js | ~145 | Add `_arrivalTriggered = false` here |
| `clearRenderOutputPanel()` | render-ui.js | ~(search) | Add `_arrivalTriggered = false` here too |
| `_showToast('Retry error…')` | review-queue.js | ~109 | Change to `'Retry failed — check connection'` |
| `_showToast('Restored…')` | review-queue.js | ~119 | Change to `'Restored'` |
| `_showToast('Dismissed…')` | review-queue.js | ~76 | Change to `'Dismissed — tap Undo to restore'` |
| Words tab `<details>` | index.html | (search `Advanced`) | Add CSS `[open]` arrow toggle |
| `_cardHtml()` button HTML | review-queue.js | ~204 | Add label spans to action buttons |
| `_loadQueueStatus` catch | render-ui.js | ~176 | Add `console.warn` |
| `populateRenderOutputPanel` catch | render-ui.js | ~3986 | Add `console.warn` |
| `_focusNextCard()` | review-queue.js | ~145 | Replace `setTimeout(fn, 0)` with `rAF(fn)` |
