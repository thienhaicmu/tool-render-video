# Sprint Backlog — Phases C–T

> Last updated: 2026-06-13
> Branch: `feature/phases-c-to-l` (commit `3375850f`)
> Pytest baseline: 1087 passed, 1 pre-existing failure (test_render_pipeline_integration)

---

## Completed ✓

| Phase | Tên | Files chính | Commit |
|-------|-----|-------------|--------|
| C | Asset Library | `db/assets_repo.py`, `domain/asset.py`, `features/download/engine/enrichment.py`, `routes/assets.py`, migration `0007` | `3375850f` |
| D | Creator Feedback Loop | `db/feedback_repo.py` → `get_feedback_signals()`, `features/render/ai/feedback/signals.py`, `llm_stage.py` | `3375850f` |
| E | Smart Render Presets | `db/presets_repo.py`, `domain/render_preset.py`, `routes/presets.py`, `services/preset_seeder.py`, migration `0008` | `3375850f` |
| F | Multi-Output Compare & Export | `db/ab_scores_repo.py` → `list_ab_scores_for_job()`, `routes/outputs.py` | `3375850f` |
| G | Analytics Dashboard API | `routes/analytics.py` — overview / scores trend / feedback by-hook / jobs trend | `3375850f` |
| H | Whisper Speed Optimization | `adapters.py` → `WHISPER_BATCH_SIZE`, `pipeline_cache.py` → content-hash cache (`WHISPER_CONTENT_HASH_CACHE`) | `3375850f` |
| I | Per-Channel Creator Context API | `routes/channels_context.py` — `GET/PUT/DELETE /api/channels/{code}/context` | `3375850f` |
| J | Output Thumbnail API | `routes/thumbnails.py` — `GET /api/jobs/{id}/outputs/{part_no}/thumbnail` | `3375850f` |
| K | Batch Render from Asset Library | `routes/batch_render.py` — `POST /api/render/batch` (max 20 assets + preset) | `3375850f` |
| L | Disk Usage & Cleanup API | `routes/storage.py` — summary / per-job delete / bulk cleanup | `3375850f` |

---

## Remaining — theo thứ tự ưu tiên

### P — Job Snapshot Endpoint
**Risk:** LOW  
**Endpoint:** `GET /api/jobs/{job_id}/snapshot`  
**Mô tả:** Trả về full job state (job + parts + WsProgressSummary) dưới dạng một JSON blob duy nhất, shape giống hệt WebSocket event. Frontend dùng khi WS reconnect để re-sync ngay lập tức thay vì poll 3 endpoint riêng (`/jobs/{id}`, `/jobs/{id}/parts`, tính lại summary).  
**Files cần tạo:**
- `backend/app/routes/snapshot.py` (NEW) — tập hợp từ `get_job()` + `list_job_parts()` + tính `WsProgressSummary`
- `backend/app/main.py` (+2 lines)
- `frontend/src/types/api.ts` — không cần type mới (dùng lại `WebSocketEvent`)

---

### Q — Asset Search & Filter API
**Risk:** LOW  
**Endpoint:** `GET /api/assets?content_type=short_clip&language=vi&min_duration=30&max_duration=120&q=keyword&limit=20&offset=0`  
**Mô tả:** Hiện tại `GET /api/assets` trả toàn bộ không filter. Thêm query params: `content_type`, `language`, `min_duration`, `max_duration`, `q` (title search), `limit`/`offset` pagination.  
**Files cần sửa:**
- `backend/app/db/assets_repo.py` — mở rộng `list_assets()` với SQL WHERE filter
- `backend/app/routes/assets.py` — thêm query params vào GET endpoint
- `frontend/src/types/api.ts` — thêm `AssetsListResponse` interface

---

