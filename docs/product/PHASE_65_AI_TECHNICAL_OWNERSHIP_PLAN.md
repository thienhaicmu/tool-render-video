# PHASE 65 — AI TECHNICAL OWNERSHIP PLAN
## Auto-Default Pass: Technical Decisions the Engine Should Own

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 64 Simple Mode — COMPLETE, zero regressions
**Plan date:** 2026-05-19
**Planning only — no implementation in this session**

---

## 1. EXECUTIVE SUMMARY

Phase 63 removed developer noise. Phase 64 removed creator noise. Phase 65 removes **technical thinking**.

The Semi-Opus Hybrid goal is: creator thinks "what outcome do I want?", not "how should the engine work?". That means every purely technical setting — settings that have a clearly correct value given the creator's intent — should be owned by the engine, not the creator.

This audit finds:

**Good news:** Most technical settings are already auto-owned. Playback speed, source quality, part order, frame scale, loudness normalization, subtitle tone, and structure bias all run automatically. The engine already handles more than the UI suggests.

**Real gap:** One critical gap exists — **Platform selection does not auto-set Aspect Ratio**. A creator who selects "TikTok" in the QS Bar still gets a 3:4 aspect ratio (wrong for TikTok) unless they open Advanced or used a Quick Preset card. Phase 64 collapsing the preset cards made this gap worse. This must be fixed.

**One dead control:** The Transform preset in Render Settings has zero effect on normal renders. It only influences Reup Mode (a hidden feature). It should become a hidden input.

**Everything else:** Device/FPS/Reframe Mode/Output Profile/Min-Max Clip all have legitimate creator-facing value as overrides. They stay visible in their current collapsed locations.

**Phase 65 implementation: 2 commits, 2 files.**

---

## 2. CURRENT TECHNICAL SURFACE

### Complete inventory of technical controls after Phase 64

#### A. Already fully auto-owned (hidden, engine decides)

These controls exist in the DOM as hidden inputs or in the `evEditorCompat` div. Creators never see them. They are documented here to confirm the engine's ownership is already correct.

| ID | Location | Default | What it controls | Status |
|---|---|---|---|---|
| `evPlaybackSpeed` | `evEditorCompat` (hidden div) | 1.07× | Speech tightening — subtle 7% speedup | AUTO ✓ |
| `evSourceQualityMode` | `evEditorCompat` (hidden div) | standard_1080 | Source decode resolution | AUTO ✓ |
| `evPartOrder` | `evEditorCompat` (hidden div) | viral | Clip sort order — best first | AUTO ✓ |
| `evFrameScaleY` | `evEditorCompat` (hidden div) | 106 | Vertical frame zoom (6% crop guard) | AUTO ✓ |
| `evCleanupTemp` | `evEditorCompat` (hidden div) | checked | Temp file cleanup | AUTO ✓ |
| `evLoudnormEnabled` | Hidden input outside `<details>` | 1 (ON) | Audio loudness normalization | AUTO ✓ (Phase 63) |
| `mvSubtitleTone` | Hidden inside collapsed `<details>` | clean | Subtitle font tone | AUTO ✓ (Phase 63) |
| `evSubtitleEmphasis` | Hidden inside `qsAdvBody` | balanced | Subtitle size emphasis | AUTO ✓ (Phase 63) |
| `qsStructureBias` | Hidden input in `qsBar` | balanced | Clip pacing bias | AUTO ✓ (driven by pills) |
| `evTargetPlatform` | Hidden select in `qsAdvBody` | youtube_shorts | Platform signal to render pipeline | AUTO ✓ (driven by pills) |

**Assessment:** Engine already owns 10 technical parameters without any creator interaction. The product is already more "semi-Opus" than the visible UI suggests.

#### B. Visible in collapsed sections (Advanced / Render Settings)

These controls are accessible but require the creator to open a collapsed section.

| ID | Section | Default | Options | Creator need |
|---|---|---|---|---|
| `evAspectRatio` | qsAdvBody (Advanced) | 3:4 Vertical | 3:4 / 9:16 / 1:1 | **Critical override — currently disconnected from Platform pills** |
| `evRenderProfile` | qsAdvBody (Advanced) | Balanced | Fast Draft / Balanced / Quality / Best | Quality/speed tradeoff — real choice |
| `evMinPart` | qsAdvBody (Advanced) | 70s | 20–600 | Clip length bounds |
| `evMaxPart` | qsAdvBody (Advanced) | 180s | 30–900 | Clip length bounds |
| `evOutputPreset` | qsAdvBody (Advanced) | Manual/Custom | 5 expert profiles | Power-user shortcut |
| `evRenderDevice` | Render Settings (collapsed) | Auto (GPU) | Auto / CPU / GPU force | Troubleshoot/override |
| `evOutputFps` | Render Settings (collapsed) | 60 fps | 30 / 60 | Quality/speed tradeoff |
| `evTransformPreset` | Render Settings (collapsed) | Slightly Different | None / Slight / Strong | **Zero effect for normal renders — dead control** |
| `evReframeStrategy` | Render Settings (collapsed) | Fast Center Crop | Fast / Motion / Subject | Quality/speed tradeoff |

