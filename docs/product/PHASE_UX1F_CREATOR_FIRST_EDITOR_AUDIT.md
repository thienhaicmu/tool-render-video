# PHASE UX-1F — Creator-First Minimal Editor Audit

**Type:** Visibility audit — NOT implementation, NOT redesign
**Date:** 2026-05-20
**Rule:** If AI can safely decide → HIDE IT. If creator must confirm intent → SHOW IT.
**Tabs:** Edit / Captions / Export (locked — no tab redesign)
**Source:** UX1A through UX1E audit series + full code trace

---

## 1. Executive Summary

### 1.1 Does This Editor Match Creator-First?

The UX1E model (Edit/Captions/Export) is already significantly better than the original 6-tab editor. It brought Duration and Format into primary view, hid most technical controls, and established a clean 3-tab structure. But applying the new rule — "If AI can safely decide it, hide it" — reveals two controls that don't survive:

**AI Picks** — the creator does not need to decide this. Platform selection already implies the correct clip selection bias. TikTok → hook-heavy. YouTube → balanced. Reels → story arc. The connection is logical and automatic. A control that asks the creator to explicitly state what the platform choice already implies is redundant.

**Quality (render profile)** — the creator does not need to decide this. "Balanced" quality works correctly for all major platforms. Creator who needs "Fast Draft" for a test render is a power user case. The render quality decision is one AI can make correctly with a static default. It does not need primary UI real estate.

Removing these two from the primary flow reduces the visible Export tab to: **Platform + Render button**. This is the correct end state for Export.

### 1.2 What Still Feels Heavy

One remaining heaviness: the EDIT tab has two controls that feel related — **Style** and **Duration** — but they don't connect visually. A creator picking "Viral" style doesn't see any suggestion about appropriate clip duration. The controls are correct but feel like an unrelated list rather than a coherent setup flow.

This is a **label and ordering problem**, not a controls problem. Fixing it is Phase A work (label changes, visual grouping), not a control removal.

### 1.3 Final State Summary

After applying the new rule:

| Tab | Visible decisions | Controls |
|---|---|---|
| EDIT | 5 (+ 1 conditional) | Trim, Style, Format, Duration, Clips [+ Smart Framing when conversion] |
| CAPTIONS | 5 + 1 action | Subtitle ON/OFF, Style, Size, Color, Position + Fix Subs |
| EXPORT | 1 + render action | Platform + ▶ Start Render |
| **Total** | **~10–11** | |

**10–11 visible decisions.** Under the 10–12 target from UX1E. Within reach of "under 10 for 16:9 YouTube creators" when Smart Framing is hidden (no conversion needed).

Creator opens editor. Sees Trim and Style immediately. Picks Format. Sets Duration. Sets Clips. Goes to Captions. Sets Subtitle look. Goes to Export. Picks Platform. Clicks Render.

That is the entire flow. Under 60 seconds for an experienced creator. Under 2 minutes for a first-time creator.

---

## 2. Show vs Hide Audit

Rule applied to every current and proposed visible control.

---

```
CONTROL: Trim (in/out points)
AI CAN HANDLE? NO
WHY: Trim defines which portion of source footage to process. 
  AI has no way to know which part of a 40-minute lecture the creator wants to clip from.
  This is pure creator intent — "I want clips from minute 5 to minute 25."
DECISION: SHOW
DEFAULT BEHAVIOR: Full source duration (no trim applied)
QUALITY RISK IF HIDDEN: HIGH — AI processes all footage when creator only wanted a segment.
  Creator gets clips from parts of the video they didn't intend.
```

---

```
CONTROL: Video Style (Viral / Cinematic / Aggressive / Balanced)
AI CAN HANDLE? NO — this is brand identity
WHY: Style defines the visual energy and color treatment of every clip.
  AI cannot know if a creator's brand is high-energy TikTok viral or cinematic storytelling.
  This is a creative decision that only the creator can express.
  Style also sets evEffectPreset via evApplyPreset() — changing this changes the visual
  look of every exported clip.
DECISION: SHOW
DEFAULT BEHAVIOR: If no style selected → 'story_clean_01' effect (clean, minimal look)
QUALITY RISK IF HIDDEN: MEDIUM — default 'story_clean_01' is not wrong, but it applies
  a clean visual treatment to content the creator may have wanted to look Viral or Cinematic.
  Creator brand identity is lost.
```

---

```
CONTROL: AI Picks (Hook-Heavy / Balanced / Story Arc) — qsStructureBias
AI CAN HANDLE? YES — platform already implies the correct bias
WHY: The clip selection bias directly follows from the publishing platform:
  TikTok → hook-heavy content performs best → hook bias is correct
  YouTube Shorts → narrative/value content performs → balanced is correct
  Reels → story-focused content performs → story arc is correct

  Platform selection is already a creator decision (in EXPORT). The AI Picks control
  asks the creator to state what the platform choice already implies. This is a
  redundant decision.

  Implementation: When Platform pill is clicked → automatically write qsStructureBias:
    TikTok     → qsStructureBias = 'hook'
    YouTube    → qsStructureBias = 'balanced'
    Reels      → qsStructureBias = 'story'

  Creator who wants to override (e.g., story-arc clips on TikTok) uses EDIT Advanced.

DECISION: HIDE from primary view — auto-driven by Platform selection
DEFAULT BEHAVIOR:
  No platform set         → balanced (safe neutral)
  Platform = TikTok       → hook
  Platform = YouTube      → balanced
  Platform = Reels        → story
QUALITY RISK IF HIDDEN: Low. Platform-derived defaults are better than
  the current static 'balanced' default for all platforms.
  Removes one decision, improves default quality for TikTok creators.
WHEN SHOULD UI APPEAR: EDIT Advanced — "AI Clip Selection" for creators who
  want to override the platform-driven default.
```

