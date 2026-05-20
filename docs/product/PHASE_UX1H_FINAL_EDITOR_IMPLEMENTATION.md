# PHASE UX-1H — Final Locked Video Editor Implementation Plan

**Type:** Implementation plan — NOT redesign, NOT code
**Date:** 2026-05-20
**Principle:** If AI can safely decide → hide it. If creator must confirm intent → show it.
**Locked tabs:** Edit / Captions / Export — no restructure
**Source:** UX1A through UX1F audit series + UX1H locked model spec

> **Note:** `PHASE_UX1G_R2_LOCKED_EDITOR_PLAN.md` was referenced in this phase's brief but does not exist in the repository. The locked editor structure defined in this phase's spec supersedes any prior intermediate planning. All decisions here are grounded in the UX1A–UX1F audit series.

---

## 1. Executive Summary

### 1.1 Why This Editor Is Finally Simpler

The original 6-tab editor asked the creator to navigate six conceptual spaces before hitting render. Three of those tabs (Audio, Words, AI) were for opt-in features most creators never touch. The Export tab alone contained 17+ decisions — presets, platform, subtitle style, batch, GPU settings, and editor diagnostics — all with equal visual weight.

The final 3-tab model collapses those six spaces into three task-oriented areas:

- **Edit** answers: "What do you want the clips to be like?"
- **Captions** answers: "How should the text look?"
- **Export** answers: "Where are you publishing, at what quality, and how many clips?"

That is the complete mental model. A creator who understands these three questions understands the editor.

### 1.2 What Complexity Disappeared

| What Was Removed | Where It Went | Why |
|---|---|---|
| Audio tab (Source volume, BGM, Loudness) | Edit Advanced / permanently hidden | Loudness always on; BGM/volume are opt-in power features |
| Words tab (AI Narration, Text Layers) | Edit Advanced / Captions Advanced | Narration is opt-in; Text Layers collapse to Captions Advanced |
| AI tab (chat panel) | Edit Advanced (deep) | Power feature; creator who needs it knows to look |
| Quick Presets (8 cards) | Edit Advanced | AI handles defaults; creator who wants starting point can find them |
| Market & Target | Edit Advanced | Professional feature; all default off; no effect on standard render |
| Creator Presets bar | Footer (tab-independent) | Correct home — never was an Edit-tab decision |
| Structure Bias (AI Picks) | Auto-driven by Platform selection | Platform implies clip bias; creator doesn't need to decide twice |
| Quality selector | Hidden default Balanced | Balanced is always correct; power users access Export Advanced |
| Reframe Mode (from Render Settings) | Edit tab as "Reframe" (creator-controlled) | Frame-ratio conversion affects creator's visual result — creator must confirm |
| Editor Performance section | Edit Advanced | Not a render decision; belongs in settings, not render flow |
| Batch Queue | Hidden | Power workflow; most creators never use it |
| Edit History | Removed from UI | Creator cannot act on history during render setup |
| Creator Memory panel | Removed from UI | Passive reference; not a render decision |
| Three-preset system confusion | Rationalized | Quick Presets → Edit Advanced; Creator Presets → Footer; Expert Preset → Edit Advanced |

### 1.3 Why Creator Workflow Is Faster

The creator flow is now:

```
Open editor
  → Edit: Trim source → pick Style → set Frame Ratio → set Reframe → set Duration
  → Captions: toggle Subtitles ON → pick Style → set Position
  → Export: pick Optimize For (only for 9:16/1:1 creators) → set FPS → click Render
```

For a 16:9 YouTube creator: Optimize For is hidden (auto-set). FPS defaults to Auto (source-matched). The Export tab contains exactly **one visible decision** (FPS) plus the Render button.

For a 9:16 TikTok creator: Optimize For shows three platform options. One tap. Then Render.

Under 60 seconds for an experienced creator. Under 2 minutes for first-time.

### 1.4 Why Render Quality Remains Safe

Every hidden control has a safe, calibrated default that matches or improves on current behavior:

- **AI Picks (structure_bias)** — platform-derived default is better than the previous static 'balanced' for TikTok creators. Platform click auto-writes the correct bias.
- **Loudness normalization** — always on. No creator should turn this off.
- **Playback speed (1.07x)** — research-calibrated. Platform speed_delta adjusts further.
- **Zoom (106%)** — hardcoded correct value. Edge artifacts prevented.
- **Quality (Balanced)** — good output for all platforms. Power user override in Export Advanced.
- **FPS (Auto)** — matches source FPS, preventing frame rate mismatch artifacts.
- **Reframe default** — Frame Ratio click auto-suggests the correct reframe mode; creator can override before render. No silent bad crops.

---

## 2. Current → Final Mapping

Complete mapping of every existing control to its final location.

---

### 2.1 Tab Bar

```
CURRENT:
Story | Subtitles | Words | Audio | Export | AI

FINAL:
Edit | Captions | Export

WHY:
Three tabs removed from tab bar. Audio/Words/AI content moves to Edit Advanced.
Tab labels renamed to task-based language.

RISK: Low
  - data-insp-panel values do NOT change (mode/subtitle/performance)
  - Only display text on tab buttons changes
  - validTabs array in setInspectorTab() must update: remove 'text', 'audio', 'ai'
  - If JS calls setInspectorTab('text'/'audio'/'ai') from other modules, those
    must redirect to 'mode' (Edit tab)
```

---

### 2.2 Story Tab (data-insp-panel="mode") → Edit Tab

```
CURRENT:
Story tab → Trim section, Quick Styles (4 cards), AI Edit Actions (collapsed),
Edit History (collapsed), Creator Memory panel

TRIM:
FINAL: Remains in Edit tab, primary position
WHY: Creator intent — AI cannot determine which portion of source footage to process
RISK: None

QUICK STYLES (Viral / Cinematic / Aggressive / Balanced):
FINAL: Remains in Edit tab as "Video Style" — renamed section heading
WHY: Brand identity — must remain creator-controlled
CRITICAL: Each style card MUST continue to call evApplyPreset() on click
  evEffectPreset hidden input MUST remain in DOM, OUTSIDE any <details>
RISK: Low — rename only; evApplyPreset() chain must not break

AI EDIT ACTIONS (collapsed):
FINAL: Removed from primary flow — into Edit Advanced if genuinely useful
WHY: Power feature; creator does not need this on render setup
RISK: Low

EDIT HISTORY (collapsed):
FINAL: Removed from UI entirely
WHY: Creator cannot act on history during render setup
  History is "what happened," not "what to do"
RISK: None — collapsed section removal

CREATOR MEMORY PANEL:
FINAL: Removed from UI entirely
WHY: Passive reference. Not a render decision. Belongs in Settings/Profile.
RISK: None — display-only panel removal
```

---

### 2.3 Subtitles Tab (data-insp-panel="subtitle") → Captions Tab

