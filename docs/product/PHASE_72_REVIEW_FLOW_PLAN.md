# PHASE 72 — REVIEW FLOW OPTIMIZATION PLAN
## Speed, Flow, and Keyboard-Friendliness for Clip Review

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 71 Ship Hardening — COMPLETE, zero regressions
**Plan date:** 2026-05-19
**Planning only — no implementation in this session**

---

## 1. EXECUTIVE SUMMARY

Phases 63–71 completed the rendering, memory, explainability, preference learning, and hardening layers. The review loop itself — the moment after clips appear — has not been touched since it was first built.

The creator flow today is:
> Render completes → scroll clip list → mouse to Keep button → mouse to next clip → repeat.

For a 6-clip render that is 30+ mouse movements and 0 keyboard actions. The flow is correct but not fast. Phase 72 fixes this without adding new capabilities or changing any decision-making.

**Three confirmed friction sources (code-verified):**

1. **Render view has zero keyboard shortcuts.** The centralized `init.js` keydown handler only fires when `currentView === 'editor'`. Clip cards have no `tabindex`. The creator cannot act on clips without a mouse.

2. **No auto-next after Keep/Avoid.** After clicking Keep on clip 3, the cursor stays on clip 3. The creator manually scrolls and clicks clip 4. No focus advance, no scroll assist.

3. **ReviewQueue loses focus after every action.** After pressing `K` on a ReviewQueue card, `_refreshView()` re-renders the list. The acted-on card is removed from "Ready to Review". Focus jumps to the browser default — usually page top. The creator must find the next card and click it to focus again.

**Phase 72 fixes all three with minimal code surface:**

- `tabindex="0"` + two data attributes on clip cards → keyboard-navigable
- Extend `init.js` handler to render view → K/A/D shortcuts active on focused card
- `_r72AdvanceFocus(partNo)` in `csKeepClip` / `csAvoidClip` → auto-next
- `_getNextReviewId` + `setTimeout(focus, 0)` in ReviewQueue → auto-focus next card

No new UI systems. No new AI. No redesign.

---

## 2. REVIEW FRICTION AUDIT

### 2.1 Render view — clip cards

**Current clip card HTML (confirmed in render-ui.js:4663):**
```html
<div class="clipCard isDone"
     data-clip-status="done"
     data-part-no="2"
     data-aspect="9:16">
  <!-- thumb, score, steer row, actions -->
</div>
```

Missing:
- No `tabindex` → card cannot receive keyboard focus
- No `data-start-sec` / `data-end-sec` → keyboard handler cannot call `csKeepClip(startSec, endSec, label, partNo)` without a DOM lookup
- No `.isReviewed` class or tracking set

**Current keyboard situation (confirmed in init.js:63–86):**
```javascript
document.addEventListener('keydown', function (e) {
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (_isTyping(e.target)) return;
  if (currentView !== 'editor') return;  // ← render view blocked here
  switch (e.code) { /* Space / I / O / Escape / Enter */ }
});
```

Result: **zero keyboard shortcuts in render view**.

**Current auto-next (confirmed):** Does not exist. `csKeepClip` calls `ClipSteering.lockClip`, shows toast, calls `v3RefreshSteeringPanel`. No focus or scroll advance.

**Click cost per clip (6-clip render example):**

| Action | Clicks | Mouse travel |
|---|---|---|
| Click clip 1 thumb → preview | 1 | medium |
| Click "Keep" on clip 1 | 1 | small |
| Scroll down to clip 2 | 0 | medium (wheel) |
| Click clip 2 thumb → preview | 1 | medium |
| Click "Avoid" on clip 2 | 1 | small |
| …repeat for clips 3–6… | +8 | +8 moves |
| **Total (6 clips)** | **12 clicks** | **high** |

With keyboard shortcuts + auto-next:

| Action | Keys | Mouse travel |
|---|---|---|
| Tab → focus clip 1 | 1 | none |
| K → Keep | 1 | none |
| (auto-next to clip 2) | — | none |
| A → Avoid | 1 | none |
| (auto-next to clip 3) | — | none |
| …repeat for clips 4–6… | +6 | none |
| **Total (6 clips)** | **12 keys, 0 clicks** | **zero** |

### 2.2 ReviewQueue view

