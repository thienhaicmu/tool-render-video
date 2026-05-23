# Design System — Component Specs v2
Phase B3/B3.5 | 2026-05-23

All components use tokens from `docs/design/tokens.css`.
Desktop-only layout. React implementation target: `frontend/src/`.

---

## 1. Sidebar Nav Item

**Purpose:** Primary navigation between Source / Studio / Monitor / Results / Library / Downloads / System.

**Anatomy:**
```
[icon 18px] [label 13px medium] [optional: notification dot]
```

**States:**

| State | Background | Text | Icon | Left accent bar |
|-------|-----------|------|------|----------------|
| Default | transparent | `--text-secondary` | `--text-tertiary` | none |
| Hover | `--surface-card` | `--text-primary` | `--text-secondary` | none |
| Active | `--accent-subtle` | `--accent-primary` | `--accent-primary` | 2px `--accent-primary` |
| Disabled | transparent | `--text-disabled` | `--text-disabled` | none |

**Dimensions:**
- Height: 36px
- Padding: `0 12px`
- Icon: 18×18px, `--radius-sm`
- Label: `--text-base` `--weight-medium`
- Left accent bar: `2px × 20px`, vertically centered

**Behavior:**
- Click navigates; active state is set by router.
- Notification dot: 6px circle `--status-warning` when a job needs attention.

---

## 2. Step Indicator Strip

**Purpose:** Linear workflow progress — Source → Studio → Monitor → Results.

**Anatomy:**
```
[step 1: label + number] [connector] [step 2] [connector] [step 3] [step 4]
```

**States per step:**

| State | Number bg | Number text | Label | Connector |
|-------|----------|-------------|-------|-----------|
| Done | `--status-success` 20% | `--status-success` | `--text-secondary` | `--status-success` line |
| Active | `--accent-primary` | white | `--text-primary` semibold | `--border-default` |
| Upcoming | `--surface-card` | `--text-tertiary` | `--text-tertiary` | `--border-subtle` |
| Blocked | `--status-error` 15% | `--status-error` | `--text-secondary` | `--border-subtle` dashed |

**Dimensions:**
- Strip height: `--step-strip-height` (40px)
- Number circle: 22px diameter
- Number: `--text-sm` `--weight-semibold`
- Label: `--text-base`
- Connector: 1px horizontal line, `--space-3` margin each side

**Behavior:**
- Past steps are clickable (navigate back, confirm draft not lost).
- Future steps are non-clickable until previous step completes.
- Active step label is always fully visible; others can truncate.

---

## 3. Clip Card

**Purpose:** Display one rendered output clip with score and key metadata.

**Anatomy:**
```
┌──────────────────────────────────────────────┐
│  [thumbnail 16:9]                            │
│  ├── [BEST badge if is_best_output]           │
│  └── [score badge: 84]                       │
├──────────────────────────────────────────────┤
│  Part 3 · 1:24                [⚡ AI Applied] │
│  Hook score reason truncated…                │
│  [▶ Preview] [↓ Export] [⋯ More]             │
└──────────────────────────────────────────────┘
```

**States:**

| State | Border | Background | Shadow |
|-------|--------|-----------|--------|
| Default | `--border-subtle` | `--surface-card` | `--shadow-card` |
| Hover | `--accent-subtle-hover` | `--surface-card-hover` | `--shadow-panel` |
| Selected | `--accent-primary` 1px | `--surface-card-hover` | `--shadow-panel` |
| Best | `--score-high` 1px | `--surface-card` | `--shadow-card` |

**Dimensions:**
- Width: flexible (grid column)
- Thumbnail aspect: 9:16 (vertical clip preview)
- Radius: `--radius-lg`
- Metadata row: `--text-sm` `--text-secondary`

**Score Badge:**
- Size: 36×36px circle, positioned bottom-right of thumbnail
- Font: `--text-xl` `--weight-semibold`
- Color: `--score-high` / `--score-mid` / `--score-low` based on value
- Background: `--surface-base` with 80% opacity ring

**BEST Badge:**
- Position: top-left of thumbnail, `--space-2` inset
- Background: `--score-high`
- Text: "BEST" `--text-xs` `--weight-semibold` `--text-inverse`
- Radius: `--radius-sm`

**Appearance animation:** See `motion.md` `clip-card-appear`.

---

## 4. Score Badge (standalone)

**Purpose:** Display a numeric score 0–100 with semantic color. Used in clip cards, summaries, inspector.

**Anatomy:**
```
[numeric value, 1–3 digits]
```

**Sizes:**

| Size | Font | Use |
|------|------|-----|
| xl | `--text-score-xl` (64px) | Full-screen score reveal |
| lg | `--text-2xl` (24px) | Inspector score |
| md | `--text-xl` (20px) | Card score |
| sm | `--text-md` (14px) | Row score |

