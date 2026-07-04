# 11 — Clip Mode (review chuyên sâu)

`render_format="clips"` (mặc định) — orchestrator `run_render_pipeline`
([render_pipeline.py:472](../../backend/app/features/render/engine/pipeline/render_pipeline.py#L472), **1934 dòng**).

## 1. Workflow

```
source (local file / edit_session)
  → Whisper transcribe TOÀN video 1 lần (TRANSCRIBING_FULL, heartbeat progress)
  → scene_detection (PySceneDetect)
  → SEGMENT_BUILDING: LLM select_render_plan → clips + subtitle_policy +
       camera_strategy + audio_plan + overlays  (1 call, fallback nếu None)
  → clip_lock / clip_exclude filter (Timeline Steering hard constraint)
  → run_render_loop: parallel part dispatch → part_renderer(8 stage)
  → pipeline_ranking: viral_scoring (market-aware) → rank → best clip
  → QA từng output (Sacred #8) → WRITING_REPORT → DONE
```

## 2. Input / Output

- **Input:** `source_video_path` (local) hoặc `edit_session_id`. Không nhận remote
  (phải qua Downloader trước) — [_common.py:192-200](../../backend/app/features/render/routers/_common.py#L192-L200).
- **Output:** N clip dọc (9:16), mỗi clip có subtitle burn, overlay, voice,
  viral_score + rank. `result_json` mang Sacred #1 keys per output.

## 3. Business logic đặc thù

- **Whisper 1 lần** cho toàn video rồi tái dùng cho mọi part → tránh transcribe
  lặp (dedup-Whisper bug đã fix qua source dedup ADR-007).
- **Timeline Steering:** `clip_lock` (ép chọn), `clip_exclude` (loại) —
  `_apply_clip_lock_exclude_filter` ([:260](../../backend/app/features/render/engine/pipeline/render_pipeline.py#L260)).
- **Multi-variant / creator DNA:** hook_strength, structure_bias, target_market,
  subtitle_emphasis threaded vào prompt (S5 creator prefs).
- **Ranking:** `viral_scoring` rule-based per market → `output_rank_score`,
  `is_best_output`, `is_best_clip`.

## 4. Đánh giá theo checklist yêu cầu

| Câu hỏi | Kết luận |
|---------|----------|
| Workflow đúng? | **Đúng** — transcribe→detect→plan→render→rank→QA logic mạch lạc |
| Dư bước? | Không rõ dư; nhưng finalize/result_json trùng với recap/content (doc 14) |
| Thiếu bước? | Thiếu preflight cost cho LLM; thiếu eval chất lượng pick (doc 09) |
| Tối ưu được gì? | Tách God-function; cache render plan theo (source+params) mạnh hơn |
| Bug logic? | Không phát hiện bug rõ; dedup dựa "30 job gần nhất" là giả định ngầm |
| Race condition? | Được chặn: JOB_SEMAPHORE, NVENC_SEMAPHORE, source dedup 2 lớp, thread-local DB |
| Bottleneck? | Whisper (đã 1-lần + warmup + LRU), NVENC session cap, SQLite write (WAL) |
| Memory leak? | Whisper LRU cap 2 đóng lỗ; thread-conn close belt-and-suspenders |
| API thừa? | Không trong clip path; nhiều route phụ trợ (analytics/presets) tách sạch |
| Duplicate code? | **Có** — _set_stage, _safe_filename, terminal block dùng lại ở 3 mode |
| Abstraction sai? | recap/content import primitive nội bộ từ render_pipeline (coupling ẩn) |

## 5. Vấn đề trọng điểm

### CLIP-1: God-function 1934 dòng (đã nêu RE-1)
- **Ảnh hưởng:** Cao — CRITICAL tier, mọi platform/video type chịu tác động của
  1 thay đổi nhỏ.
- **Ngắn hạn:** tuân Render Edit Protocol; không "while I'm here".
- **Dài hạn:** rút stage (transcribe-heartbeat, clip-filter, finalize) thành
  module, đưa `run_render_pipeline` về ~300 dòng điều phối.

### CLIP-2: Fallback plan khi LLM None
- Có `_scored_from_render_plan(render_plan, fallback_scored)` — cần đảm bảo
  fallback không tạo clip kém chất lượng được đánh dấu "best". Không thấy bug
  nhưng nên có test đảm bảo fallback path vẫn qua QA.

## 6. Điểm

| Trục | Điểm |
|------|------|
| Đúng đắn workflow | 8 |
| Chống race/leak | 8.5 |
| Bảo trì (God-file) | 5 |
| Tối ưu | 7 |
| **Tổng** | **7.1** |
