# RENDER SYSTEM REDUCTION + AI INTERVENTION AUDIT
## V1 RC → Semi-Opus Preparation

**Branch:** `feature/ai-output-upgrade`
**Date:** 2026-05-19
**Stage:** V1 RC / Packaging → V2.x transition planning

---

## 1. EXECUTIVE SUMMARY

The tool currently has **150+ creator-facing controls** across 6 inspector tabs. Most of these controls are legitimate features, but their surface area is spread incorrectly: developer diagnostics live alongside subtitle pickers, redundant style controls appear in three separate tabs, and the Export tab alone contains 50+ controls mixing creator strategy with engineering configuration.

This is not a product quality problem. The core systems are sound. This is a **presentation and reduction problem**.

To reach Semi-Opus readiness:
- **~30 controls can be removed** (dead weight or developer-only)
- **~40 controls should collapse** into Advanced mode or Settings
- **~8 mechanical decisions should become AI-owned** (platform-derived or content-derived)
- **~15 controls are the moat** and must stay prominent, creator-visible, and trust-preserving

The minimum creator input for a great render should become:
> Input → Platform → Style → Max clips → Go

Everything else is either AI-decided or optional advanced steering.

---

## 2. FEATURE INVENTORY

Total discoverable creator-facing controls: **~155**

### 2.1 Pre-Render Setup

| Control | Type | Location |
|---|---|---|
| Source Type (YouTube / Local) | Dropdown | Sidebar |
| Video URL | Text input | Sidebar, YouTube mode |
| Local Video File Picker | File input | Sidebar, Local mode |
| Output Folder | Directory picker | Sidebar |
| Resume Job ID | Text + button | Sidebar |
| Open Editor button | Primary CTA | Sidebar |
| Hidden payload: aspect_ratio | Hidden select | `#evEditorCompat` |
| Hidden payload: render_profile | Hidden select | `#evEditorCompat` |
| Hidden payload: render_device | Hidden select | `#evEditorCompat` |
| Hidden payload: output_fps | Hidden select | `#evEditorCompat` |
| Hidden payload: playback_speed | Hidden select | `#evEditorCompat` |
| Hidden payload: min_part_sec | Hidden input | `#evEditorCompat` |
| Hidden payload: max_part_sec | Hidden input | `#evEditorCompat` |
| Hidden payload: max_export_parts | Hidden input | `#evEditorCompat` |
| Hidden payload: part_order | Hidden input | `#evEditorCompat` |
| Hidden payload: frame_scale_x | Hidden input | `#evEditorCompat` |
| Hidden payload: frame_scale_y | Hidden input | `#evEditorCompat` |
| Hidden payload: subtitle_style | Hidden input | `#evEditorCompat` |
| Hidden payload: transform_preset | Hidden input | `#evEditorCompat` |
| Hidden payload: motion_aware_crop | Hidden checkbox | `#evEditorCompat` |
| Hidden payload: add_subtitle | Hidden checkbox | `#evEditorCompat` |
| Hidden payload: reup_mode | Hidden checkbox | `#evEditorCompat` |
| Hidden payload: cleanup_temp_files | Hidden checkbox | `#evEditorCompat` |
| Hidden payload: reup_bgm_* | Hidden inputs (3) | `#evEditorCompat` |

### 2.2 Story Tab (Editor Inspector)

| Control | Type |
|---|---|
| Trim In slider + number | Range + number |
| Trim Out slider + number | Range + number |
| Set IN button | Button |
| Set OUT button | Button |
| Reset trim | Button |
| Quick Style: Viral | Button |
| Quick Style: Cinematic | Button |
| Quick Style: Aggressive | Button |
| Quick Style: Balanced | Button |
| Snapshots list | Dynamic list |
| AI Action: Tighten Cuts | Button |
| AI Action: Stronger Hook | Button |
| AI Action: Faster Pacing | Button |
| AI Action: Best First | Button |
| AI Action: Viral Mode | Button |
| AI Action: Cinematic | Button |
| AI Action: Quick Subtitle Fix | Link |
| AI Action: Undo Last Edit | Button |
| Edit History rail | Read-only display |
| Creator Memory hints | Dynamic display |

### 2.3 Subtitles Tab

| Control | Type |
|---|---|
| Auto subtitles toggle | Checkbox |
| Style preset | Dropdown (5 styles) |
| Font | Dropdown (8 fonts) |
| Size (px) | Slider 24–120 |
| Text color | Color picker |
| Highlight color | Color picker |
| Y Position (%) | Slider 5–60 |
| X Position (%) | Slider 5–95 |
| Outline (px) | Slider 0–8 |
| Static preview | Display |
| Fix Subs AI button | Button |
| Translate toggle | Checkbox |
| Target language | Dropdown (conditional) |

### 2.4 Words Tab

| Control | Type |
|---|---|
| AI Narration toggle | Checkbox |
| Voice controls (injected) | Dynamic |
| + Layer button | Button |
| Style presets row | Button group |
| Text layer list | Dynamic list |
| Per-layer: text content | Textarea |
| Per-layer: font | Dropdown (8) |
| Per-layer: size (px) | Number 12–300 |
| Per-layer: color | Color picker |
| Per-layer: align | Dropdown |
| Per-layer: position preset | Dropdown (7) |
| Per-layer: X % | Number |
| Per-layer: Y % | Number |
| Per-layer: start time | Number |
| Per-layer: end time | Number |
| Per-layer: bold | Checkbox |
| Per-layer: outline enabled | Checkbox |
| Per-layer: outline px | Number 0–8 |
| Per-layer: shadow enabled | Checkbox |
| Per-layer: shadow X | Number −20 to 20 |
| Per-layer: shadow Y | Number −20 to 20 |
| Per-layer: BG box enabled | Checkbox |
| Per-layer: BG color | Color picker |
| Per-layer: BG padding | Number 0–64 |
| Per-layer: animation preset | Dropdown (5) |
| Per-layer: enabled toggle | Checkbox |
| Per-layer: locked toggle | Checkbox |

