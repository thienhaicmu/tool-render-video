# PHASE UX-1A — Video Editor UI/UX Audit

**Scope:** Video Editor only (inspector right panel + preview stage + workflow entry)
**Status:** Audit only. No implementation. No redesign proposals.
**Date:** 2026-05-20
**Based on:** Full HTML/JS code read + Phase 63–74 history

---

## 1. Executive Summary

The Video Editor's core pipeline is solid. AI works. Render works. The product is ready.
The friction is structural, not functional. The editor still feels hard because:

1. **The Export tab holds everything.** Platform, subtitles, presets, batch, GPU settings, and editor performance toggles all live in one tab. The creator doesn't know where to look for anything.

2. **Three preset systems with no clear relationship** (Quick Presets, Creator Presets, Expert Preset) all appear in the same tab, stacked, with no hierarchy.

3. **The most impactful decision — platform/aspect/duration — is buried or hidden.** Aspect Ratio is in Advanced fold. Min/Max duration is in Advanced fold. The creator sets up a render without ever seeing these unless they know to open Advanced.

4. **Subtitle controls are split across two tabs** with no visual connection between them. The QS Bar subtitle pill and the full Subtitles tab are disconnected.

5. **The live subtitle preview exists but is invisible in practice.** The video frame overlay IS rendering subtitles in real time, but the creator is likely reading the small static preview in the inspector panel, not the large video on the left.

6. **Tab names are conceptual, not task-oriented.** "Story", "Words", "Performance" (internal name for Export) are not what creators think when they sit down to work.

---

## 2. Current Editor Architecture

### 2.1 Layout Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│  Sidebar (left)     │  Center Stage           │  Inspector (right)  │
│  ─────────────      │  ─────────────────────  │  ──────────────     │
│  1. Source          │  Preview + Timeline     │  "Video Editor"     │
│     Source Type     │  Rich multi-track TL    │  6 tabs:            │
│     Video URL /     │  (Video/Energy/Wave/    │  Story|Subs|Words|  │
│     Local File      │  Clips/AI/Subs/Text)    │  Audio|Export|AI    │
│  2. Package         │                         │                     │
│     Output Folder   │  [wfStrip: 5-step flow] │  Footer: status +  │
│                     │  Source→Prepare→Render  │  ▶ Start Render     │
│  [Open Editor] btn  │  →Review→Export         │                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Inspector Tab Content Map

| Tab Label | Internal ID | Contains |
|---|---|---|
| Story | `mode` | Trim section, Quick Styles (4 looks), AI Edit Actions (collapsed), Edit History (collapsed), Creator Memory panel |
| Subtitles | `subtitle` | Auto subtitle toggle, Style/Font/Size/Color/Position/Outline controls, static preview, AI Fix Subs, Translate |
| Words | `text` | AI Narration toggle, Text Layers (collapsed group) |
| Audio | `audio` | Audio Tracks (collapsed): Source volume, BGM, Loudness normalization |
| Export | `performance` | Quick Presets (collapsed), Market & Target (collapsed), Creator Presets bar, QS Bar, Max clips, Advanced fold, Batch Queue section, Render Settings (collapsed), Editor Performance section |
| AI | `ai` | Conversational editing input + example prompts |

### 2.3 Export Tab Detail (the critical tab)

In render order, top to bottom:

```
[▸ Quick Presets (4)]              ← collapsed <details>
[▸ Market & Target (4)]            ← collapsed <details>
[— No Preset — ▾]  [Save]         ← Creator Presets bar (cpBar)
Steering Panel (steering chips)    ← hidden until active
─────────────────────────────────
Platform: YouTube | TikTok | Reels
Subtitle: Off | Clean | Viral | Karaoke
Structure: More Hook | Balanced | More Story
─────────────────────────────────
Max clips: [0]  (0 = no limit)
[Advanced ▸]
  └─ Expert Preset select
  └─ Aspect Ratio  |  Output Profile
  └─ Min clip (s)  |  Max clip (s)
  └─ Multi-variant render checkbox
  └─ Add ending CTA checkbox
  └─ Title Overlay checkbox
  └─ Creator Assets (Logo/Intro/Outro/Music)
  └─ Batch Mode checkbox + URL textarea
─────────────────────────────────
[▸ Batch Queue]                    ← separate drag-drop file queue
[▸ Render Settings]                ← Device, FPS, Reframe Mode
─────────────────────────────────
Editor Performance                 ← always visible
  └─ Health banner
  └─ Hover video previews
  └─ Timeline filmstrip
  └─ Waveform lane
```

