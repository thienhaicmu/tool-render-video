# PHASE UX-1D — Minimal Video Editor Feasibility Audit

**Type:** Feasibility audit — NOT implementation, NOT redesign, NOT feature development
**Date:** 2026-05-20
**Background context:** UX1A + UX1A-R2 + UX1B + UX1C (do not blindly follow previous conclusions)
**Directive:** Challenge the proposal honestly. If something is wrong, say so.

---

## 1. Executive Summary — Is This Direction Viable?

### 1.1 Direct Answer

The proposed Video/Text/AI model is the right conceptual direction. Tab names that describe WHAT (Video, Text, AI) rather than HOW (Edit, Export, Subtitles) are immediately clearer. Concentrating video render parameters (style, duration, count, format) into one tab removes artificial friction caused by the current Edit/Export split.

**But the proposal has four serious problems that must be addressed before this direction is viable:**

1. **"AI Intervention (Light / Medium / Strong)" does not exist as a product control.** There is no backend parameter for intervention level in the current system. This is a new feature proposal embedded in a simplification audit. It cannot be in scope here.

2. **"Video Style" and "AI Mode" will feel like the same decision asked twice.** "Viral" and "More Hook" both mean attention-grabbing. "Story" and "More Story" both mean narrative. Creator will stop and wonder: "didn't I already pick this?" The proposed model puts them in different tabs but does not resolve the conceptual overlap.

3. **"Video Style (Viral / Balanced / Story)" reduces 4 existing options to 3.** The current product has Quick Styles: Viral / Cinematic / Aggressive / Balanced. The proposal drops two and introduces "Story" (which may or may not map to "Cinematic"). Removing a style option is a product decision, not a UX simplification. This requires a separate product call.

4. **Platform target (YouTube / TikTok / Reels) disappears entirely.** The backend uses platform selection for encoding decisions beyond aspect ratio. Replacing it with only an Aspect Ratio selector loses platform encoding hints. This needs investigation — Aspect Ratio alone may not be sufficient.

**What becomes better if the direction is approved:** Tab naming is the most meaningful UX improvement of the entire audit series. "Video / Text / AI" is immediately intuitive. The consolidation of Style + Duration + Count + Format into a single Video tab removes the current Edit/Export split, which is the second largest friction source after Export tab overload. If the four problems above are resolved, this model is achievable and better.

**What becomes worse:** Preset system (Creator Presets, Quick Presets) loses its home. Subtitle Color and Font disappear from primary view unless explicitly added to the Text tab. Platform-specific encoding may silently downgrade.

### 1.2 Verdict by Section

| Proposed Section | Verdict | Reason |
|---|---|---|
| Video / Text / AI tab names | APPROVED | Best naming in the audit series |
| Style in Video tab | APPROVED with fix | 4 options, not 3 |
| Clip Duration in Video tab | APPROVED | Correctly elevated |
| Output Count in Video tab | APPROVED | Correct position and rename |
| Format / Aspect Ratio in Video tab | APPROVED | Correctly elevated |
| Smart Framing in Video tab | CONDITIONAL | Deserves visibility, but secondary |
| Subtitle ON/OFF in Text tab | APPROVED | Core |
| Subtitle Style in Text tab | APPROVED | Core |
| Text Size in Text tab | APPROVED | Core |
| Position (Bottom/Middle/Top) | APPROVED | Brilliant simplification — requires implementation |
| Text Layer ON/OFF | FLAGGED | Toggle assumes layers exist; first-time creators see empty state |
| AI Mode (More Hook / Balanced / More Story) | APPROVED with renaming | Needs distinct label from Video Style |
| AI Intervention (Light / Medium / Strong) | REJECTED | New feature, not in current product |
| No Export tab | APPROVED with caveats | Platform and Presets need explicit new homes |
| Missing: Subtitle Color | ADD | Core decision removed without replacement |
| Missing: Platform target | ADD to Video Advanced | Backend encoding risk if removed entirely |
| Missing: Creator Presets | ADD to footer | Power user efficiency tool needs a home |

---

## 2. Feature Necessity Audit

Every proposed visible control evaluated honestly.

---

```
FEATURE: Video Style (Viral / Balanced / Story) — proposed
DECISION: KEEP — but fix the option count

WHY: Style selection is the primary creative lever. Every creator makes this choice. Correctly placed in Video tab. The reduction from 4 to 3 options is a product decision, not a UX decision — cannot be made here.

The proposed third option "Story" either:
  (a) Maps to existing "Cinematic" (renamed — possible) with "Aggressive" dropped, or
  (b) Is a new style that doesn't exist in the current system (product change)

Without a product decision on which mapping applies, we cannot reduce to 3.
Recommendation: Keep all 4 current options (Viral / Cinematic / Aggressive / Balanced).
Renaming is in scope — removing is not.

RISK IF HIDDEN: Creator loses primary creative control. Unacceptable.
```

```
FEATURE: Clip Duration (min / max)
DECISION: KEEP — elevated to Video tab primary surface

WHY: The most impactful AI discovery parameter. If min duration is wrong for the source content, the AI produces no usable clips. Creator must be able to set this before render. (UX1A §3.5, §6.2)
Relabeled: Shortest clip [61] → Longest clip [180]

RISK IF HIDDEN: Creator gets wrong-length clips with no obvious fix path. This was the original problem. Do not hide this.
```

