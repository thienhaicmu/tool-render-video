# Product State — Post P3.2

**Date:** 2026-05-16
**Branch:** `feature/ai-output-upgrade`
**Last phase:** P3.2 — Conversational Editing

> Reality-first snapshot. No invented features. Everything described here exists in code.

---

## What Changed in P3.2

### Starting point: button-driven AI editing

Before P3.2, accessing AI editing required:
1. Knowing the right button exists in the Cut tab
2. Clicking it to see a preview
3. Accept or reject

The AI was intelligent. The interface was still software.

### What P3.2 delivers

**A "Talk" inspector tab** — a 6th tab alongside Cut, Subtitles, Text & Voice, Audio, Render. Inside: a lightweight conversation surface with conversation history, example chips, and a text input.

**Intent-to-patch pipeline** — user text is parsed against 7 intent rules using keyword scoring. The resolved intent triggers `EditorAiActions.previewAction()` — the existing non-destructive patch system. No new mutation path was created.

**Conversation history** — up to 6 turns shown, older turns fade. The history is in-memory (resets on editor close), not persisted.

**Ambiguity clarification** — if the top 2 intent scores tie, the system shows clarification buttons instead of guessing. If no intent matches, it offers 4 quick actions.

**Memory-aware responses** — after resolving intent, `CreatorMemory.getDerivedPreferences()` is checked. If confidence is established (≥5 signals), the response prefixes with "You usually keep this one" or "You've skipped this before."

**Accept/reject feedback** — when the user accepts or discards the preview (via the existing card in `#evInspAiPanel`), the conversation receives a follow-up: "Applied. What else would you like to change?" or "Discarded. Try a different direction."

---

## Data Flow

```
Talk tab input: "intro feels slow"
  │
  ▼
EditorConverse._parseIntent()
  keyword scoring: "slow" → fasterPacing(1), "intro" → strongerHook(1)
  → tied → clarification: [Stronger Hook] [Faster Pacing]

User clicks "Stronger Hook"
  → EditorConverse._clarify('strongerHook', 'Stronger Hook')
  → _fireIntent('strongerHook', 'stronger opening hook', ...)

_fireIntent():
  → CreatorMemory.getDerivedPreferences() → not confident yet → no prefix
  → _addTurn('ai', 'I understood: stronger opening hook. Here's a preview...')
  → EditorAiActions.previewAction('strongerHook')
      → renders ghost overlay on timeline
      → populates #evInspAiPanel with preview card

User clicks ✓ Apply (in #evInspAiPanel):
  → EditorAiActions.acceptPreview() → applies patches, updates timeline
  → EditorConverse._onAccept() → adds "Applied. What else..." turn
```

---

## UI Layout

```
┌─────────────────────────────┐
│  #evInspAiPanel             │  ← always visible, above tabs
│  [Preview card appears here]│     empty when no preview active
├─────────────────────────────┤
│ Cut | Subtitles | Text |    │  ← tab bar
│ Audio | Render | Talk       │
├─────────────────────────────┤
│  ← Talk tab content →       │
│                             │
│  [conversation history]     │  ← #convHistory, max 6 turns
│                             │
│  [example chips]            │  ← hidden once history exists
│                             │
│  [input field] [↵]          │  ← #convInputField + send button
└─────────────────────────────┘
```

The preview card (`#evInspAiPanel`) is always visible — when user types in Talk tab and triggers a preview, the preview appears at the top while the conversation remains visible below. Accept/discard in the card, conversation feedback in the Talk tab.

---

## Intent Rules

| Rule | Action | Trigger keywords |
|---|---|---|
| stronger opening hook | `strongerHook` | hook, intro, opening, start, beginning, lead |
| faster pacing | `fasterPacing` | slow, boring, dragging, pace, pacing, long, tighten, faster |
| remove dead air | `removeDeadSpace` | silence, dead, gap, pauses, quiet, air |
| viral optimization | `viralMode` | viral, algorithm, tiktok, energy, energetic, engagement |
| cinematic flow | `cinematicMode` | cinematic, emotional, story, narrative, jumpy, choppy, calm |
| subtitle cleanup | `subtitleCleanup` | subtitle, caption, hard to read, messy text |
| AI prioritization | `smartClipPrioritization` | best clips, rank, quality, priority, highlight |

---

## Maturity Assessment (Updated)

### UI

**Score: 7.5 / 10** (was 7 / 10)

Gained:
- Natural language entry point for AI editing
- Conversation history gives sense of session context
- Example chips lower barrier for new users
- Memory-aware responses personalize the interaction

Remaining weak:
- No mobile layout
- No undo from Talk tab
- Intent parser is keyword-only heuristics — "make it better" always fails
- Example chips don't reappear after first message

### AI Collaboration

**Score: 8 / 10** (was 7 / 10)

Gained:
- Natural creative intent maps to non-destructive patch previews
- Memory context makes responses creator-aware
- Ambiguity handled transparently (clarification vs. hallucinated intent)
- Every conversation message MUST change the edit or explain why it can't

Remaining weak:
- Single-turn intent only — no multi-step reasoning ("make it faster than last time")
- No semantic understanding — keyword matching misses paraphrase
- No learning from conversation patterns

---

## What Has Not Changed

- Backend render pipeline: unchanged
- Patch system: unchanged (`EditorAiActions.previewAction()` is unmodified)
- `#evInspAiPanel` preview card: unchanged except two button onclick additions
- `creator_prefs` backend: unchanged

---

## Known Limitations

### Intent ambiguity
"too slow" ties between `fasterPacing` and `strongerHook` because "slow" matches both. The clarification prompt resolves this, but it adds a friction step the user didn't expect. A future improvement: weight keywords contextually (e.g., "slow" with "intro" → hook; "slow" alone → pacing).

### No conversational context
Each input is parsed independently. "Make it less aggressive than last time" fails because the parser doesn't see the previous turn. Building conversational context would require maintaining intent state across turns.

### Example chip visibility
Example chips hide once conversation history exists and don't come back. New users who accidentally dismiss history lose the guidance. A future improvement: always show chips at the bottom, or restore when history is short.

---

## Risks

### Keyword false positives
"I want more story flow" → "story" hits `cinematicMode`. Correct. But "the story doesn't have good timing" → "story" still hits `cinematicMode` even though the intent is unclear. Low risk since ambiguity is caught when two rules tie, but single-match false positives are possible.

### Preview panel overlap
`#evInspAiPanel` is always visible. If the user triggers a conversation preview while a manual preview from the Cut tab is still showing, the second preview overwrites the first. This matches existing behavior (not new to P3.2) but may be surprising when coming from the Talk tab.

---

## Next Phase Direction

### P3.3 — Contextual Intent (Smarter Parsing)

Improve intent resolution:
- Weight keywords by co-occurrence with context words ("intro" + "slow" → always hook, never pacing)
- Add negation handling ("not too jumpy" → `fasterPacing` down, not `cinematicMode` up)
- Persistent conversation context: last 2 turns inform current parse

No backend changes needed — pure frontend intent logic.

### P3.4 — Render Output Feedback Loop

Feed download/preview signals from the review panel into `creator_prefs`. Closes the loop between render output and creator memory.

### P2.10 — Output Review & Export (alternative narrow scope)

Side-by-side clip comparison, batch export, inspector panel completion.