```
CURRENT:
Subtitles tab → Subtitle toggle, Style, Font, Size, Color/Highlight, Y Pos, X Pos,
Outline, Static preview, Fix Subs, Translate

SUBTITLE ON/OFF TOGGLE:
FINAL: Captions tab, primary position (top)
WHY: Whether subtitles appear is creator's publishing decision
RISK: None

SUBTITLE STYLE dropdown:
FINAL: Captions tab, visible — remains primary control
WHY: Brand identity; platform-relevant
RISK: None

POSITION (Bottom / Middle / Top):
FINAL: Captions tab, visible — 3-button row replacing Y Pos slider
WHY: 3 options replace technical percentage slider; creator intent, not AI decision
IMPLEMENTATION: 3 buttons write specific values to evSubPos:
  Bottom → evSubPos.value = 15 (or current calibrated bottom value)
  Middle → evSubPos.value = 50
  Top    → evSubPos.value = 85 (or current calibrated top value)
  evSubPos input must remain in DOM (line 2250 reads it)
RISK: Low — display change; evSubPos ID unchanged

TEXT LAYER section:
FINAL: Captions Advanced — "Add Text Layer" entry only
WHY: Text layers are opt-in creator content; complex for primary UI
RISK: Low — DOM section moves, IDs unchanged
  EditorTextRuntime.onTabActivate() trigger must move (see Section 4)

FIX SUBS button:
FINAL: Captions tab, CONDITIONAL — visible only when subtitle confidence is low
IMPLEMENTATION CHALLENGE: Confidence score must come from prepare-source or
  subtitle generation response. If not available at render-setup time:
  FALLBACK → show always (simpler, no confidence signal required)
  See Section 4.3 for full conditional logic plan.
WHY: One-tap action button; creator who gets bad subtitles needs easy access
RISK: Low if shown always (fallback). Medium if conditional (requires backend signal).

TRANSLATE checkbox + language select:
FINAL: Captions Advanced collapse
WHY: Opt-in feature; off by default; hidden is safe
RISK: None — already off by default

FONT dropdown:
FINAL: Captions Advanced collapse
WHY: Font is secondary to Style (Style already implies a font); power user tweak
RISK: Low — evSubFont ID must remain in DOM (payload builder reads it)

SIZE slider:
FINAL: Captions Advanced collapse
WHY: Default 46px is calibrated; creator adjusts after seeing live preview
RISK: Low — evSubSize ID must remain in DOM

COLOR / HIGHLIGHT pickers:
FINAL: Captions Advanced collapse
WHY: White/Yellow defaults are standard. Creator who needs brand colors finds in Advanced.
NOTE: This is a reduction from UX1F which recommended keeping Color visible.
  Rationale: Color is secondary to Style/Position in creator setup priority.
  If user feedback shows creators missing color control, it can surface quickly.
RISK: Low — evSubColor, evSubHighlight IDs must remain in DOM

X POS (horizontal) slider:
FINAL: Captions Advanced collapse (as "Fine Position — Horizontal")
WHY: 50% (centered) correct for 95%+ of use cases
evSubPosX input must remain in DOM at value 50 (line 2250 reads it)
RISK: Low

OUTLINE slider:
FINAL: Captions Advanced collapse
WHY: 3px default calibrated; power user adjustment only
evSubOutline ID must remain in DOM
RISK: None

STATIC PREVIEW ("Preview subtitle" text in inspector):
FINAL: REMOVED
WHY: Inadequate (no frame context, no animation, no real content)
  Live preview on video frame replaces it entirely
  Add callout in Captions tab: "↑ Adjust and watch your video on the left"
RISK: None — display element removal
```

---

### 2.4 Words Tab (data-insp-panel="text") → Edit Advanced

```
CURRENT:
Words tab → AI Narration toggle + sub-controls, Text Layers (collapsed group)

AI NARRATION toggle + sub-controls:
FINAL: Edit Advanced — "Narration" section (conditional if enabled)
WHY: Opt-in power feature; most creators don't use it
RISK: Medium — EditorTextRuntime.onTabActivate() currently fires on Words tab entry
  After merge: must fire when Edit Advanced Narration section expands
  (or on Edit tab entry if EditorTextRuntime is lightweight enough to init early)
  See Section 3 for runtime dependency detail.

TEXT LAYERS (collapsed group):
FINAL: Captions Advanced — "Add Text Layer" entry
WHY: Text layers appear on the video frame alongside subtitles — belongs with Captions
RISK: Low — DOM move; EditorTextRuntime trigger update needed
```

---

### 2.5 Audio Tab (data-insp-panel="audio") → Hidden + Edit Advanced

```
CURRENT:
Audio tab → Source volume slider, BGM toggle + sub-controls, Loudness normalization

SOURCE VOLUME (evVolume):
FINAL: Edit Advanced — "Source Audio" section
WHY: Opt-in adjustment; loudness normalization handles platform levels automatically
DEFAULT: 100% (no change) — always correct starting point
RISK: Low — ID unchanged; trigger update needed

BGM toggle + file/volume/fade:
FINAL: Edit Advanced — "Background Music" section (conditional when enabled)
WHY: Optional feature; off by default; no effect on standard render
RISK: Low — IDs unchanged; trigger update needed

LOUDNESS NORMALIZATION (evLoudnormEnabled):
FINAL: PERMANENTLY HIDDEN — always on
WHY: Platform audio normalization is always correct. Exposing this control risks
  creators turning it off and producing clips with wrong loudness levels.
CRITICAL CONSTRAINT (Phase 64): evLoudnormEnabled input must remain in DOM
  and must remain OUTSIDE any <details> element after restructuring.
  evApplyPreset() reads it unconditionally by ID.
RISK: None for behavior — HIGH RISK if DOM constraint violated

AUDIO TAB REMOVAL:
When tab is removed from tab bar, EditorAudioRuntime.onTabActivate() currently
fires on 'audio' tab entry. After removal, this trigger moves to Edit tab entry.
See Section 3.4 for runtime dependency resolution.
```

---

### 2.6 Export Tab (data-insp-panel="performance") → Export Tab (reduced)

```
CURRENT:
Export tab → Quick Presets (collapsed), Market & Target (collapsed), Creator Presets bar,
QS Bar (Platform/Subtitle/Structure pills), Max clips, Advanced fold (Expert Preset,
Aspect Ratio, Min/Max clip, multi-variant, CTA, Title Overlay, Creator Assets, Batch Mode),
Batch Queue section, Render Settings (Device/FPS/Reframe), Editor Performance

QS BAR — Platform pills (YouTube / TikTok / Reels):
FINAL: REPLACED by "Optimize For" conditional in Export tab
  Logic: visible only when Frame Ratio ≠ 16:9 (see Section 5.1 for full conditional)
  When visible: [TikTok] [Reels] [Shorts] (for 9:16)
  evTargetPlatform still written on selection
WHY: Platform pill in old model conflated format + encoding bias.
  Now Frame Ratio is in Edit tab (creator's format choice) and Optimize For is
  in Export (AI tuning only). Decoupled correctly.
RISK: Medium — QS Bar pills currently call evQsSet() which sets BOTH evAspectRatio
  AND evTargetPlatform. After decoupling: Optimize For clicks must ONLY write
  evTargetPlatform + qsStructureBias. Must NOT touch evAspectRatio.
  evQsSet() may need a new code path or the Optimize For buttons bypass evQsSet()
  entirely and write directly.

QS BAR — Subtitle pills (Off / Clean / Viral / Karaoke):
FINAL: REMOVED from Export tab
WHY: Subtitle style belongs in Captions tab — having it in QS Bar created
  the disconnected-state problem (UX1A §4.5). Style is set in Captions tab.
RISK: Medium — evSyncQsBar() currently syncs QS Bar subtitle pill with Subtitle tab.
  When pill is removed, evSyncQsBar() must be updated or removed for subtitle group.
  Ensure Subtitle tab Style dropdown still works independently.

QS BAR — Structure pills (More Hook / Balanced / More Story):
FINAL: REMOVED from primary UI — auto-driven by Optimize For selection
  JS: Platform selection auto-writes qsStructureBias (see Section 5.1)
  qsStructureBias hidden input must remain in DOM (line 2464 reads it)
WHY: Creator does not need to decide clip selection bias separately from platform.
  Platform already implies the correct bias.
RISK: Medium — new JS behavior required (see Section 5)

MAX CLIPS (evMaxExportParts):
FINAL: Edit tab as "Output Count" — below Clip Duration
WHY: Moved in UX1F analysis but new locked model places it in Edit tab
  "How many clips" is part of the editing setup, not the export decision
RISK: Low — HTML reorder; ID evMaxExportParts unchanged

QUICK PRESETS (collapsed section at top):
FINAL: Edit Advanced — "Quick Presets — Starting Points"
WHY: Starting-point tool; not needed on standard re-render
RISK: Low — DOM section move; IDs unchanged; evApplyPreset() chain must remain working

MARKET & TARGET (collapsed section):
FINAL: Edit Advanced
WHY: Professional feature; all default off
RISK: Low — mvMarket, mvAutoBestClips, mvKeywordHighlight, mvBestExportEnabled
  IDs must remain DOM-accessible for mvHandleChange(), mvHandleAutoBestClips()

CREATOR PRESETS BAR (cpBar):
FINAL: Footer position — tab-independent
WHY: Creator preset applies across all tabs; doesn't belong inside any single tab
RISK: Medium — cpBar has CSS position assumptions relative to inspector panel.
  Moving to footer requires CSS update. JS cpBar functions must still find it by ID.

ADVANCED FOLD — Expert Preset select:
FINAL: Edit Advanced
WHY: Power user preset; not a first-render decision
RISK: Low — evApplyOutputPreset() must still find the element

ADVANCED FOLD — Aspect Ratio (evAspectRatio):
FINAL: REPLACED by Frame Ratio buttons in Edit tab (visible)
WHY: Frame Ratio is now a primary creator decision in Edit tab, not hidden in Advanced
CRITICAL: evAspectRatio hidden input must remain in DOM.
  Frame Ratio buttons write to evAspectRatio by ID — same payload path.
  The visible buttons replace the old hidden select; the select can become a
  hidden input holding the current value.
RISK: Medium — evQsSet() currently writes evAspectRatio from QS Bar.
  After change: Frame Ratio buttons in Edit tab write evAspectRatio directly.
  Platform pills (now Optimize For) must NOT write evAspectRatio.

ADVANCED FOLD — Output Profile (evRenderProfile):
FINAL: HIDDEN default Balanced — exposed in Export Advanced only
WHY: Balanced is always correct for standard renders
DEFAULT: evRenderProfile.value = 'balanced'
RISK: None

ADVANCED FOLD — Min/Max clip duration (evMinPart / evMaxPart):
FINAL: Edit tab as "Clip Duration — Shortest / Longest" (visible, primary)
WHY: Most impactful control for AI clip discovery; must be above fold (UX1A §6.2, §3.5)
RISK: Low — IDs unchanged; just move to Edit tab panel from Advanced fold

ADVANCED FOLD — Multi-variant checkbox (evMultiVariant):
FINAL: Edit Advanced
WHY: Power feature; off by default
RISK: None

ADVANCED FOLD — CTA, Title Overlay:
FINAL: Edit Advanced
WHY: Optional features; off by default
RISK: None

ADVANCED FOLD — Creator Assets (Logo/Intro/Outro/Music profile):
FINAL: Edit Advanced
WHY: Optional branding; null by default
RISK: None

ADVANCED FOLD — Batch Mode (checkbox + URLs):
FINAL: Edit Advanced — "Batch URLs" section
WHY: Power feature; off by default
RISK: None

BATCH QUEUE section (bqSection):
FINAL: Edit Advanced — "Batch Queue" section
WHY: Power feature for file-based batch processing
RISK: Low — bqSection ID must remain in DOM for BatchQueue module

RENDER SETTINGS — Device (evRenderDevice):
FINAL: HIDDEN (GPU Auto) — Export Advanced "Performance" section
WHY: 'auto' is always correct; manual selection only needed for hardware issues
DEFAULT: evRenderDevice.value = 'auto'
RISK: None

RENDER SETTINGS — Output FPS (evOutputFps):
FINAL: Export tab as "FPS" — visible [Auto] [30 FPS] [60 FPS]
WHY: FPS affects output quality and platform compatibility; creator may need to override
  Auto mode matches source FPS (see Section 5.2)
RISK: Low — evOutputFps ID unchanged; Auto mode requires new JS

RENDER SETTINGS — Reframe Mode (evReframeStrategy):
FINAL: Edit tab as "Reframe" — visible, creator-controlled
WHY: Frame-ratio conversion directly affects visual result.
  Creator must confirm or override reframe behavior.
  AI suggests defaults (16:9→Center, 9:16→Follow Face) but creator decides.
RISK: Low — evReframeStrategy ID unchanged; default-suggestion JS is new

EDITOR PERFORMANCE section (edPerfHealthBanner etc.):
FINAL: Edit Advanced — "Editor Performance" section
WHY: Not a render decision. Belongs in settings, not render flow.
CRITICAL: edPerfHealthBanner, edPerfHoverPreview, edPerfFilmstrip, edPerfWaveform
  IDs must remain DOM-accessible for EditorPerformanceRuntime
RISK: Medium — EditorPerformanceRuntime.onTabActivate()/onTabDeactivate() currently
  fire on Export (performance) tab entry/exit. After move to Edit Advanced, triggers
  must update. See Section 3.4.
```