---

```
CONTROL: Clip Duration (Shortest / Longest)
AI CAN HANDLE? NO
WHY: Duration range directly controls AI discovery. Too narrow = no clips found.
  The creator's content type determines the appropriate range:
  - Long-form lecture/podcast: clips of 60–180s
  - Highlight reel: clips of 15–45s
  - Interview cuts: clips of 30–90s
  AI has no way to know the creator's content type or their audience expectations.
  Wrong defaults here are the #1 cause of "no clips found" failures. (UX1A §3.5, §6.2)
DECISION: SHOW
DEFAULT BEHAVIOR: Shortest 61s, Longest 180s (current defaults from evMinPart/evMaxPart)
QUALITY RISK IF HIDDEN: HIGH — creators making highlight reels get no results at 61s minimum.
  Creator cannot diagnose the problem without knowing this control exists.
```

---

```
CONTROL: Output Count (max clips / max_export_parts)
AI CAN HANDLE? BORDERLINE
WHY: Creator often has a specific output need ("I need 5 clips for this week's content").
  Default of 6 (Phase 73) is reasonable, but creator who wants 1 test clip or 10 clips
  for a full series has different needs.
  Hiding at 6 default would be acceptable — creator gets up to 6 clips and deletes extras.
  But "how many clips do I want?" is a low-cognitive-cost decision the creator can answer
  in under 2 seconds. Worth keeping visible.
DECISION: SHOW — but LOW priority (below Duration in visual hierarchy)
DEFAULT BEHAVIOR: 6 clips (current Phase 73 default)
QUALITY RISK IF HIDDEN: Low. Creator may get more or fewer clips than intended,
  but can re-render. Not a silent quality regression.
ALTERNATIVE: Move to EXPORT tab (it's a render quantity decision, not an edit decision).
  Consider: EXPORT shows Platform + Clips + Render. EDIT becomes even cleaner.
```

---

```
CONTROL: Frame Ratio (9:16 / 1:1 / 16:9 / 3:4)
AI CAN HANDLE? NO — format is platform intent
WHY: Frame ratio determines the output format of every clip. This is the creator's
  fundamental publishing format choice. AI cannot know if creator is making TikTok
  content (9:16) or YouTube content (16:9) or Instagram square (1:1).
  Platform selection in EXPORT implies a format, but creator picks format explicitly.
DECISION: SHOW
DEFAULT BEHAVIOR: No safe universal default. Must show and require selection.
  (Or default 9:16 if TikTok is the most common platform for this creator — but
  that requires creator history, which is not in scope.)
QUALITY RISK IF HIDDEN: HIGH — wrong format = completely wrong output. Every clip
  is in the wrong aspect ratio. This is immediately visible.
NOTE: Frame Ratio and Platform are INDEPENDENT controls. Format = output shape.
  Platform = encoding bias + speed delta. A creator can pick 9:16 + YouTube Shorts
  (vertical YouTube content) or 9:16 + TikTok (same shape, different speed tuning).
```

---

```
CONTROL: Smart Framing (Auto / Follow Face / Follow Person / Center)
AI CAN HANDLE? YES — with default change
WHY: The current DEFAULT (fast_center → center crop) is the problem. Center crop
  fails for off-center subjects. If the default is changed to 'subject' tracking,
  the AI handles framing correctly in most cases without creator input.

  Current: evReframeStrategy default = 'fast_center' → reframe_mode = 'center'
  Proposed: when aspect ratio conversion occurs, auto-set evReframeStrategy = 'subject'

  With 'subject' as the default for conversion scenarios:
  - Talking head footage: AI tracks the face → correct framing
  - Multi-speaker: AI tracks nearest subject → acceptable
  - B-roll/landscape: subject tracking still works (falls back to center if no subject)
  - Only failure: creator wants center crop specifically (e.g., symmetrical compositions)
    → Creator finds Smart Framing in EDIT Advanced to override.

DECISION: HIDE from primary view — auto-set to 'subject' when conversion occurs
  Expose in EDIT Advanced for override (following UX1E conditional model).
DEFAULT BEHAVIOR:
  No aspect ratio conversion (16:9 → 16:9): reframe_mode = 'center', motion_aware_crop = false
  Aspect ratio conversion (any ratio change): reframe_mode = 'subject', motion_aware_crop = true
QUALITY RISK IF HIDDEN: LOW with the default change.
  'subject' is better than 'center' in most conversion scenarios.
  Risk: symmetrical compositions may look slightly off-center.
  Mitigation: Smart Framing override in EDIT Advanced.
WHEN SHOULD UI APPEAR: EDIT tab — "Framing" option in Advanced collapse.
  Creator who notices wrong framing in preview can find and override.
IMPLEMENTATION NOTE: Requires changing the default write for evReframeStrategy
  from 'fast_center' to 'subject' when format conversion is detected.
  Source format is available from session data (prepare-source returns it).
```

---

