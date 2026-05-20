# PHASE UX-1C — Video Editor Simplification Re-Audit

**Type:** Re-audit with product goal reset. NOT implementation. NOT redesign.
**Date:** 2026-05-20
**Background context:** UX1A + UX1A-R2 + UX1B (do not blindly follow UX1B conclusions)
**Constraint:** No new features. No backend changes. No VideoLocal flow changes. Editor UX only.

---

## 1. Executive Summary — Why UX1B Still Felt Heavy

### 1.1 The Core Failure of UX1B

UX1B reorganized complexity. It did not reduce it.

Every control that existed in the 6-tab editor still exists in the 4-tab editor. The export tab's internal decision count was unchanged. The "More" tab held all the controls that were previously hiding in Audio, Render Settings, and Editor Performance — still reachable in one click from the tab bar.

The number of tabs dropped. The number of decisions did not.

**A tab in the tab bar is a visible reminder that decisions exist there.** Four tabs = four areas of concern the creator must mentally account for. "More" is the most dangerous of these: it signals "there is more to configure" without telling the creator whether they should care. For creators who want fast renders, a "More" tab creates more anxiety than Audio and Render Settings hiding inside Export's collapsed sections — because a tab is always visible.

UX1B also kept the Export tab's Advanced fold intact with Min/Max duration and Aspect Ratio buried inside it. The plan added a read-only badge above fold showing the current values, but the actual controls remained hidden. This was a compromise — it acknowledged the problem without solving it.

**The dirty flag concern was used as a reason to not fix a core problem.** Min/Max duration is one of the most impactful creator decisions (UX1A §3.5, §6.2). Keeping it hidden because platform→duration auto-link infrastructure doesn't exist is backwards: the control should become visible first; auto-link (if ever built) is an enhancement, not a prerequisite.

### 1.2 Principle Change

**Before (UX1B):** Every control stays. Organize controls so creators can find them.

**After (UX1C):** Every visible control must earn its place. Ask "does the creator actually need to see this for a typical render?" If no, it disappears from the primary surface.

**Before (UX1B):** Reduce tab count by creating a new "More" tab.

**After (UX1C):** Reduce tab count to 3 by eliminating "More" entirely. Rarely-used controls collapse into the bottom of Export, invisible until scrolled to.

**Before (UX1B):** Core controls (duration, aspect ratio) stay buried because surfacing them has implementation complications.

**After (UX1C):** Core controls surface to above fold. Implementation complexity is a problem for the implementation phase, not a reason to penalize the creator.

### 1.3 Target State

Creator opens the editor. They see **3 tabs**. The Edit tab shows trim and style. The Subtitles tab shows subtitle controls. The Export tab shows platform, AI direction, clip duration, aspect ratio, max clips, and a render button. That is the complete primary surface. If they need BGM, outlet routing, text layers, or AI narration — those exist but are not competing for attention on first look.

**Visible decision target: 15–20 total across all three tabs.**
**Comprehension target: Creator understands what to do within 30 seconds.**

---

## 2. True Core vs Optional — Full Classification

Every editor section classified against one test: does a creator who is doing a normal first or second render need to see this?

---

```
FEATURE: Trim controls
CATEGORY: Core
DECISION: Always visible in Edit tab
WHY: Every creator session involves at least reviewing the trim. It is the primary editorial action. (UX1A §6.1 "Core, high use, correct placement")
RISK: NONE
```

```
FEATURE: Quick Styles (Viral / Cinematic / Aggressive / Balanced)
CATEGORY: Core
DECISION: Always visible in Edit tab
WHY: Primary creative lever. Most creators pick a style on every render. (UX1A §6.1)
RISK: NONE
```

```
FEATURE: AI Edit Actions (collapsed group)
CATEGORY: Optional
DECISION: Collapsed inside Edit tab "More Options" section
WHY: Secondary creative tool. Used when something needs fixing, not on every render. Currently collapsed by default — keep collapsed. (UX1A §6.1)
RISK: LOW
```

```
FEATURE: Edit History
CATEGORY: Rare
DECISION: Collapsed inside Edit tab "More Options" section
WHY: Passive reference. Creator does not interact with this on most renders.
RISK: LOW
```

```
FEATURE: Creator Memory panel
CATEGORY: Rare
DECISION: Collapsed inside Edit tab "More Options" section
WHY: Passive reference. Creator reads it occasionally, never makes decisions from it on first render.
RISK: LOW
```

```
FEATURE: Text Layers / AI Narration (Words tab content)
CATEGORY: Rare
DECISION: Collapsed inside Edit tab "More Options" section
WHY: Off by default. Power user feature. No first-render creator needs to touch this. (UX1A-R2 §3.3)
RISK: LOW (EditorTextRuntime.onTabActivate() must move to 'mode' trigger)
```

```
FEATURE: Conversational AI (AI tab content)
CATEGORY: Rare
DECISION: Collapsed inside Edit tab "More Options" section
WHY: Most creators don't know it exists. Power users will find it. A collapsed label "AI Chat" is sufficient discoverability. (UX1A-R2 §3.6)
RISK: LOW (no runtime tab-switch side effects)
```

```
FEATURE: Subtitle On/Off toggle
CATEGORY: Core
DECISION: Always visible in Subtitles tab
WHY: Primary subtitle decision. Creator must know subtitles are on before render.
RISK: NONE
```

```
FEATURE: Subtitle Style (Viral / Karaoke / Bold Cap / Boxed / Clean)
CATEGORY: Core
DECISION: Always visible in Subtitles tab
WHY: Visual output. Creator must choose their subtitle look. Most creators visit this once per project. (UX1A §4, UX1A-R2 §3.2)
RISK: NONE
```

