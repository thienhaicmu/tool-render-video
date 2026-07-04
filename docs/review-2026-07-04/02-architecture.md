# 02 — Kiến trúc tổng thể (Overall Architecture)

## 1. Sơ đồ luồng chính

```
┌────────────────────────────────────────────────────────────────────┐
│  Electron shell (desktop-shell/)  ─ wraps ─►  React SPA (frontend/) │
└───────────────┬────────────────────────────────────────────────────┘
                │ HTTP + WebSocket (127.0.0.1:8000)
                ▼
┌────────────────────────────────────────────────────────────────────┐
│  FastAPI app (backend/app/main.py) — ~30 routers mounted            │
│  Middlewares: GZip, CSP (v2 UI only)                                │
└───────────────┬────────────────────────────────────────────────────┘
                │  POST /api/render/process
                ▼
┌────────────────────────────────────────────────────────────────────┐
│  Router layer  features/render/routers/{lifecycle,prepare,read,...} │
│    → _common.process_render  (dispatch theo render_format)          │
└───────────────┬────────────────────────────────────────────────────┘
                │ submit_job(job_id, process_render, ...)
                ▼
┌────────────────────────────────────────────────────────────────────┐
│  QUEUE  jobs/manager.py                                             │
│    min-heap ưu tiên + ThreadPoolExecutor(MAX_CONCURRENT_JOBS)       │
│    scheduler thread · watchdog thread · cleanup thread              │
└───────────────┬────────────────────────────────────────────────────┘
                │ worker thread chạy process_render()
                ▼
┌───────────────────────────── AI ───────────────────────────────────┐
│ features/render/ai/llm  (gemini│openai│claude dispatch + fallback)  │
│   select_render_plan · select_recap_plan · select_content_plan     │
│ Whisper transcription · scene_detector · viral_scoring             │
└───────────────┬────────────────────────────────────────────────────┘
                ▼
┌────────────────────────── RENDERER ────────────────────────────────┐
│ engine/pipeline/*  +  engine/stages/part_renderer → 8 stage helpers │
│ engine/encoder/ffmpeg_helpers (NVENC_SEMAPHORE) · motion/crop       │
│ engine/audio · engine/overlay · engine/subtitle · engine/visual     │
└───────────────┬────────────────────────────────────────────────────┘
                ▼
┌───────── STORAGE ─────────┐   ┌──────────── OUTPUT ────────────────┐
│ data/app.db (SQLite WAL)  │   │ channels/{code}/... , output_dir   │
│ cache/ · temp/ · logs/    │   │ result_json (Sacred Contract #1)   │
└───────────────────────────┘   └────────────────────────────────────┘
```

## 2. Phân tầng thư mục (feature-layer migration Phase 1-18)

```
backend/app/
├── main.py                # startup, env redirect, router mounts, cleanup loop
├── core/                  # config, stage (enums), ui_gate, devtools_safety, logging
├── db/                    # connection (WAL, thread-local), *_repo.py, migrations
├── domain/                # dataclass thuần: render_plan, recap_plan, content_plan,
│                          #   scene_map, timeline, creator_context (no I/O)
├── jobs/                  # manager (queue), cancel (registry), whisper_timeout
├── models/                # render.py (RenderRequest 201 field), render_public.py,
│                          #   jobs.py, schemas.py (shim 39 dòng re-export)
├── routes/                # ~24 REST router mỏng (jobs, settings, assets, presets…)
├── services/              # channel_service, maintenance, metrics, warmup, dev/
└── features/
    ├── render/
    │   ├── router.py             # /api/render/ (mount)
    │   ├── routers/              # _common, lifecycle, prepare, read, utility
    │   ├── ai/{llm,context,feedback,visibility}
    │   ├── editing/router.py     # /api trim/rerender/export
    │   └── engine/
    │       ├── pipeline/         # render_pipeline, recap_pipeline, content_pipeline,
    │       │                     #   llm_pipeline, qa_pipeline, pipeline_* helpers
    │       ├── stages/           # part_renderer + 8 helpers, viral_scoring,
    │       │                     #   content_scene_render, recap_assembler
    │       ├── encoder/          # ffmpeg_helpers (NVENC), clip_ops
    │       ├── motion/           # crop.py (OpenCV tracking), path*.py
    │       ├── audio/ overlay/ subtitle/ visual/ preview/ quality/ thumbnail/
    ├── content/router.py         # /api/content/ (plan, narration, projects, publish)
    └── download/                 # yt-dlp downloader (tách khỏi render)
```

