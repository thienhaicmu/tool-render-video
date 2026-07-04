# 05 — Review Frontend

## 1. Kiến trúc tổng thể

- **Stack:** React + TypeScript + Vite, Zustand store, hash-based routing, code
  splitting per-screen. ~26.1k dòng TS/TSX.
- **Build:** `vite.config.ts` → `outDir=../backend/static-v2`, `emptyOutDir:true`
  (RESOLVED — CLAUDE.md Issue 1). Backend serve qua `ui_gate.py` khi
  `STATIC_UI_VERSION=v2`.
- **Shell:** `App.tsx` (125 dòng) → `AppShell` (nav rail + topbar). Mọi panel
  render trong shell (P2.1 single-shell).

## 2. Routing & code splitting

`App.tsx` dùng `PANEL_MAP` ([App.tsx:53-67](../../frontend/src/App.tsx#L53-L67)) —
**không** phải react-router mà là panel-switch qua `uiStore.activePanel` +
`useHashRoute` deep-link. Mỗi screen `lazy()` + prefetch khi browser idle
([App.tsx:93-109](../../frontend/src/App.tsx#L93-L109)).

Panels: `home/library/history → HistoryScreen`, `clip-studio`, `content-studio`,
`queue`, `download`, `editor`, `settings`, `publish (placeholder)`.

**Nhận xét:**
- **Tốt:** code-split + idle prefetch → mở panel instant, bundle đầu nhẹ.
- **Điểm yếu:** dùng panel-map thủ công thay vì router chuẩn → deep-link giới hạn
  ở "safe subset"; nhiều alias deprecated (`render/history/editor`) trỏ cùng screen
  → nợ điều hướng.
- `publish` vẫn là placeholder "coming soon" ([App.tsx:45-51](../../frontend/src/App.tsx#L45-L51)).

## 3. State management (Zustand)

Stores: `editorStore`, `jobsStore`, `qualityStore`, `renderStore`, `themeStore`,
`uiStore`. Tách theo domain — **hợp lý**. `jobsStore` được `useJobCompletionNotifier`
theo dõi để bắn OS notification khi job terminal.

## 4. API & WebSocket layer

- `api/client.ts` + ~16 module API domain-specific (`render`, `jobs`, `content`,
  `editing`, `presets`, `feedback`, `system`...). Tách rõ theo domain.
- `websocket/RenderSocketClient.ts` + `hooks/useRenderSocket.ts` — consume
  `GET /api/jobs/{id}/ws` với shape `{job, parts, summary}` (Sacred WS Contract).
- `hooks/pollVisibility.ts` + `useBackendHealth` → HTTP polling fallback khi WS
  fail (bắt buộc cho Electron — CLAUDE.md).

## 5. Clip Studio (feature giàu nhất)

`features/clip-studio/render/` có ~40 file: `RenderWorkflow.tsx` (màn chính),
`buildRenderPayload.ts`, `useRenderConfig.ts`, steps (`StepConfigure`,
`StepRendering`, `StepResults`, `RecapLiveView`, `RecapResults`), `ClipTile`,
`ClipPlayerModal`, `scoring.ts`, `eta.ts`, `subtitle-styles.tsx`.

**Nhận xét:** đây là phần FE **chín nhất**, có tách `payloadToConfig`/
`buildRenderPayload` (map giữa 88-field public payload ↔ UI config), ETA,
progress, scoring view. Recap có màn riêng (`RecapLiveView`/`RecapResults`).

## 6. ⚠ Content Studio quá mỏng so với backend

- FE: **chỉ 1 file** `content-studio/ContentStudio.tsx` (709 dòng).
- BE đã có: `/api/content/plan`, `/narration/preview`, `/projects` (CRUD),
  `/publish-meta` — nhưng FE 1 file khó tận dụng hết + khó bảo trì.
- **Root cause:** Content là studio thứ 3, mới nhất (CS-A→CU-14), FE chưa được
  tách component như clip-studio.
- **Ảnh hưởng:** TB — khó mở rộng UI Review/scene-editor; 709 dòng/1 file dễ
  thành God-component.
- **Ngắn hạn:** tách `ContentStudio.tsx` thành `steps/` như clip-studio.
- **Dài hạn:** chia sẻ component render/progress giữa Clip & Content studio.

## 7. Loading / animation / responsive / a11y / perf

- **Loading:** `Suspense` + `ScreenFallback` spinner; skeleton ở clip tiles.
- **Perf:** lazy + prefetch + GZip từ BE. Tốt.
- **A11y/responsive:** không đọc sâu từng component; có `CommandPalette`,
  global shortcuts (⌘N/⌘,/?), `ConfirmDialog` host → có đầu tư UX. Không thấy
  bằng chứng test a11y tự động (cần kiểm — doc 17).
- **prototype.html / render-flow.html:** CLAUDE.md cảnh báo đây chỉ là prototype,
  source-of-truth là `RenderWorkflow.tsx`. Rủi ro drift nếu ai đó sửa prototype.

## 8. Đánh giá

| Trục | Điểm | Ghi chú |
|------|------|---------|
| Kiến trúc FE | 7 | Store/api/ws tách sạch; routing thủ công |
| Clip Studio | 8 | Chín, tách bước tốt |
| Content Studio | 5 | 1 file 709 dòng, mỏng |
| Perf | 8 | Code-split + prefetch |
| Bảo trì | 6.5 | Alias deprecated + prototype drift risk |
| **Tổng** | **6.9** | |

> Lưu ý: frontend đang được xây lại riêng (CLAUDE.md: "frontend is being rebuilt
> separately"), nên ưu tiên backend. Đánh giá FE ở mức tham chiếu.