#### C. Visible in primary area (not in any collapsed section)

| ID | Location | Default | Notes |
|---|---|---|---|
| `evMaxExportParts` | Above `qsAdvBody` | 0 (no limit) | Primary creator decision — correctly visible |

#### D. Editor performance controls (Export tab, visible section)

| ID | Location | Default | Notes |
|---|---|---|---|
| `edPerfHoverPreview` | Editor Performance section | checked | Timeline hover video previews |
| `edPerfFilmstrip` | Editor Performance section | checked | Timeline filmstrip thumbnails |
| `edPerfWaveform` | Editor Performance section | checked | Waveform audio lane |

These are editor UI controls, not render controls. They default to ON. Creators only need them if the editor is slow. Currently visible — addressed in Section 8.

---

## 3. AUTO BY DEFAULT MATRIX

Controls that should be fully owned by the engine, with no creator UI involvement.

### 3A. Already auto — confirmed correct

| Control | Engine default | Creator impact of wrong default | Trust risk |
|---|---|---|---|
| Playback speed 1.07× | Good — tightens speech naturally | If 1.0×, clips feel slightly slow | LOW — already auto |
| Source quality standard_1080 | Good — fast and sufficient | If best_available, slower renders | LOW — already auto |
| Part order viral | Good — best content first | If timeline, random-feeling order | MEDIUM — already auto |
| Frame scale Y 106 | Good — prevents black bars | If 100, may letterbox | LOW — already auto |
| Loudness norm ON | Good — consistent volume | If OFF, clips sound uneven | MEDIUM — already auto (Phase 63) |

### 3B. Newly recommended for AUTO (Phase 65 actions)

#### AUTO-1: Platform → Aspect Ratio (JS change, `editor-view.js`)

**Problem:** `evQsSet('platform', 'tiktok')` sets `evTargetPlatform = 'tiktok'` but does NOT update `evAspectRatio`. The render pipeline backend reads `payload.aspect_ratio` directly from `evAspectRatio.value` — it does NOT auto-derive aspect ratio from target platform (confirmed in `render_pipeline.py` line 2151 equivalent, line 651: `getattr(payload, "aspect_ratio", "3:4")`).

**Current result:** Creator selects TikTok → renders at 3:4 aspect ratio (wrong for TikTok, which expects 9:16).

**This gap was present before Phase 64 but was masked** by the Quick Preset cards being always visible. A creator who clicked "TikTok/Reels" preset got 9:16. A creator who used Platform pills without the preset got 3:4. Phase 64 collapsing the preset cards removed the implicit fix.

**Recommended mapping:**

| Platform pill | Sets `evAspectRatio` to | Rationale |
|---|---|---|
| YouTube | 3:4 | YouTube Shorts accepts 3:4 and 9:16; 3:4 is wider-safe |
| TikTok | 9:16 | TikTok enforces 9:16; 3:4 produces pillarbox/black bars |
| Reels | 9:16 | Instagram Reels enforces 9:16 |

**Implementation:** In `evQsSet()` function, add aspect ratio update inside the `group === 'platform'` branch:

```javascript
function evQsSet(group, val) {
  if (group === 'platform') {
    const el = document.getElementById('evTargetPlatform');
    if (el) el.value = val;
    // Auto-link aspect ratio to platform intent
    const ar = document.getElementById('evAspectRatio');
    if (ar) {
      ar.value = (val === 'tiktok' || val === 'instagram_reels') ? '9:16' : '3:4';
      if (typeof evUpdateAspectRatio === 'function') evUpdateAspectRatio();
    }
  } else if (group === 'structure') {
    // ... existing code unchanged
  }
  evSyncQsBar();
}
```

**Trust risk:** LOW. The mapping is unambiguous for TikTok and Reels. YouTube is given the current safe default (3:4). Creator still sees the Aspect Ratio select in Advanced if they want to override.

**Rollback:** Remove the aspect ratio update lines from `evQsSet`. The select still exists in Advanced for manual override.

