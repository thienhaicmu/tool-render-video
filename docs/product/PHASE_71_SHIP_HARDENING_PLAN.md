# PHASE 71 — SHIP HARDENING PLAN
## Production Readiness: Fallbacks, Guards, Graceful Degradation

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 70 Duration Preference — COMPLETE, zero regressions
**Plan date:** 2026-05-19
**Planning only — no implementation in this session**

---

## 1. EXECUTIVE SUMMARY

Phases 63–70 added substantial capability: explainability, multi-phase creator memory, feedback visibility, score preference learning, and duration learning. The render engine and UI are functionally complete. What remains is making them **hard to break under real-world conditions**.

This plan audits actual failure modes found in the codebase — not hypothetical ones — and defines specific, low-risk fixes scoped to the frontend JS layer where possible. Backend changes are flagged but deferred unless trivially safe.

**The creator's question Phase 71 eliminates:**
> "What happens if this breaks?"

**Three real gaps confirmed by code audit:**

1. **Double render submission** — `startRenderFromEditor()` is guarded on the `evStartBtn` button, but `v3TriggerRerender()` and other callers can fire it concurrently. No global in-flight flag exists. Two concurrent `await _submitRenderPayload(...)` calls create duplicate jobs writing to the same output.

2. **Silent input misconfiguration** — `min_part_sec > max_part_sec` is accepted by the frontend with no warning; the backend silently swaps the values. `min_part_sec = 0` is similarly coerced to 10s silently. User never knows their config was corrected.

3. **Silent preference data loss** — All six localStorage preference modules (`clip-steering.js`, `score-preference.js`, `duration-preference.js`, `creator-taste.js`, `creator-feedback.js`, `creator-series.js`) have `try { localStorage.setItem(...) } catch {}` with empty catch blocks. When browser storage quota is exceeded, every preference write silently fails. The user loses all cross-session data with no notice.

**Implementation scope:** 3 commits. All frontend JS. Zero backend changes. Zero ranking changes. Zero UX redesign. Strictly defensive.

---

## 2. FAILURE AUDIT MATRIX

### Confirmed by code — frontend scope

| # | Failure | File | Lines | Severity | Type |
|---|---|---|---|---|---|
| F1 | `startRenderFromEditor` re-entrant via `v3TriggerRerender` + `csKeepAndRerender` — no in-flight guard | `editor-view.js:342–347`, `render-ui.js:4542–4553` | P0 | State |
| F2 | `min_part_sec > max_part_sec` submitted to backend, swapped silently, no user feedback | `editor-view.js:2261–2262`, `segment_builder.py:356–357` | P1 | Validation |
| F3 | `min_part_sec = 0` submitted, backend coerces to 10s silently | `editor-view.js:2261`, `segment_builder.py:359` | P1 | Validation |
| F4 | localStorage `_save()` quota exceeded — empty `catch {}` on all 6 modules | All preference `*.js` files | P1 | Reliability |
| F5 | localStorage `_load()` JSON corruption — silent fallback, user doesn't know data was lost | All preference `*.js` files | P1 | Reliability |
| F6 | Upload: no client-side file size check before upload starts — user waits for large upload then render fails mid-process | upload handler in `render-ui.js` / form | P1 | UX |
| F7 | Batch poll timer never cleared after all jobs complete — polling indefinitely every 2s | `batch-queue.js` | P2 | Performance |
| F8 | Stall message "No progress for Xs" with no action path — creator doesn't know what to do | `render-ui.js:513` | P2 | UX |
| F9 | `_r67ApplyDuration` / `_r70DismissDuration` — no guard if evMinPart/evMaxPart DOM elements absent | `editor-view.js:289–299, 338–340` | P2 | Resilience |

### Confirmed by code — backend scope (deferred, out of Phase 71)

