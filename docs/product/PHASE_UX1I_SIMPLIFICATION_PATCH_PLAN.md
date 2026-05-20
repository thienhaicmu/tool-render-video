# PHASE UX-1I — Video Editor Simplification Patch Plan

**Type:** Implementation patch plan — NOT redesign
**Date:** 2026-05-20
**Source:** Direct code trace — index.html lines 836–1601, editor-view.js lines 355–2520, editor-ai-sessions.js
**Target files:** `backend/static/index.html`, `backend/static/js/editor-view.js`, `backend/static/js/editor-ai-sessions.js`
**UI direction:** LOCKED — no redesign, no new tabs, no new creator decisions

---

## 1. Executive Summary

### 1.1 What Exactly Changes

**Tab bar:** 6 tabs → 3 tabs. The Words, Audio, and AI tab buttons are removed. Their content either moves to Edit Advanced (Narration, BGM, Text Layers, AI Chat) or is removed from the primary UI (Edit History, Creator Memory, AI Edit Actions, Source Volume UI).

**Edit tab (data-insp-panel="mode"):** Gains six new visible sections — Frame Ratio buttons (replacing the hidden evAspectRatio select), Reframe buttons (replacing the hidden evReframeStrategy select in Render Settings), Clip Duration fields (moved from Export Advanced fold), Output Count (moved from Export tab), and a new "Video Style → evEffectPreset" write behavior. Loses: AI Edit Actions, Edit History, Creator Memory.

**Captions tab (data-insp-panel="subtitle"):** Gains Position buttons (Bottom/Middle/Top replacing Y Pos slider in primary view), removes the static subtitle preview element. Font/Size/Color/Highlight/Outline/X Pos/Translate move into a new `<details>` Advanced section. Text Layers (currently in Words tab) moves here.

**Export tab (data-insp-panel="performance"):** Gains "Optimize For" conditional section and upgraded FPS selector with Auto mode. Loses: Quick Presets section, Market & Target section, Creator Presets bar (moves to footer), QS Bar (Platform/Subtitle/Structure pills), Max clips, Advanced fold contents (Aspect Ratio, Min/Max clip, Multi-variant, CTA, Title Overlay, Creator Assets, Batch Mode). Render Settings (Device/FPS/Reframe) moves out entirely — FPS goes to visible Export, Device goes to Export Advanced, Reframe goes to Edit tab. Batch Queue, Editor Performance move out.

**evQsSet() decoupled:** Platform pill click in `evQsSet()` currently writes BOTH `evTargetPlatform` AND `evAspectRatio`. After simplification, the new Optimize For buttons write ONLY `evTargetPlatform` and `qsStructureBias`. Frame Ratio buttons write ONLY `evAspectRatio`. These two actions are fully decoupled.

### 1.2 What Complexity Disappears

| Removed from primary flow | Decisions gone |
|---|---|
| QS Bar (Platform / Subtitle / Structure pills) | 9 pill options |
| Quick Presets section (visible in Export) | 1 collapsed section header |
| Market & Target section | 1 collapsed section header + 4 toggles |
| Creator Presets bar (moves to footer, not removed) | 0 decisions — just relocated |
| Export Advanced fold (Aspect Ratio, Profile, Min/Max, multi-variant, CTA, Title Overlay, Assets, Batch) | 10+ decisions in Advanced |
| Render Settings group (Device, FPS, Reframe) | 3 controls → Device hidden, FPS stays visible, Reframe moves to Edit |
| Editor Performance section (always visible in Export) | 1 section + 3 toggles |
| Audio tab (Source volume, BGM, Loudness normalize) | 3 controls hidden |
| Words tab (AI Narration, Text Layers) | 2 sections relocated |
| AI tab (conversational panel) | 1 entire tab |
| Edit History, Creator Memory, AI Edit Actions | 3 collapsed sections removed |

### 1.3 Why Render Quality Remains Safe

Every hidden control has a DOM input that remains in place and is still read by `startRenderFromEditor()`. No payload field is broken by the visual restructure:

- `evEffectPreset` — stays in DOM outside `<details>` (Phase 64 constraint honored)
- `evLoudnormEnabled` — stays in DOM outside `<details>` (Phase 64 constraint honored)
- `evAspectRatio` — written by Frame Ratio buttons (same ID, same payload read at line 2272)
- `evReframeStrategy` — written by Reframe buttons (same ID, same payload read at lines 2328-2330)
- `evOutputFps` — written by FPS selector (same ID, same payload read at line 2298)
- `evTargetPlatform` — written by Optimize For buttons (same ID, same payload read at line 2301)
- `qsStructureBias` — written by Optimize For auto-write (same ID, same payload read at line 2464)
- All other inputs in `evEditorCompat` (evPlaybackSpeed, evFrameScaleY, evPartOrder, evReupMode, evCleanupTemp) — untouched

---

## 2. File-Level Patch Plan

---

```
FILE:
backend/static/index.html

CHANGE:
Tab bar — remove 3 tab buttons

CURRENT (lines 837–842):
<button class="insp-tab active" data-insp-tab="mode"        onclick="setInspectorTab('mode')">Story</button>
<button class="insp-tab"        data-insp-tab="subtitle"    onclick="setInspectorTab('subtitle')">Subtitles</button>
<button class="insp-tab"        data-insp-tab="text"        onclick="setInspectorTab('text')">Words</button>
<button class="insp-tab"        data-insp-tab="audio"       onclick="setInspectorTab('audio')">Audio</button>
<button class="insp-tab"        data-insp-tab="performance" onclick="setInspectorTab('performance')">Export</button>
<button class="insp-tab"        data-insp-tab="ai"          onclick="setInspectorTab('ai')">AI</button>

FINAL:
<button class="insp-tab active" data-insp-tab="mode"        onclick="setInspectorTab('mode')">Edit</button>
<button class="insp-tab"        data-insp-tab="subtitle"    onclick="setInspectorTab('subtitle')">Captions</button>
<button class="insp-tab"        data-insp-tab="performance" onclick="setInspectorTab('performance')">Export</button>

WHY:
Words, Audio, AI tab buttons removed. Display text updated.
data-insp-tab values unchanged — tab system still works.

RISK: Low — only removes button elements and renames display text.
NOTE: data-insp-panel="text", "audio", "ai" sections remain in DOM but become
unreachable via tab bar (they will be moved to Advanced sections — see separate patches).
```

---

```
FILE:
backend/static/js/editor-view.js

CHANGE:
setInspectorTab() — update validTabs and add runtime redirects + trigger migrations

CURRENT (lines 2637–2638):
function setInspectorTab(tab) {
  const validTabs = ['mode', 'subtitle', 'text', 'audio', 'performance', 'ai'];

CURRENT tabTitles (lines 2638–2645):
  const tabTitles = {
    mode:        'Story',
    subtitle:    'Subtitles',
    text:        'Words',
    audio:       'Audio',
    performance: 'Export',
    ai:          'AI',
  };

CURRENT triggers (lines 2664–2678):
  if (activeTab === 'audio') {
    evSetInspGroupOpen('audio', true);
    if (typeof EditorAudioRuntime !== 'undefined') EditorAudioRuntime.onTabActivate();
  }
  if (activeTab === 'performance') {
    evSetInspGroupOpen('performance', true);
    if (typeof EditorPerformanceRuntime !== 'undefined') EditorPerformanceRuntime.onTabActivate();
  } else {
    if (typeof EditorPerformanceRuntime !== 'undefined') EditorPerformanceRuntime.onTabDeactivate();
  }
  if (activeTab === 'text') {
    if (typeof EditorTextRuntime !== 'undefined') EditorTextRuntime.onTabActivate();
    const hasLayers = typeof _ev !== 'undefined' && Array.isArray(_ev.textLayers) && _ev.textLayers.length > 0;
    evSetInspGroupOpen('text-layers', hasLayers);
  }

FINAL:
function setInspectorTab(tab) {
  // Redirect removed tabs to Edit
  if (['text', 'audio', 'ai'].includes(tab)) tab = 'mode';
  const validTabs = ['mode', 'subtitle', 'performance'];
  const tabTitles = {
    mode:        'Edit',
    subtitle:    'Captions',
    performance: 'Export',
  };
  // ... rest of function unchanged until triggers ...

  if (activeTab === 'mode') {
    // Audio init fires on Edit tab entry (was: on 'audio' tab entry)
    if (typeof EditorAudioRuntime !== 'undefined') EditorAudioRuntime.onTabActivate();
    // Text init fires on Edit tab entry (was: on 'text' tab entry)
    // Auto-open of text-layers group removed — only opens in Captions Advanced on explicit user action
    if (typeof EditorTextRuntime !== 'undefined') EditorTextRuntime.onTabActivate();
  }
  if (activeTab === 'performance') {
    evSetInspGroupOpen('performance', true);
    if (typeof EditorPerformanceRuntime !== 'undefined') EditorPerformanceRuntime.onTabActivate();
  } else {
    if (typeof EditorPerformanceRuntime !== 'undefined') EditorPerformanceRuntime.onTabDeactivate();
  }
  // 'text' and 'audio' triggers removed (both handled above under 'mode')
  // EditorState.setEditorState call unchanged

WHY:
Removes 3 tabs from routing. Migrates EditorAudioRuntime and EditorTextRuntime triggers
from removed tabs to Edit tab entry. Removes auto-open of text-layers group on tab switch
(was confusing when Words tab opened — should only expand when creator explicitly uses it
in Captions Advanced).

RISK: Medium
  - EditorAudioRuntime.onTabActivate() will now fire every time Edit tab is entered.
    Verify that repeated calls are safe (should be idempotent/lazy-init — confirm with
    editor-audio-runtime.js before shipping).
  - EditorTextRuntime.onTabActivate() same concern — verify idempotent.
  - EditorPerformanceRuntime triggers are unchanged — low risk.
```

---