**Override path:** `evAspectRatio` select remains in qsAdvBody — creator can set any value after platform selection.

---

#### AUTO-2: Transform preset → hidden input (`index.html`)

**Problem:** `evTransformPreset` is a visible select in the Render Settings collapsed group. It offers: "None / Slightly Different / Strong Transform". Default = "Slightly Different".

**Critical finding from payload assembly (editor-view.js lines 2193-2209):**

```javascript
const reupEnabled = qs('evReupMode').checked;       // Always false in normal workflow
const transformPreset = qs('evTransformPreset').value;
if (reupEnabled && transformPreset === 'strong') {
  // Strong Reup Mode
} else if (reupEnabled) {
  // Normal Reup Mode
} else {
  // NORMAL RENDER — transformPreset is NEVER READ HERE
  payload.effect_preset = qs('evEffectPreset')?.value || 'story_clean_01';
}
```

`evReupMode` is an unchecked hidden input in `evEditorCompat`. In the normal creator workflow, `reupEnabled` is always `false`. The `transformPreset` value is read but the else-branch (normal renders) never uses it. **The Transform preset has zero effect on every normal render.**

It only matters when Reup Mode (a hidden power feature) is explicitly enabled. Creators who enable Reup Mode are advanced enough to also open Render Settings.

**Recommended change:** Replace visible `<select id="evTransformPreset">` with `<input type="hidden" id="evTransformPreset" value="slight">`. Remove the label and select from the Render Settings 2-column grid.

**After this change, Render Settings contains:** Device | FPS | Smart Crop (3 controls instead of 4).