| # | Failure | File | Notes |
|---|---|---|---|
| B1 | File upload: no server-side size check; disk full → partial file written, 200 returned | `backend/app/routes/upload.py:807–834` | Backend change — deferred |
| B2 | Batch cancel stops new submissions but running child continues up to 2h | `backend/app/routes/render.py` batch cancel | Requires process management change — deferred |
| B3 | `clip_exclude` filtering can remove all scored segments post-ranking → late failure after full pipeline ran | `backend/app/orchestration/render_pipeline.py` | Backend logic — deferred |
| B4 | Whisper `model.transcribe()` has no timeout; preview endpoint hangs indefinitely on malformed audio | `backend/app/routes/render.py:568–584` | Backend async/timeout — deferred |

### Confirmed working — no action needed

| System | Status |
|---|---|
| `evStartBtn` disabled before `await _submitRenderPayload` | Working — synchronous disable at line 2487 prevents Start button double-click |
| Session null pre-flight check | Working — `editor-view.js:2183–2190` validates `_ev.sessionId` and returns with error |
| Output dir pre-flight check | Working — `editor-view.js:2468–2476` validates and returns with toast |
| Voice text validation | Working — `editor-view.js:2333–2342` guards empty voice text |
| Stall heartbeat detection (45s) | Working — `render-ui.js:472–513` surfaces stall state |
| Error messaging (`friendlyRenderError`) | Working — `editor-view.js:2525–2527` maps technical errors to readable messages |
| All localStorage modules: `_load()` try/catch | Working — returns empty state on failure (silent but safe) |
| Backend min/max swap | Working silently — `segment_builder.py:356–357` — just needs user visibility |

---

## 3. SAFE FALLBACK MODEL

### F1: In-flight render guard

**Problem:** `v3TriggerRerender()` (`editor-view.js:342`) calls `startRenderFromEditor()` directly. `csKeepAndRerender()` calls `v3TriggerRerender()`. A creator who clicks **Rerender** twice in quick succession (or whose click fires twice due to lag) can trigger two concurrent `await _submitRenderPayload()` calls. Both submit identical payloads; both get job IDs; both write to the same output directory.

**Fix:** Add a module-level `_r71RenderSubmitInFlight` boolean flag to `editor-view.js`. Set it `true` at the top of `startRenderFromEditor()` before any validation. Clear it `false` in both the success path and the error path. Guard `v3TriggerRerender()` with a check: if in-flight, show toast "Render already queued" and return.

```javascript
let _r71RenderSubmitInFlight = false;

function v3TriggerRerender() {
  if (_r71RenderSubmitInFlight) {
    if (typeof showToast === 'function') showToast('Render already queued', 'info');
    return;
  }
  if (typeof startRenderFromEditor === 'function' && typeof _ev !== 'undefined' && _ev.sessionId) {
    startRenderFromEditor();
  } else if (typeof showToast === 'function') {
    showToast('Open a video in the editor first, then use ▶ Start Render', 'info');
  }
}

async function startRenderFromEditor() {
  if (_r71RenderSubmitInFlight) {
    if (typeof showToast === 'function') showToast('Render already queued', 'info');
    return;
  }
  _r71RenderSubmitInFlight = true;
  try {
    // ... existing body unchanged ...
  } finally {
    _r71RenderSubmitInFlight = false;
  }
}
```

**Fallback behavior:** Second Rerender click → "Render already queued" toast → dismissed. No duplicate job. No confusing state.

### F2 + F3: min/max clip duration validation

**Problem:** `editor-view.js:2261–2262` reads `evMinPart.value` and `evMaxPart.value` as numbers and sends them to the backend with no validation. Backend silently corrects:
- `min > max` → swapped, no notification
- `min = 0` → coerced to 10s, no notification

The creator submitted a config they believe is correct, but the render ran with different settings. Trust eroded.

**Fix:** Add explicit validation in `startRenderFromEditor()` immediately after line 2262:

```javascript
const minPart = Number(qs('evMinPart').value) || 0;
const maxPart = Number(qs('evMaxPart').value) || 0;
if (minPart > 0 && maxPart > 0 && minPart >= maxPart) {
  const _mmMsg = `Min clip (${minPart}s) must be less than max clip (${maxPart}s).`;
  qs('evStatusLine').textContent = _mmMsg;
  qs('evStatusLine').style.color = '#ef4444';
  qs('evStartBtn').disabled = false;
  qs('evStartBtn').textContent = '▶ Start Render';
  if (typeof showToast === 'function') showToast(_mmMsg, 'error');
  _r71RenderSubmitInFlight = false;
  return;
}
if (minPart === 0 || maxPart === 0) {
  const _zeroMsg = 'Min and max clip length must be greater than 0.';
  qs('evStatusLine').textContent = _zeroMsg;
  qs('evStatusLine').style.color = '#ef4444';
  qs('evStartBtn').disabled = false;
  qs('evStartBtn').textContent = '▶ Start Render';
  if (typeof showToast === 'function') showToast(_zeroMsg, 'error');
  _r71RenderSubmitInFlight = false;
  return;
}
```

**Fallback behavior:** Inverted min/max → red status line with plain-language correction → render not submitted → creator fixes and clicks Start Render again. No hidden correction.

### F4 + F5: localStorage save failure warning

**Problem:** All six preference modules have:
```javascript
function _save(d) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(d)); } catch (_) {}
}
```
When `localStorage.setItem` throws (quota exceeded, private browsing restriction, browser policy), the preference is lost silently. The user continues the session believing their keeps and downloads are being remembered. On next session, everything is gone.

**Fix:** Replace the empty catch with a `console.warn`. This is the minimal observable signal. A toast would be intrusive (storage full during normal use is edge-case enough). `console.warn` is sufficient to let a developer or a creator with devtools open see what happened.

```javascript
function _save(d) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify(d));
  } catch (_) {
    console.warn('[preference] localStorage write failed — storage may be full or restricted');
  }
}
```

Apply to all six modules: `clip-steering.js`, `score-preference.js`, `duration-preference.js`, `creator-taste.js`, `creator-feedback.js`, `creator-series.js`.

**Fallback behavior:** Storage write fails → preference not persisted → creator's previous session data still loads fine (read was not affected) → console.warn visible in devtools → no UX interruption.

### F6: Upload file size pre-flight warning

**Problem:** The upload handler in the frontend doesn't check `file.size` before starting the upload. A creator who uploads a 10GB podcast video waits for the full upload to complete, gets a 200 response, then watches the render fail somewhere deep in the pipeline. All of this could have been warned within 1 second of file selection.

**Fix:** In the upload form's file selection handler, add a size check. The browser's `File` object always provides `.size` in bytes for local files.

```javascript
const MAX_UPLOAD_SIZE_BYTES = 4 * 1024 * 1024 * 1024; // 4 GB practical limit
if (file.size > MAX_UPLOAD_SIZE_BYTES) {
  const sizeMB = Math.round(file.size / 1024 / 1024);
  const _sizeMsg = `File is ${sizeMB}MB — very large files may cause render timeouts. Consider trimming first.`;
  if (typeof showToast === 'function') showToast(_sizeMsg, 'info');
  // Do not block — show warning, allow upload to proceed
}
```

This is a **warning only** — it does not block the upload. The render engine may succeed with large files. The goal is to set expectations, not gatekeep.

**Fallback behavior:** Large file selected → informational toast → upload proceeds → creator is aware of risk → no surprise failure.

### F7: Batch poll cleanup

**Problem:** `batch-queue.js` poll timer runs every 2 seconds, checking status on all queued items. It is never stopped, even after all items reach a terminal state (`done`, `failed`, `completed_with_errors`). After a 50-item batch completes, the browser continues making 25+ API calls per minute indefinitely until the tab is closed.

**Fix:** In the poll callback, check if all items are in terminal state. If so, stop the timer.

```javascript
// Inside the poll callback, after updating item states:
const allDone = _items.every(function(item) {
  return item.status === STATUS.DONE || item.status === STATUS.FAILED || item.status === STATUS.CANCELLED;
});
if (allDone && _pollTimer) {
  clearInterval(_pollTimer);
  _pollTimer = null;
}
```

