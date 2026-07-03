# Render Pipeline — AI Video Render Studio

> Cập nhật 2026-06-29 từ source. Đây là vùng **CRITICAL** — đọc kỹ trước khi sửa.
> File chính: `backend/app/features/render/engine/pipeline/render_pipeline.py`.

## 1. Tổng quan

Pipeline biến một video nguồn thành N clip ngắn. Orchestrator
`run_render_pipeline(job_id, payload, ...)` điều phối tuần tự các stage cấp job,
rồi render từng part song song. Logic được tách thành nhiều module để giữ file
orchestrator quản lý được, nhưng `render_pipeline.py` vẫn sở hữu **state machine
JobStage** và `stages/part_renderer.py` sở hữu **state machine JobPartStage**.

## 2. State machine cấp JOB (đóng băng — Sacred Contract #4)

Enum tại `backend/app/core/stage.py` (`JobStage`):

```
QUEUED → STARTING → RUNNING → ANALYZING → TRANSCRIBING_FULL →
SCENE_DETECTION → SEGMENT_BUILDING → RENDERING → RENDERING_PARALLEL →
WRITING_REPORT → DONE
terminal: FAILED, CANCELLED
(DOWNLOADING giữ lại để tương thích bản ghi cũ, pipeline không phát ra)
```

`STAGE_TO_EVENT` (cùng file) ánh xạ mỗi stage → tên sự kiện WebSocket
(`render.start`, `render.analyze.start`, `render.ffmpeg.start`, …).

Tên các stage này được frontend khớp **string trực tiếp**. Không đổi tên, không
chèn stage mới mà chưa cập nhật mọi consumer WebSocket + UI.

## 3. State machine cấp PART (đóng băng — Sacred Contract #5)

`JobPartStage`:

```
QUEUED → WAITING → CUTTING → TRANSCRIBING → RENDERING → DONE
terminal: FAILED, SKIPPED
```

Chuyển trạng thái part nằm trong `stages/part_renderer.py` (delegate sang
`stages/part_db.py` cho 3 transition ghi DB).

## 4. Luồng orchestrator (theo `run_render_pipeline`)

1. **Setup** — `pipeline_setup.setup_render_pipeline(payload)`: chuẩn hoá
   payload, resolve channel, hook market-viral, tạo `output_dir`. Sau đó
   `prepare_output_dir()` tạo thư mục + phát event chuẩn bị output.
2. **Đăng ký log** + `work_dir = TEMP_DIR/job_id`. `upsert_job(... running ...)`.
3. **Source prep** — `pipeline_source_prep.prepare_render_source()`: phân giải
   nguồn (`source_mode="local"` hoặc `edit_session_id`), probe duration, chuẩn
   bị file. (Tải YouTube/TikTok là feature riêng `features/download/` — pipeline
   chỉ nhận đường dẫn local đã có.)
4. **Voice TTS thủ công** (nếu bật) — `pipeline_narration.run_manual_voice_tts()`.
5. **LLM pre-render** — `llm_pipeline.run_llm_pre_render()`: chạy Whisper
   transcribe toàn bộ video một lần (stage `TRANSCRIBING_FULL`), scene detection,
   và chọn segment (`scored`).