```
FEATURE: Output Count (number of clips)
DECISION: KEEP

WHY: Creator controls how many clips to produce. Primary output quantity decision. Correctly renamed from "Max clips" — "Output count" is clearer.

RISK IF HIDDEN: Creator gets unlimited clips or too few without understanding why.
```

```
FEATURE: Format / Aspect Ratio (9:16 / 1:1 / 16:9 / 3:4)
DECISION: KEEP — elevated to Video tab primary surface

WHY: Core output format. Platform pills currently auto-set this. The proposal presents it as the primary control, which is correct — creator picks format, not platform name.

IMPORTANT: Aspect ratio selection does NOT fully replace Platform selection. The backend may use platform encoding hints beyond ratio. See Section 7.

RISK IF HIDDEN: Creator renders wrong format for their platform. High-visibility mistake.
```

```
FEATURE: Smart Framing (Follow Face / Follow Person / Center / Auto)
DECISION: CONDITIONAL — visible but secondary

WHY: When a creator makes vertical content (9:16), Smart Framing directly affects whether subjects are properly framed. "Auto" works for 70-80% of use cases. For the remaining 20%, a bad crop (head cut off) is immediately obvious in the output.

The case for visibility: creator who renders vertical content and gets cropped-out subjects needs to know this control exists. It is more consequential than Render Settings (Device/FPS).
The case against primary visibility: "Auto" is almost always correct; this adds a decision for most creators who do not need to change it.

Recommendation: Visible in Video tab but placed after Style/Duration/Count/Format (lower priority). Default Auto. If creator picks 16:9 format (horizontal), this control can be hidden entirely (no reframing needed for horizontal output).

Maps to current "Reframe Mode" control (renamed to "Smart Crop" in UX1C). Same options.

RISK IF HIDDEN: Creators making vertical content with specific framing needs get wrong crops silently.
```

```
FEATURE: Subtitle ON/OFF toggle
DECISION: KEEP

WHY: Primary subtitle decision. Creator must know subtitles are on before render.
RISK IF HIDDEN: Creator renders without subtitles or with unintended subtitles.
```

```
FEATURE: Subtitle Style (Viral / Karaoke / Bold Cap / Boxed / Clean)
DECISION: KEEP

WHY: Visual output. The look of subtitles directly affects platform performance. Creator makes this choice once per project or once per platform.
RISK IF HIDDEN: Creator gets default style without conscious choice.
```

```
FEATURE: Text Size
DECISION: KEEP

WHY: Readability. Wrong size is immediately visible in output. Creator adjusts when clips look wrong.
RISK IF HIDDEN: Creator has no control over a prominently visible attribute.
```

```
FEATURE: Subtitle Color / Highlight
DECISION: ADD — missing from proposed Text tab

WHY: The proposed model does not include Color in the visible Text tab controls. Color is a core brand decision — creator's subtitle color defines their visual identity. Hiding Color in Advanced means creator who wants custom colors cannot find it on first look.
Current product: Color and Highlight pickers are always visible in Subtitles tab.
Recommendation: Color and Highlight should be visible in Text tab primary area.

RISK IF HIDDEN: Creator renders with wrong color, cannot find control to fix it.
```

```
FEATURE: Position (Bottom / Middle / Top)
DECISION: KEEP — and this is a genuine improvement over the current Y Pos slider

WHY: "Bottom / Middle / Top" is the right abstraction. 95% of creators want one of these three positions. The current Y Pos percentage slider (5–60%) requires the creator to think in coordinates.

Implementation note: This replaces the visible Y Pos slider with three buttons. Each button writes a specific value to evSubPos (the existing hidden input). The underlying evSubPos input remains in DOM. This requires CSS/JS work — it is not a pure HTML change. The percentage mappings must be defined (Bottom ≈ 15%, Middle ≈ 38%, Top ≈ 58% — based on current slider range).

The fine-position slider (exact percentage) belongs in Advanced collapse for creators who need precise control.
RISK IF CHANGED: Implementation must write correct percentage values to evSubPos. If mapping is wrong, subtitle position breaks.
RISK IF HIDDEN (current slider): Creator cannot intuitively place subtitles.
```

```
FEATURE: Text Layer ON/OFF toggle (proposed)
DECISION: FLAGGED — the toggle model assumes layers exist

WHY: First-time creators have zero text layers. A "Text Layer: ON/OFF" toggle with no layers present is confusing — ON does nothing. The current product manages text layers individually (add/remove specific layers).

A boolean toggle only makes sense if:
  (a) Creator has at least one text layer already configured, OR
  (b) "ON" creates a default text layer

Neither is currently how the product works. Implementing option (b) would be a new feature.

Recommendation: Show a collapsed "Text Layers" section with an add button (current behavior). Do not replace with ON/OFF toggle. Creators who use text layers will see the section and interact; creators who don't need it will ignore the collapsed section.

RISK IF IMPLEMENTED AS TOGGLE: First-time creator toggle-ON and sees nothing, or the toggle triggers unexpected layer creation.
```