**Fallback behavior:** All batch jobs complete → poll timer cleared → no unnecessary API traffic → browser memory freed.

### F8: Stall message actionability

**Problem:** `render-ui.js:513` currently shows:
```
"No progress update for 45s — render may be stalled"
```
This is accurate but offers no action path. The creator doesn't know whether to wait, cancel, or check logs.

**Fix:** Add a "Cancel Render" link or guidance text alongside the stall message in `updateRenderMonitorHeartbeat()`:
```javascript
// When stalled:
heartbeat.innerHTML = `No progress for ${Math.floor(noProgressMs / 1000)}s — `
  + `<span style="opacity:0.7">render may be stalled · </span>`
  + `<button ... onclick="cancelCurrentJob()">Cancel</button>`;
```

**Note:** This requires confirming `cancelCurrentJob()` exists. If it does, wire it. If not, use text only: "Check logs or cancel the render."

### F9: Duration hint DOM guard

**Problem:** `_r67ApplyDuration(mn, mx)` and `_r70DismissDuration()` assume `evMinPart`/`evMaxPart` exist in the DOM. If called in a state where the editor hasn't fully mounted (e.g., hint button clicked before layout completes), a null reference could throw.

**Fix:** Both functions already have `if (minEl)` / `if (maxEl)` guards for the input elements. The issue is `_r70_ensureDurationHintEl()` which could be called before the `evMaxPart` label is in the DOM. This is unlikely in practice but the fallback path (returns `null`) is not guarded in `_r70SyncDurationHint`. Add:

```javascript
function _r70SyncDurationHint() {
  if (typeof DurationPreference === 'undefined') return;
  var pref = DurationPreference.getPreference();
  var el = _r70_ensureDurationHintEl();
  if (!el) return;  // guard already exists
  // ... rest unchanged
}
```

This guard IS already present (`if (!el) return`). No fix needed for F9 — it's already handled.

---

## 4. ERROR UX RULES

### Tone principles

