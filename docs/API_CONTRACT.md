# API Contract — AI Video Render Studio

> Cập nhật 2026-06-29 từ source (grep decorator router + prefix). Backend FastAPI,
> mount trong `backend/app/main.py`. API **không có xác thực** — chỉ dùng loopback.

## 1. Contract đóng băng (NEVER BREAK)

Các path sau bị frontend Electron, bản ghi job đã lưu, và client ngoài tiêu thụ.
Đổi = phải migrate đồng loạt mọi consumer → trên thực tế là **không bao giờ đổi**.

| Method | Path | Ghi chú |
|--------|------|---------|
| POST | `/api/render/process` | Body `RenderRequestPublic` (88 field FE, `extra='forbid'`) → tạo job. Handler mở rộng thành `RenderRequest` nội bộ |
| GET | `/api/jobs/{id}` | Poll trạng thái job |
| GET | `/api/jobs/{id}/ws` | Nâng cấp WebSocket stream tiến trình |

Quy tắc: không đổi path; không thêm path/query bắt buộc; không bỏ field response;
chỉ được **thêm**. HTTP polling `GET /api/jobs/{id}` phải luôn là phương án thay
thế đầy đủ cho WebSocket (môi trường desktop có thể chặn WS).

### Shape sự kiện WebSocket (đóng băng)
Mọi event từ `_emit_render_event` phải có 3 key top-level:

```json
{ "job": { ... }, "parts": [ { ... } ], "summary": { ... } }
```

Không bỏ/đổi tên key; không đổi `parts` thành `clips`; không flatten `summary`.
Luôn có đủ 3 key kể cả khi `parts` rỗng.

### Public vs Internal surface
- Wire nhận `RenderRequestPublic` (`models/render_public.py`, 88 field FE).
- Replay (resume/retry/bản ghi cũ) dùng `RenderRequest` (`models/render.py`, đầy
  đủ field) — Sacred Contract #2: field mới default `False`/disabled.
- Field BE-only (server-derived) **không** cần thêm vào Public surface.

## 2. Render — `/api/render` (`features/render/routers/`)

| Method | Path | Việc |
|--------|------|------|
| POST | `/api/render/process` | Tạo job render (đóng băng) |
| POST | `/api/render/upload-local` | Upload + render file local |
| POST | `/api/render/quick-process` | Render nhanh |
| POST | `/api/render/test-cloud-ai` | Test kết nối AI cloud |
| POST | `/api/render/resume/{job_id}` | Resume job gián đoạn |
| POST | `/api/render/retry/{job_id}` | Retry job lỗi |
| GET | `/api/render/{job_id}/cancel-status` | Trạng thái huỷ |
| POST | `/api/render/{job_id}/cancel` | Huỷ job |
| POST | `/api/render/prepare-source` | Tạo phiên preview nguồn |
| DELETE | `/api/render/prepare-source/{session_id}` | Xoá phiên preview |
| GET | `/api/render/preview-video/{session_id}` | Video preview |
| GET | `/api/render/preview-transcript/{session_id}` | Transcript preview |
| GET | `/api/render/jobs/{job_id}/parts/{part_no}/media` | Media của part |
| GET | `/api/render/jobs/{job_id}/parts/{part_no}/thumbnail` | Thumbnail part |
| GET | `/api/render/subtitle-preview` | Preview phụ đề |
| GET | `/api/render/queue-status` | Trạng thái hàng đợi |
| GET | `/api/render/system-info` | Thông tin hệ thống |
| POST | `/api/render/cache/clear` | Xoá cache render |
| GET | `/api/render/ai-diagnostics` | Chẩn đoán AI |
| POST | `/api/render/preview-prompt` | Preview prompt LLM (`prompt_preview.py`) |
| POST | `/api/render/batch` | Batch render từ asset library (`batch_render.py`) |

## 3. Jobs — `/api/jobs` (`routes/jobs.py` + nhiều router phụ)

