# Product State — Post P3.5

**Date:** 2026-05-16
**Branch:** `feature/ai-output-upgrade`
**Last phase:** P3.5 — Multi-Agent Editing System

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in P3.5

### Starting point: one generalized brain

Before P3.5, all editing intelligence — hook quality, pacing, subtitles, emotion, viral score — was evaluated by the same generalized logic. `_parseIntent()` used keyword scoring that treated every creator the same. `getConcerns()` checked two taste-based conditions. Nothing was specialized. The result: reasonable but generic recommendations that didn't feel like expert judgment.

### What P3.5 delivers

**Five specialized editing agents** (`editor-agents.js`) — each one a pure-data function that reads from real signal sources, evaluates one editing dimension, and produces a confidence-ranked recommendation. No LLM, no orchestration bus, no invented signals.

**Agent consensus engine** — `EditorAgents.runAll()` runs all 5 agents, filters silent agents (null returns), and sorts by confidence descending. The top recommendation drives action. Agents that don't have enough signal stay silent.

**Conversational routing** — `_parseIntent()` now has a 5th resolution step. When keyword scoring, tie-breaking, and vague-power resolution all fail, the agent consensus fires. The conversation surfaces the agent's identity: "Hook Agent · high confidence" as a small pill badge, with the agent's reason as explainText.

**Richer runtime concerns** — `RuntimeIntelligence.getConcerns()` delegates to the agent system. Concern items in the evolution feed now carry agent labels ("Hook Agent", "Pacing Agent") instead of generic tier text.

---

## Agent Architecture

```
buildSignals(parts)
  ├─ EditorSceneIntelligence.getLatest() → markers, scenes, silences
  ├─ EditorReviewIntelligence.getReviewData() → hookScore, retentionRisks, badSubCount, partScores
  ├─ CreatorMemory.getTasteModel() → pace, hook, editStyle, confident
  └─ parts[] → viral_score per completed render part

runAll(signals)
  ├─ _runHookAgent(signals)    → strongerHook      (baseline 0.82–0.87)
  ├─ _runPacingAgent(signals)  → fasterPacing /    (baseline 0.74–0.88)
  │                               removeDeadSpace
  ├─ _runSubtitleAgent(signals) → subtitleCleanup  (baseline 0.65–0.84)
  ├─ _runEmotionAgent(signals) → cinematicMode     (baseline 0.58–0.70)
  └─ _runViralAgent(signals)   → viralMode /       (baseline 0.63–0.78)
                                  smartClipPrioritization
  → [null agents filtered] → sorted by confidence desc
```

---

## Agent Signal Map

| Agent | Primary Signal | Threshold | Taste Weight |
|---|---|---|---|
| Hook | `weak-intro` marker OR `hookScore < 0.55` | Silence below 0.55 | `hook=aggressive` → +9% |
| Pacing | `pacing-drop` marker OR silence zones ≥ 2 | < 2 silence zones → no action | `pace=fast` → +8% |
| Subtitle | `subtitle-overload` marker OR `badSubCount >= 3` | `badSubCount < 3` → no action | `editStyle=educational` → +12% |
| Emotion | `emotional-shift` ≥ 2 OR avg emotion < 0.55 | < 2 shifts AND emotion ≥ 0.55 → no action | `editStyle=cinematic` → +12% |
| Viral | `retentionRisks >= 2` OR avg viral < 50% | < 2 risks AND retention ≥ 0.5 → no action | `editStyle=viral` → +10% |

All threshold values come from real signal sources — no invented scores.

---

## Conversation Flow (P3.5-F)

```
User: "my edit could use some work"
  │
  ▼
_parseIntent("my edit could use some work")
  1. _tryContextResolve() → null (no context pattern)
  2. keyword scoring → 0 matches (no rule keywords present)
  3. _resolveWithTaste() → null (no vague power word)
  4. _resolveWithAgents()
      → EditorAgents.buildSignals()
      → EditorAgents.getTopRecommendation(signals)
          Hook Agent: weak-intro marker present → confidence 0.82
          Pacing Agent: null (no drops)
          → returns { action: 'strongerHook', confidence: 0.82, reason: 'Low-energy opening...', agentLabel: 'Hook Agent' }
      → confidence 0.82 ≥ 0.65 → return intent
      → { action: 'strongerHook', explainText: 'Hook Agent identified this — ...', agentMeta: { label: 'Hook Agent', tier: 'high' } }
  │
  ▼
_fireIntent('strongerHook', 'stronger opening hook', ..., agentMeta)
  → _addTurn('ai', intro, ..., agentMeta)
  → _render() → .p35AgentPill[data-tier="high"] "Hook Agent · high confidence"
  → EditorAiActions.previewAction('strongerHook')
```

