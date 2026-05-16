# Product State — Post P3.7

**Date:** 2026-05-16
**Branch:** `feature/ai-output-upgrade`
**Last phase:** P3.7 — Creator Co-Pilot & Adaptive Collaboration

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in P3.7

### Starting point: static expert system

Before P3.7, agent debates produced the same output regardless of who was watching. Hook Agent and Pacing Agent would always agree the same way. Extreme conflict always triggered the same threshold. No memory of whether the creator accepted or rejected those directions. The AI collaborated — but didn't learn from the collaboration.

### What P3.7 delivers

**Collaboration memory** (`creator-memory.js`) — a new `collab` sub-object in `_profile` tracks how the creator resolves creative tradeoffs from agent debates:
- `aggressiveWins` / `aggressiveRejects` — aggressive direction decisions
- `narrativeWins` / `narrativeRejects` — narrative direction decisions
- `compromiseWins` — accepted compromise actions
- `lastDebateResult` — most recent direction outcome

**`recordDebateChoice(direction, accepted)`** — new public function called from `_onAccept()` and `_onReject()` in `editor-converse.js` when the last intent was agent-routed.

**`getCollabProfile()`** — derives collaboration preference from debate history. Requires ≥3 debate decisions for confident output. Returns:
- `preferredDir`: 'aggressive' | 'narrative' | null
- `compromiseTolerant`: true when creator accepted ≥2 compromise actions
- `confident`: boolean (3+ decisions)

**Adaptive consensus** (`editor-consensus.js`) — `resolve()` reads `getCollabProfile()` and applies soft weighting:
- When creator prefers winning direction: `confidence × 1.04` (reinforcement)
- When creator tolerates compromise: extreme conflict threshold lowers from `0.45` to `0.38` (more compromise-first behavior)

**Co-pilot reasoning text** (`editor-converse.js`) — `_resolveWithAgents()` now computes `copilotNote` when the debate direction diverges from the creator's history:
- "You tend to preserve emotional pacing. Applied a conservative adjustment."
- "You usually favor high-energy edits. Cinematic approach taken — signal was compelling."
- "Balanced compromise applied — aligns with how you usually resolve these."

`copilotNote` is added to `agentMeta` and rendered as `.p37CopilotNote` (warm amber italic below compromise note).

**Context tracking** (`editor-converse.js`) — `_ctx` extended with `lastWasAgentRouted` and `lastAgentDir` to track when `_fireIntent` originated from agent routing. `_dirOf(action)` helper mirrors the direction map in `editor-consensus.js`.

**Runtime co-pilot** (`editor-runtime-intelligence.js`) — `getConcerns()` P3.6 path now appends a soft collab note to the primary concern when the concern direction conflicts with creator history:
- "You usually prefer lighter adjustments." (when aggressive recommendation, but creator prefers narrative)
- "Note: you usually favor high-energy edits." (when narrative, but creator prefers aggressive)

**Creator Memory panel** (`creator-memory.js`) — `_renderKnown()` extended with P3.7 collaboration rows when `collab.confident`:
- "Debate tendency: Dynamic / High-energy" or "Debate tendency: Narrative / Cinematic"
- "Compromise: Accepts balanced solutions" (when `compromiseTolerant`)

**CSS** (`review.css`) — P3.7 section appended:
- `.p37CopilotNote` — warm amber italic, below compromise note in conversation
- `.p37CollabRow .cmPrefVal` — purple accent for collab rows in creator panel

---

## Architecture

```
Creator accepts/rejects agent-routed intent
  ↓
_onAccept() / _onReject() in editor-converse.js
  ↓ (only when _ctx.lastWasAgentRouted)
CreatorMemory.recordDebateChoice(direction, accepted)
  ↓
_profile.collab updated → localStorage + backend sync
  ↓
Next debate: EditorConsensus.resolve() reads getCollabProfile()
  → soft confidence boost if creator prefers winning direction
  → lower extreme threshold if creator tolerates compromise
  ↓
_resolveWithAgents() reads getCollabProfile()
  → copilotNote generated when direction diverges from history
  → agentMeta.copilotNote passed through _fireIntent → _addTurn → _render
  ↓
Conversation renders: [AgentPill] [consensus] [dissent] [compromise] [copilotNote]
```

---

## What Was NOT Built

Per the brief's explicit instruction, these are noted as future foundation only — no code written:

- **P4.1 Autonomous Assist** — post-render autonomous fix suggestions
- **P4.2 Creative Planning** — pre-render goal-setting conversation
- **P4.3 Publishing Intelligence** — platform-aware output optimization
- **P4.4 Multi-Video Learning** — cross-session pattern learning

The collab memory structure in `_profile.collab` is intentionally minimal and forwards-compatible with any of these future layers.

---

## Failure Safety

- `getCollabProfile()` returns `{ confident: false }` until 3+ debate decisions — no adaptive behavior before then
- All collab weighting is soft — max 4% confidence boost, threshold delta of 0.07
- `typeof CreatorMemory !== 'undefined'` guards in consensus and converse prevent errors if module not loaded
- `collab` sub-object uses `Object.assign(base, _profile.collab || {})` everywhere — graceful handling of old profiles without collab key
- Reset wipes collab data via `_empty()` which includes the zero-state collab sub-object

---

## Maturity Assessment (Updated)

### AI Collaboration

**Score: 9.7 / 10** (up from 9.5)

Gained vs. P3.6:
- AI now remembers HOW creator resolves creative tradeoffs, not just WHAT they accept
- Debate behavior adapts across sessions — compromise tolerance lowers the threshold that triggers clarification
- Co-pilot note explains when the recommendation diverges from creator history
- Runtime concern messaging adapts to collab preference

Remaining weak:
- Compromise always = `removeDeadSpace` for aggressive/narrative conflict (same as P3.6 limitation)
- Direction detection in `_dirOf()` is duplicated across converse and consensus — could drift if actions change
- Collab memory resets fully with general memory reset — no graduated confidence decay

### UI

**Score: 7.5 / 10** (unchanged)

Co-pilot note is a new amber italic line — adds one more layer of text below the compromise note. Panel gains two optional rows when collab is confident. No new panels or controls introduced.

---

## Known Limitations

### `_dirOf()` duplication
The direction lookup for actions is defined independently in `editor-converse.js` (as `_dirOf`) and in `editor-consensus.js` (as inline `Set` checks). If an action is added or removed from a direction, both files need updating. A shared constant would remove the drift risk.

### Compromise action is still fixed
`removeDeadSpace` remains the only compromise between aggressive and narrative directions. P3.7 doesn't change this — it only adjusts the threshold for when compromise is applied. The compromise action itself would require P3.6.1 to vary.

### No intra-collab debate
When a creator accepts an aggressive recommendation but the debate included a compromise, the collab memory records `aggressive` — not `aggressive-over-compromise`. There's no way to know if the creator accepted despite a dissent or because of a dissent. P3.7 doesn't model this nuance.

---

## Next Phase Direction

### P3.7.1 — Collab-Aware Clarification Wording
When the conversation surfaces clarification buttons (extreme conflict), the button labels could reflect collab history: "Faster Pacing (your tendency)" vs "Cinematic Flow". Currently the labels are generic.

### P3.6.1 — Compromise Preference Learning
Record which compromise actions a creator accepts. Weight `removeDeadSpace` vs. narrative-lean based on actual acceptance history. Minimal change to `_COMPROMISE` selection in `editor-consensus.js`.

### P4.1 — Autonomous Assist
After a creator accepts an action, the relevant agent should quietly evaluate if the accepted edit created a new problem. Hook added to `_onAccept()` — implementation pending.