### 2.5 Audio Tab

| Control | Type |
|---|---|
| Source audio enabled | Checkbox |
| Source volume slider | Range 0–200 |
| Source volume number | Number 0–200 |
| BGM enabled | Checkbox |
| BGM volume slider | Range 0–100 |
| BGM gain number | Number 0.01–1.0 |
| BGM file path + browse | Text + button |
| BGM fade in (s) | Number 0–10 |
| BGM fade out (s) | Number 0–10 |
| Loudness normalization | Checkbox |

### 2.6 Export Tab

| Control | Type |
|---|---|
| Quick Start: TikTok/Reels preset | Button |
| Quick Start: Podcast Clip preset | Button |
| Quick Start: Clean Business preset | Button |
| Quick Start: High Quality preset | Button |
| Target Market | Dropdown (US/EU/JP) |
| Market Tone | Dropdown (Clean/Bold/Karaoke) |
| Auto Best Clips toggle | Checkbox |
| Keyword Highlight toggle | Checkbox |
| Auto Best Export toggle | Checkbox |
| Hook Card | Dynamic display |
| Analyze Market button | Button |
| AI Strategy Panel | Dynamic display |
| Creator Preset selector | Dropdown |
| Save preset | Button |
| Delete preset | Button |
| DNA / Series / Consistency hints | Dynamic displays (3) |
| Clip Steering Panel | Dynamic display |
| Reset Steering | Button |
| Rerender button | Button |
| Platform pills: YouTube/TikTok/Reels | Button group (3) |
| Multi-variant toggle | Toggle button |
| Subtitle pills: Off/Clean/Viral/Karaoke | Button group (4) |
| End Card toggle | Toggle button |
| Structure pills: Hook/Balanced/Story | Button group (3) |
| Expert Preset dropdown | Dropdown (6 options) |
| Aspect Ratio | Dropdown (3:4 / 9:16 / 1:1) |
| Output Profile | Dropdown (Fast/Balanced/Quality/Best) |
| Min clip (s) | Number 20–600 |
| Max clip (s) | Number 30–900 |
| Max clips | Number (0=no limit) |
| Add ending CTA toggle | Checkbox |
| CTA Type | Dropdown (conditional, 4 options) |
| Title Overlay toggle | Checkbox |
| Title Overlay text | Text input (conditional) |
| Subtitle Size emphasis | Dropdown (Subtle/Balanced/Aggressive) |
| Logo asset | File picker |
| Intro asset | File picker |
| Outro asset | File picker |
| Music Profile | Dropdown (No pref/Clean/Soft/Energetic) |
| Brand Subtitle | Dropdown (No pref/Clean/Viral/Karaoke/Bold) |
| Batch queue drop zone | Drag-and-drop area |
| Queue All + Clear buttons | Buttons |
| Queue list | Dynamic list |
| Render Device | Dropdown (Auto/CPU/GPU) |
| FPS | Dropdown (30/60) |
| Transform preset | Dropdown (None/Slight/Strong) |
| Reframe Mode | Dropdown (Center/Motion/Subject) |
| Hover preview toggle | Checkbox |
| Filmstrip toggle | Checkbox |
| Waveform toggle | Checkbox |
| Runtime Diagnostics panel | Read-only metrics (8 fields) |
| Refresh diagnostics | Button |
| Clear thumbs | Button |
| Clear waves | Button |
| Dev overlay | Button |
| Batch Mode toggle | Checkbox |
| Batch URLs textarea | Textarea |

### 2.7 AI Tab

| Control | Type |
|---|---|
| Chat history | Dynamic display |
| Quick input: "make intro stronger" | Button |
| Quick input: "too slow" | Button |
| Quick input: "clean subtitles" | Button |
| Quick input: "more energy" | Button |
| Quick input: "less jumpy" | Button |
| Text input field | Text input |
| Send button | Button |

### 2.8 Timeline

| Control | Type |
|---|---|
| Guides toggle | Button |
| Play/Pause | Button |
| Fit to window | Button |
| Zoom out / Zoom in | Buttons |
| Click-to-seek | Interactive zone |
| Clip segment (hover/select) | Interactive per-clip |
| Tracks: ruler, video, energy, wave, clips, AI, subs, text | Read-only displays (8) |

---

## 3. ESSENTIAL vs ADVANCED vs REDUNDANT vs DEAD WEIGHT

### A — ESSENTIAL

These are high-frequency, high-trust controls. Removing or hiding any of these hurts the core workflow.

| Control | Why Essential |
|---|---|
| Source input (URL / local file) | Gateway to everything |
| Output folder | Required output path |
| Platform pills (YouTube/TikTok/Reels) | Drives downstream decisions |
| Quick Style (Viral/Cinematic/Aggressive/Balanced) | Core creative direction |
| Max clips | Scope of output |
| Subtitle toggle | Major creator decision |
| Subtitle style + font + size + color | Creator brand identity |
| Trim in/out | Per-clip editing |
| Play / Pause / Seek | Fundamental editing |
| Creator Presets (save/load) | Encodes creator taste |
| Clip Steering (keep/avoid) | Creator teaches AI |
| Rerender button | Core creator loop |
| BGM toggle + file + volume | Creative element |
| Source volume | Basic audio control |
| Creator Assets (logo/intro/outro) | Brand identity |
| AI Conversational editing (AI Tab) | Semi-Opus moat |
| Tighten Cuts / Stronger Hook / Faster Pacing | High-value AI actions |
| Subtitle translation + target language | Market reach |
| Structure bias (Hook/Balanced/Story) | Content strategy |
| Auto Best Clips | Intelligent selection |
| Snapshots list | Undo with memory |
| Quick Start Presets (TikTok/Podcast/Business/HQ) | First-run simplification |

