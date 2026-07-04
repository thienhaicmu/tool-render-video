# 15 — Review Performance

## 1. CPU / GPU / Thread

| Cơ chế | Vị trí | Đánh giá |
|--------|--------|----------|
| `MAX_CONCURRENT_JOBS` | manager.py:40 (mặc định `cpu//2`) | Cap job đồng thời — bảo vệ máy desktop |
| `NVENC_SEMAPHORE` | ffmpeg_helpers.py:28 (mặc định 3) | Cap phiên NVENC — chống fail-all |
| `resolve_ffmpeg_threads(workers)` | recap P1 fix | Chia core đều, tránh idle CPU |
| Worker cap GPU vs CPU | recap:686, content:284 | GPU→NVENC-capped, CPU→core-capped |
| `JOB_SEMAPHORE` + `_render_active_count` | render_pipeline | Cap render đồng thời cấp pipeline |

**Điểm mạnh:** phân biệt rõ đường NVENC (single-shot, semaphore) và đường CPU
(parallel, core-capped). Content parallel dùng libx264 → không tranh NVENC (đã xác
minh doc 13). **Đây là quản lý tài nguyên chín.**

## 2. Whisper (bottleneck AI chính)

- Transcribe **1 lần** toàn video, tái dùng cho mọi part (clip/recap).
- **Warmup** model vào RAM lúc startup ([main.py:373-383](../../backend/app/main.py#L373-L383))
  → job đầu không trả 5-15s load cost.
- **LRU cache cap 2** cho cả openai-whisper + faster-whisper (Issue 7 RESOLVED) →
  không pin multi-GB khi trộn tiny(preview)+large-v3(render).
- **Lock-serialised** → parallel scene an toàn.

## 3. Song song hoá thông minh (recap)

SceneMap (scenedetect) chạy **thread nền song song** với Whisper + LLM, join ngay
trước consumer đầu tiên ([recap_pipeline.py:316-335](../../backend/app/features/render/engine/pipeline/recap_pipeline.py#L316)).
→ overlap wall-clock. Sáng kiến tốt.

## 4. Disk / Cache

- **Cache root** `APP_DATA_DIR/cache`, prune startup + mỗi 1800s, TTL 72h render /
  30d xtts+gemini / 7d overlay. Atomic write (`.tmp`+os.replace, Batch 10F).
- **Free-disk preflight** (N8) từ chối render nếu <256MB, warn <2GB
  ([_common.py:151-178](../../backend/app/features/render/routers/_common.py#L151)).
- **Cleanup on failure** — CLAUDE.md bắt buộc; temp/preview/render dir prune.

## 5. DB / Network

- WAL + 2-pattern connection (`_thread_conn` hot path 165× nhanh hơn `db_conn`).
- Index đóng full-scan history/recovery.
- WS `_ws_fingerprint` chỉ push khi state đổi → giảm traffic.
- Không network ngoài (offline) trừ LLM/download provider.

## 6. Vấn đề & tối ưu

### PERF-1: SQLite write throughput là trần
- Progress write tần suất cao qua `_thread_conn`; WAL giảm chặn reader nhưng nhiều
  job đồng thời + nhiều part → nhiều write nhỏ. Hiện MAX_CONCURRENT_JOBS nhỏ nên OK.
- **Dài hạn:** batch progress write (debounce update_job_progress ~250ms).

### PERF-2: God-function không ảnh hưởng perf nhưng cản tối ưu
- Khó chèn caching/parallel mới vào 1934-dòng function.

### PERF-3: Render-plan cache
- Whisper cache có; render plan (LLM) cache — kiểm tra `cache.py`. Nếu cùng
  (source+params) render lại vẫn gọi LLM → cache theo hash prompt sẽ tiết kiệm
  latency + chi phí. **Cần xác minh cache LLM đang bật cho render plan.**

### PERF-4: Content không warmup provider visual
- Scene visual (stock/ai_image/ai_video) gọi tuần tự trong worker; không prefetch.
  Với budget guard, chi phí kiểm soát nhưng latency có thể cải thiện bằng prefetch
  song song asset trước vòng render.

## 7. Đánh giá

| Trục | Điểm |
|------|------|
| GPU/CPU management | 9 |
| Whisper optimization | 8.5 |
| Parallelism | 8.5 |
| Cache/disk | 8 |
| DB throughput | 6.5 |
| **Tổng** | **8.0** |

**Kết luận:** perf là điểm mạnh — các protection là "system failure prevention",
không phải micro-opt. Trần scale là SQLite + single-machine (by design).