```
FILE:
backend/static/js/editor-view.js

CHANGE:
evQsSet() — decouple Platform pill from Aspect Ratio write

CURRENT (lines 355–363):
function evQsSet(group, val) {
  if (group === 'platform') {
    const el = document.getElementById('evTargetPlatform');
    if (el) el.value = val;
    const ar = document.getElementById('evAspectRatio');
    if (ar) {
      ar.value = (val === 'tiktok' || val === 'instagram_reels') ? '9:16' : '3:4';
      if (typeof evUpdateAspectRatio === 'function') evUpdateAspectRatio();
    }
  }

FINAL:
function evQsSet(group, val) {
  if (group === 'platform') {
    const el = document.getElementById('evTargetPlatform');
    if (el) el.value = val;
    // REMOVED: evAspectRatio write — Frame Ratio is now set independently in Edit tab.
    // Platform (Optimize For) only sets target_platform and structure_bias.
    // Do NOT write evAspectRatio from here.
  }

WHY:
In the locked model, Frame Ratio (aspect ratio) is a creator-controlled Edit tab decision.
Platform (Optimize For in Export tab) is AI tuning only — it must NOT auto-change the
creator's explicit format choice. Decoupling these is the most critical functional change.

RISK: High (functionally significant)
  - The old QS Bar Platform pills (YouTube/TikTok/Reels) called evQsSet() and relied on
    the aspect ratio side-effect. After this change, the old Platform pills must not exist
    in the visible UI (they're removed by this patch). The new Optimize For buttons (added
    in index.html patch) bypass evQsSet() entirely and write evTargetPlatform directly.
  - evSyncQsBar() reads evTargetPlatform to highlight platform pills. After removing the
    QS Bar Platform pills from the DOM, evSyncQsBar() will iterate over zero platform pill
    elements — this is safe (querySelectorAll returns empty NodeList, forEach is no-op).
  - evApplyPreset() calls evApplyOutputPreset() which may call evQsSet() — check that
    preset apply functions don't rely on the aspect ratio side effect.
```

---

