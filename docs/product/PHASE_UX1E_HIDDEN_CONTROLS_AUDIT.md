# PHASE UX-1E — Hidden Controls & Default Behavior Audit

**Type:** Render safety audit — NOT implementation, NOT redesign
**Date:** 2026-05-20
**Source:** Full code trace — startRenderFromEditor() (editor-view.js:2178–2520), RenderRequest model, render_pipeline.py platform profiles
**Proposed model being audited:**
- EDIT: Trim, Style, AI Picks, Duration, Output Count, Frame Ratio, Smart Framing
- CAPTIONS: Subtitle, Style, Size, Color, Position, Text Layer, Fix Subs
- EXPORT: Platform, Quality, Render

---

## 1. Executive Summary — Simplification Risks

### 1.1 What Is Safe to Hide

The majority of the current editor's complexity is genuinely safe to hide. Most controls have well-calibrated defaults that work correctly for the vast majority of renders without creator intervention:

- Zoom (frame_scale_y = 106%) — permanently hidden; 106% is the correct permanent default
- Playback speed (1.07x) — permanently hidden; platform encoding adjusts it automatically
- Loudness normalization — permanently on; no creator ever needs to turn this off
- Part ordering (viral = best clips first) — correct default; hiding is safe
- Temp cleanup — always true; never needs UI
- Reup mode, BGM, Voice narration — all default off; hiding is safe
- Multi-variant, CTA, Title Overlay — all default off; hiding is safe
- Subtitle X position, Outline — safe in Advanced collapse
- Output FPS (60) — safe in Advanced
- Encoder mode (auto) — safe in Advanced
- Market & Target — all disabled by default; safe in Advanced

### 1.2 What Is NOT Safe to Hide

Three controls are dangerous to remove from the primary flow:

**1. Platform target (target_platform)**
Platform is not just a label — it changes how the render performs:
- TikTok: +8% speed delta, +6 hook_sort_bonus (clip scoring)
- Reels: -6% speed delta
- YouTube Shorts: no adjustments

A TikTok creator who doesn't set platform gets YouTube Shorts defaults. Their output is 8% slower than TikTok-calibrated speed and misses the hook ranking bonus that surfaces attention-grabbing clips. This is a **silent, invisible quality regression** that no creator will know is happening.

**2. Reframe mode (reframe_mode) — for aspect ratio conversion only**
Default is "center" (evReframeStrategy = "fast_center"). When a creator makes vertical content (9:16) from a horizontal source (16:9), center crop frequently cuts off the subject's head or misses the speaker. This produces consistently bad framing in every clip.

This control is safe to hide when no aspect ratio conversion is happening (source and output are same ratio). It is dangerous to hide when conversion is occurring.

**3. Effect preset — indirectly via Quick Style selection**
Every render gets an effect_preset. The JS default is 'story_clean_01'. Clicking a Quick Style card calls evApplyPreset() which sets evEffectPreset to the corresponding preset for that style. If Quick Styles are removed, renamed incorrectly, or fail to call evApplyPreset(), all clips silently default to 'story_clean_01' visual treatment regardless of what the creator intended.

Quick Styles MUST remain in the EDIT tab AND must correctly call evApplyPreset(). This is not the control that's dangerous — it is the dependency on evApplyPreset() that must not break.

### 1.3 Critical Design Warning — Cross-Tab Sync

The proposed model puts **Frame Ratio in EDIT** and **Platform in EXPORT**. This creates a synchronization problem.

Currently: Platform pills (YouTube/TikTok/Reels) call evQsSet() which sets evAspectRatio AND evTargetPlatform in the same tab. Creator sees the change immediately.

In the proposed model: Creator picks Platform in EXPORT → evAspectRatio in EDIT silently updates → creator sees nothing change. If creator is in EDIT tab when this happens, they see no feedback.

**Solution (Section 3.4):** Separate the concepts. Frame Ratio is the creator's explicit format choice. Platform is a secondary optimization bias. Let the creator set Frame Ratio independently. When 9:16 is selected, show a sub-choice: "Optimize for: [TikTok] [Reels] [Both]." Platform no longer auto-sets Frame Ratio — it only sets the encoding bias. This eliminates the cross-tab sync problem.

---

## 2. Control-by-Control Audit

Every render-affecting control traced to its payload field, its default value, and what happens when it is hidden.

---

```
CONTROL: Zoom / Frame Scale Vertical
PAYLOAD FIELD: frame_scale_y
CURRENT PURPOSE: Applies a vertical scale (default 6% zoom) to each clip before crop.
  This removes edge artifacts from the video edges and creates slight zoom energy.
  JS reads: qs('evFrameScaleY').value || 106 (line 2305)
  Clamped to 80–130.

CAN HIDE? YES — permanently

DEFAULT IF HIDDEN: 106 (6% zoom). Backend RenderRequest default is also 106.
  Even if the hidden input is missing from payload, backend applies 106.

QUALITY RISK IF HIDDEN: Low. 106% is the correct permanent value.
  Setting below 100% risks edge artifacts in cropped output.
  Setting above 115% creates excessive zoom that loses context.
  106% is calibrated — creator should never change it.

RECOMMENDED DEFAULT: 106 — hardcoded hidden input, never expose in UI.

WHEN SHOULD UI APPEAR: Never. This is an internal pipeline parameter.
  The hidden input evFrameScaleY must remain in DOM for the payload builder.
```

---

```
CONTROL: Playback Speed
PAYLOAD FIELD: playback_speed
CURRENT PURPOSE: Base speed multiplier applied to every clip before platform delta.
  JS reads: qs('evPlaybackSpeed').value — HTML default "1.07" (editor-view.js:2273)
  Platform then adds its own delta on top:
    TikTok:  +0.08 → final speed = 1.15x
    YouTube: +0.00 → final speed = 1.07x
    Reels:   -0.06 → final speed = 1.01x

CAN HIDE? YES — permanently

DEFAULT IF HIDDEN: 1.07. This is the correct baseline for most content.

QUALITY RISK IF HIDDEN: Low. Creators should NOT manually set this.
  The platform speed_delta handles per-platform calibration automatically.
  If creator sets this manually to 1.0 (natural speed), the output feels sluggish
  compared to platform-native content. 1.07 is the research-calibrated value.

RECOMMENDED DEFAULT: 1.07 — hardcoded hidden input, never expose in UI.

WHEN SHOULD UI APPEAR: Never for typical creators.
  Advanced toggle for power users who understand speed theory.
```