```
FEATURE: AI Mode (More Hook / Balanced / More Story) — proposed Tab 3
DECISION: KEEP — but rename to avoid duplication with Video Style

WHY: This control (currently "Structure" in the QS Bar) determines which moments the AI selects — hook-heavy vs narrative arc. It is genuinely different from Video Style (which determines how clips are edited). But the current naming makes them feel identical:
  - Video Style: Viral / Balanced / Story
  - AI Mode:     More Hook / Balanced / More Story

Both have "Balanced." Both have something meaning "Story." Creator will stop at the AI tab and think: "I already picked Style — why is there another choice that sounds the same?"

Solution: Name them so their difference is obvious:
  Video tab  → "Edit Style" (Viral / Cinematic / Aggressive / Balanced) — HOW clips are cut
  AI tab     → "Clip Selection" (Hook-Heavy / Balanced / Story Arc) — WHICH moments AI picks

Renaming the AI tab control to "Clip Selection" with clearer option labels makes the distinction immediate.

RISK IF BOTH VISIBLE WITH CURRENT NAMES: Creator confusion, double-picking the same concept.
```

```
FEATURE: AI Intervention (Light / Medium / Strong) — proposed Tab 3
DECISION: REJECT — this is a new feature, not a simplification

WHY: No backend parameter for "AI Intervention Level" exists in the current product. There is no control that maps to Light/Medium/Strong in the existing UI or API. Creating this control requires:
  - Defining what L/M/S means in terms of AI parameters
  - Backend support for a new aggressiveness parameter
  - UI implementation of a new 3-option selector

This is not a simplification of an existing control. It is a new product feature. It cannot be in scope for a UX reduction audit.

IF the product wants to add this concept in a future phase: it would live in the AI tab and could merge with the Structure/Clip Selection control as a combined "AI Behavior" setting. That is a separate product decision.

RISK IF INCLUDED NOW: Requires backend work, new API parameters, new frontend control — none of which can be delivered in a UX-only phase.
```

---

## 3. Duplication Analysis

### 3.1 Video Style vs AI Mode — Most Critical Overlap

This is the central duplication problem in the proposed model.

**Current controls and what they do:**

| Control | Current Name | Tab | What it controls |
|---|---|---|---|
| Quick Styles | Viral / Cinematic / Aggressive / Balanced | Edit (Story) tab | HOW clips are edited — music energy, cut frequency, filter look, transition style |
| Structure | More Hook / Balanced / More Story | Export tab (QS Bar) | WHICH moments AI selects — clip ranking weights, hook vs narrative ratio |

**These are two different systems in the backend.** Quick Styles apply edit parameters (audio, visual, timing). Structure pills adjust AI clip selection ranking. One affects how the clips look; the other affects which clips get chosen.

**The naming problem:**
- "Viral" (style) and "More Hook" (structure) both mean: aggressive, attention-grabbing, TikTok-optimized
- "Balanced" appears in BOTH systems with the same word
- "Story" (proposed style rename) and "More Story" (structure) both mean: narrative, slower, longer

When a creator sees both controls — even in different tabs — they ask: "I just picked 'Viral' style. Now it's asking me 'More Hook or Balanced.' Isn't that the same thing?"

**The answer a creator would give:** "They seem like the same question. I'll pick the same thing both times." That is exactly what they will do. The duplication is not dangerous (picking "Viral" + "More Hook" is internally consistent), but it signals poor product design and erodes trust.

**Hard recommendation:**

Option A (rename only, no structural change):
```
Video tab: "Edit Style"    → Viral / Cinematic / Aggressive / Balanced
                              subtitle: "How each clip is cut and scored"

AI tab:    "Clip Selection" → Hook-Heavy / Balanced / Story Arc
                              subtitle: "Which moments the AI picks from your footage"
```
Clear separation. Two distinct questions. Creator understands they are different.

Option B (merge the concepts, requires backend change — out of scope):
One combined "Video Mode" control that simultaneously sets Edit Style AND Structure bias. A single choice like "Viral" applies both Viral quick style AND More Hook structure. This would require backend coordination. Not in scope for a UX phase.

**Conclusion:** Option A (rename + subtitle clarification) is the correct path. It resolves the confusion at the naming level without any functional change.

### 3.2 Subtitle Style (Text tab) vs Subtitle Pill (QS Bar)

In the current product, the Export tab QS Bar has a Subtitle pill (Off/Clean/Viral/Karaoke). The Subtitles tab has a full Style dropdown. These are the same control — linked via evSyncQsBar().

In the proposed model:
- Text tab has "Subtitle Style" (= the full style dropdown)
- No Export tab exists → QS Bar disappears → Subtitle pill disappears

**Result:** Only one subtitle style control exists. The duplication is resolved by removing Export tab. This is a genuine simplification — one fewer control for the same outcome.

**No action needed** — the proposed model accidentally fixes this duplication.

### 3.3 Format / Aspect Ratio vs Platform Encoding

The proposed model replaces Platform pills (YouTube/TikTok/Reels) with Format/Aspect Ratio (9:16/1:1/16:9/3:4).