---

## 3. Final Edit Tab Implementation

### 3.1 Exact Component Order

```
TAB 1 — Edit (data-insp-panel="mode")
────────────────────────────────────────────────────────
[1] TRIM
    In: [─────●─────────────────────] Out: [────────────●─────]
    Duration display: "4:35 / 12:30"
    Controls: evTrimIn, evTrimOut (or timeline in/out markers)

[2] VIDEO STYLE
    Section heading: "Style"
    [Viral 🔥]  [Cinematic 🎬]  [Aggressive ⚡]  [Balanced ⚖️]
    Each card calls evApplyPreset() on click
    evEffectPreset hidden input reads result — MUST remain outside <details>
    evLoudnormEnabled hidden input — MUST remain outside <details>

[3] FRAME RATIO
    Section heading: "Frame Ratio"
    [9:16 ↕]  [1:1 □]  [16:9 ↔]  [3:4 ▭]
    Each button writes to evAspectRatio (ID unchanged)
    On selection: triggers Reframe default suggestion (see 3.2)

[4] REFRAME
    Section heading: "Reframe"
    [Auto ✓]  [Follow Face]  [Follow Person]  [Center]
    Writes to evReframeStrategy
    Default highlighted based on Frame Ratio selection (see 3.2)
    Creator override: any button can be clicked regardless of AI suggestion
    Tooltip on each: "Auto — best for most footage"
                     "Follow Face — tracks the nearest face in frame"
                     "Follow Person — tracks full body"
                     "Center — fixed center crop"

[5] CLIP DURATION
    Section heading: "Clip Duration"
    Shortest [61] s  ——  Longest [180] s
    Controls: evMinPart, evMaxPart (IDs unchanged)
    Labels: "Shortest" / "Longest" (replaces "Min clip (s)" / "Max clip (s)")

[6] OUTPUT COUNT
    Section heading: "Output Count" (or just "Clips")
    [6]  clips
    Control: evMaxExportParts (ID unchanged, moved from Export tab)

[▸ Advanced]
    ─── Clip & AI Settings ───
    └─ AI Clip Selection:     [Hook-Heavy]  [Balanced ✓]  [Story Arc]
                              Writes qsStructureBias (hidden input — must stay in DOM)
                              Note: auto-written by Optimize For; manual override here
    └─ Part Order:            [Best First ▾]  (evPartOrder, default 'viral')
    └─ Multi-variant:         [ ] 3 style variants per render  (evMultiVariant)
    ─── Audio Settings ───
    └─ Source Volume:         [──────●──────] 100%  (evVolume)
    └─ Background Music:      [ ]  → [file picker] [volume] [fade]  (evBgmEnable)
    ─── Content Add-ons ───
    └─ AI Narration:          [ ]  → [source] [language] [gender] [rate] [text]
                              (evVoiceEnable + sub-controls)
    └─ CTA:                   [ ]  → [type ▾]  (cta_enabled)
    └─ Title Overlay:         [ ]  → [text input]  (add_title_overlay)
    └─ Creator Assets:        [Logo] [Intro] [Outro] [Music Profile]
    ─── Technical ───
    └─ Expert Preset:         [— Manual — ▾]  (evApplyOutputPreset target)
    └─ Quick Presets:         [▸ Starting Points (4)]
    └─ Market & Target:       [collapsed group]  (mvMarket etc.)
    └─ Batch Mode (URLs):     [ ]  → [URL textarea]
    ─── Advanced ───
    └─ AI Chat:               [conversational panel — collapsed by default]
    └─ Batch Queue:           [drag-drop zone]  (bqSection — ID unchanged)
    └─ Editor Performance:    [health banner + toggles]
                              (edPerfHealthBanner, edPerfHoverPreview,
                               edPerfFilmstrip, edPerfWaveform — IDs unchanged)
```

### 3.2 Reframe Behavior — Default Suggestion on Frame Ratio Click

When creator picks a Frame Ratio, the editor auto-highlights a Reframe suggestion. This is a visual suggestion only — creator can override at any time.

```javascript
// Fires when Frame Ratio button is clicked
function onFrameRatioSelected(ratio) {
  // 1. Write aspect ratio (existing behavior)
  document.getElementById('evAspectRatio').value = ratio; // '9:16', '1:1', '16:9', '3:4'

  // 2. Suggest reframe default (NEW behavior)
  const reframeEl = document.getElementById('evReframeStrategy');
  if (!reframeEl) return;

  // Do not overwrite if creator manually changed reframe in this session
  if (reframeEl.dataset.manuallySet === '1') return;

  if (ratio === '16:9') {
    // No aspect ratio conversion — center is appropriate
    reframeEl.value = 'fast_center';
    highlightReframeButton('center');
  } else {
    // Conversion occurring — subject tracking is better than center crop
    reframeEl.value = 'subject';
    highlightReframeButton('subject');  // highlights "Follow Face" button
  }
}

// Fires when creator manually clicks a Reframe button
function onReframeSelected(mode) {
  document.getElementById('evReframeStrategy').value = mode;
  document.getElementById('evReframeStrategy').dataset.manuallySet = '1';
  highlightReframeButton(mode);
}
```