### 2.4 VideoLocal Workflow Path

```
sidebar "Local Video File" selected
  → browseLocalVideo() → file picker
  → onLocalVideoPicked()
      → if Electron: file.path → selectedLocalVideoPath
      → if browser: _pendingLocalFile stored, uploads on render
  → sidebar "Output Folder" filled
  → [Open Editor] → startRender() in render-engine.js
      → validates outputDir, localVideoPath
      → builds base payload with defaults (min_part_sec=70, max_part_sec=180, etc.)
      → calls /api/render/prepare-source (POST)
      → receives session_id, export_dir
      → openEditorView(sessionId, exportDir, payload, ...)
  → editor opens, _ev.sessionId and _ev.exportDir stored
  → creator configures settings
  → [▶ Start Render] → startRenderFromEditor()
      → reads all inspector controls
      → builds final payload
      → output_dir resolution: _ev.exportDir || payload.output_dir
          → appends /video_output if not already ending in video_output/video_out
      → payload.channel_code = '' (always clears channel)
      → payload.output_mode = 'manual' (always forces manual)
      → POST to /api/render/start
```

---

## 3. Friction Audit

### 3.1 Tab Naming — Conceptual vs Task-Based

**Current names:** Story · Subtitles · Words · Audio · Export · AI

These are content-category names, not task names. A creator does not think "I need to work on Story." They think "I need to trim this" or "I need to fix my subtitles."

| Current Name | What it actually is | What a creator is trying to do |
|---|---|---|
| Story | Trim + AI styles + Edit history | "Edit / Trim" |
| Subtitles | Subtitle style controls | "Style subtitles" |
| Words | Text overlays + AI voice | "Add text" |
| Audio | Volume, BGM, loudness | "Audio mix" |
| Export | Every setting that exists | Unclear — anything |
| AI | Chat interface | "Ask AI" |

**Most damaging mismatch:** the Export tab. Its internal name in JS is "performance" and it contains: presets, platform, subtitle style, duration, batch, GPU settings, and editor responsiveness toggles. A creator cannot mentally model what lives here.

### 3.2 Export Tab — Structural Overload

The Export tab has **at minimum 8 visible choice points before a creator opens Advanced:**

1. Which Quick Preset? (collapsed, but visible)
2. Which Market? (collapsed, but visible)
3. Which Creator Preset? (always visible dropdown)
4. Platform pill
5. Subtitle style pill
6. Structure pill
7. Max clips number
8. Open Advanced or not?

And Advanced adds ~10 more decisions.

**The problem is not the number of options.** The problem is there's no sense of priority. Everything appears with equal visual weight. A creator trying to do a first render has no idea where to start or what matters.

### 3.3 Three Preset Systems — Zero Hierarchy

Three completely separate preset mechanisms coexist in the Export tab:

| Preset System | Location | What it does | Who uses it |
|---|---|---|---|
| Quick Presets | Top of Export tab, collapsed `<details>` | Applies full starting configuration (platform, subtitle, loudness, profile) | First-time / occasional users |
| Creator Presets (`cpBar`) | Always visible dropdown below Market section | Saves/restores user's own named configurations | Power users |
| Expert Preset | Inside Advanced fold, select dropdown | Named technical presets (TikTok US Viral, EU Clean Review, etc.) | Expert users / regional targeting |

**Why this is hard:** A creator opening the Export tab sees a collapsed "Quick Presets" section, then a "— No Preset —" dropdown with a Save button, then (in Advanced) another preset select. The relationship between these three is completely opaque. Does applying a Quick Preset also change the Creator Preset dropdown? Does Expert Preset override Quick Preset? There is no visual or textual explanation.

**Historical cause:** Quick Presets and Creator Presets were added at different phases. Expert Preset was inside Advanced for power users. None were designed together.

### 3.4 Aspect Ratio — Hidden but Controlled Elsewhere

- Platform pills (TikTok, Reels) auto-set aspect ratio to 9:16 (Phase 65 — `evQsSet()`)
- Aspect Ratio control lives in Advanced fold (hidden)
- The `evAspectBadge` badge in the preview area shows the current ratio — small, 11px, easy to miss
- Creator picks TikTok → aspect changes to 9:16 → they cannot see this in the Export tab without opening Advanced

This creates a silent state change. The creator clicks TikTok, something changes, and they have no visible confirmation of what changed in the panel they're working in.

### 3.5 Min/Max Duration — Fundamental Setting in Advanced fold