**Current keyboard situation (confirmed in review-queue.js:133–139):**
```javascript
function handleKey(e, jobId) {
  if (['INPUT','TEXTAREA','SELECT'].includes(e.target?.tagName)) return;
  if (e.key === 'k' || e.key === 'K') { e.preventDefault(); keep(jobId); }
  if (e.key === 'f' || e.key === 'F') { e.preventDefault(); favorite(jobId); }
  if (e.key === 'd' || e.key === 'D') { e.preventDefault(); dismiss(jobId); }
  if (e.key === 'r' || e.key === 'R') { e.preventDefault(); retry(jobId); }
}
```

Cards have `tabindex="0"` and call `handleKey` on `onkeydown`. Shortcuts exist.

**The friction (confirmed in keep/favorite/dismiss functions):**
```javascript
function keep(jobId) {
  const item = _setState(jobId, STATE.KEPT);
  // ...
  _showToast('Kept', 'success');
  _refreshView();  // ← full re-render of list
}
```

`_refreshView()` calls `renderView()` which does `container.innerHTML = ...`. The acted-on card is removed from the "Ready to Review" section (it moves to "Kept"). The browser drops focus. The creator must find and click the next card manually.

**Click cost without auto-focus:**
- Keep card 1 with `K` → 0 clicks
- Find next card → 1 click (to focus it)
- Keep with `K` → 0 clicks
- Find next → 1 click
- **Total for 5 cards:** 5 keys + 5 clicks (to re-establish focus)

With auto-focus-next:
- Keep card 1 with `K` → 0 clicks, 1 key
- Auto-focus card 2 → 0 clicks
- Keep with `K` → 0 clicks, 1 key
- **Total for 5 cards:** 5 keys + 0 clicks

### 2.3 What is already good — do not touch

| Feature | Status | File |
|---|---|---|
| UX-R3-F: Auto-preview best clip on completion | ✅ Working | `render-ui.js:4755` |
| Hover video preview (mouseenter) | ✅ Working | `render-ui.js:4800` |
| Score tier headers (Best/Strong/Developing) | ✅ Working | `render-ui.js:4239` |
| ReviewQueue K/F/D/R per-card shortcuts | ✅ Working | `review-queue.js:133` |
| `render_output_badge` clip count | ✅ Working | `index.html:574` |
| Sort by score / part_no | ✅ Working | `render-ui.js:4859` |
| `_isTyping` guard pattern in init.js | ✅ Reusable | `init.js:67` |

---

## 3. KEYBOARD INTERACTION MODEL

### 3.1 Render view (clip cards)

**Prerequisite:** Clip cards need `tabindex="0"` to receive focus. Currently missing. Adding it is one HTML attribute change in the card template in `render-ui.js`.

**Data availability problem:** `csKeepClip(startSec, endSec, label, partNo)` requires `startSec` and `endSec`. These are in scope at card-build time (lines 4607–4608) but not stored anywhere accessible to a global keyboard handler. Solution: add `data-start-sec` and `data-end-sec` attributes to the card `<div>`.

```javascript
// Current (render-ui.js:4663):
return `<div class="${cardClass}" data-clip-status="..." data-part-no="${partNo}" data-aspect="...">`;

// After 72.1:
return `<div class="${cardClass}" data-clip-status="..." data-part-no="${partNo}" data-aspect="..."
             data-start-sec="${startSec}" data-end-sec="${endSec}" tabindex="0">`;
```

**Keyboard handler (extend init.js):**

Add a second branch inside the existing keydown IIFE for `currentView === 'render'`:

```javascript
if (currentView === 'render') {
  const card = document.activeElement?.closest?.('.clipCard.isDone');
  if (!card) return;  // shortcut only fires when a done clip card has focus
  const partNo   = Number(card.dataset.partNo || 0);
  const startSec = Number(card.dataset.startSec || 0);
  const endSec   = Number(card.dataset.endSec || 0);
  const label    = card.querySelector('.clipCardTitle')?.textContent?.trim() || 'clip' + partNo;

  switch (e.code) {
    case 'KeyK':
      if (typeof csKeepClip === 'function') csKeepClip(startSec, endSec, label, partNo);
      break;
    case 'KeyA':
      if (typeof csAvoidClip === 'function') csAvoidClip(startSec, endSec, label, partNo);
      break;
    case 'KeyD':
      card.querySelector('.renderClipActionLink')?.click();
      break;
  }
}
```

**Why `.clipCard.isDone` required:** Pending/failed cards have no Keep/Avoid/Download action. The `.isDone` class selector ensures the shortcut only fires on completed, actionable clips.

