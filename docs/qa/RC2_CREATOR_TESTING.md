# RC2 — Real Creator Testing

**Branch**: `feature/ai-output-upgrade`  
**Date**: 2026-05-18  
**Status**: Ready for execution  
**Prerequisite**: RC1.1 hotfixes merged, staging build green

---

## Purpose

Validate that real creators — not engineers — can complete the core loop with minimal friction.  
RC1 found code-level bugs. RC2 finds friction, confusion, and broken mental models that code review cannot surface.

**Pass condition**: A creator can complete import → render → review → rerender → choose with ≤1 intervention from the observer.  
**Rule**: Same friction at ≥3 creators = fix it. Single-creator friction = note it, probably ignore it.

---

## Test Group Composition

Recruit 3–5 creators covering:

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

## Observation Areas

### 1. First 60 Seconds (Import & Orient)
- Do they find the import/upload path without prompting?
- What do they look at first — presets, DNA settings, platform selector, or something else?
- Do they read any labels or skip straight to clicking?
- Where does the first hesitation occur?

### 2. Create Flow (Settings → Render)
- Do they understand what "preset" means vs. manual settings?
- Do they change platform? If not, do they seem aware they could?
- Do they notice structure bias / DNA settings? Do they engage with them?
- Does the render start confidently or after searching for the button?
- What do they do while rendering? (Leave? Watch progress? Refreshing?)

### 3. Rerender Loop
- Do they find the rerender path from the review queue without instruction?
- Do they understand what a rerender will change vs. keep?
- Do they expect to be able to edit settings before rerender?
- Do they rerender all parts or just one clip?

### 4. Review Queue
- Do they understand the Keep / Favorite / Dismiss / Retry distinction?
- Do they use keyboard shortcuts or only buttons?
- Do they understand the state sections (Ready to Review / Favorites / Kept)?
- Do they click Open Folder? Do they know what to do with it?
- Does the "recovered" chip cause confusion?

### 5. Trust Chips
- Do they notice the chips (preset, DNA, structure bias, assets)?
- Do they understand what the chips mean?
- Do they trust the output more or less because of them?

### 6. Failure Handling
- If a render fails or partially fails, do they understand what failed?
- Do they find the Retry path?
- Is the error message actionable for them?

---

## Per-Creator Observation Log

Copy this template once per creator session.

```
## Creator: [C1 / C2 / C3 / C4 / C5]
**Profile**: [brief descriptor]
**Date**: 
**Source video length**: 
**Session length**: 

### What Worked
- 

### What Confused Them
- 

### Where They Stopped (needed help or abandoned)
- 

### Observed Behavior (verbatim moments worth quoting)
- 

### Friction Map

| Step | Friction | Severity | Notes |
|---|---|---|---|
| Import | | | |
| Platform select | | | |
| Preset select | | | |
| Start render | | | |
| Review queue | | | |
| Keep/Dismiss | | | |
| Rerender | | | |
| Open folder | | | |

### Fix Recommendation
- 
```

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

## Aggregate Findings Template

After all sessions, fill in:

```
## Aggregate Friction Summary

### Consistent friction (≥3 creators)
| Friction point | Severity | Fix |
|---|---|---|
| | | |

### Isolated friction (1–2 creators)
| Friction point | Creator | Severity | Notes |
|---|---|---|---|
| | | | |

### What creators praised (keep / double down)
- 

### Recommended fixes before ship
1. 
2. 

### Backlog items (do not block ship)
1. 
2. 
```

---

## Pass / Fail Criteria

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
