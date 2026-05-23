# Tier 1 Screen Layouts — v2
Phase B3/B3.5 | 2026-05-23

B3.5 refinements applied:
- Timeline: 3 tracks only (Video · Subtitle · AI Markers)
- Source/Home: minimal — no analytics, no momentum hero
- Results: single-pane v1 — no right inspector
- Tone: professional, not dramatic

All measurements reference tokens from `docs/design/tokens.css`.

---

## 1. App Shell (shared)

```
┌─────────────────────────────────────────────────────────────┐
│ TOPBAR (48px)   [AI Clip Studio]        [System ●] [⋯]      │
├──────────┬──────────────────────────────────────────────────┤
│          │  STEP STRIP (40px — Source/Studio/Monitor only)   │
│ SIDEBAR  ├──────────────────────────────────────────────────┤
│ (220px)  │                                                   │
│          │              CONTENT AREA                         │
│  Source  │         (fills remaining height)                  │
│  Studio  │                                                   │
│  Monitor │                                                   │
│  Results │                                                   │
│  ──────  │                                                   │
│  Library │                                                   │
│  Downloads                                                   │
│  ──────  │                                                   │
│  System  │                                                   │
│          │                                                   │
└──────────┴──────────────────────────────────────────────────┘
```

**Topbar:**
- Background: `--surface-panel`, border-bottom `--border-subtle`
- Product wordmark: `--text-primary` `--text-md` `--weight-semibold`
- System indicator: colored dot (green=healthy, amber=degraded, red=missing dep)
- Height: `--topbar-height` (48px), never scrolls away

**Sidebar:**
- Background: `--surface-panel`, border-right `--border-subtle`
- Width: `--sidebar-width` (220px), fixed — no collapse in v1
- Nav items: see component spec #1
- Group separator: 1px `--border-subtle` with `--space-1` margin

**Step Strip:**
- Only visible on Source, Studio, Monitor, Results screens
- Background: `--surface-panel`, border-bottom `--border-subtle`
- See component spec #2

---

## 2. Source Screen

**Purpose:** Start a render job. Minimal. No analytics.

