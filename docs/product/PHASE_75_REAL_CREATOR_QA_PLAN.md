# Phase 75 — Real Creator QA Plan
**Post-74 RC Polish | V1 Ship Readiness Validation**
**Status:** PLANNING — not yet executed
**Branch target:** feature/ai-output-upgrade
**Date:** 2026-05-19

---

## Executive Summary

Phases 63–74 solved the builder's problems: UI overload, review friction, weak clips, inconsistent state, confusing feedback. What has not been validated is whether those solutions translate into a creator experience that actually feels productive.

This phase is not a code audit. It is a structured real-use validation across 20–30 videos in conditions that reflect actual creator behavior: unfamiliar content, impatient expectations, real time pressure, and no awareness of what the tool was designed to do.

**The goal is not to find bugs. The goal is to find friction.**

A technically-working tool that makes creators say "ugh" is not ready to ship. A tool with one rough edge but a clear path from source to sharable clip is.

**Three questions drive every test:**
1. Did the first render produce at least one clip the creator would seriously consider sharing?
2. How many rerenders did it take to get there?
3. At any point did the creator feel confused, misled, or like the tool was working against them?

---

## 1. QA Framework

### Session structure

Run QA in three phases, each building on the previous:

**Phase A — Solo runs (10 videos, no observer)**
Creator runs the tool alone with no guidance. Observe via screen recording or think-aloud protocol. Goal: surface first-contact confusion and unguided behavior.

**Phase B — Paired runs (10 videos, QA observer present)**
Observer watches silently and logs all friction events in real time. Does not explain or help unless creator explicitly stops. Goal: precise friction logging with timestamps.

**Phase C — Stress runs (10 videos, adversarial content)**
Test with low-quality source material, borderline content, short videos, and bad audio. Goal: validate quality floor and fallback behavior under realistic worst-case conditions.

### Per-session structure

Each session = one source video + full tool flow from source selection to at least one clip in review queue.

| Step | What happens | Max time budget |
|---|---|---|
| Source selection | Paste URL or pick local file | 2 min |
| First render | Default settings, no preset override | — |
| First review | Review all clips from first render | 5 min |
| Rerender (if needed) | One rerender with any steering change | — |
| Second review | Review all clips from rerender | 5 min |
| Post-session debrief | 3 questions, max 2 min | 2 min |

### How many sessions

- **Minimum for ship decision:** 20 completed sessions across all content types
- **Target for confidence:** 30 sessions
- **Abort condition:** If 3 consecutive sessions in Phase A produce zero usable clips without a rerender, stop and investigate before continuing

### What to observe and log

For each session, log:
1. Time from source selection to first clip rendered (wall clock)
2. Number of clips produced on first render
3. Number of clips rated "would share" by creator after first render
4. Number of rerenders before creator found a satisfying clip
5. All friction events (see QA Checklist)
6. Any moment the creator expressed confusion, frustration, or surprise
7. Whether the creator used keyboard shortcuts (K/A/D) or mouse only
8. Whether the creator noticed the explainability chips and acted on them
9. Whether memory chips/hints appeared and whether creator used them

---

## 2. Content Matrix

### Test categories and risk profiles

| Category | Description | Risk level | Why |
|---|---|---|---|
| **Podcast** | Single speaker, 20–60 min, dense speech | Low | Natural arc structure; 61s+ defaults aligned; high speech density |
| **Education / Tutorial** | Step-by-step instruction, screen + face | Low–Medium | Clear structure; risk = low visual energy reduces scene density score |
| **Interview (two-person)** | Q&A format, two voices, cuts | Medium | Speaker transitions may fragment arcs; pacing score sensitive to cut timing |
| **Commentary / Opinion** | Single speaker, 5–15 min, opinionated | Medium | Energy varies widely; hook quality depends on opening statement |
| **Finance / Business** | Data-heavy, charts, slower delivery | Medium–High | Low motion score; speech density strong but visual signal weak; risk of uniform scoring |
| **Mixed (B-roll + talking head)** | Some cutaway footage, main speaker | Medium–High | Scene quality varies; pacing stability may flag B-roll transitions |
| **Low-energy talking head** | Minimal movement, quiet delivery | High | Narrow score spread likely; all clips may cluster in experimental tier |
| **Bad audio source** | Background noise, low mic, muffled | High | Speech density unreliable; silence penalty may over-fire; quality floor may over-prune |

### Content sourcing rules

- Use real public content, not synthetic test videos
- Minimum 3 videos per category
- Include at least 2 videos that are clearly "bad" source material per Phase C
- Include at least 1 video under 10 minutes and at least 1 over 40 minutes
- Include at least 2 non-English source videos to test behavior outside primary language assumption
- Do not cherry-pick high-quality sources — include the kind of mediocre content real creators actually work with