```
FILE:
backend/static/index.html

CHANGE:
evPresetSection (Quick Presets) — move evEffectPreset and evLoudnormEnabled to Edit tab panel,
move Quick Presets section to Edit Advanced

CURRENT (lines 947–986, data-insp-panel="performance"):
<div class="evSection evPresetSection ev-panel-card ev-option-panel" id="evPresetSection" data-insp-panel="performance">
  <details>
    <summary>Quick Presets (4)</summary>
    ...4 preset cards calling evApplyPreset()...
  </details>
  <input type="hidden" id="evEffectPreset" value="">
  <input type="hidden" id="evLoudnormEnabled" value="1">
</div>

FINAL:
(a) Move evEffectPreset and evLoudnormEnabled OUT of this section to be siblings of the
    QS Bar or directly in evEditorCompat, maintaining their position OUTSIDE any <details>:

  <!-- In the mode panel (Edit tab), OUTSIDE any <details> wrapper: -->
  <input type="hidden" id="evEffectPreset" value="">
  <input type="hidden" id="evLoudnormEnabled" value="1">

(b) Move the Quick Presets <details> section to Edit Advanced (data-insp-panel="mode")

WHY:
Phase 64 constraint: evEffectPreset and evLoudnormEnabled MUST remain outside any <details>
element. Currently they are outside the <details> but inside evPresetSection which is in
the performance panel. Moving them to be in the mode panel (Edit tab) where they are also
not inside <details> satisfies the constraint and keeps them accessible regardless of
which tab is active.

RISK: Critical — must verify evEffectPreset and evLoudnormEnabled are outside <details>
after move. Use browser devtools: document.getElementById('evEffectPreset').closest('details')
must return null after restructuring.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Add Frame Ratio buttons to Edit tab (replaces hidden evAspectRatio select in Advanced)

CURRENT:
evAspectRatio is a <select> inside qsAdvBody (Advanced fold in Export tab, lines 1097–1103):
  <select class="fieldInput" id="evAspectRatio" onchange="evUpdateAspectRatio()">
    <option value="3:4" selected>3:4 Vertical</option>
    <option value="9:16">9:16 TikTok</option>
    <option value="1:1">1:1 Square</option>
  </select>

FINAL:
Replace the <select> with a hidden <input> + add visible Frame Ratio button row to Edit tab
(data-insp-panel="mode"):

  <!-- Visible in Edit tab — replaces the <select> -->
  <div class="evSection" data-insp-panel="mode" id="evSectionFrameRatio">
    <div class="evSectionTitle">Frame Ratio</div>
    <div class="evRatioGrid">
      <button class="evRatioBtn" data-ratio="9:16" onclick="evSetFrameRatio('9:16')">9:16 ↕</button>
      <button class="evRatioBtn" data-ratio="1:1"  onclick="evSetFrameRatio('1:1')">1:1 □</button>
      <button class="evRatioBtn" data-ratio="16:9" onclick="evSetFrameRatio('16:9')">16:9 ↔</button>
      <button class="evRatioBtn" data-ratio="3:4"  onclick="evSetFrameRatio('3:4')">3:4 ▭</button>
    </div>
  </div>

  <!-- evAspectRatio becomes a hidden input (keeps ID, keeps payload read) -->
  <input type="hidden" id="evAspectRatio" value="3:4">
  <!-- NOTE: add value="9:16" or "16:9" as appropriate for default once confirmed -->

NEW JS in editor-view.js:
  function evSetFrameRatio(ratio) {
    // 1. Write aspect ratio (same effect as old evAspectRatio select change)
    const ar = document.getElementById('evAspectRatio');
    if (ar) { ar.value = ratio; }
    evUpdateAspectRatio();  // updates frame preview and badge

    // 2. Highlight active button
    document.querySelectorAll('.evRatioBtn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.ratio === ratio);
    });

    // 3. Suggest Reframe default (NEW behavior)
    const reframeEl = document.getElementById('evReframeStrategy');
    if (reframeEl && reframeEl.dataset.manuallySet !== '1') {
      reframeEl.value = (ratio === '16:9') ? 'fast_center' : 'subject';
      _evHighlightReframeBtn(reframeEl.value);
    }

    // 4. Update Optimize For visibility in Export tab (NEW behavior)
    _evUpdateOptimizeForVisibility(ratio);

    // 5. Auto-write evTargetPlatform for 16:9 (YouTube Shorts auto-default)
    if (ratio === '16:9') {
      const tp = document.getElementById('evTargetPlatform');
      if (tp) tp.value = 'youtube_shorts';
      const sb = document.getElementById('qsStructureBias');
      if (sb && sb.dataset.manuallySet !== '1') sb.value = 'balanced';
    }
  }

WHY:
Frame Ratio is now a primary creator decision in Edit tab.
evAspectRatio ID stays the same — startRenderFromEditor() line 2272 reads it unchanged.
The new function also drives Reframe suggestion and Optimize For visibility.

RISK: Medium
  - evUpdateAspectRatio() reads evAspectRatio.value — now a hidden input instead of select.
    This is fine — same DOM property.
  - evApplyPreset() (Quick Presets) calls setVal('evAspectRatio', cfg.aspect_ratio) which
    writes to evAspectRatio by ID. After change: writes to hidden input — evUpdateAspectRatio()
    must be called after. Verify evApplyPreset() still calls evUpdateAspectRatio() on line 2158.
  - CONFIRMED: line 2158 calls evUpdateAspectRatio() — safe.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Add Reframe buttons to Edit tab (replaces evReframeStrategy select in Render Settings)

CURRENT (lines 1554–1561, inside inspGroupPerfBody in performance panel):
  <label class="field" style="grid-column:1/-1">
    <span class="fieldLabel">Reframe Mode</span>
    <select class="fieldInput" id="evReframeStrategy">
      <option value="fast_center" selected>Fast Center Crop</option>
      <option value="motion">Motion Tracking</option>
      <option value="subject">Subject Tracking</option>
    </select>
  </label>

FINAL:
Replace <select> with hidden <input> + add visible Reframe button row to Edit tab:

  <!-- In Edit tab (data-insp-panel="mode"), after Frame Ratio section -->
  <div class="evSection" data-insp-panel="mode" id="evSectionReframe">
    <div class="evSectionTitle">Reframe</div>
    <div class="evReframeGrid">
      <button class="evReframeBtn" data-reframe="subject"    onclick="evSetReframe('subject')">Auto</button>
      <button class="evReframeBtn" data-reframe="subject"    onclick="evSetReframe('subject')">Follow Face</button>
      <button class="evReframeBtn" data-reframe="motion"     onclick="evSetReframe('motion')">Follow Person</button>
      <button class="evReframeBtn" data-reframe="fast_center" onclick="evSetReframe('fast_center')">Center</button>
    </div>
    <div class="inspHint">AI suggests default based on your Frame Ratio. You can override.</div>
  </div>

  <!-- evReframeStrategy becomes hidden input (keeps ID, keeps payload read at lines 2328-2330) -->
  <input type="hidden" id="evReframeStrategy" value="fast_center">

NOTE: "Auto" and "Follow Face" both write 'subject' to evReframeStrategy.
  Auto = suggested by AI (evSetFrameRatio suggestion). Follow Face = same value but
  explicitly chosen by creator. Distinguish via CSS active state only.

NEW JS in editor-view.js:
  function evSetReframe(mode) {
    const el = document.getElementById('evReframeStrategy');
    if (el) {
      el.value = mode;
      el.dataset.manuallySet = '1';  // creator override — Frame Ratio click won't overwrite
    }
    _evHighlightReframeBtn(mode);
  }

  function _evHighlightReframeBtn(mode) {
    document.querySelectorAll('.evReframeBtn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.reframe === mode);
    });
  }

WHY:
Reframe is now creator-controlled and visible in Edit tab. Default suggestion comes from
Frame Ratio selection (evSetFrameRatio), but creator can override at any time.
evReframeStrategy ID stays the same — startRenderFromEditor() lines 2328-2330 unchanged.

RISK: Low — ID unchanged, payload read unchanged. Only visual layer changes.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Move Min/Max Duration and Output Count from Export Advanced/Export tab to Edit tab

CURRENT:
  evMinPart: inside qsAdvBody (Advanced fold), line 1113-1115
  evMaxPart: inside qsAdvBody (Advanced fold), line 1116-1118
  evMaxExportParts: below QS Bar in Export section, line 1074-1078

FINAL:
Move all three to Edit tab panel (data-insp-panel="mode"):

  <!-- In Edit tab, after Reframe section -->
  <div class="evSection" data-insp-panel="mode" id="evSectionDuration">
    <div class="evSectionTitle">Clip Duration</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <label class="field">
        <span class="fieldLabel">Shortest (s)</span>
        <input class="fieldInput" type="number" id="evMinPart" value="70" min="20" max="600">
      </label>
      <label class="field">
        <span class="fieldLabel">Longest (s)</span>
        <input class="fieldInput" type="number" id="evMaxPart" value="180" min="30" max="900">
      </label>
    </div>
  </div>

  <div class="evSection" data-insp-panel="mode" id="evSectionOutputCount">
    <label class="field">
      <span class="fieldLabel">Clips</span>
      <input class="fieldInput" type="number" id="evMaxExportParts" value="0" min="0">
      <span class="inspHint">0 = no limit</span>
    </label>
  </div>

WHY:
Min/Max Duration is the most impactful control for AI clip discovery. Must be above fold.
Output Count belongs with editing setup ("how many clips do you want?").
IDs unchanged — startRenderFromEditor() lines 2274-2275 and 2299 read unchanged.

RISK: Low — HTML move only. IDs unchanged. No JS impact.
NOTE: evApplyPreset() calls setVal('evMinPart', cfg.min_part_sec) and setVal('evMaxPart',
  cfg.max_part_sec) — these write by ID and will still work after the move.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Add Video Style → evEffectPreset write behavior

CRITICAL FINDING:
The current "Quick Styles" buttons (Viral/Cinematic/Aggressive/Balanced) in the Story tab
call EditorAiSessions?.applyVariant?.('viral') etc.
This is a TIMELINE EDITING action (rearranges clips), NOT a preset setter.
It does NOT write to evEffectPreset.

The evEffectPreset is currently only set by:
  (a) evApplyPreset() — called by Quick Presets (TikTok/Podcast/Business/HQ cards)
  (b) Reup mode logic in startRenderFromEditor() lines 2339-2349
  (c) Default fallback: 'story_clean_01' (line 2349)

In the locked model, "Video Style" (Viral/Cinematic/Aggressive/Balanced) must set
evEffectPreset to control the visual look of rendered clips.

CURRENT (lines 901-904):
  <button class="aiVariantBtn" id="aiVariant_viral"       onclick="EditorAiSessions?.applyVariant?.('viral')">Viral</button>
  <button class="aiVariantBtn" id="aiVariant_cinematic"   onclick="EditorAiSessions?.applyVariant?.('cinematic')">Cinematic</button>
  <button class="aiVariantBtn" id="aiVariant_aggressive"  onclick="EditorAiSessions?.applyVariant?.('aggressive')">Aggressive</button>
  <button class="aiVariantBtn" id="aiVariant_balanced"    onclick="EditorAiSessions?.applyVariant?.('balanced')">Balanced</button>

FINAL:
Update onclick to ALSO write evEffectPreset (both timeline action AND preset write):

  <button class="aiVariantBtn" id="aiVariant_viral"
    onclick="EditorAiSessions?.applyVariant?.('viral'); evSetVideoStyle('viral')">Viral</button>
  <button class="aiVariantBtn" id="aiVariant_cinematic"
    onclick="EditorAiSessions?.applyVariant?.('cinematic'); evSetVideoStyle('cinematic')">Cinematic</button>
  <button class="aiVariantBtn" id="aiVariant_aggressive"
    onclick="EditorAiSessions?.applyVariant?.('aggressive'); evSetVideoStyle('aggressive')">Aggressive</button>
  <button class="aiVariantBtn" id="aiVariant_balanced"
    onclick="EditorAiSessions?.applyVariant?.('balanced'); evSetVideoStyle('balanced')">Balanced</button>

NEW JS in editor-view.js:
  const _EV_STYLE_PRESETS = {
    viral:      'viral_fast_01',
    cinematic:  'cinematic_color_01',   // verify exact preset string name from backend
    aggressive: 'aggressive_cut_01',    // verify exact preset string name from backend
    balanced:   'story_clean_01',
  };
  function evSetVideoStyle(style) {
    const ep = document.getElementById('evEffectPreset');
    if (ep && _EV_STYLE_PRESETS[style]) {
      ep.value = _EV_STYLE_PRESETS[style];
    }
    // Highlight active style button
    document.querySelectorAll('.aiVariantBtn').forEach(btn => {
      btn.classList.toggle('isActive', btn.id === 'aiVariant_' + style);
    });
  }

IMPORTANT: The exact effect_preset strings for 'cinematic' and 'aggressive' must be
  verified against the backend render_pipeline.py before shipping. The 'viral' preset
  string 'viral_fast_01' comes from _EV_PRESETS.tiktok.effect_preset in editor-view.js
  line 2113. Confirm the cinematic and aggressive equivalents exist in the backend.

WHY:
Video Style selection must set evEffectPreset to control visual treatment of clips.
Without this, all renders default to 'story_clean_01' regardless of Style selection.
This was a hidden gap in the original design — the Quick Styles were timeline tools,
not render preset setters.

RISK: Medium
  - Requires verifying exact backend effect_preset string values for cinematic/aggressive.
  - evApplyPreset() (Quick Presets) also sets evEffectPreset — if creator applies a Quick
    Preset AND also selects a Video Style, the last write wins. This is acceptable behavior.
  - EditorAiSessions.applyVariant() continues to work unchanged (timeline editing action).
    The evEffectPreset write is additive — it doesn't break the existing action.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Add Optimize For conditional section to Export tab

CURRENT:
No conditional platform section in Export tab. The platform is set by QS Bar pills
(which are being removed).

FINAL:
Add new section in Export tab (data-insp-panel="performance"), ABOVE FPS:

  <div class="evSection" id="evSectionOptimizeFor" data-insp-panel="performance" style="display:none">
    <div class="evSectionTitle">Optimize For</div>
    <div class="inspHint" style="margin-bottom:8px">Sets AI clip priority and pacing for your platform</div>
    <div class="evOptimizeGrid" id="evOptimizeGrid">
      <!-- Populated dynamically by _evUpdateOptimizeForVisibility() based on Frame Ratio -->
    </div>
    <div id="evOptimize16note" style="display:none;font-size:11px;color:var(--text-mut)">Optimized for YouTube Shorts</div>
  </div>

NEW JS in editor-view.js:
  function _evUpdateOptimizeForVisibility(ratio) {
    const section = document.getElementById('evSectionOptimizeFor');
    const grid    = document.getElementById('evOptimizeGrid');
    const note    = document.getElementById('evOptimize16note');
    if (!section || !grid) return;

    const OPTIONS = {
      '9:16': [
        { val: 'tiktok',          label: 'TikTok',          bias: 'hook' },
        { val: 'instagram_reels', label: 'Reels',           bias: 'story' },
        { val: 'youtube_shorts',  label: 'Shorts',          bias: 'balanced' },
      ],
      '1:1': [
        { val: 'instagram_reels', label: 'Instagram Feed',  bias: 'balanced' },
        { val: 'instagram_reels', label: 'Facebook',        bias: 'balanced' },
      ],
      '3:4': [
        { val: 'instagram_reels', label: 'Instagram Feed',  bias: 'balanced' },
        { val: 'instagram_reels', label: 'Reels',           bias: 'story' },
      ],
    };

    if (ratio === '16:9') {
      section.style.display = '';
      grid.style.display = 'none';
      if (note) note.style.display = '';
      // Auto-set platform and bias for 16:9
      _evSetOptimizeFor('youtube_shorts', 'balanced', false);
      return;
    }

    const opts = OPTIONS[ratio];
    if (!opts) { section.style.display = 'none'; return; }

    section.style.display = '';
    if (note) note.style.display = 'none';
    grid.style.display = '';
    grid.innerHTML = opts.map((o, i) =>
      `<button class="evOptimizeBtn${i===0?' active':''}" data-platform="${o.val}" data-bias="${o.bias}"
        onclick="_evSetOptimizeFor('${o.val}','${o.bias}',true)">${o.label}</button>`
    ).join('');

    // Auto-select first option as default
    if (opts.length > 0) _evSetOptimizeFor(opts[0].val, opts[0].bias, false);
  }

  function _evSetOptimizeFor(platform, bias, userClick) {
    const tp = document.getElementById('evTargetPlatform');
    if (tp) tp.value = platform;

    const sb = document.getElementById('qsStructureBias');
    if (sb && (!userClick || sb.dataset.manuallySet !== '1')) {
      sb.value = bias;
      if (userClick) sb.dataset.manuallySet = '0'; // platform click resets dirty flag
    }

    // Highlight active button
    document.querySelectorAll('.evOptimizeBtn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.platform === platform);
    });
  }

WHY:
Optimize For replaces the QS Bar Platform pills with a context-sensitive interface.
Only shown when Frame Ratio implies a platform choice is needed.
16:9 silently sets youtube_shorts (no choice needed — YouTube Shorts is the only horizontal
platform target in the backend).

RISK: Medium
  - evTargetPlatform is still written by ID — payload read at line 2301 unchanged.
  - qsStructureBias is still written by ID — payload read at line 2464 unchanged.
  - New section requires correct CSS (evOptimizeBtn needs styling consistent with pill buttons).
```

---