**Trust risk:** ZERO. No normal render is affected. Reup Mode users can still manually set the value if they need "strong" (they'd need to inspect DOM or we could surface it in a Reup Mode section).

**Rollback:** Change hidden input back to visible select. Zero JS changes required.

**Override path:** Reup Mode is a hidden feature; creators who discover it are advanced enough to understand the DOM or be told to use a preset.

---

## 4. SMART DEFAULTS MATRIX

Controls that should stay visible but with **better defaults** or **creator-friendly labels**. No logic change — label or default value only.

| Control | Current label | Recommended label | Why |
|---|---|---|---|
| `evRenderProfile` | "Output Profile" | "Render Quality" | Creator-brain: "how good do I want it?" not "what profile?" |
| `evReframeStrategy` | "Reframe Mode" | "Smart Crop" | Creator-brain: "how should it crop?" not "what reframe mode?" |
| `evOutputFps` | "FPS" | "Frame Rate" | "Frame Rate" is more self-explanatory to non-technical creators |
| `evRenderDevice` | "Device" | "Render Device" | Minor — adds context |

**These are optional polish labels. They do not affect behavior. Include in Phase 65 if scope permits.**

---

## 5. MANUAL CONTROLS MATRIX

Controls that should NEVER be auto-owned. They represent genuine creator intent and taste.

| Control | Why manual | Override required? |
|---|---|---|
| `evCtaEnabled` — CTA On/Off | Creator decides: does this video have a CTA? Pure intent. | Yes — default OFF is correct |
| `evMultiVariant` — Multi-variant render | Creator decides: do I want multiple versions? Pure intent. | Yes |
| `evAddTitleOverlay` + text | Creator's content choice. Cannot be auto-guessed. | Yes |
| Creator Assets (Logo/Intro/Outro) | Creator's brand. Cannot be auto. | Yes |
| Subtitle style / font / color | Creator taste. Subjective. | Yes |
| BGM enable/file | Creator taste. Subjective. | Yes |
| Max clips (`evMaxExportParts`) | Creator decides output volume. Pure intent. | Yes |

---

## 6. RISK ASSESSMENT

### AUTO-1: Platform → Aspect Ratio

| Risk | Assessment |
|---|---|
| Creator selects YouTube but wants 9:16 | LOW — YouTube accepts both; creator uses Advanced override |
| Creator preset restores aspect ratio after platform change | SAFE — `evApplyPreset()` calls `setVal('evAspectRatio', cfg.aspect_ratio)` which overwrites the auto-set value |
| Existing renders with TikTok + 3:4 (explicit Advanced choice) | After update, next platform pill press will change to 9:16. If creator had explicitly set 3:4 in Advanced, they'll need to redo it. This is the intended behavior — explicit choice is overridden by intent signal. |
| `evUpdateAspectRatio()` side effects | Only updates canvas sizing in editor preview. Safe to call on pill press. |

### AUTO-2: Transform preset hidden

| Risk | Assessment |
|---|---|
| Reup Mode user who needs "strong" | Reup Mode is itself a hidden feature. These users are advanced enough to use Expert Presets or the evEditorCompat DOM. Risk: MINIMAL |
| Render payload reads undefined | `qs('evTransformPreset').value` still works — hidden input is still in DOM | SAFE |
| Creator Preset restore tries to set evTransformPreset | `set('evTransformPreset', val)` still finds the hidden input and sets its value | SAFE |

---

## 7. TRUST ANALYSIS

### The Trust Rule from Phase 65 brief

> "Never auto-own something if bad output is highly visible and damages trust."

#### AUTO-1 passes the trust rule

Bad output scenario: Creator selects TikTok, auto-gets 9:16, doesn't notice, renders.
- Result: Correct TikTok-format 9:16 video. Creator is happy.

Failure scenario: Creator selects YouTube for a channel that uses 3:4, auto-gets 3:4, renders.
- Result: Correct 3:4 video. Creator is happy.

Only failure: Creator selects YouTube but actually wanted 9:16 (for a YouTube Shorts-specific account).
- Result: Gets 3:4. Notices and opens Advanced to change. Renders again.
- Trust damage: LOW — the video was the wrong shape, but creator has the override.

#### AUTO-2 passes the trust rule

For normal renders: no effect whatsoever. Zero trust risk.
For Reup Mode: Reup Mode itself is an advanced feature with no creator-facing toggle. These users are operating at a level where they understand the pipeline.

#### Controls that would FAIL the trust rule (and are correctly kept manual)

| Control | Why auto would damage trust |
|---|---|
| Subtitle style | Karaoke vs Clean is highly visible. Wrong choice on first render → creator doubts the tool. |
| FPS | If auto-set to 30fps for "slow devices", some creators would notice reduced quality. |
| Min/Max clip duration | If auto-restricted to 60-90s, creator who wanted 3-minute clips gets short ones with no explanation. |
| Output Profile / Render Quality | If auto-set to "Fast Draft" for speed, creator gets low-quality output and loses trust. |
| Reframe Mode / Smart Crop | If auto-set to Subject Tracking (slowest), creator wait time increases unexpectedly. |

---

## 8. RECOMMENDED UI CHANGES

### Required (Phase 65 commits)

**Commit 65.1: Platform → Aspect Ratio auto-link**
- File: `backend/static/js/editor-view.js`
- Function: `evQsSet()`
- Change: Add aspect ratio update in the `group === 'platform'` branch
- Mapping: TikTok → 9:16, Reels → 9:16, YouTube → 3:4

**Commit 65.2: Transform preset → hidden input**
- File: `backend/static/index.html`
- Location: Render Settings `inspGroupPerfBody` grid
- Change: Remove `<label>Transform</label><select id="evTransformPreset">` and replace with `<input type="hidden" id="evTransformPreset" value="slight">` placed outside the grid

### Optional polish (Phase 65.x — minimal scope)

**Commit 65.3: Label clarity pass — Render Settings**
- File: `backend/static/index.html`
- Changes:
  - "Output Profile" → "Render Quality" (in qsAdvBody)
  - "Reframe Mode" → "Smart Crop" (in Render Settings)
  - Keep all select options and IDs unchanged

**Not recommended for Phase 65:**
- Editor Performance section collapse (Phase 65.5 candidate — separate concern)
- Min/Max clip duration changes (content-dependent, no clear auto default)
- Output Profile default change (Balanced is already the right auto-default)

---

## 9. SAFE ROLLOUT PLAN

### Before Commit 65.1

Verify current behavior:
- Select TikTok pill → `evTargetPlatform` = tiktok, `evAspectRatio` = 3:4 (confirm the gap exists)
- Open Advanced → Aspect Ratio still shows 3:4 (confirmed wrong)

### Commit 65.1: `auto(65.1): platform pill auto-sets aspect ratio`

Validation checklist:
- [ ] Select TikTok pill → Aspect Ratio in Advanced shows 9:16
- [ ] Select Reels pill → Aspect Ratio in Advanced shows 9:16
- [ ] Select YouTube pill → Aspect Ratio in Advanced shows 3:4
- [ ] Select TikTok → manually change Advanced to 1:1 → renders at 1:1 (override works)
- [ ] Apply Quick Preset "TikTok/Reels" → Aspect Ratio shows 9:16 (preset still works)
- [ ] Apply Quick Preset "Business" → Aspect Ratio shows 3:4 (preset still works, not overwritten)
- [ ] Creator Preset restore with saved platform+aspect combination still restores correctly
- [ ] Render payload: `aspect_ratio = '9:16'` when TikTok selected

Stop if: aspect ratio override in Advanced doesn't persist across render submission.

### Commit 65.2: `auto(65.2): transform preset — hidden input`

Validation checklist:
- [ ] Render Settings group shows 3 controls: Device, Frame Rate, Smart Crop
- [ ] Render payload: `transformPreset = 'slight'` still sent (hidden input value is read)
- [ ] Normal render with TikTok settings: effect_preset, transition_sec correct (Reup branch not triggered)
- [ ] Render Settings collapse/expand: no visual gaps from removed select

Stop if: Render payload does not include `transformPreset` correctly.

### Commit 65.3 (optional): `auto(65.3): label clarity pass`

Validation checklist:
- [ ] "Render Quality" label shows in Advanced fold (was "Output Profile")
- [ ] "Smart Crop" label shows in Render Settings (was "Reframe Mode")
- [ ] Select options and IDs unchanged
- [ ] No JS errors (labels have no JS bindings)

---

## 10. COMMIT PLAN

| # | Commit message | File | Lines changed |
|---|---|---|---|
| 1 | `auto(65.1): platform pill auto-sets aspect ratio` | `editor-view.js` | ~5 lines in `evQsSet()` |
| 2 | `auto(65.2): transform preset — hidden input` | `index.html` | ~5 lines removed, 1 added |
| 3 | `auto(65.3): render settings label clarity` (optional) | `index.html` | ~3 label text changes |

**Total scope: 2–3 commits, 1–2 files, ~11 lines changed.**

Phase 65 is deliberately small. The engine already owns most technical parameters. The two required changes fix a real gap (platform→aspect) and remove a dead control (transform). Nothing else warrants "AI technical ownership" action without a proportional UX benefit.

---

## 11. DEFINITION OF DONE

Phase 65 is complete when:

- [ ] Selecting TikTok or Reels in Platform pills auto-updates Aspect Ratio to 9:16
- [ ] Selecting YouTube in Platform pills sets Aspect Ratio to 3:4
- [ ] Aspect Ratio override in Advanced still works after pill selection
- [ ] Transform preset is a hidden input in Render Settings (not a visible select)
- [ ] Render Settings group contains exactly 3 controls: Render Device, Frame Rate, Smart Crop
- [ ] All auto-owned parameters documented in this file remain stable
- [ ] Zero regressions: render payload values for `aspect_ratio`, `transform_preset`, and `encoder_mode` all correct

### Auto-ownership summary after Phase 65

| Parameter | Owner |
|---|---|
| Aspect ratio | **Auto** via Platform pill (Phase 65) + manual override in Advanced |
| Transform preset | **Auto** = slight, always (Phase 65) |
| Playback speed | **Auto** = 1.07× (pre-Phase 65) |
| Source quality | **Auto** = standard_1080 (pre-Phase 65) |
| Part order | **Auto** = viral/best-first (pre-Phase 65) |
| Frame scale Y | **Auto** = 106 (pre-Phase 65) |
| Loudness | **Auto** = ON (Phase 63) |
| Subtitle tone | **Auto** = clean (Phase 63) |
| Subtitle emphasis | **Auto** = balanced (Phase 63) |
| Structure bias | **Auto** via QS Bar pill |
| Platform | **Manual** via QS Bar pill |
| Subtitle style | **Manual** via QS Bar pill / Subtitles tab |
| Render quality | **Manual** in Advanced (with smart Balanced default) |
| Min/Max clip | **Manual** in Advanced (with sensible 70/180 defaults) |
| FPS | **Manual** in Render Settings (with smart 60fps default) |
| Render device | **Manual** in Render Settings (with safe auto-GPU default) |
| Smart Crop mode | **Manual** in Render Settings (with fast-center default) |
| CTA | **Manual** in Advanced (default OFF) |
| Multi-variant | **Manual** in Advanced (default OFF) |

---

## What Phase 65 does NOT change

The following are explicitly out of scope:

| Item | Why deferred |
|---|---|
| Editor Performance section (hover/filmstrip/waveform toggles) | UI performance, not render ownership — Phase 65.5 |
| Subtitles tab X Position slider | Tab-scope change — Phase 65+ |
| Output Profile default change | Balanced is already the correct auto-default |
| FPS auto-linking to platform | 30/60fps both valid for all platforms; no clear auto mapping |
| Min/Max clip auto defaults | Content-dependent; no reliable signal for auto-sizing |
| Any new AI system | Phase 65 brief explicitly excludes new AI systems |

---

*Phase 65 plan based on Phase 64 Simple Mode completion and post-64 code audit.*
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*