```
FEATURE: Subtitle Font
CATEGORY: Core
DECISION: Always visible in Subtitles tab
WHY: Font is the most visible subtitle attribute. Creator notices wrong font immediately.
RISK: NONE
```

```
FEATURE: Subtitle Size
CATEGORY: Core
DECISION: Always visible in Subtitles tab
WHY: Directly affects readability. Creator adjusts this when output looks wrong.
RISK: NONE
```

```
FEATURE: Subtitle Color / Highlight
CATEGORY: Core
DECISION: Always visible in Subtitles tab
WHY: Brand and platform look. Creator adjusts for each platform or content type.
RISK: NONE
```

```
FEATURE: Subtitle Y Position (position from bottom)
CATEGORY: Core
DECISION: Always visible in Subtitles tab, relabeled "Position from bottom"
WHY: Creator adjusts to avoid overlapping speaker face or lower-third graphics. (UX1A §4.3, §7.3)
RISK: LOW (label change only)
```

```
FEATURE: Subtitle X Position (horizontal center)
CATEGORY: Rare
DECISION: Collapsed inside "Advanced" section in Subtitles tab
WHY: 95% of creators always use center (default 50%). This control creates false impression that manual positioning is required. (UX1A §4.3)
RISK: LOW — evSubPosX must remain in DOM (payload reads it)
```

```
FEATURE: Subtitle Outline slider
CATEGORY: Optional
DECISION: Collapsed inside "Advanced" section in Subtitles tab
WHY: Default (3px) works for nearly all use cases. Fine-tuning outline is an edge-case concern. Hiding reduces slider count without losing capability.
RISK: LOW — evSubOutline must remain in DOM
```

```
FEATURE: AI Fix Subs button
CATEGORY: Optional
DECISION: Always visible in Subtitles tab
WHY: Creators who use auto-subtitles frequently use AI Fix Subs when transcript quality is poor. One button, no decision point, clearly labeled.
RISK: NONE
```

```
FEATURE: Translate subtitles
CATEGORY: Rare
DECISION: Collapsed inside "Advanced" section in Subtitles tab
WHY: Special-use case. Most creators rendering for their primary market don't need translation. (UX1A §4.1 — listed but not frequently used)
RISK: LOW — translate toggle and language select remain in DOM
```

```
FEATURE: Static subtitle preview block
CATEGORY: Remove from primary flow
DECISION: Remove — replace with live-preview callout text
WHY: The live overlay on the video frame (evSubOverlay) is a better preview in every dimension. The static inspector preview gives no position context and doesn't show animation. Creator is reading the wrong preview. (UX1A §4.2)
RISK: LOW — evSubOverlay JS unchanged; removing static preview block only
```

```
FEATURE: Platform pills (YouTube / TikTok / Reels) — QS Bar
CATEGORY: Core
DECISION: Always visible in Export tab
WHY: Platform is the primary render intent. Creator decides platform before anything else. (UX1A §6.1, §3.4)
RISK: NONE
```

```
FEATURE: Subtitle style pills (QS Bar shortcut) — Off / Clean / Viral / Karaoke
CATEGORY: Core
DECISION: Always visible in Export tab (QS Bar pill)
WHY: Quick subtitle mode selection without leaving Export tab. Bridges Subtitles tab to Export tab for the most common subtitle decisions. (UX1A §4.5)
RISK: NONE
```

```
FEATURE: AI Direction pills (More Hook / Balanced / More Story)
CATEGORY: Core
DECISION: Always visible in Export tab — with title= tooltips added
WHY: This is the primary AI behavior control. Creator influences what the AI prioritizes. Currently unlabeled vocabulary — adding tooltips fixes the problem without structural change. (UX1A §3.6, §6.1 "Secondary — above fold but needs explanation")
RISK: LOW (tooltip addition only)
```

```
FEATURE: Aspect Ratio — control (evAspectRatio)
CATEGORY: Core
DECISION: Elevated to always visible in Export tab above fold — removed from Advanced fold
WHY: Aspect ratio directly affects the output format. Currently auto-set by platform pills but buried in Advanced without visible confirmation. Creator picks TikTok and cannot verify ratio without opening Advanced. (UX1A §3.4, §6.2) The control must surface — platform pills already set it, but creator deserves to see and confirm the value in context.
RISK: MEDIUM — evAspectRatio input must remain same ID. Removing it from Advanced fold and placing above fold changes HTML structure of Advanced. Must verify evToggleAdvancedOutput() does not assume Aspect Ratio is inside the fold. evQsSet() already writes to this input; no change needed to set logic.
```

```
FEATURE: Min/Max clip duration (evMinPart, evMaxPart)
CATEGORY: Core
DECISION: Elevated to always visible in Export tab above fold — removed from Advanced fold
WHY: These are the primary AI discovery parameters. They determine what clips the AI can find. A creator whose content has natural breaks at 55s gets zero results at default min=61s without knowing why. Hiding this is the most consequential UX failure in the current editor. (UX1A §3.5, §6.2) The dirty flag concern (UX1B §4.2) is an implementation detail for future auto-link features — it is not a reason to keep a core control hidden.
RISK: MEDIUM — evMinPart and evMaxPart inputs move from Advanced fold to above fold. IDs unchanged. Payload reads by ID (editor-view.js:2274-2275) — safe. Must verify Advanced fold HTML doesn't assume these inputs are inside it (they are just inside a <div> today; moving the <div> is sufficient).
```

```
FEATURE: Max clips (max_export_parts)
CATEGORY: Core
DECISION: Always visible in Export tab
WHY: Creator sets how many clips to produce. Primary output quantity control. (UX1A §6.1)
RISK: NONE
```