```
CONTROL: Subtitle ON/OFF (evAddSubtitle)
AI CAN HANDLE? NO — this is a creator/business decision
WHY: Whether subtitles appear is a platform and brand choice. Some creator categories
  explicitly do not use subtitles (certain music content, art videos). More importantly:
  if subtitles are ON by default and creator's audio is wrong, they get garbage subtitles
  on every clip. Creator needs to actively confirm "yes, add subtitles."
  Default: ON (checked in HTML). This is correct — most short-form content uses subtitles.
DECISION: SHOW — toggle is a single interaction, zero cognitive cost
DEFAULT BEHAVIOR: ON — subtitles added to all clips
QUALITY RISK IF HIDDEN: MEDIUM — creator who doesn't want subtitles gets them on every clip.
  The toggle is the safety confirmation.
NOTE: When toggle is OFF → hide all subtitle style controls (Size, Style, Color, Position).
  Conditional hiding when OFF reduces CAPTIONS tab to almost nothing for
  creators who don't use subtitles — clean experience.
```

---

```
CONTROL: Subtitle Style (Viral / Karaoke / Bold Cap / Boxed / Clean)
AI CAN HANDLE? PARTIALLY — platform could suggest a default
WHY: Style is a brand and platform visual choice. But:
  TikTok → Viral or Karaoke (word-highlight is platform-native)
  YouTube Shorts → Bold Cap or Clean
  Reels → Clean or Karaoke
  Platform could auto-set a good default style. BUT: subtitle style is strongly
  brand-identity for established creators. Many creators have a signature subtitle look.
  Auto-setting from platform risks overwriting creator's deliberate style choice.
DECISION: SHOW — creator must confirm style once per project/brand
DEFAULT BEHAVIOR: Karaoke (pro_karaoke) — current default, word-highlight is
  platform-appropriate for TikTok/Reels. Neutral enough for YouTube.
QUALITY RISK IF HIDDEN: LOW if default is Karaoke. But creator who wants Viral
  bounce or Clean subtitles loses their brand identity.
NOTE: Could auto-suggest from Platform (TikTok → Viral pill highlighted) without
  forcing it. That would be a UX enhancement, not a control change.
```

---

```
CONTROL: Subtitle Size (evSubSize)
AI CAN HANDLE? PARTIALLY — could auto-scale by platform and ratio
WHY: Size affects readability and visual impact. Default (46px) is calibrated.
  For 9:16 content, larger text performs better on mobile. For 16:9, medium text works.
  Creator adjusts when they see the subtitle preview looks too small or too large.
  Size is a visual decision the creator makes AFTER seeing the preview, not before.
DECISION: SHOW — creator adjusts based on preview feedback, not abstract setting
DEFAULT BEHAVIOR: 46px — correct for 9:16 content at evSubSize default
QUALITY RISK IF HIDDEN: LOW. Default 46px is appropriate for most use cases.
  Creator who wants large viral text or small clean text would miss this control.
NOTE: For future: AI could auto-scale size based on Format (9:16 → 60px, 16:9 → 40px).
  Not in scope for current simplification.
```

---

```
CONTROL: Subtitle Color / Highlight (evSubColor / evSubHighlight)
AI CAN HANDLE? NO — color is brand identity
WHY: Subtitle color is one of the most visible creator brand elements.
  White text on dark background is a standard, but many creators have signature
  color schemes (yellow text, colored highlights, brand-matching colors).
  AI cannot know the creator's brand palette.
DECISION: SHOW
DEFAULT BEHAVIOR: White (#FFFFFF) text, Yellow (#FFFF00) highlight — standard readable
QUALITY RISK IF HIDDEN: MEDIUM — creator brand identity not expressed.
  Creator who has a signature subtitle color cannot apply it.
```

---

```
CONTROL: Subtitle Position (Bottom / Middle / Top) — replacing Y Pos slider
AI CAN HANDLE? PARTIALLY — AI knows where faces are; could auto-position
WHY: For most content, Bottom is the correct position. It avoids overlapping the subject.
  The three-option control (Bottom/Middle/Top) is already a simplification from the
  percentage slider. Creator picks once per project/platform.
  Auto-position based on face detection would be ideal but requires real-time analysis
  per clip — not currently feasible without significant new development.
DECISION: SHOW — three buttons, near-zero cognitive cost, one-time setup per project
DEFAULT BEHAVIOR: Bottom (≈15% from bottom) — correct for 90%+ of content
QUALITY RISK IF HIDDEN: LOW. Default Bottom is correct. Hiding would prevent creator
  from adjusting when their content has text or graphics at the bottom of frame.
```

---

```
CONTROL: Text Layer section
AI CAN HANDLE? N/A — creator-generated content
WHY: Text layers contain creator-authored content (branding, overlays, custom text).
  AI cannot generate this content for the creator.
  BUT: showing a complex Text Layer UI to every creator whether they use it or not
  adds confusion for the majority who never use text layers.
DECISION: COLLAPSE to an "Add Text" entry in CAPTIONS Advanced
  First-time creators: CAPTIONS tab shows no Text Layer section
  Creators with layers: show layer count indicator (expandable)
  A simple "Add Text" link/button in CAPTIONS Advanced is sufficient discoverability
DEFAULT BEHAVIOR: No text layers
QUALITY RISK IF HIDDEN: NONE — off by default, no effect when empty
```

---