### B — ADVANCED

These are legitimate controls, but too technical or niche to surface by default. Move to an expandable Advanced panel or Settings.

| Control | Collapse Reason |
|---|---|
| Output Profile (Fast/Balanced/Quality/Best) | Most creators use Balanced always |
| FPS (30 / 60) | Platform-derived; AI can decide |
| Transform preset | Mechanical; AI can decide |
| Reframe Mode | Technical; AI can decide based on content |
| Render Device | Always auto; surfacing this causes confusion |
| Min clip duration | Most creators never change this |
| Max clip duration | Most creators never change this |
| BGM fade in/out | Useful but niche; default values work |
| Subtitle Y position | Position tweaking; default covers 90% of use |
| Subtitle X position | Same |
| Subtitle outline | Style detail; default covers 90% of use |
| CTA Type | "Auto" default covers 90% of cases |
| Title Overlay + text | Niche branding use case |
| Resume Job ID | Edge case; belongs in Settings |
| Source Quality Mode (hidden) | Technical; should stay hidden with auto-value |
| Part Order (hidden) | Always best-first; static default |
| Playback speed (hidden) | Legacy; static default |
| Loudness normalization | Should always be on; hide the toggle |
| Editor performance toggles (hover/filmstrip/waveform) | Power user system tuning |
| Batch Mode + URLs | Power user workflow |
| AI Narration (Words tab) | Niche feature; not primary workflow |
| Text layer advanced props (shadow X/Y, BG padding, lock, enabled) | Full motion graphics complexity |
| Multi-variant toggle | Power user output mode |
| Analyze Market button | Useful but non-critical; can be passive |

### C — REDUNDANT

These duplicate an existing control. Consolidate into the primary.

| Control | Duplicate Of | Action |
|---|---|---|
| AI Action: Viral Mode | Quick Style: Viral button | Remove AI Action version; Quick Style IS the variant |
| AI Action: Cinematic | Quick Style: Cinematic button | Same — remove from AI Actions |
| Expert Preset dropdown (TikTok US Viral, EU Clean Review…) | Quick Strategy Bar + Market dropdown | Expert Preset overlaps completely; remove or collapse |
| Brand Subtitle (Creator Assets) | Subtitle Style (Subtitles tab) | Same concept in two places — merge into Subtitles tab |
| Market Tone (Clean/Bold/Karaoke) | Subtitle pills in Quick Strategy Bar | Two controls for the same subtitle vibe choice — keep QS bar pills only |
| Subtitle Size emphasis (Export Advanced) | Subtitle Size slider (Subtitles tab) | Same setting, two locations |
| "Quick Subtitle Fix" link in Story tab | "Fix Subs AI" button in Subtitles tab | Same action; keep in Subtitles tab only |

### D — DEAD WEIGHT

These have low creator value. Removing them frees cognitive space without hurting any workflow.

| Control | Why Dead Weight | Risk |
|---|---|---|
| Runtime Diagnostics panel (FPS/Dropped/DOM/cache) | Developer-only; creators never interpret these | None |
| Dev overlay button | Developer-only | None |
| Clear thumbs / Clear waves buttons | Internal cache management; edge case | None |
| Frame Scale Y (hidden input) | Opaque mechanical parameter; legacy pipeline artifact | None |
| ReupMode (hidden checkbox) | Legacy repurposing feature; unknown usage | Low |
| Cleanup Temp (hidden checkbox) | Technical; should always be on | None |
| Render Insights / Benchmark grid | Developer analytics; no creator decision unlocked | None |
| Compare Panel (multi-render) | Very edge case; unclear if used | Low |
| Stage Timeline in render progress | Overly technical step-by-step breakdown | None |
| Hook Card display (Market section) | Unclear display purpose; rarely populated | None |
| AI Strategy Panel (`aiux_strategy_panel`) | Unclear display; no interaction | None |
| Log filter "FFmpeg" button | Developer filter inside creator log panel | None |
| DNA / Series / Consistency hint displays | Passive displays with low creator action rate | Low |

---

## 4. FILTER SYSTEM AUDIT

The filter system is the set of controls that influence **which clips get selected, how they're scored, and how outputs are configured**. These live across Export tab Advanced, hidden payload inputs, and Quick Strategy Bar.

### Keep Manual (Creator Taste)

These express creative preference. AI should learn from them, not replace them.

| Control | Why Keep |
|---|---|
| Platform (YouTube Shorts / TikTok / Reels) | The most fundamental creator decision |
| Quick Style (Viral / Cinematic / Aggressive / Balanced) | Defines creator's content identity |
| Subtitle style + font + color | Brand identity, not a mechanical decision |
| Subtitle language / translation target | Market strategy |
| Max clips | Creator decides output scope |
| Structure bias (Hook/Balanced/Story) | Intentional narrative decision |
| Clip Steering (keep/avoid) | Direct AI teaching signal |
| BGM on/off + file | Creative choice |
| Music Profile | Taste signal |
| Creator Assets | Brand identity |
| CTA toggle | Audience strategy |