**Nhận xét:** phân tầng feature-first **rõ ràng và nhất quán**. Ranh giới
domain (dataclass thuần, no I/O) / engine (I/O) / router (HTTP) được giữ tốt.
CLAUDE.md tuyên bố các path cũ (`orchestration/`, `services/db.py`,
`routes/channels.py`) đã bị xóa — đã xác nhận không còn tồn tại.

## 3. Startup flow (main.py)

Trình tự tại [main.py:327-408](../../backend/app/main.py#L327-L408):

1. `_assert_main_bind_safe(...)` **import-time** — từ chối khởi động nếu bind
   non-loopback mà không có `ALLOW_REMOTE=1` ([main.py:150](../../backend/app/main.py#L150)).
2. Redirect mọi cache dir (Whisper, Torch, HF, Ollama, TEMP, fontconfig) sang
   `APP_DATA_DIR` — quan trọng để đóng gói desktop ([main.py:103-138](../../backend/app/main.py#L103-L138)).
   - Fontconfig fix để tránh Access Violation của libass trên Windows — chi tiết
     đáng giá, cho thấy va vấp production thực.
3. `init_db()` → `_check_db_fallback_at_startup()` (cảnh báo split-DB).
4. Seed presets, prune logs/preview/cache, `recover_pending_render_jobs()`.
5. Warmup threads (Whisper model, cookies, yt-dlp update) — daemon, non-blocking.
6. `_run_periodic_cleanup` thread (mặc định 1800s).

**Điểm mạnh:** startup phòng thủ toàn diện, mọi bước bọc `try/except`, không bao
giờ chặn boot. **Điểm yếu:** `main.py` làm quá nhiều việc (env, security, CSP,
cleanup, health) — 498 dòng, nên tách `bootstrap/`.

## 4. Dependency & coupling

- **Hướng phụ thuộc đúng:** `routes/services` → `features/engine` → `db/domain`.
  `db.connection` **không** import `services` trực tiếp (lazy import metrics để
  tránh cycle — [connection.py:23](../../backend/app/db/connection.py#L23)).
- **Lazy import khắp nơi** để (a) tránh circular, (b) cho phép optional AI deps
  vắng mặt mà app vẫn chạy. Đây là pattern nhất quán và đúng cho offline-first.
- **Coupling ẩn:** `recap_pipeline` import trực tiếp `JOB_SEMAPHORE`,
  `_render_active_lock`, `_render_active_count` từ `render_pipeline`
  ([recap_pipeline.py:63-67](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L63-L67)) →
  recap phụ thuộc nội bộ clips path. Nên nâng các primitive này lên module chung.

## 5. Đánh giá kiến trúc

| Tiêu chí | Điểm | Ghi chú |
|----------|------|---------|
| Phân tầng | 8 | Feature-layer sạch, domain/engine/router tách rõ |
| Startup/init | 7.5 | Phòng thủ tốt; main.py ôm đồm |
| Dependency mgmt | 7 | Lazy import đúng; vài coupling ẩn cross-pipeline |
| Khả năng thay thế thành phần | 6 | Provider seam tốt; queue/DB khó thay |
| **Tổng** | **7.0** | |

**Root cause của điểm chưa cao:** hệ thống lớn dần theo "batch/phase" (10A→10R,
Phase 1-18, CS-A→CU-14) — mỗi lần thêm một mode/feature thay vì refactor lớp
orchestration chung, dẫn tới God-file + duplicate. Giải pháp dài hạn: doc 20.