```
CONTROL: Fix Subs button (AI subtitle correction)
AI CAN HANDLE? YES — but creator review is appropriate before applying
WHY: AI CAN fix subtitle errors automatically. However:
  - Auto-fix modifies the transcript, which is creator-verified text
  - Creator may want to review what changed
  - Some "errors" are deliberate (brand terminology, proper nouns)
  The button is a one-tap action with no decision overhead. Creator taps it when
  they see subtitle quality is poor. It's not a configuration decision.
DECISION: SHOW — action button, not a decision. Zero cognitive cost.
DEFAULT BEHAVIOR: Subtitles are not auto-fixed. Creator triggers manually.
QUALITY RISK IF HIDDEN: LOW. Creator with bad auto-subtitles cannot fix them
  without knowing this exists. For creators who rely on auto-subtitles, this is
  a frequently-used action.
```

---

```
CONTROL: Platform (YouTube Shorts / TikTok / Reels) — in EXPORT tab
AI CAN HANDLE? NO — publishing platform is creator's business decision
WHY: Platform determines speed_delta (+8% for TikTok, -6% for Reels) and
  hook_sort_bonus (+6 for TikTok). These are real render differences.
  Platform also auto-sets AI Picks (structure_bias) in the proposed model.
  Creator must tell the system where they're publishing — AI cannot infer this.
DECISION: SHOW — primary control in EXPORT tab
DEFAULT BEHAVIOR: No safe universal default. Must show without preselection.
  (Or infer from Frame Ratio: 16:9 → pre-select YouTube, 9:16 → pre-select TikTok)
QUALITY RISK IF HIDDEN: MEDIUM-HIGH. TikTok creator who doesn't set platform
  gets YouTube Shorts bias: 8% slower speed, 0 hook bonus. Invisible regression.
NOTE: Platform and Frame Ratio are INDEPENDENT. Platform only sets:
  - target_platform (encoding bias)
  - qsStructureBias (AI Picks default — new behavior)
  Frame Ratio remains a separate creator decision in EDIT.
  No cross-tab auto-setting from Platform → Frame Ratio or vice versa.
```

---

```
CONTROL: Quality (render_profile — Fast / Balanced / Quality / Best)
AI CAN HANDLE? YES — "Balanced" is correct for all creators in all cases
WHY: Creator does not need to make a quality-vs-speed tradeoff in a typical render session.
  - "Balanced" produces good quality for all platforms
  - "Fast" is a power user optimization (quick test, slow machine)
  - "Best" is a power user preference (archival, commercial output)
  For 90%+ of creators: Balanced is always correct. The decision has no meaningful
  creative input — it's purely a machine resource tradeoff.
  AI (or the system) can make this decision: always Balanced. Creator who needs
  Fast or Best goes to EXPORT Advanced.
DECISION: HIDE — default Balanced always
DEFAULT BEHAVIOR: render_profile = 'balanced' — correct for all standard workflows
QUALITY RISK IF HIDDEN: NONE. Balanced produces quality output for all platforms.
  Power user who wants 'best' or 'fast' uses EXPORT Advanced.
IMPACT ON EXPORT TAB: With Quality hidden, EXPORT contains only:
  Platform + ▶ Start Render
  This is the correct end state for Export — "where are you publishing, then go."
WHEN SHOULD UI APPEAR: EXPORT Advanced section.
```

---

```
CONTROL: Playback Speed (evPlaybackSpeed = 1.07)
AI CAN HANDLE? YES — auto-calibrated per platform
WHY: 1.07x is the research-calibrated base speed. Platform speed_delta adjusts it
  further (TikTok +0.08, Reels -0.06). This is a pipeline parameter, not a creative
  decision. Creator who manually adjusts this risks producing content that feels
  unnatural on platform (too fast or too slow for the platform's native feel).
DECISION: HIDE permanently
DEFAULT BEHAVIOR: 1.07x base, auto-adjusted by platform delta
QUALITY RISK IF HIDDEN: None. The calibrated default is always better than manual.
```

---

```
CONTROL: Zoom / Frame Scale (evFrameScaleY = 106)
AI CAN HANDLE? YES — hardcoded correct value
WHY: 6% vertical zoom removes edge artifacts and adds visual energy. This value
  was calibrated for the render pipeline. Creator should never change it.
DECISION: HIDE permanently (hardcoded)
DEFAULT BEHAVIOR: 106% always
QUALITY RISK IF HIDDEN: None. 106% is always correct.
```

---

```
CONTROL: Loudness Normalization (evLoudnormEnabled = "1")
AI CAN HANDLE? YES — always on is always correct
WHY: Loudness normalization ensures clips meet platform audio standards.
  Always-on is always correct. Creator who disables this produces clips that
  may be rejected or muted by platform auto-normalization anyway.
  CONSTRAINT: Phase 64 — evLoudnormEnabled must remain outside any <details> element.
DECISION: HIDE — always on, never exposes in UI
DEFAULT BEHAVIOR: Loudness normalization always applied
QUALITY RISK IF HIDDEN: None. Default on is the only correct state.
```

---

```
CONTROL: BGM, Voice Narration, Subtitle Translation, CTA, Title Overlay, 
  Creator Assets, Market & Target, Multi-variant, Reup Mode, Batch
AI CAN HANDLE? All default off, all are opt-in workflows
WHY: All these controls default to off and have zero effect on a standard render.
  Creator who wants any of these finds them in EDIT Advanced.
DECISION: HIDE from primary flow — EDIT Advanced only
DEFAULT BEHAVIOR: All features disabled
QUALITY RISK IF HIDDEN: None — defaults are off, no change to standard render.
```

---

## 3. Duplication Audit

### 3.1 Video Style vs AI Picks — RESOLVED by new rule