```
FEATURE: Creator Presets bar (cpBar)
CATEGORY: Optional (but efficiency tool for returning creators)
DECISION: Always visible in Export tab — it reduces decisions for returning creators
WHY: A returning creator with a saved preset can apply one config and render. Hiding this would force power users to reconstruct settings each time. However, a first-time creator with no presets sees only a "— No Preset —" dropdown — low confusion cost.
RISK: LOW
```

```
FEATURE: Quick Presets (4 starting-point cards)
CATEGORY: Optional
DECISION: Keep as collapsed <details> in Export tab but move BELOW the primary visible controls
WHY: Useful for first-time creators who want a starting point. But showing them at the top of Export (current position) means they compete visually with the QS Bar. Moving below primary controls preserves discoverability without imposing on experienced creators. Relabeled: "Quick Presets — starting points" (UX1B §4.2)
RISK: LOW (HTML reorder + label change)
```

```
FEATURE: Expert Preset (named technical presets in Advanced fold)
CATEGORY: Rare
DECISION: Keep inside Advanced fold — no change from current position
WHY: Power-user feature. Regional targeting presets are not first-render concerns. Creator who needs "JP Storytelling" preset knows to find it in Advanced. (UX1A §6.1 — "Consider removing or deeper burial")
RISK: LOW
```

```
FEATURE: Market & Target (collapsed group at top of Export)
CATEGORY: Rare
DECISION: Move inside Advanced fold — below Expert Preset
WHY: Regional and professional targeting. Not a general creator concern. Currently collapsed but visible at top of Export, above cpBar — wrong priority. (UX1A §8.3, UX1B §3.3)
RISK: MEDIUM — mvMarket, mvAutoBestClips, mvKeywordHighlight, mvBestExportEnabled IDs must remain in DOM. mvHandleChange() is ID-based — safe to move.
```

```
FEATURE: Multi-variant render, CTA, Title Overlay, Creator Assets (inside Advanced fold)
CATEGORY: Rare
DECISION: Keep inside Advanced fold — no change
WHY: Specialized features. Correct depth. (UX1A §6.1)
RISK: NONE
```

```
FEATURE: Batch Mode (URLs, inside Advanced fold)
CATEGORY: Rare
DECISION: Keep inside Advanced fold — no change
WHY: Power user feature. Correct depth.
RISK: NONE
```

```
FEATURE: Audio controls (Source volume, BGM, Loudness) — currently standalone tab
CATEGORY: Rare
DECISION: Move to collapsed "Settings" section at bottom of Export tab
WHY: Most creators never touch audio. BGM off by default. Loudness normalization is always-on behavior, not a decision. A collapsed section at the bottom of Export is lower cognitive cost than a standalone tab — it does not appear in the tab bar. (UX1A §6.1 — "Rarely used"; UX1A-R2 §3.4)
RISK: MEDIUM — EditorAudioRuntime.onTabActivate() currently fires on 'audio' tab entry. After move, this must fire when creator opens the Settings section (or on Export tab entry, to be safe). BGM controls must still respond correctly. (UX1A-R2 §10 most-risk item)
```

```
FEATURE: Render Settings (Device, FPS, Reframe Mode) — currently in Export tab
CATEGORY: Rare
DECISION: Move to collapsed "Settings" section at bottom of Export tab
WHY: Advanced technical settings. Creator who renders on default settings (most creators) never touches this. (UX1A §6.1 — "Advanced, collapsed is fine"; UX1A-R2 §3.5)
RISK: MEDIUM — EditorPerformanceRuntime triggers must update. Auto-expand on Export tab entry must stop.
```

```
FEATURE: Editor Performance (health banner, hover previews, filmstrip, waveform toggles) — currently always visible in Export tab
CATEGORY: Remove from primary flow entirely
DECISION: Move to collapsed "Settings" section at bottom of Export tab
WHY: This is a support/debugging control. It has no place on the same surface as platform selection and clip duration. It does not affect render output. Showing it at primary level is an active mistake. (UX1A §6.1 — "Should be in settings, not Export"; §8.3 point 8)
RISK: MEDIUM — EditorPerformanceRuntime.onTabDeactivate() must fire correctly. IDs must remain in DOM.
```

```
FEATURE: Batch Queue (drag-drop file queue) — currently in Export tab
CATEGORY: Rare
DECISION: Move to collapsed "Settings" section at bottom of Export tab
WHY: Power feature for multi-file local renders. First-time creator does not need it. Drag-drop zone below Advanced fold and Render Settings is already poorly located. (UX1A §3.7; UX1A-R2 §4.4)
RISK: LOW — bqSection ID preserved; BatchQueue module is ID-based.
```

---

## 3. Aggressive Tab Reduction — True Minimum Model

### 3.1 The Case for 3 Tabs

UX1B proposed 4 tabs: Edit | Subtitles | Export | More.

The "More" tab is the correct idea with the wrong execution. The intent was good: separate rarely-used settings from primary controls. But a tab in the tab bar carries cognitive weight regardless of its contents. Every time a creator looks at the editor, they see "More" and must decide: "should I check what's in there?"

The solution is not a "More" tab. The solution is a "Settings" section collapsed at the very bottom of the Export tab. This is identical to the "More" tab in contents — but it disappears from the primary navigation surface. Creator who never needs audio or render settings never sees it. Creator who does need it scrolls to the bottom of Export and finds it.

**3 tabs is achievable. No controls are lost.**

### 3.2 Feasibility — Can Subtitles Merge?

The audits established (UX1A-R2 §3.2, §5.2):
- Subtitles cannot merge into Export — Export is overloaded and subtitle controls have a different mental model (styling an output vs configuring a render)
- Subtitles cannot merge into Edit — subtitle style is an output decision, not an editorial decision
- Subtitles has enough controls (9+) to justify a dedicated tab

