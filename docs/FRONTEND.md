# Frontend & Desktop Shell — AI Video Render Studio

> Cập nhật 2026-06-29 từ source.

## 1. Stack

- **React 18 + TypeScript**, build bằng **Vite**.
- State: **Zustand** (`src/stores/`).
- Test: **Vitest** (`npm test`).
- Vỏ desktop: **Electron** (`desktop-shell/`).

`frontend/package.json` → `name: render-studio-ui`. Dependencies runtime tối giản:
`react`, `react-dom`, `zustand` (mọi thứ khác là devDependency / tooling).

## 2. Build & phục vụ

`frontend/vite.config.ts` build ra thẳng `backend/static-v2/`
(`outDir: '../backend/static-v2'`, `emptyOutDir: true`). Backend phục vụ thư mục
này khi `STATIC_UI_VERSION=v2` (xem `core/ui_gate.py`).

> ⚠️ `emptyOutDir: true` xoá sạch `backend/static-v2/` mỗi lần build — không đặt
> asset viết tay vào đó.

Scripts:

| Lệnh | Việc |
|------|------|
| `npm run dev` | Vite dev server |
| `npm run build` | `tsc -b && vite build` → cập nhật UI live trong `backend/static-v2/` |
| `npm test` | Vitest |
| `npm run gen:openapi` | Sinh type TS từ OpenAPI backend |
| `npm run check:openapi-drift` | Fail khi type FE lệch backend |

> Typecheck dùng `tsc -b` (không phải `tsc --noEmit`).

## 3. Bố cục `frontend/src/`

| Thư mục | Vai trò |
|---------|---------|
| `App.tsx` / `main.tsx` | Entry + root component |
| `api/` | Client gọi REST backend |
| `websocket/` | Kết nối WS tiến trình job |
| `stores/` | Zustand stores |
| `features/` | Các màn hình theo tính năng |
| `components/` | UI dùng chung |
| `layouts/` | Layout khung |
| `hooks/` · `lib/` · `types/` | Tiện ích, type (gồm `openapi-generated.ts`) |
| `i18n/` | Đa ngôn ngữ |
| `styles/` | CSS/theme |

### `features/`

```
features/
├── clip-studio/          # luồng chính: tải → render → lịch sử
│   ├── download/
│   ├── render/           # RenderWorkflow.tsx (+ .css) — màn render/kết quả
│   │   └── steps/        # các bước cấu hình
│   └── history/
├── downloader/           # màn tải độc lập
├── editor/               # chỉnh sửa clip sau render
├── jobs/                 # danh sách/chi tiết job
├── queue/                # QueueScreen — hàng đợi job
├── progress/, quality/   # chỉ còn *.utils.ts / *.types.ts (component React cũ đã gỡ)
└── settings/             # cài đặt + creator context
```

> Nguồn chân lý cho màn render là `features/clip-studio/render/RenderWorkflow.tsx`
> + `RenderWorkflow.css`. File `render-flow.html` / `prototype.html` ở gốc repo chỉ
> là **prototype trực quan** — đổi prototype chưa tính là xong cho tới khi port
> sang file React thật.

### Màn render — monitor & kết quả (redesign 2026-07)

`RenderWorkflow.tsx` điều phối 3 view: **create** (Source + Configure gộp làm
một), **monitor** (đang render), **results**. Đầu màn có **step indicator**
(Configure → Rendering → Result) highlight theo view — luôn biết đang ở bước nào.

`steps/` — các thành phần chính:
- `StepRendering.tsx` — khung: card tổng (stage rail + % tổng), banner trạng
  thái, event log; recap dùng `RecapLiveView`.
- `RenderStage.tsx` — kiểu **render-dashboard desktop**: một *Current Rendering*
  card (thumbnail landscape · tên clip AI đặt · status pill · progress gradient ·
  hàng stats ETA/Elapsed/Progress/Duration) + danh sách **Queue** dạng row
  (`ClipTile.tsx`: idx · thumb · tên · status màu · progress · time · play).
  Full-width, cuộn khi nhiều clip.
- `useCountUp.ts` — đếm % mượt cho card focus.
- `StepConfigure.tsx` (tab Narration) — ô **AI Voice** (Gemini / Edge / XTTS,
  mặc định Gemini); AI auto-select + bật/tắt Narration hiện cả ở Quick mode.

Toàn bộ dùng token theme (`--bg-card`, `--text-*`, `--accent`, `--status-*`) →
**tự đổi sáng/tối** theo `[data-theme]` trên `<html>`.

## 4. Vỏ Electron (`desktop-shell/`)

| File | Vai trò |
|------|---------|
| `main.js` | Process chính Electron: spawn backend (uvicorn), mở `BrowserWindow` trỏ `http://127.0.0.1:8000` |
| `preload.js` | Cầu nối an toàn renderer ↔ main |
| `package.json` | `name: yt-tiktok-desktop-shell`, `main: main.js`; `prestart` build frontend trước, `dist` đóng gói NSIS/portable bằng electron-builder |
| `scripts/logerror.js` | Tiện ích log lỗi client |

Client error của Electron được POST về `/api/client/error` → ghi `errors.jsonl`.

## 5. Giao tiếp với backend

- **REST**: `src/api/` gọi các endpoint trong [API_CONTRACT.md](API_CONTRACT.md).
- **WebSocket**: `src/websocket/` lắng nghe `GET /api/jobs/{id}/ws`, parse shape
  `{ job, parts, summary }` (đóng băng). Có **fallback polling** `GET /api/jobs/{id}`
  khi WS bị chặn — không làm dữ liệu tiến trình chỉ-có-trên-WS.
- Tên stage/part khớp **string trực tiếp** theo enum `core/stage.py`. Backend đổi
  tên = UI vỡ im lặng.

## 6. Chạy nhanh (từ gốc repo)

```powershell
# Backend (UI v2)
./run-backend-v2.ps1

# Desktop (Electron) — tự build frontend rồi mở app
./run-desktop-v2.ps1
```

Hoặc `npm start` ở gốc (gọi `start.ps1`).
