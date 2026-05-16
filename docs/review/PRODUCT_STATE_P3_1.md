# Product State — Post P3.1

**Date:** 2026-05-16
**Branch:** `feature/ai-output-upgrade`
**Last phase:** P3.1 — Creator Memory & Preference Intelligence

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in P3.1

### Starting point: session-only preference tracking

Before P3.1, `_trackPreference(name, accepted)` in `editor-ai-actions.js` accumulated a session-only `aiPreferenceProfile` in EditorState. The profile drove `_getAggressiveness()` to scale trim ratios. But every page load reset it to `null`. The AI never knew what you liked yesterday.

### What P3.1 delivers

**Persistence bridge** — `CreatorMemory` IIFE (`creator-memory.js`) bridges the existing `_trackPreference` signal into localStorage and a new backend table (`creator_prefs`). Every accept/reject now survives the session.

**Backend persistence** — new `creator_prefs` SQLite table (singleton row, id=1, JSON blob). New route `GET /PUT /api/creator/preferences`. Data round-trips: frontend reads on init, writes on every signal (debounced 2s).

**Memory-aware AI copy** — `_buildReasoning` in `editor-ai-actions.js` injects a preference-aware prefix into the confidence text when `totalSignals ≥ 5`:
- Favored action: `"Based on your history, you tend to keep this."`
- Avoided action: `"You've passed on this before — worth a second look."`

**Inspector panel** — `#cmPrefsPanel` in the Cut tab. Two states:
1. **Learning** (< 5 signals): progress bar, hint text counting down to preference unlock
2. **Known** (≥ 5 signals): editing style label (Bold/Balanced/Conservative), top favored actions in green, avoided actions in red, total signal count, Reset button

**Safety** — `MIN_SIG = 5` threshold means no AI copy changes before meaningful signal volume. Reset clears localStorage + backend + EditorState immediately.

---

## Data Flow

```
User accepts/rejects AI suggestion
  │
  ▼
_trackPreference(name, accepted)         ← editor-ai-actions.js
  ├── EditorState.aiPreferenceProfile    ← session memory (unchanged from P2.x)
  └── CreatorMemory.recordSignal()       ← P3.1
        ├── _profile (in-memory)
        ├── localStorage('cm_prefs_v1')
        ├── debounced PUT /api/creator/preferences
        └── #cmPrefsPanel DOM update

Editor opened
  └── CreatorMemory.init()
        ├── GET /api/creator/preferences
        ├── merge: remote wins if totalSignals higher
        ├── seed EditorState.aiPreferenceProfile
        └── render #cmPrefsPanel

_buildReasoning() — per action suggestion
  └── CreatorMemory.getDerivedPreferences()
        └── if confident: prefix confText with memory context
```

---

## Maturity Assessment (Updated)

### AI Collaboration

**Score: 7 / 10** (was 6 / 10)

Gained:
- Editor preference signals now persist across sessions
- Memory-aware copy visible in AI suggestion cards after 5 signals
- Inspector panel surfaces what the AI has inferred about creator taste
- Backend table ready for future cross-feature memory integration

Remaining weak:
- No feedback from render output (downloads, previews, exports) — only editor UI signals
- `feedback_learning.py` (Phase 43) backend preference learning is still disconnected from `creator_prefs`
- No taste model per content category
- Installation-scoped (no user accounts) — single profile per machine

### Production Readiness

**Score: 6 / 10** (unchanged)

The `creator_prefs` table is created by `init_db()` at startup using `CREATE TABLE IF NOT EXISTS` — safe for existing installations. No migration risk.

### UI

**Score: 7 / 10** (unchanged) — the creator memory panel adds new surface but doesn't change overall score.

---

## What Has Not Changed

Backend render pipeline (Python/FFmpeg) is unchanged.
Runtime CSS (`runtime.css`) is unchanged.
WebSocket transport is unchanged.
`feedback_learning.py` is unchanged and still disconnected from the new `creator_prefs` table.

---

## Risks

### Signal sparsity
Most users won't use the editor extensively enough to accumulate 5 signals quickly. The learning progress bar mitigates UX awkwardness during the ramp-up period, but the feature may feel inert to casual users.

### Aggressiveness drift
If a user happens to reject 5 actions in a row (e.g., all were bad suggestions), aggressiveness will drop to ~0.35 and all subsequent suggestions will be more conservative. The Reset button is the escape valve, but it requires the user to find it.

### Single-installation profile
The profile is stored per machine. Users switching computers or reinstalling will lose memory. Acceptable for the current local-app scope.

---

## Commit Grouping (suggested)

**Commit 1 — P3.1 backend (db + route)**
- `backend/app/services/db.py`: `creator_prefs` table + `get_creator_prefs()` + `upsert_creator_prefs()`
- `backend/app/routes/creator.py`: `GET /api/creator/preferences`, `PUT /api/creator/preferences`
- `backend/app/main.py`: register `creator_router`

**Commit 2 — P3.1 frontend (memory module + wiring)**
- `backend/static/js/creator-memory.js`: `CreatorMemory` IIFE (new file)
- `backend/static/js/editor-ai-actions.js`: `_trackPreference` + `_buildReasoning` changes
- `backend/static/js/editor-view.js`: `CreatorMemory.init()` + panel clear on cancel
- `backend/static/index.html`: panel div + script tag

**Commit 3 — P3.1 CSS**
- `backend/static/css/v3/review.css`: creator memory panel styles

**Commit 4 — Documentation**
- `docs/review/frontend_ui_audit.md`: Section 28 appended
- `docs/review/PRODUCT_STATE_P3_1.md`: this file (new)

---

## Next Phase Direction

### P3.2 — Render Output Feedback Loop

Close the gap between editor preferences and actual render quality:
- Track which clips the user downloads or previews
- Feed download/preview signals into `creator_prefs` with lower weight than editor accept/reject
- Requires backend event (download endpoint → `upsert_creator_prefs`)
- No frontend UI changes needed — existing `CreatorMemory.recordSignal()` can be reused

### P3.3 — Feedback Learning Bridge

Connect `feedback_learning.py` (Phase 43) output (`feedback_memory.json`) into `creator_prefs`. Currently these run independently:
- `feedback_learning.py` learns from render output ranking at the job level
- `creator_prefs` learns from editor UI signals at the action level
Merging them would give the AI a richer signal for preference-aware suggestions.

### Alternative: P2.10 — Output Review & Export

A narrower next step that stays in current scope:
- Side-by-side clip comparison
- Batch export with format selection
- Inspector panel completion (finish stub panels)
