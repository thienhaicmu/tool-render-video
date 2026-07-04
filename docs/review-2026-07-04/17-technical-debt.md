# 17 — Technical Debt

Phân loại theo mức độ. Mỗi mục: Root Cause · Ảnh hưởng · Phạm vi · Ngắn hạn · Dài hạn.

## CRITICAL

### TD-C1 · `render_pipeline.py` = 1934 dòng (God-function)
- **Root cause:** clips path lớn dần inline; stage tách helper nhưng orchestration
  tập trung ở `run_render_pipeline` (472→~1930).
- **Ảnh hưởng:** Rất cao — CRITICAL tier, đổi nhỏ ảnh hưởng mọi render; cản mọi
  tối ưu/mở rộng.
- **Phạm vi:** toàn bộ clip mode + gián tiếp recap (import primitive).
- **Ngắn hạn:** đóng băng, tuân Render Edit Protocol; thêm test đặc trưng từng block.
- **Dài hạn:** rút block (transcribe-heartbeat, clip-filter, finalize) thành stage
  module; mục tiêu ~300 dòng điều phối. Kế hoạch riêng, full pytest baseline.

### TD-C2 · Concurrency primitive nằm trong render_pipeline, bị recap/content import
- **Root cause:** `JOB_SEMAPHORE`, `_render_active_lock/count` định nghĩa trong
  clips module, recap import trực tiếp ([recap_pipeline.py:63-67](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L63-L67)).
- **Ảnh hưởng:** Cao — "3 mode tách hoàn toàn" là ảo tưởng; đổi clips vỡ recap.
- **Dài hạn:** nâng lên `engine/concurrency.py` trung lập.

## HIGH

### TD-H1 · `RenderRequest` = 201 field phẳng
- **Root cause:** mọi feature thêm field vào 1 model; Sacred #2 khóa.
- **Ảnh hưởng:** Cao bảo trì; nặng validation; dễ default sai.
- **Ngắn hạn:** field MỚI gom vào `Optional[SubModel]` default disabled.
- **Dài hạn:** `payload_schema_version` + nested config + adapter đọc bản cũ.

### TD-H2 · Duplicate orchestration 3 mode
- **Root cause:** mỗi mode viết lại `_set_stage`, `_safe_filename`, terminal
  result_json block.
- **Ảnh hưởng:** Cao — Sacred #1 keys phải maintain 3 nơi, rủi ro lệch.
- **Dài hạn:** `_orchestrator_base.py` (doc 14 §6).

### TD-H3 · Bùng nổ env flag (đặc biệt recap AI)
- **Root cause:** mỗi cải tiến thêm kill-switch.
- **Ảnh hưởng:** TB-Cao — không gian cấu hình lớn, khó test tổ hợp, bug phụ thuộc env.
- **Dài hạn:** gom thành "intelligence profile" (basic/standard/max).

### TD-H4 · Auth model — no-auth cả khi remote
- Xem doc 16. Dài hạn: optional token auth khi ALLOW_REMOTE=1.

## MEDIUM

### TD-M1 · `part_voice_mix.py` (1192) + `part_asset_planner.py` (1104)
- Stage helper phình to; cohesion còn cao. Dài hạn: tách sub-helper theo bước.

### TD-M2 · Content Studio FE 1 file 709 dòng
- Doc 05/13. Ngắn hạn: tách steps/.

### TD-M3 · `main.py` (498) ôm đồm (env/security/CSP/cleanup/health)
- Dài hạn: tách `bootstrap/` (env, security, cleanup scheduler).

### TD-M4 · Ownership `recap_assembler` mờ (phục vụ 3 mode từ stages/)
- Dài hạn: → `engine/media/assembly.py`.

### TD-M5 · 2 codec resolver song song (parity test pinned)
- Rủi ro divergence. Dài hạn: hợp nhất (CRITICAL plan).

## LOW

- TD-L1 · Alias route deprecated (`render/history/editor` cùng screen) — dọn dần.
- TD-L2 · `publish` panel placeholder — hoàn thiện hoặc ẩn.
- TD-L3 · `prototype.html`/`render-flow.html` drift risk — nên gắn CI check hoặc xóa.
- TD-L4 · Response shape API không đồng nhất — chuẩn hoá cho endpoint mới.
- TD-L5 · `download_repo` f-string `SET {cols}` — whitelist tên cột (doc 16).
- TD-L6 · v2 routes song song (ENABLE_V2) — làm rõ vòng đời migrate v1→v2.

## Bảng ưu tiên trả nợ

| ID | Mức | Effort | ROI | Ưu tiên |
|----|-----|--------|-----|---------|
| TD-C2 | CRIT | Thấp | Cao | **1** (nâng concurrency — ít rủi ro, gỡ coupling) |
| TD-H2 | HIGH | TB | Cao | **2** (_orchestrator_base — giảm 3× maintain Sacred #1) |
| TD-H3 | HIGH | TB | TB | 3 |
| TD-C1 | CRIT | Cao | Cao | 4 (cần plan lớn, baseline) |
| TD-M2 | MED | TB | TB | 5 |
| TD-H1 | HIGH | Rất cao | TB | 6 (dài hạn, versioning) |
