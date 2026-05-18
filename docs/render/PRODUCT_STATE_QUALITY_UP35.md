# PRODUCT STATE — QUALITY-UP35: Reliability+

**Branch:** `feature/ai-output-upgrade`
**Commit:** `feat(render): reliability hardening`
**Status:** Shipped

---

## Summary

Production hardening phase. Moves from "usually reliable" to "creator-trust reliable."

Fixes the retry payload bug (retries were rebuilding from current form state, not the original submitted payload), adds frontend stall detection for long-running jobs, and surfaces clearer trust signals on recovered/stalled items in the batch queue.

**Creator experience:** "I can trust overnight batch runs to use the right settings and tell me if something went wrong."

---

## Philosophy

- **NO new intelligence.** NO feature expansion. NO architecture rewrite.
- **NO pipeline reorder.** NO new dependencies. NO model changes. NO render slowdown.
- **Fix real bugs.** The retry bug was the most concrete reliability failure: retrying a job silently used different settings than the original.
- **Warn, don't block.** Stall detection shows a warning chip; it does not cancel or retry automatically.
- **Advisory surface.** "Review Suggested" links to the review queue. Creator decision always wins.
- **Pure frontend.** All changes in batch-queue.js and review.css. Zero backend changes.

---

## Root Cause Audit (STEP 0)

### Confirmed bugs

| Issue | Root Cause | Fix |
|---|---|---|
| Retry uses wrong payload | `retryItem()` called `_submitItem()` which called `_buildPayload()` reading current form fields, not original submitted settings | `retryItem()` uses `item._payload` snapshot directly via new `_submitWithPayload()` |
| No frontend stall detection | `_tick()` polls active items but never checks elapsed time — items stuck in RUNNING show "Running" indefinitely | Track `item._lastProgressAt`, warn after `STALL_WARN_MS` (5 min) with no progress change |

### Confirmed correct (no fix needed)

- Backend stall detection: exists (`_stall_deadline()` in render_pipeline.py) — backend side is covered
- Quality checks: `_assess_output_quality()` runs and logs warnings; not in job status API but already shown via job message for partial failures
- `ReviewQueue.retry()`: intentionally just shows a toast — retry from review requires re-opening the render form, by design
- Cancel flow: correct and unaffected
- Poll interval and `_stopPollIfDone()`: correct

---

## Architecture

### Changes (frontend only)

#### `_submitWithPayload(item, payload)` — new helper

Submits a payload directly to `/api/render/process` without calling `_buildPayload()`. Used by retry path only. Preserves the stored `item._payload` snapshot so the same settings are reused.

#### `retryItem(id)` — fixed

```
old: retryItem → _submitItem → _buildPayload (reads current form)
new: retryItem → reads item._payload → _submitWithPayload (uses snapshot)
               ↳ fallback: _submitItem if no snapshot (new items)
```

Logs `retry_snapshot: {name} (payload snapshot used)`.

#### Stall detection

```
STALL_WARN_MS = 300000  (5 minutes)

per-item: item._lastProgressAt updated when item.progress changes
_tick(): for each RUNNING/QUEUED item:
  if (!stalled && now - _lastProgressAt > STALL_WARN_MS):
    item.stalled = true
    log queue_stall once per batch session
```

#### UI chips

| Condition | Chip |
|---|---|
| `item.stalled === true` | Amber warning line: "No progress for 5+ min — may be stalled. Cancel and retry if needed." |
| `item.status === 'recovered'` | Blue hint line: "Review suggested [Open Review →]" |
| `item.status === 'recovered'` | Card border: amber accent via `.bq-stalled` |

---

## Parts

### Part A — Output sanity surface

Backend already runs `_assess_output_quality()` and logs quality warnings per-part. These are emitted as WebSocket events and stored in job logs. The frontend surfaces partial failures via the `RECOVERED` status (existing) and now adds a "Review Suggested" link on recovered cards.