**These are not fully equivalent.** Platform pills do two things:
1. Set evAspectRatio via evQsSet() → aspect ratio of the output
2. Set evTargetPlatform hidden input → used by backend for platform-specific encoding decisions

If Platform pills disappear and only Aspect Ratio is set, evTargetPlatform is never set. The backend behavior depends on what the pipeline does with a blank evTargetPlatform.

**Hard finding:** If evTargetPlatform defaults to YouTube when blank, vertical 9:16 renders will be encoded with YouTube vertical parameters instead of TikTok parameters. These may differ in bitrate targets, encoding profile, or metadata. Whether this matters for output quality requires backend code investigation — which is outside UX audit scope.

**Recommendation:** Keep platform selection, but make it a consequence of Format selection, not a separate choice:
- Creator picks 9:16 → UI automatically shows "Platform: TikTok / Reels" as a sub-choice (2 options)
- Creator picks 16:9 → evTargetPlatform = YouTube (automatic)
- Creator picks 1:1 or 3:4 → evTargetPlatform = Reels/Instagram (automatic)

This reduces Platform to a 2-option clarifier (TikTok vs Reels) that only appears when relevant — i.e., when creator picks 9:16. For 16:9 and 1:1, platform is inferred from format.

---

## 4. Missing Critical Controls

### 4.1 What Disappears and Whether Creators Will Miss It

```
MISSING: Subtitle Color / Highlight
SEVERITY: High
WHY MATTERS: Color defines visual identity. Creator who sees wrong subtitle color in output cannot find the fix without knowing to look in Advanced.
FIX: Add to Text tab primary visible area. Currently always-visible in Subtitles tab. Must remain always-visible.
```

```
MISSING: Platform Target (YouTube / TikTok / Reels)
SEVERITY: Medium
WHY MATTERS: Backend may use evTargetPlatform for encoding decisions beyond aspect ratio. Silently defaulting to YouTube for all renders could affect TikTok/Reels output quality.
FIX: See Section 3.3 — platform becomes a 2-option follow-up to 9:16 format selection (TikTok vs Reels). Does not require a separate control for other formats.
```

```
MISSING: Creator Presets (cpBar — save/load named configurations)
SEVERITY: Medium
WHY MATTERS: Returning creators who set up presets lose access to their saved configurations. This is an efficiency tool that reduces the number of decisions a experienced creator makes on every render.
FIX: Move cpBar to the editor footer, adjacent to the Start Render button. Tab-independent position. One line: [— No Preset — ▾] [Save]. Always visible regardless of which tab is open.
WHY THIS HOME: Presets are cross-tab (they save settings from all tabs). A footer placement signals "applies to entire session" rather than belonging to one tab.
```

```
MISSING: AI Fix Subs button
SEVERITY: Low-Medium
WHY MATTERS: Creators who use auto-subtitles frequently use AI Fix Subs when transcript quality is poor. Without it accessible, AI subtitle errors persist through the render.
FIX: Keep visible in Text tab. It is a one-button action, not a decision — zero cognitive cost.
```

```
MISSING: Quick Presets (starting-point cards)
SEVERITY: Low
WHY MATTERS: First-time creators benefit from configured starting points. Without Quick Presets, first-time creators make all decisions from scratch.
FIX: Move inside Video tab as a collapsed section "▸ Starting points (4 presets)". Behind one collapse — accessible but not demanding attention.
```

```
MISSING: Render quality / Output Profile
SEVERITY: Low
WHY MATTERS: Creator with a slow machine cannot select "Fast Draft" to get results faster. Creator targeting archival quality cannot select "Best."
FIX: Move to collapsed "Advanced" section in Video tab. Not visible by default — correct depth.
```

```
MISSING: BGM / Background Music
SEVERITY: Low
WHY MATTERS: Creators who use BGM (background music) need to set this before render.
FIX: Move to collapsed "Advanced" section in Video tab or as a dedicated collapsed section. Not primary visibility — BGM is off by default and rarely used.
```

```
MISSING: Trim controls
SEVERITY: HIGH — not in proposed model at all
WHY MATTERS: The proposed Video tab (Style, Duration, Count, Format, Smart Framing) does not include trim controls. Trim is the PRIMARY editorial action — the creator's ability to select the source clip range. This was in the "Story" / Edit tab in all previous models.
FIX: Trim must be in Video tab. It is the first action most creators take after opening the editor.
CRITICAL: This is the most significant omission in the proposed model.
```

---

## 5. Smart Framing Audit

### 5.1 Does It Deserve Front-Row Visibility?

**Proposed position:** Front-row in Video tab (equal weight to Style, Duration, Count, Format)

**Current position:** Inside Render Settings (collapsed Advanced area)

**What Smart Framing controls:** When the output format requires cropping (vertical 9:16 from horizontal source, or any aspect ratio change), Smart Framing determines HOW the crop follows the subject. Options: Follow Face / Follow Person / Center / Auto.

### 5.2 The Honest Assessment

**For vertical content creators (TikTok, Reels):** This matters significantly. A creator who selects 9:16 and gets a centered crop (when subjects are off-center) sees poor framing in every clip. Follow Face would have fixed it. This creator is confused and frustrated.

**For horizontal content creators (YouTube 16:9):** Completely irrelevant. There is no reframing for same-aspect-ratio output. The control has no effect.

