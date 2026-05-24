# Mode Tab — AI ASSIST & AI Edit Actions: Mental Model Review

**Scope:** `setInspectorTab('mode')` → AI ASSIST section + AI Edit Actions section  
**Review type:** Mental model audit (not code review)  
**Date:** 2026-05-19

---

## 1. What It Actually Does

### AI ASSIST

**What a creator sees:**
- A header labeled "AI Assist" with an **Undo** button
- An empty chip row (suggestion chips — currently unpopulated)
- A small activity log showing the last 5 AI actions (e.g., "Applied: Viral Mode", "Tightened cuts")

**What it actually does:**
- **Nothing active.** It is a read-only log of what AI Edit Actions have done this session.
- The **Undo button** rolls back the most recent AI Edit Action (20-item history stack).
- No payload sent to backend. No settings changed. No clips modified.

**One sentence:** AI ASSIST is an activity feed and undo control for actions taken by AI Edit Actions — it is not a mode, toggle, or assistant you interact with.

---

### AI Edit Actions

**What a creator sees:**
A collapsible section with **6 buttons** in a 2-column grid:

| Button | Plain-English Description |
|---|---|
| **Tighten Cuts** | Trims 0.10–0.18s of dead space from both edges of every clip |
| **Stronger Hook** | Moves the highest-scoring clip to position 1 (opening slot) |
| **Faster Pacing** | Trims 8–16% off clip edges across the board to speed up the feel |
| **Best First** | Re-sorts all clips by viral score, highest to lowest |
| **Viral Mode** | Sorts by score AND trims edges — the most aggressive combo |
| **Cinematic** | Sorts clips in original chronological order, enforces minimum 4s per clip |

**What actually happens when a creator clicks any button:**

1. A **ghost overlay** appears on the timeline showing the proposed new clip arrangement
2. A **preview card** appears with:
   - Runtime delta (e.g., "−3.2s")
   - Number of edits made
   - Before/after estimates (retention, pacing)
   - 3 bullet reasoning points
   - Confidence level (High / Mid / Low)
   - "✓ Apply" and "✕ Discard" buttons
3. Creator decides:
   - **Apply** → clips are rewritten in the editor, action is logged, undo snapshot saved, scene analysis re-runs
   - **Discard** → nothing changes, preference tracked (affects future aggressiveness)

**Key mechanics:**
- All mutations happen **frontend-only** (in-memory editor state)
- Changes only reach the backend when "▶ Start Render" is clicked, serialized as `editor_clip_plan`
- Aggressiveness of each action **auto-adjusts** based on your accept/reject history (0.25 → 0.88 scale)
- Creator memory integration: if you've accepted Viral Mode 3 times, it notes "You tend to keep this"

---

## 2. Creator Mental Model

### What a creator thinks when they see "AI ASSIST":

> "There's an AI assistant helping me. What does it do? Can I ask it something? Why is there an Undo button here and not elsewhere?"

**Reality:** It's a log + undo control. The name "AI ASSIST" describes nothing the creator can *do*. The undo button's position here (not in a global toolbar) is unexpected.

**Verdict: Confusing. Creator reaction is likely "wtf is this."**

---

### What a creator thinks when they see "AI Edit Actions":

> "These are things the AI can do to my video. I can click them and see what happens."

**Reality:** Exactly correct. The name is literal, the buttons are self-describing, and the preview-before-apply pattern protects against accidental changes.

**Verdict: Clear. Creator gets it without explanation.**

---

### Per-Control Mental Model Breakdown

#### Tighten Cuts
- **Actual purpose:** Remove micro-pauses at clip boundaries to make transitions feel snappier
- **Best use case:** After scene detection generates clips with trailing silence or breath gaps
- **Bad use case:** If clips already start/end on tight beats — will cut into audio
- **Expected result:** Slightly shorter total runtime, crisper cuts

#### Stronger Hook
- **Actual purpose:** Re-orders clips to put the AI's top-scored clip first
- **Best use case:** When opener feels weak but a later clip has high energy
- **Bad use case:** When narrative order matters (story-driven content)
- **Expected result:** First clip changes; rest stay in same relative order

