# 20 — Frontend Reference

Rebuilt from code on 2026-06-06. For deep dive see [01_frontend_inventory.md](01_frontend_inventory.md), [04_workflow_user.md](04_workflow_user.md).

## Stack

| Layer | Tech |
|---|---|
| Framework | React 18.3.1 |
| Build | Vite 5.3.4 |
| Language | TypeScript 5.5.3 strict |
| State | Zustand 4.5.2 |
| Test (declared, unused) | Vitest 1.6.0 + @testing-library/* |
| Codegen | `openapi-typescript` 7.4.4 (manual, no CI gate) |
| Path alias | `@/*` → `src/*` |
| Build output | `../backend/static-v2/` |

## Layout

```
frontend/src/
├── main.tsx, App.tsx                # root + panel router
├── api/                             # 7 client modules
│   ├── client.ts                    # apiFetch + apiFetchFormData
│   ├── render.ts, jobs.ts, editing.ts, upload.ts,
│   ├── feedback.ts, creatorContext.ts, platformDownloader.ts
├── stores/                          # 4 Zustand stores
│   ├── uiStore.ts                   # activePanel, sidebar, notifications
│   ├── renderStore.ts               # jobs{}, activeJobId, submitRender()
│   ├── qualityStore.ts
│   └── editorStore.ts
├── websocket/RenderSocketClient.ts  # WS reconnect, ping-ignore
├── hooks/useRenderSocket.ts         # subscribes to /api/jobs/{id}/ws
├── features/
│   ├── clip-studio/                 # primary 3-step workflow (RENDER/DOWNLOAD/HISTORY tabs)
│   │   ├── ClipStudio.tsx
│   │   └── render/
│   │       ├── RenderWorkflow.tsx   # step orchestrator
│   │       ├── steps/
│   │       │   ├── StepConfigure.tsx  # 944 LOC (god component)
│   │       │   ├── StepRendering.tsx
│   │       │   └── StepResults.tsx    # 786 LOC
│   │       └── ...
│   ├── editor/                      # legacy trim/effects (Phase 1 F06)
│   ├── downloader/                  # sidebar YT/TikTok downloader
│   ├── jobs/                        # history list + drawer + AI summary card
│   ├── progress/                    # live job progress widgets
│   ├── quality/                     # per-part quality panel
│   └── settings/                    # creator context form
├── components/ui/                   # Button, Card, Badge, StatusPill, ScoreBadge, ...
├── components/quality/              # QualityBadge, QualityIssueList
├── i18n/translations.ts             # VI/EN
├── types/api.ts                     # 419 LOC handwritten
└── types/openapi-generated.ts       # 4091 LOC auto-generated
```

## Routing model

Panel-based. `uiStore.activePanel` is the single source of truth. App.tsx switch:

| Panel | Component |
|---|---|
| `clip-studio` (fullscreen) | ClipStudio |
| `home`, `library` | HistoryScreen |
| `download` | DownloaderScreen |
| `settings` | SettingsScreen |
| `publish` (TBD) | PublishPlaceholder |
| `render`, `history`, `editor` (deprecated aliases) | mapped to existing |

No React Router, no URL deep-linking.

## State stores

- **`useUIStore`** — activePanel, sidebar, notifications, language.
- **`useRenderStore`** — `jobs{}`, `activeJobId`, `submitRender()`.
- **`useQualityStore`** — quality panel cache.
- **`useEditorStore`** — trim/effects local state.

No auth/session store. No user identity. Single-user desktop assumption.

## API client

[frontend/src/api/client.ts](../../frontend/src/api/client.ts) — `apiFetch<T>(path, options)` + `apiFetchFormData<T>(path, formData)`. Base URL from `VITE_API_BASE_URL` (default empty → same-origin). Throws `ApiError({status, detail})` on non-2xx.

WS client at [frontend/src/websocket/RenderSocketClient.ts](../../frontend/src/websocket/RenderSocketClient.ts): 20 reconnect attempts, 2 s → 30 s backoff, ignores `{"type":"ping"}` keepalives.

## Render workflow

[frontend/src/features/clip-studio/render/RenderWorkflow.tsx](../../frontend/src/features/clip-studio/render/RenderWorkflow.tsx) (566 LOC). Four steps:

1. **Source** — local file via `electronAPI.pickVideoFile()` → `prepareSource()`.
2. **Configure** — 50+ form knobs, persisted to `localStorage`.
3. **Rendering** — POST `/api/render/process`, then WS subscription.
4. **Results** — clip grid, AI summary card, quality panel, per-clip actions.

## Electron preload bridge

[desktop-shell/preload.js](../../desktop-shell/preload.js) exposes `window.electronAPI`:

- `pickDirectory`, `pickVideoFile`, `pickCookiesFile`
- `openPath`
- `onJobProgress`, `onBootStatus`, `onBootVersion`
- `getAppVersion`

## Testing

**0 test files.** Vitest installed, unused. Phase 9 / Phase 5 T06.

End of 20_frontend.md.
