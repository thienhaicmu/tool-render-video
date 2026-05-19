# Phase 75-A — QA Execution Kit
## Real Creator QA | Human Operator Guide

**Status:** READY TO RUN  
**Date:** 2026-05-19  
**Branch:** feature/ai-output-upgrade  
**Sessions required:** 10 (Phase A solo runs)  
**Operator role:** Observer only — do not help, explain, or fix  

Source documents:
- [PHASE_75_REAL_CREATOR_QA_PLAN.md](PHASE_75_REAL_CREATOR_QA_PLAN.md)
- [PHASE_75_EXPECTED_FRICTION_ANALYSIS.md](PHASE_75_EXPECTED_FRICTION_ANALYSIS.md)

---

## 1. Executive Summary

You are running 10 unguided creator sessions. The creator uses the tool alone. You watch and log. You say nothing that helps them. The goal is to find **real friction** — not bugs, not crashes, but moments that make a creator think "ugh" or feel like the tool is working against them.

Each session takes 15–25 minutes of creator time. Allow 30 minutes per session total including setup and debrief.

At the end of 10 sessions, fill in the aggregation table and write a one-page summary. That summary determines whether the tool ships or goes back for Phase 76 fixes.

**What you are measuring:**
1. Can a creator get at least one usable clip from a first render?
2. How many rerenders does it take?
3. At what moments does the tool create confusion or frustration?

**What you are NOT doing:**
- Fixing anything
- Explaining anything
- Simulating results
- Guessing how sessions would go

---

## 2. Quick Start

### Before the first session (one-time setup, 10 minutes)

- [ ] Server is running and reachable at `localhost` (or wherever tool is hosted)
- [ ] You have 10 source videos ready — see Section 3
- [ ] You have a folder for session files: `docs/qa/phase75a/`
- [ ] You have a screen recorder running (optional but strongly recommended)
- [ ] You have copied the session template (Section 4) into 10 separate files:
  ```
  qa_session_001_podcast_YYYYMMDD.md
  qa_session_002_podcast_YYYYMMDD.md
  qa_session_003_education_YYYYMMDD.md
  qa_session_004_education_YYYYMMDD.md
  qa_session_005_finance_YYYYMMDD.md
  qa_session_006_finance_YYYYMMDD.md
  qa_session_007_commentary_YYYYMMDD.md
  qa_session_008_interview_YYYYMMDD.md
  qa_session_009_mixed_YYYYMMDD.md
  qa_session_010_talking_head_YYYYMMDD.md
  ```

### Per session (5-minute setup, then observe)

**Step 1 — Brief the creator (60 seconds, say this exactly):**
> "I'm going to watch you use this video tool. There are no right or wrong answers. Do whatever feels natural. I won't help or explain anything — that's on purpose. Just narrate what you're thinking as you go if you can. Ready?"

**Step 2 — Hand them the source video:**
Give them the URL or point to the local file. Do not explain what it is for or what to do with it.

**Step 3 — Observe and log:**
Open your session template file. Log every hesitation, reread, repeated click, verbal comment, or expression of confusion or satisfaction.

**Step 4 — Stop at maximum 2 rerenders:**
Let the creator run up to 2 rerenders if they choose. Do not suggest rerenders. Do not stop them from rerending if they want to.

**Step 5 — Debrief (3 questions, 2 minutes):**
Ask exactly as written — see Section 4 template. Record verbatim. Do not prompt or react.

**Step 6 — Save session file and move on.**

---

## 3. Video Sourcing Guide

### Required mix (10 videos)

| # | Category | Count | Risk |
|---|---|---|---|
| 1–2 | Podcast | 2 | Low |
| 3–4 | Education / Tutorial | 2 | Low–Medium |
| 5–6 | Finance / Business | 2 | Medium–High |
| 7 | Commentary / Opinion | 1 | Medium |
| 8 | Interview (two-person) | 1 | Medium |
| 9 | Mixed Content (B-roll + talking head) | 1 | Medium–High |
| 10 | Low-energy Talking Head | 1 | High |

