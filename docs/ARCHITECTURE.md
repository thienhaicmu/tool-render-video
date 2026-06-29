# Architecture — AI Video Render Studio

> Cập nhật 2026-06-29 từ source thực tế. Tin code khi có mâu thuẫn.

## 1. Tầm nhìn hệ thống

Ứng dụng desktop **offline-first**: chạy hoàn toàn trên máy người dùng, không
bắt buộc cloud. Một backend FastAPI cục bộ phục vụ cả API lẫn UI tĩnh; vỏ
Electron mở cửa sổ trỏ vào backend đó.

```
┌──────────────────────────────────────────────────────────────────┐
│ Electron shell (desktop-shell/main.js)                             │
│   • spawn backend (uvicorn) như tiến trình con                     │
│   • mở BrowserWindow → http://127.0.0.1:8000                       │
└───────────────────────────────┬──────────────────────────────────┘
                                 │ HTTP / WebSocket (loopback)
┌───────────────────────────────▼──────────────────────────────────┐
│ FastAPI app  (backend/app/main.py)                                 │
│   • REST routers (render, jobs, download, settings, …)             │
│   • WebSocket tiến trình job                                        │
│   • phục vụ UI tĩnh React đã build (backend/static-v2/)            │
│   • ThreadPoolExecutor scheduler cho hàng đợi job                   │
└───────┬───────────────────────────────┬───────────────────────────┘
        │                               │
        ▼                               ▼
┌───────────────┐              ┌────────────────────────────────────┐
│ SQLite (WAL)  │              │ Worker threads                      │
│ data/app.db   │◀────────────▶│  • render pipeline (FFmpeg/Whisper) │
│ nguồn chân lý │              │  • download pipeline (yt-dlp)       │
└───────────────┘              └─────────────┬──────────────────────┘
                                             │ subprocess
                          ┌──────────────────┼──────────────────┐
                          ▼                  ▼                  ▼
                       FFmpeg            Whisper            yt-dlp
                     (NVENC/x264)     (faster-whisper)   (download)
                                             │
                                             ▼
                                   LLM cloud (tuỳ chọn)
                              Gemini / OpenAI / Claude
```

## 2. Triết lý kiến trúc

- **Modular monolith** với worker tách biệt theo tiến trình con (FFmpeg, yt-dlp,
  Whisper). Không Redis, không message queue ngoài, không service cloud bắt buộc.
- **SQLite là state store duy nhất** (`data/app.db`, WAL mode). Không có cache
  trạng thái nào sống sót qua restart ngoài DB này.
- **Hàng đợi job in-process**: một min-heap ưu tiên + `ThreadPoolExecutor`
  (`backend/app/jobs/manager.py`). Job được re-queue từ DB khi khởi động lại.
- **Render bằng subprocess FFmpeg**: pipeline Python điều phối, FFmpeg thực thi.
- **AI là tuỳ chọn và phải an toàn**: một exception chưa bắt trong module AI sẽ
  giết cả job render → mọi module AI bắt buộc `return None` khi lỗi.

## 3. Bố cục backend (`backend/app/`)

| Thư mục | Vai trò |
|---------|---------|
| `main.py` | Khởi tạo FastAPI, mount toàn bộ router, hook startup/shutdown, vòng cleanup định kỳ, bind-safety guard |
| `core/` | Hạ tầng nền: `config.py` (env + path), `stage.py` (enum JobStage/JobPartStage), `ui_gate.py`, `logging_setup.py`, `devtools_safety.py`, `contracts.py`, `tracing.py`, `naming.py`, `error_sink.py` |
| `db/` | Truy cập SQLite: `connection.py` (WAL + thread-local), `migrations.py` (runner) + `migration_steps/`, và các repo (`jobs_repo`, `creator_repo`, `feedback_repo`, `download_repo`, `assets_repo`, `presets_repo`, `history_repo`, `ab_scores_repo`, `platform_metrics_repo`) |
| `domain/` | Dataclass thuần (không I/O): `render_plan.py` (RenderPlan), `creator_context.py`, `asset.py`, `render_preset.py`, `timeline.py`, `manifests.py` |
| `models/` | Pydantic: `render.py` (RenderRequest nội bộ), `render_public.py` (wire surface FE), `jobs.py`, `render_field_groups.py`, `schemas.py` (shim re-export) |
| `routes/` | REST router không thuộc feature render (jobs, settings, assets, presets, analytics, feedback, voice, …) |
| `jobs/` | Hàng đợi: `manager.py` (scheduler + executor), `cancel.py` (registry huỷ), `whisper_timeout.py` |
| `services/` | Dịch vụ ngang: `channel_service`, `maintenance` (prune), `metrics` (Prometheus), `warmup`, `preset_seeder`, `bin_paths`, `qa_runner`, `dev/` |
| `features/` | Các feature lớn: `render/`, `download/`, `data/` (dữ liệu runtime) |
| `knowledge/` | Tài liệu domain dạng dữ liệu (chỉ thêm, không xoá) |

