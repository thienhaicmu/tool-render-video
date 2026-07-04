# 04 — Review Backend

## 1. Bản đồ module & trách nhiệm

| Layer | Module | Trách nhiệm | Coupling | Cohesion |
|-------|--------|-------------|----------|----------|
| HTTP | `routes/*.py` (~24) | REST mỏng, 1 domain/file | Thấp | Cao |
| HTTP | `features/render/routers/*` | Render lifecycle, dispatch | TB | Cao |
| Service | `services/*` | channel, maintenance, metrics, warmup | Thấp | Cao |
| Queue | `jobs/manager.py`, `jobs/cancel.py` | Hàng đợi, watchdog, recovery | Thấp | **Rất cao** |
| Pipeline | `engine/pipeline/*` | Orchestrate render 3 mode | **Cao** | TB |
| Stage | `engine/stages/*` | Đơn vị render (part/scene) | TB | Cao |
| Encoder | `engine/encoder/*` | FFmpeg exec + NVENC | TB | Cao |
| AI | `ai/llm/*` | Provider dispatch + parse + prompt | Thấp | Cao |
| Data | `db/*_repo.py` | CRUD qua connection | Thấp | Cao |
| Domain | `domain/*.py` | Dataclass thuần, no I/O | Không | **Rất cao** |

## 2. Service layer / Repository / Model / DTO

- **Repository pattern rõ ràng:** mỗi bảng có `*_repo.py`
  (`jobs_repo`, `creator_repo`, `content_repo`, `assets_repo`, `presets_repo`,
  `feedback_repo`, `download_repo`, `history_repo`, `platform_metrics_repo`,
  `ab_scores_repo`). Tất cả access DB **chỉ** qua `db/connection.py`
  (`db_conn()` hoặc `_thread_conn()`), enforced bởi
  `tests/test_contract_db_sole_authority.py`. **Rất tốt.**
- **DTO/Model:** `models/render.py` chứa `RenderRequest` (internal, 201 field) +
  `RenderRequestStrict`; `models/render_public.py` = wire surface 88 field
  `extra='forbid'`. Tách public/internal (MT-3) là quyết định **đúng** để bảo vệ
  Sacred Contract #2 mà vẫn giới hạn bề mặt FE.
- **Domain dataclass:** `render_plan`, `recap_plan`, `content_plan`, `scene_map`
  — (de)serialise phòng thủ, đúng nguyên tắc DDD "domain thuần".

### ⚠ Vấn đề: RenderRequest 201 field (flat model)
- **Root cause:** mọi feature/mode mới thêm field vào cùng một model phẳng thay
  vì gom nhóm (đã có `render_field_groups.py` nhưng field vẫn nằm phẳng ở
  `render.py`).
- **Ảnh hưởng:** Trung bình. Khó đọc, dễ vi phạm Sacred #2 (default sai),
  validation nặng.
- **Phạm vi:** mọi consumer deserialize job cũ (replay/retry).
- **Ngắn hạn:** giữ nguyên (Sacred #2 cấm đổi), thêm nhóm con `Optional[SubModel]`
  cho field MỚI.
- **Dài hạn:** version hoá payload (`payload_schema_version`), migrate dần sang
  nested config; giữ backward-compat qua adapter đọc.

## 3. Middleware · Cache · Logging · Exception · Config

- **Middleware:** GZip + CSP (chỉ v2 UI). Không có middleware auth/rate-limit
  (by design cho loopback — doc 16).
- **Cache:** `pipeline_cache.py` (render/whisper/overlay) — atomic write qua
  `.tmp` + `os.replace` (Batch 10F), prune bỏ qua `.tmp`. TTL 72h/30d/7d.
  **Đã đóng** các lỗ growth vô hạn.
- **Logging:** phân loại 3-type error (Type 1 request.log, Type 2 error.log +
  channel log, Type 3 desktop-backend.log) — [_common.py:23-37](../../backend/app/features/render/routers/_common.py#L23-L37).
  Filter suppress noisy access + client-disconnect. **Thiết kế logging chín.**
- **Exception:** mọi AI module trả None; pipeline setup lỗi được `process_render`
  bắt và ép terminal row (chống phantom job) — [_common.py:279-298](../../backend/app/features/render/routers/_common.py#L279-L298).
- **Config:** `core/config.py` env-driven, path resolution packaged/dev. LOW-tier.

## 4. Worker / Scheduler

`jobs/manager.py` (723 dòng) — **module tốt nhất về mặt kỹ thuật đồng thời:**
- Min-heap `(-priority, seq, job_id, fn, args, kwargs)` — FIFO trong tier.
- Một scheduler thread, dispatch tới `ThreadPoolExecutor(MAX_CONCURRENT_JOBS)`.
- Watchdog thread hủy job quá `MAX_JOB_AGE_SECONDS` (2h) + per-job extend override.
- Hold/resume, move-to-front/back, reorder — Queue Workspace UI.
- Graceful shutdown có bound timeout (signal cancel → drain → abandon).
- Startup recovery + reconcile orphaned/phantom.

**Điểm trừ nhỏ:**
- Toàn bộ state in-memory (`_pending`, `_held`, `_job_age_overrides`) — restart
  mất hold/override; đã ghi chú và chấp nhận. Đúng cho desktop.
- `_run` wrapper nuốt mọi exception log ở [manager.py:257](../../backend/app/jobs/manager.py#L257) — job lỗi vẫn được `process_render` xử lý terminal riêng, nên OK.

## 5. Đánh giá backend

| Module | Kiến trúc | Code | Bảo trì | Ghi chú |
|--------|-----------|------|---------|---------|
| jobs/manager | 8.5 | 8.5 | 8 | Chuẩn mực |
| db + repo | 8 | 8 | 8 | Sole-authority enforced |
| models | 6 | 5.5 | 5 | 201-field flat |
| pipeline | 6 | 6 | 5 | God-file render_pipeline |
| ai/llm | 8 | 8 | 7.5 | Fallback + safety tốt |
| routes | 7.5 | 7.5 | 8 | Mỏng, rõ |
| **Trung bình** | **7.3** | **7.2** | **6.9** | |

**Kết luận:** backend là phần **chín nhất** của hệ thống. Nợ kỹ thuật tập trung
ở `render_pipeline.py` (1934 dòng) và `RenderRequest` (201 field) — cả hai đều bị
Sacred Contract khóa nên phải refactor có kế hoạch (doc 21).