**Why no `e.preventDefault()`:** K/A/D do not have default browser behaviors to prevent. If `e.preventDefault()` is needed for a specific key (e.g., `Space`), it would be added per-case.

### 3.2 Shortcut map — render view

| Key | Action | Notes |
|---|---|---|
| `K` | Keep this clip | Requires focused `.clipCard.isDone` |
| `A` | Avoid this clip | Requires focused `.clipCard.isDone` |
| `D` | Download this clip | Triggers `.renderClipActionLink` click |
| `Tab` | Next card | Browser default with `tabindex` — free |
| `Shift+Tab` | Previous card | Browser default — free |

### 3.3 Shortcuts explicitly NOT added (with reasons)

| Key | Reason not included |
|---|---|
| `R` = Rerender | Rerender starts a full new job. The P0 in-flight guard (71.1) makes it safe but the action is too consequential for a one-key press with no confirmation. Download and Preview are much more common reviewer actions. |
| `Space` = Preview | Space requires `e.preventDefault()` (stops page scroll). Preview also requires knowing which preview panel to target. The existing thumb click + UX-R3-F auto-preview already handles this. Adding Space is P2. |
| `Arrow keys` = navigate | Arrow keys require `e.preventDefault()` to stop page scroll. Tab/Shift+Tab already provides free navigation once `tabindex` is on cards. Arrow keys are P2. |
| `F` = Favorite | The render view doesn't have a Favorite action on clip cards. Favorite is a ReviewQueue concept. |

### 3.4 ReviewQueue — no changes to existing shortcuts

The existing K/F/D/R shortcuts in `review-queue.js` are correct. Phase 72 only adds auto-focus behavior after those actions fire.

### 3.5 Conflict analysis

| Shortcut | Conflict with editor view? | Conflict with ReviewQueue? | Safe? |
|---|---|---|---|
| `K` (render) | No — editor has no K shortcut | No — review view is separate `currentView` | ✅ |
| `A` (render) | No — editor has no A shortcut | No | ✅ |
| `D` (render) | No — editor has no D shortcut | No — review `D=Dismiss` is different view | ✅ |
| Tab (render) | Already works in editor | No conflict | ✅ |

---

## 4. AUTO-NEXT MODEL

### 4.1 When to advance focus

| Action | Auto-next? | Reason |
|---|---|---|
| Keep | Yes → next isDone card | Creator has decided. Next clip is waiting. |
| Avoid | Yes → next isDone card | Creator has decided. Same reasoning. |
| Download | No — stay on card | Creator may want to preview again or also Keep/Avoid. Download is not always the final action. |
| Rerender | No — stay on card | Rerender starts a new job. Creator may want to watch the panel. Card itself stays visible. |
| Preview (thumb click) | No | Preview is informational — creator hasn't decided yet. |

### 4.2 Implementation — render view

Add `_r72AdvanceFocus(fromPartNo)` to `render-ui.js`:

```javascript
function _r72AdvanceFocus(fromPartNo) {
  var list = document.getElementById('render_output_list');
  if (!list) return;
  var cards = Array.from(list.querySelectorAll('.clipCard.isDone[tabindex="0"]'));
  var idx = cards.findIndex(function(c) { return Number(c.dataset.partNo) === fromPartNo; });
  var next = cards[idx + 1];
  if (next) {
    next.focus();
    next.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
}
```

Call from `csKeepClip` and `csAvoidClip` at the end of each function body:

```javascript
window.csKeepClip = function(startSec, endSec, label, partNo) {
  // ... existing code unchanged ...
  _r72AdvanceFocus(Number(partNo) || 0);  // ADD
};

window.csAvoidClip = function(startSec, endSec, label, partNo) {
  // ... existing code unchanged ...
  _r72AdvanceFocus(Number(partNo) || 0);  // ADD
};
```

**Why `querySelectorAll('.clipCard.isDone[tabindex="0"]')`:** Only advance through done clips (pending/failed are not actionable). The `[tabindex="0"]` selector ensures we only walk through cards that can receive focus — skipping any tier header divs inserted by UX-R3.

**Why `scrollIntoView({ block: 'nearest' })`:** `nearest` only scrolls if the card is out of view. If the next card is already visible, it doesn't scroll at all — minimizing visual distraction.

### 4.3 ReviewQueue auto-focus-next