**Current state:** Smart Framing is in Advanced/Render Settings — most creators never see it, even when it matters for their vertical content.

**The dilemma:** If it stays hidden, creators making vertical content get wrong framing. If it's shown front-row, it adds a decision that 16:9 creators never need.

### 5.3 Recommendation

**Smart Framing should be conditionally visible** based on format selection:

- Creator picks 9:16 → Smart Framing appears as a visible control in Video tab
- Creator picks 16:9 → Smart Framing is hidden (no reframing needed)
- Creator picks 1:1 or 3:4 → Smart Framing appears (cropping is occurring)

This is the right UX behavior: show the control when it's relevant, hide it when it isn't.

**Implementation approach:** Smart Framing visibility is toggled by the same JS that handles format/aspect ratio pill clicks. The `evQsSet()` function already fires on pill click — adding a show/hide of the Smart Framing control there is a low-risk addition.

**Verdict:** Smart Framing is NOT "advanced noise" — it is genuinely impactful for creators making vertical content. But it should not be front-row for horizontal creators. Conditional visibility based on format selection is the correct solution.

---

## 6. AI Tab Audit

### 6.1 Does AI Deserve Its Own Tab?

**Arguments for AI tab:**
- "AI" as a concept is a first-class creator choice. Separating "what AI does" from "what the video looks like" is conceptually clean.
- Creator intuitively understands: "I'm deciding how AI should behave here."
- The AI tab can expand over time (AI narration, AI Edit Actions) without polluting Video or Text tabs.

**Arguments against AI tab:**
- With only "Clip Selection" (3 options) as visible content and AI Intervention rejected (new feature), the AI tab has one visible control.
- A whole tab for one control feels sparse.
- Creator can't tell if they're done with AI configuration or if there's more.

### 6.2 What Should Be In The AI Tab

If AI tab exists, it needs enough content to justify a dedicated tab:

```
AI tab — visible:
  Clip Selection:  [Hook-Heavy]  [Balanced]  [Story Arc]
                   subtitle: "Which moments the AI picks from your footage"

  [▸ AI Options — collapsed]
    AI Edit Actions  (moved from Edit tab "More Options")
    AI Narration     (moved from Edit tab "More Options")
    AI Chat          (conversational panel)
```

With AI Edit Actions and AI Chat moved to the AI tab, the tab has a coherent purpose: "everything AI-related." Creator who wants to chat with the AI, run AI edit actions, or adjust AI clip selection — all in one place.

**This also cleans up the Video tab "More Options" collapse** — it no longer needs to hold AI-related items.

### 6.3 Are AI Mode and AI Intervention Actually Different?

**AI Mode (proposed):** Clip Selection bias — which moments get picked (hook vs story)
**AI Intervention (proposed):** How aggressively AI edits — light touch vs strong changes

These are genuinely different concepts. AI Mode = selection. AI Intervention = transformation. A creator can pick "Story Arc" selection + "Strong" intervention (AI picks narrative moments AND heavily edits them). Or "Hook-Heavy" + "Light" (AI picks hook moments AND minimally edits them).

However, as established in Section 2 — AI Intervention does not exist. The two concepts are different, but only one of them (AI Mode = Clip Selection) has a current implementation. The other is a new feature.

### 6.4 Verdict on AI Tab

**APPROVED with content expansion.** The AI tab earns its place if AI Edit Actions and AI Chat are also housed there. It becomes "all AI behavior" rather than "one lonely control." The Video tab's "More Options" collapse becomes smaller (no AI items in it).

---

## 7. Export Tab Removal Audit

### 7.1 Can Export Tab Disappear Safely?

**What Export tab currently holds and where each control goes:**

| Current Export Content | Proposed New Home | Safe? |
|---|---|---|
| Platform pills (YouTube/TikTok/Reels) | Video tab — conditional sub-choice after Format | MEDIUM risk — evTargetPlatform must still be set |
| Subtitle style pills (QS Bar) | Removed — Text tab Style dropdown covers this | SAFE — duplication resolved |
| Structure pills (More Hook/Balanced/More Story) | AI tab as "Clip Selection" | SAFE — same control, new home |
| Max clips | Video tab as "Output Count" | SAFE |
| Creator Presets bar | Footer (tab-independent) | SAFE |
| Quick Presets | Video tab, collapsed | SAFE |
| Advanced fold contents | Distributed to Video/AI tab Advanced sections | SAFE if IDs unchanged |
| Audio (BGM, volume) | Video tab, collapsed Advanced | SAFE (medium risk for EditorAudioRuntime trigger) |
| Render Settings | Video tab, collapsed Advanced | SAFE (medium risk for EditorPerformanceRuntime trigger) |
| Editor Performance | Video tab, collapsed Advanced | SAFE |
| Batch Queue | Video tab, collapsed Advanced | SAFE (ID-based) |

**Verdict:** Export tab can disappear safely IF and ONLY IF:
1. evTargetPlatform is still set (via Format → conditional platform sub-choice)
2. All IDs remain unchanged in their new tab homes
3. EditorAudioRuntime and EditorPerformanceRuntime triggers move correctly
4. Creator Presets bar gets a tab-independent home (footer)