### M — Job Clone / Re-render API
**Risk:** MEDIUM  
**Endpoint:** `POST /api/jobs/{job_id}/clone`  
**Body (optional):** `{ whisper_model, output_count, llm_model, channel_code, output_dir, ... }`  
**Mô tả:** Deserialize `payload_json` từ DB, merge overrides, enqueue job mới qua `_queue_render_job()`. Cho phép "re-render với settings khác" từ history panel không cần rebuild payload.  
**Files cần tạo:**
- `backend/app/routes/job_clone.py` (NEW)
- `backend/app/main.py` (+2 lines)
- `frontend/src/types/api.ts` — `CloneJobRequest` interface

---

### R — LLM Prompt Preview
**Risk:** LOW  
**Endpoint:** `POST /api/render/preview-prompt`  
**Body:** subset của `RenderRequest` (source_video_path, channel_code, llm_model, ai_provider, ...)  
**Mô tả:** Trả về LLM prompt text sẽ được gửi mà không launch render. Dùng để debug và power users kiểm tra editorial hint trước khi render.  
**Files cần tạo:**
- `backend/app/routes/prompt_preview.py` (NEW) — gọi `_build_editorial_hint()` + `_build_prompt()` từ llm_stage
- `backend/app/main.py` (+2 lines)

---

### S — Job Export Report
**Risk:** LOW  
**Endpoint:** `GET /api/jobs/{job_id}/report`  
**Query:** `?format=json` (default) hoặc `?format=csv`  
**Mô tả:** Xuất tổng hợp job gồm: job metadata, per-part scores (viral/hook/retention/rank), AI decisions (ai_title, ai_reason), segment timing, file sizes. Dùng cho phân tích offline.  
**Files cần tạo:**
- `backend/app/routes/job_report.py` (NEW) — merge từ `get_job()` + `list_job_parts()` + `list_ab_scores_for_job()`
- `backend/app/main.py` (+2 lines)
- `frontend/src/types/api.ts` — `JobReport`, `JobReportPart` interfaces

---

### T — Output File Archive
**Risk:** LOW  
**Endpoint:** `POST /api/jobs/{job_id}/outputs/archive`  
**Body:** `{ archive_dir: "/path/to/archive" }`  
**Mô tả:** Di chuyển (move) các output files của job sang archive_dir, cập nhật `output_file` column trong DB về path mới. Khác với DELETE (xoá file) — archive giữ file nhưng dọn khỏi thư mục render output.  
**Files cần tạo:**
- `backend/app/routes/storage.py` (MODIFY) — thêm POST `/api/jobs/{job_id}/outputs/archive`
- `frontend/src/types/api.ts` — `ArchiveResponse` interface

---

## Env vars mới (Phase H)

| Var | Default | Mô tả |
|-----|---------|--------|
| `WHISPER_BATCH_SIZE` | `8` (CUDA) / `4` (CPU) | WhisperX batch size |
| `WHISPER_CONTENT_HASH_CACHE` | `0` | `1` = enable content-hash transcription cache |

## API endpoints mới (Phases C–L)

| Method | Path | Phase |
|--------|------|-------|
| GET | `/api/assets` | C |
| GET | `/api/assets/{asset_id}` | C |
| DELETE | `/api/assets/{asset_id}` | C |
| GET | `/api/jobs/{id}/outputs` | F |
| GET | `/api/jobs/{id}/outputs/best` | F |
| GET | `/api/jobs/{id}/outputs/export` | F |
| GET | `/api/jobs/{id}/outputs/{part_no}/thumbnail` | J |
| DELETE | `/api/jobs/{id}/outputs` | L |
| GET | `/api/analytics/overview` | G |
| GET | `/api/analytics/scores/trend` | G |
| GET | `/api/analytics/feedback/by-hook` | G |
| GET | `/api/analytics/jobs/trend` | G |
| GET | `/api/presets` | E |
| POST | `/api/presets` | E |
| PUT | `/api/presets/{id}` | E |
| DELETE | `/api/presets/{id}` | E |
| GET | `/api/channels/{code}/context` | I |
| PUT | `/api/channels/{code}/context` | I |
| DELETE | `/api/channels/{code}/context` | I |
| POST | `/api/render/batch` | K |
| GET | `/api/storage/summary` | L |
| POST | `/api/storage/cleanup` | L |