6. **Lấy RenderPlan** (khi `LLM_EMIT_RENDER_PLAN=1`, mặc định):
   - Resume: nạp RenderPlan đã lưu trong DB nếu `resume_from_last`.
   - Cache: tra `_llm_plan_cache_get` theo key gồm toàn bộ tham số ảnh hưởng.
   - Gọi `ai.llm.select_render_plan(provider=...)`. Nếu trả `None` → fallback
     logic suy từ payload (Sacred Contract #2 giữ nguyên hành vi cũ).
   - Persist plan vào cột `render_plan_json` (additive-safe).
7. **Suy `scored` từ RenderPlan** + lọc `clip_lock`/`clip_exclude`
   (defence-in-depth, không bao giờ raise).
8. **Inject overlay AI** (hook/cta) vào `normalized_text_layers`.
9. **Cấu hình phụ đề** theo `subtitle_viral_min_score` / `subtitle_only_viral_high`.
10. **Render loop** — `pipeline_render_loop.run_render_loop()` dispatch từng part
    qua `ThreadPoolExecutor`; mỗi part chạy `stages/part_renderer.py`.
11. **Finalize** — `pipeline_finalize.run_render_finalize()`: xếp hạng output,
    ghi `result_json` (kèm các key Sacred Contract #1), viết report, gắn tóm tắt
    AI visibility. Stage `WRITING_REPORT` → `DONE`.
12. **Cleanup** trong `finally`: đóng thread-local DB conn, dọn temp.

## 5. Render từng part (`stages/part_renderer.py`)

`part_renderer` là skeleton mỏng delegate sang 8 helper:

| Helper | Việc |
|--------|------|
| `part_render_context.py` | Dựng context cho part |
| `part_asset_planner.py` | Resolve subtitle policy + CTA + asset |
| `part_cut.py` | Cắt segment nguồn (CUTTING) |
| `part_render_setup.py` | Resolve camera strategy / crop |
| `part_render_encode.py` | Encode FFmpeg — **acquire NVENC_SEMAPHORE** |
| `part_voice_mix.py` | Trộn voice/narration |
| `part_render_finalize.py` | Cổng `qa_pipeline` (Sacred Contract #8) |
| `part_done.py` | Đánh dấu DONE + thumbnail |

Phụ trợ: `segment_metadata.py` (suy đường dẫn — pure helper), `part_db.py`
(3 transition ghi DB), `part_render_plan_resolvers.py`, `viral_scoring.py`,
`manifest_writer.py`.

## 6. Sacred Contracts liên quan pipeline

### #1 — `result_json` giữ alias tương thích ngược (mãi mãi)
Mọi blob `result_json` phải có 3 key: `output_rank_score`, `is_best_output`,
`is_best_clip`. Ghi tại `pipeline_finalize.py` + `pipeline_ranking.py`. UI history
đọc trực tiếp các string này — thiếu là mất dữ liệu im lặng (không raise).

### #4 / #5 — tên stage/part đóng băng
Xem mục 2 & 3.

### #6 — `_emit_render_event` đóng băng
`render_events.py`. Chữ ký (keyword-only): `channel_code, job_id, event, level,
message, step, context?, exception?, traceback_text?, duration_ms?, error_code?`.
Gọi ở 50+ chỗ. Output là stream thô feed vào WebSocket. Mỗi event phải có 3 key
top-level: `job`, `parts`, `summary`.

### #8 — `qa_pipeline.py` không bao giờ bypass
Cổng validate output duy nhất: bắt file thiếu, file quá nhỏ (hỏng/cụt), không có
video stream, không có audio stream, video 0 giây. Không bắt exception của nó để
trả "success", không hạ ngưỡng để cho qua một render hỏng.

## 7. Bảo vệ tài nguyên

- **`NVENC_SEMAPHORE`** (`encoder/ffmpeg_helpers.py`, mặc định 3, env
  `NVENC_MAX_SESSIONS`): giới hạn phiên NVENC GPU. Vượt giới hạn phần cứng →
  NVIDIA fail **tất cả** phiên đang chạy. `_run_ffmpeg_with_retry` tự acquire khi
  argv dùng codec NVENC. `motion/crop.py` chạy subprocess thô không tự khoá → 3
  call site trong `encoder/clip_renderer.py` phải acquire trước.
- **`JOB_SEMAPHORE`** (`render_pipeline.py`, env `MAX_RENDER_JOBS`, mặc định =
  `MAX_CONCURRENT_JOBS`): số pipeline vào vùng encode cùng lúc.
- **Helper đường dẫn FFmpeg bắt buộc dùng**: `safe_filter_path()`,
  `get_ffmpeg_bin()`, `get_ffprobe_bin()`. Không nối chuỗi path thô vào filter
  graph (path Windows có space/ngoặc làm FFmpeg lỗi im lặng).
- **Motion-crop stderr drain** (`motion/crop.py`, fix 2026-07-03): vòng lặp bơm
  rawvideo vào `ffmpeg` stdin PHẢI rút `stderr` song song bằng daemon thread
  (`_drain_pipe`). Nếu không, buffer stderr đầy → ffmpeg chặn ghi stderr → ngừng
  đọc stdin → `stdin.write()` chặn → **deadlock treo cả render, log câm**. Fix
  cũng log `argv` ffmpeg + heartbeat frame để chẩn đoán khi treo.
- **Recap episode concat** (`recap_assembler.py`): title card phải khớp fps +
  audio sample-rate của scene (probe qua `probe_av_spec`) để concat **copy-stream**
  (nhanh) thay vì bị `_demuxer_output_sane` loại rồi re-encode chậm mỗi lần.

## 8. Không bao giờ làm (Render Never-Do)

- Không bypass `qa_pipeline.py` để giả thành công.
- Không biến partial-success (8/10 clip OK) thành failure hay full-success.
- Không đổi `_emit_render_event` mà chưa cập nhật mọi consumer.
- Không bỏ logic resume/retry (render dài 20–60 phút, gián đoạn là chuyện thường).
- Không bỏ cleanup nguồn ở nhánh failure (rò rỉ disk im lặng).

## 9. Quy trình sửa bắt buộc (tóm tắt)

Với mọi thay đổi `render_pipeline.py` / `part_renderer.py` / `qa_pipeline.py` /
`motion/crop.py`:

1. Đọc tài liệu này + [ARCHITECTURE.md](ARCHITECTURE.md).
2. Planner ra phân tích (file, dòng, risk, test, rollback).
3. Người dùng phê duyệt rõ ràng.
4. Chạy **full pytest** lấy baseline TRƯỚC khi sửa.
5. Đọc lại file ở trạng thái hiện tại (không sửa từ trí nhớ).
6. Sửa tối thiểu bằng Edit (không Write toàn file).
7. Chạy lại full pytest, so baseline. Có regression = DỪNG, báo cáo.