**Reframe → payload mapping** (editor-view.js lines 2328–2330, unchanged):
```javascript
const _reframeStrategy = document.getElementById('evReframeStrategy')?.value || 'fast_center';
payload.motion_aware_crop = _reframeStrategy !== 'fast_center';
payload.reframe_mode = _reframeStrategy === 'fast_center' ? 'center' : _reframeStrategy;
```

Reframe button label → evReframeStrategy value mapping:
| Button | evReframeStrategy value | payload.reframe_mode |
|---|---|---|
| Auto | 'subject' | 'subject' |
| Follow Face | 'subject' | 'subject' |
| Follow Person | 'motion' | 'motion' |
| Center | 'fast_center' | 'center' |

Note: "Auto" and "Follow Face" both map to 'subject'. Auto is the user-facing label for the AI-suggested default when reframe hasn't been manually set. In the hidden input, 'subject' is the value for both.

### 3.3 DOM and Runtime Dependencies

**Critical DOM requirements for Edit tab:**

| Input ID | Type | Required Because | Constraint |
|---|---|---|---|
| evEffectPreset | hidden input | startRenderFromEditor() line 2349, evApplyPreset() | MUST be outside any `<details>` element — Phase 64 |
| evLoudnormEnabled | hidden input | evApplyPreset() reads unconditionally | MUST be outside any `<details>` element — Phase 64 |
| evAspectRatio | hidden input (or select) | startRenderFromEditor() line 2272 | ID must remain unchanged |
| evReframeStrategy | hidden input or select | startRenderFromEditor() lines 2328-2330 | ID must remain unchanged |
| evMinPart | number input | startRenderFromEditor() line 2274 | ID must remain unchanged |
| evMaxPart | number input | startRenderFromEditor() line 2275 | ID must remain unchanged |
| evFrameScaleY | hidden input | startRenderFromEditor() line 2305 | Value must be 106, never expose |
| evPlaybackSpeed | hidden input | startRenderFromEditor() line 2273 | Value must be 1.07, never expose |
| evPartOrder | hidden input/select | startRenderFromEditor() line 2304 | Default 'viral' |
| qsStructureBias | hidden input | startRenderFromEditor() line 2464 | Written by Optimize For and AI Clip Selection |
| evCleanupTemp | hidden checkbox | startRenderFromEditor() line 2331 | Must be checked (true) |
| evMaxExportParts | number input | startRenderFromEditor() (clips count) | ID unchanged after moving to Edit tab |

### 3.4 Runtime Trigger Migration

The current `setInspectorTab()` function fires side effects when specific tabs activate. After removing three tabs from the tab bar, these triggers must be relocated:

**EditorAudioRuntime.onTabActivate()**
- Current: fires when 'audio' tab is entered
- After: fires on Edit tab entry (tab 'mode' activated)
- Implementation: add to `if (activeTab === 'mode')` branch in setInspectorTab()
- Risk: if EditorAudioRuntime performs lazy initialization, firing on every Edit tab entry is acceptable. If it resets user state, it must only fire once per session or on specific Audio Advanced section expand.
- Safe approach: fire on Edit tab entry and on Audio Advanced `<details>` `toggle` event.

**EditorTextRuntime.onTabActivate()**
- Current: fires when 'text' tab is entered; also conditionally opens text-layers group
- After: the text-layers group auto-open should NOT happen on Edit tab entry (too aggressive)
- Implementation: fire EditorTextRuntime.onTabActivate() on Narration section expand in Edit Advanced
- The auto-open of text-layers should only happen when creator explicitly opens Text Layers in Captions Advanced

**EditorPerformanceRuntime.onTabActivate() / onTabDeactivate()**
- Current: fires when 'performance' (Export) tab is entered/exited
- After: Export tab remains as 'performance' — this trigger is unchanged
- BUT: Editor Performance section moves to Edit Advanced. If EditorPerformanceRuntime manages filmstrip/waveform rendering that depends on being "active," the trigger may need to also fire when Edit Advanced Performance section expands.
- Safe approach: keep existing Export tab trigger for basic init; add Advanced section `toggle` event for Performance sub-features.

**validTabs array update:**
```javascript
// Current (editor-view.js, setInspectorTab):
const validTabs = ['mode', 'subtitle', 'text', 'audio', 'performance', 'ai'];

// After:
const validTabs = ['mode', 'subtitle', 'performance'];
// Add redirect for legacy calls:
// if (['text', 'audio', 'ai'].includes(tab)) tab = 'mode';
```

---

## 4. Final Captions Tab Implementation

### 4.1 Subtitle Flow

```
TAB 2 — Captions (data-insp-panel="subtitle")
────────────────────────────────────────────────────────
[1] SUBTITLE ON/OFF
    [ ON ●──────────── ]   toggle (evAddSubtitle)
    Default: ON (checked)

[2] ↓ ALL CONTROLS BELOW HIDDEN WHEN TOGGLE IS OFF
    JS: toggle OFF → add hidden class to all sibling sections below
    JS: toggle ON  → remove hidden class

[3] SUBTITLE STYLE
    [Viral — Fast TikTok/Reels captions ▾]  (evSubStyle dropdown)
    Options: Viral | Karaoke | Bold Cap | Boxed | Clean
    Default: Karaoke (current default)

[4] POSITION
    [Bottom ✓]  [Middle]  [Top]
    Writes to evSubPos (ID unchanged):
      Bottom → 15  (calibrated bottom value, matches current default)
      Middle → 50
      Top    → 85
    Note: evSubPos must remain in DOM. Button-to-value mapping must match
    what startRenderFromEditor() expects at line 2250 (evSubPos.value).

[5] TEXT LAYER
    When no layers: show "+ Add Text Layer" link → opens layer creation flow
    When layers exist: show "N text layers" (expandable list)
    Collapsed by default; expand on click
    EditorTextRuntime.onTabActivate() fires when this section expands

[6] FIX SUBS (CONDITIONAL)
    [✦ Fix Subs — Let AI correct subtitle errors]
    Conditional visibility plan:
      → If confidence signal available: show when confidence < threshold
      → If no confidence signal: SHOW ALWAYS (fallback — see 4.3)

[7] LIVE PREVIEW CALLOUT
    Static text in Captions tab: "↑ Watch your video on the left for live preview"
    Small, muted. Replaces static inspector preview. Not a control.
    evSubOverlay (live overlay on video frame) continues operating normally.

[▸ Advanced]
    └─ Size:           [──────●──────] 46px  (evSubSize)
    └─ Color [  ]      Highlight [  ]  (evSubColor, evSubHighlight)
    └─ Font:           [Bungee (Viral 🔥) ▾]  (evSubFont)
    └─ Outline:        [──●──] 3px  (evSubOutline)
    └─ Horizontal Pos: [────●──────] 50%  (evSubPosX — MUST stay in DOM at 50)
    └─ Translate:      [ ]  → [target language ▾]  (evSubTranslate)
    └─ Add Text Layer: [+ Add Layer]  / [layer list if layers exist]
```

### 4.2 Subtitle ON/OFF Conditional Logic

When Subtitle toggle is OFF, all subtitle controls must hide AND the payload must still send correct defaults (not undefined).

```javascript
// On subtitle toggle change:
function onSubtitleToggle(isOn) {
  const sections = ['sub-style-section', 'sub-position-section', 
                    'sub-textlayer-section', 'sub-fixsubs-section',
                    'sub-advanced-section'];
  sections.forEach(id => {
    document.getElementById(id).style.display = isOn ? '' : 'none';
  });
  // Note: evSubStyle, evSubPos, evSubColor etc. remain in DOM even when hidden
  // startRenderFromEditor() reads them regardless of visibility
  // Their values are unchanged — they just aren't visible when subtitles are OFF
  // The payload field add_subtitle is false when toggle is OFF, so style values
  // are sent but the backend ignores them — no silent regression.
}
```

Hidden subtitle control IDs that must remain in DOM (still read by payload builder):
- evSubStyle (line 2239)
- evSubSize (line 2236)
- evSubPos (line 2250)
- evSubPosX (line 2250 — must be 50)
- evSubColor (line 2242)
- evSubHighlight (line 2244)
- evSubOutline (line 2234)
- evSubFont (line 2232)
- evSubtitleEmphasis (line 2467 — hidden input, default 'balanced')

### 4.3 Fix Subs Conditional Display

**The challenge:** "Show only when subtitle confidence is low" requires a confidence score. The subtitle confidence is generated during the render process (Whisper transcription), not during prepare-source. At render-setup time, no confidence score exists yet.

**Implementation paths:**