**Color thresholds:**
- `--score-high` (#34C878) — value ≥ 70
- `--score-mid` (#F5A623) — value 40–69
- `--score-low` (#E05252) — value < 40

**Animation:** Count-up from 0 over `--duration-score`. See `motion.md`.

---

## 5. Status Pill

**Purpose:** Compact status indicator. Used in Library rows, Monitor part rows.

**Anatomy:**
```
[dot 6px] [label]
```

**Variants:**

| Status | Dot color | Text | Background |
|--------|----------|------|-----------|
| queued | `--status-queued` | "Queued" | `--status-queued-bg` |
| running | `--status-running` | "Running" | `--status-running-bg` |
| completed | `--status-success` | "Completed" | `--status-success-bg` |
| partial | `--status-partial` | "Partial" | `--status-partial-bg` |
| failed | `--status-error` | "Failed" | `--status-error-bg` |
| interrupted | `--status-interrupted` | "Interrupted" | `--status-warning-bg` |

**Dimensions:**
- Height: 22px
- Padding: `0 8px`
- Dot: 6px circle
- Font: `--text-xs` `--weight-medium`
- Radius: `--radius-sm`

**Running animation:** Dot pulses (opacity 1→0.4→1, 1.2s infinite ease-in-out).

---

## 6. AI Advisory Chip

**Purpose:** Indicate AI phase applied or advisory state for a clip or setting.

**Anatomy:**
```
[⚡ icon 12px] [label]
```

**Variants:**

| Variant | Icon color | Text | Background |
|---------|-----------|------|-----------|
| applied | `--ai-active` | "AI Applied" | `--ai-subtle` |
| advisory | `--ai-active` 60% | "AI Advisory" | `--ai-subtle` 60% |
| skipped | `--text-tertiary` | "AI Skipped" | `--surface-card` |
| unavailable | `--text-disabled` | "AI Unavailable" | transparent |

**Dimensions:**
- Height: 20px
- Padding: `0 6px`
- Icon: 12×12px
- Font: `--text-xs` `--weight-medium`
- Radius: `--radius-sm`

---

## 7. Progress Row (Render Part)

**Purpose:** Display per-part render progress in Monitor and job detail views.

**Anatomy:**
```
[Part N label] [status pill]     [progress bar ──────░░] [percentage]
[stage label: "Transcribing…"]                           [elapsed time]
```

**States:**

| State | Progress bar fill | Row bg |
|-------|------------------|--------|
| queued | `--score-track-bg` (empty) | `--surface-card` |
| running | `--accent-primary` animated | `--surface-card` |
| completed | `--status-success` | `--surface-card` |
| failed | `--status-error` | `--status-error-bg` |
| partial | `--status-partial` | `--surface-card` |

**Dimensions:**
- Row height: 56px
- Progress bar height: 4px, `--radius-sm`
- Progress bar track: `--score-track-bg`
- Row padding: `--space-3 --space-4`
- Border bottom: 1px `--border-subtle`

**Running animation:** Indeterminate shimmer on progress bar if percentage not available.

---

## 8. Action Button

**Purpose:** Primary actions (Submit render, Export, Retry) and secondary/ghost/danger variants.

**Anatomy:**
```
[optional: icon 16px] [label]
```

**Variants:**

| Variant | Background | Text | Border | Use |
|---------|-----------|------|--------|-----|
| primary | `--accent-primary` | white | none | Render submit, main CTA |
| secondary | `--surface-card` | `--text-primary` | `--border-default` | Secondary actions |
| ghost | transparent | `--accent-primary` | `--accent-subtle` | Tertiary actions |
| danger | `--status-error` 15% | `--status-error` | `--status-error` 40% | Destructive |

**States for all variants:**

| State | Opacity / Effect |
|-------|-----------------|
| Hover | Background lightens by ~8% |
| Pressed | Background darkens by ~8% |
| Disabled | 40% opacity, cursor not-allowed |
| Loading | Icon replaced by spinner, text unchanged |

**Sizes:**

| Size | Height | Padding | Font |
|------|--------|---------|------|
| sm | 28px | `0 10px` | `--text-sm` |
| md | 32px | `0 14px` | `--text-base` |
| lg | 40px | `0 20px` | `--text-md` |

**Radius:** `--radius-md`

---

## 9. Inspector Section Header

**Purpose:** Collapsible section label in inspector/settings panels.

**Anatomy:**
```
[▸ chevron] [Section Title]         [optional: badge count]
```

**States:**

| State | Chevron | Background |
|-------|---------|-----------|
| Collapsed | ▸ (right) | transparent |
| Expanded | ▾ (down) | transparent |
| Hover | — | `--surface-card-hover` |

**Dimensions:**
- Height: 32px
- Padding: `0 --space-4`
- Font: `--text-sm` `--weight-semibold` `--text-secondary`
- Chevron: 14×14px, animated 90° on expand/collapse (`--duration-fast`)
- Separator: 1px `--border-subtle` above section

---

## 10. Empty State

**Purpose:** Placeholder for sections with no content. Used in Library (no jobs), Results (no clips), Clip list.

**Anatomy:**
```
[icon 32px, optional]
[Primary message — text-secondary]
[Secondary hint — text-tertiary]
[optional: CTA button]
```

**Variants:**

| Variant | Icon | Primary | Secondary | CTA |
|---------|------|---------|-----------|-----|
| no-jobs | folder-open | "No render jobs yet" | "Start a new source above" | "New Source" (ghost) |
| no-clips | film | "No clips in this job" | "Run a render to see clips here" | — |
| source-needed | arrow-up | "Open a source to continue" | "YouTube URL or local video file" | — |
| ai-unavailable | cpu | "AI features unavailable" | "Check System for diagnostics" | "Open System" (ghost) |

**Layout:**
- Centered in container
- Icon: `--text-tertiary` 32px
- Gap: `--space-4` between elements
- Max width: 320px
- No background, no border — integrated into containing panel