Capture the next "Ready to Review" item's jobId before the state transition, then focus after re-render:

```javascript
function _getNextReviewId(currentJobId) {
  var ready = _sort(_items.filter(function(it) { return it.state === STATE.NEW; }));
  var idx = ready.findIndex(function(it) { return it.jobId === currentJobId; });
  var next = ready[idx + 1];
  return next ? next.jobId : null;
}
```

Call pattern in `keep()`, `favorite()`, `dismiss()`:

```javascript
function keep(jobId) {
  var nextId = _getNextReviewId(jobId);  // capture before state change
  var item = _setState(jobId, STATE.KEPT);
  if (!item) return;
  // ... existing log + steeringFeedback + CreatorSeries calls unchanged ...
  _showToast('Kept', 'success');
  _refreshView();
  if (nextId) setTimeout(function() {
    var el = document.querySelector('[data-rq-jobid="' + nextId + '"]');
    if (el) el.focus();
  }, 0);
}
```

The `setTimeout(0)` ensures the DOM is settled from `_refreshView()` before focus is attempted. `querySelector` by `data-rq-jobid` is the same pattern already used in `_cardHtml`.

**Same pattern applied to `favorite()` and `dismiss()`.**

**retry() and undismiss():** Do NOT advance. Retry starts a new async job. Undismiss restores a card — creator may want to act on it immediately.

### 4.4 Trust rule: auto-next never skips

Auto-next advances focus to the next card. It does NOT:
- Make any decision about the next card
- Trigger any action on the next card
- Skip cards that haven't loaded yet

The creator sees the next card highlighted and chooses what to do. If they don't want to act, they do nothing. If they want to go back, `Shift+Tab` returns to the previous card.

---

## 5. MOMENTUM MODEL

### 5.1 Progress counter — render view

**What to show:** After clip review actions (Keep, Avoid, Download), a lightweight counter updates in the `renderOutputHeader` area:

```
Clips  [3]           Best first ▾   [Open Folder]
X reviewed
```

The counter line (`X reviewed`) appears below the title row after the first action. It resets on new render (same as `_selectedClipPaths` which is cleared in `clearRenderOutputPanel`).

**Implementation:**
```javascript
// Module-level in render-ui.js:
let _r72ReviewedPartNos = new Set();

// Clear in clearRenderOutputPanel (same location as _selectedClipPaths reset):
_r72ReviewedPartNos = new Set();

// Update in csKeepClip, csAvoidClip (after action fires):
_r72ReviewedPartNos.add(Number(partNo) || 0);
_r72UpdateReviewCounter();

// Also update on download (add to onclick in download button template):
// _r72ReviewedPartNos.add(${partNo}) — embedded in inline onclick

function _r72UpdateReviewCounter() {
  var el = document.getElementById('r72ReviewCounter');
  if (!el) return;
  var total = document.querySelectorAll('#render_output_list .clipCard.isDone').length;
  var n = _r72ReviewedPartNos.size;
  el.textContent = n > 0 ? n + ' reviewed' + (total > 0 ? ' of ' + total : '') : '';
  el.style.display = n > 0 ? '' : 'none';
}
```

The element `id="r72ReviewCounter"` is injected once into `#render_output_path` (the div immediately below the header — already exists in index.html:584, currently used to show the output file path).

**Deliberately minimal:** No dashboard, no progress bar, no percentage, no stars. One line of text. When the creator has reviewed all clips, the counter reads "6 reviewed of 6". That is the closure signal.

**Session-only:** `_r72ReviewedPartNos` is a Set in module scope. It survives re-renders of the clip list (like `_selectedClipPaths` does) but is cleared on new job start. No localStorage.

### 5.2 ReviewQueue — momentum already exists

The ReviewQueue nav badge already shows the count of "new" items. As the creator acts on clips, the badge number decreases. When it hits 0, the "All caught up" empty state appears. No changes needed here.

### 5.3 What momentum must NOT do

| Action | Why forbidden |
|---|---|
| Auto-sort by "not reviewed" first | Changes the ranking display. Creator's mental model of clip order must stay stable. |
| Dim reviewed clips | Reduces visibility of clips the creator may want to re-examine or compare. |
| Play animation on completion | "All done" animations are cute but distracting. The counter is enough. |
| Persist reviewed state cross-session | If the creator leaves and returns, they see fresh clip cards. That's correct — the render context is different. |

---

## 6. TRUST & UX RULES

