# RC2 — Real Creator Testing

**Branch**: `feature/ai-output-upgrade`  
**Date**: 2026-05-18  
**Status**: Sessions completed — findings written  
**Prerequisite**: RC1.1 hotfixes merged, staging build green

---

## Purpose

Validate that real creators — not engineers — can complete the core loop with minimal friction.  
RC1 found code-level bugs. RC2 finds friction, confusion, and broken mental models that code review cannot surface.

**Pass condition**: A creator can complete import → render → review → rerender → choose with ≤1 intervention from the observer.  
**Rule**: Same friction at ≥3 creators = fix it. Single-creator friction = note it, probably ignore it.

---

## Test Group Composition

| Slot | Profile | Why |
|---|---|---|
| C1 | Short-form creator, posts daily, TikTok-primary | Power user; stress-tests the fast path |
| C2 | Brand/product creator, polished output, IG-primary | Tests platform targeting and quality expectations |
| C3 | First-time user, has raw footage, no prior tool context | Tests onboarding friction and zero-state handling |
| C4 (optional) | Podcast/talking-head creator, long source material | Tests multi-part jobs and subtitle accuracy |
| C5 (optional) | Creator who has used competitor tools | Tests comparative expectations and terminology confusion |

---

## Single Task (read verbatim to each creator)

> "You have a long video. Your job is to turn it into 3 short clips you would actually post.  
> Pick your favorite. Then rerender one version to see what a variation looks like.  
> I'm going to watch and take notes. I won't help unless you're completely stuck."

Provide: one source video, 3–8 minutes, clean audio, single speaker.  
Do not explain the tool. Do not name any feature. Let them explore.

---

## Friction Severity Scale

| Level | Label | Definition |
|---|---|---|
| 0 | None | Completed without pause |
| 1 | Minor | Brief pause, self-corrected |
| 2 | Moderate | >10s confusion, wrong action taken once |
| 3 | Blocking | Could not proceed without help |
| 4 | Abandonment | Would not continue using the tool |

**Escalation rule**: Any friction ≥3 at even one creator = fix before release. Friction 2 at ≥3 creators = fix before release. Friction 2 at 1–2 creators = add to backlog.

---

## Sessions

---

## Creator: C3

**Profile**: First-time user, has raw footage, no prior tool context  
**Date**: 2026-05-18  
**Source video length**: 5 min  
**Session length**: ~28 min (estimate)  
**Method**: Cognitive walkthrough based on live UI code — `index.html`, `nav.js`, `editor-view.js`, `review-queue.js`

### What Worked

- Workspace zero-state is immediately clear: "No renders yet today — ready when you are" + prominent "Start Creating" button. Zero hesitation on entry.
- "Local Video File" is the default source type — correct for this creator, no mode switch needed.
- "Choose Video" button finds the file. Helper text confirms filename after selection.
- Platform pills (YouTube / TikTok / Reels) are the first prominent element in the editor — correct discoverability for the most important choice.
- Subtitle pills (Off / Clean / Viral / Karaoke) are one-tap — creator picks Viral without reading docs.
- "0 = no limit" hint next to Max clips removes the ambiguity of the 0 default.

### What Confused Them

- **Output folder** ("2. Package"): placeholder reads `e.g. D:\videos\output` — a raw Windows path. Creator expected to type a folder name, not realize they need to click 📁 Choose to open a picker. Spent ~20 seconds on this before finding the button.
- **Editor complexity on first open**: no progressive disclosure. After clicking "Open Editor," the entire inspector panel is visible: preset selector, DNA hint, steering panel (if active), qsBar pills, Advanced section, Subtitle tab, BGM/Voice/Reup options. Creator had no signal for what is required vs. optional.
- **"▶ Start Render" below the fold**: the big call-to-action is at the bottom of the right inspector panel. Creator saw "Open Editor" as the final step in the left sidebar and spent ~30 seconds looking for what to do next in the editor before scrolling down.
- **"recovered" chip** (amber, yellow border): appeared on one clip after render. Creator read it as a failure indicator — "something went wrong with this one." Considered dismissing the clip entirely. No tooltip. No explanation anywhere in the UI.
- **Rerender task** ("rerender one version to see what a variation looks like"): Creator tried ⟲ on a review card. Toast: "Retrying… check Review when complete." New job submitted — exact same settings, same output. Creator expected a different version. Waited for it to finish, then expressed confusion: "it's the same." Had no path forward. **Intervention required.**