### Highest-risk categories for first render quality

**Finance / Business** is the highest risk because the scoring signals that matter most (hook_opening_score, avg_scene_quality) depend on visual energy that financial content structurally lacks. The quality floor (Phase 73.3) may remove genuinely the best clips from this content type.

**Low-energy talking head** is the second highest risk because the narrow-spread condition (all clips within 1.5 points, all experimental tier) is structurally likely for this content. The Phase 73.4 advisory note (not yet implemented) would help here.

**Bad audio** is the third highest risk because silence_penalty behavior is unpredictable when audio quality is borderline.

---

## 3. QA Checklist

Use this checklist for every session. Complete all items in order. Mark each as ✓ (pass), ✗ (fail/friction), or N/A.

### Section A — Source and Setup

```
[ ] A1. Creator selected source without confusion (URL or local file)
[ ] A2. Source video confirmed with name/path visible in UI
[ ] A3. No unexpected error on source selection
[ ] A4. Default settings appeared reasonable to creator without explanation
[ ] A5. Creator understood what platform/aspect ratio selection does
[ ] A6. Creator started render without needing to ask "what do I do now?"
```

### Section B — First Render Output

```
[ ] B1. First render completed without error
[ ] B2. Clips appeared in output panel without UI confusion
[ ] B3. Clip count was sensible (not overwhelming, not zero)
[ ] B4. At least 1 clip scored high enough that creator would seriously consider it
[ ] B5. Quality floor removed obvious weak clips (no clearly bad clips mixed in)
[ ] B6. Clip duration felt appropriate for the content type
[ ] B7. Creator understood clip ranking order without explanation
[ ] B8. Explainability chips (if shown) were useful, not confusing
[ ] B9. Confidence tier ("Strong Candidates" vs "Additional Results") matched creator's own assessment
[ ] B10. No clip showed content creator wouldn't want to share (embarrassing cut points, mid-sentence, etc.)
```

### Section C — Review Flow

```
[ ] C1. Creator knew how to review clips (Keep/Avoid/Download)
[ ] C2. Review counter incremented correctly and was noticed
[ ] C3. Keyboard shortcuts (K/A/D) were discovered or used without prompting
[ ] C4. After Keep/Avoid, focus moved to next clip correctly
[ ] C5. Review completed within 5 minutes for 5 clips
[ ] C6. Creator did not feel overwhelmed by number of clips
[ ] C7. Creator did not feel underwhelmed (too few clips to compare)
[ ] C8. No clip was buried that creator later identified as the best one
```

### Section D — Rerender and Steering

```
[ ] D1. Creator knew a rerender was possible if first render was unsatisfying
[ ] D2. Creator understood what changing a setting would do before rerendering
[ ] D3. Rerender produced visibly different output (not identical to first)
[ ] D4. Rerender did not require more than 1 additional attempt to find a good clip
[ ] D5. Memory chips / steering suggestions (if shown) were accurate and acted on
[ ] D6. Rerender arrival animation fired (not silently loading) — Phase 74.1 validation
```

### Section E — Review Queue

```
[ ] E1. Creator found the Review queue without help
[ ] E2. ReviewQueue buttons (Keep, Fav, Dismiss, Retry, Open) were self-explanatory — Phase 74.5 validation
[ ] E3. Keyboard shortcuts in ReviewQueue worked correctly
[ ] E4. Dismissed clip Undo was discovered after dismissing a clip the creator wanted
[ ] E5. Review queue badge count was accurate
[ ] E6. ReviewQueue card auto-focus advanced to next card after action
```

### Section F — Trust and Consistency

```
[ ] F1. No unexpected state reset or data loss during session
[ ] F2. Toast messages were understandable and appropriately timed
[ ] F3. No moment where creator was unsure if an action had worked
[ ] F4. Arrow indicators in editor (▸/▾) correctly reflected open/closed state — Phase 74.3 validation
[ ] F5. No "beta feeling" moments (confusing labels, stuck loading, ghost state)
[ ] F6. Creator trusted the ranking order and did not feel the need to override everything
[ ] F7. No moment where creator felt "the tool is working against me"
```

### Section G — Session Metrics (record for every session)

```
Source video:          _______________________________________________
Duration:              ___ min
Content type:          _______________________________________________
Clips on first render: ___
"Would share" clips:   ___
Rerender count:        ___
Time to first good clip: ___ min
Friction events logged: ___
Creator satisfaction (1–5): ___
```

### Post-session debrief questions (ask exactly as written)

