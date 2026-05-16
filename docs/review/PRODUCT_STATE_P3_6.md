# Product State — Post P3.6

**Date:** 2026-05-16
**Branch:** `feature/ai-output-upgrade`
**Last phase:** P3.6 — Agent Debate & Consensus Intelligence

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in P3.6

### Starting point: winner-takes-all agents

Before P3.6, five specialized agents evaluated editing independently and `runAll()` sorted by confidence. The highest-confidence agent fired. Agreement between agents (Hook and Viral both detecting an energy problem) was invisible. Conflict (Pacing wanting faster cuts while Emotion wanted to preserve rhythm) was also invisible. Recommendations felt like one agent's opinion, not collaborative reasoning.

### What P3.6 delivers

**`EditorConsensus`** (`editor-consensus.js`) — a lightweight debate engine that groups agents by creative direction, detects agreement and conflict, boosts confidence for consensus, and surfaces compromise when both sides are meaningful.

**Creative direction model** — agents are classified into three directions:
- `aggressive` — fasterPacing, strongerHook, viralMode, removeDeadSpace
- `narrative` — cinematicMode
- `clarity` — subtitleCleanup, smartClipPrioritization

**Agreement boost** — when 2+ agents are in the same direction, confidence is boosted (+8% per extra ally) and the pill label changes from "Hook Agent" to "Hook Agent + Viral Agent".

**Conflict detection** — aggressive vs. narrative is the primary conflict axis. `conflictLevel` is computed as the ratio of opposing group confidence to winning group confidence.

**Compromise** — when conflict is extreme (conflictLevel > 0.45, opposer confidence ≥ 0.60), the system applies a neutral compromise action (`removeDeadSpace`) that satisfies both directions: it tightens without destroying intentional pacing.

**Creator clarification** — in extreme conflict where compromise would misrepresent both sides, the conversation surfaces two directions as clarification buttons: "Stronger Pacing" vs. "Cinematic Flow". The creator decides.

---

## Debate Flow

```
EditorConsensus.resolve(signals)
  ↓
EditorAgents.runAll(signals)
  → Hook Agent:    strongerHook   (0.87) — aggressive
  → Pacing Agent:  fasterPacing   (0.74) — aggressive
  → Emotion Agent: cinematicMode  (0.68) — narrative
  → Subtitle Agent: null (no signal)
  → Viral Agent:   null (no signal)

Group by direction:
  aggressive: [Hook(0.87), Pacing(0.74)] — weight = (0.87+0.74) × 1.10 = 1.771
  narrative:  [Emotion(0.68)]            — weight = 0.68

Winner: aggressive direction
  topAgent    = Hook Agent (strongerHook, 0.87)
  agreeCount  = 2
  allyLabel   = "Hook Agent + Pacing Agent"
  consensus   = "Hook Agent + Pacing Agent agree — opening clip is below engagement threshold."

Conflict:
  opposing = narrative → Emotion Agent (0.68)
  conflictLevel = 0.68 / (0.87 + 0.74) = 0.42

  isExtremeConflict = (0.42 > 0.45)? → FALSE  (below threshold)
  dissent = "Emotion Agent preferred Cinematic Flow."

Confidence:
  base      = 0.87
  + ally    × 1.08 = 0.94
  - conflict× 0.96 = 0.90
  → final confidence: 0.90

Output:
  { action: 'strongerHook', confidence: 0.90, allyLabel: 'Hook Agent + Pacing Agent',
    consensus: '...agree...', dissent: 'Emotion Agent preferred...', compromiseNote: null,
    isExtremeConflict: false, conflictOptions: null }
```

```
Extreme conflict example:
  → Pacing Agent: fasterPacing (0.82)  — aggressive
  → Emotion Agent: cinematicMode (0.80) — narrative

  conflictLevel = 0.80 / 0.82 = 0.98  → isExtremeConflict = true
  compromise action = 'removeDeadSpace'
  compromiseNote = "Removed dead air only — intentional pacing preserved for emotional impact."
  confidence = 0.82 × 1.0 × (1 - 0.098) × 0.93 ≈ 0.76

  Conversation:  { action: null, ambiguous: true, options: [{Faster Pacing}, {Cinematic Flow}] }
  OR (if compromise applied before clarification threshold):
  { action: 'removeDeadSpace', compromiseNote: '...', dissent: 'Emotion Agent preferred...' }
```

---

## Conversation Output Examples

### Agreement (no conflict)
```
[Hook Agent + Viral Agent]
Hook Agent and Viral Agent agree — opening clip is below engagement threshold —
first impression needs a stronger hook.
```

### Agreement with dissent
```
[Hook Agent + Pacing Agent]
Hook Agent and Pacing Agent agree — opening clip is below engagement threshold.
Emotion Agent preferred Cinematic Flow.
```