**Before this audit:** Both visible as separate controls. Creator decides Style (how clips look) AND AI Picks (which clips are selected). Names overlapped — "Viral" (Style) vs "More Hook" (AI Picks), "Balanced" in both.

**After this audit:** AI Picks removed from primary view. Platform selection auto-sets qsStructureBias. Creator now decides ONE thing that implies the other:
- Creator picks TikTok (in EXPORT) → AI automatically uses hook-heavy clip selection
- Creator picks Style (in EDIT) → visual look only, no overlap with AI Picks

**Duplication: RESOLVED. No action needed beyond implementing Platform → qsStructureBias auto-write.**

### 3.2 Smart Framing vs "Advanced Crop" — NOT a duplication

Smart Framing IS the reframe control. There's no separate "Advanced Crop" control in the current product. The confusion came from naming — "Reframe Mode" in Render Settings and "Smart Framing" in proposed UI are the same underlying control. With Smart Framing hidden (default 'subject'), the question doesn't arise. **No action needed.**

### 3.3 Platform vs Frame Ratio — CONFIRMED INDEPENDENT

UX1E established and this audit confirms: Platform and Frame Ratio are independent controls. Platform = encoding bias + AI Picks. Frame Ratio = output format shape. Creator picks both explicitly. No auto-linking between them.

**Benefit of independence:** Creator making 9:16 vertical YouTube content picks 9:16 (EDIT) + YouTube Shorts (EXPORT). No confusion. No auto-override across tabs.

**Duplication: None. Both needed.**

### 3.4 Subtitle Style vs Color/Highlight — NOT a duplication

Subtitle Style is a preset (Viral = specific font + animation + default colors). Color/Highlight are per-creator overrides WITHIN the style. Creator picks Style first (broad look), then optionally adjusts Color (brand customization).

The interaction: picking "Viral" style sets default colors. Creator who then changes Color overrides the style's default. This is expected behavior. Clear enough in practice.

**Duplication: None. CAPTIONS shows both correctly.**

### 3.5 Output Count in EDIT vs Render in EXPORT — Potential Relocation

Output Count (max clips) is currently proposed in EDIT. But it's not an editing decision — "how many clips to produce" is a render output decision. It belongs more naturally in EXPORT alongside Platform.

**Recommendation:** Move Output Count to EXPORT tab.

New EXPORT visible:
```
Platform:  [YouTube ✓]  [TikTok]  [Reels]
Clips:     [6]
[▶ Start Render]
```

EDIT tab loses Output Count → becomes 4 always-visible controls (Trim, Style, Format, Duration).

EDIT tab now answers: "What do you want the clips to be like?"
EXPORT tab now answers: "Where are you publishing and how many clips?"

This is a cleaner conceptual split and reduces EDIT to its core editorial purpose.

---

## 4. What Should Be Removed From Creator Flow

### 4.1 Remove from Primary Flow (Into EDIT Advanced)

```
AI Picks (qsStructureBias)
→ HIDDEN — auto-driven by Platform. Override in EDIT Advanced.

Quality (render_profile)
→ HIDDEN — Balanced always. Override in EXPORT Advanced.

Smart Framing (reframe_mode)
→ HIDDEN — Auto/subject default. Override in EDIT Advanced.

Text Layer (primary UI)
→ COLLAPSED — CAPTIONS Advanced, "Add Text" entry only.

Audio Controls (BGM, Source Volume, Loudness)
→ EDIT Advanced

Voice Narration
→ EDIT Advanced (collapsed; conditional sub-controls)

Creator Assets (Logo/Intro/Outro)
→ EDIT Advanced

Market & Target
→ EDIT Advanced

Expert Preset
→ EDIT Advanced

Quick Presets (starting points)
→ EDIT Advanced (useful for first-time setup)

Batch Queue / Batch Mode
→ EDIT Advanced

Multi-variant, CTA, Title Overlay
→ EDIT Advanced

Reup Mode
→ EDIT Advanced (power user workflow)
```

### 4.2 Remove from Advanced Too (Never in UI)

```
Playback Speed (1.07) — hardcoded, no UI at any level
Zoom / Frame Scale Y (106) — hardcoded, no UI at any level
Loudness Normalization — always on, hidden input only (Phase 64 constraint)
Temp Cleanup — always on, no UI needed
Sub X Position (50) — hidden input, keeps DOM presence but slider in CAPTIONS Advanced
Subtitle Emphasis (balanced) — hidden input, no UI needed
Part Order (viral) — correct default, EDIT Advanced if creator needs timeline order
Source Quality Mode (standard_1080) — EDIT Advanced for YouTube quality
```

### 4.3 Audit History Controls

```
Edit History
→ FULLY REMOVE from primary flow and Advanced.
  Creator cannot act on history in a meaningful way during render setup.
  History is a "what happened" reference, not a "what to do" control.
  If needed, expose only after render completes in a post-render review flow.

Creator Memory panel
→ FULLY REMOVE from primary flow.
  Passive reference. Creator who wants to see their style preferences
  can find this in a dedicated Settings/Profile view, not in the render editor.
  No render decision depends on manually reading Creator Memory.

AI Chat (conversational panel)
→ COLLAPSE deeply in EDIT Advanced.
  Power feature. Creator who needs it knows to look.
  Most creators will never use it.
  NOT removed entirely — it's genuinely useful for power editing ("make intro stronger").
```

---

## 5. Conditional UI Audit

What should appear only when needed.

### 5.1 Format → Smart Framing (default invisible, best-effort auto)