**Verdict:** Subtitles stays as a standalone tab. It is the right structural decision and it serves the creator well.

### 3.3 The 3-Tab Model

```
Before:    Story | Subtitles | Words | Audio | Export | AI    (6 tabs)
UX1B:      Edit  | Subtitles | Export | More                  (4 tabs)
UX1C:      Edit  | Subtitles | Export                         (3 tabs)
```

**What changed between UX1B and UX1C:**
- "More" tab eliminated — its contents become a collapsed "Settings" section inside Export
- Export tab is now the only tab a creator needs for render configuration
- Audio tab is eliminated (content collapsed inside Export Settings)
- Tab bar is clean: 3 tabs, each with a clear, non-overlapping purpose

### 3.4 Tab Purpose Definitions (No Overlap)

```
Edit tab:     What to do with the footage (trim, style, AI edits)
Subtitles:    How subtitles look (style, font, size, color, position)
Export:       What to render and where (platform, duration, ratio, output)
```

Creator can answer "which tab do I need?" within 3 seconds of reading the tab names.

---

## 4. Visible vs Hidden Model — Every Section

The key question for each section: **VISIBLE / COLLAPSED / ADVANCED / REMOVED FROM PRIMARY FLOW**

### 4.1 Edit Tab

| Section | Status | Why | Discoverability Risk |
|---|---|---|---|
| Trim controls | VISIBLE | Core action every session | NONE |
| Quick Styles (4 cards) | VISIBLE | Primary creative lever | NONE |
| AI Edit Actions | COLLAPSED — "▼ More Options" | Secondary, not every-session | LOW — "More Options" label sufficient |
| Text Layers | COLLAPSED — "▼ More Options" | Power feature, off by default | LOW |
| AI Narration | COLLAPSED — "▼ More Options" | Rare, off by default | LOW |
| Edit History | COLLAPSED — "▼ More Options" | Passive reference | LOW |
| Creator Memory | COLLAPSED — "▼ More Options" | Passive reference | LOW |
| AI Chat (conversational) | COLLAPSED — "▼ More Options" | Power feature, most creators don't know it exists | LOW — same as current situation; collapse doesn't worsen discovery |

**Edit tab visible decision count: 2 (Trim + Style choice)**

One collapse handles all low-priority Edit content. Creator who needs Text Layers or AI Chat expands "More Options" once.

### 4.2 Subtitles Tab

| Section | Status | Why | Discoverability Risk |
|---|---|---|---|
| Auto subtitle On/Off | VISIBLE | Primary decision | NONE |
| Style dropdown | VISIBLE | Visual output — must pick | NONE |
| Font | VISIBLE | Most-visible attribute | NONE |
| Size | VISIBLE | Readability — creator adjusts | NONE |
| Color / Highlight | VISIBLE | Brand / platform look | NONE |
| Position from bottom (Y Pos, relabeled) | VISIBLE | Placement — creator adjusts | NONE |
| AI Fix Subs | VISIBLE | Frequent action after auto-transcription | NONE |
| Live-preview callout | VISIBLE | Directs creator to correct preview | NONE |
| X Position | COLLAPSED — "▼ Advanced" | 95% of creators never change center default | LOW |
| Outline | COLLAPSED — "▼ Advanced" | Default (3px) works for nearly all | LOW |
| Translate | COLLAPSED — "▼ Advanced" | Special-use case | LOW |
| Static preview block | REMOVED | Misleading; live overlay is the real preview | REPLACED by callout |

**Subtitles tab visible decision count: 7 (On/Off, Style, Font, Size, Color, Position, AI Fix)**

### 4.3 Export Tab

| Section | Status | Why | Discoverability Risk |
|---|---|---|---|
| Platform pills (YouTube/TikTok/Reels) | VISIBLE — primary | Core intent | NONE |
| Subtitle style pills (QS Bar) | VISIBLE — primary | Quick subtitle mode without leaving Export | NONE |
| AI Direction pills (More Hook/Balanced/More Story) + tooltips | VISIBLE — primary | Core AI behavior control | NONE (tooltips explain it) |
| Aspect Ratio (evAspectRatio) — actual control | VISIBLE — primary, elevated from Advanced | Core output parameter; platform pills auto-set it but creator can override | NONE (actually improves visibility vs current) |
| Clip duration: Shortest [61] — Longest [180] | VISIBLE — primary, elevated from Advanced | Most impactful AI discovery parameter | NONE (actually improves visibility) |
| Max clips | VISIBLE — primary | Output quantity control | NONE |
| Creator Presets bar (cpBar) | VISIBLE | Efficiency tool for returning creators | NONE |
| Quick Presets — starting points (4) | COLLAPSED — below primary controls | Starting points for first-time creators | LOW — collapsed label is sufficient |
| Advanced fold | COLLAPSED — below Quick Presets | Power controls | LOW — existing Advanced pattern |
| Expert Preset | ADVANCED fold | Power user, rarely-needed | LOW |
| Market & Target (moved in) | ADVANCED fold | Regional/professional only | LOW |
| Render quality (Output Profile) | ADVANCED fold | Technical, defaults work | LOW |
| Multi-variant / CTA / Title Overlay / Creator Assets / Batch Mode | ADVANCED fold | Specialized features | LOW |
| Settings section — collapsed at bottom | COLLAPSED — very bottom | Rarely-needed technical settings | LOW — scrolling past Advanced is intentional friction |
| Audio (Source vol, BGM, Loudness) | SETTINGS section | Rare, defaults work | LOW |
| Render Settings (Device, FPS, Smart Crop) | SETTINGS section | Advanced technical, rare | LOW |
| Editor Performance | SETTINGS section | Support/debug tool | LOW |
| Batch Queue | SETTINGS section | Power feature | LOW |