### Part B — Retry hardening

`retryItem()` now uses `item._payload` (set at original submission time) instead of calling `_buildPayload()` which reads current form fields. If no snapshot exists (edge case: pre-UP35 item), falls back to `_submitItem()` with a log note.

### Part C — Overnight safety

Frontend stall detection: after 5 minutes with no `progress_percent` change on a RUNNING item, `item.stalled = true` is set and a warning chip appears. `queue_stall` is logged once per batch session. Stall flag clears automatically when progress resumes.

`_queueStallLogged` resets when the batch completes, so a new batch session gets fresh detection.

### Part D — UI trust

Two new inline lines inside batch cards (no new overlays):
- **Stall warning** (amber): shown when `item.stalled && (RUNNING || QUEUED)`
- **Review Suggested** (blue): shown for all `RECOVERED` items with a direct link to the review tab

Cards with stall warning get a subtle amber border via `.bq-stalled` CSS class.

### Part E — Logging

| Log event | When | Contains |
|---|---|---|
| `retry_snapshot` | Retry fires | Item name + `(payload snapshot used)` or `(rebuilt from form)` |
| `queue_stall` | First item crosses 5-min stall threshold | Count of stalled items + threshold |
| `recovery_loop` | Batch completes with 1+ recovered items | Count recovered / total |

### Part F — Performance

All checks are O(n) timestamp comparisons in JavaScript. No API calls added. No new polling. No ffprobe from frontend. Stall detection runs inside the existing 2-second poll tick.

---

## Files Changed

### Modified Files

| File | Change |
|---|---|
| `backend/static/js/batch-queue.js` | `retryItem()` fix; `_submitWithPayload()` new helper; stall detection in `_tick()`; stall/recovered chips in `_cardHtml()`; `recovery_loop` log |
| `backend/static/css/v3/review.css` | `.bqCardWarn`, `.bqCardStall`, `.bqCardReviewSuggested`, `.bqCard.bq-stalled` styles |

### New Files

| File | Purpose |
|---|---|
| `docs/render/PRODUCT_STATE_QUALITY_UP35.md` | This document |

---

## Manual QA Checklist

### A — Retry uses correct payload

- [ ] Queue a file; set subtitle_style to "pro_karaoke" on the form; Submit
- [ ] Wait for it to run; then change form subtitle_style to "tiktok_bounce_v1"
- [ ] After job fails (or force to failed state): click Retry
- [ ] Log shows `retry_snapshot: {name} (payload snapshot used)`
- [ ] The retry uses "pro_karaoke" — NOT the new "tiktok_bounce_v1" setting
- [ ] Rendered output matches original settings

### B — Stall detection warning appears

- [ ] Queue a file; it enters RUNNING state
- [ ] Simulate no progress for >5 min (or temporarily set `STALL_WARN_MS = 10000` for testing)
- [ ] Card shows amber warning: "No progress for 5+ min — may be stalled. Cancel and retry if needed."
- [ ] Log shows `queue_stall: 1 item(s) stuck >5min with no progress`
- [ ] When progress resumes: `item.stalled` clears, amber warning disappears on next render

### C — Recovery_loop log fires

- [ ] Run a batch where 1+ items end as RECOVERED
- [ ] When last item completes: log shows `recovery_loop: N of M item(s) used safe fallback — recommend review`

### D — Review Suggested chip on recovered items

- [ ] Item completes as RECOVERED
- [ ] Card shows blue "Review suggested — Open Review →" line
- [ ] Clicking "Open Review →" navigates to review tab

### E — No regressions

- [ ] Normal render: no stall chip, no recovery line
- [ ] Cancel flow: unchanged
- [ ] New item submission: `_buildPayload()` still called (retry fix only affects retry path)
- [ ] No console errors
- [ ] DNA, Series, Consistency hints all still show independently
- [ ] History, settings, review queue unaffected