```
Creator picks Format:
  16:9 → Smart Framing HIDDEN (no conversion, center = subject for horizontal)
  9:16 → Smart Framing HIDDEN (auto writes 'subject' to evReframeStrategy)
  1:1  → Smart Framing HIDDEN (auto writes 'subject')
  3:4  → Smart Framing HIDDEN (auto writes 'subject')

Default for all conversion cases: 'subject' tracking.
Override: EDIT Advanced → "Framing" section shows full option set.

WHY: Creator who gets bad framing notices in the preview. They go to EDIT Advanced.
  Most creators never need this — 'subject' handles their content correctly.
```

### 5.2 Platform → AI Picks (auto-write, not a conditional UI)

```
Creator picks Platform in EXPORT:
  YouTube Shorts → write qsStructureBias = 'balanced' (automatic, no UI)
  TikTok         → write qsStructureBias = 'hook'     (automatic, no UI)
  Reels          → write qsStructureBias = 'story'    (automatic, no UI)

No conditional UI. Just automatic behavior.
Override: EDIT Advanced → "AI Clip Selection" section.
```

### 5.3 Subtitle ON/OFF → All Subtitle Controls

```
Subtitle toggle OFF:
  → Style, Size, Color, Position, Fix Subs ALL hidden
  → CAPTIONS tab shows only: [OFF toggle] and live-preview callout (empty)

Subtitle toggle ON:
  → All subtitle controls appear
  → CAPTIONS tab fully populated

WHY: When subtitles are off, all subtitle controls are irrelevant.
  Hiding them when off keeps CAPTIONS clean for creators who don't use subtitles.
```

### 5.4 Feature Toggles → Sub-Controls (in Advanced)

```
BGM enabled    → BGM file picker, volume, fade appear
AI Narration   → source, language, gender, rate, text appear
CTA enabled    → CTA type selector appears
Translate      → target language selector appears
Title Overlay  → title text input appears
Reup Mode      → transform preset (light/strong) appears
```

### 5.5 Text Layers → Expand on Add

```
No text layers:
  CAPTIONS Advanced shows: [+ Add Text Layer]
  No layer controls visible

Layers exist:
  CAPTIONS Advanced shows: "2 text layers" (expandable)
  On expand: layer list with edit/remove options
```

---

## 6. True Minimal Safe Editor

After applying all findings from UX1F and the prior audit series.

### 6.1 Final Structure

```
┌──────────────────────────────────────────────────────────────────┐
│  [ Edit ]    [ Captions ]    [ Export ]                           │
│                                                                    │
│  FOOTER: [● status]  [Creator Presets: — ▾  Save]  [▶ Render]    │
└──────────────────────────────────────────────────────────────────┘


TAB 1 — Edit
────────────────────────────────────────────────────
  Trim:
  [in ────────────●────────────── out]

  Style:
  [Viral 🔥]  [Cinematic 🎬]  [Aggressive ⚡]  [Balanced ⚖️]

  Format:
  [9:16 ↕]  [1:1 □]  [16:9 ↔]  [3:4 ▭]

  Duration:
  Shortest [61] s  ——  Longest [180] s

  [▸ Advanced]
    └─ Framing (Smart Crop):   [Auto ✓]  [Follow Face]  [Follow Person]  [Center]
    └─ AI Clip Selection:      [Hook-Heavy]  [Balanced ✓]  [Story Arc]
    └─ FPS:                    [60 ▾]
    └─ Encoder:                [Auto ▾]
    └─ Part order:             [Viral ▾]
    ──────────────────────────
    └─ Multi-variant:          [ ]
    └─ CTA:                    [ ]  →  [type ▾]
    └─ Title Overlay:          [ ]  →  [text]
    └─ Creator Assets:         [Logo] [Intro] [Outro] [Music profile]
    └─ BGM:                    [ ]  →  [file] [volume] [fade]
    └─ Source volume:          [slider]
    └─ AI Narration:           [ ]  →  [source] [language] [gender] [text]
    └─ Batch Mode (URLs):      [ ]  →  [textarea]
    └─ Market & Target:        [group]
    └─ Expert Preset:          [— Manual — ▾]
    └─ Quick Presets:          [▸ Starting points (4)]
    ──────────────────────────
    └─ AI Edit Actions:        [grouped actions]
    └─ AI Chat:                [conversational panel]
    ──────────────────────────
    └─ Batch Queue:            [drag-drop zone]
    └─ Editor Performance:     [health + toggles]


TAB 2 — Captions
────────────────────────────────────────────────────
  Subtitles:  [ ON ●────── ]   ← toggle

  ↳ All controls below hidden when OFF

  Style:  [Viral — Fast TikTok/Reels captions ▾]

  Size:   [──────●────────]  72px

  Color [  ]   Highlight [  ]

  Position:  [Bottom ✓]  [Middle]  [Top]

  [✦ Fix Subs]

  ↑ Live preview is in the video on the left.

  [▸ Advanced]
    └─ Font:                  [Bungee (Viral 🔥) ▾]
    └─ Horizontal position:   [slider]  50%
    └─ Outline:               [slider]  3px
    └─ Translate:             [ ]  →  [language ▾]
    └─ Add Text Layer:        [+ Add Layer]
                              [layer list if layers exist]


TAB 3 — Export
────────────────────────────────────────────────────
  Platform:
  [YouTube Shorts]  [TikTok]  [Reels]
  "Sets speed and AI clip priority"

  Clips:  [6]

  [▶ Start Render]

  [▸ Advanced]
    └─ Quality:   [Fast]  [Balanced ✓]  [High Quality]  [Best]
    └─ Render Settings:  Device [Auto ▾]
    └─ Clip order:  [Best first ▾]


FOOTER (always visible):
  [● preparing... / ✓ ready]
  [— No Preset — ▾]  [Save]
  [▶ Start Render]
```