**Export tab visible decision count: ~7 groups (Platform, Subtitle pill, AI Direction, Aspect Ratio, Duration, Max clips, Creator Presets)**

**Total visible decisions across all 3 tabs: ~16**
This is within the 15–20 target.

---

## 5. Export Tab — Minimal Model

### 5.1 Above Fold (Creator's Primary Render Decisions)

Everything a creator needs to set for a typical render, in priority order:

```
┌─────────────────────────────────────────────────────┐
│  [— No Preset — ▾]  [Save]   ← Creator Presets bar  │
│                                                      │
│  Platform:    [YouTube] [TikTok] [Reels]             │
│  Subtitle:    [Off] [Clean] [Viral] [Karaoke]        │
│  Direction:   [More Hook] [Balanced] [More Story]    │
│                (tooltips on all three)               │
│                                                      │
│  Aspect Ratio:  [16:9 ▾]   (auto-set by Platform)   │
│                                                      │
│  Shortest clip:  [61]  Longest clip:  [180]          │
│  Max clips:  [6]                                     │
│                                                      │
└─────────────────────────────────────────────────────┘
```

Creator sees: platform, subtitle mode, AI direction, aspect ratio, clip duration range, output count. These are all render decisions with immediate understanding. Aspect ratio and duration are now actual editable fields, not read-only badges with hidden controls below.

### 5.2 Secondary (Collapsed, Accessible Without Scrolling)

```
┌─────────────────────────────────────────────────────┐
│  [▸ Quick Presets — starting points (4)]             │
└─────────────────────────────────────────────────────┘
```

Collapsed by default. First-time creators can expand for a configured starting point. Returning creators ignore it.

### 5.3 Advanced Fold (Power User Controls)

```
┌─────────────────────────────────────────────────────┐
│  [Advanced ▸]                                        │
│    Expert Preset:     [— Manual — ▾]                 │
│    Market & Target:   [group — moved in]             │
│    Render quality:    [Balanced ▾]                   │
│    Multi-variant render:  [ ]                        │
│    Add ending CTA:        [ ]                        │
│    Title Overlay:         [ ]                        │
│    Creator Assets:        [Logo / Intro / Outro /    │
│                            Music]                    │
│    Batch Mode (URLs):     [ ]  [textarea]            │
└─────────────────────────────────────────────────────┘
```

### 5.4 Settings Section (Collapsed, Bottom of Tab)

```
┌─────────────────────────────────────────────────────┐
│  [▸ Settings]                                        │
│    Audio                                             │
│      Source volume: [slider]                         │
│      BGM: [ ] [file] [volume] [fade]                 │
│      Loudness normalization: [ ]                     │
│    Render Settings                                   │
│      Device: [Auto ▾]                               │
│      FPS: [Auto ▾]                                   │
│      Smart Crop: [Auto ▾]                            │
│    Editor Performance                                │
│      [health banner] [toggle controls]               │
│    Batch Queue                                       │
│      [drag-drop zone] [file picker]                  │
└─────────────────────────────────────────────────────┘
```

### 5.5 What Disappears From First View in Export

| Removed from primary view | Was visible before | Why it's safe to hide |
|---|---|---|
| Market & Target | Collapsed at top of Export | Regional feature; wrong prominence position |
| Quick Presets | Collapsed at top of Export (above cpBar) | Still collapsed — just moved below primary controls |
| Aspect Ratio as Advanced-fold control | Inside Advanced | Elevated to above fold; Advanced entry now gone |
| Min/Max duration as Advanced-fold controls | Inside Advanced | Elevated to above fold; Advanced entry now gone |
| Audio | Standalone tab | Defaults work; behavior continues without creator touching it |
| Render Settings | Collapsed in Export | Technical, defaults work |
| Editor Performance | Always visible in Export | Support tool; behavior continues with defaults |
| Batch Queue | Visible in Export after Render Settings | Power feature; discoverable via Settings section |

---

## 6. Subtitle Tab — Simple Model

### 6.1 The Minimum Creator Truly Uses

From UX1A §4.1 and §4.3:

- **On/Off:** Yes — primary decision, must be visible
- **Style:** Yes — visual output, creator picks this every time
- **Font:** Yes — most visible attribute
- **Size:** Yes — readability
- **Color/Highlight:** Yes — brand and platform
- **Y Position (Position from bottom):** Yes — avoids covering faces; creator adjusts when something looks wrong
- **AI Fix Subs:** Yes — commonly used after auto-transcription
- **X Position:** NO — 95% of creators use center (50%); creates false complexity
- **Outline:** NO — default (3px) works; fine-tuning is an edge case
- **Translate:** NO — special use case
- **Static preview:** NO — the live video overlay is the real preview

### 6.2 Making Subtitle Obvious

The subtitle tab still uses a dropdown for Style selection. This is fine as long as the options are clearly labeled ("Viral — Fast TikTok/Reels captions"). The names work.

What makes Subtitle feel "technical" today is not the style dropdown — it's the proliferation of sliders (X, Y, Outline) and the misleading static preview that looks like a design tool. Removing X Pos and Outline from primary view, and replacing the static preview with a live-preview callout, transforms the tab from "configure a design system" to "pick how your text looks."

