# Product State — Post P3.4

**Date:** 2026-05-16
**Branch:** `feature/ai-output-upgrade`
**Last phase:** P3.4 — Adaptive Runtime Intelligence

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in P3.4

### Starting point: generic runtime editorial

Before P3.4, `RenderAiRuntime` treated every creator identically. The same three editorial messages rotated for high/mid/low clips regardless of whether the creator is a viral editor who expects aggressive hook scoring or a cinematic creator who values narrative pacing. Completion intelligence used generic tier-based text with no awareness of who rendered the job.

### What P3.4 delivers

**`RuntimeIntelligence` module** (`editor-runtime-intelligence.js`) — a new lightweight IIFE that provides taste-aware editorial context to `RenderAiRuntime`. No DOM access, no invented signals. Pure data from real sources: `viral_score` per part and `CreatorMemory.getTasteModel()`.

**Taste-adaptive evolution feed** — each completed clip now gets an editorial message shaped by the creator's taste profile:
- Viral/fast creator + high-tier hook clip: "High-energy signal — above your viral editing threshold."
- Viral/fast creator + low-tier hook clip: "Weak opening signal — this sits below your usual hook threshold."
- Cinematic creator + mid-tier: "Steady clip — narrative rhythm present, hook softer."
- Generic fallback (< 8 signals): identical to prior behavior

**Taste note** — when taste is confident, a short italic annotation appears below the editorial message: "Aligned with your high-energy editing profile." or "Below your cinematic profile threshold."

**Concern system** — editorial concern items appear in the evolution feed when real signal conditions warrant:
- **Retention Risk**: first clip scored < 45% AND creator hook preference is `aggressive` — "Opening clip at 38% — below your typical hook threshold."
- **Pacing Signal**: batch avg < 45% (≥3 clips) AND creator is `viral` or `fast` — "Avg score 41% — softer than your high-energy editing pace."
- No concerns shown when taste not confident (< 8 signals)

**Taste-aware completion intelligence** — `showCompletionIntelligence()` now surfaces creator-matched summaries:
- Viral creator + strong output: "High-energy output — signal density aligns with your viral editing profile."
- Cinematic creator: "Output follows your cinematic rhythm — narrative signal is strong."
- Educational creator: "Clear, structured result — well-matched to your clarity-first style."

**Completion card taste note** — italic footer in the `.rcAiCompCard`: "Your high-energy editing profile shaped the output ranking." Only shown when taste is confident.

**Completion summary line** — `bits` array in `.renderCompletionSummary` now includes "high-energy profile matched" or "cinematic profile matched" for creators with established taste.

---

## Data Flow

```
Render heartbeat → RenderAiRuntime.update(stage, status, parts)
  │
  ├─ _updateEvolutionFeed(parts)
  │    For each newly completed part:
  │      pNo = part.part_no
  │      pct = part.viral_score × 100
  │      tier = pct >= 75 ? 'high' : pct >= 50 ? 'mid' : 'low'
  │      ctx = RuntimeIntelligence.getEvolutionContext(pNo, pct, tier)
  │        → CreatorMemory.getTasteModel()
  │        → taste.confident? → taste-adapted why + tasteNote
  │        → taste.confident = false? → generic messages (prior behavior)
  │      Render .p28EvolItem with ctx.why + optional .p34EvolTaste
  │
  └─ _renderConcernItems(parts)
       concerns = RuntimeIntelligence.getConcerns(parts)
         → taste.confident = false? → []
         → firstClip.viral_score < 0.45 + hook=aggressive? → hook-risk concern
         → avg < 0.45 + (viral|fast)? → pacing-mismatch concern
       hash dedup → only re-renders when concern set changes
       .p34ConcernItem elements appended to rc_ai_evolution_list

Render completes → showCompletionIntelligence(job, summary, parts)
  │
  narrative = RuntimeIntelligence.getCompletionNarrative(avgPct, topPct, count)
    → taste.editStyle === 'viral' → viral summaryMsg
    → taste.editStyle === 'cinematic' → cinematic summaryMsg
    → taste.editStyle === 'educational' → educational summaryMsg
    → taste.confident = false → generic summaryMsg (prior behavior)
  Render .rcAiCompCard with narrative.summaryMsg + optional .p34TasteNote
  Set .renderCompletionSummary = narrative.bits.join(' · ')
```