**Path A (Recommended P1): Show Always**
- Fix Subs always visible when Subtitles are ON
- Zero implementation complexity
- Creator who doesn't need it ignores the button
- Creator who gets bad subtitles (which is common, especially non-English) has immediate access
- This matches UX1F recommendation and is the lower-risk option

**Path B (P2): Conditional on Post-Render Data**
- After render completes, check subtitle confidence in render output
- If low-confidence clips found → surface Fix Subs in Review Queue view
- Not in the editor setup flow at all — belongs with review, not with setup
- Requires backend to expose per-clip subtitle confidence in render response

**Path C: Not feasible for render-setup flow**
- Confidence signal before render doesn't exist
- Cannot show conditional without the signal

**Recommendation:** Implement Path A (always visible) for P1. Evaluate Path B as a post-render UX enhancement in a future phase. Do not block the simplified editor on a signal that doesn't exist at render-setup time.

### 4.4 Static Preview Removal Impact

The static "Preview subtitle" text element in the Subtitles inspector will be removed. No functional payload impact — it was a display-only element.

The live subtitle overlay (`evSubOverlay`) on the video frame is the correct preview. It already renders subtitles in real time with current style/size/color/position. The only change: add a callout label in the Captions tab pointing creators to look at the video frame.

Verify after implementation:
- `evSubOverlay` position CSS is not relative to the inspector panel position
- Removing the static preview element doesn't affect any JS that reads it

---

## 5. Final Export Tab Implementation

### 5.1 Optimize For — Conditional Logic

"Optimize For" replaces the old Platform QS Bar pills. It is conditional: only appears when the Frame Ratio requires a platform decision.

```
Frame Ratio = 16:9 selected:
  → Optimize For: HIDDEN
  → Auto-write: evTargetPlatform.value = 'youtube_shorts'
  → Auto-write: qsStructureBias.value = 'balanced'
  → Display note (small, muted): "Optimized for YouTube Shorts"

Frame Ratio = 9:16 selected:
  → Optimize For: VISIBLE
  → Options: [TikTok ✓]  [Reels]  [Shorts]
  → TikTok selected (default for 9:16):
      evTargetPlatform.value = 'tiktok'
      qsStructureBias.value = 'hook'
  → Reels selected:
      evTargetPlatform.value = 'instagram_reels'
      qsStructureBias.value = 'story'
  → Shorts selected (vertical YouTube):
      evTargetPlatform.value = 'youtube_shorts'
      qsStructureBias.value = 'balanced'

Frame Ratio = 1:1 selected:
  → Optimize For: VISIBLE (optional sub-choice)
  → Options: [Instagram Feed ✓]  [Facebook]
  → Instagram Feed selected (default):
      evTargetPlatform.value = 'instagram_reels'   ← nearest available platform value
      qsStructureBias.value = 'balanced'
  → Facebook selected:
      evTargetPlatform.value = 'instagram_reels'   ← same until 'facebook' platform exists
      qsStructureBias.value = 'balanced'

Frame Ratio = 3:4 selected:
  → Optimize For: VISIBLE
  → Options: [Instagram Feed ✓]  [Reels]
  → Same mapping as 1:1 above
```

**Critical implementation rule:** Optimize For selection must ONLY write `evTargetPlatform` and `qsStructureBias`. It must NOT write `evAspectRatio`. Frame Ratio (in Edit tab) is the creator's format choice. Optimize For is AI tuning only.

**Decoupling from evQsSet():** The current QS Bar calls `evQsSet(group, val)` which writes both `evAspectRatio` AND `evTargetPlatform` for the Platform group. This coupling must be broken:
- Frame Ratio buttons in Edit tab → write only `evAspectRatio`
- Optimize For buttons in Export tab → write only `evTargetPlatform` + `qsStructureBias`
- `evQsSet()` may need a refactored path or the new buttons bypass it entirely via direct DOM writes

**qsStructureBias dirty flag:** If creator manually set AI Clip Selection (in Edit Advanced), Optimize For selection should NOT overwrite it:
```javascript
function onOptimizeForSelected(platform) {
  document.getElementById('evTargetPlatform').value = platform;
  
  const biasEl = document.getElementById('qsStructureBias');
  if (biasEl && biasEl.dataset.manuallySet !== '1') {
    // Only auto-write if creator hasn't manually overridden
    const biasMap = { tiktok: 'hook', instagram_reels: 'story', youtube_shorts: 'balanced' };
    biasEl.value = biasMap[platform] || 'balanced';
  }
}
```

### 5.2 FPS Logic

```
TAB 3 — Export (data-insp-panel="performance") — FPS section
────────────────────────────────────────────────────────────

FPS:
[Auto (Recommended) ✓]  [30 FPS]  [60 FPS]

Auto behavior:
  Reads source FPS from session data: _ev.sourceFps (or equivalent field from prepare-source)
  Calculates nearest standard FPS:
    sourceFps >= 55  → output 60 fps
    sourceFps >= 27  → output 30 fps
    sourceFps >= 20  → output 24 fps
    else             → output 30 fps (safe fallback)
  Writes calculated value to evOutputFps

Examples:
  29.97 source → Auto writes 30
  59.94 source → Auto writes 60
  23.976 source → Auto writes 24
  25.0 (PAL) source → Auto writes 30
  60.0 source → Auto writes 60

30 FPS override:
  evOutputFps.value = 30
  Use case: file size reduction, older platform compatibility

60 FPS override:
  evOutputFps.value = 60
  Use case: explicit smooth motion requirement regardless of source

Implementation note: Source FPS must be available in _ev after prepare-source.
  Verify: what field does prepare-source return for source video FPS?
  Likely: _ev.sourceFps or session.source_fps from prepare-source response.
  If not available: Auto defaults to 60fps (current default behavior — no regression).
```

### 5.3 GPU Behavior

GPU (encoder device) is auto-managed. Creator never sees this control in the standard flow.

```
DEFAULT: evRenderDevice.value = 'auto'
AUTO BEHAVIOR: GPU if available, CPU if not (existing backend logic unchanged)

Export Advanced → "Performance":
  Device: [Auto ▾]  (manual override for hardware issues)
  Options: Auto | CPU only | NVIDIA GPU | AMD GPU | Apple Silicon

This is the only control in Export Advanced. Performance section is the
complete Export Advanced content.
```

### 5.4 Quality — Hidden Default Behavior

```
HIDDEN DEFAULT: evRenderProfile.value = 'balanced'
  'balanced' produces good output for all platforms with reasonable encode time

Export Advanced:
  Quality: [Fast Draft]  [Balanced ✓]  [High Quality]  [Best]
  When visible: creator can select for specific use case
    Fast Draft: quick review render, lower quality
    Balanced: standard (default)
    High Quality: final publish
    Best: archival / commercial

evRenderProfile input must remain in DOM regardless of whether
  Quality selector is visible (payload builder reads it at line 2314).
```

### 5.5 Export Tab Final Structure

```
TAB 3 — Export (data-insp-panel="performance")
────────────────────────────────────────────────────────
[CONDITIONAL] OPTIMIZE FOR
  (only visible when Frame Ratio ≠ 16:9)
  Label: "Optimize For"
  Subtext: "Sets AI clip priority and pacing"
  16:9: [hidden — "Optimized for YouTube Shorts" note only]
  9:16: [TikTok ✓]  [Reels]  [Shorts]
  1:1:  [Instagram Feed ✓]  [Facebook]
  3:4:  [Instagram Feed ✓]  [Reels]

FPS
  [Auto (Recommended) ✓]  [30 FPS]  [60 FPS]
  "Auto matches your source video"

[▸ Advanced]
  └─ Quality: [Fast Draft]  [Balanced ✓]  [High Quality]  [Best]
  └─ Performance:
       Device: [Auto ▾]  (evRenderDevice)
       [Editor Performance section: health banner + toggles]
       (edPerfHealthBanner, edPerfHoverPreview, edPerfFilmstrip, edPerfWaveform)

NOTE: No standalone Render button in Export tab.
Render button stays in Global Footer (see Section — Global Footer).
```

---

## 6. Hidden Default Table

Every control that disappears from the visible UI and what the render produces automatically.

### 6.1 Always-Hidden Pipeline Parameters (Never in Any UI)