```
FILE:
backend/static/index.html

CHANGE:
FPS selector — add Auto option, move to Export primary view

CURRENT (lines 1547–1552, inside inspGroupPerfBody):
  <label class="field">
    <span class="fieldLabel">FPS</span>
    <select class="fieldInput" id="evOutputFps">
      <option value="30">30 fps</option>
      <option value="60" selected>60 fps</option>
    </select>
  </label>

FINAL:
Move to Export primary view (data-insp-panel="performance"), with Auto added.
Add to new section BELOW Optimize For, ABOVE Advanced fold:

  <div class="evSection" data-insp-panel="performance" id="evSectionFps">
    <div class="evSectionTitle">FPS</div>
    <div class="evFpsGrid">
      <button class="evFpsBtn active" data-fps="auto" onclick="evSetFps('auto')">Auto</button>
      <button class="evFpsBtn" data-fps="30"  onclick="evSetFps('30')">30 FPS</button>
      <button class="evFpsBtn" data-fps="60"  onclick="evSetFps('60')">60 FPS</button>
    </div>
    <div class="inspHint" id="evFpsHint">Auto matches your source video frame rate</div>
  </div>

  <!-- evOutputFps hidden input — payload read at line 2298 unchanged -->
  <input type="hidden" id="evOutputFps" value="60">

NEW JS in editor-view.js:
  function evSetFps(val) {
    document.querySelectorAll('.evFpsBtn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.fps === val);
    });
    const fpsEl  = document.getElementById('evOutputFps');
    const hint   = document.getElementById('evFpsHint');
    if (val === 'auto') {
      // Calculate from source FPS stored in _ev
      const srcFps = _ev.sourceFps || 0;
      let outputFps = 60; // safe fallback
      if (srcFps >= 55)      outputFps = 60;
      else if (srcFps >= 27) outputFps = 30;
      else if (srcFps >= 20) outputFps = 24;
      if (fpsEl) fpsEl.value = outputFps;
      if (hint)  hint.textContent = srcFps > 0
        ? `Auto: ${srcFps.toFixed(2)}fps source → ${outputFps}fps output`
        : 'Auto matches your source video frame rate';
    } else {
      if (fpsEl) fpsEl.value = val;
      if (hint)  hint.textContent = `Override: ${val} FPS output`;
    }
  }

NOTE ON _ev.sourceFps:
  Must verify that prepare-source response populates a source FPS field in _ev.
  Check openEditorView() call in editor-view.js for what fields are stored in _ev.
  If sourceFps is not available: Auto writes 60 (same as current default — no regression).

WHY:
FPS Auto mode matches source FPS, preventing frame rate mismatch artifacts.
Creator who needs 30fps for file size or 60fps for explicit quality uses override buttons.

RISK: Low
  - evOutputFps ID unchanged — payload read at line 2298 unchanged.
  - Auto fallback (60fps) matches current default behavior if sourceFps not available.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Captions tab — restructure for locked model

CURRENT (data-insp-panel="subtitle", lines 1226–1305):
Subtitle ON/OFF toggle + Style + Font + Size + Color/Highlight + Y Pos + X Pos + Outline
+ Static preview ("Preview subtitle" text) + Fix Subs button + Translate

FINAL:
Keep visible: Subtitle ON/OFF + Style + Position buttons (Bottom/Middle/Top) + Fix Subs
Move to Advanced: Font + Size + Color + Highlight + X Pos + Outline + Translate
Remove: static preview element
Add: Text Layers section (moved from Words tab)
Add: live preview callout text

Changes in order:

(a) Keep Subtitle ON/OFF toggle — no change
(b) Keep Style dropdown (evSubStyle) — no change
(c) REPLACE Y Pos slider with Position button row:
    CURRENT:
      <label class="field">
        <span class="fieldLabel">Y Pos: <strong id="evSubPosVal">15</strong>%</span>
        <input type="range" id="evSubPos" ...>
      </label>
    FINAL:
      <!-- Position buttons — write to evSubPos by value -->
      <div class="evSection" id="evSubPosRow">
        <div class="evSectionTitle" style="margin-bottom:6px">Position</div>
        <div class="evPosGrid">
          <button class="evPosBtn" onclick="evSetSubPos('top')">Top</button>
          <button class="evPosBtn" onclick="evSetSubPos('middle')">Middle</button>
          <button class="evPosBtn active" onclick="evSetSubPos('bottom')">Bottom ✓</button>
        </div>
      </div>
      <!-- evSubPos hidden input — payload read at line 2235 unchanged -->
      <input type="hidden" id="evSubPos" value="15">
      <span id="evSubPosVal" style="display:none">15</span>

    NEW JS:
      function evSetSubPos(pos) {
        const map = { top: 55, middle: 35, bottom: 15 };  // verify calibrated values
        const el = document.getElementById('evSubPos');
        const valEl = document.getElementById('evSubPosVal');
        const v = map[pos] || 15;
        if (el) el.value = v;
        if (valEl) valEl.textContent = v;
        document.querySelectorAll('.evPosBtn').forEach(b => b.classList.remove('active'));
        const activeBtn = document.querySelector(`.evPosBtn[onclick*="'${pos}'"]`);
        if (activeBtn) activeBtn.classList.add('active');
        evUpdateSubPreview();
      }

    VERIFY: evSubPos value mapping to sub_margin_v in startRenderFromEditor() line 2235-2238.
      The calculation: sub_margin_v = Math.round((posY / 100) * _playResY)
      For 9:16 (playResY=1920): posY=15 → 288px from top, posY=35 → 672px, posY=55 → 1056px
      Confirm these feel like Bottom, Middle, Top on the actual output frame.
      These may need tuning after visual testing.

(d) REMOVE static preview element (lines 1285–1288):
    DELETE:
      <div class="inspSubPreview" id="evSubStaticPreview">
        <img id="evSubPreviewImg" ...>
        <span id="evSubStaticText" ...>Preview subtitle</span>
      </div>

(e) ADD live preview callout (after Position section):
    <div class="inspHint" style="margin-top:6px">
      ↑ Watch your video on the left — subtitle updates live as you change settings
    </div>

(f) Keep Fix Subs button — visible always (not conditional):
    CURRENT (line 1290):
      <button class="aiActionBtn" ... onclick="EditorAiActions?.subtitleCleanup?.()">✦ Fix Subs — AI cleanup</button>
    FINAL: no change to this element. Always visible when Subtitles are ON.

(g) Add <details> Advanced section containing: Font + Size + Color + Highlight + Outline + X Pos + Translate
    These elements move inside a <details> wrapper in the subtitle panel.
    CRITICAL: evSubPosX must have its hidden input OUTSIDE the <details>:
      <!-- Keep evSubPosX outside <details> as hidden input at default 50 -->
      <input type="hidden" id="evSubPosX" value="50">
      <span id="evSubPosXVal" style="display:none">50</span>
    Then add a visible X Position slider INSIDE the <details> Advanced section.

(h) Add Text Layers section (moved from Words tab data-insp-panel="text"):
    The inspCollapsedGroup with data-insp-panel="text" (line 1322) becomes
    data-insp-panel="subtitle".
    EditorTextRuntime.onTabActivate() must fire when this section expands
    (add <details> ontoggle event handler).

RISK: Medium overall
  - evSubPos as hidden input: evUpdateSubPreview() at line 1681 reads qs('evSubPos').value
    This still works with hidden input.
  - evSubPosX must remain outside <details>. Verify after restructure.
  - evSubStaticPreview removal: no JS reads this element by ID in startRenderFromEditor().
    Safe to remove.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Move Creator Presets bar (cpBar) to inspector footer (evFooter)

CURRENT (lines 1025–1035, inside evSectionBasic which is performance panel):
  <div class="cpBar" id="cpBar">
    <select class="fieldInput cpSelect" id="cpPresetSelect" ...>
    <button class="ghostButton cpSaveBtn" id="cpSaveBtn" ...>Save</button>
    <button class="ghostButton cpDeleteBtn" id="cpDeleteBtn" ...></button>
  </div>

FINAL:
Move cpBar HTML into evFooter (line 1592–1601), between status line and render button:
  <div class="evFooter">
    <div ... status line ...></div>
    <!-- Creator Presets — moved to footer for tab-independent access -->
    <div class="cpBar" id="cpBar">
      <select class="fieldInput cpSelect" id="cpPresetSelect" ...>
      <button ... id="cpSaveBtn" ...>Save</button>
      <button ... id="cpDeleteBtn" ...></button>
    </div>
    <button class="primaryButton" id="evStartBtn" ...>▶ Start Render</button>
  </div>

WHY:
Creator Presets apply to the entire render setup, not just Export.
Footer placement makes them always visible regardless of active tab.

RISK: Medium
  - cpBar DOM-ready and init code in creator-presets.js may use document-ready timing.
    The footer is part of the main layout — should be available at same time as before.
  - CSS: cpBar may have CSS that assumes it's inside the inspector scroll area.
    After move to footer (fixed position): review cpBar CSS for any relative positioning
    assumptions.
  - ID cpBar, cpPresetSelect, cpSaveBtn, cpDeleteBtn unchanged — CreatorPresets JS works.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Remove Edit History, Creator Memory, AI Edit Actions sections from mode panel

CURRENT (lines 912–944, data-insp-panel="mode"):
  <!-- AI Edit Actions (collapsible) -->
  <div class="inspCollapsedGroup" id="inspGroupAiEdit" data-insp-panel="mode">
    ...
  </div>

  <!-- Edit History -->
  <div class="inspCollapsedGroup" id="inspGroupEditHistory" data-insp-panel="mode">
    ...
  </div>

  <!-- Creator Memory panel -->
  <div id="cmPrefsPanel" class="cmPrefsPanel" data-insp-panel="mode"></div>

FINAL:
Remove all three sections entirely from mode panel.

RISK: Low
  - inspGroupAiEdit: buttons call EditorAiActions methods. Removing the container removes
    the buttons. No other JS depends on inspGroupAiEdit existing.
  - inspGroupEditHistory: contains aiSuggestionChips and aiActivityRail. Check if any JS
    appends to these by ID (aiSuggestionChips, aiActivityRail) and whether that JS errors
    if the elements don't exist. Add null guards if needed.
  - cmPrefsPanel: populated by creator-memory.js via innerHTML. Removing the container means
    creator-memory.js will try to populate a non-existent element. The populate call must
    be null-guarded (check if JS does getElementById null check already).
```

---

