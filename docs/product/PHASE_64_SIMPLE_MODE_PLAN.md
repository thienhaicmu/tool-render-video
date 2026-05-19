# PHASE 64 — SIMPLE MODE PLAN
## Post-Stabilization Export Flow Reduction

**Branch:** `feature/ai-output-upgrade`
**Prerequisite:** Phase 63.5 stabilization COMPLETE, verdict GO
**Stabilization source:** `docs/product/PHASE_63_STABILIZATION.md`
**Plan date:** 2026-05-19

---

## 1. EXECUTIVE SUMMARY

Phase 63 cleared the developer noise. Phase 64 clears the creator noise.

The single biggest remaining friction in the Export tab is the Market & Target section — 5 controls visible by default that most creators never touch in their first 10 renders. Phase 64 collapses this section and two other pre-content UI blocks (Quick Start Preset cards) so that creators opening the Export tab immediately see exactly three things: their preset, the Quick Strategy Bar, and Max clips.

One critical dead-feature removal is included: the Analyze Market button has been non-functional since before Phase 63 (its result display element `mvMarketRec` does not exist in the HTML). It should be removed rather than collapsed.

After Phase 64, the primary Export flow becomes:

```
[▸ Quick Preset]         ← collapsed — one tap to reset all settings
[▸ Market & Target]      ← collapsed — one tap to access optimization
Creator Presets bar
Platform | Subtitle | Structure
Max clips
[Advanced ▸]
```

Five commits. One file each. All reversible.

---

## 2. PROBLEMS REMAINING AFTER PHASE 63

From `PHASE_63_STABILIZATION.md` — Section 10 "What Still Feels Heavy":

| Problem | Source | Priority |
|---|---|---|
| Market & Target section — 5 visible controls before Output area | FP-3 (Friction Point 3) | HIGH — Phase 64 |
| Quick Start Preset cards — 4 cards above strategic controls | Section 10, item 3 | MEDIUM — Phase 64 |
| Analyze Market button — dead feature, visually looks active | Section 10, item 4 | HIGH — trivial fix |
| CTA toggle in QS Bar — makes bar feel crowded | Section 10 / audit | MEDIUM — Phase 64 |
| Variant toggle in QS Bar — rarely used, duplicated in Advanced | Audit finding | LOW — Phase 64 |

**Critical finding discovered during Phase 64 code audit (new):**

The following IDs referenced in JS are **not present in the HTML** and have been gone for some time:

| Ghost ID | Referenced in JS | Impact |
|---|---|---|
| `mvMarketRec` | `mvAnalyzeMarket()` line 3590: `if (!resultEl) return` | Analyze Market button **always returns immediately** — the button is already completely broken |
| `mvAdaptiveRow` | `mvHandleChange()` line 2587 | Visual accent update is a no-op |
| `mvAutoBestRow` | `mvHandleAutoBestClips()` line 2634 | Visual accent update is a no-op |
| `mvCombinedScoring` | `mvHandleChange()` line 2583 | Combined scoring never enabled from UI |
| `mvAdaptiveScoring` | `mvHandleChange()` line 2596 | Adaptive scoring never enabled from UI |
| `mvBestExportCount` | `mvHandleChange()` line 2610 | Count input doesn't exist; defaults to 3 |
| `mvBestExportCountRow` | `mvHandleChange()` line 2605 | No-op |

**Implication:** The Analyze Market button is not a deferred feature — it is a broken feature with no visible output. It should be fully removed, not collapsed.

The remaining working controls in the Market section are:
- `mvMarket` (Target Market dropdown) — functional
- `mvAutoBestClips` (checkbox) — functional
- `mvKeywordHighlight` (checkbox) — functional
- `mvBestExportEnabled` (checkbox) — functional, count defaults to 3

---

## 3. SIMPLE MODE GOALS

Creator-facing goal:
> Upload a video → feel immediately capable → render without thinking.

The primary Export tab should answer one question:

**"What kind of clip are you making and where is it going?"**

Everything else is Advanced.

Simple Mode is NOT:
- A separate mode toggle
- A feature flag
- A redesigned tab

