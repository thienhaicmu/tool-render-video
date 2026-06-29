# Database — AI Video Render Studio

> Cập nhật 2026-06-29 từ source. Vùng **HIGH**. Quy tắc additive-only là tuyệt đối.

## 1. Nguyên tắc cốt lõi (Sacred Contract #7)

`data/app.db` là **nguồn chân lý duy nhất** của mọi trạng thái job. Không Redis,
không cloud, không fallback in-memory sống sót qua restart.

- **KHÔNG** xoá file này.
- **KHÔNG** `sqlite3.connect()` thô ngoài `backend/app/db/`.
- **KHÔNG** `DROP` / `TRUNCATE` / `ALTER TABLE RENAME` cột hay bảng.
- Đây là app desktop — **không có backup, không có recovery**. Mất = mất vĩnh viễn.

Vị trí thực: `APP_DATA_DIR/app.db` (xem [CONFIGURATION.md](CONFIGURATION.md)). Khi
đường dẫn chính không ghi được, `connection.py` fallback sang `LOCALAPPDATA` và
log CRITICAL + tạo `DB_FALLBACK_ENGAGED.flag` (split-DB là tình huống cần xử lý).

## 2. Mô hình kết nối

File: `backend/app/db/connection.py`. **WAL mode** bật lúc startup — không đổi
journal mode (DELETE mode khiến writer chặn reader, làm UI đứng khi render).

Hai pattern kết nối (steady state, đã chốt giữ nguyên):

| Pattern | Dùng cho | Hành vi |
|---------|----------|---------|
| `db_conn()` (context manager) | HTTP path / thao tác có giới hạn | Auto-commit khi thoát thường, rollback khi exception |
| `_thread_conn()` | Hot path render | Connection thread-local bền; dùng bởi `update_job_progress()` + `upsert_job_part()`; giải phóng bằng `close_thread_conn()` |

`db_conn` chậm hơn ~165× mỗi call (3.152 μs vs 18.8 μs) → việc hợp nhất bị hoãn
vô thời hạn. **Không** thêm pattern thứ ba (raw `sqlite3.connect()` ngoài các chỗ
được phép: `connection.py`, `pipeline/db_backup.py`,
`features/download/engine/cookie_extractor.py`).

Repo (tất cả qua `db/`): `jobs_repo`, `creator_repo`, `feedback_repo`,
`download_repo`, `assets_repo`, `presets_repo`, `history_repo`, `ab_scores_repo`,
`platform_metrics_repo`.

## 3. Schema baseline (`connection.py::init_db`)

### `jobs`
| Cột | Kiểu | Ghi chú |
|-----|------|---------|
| `job_id` | TEXT PK | |
| `kind` | TEXT | `render` / `download` |
| `channel_code` | TEXT | |
| `status` | TEXT | running/queued/done/failed/cancelled |
| `stage` | TEXT | giá trị `JobStage` |
| `progress_percent` | INTEGER | |
| `message` | TEXT | |
| `payload_json` | TEXT | `RenderRequest` đầy đủ (để replay) |
| `result_json` | TEXT | kết quả + key Sacred Contract #1 |
| `priority` | INTEGER | thêm qua `_ensure_columns` |
| `error_kind` | TEXT | |
| `render_plan_json` | TEXT | thêm qua migration 0001 |
| `created_at` / `updated_at` | TEXT | |

Index: `idx_jobs_updated(updated_at DESC, created_at DESC)`,
`idx_jobs_status_kind(status, kind)`.

### `job_parts`
Mỗi clip một dòng: `id` PK, `job_id`, `part_no`, `part_name`, `status` (giá trị
`JobPartStage`), `progress_percent`, `start_sec`, `end_sec`, `duration`,
`viral_score`, `motion_score`, `hook_score`, `output_file`, `message`, timestamps.
`UNIQUE(job_id, part_no)` + `FOREIGN KEY(job_id) → jobs(job_id) ON DELETE CASCADE`
(DB mới; DB cũ được retrofit bằng migration 0003). Migration 0011 thêm
cover_quality.

### `creator_prefs`
Singleton (`id=1`), `prefs_json` — chứa creator context, data_retention
(`job_retention_days`), render defaults… Migration 0005 thêm bảng per-channel.

### `download_jobs`
Job tải độc lập (yt-dlp), không gắn vào render pipeline: url, platform, status,
progress, speed/eta, output_path/dir, filename, title, duration, height, fps,
filesize, error_msg, timestamps. Index theo status + created_at.

### `clip_feedback` (Phase 6)
Rating người dùng để bias chọn clip AI tương lai: `job_id`, `part_no`,
`channel_code`, `goal`, `rating ∈ {-1, 1}`, `hook_type`, `clip_type`, thời lượng,
`rated_at`. `UNIQUE(job_id, part_no)` + FK cascade. Index theo `(channel_code, goal)`.

Bảng khác qua migration: `render_ab_scores` (0004/0006), `assets` (0007/0009),
`render_presets` (0008), `platform_metrics` (0010), `schema_versions` (runner).

## 4. Migration (additive-only)

Runner: `backend/app/db/migrations.py`. File trong `db/migration_steps/` theo quy
ước `NNNN_slug.py`, export `VERSION: int`, `NAME: str`, `up(conn)`. Mỗi migration
chạy trong transaction riêng; lỗi → rollback + `MigrationError` (init_db bắt để
app vẫn boot). Bảng `schema_versions` ghi version đã áp dụng (idempotent).

Thứ tự khởi động: `init_db()` dựng/migrate baseline (CREATE IF NOT EXISTS +
`_ensure_columns` ALTER ADD COLUMN) → `run_pending_migrations()` áp các step mới.

### Cho phép vs Cấm

| Cho phép | Cấm |
|----------|-----|
| Bảng mới (cột nullable hoặc có DEFAULT) | DROP TABLE |
| Cột mới có DEFAULT | DROP COLUMN |
| Index mới | RENAME COLUMN / ALTER TABLE RENAME |
| | Đổi kiểu cột |

Lý do: app desktop không có đường rollback migration. Migration phá huỷ chạy trên
máy người dùng = mất dữ liệu vĩnh viễn.

## 5. Retention & cleanup

`prune_old_jobs(max_age_days)` chạy mỗi tick cleanup (mặc định 30 phút). Đọc
`data_retention.job_retention_days` từ `creator_prefs` (UI Settings), fallback env
`JOB_RETENTION_DAYS`. `0` = tắt retention (mặc định). Job đang active
(`running`/`queued`) **không bao giờ** bị prune bất kể tuổi (Contract #7).

## 6. Quan sát

Mỗi lần acquire connection phát vào histogram Prometheus
`db_conn_acquire_seconds` với label `role={db_conn|_thread_conn}` (bỏ qua cache
hit của `_thread_conn`). Xem `/metrics`.