---

```
CONTROL: Platform Target
PAYLOAD FIELD: target_platform
CURRENT PURPOSE: Sets platform-specific encoding biases applied in the render pipeline.
  JS reads: qs('evTargetPlatform')?.value || 'youtube_shorts' (line 2301)

  Platform profiles (from render_pipeline.py):
    TikTok:         speed_delta +0.08, hook_sort_bonus +6
    YouTube Shorts: speed_delta  0.00, hook_sort_bonus  0
    Reels:          speed_delta -0.06, hook_sort_bonus  0

  speed_delta: added to playback_speed before encoding
  hook_sort_bonus: added to viral_score for clips with high hook intensity

CAN HIDE? NO — platform selection must remain visible

DEFAULT IF HIDDEN: youtube_shorts — which applies NO platform biases.
  TikTok creator who doesn't set platform:
    Gets 1.07x speed instead of 1.15x → output feels slower than native TikTok
    Gets 0 hook bonus → viral hook clips don't rank higher → weaker clip selection

QUALITY RISK IF HIDDEN: MEDIUM-HIGH for TikTok/Reels creators.
  The speed delta is visible in the output. TikTok at 1.07x vs 1.15x is 7% slower.
  On short clips (30s), this is 2 seconds — noticeable.
  The hook_sort_bonus affects which clips get exported. Without it, hook-heavy
  clips don't preferentially surface. For TikTok content, hook strength is a
  key performance driver.

RECOMMENDED DEFAULT: Inferred from Frame Ratio when possible:
    16:9 selected → youtube_shorts (default)
    9:16 selected → show Platform sub-choice: [TikTok] [Reels]
    1:1 selected → instagram (or show sub-choice)

WHEN SHOULD UI APPEAR: Always — but as a consequence of Format/Frame Ratio selection.
  See Section 3.4 for the decoupled Platform/Format model.
```

---

```
CONTROL: Reframe Mode / Smart Framing
PAYLOAD FIELDS: reframe_mode + motion_aware_crop
CURRENT PURPOSE: When aspect ratio conversion occurs (e.g., 16:9 source → 9:16 output),
  determines how the crop tracks the subject.
  Options:
    fast_center → reframe_mode='center', motion_aware_crop=false (line 2328-2330)
    motion      → reframe_mode='motion', motion_aware_crop=true
    subject     → reframe_mode='subject', motion_aware_crop=true

CAN HIDE? CONDITIONAL — safe to hide when no aspect ratio conversion; dangerous when conversion is happening

DEFAULT IF HIDDEN: center crop. Center crop cuts a fixed rectangle from the source frame.
  For talking heads and interviews (subject may be off-center), center crop
  frequently frames the subject poorly.
  For B-roll and landscape footage, center crop is usually acceptable.
  For content with multiple subjects, center crop is always wrong.

QUALITY RISK IF HIDDEN: MEDIUM for vertical content creators.
  Creator making 9:16 content from 16:9 source with a talking head that's
  slightly off-center: every clip shows the wrong part of the frame.
  This is visible and frustrating. Creator cannot diagnose without knowing
  the control exists.

RECOMMENDED DEFAULT: Auto (subject tracking if available, motion-aware if not)
  OR: Prompt creator to set Smart Framing when they pick a non-matching Format ratio.

WHEN SHOULD UI APPEAR: Conditional — appears in EDIT tab when Frame Ratio
  implies aspect ratio conversion is happening (i.e., when source format ≠ output format).
  When source is 16:9 and creator picks 9:16: Smart Framing appears.
  When source is 16:9 and creator picks 16:9: Smart Framing hidden (no conversion).
  Implementation: smart framing visibility toggles on format pill click.
  (Source format is known after prepare-source — stored in session/payload.)
```

---

```
CONTROL: Effect Preset
PAYLOAD FIELD: effect_preset
CURRENT PURPOSE: Visual effect / color grading preset applied to each clip.
  JS behavior (line 2339-2349):
    If reup_mode + strong:    effect_preset = 'slay_pop_01'
    If reup_mode + light:     effect_preset = 'story_clean_01'
    If no reup:               effect_preset = qs('evEffectPreset')?.value || 'story_clean_01'

  evEffectPreset is set by evApplyPreset() when creator clicks a Quick Style card.
  If no Quick Style is ever clicked: evEffectPreset is empty → fallback 'story_clean_01'

CAN HIDE? YES — the hidden input should remain, but the UI control should be Quick Styles

DEFAULT IF HIDDEN (no Quick Style selected): 'story_clean_01' visual treatment.
  This is the clean/minimal look. Not wrong, but not what creator may have intended
  if they expected Viral or Cinematic treatment.

QUALITY RISK IF HIDDEN: Low — 'story_clean_01' is a good neutral default.
  BUT: this means Quick Style card selection is the ONLY way to change effect_preset.
  If Quick Styles are removed, renamed incorrectly, or evApplyPreset() breaks,
  ALL renders silently default to 'story_clean_01' regardless of creator intent.

CRITICAL DEPENDENCY: Quick Styles (Viral/Cinematic/Aggressive/Balanced) cards MUST:
  1. Remain in EDIT tab
  2. Call evApplyPreset() correctly on click
  3. Map to the correct effect_preset value for that style
  The hidden evEffectPreset input must remain in DOM.

RECOMMENDED DEFAULT: 'story_clean_01' when no style is selected.
  The creator MUST pick a Style to get any other treatment.

WHEN SHOULD UI APPEAR: Never directly — always via Quick Style cards in EDIT tab.
```