```
Subtitles tab — after simplification:

  Auto subtitles:  [ON] ← toggle

  Style:  [Viral — Fast TikTok/Reels captions ▾]

  Font:   [Bungee (Viral 🔥) ▾]

  Size:   [──────●────────]  72px

  Color [  ] / Highlight [  ]

  Position from bottom:  [──●──────────────]  15%

  [✦ Fix Subs]

  ↑ Live preview is in the video on the left — adjust controls above.

  [▸ Advanced]
    Horizontal position:  [slider]  50%
    Outline:              [slider]  3px
    Translate:            [ ] Target language [▾]
```

7 visible controls. The rest is behind one collapse. Creator who opens Subtitles tab immediately sees what they need.

---

## 7. Edit Tab — Simple Model

### 7.1 If Creator Only Touches 3 Things Before Render

Based on typical usage patterns and audit findings (UX1A §6.1, UX1A-R2 §3.1):

1. **Trim:** Set the clip window
2. **Quick Style:** Pick the edit energy (Viral / Cinematic / Aggressive / Balanced)
3. (Then they go to Export tab)

The Edit tab should make those two things immediately obvious. Everything else is secondary.

### 7.2 What Should Be Collapsed Forever

"Collapsed forever" means: collapsed by default, and most creators will never open it. These controls are not removed — they are simply not competing for attention.

| Section | Why Collapsed Forever |
|---|---|
| AI Edit Actions | Used when something specific needs fixing, not every session |
| Text Layers | Power feature — creator who uses it knows it's there |
| AI Narration | Off by default; requires voice profile setup; rare |
| Edit History | Passive reference; creator doesn't need it open |
| Creator Memory | Passive reference; low-interaction |
| AI Chat | Power feature; most creators don't know it exists (UX1A-R2 §3.6) |

### 7.3 Edit Tab Structure

```
Edit tab — after simplification:

  ┌──────────────────────────────────────────┐
  │  [Trim controls — in / out / duration]   │
  └──────────────────────────────────────────┘

  Style:
  [Viral 🔥]  [Cinematic 🎬]  [Aggressive ⚡]  [Balanced ⚖️]

  [▸ More Options]
    AI Edit Actions
    Text Layers
    AI Narration
    Edit History
    Creator Memory
    AI Chat
```

2 visible decision groups. One collapse for everything else. Creator who opens the Edit tab immediately knows what to do.

---

## 8. What Should Disappear — Explicit List

This section answers: what stops being visible at the primary level?

### 8.1 Full Disappearance List

**From Tab Bar:**
- Audio tab → disappears (content in Export Settings section)
- Words tab → disappears (content in Edit "More Options")
- AI tab → disappears (content in Edit "More Options")
- More tab (UX1B proposal) → never created; concept replaced by Export Settings section

**From Primary View in Edit Tab:**
- AI Edit Actions → "More Options" collapse
- Text Layers → "More Options" collapse
- AI Narration → "More Options" collapse
- Edit History → "More Options" collapse
- Creator Memory → "More Options" collapse
- AI Chat → "More Options" collapse

**From Primary View in Subtitles Tab:**
- X Position slider → "Advanced" collapse
- Outline slider → "Advanced" collapse
- Translate → "Advanced" collapse
- Static preview block → removed entirely (replaced by live-preview callout)

**From Primary View in Export Tab:**
- Market & Target → moved inside Advanced fold
- Quick Presets → moved below primary controls (was at top, now below)
- Audio controls → Settings section (collapsed at bottom)
- Render Settings → Settings section (collapsed at bottom)
- Editor Performance toggles → Settings section (collapsed at bottom)
- Batch Queue → Settings section (collapsed at bottom)

**From Advanced fold in Export:**
- Aspect Ratio control → elevated to above fold
- Min/Max clip duration controls → elevated to above fold

### 8.2 Why Hiding Is Safe for Each Category

**Audio controls:**
Source audio volume default works for nearly all renders. BGM is off by default — no creator is harmed by its absence from primary view. Loudness normalization is always-on; hiding the toggle doesn't change the behavior. Creator who wants BGM will find it in Settings. (UX1A §6.1)

**Render Settings:**
Device auto-detection works. FPS defaults are correct for platform. Smart Crop (Reframe Mode) auto mode is correct for most vertical content. Creator who has a specific device or FPS requirement knows to look in settings. (UX1A §6.1)

**Editor Performance:**
This control has zero effect on render output. It affects how the editor itself performs on the creator's machine. It belongs in settings, not on the primary render configuration surface. Hiding it from primary view removes zero render capability. (UX1A §8.3 point 8)

**Batch Queue:**
First-time creators don't need batch processing. Power users who batch local files know the feature exists. The Settings section label is sufficient discoverability. (UX1A §3.7)

**Expert Preset:**
Redundant for creators who use Creator Presets. Useful for regional/professional configs. Correct depth is Advanced fold — it was already there; keeping it there is a no-change. (UX1A §6.1)

**AI Chat (conversational):**
Most creators don't know this tab exists now (UX1A-R2 §3.6). Collapsing it into Edit "More Options" doesn't worsen discoverability — it gives it a clear labeled entry while not demanding attention.

**X Position slider:**
95% use case is center. Having both X and Y sliders creates the false impression that subtitle positioning requires manual coordination, like a design tool. Hiding X removes the false complexity while keeping Y (vertical position is the relevant decision for most creators). (UX1A §4.3)

**Outline slider:**
3px is the right default for nearly all content. Exposing this control at primary level makes the subtitle tab feel like an advanced typography tool when it should feel like a simple style picker. (UX1A §4.6)

---

## 9. Final Proposed Structure

Simple text layout of the complete editor after UX1C changes.