### Move to Advanced (Useful but Niche)

| Control | Reason |
|---|---|
| Min/Max clip duration | Most creators never tune these; platform norms handle 90% |
| Output Profile (quality level) | Balanced is correct default; only hardware-constrained creators adjust |
| CTA type | "Auto" default works; control useful only for series creators |
| Title Overlay | Branding edge case |
| Aspect Ratio | Should be platform-derived (see AI ownership), but allow override in Advanced |

### AI Should Own (Mechanical Decisions)

These are engineering decisions disguised as creative ones. Creators shouldn't need to understand them.

| Control | AI Ownership Logic |
|---|---|
| Aspect Ratio | Platform → ratio is a table lookup: TikTok=9:16, YouTube Shorts=9:16, Reels=9:16, default=3:4 |
| FPS | Platform → fps is a table lookup: TikTok/Shorts=60, default=30. No creator decision needed |
| Transform preset | Content analysis → slight transform for talking heads, none for high-motion; AI knows |
| Reframe Mode | Content analysis → center crop for static, motion tracking for dynamic, subject tracking for interviews |
| Part Order | Always best-first; never expose this toggle |
| Frame Scale Y | Fully mechanical; static value or content-derived |
| Loudness normalization | Always on; broadcast standard; remove the toggle |
| Render Device | Always auto; creator has no meaningful preference here |
| Subtitle Size relative emphasis | Platform norms determine this; AI can pick based on platform + style |

### Legacy Complexity (Flag for Removal)

| Control | Diagnosis |
|---|---|
| Frame Scale Y (hidden) | Pre-AI scaling artifact; unclear semantic value |
| ReupMode (hidden) | Legacy repurposing workflow; likely zero usage in current flows |
| Playback Speed (hidden 1.07x) | Speed adjustment should be AI-decided based on energy level |
| Source Quality Mode (hidden) | Overlaps with Output Profile; pre-dates current architecture |
| Expert Preset dropdown | Predates Quick Strategy Bar; now fully redundant |

---

## 5. PRE-RENDER OVERLOAD

### Current visible controls before "Open Editor": 4

1. Source type (YouTube / Local)
2. URL or local file
3. Output folder
4. Resume Job ID

The pre-render surface is **not overloaded visually**. But it carries invisible weight:

- 20+ hidden payload fields are pre-configured before render but creators have no awareness of them
- Output folder is required as a gate — adds friction before any creative work starts
- Resume Job ID is an edge-case recovery control mixed into the primary setup flow

### What Should Become Auto

| Field | Auto Behavior |
|---|---|
| Output folder | Default to `./output/` relative to input file, or last-used folder |
| Aspect ratio | Derived from platform selection (happens in editor, not pre-render) |
| Render profile | Fixed default: Balanced |
| Render device | Fixed default: Auto |
| FPS | Derived from platform selection |
| Part order | Fixed: best-first |
| Frame Scale Y | Fixed: 106 (or remove concept) |
| Loudness normalization | Fixed: on |
| Cleanup temp | Fixed: on |

### What Should Only Appear After First Render

- Batch mode / batch URLs
- Advanced quality settings
- Resume Job ID (move to job history panel)
- Expert preset / output profile

### Pre-Render Ideal State (vNext)

```
[Input video or URL]
[Open Editor →]
```

Output folder auto-fills. All technical parameters auto-derive from platform selection inside the editor.

---

## 6. EDITOR OVERLOAD

### Verdict: Engineer Cockpit

The editor currently reads as an engineer cockpit for three structural reasons:

**1. Export tab is a kitchen sink.**
50+ controls in a single tab span: creator strategy (platform, style), output logistics (aspect, fps, CTA), creator assets (logo, BGM), developer diagnostics (cache, DOM metrics, dev overlay), and batch queue. These have completely different mental contexts and should not coexist in one panel.

**2. "Viral" appears in three places.**
- Story tab: Quick Style button "Viral"
- Story tab: AI Actions button "Viral Mode" (identical effect)
- Export tab: Subtitle pill "Viral" (subtitle styling, not clip selection)
- Creator sees three "Viral" buttons and doesn't know which one matters

**3. Developer tooling is unsegregated.**
Runtime Diagnostics (FPS/Dropped/DOM nodes/cache sizes), Dev Overlay button, Clear Thumbs, Clear Waves — these live inside the creator's Export tab. A creator clicking through settings encounters DOM node counts. This erodes trust and creates an impression the tool is unfinished.

### What Overwhelms Creators

| Area | Overload Symptom |
|---|---|
| Export tab Advanced | 8 dropdowns before seeing a render (Aspect/Profile/CTA/Transform/Reframe/FPS/Device/Expert) |
| Words tab text layer | 15+ controls per layer: more complex than most standalone text editors |
| Story tab AI Actions + Quick Styles | Two overlapping control sets for the same creative direction |
| Audio tab BGM fade | Fade in/out feel like Pro Tools; creators want "BGM on/off + volume" |
| Export tab hints (DNA/Series/Consistency) | Passive displays with no clear action; visual clutter |
| Market Tone + Subtitle pills | Two separate controls for the same decision (subtitle vibe) |

### Editor Ideal State

| Tab | Should Contain |
|---|---|
| Story | Trim + Quick Styles + Snapshots + single AI Actions set (no duplicates) |
| Subtitles | Toggle + Style + Font + Size + Color + Position (collapsed) + Translation |
| Words | Narration toggle + Text Layers (simplified: content, font, size, color, position, timing) |
| Audio | Source volume + BGM (toggle/file/volume) — fades in Advanced |
| Export | Platform + Structure bias + Max clips + Creator Assets + Creator Presets + Rerender |
| AI | Conversational editing |