| Control | DOM Input | Payload Field | Hidden Default | Why Safe |
|---|---|---|---|---|
| Zoom | evFrameScaleY (value=106) | frame_scale_y | 106% vertical scale | Calibrated; creator should never change; edge artifacts prevented |
| Playback speed | evPlaybackSpeed (value=1.07) | playback_speed | 1.07x (platform delta applied on top) | Research-calibrated; platform adjusts automatically |
| Loudness normalization | evLoudnormEnabled (value="1") | loudnorm_enabled | Always ON | Platform audio standards; off = risk of rejected/muted content |
| Temp file cleanup | evCleanupTemp (checked) | cleanup_temp_files | true | Always correct; disk cleanup |
| Subtitle X position | evSubPosX (value=50) | sub_x_percent | 50% (centered) | Correct for 95%+ of content; Advanced if needed |
| Subtitle emphasis | evSubtitleEmphasis (value='balanced') | subtitle_emphasis | 'balanced' | Standard sizing; variant feature only |

**CRITICAL:** evEffectPreset and evLoudnormEnabled must remain in DOM and OUTSIDE any `<details>` element. This constraint (Phase 64) applies even if they are not visible in any UI section.

### 6.2 Feature Defaults (All Off — Hidden in Advanced)

| Feature | Payload Fields | Hidden Default | Creator Gets |
|---|---|---|---|
| BGM | reup_bgm_enable, reup_bgm_path, reup_bgm_gain | OFF | No background music |
| AI Narration | voice_enabled, voice_source, voice_language, voice_gender, voice_rate, voice_text | OFF | No voice synthesis |
| Subtitle Translation | subtitle_translate_enabled, subtitle_target_language | OFF | Subtitles in source language |
| Reup Mode | reup_mode, reup_overlay_enable, effect_preset override | OFF | Standard render, no overlay |
| Multi-variant | multi_variant | OFF | Single render, single style |
| CTA | cta_enabled, cta_type | OFF | No call-to-action overlay |
| Title Overlay | add_title_overlay, title_overlay_text | OFF | No title card |
| Creator Assets | asset_logo_path, asset_intro_path, asset_outro_path | All null | No branding overlays |
| Market & Target | target_market, hook_apply_enabled, combined_scoring_enabled | All off | Standard clip scoring, no regional bias |
| Batch Mode | batch_mode (implied by URL list) | OFF | Single source render |

### 6.3 Auto-Driven Behavior (Previously Required Creator Decision)

| Control | Payload Field | Auto Behavior | Trigger |
|---|---|---|---|
| AI Clip Selection | structure_bias (via qsStructureBias) | TikTok→'hook', Reels→'story', YouTube→'balanced' | Optimize For selection |
| Reframe default | evReframeStrategy | 16:9→'fast_center', others→'subject' | Frame Ratio selection |
| Platform target | target_platform (via evTargetPlatform) | 16:9→'youtube_shorts', 9:16 shows sub-choice | Frame Ratio selection |
| Output FPS | output_fps (via evOutputFps) | Calculated from source FPS | FPS Auto selection |

### 6.4 Render Quality Defaults

| Control | Payload Field | Hidden Default | Creator Impact |
|---|---|---|---|
| Render quality | render_profile | 'balanced' | Good quality, reasonable encode time |
| Encoder mode | encoder_mode | 'auto' | GPU if available, CPU if not |
| Part ordering | part_order | 'viral' (best-scored clips first) | Best clips in output |

### 6.5 Platform Encoding Defaults (When Optimize For Is Auto-Hidden)

For 16:9 content where Optimize For is hidden:

| Invisible Setting | Auto Value | Effect on Render |
|---|---|---|
| evTargetPlatform | 'youtube_shorts' | No speed delta, no hook bonus — correct for YouTube |
| qsStructureBias | 'balanced' | Equal weight hook and narrative clips |
| Playback speed | 1.07x (no platform delta for YouTube) | Natural pace for YouTube |

---

## 7. Extra Reduction Pass

Challenge every remaining visible control. Can it still be removed without hurting render quality?

### 7.1 EDIT Tab Controls

**Can Trim be hidden?**
NO. Trim defines which portion of source footage the AI processes. A 40-minute lecture where the creator wants clips from minutes 5–25 cannot be automatically segmented. Full-source processing produces clips from segments the creator didn't intend. Must remain visible.

**Can Video Style be hidden?**
NO. Style is brand identity — it sets the evEffectPreset via evApplyPreset(), which changes the visual energy and color treatment of every clip. Default 'story_clean_01' is not wrong but is not any creator's actual brand. Must remain visible.

**Can Frame Ratio be hidden?**
NO. Wrong format = completely wrong output shape. Every clip is wrong. Must remain visible. No safe universal default.

**Can Reframe be hidden? (Given new locked model showing it)**
Per the locked model, Reframe is creator-controlled and must remain visible. This differs from UX1F which recommended hiding it with auto-default. The locked model is correct: when aspect ratio conversion occurs, creator needs to confirm the framing behavior — AI suggesting "Follow Face" is good but creator may have symmetrical composition that needs Center. The visible control with smart suggestion balances both concerns. Keep visible.

**Can Clip Duration be hidden?**
NO. This is the single most impactful parameter for AI clip discovery. Wrong duration range = no clips found. Hiding with wrong defaults is the #1 cause of render failures for new creators (UX1A §3.5). Must remain visible.

**Can Output Count be hidden?**
BORDERLINE. Default 6 clips is correct for a typical content session. Creator who wants 1 test clip or 12 clips for a full campaign cannot adjust without this control. However: getting 6 clips when you wanted 3 is non-fatal (delete the extras). Getting 6 clips when you wanted 12 requires a re-render.
**Verdict: Keep visible.** Low cognitive cost (one number). High annoyance when wrong.

### 7.2 CAPTIONS Tab Controls

**Can Subtitle Style be hidden?**
NO. Style is brand identity for subtitles. Default Karaoke is a reasonable choice but many creators have a signature subtitle look. A creator who relies on "Bold Cap" for their podcast style gets the wrong look silently. Must remain visible.

**Can Position be simplified further?**
It's already the minimum: 3 options (Bottom / Middle / Top). Could become 2 options (Bottom / Top) but Middle is a legitimate choice for certain content types (e.g., content with bottom graphics). 3 buttons is low cognitive cost. Keep as 3.

**Can Text Layer be removed entirely from Captions tab?**
BORDERLINE. Text layers are an opt-in feature used by creators who want persistent branding text on clips. Removing from Captions Advanced (even the "+ Add Layer" entry) would make the feature undiscoverable.
**Verdict: Keep in Captions Advanced.** One entry point ("+ Add Layer"). No cognitive cost when not in use.

**Can Fix Subs be removed?**
NO (if shown always). Fix Subs is a one-tap action that corrects auto-subtitle errors. For creators with non-English audio or technical terminology, subtitle errors are common. Removing Fix Subs means creators with poor auto-subtitles have no correction mechanism in the editor flow.
**Verdict: Show always** (Path A from Section 4.3). The conditional-on-confidence approach is premature given no confidence signal exists at render-setup time.

### 7.3 EXPORT Tab Controls

**Can Optimize For be hidden for all creators?**
NO for 9:16 creators. The platform encoding difference between TikTok (+8% speed, +6 hook bonus) and Reels (-6% speed) is real and visible in output. A TikTok creator whose content gets Reels speed will notice clips feel sluggish. Must show when 9:16 is selected.
16:9 creators: correct to hide (YouTube Shorts is the only horizontal-format option in the current platform list).

**Can FPS be hidden?**
BORDERLINE. Auto mode (source-matched) is the correct default for nearly all content. 30fps or 60fps override is needed when:
- Creator wants file size reduction (30fps for archival)
- Creator has 60fps source but wants 30fps output for style reasons
- Creator has 24fps film content
These are real use cases but edge cases.
**Verdict: Keep visible — 3 options.** The Auto button makes the common case zero-friction. Override options are there for real edge cases. FPS mismatch (60fps source → 30fps output) can create visible stutter that creator cannot diagnose without knowing the control exists. Low cost to show.

**Can GPU/Device be moved out of Export Advanced to a Settings panel?**
YES. Device selection is a one-time machine-specific configuration, not a per-render decision. It belongs in a global Settings view, not in the Export Advanced section of every render. However, moving it out of the editor entirely is outside the current scope (requires Settings view to exist).
**Verdict: Keep in Export Advanced for now.** Mark for future relocation to Settings.

**Anything hidden that should return to visible UI?**
After reviewing the complete hidden list (Section 6), one control deserves reconsideration:

**Part Order** (viral vs. timeline) — currently hidden in Edit Advanced. Creators making tutorial series or ordered training content need timeline order for clips to make sense to viewers. 'Viral' (best-scored clips first) will order content in the wrong sequence for sequential content.
**Verdict: Keep hidden in Edit Advanced.** 'viral' is correct for 95%+ of short-form content. Tutorial/training creators are power users who will find it in Advanced. Not a primary-view concern.