1. "What, if anything, felt confusing or annoying during this session?"
2. "Was there a moment where you weren't sure what to do next?"
3. "Would you use this tool again for your next video? Why or why not?"

Do not prompt or suggest answers. Record verbatim.

---

## 4. Friction Classification

### Categories

**P0 — Trust blocker**
Creator cannot confidently complete the flow or loses trust in the tool entirely. Requires fix before ship.

Examples:
- Creator gets no usable clips from content that should work
- A rerender produces identical results to the first render with no explanation
- Creator cannot find how to download a clip they want
- A setting change silently had no effect
- Tool shows an error state with no recovery path

**P1 — Friction / annoying but usable**
Creator can complete the flow but the experience leaves a negative impression. Should fix before ship if possible; document if not.

Examples:
- Creator has to rerender 3+ times before finding a good clip
- Review flow takes >10 minutes for a standard 5-clip output
- Clip duration is consistently wrong for the content type without platform selection
- Creator misses the best clip because it was buried under lower-ranked clips
- Memory suggestions appeared but creator didn't trust them

**P2 — Minor polish**
Noticeable but doesn't affect the core result. Document for Phase 76 backlog.

Examples:
- A label is slightly unclear but creator eventually figured it out
- Toast timing felt slightly off
- Creator expected a button to do something slightly different
- Visual alignment inconsistency noticed
- Arrow/indicator micro-animation felt abrupt

### Friction log format

For each friction event, record:

```
Event ID:    F-[session#]-[sequence#]
Severity:    P0 / P1 / P2
Step:        (which QA section: A/B/C/D/E/F)
Trigger:     (what the creator did immediately before)
Observation: (exactly what happened and what creator said/did)
Root cause:  (if known — code location or design decision)
```

---

## 5. Stop Conditions

### Ship thresholds

The tool is ready to ship V1 when ALL of the following are true across at least 20 completed sessions:

| Metric | Threshold | Why |
|---|---|---|
| First render usable (≥1 clip worth sharing) | ≥ 70% of sessions | Below 70% means rerenders are load-bearing for basic use |
| Average rerender count before first good clip | ≤ 1.5 | More than 1.5 rerenders means first render is not reliable enough |
| P0 trust blockers found | 0 (unresolved) | P0s must be fixed before ship, no exceptions |
| Sessions with creator confusion > 2 events | ≤ 20% of sessions | Confusion is a retention killer |
| Review queue flow (5 clips in < 5 min) | ≥ 80% of sessions | If review is slow, review velocity improvements haven't landed |
| Creator would use again (score ≥ 3/5) | ≥ 75% of sessions | The most honest metric |

### Content-type minimum pass rates

Because content types have different risk profiles, minimum pass rates per category:

| Category | Min "first render usable" rate |
|---|---|
| Podcast | 85% |
| Education | 80% |
| Commentary | 75% |
| Interview | 70% |
| Finance / Business | 65% |
| Mixed content | 65% |
| Low-energy talking head | 55% |
| Bad audio | 45% |

Bad audio and low-energy content have lower thresholds because these are structurally challenging. If they fall below threshold, document but do not block ship — add a known limitation note.

### Abort conditions (stop QA and investigate before continuing)

- 3 consecutive sessions produce 0 usable clips without a rerender
- Any P0 trust blocker appears in 2 or more sessions
- Quality floor (`viral_score < 25`) removes ALL clips in a single session (always-keep-1 guard should prevent this — if it fails, it is a code bug)
- Review queue auto-focus advance stops working (Phase 72 regression check)
- Second render arrival animation does not fire (Phase 74.1 regression check)

---

## 6. Reusable QA Template

Copy this template for each session. File naming: `qa_session_[NNN]_[content_type]_[date].md`