Advanced Mode (unlocked in settings): everything else.

---

## 7. CURRENT AI INTERVENTION MAP

### Stage-by-Stage Analysis

| Stage | AI Level | Deterministic Level | Trust | Limitation |
|---|---|---|---|---|
| Input understanding | LIGHT | HEAVY | High | Whisper transcription only; no semantic content analysis |
| Scene detection | NONE | HEAVY | High | Threshold-based; works well; no AI needed here |
| Hook detection | MEDIUM | MEDIUM | Medium | Heuristic scoring + energy; misses semantic hooks |
| Segment scoring | MEDIUM | MEDIUM | High | Energy + engagement signal; reliable baseline |
| Clip ranking | MEDIUM | MEDIUM | Medium | Score-based; no AI reasoning surfaced to creator |
| Subtitle generation | HEAVY | NONE | High | Whisper; mature, stable, high trust |
| Subtitle styling | NONE | HEAVY | Medium | Preset-only; no content-aware style selection |
| Crop/framing | NONE | HEAVY | Medium | Rule-based center + motion tracking; no subject intelligence |
| Pacing | LIGHT | HEAVY | Medium | Heuristic; no content-aware pacing decisions |
| Edit suggestions | MEDIUM | NONE | Medium | AI actions use reasoning; not always transparent |
| Clip selection | MEDIUM | MEDIUM | High | Scoring + creator steering; reliable |
| Rerender decisions | NONE | HEAVY | High | Fully creator-driven; correct design |
| Creator preference learning | LIGHT | MEDIUM | Medium | Creator DNA via localStorage; limited signal capture |
| Export optimization | NONE | HEAVY | High | Preset-based; deterministic; correct |

### Key Observation

The system is **under-AI-ized** in reasoning and explanation, and **correctly deterministic** in execution. The problem is not AI doing too much — it's AI doing mechanical work (scoring) without showing the creator why.

---

## 8. AI OWNERSHIP CANDIDATES

### High ROI Interventions

| Opportunity | What AI Does | Creator Value | Implementation Risk |
|---|---|---|---|
| **Clip reranker explanation** | After deterministic rank, AI explains "why this clip won" in 1 sentence | High — transforms black-box scoring into legible reasoning | Low — inference on existing metadata |
| **Hook confidence score** | Visible signal on timeline: how confident AI is about the hook quality | High — creator knows where to focus attention | Low — extends existing hook detection |
| **Creator taste memory** | Learns from rerender + steering signals to pre-populate preferences | High — "the tool learns how I edit" moat | Medium — requires preference vector design |
| **Subtitle strategy auto-select** | Content type (talking head vs action) → subtitle style recommendation | Medium-High — removes a decision creator often gets wrong | Low — content classification is feasible |
| **AI-derived aspect ratio + FPS** | Platform selection → correct technical parameters automatically | Medium — removes decisions creators shouldn't need to make | Very Low — table lookup logic |

### Medium ROI Interventions

| Opportunity | Notes |
|---|---|
| Pacing intelligence | Detect monotone vs dynamic content; adjust pacing suggestion accordingly |
| Crop intelligence | Detect active speaker face position; inform reframe mode selection |
| Rerender suggestion | After reviewing clips, AI suggests "try more hook bias" if creator rejected first-ranked clips |

### Low ROI — Avoid

| Opportunity | Why Low ROI |
|---|---|
| AI-generated titles/CTAs | Too variable; erodes trust when suggestions are off |
| Full-video LLM editing pipeline | Slow, expensive, unpredictable; undermines rerender trust |
| AI music matching | Complex licensing, latency, low accuracy vs creator taste |
| AI-driven subtitle grammar cleanup | Whisper quality is already high; diminishing returns |

---

## 9. AI INTERVENTION VERDICT

**Current AI intervention score: Under-leveraged in reasoning, correctly sized in execution.**

The tool has a strong deterministic engine that produces reliable results. AI is correctly absent from encoding, timeline rendering, and progress management. Where AI exists (hook scoring, segment scoring, edit actions), it works but is opaque to the creator.

The gap is not more AI execution. The gap is **AI legibility and preference learning**.

### What Must Remain Deterministic

| System | Reason |
|---|---|
| Video encoding pipeline | Speed, consistency, cheap compute |
| Scene segmentation | Well-tuned heuristics outperform AI here; trust is high |
| Subtitle timing | Whisper handles this; don't add AI on top |
| Audio normalization | Technical standard; deterministic is correct |
| Progress tracking / queue | Reliability-critical; no AI in the loop |
| Rerender execution | Creator-commanded; must be predictable and instant |

### Where AI Belongs

```
Deterministic engine produces candidates
         ↓
AI reranker explains top candidates (V2.1)
         ↓
AI editor notes surface reasoning (V2.2)
         ↓
Creator acts (keep/avoid/rerender)
         ↓
Creator memory captures signal (V2.3)
         ↓
AI agent suggests next edit (V2.4)
```

---

## 10. SEMI-OPUS READINESS

### Target Creator Flow

```
Input video
    ↓
Choose: Platform + Style + Max clips
    ↓
AI generates optimized outputs
    ↓
Creator reviews clips with AI notes
    ↓
Clip steering (keep/avoid)
    ↓
Rerender
    ↓
Done
```

### Controls That Conflict with This Future