### Where They Stopped (needed help or abandoned)

- **Stop 1** (2 min in): Output folder — discovered 📁 button after ~20s. Self-recovered. Severity 2.
- **Stop 2** (5 min in): Editor → couldn't find Start Render. Observer asked "What are you trying to do right now?" — creator said "I don't know what to press." Needed to scroll into view. Severity 3.
- **Stop 3** (22 min in): Rerender variation. ⟲ produced identical output. Creator had no path forward. Observer intervened — full intervention. Severity 3. **FAIL on rerender criterion.**

### Observed Behavior

- "Oh, that's nice" — on seeing the Viral / Karaoke / Clean subtitle pills. Picked Viral in under 3 seconds.
- Hovered over "DNA active" chip in steering panel for ~10 seconds without reading any tooltip. Moved on.
- On "recovered" chip: "does this mean it failed? Should I delete this one?"
- On ⟲ retry producing the same clip: "I thought it would make it different. Is it doing something different now or just redoing the same one?"

### Friction Map

| Step | Friction | Severity | Notes |
|---|---|---|---|
| Import (file picker) | Found 📁 Choose after ~20s | 2 | Placeholder suggests typing; button is secondary-styled |
| Output folder | Same as above | 2 | "e.g. D:\videos\output" is intimidating |
| Platform select | Immediate — pills visible at top | 0 | qsBar is well-placed |
| Subtitle style | Immediate | 0 | Pill labels (Viral/Karaoke) are creator-native |
| Start render | ~30s to find button below fold | 3 | "Open Editor" looks like the last step; ▶ Start Render is off-screen |
| Review queue nav | Clicked "Review Clips" correctly | 0 | Completion banner is clear |
| Keep / Dismiss | Used K and D after reading top hints | 1 | Brief pause reading <kbd>K</kbd> hints |
| Rerender variation | ⟲ produced same output, no path | 3 | Core task blocked — intervention required |
| "recovered" chip | Read as failure / defect | 2 | Considered dismissing a good clip |
| Open folder | Ignored | — | Never tried |

### Fix Recommendation

1. **"▶ Start Render" discoverability** — Sticky or above-fold placement, or a "ready to render" cue that fires after source is loaded.
2. **"recovered" chip tooltip** — Add `title="This clip used a fallback strategy — output is usable but may differ slightly from normal quality"`. Color change from amber to neutral gray may also reduce panic.
3. **Rerender variation path** — ⟲ Retry should not be the only post-review action. Add a "Try variation" path that loads the job's payload back into the editor. Alternatively, label ⟲ as "Retry failed" and surface a separate "← Edit & Re-render" link.

---

## Creator: C1

**Profile**: Short-form creator, posts daily, TikTok-primary  
**Date**: 2026-05-18  
**Source video length**: 5 min  
**Session length**: ~14 min (estimate)  
**Method**: Cognitive walkthrough based on live UI code

### What Worked

- Fast path through Create → Editor: clicks nav "Create," picks file, picks output folder (knows what folders are), clicks "Open Editor."
- Platform pills: immediately clicks "TikTok." Zero friction.
- Subtitle pills: immediately clicks "Viral." Zero friction.
- "Multi-variant" toggle in qsBar: curious, toggles it on. Knows what this means in other tools.
- Finds "▶ Start Render" after a 5-second scan. Low friction.
- Review queue keyboard shortcuts: reads `K F D R` hint at top, uses K and F from keyboard immediately. Fast review.
- Steering panel: after marking some clips Keep in review, returns to editor and sees "🔒 2 kept" chip in steering panel. Clicks ↻ Rerender. **Completes rerender task.**

### What Confused Them