Simple Mode is a **surface reduction**: collapse non-primary blocks so that the primary flow is the first thing creators see.

---

## 4. VISIBLE VS ADVANCED DECISION MATRIX

After Phase 64, every export control falls into one of three buckets:

| Bucket | Meaning | Examples |
|---|---|---|
| **Primary** | Creator must decide this before every render | Platform, Subtitle style, Structure bias, Max clips |
| **Optional** | Creator benefits from it after first few renders | Quick Presets, Market Target, CTA, Aspect Ratio |
| **Power** | Creator needs it for specific advanced use cases | Expert Preset, Batch Mode, Creator Assets, Title Overlay |

### Decision matrix

| Control | Current visibility | Phase 64 decision | Bucket |
|---|---|---|---|
| Creator Presets bar | Visible | Keep visible | Primary |
| Platform pills | Visible (QS Bar) | Keep visible | Primary |
| Subtitle pills | Visible (QS Bar) | Keep visible | Primary |
| Structure pills | Visible (QS Bar) | Keep visible | Primary |
| CTA pill (End Card) | Visible (QS Bar) | Move to Advanced | Optional |
| Variant pill (Multi-variant) | Visible (QS Bar) | Move to Advanced | Optional |
| Max clips | Visible (above fold) | Keep visible | Primary |
| Quick Start Presets (4 cards) | Visible section | Collapse to `<details>` | Optional |
| Target Market dropdown | Visible section | Collapse to `<details>` | Optional |
| Auto Best Clips checkbox | Visible section | Collapse to `<details>` | Optional |
| Keyword Highlight checkbox | Visible section | Collapse to `<details>` | Optional |
| Auto Best Export checkbox | Visible section | Collapse to `<details>` | Optional |
| Analyze Market button | Visible section | **Remove** (already broken) | Dead |
| Expert Preset | Advanced | Keep in Advanced | Power |
| Aspect Ratio | Advanced | Keep in Advanced | Power |
| Output Profile | Advanced | Keep in Advanced | Power |
| Min/Max clip duration | Advanced | Keep in Advanced | Power |
| CTA type select | Advanced | Keep in Advanced (CTA joins here) | Optional |
| Multi-variant checkbox | Advanced (hidden) | Make visible in Advanced | Optional |
| Title Overlay | Advanced | Keep in Advanced | Power |
| Creator Assets | Advanced | Keep in Advanced | Power |
| Batch Mode | Advanced | Keep in Advanced | Power |

---

## 5. MARKET SECTION DECISION

### What the Market & Target section contains

```html
<!-- Market / Target section (evSectionMarket) -->
🌍 Market & Target
"Market scoring, subtitle tone, and hook optimization for every exported clip."

Target Market: [🇺🇸 US / 🇪🇺 EU / 🇯🇵 JP]   ← functional
✨ Auto Best Clips                              ← functional
🔑 Keyword Highlight                           ← functional
📦 Auto Best Export                            ← functional (count missing)
[Analyze Market] button                        ← BROKEN — always no-ops
```

### Why it feels heavy

5 visible items including a full-width action button, all before the primary Output section. For the majority of creators (US, not using market analysis), zero of these controls change between renders. The section description — "Market scoring, subtitle tone, and hook optimization" — reads like a feature advertisement, not a creator instruction.

### Decision

**64.1:** Remove Analyze Market button. It has been broken since before Phase 63. `mvAnalyzeMarket()` checks `document.getElementById('mvMarketRec')` and `if (!resultEl) return` — the button click silently does nothing. No creator has ever seen a result from this button.

**64.2:** Wrap entire `evSectionMarket` div body in `<details>` collapsed by default.

Summary label: `▸ Market & Target`

All IDs (`mvMarket`, `mvAutoBestClips`, `mvKeywordHighlight`, `mvBestExportEnabled`) remain in the DOM. Creator Preset restore and `mvHandleChange()` both read by ID — both safe regardless of `<details>` open state.

### What this achieves

Before: 5 controls visible for all creators before they reach Platform/Subtitle.
After: 1 collapsed line `▸ Market & Target`. Creators who need it expand it. US creators on default settings never notice it.