| Control | Conflict |
|---|---|
| 8 advanced dropdowns in Export Advanced | Forces configuration before AI can run; creates pre-AI paralysis |
| Expert Preset dropdown | Creates impression of manual orchestration; conflicts with AI-first flow |
| Market Tone + Subtitle pills overlap | Requires two decisions for one concept (subtitle vibe) |
| Transform/Reframe/FPS/Device settings | Creator shouldn't configure rendering; AI + platform should decide |
| Frame Scale Y | Opaque; creator cannot meaningfully interact |
| Edit Actions "Viral Mode" + Quick Style "Viral" | Duplicate controls at the creative steering layer create confusion |

### Minimum Viable Creator Input for Semi-Opus

```
Platform       → 1 click (YouTube/TikTok/Reels)
Style          → 1 click (Viral/Cinematic/Aggressive/Balanced)
Max clips      → 1 number
```

Everything else: AI-decided default or Advanced.

### What Moves to Advanced Mode

- Output Profile / Quality
- FPS override
- Transform override
- Reframe Mode override
- Min/Max clip duration
- Subtitle position fine-tuning
- BGM fade times
- CTA type selection
- Title Overlay
- Batch Mode

---

## 11. CAPCUT COMPARISON

### CapCut AI Cut

| Dimension | CapCut | This Tool |
|---|---|---|
| Time to first clip | < 60 seconds | 2–5 minutes (configuration overhead) |
| Pre-config required | None | Output folder + editor setup |
| Style control | 3–4 mood presets | Viral/Cinematic/Aggressive/Balanced + steering |
| Rerender | No | Yes — core loop |
| Clip steering | No | Yes — keep/avoid with memory |
| Subtitle quality | Good | Equal or better |
| Offline | No | Yes |
| Creator taste learning | No | Partial (Creator DNA) |
| Editor depth | Limited | Deep |

**Where CapCut beats us:** Time to first clip. Zero configuration. One-click flow.

**Where we beat CapCut:** Rerender trust. Creator steering. Offline. Editor depth. Taste memory.

**What CapCut would remove from our tool:** All of Export Advanced. All hidden payload inputs. Dev diagnostics. BGM fade controls. Frame Scale Y. Expert Preset.

**What we should NOT copy from CapCut:** Removing creator steering. Removing rerender control. Removing editor depth.

---

## 12. OPUS CLIP COMPARISON

### Opus Clip

| Dimension | Opus Clip | This Tool |
|---|---|---|
| Virality score visible | Yes — visible on each clip | No — black-box rank |
| Curation UX | Clean, card-based | Editor-based |
| Rerender | No | Yes |
| Clip steering | No | Yes |
| Subtitle quality | Good | Equal or better |
| Editor after clip selection | None | Full editor |
| Offline | No | Yes |
| SaaS / local | SaaS only | Local |
| Creator taste | No learning | Partial (Creator DNA) |
| Multi-clip batch | Yes | Yes |

**Where Opus beats us:** Virality score surfaced to creator. Cleaner curation flow. Better clip selection UX.

**Where we beat Opus:** Rerender. Editor. Offline. Creator steering. Taste learning.

**What Opus would automate from our tool:** All technical render settings. FPS, aspect ratio, profile. Transform and reframe. Part ordering.

**What Opus lacks that is our moat:** The creator can't teach Opus their style. Every Opus render starts from zero.

---

## 13. COMPETITIVE MOAT

**Core moat statement:**
> "CapCut edits videos. Opus picks clips. This tool learns how YOU edit."

### Moat Components

| Moat Element | How It's Expressed | Risk if Removed |
|---|---|---|
| Clip Steering (keep/avoid) | Creator manually marks clips → feeds future renders | Becomes generic; no learning signal |
| Creator Presets | Encodes full render recipe; reusable | Loses brand consistency across sessions |
| Rerender trust | Creator knows rerenders are deterministic + fast | Kills confidence in iteration loop |
| Creator DNA | Accumulates taste from steering + preset behavior | Loses differentiation from CapCut |
| Editor depth (after AI selection) | Creator can fine-tune AI output | Loses control parity with desktop editors |
| Offline | Privacy + zero API cost | Would require SaaS conversion |

### What Must Never Be Removed in Reduction

1. Clip Steering (keep/avoid per clip)
2. Rerender button + rerender predictability
3. Quick Style variants (Viral/Cinematic/Aggressive/Balanced)
4. Creator Presets
5. Structure bias (Hook/Balanced/Story)
6. Trim per clip
7. AI Conversational editing (semi-opus anchor)
8. Subtitle control quality

---

## 14. REDUCTION DECISION MATRIX

### Phase A — Remove

Safe to remove. Low/no creator impact. No moat contribution.

| Item | Severity | Creator Impact | Impl. Difficulty | Risk | Reasoning |
|---|---|---|---|---|---|
| Runtime Diagnostics panel | Medium | None | Easy | None | Developer tool inside creator interface |
| Dev overlay button | Low | None | Easy | None | Developer-only |
| Clear thumbs / Clear waves | Low | None | Easy | None | Cache management; not creator-relevant |
| Frame Scale Y (hidden) | Medium | None | Easy | Low | Opaque legacy parameter; no creator meaning |
| ReupMode (hidden) | Medium | None | Easy | Low | Legacy feature; verify zero active usage first |
| Cleanup Temp (hidden) | Low | None | Easy | None | Always-on technical parameter |
| AI Action: Viral Mode | Medium | Low | Easy | None | Exact duplicate of Quick Style: Viral |
| AI Action: Cinematic (action) | Medium | Low | Easy | None | Exact duplicate of Quick Style: Cinematic |
| Expert Preset dropdown | High | Low | Easy | Low | Fully superseded by Quick Strategy Bar; verify no active usage |
| Render Insights / Benchmark grid | Medium | None | Easy | None | Developer analytics |
| Log filter "FFmpeg" button | Low | None | Easy | None | Developer-facing filter |
| Hook Card display | Low | None | Easy | None | Unclear display; no interaction |
| AI Strategy Panel display | Low | None | Easy | None | Unclear display; no interaction |
| Compare Panel (multi-render) | Low | None | Easy | Low | Edge case; verify active usage |
| Stage Timeline in progress | Low | None | Easy | None | Engineering detail; progress bar is sufficient |

