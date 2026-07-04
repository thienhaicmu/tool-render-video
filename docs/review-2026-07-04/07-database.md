# 07 — Review Database

## 1. Engine & mô hình

- **SQLite (WAL mode)**, single file `data/app.db` — sole job state authority
  (Sacred Contract #7). Không Redis/cloud.
- Connection tại [db/connection.py](../../backend/app/db/connection.py):
  - `db_conn()` — HTTP path, context manager transaction (commit/rollback/close).
  - `_thread_conn()` — render hot path, thread-local persistent connection.
  - Mọi conn set `PRAGMA journal_mode=WAL; synchronous=NORMAL; foreign_keys=ON`.

## 2. Schema (bảng chính)

| Bảng | Vai trò | Ghi chú |
|------|---------|---------|
| `jobs` | Job render/download | PK `job_id`, index `(updated_at,created_at)`, `(status,kind)` |
| `job_parts` | Part/scene per job | UNIQUE(job_id,part_no), **FK CASCADE** (Batch 10L) |
| `clip_feedback` | Rating clip | FK CASCADE, CHECK rating∈(-1,1) |
| `creator_prefs` | Singleton prefs | CHECK id=1 |
| `download_jobs` | Downloader | index status/created |
| `content_projects` | Content Studio draft | migration 0016 |
| + render_ab_scores, assets, render_presets, platform_metrics, creator_prefs_channel, scene_map/story_model/recap_plan/content_plan JSON cols | migrations 0001-0016 |

Nhiều "plan" lưu dạng **JSON column** trên `jobs` (`render_plan_json`,
`recap_plan_json`, `story_model_json`, `scene_map_json`, `content_plan_json`) —
pattern document-in-relational.

## 3. Migration

16 step additive-only ([db/migration_steps/](../../backend/app/db/migration_steps/)),
runner idempotent + `schema_versions` table, failure non-fatal (log WARNING,
không chặn boot — [connection.py:405-409](../../backend/app/db/connection.py#L405-L409)).
Không có DROP/RENAME/type-change — **tuân thủ nghiêm** quy tắc offline no-rollback.

`init_db()` cũng có `_ensure_columns()` ALTER ADD phòng thủ cho DB cũ, và
`ANALYZE` refresh planner stats.

## 4. Index / Constraint / Concurrency / Lock

- **Index:** `idx_jobs_updated`, `idx_jobs_status_kind`, download + feedback
  index. Đóng lỗ full-scan cho history pagination + recovery filter (audit
  2026-06-02). **Tốt.**
- **Constraint:** FK CASCADE trên job_parts/clip_feedback (2 bảng con của jobs) —
  `delete_job` atomic qua transaction, FK là defense-in-depth (BR03).
- **Concurrency:** WAL cho phép reader đồng thời khi có 1 writer → progress write
  hot path không chặn HTTP polling. Đây là lý do WAL **không được đổi**
  (CLAUDE.md). Đúng.
- **Fallback:** nếu primary path không ghi được → fallback `LOCALAPPDATA`, cảnh
  báo CRITICAL + drop flag file. Xử lý split-DB có ý thức.

## 5. Vấn đề & rủi ro

### ⚠ DB-1: Mixed connection model (2 pattern) — DEFERRED
- **Root cause:** `db_conn()` chậm ~165× so với `_thread_conn()` (3152μs vs 18.8μs).
- **Ảnh hưởng:** Thấp — đã benchmark, quyết định deferred indefinitely; enforced
  bởi `tests/test_contract_db_sole_authority.py` chống pattern thứ 3.
- **Kết luận:** chấp nhận được; là steady state có chủ đích.

### ⚠ DB-2: SQLite là trần scale ngang
- **Root cause:** single-writer. Với desktop 1 user + MAX_CONCURRENT_JOBS nhỏ →
  không phải nút cổ chai. Nhưng chặn multi-tenant/cloud.
- **Ảnh hưởng:** Cao NẾU đổi hướng sang SaaS; Không nếu giữ desktop.
- **Dài hạn:** nếu cloud hoá → tách job-state store (Postgres) + object storage;
  repo pattern hiện tại giúp việc này khả thi (đổi implement `*_repo.py`).

### ⚠ DB-3: JSON-in-column khó query
- **Root cause:** plan/story/scene_map lưu JSON blob → không index được nội dung.
- **Ảnh hưởng:** Thấp bây giờ; nếu cần analytics theo trường trong plan sẽ phải
  full-scan + parse.
- **Dài hạn:** nếu cần → cột generated + index (SQLite hỗ trợ JSON1).

### ⚠ DB-4: Không backup/replication
- **Root cause:** offline desktop by design (CLAUDE.md: no recovery path).
- **Ảnh hưởng:** Cao cho user (mất app.db = mất toàn bộ history).
- **Ngắn hạn:** thêm export/snapshot định kỳ (`db_backup.py` đã tồn tại — kiểm
  tra cadence); khuyến khích user chọn thư mục output có backup.

## 6. Đánh giá

| Trục | Điểm | Ghi chú |
|------|------|---------|
| Schema design | 7.5 | Chuẩn hoá tốt + JSON pragmatic |
| Migration safety | 9 | Additive-only, idempotent, non-fatal |
| Index/perf | 8 | Đóng full-scan; WAL đúng |
| Concurrency | 8 | WAL + 2-pattern có chủ đích |
| Scalability | 4 | SQLite single-machine |
| Durability | 5 | No backup by design |
| **Tổng** | **6.9** | |
