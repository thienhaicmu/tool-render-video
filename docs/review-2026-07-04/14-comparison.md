# 14 — So sánh 3 Mode (Clip · Recap · Content)

## 1. Bảng so sánh tổng

| Trục | Clip | Recap | Content |
|------|------|-------|---------|
| `render_format` | `clips` | `recap` | `content` |
| Orchestrator | `run_render_pipeline` (1934) | `run_recap` (970) | `run_content` (553) |
| Nguồn | 1 video local | 1 phim/tập dài | Script (KHÔNG footage) |
| Whisper | Có (1 lần) | Có (1 lần) | Không |
| Scene detection | Có | Có (SceneMap song song) | Không |
| LLM call | 1 (select_render_plan) | 3-pass (story/editorial/binding) | 1 (select_content_plan) |
| Deterministic guard | clip_lock/exclude | snap-to-shots + trim-band | visual decision tree + budget |
| Đơn vị render | part (clip) | scene→part (mượn loop) | scene (tự loop) |
| Output | N clip 9:16 ranked | 1 video/tập + title-card | 1 video từ TTS+visual |
| Ranking | viral_scoring | chronological (neutral) | single (score 100) |
| Assemble | không (mỗi clip riêng) | concat episode | concat scenes + BGM |
| QA gate (#8) | per output | per episode | 1 output |
| Partial success | có | có (episode/part) | có (≥1 scene) |
| Parallel encode | NVENC-capped | NVENC-capped | CPU-capped (libx264) |

## 2. Điểm GIỐNG (code thực tế)

Cả 3 orchestrator có **cùng khung**:
1. `setup_render_pipeline(payload)` + `prepare_output_dir` + `register_job_log_dir`.
2. Hàm `_set_stage(stage, progress, message)` nội bộ — **gần như y hệt** ở 3 file
   (update_job_progress + _job_log + _emit_render_event với STAGE_TO_EVENT).
3. `_safe_filename()` — **định nghĩa trùng** ở content_pipeline.py:96 và
   recap_pipeline.py:86 (cùng regex `_FS_ILLEGAL_RE`, cùng logic).
4. Khối terminal: build `result_json` với outputs[] + Sacred #1 keys
   (`output_rank_score`/`is_best_output`/`is_best_clip`) + `is_partial_success`
   + upsert_job(DONE) + emit render.complete + `finally: unregister + close_thread_conn`.
5. Signature `(job_id, payload, resume_mode, *, load_session_fn, cleanup_session_fn)`
   — chung để `process_render` gọi thống nhất.

## 3. Điểm KHÁC (bản chất)

- **Clip**: viral ranking là trung tâm; nhiều output độc lập.
- **Recap**: story understanding + editorial + guardrail tất định là trung tâm;
  gom scene→episode.
- **Content**: sinh visual từ prompt + kiểm soát chi phí provider là trung tâm;
  không có nguồn.

## 4. Code reuse & shared services

**Reuse tốt (composition, không copy logic):**
- `pipeline_setup`, `qa_pipeline`, `render_events`, `pipeline_render_loop`,
  `recap_assembler.concat_clips`, `visual` seam, `ffmpeg_helpers`.
- Content & recap **dùng lại** `concat_clips` của assembler.
- Recap **dùng lại** `run_render_loop` + `PartRenderContext` của clips.

**Duplicate thực sự (copy logic — nên khử):**
| Thứ | Nơi | Khuyến nghị |
|-----|-----|-------------|
| `_safe_filename` | content:96, recap:86 | → `engine/util/fs.py` |
| `_set_stage` closure | 3 orchestrator | → helper `make_stage_setter(job_id, channel, render_format)` |
| Terminal result_json block | 3 orchestrator | → `finalize_render_job(job_id, outputs, render_format, ...)` |
| Parallel scene loop (content) vs run_render_loop | content tự viết vòng ThreadPool | → cân nhắc dùng chung loop |

## 5. Abstraction sai / coupling

- **Coupling ẩn:** recap/content import primitive nội bộ từ render_pipeline
  (`JOB_SEMAPHORE`, `_render_active_lock/count`) → 3 mode không thực sự "tách hoàn
  toàn" như doc-string tuyên bố; chúng chia sẻ concurrency state qua import trực
  tiếp module clips. **Nên** nâng lên `engine/concurrency.py` trung lập.
- **Ownership mờ:** `recap_assembler` nằm trong `stages/` nhưng phục vụ cả 3
  orchestrator → nên chuyển concat/assemble ra `engine/media/assembly.py`.

## 6. Đề xuất abstraction chung (không phá Sacred)

```
engine/pipeline/_orchestrator_base.py   (mới)
  · make_stage_setter(job_id, channel, render_format) -> _set_stage
  · finalize_render_job(job_id, channel, payload, outputs, render_format,
        failed, extra_result) -> upsert DONE + Sacred #1 keys + emit + cleanup
  · safe_output_stem(name)   (thay 2 _safe_filename)
engine/concurrency.py  (mới)
  · JOB_SEMAPHORE, render_active_lock, render_active_count  (nâng khỏi render_pipeline)
```
→ 3 orchestrator chỉ còn phần **khác biệt bản chất**; giảm ~150-200 dòng duplicate;
giảm rủi ro lệch Sacred #1 keys giữa 3 mode (hiện phải maintain 3 nơi).

## 7. Điểm

| Trục | Điểm |
|------|------|
| Reuse (composition) | 8 |
| Khử duplicate | 5 |
| Ranh giới mode | 6.5 |
| **Tổng** | **6.5** |