### 6.2 Decision Count

| Tab | Visible controls | Creator decisions |
|---|---|---|
| EDIT | Trim + Style + Format + Duration | 4 decisions |
| CAPTIONS (subtitles ON) | Subtitle ON/OFF, Style, Size, Color, Position | 5 decisions |
| EXPORT | Platform + Clips | 2 decisions |
| **Total** | | **~11 decisions** |

For **16:9 YouTube creators**: Smart Framing is hidden, Platform auto-implies AI Picks. **9 decisions** — under 10.

For **9:16 TikTok creators**: Same count — Smart Framing is hidden (auto 'subject'), AI Picks set by Platform. **11 decisions** including Format+Platform as 2 of those.

### 6.3 What Happens Without Creator Touching Anything

Creator opens editor, changes nothing, clicks render:
- Trim: full source duration processed
- Style: 'story_clean_01' visual treatment (neutral, clean look)
- Format: whatever is currently set (must be set before render)
- Duration: 61s–180s clips
- Output: 6 clips max
- Captions: ON, Karaoke style, 46px, white/yellow, Bottom position
- Platform: must be set (no universal safe default exists)
- Quality: Balanced
- AI Picks: whatever Platform implies (or 'balanced' if no platform set)
- Smart Framing: 'subject' if conversion needed, 'center' if not
- Speed: 1.07x + platform delta
- Zoom: 106%
- Loudness: always normalized

Creator who sets Style and Platform and Format gets a properly calibrated render. These are the minimum 3 decisions that define a meaningful render.

---

## 7. Extra Reduction Pass — Challenge Everything Visible

Applying maximum pressure to every control still visible. Honest assessment only.

### 7.1 Can Trim be hidden?

**NO.** Trim is editorial intent. The creator's choice of "which part of this 40-minute video to clip from" cannot be decided by AI. Full source processing when creator wanted only minutes 5–25 produces clips the creator cannot use. Trim must stay visible.

### 7.2 Can Style be hidden?

**NO.** Style is brand identity. The effect_preset that comes from Style selection is what makes a creator's content look consistent. Hiding it defaults to 'story_clean_01' — not wrong, but not the creator's voice. Style must stay visible.

**Can Style count reduce from 4 to 3?** This is a product decision (removing a style option), not UX scope. Do not change the option count. Rename only.

### 7.3 Can Duration be hidden?

**NO.** Duration is the single most impactful parameter for AI clip discovery. Wrong duration range = no clips found. This is the most consequential control in the editor. Must stay visible. (UX1A §3.5, §6.2)

**Can Duration get smarter defaults?** YES — but defaults don't solve the visibility problem. If defaults are wrong for a creator's content type, they need to find and fix the control. Visible is correct.

### 7.4 Can Fix Subs be hidden?

**YES — technically safe.** The button is an action, not a configuration. If hidden, creator who gets bad subtitles has no correction mechanism without going to Advanced. Given that auto-subtitles frequently have errors (especially for non-English audio), keeping Fix Subs visible is better practice.

**Verdict: Keep visible.** One button, zero decision overhead. High value for creators who need it.

### 7.5 Can AI Picks be hidden (already recommended)?

**YES — confirmed.** Platform-driven default is better than the current static 'balanced' for TikTok creators. Removing from primary view reduces visible decisions without quality regression.

### 7.6 Can Output Count (Clips) be simplified further?

**BORDERLINE.** Clips (default 6) is a quick number the creator understands: "how many clips do you want?" If hidden at 6, creator who needs 1 test clip or 12 for a full campaign cannot adjust. Moving to EXPORT alongside Platform is the right location. Keeping it visible is correct.

**Can the default change?** Yes — if Platform is TikTok and Duration is 30–60s, the AI could suggest "making 8–10 clips" vs "making 3–4 clips" for a YouTube creator. This is a future enhancement (platform-aware suggestions), not current scope.

### 7.7 Can Color/Highlight be simplified?

**BORDERLINE.** Color is brand identity — cannot hide. But:
- Could default to White/Yellow and let creator find color picker in CAPTIONS Advanced if they want to change
- Would reduce CAPTIONS to: Style, Size, Position, Fix Subs (4 visible + 1 action)
- Risk: creator who wants a custom brand color doesn't know where to look

**Verdict: Keep visible.** Color is a visual decision the creator makes once per brand setup. The picker is a small UI element (one click to open). Hiding it saves one control at the cost of discoverability for an important brand decision.

### 7.8 Can Quality (render_profile) be hidden (already recommended)?

**YES — confirmed.** Balanced is always correct. Power users access via EXPORT Advanced.

### 7.9 Can Subtitle Position (Bottom/Middle/Top) merge into Style?

**MAYBE in a future phase.** Style presets could include position as part of the preset definition. "Viral" style → Bottom. "Bold Cap" → Bottom. "Boxed" → Middle or Bottom by default. But this requires backend changes to how subtitle styles define their default position, which is outside current UX scope.

**Verdict: Keep as standalone 3-option control.** Very low cognitive cost.

---

## 8. Implementation Risk

### 8.1 New Behavior This Audit Introduces