### JS safety

| JS call | Impact | Safe? |
|---|---|---|
| `mvHandleChange()` reads `g('mvMarket')` | Element in DOM inside `<details>` | YES |
| `mvHandleAutoBestClips()` reads `g('mvAutoBestClips')` | Same | YES |
| `mvAnalyzeMarket()` reads `g('mvAnalyzeBtn')` | After 64.1, element removed; `if (btn)` guard at line 3599 | YES |
| Preset restore calls `set('mvMarket', cfg.market)` | Writes to element in DOM | YES |
| Preset watcher observes `mvMarket`, `mvAutoBestClips`, etc. | MutationObserver / event listener on document — ID-independent | YES |

---

## 6. QUICK PRESETS DECISION

### The overlap question

Quick Start Presets set:
`aspect_ratio`, `render_profile`, `min/max_part_sec`, `subtitle_style`, `sub_font`, `sub_size`, `sub_color`, `sub_highlight`, `sub_outline`, `sub_pos`, `effect_preset`, `loudnorm`

Quick Strategy Bar sets:
`target_platform`, `subtitle vibe` (→ `evSubStyle`), `structure bias`, `cta_enabled`, `multi_variant`

These set **different fields** — presets set deep render config, QS Bar sets surface creative intent. They are not truly redundant; they operate at different layers.

The overlap the creator feels is conceptual: "TikTok/Reels" preset card looks the same as selecting "TikTok" in the Platform pills. Creators don't understand that the preset also sets render_profile=balanced, min_part_sec=30, max_part_sec=90, and subtitle font/size.

### Decision

**64.3:** Wrap Quick Start Preset section body in `<details>` collapsed by default.

Summary label: `▸ Quick Preset — apply a starting look`

The 4 preset cards (TikTok/Reels, Podcast Clip, Clean Business, High Quality) remain fully functional inside the collapsed section. `evApplyPreset()` reads `data-preset` attribute from clicked button — position-independent, unaffected by `<details>` nesting.

### What this achieves

Before: 4 preset cards occupying the top of the Export tab before Creator Presets or Quick Strategy Bar.
After: 1 collapsed line above the Output section. First-time creators who want to start with a template expand it. Returning creators who go straight to QS Bar skip it entirely.

The preset section stays where it is in DOM order — above the Output section. After collapse, only 1 line of height. Creators reach the QS Bar immediately.

### JS safety

| JS call | Safe? |
|---|---|
| `evApplyPreset('tiktok')` — reads `data-preset` from button, doesn't need element visible | YES |
| `document.querySelectorAll('.evPresetCard')` — finds all cards in DOM regardless of `<details>` state | YES |
| `evApplyPreset` writes to other fields via `setVal()` with ID lookup | YES |

---

## 7. CTA DECISION

### Current state

CTA appears in two places:

1. **QS Bar** — `qsCtaBtn` button (`"End Card"` toggle), visible in Quick Strategy Bar
2. **qsAdvBody** — `evCtaEnabled` checkbox + `evCtaTypeWrap` (select for Auto/Comment/Series/Follow), inside Advanced fold

The QS Bar button is a visual mirror of the Advanced checkbox. Both call `evSyncQsBar()` to stay in sync. CTA **defaults to OFF** (unchecked).

### Decision

**64.4 (partial):** Remove the CTA pill group from the QS Bar.

`evCtaEnabled` checkbox already exists and is fully functional inside qsAdvBody. Creators who want to add a CTA will find it in Advanced — where it already lives with a proper label ("Add ending CTA — Tasteful end card — comment / part 2 / follow") and the type selector.

The QS Bar End Card button was a shortcut to a feature that most creators don't use and many don't understand on first render. Removing it makes the QS Bar narrower and gives Platform/Subtitle/Structure more visual breathing room.

### JS safety

`evSyncQsBar()` at line 136-141 reads `qsCtaBtn` with `if (ctaEl && ctaBtn)` null guard. After removing the DOM element, `ctaBtn` will be null — guard fires, no error. `evCtaEnabled.onchange` calls `evSyncQsBar()` — safe for same reason.