```markdown
# QA Session [NNN]
**Date:** YYYY-MM-DD
**Content type:** [podcast / education / commentary / interview / finance / mixed / talking-head / bad-audio]
**Source:** [URL or filename — no PII]
**Duration:** [X min]
**QA phase:** [A / B / C]
**Observer:** [solo / paired]

---

## Session Metrics

| Metric | Value |
|---|---|
| Clips on first render | |
| "Would share" clips (first render) | |
| Rerender count | |
| Time to first good clip (min) | |
| Creator satisfaction (1–5) | |
| Total friction events | |

---

## QA Checklist Results

### A — Source and Setup
A1 [ ] A2 [ ] A3 [ ] A4 [ ] A5 [ ] A6 [ ]

### B — First Render Output
B1 [ ] B2 [ ] B3 [ ] B4 [ ] B5 [ ] B6 [ ] B7 [ ] B8 [ ] B9 [ ] B10 [ ]

### C — Review Flow
C1 [ ] C2 [ ] C3 [ ] C4 [ ] C5 [ ] C6 [ ] C7 [ ] C8 [ ]

### D — Rerender and Steering
D1 [ ] D2 [ ] D3 [ ] D4 [ ] D5 [ ] D6 [ ]

### E — Review Queue
E1 [ ] E2 [ ] E3 [ ] E4 [ ] E5 [ ] E6 [ ]

### F — Trust and Consistency
F1 [ ] F2 [ ] F3 [ ] F4 [ ] F5 [ ] F6 [ ] F7 [ ]

---

## Friction Events

| ID | Severity | Step | Trigger | Observation | Root cause |
|---|---|---|---|---|---|
| F-[NNN]-01 | | | | | |
| F-[NNN]-02 | | | | | |

---

## Post-session Debrief

**Q1 — What felt confusing or annoying?**
> [verbatim response]

**Q2 — Was there a moment you weren't sure what to do next?**
> [verbatim response]

**Q3 — Would you use this again? Why or why not?**
> [verbatim response]

---

## Session Summary

**First render assessment:** [usable / not usable / borderline]
**Highest-severity finding:** [P0 / P1 / P2 / none]
**Most interesting friction event:** [ID or description]
**Regression checks passed:** [74.1 arrival ✓/✗] [74.3 arrow ✓/✗] [74.5 labels ✓/✗] [73.3 floor ✓/✗]
**Notes:**
```

---

## 7. Friction-to-Phase Mapping

When a friction event is found, use this table to determine which phase it belongs to:

| Finding area | Likely phase owner |
|---|---|
| First render no usable clips — podcast/education | Phase 73 (defaults not yet deployed: 73.1/73.2) |
| First render too many weak clips | Phase 73.3 (quality floor — already deployed) |
| Platform selection does not change duration | Phase 73 (73.1 not yet deployed) |
| Too many clips on first render | Phase 73 (73.2 default=6 not yet deployed) |
| Arrival animation doesn't fire on rerender | Phase 74.1 regression |
| Arrow doesn't toggle on inspector group | Phase 74.3 regression |
| ReviewQueue buttons confusing | Phase 74.5 regression |
| Toast messages inconsistent | Phase 74.2 regression |
| Review flow slow or awkward | Phase 72 (review velocity) |
| Memory chips appear but feel wrong | Phase 67/68 (memory/feedback visibility) |
| Explainability chips feel noisy | Phase 66 (explainability) |
| Keyboard shortcuts not discovered | Phase 72 (consider discoverability improvement in Phase 76) |
| Creator confused about rerender vs new render | Phase 71/67 (steering panel clarity) |
| Clip duration consistently wrong | Phase 73.1 deferred — document as known gap |
| Uniform scoring / all "Strong Candidates" noise | Phase 73.4 not yet deployed — document |

---

## 8. Definition of Done

Phase 75 is complete when:

- [ ] Minimum 20 sessions completed across all 8 content categories (minimum 2 per category)
- [ ] All friction events classified P0/P1/P2
- [ ] All P0 findings either resolved or have an explicit owner and timeline
- [ ] Ship thresholds assessed against actual session data
- [ ] Phase 76 backlog populated with P1/P2 findings that were not resolved
- [ ] Regression checks for Phases 72, 73.3, and 74 confirmed across sessions
- [ ] QA summary document written with aggregate metrics and ship/hold recommendation

The QA summary document format:
- Total sessions run
- Pass/fail against each stop condition threshold
- Top 5 friction events by frequency
- Explicit ship recommendation: GO / HOLD / GO WITH KNOWN LIMITATIONS
- If HOLD: specific P0 items that must resolve before revisiting

---

## Appendix — Known Gaps Entering QA

These are items that may produce friction events during QA but are **intentional deferred decisions**, not bugs:

| Gap | Status | Impact |
|---|---|---|
| `evMinPart` default still 70s (73.1 not deployed) | Planned, not implemented | Story-complete 61–70s arcs may produce 0 candidates |
| `evMaxExportParts` default still 0/unlimited (73.2 not deployed) | Planned, not implemented | First render may produce too many clips |
| Platform pill does not set duration (73.1 rejected auto-link) | Intentional, documented in 73-A audit | TikTok/Reels clips may be wrong duration |
| Narrow-spread advisory note (73.4 not deployed) | Optional P1, not implemented | Low-energy content shows no confidence signal |
| Dirty flag protection for duration fields | Intentional deferred | No auto-linking until built |

If QA surfaces consistent P0 friction from any of these gaps, escalate to Phase 76 scope.