```
FILE:
backend/static/index.html + backend/static/js/editor-view.js

CHANGE:
AI tab content (convPanel) — move to Edit Advanced (deep collapse)

CURRENT (lines 851–865, data-insp-panel="ai"):
  <div class="convPanel" data-insp-panel="ai">
    ...conversation history, input, example buttons...
  </div>

FINAL:
Change data-insp-panel="ai" to data-insp-panel="mode", wrap in <details> inside
Edit Advanced section (deepest level):

  <!-- Inside Edit Advanced section, at the bottom: -->
  <details>
    <summary>AI Chat</summary>
    <div class="convPanel">  ← remove data-insp-panel attribute
      ...conversation history, input, example buttons... (unchanged)
    </div>
  </details>

ALSO: evInspAiPanel (line 848, data-insp-panel="mode"):
  This is already in the mode panel. No change needed.

RISK: Low — content unchanged; only panel visibility changes.
  EditorConverse.reset() is called on editor teardown (line 2044) — unchanged.
```

---

```
FILE:
backend/static/index.html

CHANGE:
Export tab cleanup — QS Bar removal, Market & Target relocation

CURRENT qsBar section (lines 1044–1073, data-insp-panel="performance"):
Full QS Bar with Platform + Subtitle + Structure pill groups + qsStructureBias hidden input

FINAL:
Remove Platform pill group (<div class="qsGroup"> containing YouTube/TikTok/Reels buttons)
Remove Subtitle pill group (<div class="qsGroup"> containing Off/Clean/Viral/Karaoke buttons)
Remove Structure pill group (<div class="qsGroup"> containing More Hook/Balanced/More Story buttons)
KEEP: qsStructureBias hidden input (MUST stay in DOM — line 2464 reads it)
  Move it to evEditorCompat if the entire qsBar wrapper is removed.

FINAL qsStructureBias placement:
  <!-- In evEditorCompat or directly in mode panel as hidden input: -->
  <input type="hidden" id="qsStructureBias" value="balanced">

ALSO: Market & Target section (lines 988–1019) — move to Edit Advanced:
  Change data-insp-panel="performance" to data-insp-panel="mode"
  Wrap in <details> in Edit Advanced section

ALSO: Quick Presets section (lines 947–986) — move to Edit Advanced (see earlier patch)

ALSO: Batch Queue section (lines 1206–1224, data-insp-panel="performance") — move to Edit Advanced:
  Change data-insp-panel="performance" to data-insp-panel="mode"
  Wrap in <details> in Edit Advanced section

ALSO: Editor Performance section (lines 1569–1587, data-insp-panel="performance") — move to Export Advanced:
  Keep in performance panel but inside a new <details> Advanced section:
  <details id="evExportAdvanced">
    <summary>Advanced</summary>
    <!-- Quality select (evRenderProfile) -->
    <!-- Device select (evRenderDevice) -->
    <!-- Editor Performance section -->
  </details>

RISK: Medium for QS Bar removal
  - evSyncQsBar() iterates over [data-qs-group="platform"], [data-qs-group="sub"],
    [data-qs-group="structure"] elements. After removal, these return empty NodeList.
    evSyncQsBar() calls will execute but do nothing (no-op). Safe.
  - v3RefreshSteeringPanel() reads qsStructureBias.value (line 202) — must remain in DOM.
  - evQsSet('structure', val) writes qsStructureBias.value — this call still works after
    qsBar removal as long as the hidden input exists.
```

---

## 3. Component Move Map

```
CONTROL: QS Bar Platform pills (YouTube/TikTok/Reels)
ACTION: Remove from UI. Replace with Optimize For conditional (separate section).
BACKEND IMPACT: None — evTargetPlatform still written by new Optimize For buttons.
RUNTIME IMPACT: evQsSet('platform') still exists but Optimize For bypasses it, writes directly.
  evSyncQsBar() platform iteration becomes no-op (empty NodeList).
RISK: Medium — evQsSet() decoupling required (see Section 2 patch).
```

```
CONTROL: QS Bar Subtitle pills (Off/Clean/Viral/Karaoke)
ACTION: Remove from UI. Subtitle style is set exclusively in Captions tab (evSubStyle dropdown).
BACKEND IMPACT: None — evSubStyle still read at line 2239.
RUNTIME IMPACT: evSyncQsBar() subtitle iteration becomes no-op. evQsSet('sub') still works
  if called by evApplyPreset() — verify evApplyPreset does not call evQsSet('sub').
  Confirmed: evApplyPreset() sets evSubStyle directly (line 2162), not via evQsSet.
RISK: Low.
```

```
CONTROL: QS Bar Structure pills (More Hook/Balanced/More Story)
ACTION: Remove from UI. qsStructureBias is auto-written by Optimize For selection.
BACKEND IMPACT: None — qsStructureBias hidden input stays in DOM (line 2464).
RUNTIME IMPACT: evSyncQsBar() structure iteration becomes no-op.
RISK: Low — qsStructureBias input stays, just no visible buttons.
```

```
CONTROL: Aspect Ratio select (evAspectRatio) — in Export Advanced
ACTION: Replace with hidden input. Frame Ratio buttons in Edit tab write to it.
BACKEND IMPACT: None — payload.aspect_ratio read at line 2272 unchanged.
RUNTIME IMPACT: evUpdateAspectRatio() reads evAspectRatio.value — works with hidden input.
  evApplyPreset() writes to evAspectRatio by ID — still works.
RISK: Low — ID unchanged, payload unchanged.
```

```
CONTROL: Reframe Mode select (evReframeStrategy) — in Render Settings
ACTION: Replace with hidden input. Reframe buttons in Edit tab write to it.
BACKEND IMPACT: None — payload lines 2328-2330 unchanged.
RUNTIME IMPACT: None — same ID, same read.
RISK: Low — ID unchanged.
```

```
CONTROL: FPS select (evOutputFps) — in Render Settings
ACTION: Replace with hidden input. FPS buttons in Export tab write to it with Auto mode.
BACKEND IMPACT: None — payload line 2298 unchanged.
RUNTIME IMPACT: Auto mode requires _ev.sourceFps — must verify field is populated.
RISK: Low with fallback (60fps if sourceFps missing).
```

```
CONTROL: AI Clip Selection (qsStructureBias UI — structure pills)
ACTION: Remove from visible UI. Auto-written by Optimize For selection (platform-driven).
  Override available in Edit Advanced (AI Clip Selection section).
BACKEND IMPACT: None — qsStructureBias hidden input stays.
RUNTIME IMPACT: v3RefreshSteeringPanel() reads qsStructureBias.value — still works.
RISK: Low.
```

```
CONTROL: Reframe (evReframeStrategy) — new visible position in Edit tab
ACTION: Keep visible. Becomes button row in Edit tab.
  Default suggestion written by Frame Ratio selection.
  Creator can override by clicking any Reframe button.
NEW DEFAULT: 16:9 → 'fast_center' (Center); all other ratios → 'subject' (Auto/Follow Face)
BACKEND IMPACT: None — same payload.
RUNTIME IMPACT: New JS functions evSetReframe() and _evHighlightReframeBtn().
RISK: Medium — new behavior; verify payload.reframe_mode and motion_aware_crop correct.
```

```
CONTROL: Output Profile (evRenderProfile) — in Export Advanced
ACTION: Keep in DOM. Remove from primary Export visible. Move to Export Advanced <details>.
DEFAULT: 'balanced' (unchanged)
BACKEND IMPACT: None — line 2314 reads unchanged.
RISK: Low.
```

```
CONTROL: Encoder Device (evRenderDevice) — in Render Settings
ACTION: Keep in DOM. Move to Export Advanced <details>.
DEFAULT: 'auto' (unchanged)
BACKEND IMPACT: None — line 2311 reads unchanged.
RISK: Low.
```

```
CONTROL: Editor Performance section
ACTION: Move to Export Advanced <details>. Keep IDs.
BACKEND IMPACT: None.
RUNTIME IMPACT: EditorPerformanceRuntime.onTabActivate() currently fires on Export tab
  entry — trigger is unchanged (Export tab still exists, EditorPerformanceRuntime still
  fires on 'performance' tab entry in setInspectorTab()).
RISK: Low.
```

```
CONTROL: AI Narration (evSectionNarration, data-insp-panel="text")
ACTION: Change data-insp-panel to "mode". Wrap in Edit Advanced <details>.
  Conditional: sub-controls only visible when evVoiceEnable is checked.
BACKEND IMPACT: None — payload lines 2365-2385 read the same IDs.
RUNTIME IMPACT: EditorAudioRuntime.onVoiceToggle() called by evVoiceEnable onchange — unchanged.
RISK: Low.
```

```
CONTROL: Text Layers (inspCollapsedGroup, data-insp-panel="text")
ACTION: Change data-insp-panel to "subtitle". Add to Captions Advanced section.
BACKEND IMPACT: None — EditorTextRuntime.serializeForRender() called at line 2451.
RUNTIME IMPACT: EditorTextRuntime.onTabActivate() must fire when this section expands.
  Add <details ontoggle="if(this.open && typeof EditorTextRuntime!=='undefined') EditorTextRuntime.onTabActivate()">
RISK: Low.
```

```
CONTROL: Audio Tracks (inspCollapsedGroup, data-insp-panel="audio")
ACTION: Change data-insp-panel to "mode". Add to Edit Advanced section.
BACKEND IMPACT: None — evVolume, evBgmEnable, evBgmGain etc. read unchanged.
RUNTIME IMPACT: EditorAudioRuntime.onTabActivate() now fires on Edit tab entry — see
  setInspectorTab() patch. EditorAudioRuntime.onSourceToggle(), onBgmToggle() etc.
  called by element onchange — these fire correctly regardless of tab.
RISK: Low.
```

```
CONTROL: Loudness normalization (edAudioLoudnorm checkbox, in Audio section)
ACTION: Remove from visible UI. evLoudnormEnabled stays always-on.
BACKEND IMPACT: None — evLoudnormEnabled always reads "1".
RUNTIME IMPACT: The edAudioLoudnorm checkbox currently writes to evLoudnormEnabled via
  inline onchange. Removing the visible checkbox is fine — evLoudnormEnabled hidden
  input stays at "1" permanently.
RISK: Low. Verify evLoudnormEnabled remains outside <details>.
```

```
CONTROL: Market & Target (evSectionMarket, data-insp-panel="performance")
ACTION: Change data-insp-panel to "mode". Wrap in Edit Advanced <details>.
BACKEND IMPACT: None — mvGetState() called at line 2391.
RUNTIME IMPACT: mvHandleChange(), mvHandleAutoBestClips() called by element onchange — unchanged.
RISK: Low.
```