---

## 8. EXPORT FLOW RECOMMENDATION

### Current state (post-Phase 63)

```
Export tab opened
│
├─ Quick Start Preset [VISIBLE SECTION — 4 cards, ~120px]
│
├─ Market & Target [VISIBLE SECTION — 5 controls, ~100px]
│
├─ Output
│   ├─ Creator Presets bar
│   ├─ Quick Strategy Bar: Platform | Variant | Subtitle | CTA | Structure
│   ├─ Max clips
│   └─ [Advanced ▸]
│
└─ Batch Queue
```

### After Phase 64

```
Export tab opened
│
├─ [▸ Quick Preset]        ← 1 line, collapsed
│
├─ [▸ Market & Target]     ← 1 line, collapsed
│
├─ Output
│   ├─ Creator Presets bar
│   ├─ Quick Strategy Bar: Platform | Subtitle | Structure  [3 groups]
│   ├─ Max clips
│   └─ [Advanced ▸]
│       ├─ Expert Preset
│       ├─ Aspect Ratio / Output Profile
│       ├─ Min/Max clip duration
│       ├─ Multi-variant [now visible checkbox]
│       ├─ Add ending CTA + CTA Type
│       ├─ Title Overlay
│       ├─ Creator Assets
│       └─ Batch Mode
│
└─ Batch Queue
```

**Creator's primary question answered immediately:** Platform (where?) + Subtitle (what look?) + Structure (what pacing?). Three decisions. Then render.

**Reduction count:**
- Visible controls before strategic area: was ~9 items (4 cards + 5 market controls), now ~2 lines (collapsed summaries)
- QS Bar pill groups: was 5, now 3

---

## 9. EXACT UI CHANGES

### Phase 63.6-A: `<details>` arrow fix (prerequisite)

**File:** `backend/static/css/v3/app.css`

Add to end of file:
```css
/* details open/close arrow — Words tab Advanced panel */
details > summary { list-style: none; }
details > summary::-webkit-details-marker { display: none; }
details > summary::marker { display: none; }
details > summary::before { content: '▸ '; font-size: 11px; }
details[open] > summary::before { content: '▾ '; }
```

**File:** `backend/static/index.html`

