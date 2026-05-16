# AI Clip Studio — Production UI Architecture
> V3 merge completed 2026-05-16. Source: backend/static-v3 → backend/static.

---

## CSS Load Order

```
/static/css/v3/app.css          ← entry point (@imports in order below)
  ├── tokens.css                  design tokens, CSS custom properties
  ├── layout.css                  app shell, 3-col grid, sidebar, inspector, bottom panel
  ├── components.css              buttons, inputs, cards, pills, badges, progress, forms
  ├── workflow.css                render setup sidebar, editor stage, workflow strip
  ├── runtime.css                 render active panel, logs, queue, part cards
  ├── review.css                  output panel, clips gallery, AI panels, preview modal
  ├── download.css                download manager workspace
  ├── history.css                 history view + render home panel
  └── hardening.css               view guards, responsive breakpoints, a11y, print
```

**Rollback**: `index.html` CSS link → `/static/css/app.css` (17k-line v2 backup at `css/app.css.v2.bak`).

---

## Protected IDs — Never Rename

| ID | Owner | JS file |
|---|---|---|
| `event_log_render` | render log container | render-ui.js |
| `job_bar`, `job_percent`, `job_stage_pill` | job progress | render-ui.js |
| `render_active_panel` | active render state | render-ui.js |
| `render_completion_bar` | render done bar | render-ui.js |
| `render_output_panel` | output clips | render-ui.js |
| `jobs_out` | render history grid | render-ui.js |
| `abp_collapse_btn`, `abp_*` | bottom panel | render-ui.js, nav.js |
| `rc_*` | render card elements | render-ui.js |
| `wfStrip` | workflow step strip | nav.js |
| `partial_render_home` | partial injection point | partials-loader.js |
| `partial_download_view` | partial injection point | partials-loader.js |
| `partial_history_view` | partial injection point | partials-loader.js |
| `partial_settings_view` | partial injection point | partials-loader.js |

---

## View Ownership Map

| View | Body class | Partial | Sidebar card |
|---|---|---|---|
| render | `is-render-studio-active` | `#partial_render_home` | `card_render_setup` |
| editor | `is-render-studio-active` | — (inline) | `card_render_setup` |
| download | `is-download-active` | `#partial_download_view` | `card_download_setup` |
| history | `is-history-active` | `#partial_history_view` | — |
| reports | — | — | `card_reports` |
| settings | — | `#partial_settings_view` | `card_settings` |

---

## Workflow State Map

```
source → prepare → render → review → export
  ↑          ↑         ↑        ↑        ↑
editor    inPipeline  job    completion  output
mode      class       active  bar vis    panel vis
```

`updateWfStrip()` in nav.js reads live DOM state to derive step.
Called by: `setView()`, `showRenderCompletionBar()`, `hideRenderCompletionBar()`, `updateRenderMainState()`.

---

## JS Files — Change Log

| File | Status | Change |
|---|---|---|
| `nav.js` | **updated** | +inPipeline class, +is-download-active, +updateWfStrip() |
| `render-ui.js` | **updated** | +inPipeline reset on session clear, +3× updateWfStrip() calls |
| all others | unchanged | byte-identical to v2 |

---

## Partial System

Partials are fetched at runtime by `partials-loader.js` from `/static/partials/`.
Injection targets: `#partial_render_home`, `#partial_download_view`, `#partial_history_view`, `#partial_settings_view`.

---

## Rollback Notes

1. **HTML only**: revert `index.html` CSS link from `/static/css/v3/app.css` → `/static/css/app.css`
2. **Full rollback**: `cp index.html.v2.bak index.html` + `cp css/app.css.v2.bak css/app.css` + revert nav.js + render-ui.js from git
3. Backup files: `index.html.v2.bak`, `css/app.css.v2.bak`

---

## Remaining Technical Debt

- `css/app.css.v2.bak` (17,430-line v2 CSS) — remove after one release cycle of stable production
- `index.html.v2.bak` — remove after one release cycle
- `backend/static-v3/` directory — archive after confirming production stable