```
CONTROL: Quick Presets (evPresetSection, data-insp-panel="performance")
ACTION: Move <details> contents to Edit Advanced. evEffectPreset + evLoudnormEnabled
  must move OUTSIDE the <details> to remain Phase 64 compliant.
BACKEND IMPACT: None.
RUNTIME IMPACT: evApplyPreset() writes evEffectPreset — still works.
RISK: Critical — Phase 64 constraint. Must verify evEffectPreset outside <details>.
```

```
CONTROL: Batch Queue (bqSection, data-insp-panel="performance")
ACTION: Change data-insp-panel to "mode". Wrap in Edit Advanced <details>.
BACKEND IMPACT: None — BatchQueue.submit() works by ID.
RUNTIME IMPACT: BatchQueue module finds bqDropZone, bqList by ID — unchanged.
RISK: Low.
```

```
CONTROL: Batch Mode (evBatchPanel, inside qsAdvBody)
ACTION: Move to Edit Advanced along with other qsAdvBody content.
BACKEND IMPACT: None.
RISK: Low.
```

```
CONTROL: Edit History (inspGroupEditHistory)
ACTION: Remove from DOM.
BACKEND IMPACT: None.
RUNTIME IMPACT: aiSuggestionChips, aiActivityRail — check if any JS appends to these.
  Add null check if found.
RISK: Low.
```

```
CONTROL: Creator Memory (cmPrefsPanel)
ACTION: Remove from DOM.
BACKEND IMPACT: None.
RUNTIME IMPACT: creator-memory.js populates cmPrefsPanel by ID. Must add null guard.
RISK: Low.
```

---

## 4. DOM + JS Dependency Audit

### 4.1 Critical DOM Requirements (Must Never Break)

| Element ID | DOM Rule | Used By | Risk If Violated |
|---|---|---|---|
| `evEffectPreset` | Must be in DOM, OUTSIDE any `<details>` | startRenderFromEditor() line 2349, evApplyPreset() line 2170 | Silent: all renders default to 'story_clean_01' |
| `evLoudnormEnabled` | Must be in DOM, OUTSIDE any `<details>` | startRenderFromEditor() line 2353, evApplyPreset() line 2171 | Silent: loudness normalization may be disabled |
| `evSubPosX` | Must be in DOM, value=50 | startRenderFromEditor() line 2250, evSubPosXChange() | Subtitle X position defaults incorrectly |
| `qsStructureBias` | Must be in DOM | startRenderFromEditor() line 2464, v3RefreshSteeringPanel() line 202 | Structure bias missing from payload |
| `evTargetPlatform` | Must be in DOM | startRenderFromEditor() line 2301, evSyncQsBar() line 113 | Platform defaults to 'youtube_shorts' for all creators |
| `evAspectRatio` | Must be in DOM | startRenderFromEditor() line 2272, evUpdateAspectRatio() | Aspect ratio payload wrong |
| `evReframeStrategy` | Must be in DOM | startRenderFromEditor() lines 2328-2330 | Reframe mode defaults to center crop |
| `evFrameScaleY` | Must be in DOM, value=106 | startRenderFromEditor() line 2305 | Frame scale wrong |
| `evPlaybackSpeed` | Must be in DOM, value=1.07 | startRenderFromEditor() line 2273 | Speed wrong |
| `evPartOrder` | Must be in DOM, value='viral' | startRenderFromEditor() line 2304 | Clip order wrong |
| `evCleanupTemp` | Must be in DOM, checked=true | startRenderFromEditor() line 2331 | Temp files not cleaned |
| `evSubtitleEmphasis` | Must be in DOM, value='balanced' | startRenderFromEditor() line 2466 | Subtitle emphasis wrong |
| `evTransformPreset` | Must be in DOM, value='slight' | startRenderFromEditor() line 2336 | Reup transform preset missing |
| `bqSection` | Must be in DOM | BatchQueue module (finds by ID) | Batch Queue broken |
| `edPerfHealthBanner` | Must be in DOM | EditorPerformanceRuntime | Performance health display broken |
| `evStartBtn` | Must be in DOM | startRenderFromEditor() line 2522, multiple places | Render button state broken |

### 4.2 JS Function Dependencies

**evSyncQsBar()** (editor-view.js lines 112–176):
- Reads `evTargetPlatform`, iterates `[data-qs-group="platform"]` → after removal: no-op on platform group. Safe.
- Reads `evAddSubtitle`, `evSubStyle` to determine subtitle pill state → after removal: no-op. Safe.
- Reads `evMultiVariant` for variant button → `qsVariantBtn` (keep in DOM or null-guard).
- Reads `qsStructureBias` → must remain in DOM.
- Reads `evCtaEnabled` for `qsCtaBtn` → after QS Bar removal, `qsCtaBtn` may not exist. Null-guard already present (`if (ctaEl && ctaBtn)`). Safe.
- Calls `v3RefreshSteeringPanel()` → safe.
- **Action:** No changes needed to evSyncQsBar() itself. It handles missing elements gracefully via null checks.

**evQsSet()** (editor-view.js lines 355–379):
- Platform group: decoupled (see Section 2 patch — remove evAspectRatio write).
- Structure group: still writes qsStructureBias — used by Edit Advanced AI Clip Selection.
- Sub group: still writes evAddSubtitle and evSubStyle — still valid for Quick Presets.
- **Action:** Remove evAspectRatio write from platform group.

**evApplyPreset()** (editor-view.js lines 2143–2174):
- Calls `setVal('evAspectRatio', cfg.aspect_ratio)` → writes to new hidden input. Then calls `evUpdateAspectRatio()` line 2158 → reads evAspectRatio.value. Works with hidden input. No change needed.
- Calls `setVal('evEffectPreset', cfg.effect_preset)` → evEffectPreset must stay in DOM. Works as long as the Phase 64 constraint is honored.
- Called by Quick Presets cards (evApplyPreset('tiktok') etc.) — these move to Edit Advanced. onclick handlers unchanged.

**evUpdateAspectRatio()** (editor-view.js lines 1664–1673):
- Reads `evAspectRatio.value` → works with hidden input. Updates `evVideoFrame` aspect ratio and `evAspectBadge`. No change needed.

**evUpdateSubPreview()** (editor-view.js lines 1676+):
- Reads `evSubFont`, `evSubSize`, `evSubColor`, `evSubHighlight`, `evSubPos`, `evSubOutline`.
- After restructure: some of these are in Captions Advanced <details>. They remain in DOM regardless of collapse state. Works correctly.
- Writes to `evSubStaticText` (static preview span) and `evSubPreviewImg`. After removing the static preview element, these writes will fail silently (element not found). Must add null guards in evUpdateSubPreview() for these two writes.
- **Action:** Add `if (el)` guard around evSubStaticText and evSubPreviewImg writes in evUpdateSubPreview().

**EditorAudioRuntime** (editor-audio-runtime.js):
- `onTabActivate()`: verify this can be called multiple times (idempotent / lazy init).
- `onVoiceToggle()`: called by evVoiceEnable onchange — unchanged.
- `onVolumeSlider()`, `onBgmToggle()` etc: called by element onchange — unchanged.
- **Action before shipping:** Read editor-audio-runtime.js line 1 of onTabActivate() to confirm idempotent call safety.

**EditorTextRuntime** (editor-text-runtime.js):
- `onTabActivate()`: currently fires when Words tab opens. After move: fires on Edit tab entry. Verify idempotent.
- The text-layers group auto-open (`evSetInspGroupOpen('text-layers', hasLayers)`) is REMOVED from setInspectorTab(). This was triggering for the Words tab — in the new model, Text Layers are in Captions Advanced and only open on creator's explicit action.
- **Action before shipping:** Read editor-text-runtime.js onTabActivate() to confirm idempotent call safety.

**EditorPerformanceRuntime** (editor-performance-runtime.js):
- `onTabActivate()` / `onTabDeactivate()`: still fires on 'performance' tab entry/exit. Unchanged.
- `onHoverPreviewToggle()`, `onFilmstripToggle()`, `onWaveformToggle()`: called by element onchange — unchanged.
- Elements `edPerfHealthBanner`, `edPerfHoverPreview`, `edPerfFilmstrip`, `edPerfWaveform` must stay in DOM.

**v3RefreshSteeringPanel()** (editor-view.js lines 179–251):
- Reads `qsStructureBias` (line 202) → must stay in DOM.
- Reads `evSubtitleEmphasis` (line 205) → must stay in DOM.
- Reads `cpDnaHint`, `cpSeriesHint`, `cpConsistencyHint` elements by ID — these are inside cpBar. If cpBar moves to footer, these IDs must move with it or be null-guarded.
- **Action:** Move `cpDnaHint`, `cpSeriesHint`, `cpConsistencyHint` elements with cpBar to footer. Or confirm they are already inside cpBar HTML.

**CreatorPresets** (creator-presets.js):
- Finds `cpBar`, `cpPresetSelect`, `cpSaveBtn`, `cpDeleteBtn` by ID.
- After moving cpBar to footer: these IDs still exist in DOM. No change needed to CreatorPresets.
- Verify: CreatorPresets initializes via DOMContentLoaded or similar. Footer elements are part of initial DOM — available at same time as before.

**BatchQueue** (batch-queue.js):
- Finds `bqSection`, `bqDropZone`, `bqList`, `bqActions`, `bqSubmitBtn`, `bqFileInput` by ID.
- After moving bqSection to Edit Advanced: all IDs unchanged. BatchQueue.init() must find these after DOMContentLoaded — still works as long as the elements exist in initial HTML.

---

## 5. Payload Safety Audit

Every payload field that must continue to be set correctly after simplification.