### 7.2 Mental Model: What Breaks vs Gets Better

**What breaks mentally:**
- Creator who is used to "Export tab = where I set up the render" has no Export tab. They may feel uncertain about where to go before pressing render.
- In the first session with the new model, returning creators will feel disoriented.
- "Platform" as a concept disappears from the primary UI. Creator thinking "I'm making a TikTok video" no longer has a "TikTok" button to click — they pick 9:16 format instead. This is a subtle vocabulary change.

**What gets better mentally:**
- Creator never again has to wonder "is this an Edit setting or an Export setting?" The current Edit/Export split is artificial — all render decisions live in "Video" now.
- First-time creator sees Video tab and immediately understands it. No mystery about what "Export" means.
- The render button in the footer is always visible. Creator doesn't associate "render" with a specific tab.
- Structure pills (AI Clip Selection) and Platform (conditional on Format) are no longer co-located — the current Export tab mixes creative AI decisions with encoding settings, which is confusing.

**Overall:** The mental model improvement outweighs the disorientation cost. Export tab removal is correct.

---

## 8. Minimal Decision Count

### 8.1 Target Assessment

User target: under 10 visible decisions if realistic.

**Current model (6 tabs):** ~17 visible decisions (UX1A §7.1)
**UX1C model (3 tabs):** ~16 visible decisions
**Proposed UX1D model (3 tabs):** needs honest count

### 8.2 Decision Count in Corrected UX1D Model

After applying all Section 2 and Section 4 corrections:

```
VIDEO tab visible decisions:
  1. Trim controls                          (1 decision group)
  2. Edit Style (4 options)                 (1 decision group)
  3. Clip Duration: shortest + longest      (1 decision group — 2 fields)
  4. Output Count                           (1 decision)
  5. Format (9:16 / 1:1 / 16:9 / 3:4)     (1 decision group)
  6. Smart Framing — conditional on format  (1 decision — appears only for non-16:9)
  ────────────────────────────────────────
  Subtotal: 5 always-visible + 1 conditional = 5–6

TEXT tab visible decisions:
  7. Subtitle ON/OFF                        (1 toggle)
  8. Subtitle Style                         (1 decision — 5 options)
  9. Text Size                              (1 control)
  10. Color / Highlight                     (1 decision group — 2 pickers)
  11. Position (Bottom / Middle / Top)      (1 decision — 3 options)
  12. AI Fix Subs                           (1 action, not a decision)
  ────────────────────────────────────────
  Subtotal: 5 decisions + 1 action

AI tab visible decisions:
  13. Clip Selection (3 options)            (1 decision group)
  ────────────────────────────────────────
  Subtotal: 1 decision

TOTAL VISIBLE DECISIONS: 11–12
```

**11–12 visible decisions across 3 tabs.** This is achievable and significantly under the 15–20 target from UX1C. It's close to the "under 10 if realistic" target — the difference from 10 is:
- Subtitle Color/Highlight (added as a necessary correction)
- Trim controls (critical omission that must be added)

Without those two additions, it's 9–10. But omitting them would be a mistake — they are both genuinely core. **11–12 is the honest minimum without capability loss.**

### 8.3 Recommended Decision Count

**Target: 11–12 visible decisions.**

Under 10 is achievable only if Subtitle Color is moved to Advanced (risky for creator discoverability) or Trim controls are collapsed by default (unacceptable — trim is a primary action). Neither compromise is worth the simplification.

**11–12 is the right number.** Creator opens the editor, sees 11 decisions across 3 tabs — roughly 4 per tab. This is dramatically simpler than the current 17, achieves the "under 30 seconds to understand" goal, and retains all critical capabilities.

---

## 9. Final Recommended Structure

This is the BEST minimal editor — not the smallest.