**Bonus (include any if you have them):**
- 1 video with bad audio (background noise, low mic)
- 1 non-English source video
- 1 mediocre source (boring content, not particularly well-made)

---

### Category 1 — Podcast

**What to look for:**
- One or two hosts, long-form, mostly talking
- 20–60 minutes preferred; minimum 15 minutes
- Dense continuous speech, few scene cuts
- Natural conversational pace — not scripted reads

**Good test content (realistic):**
- A weekly show that is 10–30 episodes in — not a polished flagship production
- Two hosts that talk over each other occasionally
- No professional B-roll, just a static camera or Zoom recording

**Bad test content (disqualifiers):**
- Heavily produced podcast with constant B-roll (that's mixed content)
- Under 10 minutes (too short to test clipping behavior)
- Scripted monologue read from a teleprompter (unusual speech pattern)

**Where to find it:**
Search YouTube for: `"podcast" OR "episode" site:youtube.com` — filter by duration > 20 minutes. Look for channels in the 1,000–50,000 subscriber range. Avoid flagship productions from major media brands.

**Known risk to watch (from friction analysis):**
- Expect 8–15 clips on first render (unlimited default)
- Expect all clips labeled "Strong Candidates"
- Watch for review fatigue — creator scrolling without deciding

---

### Category 2 — Education / Tutorial

**What to look for:**
- Single instructor explaining something step-by-step
- 10–30 minutes preferred
- Screen recording, whiteboard, or face-cam with slides
- Technical or skill-based topic (coding, design, cooking, fitness)

**Good test content (realistic):**
- A solo creator teaching their workflow — not a polished Skillshare course
- Some dead time between steps ("okay so now I'm going to...")
- Mix of explanation and demonstration

**Bad test content (disqualifiers):**
- Highly produced eLearning with professional editing (too clean)
- Pure music or art tutorial with no narration (no speech signal)
- Under 8 minutes

**Where to find it:**
YouTube search: `"how to" OR "tutorial" filetype:` — any niche. Look for mid-tier channels, not top 10 results. Good targets: programming tutorials, cooking techniques, fitness form videos.

**Known risk to watch (from friction analysis):**
- Creator's "aha moment" (key formula, key technique) may not rank #1
- Screen content → low visual intensity → may depress ranking of the most important segment
- Watch for creator identifying their preferred clip and checking its position

---

### Category 3 — Finance / Business

**What to look for:**
- Single presenter, professional setting, relatively slow delivery
- Charts, numbers, market commentary, business advice
- 15–45 minutes preferred
- No B-roll cutaways — static shot or slow zoom

**Good test content (realistic):**
- An independent finance analyst or business commentator on YouTube
- Not a Bloomberg or CNBC segment (too much B-roll = mixed content)
- Calm, measured delivery — not high-energy sales pitch

**Bad test content (disqualifiers):**
- Heavy B-roll financial news segments
- Earnings call with rapid back-and-forth (that's interview)
- Under 10 minutes

**Where to find it:**
YouTube search: `finance analysis OR market update OR business strategy` — filter duration > 15 min. Target independent analysts (1,000–200,000 subscribers).

**Known risk to watch (from friction analysis):**  
**HIGHEST RISK CATEGORY.** Quality floor may fire silently, producing 1 clip on a 30-minute source. If creator gets 1 clip:
- Log the clip count immediately
- Note whether creator assumes this is normal
- Note whether creator rerenders expecting more
- This is a predicted P0 — watch carefully

---

### Category 4 — Commentary / Opinion

**What to look for:**
- Single host reacting to news, trends, or another creator's content
- 5–15 minutes preferred (shorter than podcast)
- High vocal energy, variable pacing — quiet then loud reactions
- May include clips of what they're reacting to

**Good test content (realistic):**
- A creator reacting to viral content or news events
- Energy peaks and valleys — not uniform delivery
- Occasional visual of source content (1–3 seconds) mixed in

**Bad test content (disqualifiers):**
- Fully static reaction ("react podcast") — that's podcast type
- Under 5 minutes (too short for multiple 61s candidates)
- Heavily edited montage (that's mixed content)

**Where to find it:**
YouTube: `"my thoughts on" OR "reaction to" OR "commentary"` — mid-tier creators, 5,000–500,000 subscribers.

**Known risk to watch (from friction analysis):**
- Best emotional peak may be 45–60s — shorter than the 61s emission gate
- Watch for creator identifying a moment ("that right there") that is NOT its own clip
- If best moment appears mid-clip (not at the start), log it as a potential CONFIRMED prediction

---

### Category 5 — Interview (Two-Person)

**What to look for:**
- Host + guest, Q&A format
- 20–60 minutes
- Clear turn-taking: question, then answer
- Video interview with camera cuts OR audio-only podcast style

**Good test content (realistic):**
- Independent creator interviewing a practitioner or expert
- Some awkward pauses, topic pivots, follow-up questions
- Not a polished late-night style production

**Bad test content (disqualifiers):**
- Panel discussions with 3+ people (too complex)
- Interview edited into short clips (no long-form structure to test)
- Under 15 minutes

**Where to find it:**
YouTube: `"interview with" OR "I spoke with"` — mid-tier creators in business, tech, personal development, or creative spaces.

**Known risk to watch (from friction analysis):**
- Top-ranked clip may start with the answer, not the question
- Creator may want Q+A as a unit but tool may separate them
- Watch for creator rewinding a clip to find where the question was

---

### Category 6 — Mixed Content (B-roll + Talking Head)

**What to look for:**
- Main speaker with some cutaway B-roll footage mixed in
- 10–30 minutes
- Clear sections: presenter talking, then illustrative footage, then back to presenter

**Good test content (realistic):**
- Travel vlog with narration + location shots
- Documentary-style video essay with interview + illustrative clips
- A product review with face-cam + product footage cutaways

**Bad test content (disqualifiers):**
- Pure B-roll with no talking head (no speech signal)
- Music video or cinematic content (no speech)
- Highly produced short-form content (<5 min)

**Where to find it:**
YouTube: `documentary style OR video essay OR vlog` — travel, food, history, or tech spaces.

**Known risk to watch (from friction analysis):**
- B-roll segments may rank above talking-head moments
- Creator's "hero soundbite" may be buried under visually-dense B-roll clips
- Watch for creator saying "that's not what the video is about"

---

### Category 7 — Low-Energy Talking Head

**What to look for:**
- Solo speaker, calm and measured delivery
- Minimal gestures, static background, consistent lighting
- No cuts or very few cuts
- 10–30 minutes

**Good test content (realistic):**
- A founder explaining their product roadmap
- A consultant delivering calm advice directly to camera
- An educator speaking without slides or animation

**Bad test content (disqualifiers):**
- High-energy motivational speaker (that's commentary)
- Presenter with B-roll (that's mixed content)
- Under 8 minutes

**Where to find it:**
YouTube: `product walkthrough OR founder story OR calm business update` — B2B SaaS, consulting, or professional services creators.

**Known risk to watch (from friction analysis):**  
**SECOND HIGHEST RISK CATEGORY.** Expect all clips labeled "Strong Candidates" with no differentiation. Watch for:
- Creator unable to identify which clip to use
- Creator assuming the AI is making random picks
- Review fatigue without any action taken

---

### Quick video acquisition checklist (before sessions start)

```
[ ] 2 podcast videos (each 20+ min)
[ ] 2 education videos (each 10+ min, screen or face-cam)
[ ] 2 finance/business videos (each 15+ min, static shot)
[ ] 1 commentary video (5–15 min, energetic)
[ ] 1 two-person interview (20+ min)
[ ] 1 mixed content video (10+ min, B-roll + talking head)
[ ] 1 low-energy talking head (10+ min, static delivery)
[ ] (Optional) 1 with bad audio
[ ] (Optional) 1 non-English
```

---

## 4. Session Template

Copy this for each session. Save as `qa_session_[NNN]_[type]_[YYYYMMDD].md`.

---

```markdown
# QA Session [NNN]

**Date:** YYYY-MM-DD  
**Content type:** [podcast / education / finance / commentary / interview / mixed / talking-head / bad-audio]  
**Source:** [URL or filename — no PII]  
**Source duration:** [X min]  
**QA phase:** A  
**Observer:** [name or initials]  
**Screen recording:** YES / NO  

---

## Session Metrics (fill during / immediately after)

| Metric | Value |
|---|---|
| Clips on first render | |
| Clips labeled "Strong Candidates" on first render | |
| Creator's self-identified best clip position (1st / 2nd / 3rd / buried) | |
| Time to first render complete (min) | |
| Time until creator said "ok this is usable" or equivalent (min) | |
| Rerender count (0 / 1 / 2) | |
| Total friction events logged | |

---

## First Render Assessment

**Was first render usable?**
- [ ] YES — creator found at least one clip they'd seriously use
- [ ] PARTIAL — something was there but required a rerender to feel confident
- [ ] NO — first render produced nothing usable

**First render confidence (ask creator or observe their behavior):**
- [ ] A — "I'd stop here if this were a deadline"
- [ ] B — "I'd try one more render"
- [ ] C — "I definitely need to rerender"

---

## QA Checklist

Mark: ✓ pass | ✗ friction | — not applicable | ? unclear

### A — Source and Setup
```
A1 [ ] Creator selected source without confusion (URL or local file)
A2 [ ] Source video name/path visible and correct in UI
A3 [ ] No unexpected error on source selection
A4 [ ] Default settings appeared reasonable — creator didn't ask "what does this mean?"
A5 [ ] Creator understood platform/aspect ratio selection without help
A6 [ ] Creator started render without asking "what do I do now?"
```

### B — First Render Output
```
B1  [ ] First render completed without error
B2  [ ] Clips appeared in output panel — creator understood what they were
B3  [ ] Clip count felt sensible (not overwhelming, not zero)
B4  [ ] At least 1 clip creator would seriously consider sharing
B5  [ ] No obviously bad clips mixed in (mid-sentence cuts, embarrassing moments)
B6  [ ] Clip duration felt appropriate for content type
B7  [ ] Creator understood ranking order without explanation
B8  [ ] Explainability chips (if shown) were useful, not confusing
B9  [ ] "Strong Candidates" label matched creator's own assessment
B10 [ ] Creator did not feel misled by any label or tier description
```

### C — Review Flow
```
C1 [ ] Creator understood Keep / Avoid / Download without asking
C2 [ ] Review badge / counter was noticed
C3 [ ] Creator used keyboard shortcuts (K/F/D) — discovered on own? YES / NO / DID NOT USE
C4 [ ] Focus moved to next clip correctly after Keep/Avoid action
C5 [ ] Creator reviewed 5+ clips within 5 minutes
C6 [ ] Creator did not feel overwhelmed (too many clips)
C7 [ ] Creator did not feel underwhelmed (too few to compare)
C8 [ ] No clip was buried that creator later identified as their preferred one
```

### D — Rerender and Steering
```
D1 [ ] Creator knew rerender was possible if unsatisfied (or: never rerended — mark N/A)
D2 [ ] Creator understood what changing a setting would do before rerending
D3 [ ] Rerender produced different output from first render
D4 [ ] Rerender required ≤ 1 additional attempt
D5 [ ] Rerender arrival animation fired (not silently loading)  [74.1 check]
```

### E — Review Queue
```
E1 [ ] Creator found Review queue without help
E2 [ ] Queue buttons (Keep / Fav / Dismiss / Retry / Open) were self-explanatory  [74.5 check]
E3 [ ] Keyboard shortcuts in queue worked
E4 [ ] Undo appeared and was usable if creator dismissed a clip by mistake
E5 [ ] Queue badge count was accurate
E6 [ ] Card auto-focus advanced to next after each action
```

### F — Trust and Consistency
```
F1 [ ] No unexpected state reset or data loss
F2 [ ] Toast messages were clear and well-timed
F3 [ ] No moment where creator was unsure if an action worked
F4 [ ] Arrow indicators (▸/▾) correctly reflected open/closed state  [74.3 check]
F5 [ ] No "beta feeling" moments (stuck loading, ghost state, confusing labels)
F6 [ ] Creator trusted clip ranking — did not feel the need to override everything
F7 [ ] No moment creator said or implied "the tool is fighting me"
```

---

## Friction Events

*Add a row for each event. Log in real time — don't reconstruct after.*

| ID | Severity | Step | What creator did | What happened / what creator said | Root cause (if known) |
|---|---|---|---|---|---|
| F-[NNN]-01 | P0/P1/P2 | A/B/C/D/E/F | | | |
| F-[NNN]-02 | P0/P1/P2 | A/B/C/D/E/F | | | |
| F-[NNN]-03 | P0/P1/P2 | A/B/C/D/E/F | | | |

---

## Prediction Check

Compare session observations to PHASE_75_EXPECTED_FRICTION_ANALYSIS.md predictions.

| Predicted Event | Status | Notes |
|---|---|---|
| All clips labeled "Strong Candidates" — no differentiation | CONFIRMED / PARTIAL / REFUTED / N/A | |
| Unlimited clips → review fatigue | CONFIRMED / PARTIAL / REFUTED / N/A | |
| Best peak moment not exported as standalone clip | CONFIRMED / PARTIAL / REFUTED / N/A | |
| Silent quality floor → 1-clip output, no explanation | CONFIRMED / PARTIAL / REFUTED / N/A | |
| Best clip buried in position 3–5 | CONFIRMED / PARTIAL / REFUTED / N/A | |
| Rerender produces same result | CONFIRMED / PARTIAL / REFUTED / N/A | |

*If reality contradicts prediction, note it in the Notes column. Reality wins.*

---

## Post-Session Debrief

Ask exactly as written. Record verbatim. Do not prompt.

**Q1 — "What, if anything, felt confusing or annoying during this session?"**
>

**Q2 — "Was there a moment where you weren't sure what to do next?"**
>

**Q3 — "Would you use this tool again for your next video? Why or why not?"**
>

---

## Session Summary

**First render usable:** YES / PARTIAL / NO  
**Highest severity finding:** P0 / P1 / P2 / none  
**Would this block ship?** YES / NO  
**Most important friction event:** [ID or one-line description]  
**Regression checks:** 74.1 arrival ✓/✗ | 74.3 arrow ✓/✗ | 74.5 queue labels ✓/✗ | 73.3 floor ✓/✗  
**Surprise (anything unexpected that wasn't in the prediction doc):**

```

---

## 5. Observer Guide

### Your role

You are a silent witness. You log what happens. You do not influence what happens.

The value of this data comes entirely from the creator behaving as they would if you weren't there. The moment you help, explain, or react, the data is contaminated.

---

### What NOT to do

**Do not explain the tool:**
- Do not say what K, F, or D do
- Do not say what "Strong Candidates" means
- Do not explain why there is only one clip
- Do not explain the Review queue
- Do not explain what a rerender does
- Do not explain any label, chip, or icon

**Do not coach:**
- Do not say "try the keyboard shortcut"
- Do not say "you can rerender if you want"
- Do not say "that clip is ranked first because..."
- Do not say "the quality filter removed the others"

**Do not comfort:**
- Do not say "that's expected" when something confuses them
- Do not say "don't worry about that"
- Do not say "it's a known issue"

**Do not react:**
- Do not nod when they make a correct choice
- Do not wince when they struggle
- Do not show that you know what's happening

**Do not fix during session:**
- Do not change settings before or after they run a render
- Do not reset the queue
- Do not clear state between renders unless the creator explicitly does it
- Do not open a different browser tab to check something

---

### What you CAN do

- Say "keep going" if they freeze and look at you for direction
- Say "whatever you'd naturally do" if they ask "what should I do now?"
- Take notes — silently
- Start and stop screen recording
- Ask the 3 debrief questions after the session ends

If the creator seems genuinely stuck for more than 2 minutes on something that prevents any further progress, you may say: "Do whatever you'd do if I wasn't here." That is the limit of your intervention.

---

### What to log in real time

You cannot reconstruct friction accurately after the fact. Log while it's happening.

**Log immediately when you see:**
- Creator pauses and rereads a label
- Creator clicks something twice (expected first click to work)
- Creator says anything out loud ("hm," "wait," "that's weird," "okay...")
- Creator's face or body language signals confusion or disappointment
- Creator scrolls through clips without taking action
- Creator opens and closes the same panel twice
- Creator asks you a question (log the question exactly — even if you don't answer it)
- Creator says "I thought it would..." or "I expected..."

**Note timestamps** (approximate minute:second from session start) for any P0 or P1 event.

---

### If a P0 happens

A P0 is a trust blocker. Examples:
- Creator gets zero clips from a source that should work
- Rerender produces identical results with no explanation
- Creator cannot find how to access a clip they want
- Creator says "this doesn't work" and stops trying

When a P0 happens:
1. Log it immediately with maximum detail
2. Let the session continue naturally — do not stop it
3. Note whether the creator recovers on their own
4. Mark "Would block ship: YES" in the session summary
5. Do not fix it during the session

---

## 6. Aggregation Template

Fill this after all 10 sessions are complete. One row per session.

```markdown
# Phase 75-A — Session Aggregation

**Sessions complete:** ___ / 10  
**Date range:** YYYY-MM-DD to YYYY-MM-DD  

---

## Session Summary Table

| Session | Type | First Render | Confidence | Best Clip Pos | Clip Count | Rerenders | P0? | P1 count | Block ship? |
|---|---|---|---|---|---|---|---|---|---|
| S001 | podcast | YES/PARTIAL/NO | A/B/C | 1st/2-3/buried | | 0/1/2 | Y/N | | Y/N |
| S002 | podcast | | | | | | | | |
| S003 | education | | | | | | | | |
| S004 | education | | | | | | | | |
| S005 | finance | | | | | | | | |
| S006 | finance | | | | | | | | |
| S007 | commentary | | | | | | | | |
| S008 | interview | | | | | | | | |
| S009 | mixed | | | | | | | | |
| S010 | talking-head | | | | | | | | |

---

## Aggregate Metrics

| Metric | Result | Threshold | Pass? |
|---|---|---|---|
| First render usable rate | __/10 (___%) | ≥ 70% | YES / NO |
| Avg rerenders before usable clip | ___ | ≤ 1.5 | YES / NO |
| Sessions with P0 trust blocker | ___ | 0 | YES / NO |
| Sessions with >2 confusion events | ___ | ≤ 2 of 10 | YES / NO |
| Creator would use again (≥3/5) | __/10 (___%) | ≥ 75% | YES / NO |

---

## Top Friction Events (by frequency across sessions)

| Event | Sessions affected | Severity | Content types | Block ship? |
|---|---|---|---|---|
| | | P0/P1/P2 | | Y/N |
| | | | | |
| | | | | |
| | | | | |
| | | | | |

---

## Prediction Accuracy

| Predicted Event (from friction analysis) | Outcome | Sessions confirmed |
|---|---|---|
| All clips labeled "Strong Candidates" — no differentiation | CONFIRMED/PARTIAL/REFUTED | |
| Unlimited clips → review fatigue | | |
| Best peak moment not exported as standalone clip | | |
| Silent quality floor → 1-clip output, no explanation | | |
| Best clip buried in position 3–5 | | |
| Rerender produces same result | | |
| B-roll clips ranked above talking-head clips | | |
| Interview Q+A arc split | | |
| Silence penalty removes intentional pause clip | | |
| Bad audio clips rank normally | | |

---

## Regression Check Summary

| Fix (Phase) | Sessions tested | All passed? | Notes |
|---|---|---|---|
| 74.1 — Rerender arrival animation | | YES/NO | |
| 74.2 — Toast message wording | | YES/NO | |
| 74.3 — Inspector arrow toggle | | YES/NO | |
| 74.5 — Review queue button labels | | YES/NO | |
| 73.3 — Quality floor behavior | | YES/NO | |

---

## Ship Readiness

**All stop thresholds met:** YES / NO  
**Unresolved P0s:** ___  
**Recommendation:** GO / HOLD / GO WITH KNOWN LIMITATIONS  

**If HOLD — specific P0 items that must resolve:**
1.
2.

**If GO WITH KNOWN LIMITATIONS — document here:**
1.
2.

---

## Surprises (things not predicted by friction analysis)

1.
2.
3.

---

## Recommended Phase 76 Scope (top P1/P2 items not resolved)

1.
2.
3.
4.
```

---

## 7. Stop Conditions

### Stop a session early if:

| Condition | Action |
|---|---|
| Creator is visibly distressed (not just frustrated) | Stop session. Thank them. Move on. Do not use the data. |
| Technical error prevents any render from completing | Stop session. Log error. Fix before continuing. |
| Creator explicitly asks to stop | Stop immediately. Record what happened up to that point. |

Do not stop a session because of friction. Friction is data. Let it happen.

### Stop ALL sessions (abort QA, investigate before continuing) if:

| Condition | Meaning |
|---|---|
| 3 consecutive sessions produce zero usable clips (first render NO, rerender also NO) | Engine-level failure — investigate render_pipeline.py and quality floor before continuing |
| Any P0 trust blocker confirmed in 2 or more sessions | P0 must be fixed before remaining sessions are meaningful |
| Quality floor removes ALL clips AND the top-1 fallback guard did not fire | Code bug in 73.3 — the fallback-to-top-1 is supposed to prevent empty output |
| Rerender arrival animation fails in 3+ sessions | Phase 74.1 regression — investigate before continuing |
| Review queue auto-focus stops working in 3+ sessions | Phase 72 regression — investigate before continuing |

When you abort: stop all sessions. Write up what you observed so far. Do not fill in the aggregation template with incomplete data. Escalate to Phase 76.

---

## 8. Definition of Done

Phase 75-A is complete when ALL of the following are true:

```
[ ] 10 sessions completed (or abort decision documented with reasons)
[ ] Each session has a filled session template saved in docs/qa/phase75a/
[ ] Every friction event has a severity (P0/P1/P2)
[ ] Aggregation table is filled with real observed data (not estimates)
[ ] Prediction accuracy table is filled (CONFIRMED/PARTIAL/REFUTED)
[ ] Regression checks confirmed across sessions
[ ] Ship readiness recommendation written (GO / HOLD / GO WITH KNOWN LIMITATIONS)
[ ] If any P0: owner and resolution timeline identified
```

**Phase 75-A output document:**

Write a single `PHASE_75A_SUMMARY.md` with:
1. Aggregate metrics table (from Section 6)
2. Prediction accuracy summary
3. Top 5 recurring friction events
4. Most painful creator moments (verbatim quotes preferred)
5. Surprises (anything the friction analysis did not predict)
6. Ship readiness estimate with threshold pass/fail
7. Recommended Phase 76 scope (P1/P2 items to address)

The summary document is the handoff artifact. It drives Phase 76 planning.

---

*Kit prepared: 2026-05-19 | Source: PHASE_75_REAL_CREATOR_QA_PLAN.md + PHASE_75_EXPECTED_FRICTION_ANALYSIS.md*  
*No synthetic data. No simulated sessions. Human execution required.*