---

```
CONTROL: Loudness Normalization
PAYLOAD FIELD: loudnorm_enabled
CURRENT PURPOSE: Normalizes audio loudness to platform standards.
  JS reads: qs('evLoudnormEnabled')?.value === '1' (line 2353)
  HTML default: "1" (always enabled)
  CRITICAL: Phase 64 constraint — evLoudnormEnabled must NOT be inside any <details> element.
  evApplyPreset() reads it unconditionally by ID.

CAN HIDE? YES — keep always enabled

DEFAULT IF HIDDEN: true. Loudness normalization prevents clips from being too loud
  or too quiet relative to platform expectations. This should NEVER be turned off
  by typical creators.

QUALITY RISK IF HIDDEN: None — default on is correct.
  Risk of SHOWING this control: creator might turn it off, producing clips that
  are too loud/quiet on platform. The control should stay hidden from primary view.

RECOMMENDED DEFAULT: Always on (hardcoded or hidden input with value "1").
  CONSTRAINT: evLoudnormEnabled input must remain in DOM and OUTSIDE any <details>
  wrapper — Phase 64 prohibition.

WHEN SHOULD UI APPEAR: Advanced/Settings section only. Not a first-render decision.
```

---

```
CONTROL: Reup Mode
PAYLOAD FIELDS: reup_mode, reup_overlay_enable, effect_preset (overridden), 
  subtitle_style (overridden), transition_sec, reup_overlay_opacity
CURRENT PURPOSE: Specialized reup workflow — adds overlay effects and changes
  the clip treatment for reposting content from other creators.
  When enabled with 'strong' transform: forces effect_preset='slay_pop_01',
    transition_sec=0.35, overlay_opacity=0.12, subtitle_style='tiktok_bounce_v1'
  When enabled with 'light' transform: forces effect_preset='story_clean_01',
    transition_sec=0.20, overlay_opacity=0.06

CAN HIDE? YES — default off, no effect when hidden

DEFAULT IF HIDDEN: reup_mode=false, all overrides inactive.
  Normal render proceeds without any reup-specific treatment.

QUALITY RISK IF HIDDEN: None — this is an opt-in feature. Hidden = off = normal render.

RECOMMENDED DEFAULT: Off. Advanced section if creator needs reup workflow.

WHEN SHOULD UI APPEAR: Power user Advanced section only. Not a typical render concern.
```

---

```
CONTROL: Structure Bias / AI Picks
PAYLOAD FIELD: structure_bias
CURRENT PURPOSE: Gentle clip ranking re-weight for the AI clip selection algorithm.
  JS reads: document.getElementById('qsStructureBias')?.value || 'balanced' (line 2465)
  Options: 'hook' (More Hook), 'balanced', 'story' (More Story)
  Effect: adjusts internal score weighting — hook= boosts intro-heavy clips,
    story= boosts narrative clips, balanced= no re-weight.

CAN HIDE? PARTIALLY — the control should be visible via "AI Picks" in EDIT tab;
  the qsStructureBias hidden input must remain in DOM.

DEFAULT IF HIDDEN: 'balanced' — no re-weight. Default is safe and neutral.

QUALITY RISK IF HIDDEN: Low. The default produces well-balanced clip selection.
  Hidden means creator loses the ability to steer toward hook-heavy or narrative.
  For creators optimizing for TikTok virality, 'hook' produces better results.
  But 'balanced' is acceptable as a permanent default.

RECOMMENDED DEFAULT: 'balanced' — exposed via AI Picks control in EDIT tab.
  The control is already planned as "AI Picks" in the proposed EDIT tab. Keep it.

WHEN SHOULD UI APPEAR: Always visible in EDIT tab as "AI Picks."
```

---

```
CONTROL: Subtitle Emphasis
PAYLOAD FIELD: subtitle_emphasis
CURRENT PURPOSE: Font-size multiplier for subtitle rendering.
  JS reads: document.getElementById('evSubtitleEmphasis')?.value || 'balanced' (line 2467)
  Options: 'subtle' (smaller), 'balanced', 'aggressive' (larger)
  Used in variant planning (UP13 multi-variant).

CAN HIDE? YES

DEFAULT IF HIDDEN: 'balanced' — correct for most content.

QUALITY RISK IF HIDDEN: Low. 'balanced' subtitle emphasis is appropriate for
  all standard content types.

RECOMMENDED DEFAULT: 'balanced' — hardcoded or hidden input. No UI needed.

WHEN SHOULD UI APPEAR: Advanced section only (or inside multi-variant configuration).
```

---

```
CONTROL: Part Order
PAYLOAD FIELD: part_order
CURRENT PURPOSE: Controls clip export ordering.
  JS reads: qs('evPartOrder').value — HTML default "viral"
  Options: 'viral' (highest-scored clips first), 'timeline' (chronological)

CAN HIDE? YES

DEFAULT IF HIDDEN: 'viral' — highest-scoring clips exported first.
  This is correct for most creators: they want the best clips.

QUALITY RISK IF HIDDEN: Low. 'viral' is the correct default.
  Timeline order is only needed for specific workflows (e.g., training content,
  tutorial series) where chronological order matters.

RECOMMENDED DEFAULT: 'viral' — exposed in Advanced for power users who need timeline.

WHEN SHOULD UI APPEAR: Advanced section only.
```

---

```
CONTROL: BGM (Background Music)
PAYLOAD FIELDS: reup_bgm_enable, reup_bgm_path, reup_bgm_gain
CURRENT PURPOSE: Adds background music track to rendered clips.
  JS reads: qs('evBgmEnable').checked (line 2356) — HTML default: unchecked

CAN HIDE? YES

DEFAULT IF HIDDEN: BGM disabled. No background music added.

QUALITY RISK IF HIDDEN: None — default off is correct for most renders.
  Creator who wants BGM will look for the control.

RECOMMENDED DEFAULT: Off. Accessible in EDIT Advanced or Captions section.

WHEN SHOULD UI APPEAR: Advanced section. When enabled, BGM file/gain/fade appear.
```