**Platform → AI Picks auto-write (NEW)**
When creator clicks Platform pill in EXPORT → JS writes qsStructureBias:

```
Platform click handler → add:
  if (platform === 'tiktok')         qsStructureBias.value = 'hook';
  if (platform === 'youtube_shorts') qsStructureBias.value = 'balanced';
  if (platform === 'instagram_reels') qsStructureBias.value = 'story';
```

Risk: If creator manually sets AI Picks in EDIT Advanced and then clicks Platform, the manual setting gets overwritten. Mitigation: add a dirty flag for qsStructureBias — if creator manually changed AI Picks, Platform click does NOT overwrite it.

**Smart Framing default change (MEDIUM RISK)**
Change from `evReframeStrategy = 'fast_center'` to `'subject'` when aspect ratio conversion is detected.

When does conversion occur? When `output_aspect_ratio ≠ source_aspect_ratio`. Source aspect ratio is available from the session (prepare-source probes the source video dimensions). The JS needs to compare session source dimensions with evAspectRatio selection.

If source aspect ratio data is not available in `_ev`, this detection cannot happen client-side. Fallback: always use 'subject' as default (safer than 'center' in all conversion cases). Verify `_ev.duration` and session data contain source aspect ratio.

**Output Count moved to EXPORT tab**
HTML reorder only. evMaxExportParts input changes tabs. ID unchanged. Low risk.

### 8.2 What Must Be Tested

- [ ] Platform → qsStructureBias auto-write: verify correct values written for all three platforms
- [ ] AI Picks dirty flag: verify manual override survives Platform pill click
- [ ] Smart Framing default 'subject': verify reframe_mode='subject', motion_aware_crop=true are written correctly
- [ ] evEffectPreset chain: Quick Style click → evApplyPreset() → evEffectPreset.value updated → payload.effect_preset set correctly for all 4 styles
- [ ] evLoudnormEnabled DOM position: must be outside any `<details>` element after restructuring
- [ ] evSubPosX DOM presence: hidden input exists and reads 50 even when slider is in CAPTIONS Advanced
- [ ] qsStructureBias DOM presence: hidden input exists and Platform writes to it even when AI Picks is in EDIT Advanced
- [ ] Subtitle conditional hide: when toggle is OFF, all subtitle controls hide correctly AND sub_* payload fields still send defaults (not undefined)
- [ ] evTargetPlatform written correctly for all Platform selections (YouTube/TikTok/Reels)

### 8.3 Hidden Dependencies (Must Not Break)

| Hidden input | DOM requirement | Used by |
|---|---|---|
| evEffectPreset | Must be in DOM | startRenderFromEditor() line 2349 — reads value |
| evLoudnormEnabled | Must be outside `<details>` | evApplyPreset() reads unconditionally |
| evSubPosX | Must be in DOM at value 50 | startRenderFromEditor() line 2250 |
| qsStructureBias | Must be in DOM | startRenderFromEditor() line 2464 |
| evSubtitleEmphasis | Must be in DOM | startRenderFromEditor() line 2467 |
| evReframeStrategy | Must be in DOM | startRenderFromEditor() lines 2328-2330 |
| evTargetPlatform | Must be in DOM | startRenderFromEditor() line 2301 |
| evFrameScaleY | Must be in DOM at value 106 | startRenderFromEditor() line 2305 |
| evPlaybackSpeed | Must be in DOM at value 1.07 | startRenderFromEditor() line 2273 |
| evPartOrder | Must be in DOM | startRenderFromEditor() line 2304 |
| evCleanupTemp | Must be in DOM, checked | startRenderFromEditor() line 2331 |

### 8.4 Implementation Phase Sequence

**Phase A — Zero risk (labels and attributes only):**
Tab button text: "Edit" / "Captions" / "Export"
Field labels: "Shortest clip", "Longest clip", "Clips", Style labels
Subtitle live-preview callout in Captions tab
Position buttons (Bottom/Middle/Top) as display layer over existing evSubPos slider

**Phase B — Low risk (collapses and attribute moves):**
Edit History → remove from UI (keep no Advanced entry)
Creator Memory → remove from UI
AI Chat → EDIT Advanced (deep collapse)
Text Layers → CAPTIONS Advanced (Add Layer entry)
AI Narration → EDIT Advanced (conditional expand)
Market & Target → EDIT Advanced
Quick Presets → EDIT Advanced
Batch Queue → EDIT Advanced
Editor Performance → EDIT Advanced
Merge AI/Words tab content to EDIT (data-insp-panel changes)
Output Count → move to EXPORT tab (HTML reorder)
Creator Presets bar → footer position

**Phase C — Medium risk (new behavior + structural):**
Platform → qsStructureBias auto-write (new JS)
Smart Framing default change to 'subject' for conversion cases (new JS)
Subtitle ON/OFF conditional hide of all subtitle controls (new JS show/hide)
Quality hidden from primary EXPORT (moved to EXPORT Advanced)
Audio controls → EDIT Advanced (EditorAudioRuntime trigger update)
Render Settings → EDIT Advanced (EditorPerformanceRuntime trigger update)

---

*End of Audit — PHASE UX-1F*
*Final finding: 10–11 visible decisions achievable. AI safely handles Smart Framing, AI Picks, Quality, Speed, Zoom, Loudness — creator only decides what only the creator can know: what their content is, where it's being published, and how they want it to look.*
*Next step: Phase A implementation (tab renames + label changes — zero functional risk).*