| Method | Path | Việc |
|--------|------|------|
| GET | `/api/jobs` | Danh sách job |
| GET | `/api/jobs/history` | Lịch sử |
| GET | `/api/jobs/queue/status` | Trạng thái hàng đợi |
| GET | `/api/jobs/{job_id}` | Poll trạng thái (đóng băng) |
| GET | `/api/jobs/{job_id}/ws` | WebSocket (đóng băng) |
| GET | `/api/jobs/{job_id}/parts` | Danh sách part |
| GET | `/api/jobs/{job_id}/ai-summary` | Tóm tắt AI |
| GET | `/api/jobs/{job_id}/logs` | Log job |
| GET | `/api/jobs/{job_id}/quality` · `/parts/{part_no}/quality` | Chất lượng |
| GET | `/api/jobs/{job_id}/parts/{part_no}/stream` | Stream video part |
| GET | `/api/jobs/{job_id}/report` | Report (`job_report.py`) |
| GET | `/api/jobs/{job_id}/snapshot` | Snapshot (`snapshot.py`) |
| GET | `/api/jobs/{job_id}/outputs` · `/outputs/best` · `/outputs/export` | Output compare/export (`outputs.py`) |
| GET | `/api/jobs/{job_id}/outputs/{part_no}/thumbnail` | Thumbnail output (`thumbnails.py`) |
| POST | `/api/jobs/{job_id}/clone` | Clone/re-render (`job_clone.py`) |
| POST | `/api/jobs/{job_id}/extend` | Gia hạn |
| POST | `/api/jobs/{job_id}/queue/{move-top,move-bottom,move,hold,resume}` | Điều khiển hàng đợi |
| POST | `/api/jobs/cleanup/logs` | Dọn log |
| DELETE | `/api/jobs/{job_id}` | Xoá job (cascade) |
| DELETE | `/api/jobs/{job_id}/parts/{part_no}/output` | Xoá output 1 part |
| POST | `/api/jobs/{job_id}/parts/{part_no}/{trim,rerender,export}` | Editing (`editing/router.py`) |

## 4. Download — `/api/downloader` (`features/download/router.py`)

| Method | Path | Việc |
|--------|------|------|
| GET | `/api/downloader/info` | Probe metadata URL |
| POST | `/api/downloader/start` · `/batch` | Tạo job tải |
| GET | `/api/downloader/jobs` · `/jobs/{job_id}` | Liệt kê / xem job tải |
| DELETE | `/api/downloader/jobs/{job_id}` | Xoá job tải |
| WS | `/api/downloader/jobs/{job_id}/ws` | Tiến trình tải |
| POST | `/api/downloader/refresh-cookies` · `/import-cookies` | Cookie |
| GET | `/api/downloader/cookie-status` | Trạng thái cookie |

## 5. Settings & creator context

| Method | Path | Việc |
|--------|------|------|
| GET/PUT | `/api/settings/creator-context` | Creator context toàn cục |
| GET/PUT | `/api/settings/data-retention` | Số ngày giữ job |
| GET/PUT | `/api/settings/output-dir` | Thư mục lưu output |
| GET/PUT | `/api/settings/render-defaults` | Mặc định render |
| GET/PUT | `/api/settings/whisper/{channel_code}` | Cấu hình Whisper theo channel |
| GET | `/api/settings/channels` · `/channels/creator-context` | Channel |
| GET | `/api/settings/scores/{channel_code}` · `/summary` | Điểm A/B |
| DELETE | `/api/settings/scores/{job_id}` · PATCH `/scores/{job_id}/{part_no}/rating` | Sửa điểm |
| POST | `/api/settings/clear-history` | Xoá lịch sử |
| GET/PUT/DELETE | `/api/channels/{channel_code}/context` | Creator context theo channel (`channels_context.py`) |

## 6. Library, analytics, feedback, system

| Method | Path | Việc |
|--------|------|------|
| GET/DELETE | `/api/assets` · `/api/assets/{id}` | Asset library |
| GET/POST/PUT/DELETE | `/api/presets` ... | Smart render presets |
| GET | `/api/analytics/{overview,presets,scores/trend,feedback/by-hook,jobs/trend}` | Dashboard analytics |
| POST/GET/DELETE | `/api/feedback/jobs/{job_id}/parts/{part_no}` | Rating clip |
| GET | `/api/feedback/channel/{channel_code}` | Tóm tắt feedback |
| POST | `/api/feedback/platform-metrics` | Số liệu nền tảng |
| GET | `/api/voice/profiles` | Profile giọng TTS |
| GET | `/api/system/resources` | CPU/GPU/disk snapshot |
| GET | `/api/storage/summary` · POST `/api/storage/cleanup` | Dung lượng/dọn dẹp |
| POST | `/api/client/error` | Electron client error → `errors.jsonl` |
| POST | `/api/upload-file` | Upload file chung |
| GET | `/metrics` | Prometheus |
| GET | `/health` | Health + đường dẫn DB + cờ fallback |
| GET | `/api/warmup/status` | Trạng thái warmup |

## 7. Devtools (mặc định TẮT)

`POST /api/dev/command` — chạy shell, **không auth**. Chỉ mount khi
`ENABLE_DEVTOOLS=1` **và** bind loopback (3 lớp bảo vệ). Không bao giờ bật ở
production, không thêm endpoint mới.

## 8. Sinh type cho FE

`frontend` có script `gen:openapi` dump OpenAPI từ backend
(`backend/scripts/dump_openapi.py`) rồi sinh `src/types/openapi-generated.ts`.
`check:openapi-drift` fail khi type FE lệch backend.