**Subtitle Color / Highlight** — moved to Captions Advanced in this locked model. UX1F recommended keeping visible. The question: how many creators have custom brand colors?
**Verdict: Accept Advanced placement for now.** White/Yellow defaults are readable and standard. Creator who needs brand colors will look in Captions Advanced. If user feedback shows color is frequently sought, it surfaces to primary view in a future phase.

### 7.4 Summary — Reduction Pass Verdict

No visible controls should be removed beyond what the locked model specifies. Every remaining visible control survives the honest challenge:

| Tab | Control | Challenge Result |
|---|---|---|
| Edit | Trim | KEEP — AI cannot infer source segment intent |
| Edit | Video Style | KEEP — Brand identity; must be creator-confirmed |
| Edit | Frame Ratio | KEEP — Wrong format = unusable output |
| Edit | Reframe | KEEP — Creator confirms framing for aspect ratio conversion |
| Edit | Clip Duration | KEEP — #1 cause of "no clips found" if wrong |
| Edit | Output Count | KEEP — Non-fatal but annoying if wrong |
| Captions | Subtitle ON/OFF | KEEP — Creator publishing decision |
| Captions | Subtitle Style | KEEP — Brand identity |
| Captions | Position | KEEP — 3 options, near-zero cognitive cost |
| Captions | Text Layer | KEEP in Advanced — must be discoverable |
| Captions | Fix Subs | KEEP always visible — no confidence signal at render-setup time |
| Export | Optimize For | KEEP conditional — platform encoding matters for TikTok/Reels |
| Export | FPS | KEEP — mismatch causes visible artifacts; Auto makes it zero-friction |

---

## 8. Safe Implementation Order

### P0 — Zero Functional Risk (Label and Text Changes Only)

No JS changes. No DOM restructure. No runtime behavior changes. Pure text updates.

1. Tab button text: "Story" → "Edit", "Subtitles" → "Captions", "Export" stays "Export"
   - `data-insp-tab` values do NOT change (mode/subtitle/performance)
   - Only the visible text label changes

2. Field label updates:
   - "Min clip (s)" → "Shortest"
   - "Max clip (s)" → "Longest"
   - "Output Profile" → "Render Quality" (in Advanced)
   - "Reframe Mode" → "Reframe" (section heading in Edit tab)
   - "Max clips" → "Clips" or "Output Count"

3. Add tooltip attributes (title="..."):
   - Reframe buttons: describe each option in one sentence
   - FPS options: "Auto matches your source video frame rate"
   - Style cards: ensure existing tooltips are clear

4. Add Captions tab callout:
   - Small text below Fix Subs: "↑ Your video on the left shows live subtitle preview"
   - Replace or remove "Preview subtitle" static text element

5. Add Optimize For descriptive subtext:
   - Under Optimize For section: "Sets AI clip priority and pacing for your platform"

**Testing P0:** Visual review only. No functional testing required.

---

### P1 — Structural Moves (Low-Medium Risk — No New JS Behavior)

DOM restructuring and section moves. Existing JS still fires; IDs unchanged.

1. **Remove tab buttons from tab bar:** Remove `<button data-insp-tab="text">`, `<button data-insp-tab="audio">`, `<button data-insp-tab="ai">` from the tab bar HTML. Tab panels (data-insp-panel sections) remain in DOM but are no longer accessible via tab buttons.

2. **Update validTabs array:** `['mode','subtitle','performance']` — add redirect for legacy calls.

3. **Move Edit History and Creator Memory to removed (not Advanced):** Delete or comment out these sections in mode panel. No IDs from these are read by payload builder.

4. **Move AI Chat deeply into Edit Advanced:** Move conversational panel to bottom of Edit Advanced section. Collapsed by default.

5. **Move Batch Queue (bqSection) into Edit Advanced:** bqSection moves from Export panel to Edit Advanced panel. ID unchanged. BatchQueue module finds it by ID — verify no positional assumptions.

6. **Move Editor Performance into Edit Advanced:** Move edPerfHealthBanner, edPerfHoverPreview, edPerfFilmstrip, edPerfWaveform sections to Edit Advanced. IDs unchanged. EditorPerformanceRuntime trigger update: see Section 3.4.

7. **Move Market & Target into Edit Advanced:** Moves from Export top area. mvMarket, mvAutoBestClips, mvKeywordHighlight, mvBestExportEnabled IDs unchanged.

8. **Move Quick Presets into Edit Advanced:** Moves from Export top area.

9. **Remove static subtitle preview element** from Captions/Subtitles tab. Add live-preview callout text.

10. **Move Subtitle Size, Color, Highlight, Font, Outline to Captions Advanced:** These inputs stay in DOM but their visible UI elements move into `<details>` Advanced section. evSubSize, evSubColor, evSubHighlight, evSubFont, evSubOutline IDs unchanged and still read by payload builder.

11. **Move X Pos slider to Captions Advanced as "Horizontal Position":** evSubPosX hidden input must remain at value 50 in DOM outside the Advanced fold (to be safe), with the visible slider only in Advanced.

12. **Move Translate to Captions Advanced:** evSubTranslate — off by default, no change.

13. **Move Render Settings (Device) to Export Advanced as "Performance" section:** evRenderDevice — 'auto' default unchanged.

14. **Move Creator Presets bar (cpBar) to Footer:** Update CSS position. cpBar functions still find it by ID. Verify cpBar DOM-ready events fire correctly from footer position.

15. **Move Output Count (evMaxExportParts) from Export to Edit tab:** HTML reorder only. ID unchanged.

16. **Move Min/Max Duration (evMinPart, evMaxPart) from Advanced fold to primary Edit tab:** HTML reorder. Remove from `<details>` Advanced section. IDs unchanged.

17. **Add Subtitle ON/OFF conditional hide JS:** When toggle changes, hide/show subtitle style sections in Captions tab. Existing inputs remain in DOM.

18. **Add Position buttons (Bottom/Middle/Top):** Three buttons that write to evSubPos. The existing Y Pos slider moves to Captions Advanced (or is hidden entirely if position buttons fully replace it). evSubPos must remain in DOM.

**Testing P1:** 
- [ ] Verify all moved IDs still found by payload builder (startRenderFromEditor() passes)
- [ ] Verify evLoudnormEnabled and evEffectPreset are NOT inside any `<details>` element after restructuring
- [ ] Verify evSubPosX is at value 50 and accessible outside Advanced collapse
- [ ] Verify BatchQueue module still finds bqSection by ID
- [ ] Verify cpBar functions still work from footer position
- [ ] Verify subtitle controls hide correctly when toggle is OFF
- [ ] Verify Position buttons write correct values to evSubPos

---

### P2 — New Behavior (Medium Risk — New JS Required)

New JavaScript interactions. Each must be tested against specific failure cases.

1. **Frame Ratio buttons (replace evAspectRatio select in Edit tab):**
   - 4 buttons write to evAspectRatio by ID
   - On click: trigger Reframe default suggestion (Section 3.2)
   - On click: trigger Optimize For visibility update in Export tab
   - Must NOT write evTargetPlatform — that is Optimize For's responsibility

2. **Reframe default suggestion on Frame Ratio selection:**
   - 16:9 → auto-highlight Center button, write 'fast_center' to evReframeStrategy
   - Others → auto-highlight Follow Face button, write 'subject' to evReframeStrategy
   - Only auto-write if `evReframeStrategy.dataset.manuallySet !== '1'`
   - Manual Reframe click sets `dataset.manuallySet = '1'` and `dataset.manuallySet` persists until Frame Ratio changes (reset on ratio change)

3. **Optimize For conditional visibility:**
   - Frame Ratio button click → check ratio → show/hide Optimize For section
   - 16:9 selected → hide Optimize For, auto-write 'youtube_shorts' to evTargetPlatform, write 'balanced' to qsStructureBias
   - 9:16 selected → show Optimize For with [TikTok ✓] [Reels] [Shorts]
   - 1:1/3:4 selected → show Optimize For with Instagram Feed / Facebook options

4. **Optimize For selection → auto-write evTargetPlatform + qsStructureBias:**
   - Decoupled from evQsSet() — writes directly
   - Respects qsStructureBias dirty flag (Section 5.1)
   - Does NOT write evAspectRatio

5. **FPS Auto mode:**
   - Auto button selected → calculate from _ev.sourceFps (or equivalent)
   - Apply FPS calculation formula (Section 5.2)
   - Write result to evOutputFps
   - If sourceFps not available → write 60 (current default, no regression)