---

## Signal Map

| Signal | Source | Used by |
|---|---|---|
| `part.viral_score` | Backend job_parts | Tier classification, concern thresholds |
| `part.part_no` | Backend job_parts | Hook clip detection (pNo ≤ 2) |
| `part.status` | Backend job_parts | Completed-part filtering |
| `taste.hook` | CreatorMemory.getTasteModel() | Hook-risk concern, hook-clip messaging |
| `taste.pace` | CreatorMemory.getTasteModel() | Pacing-signal concern |
| `taste.editStyle` | CreatorMemory.getTasteModel() | Completion narrative, evolution messaging |
| `taste.confident` | CreatorMemory.getTasteModel() | Gate: all concern/taste paths disabled below threshold |

No invented signals. No derived metrics beyond the tier classification already present in P2.8.

---

## Maturity Assessment (Updated)

### AI Collaboration

**Score: 9 / 10** (was 8.5 / 10)

Gained:
- Runtime surfaces taste-aware insight during render, not just post-render
- Concern system grounds editorial attention in real signal conditions
- Completion narrative matches editorial voice to creator's established style
- Every taste-adaptive path degrades gracefully for new creators (< 8 signals)

Remaining weak:
- No historical render comparison — "below your usual output" can't be computed without prior render records
- Concern resolved state: a cleared concern (score improved mid-render) doesn't surface improvement confirmation
- `getConcerns()` is evaluated every WS heartbeat — no cooldown, no "you were warned" memory across sessions

### UI

**Score: 7.5 / 10** (unchanged from P3.3)

P3.4 changes are data-layer and text-layer only. No new UI panels.

---

## What Has Not Changed

- Backend render pipeline: unchanged
- `_STAGES`, `_REASONING` stage labels: unchanged
- `_applyConfidenceEvolution()`: unchanged
- `_syncOutputCard()` transient card classes: unchanged
- All P3.3 conversation and taste inspector: unchanged

---

## Known Limitations

### No render history per creator
`getCompletionNarrative()` compares `avgPct` against taste dimension expectations (viral creator expects high output), but can't compare against actual prior render averages. "Below your usual signal threshold" is a taste-relative statement, not a statistical one. A real comparison would require a `render_history` table or localStorage cache of prior avgPct values — not implemented.

### Concern timing gap
The hook-risk concern requires `part_no === 1` to be completed. If the first clip renders 4th (out of 5), the concern won't appear until 80% of the render is done — too late to be actionable. This is a real-data limitation: we only know the score once the clip is rendered.

### Taste model cold start (inherited from P3.3)
New creators (< 8 signals) get zero taste-adaptive behavior in the runtime — identical to P2.9 experience. The same cold-start tradeoff from P3.3 applies here.

---

## Next Phase Direction

### P3.5 — Temporal Signal Weighting

Add `signal_weights_json` to `creator_prefs`: decay older signals, amplify recent ones. The taste model would reflect current taste, not lifetime average. Requires DB schema change (add column) and updated `getTasteModel()` math. Would also make concern thresholds more accurate over time.

### P3.4.1 — Concern Lifecycle (minor)
Add "resolved" state to concern items: when a hook-risk concern is active and the 2nd hook clip comes in high-tier, replace "Retention Risk" with a "Risk resolved — strong follow-up hook." Requires tracking which concerns were shown and checking their conditions on subsequent ticks.

### P2.10 — Output Review & Export
Side-by-side clip comparison, batch export, inspector stub panel completion.
