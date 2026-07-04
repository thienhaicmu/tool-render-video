# 01 — Tổng quan hệ thống (Overview)

> Review kiến trúc toàn diện · 2026-07-04 · dựa trên đọc mã nguồn thực tế
> (không suy đoán). Mọi nhận định đều dẫn chứng `file:line`.

## 1. Hệ thống là gì

**AI Video Render Studio** — nền tảng dựng video dạng **desktop, offline-first**.
Không cloud, không Redis, không hàng đợi ngoài. Toàn bộ trạng thái nằm trong một
file SQLite (`data/app.db`).

- **Stack:** FastAPI + Uvicorn + SQLite (WAL) + FFmpeg + Whisper + OpenCV +
  yt-dlp + Electron shell + React/Vite frontend.
- **Backend:** ~64.8k dòng Python trong `backend/app` (269 file `.py`),
  204 file test.
- **Frontend:** ~26.1k dòng TS/TSX trong `frontend/src`.
- **Triết lý kiến trúc:** *modular monolith* với worker cô lập theo thread;
  `ThreadPoolExecutor` in-process làm job queue; FFmpeg subprocess thực thi render.

## 2. Ba chế độ render (3 backend modes)

Tất cả đi qua **một** endpoint `POST /api/render/process`, phân nhánh bằng
trường `render_format` tại [_common.py:242-269](../../backend/app/features/render/routers/_common.py#L242-L269):

| Mode | `render_format` | Orchestrator | Input | Output |
|------|-----------------|--------------|-------|--------|
| **Clip** | `clips` (mặc định) | `run_render_pipeline` ([render_pipeline.py:472](../../backend/app/features/render/engine/pipeline/render_pipeline.py#L472)) | 1 video nguồn local | N clip dọc ngắn, xếp hạng viral |
| **Recap** | `recap` | `run_recap` ([recap_pipeline.py:254](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L254)) | 1 phim/tập dài | 1 video/tập tóm tắt có narration |
| **Content** | `content` | `run_content` ([content_pipeline.py:110](../../backend/app/features/render/engine/pipeline/content_pipeline.py#L110)) | Script/bài viết (KHÔNG có footage) | 1 video từ TTS + visual sinh ra |

Cả ba dùng chung wrapper `process_render` để thống nhất cancel / failure / metrics /
`close_thread_conn` housekeeping — thiết kế **đúng và sạch**.

## 3. Điểm mạnh nổi bật (đọc từ code, không đoán)

1. **Sacred Contracts được thực thi nghiêm** — 8 hợp đồng bất biến (result_json
   aliases, AI return-None, stage names, WS shape, DB sole authority, QA gate...)
   có test guard. Ví dụ `tests/test_contract_db_sole_authority.py`,
   `tests/test_nvenc_semaphore_external_acquire.py`.
2. **AI safety tuyệt đối** — mọi provider trả `None` thay vì raise; dispatcher
   ([llm/__init__.py](../../backend/app/features/render/ai/llm/__init__.py)) có
   lớp `try/except` phòng thủ *lần hai* quanh mỗi provider dù provider đã tự bắt.
3. **GPU protection** — `NVENC_SEMAPHORE` giới hạn phiên NVENC, auto-acquire theo
   codec argv, có test parity giữa 2 resolver.
4. **Recovery & resume** — job gián đoạn được đánh dấu `interrupted` khi khởi
   động lại ([manager.py:647](../../backend/app/jobs/manager.py#L647)); phantom
   job được reconcile ([manager.py:597](../../backend/app/jobs/manager.py#L597)).
5. **Disk-truth resume** — mỗi scene/part kiểm tra file đã pass QA trên đĩa để
   bỏ qua render lại (content_pipeline.py:295, recap parts).
6. **Migration additive-only** — 16 migration step, không có DROP/RENAME.

## 4. Điểm yếu cấu trúc nổi bật (chi tiết ở doc 17-18)

1. **`render_pipeline.py` = 1934 dòng** — một hàm `run_render_pipeline` khổng lồ
   (472→~1930), là "God function" thực sự dù đã tách stage helper.
2. **`RenderRequest` = 201 field** trong một model phẳng
   ([render.py](../../backend/app/models/render.py)) — nợ kỹ thuật hình học.
3. **Không có xác thực (auth) ở BẤT KỲ endpoint nào** — chấp nhận được cho
   desktop loopback, nhưng là rủi ro nếu deploy remote (đã có guard bind).
4. **Trùng lặp orchestration** giữa 3 mode — `_safe_filename`, `_set_stage`,
   khối terminal `result_json`, vòng lặp parallel scene xuất hiện gần như y hệt ở
   `content_pipeline` và `recap_pipeline` (chi tiết doc 13-14).
5. **Content Studio frontend chỉ 1 file 709 dòng** — mỏng so với backend đã có
   (publish-meta, projects, narration preview).

## 5. Bảng điểm tổng hợp (0–10)

| Trục | Điểm | Ghi chú nhanh |
|------|------|---------------|
| Kiến trúc | 7.0 | Modular monolith rõ ràng; nhưng vài God-file |
| Code Quality | 6.5 | Comment xuất sắc; trùng lặp + file quá lớn kéo xuống |
| Hiệu năng | 7.5 | NVENC/thread/cache quản lý tốt; SQLite là trần scale |
| Khả năng mở rộng | 5.5 | Single-machine by design; provider seam tốt |
| UX | 6.5 | WS + polling fallback tốt; Content UI mỏng |
| AI Workflow | 8.0 | Multi-pass, fallback, deterministic guardrails — mạnh |
| Media Pipeline | 7.5 | FFmpeg path-safe helpers, QA gate nghiêm |
| Bảo mật | 5.0 | No-auth by design; devtools/injection cần soát (doc 16) |
| Bảo trì | 6.0 | Docs + contracts tốt; nợ ở file lớn + duplicate |
| **Trung bình** | **6.6** | Sản phẩm chín cho desktop cá nhân, chưa cho SaaS |

## 6. Mức sẵn sàng production

- **Desktop cá nhân / offline (mục tiêu thiết kế):** ~**8/10** — ổn định, có
  recovery, QA gate, cleanup.
- **SaaS / multi-tenant / cloud:** ~**3/10** — thiếu auth, thiếu tách tenant,
  SQLite + ThreadPool không scale ngang (xem doc 20 + 21).

Chi tiết từng phần: `02-architecture` → `20-final-review`.