| Payload Field | Source Element | Source Location After Change | Line in startRenderFromEditor() | Safe? |
|---|---|---|---|---|
| `aspect_ratio` | evAspectRatio | Hidden input in Edit panel | 2272 | ✓ Written by Frame Ratio buttons |
| `playback_speed` | evPlaybackSpeed | evEditorCompat (unchanged) | 2273 | ✓ Unchanged |
| `min_part_sec` | evMinPart | Edit tab (moved from Advanced fold) | 2274 | ✓ ID unchanged |
| `max_part_sec` | evMaxPart | Edit tab (moved from Advanced fold) | 2275 | ✓ ID unchanged |
| `output_fps` | evOutputFps | Hidden input in Export panel | 2298 | ✓ Written by FPS buttons |
| `max_export_parts` | evMaxExportParts | Edit tab (moved from Export) | 2299 | ✓ ID unchanged |
| `multi_variant` | evMultiVariant | Edit Advanced | 2300 | ✓ ID unchanged |
| `target_platform` | evTargetPlatform | Hidden input (written by Optimize For) | 2301 | ✓ Written by Optimize For |
| `part_order` | evPartOrder | evEditorCompat (unchanged) | 2304 | ✓ Unchanged |
| `frame_scale_y` | evFrameScaleY | evEditorCompat (unchanged) | 2305 | ✓ Unchanged |
| `encoder_mode` | evRenderDevice | Export Advanced | 2311 | ✓ ID unchanged |
| `render_profile` | evRenderProfile | Export Advanced | 2314 | ✓ ID unchanged |
| `add_subtitle` | evAddSubtitle | Captions tab (unchanged) | 2327 | ✓ Unchanged |
| `motion_aware_crop` | evReframeStrategy | Hidden input in Edit panel | 2329 | ✓ Written by Reframe buttons |
| `reframe_mode` | evReframeStrategy | Hidden input in Edit panel | 2330 | ✓ Written by Reframe buttons |
| `cleanup_temp_files` | evCleanupTemp | evEditorCompat (unchanged) | 2331 | ✓ Unchanged |
| `reup_mode` | evReupMode | evEditorCompat (unchanged) | 2337 | ✓ Unchanged |
| `effect_preset` | evEffectPreset | Mode panel outside <details> | 2349 | ✓ Written by evSetVideoStyle() + evApplyPreset() |
| `loudnorm_enabled` | evLoudnormEnabled | Mode panel outside <details> | 2353 | ✓ Always "1", Phase 64 compliant |
| `reup_bgm_enable` | evBgmEnable | Edit Advanced (Audio) | 2356 | ✓ ID unchanged |
| `reup_bgm_gain` | evBgmGain | Edit Advanced (Audio) | 2358 | ✓ ID unchanged |
| `voice_enabled` | evVoiceEnable | Edit Advanced (Narration) | 2365 | ✓ ID unchanged |
| `subtitle_translate_enabled` | evSubTranslate | Captions Advanced | 2386 | ✓ ID unchanged |
| `sub_font` | evSubFont | Captions Advanced | 2230 | ✓ In DOM |
| `sub_font_size` | evSubSize | Captions Advanced | 2231 | ✓ In DOM |
| `sub_color` | evSubColor | Captions Advanced | 2232 | ✓ In DOM |
| `sub_highlight` | evSubHighlight | Captions Advanced | 2233 | ✓ In DOM |
| `sub_outline` | evSubOutline | Captions Advanced | 2234 | ✓ In DOM |
| `sub_margin_v` | evSubPos | Hidden input (replaced Y Pos slider) | 2235-2238 | ✓ Written by Position buttons |
| `subtitle_style` | evSubStyle | Captions tab (visible) | 2239 | ✓ Unchanged |
| `sub_x_percent` | evSubPosX | Hidden input, value=50 | 2250 | ✓ Outside <details> |
| `structure_bias` | qsStructureBias | Hidden input in DOM | 2464 | ✓ Written by Optimize For |
| `subtitle_emphasis` | evSubtitleEmphasis | Hidden input (unchanged) | 2466 | ✓ Unchanged |
| `market_viral.*` | mvGetState() | Edit Advanced (Market & Target) | 2391 | ✓ IDs unchanged |
| `cta_enabled` | evCtaEnabled | Edit Advanced | 2302 | ✓ ID unchanged |
| `editor_audio_plan` | EditorAudioRuntime | Runtime (unchanged) | 2459 | ✓ Unchanged |
| `editor_text_layers` | EditorTextRuntime | Runtime (unchanged) | 2451 | ✓ Unchanged |