| Situation | Correct copy | Wrong copy |
|---|---|---|
| min > max | `"Min clip (40s) must be less than max clip (30s)."` | `"ValidationError: min_part_sec exceeds max_part_sec"` |
| Render already in flight | `"Render already queued"` | `"Cannot submit: _r71RenderSubmitInFlight=true"` |
| Zero min/max | `"Min and max clip length must be greater than 0."` | `"Value 0 rejected by schema validator"` |
| Large file | `"Very large files may cause render timeouts."` | `"File too large"` (implies rejection when it doesn't block) |
| localStorage fail | *(console.warn only — not shown to user)* | N/A — not surfaced in UI |

### Error display rules

1. **Short sentences.** One sentence per error. No paragraph explanations.
2. **Actionable.** Tell the creator what to change, not what the system expected.
3. **No jargon.** No field names, no stack trace fragments, no variable names.
4. **Red status line + toast.** Both channels used for errors that block the render.
5. **Re-enable Submit.** Every early-return error path must re-enable `evStartBtn` and restore its label to `▶ Start Render`.
6. **Clear `_r71RenderSubmitInFlight = false`.** Every early-return path in `startRenderFromEditor` must release the in-flight lock, or Start Render becomes permanently disabled until page reload.

---

## 5. STATE HARDENING PLAN

### The in-flight lock pattern

The core anti-pattern across the codebase is: **action handlers with no idempotency guard**. The fix is a single shared boolean:

```javascript
// editor-view.js — module scope
let _r71RenderSubmitInFlight = false;
```

This one flag, placed in two guards (`startRenderFromEditor` + `v3TriggerRerender`), eliminates:
- Double render from rapid Rerender button clicks
- Double render from keyboard shortcut + button
- Double render from Rerender firing during slow network submission

**Lock discipline:** The flag MUST be cleared in every exit path of `startRenderFromEditor`:
- Early return: validation fail → `_r71RenderSubmitInFlight = false` before `return`
- Success path: render queued → `_r71RenderSubmitInFlight = false`
- Error path: API error → `_r71RenderSubmitInFlight = false`
- The cleanest implementation: wrap the body in a `try { ... } finally { _r71RenderSubmitInFlight = false; }`

### Preference module save-failure contract

All six preference modules follow the same IIFE pattern. The `_save()` function should follow a consistent contract:
```
try { setItem } catch { console.warn(moduleId + ' write failed') }
```
This ensures any storage failure is observable in devtools during debugging without interrupting the UI.

### Stall state clarity

The existing stall detection is correct. The gap is UX — creator sees a number counting up but no guidance. The minimum fix: change the heartbeat message when `cancelCurrentJob` is available to include a cancel action. When not available, add: `"· Check logs or cancel and retry"`.

---

## 6. PERFORMANCE GUARDRAILS

### Already in place (no action needed)

| Guard | Location | Value |
|---|---|---|
| FFmpeg wall-clock timeout | `render_engine.py:43` | Default 3600s (1 hour), env-configurable |
| Render stall detection | `render-ui.js:472` | 45s no-progress → shows stall state |
| Max parallel parts | `editor-view.js:2289` | `payload.max_parallel_parts = 0` (adaptive) |
| ClipSteering signal cap | `clip-steering.js:3` | `MAX_ENTRIES = 10`, 72h TTL |
| ScorePreference signal cap | `score-preference.js:5` | `MAX_SIGNALS = 30`, 30-day TTL |
| DurationPreference signal cap | `duration-preference.js:5` | `MAX_SIGNALS = 30`, 30-day TTL |

### Missing (Phase 71 scope)

| Gap | Fix | Risk |
|---|---|---|
| Batch poll runs forever after completion | Clear interval when all items terminal | Trivial — stops network waste |
| No client-side file size warning | Toast when `file.size > 4GB` (warning, not block) | Zero — informational only |

### Deferred (backend scope, not Phase 71)

| Gap | Where | Why deferred |
|---|---|---|
| Upload: no server-side size limit | `upload.py` | Requires FastAPI streaming limit config; could break valid large uploads |
| Batch cancel: child process not killed | `render.py` | Requires `subprocess.kill()` wiring in job runner — significant change |
| Whisper transcription: no timeout | `render.py:568` | Requires `asyncio.wait_for()` or threading timeout — significant change |
| Unknown-duration stall: 1-hour wall clock | `render_pipeline.py` | Already has stall detection; a tighter limit risks killing slow legitimate renders |

---

## 7. PRIORITY MATRIX

### P0 — Ship blocker

| Fix | Why blocker | Commit |
|---|---|---|
| In-flight render guard | Double render jobs corrupt output directory; duplicate jobs waste queue | 71.1 |
| min > max validation with user feedback | Inverted values accepted silently; backend swap is invisible; creator believes wrong config was used | 71.1 |

### P1 — Should fix before ship

| Fix | Why | Commit |
|---|---|---|
| Zero min/max validation | `min=0` coerced to 10s silently — same trust issue as inverted values | 71.1 |
| localStorage save-failure warn | Quiet data loss of creator preferences on quota exceeded — no signal at all | 71.2 |
| File upload size warning | Large upload followed by deep render failure is the worst possible UX — warn early | 71.3 |

### P2 — Nice to have, ship without if needed

| Fix | Why | Commit |
|---|---|---|
| Batch poll cleanup | Unnecessary background polling after completion — performance waste | 71.3 |
| Stall message: add cancel/guidance text | "No progress for 45s" is accurate but leaves creator without action path | 71.3 |

### Not in Phase 71

| Item | Reason |
|---|---|
| Backend: upload size limit | Requires server config change — separate deploy decision |
| Backend: batch cancel child processes | Significant orchestration change — not a frontend fix |
| Backend: Whisper timeout | Requires async architecture change in render route |
| Batch queue: file path existence check | Browser cannot check server paths — would need a pre-flight API call |

---

## 8. COMMIT PLAN

| # | Commit message | Files | Change | P-level |
|---|---|---|---|---|
| 1 | `ship(71.1): render submit in-flight guard and min/max validation` | `editor-view.js` | `_r71RenderSubmitInFlight` flag, guard in `v3TriggerRerender` + `startRenderFromEditor`; min>max and zero checks before submit | P0+P1 |
| 2 | `ship(71.2): localStorage save-failure console.warn across preference modules` | `clip-steering.js`, `score-preference.js`, `duration-preference.js`, `creator-taste.js`, `creator-feedback.js`, `creator-series.js` | Replace `catch {}` with `catch { console.warn(...) }` in `_save()` of each module | P1 |
| 3 | `ship(71.3): upload size warning, batch poll cleanup, stall guidance` | `render-ui.js`, `batch-queue.js` | File size pre-check toast; batch poll clear-on-complete; stall message with cancel/guidance | P1+P2 |

**Total: 3 commits, 9 files. Zero backend changes. Zero ranking changes. Zero UX redesign.**

---

## 9. DEFINITION OF DONE

Phase 71 is complete when:

**In-flight guard:**
- [ ] Clicking Rerender twice in under 100ms submits exactly one render job
- [ ] `_r71RenderSubmitInFlight` is reset to `false` after render submit succeeds
- [ ] `_r71RenderSubmitInFlight` is reset to `false` after any validation error early-return
- [ ] Toast "Render already queued" appears on second Rerender click while first is in-flight

**min/max validation:**
- [ ] Setting `evMinPart=90`, `evMaxPart=60` and clicking Start Render shows error: "Min clip (90s) must be less than max clip (60s)."
- [ ] `evStartBtn` is re-enabled after the validation error
- [ ] Setting `evMinPart=0` shows error: "Min and max clip length must be greater than 0."
- [ ] Valid `evMinPart=45`, `evMaxPart=90` submits without error

**localStorage warn:**
- [ ] `score-preference.js` `_save()` catch logs `console.warn` with module identifier
- [ ] `duration-preference.js` `_save()` catch logs `console.warn`
- [ ] `clip-steering.js` `_save()` catch logs `console.warn`
- [ ] `creator-taste.js` `_save()` catch logs `console.warn`
- [ ] `creator-feedback.js` `_save()` catch logs `console.warn`
- [ ] `creator-series.js` `_save()` catch logs `console.warn`

**Upload size warning:**
- [ ] Selecting a file > 4GB shows informational toast (warning, not block)
- [ ] Upload proceeds after warning (not blocked)
- [ ] Files < 4GB show no warning

**Batch poll cleanup:**
- [ ] After all batch items reach `done`/`failed`, the poll interval is cleared
- [ ] No API calls made after batch completes

**Regression checks:**
- [ ] Phase 69 ScorePreference chip unaffected
- [ ] Phase 70 DurationPreference hint unaffected
- [ ] Phase 67 ClipSteering lock/exclude unaffected
- [ ] Phase 68 DNA note / alt note / feedback summary unaffected
- [ ] Normal single render still submits correctly
- [ ] Normal batch render still submits correctly

---

## What Phase 71 does NOT change

| Item | Status |
|---|---|
| Clip ranking / ordering | **Unchanged** |
| Render pipeline | **Unchanged** |
| Creator memory modules logic | **Unchanged** (only `_save()` catch body) |
| UI layout or design | **Unchanged** |
| Any Phase 63–70 feature behavior | **Unchanged** |
| Backend endpoints | **Unchanged** |

## What Phase 71 defers

| Item | Why |
|---|---|
| Backend upload size limit | `upload.py` streaming change — separate decision, needs prod config |
| Batch cancel: kill running child | Orchestration change — requires job runner refactor |
| Whisper transcription timeout | Async architecture change in preview route |
| Creator preference: cross-module quota management | Could consolidate all prefs into one key to reduce quota pressure — Phase 72 candidate if needed |

---

*Phase 71 plan based on live code audit of editor-view.js, render-ui.js, batch-queue.js, clip-steering.js, score-preference.js, duration-preference.js, creator-taste.js, creator-feedback.js, creator-series.js, upload.py, render_pipeline.py.*
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*