```
┌────────────────────────────────────────────────────────────────────┐
│  CREATOR PRESETS:  [— No Preset — ▾]  [Save]   ← always visible   │
│  (footer-adjacent, tab-independent)                                 │
└────────────────────────────────────────────────────────────────────┘

TAB BAR:   [ Video ]  [ Text ]  [ AI ]

────────────────────────────────────────────────────────────
TAB 1 — Video
────────────────────────────────────────────────────────────
  Trim:
  [in point] ──────────●──────────── [out point]   ← always visible

  Edit Style:
  [Viral 🔥]  [Cinematic 🎬]  [Aggressive ⚡]  [Balanced ⚖️]

  Format:     [9:16 ↕]  [1:1 □]  [16:9 ↔]  [3:4 ▭]

  ↳ Smart Framing (appears ONLY when 9:16 or 1:1 or 3:4 selected):
    [Follow Face]  [Follow Person]  [Center]  [Auto]
    (hidden when 16:9 selected — no reframing needed)

  ↳ Platform (appears ONLY when 9:16 selected):
    [TikTok]  [Reels]
    (hidden for 1:1, 3:4, 16:9 — inferred from format)

  Duration:    Shortest [61] s  ——  Longest [180] s

  Output:      [6] clips

  [▸ Advanced]
    └─ Render quality: [Balanced ▾]
    └─ Multi-variant:  [ ]
    └─ CTA:            [ ]
    └─ Title Overlay:  [ ]
    └─ Creator Assets: [group]
    └─ Batch Mode:     [ ]
    └─ Market & Target: [group]
    └─ Quick Presets — starting points (4)
    ──────────────────────────────
    └─ Audio
         BGM [ ]  [file]  [volume]  [fade]
         Source volume [slider]
         Loudness normalization [ ]
    └─ Render Settings
         Device [Auto ▾]  FPS [Auto ▾]
    └─ Editor Performance
         [health banner + toggles]
    └─ Batch Queue
         [drag-drop zone]

────────────────────────────────────────────────────────────
TAB 2 — Text
────────────────────────────────────────────────────────────
  Subtitles:  [●────] ON

  Style:  [Viral — Fast TikTok/Reels captions ▾]

  Size:   [──────●──────]  72px

  Color [  ]   Highlight [  ]

  Position:  [Bottom]  [Middle]  [Top]

  [✦ Fix Subs]

  ↑ Live preview is in the video on the left.

  [▸ Advanced]
    └─ Font: [Bungee (Viral 🔥) ▾]
    └─ Horizontal position: [slider] 50%
    └─ Outline: [slider] 3px
    └─ Translate: [ ]  [language ▾]

────────────────────────────────────────────────────────────
TAB 3 — AI
────────────────────────────────────────────────────────────
  Clip Selection:
  [Hook-Heavy]  [Balanced]  [Story Arc]
  subtitle: "Which moments the AI picks"

  [▸ AI Options]
    └─ AI Edit Actions
    └─ AI Narration
    └─ AI Chat (conversational panel)

────────────────────────────────────────────────────────────
FOOTER (always visible):
  [● preparing...  /  ready]   [▶ Start Render]
────────────────────────────────────────────────────────────
```

### 9.1 Decision Count in Final Structure

| Tab | Visible decisions | What they are |
|---|---|---|
| Video | 5 always + 2 conditional | Trim, Edit Style, Format, Duration, Output + Smart Framing (when relevant), Platform (when 9:16) |
| Text | 5 + 1 action | ON/OFF, Style, Size, Color, Position + Fix Subs |
| AI | 1 | Clip Selection |
| **Total** | **11–12** | |

### 9.2 What Each Tab Answers in One Question

```
Video:  "How should my video look and how many clips should I get?"
Text:   "How should my subtitles look?"
AI:     "What should the AI prioritize?"
```

Creator can answer "which tab do I need?" in under 3 seconds. This passes the 30-second understanding test.

### 9.3 Comparison to Current State

| Metric | Current (6 tabs) | UX1B (4 tabs) | UX1C (3 tabs) | UX1D (3 tabs) |
|---|---|---|---|---|
| Tab count | 6 | 4 | 3 | 3 |
| Visible decisions | ~17 | ~17 | ~16 | 11–12 |
| Core controls above fold | 4 of 6 | 5 of 6 | 6 of 6 | 6 of 6 + Trim |
| Tab name clarity | Low (Story/Export) | Medium (Edit/Export) | Medium (Edit/Subtitles/Export) | High (Video/Text/AI) |

---

## 10. Risk Analysis

### 10.1 Quality Regressions

**Risk: Platform encoding downgrade**
If evTargetPlatform is never set (because Platform pills disappear), the backend may encode vertical content as generic or YouTube format. Mitigation: conditional TikTok/Reels sub-choice when creator picks 9:16. Must verify backend default for blank evTargetPlatform before shipping.

**Risk: Smart Framing defaults to Auto when Follow Face was needed**
Creator making vertical content doesn't see Smart Framing (if conditional visibility isn't implemented), gets center crop instead of face-follow. Mitigation: implement conditional Smart Framing visibility. This requires JS (not just HTML).

**Risk: Position Bottom/Middle/Top wrong percentage mapping**
If the three buttons write wrong percentage values to evSubPos, subtitle position breaks. Mitigation: verify exact mappings against the 5–60% range. Prototype the buttons against actual video output before shipping.

### 10.2 Creator Confusion

**Risk: Clip Selection vs Edit Style naming still confusing**
Even with new names (Edit Style / Clip Selection), some creators may not understand the distinction. Mitigation: subtitle text under each control explaining what it does ("how clips are cut" vs "which moments are picked"). One sentence each.

**Risk: Returning creators can't find their settings**
Creator who knows where everything is in the current editor (6 tabs) will be disoriented after the tab restructure. This is unavoidable when making structural changes. Mitigation: a one-time "What's New" notice in the editor pointing to the new tab locations.

**Risk: No Export tab → creator doesn't know they're ready to render**
Creator who associates "go to Export to set things up, then click Start" loses that mental checkpoint. The render button is always in the footer, but creator may feel like they're missing a step. Mitigation: the render button with clear status ("Ready to render" / "Preparing...") provides the same confidence. The footer placement is always visible.

**Risk: AI Intervention absence**
Creators who want fine-grained control over how aggressive the AI is have no control for this. They can approximate it via Edit Style (Aggressive = more changes) but it's not the same. This is a genuine capability gap if creator expectations are set. Mitigation: do not promise AI Intervention in marketing until the backend feature is built.