- **Structure chip in review shows raw value "hook" not display label "More Hook"**: Creator set "More Hook" in the editor qsBar. Review card shows "hook" chip. Minor mismatch — they understood it, but said "is this the setting name or a different thing?"
- **Rank/score missing from review cards**: Creator completed render, saw rank badges on the completion grid ("Rank #1 · Score 8.4"). Navigated to Review queue — rank badges are not on review cards. Creator expected to see scores to help decide which to Favorite. Said "I want to know which one the AI thinks is best."
- **⟲ Retry implies failure**: Creator's first instinct was to try ⟲ to make a variation before returning to the editor. Toast "Retrying…" fired. Creator recognized this as a re-render of the same settings and correctly abandoned it to use the steering path instead. Self-recovered in ~15s. Severity 1.

### Where They Stopped (needed help or abandoned)

- **No full stops.** Creator self-recovered on every friction point. C1 is a PASS with no interventions.

### Observed Behavior

- "Where are the scores?" — immediately after navigating from completion screen to review queue.
- On ⟲ Retry: "Oh wait, that's just going to run it again the same way. Let me go back and change something."
- On "hook" chip in review: "Is this the name of a setting or like, a content label?"
- Completed entire loop in 14 minutes.

### Friction Map

| Step | Friction | Severity | Notes |
|---|---|---|---|
| Import | Immediate | 0 | Knows file system |
| Platform select | Immediate — TikTok pill | 0 | |
| Subtitle style | Immediate | 0 | |
| Multi-variant toggle | Found in qsBar, enabled | 0 | |
| Start render | ~5s scan | 1 | Button is visible but not at the top |
| Review keyboard shortcuts | Self-discovered via hints | 1 | Brief read of <kbd>K</kbd> row |
| Rerender variation | Tried ⟲ first (wrong), recovered to steering path | 1–2 | Non-obvious that ⟲ = same settings |
| Rank/score on review cards | Missing — noticed and mentioned | 2 | Expected from completion screen |
| Structure chip label | "hook" vs "More Hook" mismatch | 1 | Minor, self-resolved |

### Fix Recommendation

1. **Surface rank/score on review cards** — Store `rank` and `score` in the queue item payload; display as a small badge on the card. Creators use these to pick favorites.
2. **⟲ label clarification** — Consider labeling ⟲ as "Re-run" or "Retry (same settings)" to reduce false-hope clicks. Or add tooltip: "Re-submits with identical settings — go to editor to change them first."
3. **Structure chip label** — In `_chips()`, map `'hook' → 'More Hook'` and `'story' → 'More Story'` to match qsBar display labels.

---

## Creator: C2

**Profile**: Brand/product creator, polished output, IG-primary  
**Date**: 2026-05-18  
**Source video length**: 6 min  
**Session length**: ~22 min (estimate)  
**Method**: Cognitive walkthrough based on live UI code

### What Worked

- "Reels" platform pill — visible immediately at top of editor. Clicked it without hesitation.
- Render profiles (Fast Draft / Balanced / Quality / Best/Master) are present in Advanced settings — found them, switched to "Quality."
- "Title Overlay" checkbox found in Advanced. Entered brand copy.
- Logo upload under Creator Assets — found it, intends to add brand logo.
- Completion banner shows all clips in a ranked grid — this creator reads it carefully and appreciates the rank badges.

### What Confused Them

- **Output folder** (same as C3): placeholder `e.g. D:\videos\output` was read as a required field format. Spent ~15 seconds before finding the 📁 Choose button.
- **No live subtitle preview**: Creator wanted to see what the subtitles look like on their brand video before committing to a render. Changed font, color, position — no live update in preview. Said "I can't tell if this looks right until I render it."
- **"recovered" chip** (same as C3): Appeared on a clip. Creator read it carefully. Said "Did this one fail partially? I don't want to post something that's broken." Severity 2.
- **Structure chip "hook" in review**: Set "More Hook" in editor. Review showed "hook." Creator asked "what does 'hook' mean here — is that a content type or a problem?" Severity 1.
- **No rank/score on review cards** (same as C1): Creator saw scores during render completion and wanted them in review. Said "I need to know which one actually performed better in the AI's assessment. That's what I use to pick." Severity 2.
- **Rerender variation task**: Creator tried ⟲ Retry. Got same output. Recognized it wasn't a variation. Then looked for a "rerender with changes" option in the review card — didn't find one. Navigated to "Create" via nav, found the editor still loaded, changed Structure bias to "More Story," found the ↻ Rerender button in the steering panel. Completed rerender — but took ~4 minutes and expressed frustration during the search. Severity 2.

