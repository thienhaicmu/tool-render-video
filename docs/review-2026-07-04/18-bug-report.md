# 18 — Bug Report

> Nguyên tắc: chỉ liệt kê điều **đọc được từ code**, phân biệt rõ **BUG xác nhận**,
> **rủi ro tiềm ẩn (latent)**, và **không phải bug (đã xác minh an toàn)**. Review
> tĩnh — không chạy được test suite trong phiên này (cần chạy `pytest` để xác nhận).

## A. Không phát hiện BUG active nghiêm trọng

Sau khi đọc 3 orchestrator, queue, DB, AI dispatch, QA gate: **không tìm thấy bug
logic active rõ ràng**. Hệ thống có mật độ guard/test cao (204 test file) và nhiều
lỗi production đã được vá (có comment fix dated: dedup-Whisper, concat-drift,
recap part dead-link, fontconfig crash...). Đây là dấu hiệu codebase trưởng thành.

## B. Rủi ro tiềm ẩn (Latent — chưa phải bug, cần theo dõi/test)

### LAT-1 · Coupling recap → render_pipeline internals (Race/Break risk)
- **Mô tả:** recap import `JOB_SEMAPHORE`/`_render_active_lock/count` từ clips.
- **Rủi ro:** đổi semantic concurrency ở clips → recap sai thầm lặng.
- **Kiểm chứng:** full pytest khi đụng render_pipeline (đã bắt buộc).
- **Sửa:** TD-C2.

### LAT-2 · Dedup source dựa "30 job gần nhất"
- `_find_active_duplicate_source` scan `list_jobs_page(30, 0)`
  ([_common.py:349](../../backend/app/features/render/routers/_common.py#L349)).
- **Rủi ro:** nếu >30 job non-terminal gần đây (không xảy ra khi bounded bởi
  MAX_CONCURRENT_JOBS, nhưng phụ thuộc ngầm), duplicate active có thể lọt.
- **Sửa:** query trực tiếp `status IN (...)` không giới hạn 30, hoặc thêm index-backed
  scan theo source_video_path.

### LAT-3 · 2 codec resolver có thể divergence
- `ffmpeg_helpers._resolve_codec` vs `encoder_helpers.resolve_encoder`.
- **Rủi ro:** nếu lệch, crop chạy NVENC không semaphore → fail-all sessions.
- **Bảo vệ hiện tại:** `tests/test_nvenc_codec_resolver_parity.py`. Giữ lockstep.

### LAT-4 · `nvenc_runtime_ready()` probe NVENC không semaphore
- `@lru_cache` ≤2 lần/process; xác suất thấp dưới burst render đồng thời.
- **Sửa (dài hạn):** bọc semaphore hoặc dùng cached capability detect không mở session.

### LAT-5 · Migration failure non-fatal
- `run_pending_migrations` fail → log WARNING, app vẫn boot với baseline schema
  ([connection.py:405-409](../../backend/app/db/connection.py#L405)).
- **Rủi ro:** một migration lỗi giữa chừng → schema partial, code mới đọc cột chưa
  có → lỗi runtime khó chẩn đoán.
- **Sửa:** migration nên atomic per-step + đánh dấu version chỉ khi commit trọn;
  surface trạng thái "migration incomplete" ở /health.

### LAT-6 · Content parallel loop cancel giữa submit
- Content dùng ThreadPool riêng; khi cancel giữa submit, "stop submitting; running
  futures self-check cancel" ([content_pipeline.py:404-406](../../backend/app/features/render/engine/pipeline/content_pipeline.py#L404)).
  Đúng logic, nhưng future đang chạy chỉ check cancel giữa sub-step → 1 scene có
  thể chạy nốt sau cancel (chi phí, không sai kết quả). Chấp nhận được.

## C. Đã xác minh KHÔNG phải bug (verified safe)

- **Content parallel không tranh NVENC:** scene encode libx264-only
  ([content_scene_render.py:337](../../backend/app/features/render/engine/stages/content_scene_render.py#L337),
  content_background libx264-only). Concat cuối NVENC 1-shot + semaphore. ✓
- **Phantom job:** `process_render` ép terminal row khi setup raise trước try
  ([_common.py:279-298](../../backend/app/features/render/routers/_common.py#L279));
  reconcile orphaned bổ sung. ✓
- **Thread-conn leak:** belt-and-suspenders close ở `process_render.finally` +
  pipeline finally. ✓
- **Cancel khi queued:** `ev.is_set()` check đầu process_render. ✓

## D. Cần chạy để xác nhận (không làm được trong phiên tĩnh)

1. `cd backend && python -m pytest` — xác nhận 204 test file pass (baseline).
2. Kiểm `download_repo` `cols` nguồn (column injection LOW — doc 16).
3. Kiểm output/thumbnail serving có chặn traversal ngoài output_dir không.
4. Xác minh LLM render-plan cache có active (PERF-3).

## E. Dead code / unused

- Không quét toàn bộ; CLAUDE.md ghi vài mục đã xóa (channels, services/db, build_render_plan).
  `upload_*` table drop idempotent ở init_db (domain đã bỏ) — dọn sạch, tốt.
- `models/schemas.py` = 39-dòng re-export shim (MT-2) — nợ tương thích, không dead.

## Tổng kết bug

| Loại | Số lượng |
|------|----------|
| BUG active nghiêm trọng | **0** (đọc tĩnh) |
| Rủi ro latent | 6 |
| Cần chạy để xác nhận | 4 |
| Verified safe | 4 |