### Feature `render/` (trái tim hệ thống)

```
features/render/
├── router.py            # facade re-export router gộp (mounted /api/render)
├── routers/             # tách REST theo trách nhiệm
│   ├── lifecycle.py     # process / upload / quick / resume / retry / cancel
│   ├── prepare.py       # preview nguồn + phiên preview
│   ├── read.py          # đọc media/thumbnail/subtitle theo part
│   ├── utility.py       # queue-status / system-info / cache / ai-diagnostics
│   └── _common.py       # validator + process_render + helper hàng đợi
├── editing/             # API chỉnh sửa sau render (trim / rerender / export)
├── ai/                  # tích hợp LLM (xem AI_INTEGRATION.md)
│   ├── llm/             # dispatcher + providers + parser + prompts + rewrite
│   ├── context/         # builder creator-context cho prompt
│   ├── feedback/        # signal từ rating người dùng
│   └── visibility/      # tóm tắt khả năng quan sát AI
└── engine/              # bộ máy render
    ├── pipeline/        # orchestrator + các stage cấp job
    ├── stages/          # render từng part (per-part state machine)
    ├── encoder/         # FFmpeg helpers + NVENC semaphore + clip ops
    ├── motion/          # OpenCV subject tracking + crop
    ├── subtitle/        # transcription (Whisper) + render phụ đề
    ├── audio/           # TTS, mixer, narration
    ├── overlay/         # text overlay
    ├── preview/         # phiên preview nguồn
    ├── quality/         # chấm điểm chất lượng
    ├── thumbnail/       # sinh thumbnail
    └── remotion_adapter # hook intro (tuỳ chọn)
```

## 4. Vòng đời job render (mức cao)

1. FE gọi `POST /api/render/process` với `RenderRequestPublic`.
2. Handler (`routers/lifecycle.py` → `_common.process_render`) validate, mở rộng
   thành `RenderRequest` nội bộ, ghi job `queued` vào DB, đẩy vào scheduler.
3. `jobs/manager.py` dispatch job tới `ThreadPoolExecutor` khi có slot
   (`MAX_CONCURRENT_JOBS`).
4. Worker chạy `run_render_pipeline()`
   (`features/render/engine/pipeline/render_pipeline.py`):
   - `setup` → `source_prep` → (voice TTS) → `llm_pre_render` (Whisper +
     chọn segment) → lấy `RenderPlan` từ AI → render từng part song song →
     `finalize` (xếp hạng + report) → `DONE`.
5. Mỗi chuyển stage gọi `_emit_render_event()` → broadcast qua WebSocket
   `GET /api/jobs/{id}/ws`. FE cũng có thể poll `GET /api/jobs/{id}`.
6. `qa_pipeline.py` validate output trước khi đánh dấu thành công.

Chi tiết từng stage: [RENDER_PIPELINE.md](RENDER_PIPELINE.md).

## 5. Mô hình tiến trình & luồng

- **1 tiến trình** FastAPI/uvicorn (desktop). API **không có xác thực** — vì
  vậy `main.py` từ chối khởi động nếu bind vào host non-loopback mà không có
  `ALLOW_REMOTE=1` (xem [CONFIGURATION.md](CONFIGURATION.md)).
- **Scheduler thread** (daemon) trong `jobs/manager.py` rút job từ min-heap.
- **Worker threads** trong `ThreadPoolExecutor` chạy pipeline; mỗi job dùng
  thread-local DB connection (`_thread_conn`) cho hot path progress.
- **Background daemons** lúc startup: warmup Whisper, trích cookie Chrome,
  auto-update yt-dlp, vòng cleanup định kỳ (mặc định mỗi 30 phút).
- **Giới hạn phần cứng**:
  - `MAX_CONCURRENT_JOBS` (mặc định `cpu//2`) — số job chạy song song.
  - `JOB_SEMAPHORE` / `MAX_RENDER_JOBS` — số pipeline vào vùng encode cùng lúc.
  - `NVENC_SEMAPHORE` / `NVENC_MAX_SESSIONS` (mặc định 3) — số phiên NVENC GPU.

## 6. Phục vụ UI

`core/ui_gate.py` chọn thư mục tĩnh theo `STATIC_UI_VERSION`:
`v2` → `backend/static-v2/` (UI React hiện tại), mặc định/`legacy` →
`backend/static/`. Frontend build bằng Vite ra thẳng `backend/static-v2/`
(`vite.config.ts: outDir`). Xem [FRONTEND.md](FRONTEND.md).

## 7. Khả năng quan sát

- Log file qua `core/logging_setup.py` ghi vào `APP_DATA_DIR/logs/`.
- Log theo job ghi vào thư mục channel.
- Prometheus `GET /metrics` (`services/metrics.py`): thời lượng stage render,
  thời gian acquire DB connection, …
- `GET /health` báo trạng thái + đường dẫn DB đang dùng + cờ fallback DB.