---

```
CONTROL: AI Narration / Voice
PAYLOAD FIELDS: voice_enabled, voice_source, voice_language, voice_gender, 
  voice_id, voice_rate, voice_mix_mode, voice_text
CURRENT PURPOSE: Generates AI voice narration synthesized from text or subtitle.
  JS reads: qs('evVoiceEnable')?.checked (line 2365) — HTML default: unchecked

CAN HIDE? YES

DEFAULT IF HIDDEN: Narration disabled. No voice synthesis added.

QUALITY RISK IF HIDDEN: None — default off is correct.

RECOMMENDED DEFAULT: Off. Accessible in EDIT Advanced or AI tab (collapsed).
  When enabled, voice source/language/gender/text controls appear.

WHEN SHOULD UI APPEAR: Collapsed in EDIT tab "More Options" or AI tab.
  Conditional sub-controls (language, gender, text) appear when enabled.
```

---

```
CONTROL: Subtitle Translation
PAYLOAD FIELDS: subtitle_translate_enabled, subtitle_target_language
CURRENT PURPOSE: Translates auto-generated subtitles to a target language.
  JS reads: qs('evSubTranslate')?.checked (line 2386) — HTML default: unchecked

CAN HIDE? YES

DEFAULT IF HIDDEN: Translation disabled.

QUALITY RISK IF HIDDEN: None for primary use case. Creator making content in their
  native language doesn't need translation.

RECOMMENDED DEFAULT: Off. Accessible in CAPTIONS Advanced collapse.
  When enabled, target language selector appears.

WHEN SHOULD UI APPEAR: CAPTIONS tab, collapsed Advanced section. Conditional.
```

---

```
CONTROL: Subtitle X Position (Horizontal)
PAYLOAD FIELD: sub_x_percent
CURRENT PURPOSE: Horizontal centering of subtitle block (5–95%, default 50%).
  JS reads: qs('evSubPosX')?.value (line 2250) — HTML default: 50 (centered)

CAN HIDE? YES

DEFAULT IF HIDDEN: 50% (centered). Correct for 95%+ of use cases.

QUALITY RISK IF HIDDEN: None for typical content. Off-center subtitles are
  an edge case (split-screen, picture-in-picture, etc.).
  evSubPosX must remain in DOM (payload builder reads it).

RECOMMENDED DEFAULT: 50% — hidden in CAPTIONS Advanced collapse.

WHEN SHOULD UI APPEAR: CAPTIONS tab Advanced section only.
```

---

```
CONTROL: Subtitle Outline
PAYLOAD FIELD: sub_outline
CURRENT PURPOSE: Outline/stroke thickness around subtitle text (0–8px, default 3).
  JS reads: qs('evSubOutline').value (line 2234) — HTML default: 3

CAN HIDE? YES

DEFAULT IF HIDDEN: 3px — appropriate readability for most content.

QUALITY RISK IF HIDDEN: Low. 3px is correct for most fonts and background types.
  Creators using very light or custom fonts might need to adjust.

RECOMMENDED DEFAULT: 3px — hidden in CAPTIONS Advanced collapse.

WHEN SHOULD UI APPEAR: CAPTIONS tab Advanced section only.
```

---

```
CONTROL: Render Quality / Output Profile
PAYLOAD FIELD: render_profile
CURRENT PURPOSE: Encoding quality vs speed tradeoff.
  JS reads: qs('evRenderProfile').value (line 2314) — HTML default: "balanced"
  Options: 'fast' (draft), 'balanced', 'quality', 'best'

CAN HIDE? YES — but this is a good candidate for EXPORT tab visibility

DEFAULT IF HIDDEN: 'balanced' — good quality/speed tradeoff for most creators.

QUALITY RISK IF HIDDEN: Low for primary use. Creator who needs 'best' quality
  for final publish, or 'fast' for quick review, loses this control.
  Hiding means all renders use balanced encoding.

RECOMMENDED DEFAULT: 'balanced' — visible in EXPORT tab.
  This is a genuinely useful control for the creator: "how good should the output be?"
  One of the few technical controls that has a clear creator-language meaning:
  Fast Draft / Balanced / High Quality / Best.

WHEN SHOULD UI APPEAR: Always visible in EXPORT tab. 4 options, clear labels.
```

---

```
CONTROL: Output FPS
PAYLOAD FIELD: output_fps
CURRENT PURPOSE: Output video frame rate.
  JS reads: qs('evOutputFps').value || 60 (line 2298) — HTML default: 60
  Options: 30, 60

CAN HIDE? YES

DEFAULT IF HIDDEN: 60fps — correct for TikTok, YouTube Shorts, Reels.
  30fps may be needed for certain archival or file-size concerns.

QUALITY RISK IF HIDDEN: None for typical creator. 60fps is platform-optimal.

RECOMMENDED DEFAULT: 60fps — hidden in EDIT Advanced.
  Creator who specifically needs 30fps (older platforms, file size) can find it there.

WHEN SHOULD UI APPEAR: EDIT tab Advanced section only.
```

---

```
CONTROL: Encoder Mode (Device)
PAYLOAD FIELD: encoder_mode
CURRENT PURPOSE: Hardware encoder selection.
  JS reads: qs('evRenderDevice').value (line 2311) — HTML default: "auto"
  Options: 'auto' (GPU if available), 'cpu', 'gpu' (nvenc)

CAN HIDE? YES

DEFAULT IF HIDDEN: 'auto' — uses GPU if available, falls back to CPU.

QUALITY RISK IF HIDDEN: None. Auto-selection is always correct.
  Manual selection is only needed when GPU has issues or CPU is explicitly required.

RECOMMENDED DEFAULT: 'auto' — hidden in EDIT Advanced or Settings.

WHEN SHOULD UI APPEAR: EDIT tab Advanced section (Settings) only.
```

---