Min/Max clip duration (evMinPart, evMaxPart) are the primary discovery parameters. They control what clips the AI can even find. If min=70s and the source video has natural breaks at 55s, no clips will be found for those segments.

These controls are in the Advanced fold — fully hidden unless the creator deliberately opens it.

Phase 67/70 add duration hint chips near these controls. But if the fold is closed, the chips are also invisible.

**Why this matters:** When a creator gets clips that are all too long or too short, they need to find these controls. They won't know where to look.

### 3.6 Structure Pills — No Explanation

```
Structure: [More Hook] [Balanced] [More Story]
```

"More Hook" and "More Story" are abstract. "Hook" in creator language usually means "attention-grabbing opening." But a creator unfamiliar with the product's vocabulary doesn't know if "More Hook" means:
- More clips that start with a hook?
- The clip itself is structured more hook-forward?
- The AI ranks clips with stronger hooks higher?

There is a `title="UP26: Structure bias — gentle clip ranking re-weight"` on the element's code comment, but no visible tooltip or explanation in the UI.

### 3.7 Two Batch Systems in the Same Tab

The Export tab contains two distinct batch mechanisms:

**Batch Mode** (inside Advanced fold):
- A checkbox + URL textarea
- For "One YouTube URL per line, max 10"
- Submits multiple YouTube URLs as separate jobs

**Batch Queue** (`bqSection`):
- A drag-drop zone + file picker
- For local video files dropped onto the zone
- Different submission logic (`BatchQueue.submit()`)

Both are called "batch" and both are in the Export tab. A creator trying to process multiple files doesn't know which to use. The drag-drop zone appears below the Advanced fold and below the render settings — it's buried and visually disconnected from the batch mode checkbox above it.

### 3.8 "Start Render" Button — Location and Disabled State

The **▶ Start Render** button is in the inspector footer (`evFooter`), at the very bottom of the right panel, separated from the controls above by a scroll area.

On initial load: `disabled` attribute set. The button activates when the editor is ready.

The disabled state with no explanation is a common confusing moment. Creator opens the editor, sees ▶ Start Render greyed out, doesn't know why. The `evStatusLine` below the button says "Preparing editor..." but at 12px in muted color, it's easy to miss.

---

## 4. Subtitle UX Audit

### 4.1 Current Control Inventory (Subtitles Tab)

```
[Auto subtitles ON/OFF toggle]           ← toggles the whole system

Style: [dropdown — 5 options]
  - Viral — Fast TikTok/Reels captions
  - Karaoke — Word-highlight story captions  (default)
  - Bold Cap — Large podcast/interview captions
  - Boxed — Educational/documentary captions
  - Clean — Minimal business/storytelling captions

Font: [dropdown — 8 options]
  Bungee (Viral 🔥) | Anton | Bebas Neue | Oswald
  Impact | Arial Black | Montserrat | Roboto

Size: [range slider 24–120px, shows value]
Color/Highlight: [two color pickers — text + highlight]
Y Pos: [range slider 5–60%, shows value as %]
X Pos: [range slider 5–95%, shows value as %]
Outline: [range slider 0–8px, shows value]

[Static preview: "Preview subtitle" text in current font]

[✦ Fix Subs — AI cleanup button]
[Translate subtitles checkbox]
  └─ Target language select (if checked)
```

### 4.2 Two Preview Systems, Both Inadequate

**System 1: Static preview in inspector (small)**
Located at bottom of Subtitles tab. Shows "Preview subtitle" text with current font styling applied. Size and color are shown. But:
- No frame context (no awareness of video behind it)
- No position indicator — "Y Pos 15%" means nothing without seeing where 15% falls in the frame
- No X position indicator
- Cannot show animation (karaoke word-by-word highlight)
- The "Preview subtitle" placeholder text is generic — doesn't sample real subtitle content from the video

**System 2: Live overlay in video frame (not obvious)**
`evSubOverlay` is positioned absolutely over the video frame (line 287 of index.html). It animates through word pairs: "POV: " then "never gonna". The subtitle IS rendered in real time with the current font/size/color/position.

**The gap:** The live overlay exists and is the better preview, but:
- The `evSubModeLabel` shows "Preview sample" — sounds like demo content, not live preview
- The overlay is hidden (`display:none`) until JS activates it
- The creator may not realize that the large video on the left is their subtitle preview
- The subtitle tab text and the video frame are visually disconnected — there's no arrow or call-out pointing to the overlay