```
CONTENT AREA:
┌────────────────────────────────────────────────────────────┐
│                                                            │
│  New Source                                                │
│  ─────────────────────────────────────────────────────     │
│                                                            │
│  [ YouTube URL or local path ________________________ ]    │
│  [ Browse local file ▸ ]                                   │
│                                                            │
│  Output destination                                        │
│  [ Channel / folder selector ________________________ ]    │
│                                                            │
│  Quality mode   ○ Fast  ● Standard  ○ High                 │
│                                                            │
│  [          Prepare Source          ]  ← primary button    │
│                                                            │
│  ─── Source Readiness ──────────────────────────────────   │
│  ○  Duration: —                                            │
│  ○  Preview: —                                             │
│  ○  Transcript: —                                          │
│  ○  Output: —                                              │
│                                                            │
│  ─── Recent ────────────────────────────────────────────   │
│  [job row] [job row] [job row]  ← max 3, links to Library  │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Layout rules:**
- Single column, max-width 640px, centered in content area
- No hero sections, no illustrations, no marketing copy
- Source readiness section only visible after Prepare is triggered
- Recent jobs section: 3 rows max with status pill + truncated source title
- "Continue in Library →" link below recent rows if more than 3

**Source readiness states (each row):**
- Waiting: `--text-tertiary` dot, label dimmed
- Checking: spinner dot, `--text-secondary`
- Ready: `--status-success` dot, `--text-primary`
- Failed: `--status-error` dot, `--text-primary`, error message inline

**Failure presentation:**
- Inline below the failed item — not a modal
- Actionable: "Check URL", "Ensure file exists", etc.

---

## 3. Studio Screen

**Purpose:** Configure the render draft. Contains 3-track timeline.

```
CONTENT AREA (Studio):
┌──────────────────────────────────────┬───────────────────┐
│                                      │                   │
│  PREVIEW PANEL                       │  INSPECTOR (320px)│
│  (fills left column)                 │                   │
│  [video player 16:9]                 │  ▾ Clip Settings  │
│  [trim handles] [timecode]           │    Duration       │
│  [▶] [vol] [⟲]                       │    Max clips      │
│                                      │    Overlap        │
│  ── 3-TRACK TIMELINE ───────────────  │                   │
│  VIDEO   ██████████████              │  ▸ Subtitle       │
│  SUBS    ██  ████  ██  ██            │  ▸ Voice          │
│  AI      ▲▲      ▲     ▲▲           │  ▸ AI Assistance  │
│  [zoom] [scroll]                     │  ▸ Platform       │
│                                      │                   │
│  [← Back to Source]  [Submit Render →]  ← action row     │
└──────────────────────────────────────┴───────────────────┘
```

**Preview panel:**
- Left column, flexible width (content-area minus inspector)
- Video player: 16:9 aspect ratio container, black letterbox
- Trim handles below player, drag to set in/out points
- Transport: play/pause, volume, loop toggle, timecode display

**3-Track Timeline:**
- Below video player
- Track height: 24px each
- Track labels: 52px fixed left column (`--text-xs` `--text-tertiary`)
- Scrollable horizontally, zoomable (scroll wheel or zoom control)
- Tracks:
  1. **VIDEO** — solid block showing source duration, trim selection highlighted
  2. **SUBS** — segmented blocks per subtitle segment (color: `--accent-subtle`)
  3. **AI MARKERS** — triangular markers (▲) at AI-detected high-retention moments (color: `--ai-subtle`)
- No more tracks in v1. No energy/waveform/text layers tracks.

**Inspector:**
- Right column, `--inspector-width` (320px) fixed
- Collapsible sections (component spec #9)
- Default open: Clip Settings
- Sections: Clip Settings / Subtitle / Voice / AI Assistance / Platform
- No scroll-jank: each section collapses/expands in place

**Action row:**
- Fixed to bottom of content area (not floating)
- Left: "← Back to Source" (ghost button)
- Right: "Submit Render" (primary button, disabled if draft invalid)
- Validation error appears inline above action row, not modal

---

## 4. Monitor Screen

**Purpose:** Track active job execution. Bottom panel for logs.

```
CONTENT AREA (Monitor):
┌────────────────────────────────────────────────────────────┐
│                                                            │
│  Job: [source title truncated]        [Status Pill]        │
│  Started: 14:32 · Est. completion: 14:47                   │
│                                                            │
│  Overall progress ██████████████░░░░░░░░ 62%              │
│                                                            │
│  ── Parts ──────────────────────────────────────────────   │
│  [Part 1] [completed]  ████████████████████████  100%     │
│    Finished in 2m 14s                                      │
│  [Part 2] [running]    █████████████░░░░░░░░░░░   58%     │
│    Transcribing audio…                                     │
│  [Part 3] [queued]     ░░░░░░░░░░░░░░░░░░░░░░░░    —      │
│                                                            │
│  [Retry failed] [Cancel]               (if applicable)    │
│                                                            │
├────────────────────────────────────────────────────────────┤
│  BOTTOM PANEL (240px) [Logs ▾] [close ×]                   │
│  14:33:01 [INFO] Part 1 stage: subtitle_render complete     │
│  14:33:08 [INFO] Part 2 stage: transcribe started          │
│  14:33:09 [DEBUG] Whisper model loaded in 0.8s             │
│  …                                                         │
└────────────────────────────────────────────────────────────┘
```

**Job header:**
- Source title (truncated at 60 chars)
- Status pill (component spec #5) — right-aligned
- Start time, estimated completion (if available)

**Overall progress bar:**
- Height: 8px, `--radius-sm`
- Fill: `--status-running` animated shimmer while running
- Text: percentage right of bar

**Part rows (component spec #7):**
- Collapsed by default to show only Part label, status, progress
- Expandable to show: current stage name, elapsed, log count
- Border-bottom `--border-subtle` between rows

**Bottom panel — Logs:**
- Toggle open/closed (default: closed; auto-opens on warning/error)
- Background: `--surface-base`, border-top `--border-default`
- Font: `--font-mono` `--text-xs` `--text-secondary`
- Log level coloring: INFO `--text-tertiary` / WARN `--status-warning` / ERROR `--status-error`
- Auto-scrolls to bottom while running; user can scroll up to pause auto-scroll
- "↓ Jump to latest" button appears when user has scrolled up

---

## 5. Results Screen (single-pane v1)

**Purpose:** Review and act on completed render package.

```
CONTENT AREA (Results):
┌────────────────────────────────────────────────────────────┐
│  Results — [source title]                     [job status]  │
│  [N clips] · [timestamp] · [Open folder ↗]                 │
│                                                             │
│  ── Best Clip ──────────────────────────────────────────   │
│  [thumbnail 9:16, 160px wide]  Score: [84 — HIGH badge]    │
│  Part 2 · 1:24   ⚡ AI Applied                             │
│  "Hook identified at 0:04. Retention predicted 78%."       │
│  [▶ Preview]  [↓ Export]                                   │
│                                                             │
│  ── All Clips ──────────────────────────────────────────   │
│  [clip card] [clip card] [clip card] [clip card]           │
│  [clip card] [clip card]                                   │
│                                                             │
│  ── Failed Parts ───────────────────────────────────────   │
│  Part 4: subtitle_render failed — codec mismatch            │
│  [Retry Part 4]                                            │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

**No right inspector in v1.** All information is inline.

**Best Clip section:**
- Always first
- Thumbnail: 160px wide, 9:16 aspect, `--radius-lg`
- Score: `--text-2xl` colored by threshold (component spec #4)
- AI explanation: 1–2 lines, `--text-secondary`, no truncation
- Actions: Preview (ghost), Export (secondary)

**All Clips grid:**
- Responsive grid: 4 columns at 1280px+, 3 at 1024px, 2 at 800px
- Clip card (component spec #3)
- Sorted by `output_rank_score` descending, best clip excluded (shown above)
- "Export All" button above grid, right-aligned

**Failed Parts section:**
- Only shown if any parts failed or are partial
- Background: `--status-error-bg`, rounded `--radius-md`
- Per-failed-part: part name, error reason (truncated), Retry action
- Partial success shown separately with `--status-partial-bg`

**Score reveal animation:**
- When Results screen loads, all clip scores animate count-up simultaneously
- See `motion.md` for `score-count-up` keyframe