```
┌────────────────────────────────────────────────────────────────────┐
│ EDITOR                                                              │
│ ─────────────────────────────────────────────────────────────────  │
│ TAB BAR:   [ Edit ]   [ Subtitles ]   [ Export ]                   │
└────────────────────────────────────────────────────────────────────┘


TAB 1 — Edit
────────────
  Trim:   [in point]  ──────●──────  [out point]
          Duration display

  Style:
  [Viral 🔥]  [Cinematic 🎬]  [Aggressive ⚡]  [Balanced ⚖️]

  [▸ More Options]
    └─ AI Edit Actions
    └─ Text Layers
    └─ AI Narration
    └─ Edit History
    └─ Creator Memory
    └─ AI Chat


TAB 2 — Subtitles
──────────────────
  Auto subtitles:  [ ON ]

  Style:   [Viral — Fast TikTok/Reels captions ▾]

  Font:    [Bungee (Viral 🔥) ▾]

  Size:    [──────●────────]  72px

  Color [  ]   Highlight [  ]

  Position from bottom:  [──●──────────────]  15%

  [✦ Fix Subs]

  ↑ Live preview is in the video on the left.

  [▸ Advanced]
    └─ Horizontal position:  [slider]
    └─ Outline:              [slider]
    └─ Translate:            [ ]  [language ▾]


TAB 3 — Export
──────────────
  [— No Preset — ▾]  [Save]     ← Creator Presets bar

  Platform:   [YouTube]  [TikTok]  [Reels]
  Subtitle:   [Off]  [Clean]  [Viral]  [Karaoke]
  Direction:  [More Hook ⓘ]  [Balanced ⓘ]  [More Story ⓘ]

  Aspect Ratio:  [16:9 ▾]

  Shortest clip [61]  ——  Longest clip [180]

  Max clips:  [6]

  ────────────────────────────────────────
  [▸ Quick Presets — starting points]

  [▸ Advanced]
    └─ Expert Preset:     [— Manual — ▾]
    └─ Market & Target:   [group]
    └─ Render quality:    [Balanced ▾]
    └─ Multi-variant:     [ ]
    └─ Add ending CTA:    [ ]
    └─ Title Overlay:     [ ]
    └─ Creator Assets:    [group]
    └─ Batch Mode (URLs): [ ]

  [▸ Settings]
    └─ Audio
         Source volume  [slider]
         BGM  [ ]  [file]  [volume]  [fade]
         Loudness normalization  [ ]
    └─ Render Settings
         Device  [Auto ▾]
         FPS  [Auto ▾]
         Smart Crop  [Auto ▾]
    └─ Editor Performance
         [health banner + toggles]
    └─ Batch Queue
         [drag-drop zone]  [pick files]


FOOTER (always visible):
  [status line]  [▶ Start Render]
```

### 9.1 Visible Decision Count — Final Tally

| Tab | Visible decision groups | Count |
|---|---|---|
| Edit | Trim + Style selection | 2 |
| Subtitles | On/Off, Style, Font, Size, Color, Y Position, AI Fix | 7 |
| Export | Creator Presets, Platform, Subtitle mode, AI Direction, Aspect Ratio, Duration range, Max clips | 7 |
| **Total** | | **16** |

16 visible decisions across 3 tabs. Within the 15–20 target.

Non-negotiable controls confirmed accessible:
- Clip duration (min/max): **visible above fold in Export** ✓
- Video style: **visible in Edit tab** ✓
- Subtitle controls: **dedicated Subtitles tab** ✓
- Aspect ratio: **visible above fold in Export** ✓
- Basic AI direction (Structure pills): **visible above fold in Export** ✓
- Render/export action: **Start Render in footer, always visible** ✓

---

## 10. Implementation Safety

### 10.1 What Can Break

**Highest risk — EditorAudioRuntime.onTabActivate():**
Currently fires on 'audio' tab entry. After this plan, Audio tab no longer exists. The trigger must move. If forgotten, BGM and volume controls render but don't respond. This is the single most dangerous JS update in the plan.
- **Mitigation:** Fire EditorAudioRuntime.onTabActivate() on Export tab entry (since Audio moves to Settings section inside Export). This is simpler than waiting for creator to open the Settings collapse.

**High risk — Aspect Ratio elevation from Advanced fold:**
Moving evAspectRatio out of the Advanced fold's HTML structure. Must verify evToggleAdvancedOutput() does not assume Aspect Ratio is inside the fold. Must verify evQsSet() still writes to evAspectRatio by ID (it does — ID is unchanged).

**High risk — Duration elevation from Advanced fold:**
Moving evMinPart and evMaxPart out of the Advanced fold. Same structural concern as Aspect Ratio. Both inputs are read by startRenderFromEditor() at editor-view.js:2274-2275 by ID — safe as long as IDs are unchanged.

**Medium risk — EditorPerformanceRuntime triggers:**
onTabActivate() / onTabDeactivate() currently fire on 'performance' tab (Export). When Render Settings and Editor Performance move to Settings section inside Export, these triggers need to fire at the right time. Safest approach: keep them firing on Export tab entry/exit (since Settings is inside Export) and let the Performance runtime stay active whenever Export tab is visible.

**Medium risk — Market & Target move into Advanced fold:**
HTML reorder. mvMarket, mvAutoBestClips, mvKeywordHighlight, mvBestExportEnabled IDs must remain unchanged. mvHandleChange() and mvHandleAutoBestClips() are ID-based — move is safe.

**Low risk — Everything else:**
Tab renames, label changes, tooltip additions, AI/Words merge to Edit, Batch Queue move, static preview removal, X Pos collapse — these are attribute changes and HTML text changes with no functional coupling.

### 10.2 Locked IDs — Must Not Change