### Extreme conflict → compromise
```
[Pacing Agent]
Pacing Agent: Long clip detected — its runtime is softening overall pacing.
Emotion Agent preferred Cinematic Flow.
Compromise: Removed dead air only — intentional pacing preserved for emotional impact.
```

### Extreme conflict → clarification
Two clarification buttons appear:
```
[Faster Pacing]  [Cinematic Flow]
```

---

## Runtime Concern Output Examples

**Primary concern (consensus):**
```
Hook Agent + Viral Agent
Opening clip is below engagement threshold — first impression needs a stronger hook.
```

**Secondary concern (conflict note):**
```
Emotion Agent
Cinematic Flow.
[or] Compromise: Removed dead air only — intentional pacing preserved.
```

---

## Maturity Assessment (Updated)

### AI Collaboration

**Score: 9.5 / 10** (unchanged — incremental improvement within same tier)

The score stays at 9.5 because P3.6 is a depth improvement, not a new capability. The same 5 agents exist; they now reason together instead of independently.

Gained vs. P3.5:
- Multi-agent agreement is surfaced explicitly — "Hook Agent + Viral Agent agree"
- Opposing agents' views are acknowledged — dissent note in conversation and runtime
- Compromise action prevents binary winner-takes-all when conflict is meaningful
- Creator clarification path prevents AI from deciding when both sides are equally valid

Remaining weak:
- Compromise is always `removeDeadSpace` for aggressive/narrative conflict — limited set of compromise actions
- Clarity direction (subtitle/prioritization) cannot conflict with other directions — no debate path for these agents
- Agreement within same direction doesn't account for which specific signals drove each agent — two agents agreeing on `strongerHook` for different reasons looks identical to agreement on the same reason

### UI

**Score: 7.5 / 10** (unchanged)

Debate context renders in existing conversation space — no new panels. `.p36Dissent` and `.p36Compromise` lines are muted and italic — present but not disruptive.

---

## What Has Not Changed

- 5 agent implementations in `editor-agents.js` — unchanged
- `EditorAgents.runAll()` — unchanged (consensus calls it internally)
- Keyword-based conversation routing — unchanged (agents still only fire when keywords fail)
- All P3.3 conversation patterns — unchanged
- All P3.4 runtime completion intelligence — unchanged
- P3.5 agent pills in conversation — still render, now with debate context appended

---

## Known Limitations

### Compromise action is fixed
When aggressive meets narrative conflict, the compromise is always `removeDeadSpace`. A creator who strongly prefers cinematic flow might want the compromise to lean toward `cinematicMode` rather than a neutral dead-air removal. The system doesn't know which compromise direction the creator prefers — that would require historical compromise acceptance signals, which don't exist yet.

### No intra-direction debate
Two agents in the `aggressive` direction always agree, even if they're detecting completely different problems. Hook Agent flagging a weak intro and Viral Agent flagging poor retention risks are different problems — but the system treats them as "agreeing on aggressive direction." The nuance within a direction is lost.

### Clarity agents are debate-isolated
Subtitle Agent and Viral Agent (when it recommends `smartClipPrioritization`) are in the `clarity` direction. This direction has no natural opponent, so clarity agents never trigger the conflict path. This means subtitle concerns always appear at face value, without the "Emotion Agent disagrees" context that makes the debate model interesting.

### Static conflict threshold
`conflictLevel > 0.45` for extreme conflict is a fixed constant. A viral creator might want the AI to be more decisive (higher threshold, fewer clarification prompts) while a cinematic creator might want more deference (lower threshold, more clarification). Creator preference for AI decisiveness isn't tracked.

---

## Next Phase Direction

### P3.7 — Proactive Agent Nudges
Agents currently only fire when conversation routing fails. After a creator accepts an action, the relevant agent should quietly evaluate if the accepted edit created a new problem. "Hook Agent: the accepted hook is now strong — but Pacing Agent detected a new pacing drop in the middle section." Requires post-accept analysis hook in `_onAccept()`.

### P3.6.1 — Compromise Preference Learning
Record which compromise actions a creator accepts. Over time, weight the `removeDeadSpace` compromise vs. the "priority maintained" note based on actual acceptance history. Low complexity: just record compromise type in `CreatorMemory.recordSignal()` and read it in `EditorConsensus._COMPROMISE` selection.

### P3.5.1 — Cross-Agent Surfacing in Keyword Path
When a keyword match fires (e.g., `fasterPacing` from "too slow"), run agents in parallel and check if any other agent at ≥ 0.70 confidence recommends a different direction. If so, add a secondary suggestion chip: "Pacing selected · Hook Agent also detected a weak intro." Minimal change to `handleInput()`.