### Phase B — Collapse to Advanced

Legitimate controls that create overload when visible by default.

| Item | Severity | Creator Impact | Impl. Difficulty | Risk | Reasoning |
|---|---|---|---|---|---|
| Output Profile (quality) | High | Medium | Easy | Low | Default Balanced covers 90%; only hardware-constrained users touch this |
| FPS selector | High | Low | Easy | None | Platform-derived; see Phase C |
| Transform preset | High | Low | Easy | None | AI ownership candidate; see Phase C |
| Reframe Mode | High | Low | Easy | None | AI ownership candidate; see Phase C |
| Render Device | Medium | None | Easy | None | Always auto; visual clutter |
| Min/Max clip duration | High | Medium | Easy | Low | Platform norms cover defaults; advanced for fine control |
| BGM fade in/out | Medium | Low | Easy | None | Default 1s/2s is universally correct |
| Subtitle X/Y position | Medium | Low | Easy | None | Default position works; fine-tune in advanced |
| Subtitle Outline | Low | Low | Easy | None | Default 3px works; niche preference |
| CTA Type | Medium | Low | Easy | None | "Auto" default covers 90% of intent |
| Title Overlay | Medium | Low | Easy | None | Branding edge case |
| Resume Job ID | Medium | Low | Easy | None | Move to job history / Settings |
| Source Quality Mode (hidden) | Low | None | Easy | None | Keep hidden with auto-value |
| Playback Speed (hidden) | Low | None | Easy | None | Keep hidden with static default |
| Loudness normalization | Medium | Low | Easy | None | Always-on; remove toggle, keep behavior |
| Part Order (hidden) | Low | None | Easy | None | Always best-first; hardcode |
| Hover/Filmstrip/Waveform toggles | Low | Low | Easy | None | Move to Settings |
| Market Tone dropdown | High | Medium | Easy | Low | Merge with Subtitle pills (QS Bar already has Clean/Viral/Karaoke) |
| Brand Subtitle (Creator Assets) | Medium | Low | Easy | None | Merge into Subtitles tab; remove from Assets |
| Subtitle Size emphasis (Export) | Medium | Low | Easy | None | Duplicate of Subtitles tab size slider; remove from Export |
| Text layer advanced props (shadow, BG, lock) | Medium | Low | Moderate | Low | Collapse into expandable section within layer |
| AI Narration (Words tab) | Medium | Low | Easy | Low | Power user feature; collapse by default |
| Multi-variant toggle | Medium | Medium | Easy | Low | Advanced output mode; not primary workflow |
| Batch Mode + URLs | Medium | Low | Easy | None | Power user; collapse behind Advanced |
| DNA/Series/Consistency hints | Low | Low | Easy | None | Move to subtle passive indicator, not three separate display areas |
| Analyze Market button | Low | Low | Easy | None | Passive intelligence; collapse or make automatic |
| Quick Subtitle Fix link (Story tab) | Low | Low | Easy | None | Duplicate of Fix Subs in Subtitles tab; remove from Story tab |

### Phase C — AI Ownership

Creator should not make these decisions. The system knows better or can derive the answer.

| Item | AI Logic | Severity | Creator Impact | Impl. Difficulty | Risk |
|---|---|---|---|---|---|
| Aspect Ratio | Platform → ratio table lookup | High | None | Easy | None |
| FPS | Platform → fps table lookup | High | None | Easy | None |
| Part Order | Always best-first; hardcode | Medium | None | Easy | None |
| Render Device | Always auto; hardcode | Low | None | Easy | None |
| Loudness normalization | Always on; hardcode | Medium | None | Easy | None |
| Transform preset | Content analysis → slight for most; motion for high-energy | High | Low | Moderate | Low |
| Reframe Mode | Content analysis → center/motion/subject based on video type | High | Low | Moderate | Low |
| Subtitle Size relative emphasis | Platform + style → size norm | Medium | Low | Easy | Low |

### Phase D — Keep Manual (Creator Taste & Moat)

These are the core. Protect them. Never remove or auto-decide without explicit creator confirmation.

| Item | Why Keep |
|---|---|
| Platform (YouTube Shorts / TikTok / Reels) | Most fundamental strategic decision |
| Quick Style (Viral/Cinematic/Aggressive/Balanced) | Creative identity; moat anchor |
| Subtitle style + font + size + color | Brand identity |
| Subtitle language / translation | Market strategy |
| Max clips | Creator controls output scope |
| Structure bias (Hook/Balanced/Story) | Narrative intent |
| Clip Steering (keep/avoid) | Primary AI teaching signal; core moat |
| Creator Presets (save/load) | Encodes taste; reusable |
| Rerender | Creator-commanded; must stay explicit |
| BGM toggle + file + volume | Creative expression |
| Creator Assets (logo/intro/outro) | Brand expression |
| Music Profile | Taste signal |
| CTA toggle | Audience strategy |
| AI Conversational editing | Semi-Opus anchor feature |
| Tighten Cuts / Stronger Hook / Faster Pacing | High-trust AI actions |
| Trim in/out | Per-clip editing |
| Snapshots | Revert with memory |