| ID | Why | Impact if Changed |
|---|---|---|
| evMinPart, evMaxPart | payload: editor-view.js:2274-2275 | Breaks clip duration |
| evAspectRatio | payload: editor-view.js:2272 | Breaks aspect ratio |
| evSubStyle, evSubPos, evSubPosX, evSubColor, evSubHighlight, evSubOutline | payload: editor-view.js:2239-2254 | Breaks subtitle payload |
| evEffectPreset | preset apply functions — OUTSIDE `<details>` required | Phase 64 prohibition |
| evLoudnormEnabled | preset apply functions — OUTSIDE `<details>` required | Phase 64 prohibition |
| evStartBtn | editor-view.js:2522 | Breaks render button state |
| source_video_path | render-config.js:27 | Breaks VideoLocal path display |
| local_video_file_picker | render-config.js | Breaks file picker trigger |
| manual_output_dir | render-engine.js | Breaks output folder resolution |
| bqSection | BatchQueue module | Batch Queue drag-drop |
| edPerfHealthBanner, edPerfHoverPreview, edPerfFilmstrip, edPerfWaveform | EditorPerformanceRuntime | Editor performance controls |
| mvMarket, mvAutoBestClips, mvKeywordHighlight, mvBestExportEnabled | mvHandleChange() | Market & Target functionality |

### 10.3 Recommended Implementation Order (Minimum Risk)

**Phase A — Zero functional risk (label/display only):**
1. Tab button text: "Story" → "Edit"
2. Field labels: Min clip → "Shortest clip", Max clip → "Longest clip", Output Profile → "Render quality", Reframe Mode → "Smart Crop", Y Pos → "Position from bottom"
3. Structure pill tooltips (title= attributes)
4. Quick Presets summary text update
5. Static preview removal + live-preview callout in Subtitles tab
6. evSubModeLabel: "Live preview ↑"
7. QS Bar / Subtitle tab connection hint (inspHint near Style dropdown)

**Phase B — Low risk (attribute moves + tab merges):**
1. Merge AI tab: data-insp-panel="ai" → "mode"; remove AI tab button; update validTabs/tabTitles
2. Merge Words tab: data-insp-panel="text" → "mode" on Narration + Text Layers; remove Words tab button; update validTabs/tabTitles; move EditorTextRuntime.onTabActivate() to 'mode'
3. Create "More Options" collapse in Edit tab (wrap AI Actions, Text Layers, AI Narration, History, Memory, AI Chat in a single details element)
4. Collapse X Pos and Outline into "Advanced" section in Subtitles tab
5. Collapse Translate into "Advanced" section in Subtitles tab
6. Move Market & Target inside Advanced fold in Export (HTML reorder, IDs unchanged)
7. Move Quick Presets below primary controls in Export (HTML reorder)

**Phase C — Medium risk (elevate core controls, restructure Export bottom):**
1. Elevate evAspectRatio from Advanced fold to above fold in Export
2. Elevate evMinPart and evMaxPart from Advanced fold to above fold in Export
3. Update Advanced fold HTML to not include these three controls
4. Create "Settings" section at bottom of Export tab
5. Move Audio content (data-insp-panel="audio") into Settings section — remove Audio tab button
6. Move Render Settings into Settings section (data-insp-panel change)
7. Move Editor Performance into Settings section (data-insp-panel change)
8. Move Batch Queue into Settings section (data-insp-panel change)
9. Update EditorAudioRuntime.onTabActivate() trigger → fire on Export tab entry
10. Update EditorPerformanceRuntime.onTabActivate() / onTabDeactivate() → fire on Export tab entry/exit
11. Remove auto-expand evSetInspGroupOpen('performance', true) from Export tab activation

### 10.4 What to Verify Before Phase C

- [ ] What does EditorAudioRuntime.onTabActivate() initialize? Does it need to wait for the Audio section to be visible, or can it fire on Export tab entry?
- [ ] Does EditorPerformanceRuntime need to be active from editor load (not just when Export is visible)? If yes, move its trigger to editor init instead of tab entry
- [ ] Does evToggleAdvancedOutput() assume any specific controls are inside the Advanced fold? Does it iterate children or just toggle the fold itself?
- [ ] Do evMinPart and evMaxPart have any CSS or JS that assumes they are inside a `.qsAdvBody` div? (Position in DOM matters for any CSS selectors or JS traversal)
- [ ] Does any function call evSetInspGroupOpen('performance', true) outside of the tab-activation path?

### 10.5 What Must NOT Be Done

- Do NOT move evEffectPreset or evLoudnormEnabled inside any `<details>` element — Phase 64 prohibition
- Do NOT change any QS Bar data-qs-val attribute values — evQsSet() maps exact string values
- Do NOT rename any ID in the locked IDs table above
- Do NOT change output_dir path resolution logic in startRenderFromEditor()
- Do NOT change the VideoLocal source path chain (source_video_path, local_video_file_picker, manual_output_dir)
- Do NOT touch the renderSetupCompatFields hidden inputs div

---

## 11. Out of Scope (Unchanged from UX1B)

**Three Preset System Consolidation:**
Quick Presets, Creator Presets (cpBar), Expert Preset remain as separate mechanisms. Requires dedicated phase.

**Platform → Duration Auto-Link:**
TikTok → "suggest shorter clips" is a future enhancement. evMinPart and evMaxPart are elevated to above fold as plain controls. Auto-link is NOT implemented here.

**Subtitle Style Visual Cards:**
Style remains a dropdown. Card UI requires design work outside this scope.

**Async H264 Preview Transcode:**
Medium-risk backend change. Not touched.

**VideoLocal Render Flow:**
Already correct. Not touched.

**Backend Behavior:**
All changes are frontend-only.

---

*End of Audit — PHASE UX-1C*
*Next step if approved: Phase A implementation (label/display changes) — zero functional risk, immediate visible improvement.*
