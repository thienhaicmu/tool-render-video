# Product State — Post P3.3

**Date:** 2026-05-16
**Branch:** `feature/ai-output-upgrade`
**Last phase:** P3.3 — Taste Model & Adaptive Intent

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in P3.3

### Starting point: generic intent

Before P3.3, the conversation system parsed intent identically for every creator. "Make it stronger" failed with no match. "Too slow" always triggered clarification even when the taste model had a clear signal. The AI remembered what you accepted — but didn't use that memory to interpret what you meant.

### What P3.3 delivers

**Taste model** (`getTasteModel()` in `creator-memory.js`) — multi-dimensional inference from the same accept/reject signals that already drive `aggressiveness`. Three dimensions:
- **Pace**: fast / balanced / cinematic (from fasterPacing ↔ cinematicMode signal ratio)
- **Hook**: aggressive / moderate / soft (from strongerHook + viralMode signal ratio)
- **Edit style**: viral / cinematic / educational / balanced (composite of pace + hook + subtitle signals)

Requires 8+ total signals. Below that: no taste influence, no changed behavior.

**Vague power resolution** — "stronger", "better", "improve", "boost" now resolve via taste model:
- viral/fast creator → `strongerHook`
- cinematic creator → `cinematicMode`
- educational creator → `smartClipPrioritization`
- balanced/low-signal → clarification as before

**Tie-breaking** — when two keyword rules score equally, the taste model picks the one matching the creator's style. "Too slow" (fasterPacing vs strongerHook tied) → viral creator → `strongerHook` wins, no clarification needed.

**Micro conversation memory** — `_ctx` tracks the last resolved action + interpretation within a session. Three patterns:
- "again" / "repeat" → replay last action
- "just the intro" / "intro only" → force `strongerHook`
- "a bit less" / "dial it back" → apply the directional opposite of the last action

**Explainability** — when taste or context resolution is used, a short `explainText` string appears in the conversation turn (italic, muted), e.g.: `"Your high-energy editing style shaped this — I read 'stronger' as a tighter opening hook."`

**Inspector taste surface** — the Creator Memory panel (Cut tab) now shows taste dimension rows when taste model is confident: Pace tendency, Hook tendency, Edit tendency.

---

## Data Flow

```
User: "make it stronger"
  │
  ▼
_parseIntent("make it stronger")
  1. _tryContextResolve() → null (no context pattern match)
  2. keyword scoring → 0 matches (none of the 7 rules match "stronger")
  3. _resolveWithTaste("make it stronger")
      → _VAGUE_POWER.includes("stronger") = true
      → CreatorMemory.getTasteModel()
          accepted: {viralMode: 3, strongerHook: 2, fasterPacing: 1}
          → paceRaw = +0.44 → pace: 'fast'
          → hookRaw = +0.62 → hook: 'aggressive'
          → editStyle: 'viral'
          → confident: true (12 total signals)
      → action: 'strongerHook'
      → explainText: "Your high-energy editing style shaped this..."
  │
  ▼
_fireIntent('strongerHook', 'stronger opening hook', '...', explainText)
  → _ctx.lastAction = 'strongerHook'
  → EditorAiActions.previewAction('strongerHook')
```

```
User: (after the above) "a bit less"
  │
  ▼
_tryContextResolve("a bit less")
  → /a bit less/ matches
  → _ctx.lastAction = 'strongerHook'
  → OPPOSITE['strongerHook'] = 'cinematicMode'
  → returns { action: 'cinematicMode', explainText: "Dialing back from stronger opening hook." }
```

---

## Taste Model Thresholds

| Signal count | Capability unlocked |
|---|---|
| 0–4 | Learning state — no preference influence |
| 5–7 | Basic memory: favored/avoided lists, memory context in response |
| 8+ | Taste model: pace/hook/style inference, vague power resolution, tie-breaking |

These thresholds are explicit constants: `MIN_SIG = 5`, `MIN_TASTE_SIG = 8`. The system degrades gracefully below both thresholds.

---

## Maturity Assessment (Updated)

### AI Collaboration

**Score: 8.5 / 10** (was 8 / 10)

Gained:
- Vague creative intent ("stronger", "better") now resolves for creators with taste data
- Tied keyword scores break via taste rather than always showing clarification
- Micro conversation memory enables "just the intro" / "dial it back" follow-ups
- Explainability text makes taste-based decisions transparent
- Inspector shows taste dimensions (pace, hook, edit tendency)

Remaining weak:
- No taste decay — signals from early sessions influence forever unless Reset is clicked
- `editStyle` composite uses hard thresholds — sits in one bucket without gradation
- Context resolution is regex-based — natural phrasing variations may miss
- Vague resolution still falls back to clarification for new users (< 8 signals)

### UI

**Score: 7.5 / 10** (unchanged from P3.2)

The taste surface in the inspector adds a small but meaningful layer. Nothing visually disruptive.

---

## What Has Not Changed

- Backend render pipeline: unchanged
- Patch system: unchanged
- `creator_prefs` backend table: unchanged
- All P3.2 conversation UI: unchanged (no new HTML, no new tabs)

---

## Known Limitations

### Taste model cold start
New users (< 8 signals) get no taste-adaptive behavior. This is intentional safety — but means the "AI understands me" feeling takes ~8-12 editing sessions to emerge. Frustrating for users who expect intelligence immediately.

### Hard category thresholds
`editStyle = 'viral'` requires `paceRaw > 0.2 AND hookRaw > 0.2`. A creator who is `paceRaw = 0.19, hookRaw = 0.30` is categorized as `balanced` even though they lean fast. Future fix: use continuous scores instead of categorical buckets.

### Context pattern brittleness
"let's just look at the opening" does not match the regex `/just the intro|only the intro|...`". Only literal common phrasings are caught. Future fix: expand patterns or use word-level token matching.

### No forget / decay
Accepting `viralMode` 6 months ago still counts equally to last week. There's no temporal weighting. Future fix: add `lastUpdated` field per action and apply exponential decay.

---

## Next Phase Direction

### P3.4 — Render Output Feedback Loop (recommended next)

Close the signal gap: currently only editor accept/reject signals feed `creator_prefs`. Rendering output (which clips the user downloads, previews, or deletes) would be a stronger signal. Requires:
- `download` event in the review panel → `CreatorMemory.recordSignal()`
- `preview` event → lighter weight signal
- Optional: `skip` (user ignores a clip) → negative signal

No backend changes needed beyond the existing `creator_prefs` table.

### P3.5 — Temporal Signal Weighting

Add `signal_weights_json` to `creator_prefs`: decay older signals, amplify recent ones. The taste model would then reflect current taste, not lifetime average. Requires DB schema change (add column) and updated `getTasteModel()` math.

### P2.10 — Output Review & Export (alternative scope)

Side-by-side clip comparison, batch export, inspector stub panel completion.