### 10.3 What Should Stay Hidden vs What Should Stay Accessible

| Control | Should be | Why |
|---|---|---|
| Font | Advanced (Text tab) | Style dropdown covers this for most creators; font is a fine-tuning decision |
| Outline | Advanced (Text tab) | Default 3px works; this is a typography fine-tuning |
| X Position | Advanced (Text tab) | 95% center; same as UX1C finding |
| Translate | Advanced (Text tab) | Special use case |
| Render quality | Advanced (Video tab) | Defaults work; power user feature |
| BGM | Advanced (Video tab) | Off by default; discoverable in Advanced |
| Source volume | Advanced (Video tab) | Default works; rarely touched |
| Loudness normalization | Advanced (Video tab) | Always-on behavior; toggle should be accessible but not primary |
| Multi-variant / CTA / Title Overlay | Advanced (Video tab) | Specialized features; correct depth |
| Creator Assets | Advanced (Video tab) | Power feature; correct depth |
| Batch Mode URLs | Advanced (Video tab) | Power feature; correct depth |
| Market & Target | Advanced (Video tab) | Professional/regional; correct depth |
| Editor Performance | Advanced (Video tab) | Support tool; never a render decision |
| Batch Queue | Advanced (Video tab) | Power feature; discoverable |
| AI Edit Actions | AI tab, collapsed | Used for corrections, not primary flow |
| AI Narration | AI tab, collapsed | Off by default, rare |
| AI Chat | AI tab, collapsed | Power users; most creators don't know it exists |
| Expert Preset | Removed from primary view | Redundant with Creator Presets for most users; if kept, inside Advanced |
| Quick Presets | Video tab Advanced | Starting points for first-time creators; power users use Creator Presets |

### 10.4 Required Verifications Before Implementation

Before building:
- [ ] What does the backend do with blank evTargetPlatform? What encoding does it default to?
- [ ] What percentage values map to "Bottom / Middle / Top" for evSubPos in a way that looks correct across 9:16 and 16:9 outputs?
- [ ] Does Smart Framing (Reframe Mode / Smart Crop) have any effect when output format matches source format? (If not, hiding it for 16:9 is confirmed safe)
- [ ] What does EditorAudioRuntime.onTabActivate() initialize? Can it fire on Video tab entry rather than waiting for the Audio section to be opened?
- [ ] Does the current Quick Styles system have exactly 4 options (Viral/Cinematic/Aggressive/Balanced) and is "Story" a valid new option or must it map to an existing one?

### 10.5 Implementation Order (Minimum Risk Path)

**Phase A — naming and labeling only (zero functional risk):**
- Tab button renames: Story→Video (internal 'mode'), Subtitles→Text (internal 'subtitle'), Export→AI (or new internal 'ai') — wait, this requires significant JS restructuring. Actually: existing tab IDs need careful mapping to new names.
- Field label changes: Edit Style, Clip Selection, Shortest/Longest, Output Count, Format, Smart Framing
- Clip Selection tooltip text additions (subtitle text under each pill)
- AI Fix Subs remains visible

**Phase B — content merges, low risk:**
- AI tab content → merged into new AI tab structure with Clip Selection visible
- Words tab content → Video tab collapsed (AI Narration, Text Layers)
- AI Chat → AI tab collapsed section

**Phase C — structural moves, medium risk:**
- Trim controls placement in Video tab (confirm no regression)
- Smart Framing conditional visibility (JS: show/hide based on format pill click)
- Platform conditional sub-choice (JS: show TikTok/Reels when 9:16 selected)
- Position Bottom/Middle/Top buttons (JS: write percentage values to evSubPos)
- Creator Presets bar move to footer
- Audio / Render Settings / Editor Performance / Batch Queue → Video tab Advanced section

**Phase D — verification and edge cases:**
- evTargetPlatform behavior with conditional platform
- Smart Framing display/hide logic for all 4 format options
- Position button percentage values validated against actual output
- EditorAudioRuntime trigger placement confirmed

---

## 11. What the Proposal Gets Right (That Should Not Change)

These are the strongest ideas in the proposed model. Do not lose them in implementation debates.

1. **Video / Text / AI tab naming.** The best tab naming in the entire audit series. Intuitive, distinct, task-oriented. Keep these names.

2. **Style + Duration + Count + Format in the same tab.** The current Edit/Export split is the product's biggest structural mistake. One tab for "how my video is configured" is correct.

3. **Position as Bottom / Middle / Top instead of a percentage slider.** This is a genuinely better UX for this control. Creator language, not technical language. Implement it.

4. **AI as a first-class tab.** Treating AI behavior as something a creator consciously chooses (not something that happens invisibly) is the right product philosophy for a tool that is fundamentally AI-powered.

5. **No Export tab.** Removing the word "Export" from a tab that contains creative decisions (AI direction, subtitle style, structure) was always wrong. The render button in the footer is the only "export" action that belongs in an export flow.

---

*End of Audit — PHASE UX-1D*
*Next step if direction approved: Phase A implementation (naming and label changes — zero functional risk).*
*Critical pre-implementation checks: evTargetPlatform backend behavior, Position Bottom/Middle/Top percentage values, Smart Framing conditional logic.*