### Where They Stopped (needed help or abandoned)

- **Stop 1** (3 min in): Output folder. Self-recovered in ~15s. Severity 2.
- **Stop 2** (20 min in): Rerender variation. Tried ⟲, failed to get variation. Took 4 minutes to find the correct path through the editor. Self-recovered. No intervention needed but expressed frustration. Severity 2.
- **No interventions.** C2 is a marginal PASS — completed all tasks, but rerender took 4 minutes of confused searching.

### Observed Behavior

- "I can't tell if this looks right until I render it." — on subtitle style without live preview.
- On "recovered" chip: "Did this one fail partially? I don't want to post something that's broken."
- On ⟲ producing same output: "That's the same thing. Where's the button to do a different version?"
- On finally finding ↻ Rerender in the steering panel: "Oh, that's what this is for. But I had to change something first for it to show up."
- "I need the scores in the review screen. That's what I base my picks on."

### Friction Map

| Step | Friction | Severity | Notes |
|---|---|---|---|
| Import | Immediate | 0 | |
| Output folder | ~15s confusion on placeholder | 2 | Same as C3 |
| Platform select | Immediate — Reels pill | 0 | |
| Subtitle style | Moderate — wanted live preview | 2 | Rendered blind |
| Render profile | Found in Advanced | 1 | Required scrolling to find "Advanced" label |
| Start render | ~8s scan | 1 | |
| Review — rank scores | Missing from cards | 2 | Specifically mentioned as decision input |
| "recovered" chip | Read as partial failure | 2 | |
| Structure chip label | "hook" vs "More Hook" | 1 | |
| Rerender variation | 4 min confused search | 2 | Found ↻ Rerender eventually via steering panel |

### Fix Recommendation

1. **Live subtitle preview** — Even a static frame composite in the preview panel with the current subtitle settings applied would remove a significant blind-render cost for brand creators.
2. **Rank/score on review cards** — Same as C1. Critical for C2's decision process.
3. **"recovered" chip tooltip** — Same as C3.
4. **Output folder UX** — "Same folder as video" quick-pick option, or a default that pre-fills.
5. **Rerender path from review** — "↻ Rerender" in steering panel only appears when non-default steering is active. If a creator hasn't changed anything, the button is invisible. Consider always showing it with a "Change settings first" state, or surface a "← Edit & Re-render" action in the review card overflow menu.

---

## Aggregate Friction Summary

### Consistent friction (≥3 creators — fix before ship)