```
User: "too slow"
  │
  ▼
_parseIntent("too slow")
  1. _tryContextResolve() → null
  2. keyword scoring: "slow" → fasterPacing(1), "too slow" → fasterPacing(+2) = 3 total → clear winner
  → { action: 'fasterPacing', ... }
  [agents NOT consulted — keyword match takes priority]
```

---

## Runtime Concern Flow (P3.5-E)

```
RenderAiRuntime.update(stage, status, parts)
  → _renderConcernItems(parts)
    → RuntimeIntelligence.getConcerns(parts)
      → EditorAgents available?
        YES:
          buildSignals(parts)
          runAll(signals) → [Hook Agent: 0.87, Viral Agent: 0.71, ...]
          filter(confidence >= 0.65) → [Hook, Viral]
          return [
            { type: 'hook', label: 'Hook Agent', msg: 'Opening clip is below engagement threshold...' },
            { type: 'viral', label: 'Viral Agent', msg: '3 clips below retention threshold...' },
          ]
        NO: → P3.4 taste-based fallback
    → .p34ConcernItem rendered with agent label
```

---

## What Has Not Changed

- Keyword scoring path in `_parseIntent()` — agents only fire when keywords fail
- `_RULES`, `_VAGUE_POWER`, `_OPPOSITE`, `_STYLE_PREF` constants — unchanged
- P3.3 context resolution patterns — unchanged
- `EditorAiActions.previewAction()` patch system — unchanged (agents only route to actions, they don't patch)
- `CreatorMemory.getTasteModel()` — unchanged (agents consume it, don't modify it)
- All P3.4 runtime completion intelligence — unchanged

---

## Maturity Assessment (Updated)

### AI Collaboration

**Score: 9.5 / 10** (was 9 / 10)

Gained:
- Five specialized agents evaluate their respective dimensions from real signals
- Conversation routes to expert agent when general keywords fail — "my edit could use some work" now resolves
- Runtime concern items carry specific agent identity — "Hook Agent" vs. "Retention Risk"
- Taste weighting is soft and additive — no hardcoded creator archetypes
- Agents are silent when their signals are absent — no hallucinated intelligence

Remaining weak:
- Agents are stateless — no memory of previous recommendations within a session
- Cross-agent conflict not resolved — if Hook and Emotion agents both fire, only one surfaces in conversation
- Keyword matches bypass agents — "too slow" goes straight to Pacing rule without checking if Hook Agent thinks the intro is the real problem
- No "multiple expert voices" UI — only the top agent is surfaced in conversation; others are visible in runtime concerns only

### UI

**Score: 7.5 / 10** (unchanged from P3.4)

Agent pill adds a subtle but meaningful identity signal. No new panels created.

---

## Known Limitations

### Agents are consultation-only for keyword paths
When "too slow" matches `fasterPacing` by keyword, the agents are never consulted. This means Hook Agent can't surface "actually your intro is the real problem" alongside the pacing recommendation. Multi-signal awareness only appears when keyword scoring fails entirely.

### Scene intelligence cold start
Hook, Pacing, Emotion, and Subtitle agents require `EditorSceneIntelligence.getLatest()` to have run analysis. Analysis runs after the editor loads clips. In render-only mode (no editor open), these agents return null — only the Viral Agent can use render part scores.

### Confidence is flat across sessions
Agent confidence is a function of signal count and strength in the current session. There's no history: an agent that fires confidently every session isn't weighted higher than one firing for the first time.

### Agent pills only in conversation
Agent identity is surfaced in: (1) conversation turns via `.p35AgentPill`, (2) runtime concern labels. There's no inspector panel showing all active agent states. This is intentional (per P3.5-H: no giant dashboard), but means the "multiple expert minds" feel is only visible when agents actually fire.

---

## Next Phase Direction

### P3.5.1 — Cross-agent surfacing (minor)
When a keyword match fires (e.g., `fasterPacing`), check if another agent recommends a different action at high confidence. If so, surface a secondary suggestion chip: "Pacing Agent agrees · Hook Agent also detected a weak intro." Requires small `_parseIntent()` change to run agents after keyword match and compare.

### P3.6 — Session Agent Memory
Give agents a lightweight session log: which agent fired, what confidence, what the user chose. After 3+ sessions, agents can weight their recommendations based on acceptance patterns. "You've always accepted Hook Agent recommendations — show them first." Requires new in-memory session structure.

### P3.4.1 — Concern Lifecycle
Concern resolved state: when Hook Agent's concern is active and the 2nd hook clip comes in high-tier, replace the concern with "Hook Agent: risk resolved — strong follow-up detected."