**Net result:** Creator adjusts subtitle settings, watches the tiny static text in the inspector panel, and submits the render without realizing the visual result they'll get.

### 4.3 X Position — Technical Decision for 95% of Use Cases

The X Position slider (5–95%, default 50%) centers subtitles horizontally. This control exists for edge cases where a creator wants subtitles offset (e.g., for split-screen or text beside a speaker).

But for 95% of creators, center is always correct. This slider adds a decision point that should not exist by default. It was flagged as FP-4 in Phase 63 and deferred.

Having both X and Y position sliders creates the impression that subtitles need to be manually positioned, when the defaults are correct for nearly all use cases.

### 4.4 Style Dropdown vs Visual Cards

The Style dropdown works but requires reading 5 text descriptions sequentially. The names are good — "Viral — Fast TikTok/Reels captions" is clear. But it's still a text-based selector for a visual thing.

Compare this to Quick Presets in the Export tab, which use cards with icons and descriptions. The subtitle Style dropdown uses the older dropdown pattern while a visually richer style remains possible without new code.

### 4.5 Subtitle QS Bar and Subtitle Tab — Disconnected State

In the Export tab, the QS Bar has a "Subtitle" group:
```
Subtitle: [Off] [Clean] [Viral] [Karaoke]
```

In the Subtitles tab, the Style dropdown mirrors these: Viral / Karaoke / Bold Cap / Boxed / Clean.

The QS Bar pill and the Subtitles tab Style dropdown are linked via `evSyncQsBar()` / `evUpdateSubPreview()`. But visually:
- Creator picks "Viral" in Export tab QS Bar
- They switch to Subtitles tab
- They see the Style dropdown says "Viral — Fast TikTok/Reels captions"
- They don't know if this updated because of their pill click, or if it was already set

There's no visual confirmation that the pill change propagated. The "active" state on the pill provides feedback only in Export tab — not in Subtitle tab where the full controls live.

### 4.6 Outline — Default Value OK, But No Preview in Inspector

The Outline slider (0–8px, default 3px) affects readability but the static preview DOES reflect this. This is less of a problem. However, the static preview doesn't show color contrast against a dark or light background — white text with 3px outline on white background would show as unreadable, but the inspector background is dark, masking this issue.

---

## 5. VideoLocal Workflow Audit

### 5.1 Current Flow (What Actually Happens)

```
Home screen:
  [From Local File] tile → sets source_mode to "local"
  [Choose Video] → browseLocalVideo() → file picker

  ↓ user picks video file
  onLocalVideoPicked():
    - Electron path: stores to selectedLocalVideoPath
    - Browser path: stores to _pendingLocalFile (uploads on render)
    - Updates source_video_path input display value
    - Updates source_video_name div text

  ↓ user picks output folder
  [btn_pick_output_dir] → browses for folder → fills manual_output_dir

  ↓ [Open Editor] button
  startRender():
    - Validates: outputDir required, localVideoPath required
    - If _pendingLocalFile: uploadLocalFileIfNeeded() first
    - Builds base payload (min_part_sec=70, max_part_sec=180 as defaults)
    - POST /api/render/prepare-source
    - Receives: session_id, export_dir (the session's working directory)
    - Calls openEditorView(sessionId, exportDir, payload, sourceMode, localPath)

  ↓ Editor opens
  _ev.sessionId = sessionId
  _ev.exportDir = exportDir
  _ev.pendingPayload = payload (will be mutated on render)

  ↓ creator configures in inspector
  ↓ [▶ Start Render]
  startRenderFromEditor():
    - Reads all controls (evMinPart, evMaxPart, evAspectRatio, evSubStyle, etc.)
    - Output dir resolution:
        raw = payload.output_dir || _ev.exportDir
        leaf = last segment of path
        if leaf is 'video_output' or 'video_out': use raw as-is
        else: append '/video_output'
    - Forces: payload.output_mode = 'manual', payload.channel_code = ''
    - POST /api/render/start with full payload
```

### 5.2 What the UI Shows (vs What Matters)

| What UI Shows | What Actually Matters | Risk of UI Change |
|---|---|---|
| `source_video_path` input (read-only) | `selectedLocalVideoPath` or `_pendingLocalFile` | Renaming ID breaks payload builder |
| `source_video_name` div | Cosmetic display only | Low risk to change display |
| `manual_output_dir` input | Feeds into output_dir resolution | Renaming ID breaks render-engine.js |
| "Choose Video" button | Triggers `browseLocalVideo()` | Low risk to relabel |
| "Open Editor" button (labeled "Start Render" in older code) | Calls `startRender()` | Low risk to relabel |