#### Faster Pacing
- **Actual purpose:** Proportionally trims all clip edges — makes the whole video feel faster without reordering
- **Best use case:** Video feels sluggish but structure is correct
- **Bad use case:** Content where timing precision matters (reaction timing, punchlines)
- **Expected result:** Shorter runtime, same clip order, faster rhythm

#### Best First
- **Actual purpose:** Pure sort by AI confidence score — no trimming
- **Best use case:** When you trust the AI's scoring and want to front-load the best moments
- **Bad use case:** When clip scores are similar (sort won't change much but changes the order)
- **Expected result:** Reordered timeline, same clip durations

#### Viral Mode
- **Actual purpose:** Combines score-based reordering + edge trimming in one action
- **Best use case:** Starting fresh, want maximum AI impact, don't know where to start
- **Bad use case:** When you've already manually arranged clips you like
- **Expected result:** Most dramatic change — new order + shorter clips

#### Cinematic
- **Actual purpose:** Restores chronological order and enforces a minimum 4s clip length
- **Best use case:** After applying Viral Mode and the result feels fragmented or out-of-context
- **Bad use case:** Short-form content where pacing > narrative (TikTok hooks)
- **Expected result:** Slower, more stable video; clips in original time order

---

## 3. Overlaps and Confusion

### AI ASSIST vs AI Edit Actions — can creator confuse them?

**Yes. Strongly.**

| Source of confusion | Why |
|---|---|
| Same section, adjacent UI | Creator sees "AI Assist" and the 6 buttons as one block |
| Undo lives in AI ASSIST but undoes AI Edit Actions | No visual link — creator doesn't know the undo there is for the buttons below |
| "AI Assist" implies the AI is helping proactively | The 6 action buttons are also "AI helping" — no clear distinction |
| AI ASSIST is passive, Edit Actions are active | Nothing in the UI communicates this |

**Creator confusion scenario:**
> "I clicked Viral Mode. That didn't work. I want to undo. Where's undo? Oh, there's an Undo button in AI Assist — is that related? Will clicking it undo my Viral Mode?"

The answer is yes, but there's no signal that these are connected.

---

### Overlap with Other Features

| Feature | Overlap with AI Edit Actions | Risk of confusion |
|---|---|---|
| **Quick Presets** (TikTok, YouTube) | Presets set render settings before editor opens; Edit Actions mutate clips inside editor | LOW — different phase |
| **Structure Bias** (hook/story/balanced) | Independent — affects subtitle emphasis only | LOW |
| **Variants** (Viral / Cinematic / Aggressive / Balanced buttons) | HIGH — Variants call the SAME Edit Actions internally. "Viral" variant = Viral Mode button | HIGH |
| **Transform / Reframe** | Completely independent (render-time, not clip-time) | LOW |
| **Subtitle Controls** | Independent — subtitle segmentation separate from clip plan | LOW |
| **Market Targeting** | Re-runs after any Edit Action via `_reanalyze()` | LOW — automatic, no duplication |
| **Rerender button** | Rerender uses current clip plan; Edit Actions mutate that plan | LOW — sequential, not duplicated |

### Critical overlap: Edit Actions vs Variants

The **Variants section** (Viral / Cinematic / Aggressive / Balanced) calls the same underlying functions as AI Edit Actions. Clicking the "Viral" variant applies Viral Mode. Clicking "Cinematic" applies Cinematic Mode.

**Creator confusion scenario:**
> "I see a 'Viral' variant button AND a 'Viral Mode' action button. Are these the same thing? Which one should I use? What's the difference?"

Answer: Variants also auto-save a timeline snapshot. Edit Actions don't auto-save a named variant. But nothing in the UI explains this.

---

## 4. Naming Review

### "AI ASSIST"

**Is the name accurate?** No.

- "AI" → implies intelligence. Correct.
- "ASSIST" → implies it helps you do something. Incorrect — it watches and logs.
- The undo button is here but the name doesn't hint at that.

**Why it's misleading:** Creators will look for a chat input, a suggestion they can accept, or some kind of proactive assistant. They will find a log and be confused.

**Proposed rename:** `AI Activity` or `Edit History`

Rationale:
- "Activity" describes exactly what's shown — a feed of what happened
- Moves the undo button context to "undo the last activity item" — logical
- Doesn't oversell the intelligence

---

### "AI Edit Actions"

**Is the name accurate?** Mostly yes.

- "AI" → the actions use AI scoring. Correct.
- "Edit" → they edit the timeline. Correct.
- "Actions" → they are discrete triggerable actions. Correct.

**Minor issue:** "Edit Actions" sounds like menu items (File > Edit > Actions). Could be interpreted as settings rather than triggers.

**Proposed rename (optional):** `AI Timeline Edits` or just `Edit Actions`

Rationale:
- Drops "AI" prefix if it already lives inside an AI-themed tab — reduces repetition
- "Timeline Edits" makes it clear these operate on the clip timeline, not settings

---

## 5. How Creators Should Use It

```
When your video feels too slow and cuts drag:
→ Click "Tighten Cuts"
→ Preview — check if runtime delta and clip count make sense
→ Apply if it feels cleaner, Discard if it cuts into speech

When your opener is weak but you have strong clips later:
→ Click "Stronger Hook"
→ Preview — check what clip moved to position 1
→ Apply only if that clip actually works as an opener

When the pacing feels off but structure is right:
→ Click "Faster Pacing"
→ Preview — check total runtime delta
→ Apply if rhythm improves, Discard if it cuts too deep

When you don't know where to start and want AI to take a pass:
→ Click "Viral Mode"
→ Preview — this will be the most dramatic change
→ Apply, then check if anything broke; undo if needed

When Viral Mode made the video feel choppy or out of context:
→ Click "Cinematic"
→ Preview — restores chronological order with stable clip lengths
→ Apply to get back to a safe, narrative baseline

When you want to undo the last action:
→ Click "Undo" (in the AI Activity section above)
→ Up to 20 actions can be undone this way

When you want to compare two versions:
→ Apply an Edit Action (e.g., Viral Mode) — it saves a snapshot automatically
→ Click the corresponding Variant button to restore that named save
```

---

## 6. Keep / Improve / Remove

### Keep

| Item | Why |
|---|---|
| Preview-before-apply pattern | Protects creators from accidental timeline destruction |
| Undo stack (20 items) | Essential — creators will experiment and need escapes |
| Confidence tiers (High/Mid/Low) | Gives creators signal on whether to trust the suggestion |
| Aggressiveness auto-adjustment | Personalization without a settings screen |
| Creator memory integration | "You tend to keep this" reduces friction |

### Improve

| Item | Problem | Fix |
|---|---|---|
| "AI ASSIST" name | Misleading — implies active help | Rename to "AI Activity" or "Edit History" |
| Undo button location | In AI ASSIST, undoes Edit Actions — no visual link | Move undo to base of Edit Actions section, or add label: "Undo last edit action" |
| Variants vs Edit Actions overlap | Same functions, no explanation of difference | Add tooltip: "Saves a named snapshot when applied" on Variants |
| Suggestion chips (empty) | Shows empty slot with no content — looks broken | Either populate it or remove the DOM element until it has content |
| Activity rail "AI ready" default | "AI ready" sounds like something you need to start | Change default text to "No actions yet" |

### Remove

| Item | Why |
|---|---|
| Nothing — core features are sound | The 6 actions, preview system, and undo are all load-bearing |

---

## 7. 10-Second Creator Explainer

**AI Edit Actions:** Six one-click edits the AI can make to your timeline — reorder clips, trim dead space, speed up pacing. Each one shows a preview with reasoning before you commit. You can undo any of them.

**AI Activity (currently "AI ASSIST"):** A log of what edits have been applied this session, with an undo button.

---

*Generated from full code audit of: `editor-ai-actions.js` (703 lines), `editor-ai-sessions.js`, `editor-view.js` (payload serialization), `editor-engine.css`, `index.html` (lines 905–947)*