```
CONTROL: Source Volume
PAYLOAD FIELD: edit_volume
CURRENT PURPOSE: Multiplier for source audio volume (0–200%, default 100%).
  JS reads: qs('evVolume').value / 100 (line 2222)

CAN HIDE? YES

DEFAULT IF HIDDEN: 100% (1.0) — no volume change.

QUALITY RISK IF HIDDEN: Low. Most source footage has appropriate audio levels.
  Loudness normalization (always-on) handles platform-level normalization anyway.
  Creator who has very quiet or very loud footage needs this control.

RECOMMENDED DEFAULT: 100% — hidden in EDIT Advanced or Settings.

WHEN SHOULD UI APPEAR: EDIT tab Advanced or Settings section.
```

---

```
CONTROL: Multi-Variant Render
PAYLOAD FIELD: multi_variant
CURRENT PURPOSE: Creates 3 stylistic variants (aggressive, balanced, story_first) in one render job.
  JS reads: document.getElementById('evMultiVariant')?.checked (line 2300) — default: unchecked

CAN HIDE? YES

DEFAULT IF HIDDEN: false — single render, no variants.

QUALITY RISK IF HIDDEN: None — variant rendering is an opt-in power feature.

RECOMMENDED DEFAULT: Off — EDIT Advanced only.

WHEN SHOULD UI APPEAR: EDIT tab Advanced section (or Export Advanced).
```

---

```
CONTROL: Market & Target (combined_scoring_enabled, adaptive_scoring_enabled, auto_best_export_enabled)
PAYLOAD FIELDS: market_viral.target_market, hook_apply_enabled, combined_scoring_enabled,
  adaptive_scoring_enabled, auto_best_export_enabled, auto_best_export_count
CURRENT PURPOSE: Regional targeting and viral scoring optimization.
  All default to false/disabled when mvGetState() returns empty values.

CAN HIDE? YES

DEFAULT IF HIDDEN: All disabled. Normal clip scoring without regional biases.

QUALITY RISK IF HIDDEN: None for primary use. Regional targeting is a professional
  feature for creators optimizing for specific markets (US, JP, EU).

RECOMMENDED DEFAULT: All off — EDIT Advanced only.

WHEN SHOULD UI APPEAR: EDIT tab Advanced section.
```

---

```
CONTROL: Creator Assets (Logo, Intro, Outro, Music Profile, Brand Subtitle)
PAYLOAD FIELDS: asset_logo_path, asset_intro_path, asset_outro_path, 
  asset_music_profile, asset_brand_subtitle
CURRENT PURPOSE: Creator branding overlays and brand-consistent subtitle style.
  Default: all null (no assets applied).

CAN HIDE? YES

DEFAULT IF HIDDEN: No assets, no branding. Clean output.

QUALITY RISK IF HIDDEN: None — opt-in feature.

RECOMMENDED DEFAULT: All null — EDIT Advanced only.

WHEN SHOULD UI APPEAR: EDIT tab Advanced section.
```

---

```
CONTROL: CTA (Call to Action)
PAYLOAD FIELDS: cta_enabled, cta_type
CURRENT PURPOSE: Appends call-to-action text overlay at end of clips.
  Default: cta_enabled=false.

CAN HIDE? YES

DEFAULT IF HIDDEN: No CTA.

QUALITY RISK IF HIDDEN: None — opt-in feature.

RECOMMENDED DEFAULT: Off — EDIT Advanced only.

WHEN SHOULD UI APPEAR: EDIT tab Advanced section. cta_type appears when enabled.
```

---

```
CONTROL: Title Overlay
PAYLOAD FIELDS: add_title_overlay, title_overlay_text
CURRENT PURPOSE: Adds text title overlay to beginning of clips.
  Default: add_title_overlay=false.

CAN HIDE? YES

DEFAULT IF HIDDEN: No title overlay.

QUALITY RISK IF HIDDEN: None — opt-in feature.

RECOMMENDED DEFAULT: Off — EDIT Advanced only.

WHEN SHOULD UI APPEAR: EDIT Advanced. title_overlay_text input appears when enabled.
```

---

```
CONTROL: Cleanup Temp Files
PAYLOAD FIELD: cleanup_temp_files
CURRENT PURPOSE: Removes temporary working files after render completes.
  JS reads: qs('evCleanupTemp').checked — HTML default: checked (true)

CAN HIDE? YES — permanently

DEFAULT IF HIDDEN: true — always clean up. This is always correct.

QUALITY RISK IF HIDDEN: None. Leaving temp files active just wastes disk space.

RECOMMENDED DEFAULT: Always true. No UI. No Advanced entry. Backend-only behavior.

WHEN SHOULD UI APPEAR: Never.
```

---

## 3. Default Behavior Design

When a control is hidden, this is what the render produces automatically.

### 3.1 Visual / Encoding Defaults

| Control | Hidden Default | Creator Gets Without Touching Anything |
|---|---|---|
| Zoom (frame_scale_y) | 106% vertical scale | Slight zoom, clean crop, no edge artifacts |
| Playback speed | 1.07x base | Slightly snappier pace — platform adjusts further |
| Effect preset | 'story_clean_01' (unless Quick Style selected) | Clean minimal visual treatment |
| Reframe mode | Center crop | Fixed-rectangle crop — ONLY safe if no aspect ratio conversion |
| Loudness normalization | Always on | Platform-normalized audio levels |
| Part ordering | Viral (best-scored first) | Best clips exported first |
| Output FPS | 60fps | Smooth video for all major platforms |
| Render quality | Balanced | Good quality, reasonable encode time |
| Encoder mode | Auto (GPU if available) | Fastest available hardware |
| Subtitle emphasis | Balanced | Standard subtitle font sizing |
| Structure bias | Balanced | Equal weight hook and story clips |

### 3.2 Feature Defaults (All Off)