### 5.3 Auto Folder Creation — Not Visible in UI

When `prepare-source` runs, the backend creates a session directory for this render. The `export_dir` returned is this auto-created directory. The creator never sees this path until after render completes.

**Gap:** The UI shows "Output Folder" (manual_output_dir) which the creator fills in. But the actual files are stored in `export_dir/video_output/`. This mismatch is invisible in the UI. After render, the creator may not find their files if they look in the exact folder they typed.

### 5.4 Source Sync Behavior (Channel Mode vs Manual Mode)

The `channel_code` and `output_mode` hidden inputs exist for compat. Currently the UI only shows manual mode. Channel mode is completely hidden (all channel elements are `hiddenView`).

`startRenderFromEditor()` unconditionally sets:
```js
payload.channel_code = '';
payload.output_mode = 'manual';
```

This means even if `channel_code` hidden input somehow has a value, the editor clears it. The channel sync path in `syncRenderOutputByChannel()` won't be reached in normal editor flow.

**Risk:** If any future UI change accidentally shows the channel section without updating `startRenderFromEditor()`, channel code could become visible but still be ignored, creating confusion.

### 5.5 VideoLocal Dependencies — What Must Not Change

The following IDs are read by render-engine.js, render-config.js, or editor-view.js and **must not be renamed or restructured:**

| DOM ID | Read By | Impact if Changed |
|---|---|---|
| `source_video_path` | render-config.js:27, editor-view.js (payload) | Breaks file path display and upload logic |
| `local_video_file_picker` | render-config.js:browseLocalVideo | Breaks file picker trigger |
| `manual_output_dir` | render-engine.js:2, render-config.js:244 | Breaks output folder resolution |
| `btn_pick_output_dir` | index.html onclick | Can relabel, not remove |
| `source_mode` | render-engine.js:3 | Breaks source type detection |
| `evMinPart`, `evMaxPart` | editor-view.js:2274-2275 | Breaks clip duration payload |
| `evAspectRatio` | editor-view.js:2272 | Breaks aspect ratio payload |
| `evSubStyle` | editor-view.js:2239 | Breaks subtitle style payload |
| `evEffectPreset` | preset apply functions | Must stay outside `<details>` |
| `evLoudnormEnabled` | preset apply functions | Must stay outside `<details>` |
| `evStartBtn` | editor-view.js:2522 | Breaks render button state |

---

## 6. Core Controls Audit

### 6.1 Classification: Core / Secondary / Advanced

| Control | Current Location | Real Priority | Should Be |
|---|---|---|---|
| Platform (YouTube/TikTok/Reels) | QS Bar (always visible, Export tab) | **Core** | Above fold ✓ |
| Max clips | Below QS Bar (always visible) | **Core** | Above fold ✓ |
| Subtitle on/off + style | QS Bar (Export) + Subtitles tab | **Core** | Above fold (split is the problem) |
| Min/Max duration | Advanced fold (hidden) | **Core** | Should be visible |
| Aspect Ratio | Advanced fold (hidden) | **Core** | At least informational above fold |
| Output Profile (Fast/Balanced/Quality/Best) | Advanced fold (hidden) | **Secondary** | Advanced fold is OK |
| Structure bias | QS Bar (always visible) | **Secondary** | Above fold but needs explanation |
| AI Edit Actions | Story tab, collapsed group | **Secondary** | Where it is is fine |
| Quick Styles (Viral/Cinematic/etc.) | Story tab, always visible | **Core** (editorial) | Where it is is fine |
| Trim | Story tab, always visible | **Core** (editorial) | Where it is is fine |
| Creator Assets | Advanced fold (hidden) | **Secondary** | Advanced fold is OK |
| Multi-variant | Advanced fold (hidden) | **Secondary** | Advanced fold is OK |
| CTA / Title Overlay | Advanced fold (hidden) | **Secondary** | Advanced fold is OK |
| BGM | Audio tab (collapsed) | **Secondary** | Audio tab is OK |
| Expert Preset | Advanced fold (hidden) | **Advanced** | Consider removing or deeper burial |
| Batch Mode (URLs) | Advanced fold (hidden) | **Advanced/Power** | Advanced fold is OK |
| Batch Queue (files) | Export tab, after Render Settings | **Secondary** | Poor location currently |
| Render Settings (Device/FPS/Reframe) | Export tab, collapsed | **Advanced** | Collapsed is fine |
| Editor Performance | Export tab, always visible | **Advanced** | Should be in settings, not Export |