**Fields NOT in the table (they're not read from DOM form elements):**
- `edit_session_id`, `edit_trim_in`, `edit_trim_out`, `edit_volume` — from _ev state and evTrimIn/OutSlider
- `text_layers` — from _ev.textLayers state
- `editor_clip_plan` — from EditorState.getState()
- `creator_dna`, `creator_series`, `creator_consistency` — from runtime modules

All of these are unaffected by the UI restructure.

---

## 6. Implementation Order

### P0 — Zero Risk: Label Changes Only (no DOM moves, no JS changes)

1. Tab button text: "Story" → "Edit", "Subtitles" → "Captions" (2 text nodes in index.html)
2. Field label text: "Min clip (s)" → "Shortest (s)", "Max clip (s)" → "Longest (s)"
3. Reframe Mode select label: "Reframe Mode" → "Reframe"
4. Add `title` tooltip to existing Reframe select options
5. Remove `inspHint` that says "Fast = fastest · Motion = slower · Subject = slowest" — replace with "AI suggests a default based on your Frame Ratio. You can override."

**Test P0:** Visual review only. Reload page, confirm tab labels, confirm field labels. No functional test needed.

---

### P1 — Safe DOM Moves (no new JS behavior, IDs unchanged)

Execute in this sequence to minimize scope of each change:

1. **Move Min/Max Duration to Edit tab** — HTML only. evMinPart, evMaxPart leave qsAdvBody, appear in mode panel. Verify: Advanced fold opens without them.

2. **Move Output Count to Edit tab** — HTML only. evMaxExportParts leaves evSectionBasic, appears in mode panel.

3. **Move Text Layers section to Captions tab** — Change `data-insp-panel="text"` to `"subtitle"` on the inspCollapsedGroup wrapping text layers. Add `ontoggle` trigger for EditorTextRuntime.

4. **Move Audio section to Edit tab** — Change `data-insp-panel="audio"` to `"mode"` on inspCollapsedGroup for Audio Tracks. Wrap in Edit Advanced section if needed.

5. **Move AI Narration section to Edit tab** — Change `data-insp-panel="text"` to `"mode"` on evSectionNarration.

6. **Move AI Chat (convPanel) to Edit tab** — Change `data-insp-panel="ai"` to `"mode"`. Wrap in deep <details> in Edit Advanced.

7. **Move Market & Target to Edit Advanced** — Change `data-insp-panel="performance"` to `"mode"`.

8. **Move Batch Queue to Edit Advanced** — Change `data-insp-panel="performance"` to `"mode"`.

9. **Move Editor Performance to Export Advanced** — Keep in performance panel but wrap in <details> Advanced section.

10. **Remove Edit History section** — Delete inspGroupEditHistory from DOM. Add null guards for aiSuggestionChips/aiActivityRail if needed.

11. **Remove Creator Memory div** — Delete cmPrefsPanel from DOM. Verify creator-memory.js null-guards the populate call.

12. **Remove AI Edit Actions section** — Delete inspGroupAiEdit from DOM.

13. **Move cpBar to footer** — Relocate cpBar HTML into evFooter.

14. **Remove static subtitle preview** — Delete inspSubPreview element. Add null guards in evUpdateSubPreview() for evSubStaticText and evSubPreviewImg.

15. **Move subtitle Size/Color/Highlight/Font/Outline/Translate to Captions Advanced** — Wrap in <details> inside subtitle panel. Keep evSubPosX hidden input OUTSIDE <details>.

16. **Remove Words, Audio, AI tab buttons** — Delete the 3 button elements from inspTabbar.

17. **Move Quick Presets <details> to Edit Advanced** — Keep evEffectPreset and evLoudnormEnabled outside <details>.

18. **Move evEffectPreset and evLoudnormEnabled** — Ensure they are in mode panel OUTSIDE any <details>. Verify with: `document.getElementById('evEffectPreset').closest('details') === null`

19. **Update validTabs and setInspectorTab()** — Apply JS changes from Section 2 patch (redirect removed tabs, update tabTitles, migrate triggers).

**Test P1:** 
- Reload editor, open all 3 tabs, verify no console errors
- Confirm evMinPart, evMaxPart visible in Edit tab
- Confirm subtitle controls visible in Captions tab  
- Confirm evEffectPreset is outside <details>: open browser console → `document.getElementById('evEffectPreset').closest('details')` → must return null
- Submit a test render — payload must contain all expected fields (verify via network tab)

---

### P2 — New Behavior (new JS interactions)

1. **Add evSetFrameRatio() function** — Frame Ratio buttons + evAspectRatio hidden input replace the old select. Includes Reframe default suggestion and Optimize For visibility trigger.

2. **Add evSetReframe() and _evHighlightReframeBtn()** — Reframe buttons + evReframeStrategy hidden input.

3. **Add evSetVideoStyle() and _EV_STYLE_PRESETS** — Video Style buttons write evEffectPreset. Verify exact backend effect_preset strings.

4. **Add _evUpdateOptimizeForVisibility() and _evSetOptimizeFor()** — Optimize For conditional section logic. Platform-to-qsStructureBias auto-write.

5. **Add evSetFps() with Auto mode** — FPS buttons + evOutputFps hidden input. Verify _ev.sourceFps availability.

6. **Add Position buttons and evSetSubPos()** — Bottom/Middle/Top buttons write to evSubPos hidden input.

7. **Add Subtitle ON/OFF conditional hide** — JS: when evAddSubtitle toggled, show/hide subtitle controls below. (All inputs remain in DOM; only visibility changes.)

8. **Decouple evQsSet() 'platform' group** — Remove evAspectRatio write from platform branch (see Section 2 patch).

9. **Verify EditorAudioRuntime.onTabActivate() is idempotent** — Check editor-audio-runtime.js. If not idempotent, add a flag.

10. **Verify EditorTextRuntime.onTabActivate() is idempotent** — Check editor-text-runtime.js.

**Test P2:** Full integration tests from Section 7.

---

### P3 — Cleanup and Dead Code

1. Remove the old `<select id="evAspectRatio">` element (replaced by hidden input).
2. Remove the old `<select id="evReframeStrategy">` element (replaced by hidden input).
3. Remove the old FPS `<select id="evOutputFps">` element (replaced by hidden input).
4. Remove Y Pos `<input type="range" id="evSubPos">` slider (replaced by hidden input + position buttons).
5. Remove old Max clips label/input from Export evSectionBasic (moved to Edit tab).
6. Remove inspGroupPerfBody Render Settings section after FPS/Reframe are moved.
7. Remove the now-empty qsBar wrapper if all 3 pill groups are gone (keep qsStructureBias hidden input).
8. Remove `data-insp-panel="text"`, `"audio"`, `"ai"` panel sections that are now empty.

---

## 7. Test Plan

### 7.1 Render Payload Tests (most critical)

**Test: 9:16 TikTok render**
```
Setup: Frame Ratio = 9:16, Optimize For = TikTok, Reframe = Auto (Follow Face)
Expected payload:
  aspect_ratio = '9:16'
  target_platform = 'tiktok'
  structure_bias = 'hook'
  reframe_mode = 'subject'
  motion_aware_crop = true
  playback_speed = 1.07 (platform delta applied backend-side)
  frame_scale_y = 106
  loudnorm_enabled = true
Verify: Network tab → POST /api/render/start → check request body
```

**Test: 16:9 YouTube render (auto-platform)**
```
Setup: Frame Ratio = 16:9, no Optimize For shown
Expected payload:
  aspect_ratio = '16:9'
  target_platform = 'youtube_shorts'
  structure_bias = 'balanced'
  reframe_mode = 'center'
  motion_aware_crop = false
Verify: Optimize For section hidden. evTargetPlatform.value = 'youtube_shorts' in DOM.
```

**Test: Video Style → evEffectPreset**
```
Setup: Click each Video Style button (Viral, Cinematic, Aggressive, Balanced)
Expected DOM: evEffectPreset.value changes on each click
  Viral → 'viral_fast_01' (verify against backend)
  Cinematic → correct preset string
  Aggressive → correct preset string
  Balanced → 'story_clean_01'
Expected payload: effect_preset = selected preset string
Verify: Before each render click, check document.getElementById('evEffectPreset').value
```

**Test: Subtitle render**
```
Setup: Captions tab → Style = Viral, Position = Top, Subtitles ON
Expected payload:
  add_subtitle = true
  subtitle_style = 'tiktok_bounce_v1'
  sub_margin_v = Math.round((55/100) * 1920) ≈ 1056 (for 9:16)
  sub_x_percent = 50
Verify: evSubPos.value = 55 after clicking Top button
```

**Test: FPS Auto detection**
```
Setup: FPS = Auto, source video with 29.97fps
Expected: evOutputFps.value = 30 after Auto selected
Setup: FPS = Auto, source video with 59.94fps
Expected: evOutputFps.value = 60
Setup: FPS override = 30 FPS
Expected: evOutputFps.value = 30 regardless of source
Verify: Check _ev.sourceFps is populated after editor opens
```

**Test: Reframe creator override**
```
Setup: Frame Ratio = 9:16 (auto-suggests Follow Face → 'subject')
Click Reframe = Center
Expected: evReframeStrategy.value = 'fast_center', dataset.manuallySet = '1'
Then click Frame Ratio = 9:16 again (no change — should not overwrite manual override)
Expected: evReframeStrategy.value = 'fast_center' (unchanged — manuallySet flag honored)
```

**Test: Hidden defaults unchanged**
```
Open editor, do not change any controls, submit render
Verify payload contains:
  frame_scale_y = 106
  playback_speed = 1.07
  loudnorm_enabled = true
  part_order = 'viral'
  cleanup_temp_files = true
  render_profile = 'balanced'
  encoder_mode = 'auto'
  multi_variant = false
  reup_mode = false
```

**Test: Subtitle toggle conditional hide**
```
Setup: Subtitles OFF
Expected: Style dropdown, Position buttons, Fix Subs button hidden
Expected: evSubStyle, evSubPos, evSubColor etc. still in DOM (not removed)
Expected: evAddSubtitle.checked = false in payload
Then: Subtitles ON
Expected: All subtitle controls visible
```

### 7.2 UI/UX Verification Tests

**Test: Tab bar shows 3 tabs only**
Expected: Tab bar shows "Edit", "Captions", "Export". No other tabs visible.

**Test: Edit tab visible controls**
Expected in order: Trim, Video Style (4 cards), Frame Ratio (4 buttons), Reframe (4 buttons), Clip Duration (Shortest/Longest), Output Count, [▸ Advanced]

**Test: Captions tab visible controls**
Expected: Subtitle ON/OFF, Style dropdown, Position (3 buttons), Fix Subs button, live preview callout, [▸ Advanced]

**Test: Export tab visible controls for 9:16**
Expected: Optimize For (TikTok/Reels/Shorts), FPS (Auto/30/60), [▸ Advanced]

**Test: Export tab visible controls for 16:9**
Expected: "Optimized for YouTube Shorts" note (no sub-choice), FPS (Auto/30/60), [▸ Advanced]

**Test: Phase 64 constraint**
```javascript
document.getElementById('evEffectPreset').closest('details') // must return null
document.getElementById('evLoudnormEnabled').closest('details') // must return null
```

**Test: Creator Presets in footer**
Expected: cpBar visible in inspector footer regardless of active tab. Save and Apply presets work.

**Test: Quick Presets in Edit Advanced**
Expected: Edit tab → Advanced → Quick Presets section visible. Clicking TikTok/Podcast/Business/HQ sets evEffectPreset + other fields correctly.

**Test: VideoLocal render end-to-end**
Expected: Local video → Open Editor → set controls → Start Render → no errors.
source_video_path, manual_output_dir unchanged and read correctly.

---

## 8. Definition of Done

The simplification has shipped safely — without breaking render quality — when ALL of the following are true.

### 8.1 UI Completeness

- [ ] Tab bar shows exactly 3 tabs: "Edit", "Captions", "Export"
- [ ] Edit tab: Trim, Video Style (4 options), Frame Ratio (4 options), Reframe (4 options), Clip Duration (Shortest/Longest), Output Count, [▸ Advanced] all visible in that order
- [ ] Captions tab: Subtitle ON/OFF, Style, Position (3 options), Fix Subs, live-preview callout, [▸ Advanced] visible
- [ ] Export tab (9:16): Optimize For (TikTok/Reels/Shorts), FPS (Auto/30/60), [▸ Advanced]
- [ ] Export tab (16:9): "Optimized for YouTube Shorts" note, FPS, [▸ Advanced] — no sub-choice for platform
- [ ] Footer: Creator Presets bar always visible regardless of tab
- [ ] No static "Preview subtitle" text in Captions tab

### 8.2 Functional Correctness

- [ ] Frame Ratio click → evAspectRatio updates → evUpdateAspectRatio() updates frame preview
- [ ] Frame Ratio click → Reframe auto-suggestion: 9:16 → Follow Face highlighted, 16:9 → Center highlighted
- [ ] Frame Ratio click (9:16) → Optimize For section appears with TikTok/Reels/Shorts options
- [ ] Frame Ratio click (16:9) → Optimize For section hidden, evTargetPlatform = 'youtube_shorts' auto-set
- [ ] Optimize For selection → evTargetPlatform and qsStructureBias updated (not evAspectRatio)
- [ ] Reframe manual click → evReframeStrategy updated → manuallySet flag prevents Frame Ratio override
- [ ] Video Style click → evEffectPreset updated → correct preset string per style
- [ ] FPS Auto → evOutputFps = source-matched FPS (or 60 if source FPS unavailable)
- [ ] Position buttons → evSubPos updated with calibrated values
- [ ] Subtitle OFF toggle → all subtitle controls hidden (but remain in DOM)

### 8.3 Payload Integrity

- [ ] Test render (9:16 TikTok): payload contains aspect_ratio=9:16, target_platform=tiktok, structure_bias=hook, reframe_mode=subject, motion_aware_crop=true
- [ ] Test render (16:9 YouTube): payload contains aspect_ratio=16:9, target_platform=youtube_shorts, reframe_mode=center, motion_aware_crop=false
- [ ] effect_preset set to correct value after Video Style selection
- [ ] frame_scale_y = 106 in every render
- [ ] loudnorm_enabled = true in every render
- [ ] evEffectPreset.closest('details') === null (Phase 64)
- [ ] evLoudnormEnabled.closest('details') === null (Phase 64)
- [ ] evSubPosX = 50 in DOM when Captions Advanced is collapsed
- [ ] qsStructureBias in DOM with correct value

### 8.4 No Regressions

- [ ] VideoLocal end-to-end: file picker → Open Editor → render → output file produced
- [ ] Quick Presets (Edit Advanced) still apply evEffectPreset + sub settings correctly
- [ ] Creator Presets save and apply from footer position
- [ ] BatchQueue drag-drop in Edit Advanced accepts files and queues them
- [ ] No JS console errors on editor open
- [ ] No JS console errors on render submit
- [ ] No JS console errors on tab switching (Edit → Captions → Export → Edit loop)

### 8.5 Effect Preset Strings Verified

- [ ] Viral style preset string confirmed against backend render_pipeline.py
- [ ] Cinematic style preset string confirmed against backend render_pipeline.py
- [ ] Aggressive style preset string confirmed against backend render_pipeline.py
- [ ] Balanced → 'story_clean_01' confirmed

---

*End of PHASE UX-1I — Simplification Patch Plan*

*Implementation note: Complete P0 and P1 first. Test with a real render before proceeding to P2.
The P2 changes (new JS behaviors) are the highest risk — each must be tested individually
before combining with the structural P1 changes.*

*Critical finding documented in this plan: The existing "Quick Styles" (Viral/Cinematic/Aggressive/Balanced)
call EditorAiSessions.applyVariant() which is a timeline editing action, NOT a render preset setter.
The Video Style → evEffectPreset write must be ADDED as new behavior in P2. Without this addition,
Video Style selection has no effect on the rendered clip's visual treatment.*