| Feature | Hides As | Creator Gets Without Enabling |
|---|---|---|
| BGM | Off | No background music |
| AI Narration | Off | No voice synthesis |
| Subtitle Translation | Off | Subtitles in source language |
| Reup Mode | Off | Standard render, no overlay |
| Multi-variant | Off | Single render, single style |
| CTA | Off | No call-to-action overlay |
| Title Overlay | Off | No title card |
| Creator Assets | All null | No logo, intro, outro, or branding |
| Market & Target | All disabled | Standard clip scoring |
| Auto Best Export | Off | Max clips setting controls output count |
| Combined/Adaptive Scoring | Off | Standard viral scoring only |

### 3.3 Smart Platform Default — The Only Non-Trivial Default

When Platform is not set: target_platform = 'youtube_shorts'
- For creators making 9:16 content for TikTok: this is WRONG
- Speed will be 1.07x instead of 1.15x (TikTok bias missing)
- Hook sort bonus = 0 (TikTok bias missing)

**Recommended smart default for Platform:**
```
IF Frame Ratio = 9:16:
  Show Platform sub-choice: [TikTok ✓] [Reels]
  Default: TikTok (most 9:16 content is TikTok first)
  Writing: evTargetPlatform.value = 'tiktok'

IF Frame Ratio = 16:9:
  No sub-choice needed
  Writing: evTargetPlatform.value = 'youtube_shorts'

IF Frame Ratio = 1:1 or 3:4:
  Show Platform sub-choice: [Reels ✓] [Both]
  Default: Reels (Instagram-native format)
  Writing: evTargetPlatform.value = 'instagram_reels'
```

This gives correct platform defaults with zero extra decisions for YouTube creators (16:9 = youtube_shorts automatically) and one clear sub-choice for vertical/square creators.

---

## 4. Conditional UI Rules

Controls that should only appear when they are relevant.

### 4.1 Format/Ratio Triggers Smart Framing

```
Creator picks Frame Ratio:
  9:16 → Smart Framing appears: [Auto] [Follow Face] [Follow Person] [Center]
           Platform sub-choice appears: [TikTok] [Reels]
  3:4  → Smart Framing appears
           Platform sub-choice appears: [Reels]
  1:1  → Smart Framing appears
           Platform sub-choice appears: [Reels] (or both)
  16:9 → Smart Framing hidden (no conversion needed)
          Platform is implicitly YouTube Shorts

Why: Smart Framing only matters when the output aspect ratio differs from
the source. When they match, center crop and smart crop are equivalent.
```

### 4.2 Features That Generate Sub-Controls

```
BGM enabled → BGM file picker, volume slider, fade control appear
AI Narration enabled → source selector, language, gender, rate, text appear
Subtitle Translate enabled → target language selector appears
CTA enabled → CTA type selector appears
Title Overlay enabled → title text input appears
Reup Mode enabled → transform preset (light/strong) appears
```

### 4.3 Subtitle Controls Are Invisible When Subtitles Off

```
Subtitle ON/OFF toggle:
  OFF → All subtitle style controls hidden
       (Style, Font, Size, Color, Highlight, Position, Fix Subs all hidden)
  ON  → All subtitle style controls visible
```

### 4.4 Text Layers Show Content When Layers Exist

```
Text Layers section:
  No layers added → collapsed section with "+" add button
  Layers exist → collapsed section shows layer count, expands to show layer list
  The global ON/OFF toggle (from UX1D proposal) is NOT appropriate —
  the "+" add workflow is correct for this feature
```

---

## 5. Dangerous Oversimplification Risks

Explicit list of quality regressions that happen when controls are hidden without proper defaults or conditional visibility.

### 5.1 Bad Crops — MEDIUM RISK

**What causes it:** reframe_mode defaults to 'center' when Smart Framing is hidden.

**What creator sees:** Every clip has the subject cut off or off-center. Talking head footage shows a wall instead of a face. Content with off-center subjects looks poorly framed in every clip.

**Who is affected:** Creators making 9:16 (vertical) content from 16:9 (horizontal) source.

**Why it's dangerous:** Creator cannot diagnose the problem without knowing Smart Framing exists. They will assume the AI made bad clip selections, not that the framing algorithm is wrong.

**Prevention:** Smart Framing must appear conditionally when Format conversion is occurring (9:16 selected with 16:9 source). Default: Auto or subject-tracking.

### 5.2 TikTok Under-Performance — MEDIUM RISK

**What causes it:** target_platform defaults to 'youtube_shorts'. TikTok creators don't get the +8% speed delta or +6 hook ranking bonus.

**What creator sees:** Clips feel slightly slow compared to native TikTok content. The AI doesn't preferentially select attention-grabbing hook clips.

**Why it's dangerous:** The speed difference (1.07x vs 1.15x) is subtle but audible. The hook ranking difference is invisible — creator just notices their clips don't feel as viral as expected.

**Prevention:** Platform sub-choice appears when creator picks 9:16 format. TikTok is the default for 9:16. YouTube Shorts is the default for 16:9.

### 5.3 Wrong Visual Treatment — LOW-MEDIUM RISK

**What causes it:** If Quick Styles (EDIT tab) fail to call evApplyPreset() correctly, all clips default to 'story_clean_01' effect preset regardless of what creator selected.

**What creator sees:** Clips have a clean, minimal look even when they chose "Viral." No visible error — just wrong visual energy.

**Why it's dangerous:** Silent failure. Creator submitted "Viral" style but gets "Clean" output. The error is in the evApplyPreset() call chain, not in any visible control.

**Prevention:** Test evApplyPreset() → evEffectPreset write → payload.effect_preset chain before shipping. Log which effect preset is applied in the render event log.

### 5.4 Unnatural Pacing — LOW RISK (Contextual)

**What causes it:** playback_speed = 1.07 is correct for most content. But spoken-word content (podcast clips, interviews) at 1.07x sounds slightly rushed. If creator doesn't have access to speed control, they cannot adjust.

**What creator sees:** Interview clips sound slightly sped-up compared to natural conversation pace.

**Prevention:** Accept 1.07 as a permanent hidden default. The Advanced section can expose speed control for power users who notice this. Most creators will not notice at 1.07x.

### 5.5 Duplicate-Looking Output — LOW RISK

**What causes it:** Without multi-variant rendering, every render with the same settings produces similar-looking clips.