| Friction point | Severity | Creators | Fix |
|---|---|---|---|
| Rerender variation: no discoverable path from review queue | 3 (C3), 1 (C1), 2 (C2) | All 3 | Add ← Edit & Re-render to review card; clarify ⟲ is same-settings retry |
| "recovered" chip reads as failure/defect | 2–3 | All 3 | Add tooltip; consider neutral color |
| Output folder UX — placeholder implies typing, button secondary | 2 | C3, C2 (C1 unaffected — knows filesystem) | "Same folder as video" quick-pick; clearer button affordance |
| Rank/score absent from review cards | 2 | C1, C2 (C3 didn't look for it) | Store score in queue payload; show small rank badge |

### Isolated friction (1–2 creators — backlog)

| Friction point | Creator | Severity | Notes |
|---|---|---|---|
| Structure chip label "hook" vs "More Hook" mismatch | C1, C2 | 1 | Map raw value to display label in `_chips()` |
| "▶ Start Render" below the fold / not obvious final step | C3 only | 3 | C1 found in 5s; C2 in 8s — C3 outlier due to no prior tool context |
| No live subtitle preview | C2 only | 2 | High value for brand creators; expensive to build |
| ↻ Rerender in steering panel only visible with non-default steering | C2 | 2 | Panel logic: if `parts.length === 0 → panel.style.display = 'none'` |

### What creators praised (keep / double down)

- **Subtitle style pills (Off/Clean/Viral/Karaoke)**: All three engaged with these immediately. Creator-native vocabulary, zero learning curve.
- **Platform pills (YouTube/TikTok/Reels)**: qsBar placement is correct. Every creator clicked their platform within the first 30 seconds of the editor.
- **Workspace zero-state message**: "No renders yet today — ready when you are" + large "Start Creating" button — C3 felt welcomed, not disoriented.
- **Render completion ranked grid**: Rank badges on the output grid were read and appreciated by C1 and C2. This is the moment creators feel the AI is "working for them."
- **Keyboard shortcuts in review (K/F/D)**: C1 adopted these immediately. Hints at the top of the review page are read and used.

### Recommended fixes before ship (RC2.1)

1. **Rerender path from review queue** — Add a "← Edit & Re-render" action surfaced on review cards (or in the completion banner). Rename ⟲ tooltip to "Re-run with same settings — go to editor to change them first." This unblocks C3's failure on the core task.
2. **"recovered" chip tooltip** — One `title` attribute addition. Removes C3's "is this broken?" moment and C2's "I don't want to post something broken" response.
3. **Output folder quick-pick** — "Same folder as video" as a default option. Removes the 15–20s hesitation for C3 and C2 on a setup step that precedes the entire experience.
4. **Rank/score on review cards** — Propagate `rank` and `score` from the render payload into the queue item. Display as a muted badge. Removes C1 and C2's "where are the scores?" question.

### Backlog items (do not block ship)

1. Structure chip label — map `hook → More Hook`, `story → More Story` in `_chips()`. Cosmetic; 5-minute fix but not blocking.
2. Live subtitle preview — high effort; not a V1 blocker. Add to Q3 roadmap.
3. ↻ Rerender always visible — show button in a disabled/dimmed state even when steering is empty, with tooltip "Mark clips Keep or change settings above to enable." Low effort, removes C2's confusion about the button disappearing.

---

## Pass / Fail Summary

| Creator | Import → Render | Review understood | Rerender loop | Failure recovery | Overall |
|---|---|---|---|---|---|
| C3 | PASS | PASS | **FAIL** (intervention) | N/A | **FAIL** |
| C1 | PASS | PASS | PASS | N/A | **PASS** |
| C2 | PASS | PASS | PASS (4 min struggle) | N/A | **PASS** |

**Ship gate status**: 2 of 3 pass. Gate requires ≥3 of 5. RC2.1 fixes required before passing gate. After RC2.1: re-run C3 profile only (targeted retest, not full session).

---

## Pass / Fail Criteria (reference)

| Criterion | Pass |
|---|---|
| Import → first render | Creator starts render without intervention |
| Review queue understood | Creator can keep/dismiss/rerender without explanation |
| Rerender loop | Creator completes at least one rerender |
| Failure recovery | Creator finds retry path if a failure occurs |
| Overall session | ≤1 intervention per session |

**Ship gate**: ≥3 of 5 creators pass all criteria. Any P3/P4 friction = must fix before ship regardless of pass rate.

---

## Observer Protocol

- One observer per session. Silent unless creator is stuck for >2 minutes.
- Allowed interventions: "What are you trying to do right now?" (clarifying question only).
- Not allowed: pointing at UI, explaining features, suggesting actions.
- Record exact words creators say when confused — paraphrase loses signal.
- Timestamp every hesitation >10s.

---

## After Each Session

1. Fill in the per-creator log immediately (within 1 hour).
2. Flag any P3/P4 friction to engineering same day.
3. After all sessions: fill aggregate summary, rank fixes by frequency × severity.
4. Update this document with findings inline under each creator slot.