### 6.2 What Must Surface from the Advanced Fold

If a creator cannot find a control within 5 seconds of looking at the editor, it will either be ignored or cause confusion when outputs don't match expectations.

Controls currently in Advanced fold that directly affect what clips get generated:

- **Min clip duration** (evMinPart): Determines what the AI can discover. Default 61s (Phase 73), but HTML shows 70s — may not be updated in current build.
- **Max clip duration** (evMaxPart): Upper bound on clip length.
- **Aspect Ratio** (evAspectRatio): Auto-set by platform pills, but not visible in Export tab without opening Advanced.

These three affect the render result directly. A creator who doesn't touch Advanced will get the defaults. If defaults are wrong for their content, they won't know where to fix it.

---

## 7. Decision Fatigue Analysis

### 7.1 Decision Count by Tab

**Export Tab (primary work area for render settings):**

Before opening Advanced:
- Quick Presets — "which preset?" (8 cards, collapsed but visible as an option)
- Market & Target — "which market?" (collapsed but visible as an option)
- Creator Presets — "apply a saved preset?" (always visible dropdown)
- Platform pill — 3 options (YouTube/TikTok/Reels)
- Subtitle pill — 4 options (Off/Clean/Viral/Karaoke)
- Structure pill — 3 options (More Hook/Balanced/More Story)
- Max clips — numeric input

**Total: 7 decision points above fold, not counting "open Advanced" as a decision**

After opening Advanced (~10 more):
- Expert Preset (6 options)
- Aspect Ratio (3 options)
- Output Profile (4 options)
- Min clip duration (free number)
- Max clip duration (free number)
- Multi-variant checkbox
- CTA on/off + type (2 decisions)
- Title Overlay checkbox + text
- Creator Assets (4 separate items)
- Batch Mode checkbox

**Total visible decisions in Export tab: ~17**

### 7.2 Worst Offenders

**1. Three preset systems with no hierarchy**
Creator doesn't know: "Do I start with Quick Preset, then customize? Or use Creator Preset? Or Expert Preset?" These three are not explained relative to each other. A creator who saved a Creator Preset may still wonder if they need to apply a Quick Preset first.

**2. Structure bias with no vocabulary**
"More Hook / Balanced / More Story" — A creator who doesn't know the product's terminology will guess randomly or leave it on Balanced. "Hook" is creator vocabulary but "Story" in this context means "more narrative arc clips" which is not obvious.

**3. Output Profile stacked with Expert Preset**
Both control render quality/style. "Fast Draft / Balanced / Quality / Best" vs "Manual / Custom / TikTok US Viral / EU Clean Review / JP Storytelling / etc." — these overlap conceptually but one is technical (encoding quality) and one is creative preset. Placing them adjacent inside Advanced increases confusion.

**4. Batch Queue vs Batch Mode**
Two batch systems in the same tab. Creator trying to batch-process local files → finds Batch Queue (drag-drop). Creator trying to batch YouTube URLs → finds Batch Mode (inside Advanced → checkbox → textarea). These should be clearly differentiated but they share the word "Batch" and the same tab.

**5. "Max clips: 0" — the counter-intuitive default**
The current HTML shows `value="0"` with hint "0 = no limit." Phase 73 changed the default to 6, but this may not be reflected in the current build. Even if 6, a creator who changes this to 0 gets "no limit" — which is the inverse of the usual meaning where 0 = "none selected."

### 7.3 Labels with Technical Vocabulary

| Label Shown | What It Means in Plain Language |
|---|---|
| "Min clip (s)" | "Shortest clip the AI can make" |
| "Max clip (s)" | "Longest clip the AI can make" |
| "Output Profile" | "Render quality vs. speed" |
| "Reframe Mode" | "How the camera follows subjects when cropping to vertical" |
| "Loudness normalization" | "Auto-volume for all platforms" |
| "Y Pos: 15%" | "Subtitle height from bottom: 15%" |
| "X Pos: 50%" | "Subtitle left-right: centered" |
| "Outline: 3px" | "Text border thickness" |
| "Multi-variant render" | "Render with multiple style variations in one job" |
| "highlight_per_word" | (internal — never shown, but lurks in payload) |

---

## 8. Safe Simplification Opportunities

These are identified opportunities only. No implementation recommendation.

### 8.1 Label-only Changes (Essentially Zero Risk)

1. **Tab labels:** Rename without changing `data-insp-tab` values or DOM structure.
   - "Story" → "Edit" (or "Trim & Style")
   - "Words" → "Layers"
   - Current labels are safe to change in HTML text only