### 6.1 Never move focus without intent

Auto-next fires on Keep and Avoid because the creator has explicitly made a decision. It does NOT fire on:
- Download (decision may not be final)
- Rerender (job is being queued)
- Preview (browsing, not deciding)

If the creator wants to revisit a clip, Shift+Tab returns. No decision is hard to undo.

### 6.2 Keyboard guard is not negotiable

The `_isTyping` check from init.js:

```javascript
function _isTyping(el) {
  if (!el) return false;
  const t = el.tagName;
  return t === 'INPUT' || t === 'TEXTAREA' || t === 'SELECT' || !!el.isContentEditable;
}
```

This guard is already in place and works. The render-view shortcut handler uses the same guard. `K` must never fire if the creator is typing in a search field or any input.

Additionally: the render-view shortcut only fires when `document.activeElement?.closest?.('.clipCard.isDone')` is non-null. This means if the creator clicks on any non-card element, no shortcut fires. The shortcut is card-scoped, not global.

### 6.3 No global shortcuts in render view

Unlike the editor view where Space/I/O are global (always fire when editor is open), the render-view shortcuts only fire when a clip card has focus. This is stricter and safer. It matches how ReviewQueue already works.

### 6.4 Rerender is not a keyboard shortcut

`csKeepAndRerender` starts a new render job. Even with the Phase 71 in-flight guard, triggering this from a keyboard shortcut with a single key press creates too much risk of accidental rerender. It remains mouse-only (clicking the ↻ Rerender button in the steer row).

### 6.5 Avoid state desync