**What creator sees:** Over multiple render sessions, clips begin to look identical (same color grade, same energy level, same subtitle style). Creator feels their content is getting repetitive.

**Prevention:** Multi-variant is already hidden in Advanced. This is acceptable. Creator who wants variation can use it. Creators who don't care (most) are fine with consistent output.

### 5.6 Subtitle Failures — LOW RISK

**What causes it:** If evSubPosX disappears from DOM (X position slider hidden without keeping input in DOM), sub_x_percent is never set or defaults incorrectly.

**What creator sees:** Subtitles appear off-center even though creator expected center.

**Prevention:** evSubPosX must remain in DOM with value 50. The slider is hidden in CAPTIONS Advanced, but the input is still read at line 2250. The hidden input must exist.

---

## 6. True Minimal Safe Model

After all findings, this is the minimum editor that preserves render quality.

### 6.1 Final Tab Structure

```
TAB BAR:   [ Edit ]  [ Captions ]  [ Export ]
FOOTER:    [status]  [▶ Start Render]
```

---

**TAB 1 — EDIT**

```
ALWAYS VISIBLE:

  Trim:
  [in ──────────────●────── out]   (in/out sliders)

  Style:
  [Viral 🔥]  [Cinematic 🎬]  [Aggressive ⚡]  [Balanced ⚖️]

  AI Picks:
  [Hook-Heavy]  [Balanced]  [Story Arc]
  "Which moments the AI selects from your footage"

  Format:
  [9:16 ↕]  [1:1 □]  [16:9 ↔]  [3:4 ▭]

  ↳ Platform (CONDITIONAL — appears only when 9:16 or 1:1 or 3:4 selected):
     "Optimize for:"  [TikTok]  [Reels]
     (hidden when 16:9 selected — YouTube Shorts implied)

  ↳ Smart Framing (CONDITIONAL — appears only when aspect ratio conversion occurs):
     [Auto ✓]  [Follow Face]  [Follow Person]  [Center]
     (hidden when output format = source format)

  Duration:
  Shortest [61] s  ——  Longest [180] s

  Clips:  [6]

COLLAPSED — "▼ Advanced":
  Render quality:   [Fast]  [Balanced ✓]  [Good]  [Best]
  BGM:              [ ]  [file]  [volume]  [fade]
  Source volume:    [slider]
  Output FPS:       [60 ▾]
  Encoder:          [Auto ▾]
  Multi-variant:    [ ]
  CTA:              [ ]  → [type select]
  Title Overlay:    [ ]  → [text input]
  Creator Assets:   [Logo]  [Intro]  [Outro]  [Music profile]
  Part order:       [viral ▾]
  ──────────────────────────────
  AI Narration:     [ ]  → [source] [language] [gender] [text]
  Text Layers:      [+ Add Layer]  [layer list if layers exist]
  AI Edit Actions:  [collapsed group]
  Edit History:     [collapsed group]
  Creator Memory:   [collapsed group]
  AI Chat:          [conversational panel]
  ──────────────────────────────
  Batch Mode:       [ ]  [URLs]
  Market & Target:  [group]
  Expert Preset:    [— Manual — ▾]
  Quick Presets:    [▸ Starting points (4)]
  ──────────────────────────────
  Batch Queue:      [drag-drop zone]
  Editor Performance: [health banner + toggles]
```

---

**TAB 2 — CAPTIONS**

```
ALWAYS VISIBLE:

  Subtitles:  [ ON ●──── ]  toggle

  ↳ ALL subtitle controls hidden when toggle is OFF

  Style:   [Viral — Fast TikTok/Reels captions ▾]

  Size:    [──────●──────]  72px

  Color [  ]   Highlight [  ]

  Position:  [Bottom ✓]  [Middle]  [Top]

  [✦ Fix Subs]

  ↑ Live preview is in the video on the left.

COLLAPSED — "▼ Advanced":
  Font:                   [Bungee (Viral 🔥) ▾]
  Horizontal position:    [slider]  50%
  Outline:                [slider]  3px
  Translate:              [ ]  → [language ▾]
```

---

**TAB 3 — EXPORT**

```
ALWAYS VISIBLE:

  Quality:
  [Fast Draft]  [Balanced ✓]  [High Quality]  [Best]
  "Render speed vs quality"

  [▶ Start Render]

  ↳ Creator Presets (below or adjacent to Render button):
     [— No Preset — ▾]  [Save]
```

---

### 6.2 Visible Decision Count

| Tab | Visible decision groups | Controls |
|---|---|---|
| EDIT | 7 always-visible + 2 conditional | Trim, Style, AI Picks, Format, Duration, Clips, [Platform sub-choice, Smart Framing] |
| CAPTIONS | 6 (when subtitles ON) | ON/OFF, Style, Size, Color, Position, Fix Subs |
| EXPORT | 1 + render button | Quality |
| **Total** | **~13–15** | Conditional controls reduce burden for 16:9 creators |

For 16:9 YouTube creators (no aspect ratio conversion):
- Smart Framing hidden (no conversion)
- Platform hidden (YouTube Shorts implied)
- **Visible decisions: ~11**

For 9:16 TikTok creators:
- Smart Framing visible
- Platform sub-choice visible (TikTok / Reels)
- **Visible decisions: ~13–14**

### 6.3 What Disappears Completely (Safe Hidden Defaults)

| Control | Safe Default | Never Needs UI |
|---|---|---|
| Zoom (frame_scale_y) | 106% | Always correct — never expose |
| Playback speed | 1.07x (platform-adjusted) | Always correct — never expose |
| Loudness normalization | Always on | Always correct — never expose |
| Part ordering | Viral (best first) | Always correct for 95%+ |
| Temp cleanup | Always on | Always correct — never expose |
| Subtitle X position | 50% (centered) | DOM input stays; slider hidden in Advanced |
| Subtitle emphasis | Balanced | DOM input stays; never needs primary UI |
| Structure bias default | Balanced | Exposed via AI Picks — not direct |
| Encoder mode | Auto | Correct for all modern hardware |
| Reup overlay opacity | 0.08 (when reup off = irrelevant) | Never needs primary UI |