Change:
```html
<summary style="font-size:11px;color:var(--text-mut);cursor:pointer;padding:3px 0;list-style:none;user-select:none">▸ Advanced</summary>
```
To:
```html
<summary style="font-size:11px;color:var(--text-mut);cursor:pointer;padding:3px 0;user-select:none">Advanced</summary>
```
(Remove `▸ ` from text; remove `list-style:none` from inline style since it's now in CSS.)

---

### Commit 64.1: Remove Analyze Market button

**File:** `backend/static/index.html`

Remove from `evSectionMarket`:
```html
<button class="ghostButton" id="mvAnalyzeBtn" style="width:100%;margin-top:8px;font-size:12px" onclick="mvAnalyzeMarket()">Analyze Market</button>
```

No replacement. The button has been non-functional since before Phase 63. `mvAnalyzeMarket()` exits immediately at `if (!resultEl) return` because `mvMarketRec` does not exist in the HTML.

---

### Commit 64.2: Market & Target section — collapse to `<details>`

**File:** `backend/static/index.html`

Wrap the **inner content** of `evSectionMarket` in `<details>`. The outer `<div class="evSection mvPanel" id="evSectionMarket">` stays as-is so `data-insp-panel="performance"` and section CSS remain correct.

Before (structural):
```html
<div class="evSection mvPanel" id="evSectionMarket" data-insp-panel="performance">
  <div class="evSectionTitle">🌍 Market &amp; Target</div>
  <div class="mvPanelDesc">...</div>
  <div style="display:grid;...">   ← Target Market grid
    ...
  </div>
  <div class="mvToggleGroup">   ← 3 checkboxes
    ...
  </div>
  <!-- button removed in 64.1 -->
</div>
```

After:
```html
<div class="evSection mvPanel" id="evSectionMarket" data-insp-panel="performance">
  <details>
    <summary style="font-size:12px;font-weight:600;color:var(--text-mut);cursor:pointer;padding:2px 0;user-select:none">Market &amp; Target</summary>
    <div class="mvPanelDesc" style="margin-top:6px">...</div>
    <div style="display:grid;...">
      ...
    </div>
    <div class="mvToggleGroup">
      ...
    </div>
  </details>
</div>
```

The section's own `evSectionTitle` div is replaced by the `<summary>` element. This keeps the visual weight of the section header but collapses the body.

---

### Commit 64.3: Quick Start Presets — collapse to `<details>`

**File:** `backend/static/index.html`

Same pattern as 64.2. Outer `evPresetSection` div stays. The section title and body are wrapped:

Before (structural):
```html
<div class="evSection evPresetSection ev-panel-card ev-option-panel" id="evPresetSection" data-insp-panel="performance">
  <div class="evSectionTitle ev-panel-card-head">Quick Start Preset</div>
  <div style="font-size:11px;...">Applies a starting setup. You can still customize everything.</div>
  <div class="ev-panel-card-body">
    <div class="evPresetGrid ev-option-grid" id="evQuickStartPreset" ...>
      <!-- 4 preset cards -->
    </div>
  </div>
  <input type="hidden" id="evEffectPreset" value="">
  <input type="hidden" id="evLoudnormEnabled" value="1">
</div>
```

After:
```html
<div class="evSection evPresetSection ev-panel-card ev-option-panel" id="evPresetSection" data-insp-panel="performance">
  <details>
    <summary style="font-size:12px;font-weight:600;color:var(--text-mut);cursor:pointer;padding:2px 0;user-select:none">Quick Preset</summary>
    <div style="font-size:11px;...margin-top:6px">Applies a starting setup. You can still customize everything.</div>
    <div class="ev-panel-card-body">
      <div class="evPresetGrid ev-option-grid" id="evQuickStartPreset" ...>
        <!-- 4 preset cards -->
      </div>
    </div>
  </details>
  <input type="hidden" id="evEffectPreset" value="">
  <input type="hidden" id="evLoudnormEnabled" value="1">
</div>
```

The two hidden inputs stay **outside** the `<details>` tag. They are read by `evApplyPreset()` which writes to them directly, and by the render payload builder which reads by ID. They must remain unconditionally accessible. Both are `type="hidden"` so they have no visual presence.

---

### Commit 64.4: QS Bar — remove CTA pill, remove Variant pill, surface Multi-variant

**File:** `backend/static/index.html`

**4A — Remove CTA pill group from QS Bar:**

Remove:
```html
<div class="qsGroup">
  <div class="qsLabel">CTA</div>
  <div class="qsPills">
    <button class="qsPill qsPillToggle" id="qsCtaBtn" onclick="evQsToggle('cta')">End Card</button>
  </div>
</div>
```

`evCtaEnabled` checkbox is already visible inside qsAdvBody at line 1138. `evSyncQsBar()` has null guard for `qsCtaBtn`.

**4B — Remove Variant pill group from QS Bar:**

Remove:
```html
<div class="qsGroup">
  <div class="qsLabel">Variant</div>
  <div class="qsPills">
    <button class="qsPill qsPillToggle" id="qsVariantBtn" onclick="evQsToggle('variant')">Multi-variant</button>
  </div>
</div>
```

`evSyncQsBar()` has null guard for `qsVariantBtn`.

**4C — Surface Multi-variant as visible checkbox in qsAdvBody:**

Current (line 1131):
```html
<input type="checkbox" id="evMultiVariant" style="display:none" onchange="evSyncQsBar()">
```

Change to visible form. Insert a labeled checkbox row where the hidden input is:
```html
<label class="field" style="grid-column:1/-1;display:flex;align-items:center;gap:8px;padding-top:2px">
  <input type="checkbox" id="evMultiVariant" style="width:15px;height:15px;accent-color:var(--primary);flex-shrink:0" onchange="evSyncQsBar()">
  <span class="fieldLabel" style="margin-bottom:0;cursor:pointer">Multi-variant render</span>
  <span style="font-size:11px;color:#888;font-style:italic">Creates multiple style variants in one render</span>
</label>
```

The `evTargetPlatform` hidden select stays hidden — it is fully managed by the Platform pills in the QS Bar. No change needed there.

---

## 10. RISK ASSESSMENT

| Commit | Change | Riskiest element | Guard exists? | Risk level |
|---|---|---|---|---|
| 63.6-A | CSS pseudo-element + 1 HTML text node | CSS `::before` on `details > summary` | N/A — pure visual | MINIMAL |
| 64.1 | Remove `mvAnalyzeBtn` | `mvAnalyzeMarket()` reads `document.getElementById('mvAnalyzeBtn')` | `if (btn) { btn.disabled... }` at line 3599 | MINIMAL |
| 64.2 | Wrap Market section in `<details>` | Creator Preset restore + `mvHandleChange()` | All reads by ID, DOM-position-independent | LOW |
| 64.3 | Wrap Quick Presets in `<details>` | `evApplyPreset()` reads `.evPresetCard` buttons | Buttons stay in DOM, `querySelectorAll` finds them | LOW |
| 64.4 | Remove CTA/Variant pills, surface Multi-variant | `evSyncQsBar()` references `qsCtaBtn`, `qsVariantBtn` | `if (ctaEl && ctaBtn)` guards at lines 137-141 and 118-120 | LOW |

### Regression matrix for Phase 64

| Workflow | Affected by | Expected result |
|---|---|---|
| Render payload assembly | 64.2 (mvMarket etc still in DOM) | PASS — IDs unchanged |
| Creator Presets save | 64.2, 64.3 | PASS — preset watcher uses MutationObserver on document, not element position |
| Creator Presets restore | 64.2 (sets mvMarket, mvAutoBestClips etc.) | PASS — `set()` and `chk()` read by ID |
| Quick Style presets | 64.3 (evApplyPreset, evLoudnormEnabled outside details) | PASS — hidden inputs outside `<details>`, preset card buttons inside but found by `querySelectorAll` |
| CTA render payload | 64.4 (evCtaEnabled checkbox in qsAdvBody) | PASS — `payload.cta_enabled = document.getElementById('evCtaEnabled')?.checked` |
| Multi-variant render payload | 64.4 (evMultiVariant now visible checkbox) | PASS — `payload.multi_variant = document.getElementById('evMultiVariant')?.checked` |
| evSyncQsBar on CTA/Variant change | 64.4 (qsCtaBtn, qsVariantBtn removed) | PASS — null guards in lines 118-120, 136-141 |
| Market state after preset restore | 64.2 | PASS — `mvHandleChange()` called by restore logic, reads by ID |
| Subtitles | Not touched | PASS |
| BGM | Not touched | PASS |
| Text layers | Not touched | PASS |
| Batch Mode | Not touched | PASS |

---

## 11. SAFE ROLLOUT PLAN

Each commit is independently revertable. Stop and investigate if any commit shows unexpected behavior.

**Step 1 (prerequisite):** `simple(63.6-A): details arrow toggle — CSS + summary text`
- Verify: Words tab `▸ Advanced` shows `▾` when opened
- Verify: Native disclosure triangle hidden in Chrome and Firefox
- Gate: arrow must toggle before proceeding

**Step 2:** `simple(64.1): remove broken Analyze Market button`
- Verify: Analyze Market button no longer visible in Market section
- Verify: Clicking the removed button area does nothing (it's gone)
- Verify: evSectionMarket section title still shows, checkboxes still show
- Regression check: Market section rendering unchanged except button

**Step 3:** `simple(64.2): market section — collapse to details`
- Verify: Export tab shows `▸ Market & Target` collapsed by default
- Verify: Expanding reveals Target Market, Auto Best Clips, Keyword Highlight, Auto Best Export
- Verify: Changing Target Market to EU → render payload sends `target_market: 'EU'`
- Verify: Creator Preset with saved market settings restores correctly
- Regression check: `mvHandleChange()` still fires on checkbox changes when section is open

**Step 4:** `simple(64.3): quick presets — collapse to details`
- Verify: Export tab shows `▸ Quick Preset` collapsed by default
- Verify: Expanding shows all 4 preset cards
- Verify: Clicking a preset card (e.g., TikTok/Reels) applies settings correctly
- Verify: `evLoudnormEnabled` and `evEffectPreset` hidden inputs are outside `<details>`, preset writes to them correctly
- Regression check: `evApplyPreset()` applies subtitle style and render profile

**Step 5:** `simple(64.4): qs bar — remove cta+variant pills, surface multi-variant`
- Verify: QS Bar shows Platform | Subtitle | Structure only (3 groups)
- Verify: CTA End Card button is gone from QS Bar
- Verify: Variant button is gone from QS Bar
- Verify: Advanced section contains Multi-variant visible checkbox
- Verify: Advanced section still contains Add ending CTA checkbox with full description
- Verify: Opening Advanced → checking Multi-variant → render payload sends `multi_variant: true`
- Verify: Opening Advanced → checking Add ending CTA → render payload sends `cta_enabled: true`
- Regression check: `evSyncQsBar()` does not throw when called (null guards fire silently)

---

## 12. COMMIT PLAN

| # | Commit message | File(s) | Lines affected |
|---|---|---|---|
| 0 | `simple(63.6-A): details arrow toggle — css and summary text` | app.css, index.html | ~5 lines added to CSS, 1 line changed in HTML |
| 1 | `simple(64.1): remove broken analyze market button` | index.html | ~1 line removed |
| 2 | `simple(64.2): market section — collapse to details` | index.html | ~8 lines changed |
| 3 | `simple(64.3): quick presets — collapse to details` | index.html | ~8 lines changed |
| 4 | `simple(64.4): qs bar — remove cta and variant pills, surface multi-variant` | index.html | ~20 lines changed |

All commits touch `backend/static/index.html`. Commit 0 also touches `backend/static/css/v3/app.css`.

---

## 13. DEFINITION OF DONE

Phase 64 is complete when:

- [ ] `▸ Advanced` arrow in Words tab toggles to `▾` when opened (63.6-A)
- [ ] Analyze Market button is gone (64.1)
- [ ] Export tab primary view shows no section body above the Output section by default — only 2 collapsed `<details>` summaries (64.2, 64.3)
- [ ] QS Bar has exactly 3 pill groups: Platform, Subtitle, Structure (64.4)
- [ ] Multi-variant is accessible as a visible checkbox in Advanced (64.4)
- [ ] CTA is accessible as a visible checkbox in Advanced (unchanged, verified)
- [ ] Zero JS regressions: render payload, presets, market state, QS sync all work
- [ ] Creator opens Export tab → first scrollable content is Creator Presets bar + QS Bar
- [ ] Phase 63 wins untouched: Max clips above fold, Batch Mode in Advanced, loudness default ON, Words tab simplified

### Simple Mode primary flow after Phase 64

Creator opens Export tab:

```
[▸ Quick Preset]         — 1 line
[▸ Market & Target]      — 1 line
─────────────────────────
Output
  [— No Preset —  ▾] [Save]     ← Creator Presets
  Platform  | Subtitle | Structure  ← 3 decisions
  Max clips: [0]                    ← 1 field
  [Advanced ▸]
─────────────────────────
Batch Queue
```

Six lines of UI visible before creator hits Advanced. Down from ~22 lines (4 preset cards + 5 market controls + presets bar + QS Bar with 5 groups + max clips).

---

## Out of Scope for Phase 64

Carried forward to Phase 65:

| Item | Reason |
|---|---|
| Subtitles tab X Position slider | Not in stabilization brief for Phase 64; separate tab |
| Subtitles tab Outline slider evaluation | Same |
| Quick Preset section DOM reordering (below Output) | Requires larger structural change; collapsed state already achieves the goal |
| Editor Performance toggles (hover/filmstrip/waveform) | Stabilization deferred item; editor-panel scope |
| BGM fade in/out evaluation | Audio tab scope; deferred |

---

*Phase 64 plan based on Phase 63.5 stabilization findings.*
*Branch: `feature/ai-output-upgrade` · Plan date: 2026-05-19*