Clip cards are rebuilt on every WebSocket poll during an active render. `_r72ReviewedPartNos` is a Set keyed by `partNo`, which is stable across re-renders (it's the server-assigned segment number). After rebuild, the class `.isReviewed` is NOT re-applied (adding it would require walking the DOM after each rebuild). The counter is updated from the Set size, which is stable. This avoids the fragile pattern of depending on DOM classes that get wiped on each render update.

---

## 7. PRIORITY MATRIX

### P0 — Ship blocker
*(None — review friction is not a blocker for V1 ship)*

### P1 — Should ship in Phase 72

| Fix | Why | Commit |
|---|---|---|
| `tabindex="0"` + `data-start-sec` + `data-end-sec` on clip cards | Prerequisite for all keyboard interaction | 72.1 |
| K/A/D keyboard shortcuts in render view (init.js) | Eliminates mouse dependency for the 3 most common review actions | 72.1 |
| `_r72AdvanceFocus()` in `csKeepClip` / `csAvoidClip` | Removes most repetitive step in review loop | 72.1 |
| ReviewQueue auto-focus-next after Keep/Favorite/Dismiss | Removes focus-jump friction that kills keyboard momentum | 72.2 |

### P2 — Nice to have, ship without if needed

| Fix | Why | Commit |
|---|---|---|
| `_r72ReviewedPartNos` counter in render view header | Gives creator closure signal and progress sense | 72.3 |
| Arrow key navigation in render view | Convenience — Tab/Shift+Tab already works once tabindex added | Not in Phase 72 |
| Space = preview focused clip | Convenience — thumb click already works | Not in Phase 72 |
| R = Rerender keyboard shortcut | P2 feature, risk of accidental trigger | Not in Phase 72 |

### Not in Phase 72

| Item | Reason |
|---|---|
| Reorder clips by "reviewed" state | Changes ranking display — breaks creator mental model |
| Persistent reviewed state (localStorage) | Ephemeral is correct — context is session-specific |
| Keyboard shortcut for Rerender | Too consequential for single-key accident |
| New review UI panels or dashboards | Redesign — out of scope |
| Changes to clip ranking or score display | Ranking is fixed post-Phase 65 |

---

## 8. COMMIT PLAN

| # | Commit message | Files | Change | P-level |
|---|---|---|---|---|
| 1 | `review(72.1): clip card keyboard focus and K/A/D shortcuts` | `render-ui.js`, `init.js` | `tabindex="0"` + `data-start-sec` + `data-end-sec` on card; `_r72AdvanceFocus()`; extend init.js keydown IIFE with render-view branch | P1 |
| 2 | `review(72.2): ReviewQueue auto-focus next card after action` | `review-queue.js` | `_getNextReviewId()` helper; focus-after-refresh in `keep()`, `favorite()`, `dismiss()` | P1 |
| 3 | `review(72.3): reviewed clip progress counter` | `render-ui.js` | `_r72ReviewedPartNos` Set; `_r72UpdateReviewCounter()`; DOM update in `clearRenderOutputPanel` and action handlers | P2 |

**Total: 3 commits, 3 files. Zero backend changes. Zero ranking changes. Zero UX redesign.**

---

## 9. DEFINITION OF DONE

### Keyboard and focus

- [ ] Tab key advances focus through `isDone` clip cards in the render view
- [ ] `K` key on a focused clip card calls `csKeepClip` for that card
- [ ] `A` key on a focused clip card calls `csAvoidClip` for that card
- [ ] `D` key on a focused clip card triggers the Download link for that card
- [ ] No shortcut fires when focus is in a text input (`_isTyping` guard confirmed)
- [ ] No shortcut fires when no clip card is focused (global key does nothing)
- [ ] Shortcuts do not fire in editor view (`currentView === 'editor'` guard unchanged)

### Auto-next

- [ ] After clicking Keep on clip N, focus moves to clip N+1
- [ ] After pressing `K` on clip N, focus moves to clip N+1
- [ ] After clicking Avoid on clip N, focus moves to clip N+1
- [ ] After pressing `A` on clip N, focus moves to clip N+1
- [ ] After clicking Download, focus stays on current card
- [ ] After clicking Rerender, focus stays on current card
- [ ] When clip N is the last done clip, auto-next does nothing (no error)

### ReviewQueue auto-focus

- [ ] After `K` on ReviewQueue card N, card N+1 in "Ready to Review" receives focus
- [ ] After `D` (Dismiss) on ReviewQueue card N, card N+1 receives focus
- [ ] After `F` (Favorite) on ReviewQueue card N, card N+1 receives focus
- [ ] If card N was the last in "Ready to Review", no focus is set (graceful no-op)
- [ ] Retry and Undismiss do not trigger auto-focus

### Progress counter (P2)

- [ ] Counter hidden before any action is taken
- [ ] Counter appears as "1 reviewed of N" after first Keep/Avoid/Download
- [ ] Counter updates correctly after each action
- [ ] Counter resets to hidden on new render job (clearRenderOutputPanel)

### Regression checks

- [ ] Phase 69 ScorePreference: Keep/Avoid/Download signals unaffected
- [ ] Phase 70 DurationPreference: Keep/Avoid/Download signals unaffected
- [ ] Phase 71 in-flight guard: Rerender from keyboard shortcut blocked correctly
- [ ] Phase 67 ClipSteering: lock/exclude unaffected by auto-next
- [ ] UX-R3-F auto-preview best clip: still fires once on completion
- [ ] Hover video preview: still works on mouseenter
- [ ] ReviewQueue existing K/F/D/R shortcuts: unaffected
- [ ] Sort by score / by part_no: unaffected
- [ ] Normal single render: submit and track unaffected
- [ ] Batch render: unaffected

---

## What Phase 72 does NOT change

| Item | Status |
|---|---|
| Clip ranking / ordering | **Unchanged** |
| Score / tier headers (Best/Strong/Developing) | **Unchanged** |
| Steer row (Keep/Avoid/Rerender buttons) | **Unchanged** — keyboard shortcuts are additions, not replacements |
| csKeepClip / csAvoidClip logic | **Unchanged** — only `_r72AdvanceFocus()` call appended |
| ReviewQueue K/F/D/R shortcut logic | **Unchanged** — only auto-focus appended after existing logic |
| Preview behavior | **Unchanged** |
| Download behavior | **Unchanged** — D key simulates the same click |
| Creator preferences (ScorePreference, DurationPreference) | **Unchanged** |
| Creator memory (ClipSteering, DNA, Feedback) | **Unchanged** |
| Any Phase 63–71 feature | **Unchanged** |

## What Phase 72 defers

| Item | Reason |
|---|---|
| Arrow key navigation in render view | Tab/Shift+Tab works free; arrows need preventDefault; P2 |
| Space = preview focused clip | Preview already works via click/hover; P2 |
| Rerender keyboard shortcut | Too consequential for single-key with no confirmation |
| Persistent reviewed state | Ephemeral is correct for session context |
| Clip reordering by review state | Would change ranking perception |
| New review dashboard or panels | Out of scope — new capability |

---

*Phase 72 plan based on live code audit of `render-ui.js`, `init.js`, `review-queue.js`, `index.html`.*
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*