---

## 15. V2.1 → V2.4 UPGRADE ROADMAP

### V2.1 — AI Reranker

**Goal:** Make clip ranking legible to creator. Move from black-box score to explained rank.

**What AI sees:**
- Transcript excerpt (first 60s of clip)
- Energy score from deterministic engine
- Hook score from deterministic engine
- Creator DNA (platform preference, style, past steering decisions)
- Clip position relative to source video

**What AI outputs:**
- Adjusted confidence score (0–1)
- One-sentence reason ("Strong hook in first 5 seconds with clear value proposition")
- Ranked position (may differ from deterministic rank)

**What creator sees:**
- Rank badge on each clip card in review queue
- One-line AI note beneath clip thumbnail
- Original deterministic score still visible (small, secondary)

**Trust preservation:**
- Reranker adjusts but doesn't replace; original rank always accessible
- Creator can override by clip steering
- No silent changes; AI note is always visible when AI influenced rank

**Scope:** Inference only on top 10 candidates. Engine still handles scoring for all clips. AI reranks the shortlist.

---

### V2.2 — AI Editor Notes

**Goal:** Surface reasoning inside the editor so creator understands what AI did and why.

**What this is:**
- Each clip in the timeline gets a passive note explaining why it was included
- Format: "High energy opening, strong hook confidence (87%), good pacing"
- Notes appear as tooltip or small badge in Clips track

**Creator feedback loop:**
- Thumbs up/down on clip notes → improves future AI note quality
- Negative feedback propagates to creator memory (V2.3)
- Notes are passive — creator is never blocked by them

**What to avoid:**
- Notes that are too verbose (1 sentence max)
- Notes that auto-apply any change
- Notes that appear every render cycle unprompted

**Scope:** Post-render, rendered once per clip, cached until next rerender.

---

### V2.3 — Creator Memory

**Goal:** Build a persistent taste model from creator behavior, not from creator configuration.

**Signals to capture:**

| Signal | What It Means |
|---|---|
| Rerender after Viral style → kept more clips | Creator has high-energy content preference |
| Rerender after Cinematic → shorter clips preferred | Creator prefers pacing quality over clip count |
| Consistently locks first 2 clips | Creator always wants strong hook coverage |
| Subtitle style always set to Karaoke | Brand identity preference |
| BGM always enabled + energetic profile | Audio is a brand signal |
| Consistently avoids clips with talking heads only | Prefers action/b-roll heavy content |

**What is stored:**
- Lightweight preference vector (JSON, localStorage + optional cloud sync)
- Per-field: last 5 explicit values + implicit signal strength
- TTL: 6 months per signal; decays if contradicted

**How it influences the product:**
- Pre-populates Quick Style on new renders
- Influences default structure bias
- Feeds AI Reranker (V2.1) as context
- Shows as subtle "based on your preference" hints (not forced)

**What it does NOT do:**
- Change settings without creator seeing it
- Override explicit creator choices
- Operate silently without surfacing a signal

**Trust rule:** Creator Memory only applies as a suggestion. Explicit creator choice always wins.

---

### V2.4 — Agent Editor

**Goal:** Add a lightweight AI suggestion layer inside the editor. Not auto-editing. Triggered suggestions.

**Trigger conditions:**
- After AI generates clips: if hook confidence is low across all clips → suggest "Stronger Hook"
- After creator reviews clips: if majority are rejected → suggest "Try Cinematic style — your content has slower pacing"
- If subtitle style hasn't been set and content is high-energy → suggest "Viral subtitles tend to perform better for this type of content"

**Format:**
- 1–3 suggestions max per session
- Each suggestion is a clickable action button (never auto-applied)
- Suggestions disappear after action or dismissal
- Creator can disable suggestions entirely in Settings

**What to avoid:**
- More than 3 suggestions at once
- Suggestions that auto-execute
- Suggestions that repeat if dismissed
- Suggestions without an action button

**Scope:** Suggestions live in a dismissible banner above the inspector, or as a compact pill in the AI tab. Not a chat interface (that's V2.3+ AI conversational editing, which already exists).

---

## 16. FINAL RECOMMENDED CREATOR WORKFLOW

### Ideal V2.x Flow

```
[1] Input
    → Video URL or local file
    → Output folder: auto-fills

[2] One-screen setup (pre-render)
    → That's it. Open Editor.

[3] Editor first screen
    → Platform: YouTube Shorts / TikTok / Reels
    → Style: Viral / Cinematic / Aggressive / Balanced
    → Max clips: [number]
    → [Start Render]

[4] Review queue
    → Clips presented with AI notes (V2.1 + V2.2)
    → Keep / Avoid / Trim per clip
    → Structure bias visible and adjustable

[5] Refine
    → Subtitle style
    → BGM
    → Creator Assets
    → Rerender if needed

[6] Export
    → Done
```

**Advanced mode unlocks in Settings:**
All B-class controls. Technical overrides. Batch mode. Expert presets.

### Control Count Target

| Area | Today | Target |
|---|---|---|
| Pre-render visible | 4 | 2 |
| Editor primary visible | 50+ | ~20 |
| Editor advanced (collapsed) | — | ~35 |
| Developer-only (removed) | ~20 | 0 |
| AI-owned (invisible) | 0 | ~8 |
| Total creator decisions on first render | ~15 | ~5 |

---

*Audit completed: 2026-05-19. Branch: `feature/ai-output-upgrade`. Stage: V1 RC → V2 preparation.*
*Source of truth: actual HTML controls, IDs, and JS handlers inventoried from live codebase.*