---

## 7. Implementation Safety

### 7.1 What Can Break

**Critical: evEffectPreset dependency chain**
The effect_preset in the render payload is set by `qs('evEffectPreset')?.value || 'story_clean_01'` when reup is off (line 2349). If:
- evEffectPreset input disappears from DOM: fallback is 'story_clean_01' for all renders
- evApplyPreset() doesn't call correctly on Quick Style click: evEffectPreset stays empty → fallback
- Quick Style rename doesn't map to correct preset ID: wrong visual treatment

Test: After every Quick Style card click, verify evEffectPreset.value has changed to the expected preset string.

**Critical: evLoudnormEnabled must stay outside `<details>`**
Phase 64 constraint — unconditionally read by evApplyPreset(). Wrapping in any collapse breaks it.

**Critical: evSubPosX must remain in DOM**
The horizontal position slider is hidden in CAPTIONS Advanced. But the hidden input (or slider at 50%) must exist in DOM. Line 2250 reads it unconditionally.

**Critical: Platform → evTargetPlatform must still be written**
If Platform selection is a sub-choice that only appears for 9:16 creators, the JS must still write the correct value to evTargetPlatform even when the selector is hidden for 16:9 creators. Default write: 'youtube_shorts' for 16:9, 'tiktok' for 9:16 default.

**Critical: qsStructureBias input must remain in DOM**
Line 2464–2465 reads it for structure_bias payload field. AI Picks buttons must write to this input.

**Medium: Smart Framing conditional show/hide**
The visibility toggle (show Smart Framing when format ≠ 16:9) must write correct values when hidden. When Smart Framing is hidden (16:9 selected), reframe_mode must still be set to 'center' and motion_aware_crop to false.

**Medium: EditorAudioRuntime.onTabActivate() trigger**
When Audio controls move to EDIT Advanced (no longer a standalone tab), EditorAudioRuntime.onTabActivate() must fire on Edit tab entry or when the Advanced section is opened.

**Medium: EditorPerformanceRuntime triggers**
When Editor Performance moves to EDIT Advanced, EditorPerformanceRuntime.onTabActivate() / onTabDeactivate() triggers must move to Edit tab entry/exit.

### 7.2 Required Verifications Before Implementation

- [ ] Confirm what evApplyPreset() writes to evEffectPreset for each Quick Style (Viral/Cinematic/Aggressive/Balanced). Document the mapping.
- [ ] Confirm evLoudnormEnabled position in DOM after restructuring — must be outside all `<details>` elements.
- [ ] Confirm evSubPosX input exists and reads 50 when the slider is in CAPTIONS Advanced (collapsed by default).
- [ ] Confirm what backend does with blank evTargetPlatform — what is the actual default platform behavior?
- [ ] Confirm Smart Framing options map correctly: 'fast_center' → reframe_mode='center', 'motion' → motion_aware_crop=true, 'subject' → reframe_mode='subject'. Verify the evReframeStrategy → payload mapping at editor-view.js:2328-2330.
- [ ] Test Platform sub-choice (TikTok/Reels) for 9:16: verify evTargetPlatform is written correctly.
- [ ] Confirm Platform sub-choice for 16:9 writes 'youtube_shorts' even when no UI is shown.
- [ ] Verify EditorAudioRuntime.onTabActivate() — does it lazy-initialize audio system or just refresh UI state? Determines when it must fire.
- [ ] Confirm no CSS positional selectors depend on the current tab structure (.insp-tab position, adjacent sibling selectors).

### 7.3 Recommended Implementation Order

**Phase A — Labels and hidden inputs only (zero functional risk):**
1. Rename tab button text to "Edit", "Captions", "Export"
2. Rename field labels: Shortest clip, Longest clip, Clips, AI Picks
3. Add title= tooltips to AI Picks options (what they do)
4. Smart Framing tooltip explanations

**Phase B — Attribute moves, low risk:**
1. Merge AI/Words content into Edit tab (data-insp-panel changes)
2. Move Editor Performance to Edit Advanced (data-insp-panel change, no runtime change)
3. Move Batch Queue to Edit Advanced (ID-based, no runtime change)
4. Static preview removal + live-preview callout in Captions tab
5. X Pos slider → CAPTIONS Advanced (input stays in DOM)
6. Outline slider → CAPTIONS Advanced (input stays in DOM)
7. Translate → CAPTIONS Advanced
8. Market & Target → Edit Advanced
9. Quick Presets → Edit Advanced
10. Creator Presets (cpBar) → footer / Edit Advanced

**Phase C — Structural changes, medium risk:**
1. Add Platform sub-choice conditional: show TikTok/Reels when 9:16 selected
2. Add Smart Framing conditional: show when format ≠ source format
3. Move Audio controls to Edit Advanced — update EditorAudioRuntime trigger
4. Move Render Settings to Edit Advanced — update EditorPerformanceRuntime triggers
5. Verify evTargetPlatform written correctly for all format choices
6. Position (Bottom/Middle/Top) buttons: define percentage mappings, implement button→evSubPos write
7. Export tab reduction: Quality selector + Render button only
8. Subtitle ON/OFF conditional: hide all subtitle controls when toggle is OFF

**Phase D — Edge case verification:**
1. evEffectPreset chain test for all Quick Styles
2. Platform encoding bias test for TikTok vs YouTube renders
3. Smart Framing test with actual aspect ratio conversion footage
4. evSubPosX default 50 verification with Captions Advanced collapsed
5. evLoudnormEnabled DOM position verification

---

*End of Audit — PHASE UX-1E*
*Finding: Most simplification is safe. Three risks require active mitigation: Platform target (resolve via Format-conditional sub-choice), Smart Framing (conditional visibility), Effect preset chain (test evApplyPreset mapping).*
*Next step if direction approved: Phase A implementation — tab renames and label changes. Zero functional risk.*