6. **EditorAudioRuntime trigger migration:**
   - Add trigger for Edit tab entry in setInspectorTab() 'mode' branch
   - Verify EditorAudioRuntime.onTabActivate() behavior with tab-entry trigger

7. **EditorTextRuntime trigger migration:**
   - Remove auto-open of text-layers group from tab entry
   - Fire EditorTextRuntime.onTabActivate() on Text Layer section expand in Captions Advanced

8. **EditorPerformanceRuntime trigger migration:**
   - Add `<details>` toggle event for Performance section in Edit Advanced
   - Verify filmstrip/waveform rendering still works

9. **QS Bar subtitle pill removal:**
   - Remove subtitle group from QS Bar
   - Verify evSyncQsBar() doesn't error on missing subtitle pill
   - Subtitle Style dropdown in Captions tab remains the single authoritative source

**Testing P2:**
- [ ] Frame Ratio → Reframe default: verify correct reframe mode written for each ratio
- [ ] Frame Ratio → Optimize For visibility: verify correct show/hide for all 4 ratios
- [ ] Reframe manual override: verify manuallySet flag persists through Platform change, resets on ratio change
- [ ] Optimize For → evTargetPlatform: verify correct value for TikTok/Reels/Shorts/Instagram
- [ ] Optimize For → qsStructureBias: verify correct value; verify dirty flag prevents overwrite
- [ ] FPS Auto: verify correct calculation for 29.97/59.94/23.976/25fps sources
- [ ] Subtitle toggle → conditional hide/show: all controls hide when OFF, all appear when ON
- [ ] evEffectPreset chain: Style card click → evApplyPreset() → evEffectPreset.value → payload.effect_preset — verify all 4 styles
- [ ] evLoudnormEnabled DOM position: outside all `<details>` elements
- [ ] evSubPosX value: 50 and accessible even with Advanced collapsed
- [ ] qsStructureBias DOM presence and value after Optimize For selection
- [ ] Platform encoding bias test: TikTok render should use speed_delta +0.08 in render_pipeline.py
- [ ] EditorAudioRuntime: no double-init on Edit tab re-entry

---

## 9. Definition of Done

The editor is finally simplified — without breaking workflow and without hurting render quality — when all of the following are true.

### 9.1 Visual / UX Verification

- [ ] Tab bar shows exactly 3 tabs: Edit | Captions | Export
- [ ] Edit tab shows: Trim, Style (4 cards), Frame Ratio (4 buttons), Reframe (4 options), Clip Duration (Shortest/Longest), Output Count, [▸ Advanced]
- [ ] Captions tab shows: Subtitle toggle, Style, Position (3 buttons), Text Layer entry, Fix Subs, live-preview callout, [▸ Advanced]
- [ ] Export tab shows: Optimize For (conditional), FPS (3 options), [▸ Advanced]
- [ ] Optimize For is hidden for 16:9 content; visible for 9:16/1:1/3:4 content
- [ ] When Subtitle toggle is OFF: all subtitle controls are invisible (but still in DOM)
- [ ] Footer: Creator Presets dropdown + Save + Start Render always visible
- [ ] No static subtitle preview element in Captions tab
- [ ] No Audio tab, no Words tab, no AI tab in tab bar

### 9.2 Creator Workflow Test

- [ ] New creator opens editor for a YouTube Shorts video (16:9 source)
  - Visible decisions: Trim + Style + Frame Ratio (1:1) + Reframe (auto-suggested) + Duration + Captions setup + no Optimize For (auto) + FPS Auto + Render
  - Total decisions made: ≤ 8
  - Time to first render: under 60 seconds without reading documentation

- [ ] Experienced TikTok creator opens editor for 9:16 content
  - Visible decisions: Trim + Style + Frame Ratio + Reframe (auto-suggested Follow Face) + Duration + Captions + Optimize For (TikTok selected) + FPS Auto + Render
  - Total decisions made: ≤ 10
  - Time to first render: under 60 seconds

### 9.3 Render Quality Verification

- [ ] Style card click → correct evEffectPreset value written for all 4 styles
  - Viral → effect_preset = 'viral_fast_01' (or equivalent viral preset string)
  - Cinematic → effect_preset = 'cinematic_color_01' (or equivalent)
  - Aggressive → effect_preset = 'aggressive_cut_01' (or equivalent)
  - Balanced → effect_preset = 'story_clean_01'
  - If no style selected: default 'story_clean_01' (fallback)

- [ ] TikTok render gets correct platform encoding:
  - target_platform = 'tiktok' when TikTok selected in Optimize For
  - speed_delta +0.08 applied in render_pipeline.py (existing behavior unchanged)
  - hook_sort_bonus +6 applied (existing behavior unchanged)

- [ ] YouTube 16:9 render auto-applies youtube_shorts platform (without creator input)

- [ ] Reframe mode correct for aspect ratio conversion:
  - 16:9 source → 9:16 output: payload.reframe_mode = 'subject', motion_aware_crop = true (unless Center manually selected)
  - 16:9 source → 16:9 output: payload.reframe_mode = 'center', motion_aware_crop = false

- [ ] FPS Auto: payload.output_fps matches nearest standard FPS to source
  - 29.97 source → output_fps = 30
  - 59.94 source → output_fps = 60

- [ ] Loudness normalization always on (payload.loudnorm_enabled = true for every render)

- [ ] Quality always Balanced by default (payload.render_profile = 'balanced' when no manual override)

- [ ] Zoom always 106% (payload.frame_scale_y = 106 for every render)

### 9.4 DOM Integrity Verification

- [ ] evEffectPreset: exists in DOM, value is set by Style card clicks, is OUTSIDE all `<details>` elements
- [ ] evLoudnormEnabled: exists in DOM, value is "1", is OUTSIDE all `<details>` elements
- [ ] evSubPosX: exists in DOM, value is 50
- [ ] qsStructureBias: exists in DOM, value is updated by Optimize For selection
- [ ] evTargetPlatform: exists in DOM, value is updated by Optimize For selection
- [ ] evAspectRatio: exists in DOM, value is updated by Frame Ratio buttons
- [ ] evReframeStrategy: exists in DOM, value is updated by Reframe buttons and Frame Ratio auto-suggestion
- [ ] evFrameScaleY: exists in DOM, value is 106
- [ ] evPlaybackSpeed: exists in DOM, value is 1.07
- [ ] evPartOrder: exists in DOM, default value 'viral'
- [ ] evCleanupTemp: exists in DOM, is checked (true)
- [ ] evMinPart, evMaxPart: exist in DOM, are number inputs, values reflect Clip Duration controls
- [ ] evMaxExportParts: exists in DOM after move to Edit tab
- [ ] bqSection: exists in DOM after move to Edit Advanced

### 9.5 Regression Test — What Must Not Break

- [ ] VideoLocal workflow: file picker → path stored → prepare-source → editor opens → render starts
  source_video_path, local_video_file_picker, manual_output_dir IDs unchanged
- [ ] Render payload builder (startRenderFromEditor()): produces valid payload for all control states
  Spot-check: aspect_ratio, min_part_sec, max_part_sec, target_platform, structure_bias,
  reframe_mode, motion_aware_crop, effect_preset, loudnorm_enabled, output_fps, frame_scale_y
- [ ] Creator Presets (cpBar): save and apply presets works from footer position
- [ ] QS Bar remaining functions: any non-Platform, non-Subtitle QS Bar interactions still work
- [ ] BatchQueue module: finds bqSection by ID, drag-drop file queue works
- [ ] mvHandleChange(), mvHandleAutoBestClips(): Market & Target in Edit Advanced still fires correctly
- [ ] evApplyOutputPreset(): Expert Preset in Edit Advanced still fires correctly
- [ ] evToggleAdvancedOutput(): Advanced fold toggle still works (edit and export Advanced sections)
- [ ] startRenderFromEditor() completes without JS errors for a standard render

---

*End of PHASE UX-1H — Final Locked Video Editor Implementation Plan*

*Total visible decisions after implementation:*
- *16:9 YouTube creator: ~8 decisions (no Optimize For, no Reframe needed for no-conversion)*
- *9:16 TikTok creator: ~10 decisions (Optimize For visible, Reframe auto-suggested)*
- *All creators: under the 10–12 target established in UX1E*

*Implementation note: UX1G_R2 was referenced in the phase brief but does not exist in the repository. This document supersedes any prior intermediate planning. The locked structure in this phase's spec is the authoritative source.*

*Next step: P0 implementation — tab label changes and field renames. Zero functional risk. Can ship immediately without code review escalation.*