2. **Control labels:**
   - "Min clip (s)" → "Shortest clip" or "Min clip length"
   - "Max clip (s)" → "Longest clip" or "Max clip length"
   - "Output Profile" → "Render quality" (Phase 65 recommended this)
   - "Reframe Mode" → "Smart Crop" (Phase 65 recommended this)
   - "Y Pos" → "Vertical position" or "Position from bottom"
   - "X Pos" → "Horizontal position" (if it must stay visible)

3. **Structure pill tooltips:** Add `title="..."` attributes explaining More Hook and More Story in one sentence each. No JS, no DOM change.

4. **Preset section clarification:** Change `<summary>Quick Presets (4)</summary>` to include a brief parenthetical description: e.g., `"Quick Presets — starting points"` vs `"Creator Presets — your saved settings"` vs `"Expert Preset — named technical configs"`.

### 8.2 Visibility Changes (Low Risk if IDs Preserved)

5. **Show Aspect Ratio current value above fold:** Add a read-only badge or `<span>` in the Export tab above the QS Bar showing "Current: 9:16" that updates via JS. This badge has no form value, it's display-only. Low risk.

6. **Show a min/max duration hint above fold:** Add a single read-only line (like the existing `evAspectBadge`) showing "Clip length: 61s – 180s" that reflects the current evMinPart/evMaxPart values. Updates when Advanced changes. Pure display, zero functional risk.

7. **Subtitle tab: Point creator to video frame preview:** Add a small call-out in the Subtitle tab — "See live preview in the video on the left" — near the static preview. Label the `evSubModeLabel` more clearly as "Live preview in video ↑" when subtitle mode is active.

### 8.3 Organizational Changes (Medium Risk — Must Audit Each Change)

8. **Move Editor Performance section out of Export tab:** It conceptually belongs in Settings (or a collapsed section within the editor) rather than Export. However: if it's moved, the `edPerfHealthBanner`, `edPerfHoverPreview`, `edPerfFilmstrip`, `edPerfWaveform` IDs must remain in DOM and JS-accessible.

9. **Move Market & Target into Advanced fold:** Already collapsed by default. Moving it deeper (into Advanced alongside Expert Preset) would clean up the Export tab top area. Risk: `mvMarket`, `mvAutoBestClips`, `mvKeywordHighlight`, `mvBestExportEnabled` IDs must remain accessible to `mvHandleChange()` and `mvHandleAutoBestClips()`.

10. **Consolidate Batch Queue and Batch Mode:** Give them different names. "File Batch" vs "URL Batch" for example. Requires only label changes + visual separation.

11. **Reorder Export tab:** Move QS Bar to the top (before Creator Presets bar). The QS Bar is the most frequently used primary control. The cpBar is secondary. Swap order requires only HTML reordering; IDs/JS remain same. Risk: Minor visual regression only.

---

## 9. Risk Analysis

### 9.1 High-Risk Changes

| Change | Risk | Why |
|---|---|---|
| Move `evEffectPreset` inside `<details>` | CRITICAL | `evApplyPreset()` reads it by ID unconditionally; if inside closed `<details>`, some browsers may hide it from DOM traversal |
| Move `evLoudnormEnabled` inside `<details>` | CRITICAL | Same as above — Phase 64 constraint explicitly prohibits this |
| Rename any ID in `startRenderFromEditor()` payload section | HIGH | Every ID read on lines 2229–2490 feeds directly into render API payload |
| Change `output_dir` path logic (the `/video_output` append) | HIGH | Backend expects this structure; changing breaks file location for all local renders |
| Change QS Bar `data-qs-val` attribute values | HIGH | `evQsSet()` maps exact values to subtitle styles, aspect ratios, and platform targets |
| Remove `evTargetPlatform` hidden input | HIGH | `evSyncQsBar()` reads this; removing breaks platform pill state |
| Change `evMinPart` or `evMaxPart` input type | HIGH | `Number(qs('evMinPart').value)` in startRenderFromEditor — must remain numeric |

### 9.2 Medium-Risk Changes

