# AI Clip Studio — Frontend Redesign · Execution Plan

> Companion to [FRONTEND_REDESIGN_AUDIT.md](FRONTEND_REDESIGN_AUDIT.md). This is the **build plan**: every work package (WP) is a reviewable, shippable batch with exact files, changes, acceptance criteria, and verification. Approve once → I execute WP-by-WP in the agreed order.
>
> **Hard rules honored throughout:**
> - **No backend change.** Frontend-only. Every WP consumes the existing REST/WS surface (Audit §2.5). Sacred Contracts (WS `{job,parts,summary}` shape, stage/part enum strings, `result_json` keys, HTTP-polling fallback) are consumed **unchanged**.
> - **Commit lock stays on.** No `git add/commit/push` until you explicitly unlock. I work on a branch; you review the working tree.
> - **Verification per WP:** `cd frontend && npm run build` is *not* used for checks (it wipes `backend/static-v2`); instead `npx tsc -b` (type-check) + `npx vitest run` (unit) + a local `npm run dev` visual pass. Full `npm run build` only when you want the live UI updated.
> - **No `git add .`** — explicit paths only, when unlocked.

---

## 0. Execution protocol (how each WP runs)

1. I implement the WP on branch `fe-redesign` (created off `main`; I'll `git switch -c` — no commit).
2. After edits: run `npx tsc -b` + `npx vitest run`; fix until green.
3. For any **visual** WP I first build a throwaway **preview harness** (a `?preview=cliptile` dev route rendering all states with mock data) and drive it with the `run`/`verify` skill so you approve the look **before** it's wired into the live flow.
4. I report in Vietnamese: what changed, files touched, tsc/test result, screenshots/notes, what's next.
5. You approve → next WP. You can approve several WPs to run back-to-back.
6. Nothing is committed until you say "mở khoá commit".

**Rollback:** each WP is isolated; because nothing is committed, `git restore`/`git checkout -- <path>` reverts any WP cleanly.

---

## 1. Work-package map & recommended order

```
WP0  Foundations (tokens · icons · primitives)         ── must go first (thin)
 └─► WP1  ⭐ Rendering Monitor + Clip cards (Appendix E) ── YOUR PRIORITY, ships early
 └─► WP2  Shell · Navigation · Unified Queue · JobRow
 └─► WP3  Create/Configure progressive UX · Results componentization
 └─► WP4  Editor wiring (trim/rerender)
     WP5  Architecture cleanup (god component · progress store · dedupe · pollers)
     WP6  Premium polish (motion · Story Model timeline · WCAG AA)
```
WP1 depends only on the thin slice of WP0 it needs (icons + `ScoreRing` + `Card`). Recommended: **WP0 (minimal) → WP1 → WP2 → WP3 → WP4 → WP5 → WP6.**

---

## WP0 — Foundations (design system)  · Risk: Low–Med · Effort: M

### WP0.1 Token namespace freeze + kill prototype fonts
- **Goal:** one canonical token set; stop drift; remove HUD fonts.
- **Files:** `styles/tokens.css`, `styles/polish.css`, `styles/global.css`.
- **Changes:**
  - Declare the **semantic set** (`--surface-*`, `--accent-*`, `--text-primary/secondary/tertiary`, `--status-*`, `--score-*`, spacing/radius/motion) as canonical in a header comment.
  - Keep legacy aliases (`--color-*`) and prototype aliases (`--bg-*`, `--text-1..3`, `--ok/--warn/--fail`, `--accent/--grad`) **as-is** (they already resolve to semantic) — do **not** mass-delete now (avoids regression); mark them `/* DEPRECATED alias — do not use in new code */`.
  - **Change `--fh` and `--fo`** from `'Rajdhani'`/`'Orbitron'` → `var(--font-display)` (Space Grotesk) and `--fb` stays `var(--font-ui)`. This instantly de-"gamer"-ifies every screen using them.
- **Acceptance:** app renders identically except numerals/headers now use Space Grotesk/Inter (no Rajdhani/Orbitron anywhere). No layout shift.
- **Verify:** `tsc -b`; visual diff on Render + History + Results.

### WP0.2 Single line-icon set + remove emoji-as-icon
- **Goal:** replace `▶ ○ ✓ ✕ ⬇ 👍 👎 ⚡ ☁ 💻 🔥 ★ ✦` used as UI icons with a consistent line-icon component set.
- **Files:** extend `components/icons/index.tsx`; call sites: `Sidebar.tsx`, `Topbar.tsx`, `StepResults.tsx`, `StepRendering.tsx`, `RenderStage.tsx`, `DownloadTab.tsx`.
- **Changes:** add icons `IconPlay, IconCheck, IconClose, IconDownload, IconThumbUp, IconThumbDown, IconCloud, IconChip, IconLocal, IconSpark, IconStar, IconScissors, IconCaptions, IconFilm, IconRing`. Keep emoji only where it's genuinely content (e.g. flag emoji in language pickers stay).
- **Acceptance:** no emoji rendered as a status/action glyph in the 6 files above.
- **Verify:** `tsc -b`; grep for the emoji set returns only language-flag usages.

### WP0.3 Primitive components (canonical `components/ui`)
- **Goal:** the reusable kit every screen must use.
- **New/《upgrade》 files under `components/ui`:**
  - `Button.tsx` 《upgrade》 → variants `primary|secondary|ghost|danger`, sizes `sm|md`. Replaces `btn-xs/btn-next/btn-back/btn-cancel/res-export-btn`.
  - `Badge.tsx` / `StatusPill.tsx` 《adopt》 → tone by status/tier.
  - `ScoreRing.tsx` **new** → props `{value, size, tone?}`; SVG arc + centered number (extract from `StepResults.ScoreRingSm/Lg`).
  - `ScoreBar.tsx` **new** → labelled track (extract from results signal bars).
  - `SegmentedControl.tsx` **new** → `role=radiogroup`, keyboard arrows (replaces the ~10 `seg`/`seg-b` div patterns).
  - `Toggle.tsx` **new** → accessible switch (replaces `Tog`).
  - `Field.tsx` **new** → label+hint+control (generalize Settings `FormRow`).
  - `Popover.tsx` **new** → anchored panel w/ outside-click + focus return (Export panel, ScoreTip).
  - `Modal.tsx` **new** → backdrop + focus-trap + Esc (Palette/ClipPlayer/Confirm reuse).
  - `Card.tsx` 《upgrade》 / `Surface.tsx` **new** → slots + state matrix (hover/loading/empty/error).
  - `Stat.tsx` **new** → KPI tile (results hero).
  - `ConicRing.tsx` **new** → conic-gradient progress ring (used by WP1 clip tiles).
- **Acceptance:** each primitive has a minimal render + a vitest smoke test; no behavior change to existing screens yet (this WP only *adds* the kit).
- **Verify:** `tsc -b`; `vitest run` (new primitive tests green).

### WP0.4 Preview harness (dev-only)
- **Goal:** a way to eyeball components in every state without a live render.
- **Files:** `main.tsx` gains a `?preview=<name>` early-return that mounts `dev/PreviewHarness.tsx` (excluded from prod build via a `import.meta.env.DEV` guard).
- **Acceptance:** `npm run dev` + `?preview=cliptile` shows a component gallery.
- **Note:** throwaway/dev-only; never shipped in `static-v2`.

---

## WP1 — ⭐ Rendering Monitor + Clip cards (Audit Appendix E)  · Risk: Low · Effort: M

> Your stated priority. Delivers the "đẹp" the current monitor lacks. Data 100% existing (`ClipSlot`, per-part status, `getPartThumbnailUrl` on done, `getPartMediaUrl`).

### WP1.1 `ClipTile.tsx` — the rich per-clip card (replaces `.rs-chip` pills)
- **Files:** new `render/steps/ClipTile.tsx`; CSS in `RenderWorkflow.css` (`.ct-*`).
- **Props:** `{ slot: ClipSlot, jobId, thumbRatio, isFocus, onFocus, t }`.
- **States (all "alive"):**
  - **done** → real thumbnail (`getPartThumbnailUrl`), bottom scrim, `IconCheck` chip, duration badge, hover `IconPlay` (→ `getPartMediaUrl`); spring scale-in on flip.
  - **active** → `ConicRing` with `progress_percent`, big % in `--font-display`, 3-dot micro-pipeline (Cut·Sub·Render via `IconScissors/IconCaptions/IconFilm`), pulsing accent border + soft glow, low-amplitude gradient-mesh bg.
  - **waiting** → ghost card, `rs-shimmer` skeleton, muted `#0N`, "queued".
  - **failed** → red-tinted, `IconClose`, `message` first line on hover.
- **A11y:** `role=option`, `aria-selected`, focusable, Enter/Space = focus; ring has `aria-label="{pct}%"`.
- **Acceptance:** all 4 states approved in the preview harness (WP0.4) before wiring.

### WP1.2 `RenderStage.tsx` — focus card revamp
- **Files:** `render/steps/RenderStage.tsx`, `.rs-*` CSS.
- **Changes:** keep focus-selection + per-clip ETA logic as-is; replace the empty `#03` placeholder with a **large `ConicRing`** (active) / **real thumbnail** (done); pipeline nodes become line-icons; keep the animated gradient border (`.rs-focus-live`). Filmstrip `.rs-strip` → a responsive **grid of `ClipTile`** (replaces pill chips).
- **Acceptance:** clicking any tile focuses it; focus card shows ring/thumb correctly; recap unaffected.

### WP1.3 `StepRendering.tsx` — declutter progress hierarchy
- **Files:** `render/steps/StepRendering.tsx`, `.rd-*` CSS.
- **Changes:**
  - **Remove** the bottom `.rd-abp-toolbar` block entirely (duplicate of the hero).
  - **Remove** `.rd-seg-bar` (per-clip status now lives in the tile grid).
  - Keep **one** hero: `.rd-card` with a single bar + % (Space Grotesk) + a **phase rail** (Analyze·Transcribe·Render·Report·Done) using line-icon dots.
  - Keep the AI Director panel, adaptive status line, and Event Log (all good).
- **Acceptance:** exactly 2 progress surfaces remain (hero + tile grid) + the focus ring; no visual regression in the status line / event log.

### WP1.4 `RecapLiveView.tsx` — tile parity
- **Files:** `render/steps/RecapLiveView.tsx`.
- **Changes:** episodes/scenes use the same tile/ring visual language so both render modes read identically.
- **Acceptance:** recap job monitor visually matches clips-mode language.

### WP1.5 CSS + motion
- **Files:** `RenderWorkflow.css`.
- **Changes:** add `.ct-*` (tile) + `.rs-*` grid; delete `.rd-abp-*`, `.rd-seg-*`; `@media (prefers-reduced-motion: reduce)` freezes shimmer/mesh/ring animations to static fills.
- **Acceptance:** reduced-motion verified; scroll/perf smooth with 10–20 tiles.

**WP1 verify:** `tsc -b` + `vitest run` + live render walkthrough (a real job through queued→rendering→done→failed if possible, else harness).

---

## WP2 — Shell · Navigation · Unified Queue · JobRow  · Risk: Med–High · Effort: L

### WP2.1 Nav rail redesign
- **Files:** `layouts/Sidebar.tsx`, `layouts/AppShell.tsx`, `tokens.css` (`--sidebar-width`).
- **Changes:** 64px rail, icon **+ label** (hover-expand < 1440px, persistent ~200px ≥1440px). Nav items: Create · Queue · Library · Downloads · Editor · Settings. Retire Publish.
- **Acceptance:** all six destinations reachable; active state + focus ring correct; Editor has a home.

### WP2.2 Deep-linkable views (lightweight routing)
- **Files:** `stores/uiStore.ts`, `App.tsx`, `RenderWorkflow.tsx`.
- **Changes:** add a hash-based route sync (`#/monitor/<jobId>`, `#/results/<jobId>`, `#/library`, etc.) over `activePanel` + the existing `monitorJobId` handshake. Read hash on load; write on nav. Keeps offline (no server routing).
- **Risk:** touches the render workflow's view state — **High**; I'll gate this behind an approved sub-plan and add tests for the hash↔panel mapping.
- **Acceptance:** refresh/back/forward preserve the current job view; existing handshakes still work.

### WP2.3 `JobRow` unify + Unified Queue screen
- **Files:** new `components/JobRow.tsx`; new `features/queue/QueueScreen.tsx`; refactor `layouts/ActiveJobsDock.tsx` (→ summary launcher) and `layouts/QueueDrawer.tsx` (merged into QueueScreen), `features/jobs/JobListItem.tsx`, `DownloadTab` rows.
- **Changes:** one `<JobRow variant="dock|queue|library|download">` with progress, status, reorder/hold/resume/cancel where applicable (all existing endpoints).
- **Acceptance:** dock, queue, library, downloads all render the same row; reorder/hold/resume/cancel work from the Queue screen.

**WP2 verify:** `tsc -b` + `vitest` (JobRow + hash-route tests) + manual nav/queue walkthrough.

---

## WP3 — Create/Configure UX + Results componentization  · Risk: Med · Effort: L

### WP3.1 Progressive Configure
- **Files:** split `render/steps/StepConfigure.tsx` → `ConfigQuick.tsx` (platform · length · count) + `ConfigAdvanced.tsx` (drawer: AI provider/model/lang, subtitle detail, narration, trim, quality, focus, story-intel) + `PreviewStage.tsx` + `StyleStrip.tsx`. Reuse `SegmentedControl`/`Toggle`/`Field`.
- **Backend:** unchanged — `buildRenderPayload` still emits the same `RenderRequestPublic`; advanced fields default via Sacred Contract #2 when untouched.
- **Acceptance:** Quick = 3 decisions; Advanced drawer holds the rest; draft persistence + server-defaults hydration preserved; Recap becomes an explicit mode card (not a hidden confirm).

### WP3.2 Results componentization + score unification
- **Files:** split `render/steps/StepResults.tsx` → `ResultsHero.tsx`, `AiAnalysis.tsx`, `ClipCard.tsx`, `ClipDetail.tsx` (tabs Preview·Ranking·Quality — merges player+detail), `ExportPanel.tsx`. Use `ScoreRing`/`ScoreBar`/`Stat`/`Badge`.
- **Changes:** single score source at data layer (`output_rank_score ?? qualityScore`); `ClipCard` shares geometry with WP1 `ClipTile` (visual continuity monitor→results).
- **Acceptance:** feedback 👍👎, export checklist, delete, trim-menu, player all still work; ranking breakdown intact.

**WP3 verify:** `tsc -b` + `vitest` (payload round-trip `buildRenderPayload`↔`payloadToConfig` unchanged) + manual configure→render→results.

---

## WP4 — Editor wiring (close the dormant feature)  · Risk: Med · Effort: M

- **Files:** `features/editor/EditorScreen.tsx`, `TrimControls.tsx`, `EditorMetadataPanel.tsx`, `stores/editorStore.ts`, `api/editing.ts` (already has `trimJobPart`/`rerenderSelection`).
- **Changes:** wire **existing** endpoints — Save trim → `POST …/trim` (`output_mode: new_job` default); "Re-render with style" → `POST …/rerender`; on success surface the new job in the Queue and notify. Give Editor a nav home (WP2.1).
- **Acceptance:** trimming a clip produces a real new job (visible in Library/Queue); no more UI-only no-op.
- **Verify:** `tsc -b` + `vitest`; manual trim→new job appears in history.

---

## WP5 — Architecture cleanup (invisible to users)  · Risk: Med–High · Effort: L–XL

### WP5.1 Decompose `RenderWorkflow` god component
- **Files:** `render/RenderWorkflow.tsx` → extract a `useRenderWorkflow()` hook (state + submit/cancel/retry/resume/handshakes) + thin `CreateScreen`/`MonitorScreen`/`ResultsScreen` wrappers.
- **Risk:** High (owns view + submit). Gated sub-plan + tests for submit/dedup/handshake paths.

### WP5.2 Lift live progress to a store
- **Files:** new `stores/renderProgressStore.ts` wrapping `useRenderSocket`; `MonitorScreen` reads it → Monitor no longer owned by one component (prereq for deep-link WP2.2 robustness).

### WP5.3 Delete duplicate subsystems
- **Files:** after confirming zero consumers — remove `features/progress/*` and the unused `features/quality/*` and dormant `features/clip-studio/history/HistoryTab.tsx`.
- **Acceptance:** `tsc -b` clean; no dead imports; bundle shrinks.

### WP5.4 Single poll scheduler
- **Files:** new `hooks/usePoller.ts` / small scheduler; consolidate jobs(4s)+download(1.5s)+health+resources into one visibility-aware ticker (pause when tab hidden).

**WP5 verify:** full `vitest run`; manual regression of queue/monitor/history.

---

## WP6 — Premium polish + accessibility  · Risk: Low–Med · Effort: L

- **WP6.1 Motion system:** `styles/motion.css` — spring completion, score count-up, phase-dot fills; all behind `prefers-reduced-motion`.
- **WP6.2 Story Model hero timeline:** `RecapLiveView.tsx` + `StoryModelCard.tsx` — present the whole-film Story Model as a hero act/beat timeline (data already in `ai-summary.story_model` / `recap.plan.ready`).
- **WP6.3 WCAG AA pass:** contrast fixes, focus-visible everywhere, keyboard-complete flows, modal focus-trap (via `Modal`), min-12px type sweep, aria on custom controls.
- **Verify:** `tsc -b` + `vitest` + a keyboard-only walkthrough + contrast audit.

---

## 2. Cross-cutting acceptance (every WP)
- `npx tsc -b` clean · `npx vitest run` green (new tests added where logic changes).
- No new emoji-as-icon; no raw inline `style` for color/spacing in touched files (use tokens/primitives).
- No change to: WS event handling shape, enum strings, `result_json` key reads, API paths, polling fallback.
- Vietnamese comments only on touched lines (per CONVENTIONS.md); no frozen renames.

## 3. Effort roll-up (single senior FE)
| WP | Effort | Risk |
|----|--------|------|
| WP0 Foundations | M (~1 wk) | Low–Med |
| WP1 ⭐ Rendering monitor | M (~1 wk) | Low |
| WP2 Shell/Nav/Queue | L (~2 wk) | Med–High |
| WP3 Configure/Results | L (~2 wk) | Med |
| WP4 Editor wiring | M (~3 d) | Med |
| WP5 Arch cleanup | L–XL (~2–3 wk) | Med–High |
| WP6 Polish/A11y | L (~1.5 wk) | Low–Med |
**Total:** ~9–11 weeks of focused FE work, shippable per WP.

## 4. What I need from you to start
- Confirm **execution order** (default: WP0→WP1→WP2→WP3→WP4→WP5→WP6).
- Confirm **approval cadence** (per-WP gate vs. approve a run of several).
- Everything else is decided in this doc.