| Change | Risk | Why |
|---|---|---|
| Reorder sections in Export tab | MEDIUM | Visual regression possible; no functional risk if IDs unchanged |
| Move Batch Queue section | MEDIUM | `bqSection` is referenced by `BatchQueue` module by ID; must verify no positional CSS assumptions |
| Add/remove `<details>` wrappers | MEDIUM | Phase 64 constraint: only safe if hidden inputs remain outside the wrapper |
| Change subtitle tab layout | MEDIUM | `evSubSize`, `evSubPos`, `evSubPosX`, `evSubColor`, `evSubHighlight`, `evSubOutline` all read by payload builder |
| Collapse/expand behavior of `qsAdvBody` | LOW-MED | `evToggleAdvancedOutput()` toggles this; changing the toggle trigger is safe, removing the div is not |

### 9.3 Low-Risk Changes

| Change | Risk | Why |
|---|---|---|
| Tab label text changes | LOW | `data-insp-tab` values are what matter, not the text |
| Field label text changes | LOW | Labels are `<span class="fieldLabel">`, not IDs |
| Adding `title` attributes (tooltips) | LOW | No functional impact |
| Adding read-only display badges | LOW | Pure HTML, no form value, no payload impact |
| Changing placeholder text | LOW | No functional impact |
| Reordering `<details>` open/closed defaults | LOW | Only affects visual state, not DOM access |
| Changing hint text (`inspHint` spans) | LOW | No functional impact |

### 9.4 VideoLocal-Specific Risks

The following UI areas must not be removed or renamed, even if they appear redundant or could be simplified visually:

- **`renderSetupCompatFields` div and all its hidden inputs** (lines 71-92 of index.html) — these exist as compat targets for legacy JS paths. Phase 63 documentation explicitly states "All controls remain in DOM."
- **`source_video_path` input** — Electron reads `file.path` and stores to `selectedLocalVideoPath`; the input is also used for display. Both the display and the value chain matter.
- **`local_video_file_picker` input (hidden)** — `browseLocalVideo()` calls `.click()` on this element by ID.
- **`v3SteeringPanel` div** — Set to `style="display:none"` when no steering active. JS shows/hides it by style, not by class. Changing to CSS class-based hiding requires updating `v3RefreshSteeringPanel()`.

---

## 10. Recommended Scope Boundary

Before any UI change is designed, these questions must be answered:

### 10.1 What to Audit Before Touching

**Export Tab:** Before touching anything in the Export tab structure, read `evApplyPreset()`, `evApplyOutputPreset()`, `evQsSet()`, `evSyncQsBar()`, `evToggleAdvancedOutput()`, and `startRenderFromEditor()`. These functions assume specific IDs exist and are accessible. Any structural change (wrapping in details, reordering, hiding) requires checking all five.

**Subtitle Tab:** Before touching the Subtitles tab, read `evUpdateSubPreview()` and `startRenderFromEditor()` lines 2229–2254. Every subtitle control in the tab has a corresponding payload field. Adding or removing controls without updating the payload builder will create silent defaults.

**VideoLocal UI:** Before touching the sidebar Source section, read `onLocalVideoPicked()`, `uploadLocalFileIfNeeded()`, and `startRender()`. The chain is: file picker → path stored in JS variable → path synced to input display → used in render payload. Breaking any link in this chain produces silent failures (render starts but with wrong source path).

### 10.2 What Is Definitely Safe to Improve Now

1. Tab label text changes (Story/Words/Export names)
2. Field label text changes (Min clip / Max clip / Reframe Mode / Output Profile)
3. Structure pill tooltips
4. "Live preview is the video on the left" hint in Subtitle tab
5. Read-only aspect ratio current-value display in Export tab
6. Read-only duration current-value display in Export tab

### 10.3 What Requires a Dedicated Implementation Phase

1. Elevating Min/Max duration above the Advanced fold — requires dirty flag infrastructure (Phase 73A identified this gap; flags `_evMinPartTouched`/`_evMaxPartTouched` do not exist yet)
2. Consolidating the three preset systems — requires understanding the preset state machine and all places that read `evEffectPreset`
3. Subtitle tab visual card preview — requires a proper positioned preview mock, not just the current styled text
4. Moving Editor Performance out of Export tab — requires confirming no CSS position assumptions in the health banner

### 10.4 What Should Not Be Touched in This Cycle

- The VideoLocal source path chain
- Output directory path resolution logic in `startRenderFromEditor()`
- The `renderSetupCompatFields` hidden inputs
- The `evEffectPreset` / `evLoudnormEnabled` positioning (outside `<details>`)
- QS Bar `data-qs-val` attribute values (they map to backend values)
- Channel sync code (inactive but present; removing could break edge cases)

---

*End of Audit — PHASE UX-1A*
*Next step: UX-1B (Implementation Plan) — only after this document is reviewed and scope is confirmed.*
